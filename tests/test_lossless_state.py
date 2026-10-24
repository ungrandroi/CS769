import json
from pathlib import Path
import pytest
from core.lossless_state import CANDIDATES, encode, decode, _same


def fixture():
    return {'format': 'readable-graph-1', 'method': 'v1-compact',
            'source_messages': {'m0':['user','hello'], 'm1':['tool','text'], 'm2':['user','again']},
            'state_nodes': {f's{i}': {'inherits':f's{i-1}', 'changes':{}, 'same': {'content':'abc'*30}}
                            for i in range(5)},
            'nested': [{'i': i, 'a': None, 'x': True, 'content': ['repeat'*30]} for i in range(8)],
            'types': [None, False, 0, 0.0, [], {}, '', '中文'],
            'collision': {'$ref': 'v0', '$table': {'evil': 'literal'}, '$literal': [1,2]}}


@pytest.mark.parametrize('candidate', CANDIDATES)
def test_exact_decode_and_json_transport(candidate):
    original = fixture()
    encoded = encode(original, candidate)
    transported = json.loads(json.dumps(encoded))
    assert _same(decode(transported), original)
    assert _same(original, fixture())


@pytest.mark.parametrize('candidate', CANDIDATES)
def test_distinct_repeated_calls_and_order(candidate):
    original = fixture()
    original['source_messages'] = {f'm{i}':['function_call', '{}', f'call_{i}', 'ls'] for i in range(20)}
    restored = decode(encode(original, candidate))
    assert list(restored['source_messages']) == list(original['source_messages'])
    assert len(restored['source_messages']) == 20
    assert _same(original, restored)


def test_no_builder_dependency_on_decode():
    import inspect
    assert 'rebuild_original_graph' not in inspect.getsource(decode)


def test_literal_tag_collision_in_repeated_subtree():
    original = fixture()
    original['repeat'] = [{'x': {'$ref':'v0'}, 'content':'repeat'*40} for _ in range(4)]
    for candidate in CANDIDATES:
        assert _same(original, decode(encode(original, candidate)))


def test_seeded_nested_payload_roundtrips():
    import random
    rng = random.Random(107)
    leaves = [None, False, True, 0, 1, 0.0, 1.0, '中文', '$ref', 'v0', 'abc'*30]
    keys = ['alpha', 'beta', 'x', '$ref', '$literal', '$table']
    def node(depth):
        if depth == 0 or rng.random() < .3:
            return rng.choice(leaves)
        if rng.random() < .5:
            return [node(depth-1) for _ in range(rng.randrange(5))]
        return {k: node(depth-1) for k in rng.sample(keys, rng.randrange(5))}
    for _ in range(300):
        payload = {'method':'v1-compact', 'source_messages':{'m0':['user','x'], 'm1':['tool',node(3)]},
                   'states':[node(4) for _ in range(5)]}
        for candidate in CANDIDATES:
            assert _same(payload, decode(json.loads(json.dumps(encode(payload, candidate)))))
