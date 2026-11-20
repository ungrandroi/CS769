"""Prepare an outcome-blind prefix review bundle; never run model inference."""
import argparse
import csv
import hashlib
import importlib
import json
from collections import Counter
from pathlib import Path

from core.mixed_observations import tool_spec
from core.optimized_graph import _same, restore_history


def digest_bytes(value):
    return hashlib.sha256(value).hexdigest()


def prepare(repo, output):
    repo, output = Path(repo).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError(f'Refusing to replace an existing review bundle: {output}')
    source_hashes = {}

    def read_json(path):
        raw = path.read_bytes()
        source_hashes[str(path.relative_to(repo))] = digest_bytes(raw)
        return json.loads(raw)

    # The current decoders must be the historical decoders. New diagnostic view
    # helpers do not change these modules or any frozen source snapshot.
    snapshot = repo / 'experiments/bfcl_identity/mixed_tool_expansion/source_code/adapters-v1'
    for name in ('optimized_graph.py', 'lossless_state.py', 'lossless_event.py',
                 'mixed_observations.py'):
        current = repo / 'scripts/core' / name
        frozen = snapshot / 'scripts/core' / name
        if not frozen.exists():
            frozen = snapshot / 'core' / name
        if current.read_bytes() != frozen.read_bytes():
            raise ValueError(f'Historical source changed: {name}')
        source_hashes[str(frozen.relative_to(repo))] = digest_bytes(frozen.read_bytes())

    index = repo / 'experiments/bfcl_identity/combined_work1000/paired-samples.csv'
    source_hashes[str(index.relative_to(repo))] = digest_bytes(index.read_bytes())
    with index.open() as stream:
        # Outcome columns are deliberately never inspected or copied.
        source_rows = [row for row in csv.DictReader(stream)
                       if row['source_study'] == 'mixed_tool_expansion']
    cases, mapping, domains, tools, families = [], [], Counter(), Counter(), set()
    for row in sorted(source_rows, key=lambda item: item['sample_id']):
        path = repo / row['event-optimized_path']
        history = read_json(path / 'checkpoint-history.json')
        nonfile = [message for message in history
                   if message.get('type') == 'function_call'
                   and tool_spec(message['name'])['domain'] not in ('GorillaFileSystem', 'Unknown')]
        if not nonfile:
            continue
        working = [m for m in history if m.get('role') not in ('system', 'developer')]
        case_id = 'prefix-' + digest_bytes(row['sample_id'].encode())[:16]
        payloads = {}
        for label in ('state-optimized', 'event-optimized', 'dedup-optimized'):
            run = repo / row[label + '_path']
            checkpoint = read_json(run / 'checkpoint-history.json')
            if not _same(history, checkpoint):
                raise AssertionError(f'Unpaired prefix: {case_id}')
            metadata = read_json(run / 'memory-metadata.json')
            graph = metadata['graph']
            if not _same(working, restore_history(graph)):
                raise AssertionError(f'History mismatch: {case_id}')
            module = metadata['codec_module']
            if module not in ('core.lossless_state', 'core.lossless_event'):
                raise ValueError(f'Unrecognized decoder: {module}')
            if not _same(graph, importlib.import_module(module).decode(metadata['encoded'])):
                raise AssertionError(f'Payload mismatch: {case_id}')
            if label != 'dedup-optimized':
                # Dedup shares Event semantics. Verify its source above without
                # duplicating the same semantic facts in the reviewer bundle.
                payloads[label.removesuffix('-optimized')] = graph
        observed_domains = sorted({tool_spec(m['name'])['domain'] for m in nonfile})
        domains.update(observed_domains)
        tools.update(m['name'] for m in nonfile)
        families.add(row['family'])
        cases.append(dict(case_id=case_id, domains=observed_domains,
                          working_history=working, semantic_payloads=payloads))
        mapping.append(dict(case_id=case_id, sample_id=row['sample_id'],
                            family=row['family'], category=row['category'],
                            seed=int(row['seed']), checkpoint_sha256=row['checkpoint_sha256'],
                            source_paths={label: row[label + '_path'] for label in (
                                'identity', 'state-optimized', 'event-optimized', 'dedup-optimized')}))

    if len({case['case_id'] for case in cases}) != len(cases):
        raise AssertionError('Duplicate review case ID')
    if not cases:
        raise ValueError('No actual mixed-history prefixes')
    for relative, expected in source_hashes.items():
        if digest_bytes((repo / relative).read_bytes()) != expected:
            raise AssertionError(f'Source changed during preparation: {relative}')

    output.mkdir(parents=True)
    case_bytes = ''.join(json.dumps(case, ensure_ascii=False, separators=(',', ':')) + '\n'
                         for case in cases).encode()
    (output / 'cases.jsonl').write_bytes(case_bytes)
    manifest = dict(
        status='prepared_for_semantic_review_no_inference',
        source_study='mixed_tool_expansion', source_triggered_prefixes=len(source_rows),
        actual_mixed_prefixes=len(cases), diagnostic_family_count=len(families),
        independent_confirmation_family_count=None,
        selection='All source-study triggered prefixes containing a known non-filesystem call; no outcome filter.',
        blinding='Review cases omit scores, arm outcomes, future continuation, hidden initial state and GT. '
                 'Source paths are in this coordinator manifest only. Aggregate prior results are known; '
                 'this does not claim a new untouched evaluation cohort.',
        domain_prefix_counts=dict(domains), nonfilesystem_call_counts=dict(tools),
        source_sha256=source_hashes, review_cases_sha256=digest_bytes(case_bytes),
        mapping=mapping)
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    (output / 'README.md').write_text(
        '# Outcome-blind semantic review bundle\n\n'
        'Read `cases.jsonl`, the adapters, and public tool contracts. Do not read '
        'the coordinator manifest, scores, future continuations, GT, or hidden initial state.\n\n'
        'All cases contain only the visible prefix at the original conversion boundary '
        'and its saved State/Event semantic payloads. Event-Dedup has the same semantics; '
        'its exact source restoration is also checked during preparation.\n\n'
        'Audit whether factual assertions, validity, unknowns, and source bindings follow '
        'from visible calls/returns and public contracts. Distinguish unsupported assertions '
        'from deliberately conservative unknowns. Cite case IDs and message/fact IDs; '
        'do not infer causes from task success.\n\n'
        'This is diagnostic preparation, not a completed semantic audit, new model run, '
        'or independent confirmation set. Existing experimental files are not modified.\n')
    return {key: manifest[key] for key in (
        'status', 'actual_mixed_prefixes', 'diagnostic_family_count',
        'domain_prefix_counts', 'nonfilesystem_call_counts')}


def preflight(repo, bundle, output):
    """Check all archived inputs offline; token counts exclude fixed tool overhead."""
    from copy import deepcopy
    from core.diagnostic_views import (expand_shared_references, goal_boundary_views,
                                       resolve_pointer, state_index)
    from core.local_qwen_tokenizer import LocalQwenTokenizer
    from core.optimized_graph import MINIMAL, dumps
    from core.qwen_prompt_accounting import render_prompt

    repo, bundle, output = Path(repo).resolve(), Path(bundle).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError(f'Refusing to replace preflight results: {output}')
    manifest = json.loads((bundle / 'manifest.json').read_text())

    def verify_sources():
        for rel, expected in manifest['source_sha256'].items():
            if digest_bytes((repo / rel).read_bytes()) != expected:
                raise AssertionError(f'Archived source changed: {rel}')

    def verify_index(value, graph):
        if isinstance(value, dict):
            for key, child in value.items():
                if key.endswith('_ref'):
                    resolve_pointer(graph, child)
                elif key == 'fact_refs':
                    for pointer in child:
                        resolve_pointer(graph, pointer)
                else:
                    verify_index(child, graph)
        elif isinstance(value, list):
            for child in value:
                verify_index(child, graph)

    verify_sources()
    rows = []
    with LocalQwenTokenizer() as tokenizer:
        for record in manifest['mapping']:
            for method in ('state-optimized', 'event-optimized', 'dedup-optimized'):
                run = repo / record['source_paths'][method]
                history = json.loads((run / 'checkpoint-history.json').read_text())
                latest_user = [m for m in history if m.get('role') == 'user'][-1]
                goal = latest_user['content']
                if not isinstance(goal, str):
                    raise ValueError('Current diagnostic requires an exact text-only user goal')
                metadata = json.loads((run / 'memory-metadata.json').read_text())
                graph, encoded = metadata['graph'], metadata['encoded']
                graph_before = deepcopy(graph)
                index = state_index(graph)
                assert _same(graph, graph_before)
                verify_index(index['view'], graph)
                common = deepcopy(encoded)
                # Both reference arms receive the SAME explicit compatibility
                # rule before changing any references. Original records stay intact.
                rule_key = 'decoding' if method == 'state-optimized' else 'shared_rule'
                if 'shared_values' in common:
                    common[rule_key] += ' Non-reference values retain their literal types; reserved keys keep their documented escaping.'
                    expanded = expand_shared_references(common)
                    expansion_status = 'eligible' if expanded['audit']['expanded_references'] else 'empty_dictionary_negative_control'
                else:
                    expanded = {'encoded': deepcopy(common), 'audit': {
                        'expanded_references': 0, 'typed_decode_equal': True,
                        'negative_control_unchanged': True}}
                    expansion_status = 'codec_has_no_shared_references_negative_control'
                decoder = importlib.import_module(metadata['codec_module'])
                assert _same(decoder.decode(common), graph)
                assert _same(decoder.decode(expanded['encoded']), graph)
                if expanded['audit']['expanded_references'] == 0:
                    assert dumps(common) == dumps(expanded['encoded'])
                # Goal/index diagnostics use their unchanged selected encoding;
                # the common reference rule above belongs only to the ref pair.
                memory = MINIMAL + '\n' + dumps(encoded)
                pair = goal_boundary_views([{'role': 'user', 'content': memory}], goal)
                inline = render_prompt(pair['inline'], [], tokenizer.chat_template, False)
                separate = render_prompt(pair['separate'], [], tokenizer.chat_template, False)
                old = memory + pair['goal_view']
                assert inline.count(old) == 1
                expected = inline.replace(old, memory + '<|im_end|>\n<|im_start|>user\n' + pair['goal_view'], 1)
                assert expected == separate, 'Native template altered more than the message boundary'
                rows.append(dict(
                    case_id=record['case_id'], method=method, state_index=index['audit'],
                    reference_expansion={**expanded['audit'], 'status': expansion_status},
                    native_goal_boundary_exact=True,
                    reference_common_body_tokens=tokenizer.count(dumps(common)),
                    reference_expanded_body_tokens=tokenizer.count(dumps(expanded['encoded'])),
                    index_view_tokens=tokenizer.count(dumps(index['view'])),
                    goal_inline_memory_context_tokens=tokenizer.count(inline, parse_special=True),
                    goal_separate_memory_context_tokens=tokenizer.count(separate, parse_special=True)))
        tokenizer_audit = tokenizer.provenance
    verify_sources()
    counts = {}
    for method in ('state-optimized', 'event-optimized', 'dedup-optimized'):
        group = [row for row in rows if row['method'] == method]
        counts[method] = dict(
            inputs=len(group), native_goal_boundary_checks=sum(r['native_goal_boundary_exact'] for r in group),
            state_index_nonempty=sum(r['state_index']['eligible_entries'] > 0 for r in group),
            shared_reference_nonempty=sum(r['reference_expansion']['expanded_references'] > 0 for r in group),
            reference_negative_controls=sum(r['reference_expansion']['expanded_references'] == 0 for r in group))
    report = dict(
        status='offline_input_preflight_pass_no_inference', inputs=len(rows), counts=counts,
        tokenizer=tokenizer_audit,
        token_scope='Offline memory-only inputs. Fixed actual tool definitions are absent; '
                    'these are NOT full-input acceptance measurements or new model usage.',
        limits='Helper and input checks only; no resumed runner, official task score, '
               'capability result, or completed exhaustive semantic audit is claimed.',
        source_files_verified_unchanged=len(manifest['source_sha256']),
        helper_sha256=digest_bytes((repo / 'scripts/core/diagnostic_views.py').read_bytes()),
        workflow_sha256=digest_bytes(Path(__file__).read_bytes()), rows=rows)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    return {key: report[key] for key in ('status', 'inputs', 'counts', 'source_files_verified_unchanged')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path.cwd())
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--preflight', type=Path, help='Check an existing coordinator review bundle offline')
    args = parser.parse_args()
    result = preflight(args.repo, args.preflight, args.output) if args.preflight else prepare(args.repo, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
