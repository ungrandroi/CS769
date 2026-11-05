"""External source locators for the unchanged G9 record inference graph.

This is a renderer iteration: continuous G7-compatible evidence followed by
existing record/occurrence addresses and explicit typed-identifier membership.
No graph layer, content owner, temporal relation or projection rule is added.
"""
import json

from core import graph_memory_payload as p
from core import graph_memory_records as r

LAYOUT = 'external-record-references-v1'


def _source_label(event_id, field, pointer):
    p._pointer_tokens(pointer)
    quote = lambda text: json.dumps(text, ensure_ascii=False)
    return event_id + '[' + quote(field) + '] pointer=' + quote(pointer)


def _locators(graph):
    """Recompute direct-record roots; source pointers remain byte-for-byte text."""
    layer = graph['record_layer']
    records = [n for n in layer['nodes'] if n['category'] == 'payload_record']
    occurrences = [n for n in layer['nodes'] if n['category'] == 'identifier_occurrence']
    anchors = [n for n in layer['nodes'] if n['category'] == 'identifier_anchor']
    aliases = {n['id']: prefix + str(i) for prefix, group in
               (('r', records), ('o', occurrences), ('j', anchors)) for i, n in enumerate(group)}
    payload = {n['id']: n for n in graph['payload_layer']['nodes']}
    fields = {(f['event_id'], f['field']): f for f in graph['payload_layer']['fields']}
    by_record = {n['id']: n for n in records}
    roots = {}
    for occurrence in occurrences:
        source = occurrence['source']
        record = by_record[occurrence['record']]
        pointer = source['pointer']
        if source['document_pointer'] or not p._pointer_tokens(pointer):
            raise ValueError('Occurrence must have an independently owned member pointer')
        parent_pointer = pointer.rsplit('/', 1)[0]
        field = fields[(source['event_id'], source['field'])]
        target, exact = p._locate(field['root'], pointer, payload)
        parent, parent_exact = p._locate(field['root'], parent_pointer, payload)
        member = payload[occurrence['member']]
        if (exact != 'exact_value_node' or parent_exact != 'exact_value_node'
                or target != occurrence['payload_node'] or parent != record['payload_node']
                or payload[parent]['kind'] != 'object' or member['kind'] != 'member'
                or member['value'] != target or member['id'] not in payload[parent]['members']
                or (record['event_id'], record['field']) != (source['event_id'], source['field'])):
            raise ValueError('External locator differs from owned G9 record/member/value')
        locator = (source['event_id'], source['field'], parent_pointer)
        if record['id'] in roots and roots[record['id']] != locator:
            raise ValueError('Record has inconsistent external root locators')
        roots[record['id']] = locator
    if set(roots) != set(by_record):
        raise ValueError('Record lacks a supported external locator')
    lines = ['Identifier links',
        'Links group fields with equal typed identifiers recorded in these tool exchanges.']
    for record in records:
        lines.append(aliases[record['id']] + ' ' + _source_label(*roots[record['id']]))
    for occurrence in occurrences:
        source = occurrence['source']
        lines.append(aliases[occurrence['id']] + ' [' + aliases[occurrence['record']] + '] ' +
            _source_label(source['event_id'], source['field'], source['pointer']))
    for anchor in anchors:
        members = [aliases[e['from']] for e in layer['edges'] if e['to'] == anchor['id']]
        lines.append(aliases[anchor['id']] + ' ' + anchor['namespace'] +
            ' (' + anchor['value_type'] + ')' + (': ' + ' '.join(members) if members else ''))
    return '\n\n' + '\n'.join(lines)


def render_external_record_segments(graph):
    audit = r.audit_record_graph(graph)
    if not audit['ok']:
        raise ValueError('Invalid record graph: ' + '; '.join(audit['errors']))
    segments = p.render_payload_segments(r.strip_record_graph(graph), layout='g7-compatible')
    if audit['active']:
        segments.append({'kind': 'g9_external_references', 'text': _locators(graph)})
    return segments


def render_external_record_graph(graph):
    return ''.join(segment['text'] for segment in render_external_record_segments(graph))


def audit_external_record_render(graph, *, rendered_text=None):
    audit = r.audit_record_graph(graph)
    result = {**audit, 'layout': LAYOUT, 'locator_count': 0, 'exact_g7': False,
              'characters': 0, 'base_characters': 0, 'added_characters': 0}
    if not audit['ok']:
        return result
    try:
        segments = render_external_record_segments(graph)
        body = segments[0]['text']
        text = ''.join(segment['text'] for segment in segments)
        if rendered_text is not None and rendered_text != text:
            raise ValueError('Supplied rendering differs from the external-record layout')
        result.update(locator_count=audit['record_count'] + audit['occurrence_count'],
                      exact_g7=text == body, characters=len(text), base_characters=len(body),
                      added_characters=len(text) - len(body))
    except (ValueError, KeyError, TypeError, IndexError, AttributeError, RecursionError) as exc:
        result['ok'] = False
        result['errors'] = [str(exc)]
    return result
