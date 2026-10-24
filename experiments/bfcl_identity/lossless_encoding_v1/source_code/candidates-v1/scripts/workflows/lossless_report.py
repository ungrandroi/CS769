"""Paired descriptive report; automatic checks are not independent review."""
import argparse
import json
from pathlib import Path
from statistics import mean
from workflows.lossless_controller import read, write


def summarize(rows):
    if not rows:
        return dict(n=0)
    return dict(n=len(rows),passed=sum(r['passed'] for r in rows),
                first_input=mean(r['first_input'] for r in rows),
                mean_post_input=mean(r['mean_post_input'] for r in rows),
                mean_peak_input=mean(r['peak_input'] for r in rows))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,required=True)
    args=parser.parse_args()
    root=args.root
    plan=read(root/'task-split.json')
    rows,untriggered=[],[]
    for task in plan['tasks']:
        for seed in plan['seeds']:
            base=root/'evaluation'/task['id']/f'seed{seed}'
            identity=read(base/'identity/manifest.json')
            if not identity['triggered']:
                untriggered.append(dict(task=task['id'],seed=seed,passed=identity['passed']))
                continue
            for label in ('identity','state-baseline','state-optimized',
                          'event-baseline','event-optimized','dedup-baseline','dedup-optimized'):
                path=base/label
                m=read(path/'manifest.json')
                assert m['status']=='complete' and m['triggered']
                acc=[a for a in read(path/'accounting.json') if a['index']>=m['trigger_index']]
                assert acc
                rows.append(dict(task=task['id'],seed=seed,split=task['split'],
                                 method=label,passed=m['passed'],first_input=acc[0]['input_tokens'],
                                 mean_post_input=mean(a['input_tokens'] for a in acc),
                                 peak_input=max(a['input_tokens'] for a in acc),
                                 mean_fixed=mean(a['fixed_tokens'] for a in acc),
                                 mean_working=mean(a['working_tokens'] for a in acc),
                                 live_requests=len(acc),memory_tokens=m.get('memory_tokens'),
                                 instruction_tokens=m.get('instruction_tokens')))
    groups={}
    for split in ('all','development','nondevelopment'):
        subset=[r for r in rows if split=='all' or
                (r['split']=='development')==(split=='development')]
        groups[split]={label:summarize([r for r in subset if r['method']==label])
                       for label in sorted({r['method'] for r in subset})}
    pairs=[]
    by={(r['task'],r['seed'],r['method']):r for r in rows}
    for row in rows:
        if not row['method'].endswith('-optimized'):
            continue
        method=row['method'].split('-')[0]
        baseline=by[(row['task'],row['seed'],method+'-baseline')]
        identity=by[(row['task'],row['seed'],'identity')]
        pairs.append(dict(task=row['task'],seed=row['seed'],method=method,
                          identity_passed=identity['passed'],baseline_passed=baseline['passed'],
                          optimized_passed=row['passed'],
                          ratio_to_baseline=row['mean_post_input']/baseline['mean_post_input'],
                          ratio_to_identity=row['mean_post_input']/identity['mean_post_input']))
    write(root/'reports/summary.json',dict(
        status='descriptive_pending_independent_review',groups=groups,rows=rows,pairs=pairs,
        untriggered=untriggered,selection=read(root/'selection.json'),
        limitations=['Historically seen conditions; independent seed repetitions, not unseen tasks.',
                     'Conditions and seeds are clustered within 13 task families.',
                     'Input is per-trajectory mean of actual post-conversion native requests.',
                     'Untriggered cases are excluded from graph-effect estimates.']))
    print(json.dumps(groups,indent=2))


if __name__=='__main__':
    main()
