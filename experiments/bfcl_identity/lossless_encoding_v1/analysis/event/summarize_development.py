"""Read-only Event candidate comparison after all six planned cells complete."""
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
STUDY=HERE.parents[1]
labels=[f'event-{variant}-v1-{explanation}' for variant in ('tables','shared')
        for explanation in ('none','minimal','full')]
for label in labels:
    manifests=[json.loads(path.read_text()) for path in (STUDY/'development').glob('*/seed*/'+label+'/manifest.json')]
    assert len(manifests)==18 and sum(m.get('triggered') and m['status']=='complete' for m in manifests)==13, f'Incomplete: {label}'
for label in labels:
    subprocess.run([sys.executable,str(HERE/'analyze_live.py'),'--label',label],check=True,stdout=subprocess.DEVNULL)
reports={label:json.loads((HERE/('live-feedback-'+label.removeprefix('event-').replace('-v1','')+'.json')).read_text())for label in labels}
ranked=sorted([{'label':label,**report['summary']['candidate']}for label,report in reports.items()],
              key=lambda row:(-row['passed'],row['mean_post_input_macro_mean'],row['label']))
baseline=reports[labels[0]]['summary']['event-full']
winner=ranked[0]
report={'selection_rule':'Descending official passed count, then ascending mean post-conversion input (per-trajectory macro mean), then label. Same as preregistered controller.',
        'ranked_candidates':ranked,'frozen_event_full_baseline':baseline,
        'identity':reports[labels[0]]['summary']['identity'],
        'development_winner':winner['label'],
        'development_adoption_criterion_met':winner['passed']>=baseline['passed'] and winner['mean_post_input_macro_mean']<baseline['mean_post_input_macro_mean'],
        'winner_pairs':reports[winner['label']]['paired'],
        'actual_shared_utilization':json.loads((HERE/'shared-utilization.json').read_text()),
        'interpretation':'Development selection only. No claims of held-out generalization; fresh seeds are independently evaluated by the controller. Shared references and inline rules both change the representation. All candidates preserve the exact original delivered graph, but recoverability does not guarantee identical model behavior.',
        'full_report_paths':{label:str(HERE/('live-feedback-'+label.removeprefix('event-').replace('-v1','')+'.json'))for label in labels}}
(HERE/'final-development-summary.json').write_text(json.dumps(report,indent=2)+'\n')
lines=['# Event Graph development comparison','',
       'All six planned configurations completed on the same 13 triggered prefixes. Five untriggered runs per configuration are excluded.','',
       '| Configuration | Passed | First input mean | Mean post input |',
       '|---|---:|---:|---:|']
for label,s in [('Identity',report['identity']),('Frozen Event-full',baseline)]+[(r['label'],r)for r in ranked]:
    lines.append(f"| {label} | {s['passed']}/{s['total']} | {s['first_input_mean']:,.2f} | {s['mean_post_input_macro_mean']:,.2f} |")
lines+=['',f"Preregistered ability-first winner: **{winner['label']}**. Development adoption criterion: **{report['development_adoption_criterion_met']}**.",'',
        'Input counts include fixed tools and system prompts. Post input averages within each trajectory first, then equally across trajectories; these are not cumulative totals.','',
        'Actual shared-value dictionaries are nonempty for 13/13 Event checkpoints, containing 78 entries with 480 references and no unused entries. Shared representation reduces graph body tokens by a mean 167.54 relative to tables, including its visible rules. Behavioral differences cannot be attributed uniquely to deduplication because the reference grammar also changes.','',
        'All actual saved memories were checked against native requests, decoded directly to the frozen delivered payload, and checked for exact history and original graph restoration. External instructions match the old same-explanation baseline.','',
        'This ranking is for development selection only; fresh-seed validation must assess whether gains survive selection. No running code, queue or trajectories were changed by this analysis.','']
(HERE/'final-development-summary.md').write_text('\n'.join(lines))
print(json.dumps({'winner':winner,'baseline':baseline},indent=2))
