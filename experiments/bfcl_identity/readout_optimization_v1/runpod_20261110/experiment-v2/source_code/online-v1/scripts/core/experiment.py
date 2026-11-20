"""Shared source snapshots, safe batch scheduling and process execution."""
import hashlib
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / 'scripts'

def read(path):
    return json.loads(path.read_text())

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temp.replace(path)

def source_hashes():
    return {str(p.relative_to(SCRIPTS)): sha(p) for p in sorted(SCRIPTS.rglob('*.py')) if '__pycache__' not in p.parts}

def verify_sources(directory, hashes):
    for name, expected in hashes.items():
        if sha(directory / name) != expected:
            raise ValueError(f'Frozen source changed: {name}')

def prepare_plan(output, plan, hashes):
    """Freeze the actual current implementation without borrowing baseline hashes."""
    if (output / 'plan.json').exists():
        if read(output / 'plan.json') != plan:
            raise ValueError('Existing plan differs; use a new output directory')
        verify_sources(output / 'source_code', hashes)
        return
    output.mkdir(parents=True, exist_ok=True)
    for name, expected in hashes.items():
        source = SCRIPTS / name
        if sha(source) != expected:
            raise ValueError(f'Source changed during preparation: {name}')
        target = output / 'source_code' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    write(output / 'plan.json', plan)

def completed(output):
    path = output / 'progress.json'
    if path.exists() and read(path).get('status') == 'complete':
        print(f'Completed batch preserved: {output}. Use a new directory for another run.')
        return True
    return False

def run_attempt(directory, command):
    """Reuse completed attempts; never silently retry or overwrite a partial attempt."""
    path = directory / 'manifest.json'
    if path.exists():
        manifest = read(path)
        if manifest.get('status') in ('complete', 'not_reached'):
            return manifest
    if directory.exists() and any(directory.iterdir()):
        raise RuntimeError(f'Incomplete attempt retained; refusing automatic retry: {directory}')
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / 'runner.log').open('w') as log:
        subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
    return read(path)

def run_batch(output, tasks, modes_for, run_one, expected, workers=2):
    """Keep all arms of one task on the same server and preserve task order."""
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    progress = read(output / 'progress.json') if (output / 'progress.json').exists() else {'runs': {}}
    progress.update(status='running', active={})
    progress.pop('error', None)
    lock = Lock()
    write(output / 'progress.json', progress)
    def worker(worker_id):
        endpoint = f'http://127.0.0.1:{11435 + worker_id}/v1'
        for index, task in enumerate(tasks):
            if index % workers != worker_id:
                continue
            for mode in modes_for(task):
                key = task['id'] + '/' + mode
                with lock:
                    progress['active'][str(worker_id)] = key
                    write(output / 'progress.json', progress)
                try:
                    result = run_one(task, mode, endpoint)
                    with lock:
                        progress['runs'][key] = result
                        write(output / 'progress.json', progress)
                        print(key, result, flush=True)
                except Exception as error:
                    with lock:
                        progress.update(status='infrastructure_error', error=f'{key}: {error}')
                        write(output / 'progress.json', progress)
                    raise
        with lock:
            progress['active'].pop(str(worker_id), None)
            write(output / 'progress.json', progress)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(worker, i) for i in range(workers)]
        for future in futures:
            future.result()
    assert len(progress['runs']) == expected
    progress['status'] = 'complete'
    write(output / 'progress.json', progress)
