"""Lossless, self-described storage codecs for delivered state-transition payloads.

No builder is called while decoding: the input JSON payload is restored directly.
Original-history/full-builder checks are additional checks, not the losslessness claim.
"""
from collections import Counter
from copy import deepcopy
import json

CANDIDATES = ('state-tables-v1', 'state-shared-v1', 'state-columnar-v1')
TABLE_RULE = ('A $table stores its original list or object: each row maps columns to values, '
              'with defaults added; keys name object rows. $literal is unchanged original data.')
SHARED_RULE = (' $ref substitutes the exact value in shared_values; references do not merge events or states.')
MESSAGE_RULE = (' source_message_tables groups source_messages by schema; each row is [message_id, '
                'original row values after schema]. source_message_order restores original ordering.')
TAGS = {'$table', '$literal', '$ref'}


def dumps(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def _same(a, b):
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(_same(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    return a == b


def _table(value):
    """Recursively replace repeated dictionaries by self-described exact tables."""
    if isinstance(value, dict) and TAGS.intersection(value):
        return {'$literal': deepcopy(value)}
    if not isinstance(value, (list, dict)):
        return deepcopy(value)
    rows = list(value.values()) if isinstance(value, dict) else value
    ordinary = ({k: _table(v) for k, v in value.items()} if isinstance(value, dict)
                else [_table(v) for v in value])
    if len(rows) < 3 or not all(isinstance(row, dict) for row in rows):
        return ordinary
    columns = list(rows[0])
    if any(set(row) != set(columns) or TAGS.intersection(row) for row in rows):
        return ordinary
    defaults = {key: deepcopy(rows[0][key]) for key in columns
                if all(_same(row[key], rows[0][key]) for row in rows[1:])}
    varying = [key for key in columns if key not in defaults]
    descriptor = {'columns': varying, 'defaults': _table(defaults),
                  'rows': [[_table(row[key]) for key in varying] for row in rows]}
    if isinstance(value, dict):
        descriptor['keys'] = list(value)
    encoded = {'$table': descriptor}
    return encoded if len(dumps(encoded)) + 20 < len(dumps(ordinary)) else ordinary


def _untable(value):
    if isinstance(value, list):
        return [_untable(v) for v in value]
    if not isinstance(value, dict):
        return deepcopy(value)
    if '$literal' in value:
        if set(value) != {'$literal'}:
            raise ValueError('Malformed literal escape')
        return deepcopy(value['$literal'])
    if '$table' in value:
        if set(value) != {'$table'}:
            raise ValueError('Malformed table')
        table = value['$table']
        columns = table['columns']
        defaults = _untable(table['defaults'])
        if len(set(columns)) != len(columns) or set(columns).intersection(defaults):
            raise ValueError('Duplicate table fields')
        rows = []
        for values in table['rows']:
            if len(values) != len(columns):
                raise ValueError('Malformed table row')
            rows.append({**deepcopy(defaults), **dict(zip(columns, [_untable(v) for v in values]))})
        if 'keys' not in table:
            return rows
        if len(table['keys']) != len(rows) or len(set(table['keys'])) != len(rows):
            raise ValueError('Malformed table row keys')
        return dict(zip(table['keys'], rows))
    return {key: _untable(v) for key, v in value.items()}


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _shared(value):
    """Intern exact repeated subtrees, retaining an in-band readable dictionary."""
    counts, objects = Counter(), {}
    def collect(node):
        raw = _canonical(node)
        if isinstance(node, (dict, list, str)) and len(raw) >= 40:
            counts[raw] += 1
            objects[raw] = node
        if isinstance(node, dict) and set(node) == {'$literal'}:
            return
        if isinstance(node, dict):
            for child in node.values(): collect(child)
        elif isinstance(node, list):
            for child in node: collect(child)
    collect(value)
    eligible = [raw for raw, count in counts.items() if count >= 2
                and (len(raw) - 17) * (count - 1) > 50]
    eligible.sort(key=lambda raw: (-len(raw), raw))
    ids = {raw: f'v{i}' for i, raw in enumerate(eligible)}
    used = set()
    def pack(node):
        raw = _canonical(node)
        if raw in ids:
            used.add(raw)
            return {'$ref': ids[raw]}
        if isinstance(node, dict) and set(node) == {'$literal'}: return deepcopy(node)
        if isinstance(node, dict): return {key: pack(v) for key, v in node.items()}
        if isinstance(node, list): return [pack(v) for v in node]
        return deepcopy(node)
    packed = pack(value)
    shared = {ids[raw]: deepcopy(objects[raw]) for raw in eligible if raw in used}
    return packed, shared


def _unshare(value, shared):
    if isinstance(value, list): return [_unshare(v, shared) for v in value]
    if not isinstance(value, dict): return deepcopy(value)
    if set(value) == {'$literal'}: return deepcopy(value)
    if set(value) == {'$ref'}:
        # Dictionary values are literal encoded subtrees, never recursively interned.
        return deepcopy(shared[value['$ref']])
    return {key: _unshare(v, shared) for key, v in value.items()}


def _columnar(payload):
    """Factor repeated message schema identifiers while preserving source ordering."""
    result = deepcopy(payload)
    if 'source_message_tables' in result or 'source_message_order' in result:
        raise ValueError('Reserved columnar keys already exist')
    messages = result.pop('source_messages')
    grouped = {}
    for message_id, row in messages.items():
        grouped.setdefault(row[0], []).append([message_id, *deepcopy(row[1:])])
    result['source_message_tables'] = grouped
    result['source_message_order'] = list(messages)
    return result


def encode(payload, candidate='state-tables-v1'):
    """Encode full baseline delivered JSON; all dictionaries/rules are in-band."""
    if candidate not in CANDIDATES:
        raise ValueError(f'Unknown candidate: {candidate}')
    if payload.get('method') != 'v1-compact':
        raise ValueError('This codec is only for State-Transition Graph')
    source = _columnar(payload) if candidate == 'state-columnar-v1' else payload
    encoded = {'encoding': candidate, 'decoding': TABLE_RULE, 'payload': _table(source)}
    if candidate != 'state-tables-v1':
        encoded['payload'], encoded['shared_values'] = _shared(encoded['payload'])
        encoded['decoding'] += SHARED_RULE
    if candidate == 'state-columnar-v1':
        encoded['decoding'] += MESSAGE_RULE
    if not _same(decode(encoded), payload):
        raise AssertionError('Direct delivered payload restoration failed')
    return encoded


def decode(encoded):
    candidate = encoded['encoding']
    if candidate not in CANDIDATES:
        raise ValueError(f'Unknown candidate: {candidate}')
    payload = encoded['payload']
    if candidate != 'state-tables-v1':
        payload = _unshare(payload, encoded['shared_values'])
    payload = _untable(payload)
    if candidate == 'state-columnar-v1':
        messages = {}
        for schema, rows in payload.pop('source_message_tables').items():
            for row in rows:
                if row[0] in messages:
                    raise ValueError('Duplicate source message')
                messages[row[0]] = [schema, *deepcopy(row[1:])]
        order = payload.pop('source_message_order')
        if len(order) != len(messages) or set(order) != set(messages):
            raise ValueError('Invalid source ordering')
        payload['source_messages'] = {key: messages[key] for key in order}
    return payload


def build_memory(history, method, explanation, count, candidate='state-tables-v1'):
    """Runner-compatible wrapper. All codec rules count as delivered graph tokens."""
    from core.optimized_graph import build_memory as baseline, restore_history, rebuild_original_graph
    _, metadata = baseline(history, method, explanation, count)
    original = metadata['graph']
    encoded = encode(original, candidate)
    restored = decode(encoded)
    body = dumps(encoded)
    instruction = metadata['instruction']
    text = instruction + '\n' + body if instruction else body
    metadata.update({'candidate': candidate, 'baseline_graph': original, 'graph': encoded,
                     'body': body, 'body_tokens': count(body), 'graph_tokens': count(body),
                     'total_tokens': count(text), 'codec_rules_tokens': count(encoded['decoding']),
                     'baseline_body_tokens': count(dumps(original))})
    metadata['reconstruction_audit'].update({
        'delivered_payload_direct_exact': _same(original, restored),
        'history_exact': _same(restore_history(original), restore_history(restored)),
        'original_graph_rebuilt_exact': _same(rebuild_original_graph(original), rebuild_original_graph(restored)),
        'kind': 'direct JSON payload decode; additional history and builder checks',
        'external_dictionary': False, 'semantic_editing': False})
    return text, metadata
