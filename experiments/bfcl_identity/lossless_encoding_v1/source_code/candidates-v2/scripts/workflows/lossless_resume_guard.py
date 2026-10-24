"""Strong read-only validation required before resuming a stopped controller."""
import argparse
import hashlib
import json
from pathlib import Path
from workflows.lossless_controller import read, verify, write
from workflows.work1000_task import SAMPLING


def check(root):
    plan = read(root/'task-split.json')
    active=read(root/'runtime/status.json')
    registry_name=active.get('registry','candidate-registry.json')
    registry = {r['label']:r for r in read(root/registry_name)}
    selection = read(root/'selection.json')['selected'] if (root/'selection.json').exists() else {}
    tasks = {t['id']:t for t in plan['tasks']}
    snapshots = set()
    checked = []
    for phase in ('development','evaluation'):
        for path in sorted((root/phase).glob('*/seed*/*')):
            if not path.is_dir():
                continue
            assert (path/'manifest.json').exists(), f'Unmanifested attempt requires review: {path}'
            m = read(path/'manifest.json')
            assert m['status'] in ('complete','not_triggered'), f'Incomplete attempt requires review: {path}'
            task_id, seed, label = path.parts[-3], int(path.parts[-2][4:]), path.name
            task = tasks[task_id]
            assert m['task']==task_id and m['category']==task['category'] and m['seed']==seed
            assert m['sampling']==SAMPLING and m['threshold']==1000
            assert m['context']==131072 and m['max_tokens']==4096
            if phase=='development':
                assert task['split']=='development' and seed in plan['development_seeds']
                variant=registry[label]
                identity=Path(plan['old_study'])/'tasks'/task_id/f'seed{seed}'/'identity'
            else:
                assert seed in plan['seeds']
                identity=path.parent/'identity'
                if label=='identity':
                    variant=dict(method='identity',variant='readable',explanation='none')
                    identity=None
                elif label.endswith('-baseline'):
                    method=label.removesuffix('-baseline')
                    variant=dict(method=method,variant='readable',explanation=plan['baseline_explanations'][method])
                else:
                    method=label.removesuffix('-optimized')
                    variant=selection[method]
            for key in ('method','variant','explanation'):
                assert m[key]==variant[key], f'Configuration mismatch {path}: {key}'
            assert m['identity']==(str(identity) if identity else None)
            launch=read(path/'launch.json')
            snapshot=Path(launch['source_snapshot'])
            snapshots.add(snapshot)
            assert launch['source_hashes']==read(snapshot/'hashes.json')
            command=launch['command']
            for key,value in (('--task',task_id),('--category',task['category']),
                              ('--seed',str(seed)),('--method',variant['method']),
                              ('--variant',variant['variant']),('--explanation',variant['explanation'])):
                assert command[command.index(key)+1]==value
            if variant.get('module'):
                assert command[command.index('--codec-module')+1]==variant['module']
                assert command[command.index('--codec-variant')+1]==variant['variant']
            else:
                assert '--codec-module' not in command
            checked.append(str(path))
    for snapshot in snapshots:
        verify(snapshot)
    for name,expected in read(root/'runtime/preregistered-input-hashes.json').items():
        assert hashlib.sha256((root/name).read_bytes()).hexdigest()==expected
    amendments=root/'runtime/amendment-input-hashes.json'
    if amendments.exists():
        for name,expected in read(amendments).items():
            assert hashlib.sha256((root/name).read_bytes()).hexdigest()==expected
    return dict(status='pass',checked=len(checked),paths=checked,
                note='Run only after confirming previous controller is stopped; this guard does not stop processes.')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,required=True)
    args=parser.parse_args()
    result=check(args.root.resolve())
    write(args.root/'runtime/resume-guard-latest.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='paths'},indent=2))


if __name__=='__main__':
    main()
