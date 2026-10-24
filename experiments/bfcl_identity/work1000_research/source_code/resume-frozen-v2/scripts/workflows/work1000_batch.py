"""Resumable sequential stages for the paired working-context experiment."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
DEFAULT = ROOT/'experiments/bfcl_identity/work1000_research'


def write(path, value):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, indent=2) + '\n')
    tmp.replace(path)


def snapshot(out, label):
    root = out/'source_code'/label
    root.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for path in sorted((ROOT/'scripts').rglob('*.py')):
        relative = path.relative_to(ROOT)
        target = root/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        data = path.read_bytes()
        if target.exists():
            assert target.read_bytes() == data, f'Frozen source changed: {relative}'
        else:
            target.write_bytes(data)
        hashes[str(relative)] = hashlib.sha256(data).hexdigest()
    write(root/'hashes.json', hashes)
    return hashes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=DEFAULT)
    parser.add_argument('--stage', choices=['identity-dev','identity-all','graph-dev','graph-final'], required=True)
    parser.add_argument('--explanation', choices=['none','minimal','full'], default='none')
    parser.add_argument('--seed-only', type=int)
    parser.add_argument('--task-only')
    parser.add_argument('--method-only', choices=['state','event','dedup'])
    parser.add_argument('--snapshot-label')
    parser.add_argument('--base-url', default='http://127.0.0.1:11436/v1')
    args = parser.parse_args()
    out = args.root.resolve()
    plan = json.loads((out/'task-split.json').read_text())
    label = args.stage + '-' + args.explanation + (f'-{args.seed_only}' if args.seed_only else '') + ('-'+args.task_only if args.task_only else '')
    snapshot_label = args.snapshot_label or label
    frozen = out/'source_code'/snapshot_label
    if args.snapshot_label and (frozen/'hashes.json').exists():
        sources = json.loads((frozen/'hashes.json').read_text())
        for relative, expected in sources.items():
            assert hashlib.sha256((frozen/relative).read_bytes()).hexdigest() == expected
    else:
        sources = snapshot(out, snapshot_label)
    # Only dependency data is linked; every Python module executes from snapshot.
    dependency = frozen/'vendor'
    if not dependency.exists():
        dependency.symlink_to(ROOT/'vendor', target_is_directory=True)
    tasks = plan['tasks']
    if args.task_only:
        tasks = [t for t in tasks if t['id'] == args.task_only]
        assert len(tasks) == 1
    if args.stage.endswith('-dev'):
        tasks = [t for t in tasks if t['split'] == 'development']
    jobs = []
    for task in tasks:
        for seed in plan['seeds']:
            if args.seed_only and seed != args.seed_only:
                continue
            for method in (['identity'] if args.stage.startswith('identity') else ([args.method_only] if args.method_only else ['state','event','dedup'])):
                jobs.append((task, seed, method))
    progress = dict(stage=label, total=len(jobs), completed=0, errors=[], started_at=time.time(), sources=sources)
    progress_path = out/(label+('-'+args.method_only if args.method_only else '')+'-progress.json')
    for task, seed, method in jobs:
        base = out/'tasks'/task['id']/f'seed{seed}'
        dest = base/('identity' if method == 'identity' else f'{method}-{args.explanation}')
        manifest = dest/'manifest.json'
        if manifest.exists():
            previous = json.loads(manifest.read_text())
            if previous['status'] in ('complete','not_triggered'):
                progress['completed'] += 1
                write(progress_path, progress)
                continue
            progress['errors'].append({'path':str(dest), 'reason':'existing incomplete attempt; never overwrite'})
            write(progress_path, progress)
            continue
        dest.mkdir(parents=True, exist_ok=True)
        cmd = [sys.executable, '-m', 'workflows.work1000_task', '--task', task['id'],
               '--category', task['category'], '--seed', str(seed), '--method', method,
               '--output', str(dest), '--explanation', args.explanation, '--base-url',args.base_url]
        if method != 'identity':
            cmd += ['--identity', str(base/'identity')]
        write(dest/'launch.json', {'command':cmd, 'source_snapshot':str(frozen),
                                   'source_hashes':sources, 'time':time.time()})
        progress['current'] = {'task':task['id'], 'seed':seed, 'method':method}
        write(progress_path, progress)
        env = dict(os.environ, PYTHONPATH=str(frozen/'scripts'), PYTHONDONTWRITEBYTECODE='1')
        with (dest/'runner.log').open('w') as log:
            result = subprocess.run(cmd, cwd=frozen, env=env, stdout=log, stderr=subprocess.STDOUT)
        for relative, expected in sources.items():
            assert hashlib.sha256((frozen/relative).read_bytes()).hexdigest() == expected
        if result.returncode:
            progress['errors'].append({'path':str(dest),'returncode':result.returncode})
        else:
            progress['completed'] += 1
        write(progress_path, progress)
    progress['finished_at'] = time.time()
    progress['status'] = 'complete' if not progress['errors'] else 'needs_review'
    progress.pop('current', None)
    write(progress_path, progress)
    print(json.dumps({k:v for k,v in progress.items() if k!='sources'}))
    if progress['errors']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
