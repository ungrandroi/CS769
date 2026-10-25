"""Read-only aggregation of completed coverage artifacts; never runs eval or models."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import random

HERE = Path(__file__).absolute().parent
BASE = HERE.parent
ARM = 'graph-record-view-full'
PREFIX = ['cov01-prefix-k1', 'cov02-prefix-k2', 'cov03-prefix-k3']
CONT = ['cov04-continuation-k1', 'cov05-continuation-k2', 'cov06-continuation-k3']
DOMAINS = ['filesystem', 'vehicle', 'trading', 'travel']
CI_SEED = 'g9-coverage120-descriptive-family-bootstrap-v1'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def localize(path, snapshot, server_base):
    return snapshot / Path(path).relative_to(server_base)


def aggregate(rows):
    n = len(rows)
    a = sum(r['identity_passed'] for r in rows)
    b = sum(r['g9_passed'] for r in rows)
    loss = sum(r['identity_passed'] and not r['g9_passed'] for r in rows)
    gain = sum(not r['identity_passed'] and r['g9_passed'] for r in rows)
    return {'conditions': n, 'families': len({r['family'] for r in rows}),
            'identity_passed': a, 'g9_passed': b,
            'identity_rate': a / n if n else None, 'g9_rate': b / n if n else None,
            'delta_percentage_points': 100 * (b-a) / n if n else None,
            'both_pass': sum(r['identity_passed'] and r['g9_passed'] for r in rows),
            'both_fail': sum(not r['identity_passed'] and not r['g9_passed'] for r in rows),
            'new_failures': loss, 'recoveries': gain}


def quantile(ordered, q):
    x = (len(ordered)-1) * q
    lo = int(x)
    hi = min(lo+1, len(ordered)-1)
    return ordered[lo] + (ordered[hi]-ordered[lo]) * (x-lo)


def ci(rows, label, replicates):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row['family']].append(row)
    units = [(sum(int(r['g9_passed'])-int(r['identity_passed']) for r in grouped[f]), len(grouped[f]))
             for f in sorted(grouped)]
    if len(units) < 2:
        return {'available': False, 'reason': 'fewer_than_two_observed_eligible_families'}
    rng = random.Random(CI_SEED + '|' + label)
    samples = []
    for _ in range(replicates):
        delta = n = 0
        for _ in units:
            d, count = units[rng.randrange(len(units))]
            delta += d
            n += count
        samples.append(100 * delta / n)
    samples.sort()
    return {'available': True, 'level': 0.95,
            'lower_percentage_points': quantile(samples, .025),
            'upper_percentage_points': quantile(samples, .975),
            'replicates': replicates, 'cluster': 'BFCL family ID',
            'estimand': 'condition-weighted G9 minus identity pass-rate difference',
            'method': 'paired family-cluster percentile bootstrap; sample eligible families with replacement and retain all their eligible Base/Long conditions',
            'post_hoc_descriptive_not_preregistered_test': True,
            'degenerate_all_observed_pair_differences_zero': all(r['identity_passed'] == r['g9_passed'] for r in rows),
            'degenerate_interval_warning': 'If all observed paired differences are zero, empirical bootstrap yields [0,0]; this is not evidence of zero population uncertainty or guaranteed future equivalence.',
            'seed': CI_SEED+'|'+label}


def grouped(rows, field):
    return {str(value): aggregate([r for r in rows if r[field] == value])
            for value in sorted({r[field] for r in rows}, key=str)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, default=BASE/'snapshots/completed')
    parser.add_argument('--bootstrap-replicates', type=int, default=50000)
    args = parser.parse_args()
    snapshot = args.snapshot.absolute()
    selection_path = BASE/'design/coverage120-selection-v1.json'
    selection = read(selection_path)
    assert sha(selection_path) == 'cd7bd77f3ad5e0699c5e12215c3d116c9eb1c0cf8ce58ba8d16475afe801adda'
    server_base = Path(read(BASE/'authorization.json')['server_base'])
    state = read(snapshot/'execution-state.json')
    assert state['status'] == 'complete_pending_result_review'
    stage_state = {r['stage']: r for r in state['completed_stages']}
    assert set(stage_state) == set(PREFIX+CONT)
    selected = {r['id']: r for r in selection['conditions']}
    assert len(selected) == 120
    sources = [{'path': str(selection_path), 'sha256': sha(selection_path)},
               {'path': str(snapshot/'execution-state.json'), 'sha256': sha(snapshot/'execution-state.json')}]
    eligibility = {}
    certificates = []
    for stage in PREFIX+CONT:
        audit_path = snapshot/'analysis'/(stage+'-actual-audit-v2.json')
        audit = read(audit_path)
        assert audit['stage'] == stage and audit['all_checks_passed'] is True
        assert audit['failed_checks'] == []
        assert audit['planned_trajectories'] == audit['completed_trajectories'] == audit['request_audited_trajectories']
        assert stage_state[stage]['audit_passed'] is True
        assert stage_state[stage]['audit_sha256'] == sha(audit_path)
        assert localize(stage_state[stage]['audit'], snapshot, server_base) == audit_path
        certificates.append({'stage': stage, 'path': str(audit_path), 'sha256': sha(audit_path),
                             'completed_trajectories': audit['completed_trajectories']})
    for k, stage in enumerate(PREFIX, 1):
        path = snapshot/stage/'eligibility.json'
        obj = read(path)
        assert obj['status'] == 'complete'
        sources.append({'path': str(path), 'sha256': sha(path)})
        assert len(obj['conditions']) == [26,28,66][k-1]
        for r in obj['conditions']:
            assert r['id'] not in eligibility
            assert r['model'] == 'gpt-4.1' and r['mode'] == 'identity' and r['repeat'] == 1
            assert r['boundary_turns'] == selected[r['id']]['boundary_turns'] == k
            directory = localize(r['directory'], snapshot, server_base)
            assert sha(directory/'manifest.json') == r['manifest_sha256']
            eligibility[r['id']] = r
    assert set(eligibility) == set(selected)
    runs = {}
    for k, stage in enumerate(CONT, 1):
        path = snapshot/stage/'summary.json'
        obj = read(path)
        assert obj['status'] == 'complete'
        sources.append({'path': str(path), 'sha256': sha(path)})
        for row in obj['runs']:
            assert row['model'] == 'gpt-4.1' and row['repeat'] == 1
            assert row['mode'] in ['identity', ARM]
            assert row['boundary_turns'] == selected[row['id']]['boundary_turns'] == k
            assert eligibility[row['id']]['eligible'] is True
            key = (row['id'], row['mode'])
            assert key not in runs
            directory = localize(row['directory'], snapshot, server_base)
            assert sha(directory/'manifest.json') == row['manifest_sha256']
            assert sha(directory/'official-score.json') == row['score_sha256']
            score = read(directory/'official-score.json')
            assert type(score['passed']) is bool and score['passed'] == row['passed']
            runs[key] = (row, directory)
    eligible = {task_id for task_id, row in eligibility.items() if row['eligible']}
    assert set(runs) == {(task_id, arm) for task_id in eligible for arm in ['identity', ARM]}
    pairs, excluded = [], []
    for task_id, meta in selected.items():
        keep = ['id','family','domain','category','boundary_turns','user_turns','exposure_status']
        row = {key: meta[key] for key in keep}
        if task_id not in eligible:
            excluded.append({**row, 'reasons': eligibility[task_id]['reasons'],
                             'prefix_passed': eligibility[task_id]['prefix_passed'],
                             'first_turn_passed': eligibility[task_id]['first_turn_passed']})
            continue
        identity, identity_dir = runs[(task_id, 'identity')]
        graph, graph_dir = runs[(task_id, ARM)]
        g = read(graph_dir/(task_id+'.graph.json'))
        audit = g['record_audit']
        assert audit['ok'] is True and g['record_render_audit']['ok'] is True
        assert type(audit['active']) is bool
        assert audit['active'] == (audit['join_count'] > 0)
        row.update(identity_passed=identity['passed'], g9_passed=graph['passed'],
                   active_relations=audit['active'], join_count=audit['join_count'],
                   record_count=audit['record_count'], edge_count=audit['edge_count'],
                   identity_score=str((identity_dir/'official-score.json').relative_to(snapshot)),
                   g9_score=str((graph_dir/'official-score.json').relative_to(snapshot)),
                   graph_evidence=str((graph_dir/(task_id+'.graph.json')).relative_to(snapshot)))
        row['outcome'] = ('both_pass' if row['identity_passed'] and row['g9_passed'] else
                          'new_failure' if row['identity_passed'] else
                          'recovery' if row['g9_passed'] else 'both_fail')
        pairs.append(row)
    raw_reasons = Counter(reason for row in excluded for reason in row['reasons'])
    reason_sets = Counter('|'.join(sorted(row['reasons'])) for row in excluded)
    result = {'version': 'coverage120-read-only-descriptive-summary-v1', 'snapshot': str(snapshot),
        'source_pins': sources, 'stage_audit_certificates': certificates,
        'counts': {'registered_candidates': len(selected), 'registered_families': len({r['family'] for r in selected.values()}),
                   'prefix_attempts': len(eligibility), 'eligible_pairs': len(pairs), 'excluded_candidates': len(excluded),
                   'eligible_families': len({r['family'] for r in pairs}), 'continuation_trajectories': len(runs)},
        'overall': aggregate(pairs),
        'descriptive_family_cluster_ci': ci(pairs, 'overall', args.bootstrap_replicates),
        'by_domain': {d: {**aggregate([r for r in pairs if r['domain']==d]),
                             'registered_candidates': sum(r['domain']==d for r in selected.values()),
                             'excluded_candidates': sum(r['domain']==d for r in excluded),
                             'descriptive_ci': ci([r for r in pairs if r['domain']==d], d, args.bootstrap_replicates)} for d in DOMAINS},
        'by_boundary': grouped(pairs, 'boundary_turns'), 'by_exposure': grouped(pairs,'exposure_status'),
        'by_active_relations': grouped(pairs,'active_relations'), 'by_category': grouped(pairs,'category'),
        'screening_by_boundary': {str(k): {'candidates': sum(r['boundary_turns']==k for r in selected.values()),
             'eligible': sum(r['boundary_turns']==k for r in pairs), 'excluded': sum(r['boundary_turns']==k for r in excluded)} for k in [1,2,3]},
        'exclusion_reason_counts_overlap_possible': dict(raw_reasons), 'exclusion_reason_sets': dict(reason_sets),
        'all_pairs': pairs, 'excluded_conditions': excluded,
        'limitations': ['This is an exposed random coverage sample, not a wholly unseen holdout.',
            '120 candidates are 30% of Base+Long 400 conditions, not 30% of all BFCL.',
            'Success rates condition on the model-generated historical prefix passing official screening.',
            'A newly failing pair is an observed outcome mismatch in one run per arm, not yet a demonstrated reproducible regression.',
            'Family-cluster bootstrap intervals are post-hoc descriptive and are not a preregistered non-inferiority test.',
            'One sample per arm does not identify sampling variance separately from the intervention.',
            'Active relation subgroups are observational; this design does not isolate causal benefits of relations.']}
    output = HERE/'coverage-selection-summary.json'
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    with (HERE/'coverage-selection-summary.csv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(pairs[0]))
        writer.writeheader(); writer.writerows(pairs)
    print(json.dumps({key:result[key] for key in ['counts','overall','descriptive_family_cluster_ci','by_domain','by_boundary','by_exposure','by_active_relations','exclusion_reason_counts_overlap_possible']},ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
