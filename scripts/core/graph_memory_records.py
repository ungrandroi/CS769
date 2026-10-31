"""G9: typed identifier joins between uniquely owned G8 payload records.

Records are observed JSON objects, not external identities or current state.
Only frozen public G6 identifier contracts are reused; no G6 layer is retained.
Projection returns offline deletion/support plans, never compressed inference.
"""
from collections import defaultdict
from copy import deepcopy

from core import graph_memory_payload as p
from core import graph_memory_structured as s

VERSION = 'payload-record-joins-v1'
VARIANTS = ('record-joins-v1', 'record-nodes-only-v1')
BASE_KEYS = p.G7_KEYS | {'payload_layer'}
ID_NAMESPACES = frozenset(('tickets:ticket_id', 'message:user_id', 'posting:tweet_id',
    'travel:booking_id', 'travel:card_id', 'travel:insurance_id', 'trading:order_id'))


def strip_record_graph(graph):
    return {key: deepcopy(graph[key]) for key in BASE_KEYS}


def _require_base(graph):
    if not isinstance(graph, dict) or set(graph) != BASE_KEYS:
        raise ValueError('Expected only G8 payload inference')
    audit = p.audit_payload_graph(graph)
    if not audit['ok']:
        raise ValueError('Invalid G8 payload graph: ' + '; '.join(audit['errors']))
    return audit


def _layer(base, variant):
    if variant not in VARIANTS:
        raise ValueError('Unknown record variant')
    restored = p._restore(base)
    events = restored['evidence_view']['nodes']
    calls = {n['id']: (n, next(f['value'] for f in n['fields'] if f['field'].endswith('name')))
             for n in events if n['category'] == 'tool_call'}
    payload = base['payload_layer']
    nodes = {n['id']: n for n in payload['nodes']}
    parents = {child: n['id'] for n in nodes.values() for child in n.get('parts', [])}
    fields = {(f['event_id'], f['field']): f for f in payload['fields']}
    buckets, records = defaultdict(list), {}
    accepted = 0
    for event in events:
        if event['category'] not in ('tool_call', 'tool_result'):
            continue
        role = 'argument' if event['category'] == 'tool_call' else 'result'
        call, tool = calls[event['id'] if role == 'argument' else event['result_of']]
        for field in event['fields']:
            if not p._is_tool_field(event, field):
                continue
            meta = fields[(event['id'], field['field'])]
            for document_pointer, encoding, document in s._documents(field['value']):
                # G8 does not give independently owned members to JSON encoded
                # inside a text-block scalar. Coarse bindings cannot form joins.
                if document_pointer:
                    continue
                for pointer, key, value in s._leaves(document):
                    classified = s._classify(tool, role, pointer, key, value)
                    if classified is None:
                        continue
                    namespace, kind, rule, value_type = classified
                    if kind != 'contract_token' or namespace not in ID_NAMESPACES:
                        continue
                    target, granularity = p._locate(meta['root'], pointer, nodes)
                    member = nodes.get(parents.get(target, ''), {})
                    record = nodes.get(parents.get(member.get('id', ''), ''), {})
                    if (granularity != 'exact_value_node' or member.get('kind') != 'member'
                            or record.get('kind') != 'object'):
                        continue
                    accepted += 1
                    source = {'event_id': event['id'], 'field': field['field'],
                        'document_pointer': '', 'encoding': encoding, 'pointer': pointer,
                        'field_sha256': s._digest(field['value'])}
                    rid = 'g9:r:' + record['id']
                    records[rid] = {'id': rid, 'category': 'payload_record',
                        'payload_node': record['id'], 'event_id': event['id'],
                        'field': field['field'], 'call': call['id'], 'role': role,
                        'ordinal': event['ordinal']}
                    occurrence = {'id': 'g9:o:' + s._digest(source),
                        'category': 'identifier_occurrence', 'record': rid,
                        'member': member['id'], 'payload_node': target, 'source': source,
                        'namespace': namespace, 'value_type': value_type, 'rule_id': rule}
                    # Exact values are transient grouping keys; they are never
                    # copied into an annotation or a rendered value appendix.
                    buckets[(namespace, value_type, value)].append(occurrence)
    occurrences, anchors, edges = [], [], []
    for (namespace, value_type, value), members in buckets.items():
        if len({n['record'] for n in members}) < 2:
            continue
        anchor = {'id': 'g9:j:' + s._digest([namespace, value_type, value]),
            'category': 'identifier_anchor', 'namespace': namespace, 'value_type': value_type}
        anchors.append(anchor)
        occurrences.extend(members)
        if variant == 'record-joins-v1':
            for member in members:
                edge = {'from': member['id'], 'to': anchor['id'],
                    'relation': 'same_typed_identifier_member', 'supports': [deepcopy(member['source'])]}
                edge['id'] = 'g9:x:' + s._digest(edge)
                edges.append(edge)
    active_records = {n['record'] for n in occurrences}
    return {'version': VERSION, 'variant': variant, 'ruleset': s.RULESET,
        'base_g8_sha256': p._digest(base),
        'nodes': [n for rid, n in records.items() if rid in active_records] + occurrences + anchors,
        'edges': edges, 'eligible_occurrence_count': accepted}


def build_record_graph(g8_graph, variant='record-joins-v1'):
    _require_base(g8_graph)
    result = deepcopy(g8_graph)
    result['record_layer'] = _layer(g8_graph, variant)
    return result


def audit_record_graph(graph):
    errors, preserved, nodes, edges = [], False, [], []
    try:
        if not isinstance(graph, dict) or set(graph) != BASE_KEYS | {'record_layer'}:
            raise ValueError('Expected only G9 record inference')
        base = strip_record_graph(graph)
        _require_base(base)
        layer = graph['record_layer']
        nodes, edges = layer['nodes'], layer['edges']
        if any(not isinstance(items, list) or any(not isinstance(n, dict) for n in items)
               for items in (nodes, edges)):
            nodes, edges = [], []
            raise ValueError('Malformed record nodes/edges')
        ids = [n['id'] for n in nodes] + [n['id'] for n in edges]
        if len(ids) != len(set(ids)):
            raise ValueError('Duplicate record node/edge ID')
        known = {n['id'] for n in nodes}
        external = {n['id'] for n in base['payload_layer']['nodes'] + base['evidence_view']['nodes']
                    + base['observed_layer']['nodes']}
        if known & external:
            raise ValueError('Record namespace collision')
        for edge in edges:
            if edge['from'] not in known or edge['to'] not in known:
                raise ValueError('Dangling record edge')
        expected = _layer(base, layer['variant'])
        preserved = layer['base_g8_sha256'] == p._digest(base)
        if p._json(expected) != p._json(layer):
            errors.append('Record membership/source/ownership differs from public-contract reconstruction')
    except (ValueError, KeyError, TypeError, IndexError, AttributeError, RecursionError, OverflowError) as exc:
        errors.append(str(exc))
    counts = {category: sum(n.get('category') == category for n in nodes)
              for category in ('payload_record', 'identifier_occurrence', 'identifier_anchor')}
    return {'ok': not errors, 'errors': errors, 'payload_preserved': preserved,
        'record_count': counts['payload_record'], 'occurrence_count': counts['identifier_occurrence'],
        'anchor_count': counts['identifier_anchor'], 'join_count': counts['identifier_anchor'],
        'edge_count': len(edges), 'active': bool(counts['identifier_anchor'])}


def render_record_segments(graph):
    audit = audit_record_graph(graph)
    if not audit['ok']:
        raise ValueError('Invalid record graph: ' + '; '.join(audit['errors']))
    base = strip_record_graph(graph)
    segments = p.render_payload_segments(base)
    if not audit['active']:
        return segments
    original = ''.join(seg['text'] for seg in segments)
    left, right = p._marker_delimiters(original)
    layer = graph['record_layer']
    records = [n for n in layer['nodes'] if n['category'] == 'payload_record']
    occurrences = [n for n in layer['nodes'] if n['category'] == 'identifier_occurrence']
    anchors = [n for n in layer['nodes'] if n['category'] == 'identifier_anchor']
    aliases = {n['id']: prefix + str(i) for prefix, group in
               (('r', records), ('o', occurrences), ('j', anchors)) for i, n in enumerate(group)}
    payload = {n['id']: n for n in base['payload_layer']['nodes']}
    record_starts = {}
    for record in records:
        node = payload[record['payload_node']]
        while node['kind'] not in ('fragment', 'opaque'):
            node = payload[node['parts'][0]]
        record_starts[node['id']] = record
    occurrences_by_member = {n['member']: n for n in occurrences}
    result = []
    for segment in segments:
        node_id = segment.get('node_id')
        annotation = (record_starts.get(node_id) if segment['kind'] == 'payload_fragment' else
                      occurrences_by_member.get(node_id) if segment['kind'] == 'payload_member_marker' else None)
        if annotation:
            result.append({'kind': 'g9_marker', 'text': left + aliases[annotation['id']] + right,
                           'node_id': annotation['id']})
        result.append(deepcopy(segment))
    lines = ['Identifier links',
        'Links group fields with equal typed identifiers recorded in these tool exchanges.']
    for anchor in anchors:
        members = [aliases[e['from']] for e in layer['edges'] if e['to'] == anchor['id']]
        lines.append(aliases[anchor['id']] + ' ' + anchor['namespace'] +
                     (': ' + ' '.join(members) if members else ''))
    result.append({'kind': 'g9_links', 'text': '\n\n' + '\n'.join(lines)})
    if ''.join(seg['text'] for seg in result if not seg['kind'].startswith('g9_')) != original:
        raise ValueError('Record rendering changed original G8 evidence')
    return result


def render_record_graph(graph):
    return ''.join(seg['text'] for seg in render_record_segments(graph))


def plan_record_projection(graph, *, removed_member_ids):
    audit = audit_record_graph(graph)
    if not audit['ok']:
        raise ValueError('Cannot plan an invalid record graph')
    base = strip_record_graph(graph)
    payload_plan = p.plan_member_projection(base, removed_member_ids=removed_member_ids)
    removed = set(payload_plan['removed_payload_node_ids'])
    # Reconstruct the same supported relations for ablation bookkeeping, without
    # adding these edges or group assignments to the ablated inference object.
    full = _layer(base, 'record-joins-v1')
    by_id = {n['id']: n for n in full['nodes']}
    supported_occurrences = {n['id'] for n in full['nodes'] if n['category'] == 'identifier_occurrence'
        and n['payload_node'] not in removed and n['member'] not in removed
        and by_id[n['record']]['payload_node'] not in removed}
    valid_anchors = {n['id'] for n in full['nodes'] if n['category'] == 'identifier_anchor'
        and len({by_id[e['from']]['record'] for e in full['edges']
                 if e['to'] == n['id'] and e['from'] in supported_occurrences}) >= 2}
    valid_occurrences = {e['from'] for e in full['edges']
                         if e['from'] in supported_occurrences and e['to'] in valid_anchors}
    valid_records = {by_id[n]['record'] for n in valid_occurrences}
    valid_nodes = valid_anchors | valid_occurrences | valid_records
    layer = graph['record_layer']
    valid_edges = {e['id'] for e in layer['edges'] if e['from'] in valid_nodes and e['to'] in valid_nodes}
    return {'version': 'record-member-projection-plan-v1', 'base_graph_sha256': p._digest(graph),
        'removed_member_ids': list(removed_member_ids), 'payload_plan': payload_plan,
        'required_removed_record_node_ids': [n['id'] for n in layer['nodes'] if n['id'] not in valid_nodes],
        'required_removed_record_edge_ids': [e['id'] for e in layer['edges'] if e['id'] not in valid_edges],
        'supported_record_node_ids': [n['id'] for n in layer['nodes'] if n['id'] in valid_nodes],
        'supported_record_edge_ids': [e['id'] for e in layer['edges'] if e['id'] in valid_edges],
        'surviving_join_count': len(valid_anchors), 'requires_source_label_refresh': True,
        'requires_projected_graph_audit': True, 'applied': False, 'task_preservation_certified': False}


def audit_record_projection_plan(graph, plan):
    try:
        expected = plan_record_projection(graph, removed_member_ids=plan['removed_member_ids'])
        if p._json(expected) != p._json(plan):
            raise ValueError('Record projection differs from actual payload/support closure')
        return {'ok': True, 'errors': [], 'applied': False, 'task_preservation_certified': False}
    except (ValueError, KeyError, TypeError, IndexError, AttributeError, RecursionError) as exc:
        return {'ok': False, 'errors': [str(exc)], 'applied': False, 'task_preservation_certified': False}
