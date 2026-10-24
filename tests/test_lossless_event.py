"""Strict payload round trips, including collisions and historical distinctions."""
from copy import deepcopy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from core.lossless_event import VARIANTS, encode, decode
from core.optimized_graph import _same


def sample(method='v2-compact'):
    return {
        'format': 'readable-graph-1', 'method': method,
        'fact_columns': ['subject', 'predicate', 'value', 'version', 'retired_at'],
        'facts': {'f0': ['o1', 'name', 'old', 1, 2],
                  'f1': ['o1', 'name', 'new', 2, None],
                  'f2': ['o2', 'name', 'third', 1, None]},
        'event_columns': ['tool', 'step', 'status', 'rule'],
        'events': {f'a{i}': ['ls', i, 'success', 'bfcl-filesystem-v2.0:ls'] for i in range(20)},
        'object_columns': ['origin', 'first_observed_at'],
        'objects': {'o1': ['observed_object', 1], 'o2': ['observed_object', 2]},
        'relation_columns': ['from', 'relation', 'to', 'event', 'role'],
        'relations': [['a1', 'supports', 'f0', None, None],
                      ['a2', 'retires', 'f0', None, None],
                      ['a2', 'supports', 'f1', None, None]],
        'active_facts': ['f1', 'f2'], 'current_step': 20,
        'type_values': [True, False, 0, 1, 1.0, None, '', [], {}],
        'source_messages': {'m0': ['user', 'first'], 'm1': ['tool', 'second']},
    }


@pytest.mark.parametrize('variant', VARIANTS)
@pytest.mark.parametrize('method', ['v2-compact', 'v2-dedup'])
def test_exact_payload_roundtrip_and_no_mutation(variant, method):
    payload = sample(method)
    original = deepcopy(payload)
    encoded = encode(payload, variant)
    # A wire JSON round-trip must work; no Python-only side channel.
    restored = decode(json.loads(json.dumps(encoded)))
    assert _same(payload, restored)
    assert _same(payload, original)
    assert list(restored['source_messages']) == ['m0', 'm1']
    assert list(restored['facts']) == ['f0', 'f1', 'f2']
    assert len(restored['events']) == 20
    assert restored['facts']['f0'][3:] == [1, 2]
    assert restored['facts']['f1'][3:] == [2, None]


@pytest.mark.parametrize('variant', VARIANTS)
def test_literal_reference_collisions_and_nested_json_strings(variant):
    payload = sample()
    reserved = {'$shared': 'v0', '$literal': {'$json_string': 'compact', 'value': [1]}}
    payload['collision'] = [reserved, {'$shared': 'v0'}, {'$literal': {'a': 'b'}}]
    nested = {'message': 'A "quoted" string ' * 40, 'literal': reserved, 'unicode': '目录'}
    payload['json_strings'] = [json.dumps(nested, ensure_ascii=False),
                               json.dumps(nested, ensure_ascii=False, separators=(',', ':')),
                               '{  "a": 1, "a": 2 }', '{"unterminated"']
    payload['repeated'] = [nested, nested, nested, 'long repeated string ' * 20]
    assert _same(payload, decode(encode(payload, variant)))


def test_schema_defaults_preserve_null_and_missing_and_types():
    payload = sample()
    payload['event_columns'] = ['tool', 'value']
    payload['events'] = {f'a{i}': ['ls', None] for i in range(30)}
    payload['events'].update({'a30': ['ls', False], 'a31': ['ls', 0], 'a32': ['ls', 0.0]})
    payload['unknown_extension'] = {'missing_distinct_from_null': {}}
    encoded = encode(payload)
    assert 'events' in encoded['packed_tables']
    assert _same(payload, decode(encoded))


def test_reject_wrong_method():
    with pytest.raises(ValueError):
        encode({'method': 'v1-compact'})
