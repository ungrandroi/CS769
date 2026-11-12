"""Nested deletion of complete interactions, selected only from frozen G9."""
from copy import deepcopy
from collections import defaultdict
from .fine_delete import candidates
from .g9_edit import evidence, render, _refresh, _digest
from cs769.graphs.graph_memory_records import audit_record_graph


def order_candidates(graph):
    available = sorted(candidates(graph), key=lambda a: a['call_ordinal'], reverse=True)
    if len(available) < 4:
        raise ValueError('At least four complete interactions required')
    anchor = available[0]
    owned = {event: a['call_event_id'] for a in available
             for event in (a['call_event_id'], a['result_event_id'])}
    nodes = {n['id']: n for n in graph['record_layer']['nodes']}
    anchors = defaultdict(set)
    for edge in graph['record_layer']['edges']:
        assert edge['relation'] == 'same_typed_identifier_member'
        occurrence = nodes[edge['from']]
        event = occurrence['source']['event_id']
        if event in owned:
            anchors[edge['to']].add(owned[event])
    linked = set()
    supporting_anchors = []
    for aid, calls in anchors.items():
        if anchor['call_event_id'] in calls and len(calls) > 1:
            linked.update(calls - {anchor['call_event_id']})
            supporting_anchors.append(aid)
    preferred = [a for a in available[1:] if a['call_event_id'] in linked]
    fallback = [a for a in available[1:] if a['call_event_id'] not in linked]
    ordered = [anchor] + preferred + fallback
    sampling = {'rule': 'Latest complete interaction, then direct same-business-ID references, then reverse chronological',
        'anchor_call': anchor['call_event_id'], 'supporting_identifier_anchors': sorted(supporting_anchors),
        'priority_calls': [a['call_event_id'] for a in ordered],
        'selection_reason_by_call': {a['call_event_id']: ('latest_anchor' if a == anchor else
              'same_typed_business_identifier' if a['call_event_id'] in linked else 'chronological_fallback')
              for a in ordered},
        'same_identifier_is_not_causality': True, 'future_outcomes_used': False}
    return ordered, sampling


def apply(graph, actions, token_count):
    legal = candidates(graph)
    if len(actions) not in (2, 3) or len({a['call_event_id'] for a in actions}) != len(actions):
        raise ValueError('Require two or three distinct complete interactions')
    if any(a not in legal for a in actions) or len(legal) <= len(actions):
        raise ValueError('Stale action, incomplete pair, or no interaction left')
    source_hash = _digest(graph)
    source = evidence(graph)
    targets = {event for a in actions for event in (a['call_event_id'], a['result_event_id'])}
    assert len(targets) == 2 * len(actions)
    edited_evidence = deepcopy(source)
    removed = [deepcopy(n) for n in source['evidence_view']['nodes'] if n['id'] in targets]
    assert len(removed) == 2 * len(actions)
    assert all(n['category'] in ('tool_call', 'tool_result') for n in removed)
    edited_evidence['evidence_view']['nodes'] = [n for n in edited_evidence['evidence_view']['nodes'] if n['id'] not in targets]
    edited, mapping = _refresh(edited_evidence)
    assert audit_record_graph(edited)['ok']
    before = {n['id']: n for n in source['evidence_view']['nodes'] if n['category'] != 'episode'}
    after = {n['id']: n for n in evidence(edited)['evidence_view']['nodes'] if n['category'] != 'episode'}
    assert set(mapping) == set(before) - targets
    for old_id, new_id in mapping.items():
        expected = deepcopy(before[old_id]); expected.update(id=new_id, ordinal=after[new_id]['ordinal'])
        if 'result_of' in expected:
            expected['result_of'] = mapping[expected['result_of']]
        assert expected == after[new_id], 'Undeclared retained evidence change'
    assert len(candidates(edited)) == len(legal) - len(actions)
    old_tokens, new_tokens = token_count(render(graph)), token_count(render(edited))
    if new_tokens >= old_tokens:
        raise ValueError('No positive rendered-memory saving')
    assert _digest(graph) == source_hash
    action = {'kind': 'delete_interactions', 'count': len(actions), 'source_graph_sha256': source_hash,
              'interactions': deepcopy(actions)}
    return edited, {'version': 'multi-delete-v1', 'operation': 'delete_interactions', 'action': action,
        'source_graph_sha256': source_hash, 'edited_graph_sha256': _digest(edited),
        'removed_records': removed, 'old_to_new_event_ids': mapping, 'removed_interactions': len(actions),
        'memory_tokens_before': old_tokens, 'memory_tokens_after': new_tokens,
        'saved_tokens': old_tokens-new_tokens, 'applied': True, 'retained_evidence_exact': True,
        'unselected_parallel_siblings_preserved': True, 'full_original_evidence_preserved': False,
        'task_preservation_certified': False}


def select(graph, token_count):
    ordered, sampling = order_candidates(graph)
    selected = {f'delete_{n}': apply(graph, ordered[:n], token_count) for n in (2, 3)}
    return selected, sampling
