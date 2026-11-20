"""Persistent frozen cross-model transfer; no prompt selection or score retries."""
import argparse
import fcntl
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import time
import json
import urllib.request
from workflows.lossless_controller import read, write, verify
from core.muse_transport import MODEL_NAME, MODEL_KEY, REASONING_POLICY, SERVING_MODEL


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def gate_expected(root, snapshot):
    result = {name.replace('.', '_')+'_sha256':sha(path) for name,path in {
        'snapshot':snapshot/'hashes.json','plan':root/'task-split.json',
        'selection':root/'selection.json','protocol':root/'PROTOCOL.md',
        'vendor':root/'vendor-pins.json','runtime':root/'runtime/runtime-contract.json'}.items()}
    if (root/'prior-snapshots.json').exists():
        result['prior_snapshots_sha256']=sha(root/'prior-snapshots.json')
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--snapshot-label',required=True)
    parser.add_argument('--base-url',default='http://127.0.0.1:11437/v1')
    args=parser.parse_args()
    root=args.root.resolve();runtime=root/'runtime';snapshot=root/'source_code'/args.snapshot_label
    lock=(runtime/'controller.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    state=dict(pid=os.getpid(),started_at=time.time(),status='starting',completed_jobs=0,stages=[])
    def update(**values):
        state.update(values,updated_at=time.time());write(runtime/'status.json',state)
    try:
        verify(snapshot);expected=gate_expected(root,snapshot)
        review=read(root/'preflight-review.json')
        assert review['status']=='pass'
        assert all(review.get(k)==v for k,v in expected.items()),'Preflight gate mismatch'
        plan=read(root/'task-split.json');selection=read(root/'selection.json')['selected']
        env=dict(os.environ,PYTHONPATH=str(snapshot/'scripts'),PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1')
        def check():
            verify(snapshot)
            contract=read(root/'runtime/runtime-contract.json')
            with urllib.request.urlopen(args.base_url.removesuffix('/v1')+'/props',timeout=30) as response:
                live=json.load(response)
            assert all(live.get(k)==v for k,v in contract['props_projection'].items()),'Live server configuration changed'
            with urllib.request.urlopen(args.base_url.removesuffix('/v1')+'/slots',timeout=30) as response:
                slots=json.load(response)
            assert len(slots)==1 and slots[0]['n_ctx']==131072,'Live context/slot configuration changed'
            assert gate_expected(root,snapshot)==expected,'Frozen inputs changed'
            for relative,h in read(root/'vendor-pins.json').items():assert sha(snapshot/relative)==h,relative
        completed=set()
        def run(task,seed,method,optimized=False):
            selected=selection[method] if optimized else {}
            variant=selected['variant'] if optimized else ('mixed-domain-graph-1' if task['semantics']=='mixed' else 'readable')
            explanation=selected['explanation'] if optimized else ('none' if method=='identity' else plan['baseline_explanations'][method])
            label='identity' if method=='identity' else method+('-optimized' if optimized else '-baseline')
            base=root/'evaluation'/task['id']/f'seed{seed}';dest=base/label
            identity=None if method=='identity' else str(base/'identity')
            cmd=[sys.executable,'-m','workflows.muse_task','--task',task['id'],'--category',task['category'],
                 '--seed',str(seed),'--method',method,'--variant',variant,'--semantics',task['semantics'],
                 '--explanation',explanation,'--output',str(dest),'--base-url',args.base_url]
            if identity:cmd+=['--identity',identity]
            if optimized:cmd+=['--codec-module',selected['module'],'--codec-variant',variant]
            config=dict(model=MODEL_NAME,model_key=MODEL_KEY,reasoning_policy=REASONING_POLICY,
                        semantics=task['semantics'],task=task['id'],category=task['category'],seed=seed,
                        method=method,variant=variant,explanation=explanation,threshold=1000,
                        threshold_metric='native full minus fixed-only template tokens',context=131072,
                        max_tokens=4096,base_url=args.base_url,identity=identity,sampling=plan['sampling'])
            check()
            update(current=dict(task=task['id'],seed=seed,label=label,destination=str(dest)))
            if (dest/'manifest.json').exists():
                old=read(dest/'manifest.json');assert old['status'] in ('complete','not_triggered'),f'Incomplete attempt: {dest}'
                launch=read(dest/'launch.json')
                assert launch['command']==cmd
                launch_snapshot=Path(launch['source_snapshot'])
                verify(launch_snapshot)
                assert launch['source_hashes']==read(launch_snapshot/'hashes.json')
                if launch_snapshot!=snapshot:
                    prior=read(root/'prior-snapshots.json')[launch_snapshot.name]
                    assert launch_snapshot.parent==snapshot.parent
                    assert sha(launch_snapshot/'hashes.json')==prior['hashes_sha256']
                    current_hashes=read(snapshot/'hashes.json')
                    assert set(current_hashes)==set(launch['source_hashes'])
                    changed={key for key,value in launch['source_hashes'].items() if current_hashes[key]!=value}
                    assert changed==set(prior['allowed_noninference_changes'])
                    assert changed <= {'scripts/workflows/muse_controller.py','scripts/workflows/muse_report.py'}

                assert all(old.get(k)==v for k,v in config.items()),f'Existing configuration mismatch: {dest}'
            else:
                assert not dest.exists() or not any(dest.iterdir()),f'Unmanifested attempt: {dest}'
                dest.mkdir(parents=True,exist_ok=True)
                write(dest/'launch.json',dict(command=cmd,source_snapshot=str(snapshot),
                     source_hashes=read(snapshot/'hashes.json'),time=time.time(),configuration=config))
                with (dest/'runner.log').open('w') as log:
                    subprocess.run(cmd,cwd=snapshot,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
                result=read(dest/'manifest.json');assert result['status'] in ('complete','not_triggered')
                assert all(result.get(k)==v for k,v in config.items())
            check();completed.add(str(dest));state['completed_jobs']=len(completed);update(last_completed=str(dest))
            return read(dest/'manifest.json')
        update(status='running',stage='identity_and_graph_pilot',frozen_inputs=expected)
        # Predeclared pilot is retained as a formal run, regardless of score.
        pilot=next(t for t in plan['tasks'] if t['id']==plan['pilot_task'])
        seed=plan['seeds'][0];result=run(pilot,seed,'identity')
        if result['triggered']:
            for method in ('state','event','dedup'):
                for optimized in (False,True):run(pilot,seed,method,optimized)
            subprocess.run([sys.executable,'-m','workflows.muse_report','--root',str(root),'--audit-only'],cwd=snapshot,env=env,check=True)
        state['stages'].append('pilot_complete');update(stage='identity_all')
        for task in plan['tasks']:
            for seed in plan['seeds']:run(task,seed,'identity')
        state['stages'].append('identity_all_complete');update(stage='paired_graphs')
        for task in plan['tasks']:
            for seed in plan['seeds']:
                for method in ('state','event','dedup'):
                    for optimized in (False,True):run(task,seed,method,optimized)
        state['stages'].append('paired_graphs_complete');update(stage='automatic_audit_and_report')
        subprocess.run([sys.executable,'-m','workflows.muse_report','--root',str(root)],cwd=snapshot,env=env,check=True)
        update(status='inference_complete_pending_independent_audit',stage='independent_final_audit_pending',finished_at=time.time())
    except BaseException as error:
        update(status='needs_review',error=repr(error),failed_at=time.time());raise
    finally:
        lock.close()

if __name__=='__main__':main()
