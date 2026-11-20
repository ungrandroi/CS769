"""Offline lexical views over existing payload layer string owners in a full evidence graph graph.

Only find.result /matches/* is eligible. Ranges count decoded Unicode codepoints,
not JSON characters/bytes. No path normalization, identity, state or action rule.
The new layer stores references/ranges only; rendering resolves the original owner.
"""
from collections import Counter
from copy import deepcopy
import json
import re

from cs769.models.graphs import graph_memory_payload as p, graph_memory_records as r
from cs769.models.graphs import graph_memory_structured as s
from cs769.models.graphs.graph_memory_encoding import LAYOUTS as ENCODING_LAYOUTS, render_encoding_segments
from cs769.models.graphs.graph_memory_record_visibility import render_record_visibility_segments

VERSION = 'find-lexical-owner-views-v1'
RULESET = 'find-path-view-inventory-v1'
BASE_KEYS = r.BASE_KEYS | {'record_layer'}
LAYOUTS = ('external-record-evidence-v1',) + ENCODING_LAYOUTS


def _shape(value):
    # Transcribed without broadening the frozen input inventory's shape rules.
    if not isinstance(value, str):
        return 'non-string', None
    if not value:
        return 'empty', None
    if any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in value):
        return 'control-or-surrogate', None
    if '\\' in value or re.match(r'^[A-Za-z]:', value):
        return 'windows-or-backslash', None
    if re.match(r'^[A-Za-z][A-Za-z0-9+.-]*:', value):
        return 'uri-scheme', None
    if value.startswith('//'):
        return 'double-leading-slash', None
    if '//' in value:
        return 'repeated-slash', None
    index = value.rfind('/')
    if index < 0:
        return 'no-slash', None
    if index == len(value) - 1:
        return 'trailing-slash', None
    if index == 0:
        return 'empty-prefix', None
    return None, {'prefix': [0, index], 'separator': [index, index + 1],
                  'basename': [index + 1, len(value)]}


def strip_lexical_graph(graph):
    return {key: deepcopy(graph[key]) for key in BASE_KEYS}


def _require_base(base):
    if not isinstance(base, dict) or set(base) != BASE_KEYS:
        raise ValueError('Expected full record inference only')
    audit = r.audit_record_graph(base)
    if not audit['ok']:
        raise ValueError('Invalid record graph: ' + '; '.join(audit['errors']))
    if base['record_layer']['variant'] != 'record-joins-v1':
        raise ValueError('Lexical views require the complete record graph')
    return audit


def _layer(base):
    restored = p.restore_observed_graph(r.strip_record_graph(base))
    events = restored['evidence_view']['nodes']
    calls = {n['id']: next(f['value'] for f in n['fields'] if f['field'].endswith('name'))
             for n in events if n['category'] == 'tool_call'}
    fields = {(f['event_id'], f['field']): f for f in base['payload_layer']['fields']}
    owners = {n['id']: n for n in base['payload_layer']['nodes']}
    nodes, edges, abstentions = [], [], Counter()
    result_count = entry_count = 0
    for event in events:
        if event['category'] != 'tool_result' or calls[event['result_of']] != 'find':
            continue
        result_count += 1
        for field in event['fields']:
            documents = s._documents(field['value'])
            if not documents:
                abstentions['unparsed-result-field'] += 1
            for document_pointer, encoding, document in documents:
                if not isinstance(document, dict) or not isinstance(document.get('matches'), list):
                    abstentions['matches-array-absent-or-invalid'] += 1
                    continue
                for index, value in enumerate(document['matches']):
                    entry_count += 1
                    pointer = '/matches/' + str(index)
                    reason, spans = _shape(value)
                    if reason:
                        abstentions[reason] += 1
                        continue
                    if document_pointer:
                        abstentions['encoded-document-scalar'] += 1
                        continue
                    meta = fields[(event['id'], field['field'])]
                    try:
                        owner, granularity = p._locate(meta['root'], pointer, owners)
                        if (granularity != 'exact_value_node' or owners[owner]['kind'] != 'scalar'
                                or owners[owner].get('scalar_type') != 'string'):
                            abstentions['not-independent-string-scalar'] += 1
                            continue
                        if json.loads(p._expand(owner, owners)) != value:
                            raise ValueError('Owner and source disagree')
                    except (ValueError, KeyError, IndexError):
                        abstentions['ambiguous-or-missing-owner'] += 1
                        continue
                    source = {'event_id': event['id'], 'field': field['field'],
                              'pointer': pointer, 'field_sha256': meta['text_sha256']}
                    identity = 'g11:path:' + p._digest(source)
                    nodes.append({'id': identity, 'category': 'path_occurrence',
                        'payload_node': owner, 'call': event['result_of'], 'source': source,
                        'separator_range': spans['separator']})
                    for part, relation in (('prefix', 'lexical_parent_prefix'),
                                           ('basename', 'lexical_basename_suffix')):
                        target = identity + ':' + part
                        nodes.append({'id': target, 'category': 'string_span',
                            'payload_node': owner, 'range': spans[part],
                            'coordinates': 'decoded-unicode-codepoints'})
                        edges.append({'id': identity + ':edge:' + part, 'from': identity,
                                      'to': target, 'relation': relation})
    return {'version': VERSION, 'ruleset': RULESET, 'base_record_sha256': p._digest(base),
            'nodes': nodes, 'edges': edges, 'find_result_count': result_count,
            'matches_entry_count': entry_count, 'abstention_counts': dict(sorted(abstentions.items()))}


def build_lexical_graph(record_graph):
    _require_base(record_graph)
    graph = deepcopy(record_graph)
    graph['lexical_layer'] = _layer(record_graph)
    return graph


def audit_lexical_graph(graph):
    result = {'ok': False, 'errors': [], 'payload_preserved': False,
              'path_count': 0, 'span_count': 0, 'edge_count': 0,
              'additional_content_owner_count': 0}
    try:
        if not isinstance(graph, dict) or set(graph) != BASE_KEYS | {'lexical_layer'}:
            raise ValueError('Expected lexical inference only')
        base = strip_lexical_graph(graph)
        _require_base(base)
        layer = graph['lexical_layer']
        ids = [n['id'] for n in layer['nodes'] + layer['edges']]
        if len(ids) != len(set(ids)):
            raise ValueError('Duplicate lexical ID')
        node_ids = {n['id'] for n in layer['nodes']}
        if any(e['from'] not in node_ids or e['to'] not in node_ids for e in layer['edges']):
            raise ValueError('Dangling lexical edge')
        if p._json(layer) != p._json(_layer(base)):
            raise ValueError('Lexical layer differs from current owners, sources or rules')
        result.update(ok=True, payload_preserved=True,
            path_count=sum(n['category'] == 'path_occurrence' for n in layer['nodes']),
            span_count=sum(n['category'] == 'string_span' for n in layer['nodes']),
            edge_count=len(layer['edges']), find_result_count=layer['find_result_count'],
            matches_entry_count=layer['matches_entry_count'], abstention_counts=layer['abstention_counts'])
    except (ValueError, KeyError, TypeError, IndexError, AttributeError, RecursionError) as exc:
        result['errors'] = [str(exc)]
    return result


def _base_segments(graph, layout):
    if layout == 'external-record-evidence-v1':
        return render_record_visibility_segments(graph, visible_observations=False)
    return render_encoding_segments(graph, layout=layout)


def render_lexical_segments(graph, *, layout='external-record-evidence-v1'):
    audit = audit_lexical_graph(graph)
    if not audit['ok']:
        raise ValueError('Invalid lexical graph: ' + '; '.join(audit['errors']))
    base = strip_lexical_graph(graph)
    segments = _base_segments(base, layout)
    layer = graph['lexical_layer']
    paths = [n for n in layer['nodes'] if n['category'] == 'path_occurrence']
    if not paths:
        return segments
    nodes = {n['id']: n for n in layer['nodes']}
    owners = {n['id']: n for n in graph['payload_layer']['nodes']}
    lines = ['\nPath text parts']
    for index, path in enumerate(paths):
        source = path['source']
        line = ('l' + str(index) + ' = ' + source['event_id'] + '[' + p._json(source['field'])
                + '] pointer=' + p._json(source['pointer']) + ': ')
        value = json.loads(p._expand(path['payload_node'], owners))
        parts = []
        for edge in layer['edges']:
            if edge['from'] == path['id']:
                start, end = nodes[edge['to']]['range']
                name = {'lexical_parent_prefix':'prefix', 'lexical_basename_suffix':'basename'}[edge['relation']]
                parts.append(name + '=' + p._json(value[start:end]))
        lines.append(line + '; '.join(parts))
    return segments + [{'kind': 'g11_lexical_references', 'text': '\n'.join(lines) + '\n'}]


def render_lexical_graph(graph, *, layout='external-record-evidence-v1'):
    return ''.join(s['text'] for s in render_lexical_segments(graph, layout=layout))


def audit_lexical_render(graph, *, layout='external-record-evidence-v1', rendered_text=None):
    audit = audit_lexical_graph(graph)
    audit.update(layout=layout, base_exact=False, characters=0, added_characters=0)
    if not audit['ok']:
        return audit
    try:
        segments = render_lexical_segments(graph, layout=layout)
        base = _base_segments(strip_lexical_graph(graph), layout)
        retained = [s for s in segments if s['kind'] != 'g11_lexical_references']
        if retained != base:
            raise ValueError('Base encoding segments changed')
        text = ''.join(s['text'] for s in segments)
        if rendered_text is not None and text != rendered_text:
            raise ValueError('Supplied rendering differs from lexical graph')
        audit.update(base_exact=True, characters=len(text),
                     added_characters=sum(len(s['text']) for s in segments if s['kind']=='g11_lexical_references'))
    except (ValueError, KeyError, TypeError, IndexError, AttributeError, RecursionError) as exc:
        audit.update(ok=False, errors=[str(exc)])
    return audit


def plan_lexical_projection(graph, *, removed_member_ids):
    """Offline real member/element deletion closure; no projected carrier is emitted."""
    audit = audit_lexical_graph(graph)
    if not audit['ok']:
        raise ValueError('Cannot plan an invalid lexical graph')
    record_plan = r.plan_record_projection(strip_lexical_graph(graph), removed_member_ids=removed_member_ids)
    removed = set(record_plan['payload_plan']['removed_payload_node_ids'])
    layer = graph['lexical_layer']
    valid_nodes = {n['id'] for n in layer['nodes'] if n['payload_node'] not in removed}
    valid_edges = {e['id'] for e in layer['edges'] if e['from'] in valid_nodes and e['to'] in valid_nodes}
    return {'version': 'lexical-member-projection-plan-v1', 'base_graph_sha256': p._digest(graph),
        'record_plan': record_plan,
        'required_removed_lexical_node_ids': [n['id'] for n in layer['nodes'] if n['id'] not in valid_nodes],
        'required_removed_lexical_edge_ids': [e['id'] for e in layer['edges'] if e['id'] not in valid_edges],
        'supported_lexical_node_ids': [n['id'] for n in layer['nodes'] if n['id'] in valid_nodes],
        'supported_lexical_edge_ids': [e['id'] for e in layer['edges'] if e['id'] in valid_edges],
        'requires_source_label_refresh': True, 'requires_projected_graph_audit': True,
        'applied': False, 'task_preservation_certified': False}


def audit_lexical_projection_plan(graph, plan):
    try:
        expected = plan_lexical_projection(graph,
            removed_member_ids=plan['record_plan']['removed_member_ids'])
        if p._json(expected) != p._json(plan):
            raise ValueError('Lexical projection differs from owner support closure')
        return {'ok': True, 'errors': [], 'applied': False}
    except (ValueError, KeyError, TypeError, IndexError, AttributeError, RecursionError) as exc:
        return {'ok': False, 'errors': [str(exc)], 'applied': False}
