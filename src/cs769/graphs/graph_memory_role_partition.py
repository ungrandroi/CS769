"""Partition one lossless G9 evidence document into graph-only text messages.

P and R have identical content chunks. Only R restores historical user-request
envelope roles; tool evidence stays text with its original graph source role.
The existing memory_graph wrapper deliberately spans messages. This compiler
never accepts native histories, creates tool wire blocks, or scans raw evidence
for marker-shaped text.
"""
import hashlib

from cs769.graphs.graph_memory_evidence import EPISODIC_VIEW_VERSION, render_evidence_segments
from cs769.graphs.graph_memory_observed import strip_observed_graph
from cs769.graphs.graph_memory_payload import restore_observed_graph
from cs769.graphs.graph_memory_records import strip_record_graph, audit_record_graph
from cs769.graphs.graph_memory_record_visibility import render_record_visibility_segments


PARTITION_LAYOUT = 'graph-role-partition-v1'
ROLE_MODES = ('historical-user', 'assistant-only')


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _partition(graph):
    audit = audit_record_graph(graph)
    _require(audit['ok'], 'Invalid standalone record inference graph')
    evidence = strip_observed_graph(restore_observed_graph(strip_record_graph(graph)))
    view = evidence['evidence_view']
    _require(view['version'] == EPISODIC_VIEW_VERSION, 'Partition requires the frozen G5 evidence view')
    nodes = {node['id']: node for node in view['nodes']}
    ordered = [nodes[identity] for identity in view['recorded_order']]
    _require(bool(ordered) and ordered[0]['category'] == 'user_request',
             'Completed evidence must begin with a user request')
    _require(ordered[-1]['category'] != 'user_request',
             'Completed evidence must end with an assistant or tool event')
    segments = render_evidence_segments(evidence, layout='chronological-first')
    _require(segments[0]['kind'] == 'format', 'Missing dedicated graph header')
    messages = [{'role': 'assistant', 'content': segments[0]['text']}]
    cursor, episode, fields = 1, None, 0
    for node in ordered:
        start = cursor
        if node['episode'] != episode:
            _require(segments[cursor]['kind'] == 'label', 'Missing episode label')
            cursor += 1
            episode = node['episode']
        _require(segments[cursor]['kind'] == 'label', 'Missing node label')
        cursor += 1
        for field in node['fields']:
            opening, value, closing = segments[cursor:cursor + 3]
            _require(opening['kind'] == closing['kind'] == 'label'
                     and value['kind'] == 'evidence'
                     and value['node_id'] == node['id']
                     and value['field'] == field['field']
                     and value['value_type'] == field['value_type'],
                     'Typed renderer schedule differs from evidence node fields')
            cursor += 3
            fields += 1
        content = ''.join(segment['text'] for segment in segments[start:cursor])
        role = 'user' if node['category'] == 'user_request' else 'assistant'
        # The dedicated header remains separate from the first user segment.
        if len(messages) > 1 and messages[-1]['role'] == role:
            messages[-1]['content'] += content
        else:
            messages.append({'role': role, 'content': content})
    tail = segments[cursor:]
    _require(tail and all(segment['kind'] in ('relations', 'format') for segment in tail),
             'Unexpected non-episodic rendering tail')
    _require(messages[-1]['role'] == 'assistant', 'Graph tail requires an assistant segment')
    external = render_record_visibility_segments(graph, visible_observations=False)
    _require(external[0]['kind'] == 'g5-compatible'
             and all(segment['kind'] == 'g9_external_references' for segment in external[1:]),
             'Unexpected external record rendering layout')
    appendix = ''.join(segment['text'] for segment in external[1:])
    messages[-1]['content'] += ''.join(segment['text'] for segment in tail) + appendix
    body = ''.join(segment['text'] for segment in external)
    _require(''.join(message['content'] for message in messages) == body,
             'Graph partition changed the existing evidence document')
    return messages, {
        'payload_preserved': True,
        'exact_concatenation': True,
        'message_count': len(messages),
        'historical_user_segments': sum(message['role'] == 'user' for message in messages),
        'evidence_node_count': len(ordered),
        'evidence_field_count': fields,
        'record_appendix_characters': len(appendix),
        'body_sha256': hashlib.sha256(body.encode('utf-8')).hexdigest(),
    }


def compile_graph_partition(graph, role_mode='historical-user'):
    """Return only historical role/content text messages, with no native fallback."""
    _require(role_mode in ROLE_MODES, 'Unsupported graph partition role mode')
    messages, _ = _partition(graph)
    if role_mode == 'assistant-only':
        for message in messages:
            message['role'] = 'assistant'
    return messages


def render_graph_partition_text(graph):
    """The existing O-off graph document, exactly, reconstructed from graph owners."""
    return ''.join(message['content'] for message in compile_graph_partition(graph))


def audit_graph_partition(graph, messages, role_mode='historical-user'):
    """Check exact chunk boundaries, roles and strict text-only wire schema."""
    result = {'ok': False, 'errors': [], 'layout': PARTITION_LAYOUT,
              'role_mode': role_mode, 'payload_preserved': False,
              'exact_concatenation': False}
    try:
        _require(role_mode in ROLE_MODES, 'Unsupported graph partition role mode')
        expected, metrics = _partition(graph)
        if role_mode == 'assistant-only':
            for message in expected:
                message['role'] = 'assistant'
        _require(isinstance(messages, list) and all(
            isinstance(message, dict) and set(message) == {'role', 'content'}
            and message['role'] in ('user', 'assistant') and isinstance(message['content'], str)
            for message in messages), 'Partition must contain only role/content text messages')
        _require(messages == expected, 'Supplied partition differs from the frozen graph compiler')
        result.update(metrics, ok=True)
    except (ValueError, KeyError, TypeError, IndexError, AttributeError, RecursionError) as exc:
        result['errors'] = [str(exc)]
    return result
