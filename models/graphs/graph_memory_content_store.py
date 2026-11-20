"""content storage offline: direct display of existing, uniquely owned payload layer tool content.

Only top-level object members are externalized. This is a render plan, not a
new inference graph, new semantics, compression, native-wire reconstruction,
or a runnable editor. The independent decoder takes only its input string.
"""
from copy import deepcopy
import json
import re

from cs769.models.graphs import graph_memory_evidence as e
from cs769.models.graphs import graph_memory_payload as p
from cs769.models.graphs import graph_memory_records as r
from cs769.models.graphs.graph_memory_observed import strip_observed_graph
from cs769.models.graphs.graph_memory_record_visibility import render_record_visibility_graph

LAYOUT = 'owned-content-store-v1'
OPEN = '<memory_content_graph scope="completed_prior_turns">\n'
LEGEND = ('Prior visible evidence. Events reference records; object shells reference member content. '
          'ordinal is recorded sequence; call_group identifies calls in the same assistant message. '
          'chars counts Unicode characters in the following block.\n')
CLOSE = '</memory_content_graph>\n'


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def _strict_json(text):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError('Duplicate metadata JSON key')
            out[key] = value
        return out
    def invalid(value):
        raise ValueError('Invalid metadata JSON constant')
    return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid)


def _field_sources(graph):
    nodes = {n['id']: n for n in graph['payload_layer']['nodes']}
    fields = {(f['event_id'], f['field']): f for f in graph['payload_layer']['fields']}
    out = {}
    for node in graph['evidence_view']['nodes']:
        for field in node.get('fields', []):
            key = (node['id'], field['field'])
            out[key] = (p._expand(fields[key]['root'], nodes) if key in fields else
                        field['value'] if isinstance(field['value'], str) else p._display(field['value']))
    return out


def build_content_store_plan(graph):
    """Return IDs, source spans and references only; no extra raw content copy."""
    audit = r.audit_record_graph(graph)
    if not audit['ok'] or graph['record_layer']['variant'] != 'record-joins-v1':
        raise ValueError('Expected audited complete evidence graph record inference')
    view = graph['evidence_view']
    if view['version'] != e.EPISODIC_VIEW_VERSION:
        raise ValueError('Only frozen episodic evidence is supported')
    events = {n['id']: n for n in view['nodes']}
    if (not view['recorded_order'] or events[view['recorded_order'][0]]['category'] != 'user_request'
            or events[view['recorded_order'][-1]]['category'] == 'user_request'):
        raise ValueError('Expected completed visible prefix, without a pending current user')
    sources = _field_sources(graph)
    marker = '⟪'
    while any(marker in text for text in sources.values()):
        marker += '|'
    nodes = {n['id']: n for n in graph['payload_layer']['nodes']}
    records, members, field_refs, top_members = [], [], {}, {}
    for meta in graph['payload_layer']['fields']:
        root = nodes[meta['root']]
        value = nodes[root['value']] if root['kind'] == 'document' else root
        rid = 'r' + str(len(records))
        field_refs[(meta['event_id'], meta['field'])] = rid
        record = {'id': rid, 'kind': 'object' if value['kind'] == 'object' else 'dense',
                  'event_id': meta['event_id'], 'field': meta['field'],
                  'source_root': meta['root'], 'source_node': value['id'],
                  'source_kind': meta['source_kind'], 'parse_fallback': meta['parse_fallback'],
                  'span': [0, meta['text_length']], 'parts': []}
        if value['kind'] == 'object':
            pos = 0
            for mid in value['members']:
                member = nodes[mid]
                alias = 'f' + str(len(members))
                if pos < member['span'][0]:
                    record['parts'].append({'kind': 'literal', 'span': [pos, member['span'][0]]})
                record['parts'].append({'kind': 'reference', 'ref': alias})
                item = {'id': alias, 'record': rid, 'event_id': meta['event_id'], 'field': meta['field'],
                        'source_node': mid, 'value_node': member['value'], 'span': member['span'][:],
                        'value_span': nodes[member['value']]['span'][:],
                        'value_kind': nodes[member['value']]['kind']}
                members.append(item)
                top_members[mid] = alias
                pos = member['span'][1]
            if pos < meta['text_length']:
                record['parts'].append({'kind': 'literal', 'span': [pos, meta['text_length']]})
        else:
            record['parts'].append({'kind': 'literal', 'span': record['span'][:]})
        records.append(record)
    record_map = {rec['id']: rec for rec in records}
    group_nodes = {n['id']: n for n in graph['record_layer']['nodes']}
    anchors = [n for n in graph['record_layer']['nodes'] if n['category'] == 'identifier_anchor']
    groups = []
    for anchor in anchors:
        targets = []
        for edge in graph['record_layer']['edges']:
            if edge['to'] != anchor['id']:
                continue
            occurrence = group_nodes[edge['from']]
            mid = occurrence['member']
            if mid in top_members:
                targets.append(top_members[mid])
                continue
            # A nested ID is a non-owning locator within its intact dense owner.
            source = occurrence['source']; key = (source['event_id'], source['field'])
            rec = record_map[field_refs[key]]
            span, value_span = nodes[mid]['span'], nodes[occurrence['payload_node']]['span']
            owner = next((m for m in members if m['record'] == rec['id'] and
                          m['span'][0] <= span[0] and span[1] <= m['span'][1]), rec)
            start = owner['span'][0]
            targets.append({'ref': owner['id'], 'member_span': [x-start for x in span],
                            'value_span': [x-start for x in value_span]})
        groups.append({'id': 'j' + str(len(groups)), 'namespace': anchor['namespace'],
                       'value_type': anchor['value_type'], 'members': targets})
    return {'layout': LAYOUT, 'marker': marker,
            'view_metadata': {k: deepcopy(view[k]) for k in ('version', 'snapshot_boundary', 'provider')},
            'records': records, 'members': members, 'identifier_groups': groups,
            'graph_sha256': p._digest(graph)}


def _render(graph, plan):
    sources = _field_sources(graph)
    segments = [{'kind': 'format', 'text': OPEN + LEGEND}]
    def line(tag, value):
        segments.append({'kind': 'metadata', 'text': tag + ' ' + _json(value) + '\n'})
    def source(key, span, owner):
        segments.append({'kind': 'source', 'text': sources[key][span[0]:span[1]],
                         'event_id': key[0], 'field': key[1], 'span': span[:], 'owner': owner})
    def end_block():
        segments.append({'kind': 'delimiter', 'text': '\n'})
    line('graph', {'layout': LAYOUT, 'marker': plan['marker'], **plan['view_metadata']})
    by_field = {(rec['event_id'], rec['field']): rec for rec in plan['records']}
    for node in graph['evidence_view']['nodes']:
        if node['category'] == 'episode':
            line('episode', node)
            continue
        line('event', {**{k: v for k, v in node.items() if k != 'fields'}, 'field_count': len(node['fields'])})
        for field in node['fields']:
            key = (node['id'], field['field'])
            meta = {'field': field['field'], 'value_type': field['value_type']}
            if key in by_field:
                line('field', {**meta, 'ref': by_field[key]['id']})
            else:
                line('literal', {**meta, 'chars': len(sources[key])})
                source(key, [0, len(sources[key])], node['id'] + '/' + field['field'])
                end_block()
    segments.append({'kind': 'delimiter', 'text': 'CONTENT\n'})
    by_record = {}
    for member in plan['members']:
        by_record.setdefault(member['record'], []).append(member)
    for rec in plan['records']:
        key = (rec['event_id'], rec['field'])
        chars = sum(part['span'][1]-part['span'][0] if part['kind']=='literal' else
                    len(plan['marker'] + part['ref'] + '⟫') for part in rec['parts'])
        line('record', {'id': rec['id'], 'kind': rec['kind'], 'chars': chars})
        for part in rec['parts']:
            if part['kind'] == 'literal':
                source(key, part['span'], rec['id'])
            else:
                segments.append({'kind': 'owner_reference', 'text': plan['marker'] + part['ref'] + '⟫',
                                 'from': rec['id'], 'to': part['ref']})
        end_block()
        for member in by_record.get(rec['id'], []):
            line('member', {'id': member['id'], 'chars': member['span'][1]-member['span'][0]})
            source(key, member['span'], member['id'])
            end_block()
    segments.append({'kind': 'delimiter', 'text': 'IDENTIFIERS\n'})
    for group in plan['identifier_groups']:
        line('join', group)
    segments.append({'kind': 'delimiter', 'text': CLOSE})
    return segments


def render_content_store_segments(graph):
    return _render(graph, build_content_store_plan(graph))


def render_content_store_graph(graph):
    return ''.join(s['text'] for s in render_content_store_segments(graph))


class _Reader:
    def __init__(self, text):
        if not isinstance(text, str):
            raise ValueError('Content store must be text')
        self.text, self.pos = text, 0

    def expect(self, literal):
        if not self.text.startswith(literal, self.pos):
            raise ValueError('Unexpected content-store delimiter')
        self.pos += len(literal)

    def line(self):
        end = self.text.find('\n', self.pos)
        if end == -1:
            raise ValueError('Missing metadata line end')
        text = self.text[self.pos:end]; self.pos = end + 1
        tag, sep, raw = text.partition(' ')
        if not sep:
            raise ValueError('Missing metadata object')
        obj = _strict_json(raw)
        if not isinstance(obj, dict):
            raise ValueError('Metadata must be an object')
        return tag, obj

    def block(self, count):
        if type(count) is not int or count < 0 or self.pos + count > len(self.text):
            raise ValueError('Invalid character count')
        raw = self.text[self.pos:self.pos+count]; self.pos += count
        self.expect('\n')
        return raw


def _keys(obj, expected):
    if set(obj) != set(expected):
        raise ValueError('Unexpected metadata keys')


def _identity(value, prefix):
    if not isinstance(value, str) or not re.fullmatch(prefix + r'(?:0|[1-9][0-9]*)', value):
        raise ValueError('Invalid display node ID')


def _value(raw, kind):
    value = raw if kind == 'str' else json.loads(raw)
    if type(value).__name__ != kind:
        raise ValueError('Source value type mismatch')
    return value


def _member_value(raw, span=None, value_span=None):
    # Parse only for validation of source locations, never to rewrite raw text.
    root, tree, failure = p._parse('{' + raw + '}', 'decode:')
    if failure:
        raise ValueError('Member does not contain exactly one valid source member')
    nodes = {n['id']: n for n in tree}; obj = nodes[nodes[root]['value']]
    if len(obj['members']) != 1:
        raise ValueError('Member contains multiple top-level members')
    member = nodes[obj['members'][0]]
    if member['span'] != [1, len(raw)+1]:
        raise ValueError('Member boundary includes non-member source characters')
    if span is not None:
        member = next((n for n in tree if n['kind']=='member' and n['span']==[x+1 for x in span]), None)
        if member is None or nodes[member['value']]['span'] != [x+1 for x in value_span]:
            raise ValueError('Dense member locator is not a CST member/value')
    return json.loads(p._expand(member['value'], nodes))


def decode_content_store_graph(text):
    """Independently decode the actual body; never reads canonical graph/files.

    The return is visible evidence and presentation/source-location metadata,
    not a reconstructed provider-native tool wire or an edited inference graph.
    """
    reader = _Reader(text); reader.expect(OPEN); reader.expect(LEGEND)
    tag, meta = reader.line()
    _keys(meta, ('layout','marker','version','snapshot_boundary','provider'))
    if (tag != 'graph' or meta['layout'] != LAYOUT or meta['version'] != e.EPISODIC_VIEW_VERSION or
            meta['provider'] not in ('openai','anthropic') or
            meta['snapshot_boundary'] not in ('end_of_first_user_turn','archived_history_checkpoint') or
            not isinstance(meta['marker'], str) or not re.fullmatch('⟪[|]*', meta['marker'])):
        raise ValueError('Unsupported graph metadata')
    nodes, refs = [], []
    while not reader.text.startswith('CONTENT\n', reader.pos):
        tag, node = reader.line()
        if tag == 'episode':
            _keys(node, ('id','category','turn'))
            nodes.append(node)
            continue
        if tag != 'event' or type(node.get('field_count')) is not int or node['field_count'] < 1:
            raise ValueError('Expected nonempty event')
        node = deepcopy(node); count = node.pop('field_count'); fields = []
        for _ in range(count):
            field_tag, field = reader.line()
            if field_tag == 'literal':
                _keys(field, ('field','value_type','chars'))
                raw = reader.block(field['chars'])
                fields.append({'field':field['field'],'value_type':field['value_type'],
                               'value':_value(raw,field['value_type'])})
            elif field_tag == 'field':
                _keys(field, ('field','value_type','ref')); _identity(field['ref'], 'r')
                fields.append({'field':field['field'],'value_type':field['value_type'],'ref':field['ref']})
                refs.append((node['id'], fields[-1]))
            else:
                raise ValueError('Unexpected event field block')
        node['fields'] = fields; nodes.append(node)
    reader.expect('CONTENT\n')
    owners = {}
    while not reader.text.startswith('IDENTIFIERS\n', reader.pos):
        tag, node = reader.line()
        if tag == 'record':
            _keys(node, ('id','kind','chars')); _identity(node['id'], 'r')
            if node['kind'] not in ('object','dense'):
                raise ValueError('Unknown record representation')
        elif tag == 'member':
            _keys(node, ('id','chars')); _identity(node['id'], 'f'); node['kind'] = 'member'
        else:
            raise ValueError('Unexpected content owner')
        if node['id'] in owners:
            raise ValueError('Duplicate content owner ID')
        owners[node['id']] = {**node, 'raw':reader.block(node['chars'])}
    reader.expect('IDENTIFIERS\n')
    groups = []
    while not reader.text.startswith(CLOSE, reader.pos):
        tag, group = reader.line(); _keys(group, ('id','namespace','value_type','members'))
        _identity(group['id'], 'j')
        if tag != 'join' or group['id'] != 'j'+str(len(groups)) or not isinstance(group['members'], list):
            raise ValueError('Invalid identifier group')
        if not isinstance(group['namespace'], str) or group['value_type'] not in ('str','int'):
            raise ValueError('Invalid identifier type or namespace')
        groups.append(group)
    reader.expect(CLOSE)
    if reader.pos != len(text):
        raise ValueError('Extra trailing content')
    used, locations, expanded = set(), {}, {}
    for event_id, field in refs:
        rid = field['ref']; rec = owners.get(rid)
        if rec is None or rec['kind'] not in ('object','dense') or rid in used:
            raise ValueError('Missing or multiply owned record')
        used.add(rid); raw = rec['raw']; chunks, intervals, shell_spans = [], [], []
        source_pos, cursor = 0, 0
        if rec['kind'] == 'dense':
            chunks = [raw]; source_pos = len(raw); shell_spans = [[0,len(raw)]]
        else:
            while cursor < len(raw):
                start = raw.find(meta['marker'], cursor)
                if start < 0:
                    start = len(raw)
                literal = raw[cursor:start]; chunks.append(literal)
                if literal:
                    shell_spans.append([source_pos, source_pos+len(literal)]); source_pos += len(literal)
                if start == len(raw):
                    break
                stop = raw.find('⟫', start+len(meta['marker']))
                if stop < 0:
                    raise ValueError('Unterminated shell reference')
                mid = raw[start+len(meta['marker']):stop]; _identity(mid, 'f')
                member = owners.get(mid)
                if member is None or member['kind'] != 'member' or mid in used:
                    raise ValueError('Dangling, cyclic or multiply owned shell reference')
                used.add(mid); _member_value(member['raw'])
                span = [source_pos, source_pos+len(member['raw'])]
                intervals.append(span); chunks.append(member['raw']); source_pos = span[1]
                locations[mid] = {'kind':'member','record':rid,'event_id':event_id,'field':field['field'],
                                  'owned_spans':[span]}
                cursor = stop+1
        value_text = ''.join(chunks)
        if rec['kind'] == 'object':
            root, tree, failure = p._parse(value_text, 'decode:')
            by_id = {n['id']:n for n in tree}
            obj = by_id.get(by_id[root].get('value'), {})
            if failure or obj.get('kind') != 'object' or [by_id[m]['span'] for m in obj['members']] != intervals:
                raise ValueError('Shell/member boundaries do not partition a source object')
        locations[rid] = {'kind':rec['kind'],'event_id':event_id,'field':field['field'],
                          'owned_spans':shell_spans}
        expanded[rid] = value_text
        field['value'] = _value(value_text,field['value_type']); del field['ref']
    if used != set(owners):
        raise ValueError('Orphan content owner')
    # Rebuild the already-declared chronological edges without reading old graph.
    order, edges = [], []
    for node in nodes:
        if node['category'] == 'episode':
            continue
        for field in node['fields']:
            needs_record = p._is_tool_field(node, field)
            was_ref = (node['id'],field['field']) in {(k,f['field']) for k,f in refs}
            if needs_record != was_ref:
                raise ValueError('Tool fields must have unique record references')
        if node['category'] == 'tool_result':
            edges.append({'from':node['id'],'relation':'result_of','to':node['result_of']})
        edges.append({'from':node['id'],'relation':'in_turn','to':node['episode']})
        if order:
            edges.append({'from':order[-1],'relation':'precedes','to':node['id']})
        order.append(node['id'])
    view = {k:meta[k] for k in ('version','snapshot_boundary','provider')}
    view.update(nodes=nodes,edges=edges,recorded_order=order,fact_order=[])
    e._audit_episodic_view(view)
    events = {n['id']:n for n in nodes}
    if not order or events[order[0]]['category']!='user_request' or events[order[-1]]['category']=='user_request':
        raise ValueError('Expected a completed visible prefix')
    for group in groups:
        values, records, seen = [], set(), set()
        for target in group['members']:
            key = _json(target)
            if key in seen:
                raise ValueError('Duplicate identifier occurrence')
            seen.add(key)
            if isinstance(target, str):
                node = owners.get(target)
                if node is None or node['kind'] != 'member':
                    raise ValueError('Identifier must refer to a real member owner')
                value = _member_value(node['raw']); owner = target
            else:
                if not isinstance(target, dict):
                    raise ValueError('Invalid dense locator')
                _keys(target, ('ref','member_span','value_span')); owner = target['ref']
                node = owners.get(owner)
                if node is None or node['kind'] not in ('member','dense'):
                    raise ValueError('Invalid dense locator owner')
                for name in ('member_span','value_span'):
                    span = target[name]
                    if (not isinstance(span,list) or len(span)!=2 or any(type(x)is not int for x in span)
                            or not 0 <= span[0] < span[1] <= len(node['raw'])):
                        raise ValueError('Invalid dense locator span')
                if node['kind'] == 'member':
                    value = _member_value(node['raw'], target['member_span'], target['value_span'])
                else:
                    root, tree, failure = p._parse(node['raw'], 'decode:')
                    ns = {n['id']:n for n in tree}
                    match = next((n for n in tree if n['kind']=='member' and n['span']==target['member_span']),None)
                    if failure or match is None or ns[match['value']]['span'] != target['value_span']:
                        raise ValueError('Dense locator is not a CST member/value')
                    value = json.loads(p._expand(match['value'],ns))
            if type(value).__name__ != group['value_type']:
                raise ValueError('Identifier value type differs')
            values.append(value); records.add(locations[owner].get('record',owner))
        if len(records)<2 or not values or any(type(v)is not type(values[0]) or v!=values[0] for v in values):
            raise ValueError('Identifier group lacks matching distinct records')
    return {'layout':LAYOUT,'evidence_view':view,'identifier_groups':groups,'ownership':locations}


def audit_content_store_render(graph, *, rendered_text=None):
    """Compare independent body decoding and typed coverage with canonical evidence graph."""
    result = {'ok':False,'errors':[],'layout':LAYOUT,'payload_preserved':False,
              'unique_leaf_coverage':False,'independent_decode_exact':False}
    try:
        before = p._digest(graph); plan = build_content_store_plan(graph)
        segments = _render(graph,plan); expected = ''.join(s['text'] for s in segments)
        body = expected if rendered_text is None else rendered_text
        decoded = decode_content_store_graph(body)
        canonical = strip_observed_graph(p.restore_observed_graph(r.strip_record_graph(graph)))
        exact = (decoded['evidence_view']==canonical['evidence_view'] and
                 p._digest(decoded['evidence_view'])==p._digest(canonical['evidence_view']))
        if not exact or decoded['identifier_groups'] != plan['identifier_groups']:
            raise ValueError('Independent decoding differs from complete canonical evidence/relations')
        if body != expected:
            raise ValueError('Body differs from frozen deterministic content-store rendering')
        sources = _field_sources(graph); intervals = {key:[] for key in sources}
        for seg in segments:
            if seg['kind']=='source':
                intervals[(seg['event_id'],seg['field'])].append((seg['span'],seg['text'],seg['owner']))
        for key,raw in sources.items():
            pieces = sorted(intervals[key],key=lambda x:x[0]); pos = 0; chunks = []
            for span,text,_ in pieces:
                if span != [pos,pos+len(text)] or text != raw[span[0]:span[1]]:
                    raise ValueError('Source spans overlap, omit or alter characters')
                pos=span[1];chunks.append(text)
            if pos!=len(raw) or ''.join(chunks)!=raw:
                raise ValueError('Source field is incompletely owned')
        by_id={n['id']:n for n in graph['payload_layer']['nodes']}; leaf_count=0
        for field in graph['payload_layer']['fields']:
            pieces=intervals[(field['event_id'],field['field'])]
            def check(identity):
                nonlocal leaf_count
                n=by_id[identity]
                if n['kind'] in ('fragment','opaque'):
                    hits=[span for span,_,_ in pieces if span[0]<=n['span'][0] and n['span'][1]<=span[1]]
                    if len(hits)!=1:raise ValueError('CST leaf has missing or multiple display owners')
                    leaf_count+=1
                else:
                    for child in n['parts']:check(child)
            check(field['root'])
        baseline=render_record_visibility_graph(graph,visible_observations=False)
        result.update(ok=True,payload_preserved=True,unique_leaf_coverage=True,independent_decode_exact=True,
            input_graph_unchanged=p._digest(graph)==before,field_count=len(plan['records']),
            member_count=len(plan['members']),dense_field_count=sum(x['kind']=='dense' for x in plan['records']),
            dense_container_member_count=sum(x['value_kind'] in ('object','array') for x in plan['members']),
            record_count=len(plan['records']),source_field_count=len(sources),source_characters=sum(map(len,sources.values())),
            covered_leaf_count=leaf_count,identifier_group_count=len(plan['identifier_groups']),
            identifier_target_count=sum(len(g['members']) for g in plan['identifier_groups']),
            dense_identifier_locator_count=sum(isinstance(t,dict) for g in plan['identifier_groups'] for t in g['members']),
            characters=len(body),added_characters=len(body)-len(baseline),baseline_characters=len(baseline),
            formatting_characters=len(body)-sum(map(len,sources.values())),maximum_explicit_owner_hops=2,
            exact_previous_body=body==baseline,graph_sha256=before,body_sha256=p._text_digest(body))
    except (ValueError,KeyError,TypeError,IndexError,AttributeError,RecursionError,OverflowError) as exc:
        result['errors'].append(str(exc))
    return result
