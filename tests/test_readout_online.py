"""Verify online integration keeps the frozen candidate text and five-arm scope."""
import pytest
from core.readout_candidate import prepare
from test_diagnostic_task import fixture
from workflows.diagnostic_task import prepare_replacement, ARMS
from workflows.readout_online import BRANCHES, available_gpu


@pytest.mark.parametrize('method,arm', BRANCHES[1:])
def test_online_candidate_equals_offline_input(method, arm):
    history, source = fixture(method)
    messages, meta = prepare_replacement(history, source, method, arm, len)
    expected, candidate = prepare(history, source, method, event_index=arm == 'readout_compact_index')
    assert messages == expected == meta['replacement_messages']
    assert meta['view'] == candidate['view']
    assert meta['common_rule_tokens'] == 0
    assert meta['graph'] == source['graph'] and meta['encoded'] == source['encoded']
    assert meta['diagnostic']['semantic_editing'] is False


@pytest.mark.parametrize('method', ['state', 'dedup'])
def test_index_not_silently_applied_to_other_methods(method):
    history, source = fixture(method)
    with pytest.raises(ValueError, match='only for Event'):
        prepare_replacement(history, source, method, 'readout_compact_index', len)


def test_old_diagnostic_matrix_unchanged():
    assert len(ARMS) == 6
    assert len(BRANCHES) == 5 and len(set(BRANCHES)) == 5
    assert BRANCHES[0] == ('identity', 'identity_reference')


def test_insufficient_gpu_memory_waits(monkeypatch):
    monkeypatch.setattr('subprocess.check_output', lambda *a, **kw: '0, 7500\n1, 14800\n')
    assert available_gpu(43000)[0] is None


def test_selects_sufficient_card_without_mutation(monkeypatch):
    monkeypatch.setattr('subprocess.check_output', lambda *a, **kw: '0, 47000\n1, 14800\n')
    assert available_gpu(43000)[0] == 0
