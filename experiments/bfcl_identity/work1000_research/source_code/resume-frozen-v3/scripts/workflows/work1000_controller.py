"""Persistent frozen-code study controller; stop on errors, never overwrite runs."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from statistics import mean
from workflows.work1000_batch import write


def select(root):
    plan = json.loads((root/'task-split.json').read_text())
    selection, evidence = {}, {}
    for method in ('state', 'event', 'dedup'):
        candidates = []
        for explanation in ('none', 'minimal', 'full'):
            pairs = []
            for task in plan['tasks']:
                if task['split'] != 'development':
                    continue
                for seed in plan['seeds']:
                    base = root/'tasks'/task['id']/f'seed{seed}'
                    identity = json.loads((base/'identity/manifest.json').read_text())
                    if not identity['triggered']:
                        continue
                    graph = json.loads((base/f'{method}-{explanation}/manifest.json').read_text())
                    assert graph['status'] == 'complete'
                    pairs.append(dict(task=task['id'], seed=seed,
                                      identity_passed=identity['passed'], graph_passed=graph['passed'],
                                      ratio=graph['first_input']/identity['first_input']))
            assert pairs
            candidates.append(dict(explanation=explanation, n=len(pairs),
                                   passed=sum(p['graph_passed'] for p in pairs),
                                   mean_ratio=mean(p['ratio'] for p in pairs), pairs=pairs))
        candidates.sort(key=lambda c:(-c['passed'], c['mean_ratio'], ('none','minimal','full').index(c['explanation'])))
        selection[method] = candidates[0]['explanation']
        evidence[method] = candidates
    output = dict(selected_explanations=selection, candidates=evidence,
                  rule='Development triggered pass count descending; mean first-input ratio ascending; none/minimal/full tie order',
                  selected_at=time.time())
    path = root/'selection.json'
    if path.exists():
        previous=json.loads(path.read_text())
        assert previous['selected_explanations']==selection and previous['candidates']==evidence, 'Frozen selection evidence changed'
        return previous['selected_explanations']
    write(path, output)
    return selection


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--snapshot-label',required=True)
    parser.add_argument('--base-url',default='http://127.0.0.1:11436/v1')
    args=parser.parse_args()
    root=args.root.resolve()
    runtime=root/'runtime'
    state=dict(pid=os.getpid(), started_at=time.time(), status='running', completed_stages=[])
    path=runtime/'controller-status.json'
    write(path,state)
    def run(stage, explanation='none', method=None, task=None, seed=None):
        label=stage+'-'+explanation+('-'+method if method else '')+('-pilot' if task else '')
        state['current']=label;write(path,state)
        cmd=[sys.executable,'-m','workflows.work1000_batch','--root',str(root),
             '--stage',stage,'--explanation',explanation,'--snapshot-label',args.snapshot_label,
             '--base-url',args.base_url]
        if method:cmd+=['--method-only',method]
        if task:cmd+=['--task-only',task,'--seed-only',str(seed)]
        with (runtime/(label+'-controller.log')).open('a') as log:
            subprocess.run(cmd,check=True,stdout=log,stderr=subprocess.STDOUT)
        state['completed_stages'].append(label);write(path,state)
    try:
        # A real one-branch pilot precedes the full stage; its completed record is reused.
        plan=json.loads((root/'task-split.json').read_text())
        pilot=next((t['id'],seed) for t in plan['tasks'] if t['split']=='development'
                   for seed in plan['seeds'] if json.loads((root/'tasks'/t['id']/f'seed{seed}'/'identity/manifest.json').read_text())['triggered'])
        run('graph-dev','none','state',*pilot)
        for explanation in ('none','minimal','full'):
            run('graph-dev',explanation)
        selection=select(root)
        state['selection']=selection;write(path,state)
        run('identity-all')
        for method, explanation in selection.items():
            run('graph-final',explanation,method)
        subprocess.run([sys.executable,'-m','workflows.work1000_report','--root',str(root)],check=True)
        state.update(status='inference_complete_pending_independent_audit', finished_at=time.time())
    except BaseException as error:
        state.update(status='needs_review',error=repr(error),finished_at=time.time())
        raise
    finally:
        write(path,state)


if __name__=='__main__':main()
