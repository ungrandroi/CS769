"""Read-only live development audit; writes only analysis artifacts."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import sys

ROOT=Path(__file__).resolve().parents[5]
sys.path.insert(0,str(ROOT/'scripts'))
from core.lossless_event import decode
from core.optimized_graph import _same, restore_history, rebuild_original_graph

p=argparse.ArgumentParser();p.add_argument('--label',default='event-tables-v1-none');args=p.parse_args()
OLD=ROOT/'experiments/bfcl_identity/work1000_research/tasks'
NEW=ROOT/'experiments/bfcl_identity/lossless_encoding_v1/development'
OUT=Path(__file__).parent
explanation=args.label.rsplit('-',1)[-1]
reference_methods=['identity','event-full','event-none']
if explanation=='minimal': reference_methods.append('event-minimal')
rows=[];untriggered=[]
for manifest_path in sorted(NEW.glob('*/seed*/'+args.label+'/manifest.json')):
    run=manifest_path.parent; task, seed=run.parts[-3:-1]
    manifest=json.loads(manifest_path.read_text())
    if not manifest.get('triggered'):
        untriggered.append({'task':task,'seed':seed,'status':manifest['status'],
                            'passed':manifest.get('passed')})
        continue
    if manifest['status'] != 'complete':
        continue
    row={'task':task,'seed':seed,'trigger_index':manifest['trigger_index']}
    for method,loc in [(method,OLD/task/seed/method) for method in reference_methods]+[('candidate',run)]:
        m=json.loads((loc/'manifest.json').read_text())
        a=json.loads((loc/'accounting.json').read_text())
        suffix=[item for item in a if item['index']>=manifest['trigger_index']]
        row[method]={'passed':m['passed'],'first_input_tokens':suffix[0]['input_tokens'],
                     'mean_post_input_tokens':statistics.mean(item['input_tokens'] for item in suffix),
                     'post_requests':len(suffix),'run_path':str(loc.relative_to(ROOT))}
    meta=json.loads((run/'memory-metadata.json').read_text())
    baseline=json.loads((OLD/task/seed/'event-full/memory-metadata.json').read_text())
    history=json.loads((run/'checkpoint-history.json').read_text())
    matched_meta=json.loads((OLD/task/seed/f'event-{explanation}'/'memory-metadata.json').read_text())
    assert meta['instruction']==matched_meta['instruction']
    restored=decode(meta['encoded'])
    assert _same(restored,meta['graph']) and _same(restored,baseline['graph'])
    assert _same(restore_history(restored),history)
    assert _same(rebuild_original_graph(restored),rebuild_original_graph(baseline['graph']))
    first_req=next(json.loads(line) for line in (run/'native.jsonl').read_text().splitlines()
                   if json.loads(line)['event']=='request')
    memory=(run/'memory.txt').read_text()
    # The serialized user-role memory itself is what was sent to the model.
    assert any(message.get('content') == memory for message in first_req['request']['messages'])
    row['audits']={'actual_request_contains_exact_memory':True,
                   'external_instruction_exactly_matches_old_same_explanation':True,
                   'payload_matches_old_event_full_exactly':True,
                   'history_exact':True,'original_graph_rebuilt_exact':True,
                   'encoded_sha256':hashlib.sha256(meta['body'].encode()).hexdigest()}
    official=json.loads((run/'official-score.json').read_text())
    row['official_errors']=[{'type':d.get('error',{}).get('error_type'),
                            'message':d.get('error',{}).get('error_message')}
                           for d in official.get('diagnostics',[])]
    rows.append(row)

summary={}
for method in reference_methods+['candidate']:
    summary[method]={'passed':sum(row[method]['passed'] for row in rows),'total':len(rows),
                     'first_input_mean':statistics.mean(row[method]['first_input_tokens'] for row in rows),
                     'mean_post_input_macro_mean':statistics.mean(row[method]['mean_post_input_tokens'] for row in rows)}
paired={}
for method in reference_methods:
    both_success=[];both_fail=[];gains=[];losses=[]
    for row in rows:
        key=f"{row['task']}/{row['seed']}"
        if row['candidate']['passed'] and row[method]['passed']: both_success.append(key)
        elif not row['candidate']['passed'] and not row[method]['passed']:both_fail.append(key)
        elif row['candidate']['passed']:gains.append(key)
        else:losses.append(key)
    paired[method]={'both_success':both_success,'both_fail':both_fail,'gains':gains,'losses':losses}

observations={
'multi_turn_base_9/seed3301':{
 'observation':'Instead of sorting ArchivedFinalReport2024.txt, continuation creates line1.txt, writes alphabetized words, sorts that temporary file, and removes it. Official checker misses sorted_content for the report.',
 'baseline_behavior':'Event-full invokes sort on ArchivedFinalReport2024.txt; Event-none also passes.',
 'classification':'Post-conversion task interpretation/action selection divergence; no payload loss observed.'},
'multi_turn_long_context_3/seed3301':{
 'observation':'Prefix already copied both test files and entered backup_tests. Candidate repeats cp from inside backup_tests, creating a plain file named backup_tests; the next cp fails Not a directory. It ends by asking permission instead of accepting the already completed copies.',
 'retained_evidence':'Decoded active cwd fact f21 is backup_tests; successful cp events a7/a8 and cd a9 remain intact. Source returns and complete original payload match the baseline exactly.',
 'baseline_behavior':'Event-full lists the completed backup and stops successfully; Event-none already fails this case.',
 'classification':'Previously completed action/current-location recognition failure is consistent with the trace, but internal cause is not established.'},
'multi_turn_long_context_37/seed2207':{
 'observation':'Candidate creates 7.txt from its count of server-error mentions. User requested file name from line count; earlier wc returned count 1 and official target is 1.txt.',
 'retained_evidence':'Decoded payload retains active cwd /temp and original wc responses. Candidate also rechecks wc after compaction and receives 1 again.',
 'baseline_behavior':'Event-full creates 1.txt; Event-none also passes.',
 'classification':'Wrong referent for requested number after later interaction, not missing line-count evidence.'},
'multi_turn_long_context_9/seed1103':{
 'observation':'Candidate calls cat then gives a textual word-sorting response without invoking sort on the archived report. Official checker misses required sorted_content result.',
 'baseline_behavior':'Event-full invokes sort and passes; Event-none already fails.',
 'classification':'Tool-action omission/task interpretation divergence; no payload loss observed.'},
'multi_turn_long_context_9/seed2207':{
 'observation':'Candidate and both old Event variants fail while Identity succeeds. This is not a newly introduced loss relative to the frozen Event baseline.',
 'classification':'Existing Event-versus-Identity loss, not new codec evidence.'},
'multi_turn_long_context_9/seed3301':{
 'observation':'Candidate passes where Identity and Event-full fail; Event-none already passes.',
 'classification':'Gain relative to full/Identity, no gain relative to matched zero-instruction baseline.'}}

observations_by_label={'event-tables-v1-none':observations,
'event-tables-v1-minimal':{'recovery_from_none':{
 'observation':'All five none failures pass with the same encoded payload plus the 32-token minimal instruction. LC3/3301 lists and ends; LC37/2207 creates 1.txt; base9/3301 and LC9/1103 invoke report sort; LC9/2207 sorts a temporary exact copy of the full line and removes it.',
 'classification':'Development-only instruction sensitivity; does not establish a stable causal benefit.'}},
'event-tables-v1-full':{
 'multi_turn_long_context_37/seed3301':{
  'observation':'The prefix already returned line counts for 31 files in one batch. After conversion the model checks the files again, but sends one wc per request. It reaches the existing BFCL turn step limit before finishing the file list; later user turns are never reached.',
  'retained_evidence':'All original wc calls and results survive exact decoding. Different filenames are distinct calls, not identical-call duplication. The failure is official force_terminated, not an infrastructure failure.',
  'baseline_behavior':'Old Event-full passes; its rechecking is batched, allowing the remaining user turns to execute.',
  'classification':'Sequential-versus-batched action planning consumes the request budget; no stored evidence loss observed.'},
 'multi_turn_long_context_9/seed1103':{
  'observation':'The continuation tries cd Archives while already inside it, observes the error, lists and reads the report, then answers in text without invoking sort. Official checker misses sorted_content.',
  'retained_evidence':'Current-location and original tool-return evidence remain exactly intact.',
  'baseline_behavior':'Old Event-full invokes sort and passes.',
  'classification':'Current-location/action selection divergence despite identical full external instruction.'}}}

observations_by_label['event-shared-v1-none']={
'multi_turn_base_37/seed1103':{
 'observation':'The prefix already created 1.txt for the final user request. After conversion, the continuation returns to the earlier line-count request, tries cd temp, checks pwd/ls/wc, and reports that 1.txt is empty. It never appends the requested sentence.',
 'retained_evidence':'The current user request, touch result, and all earlier history survive direct decoding exactly.',
 'baseline_behavior':'Old Event-full and tables-none both append the sentence and pass.',
 'classification':'Current-task focus regression, not missing source history. Internal cause cannot be inferred from this single trajectory.'}}

report={'generated_at':datetime.now(timezone.utc).isoformat(),'candidate':args.label,
        'scope':'Development triggered checkpoints only; no final validation inference performed by this analysis.',
        'summary':summary,'paired':paired,'untriggered':untriggered,'rows':rows,
        'case_observations':observations_by_label.get(args.label,{}),
        'limitations':['Single continuation per method for each shared prefix. Three seeds reuse the same task families.',
         f'Candidate {explanation} vs Event-full changes the codec'+(' but retains the identical full external instruction.' if explanation=='full' else ' and external instruction length together; cannot isolate encoding causality from that comparison.'),
         f'Event-{explanation} is the matched external-instruction comparison; model-visible codec rules still differ.',
         'All reported input counts include fixed tool/system costs; post means average within each trajectory, then equally across trajectories.',
         'Successful strict restoration proves storage preservation, not unchanged model behavior or reasoning.',
         'Five untriggered runs are reported separately and not counted as graph-conversion evidence.']}
name='live-feedback-'+args.label.removeprefix('event-').replace('-v1','')
(OUT/(name+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
lines=[f'# Development feedback: {args.label}','',f'Actual graph continuations: {len(rows)}. Untriggered: {len(untriggered)} (excluded below).','',
       '| Method | Official passes | First input mean | Mean post input per trajectory |','|---|---:|---:|---:|']
for method,s in summary.items():
    lines.append(f"| {method} | {s['passed']}/{s['total']} | {s['first_input_mean']:,.2f} | {s['mean_post_input_macro_mean']:,.2f} |")
lines+=['','All input token counts include fixed tools/system costs; these are not cumulative input counts.','',
        '| Paired reference | Gains | Losses | Both pass | Both fail |','|---|---:|---:|---:|---:|']
for method,s in paired.items():
    lines.append(f"| {method} | {len(s['gains'])} | {len(s['losses'])} | {len(s['both_success'])} | {len(s['both_fail'])} |")
lines+=['','Every candidate payload was decoded directly and checked against the old Event-full delivered payload; histories and rebuilt original graphs also match. The first native request contains exactly the saved memory text. No payload loss was observed.','',
        ('**Attribution limit:** The full external instruction is held identical to old Event-full; representation and its embedded decoding rules change. This is one development sample, not proof of stable improvement.' if explanation=='full' else f'**Attribution limit:** {explanation} versus full changes both encoding and external explanation. Compare event-{explanation} separately; one development sample does not establish stable effects.')]
if args.label in ('event-tables-v1-none','event-tables-v1-full','event-shared-v1-none'):
    lines+=['','## Observed losses relative to Event-full','']
    for key in paired['event-full']['losses']:
        detail=observations_by_label[args.label][key]
        lines.append(f"- **{key}**: {detail['observation']} {detail.get('retained_evidence','')} Baseline: {detail['baseline_behavior']}")
lines+=['','## Next decision','',
        (('This development candidate currently matches or exceeds the frozen Event-full score; retain as a promising candidate, not a final success claim.' if summary['candidate']['passed']>=summary['event-full']['passed'] else 'This development candidate currently loses completion relative to frozen Event-full; token savings alone do not justify accepting it.')+' Wait for all preplanned instruction/shared-value comparisons before selection. Do not change running frozen code or retry failures. Exact recoverability does not imply identical model behavior.'),'']
(OUT/(name+'.md')).write_text('\n'.join(lines))
print(json.dumps({'paths':[str(OUT/(name+'.json')),str(OUT/(name+'.md'))],'summary':summary,'paired_counts':{k:{kk:len(vv) for kk,vv in v.items()}for k,v in paired.items()}},indent=2))
