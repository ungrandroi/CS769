"""Build a read-only-source index of the two audited fresh-evaluation cohorts."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
from statistics import mean

STUDIES = ('lossless_encoding_v1', 'mixed_tool_expansion')
ARMS = ('identity', 'state-baseline', 'state-optimized', 'event-baseline',
        'event-optimized', 'dedup-baseline', 'dedup-optimized')
LABELS = dict(zip(ARMS, ('Identity', 'State original', 'State optimized',
                       'Event original', 'Event optimized', 'Dedup original',
                       'Dedup optimized')))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    project, output = args.project.resolve(), args.output.resolve()
    # Avoid accidentally replacing an original study or its reports.
    if output.exists() and any(output.iterdir()):
        raise SystemExit('Output must be new or empty; existing reports are not overwritten.')
    if output == project or project in output.parents and 'source_code' in output.parts:
        raise SystemExit('Invalid output location')
    sources, results, pairs, coverage = {}, [], [], []

    def read(path):
        raw = path.read_bytes()
        sources[str(path.relative_to(project))] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw)

    for study in STUDIES:
        root = project / 'experiments/bfcl_identity' / study
        report = read(root / 'reports/summary.json')
        plan = read(root / 'task-split.json')
        tasks = {task['id']: task for task in plan['tasks']}
        lookup = {(r['task'], r['seed'], r['method']): r for r in report['rows']}
        assert len(lookup) == len(report['rows']), 'Duplicate report rows'
        files = sorted((root / 'evaluation').glob('*/*/identity/manifest.json'))
        assert len(files) == len(tasks) * len(plan['seeds'])
        seen = set()
        for path in files:
            identity = read(path)
            task, seed = identity['task'], identity['seed']
            assert task in tasks and seed in plan['seeds']
            assert (task, seed) not in seen
            seen.add((task, seed))
            assert identity['status'] == 'complete' and identity['method'] == 'identity'
            common = dict(sample_id=f'{study}/{task}/seed{seed}', source_study=study,
                          task=task, family=int(task.rsplit('_', 1)[1]),
                          category=identity['category'], seed=seed,
                          source_split=tasks[task]['split'])
            coverage.append(dict(common, triggered=identity['triggered'],
                                 identity_passed=identity['passed']))
            if not identity['triggered']:
                continue
            assert identity['threshold'] == 1000 and identity['source_work_tokens'] > 1000
            assert identity['threshold_metric'] == 'native full minus fixed-only template tokens'
            pair = dict(common, threshold=1000, comparison='strictly_greater_than',
                        source_work_tokens=identity['source_work_tokens'],
                        trigger_request_index=identity['trigger_index'],
                        trigger_user_turn_index=identity['trigger_turn'],
                        checkpoint_sha256=identity['checkpoint_sha256'])
            for arm in ARMS:
                run = path.parent.parent / arm
                manifest = read(run / 'manifest.json')
                assert manifest['status'] == 'complete' and manifest['triggered']
                for field in ('task', 'category', 'seed', 'threshold', 'threshold_metric',
                              'source_work_tokens', 'trigger_index', 'trigger_turn',
                              'checkpoint_sha256', 'sampling', 'context', 'max_tokens'):
                    assert manifest[field] == identity[field], (common['sample_id'], arm, field)
                row = lookup[(task, seed, arm)]
                assert row['passed'] == manifest['passed']
                assert row['first_input'] == manifest['first_input']
                assert row['live_requests'] > 0 and row['mean_post_input'] > 0
                relative = str(run.relative_to(project))
                pair[arm + '_passed'] = manifest['passed']
                pair[arm + '_path'] = relative
                results.append(dict(common, arm=arm, passed=manifest['passed'],
                                    first_input_tokens=row['first_input'],
                                    mean_post_input_tokens=row['mean_post_input'],
                                    peak_input_tokens=row['peak_input'],
                                    post_conversion_requests=row['live_requests'],
                                    variant=manifest['variant'],
                                    explanation=manifest['explanation'], run_path=relative))
            pairs.append(pair)
        assert len(seen) == len(tasks) * len(plan['seeds'])

    assert len(coverage) == 600 and len(pairs) == 417 and len(results) == 417 * 7
    assert len({p['sample_id'] for p in pairs}) == 417
    groups = []
    for cohort in ('all', *STUDIES):
        for arm in ARMS:
            rows = [r for r in results if r['arm'] == arm and
                    (cohort == 'all' or r['source_study'] == cohort)]
            successes = sum(r['passed'] for r in rows)
            group = dict(cohort=cohort, arm=arm, n=len(rows), passed=successes,
                         success_rate=successes / len(rows),
                         first_input_tokens=mean(r['first_input_tokens'] for r in rows),
                         mean_post_input_tokens=mean(r['mean_post_input_tokens'] for r in rows))
            cohort_pairs = [p for p in pairs if cohort == 'all' or p['source_study'] == cohort]
            group['gains_vs_identity'] = sum(p[arm + '_passed'] and not p['identity_passed'] for p in cohort_pairs)
            group['losses_vs_identity'] = sum(p['identity_passed'] and not p[arm + '_passed'] for p in cohort_pairs)
            groups.append(group)

    output.mkdir(parents=True, exist_ok=True)

    def csv_write(name, rows):
        with (output / name).open('w', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    csv_write('paired-samples.csv', pairs)
    csv_write('arm-results.csv', results)
    csv_write('coverage.csv', coverage)
    csv_write('summary.csv', groups)
    summary = dict(identity_runs=600, triggered_prefixes=417,
                   untriggered_prefixes=183, actual_graph_continuations=2502,
                   paired_arm_rows=len(results),
                   triggered_family_count=len({p['family'] for p in pairs}), groups=groups)
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    (output / 'source-hashes.json').write_text(json.dumps(sources, indent=2) + '\n')
    lines = ['# Combined 1,000-token conversion cohort', '',
             'This is an index and descriptive aggregation, not a new experiment.',
             'Original trajectories and frozen sources remain in their original studies.', '',
             '600 fresh Identity runs cover 50 base families and 200 task-condition instances.',
             '417 prefixes trigger conversion; each has Identity plus six graph results.',
             '183 untriggered prefixes stay in coverage.csv and are excluded from paired scores.', '',
             '| Arm | Successes | Rate | First input | Mean input per continuation request |',
             '|---|---:|---:|---:|---:|']
    for g in groups:
        if g['cohort'] == 'all':
            lines.append(f"| {LABELS[g['arm']]} | {g['passed']}/{g['n']} | {g['success_rate']:.1%} | {g['first_input_tokens']:,.0f} | {g['mean_post_input_tokens']:,.0f} |")
    lines += ['', '## Files', '',
              '- `paired-samples.csv`: 417 rows, one shared prefix with all seven outcomes and original run paths.',
              '- `arm-results.csv`: 2,919 rows, one method result per prefix, with input metrics and encoding/explanation.',
              '- `coverage.csv`: all 600 Identity runs, including 183 untriggered records.',
              '- `summary.csv` / `summary.json`: pooled and source-study results.',
              '- `source-hashes.json`: SHA-256 of the manifests, plans and summaries read by this export.', '',
              'All run paths are relative to the repository root. Source splits are preserved;',
              'an evaluation record labelled development refers to a development task condition',
              'repeated with fresh seeds, not a candidate-tuning run. No development-directory',
              'runs or earlier experiments enter this export.', '',
              '## Shared protocol and limits', '',
              'The threshold is native full input minus fixed system/tool template tokens,',
              '**strictly greater than 1,000**, at a complete call/return boundary. This is',
              'not a cut at exactly 1,000 tokens. Graph conversion happens once, followed by',
              'appending new interactions. Both studies use local Qwen3.8-27B-Q8_0;',
              'within-prefix sampling, boundary and checkpoint fields are checked across arms.', '',
              'Token metrics include fixed overhead. Mean input first averages post-conversion',
              'requests within each trajectory (including the first), then averages trajectories.',
              'They are not cumulative tokens. Only the first boundary request is action-aligned.', '',
              'The studies use different seed sets and graph-builder versions. Mixed-tool arms',
              'share adapted semantics within their study; this is not one identical graph builder',
              'tested 417 times. Keep source-study strata in analysis. Only 81 of the 297 mixed',
              'study prefixes contain non-filesystem calls; the mixed label alone does not prove',
              'mixed history. Repeated conditions and seeds are not independent task families.', '',
              'Event original/optimized also differ in outer explanation (full/minimal).',
              'Pooled counts do not establish equivalence or stable superiority.',
              'Independent audit details remain in the original studies:', '',
              '- [Filesystem audit](../lossless_encoding_v1/analysis/independent_audit/final.md)',
              '- [Mixed-tool audit](../mixed_tool_expansion/independent_audit/final.md)', '',
              'Rebuild into a new directory from the repository root:', '',
              '```bash', 'python scripts/workflows/combined_report.py --output /tmp/bfcl-combined-review', '```', '']
    (output / 'README.md').write_text('\n'.join(lines))
    print(json.dumps({k: v for k, v in summary.items() if k != 'groups'}))


if __name__ == '__main__':
    main()
