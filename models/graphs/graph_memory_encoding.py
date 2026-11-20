"""Two offline encodings of the same complete evidence graph graph.

Only fence boundaries change. All non-fence labels and all evidence remain in
their recorded order; the existing external record appendix is copied exactly.
No carrier, adapter, state summary, semantic edge or projection rule is added.
"""
from collections import Counter
from copy import deepcopy
import re

from cs769.models.graphs.graph_memory_evidence import render_evidence_segments
from cs769.models.graphs.graph_memory_observed import strip_observed_graph
from cs769.models.graphs.graph_memory_payload import restore_observed_graph
from cs769.models.graphs.graph_memory_records import strip_record_graph, audit_record_graph
from cs769.models.graphs.graph_memory_record_visibility import render_record_visibility_segments


LAYOUTS = ('event-blocks-v1', 'exchange-blocks-v1')


def _blocks(evidence, layout):
    view = evidence['evidence_view']
    ordered = view['recorded_order']
    nodes = {node['id']: node for node in view['nodes']}
    positions = {identity: i for i, identity in enumerate(ordered)}
    groups, results = {}, {}
    for identity in ordered:
        node = nodes[identity]
        if node['category'] == 'tool_call':
            groups.setdefault(node['call_group'], []).append(identity)
        elif node['category'] == 'tool_result':
            if node['result_of'] in results:
                raise ValueError('Duplicate result edge')
            results[node['result_of']] = identity
    safe, fallback = [], []
    for group, calls in groups.items():
        returns = [results[call] for call in calls]
        members = set(calls + returns)
        start, end = min(positions[n] for n in members), max(positions[n] for n in members)
        interval = ordered[start:end + 1]
        reason = None
        if len({nodes[n]['episode'] for n in members}) != 1:
            reason = 'cross_episode'
        elif set(interval) != members:
            reason = 'noncontiguous_exchange'
        elif max(positions[n] for n in calls) >= min(positions[n] for n in returns):
            reason = 'interleaved_call_and_result'
        item = {'call_group': group, 'call_ids': calls, 'result_ids': returns,
                'recorded_order': [n for n in interval if n in members]}
        if reason:
            fallback.append({**item, 'reason': reason})
        else:
            safe.append(item)
    starts = {item['recorded_order'][0]: item for item in safe}
    blocks, index = [], 0
    while index < len(ordered):
        identity = ordered[index]
        selected = starts.get(identity) if layout == 'exchange-blocks-v1' else None
        block = selected['recorded_order'] if selected else [identity]
        if ordered[index:index + len(block)] != block:
            raise ValueError('Exchange closure would change recorded order')
        blocks.append(block)
        index += len(block)
    return blocks, safe, fallback


def _build(graph, layout):
    if layout not in LAYOUTS:
        raise ValueError('Unsupported evidence encoding')
    audit = audit_record_graph(graph)
    if not audit['ok']:
        raise ValueError('Invalid record graph: ' + '; '.join(audit['errors']))
    if graph['record_layer']['variant'] != 'record-joins-v1':
        raise ValueError('Encoding requires the same complete record-joins-v1 graph')
    # Restore owned payload, never source_messages or an archive fallback.
    evidence = strip_observed_graph(restore_observed_graph(strip_record_graph(graph)))
    original = render_evidence_segments(evidence, layout='chronological-first')
    visibility = render_record_visibility_segments(graph, visible_observations=False)
    body = ''.join(segment['text'] for segment in original)
    if (not visibility or visibility[0] != {'kind': 'g5-compatible', 'text': body}
            or any(s['kind'] != 'g9_external_references' for s in visibility[1:])):
        raise ValueError('Frozen visibility segment contract changed')
    appendix = deepcopy(visibility[1:])
    fields = [segment for segment in original if segment['kind'] == 'evidence']
    fence = '`' * max(3, 1 + max((len(match.group()) for segment in fields
        for match in re.finditer(r'`+', segment['text'])), default=0))
    by_node = {}
    for index, segment in enumerate(original):
        if segment['kind'] == 'evidence':
            by_node.setdefault(segment['node_id'], []).append(index)
    if list(by_node) != evidence['evidence_view']['recorded_order']:
        raise ValueError('Evidence segment order differs from graph')
    blocks, safe, fallback = _blocks(evidence, layout)
    opens = {by_node[block[0]][0] - 1 for block in blocks}
    closes = {by_node[block[-1]][-1] + 1 for block in blocks}
    changes = {}
    for indices in by_node.values():
        for index in indices:
            field = original[index]
            label = field['field'].rsplit('.', 1)[-1] + ' [' + field['value_type'] + ']\n'
            if (original[index - 1] != {'kind': 'label', 'text': label + fence + '\n'}
                    or original[index + 1] != {'kind': 'label', 'text': '\n' + fence + '\n'}):
                raise ValueError('Frozen field/fence segment contract changed')
            changes[index - 1] = label
            changes[index + 1] = '\n'
    segments, original_without_fences = [], []
    for index, segment in enumerate(original):
        replacement = {**deepcopy(segment), 'text': changes.get(index, segment['text'])}
        original_without_fences.append(replacement['text'])
        if index in opens:
            segments.append({'kind': 'encoding_fence', 'text': fence + '\n'})
        segments.append(replacement)
        if index in closes:
            segments.append({'kind': 'encoding_fence', 'text': fence + '\n'})
    if [s for s in segments if s['kind'] == 'evidence'] != fields:
        raise ValueError('Original evidence changed')
    if ''.join(s['text'] for s in segments if s['kind'] != 'encoding_fence') != ''.join(original_without_fences):
        raise ValueError('Non-fence labels or evidence changed')
    detail = {'event_count': len(by_node), 'evidence_field_count': len(fields),
              'evidence_characters': sum(len(s['text']) for s in fields),
              'block_count': len(blocks), 'fence_count': 2 * len(blocks),
              'original_fence_count': 2 * len(fields),
              'exchange_group_count': len(safe) + len(fallback),
              'eligible_exchange_groups': safe,
              'grouped_exchange_count': len(safe) if layout == 'exchange-blocks-v1' else 0,
              'grouped_multi_call_count': sum(len(s['call_ids']) > 1 for s in safe)
                  if layout == 'exchange-blocks-v1' else 0,
              'fallback_exchange_groups': fallback if layout == 'exchange-blocks-v1' else [],
              'fallback_reason_counts': dict(Counter(s['reason'] for s in fallback))
                  if layout == 'exchange-blocks-v1' else {},
              'blocks': blocks, 'base_characters': sum(len(s['text']) for s in segments),
              'original_base_characters': len(body),
              'record_appendix_characters': sum(len(s['text']) for s in appendix)}
    return segments + appendix, detail


def render_encoding_segments(graph, *, layout='event-blocks-v1'):
    return _build(graph, layout)[0]


def render_encoding_graph(graph, *, layout='event-blocks-v1'):
    return ''.join(s['text'] for s in render_encoding_segments(graph, layout=layout))


def audit_encoding_render(graph, *, layout='event-blocks-v1', rendered_text=None):
    audit = audit_record_graph(graph)
    result = {**audit, 'layout': layout, 'visible_observations': False,
              'evidence_exact': False, 'evidence_order_preserved': False,
              'non_fence_text_exact': False, 'record_appendix_exact': False,
              'characters': 0}
    if not audit['ok']:
        return result
    try:
        segments, detail = _build(graph, layout)
        text = ''.join(s['text'] for s in segments)
        if rendered_text is not None and rendered_text != text:
            raise ValueError('Supplied rendering differs from selected encoding')
        result.update(detail, evidence_exact=True, evidence_order_preserved=True,
                      non_fence_text_exact=True, record_appendix_exact=True, characters=len(text))
    except (ValueError, KeyError, TypeError, IndexError, AttributeError, RecursionError) as exc:
        result.update(ok=False, errors=[str(exc)])
    return result
