"""One lossless call-signature layout over the frozen G10 event blocks.

The graph and every typed evidence segment stay unchanged. Existing type labels
precede name(raw_arguments); a forward result address inverts only result_of.
Unsafe signatures keep their complete original event block, without a warning.
"""
from collections import Counter
from copy import deepcopy
import re

from cs769.graphs.graph_memory_encoding import render_encoding_segments
from cs769.graphs.graph_memory_records import audit_record_graph


LAYOUTS = ('call-signatures-v1',)


def _fallback_reason(name, arguments, field, payload_nodes):
    if name['value_type'] != 'str' or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name['text']):
        return 'unsafe_function_name'
    if arguments['value_type'] not in ('str', 'dict'):
        return 'non_object_arguments_type'
    if field['parse_fallback'] is not None:
        return 'opaque_arguments'
    # Qualify from the existing audited CST, without a second parser or reprint.
    document = payload_nodes[field['root']]
    return None if (document['kind'] == 'document'
                    and payload_nodes[document['value']]['kind'] == 'object') else 'non_object_arguments'


def _build(graph, layout):
    if layout not in LAYOUTS:
        raise ValueError('Unsupported call-signature layout')
    # This validates the complete record graph and restores only owned payload.
    base = render_encoding_segments(graph, layout='event-blocks-v1')
    view = graph['evidence_view']
    nodes = {node['id']: node for node in view['nodes']}
    results = {}
    for identity in view['recorded_order']:
        node = nodes[identity]
        if node['category'] == 'tool_result':
            if node['result_of'] in results:
                raise ValueError('Duplicate result edge')
            results[node['result_of']] = identity
    fields = {}
    for index, segment in enumerate(base):
        if segment['kind'] == 'evidence':
            fields.setdefault(segment['node_id'], []).append(index)
    payload_fields = {(field['event_id'], field['field']): field for field in graph['payload_layer']['fields']}
    payload_nodes = {node['id']: node for node in graph['payload_layer']['nodes']}
    replacements, signatures, fallbacks, removed = {}, [], [], set()
    for identity in view['recorded_order']:
        if nodes[identity]['category'] != 'tool_call':
            continue
        indices = fields[identity]
        if len(indices) != 2:
            raise ValueError('Frozen tool-call field contract changed')
        name_index, arguments_index = indices
        name, arguments = base[name_index], base[arguments_index]
        name_label = {'kind': 'label', 'text': 'name [' + name['value_type'] + ']\n'}
        arguments_label = {'kind': 'label', 'text': 'arguments [' + arguments['value_type'] + ']\n'}
        if (name['field'].rsplit('.', 1)[-1] != 'name'
                or arguments['field'].rsplit('.', 1)[-1] != 'arguments'
                or arguments_index != name_index + 3
                or base[name_index - 1] != name_label
                or base[name_index + 1] != {'kind': 'label', 'text': '\n'}
                or base[arguments_index - 1] != arguments_label
                or base[arguments_index + 1] != {'kind': 'label', 'text': '\n'}
                or base[name_index - 2]['kind'] != 'encoding_fence'
                or base[arguments_index + 2] != base[name_index - 2]):
            raise ValueError('Frozen event-block segment contract changed')
        target = results[identity]
        payload_field = payload_fields[(identity, arguments['field'])]
        reason = _fallback_reason(name, arguments, payload_field, payload_nodes)
        if reason:
            fallbacks.append({'node_id': identity, 'result_node_id': target, 'reason': reason,
                              'payload_parse_fallback': payload_field['parse_fallback']})
            continue
        # Move the existing argument type label before the two joined raw fields.
        # Each retained original segment has one source index; syntax has none.
        replacement = [(arguments_index - 1, deepcopy(arguments_label)),
                       (name_index, deepcopy(name)),
                       (None, {'kind': 'signature_syntax', 'text': '(', 'node_id': identity}),
                       (arguments_index, deepcopy(arguments)),
                       (None, {'kind': 'signature_syntax', 'text': ') -> ' + target,
                               'node_id': identity, 'result_node_id': target})]
        replacements[name_index] = (arguments_index + 1, replacement)
        removed.add(name_index + 1)  # Only the former name/argument label separator.
        signatures.append({'node_id': identity, 'result_node_id': target,
                           'name_type': name['value_type'], 'arguments_type': arguments['value_type']})
    trace, index = [], 0
    while index < len(base):
        if index in replacements:
            index, items = replacements[index]
            trace.extend(items)
        else:
            trace.append((index, deepcopy(base[index])))
            index += 1
    retained = [index for index, _ in trace if index is not None]
    if Counter(retained) != Counter(index for index in range(len(base)) if index not in removed):
        raise ValueError('Original segment coverage changed')
    if any(segment != base[index] for index, segment in trace if index is not None):
        raise ValueError('Original segment value changed')
    segments = [segment for _, segment in trace]
    evidence = lambda items: [segment for segment in items if segment['kind'] == 'evidence']
    if evidence(segments) != evidence(base):
        raise ValueError('Typed evidence or recorded field order changed')
    appendix = lambda items: [segment for segment in items if segment['kind'] == 'g9_external_references']
    if appendix(segments) != appendix(base):
        raise ValueError('External record references changed')
    if not signatures and segments != base:
        raise ValueError('Zero-signature layout differs from event-block control')
    detail = {'base_layout': 'event-blocks-v1', 'event_count': len(fields),
              'tool_call_count': len(signatures) + len(fallbacks),
              'evidence_field_count': len(evidence(base)),
              'evidence_characters': sum(len(s['text']) for s in evidence(base)),
              'signature_count': len(signatures), 'fallback_count': len(fallbacks),
              'fallback_reason_counts': dict(Counter(row['reason'] for row in fallbacks)),
              'signature_nodes': signatures, 'fallback_nodes': fallbacks,
              'control_characters': sum(len(s['text']) for s in base),
              'characters': sum(len(s['text']) for s in segments),
              'record_appendix_characters': sum(len(s['text']) for s in appendix(base))}
    detail['character_delta'] = detail['characters'] - detail['control_characters']
    return segments, detail


def render_signature_segments(graph, *, layout='call-signatures-v1'):
    return _build(graph, layout)[0]


def render_signature_graph(graph, *, layout='call-signatures-v1'):
    return ''.join(segment['text'] for segment in render_signature_segments(graph, layout=layout))


def audit_signature_render(graph, *, layout='call-signatures-v1', rendered_text=None):
    result = {**audit_record_graph(graph), 'layout': layout, 'visible_observations': False,
              'evidence_exact': False, 'evidence_order_preserved': False,
              'event_headers_exact': False, 'result_bodies_exact': False,
              'field_type_labels_exact': False, 'record_appendix_exact': False,
              'signature_count': 0, 'fallback_count': 0, 'fallback_reason_counts': {},
              'characters': 0}
    if not result['ok']:
        return result
    try:
        segments, detail = _build(graph, layout)
        text = ''.join(segment['text'] for segment in segments)
        if rendered_text is not None and rendered_text != text:
            raise ValueError('Supplied rendering differs from call-signature layout')
        result.update(detail, evidence_exact=True, evidence_order_preserved=True,
                      event_headers_exact=True, result_bodies_exact=True,
                      field_type_labels_exact=True, record_appendix_exact=True)
    except (ValueError, KeyError, TypeError, IndexError, AttributeError, RecursionError) as exc:
        result.update(ok=False, errors=[str(exc)])
    return result
