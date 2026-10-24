"""Independent read-only audit of new working-history runs (no inference)."""
import argparse
import hashlib
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_text())


def paired(messages):
    seen, pending = set(), set()
    for message in messages:
        kind = message.get('type')
        if kind == 'function_call':
            identity = message['call_id']
            assert identity not in seen, 'Duplicate call ID'
            seen.add(identity)
            pending.add(identity)
        elif kind == 'function_call_output':
            identity = message['call_id']
            assert identity in pending, 'Duplicate, early, or unpaired output'
            pending.remove(identity)
    return not pending


def audit(path):
    manifest = read(path/'manifest.json')
    if manifest['status'] not in ('complete', 'not_triggered'):
        return {'path': str(path), 'status': manifest['status'], 'audit': 'pending'}
    if manifest['status'] == 'not_triggered':
        source = read(Path(manifest['identity'])/'manifest.json')
        assert not source['triggered']
        return {'path': str(path), 'status': 'not_triggered', 'audit': 'pass'}
    tape, accounting = read(path/'api.json'), read(path/'accounting.json')
    accounts = {row['index']: row for row in accounting}
    boundary = manifest.get('trigger_index')
    identity = manifest['method'] == 'identity'
    source = read(Path(manifest['identity'])/'api.json') if not identity else None
    if source is not None:
        source_manifest = read(Path(manifest['identity'])/'manifest.json')
        for key in ('task', 'category', 'seed', 'sampling'):
            assert source_manifest[key] == manifest[key], f'Mismatched {key}'
        assert boundary == source_manifest['trigger_index']
    first_eligible = None
    native = [json.loads(line) for line in (path/'native.jsonl').read_text().splitlines()]
    native_requests = {row['index']: row for row in native if row['event'] == 'request'}
    for index, record in enumerate(tape):
        if source is not None and index < boundary:
            assert record['source'] == 'replay'
            for key in ('request', 'response'):
                assert record[key] == source[index][key], f'Replay mismatch at {index}'
            continue
        row = accounts[index]
        assert row['working_tokens'] == row['input_tokens'] - row['fixed_tokens'] >= 0
        assert row['seed'] == manifest['seed'] + index * 1000003
        assert row['input_tokens'] == record['response']['usage']['input_tokens']
        body = native_requests[index]['request']
        assert body['seed'] == row['seed']
        for name, value in manifest['sampling'].items():
            assert body[name] == value, f'Sampler changed: {name}'
        history = record['request']['input']
        complete = paired(history)
        if identity and first_eligible is None and complete and row['working_tokens'] > 1000:
            first_eligible = index
    if identity:
        assert boundary == first_eligible, 'Not the first eligible threshold boundary'
    if boundary is not None:
        checkpoint = read(path/'checkpoint-history.json')
        assert paired(checkpoint)
        original = tape[boundary]['request']['input'] if identity else source[boundary]['request']['input']
        assert checkpoint == original
        if source is not None:
            initial = tape[boundary]['request']['input']
            memory = (path/'memory.txt').read_text()
            assert initial[-1] == {'role': 'assistant', 'content': memory}
            assert all(m.get('role') in ('system', 'developer') for m in initial[:-1])
            for record in tape[boundary:]:
                assert record['request']['input'][:len(initial)] == initial, 'Memory prefix changed'
    launch = read(path/'launch.json')
    snapshot = Path(launch['source_snapshot'])
    for relative, expected in launch['source_hashes'].items():
        assert hashlib.sha256((snapshot/relative).read_bytes()).hexdigest() == expected
    return {'path': str(path), 'status': manifest['status'], 'audit': 'pass',
            'trigger_index': boundary, 'passed': manifest['passed'], 'requests': len(tape)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    results = []
    for manifest in sorted((args.root/'tasks').glob('*/seed*/*/manifest.json')):
        try:
            results.append(audit(manifest.parent))
        except Exception as error:
            results.append({'path': str(manifest.parent), 'audit': 'fail', 'error': repr(error)})
    print(json.dumps({'runs': results, 'counts': {status: sum(r['audit'] == status for r in results)
                      for status in ('pass', 'fail', 'pending')}}, indent=2))
    raise SystemExit(1 if any(row['audit'] == 'fail' for row in results) else 0)


if __name__ == '__main__':
    main()
