"""Frozen five-arm readout validation; serial local GPU queue and audited reports.

No outcome-based selection/retry; old experiments stay read-only. Services started
here are stopped by this controller after each model or on error.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

from workflows import diagnostic_controller as checks
from workflows.diagnostic_task import prepare_replacement
from workflows.lossless_controller import freeze, verify

BRANCHES = [('identity', 'identity_reference'), ('state', 'readout_minimal'),
            ('event', 'readout_minimal'), ('dedup', 'readout_minimal'),
            ('event', 'readout_compact_index')]
STUDIES = {'qwen': 'mixed_history_diagnostics_v2', 'muse': 'muse_history_diagnostics_v2'}


def prepare(project, root):
    if root.exists():
        raise ValueError('Use a new online experiment directory')
    root.mkdir(parents=True)
    pins = {}
    for model, study in STUDIES.items():
        old = project / 'experiments/bfcl_identity' / study
        plan = checks.read(old / 'task-split.json')
        for name in ['task-split.json', 'source-inputs.json', 'vendor-pins.json', 'runtime/runtime-contract.json']:
            pins[str(old / name)] = checks.sha(old / name)
        checks.verify_hash_map(checks.read(old / 'source-inputs.json'))
        plan.pop('depends_on_root', None)
        plan.pop('depends_on_release_sha256', None)
        plan.update(schema='readout-online-v1', branches=BRANCHES,
                    expected_jobs=len(plan['samples']) * len(BRANCHES),
                    expected_graph_jobs=len(plan['samples']) * 4,
                    arms=['readout_minimal', 'readout_compact_index'],
                    scope='Previously exposed actual-mixed diagnostic prefixes; exploratory candidate validation, not held-out confirmation.',
                    resume_policy='No automatic retries or outcome-based selection', original_study=str(old))
        checks.write(root / model / 'task-split.json', plan)
        checks.write(root / model / 'source-inputs.json', checks.read(old / 'source-inputs.json'))
        checks.write(root / model / 'vendor-pins.json', checks.read(old / 'vendor-pins.json'))
        contract = checks.read(old / 'runtime/runtime-contract.json')
        contract['fixed_explanation'] = 'MINIMAL only; optional compact Event index, installed once, retained and charged on subsequent requests'
        checks.write(root / model / 'runtime/runtime-contract.json', contract)
        # Check all proposed graph inputs against the already audited offline transform.
        from core.readout_candidate import prepare as candidate_prepare
        for sample in plan['samples']:
            history = checks.read(Path(sample['source_paths']['identity']) / 'checkpoint-history.json')
            for method, arm in BRANCHES[1:]:
                source = checks.read(Path(sample['source_paths'][method + '-optimized']) / 'memory-metadata.json')
                messages, meta = prepare_replacement(history, source, method, arm, len)
                expected, _ = candidate_prepare(history, source, method, event_index=arm == 'readout_compact_index')
                checks.require(messages == expected and meta['payload_decode_exact'], 'Online/offline payload mismatch')
        for name in ['task-split.json', 'source-inputs.json', 'vendor-pins.json', 'runtime/runtime-contract.json']:
            path = root / model / name
            pins[str(path)] = checks.sha(path)
    # Reuse pinned binary launch recipe; no launch during preparation.
    muse_launch = project / 'experiments/bfcl_identity/muse_transfer_v1/runtime/server-launch.json'
    launch = checks.read(muse_launch)
    checks.write(root / 'muse-launch-recipe.json', {k: launch[k] for k in ['command', 'env_overrides']})
    pins[str(muse_launch)] = checks.sha(muse_launch)
    pins[str(root / 'muse-launch-recipe.json')] = checks.sha(root / 'muse-launch-recipe.json')
    freeze(project, root / 'source_code/online-v1')
    checks.write(root / 'release.json', dict(input_sha256=pins, snapshot='source_code/online-v1',
                                          prepared_inputs=704, expected_jobs=880,
                                          model_order=['qwen', 'muse'], gpu_free_required_mib={'qwen': 43000, 'muse': 36000}))
    checks.write(root / 'runtime/status.json', dict(status='prepared_not_started', expected_jobs=880))


def validate(path, sample, method, arm, plan, project, model):
    row = checks.validate_job(path, sample, method, arm, plan, project, transport=model)
    if method != 'identity':
        source = checks.read(Path(sample['source_paths'][method + '-optimized']) / 'memory-metadata.json')
        history = checks.read(Path(sample['source_paths']['identity']) / 'checkpoint-history.json')
        expected, meta = prepare_replacement(history, source, method, arm, len)
        saved = checks.read(path / 'memory-metadata.json')
        checks.require(saved['replacement_messages'] == expected, 'Actual candidate differs from offline design')
        checks.require(saved['view'] == meta['view'] and saved['body'] == meta['body'], 'Index/body mismatch')
    return row


def report(root, model, rows, plan, final=False):
    groups = {f'{m}/{a}': [r for r in rows if r['method'] == m and r['arm'] == a] for m, a in BRANCHES}
    result = dict(model=model, expected_jobs=plan['expected_jobs'], completed_jobs=len(rows),
                  status='complete' if final else 'partial',
                  scope=plan['scope'], rows=rows,
                  arms={key: checks.aggregate(items, len(plan['samples'])) for key, items in groups.items()},
                  missing_not_excluded=True, source_output_budget=4096, continuation_output_budget=16384)
    if final:
        from workflows.diagnostic_postrun_audit import comparison
        ordered = {key: sorted(items, key=lambda r: r['case_id']) for key, items in groups.items()}
        identity = ordered['identity/identity_reference']
        result['comparisons'] = {}
        for key, items in ordered.items():
            if key.startswith('identity/'):
                continue
            # Native context failures stay in success denominator. Missing input
            # measurements block cost acceptance instead of filtering failures.
            if all(r['mean_post_input'] is not None and r['first_input'] is not None for r in identity + items):
                result['comparisons'][key] = comparison(identity, items)
                c = result['comparisons'][key]
                c['exploratory_capability_flag'] = (not c['success']['degenerate'] and c['success']['interval95'][0] >= -0.03)
                c['engineering_mean_input_flag'] = c['mean_input_overhead']['estimate'] <= .35
            else:
                result['comparisons'][key] = {'cost_acceptance': 'not_evaluable_with_missing_input_measurements'}
        control, treatment = ordered['event/readout_minimal'], ordered['event/readout_compact_index']
        if all(r['mean_post_input'] is not None and r['first_input'] is not None for r in control + treatment):
            result['event_index_vs_same_codec_control'] = comparison(control, treatment)
        result['formal_acceptance'] = 'not_claimed: development-exposed families; precision/held-out confirmation pending'
    checks.write(root / model / 'reports/summary.json', result)
    lines = [f'# {model}: second-round readout validation', '', result['scope'], '',
             f"Completed {len(rows)} / {plan['expected_jobs']} continuations.", '',
             '| Arm | Successes / completed | First input | Mean per-request input | Calls |',
             '|---|---:|---:|---:|---:|']
    for key, values in result['arms'].items():
        def fmt(field):
            value = values[field]['mean']
            return '-' if value is None else f'{value:.2f}'
        lines.append(f"| {key} | {values['successes']} / {values['completed']} | {fmt('first_input')} | {fmt('mean_post_input')} | {fmt('emitted_calls')} |")
    lines += ['', 'All prespecified prefixes remain in the denominator; failures are retained. No held-out noninferiority claim. See summary.json for paired intervals, calls and success-at-call-threshold curves.']
    (root / model / 'reports/RESULTS.md').write_text('\n'.join(lines) + '\n')


def port_available(base):
    from urllib.parse import urlparse
    port = urlparse(base).port
    with socket.socket() as sock:
        return sock.connect_ex(('127.0.0.1', port)) != 0


def available_gpu(required):
    raw = subprocess.check_output(['nvidia-smi', '--query-gpu=index,memory.free', '--format=csv,noheader,nounits'], text=True)
    rows = [(int(i.strip()), int(free.strip())) for i, free in (line.split(',') for line in raw.splitlines())]
    eligible = [(i, free) for i, free in rows if free >= required]
    return (max(eligible, key=lambda x: x[1])[0] if eligible else None), rows


def run(project, root):
    snapshot = root / 'source_code/online-v1'
    checks.require(Path(__file__).resolve().is_relative_to(snapshot), 'Must run frozen snapshot')
    lock = (root / 'runtime/controller.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    release = checks.read(root / 'release.json')
    release_hash = checks.sha(root / 'release.json')
    remote = checks.read(root / 'remote.json') if (root / 'remote.json').exists() else None
    state = dict(pid=os.getpid(), started_at=time.time(), expected_jobs=880, completed_jobs=0)
    proc = None
    def update(**values):
        state.update(values, updated_at=time.time())
        checks.write(root / 'runtime/status.json', state)
    def integrity():
        checks.require(checks.sha(root / 'release.json') == release_hash, 'Release changed')
        verify(snapshot)
        checks.verify_hash_map(release['input_sha256'])
    try:
        for model in ['qwen', 'muse']:
            plan = checks.read(root / model / 'task-split.json')
            contract = checks.read(root / model / 'runtime/runtime-contract.json')
            integrity()
            checks.verify_hash_map(checks.read(root / model / 'source-inputs.json'))
            checks.verify_hash_map(checks.read(root / model / 'vendor-pins.json'), snapshot)
            recipe = checks.read(root / 'muse-launch-recipe.json')
            command = [s for s in contract['server_binary']['command'] if s] if model == 'qwen' else recipe['command']
            overrides = dict(recipe['env_overrides'], CUDA_VISIBLE_DEVICES='0')
            runtime = root / model / 'runtime'
            if remote:
                from workflows.readout_remote import RemoteService, verify_remote
                update(status='verifying_remote_runtime', model=model)
                verify_remote(remote, contract)
                checks.require(port_available(plan['base_url']), 'Local tunnel port is occupied')
                proc = RemoteService(remote, command, overrides, runtime, model, plan['base_url'])
                gpu = remote['gpu']
            else:
                weights = contract['weights'] if model == 'qwen' else contract['model']
                binary = contract['server_binary'] if model == 'qwen' else contract['binary']
                update(status='verifying_runtime_files', model=model)
                checks.require(checks.sha(weights['path']) == weights['sha256'], 'Weights changed')
                checks.require(checks.sha(binary['path']) == binary['sha256'], 'Server binary changed')
                while True:
                    gpu, memory = available_gpu(release['gpu_free_required_mib'][model])
                    if gpu is not None and port_available(plan['base_url']):
                        break
                    update(status='waiting_for_gpu', model=model, gpu_memory_free_mib=memory)
                    time.sleep(30)
                overrides['CUDA_VISIBLE_DEVICES'] = str(gpu)
                with (runtime / 'server.log').open('xb') as stream:
                    proc = subprocess.Popen(command, env=dict(os.environ, **overrides), cwd=project,
                                            stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT,
                                            start_new_session=True)
                checks.write(runtime / 'server-launch.json', dict(pid=proc.pid, command=command, env_overrides=overrides, time=time.time()))
            update(status='loading_model', model=model, server_pid=proc.pid, gpu=gpu)
            deadline = time.time() + 600
            while True:
                checks.require(proc.poll() is None, 'Owned model service exited during load; inspect server.log')
                try:
                    checks.check_live_runtime(plan['base_url'], contract)
                    break
                except (OSError, ValueError) as error:
                    if time.time() >= deadline:
                        raise TimeoutError('Model readiness timeout') from error
                    time.sleep(3)
            env = dict(os.environ, PYTHONPATH=str(snapshot / 'scripts'), PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1')
            rows = []
            samples = {s['case_id']: s for s in plan['samples']}
            pilots = plan['pilot_case_ids']
            order = pilots + sorted(set(samples) - set(pilots))
            for position, case_id in enumerate(order):
                sample = samples[case_id]
                relevant = {p: h for p, h in checks.read(root / model / 'source-inputs.json').items()
                            if any(Path(p).is_relative_to(Path(base)) for base in sample['source_paths'].values())}
                integrity()
                checks.verify_hash_map(relevant)
                for method, arm in BRANCHES:
                    dest = root / model / 'evaluation' / case_id / method / arm
                    checks.require(not dest.exists(), 'Existing attempt: do not overwrite or silently retry')
                    module = 'workflows.diagnostic_task' if model == 'qwen' else 'workflows.muse_diagnostic_task'
                    cmd = [sys.executable, '-m', module, '--task', sample['task'], '--category', sample['category'],
                           '--seed', str(sample['seed']), '--method', method, '--arm', arm,
                           '--identity', sample['source_paths']['identity'], '--output', str(dest),
                           '--base-url', plan['base_url'], '--max-output-tokens', '16384']
                    if method != 'identity':
                        cmd += ['--source-graph', sample['source_paths'][method + '-optimized']]
                    if model == 'muse':
                        cmd += ['--runtime-contract', str(runtime / 'runtime-contract.json')]
                    checks.check_live_runtime(plan['base_url'], contract)
                    boot = runtime / 'jobs' / case_id / method / arm
                    checks.write(boot / 'launch.json', dict(command=cmd, release_sha256=release_hash, time=time.time()))
                    update(status='running', model=model, stage='pilot' if case_id in pilots else 'all_prefixes',
                           current=dict(case_id=case_id, method=method, arm=arm))
                    with (boot / 'runner.log').open('x') as stream:
                        result = subprocess.run(cmd, cwd=snapshot, env=env, stdout=stream, stderr=subprocess.STDOUT)
                    checks.require(result.returncode == 0, f'Job needs review; no retry: {boot}')
                    rows.append(validate(dest, sample, method, arm, plan, project, model))
                    update(completed_jobs=state['completed_jobs'] + 1, model_completed=len(rows))
                    report(root, model, rows, plan)
                if position + 1 == len(pilots):
                    checks.write(runtime / 'pilot-gate.json', dict(status='pass', jobs=len(rows),
                        rule='Engineering integrity only; no outcome selection or prompt tuning', case_ids=pilots))
            # Re-audit every sent request after completion before publishing final results.
            final = [validate(Path(row['path']), samples[row['case_id']], row['method'], row['arm'], plan, project, model) for row in rows]
            integrity()
            checks.verify_hash_map(checks.read(root / model / 'source-inputs.json'))
            report(root, model, final, plan, final=True)
            proc.terminate()
            proc.wait(timeout=60)
            checks.write(runtime / 'server-stopped.json', dict(pid=proc.pid, returncode=proc.returncode, time=time.time()))
            proc = None
        update(status='complete', finished_at=time.time(), current=None)
    except BaseException as error:
        update(status='needs_review', error=repr(error), failed_at=time.time())
        raise
    finally:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=60)
        lock.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--prepare', action='store_true')
    args = parser.parse_args()
    (prepare if args.prepare else run)(args.project.resolve(), args.root.resolve())


if __name__ == '__main__':
    main()
