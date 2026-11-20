"""Strict payload codecs for Event Graph and Event Graph-Dedup.

No facts, events or relations are merged. Named defaults and shared values change
storage only. Decoding never calls a graph builder. All reference/default rules
are included in the model-visible envelope, not an external prompt dictionary.
"""
from collections import Counter
from copy import deepcopy
import json

VARIANTS = ('tables-v1', 'shared-v1', 'source-json-v1')
TABLE_RULE = ('Tables retain original column order. Each row supplies row_columns; '
              'column_defaults supply other columns, with row_overrides taking precedence. '
              'Row IDs and order are unchanged.')
SHARED_RULE = ('An object containing only $shared is a reference into shared_values. '
               '$literal escapes an original object with a reserved key.')
JSON_RULE = ('An object with $json_string and value represents an original JSON string: '
             'compact uses separators comma/colon; spaced uses comma-space/colon-space; '
             'unicode is unescaped. $literal escapes an original reserved object.')
TABLES = {'objects': 'object_columns', 'facts': 'fact_columns',
          'events': 'event_columns', 'relations': 'relation_columns'}
RESERVED = {'$shared', '$literal', '$json_string'}


def dumps(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def _key(value):
    # JSON spelling keeps False/0, 1/1.0 and ordered sequences distinct.
    return dumps(value)


def _table_pack(rows, columns):
    mapping = isinstance(rows, dict)
    keys = list(rows) if mapping else list(range(len(rows)))
    original = [deepcopy(rows[k]) for k in keys]
    if not original or any(type(row) is not list or len(row) != len(columns) for row in original):
        return None
    selected = {}

    def render(defaults):
        kept = [i for i in range(len(columns)) if i not in defaults]
        result = {'row_columns': [columns[i] for i in kept],
                  'column_defaults': {columns[i]: deepcopy(defaults[i]) for i in defaults}}
        values = [[row[i] for i in kept] for row in original]
        result['rows'] = dict(zip(keys, values)) if mapping else values
        exceptions = {}
        for key, row in zip(keys, original):
            changed = {columns[i]: deepcopy(row[i]) for i in defaults
                       if _key(row[i]) != _key(defaults[i])}
            if changed:
                exceptions[str(key)] = changed
        if exceptions:
            result['row_overrides'] = exceptions
        return result

    current = render(selected)
    # Sparse defaults let null retirement fields disappear while preserving every
    # exceptional historical version explicitly. Never infer a semantic default.
    for index in range(len(columns)):
        counts = Counter(_key(row[index]) for row in original)
        spelling, count = counts.most_common(1)[0]
        if count < 2:
            continue
        trial = {**selected, index: json.loads(spelling)}
        candidate = render(trial)
        if len(dumps(candidate)) < len(dumps(current)):
            selected, current = trial, candidate
    return current if len(dumps(current)) < len(dumps(rows)) else None


def _table_unpack(packed, columns):
    rows = packed['rows']
    mapping = isinstance(rows, dict)
    keys = list(rows) if mapping else list(range(len(rows)))
    restored = []
    for key in keys:
        values = deepcopy(packed['column_defaults'])
        values.update(zip(packed['row_columns'], deepcopy(rows[key])))
        values.update(deepcopy(packed.get('row_overrides', {}).get(str(key), {})))
        restored.append([values[column] for column in columns])
    return dict(zip(keys, restored)) if mapping else restored


def _json_strings(value, reverse=False):
    if reverse:
        if isinstance(value, dict):
            if set(value) == {'$literal'}:
                return {k: _json_strings(v, True) for k, v in value['$literal'].items()}
            if set(value) == {'$json_string', 'value'}:
                separators = (',', ':') if value['$json_string'] == 'compact' else (', ', ': ')
                return json.dumps(_json_strings(value['value'], True), ensure_ascii=False,
                                  separators=separators, allow_nan=False)
            return {k: _json_strings(v, True) for k, v in value.items()}
        if isinstance(value, list):
            return [_json_strings(item, True) for item in value]
        return deepcopy(value)
    if isinstance(value, dict):
        content = {k: _json_strings(v) for k, v in value.items()}
        return {'$literal': content} if RESERVED.intersection(value) else content
    if isinstance(value, list):
        return [_json_strings(item) for item in value]
    if isinstance(value, str) and len(value) >= 64 and value[:1] in '{[':
        try:
            parsed = json.loads(value)
        except (ValueError, TypeError):
            return value
        for name, separators in [('compact', (',', ':')), ('spaced', (', ', ': '))]:
            if json.dumps(parsed, ensure_ascii=False, separators=separators, allow_nan=False) == value:
                candidate = {'$json_string': name, 'value': _json_strings(parsed)}
                # Only eliminate actual escaping overhead, no approximate parsing.
                if len(dumps(candidate)) < len(dumps(value)):
                    return candidate
    return deepcopy(value)


def _share(value):
    counts, samples = Counter(), {}

    def scan(item):
        if isinstance(item, (str, list, dict)):
            spelling = _key(item)
            if len(spelling) >= 24:
                counts[spelling] += 1
                samples[spelling] = item
        if isinstance(item, dict):
            for child in item.values():
                scan(child)
        elif isinstance(item, list):
            for child in item:
                scan(child)
    scan(value)
    # Long repeated values first, then recompute uses after parent substitutions.
    candidates = sorted((s for s, n in counts.items() if n >= 2),
                        key=lambda s: -(len(s) * (counts[s] - 1)))
    selected = {}

    def apply(item, active, usage=None):
        spelling = _key(item)
        if spelling in active:
            identity = active[spelling]
            if usage is not None:
                usage[identity] += 1
            return {'$shared': identity}
        if isinstance(item, dict):
            content = {k: apply(v, active, usage) for k, v in item.items()}
            return {'$literal': content} if RESERVED.intersection(item) else content
        if isinstance(item, list):
            return [apply(child, active, usage) for child in item]
        return deepcopy(item)

    base = apply(value, {})
    current_size = len(dumps({'graph': base, 'shared_values': {}}))
    for spelling in candidates:
        trial = {**selected, spelling: f'v{len(selected)}'}
        usage = Counter()
        changed = apply(value, trial, usage)
        if usage[trial[spelling]] < 2:
            continue
        dictionary = {identity: deepcopy(samples[s]) for s, identity in trial.items()}
        size = len(dumps({'graph': changed, 'shared_values': dictionary}))
        if size < current_size:
            selected, current_size = trial, size
    dictionary = {identity: deepcopy(samples[s]) for s, identity in selected.items()}
    # Dictionary values are literal original values, not recursively encoded.
    return apply(value, selected), dictionary


def _unshare(value, dictionary):
    if isinstance(value, dict):
        if set(value) == {'$shared'}:
            return deepcopy(dictionary[value['$shared']])
        if set(value) == {'$literal'}:
            return {k: _unshare(v, dictionary) for k, v in value['$literal'].items()}
        return {k: _unshare(v, dictionary) for k, v in value.items()}
    if isinstance(value, list):
        return [_unshare(child, dictionary) for child in value]
    return deepcopy(value)


def encode(payload, variant='tables-v1'):
    if variant not in VARIANTS:
        raise ValueError(f'Unknown variant: {variant}')
    if payload.get('method') not in ('v2-compact', 'v2-dedup'):
        raise ValueError('Expected an Event Graph or Event Graph-Dedup payload')
    graph = deepcopy(payload)
    packed_tables = []
    for name, column_key in TABLES.items():
        if name not in graph or column_key not in graph:
            continue
        packed = _table_pack(graph[name], graph[column_key])
        if packed is not None:
            graph[name] = packed
            packed_tables.append(name)
    result = {'encoding': 'lossless-event/' + variant, 'table_rule': TABLE_RULE,
              'packed_tables': packed_tables}
    if variant == 'source-json-v1':
        graph = _json_strings(graph)
        result['json_string_rule'] = JSON_RULE
    if variant in ('shared-v1', 'source-json-v1'):
        graph, dictionary = _share(graph)
        result['shared_rule'] = SHARED_RULE + ' Values in shared_values are literal, not encoded.'
        result['shared_values'] = dictionary
    result['graph'] = graph
    return result


def decode(encoded):
    variant = encoded['encoding'].removeprefix('lossless-event/')
    if variant not in VARIANTS:
        raise ValueError('Unknown encoding')
    graph = deepcopy(encoded['graph'])
    if variant in ('shared-v1', 'source-json-v1'):
        graph = _unshare(graph, encoded['shared_values'])
    if variant == 'source-json-v1':
        graph = _json_strings(graph, True)
    for name in encoded['packed_tables']:
        graph[name] = _table_unpack(graph[name], graph[TABLES[name]])
    return graph
