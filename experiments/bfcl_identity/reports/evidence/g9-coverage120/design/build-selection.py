"""Offline metadata-only registration for the new GPT-4.1 coverage trial.

Only id, len(question), and involved_classes are projected from BFCL rows.
No question text, tool state, answer, future call, or model outcome is used.
"""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = HERE.parents[1]
SEED = 'g9-gpt41-coverage120-20261024-v1'
DOMAINS = ('filesystem', 'vehicle', 'trading', 'travel')
DOMAIN_CLASS = dict(zip(DOMAINS, ('GorillaFileSystem', 'VehicleControlAPI', 'TradingBot', 'TravelAPI')))
DATA = WORK / 'g5-domain-expansion-20261024/runner/vendor/gorilla/berkeley-function-call-leaderboard/bfcl_eval/data'


def read(path):
    return json.loads(path.read_text())


def pin(path):
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def write_new(path, data):
    with path.open('x') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def main():
    by_category = {}
    sources = []
    for category in ('base', 'long_context'):
        path = DATA / ('BFCL_v4_multi_turn_' + category + '.json')
        sources.append(pin(path))
        # Deserialize only to project the three allowed metadata fields.
        projection = []
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            projection.append({'id': row['id'], 'user_turns': len(row['question']),
                               'involved_classes': row['involved_classes']})
        assert len(projection) == 200
        by_category[category] = {int(row['id'].rsplit('_', 1)[1]): row for row in projection}
        assert set(by_category[category]) == set(range(200))
    for family in range(200):
        a, b = (by_category[c][family] for c in ('base', 'long_context'))
        assert a['user_turns'] == b['user_turns']
        assert a['involved_classes'] == b['involved_classes']
        domain = DOMAINS[family // 50]
        assert DOMAIN_CLASS[domain] in a['involved_classes']
        assert not any(DOMAIN_CLASS[d] in a['involved_classes'] for d in DOMAINS if d != domain)
    single = [f for f in range(200) if by_category['base'][f]['user_turns'] < 2]
    assert single == [46, 50, 198]

    old_exposure_path = WORK / 'g9-report-publication/package/experiments/bfcl_identity/reports/evidence/g9/g9-expansion-feasibility-projection.json'
    old_exposure = read(old_exposure_path)['data']['pools']
    recorded_exposure = set(f for d in DOMAINS for f in old_exposure[d]['recorded_exposed_families'])
    mini_path = WORK / 'g9-mini-validation-20261024/design/g9-mini-fixed24-selection-v1.json'
    mini = read(mini_path)
    # Registration overlap is disclosed separately, never equated with execution.
    prior_registration = {row['family'] for row in mini['conditions']}
    families, ranking, conditions = [], [], []
    for domain_index, domain in enumerate(DOMAINS):
        eligible = [f for f in range(domain_index * 50, (domain_index + 1) * 50) if f not in single]
        ordered = sorted(eligible, key=lambda f: (hashlib.sha256(f'{SEED}|{domain}|{f}'.encode('utf-8')).hexdigest(), f))
        chosen = ordered[:15]
        families += chosen
        ranking.append({'domain': domain, 'eligible_families': len(eligible),
                        'ranked_families': ordered, 'selected_families': chosen})
        for rank, family in enumerate(chosen, 1):
            for category in ('base', 'long_context'):
                row = by_category[category][family]
                boundary = min(3, row['user_turns'] - 1)
                assert 1 <= boundary < row['user_turns']
                conditions.append({**row, 'family': family, 'domain': domain,
                    'category': 'multi_turn_' + category, 'boundary_turns': boundary,
                    'source_batch': 'coverage120', 'rank_within_domain': rank,
                    'family_rank_sha256': hashlib.sha256(f'{SEED}|{domain}|{family}'.encode('utf-8')).hexdigest(),
                    'recorded_exposed_family': True if family in recorded_exposure else None,
                    'prior_g9_or_mini_registered_family': family in prior_registration,
                    'exposure_status': 'recorded_prior_content_exposure' if family in recorded_exposure else
                        ('previously_registered_exposure_not_reaudited' if family in prior_registration else 'unknown')})
    assert len(families) == len(set(families)) == 60
    assert len(conditions) == len({r['id'] for r in conditions}) == 120
    assert Counter(r['domain'] for r in conditions) == Counter(dict.fromkeys(DOMAINS, 30))
    by_boundary = Counter(str(r['boundary_turns']) for r in conditions)
    selection = {
        'version': 'g9-gpt41-coverage120-selection-v1',
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'models': ['gpt-4.1'], 'arms': ['identity', 'graph-record-view-full'], 'repeat_labels': [1],
        'candidate_version': 'G9-active-record-views-v1',
        'selected_before_candidate_results': True, 'selection_freeze_scope': 'Before any new coverage120 prefix or continuation request.',
        'metadata_only': True, 'selection_seed': SEED,
        'selection_rule': 'Within each of four primary domains, exclude single-turn families 46/50/198, sort remaining family IDs by SHA256(UTF8(seed + "|" + domain + "|" + decimal_family_id)) ascending (family ID tie-break), select first 15, retain both Base and Long-Context. No historical or candidate outcomes, graph activation, or prior exposure affect selection.',
        'boundary_rule': 'For each condition k=min(3,user_turns-1); share its first native prefix across arms, retain at least one future user turn. No length-triggered extra checkpoint.',
        'source_datasets': sources, 'family_ranking': ranking, 'conditions': conditions,
        'short_conditions': [r['id'] for r in conditions if r['boundary_turns'] == 1], 'short_boundary_turns': 1,
        'early_conditions': [r['id'] for r in conditions if r['boundary_turns'] == 2], 'early_boundary_turns': 2,
        'longer_conditions': [r['id'] for r in conditions if r['boundary_turns'] == 3], 'longer_boundary_turns': 3,
        'counts': {'candidate_conditions': 120, 'distinct_families': 60, 'by_domain': dict(Counter(r['domain'] for r in conditions)),
                   'by_boundary': dict(sorted(by_boundary.items())), 'max_prefixes': 120, 'max_continuations': 240,
                   'families_per_domain': 15, 'base_conditions': 60, 'long_context_conditions': 60},
        'coverage': {'universe_conditions': 400, 'universe_families': 200,
                     'registered_condition_fraction': 0.30, 'registered_family_fraction': 0.30,
                     'multiturn_eligible_universe_conditions': 394, 'not_entire_BFCL': True,
                     'target_is_registered_candidates_not_qualified_pairs': True},
        'exclusions_before_sampling': {'single_turn_families': single, 'reason': 'No completed historical prefix can retain a subsequent user turn.'},
        'eligibility': {**mini['eligibility'], 'reuse_other_model_prefix': False},
        'scope': mini['scope'], 'no_replacement': True, 'no_zero_index_exclusion': True,
        'frozen_graph_source_sha256': mini['frozen_graph_source_sha256'],
        'exposure_sources': {'recorded_content_exposure_inventory': pin(old_exposure_path), 'prior_G9_mini_registration': pin(mini_path)},
        'exposure_disclosure': 'This random coverage sample contains previously exposed or registered families; it is not an unseen holdout. The older exposure inventory is incomplete for later work, so absence is unknown, never proof of no exposure. Both variants inherit the family exposure label. Exposure and prior success do not affect inclusion.',
        'budget': {'model': 'gpt-4.1', 'cap_usd': 35, 'fresh_ledger_required': True,
                   'include_prefixes_continuations_smoke_and_retries': True, 'borrow_from_prior_campaign': False,
                   'preserve_uncertain_reservations': True, 'halt_before_unfunded_request': True,
                   'resume_only_after_user_review': True},
        'dispatch_requirements': [
            'Freeze runtime, source, sampling, schedule and official tool/eval hashes before paid calls.',
            'Every registered prefix is attempted once; all partitions finish screening before continuation outcome-based interpretation.',
            'Pair identity and G9 on the identical passed GPT-4.1 prefix. No prefix regeneration, candidate-outcome screening, or replacement.',
            'Randomize paired blocks and arm order independently of outcomes; keep one repetition and one boundary per condition.',
            'Retain zero-join conditions, all exclusions, interrupted requests, unmatched pairs and their costs.',
            'Stop on integrity/budget failure; no automatic extra repeats or representation retuning.'],
        'analysis_notes': [
            'Report 120 registered conditions and actual eligible-pair denominator separately.',
            'Base and Long-Context of the same family are correlated; do not treat 120 conditions as 120 independent families.',
            'Report domain, boundary, prior-exposure and relation-activation breakdowns; do not change official eval.',
            'This coverage experiment tests frozen graph replacement, not compression or causal benefits of individual relation types.']}
    write_new(HERE / 'dataset-metadata-projection.json', {'metadata_only': True, 'sources': sources,
        'rows': [dict(row, category='multi_turn_' + c, family=f, domain=DOMAINS[f // 50])
                 for c in ('base', 'long_context') for f, row in sorted(by_category[c].items())]})
    write_new(HERE / 'coverage120-selection-v1.json', selection)
    print(json.dumps({'counts': selection['counts'], 'selected_families': {x['domain']: x['selected_families'] for x in ranking},
        'selection_sha256': pin(HERE / 'coverage120-selection-v1.json')['sha256']}))


if __name__ == '__main__':
    main()
