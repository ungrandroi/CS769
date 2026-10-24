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
    parser.add_argument('--base-url', default='http://127.0.0.1:11436/v1')
    args = parser.parse_args()
    out = args.root.resolve()
    plan = json.loads((out/'task-split.json').read_text())
    label = args.stage + '-' + args.explanation + (f'-{args.seed_only}' if args.seed_only else '')
    sources = snapshot(out, label)
    tasks = plan['tasks']
    if args.stage.endswith('-dev'):
        tasks = [t for t in tasks if t['split'] == 'development']
    jobs = []
    for task in tasks:
        for seed in plan['seeds']:
            if args.seed_only and seed != args.seed_only:
                continue
            for method in (['identity'] if args.stage.startswith('identity') else ['state','event','dedup']):
                jobs.append((task, seed, method))
    progress = dict(stage=label, total=len(jobs), completed=0, errors=[], started_at=time.time(), sources=sources)
    progress_path = out/(label+'-progress.json')
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
        write(dest/'launch.json', {'command':cmd, 'source_snapshot':str(out/'source_code'/label),
                                   'source_hashes':sources, 'time':time.time()})
        progress['current'] = {'task':task['id'], 'seed':seed, 'method':method}
        write(progress_path, progress)
        env = dict(os.environ, PYTHONPATH=str(ROOT/'scripts'), PYTHONDONTWRITEBYTECODE='1')
        with (dest/'runner.log').open('w') as log:
            result = subprocess.run(cmd, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
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


if __name__ == '__main__':
    main()
