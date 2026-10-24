"""Detached, serial, fail-closed lossless-codec evaluation controller."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from statistics import mean


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, indent=2) + '\n')
    tmp.replace(path)


def freeze(project, target):
    hashes = {}
    for source in sorted((project/'scripts').rglob('*.py')):
        relative = source.relative_to(project)
        data = source.read_bytes()
        path = target/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            assert path.read_bytes() == data, f'Freeze mismatch: {relative}'
        else:
            path.write_bytes(data)
        hashes[str(relative)] = hashlib.sha256(data).hexdigest()
    write(target/'hashes.json', hashes)
    if not (target/'vendor').exists():
        (target/'vendor').symlink_to(project/'vendor', target_is_directory=True)
    return hashes


def verify(snapshot):
    for relative, expected in read(snapshot/'hashes.json').items():
        assert hashlib.sha256((snapshot/relative).read_bytes()).hexdigest() == expected


def post_mean(path):
    rows = read(path/'accounting.json')
    boundary = read(path/'manifest.json')['trigger_index']
    return mean(r['input_tokens'] for r in rows if r['index'] >= boundary)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--base-url', default='http://127.0.0.1:11436/v1')
    parser.add_argument('--snapshot-label', default='candidates-v1')
    parser.add_argument('--registry-name', default='candidate-registry.json')
    parser.add_argument('--explanation-controls', choices=['baseline','short-and-baseline'],
                        default='baseline')
    args = parser.parse_args()
    root, project = args.root.resolve(), args.project.resolve()
    runtime = root/'runtime'
    runtime.mkdir(parents=True, exist_ok=True)
    lock = (runtime/'controller.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    plan = read(root/'task-split.json')
    old = Path(plan['old_study'])
    status_path = runtime/'status.json'
    status = dict(pid=os.getpid(), started_at=time.time(), status='running',
                  completed_jobs=0, stages=[], source_snapshot=args.snapshot_label,
                  registry=args.registry_name, explanation_controls=args.explanation_controls)
    write(status_path, status)
    def update(**values):
        status.update(values, updated_at=time.time())
        write(status_path, status)
    snapshot = root/'source_code'/args.snapshot_label
    try:
        registry_paths = [root/'analysis'/m/'candidates.json' for m in ('state','event','dedup')]
        update(stage='waiting_for_validated_codecs')
        while not all(p.exists() and read(p).get('ready') for p in registry_paths):
            time.sleep(20)
            update(stage='waiting_for_validated_codecs')
        registries = [read(p) for p in registry_paths]
        registry = []
        for data in registries:
            module = project/'scripts'/Path(*data['module'].split('.')).with_suffix('.py')
            assert hashlib.sha256(module.read_bytes()).hexdigest() == data['source_sha256']
            for variant in data['variants']:
                controls=['none']
                if args.explanation_controls=='short-and-baseline':
                    controls.append('minimal')
                controls.append(plan['baseline_explanations'][data['method']])
                for explanation in dict.fromkeys(controls):
                    registry.append(dict(method=data['method'], module=data['module'],
                                         variant=variant, explanation=explanation,
                                         label=data['method']+'-'+variant+'-'+explanation))
        registered = root/args.registry_name
        if registered.exists():
            assert read(registered) == registry
        else:
            write(registered, registry)
        if (snapshot/'hashes.json').exists():
            verify(snapshot)
        else:
            freeze(project, snapshot)
        env = dict(os.environ, PYTHONPATH=str(snapshot/'scripts'),
                   PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1')
        def execute(task, seed, variant, destination, identity=None):
            path = destination/'manifest.json'
            if path.exists():
                manifest = read(path)
                assert manifest['status'] in ('complete','not_triggered'), f'Incomplete attempt: {destination}'
                assert manifest['task'] == task['id'] and manifest['seed'] == seed
                status['completed_jobs'] += 1
                return
            assert not destination.exists() or not any(destination.iterdir()), f'Unmanifested attempt: {destination}'
            destination.mkdir(parents=True, exist_ok=True)
            method = variant['method']
            cmd = [sys.executable, '-m', 'workflows.lossless_task',
                   '--task', task['id'], '--category', task['category'],
                   '--seed', str(seed), '--method', method,
                   '--variant', variant.get('variant','readable'),
                   '--explanation', variant.get('explanation','none'),
                   '--output', str(destination), '--base-url', args.base_url]
            if identity:
                cmd += ['--identity',str(identity)]
            if variant.get('module'):
                cmd += ['--codec-module', variant['module'], '--codec-variant',variant['variant']]
            verify(snapshot)
            write(destination/'launch.json', dict(command=cmd, source_snapshot=str(snapshot),
                  source_hashes=read(snapshot/'hashes.json'), time=time.time()))
            update(current=dict(task=task['id'],seed=seed,label=variant.get('label',method),
                                destination=str(destination)))
            with (destination/'runner.log').open('w') as log:
                subprocess.run(cmd, cwd=snapshot, env=env, stdout=log,
                               stderr=subprocess.STDOUT, check=True)
            verify(snapshot)
            assert read(path)['status'] in ('complete','not_triggered')
            status['completed_jobs'] += 1
            update(last_completed=str(destination))
        development = [t for t in plan['tasks'] if t['split']=='development']
        update(stage='development_candidates')
        for variant in registry:
            for task in development:
                for seed in plan['development_seeds']:
                    execute(task, seed, variant,
                            root/'development'/task['id']/f'seed{seed}'/variant['label'],
                            old/'tasks'/task['id']/f'seed{seed}'/'identity')
            status['stages'].append('development:'+variant['label'])
            update()
        evidence, selected = {}, {}
        for method in ('state','event','dedup'):
            choices=[]
            for variant in [r for r in registry if r['method']==method]:
                pairs=[]
                for task in development:
                    for seed in plan['development_seeds']:
                        original = old/'tasks'/task['id']/f'seed{seed}'
                        identity = read(original/'identity/manifest.json')
                        if not identity['triggered']:
                            continue
                        baseline = original/(method+'-'+plan['baseline_explanations'][method])
                        candidate = root/'development'/task['id']/f'seed{seed}'/variant['label']
                        pairs.append(dict(task=task['id'], seed=seed,
                                          identity_passed=identity['passed'],
                                          baseline_passed=read(baseline/'manifest.json')['passed'],
                                          candidate_passed=read(candidate/'manifest.json')['passed'],
                                          baseline_input=post_mean(baseline),
                                          candidate_input=post_mean(candidate)))
                choices.append(dict(**variant, pairs=pairs,
                                    passed=sum(p['candidate_passed'] for p in pairs),
                                    baseline_passed=sum(p['baseline_passed'] for p in pairs),
                                    mean_input=mean(p['candidate_input'] for p in pairs),
                                    baseline_mean_input=mean(p['baseline_input'] for p in pairs)))
            choices.sort(key=lambda c:(-c['passed'], c['mean_input'],c['label']))
            best=choices[0]
            selected[method]={k:best[k] for k in ('method','module','variant','explanation','label')}
            selected[method]['development_adoption_criterion_met'] = (
                best['passed']>=best['baseline_passed'] and best['mean_input']<best['baseline_mean_input'])
            evidence[method]=choices
        selection=dict(selected=selected, evidence=evidence)
        if (root/'selection.json').exists():
            assert read(root/'selection.json')==selection, 'Frozen development selection changed'
        else:
            write(root/'selection.json', selection)
        status['stages'].append('selection_frozen')
        update(stage='fresh_identity',selection=selected)
        for task in plan['tasks']:
            for seed in plan['seeds']:
                base=root/'evaluation'/task['id']/f'seed{seed}'
                execute(task,seed,dict(method='identity'),base/'identity')
        status['stages'].append('fresh_identity')
        update(stage='paired_baselines_and_candidates')
        for task in plan['tasks']:
            for seed in plan['seeds']:
                base=root/'evaluation'/task['id']/f'seed{seed}'
                for method in ('state','event','dedup'):
                    baseline=dict(method=method,explanation=plan['baseline_explanations'][method],
                                  label=method+'-baseline')
                    execute(task,seed,baseline,base/baseline['label'],base/'identity')
                    candidate=selected[method]
                    execute(task,seed,candidate,base/(method+'-optimized'),base/'identity')
        status['stages'].append('paired_baselines_and_candidates')
        update(stage='report')
        subprocess.run([sys.executable,'-m','workflows.lossless_report','--root',str(root)],
                       cwd=snapshot,env=env,check=True)
        update(status='inference_complete_pending_independent_audit',
               stage='independent_audit_then_cleanup',finished_at=time.time())
        write(runtime/'pending-followup.json',dict(
            independent_audit_required=True,code_cleanup_after_audit=True,
            preserve=['visualization/','frozen trajectories','source_code/']))
    except BaseException as error:
        update(status='needs_review',error=repr(error),finished_at=time.time())
        raise


if __name__ == '__main__':
    main()
