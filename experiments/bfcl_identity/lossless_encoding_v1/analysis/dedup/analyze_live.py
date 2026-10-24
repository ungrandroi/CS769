"""Read-only Dedup development comparison; never edits queue, codecs or runs."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import statistics
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
STUDY=HERE.parents[1]
OLD=ROOT/'experiments/bfcl_identity/work1000_research/tasks'
sys.path.insert(0,str(ROOT/'scripts'))
from core.lossless_event import decode
from core.optimized_graph import _same,restore_history,rebuild_original_graph

LABELS=[f'dedup-{variant}-v1-{explanation}'for variant in ('tables','shared')for explanation in ('none','minimal')]

OBSERVATIONS={'dedup-tables-v1-none':{
'multi_turn_base_9/seed3301':'After reading the archived report, continuation calls echo twice with manually alphabetized words and finishes without sort. Official required sorted_content is absent.',
'multi_turn_long_context_9/seed1103':'Continuation writes a short manually sorted word list to sorted_line.txt, then deletes it. It never invokes sort, so the official required sorted_content is absent.',
'multi_turn_long_context_9/seed2207':'Continuation lists and reads the report, then answers in text without sort. All three losses share tool-action omission/task-interpretation divergence, not identified payload corruption.'}}

def load(path):return json.loads(path.read_text())
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def refs(value,counts):
    if isinstance(value,dict):
        if set(value)=={'$shared'}:counts[value['$shared']]+=1
        else:
            for v in value.values():refs(v,counts)
    elif isinstance(value,list):
        for v in value:refs(v,counts)

def analyze(label):
    explanation=label.rsplit('-',1)[-1]
    paths=sorted((STUDY/'development').glob('*/seed*/'+label+'/manifest.json'))
    manifests=[load(p)for p in paths]
    assert len(paths)==18 and sum(m.get('triggered') and m['status']=='complete'for m in manifests)==13, f'Incomplete {label}'
    methods=['identity','dedup-none']+(['dedup-minimal']if explanation=='minimal'else[])
    rows=[];untriggered=[]
    for path,manifest in zip(paths,manifests):
        run=path.parent;task,seed=run.parts[-3:-1]
        if not manifest['triggered']:
            untriggered.append({'task':task,'seed':seed,'status':manifest['status'],'passed':manifest.get('passed')});continue
        row={'task':task,'seed':seed,'trigger_index':manifest['trigger_index']}
        for method,loc in [(m,OLD/task/seed/m)for m in methods]+[('candidate',run)]:
            m=load(loc/'manifest.json');a=[r for r in load(loc/'accounting.json')if r['index']>=manifest['trigger_index']]
            row[method]={'passed':m['passed'],'first_input_tokens':a[0]['input_tokens'],
                         'mean_post_input_tokens':statistics.mean(r['input_tokens']for r in a),
                         'post_requests':len(a),'run_path':str(loc.relative_to(ROOT))}
        meta=load(run/'memory-metadata.json');baseline=load(OLD/task/seed/'dedup-none/memory-metadata.json')
        same_explanation=load(OLD/task/seed/f'dedup-{explanation}'/'memory-metadata.json')
        restored=decode(meta['encoded']);history=load(run/'checkpoint-history.json')
        assert _same(restored,meta['graph']) and _same(restored,baseline['graph'])
        assert _same(restore_history(restored),history)
        assert _same(rebuild_original_graph(restored),rebuild_original_graph(baseline['graph']))
        assert meta['instruction']==same_explanation['instruction']
        first_request=next(json.loads(line)for line in (run/'native.jsonl').read_text().splitlines()if json.loads(line)['event']=='request')
        assert any(m.get('content')==(run/'memory.txt').read_text()for m in first_request['request']['messages'])
        row['audits']={'delivered_payload_exact':True,'history_exact':True,'original_graph_exact':True,
                       'actual_request_contains_exact_memory':True,'external_instruction_matches_same_explanation_old_diagnostic':True}
        counts=Counter();refs(meta['encoded']['graph'],counts)
        dictionary=meta['encoded'].get('shared_values',{})
        row['sharing']={'entries':len(dictionary),'references':sum(counts.values()),
                        'unused':sorted(set(dictionary)-set(counts)),
                        'body_tokens':meta['body_tokens'],'instruction_tokens':meta['instruction_tokens']}
        score=load(run/'official-score.json')
        row['official_errors']=[{'type':d.get('error',{}).get('error_type'),'message':d.get('error',{}).get('error_message')}for d in score.get('diagnostics',[])]
        rows.append(row)
    summary={m:{'passed':sum(r[m]['passed']for r in rows),'total':len(rows),
                'first_input_mean':statistics.mean(r[m]['first_input_tokens']for r in rows),
                'mean_post_input_macro_mean':statistics.mean(r[m]['mean_post_input_tokens']for r in rows)}for m in methods+['candidate']}
    paired={}
    for m in methods:
        d={k:[]for k in ('gains','losses','both_success','both_fail')}
        for r in rows:
            key=f"{r['task']}/{r['seed']}";control=r[m]['passed'];candidate=r['candidate']['passed']
            outcome=('both_success'if candidate else'both_fail')if candidate==control else('gains'if candidate else'losses')
            d[outcome].append(key)
        paired[m]=d
    sharing={'nonempty_checkpoints':sum(bool(r['sharing']['entries'])for r in rows),
             'entries':sum(r['sharing']['entries']for r in rows),'references':sum(r['sharing']['references']for r in rows),
             'unused_entries':sum(len(r['sharing']['unused'])for r in rows)}
    report={'generated_at':datetime.now(timezone.utc).isoformat(),'label':label,'primary_baseline':'dedup-none',
            'summary':summary,'paired':paired,'rows':rows,'untriggered':untriggered,'actual_sharing':sharing,
            'case_observations':OBSERVATIONS.get(label,{}),
            'limitations':['Development repeated prefixes only; not unseen-task or fresh-seed validation.',
             'Selected frozen Dedup baseline has no external instruction. Minimal is an added instruction condition relative to that baseline.',
             'Old dedup-minimal, where shown, is a same-instruction diagnostic comparator, not the selected frozen baseline.',
             'Inline codec rules are counted as input and differ even when external instruction is none.',
             'Post means are calculated within each trajectory then across trajectories; include fixed prompts/tools.',
             'Strict recovery does not guarantee model behavior invariance.']}
    name='live-feedback-'+label.removeprefix('dedup-').replace('-v1','')
    write(HERE/(name+'.json'),report)
    lines=[f'# Dedup development feedback: {label}','','Primary frozen baseline: **dedup-none**. Minimal adds an external instruction relative to that baseline.','',
           '| Method | Passed | First input mean | Mean post input |','|---|---:|---:|---:|']
    for m,s in summary.items():lines.append(f"| {m} | {s['passed']}/{s['total']} | {s['first_input_mean']:,.2f} | {s['mean_post_input_macro_mean']:,.2f} |")
    lines+=['','| Reference | Gains | Losses | Both pass | Both fail |','|---|---:|---:|---:|---:|']
    for m,d in paired.items():lines.append(f"| {m} | {len(d['gains'])} | {len(d['losses'])} | {len(d['both_success'])} | {len(d['both_fail'])} |")
    lines+=['',f"Actual shared values: {sharing['nonempty_checkpoints']}/13 nonempty, {sharing['entries']} entries, {sharing['references']} references, {sharing['unused_entries']} unused entries.",'',
            'All 13 actual memories directly decode to the original delivered Dedup payload and preserve history/original graph. Native requests contain exactly the saved memory. Five untriggered records are excluded.','',
            'These are development observations. Reduced tokens or exact recovery alone do not establish preserved task ability.','']
    if OBSERVATIONS.get(label):
        lines+=['## Observed baseline losses','']+[f'- **{key}**: {text}'for key,text in OBSERVATIONS[label].items()]+['']
    (HERE/(name+'.md')).write_text('\n'.join(lines))
    return report

p=argparse.ArgumentParser();p.add_argument('--label',choices=LABELS);args=p.parse_args()
reports={label:analyze(label)for label in ([args.label]if args.label else LABELS)}
if args.label:
    print(json.dumps(reports[args.label]['summary'],indent=2));raise SystemExit
ranked=sorted([{'label':label,**r['summary']['candidate']}for label,r in reports.items()],key=lambda r:(-r['passed'],r['mean_post_input_macro_mean'],r['label']))
baseline=reports[LABELS[0]]['summary']['dedup-none'];best=ranked[0]
report={'selection_rule':'Descending passes, ascending mean post-input macro mean, then label (controller preregistration).',
        'ranked_candidates':ranked,'frozen_baseline':baseline,'identity':reports[LABELS[0]]['summary']['identity'],
        'development_winner':best['label'],'development_adoption_criterion_met':best['passed']>=baseline['passed']and best['mean_post_input_macro_mean']<baseline['mean_post_input_macro_mean'],
        'winner_pairs':reports[best['label']]['paired'],'actual_sharing':{l:r['actual_sharing']for l,r in reports.items()},
        'limitations':reports[LABELS[0]]['limitations']}
selection_path=STUDY/'selection.json'
if selection_path.exists():
    selection=load(selection_path)
    checks={}
    for method,expected in [('dedup',report),('event',load(HERE.parent/'event/final-development-summary.json'))]:
        chosen=selection['selected'][method]
        assert chosen['label']==expected['development_winner']
        assert chosen['development_adoption_criterion_met']==expected['development_adoption_criterion_met']
        winner=expected['ranked_candidates'][0]
        evidence=next(row for row in selection['evidence'][method]if row['label']==chosen['label'])
        assert evidence['passed']==winner['passed']
        assert math.isclose(evidence['mean_input'],winner['mean_post_input_macro_mean'],rel_tol=1e-12)
        checks[method]={'label':chosen['label'],'winner_matches_independent_rank':True,
                        'passed_count_matches':True,'mean_input_matches':True,
                        'development_adoption_flag_matches':True}
    write(HERE/'controller-selection-readonly-check.json',{'checks':checks,'selection_path':str(selection_path),'mode':'read-only; no controller state or selection changed'})
    report['controller_selection_verified']=True
else:
    report['controller_selection_verified']=False

write(HERE/'final-development-summary.json',report)
lines=['# Event Graph-Dedup development comparison','','Frozen baseline: dedup-none; minimal is a new external-instruction condition relative to it.','',
       '| Configuration | Passed | First input mean | Mean post input |','|---|---:|---:|---:|']
for label,s in [('Identity',report['identity']),('Frozen Dedup-none',baseline)]+[(r['label'],r)for r in ranked]:
    lines.append(f"| {label} | {s['passed']}/{s['total']} | {s['first_input_mean']:,.2f} | {s['mean_post_input_macro_mean']:,.2f} |")
lines+=['',f"Ability-first development winner: **{best['label']}**; adoption criterion met: **{report['development_adoption_criterion_met']}**.",'',
        'All 52 actual candidate memories passed exact payload, history, rebuilt graph and native request checks. Counts include fixed tools/system prompts; means are per-trajectory macro means, not cumulative tokens.','',
        'This is development selection, not independent validation. Fresh-seed evaluation is run separately by the controller.','']
(HERE/'final-development-summary.md').write_text('\n'.join(lines))
print(json.dumps({'winner':best,'baseline':baseline},indent=2))
