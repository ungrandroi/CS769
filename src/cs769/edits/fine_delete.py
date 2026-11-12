"""Delete exactly one completed tool interaction. Reads only the current graph."""
from copy import deepcopy
import json
from .g9_edit import evidence, render, _refresh, _digest
from cs769.graphs.graph_memory_records import audit_record_graph


def candidates(graph):
    view = evidence(graph)['evidence_view']
    records = [n for n in view['nodes'] if n['category'] != 'episode']
    results = {}
    for node in records:
        if node['category'] == 'tool_result':
            results.setdefault(node['result_of'], []).append(node)
    digest = _digest(graph)
    actions = []
    for call in records:
        if call['category'] != 'tool_call':
            continue
        matched = results.get(call['id'], [])
        if len(matched) != 1 or matched[0]['call_id'] != call['call_id']:
            continue
        actions.append({'kind': 'delete_interaction', 'source_graph_sha256': digest,
                        'call_event_id': call['id'], 'result_event_id': matched[0]['id'],
                        'call_group': call['call_group'], 'call_ordinal': call['ordinal'],
                        'tool': next(f['value'] for f in call['fields'] if f['field'] == 'name')})
    return actions


def apply(graph, action, token_count):
    if action not in candidates(graph):
        raise ValueError('Action is stale or is not one complete tool interaction')
    source_hash = _digest(graph)
    source = evidence(graph)
    edited_evidence = deepcopy(source)
    targets = {action['call_event_id'], action['result_event_id']}
    removed = [deepcopy(n) for n in source['evidence_view']['nodes'] if n['id'] in targets]
    assert len(removed) == 2 and {n['category'] for n in removed} == {'tool_call', 'tool_result'}
    edited_evidence['evidence_view']['nodes'] = [n for n in edited_evidence['evidence_view']['nodes'] if n['id'] not in targets]
    edited, mapping = _refresh(edited_evidence)
    assert audit_record_graph(edited)['ok']
    before = {n['id']: n for n in source['evidence_view']['nodes'] if n['category'] != 'episode'}
    after = {n['id']: n for n in evidence(edited)['evidence_view']['nodes'] if n['category'] != 'episode'}
    assert set(mapping) == set(before) - targets
    for old_id, new_id in mapping.items():
        expected = deepcopy(before[old_id])
        expected.update(id=new_id, ordinal=after[new_id]['ordinal'])
        if 'result_of' in expected:
            expected['result_of'] = mapping[expected['result_of']]
        assert expected == after[new_id], 'Undeclared change to retained evidence'
    old_tokens, new_tokens = token_count(render(graph)), token_count(render(edited))
    if new_tokens >= old_tokens:
        raise ValueError('No positive rendered-memory token saving')
    assert _digest(graph) == source_hash, 'Source graph was mutated'
    return edited, {'version': 'fine-delete-v1', 'operation': 'delete_interaction',
                   'action': action, 'source_graph_sha256': source_hash,
                   'edited_graph_sha256': _digest(edited), 'removed_records': removed,
                   'old_to_new_event_ids': mapping, 'removed_interactions': 1,
                   'memory_tokens_before': old_tokens, 'memory_tokens_after': new_tokens,
                   'saved_tokens': old_tokens-new_tokens, 'applied': True,
                   'retained_evidence_exact': True, 'parallel_siblings_preserved': True,
                   'full_original_evidence_preserved': False, 'task_preservation_certified': False}


def select(graph, token_count):
    available, rejected = [], []
    for action in candidates(graph):
        try:
            edited, audit = apply(graph, action, token_count)
            available.append((edited, audit))
        except ValueError as error:
            rejected.append({'action': action, 'reason': str(error)})
    selected = {}
    for arm in ('delete_oldest', 'delete_recent', 'delete_largest'):
        if not available:
            break
        if arm == 'delete_oldest':
            choice = min(available, key=lambda x: x[1]['action']['call_ordinal'])
        elif arm == 'delete_recent':
            choice = max(available, key=lambda x: x[1]['action']['call_ordinal'])
        else:
            choice = min(available, key=lambda x: (-x[1]['saved_tokens'], x[1]['action']['call_ordinal']))
        selected[arm] = choice
        available.remove(choice)
    return selected, rejected
