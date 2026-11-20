"""Read-only progress and paired per-request reports for working-token trials."""
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean

METHODS = ('identity','state','event','dedup')


def read(path):
    return json.loads(path.read_text())


def summarize(root, selection=None):
    plan = read(root/'task-split.json')
    rows, requests, coverage = [], [], []
    choice = selection or {m:'none' for m in METHODS if m!='identity'}
    for task in plan['tasks']:
        for seed in plan['seeds']:
            base = root/'tasks'/task['id']/f'seed{seed}'
            if not (base/'identity/manifest.json').exists():
                continue
            identity = read(base/'identity/manifest.json')
            triggered = identity.get('triggered',False)
            coverage.append(dict(task=task['id'],seed=seed,split=task['split'],
                                 status=identity['status'],triggered=triggered,
                                 passed=identity.get('passed'),trigger_index=identity.get('trigger_index')))
            for method in METHODS:
                directory = base/('identity' if method=='identity' else method+'-'+choice[method])
                inherited = method!='identity' and identity['status']=='complete' and not triggered
                if inherited:
                    manifest = identity
                    directory = base/'identity'
                elif (directory/'manifest.json').exists():
                    manifest=read(directory/'manifest.json')
                else:
                    continue
                row=dict(task=task['id'], family=task['family'], split=task['split'], seed=seed,
                         method=method, explanation='' if method=='identity' else choice[method],
                         status='not_applicable' if inherited else manifest['status'],
                         passed=None if inherited else manifest.get('passed'),
                         inherited_identity_passed=manifest.get('passed') if inherited else None,
                         triggered=triggered, inherited_identity_without_conversion=inherited,
                         trigger_index=identity.get('trigger_index'),
                         first_input=manifest.get('first_input') if triggered else None,
                         identity_first_input=identity.get('first_input'),
                         source_work_tokens=identity.get('source_work_tokens'),
                         instruction_tokens=manifest.get('instruction_tokens',0),
                         live_requests=0 if inherited else manifest.get('live_requests'))
                row['first_input_ratio']=row['first_input']/row['identity_first_input'] if row['first_input'] and row['identity_first_input'] else None
                if (directory/'accounting.json').exists():
                    acc=read(directory/'accounting.json')
                    live=[r for r in acc if triggered and r['index']>=identity['trigger_index']]
                    row['continuation_requests']=len(live)
                    row['continuation_input_mean']=mean(r['input_tokens'] for r in live) if live else None
                    row['continuation_input_max']=max((r['input_tokens'] for r in live),default=None)
                    if not inherited:
                        for req in acc:
                            requests.append(dict(task=task['id'],run_seed=seed,method=method,
                                                 explanation=row['explanation'], **req))
                rows.append(row)
    groups=[]
    for split in ['all','development','reserved_this_cycle','new_condition_transfer']:
        for method in METHODS:
            for subset in ['all_completed','triggered_completed']:
                eligible=[r for r in rows if r['method']==method and r['status']=='complete'
                          and (split=='all' or r['split']==split)
                          and (subset=='all_completed' or r['triggered'])]
                if not eligible:
                    continue
                ratios=[r['first_input_ratio'] for r in eligible if r['first_input_ratio'] is not None]
                groups.append(dict(split=split,method=method,subset=subset,n=len(eligible),
                                   passed=sum(r['passed'] for r in eligible),
                                   mean_first_input_ratio=mean(ratios) if ratios else None))
    return dict(selection=choice,coverage=coverage,groups=groups,rows=rows),requests


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,default=Path('experiments/bfcl_identity/work1000_research'))
    args=parser.parse_args()
    selection=read(args.root/'selection.json')['selected_explanations'] if (args.root/'selection.json').exists() else None
    summary,requests=summarize(args.root,selection)
    output=args.root/'reports';output.mkdir(exist_ok=True)
    (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    for name,data in [('task-results',summary['rows']),('per-request',requests)]:
        if data:
            keys=list(dict.fromkeys(k for row in data for k in row))
            with (output/(name+'.csv')).open('w') as f:
                writer=csv.DictWriter(f,fieldnames=keys);writer.writeheader();writer.writerows(data)
    print(json.dumps({'identity_attempts':len(summary['coverage']),'groups':summary['groups']},indent=2))


if __name__=='__main__':main()
