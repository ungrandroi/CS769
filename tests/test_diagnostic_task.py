"""Lossless, common-rule controls for the live diagnostic runner's pure input path."""
from copy import deepcopy

import pytest

from core import lossless_event, lossless_state, optimized_graph
from workflows.diagnostic_task import (ARMS, INDEX_RULE, REF_RULE, _action_metrics,
                                       prepare_replacement, prepare_identity_passthrough,
                                       validate_arm_selection)


def fixture(method):
    history = [{"role": "system", "content": "fixed instruction"},
               {"role": "user", "content": '\n Move "a\\b". Keep completed work. \n'},
               {"type": "function_call", "call_id": "c1", "name": "ls", "arguments": "{}"},
               {"type": "function_call_output", "call_id": "c1", "output": '{"names":["a"]}'}]
    working = history[1:]
    packed, defaults, columns = optimized_graph._pack_messages(working)
    graph = {"method": {"state": "v1-compact", "event": "v2-compact", "dedup": "v2-dedup"}[method],
             "source_messages": packed, "message_defaults_by_type": defaults,
             "source_message_columns": columns, "repeat": ["long identical value " * 20] * 4}
    if method == "state":
        graph.update(current_state="s0", state_nodes={"s0": {"cwd": {"value": None}, "objects": []}})
        encoded = lossless_state.encode(graph, "state-shared-v1")
    else:
        graph.update(fact_columns=["subject", "predicate", "value", "key", "retired_at", "fact_scope"],
                     facts={"f1": ["o1", "name", "a", None, None, "state"]}, active_facts=["f1"])
        encoded = lossless_event.encode(graph, "tables-v1" if method == "event" else "shared-v1")
    return history, {"graph": graph, "encoded": encoded, "builder_sha256": {"frozen": "unchanged"}}


@pytest.mark.parametrize("method", ["state", "event", "dedup"])
@pytest.mark.parametrize("arm", ARMS)
def test_prepare_preserves_typed_graph_history_and_sources(method, arm, monkeypatch):
    history, source = fixture(method)
    before = deepcopy((history, source))
    def forbidden(*args, **kwargs):
        raise AssertionError("A diagnostic must not rebuild the semantic graph")
    monkeypatch.setattr(optimized_graph, "build_memory", forbidden)
    monkeypatch.setattr(optimized_graph, "rebuild_original_graph", forbidden)
    messages, meta = prepare_replacement(history, source, method, arm, len)
    codec = lossless_state if method == "state" else lossless_event
    assert optimized_graph._same(codec.decode(meta["encoded"]), source["graph"])
    assert optimized_graph._same(optimized_graph.restore_history(meta["graph"]), history[1:])
    assert (history, source) == before
    assert messages == meta["replacement_messages"]
    assert messages[0]["content"].startswith(optimized_graph.MINIMAL + "\n")
    assert meta["instruction"] == optimized_graph.MINIMAL
    assert meta["adapter_rebuilt"] is False
    assert meta["payload_decode_exact"] and meta["source_history_exact"]
    assert all(m["role"] == "user" for m in messages)


@pytest.mark.parametrize("method", ["state", "event", "dedup"])
def test_goal_views_have_identical_text_and_fixed_payload(method):
    history, source = fixture(method)
    inline, im = prepare_replacement(history, source, method, "goal_inline", len)
    separate, sm = prepare_replacement(history, source, method, "goal_separate", len)
    assert inline[0]["content"] == separate[0]["content"] + separate[1]["content"]
    assert im["encoded"] == sm["encoded"] == source["encoded"]
    assert im["diagnostic"]["goal_view"] == sm["diagnostic"]["goal_view"]
    assert im["common_diagnostic_rule"] == sm["common_diagnostic_rule"] == ""


def test_index_pair_shares_rules_and_only_adds_reference_view():
    history, source = fixture("event")
    control, cm = prepare_replacement(history, source, "event", "index_control", len)
    view, vm = prepare_replacement(history, source, "event", "index_view", len)
    assert cm["common_diagnostic_rule"] == vm["common_diagnostic_rule"] == INDEX_RULE
    assert cm["encoded"] == vm["encoded"]
    assert view[0]["content"] == control[0]["content"] + "\n" + optimized_graph.dumps(vm["view"])
    assert vm["diagnostic"]["eligible_entries"] == 1


def test_index_empty_negative_control_remains_identical():
    history, source = fixture("event")
    source["graph"]["facts"]["f1"][-1] = "observation"
    source["encoded"] = lossless_event.encode(source["graph"], "tables-v1")
    control, cm = prepare_replacement(history, source, "event", "index_control", len)
    view, vm = prepare_replacement(history, source, "event", "index_view", len)
    assert control == view
    assert cm["diagnostic"]["eligible_entries"] == vm["diagnostic"]["eligible_entries"] == 0


@pytest.mark.parametrize("method", ["state", "event", "dedup"])
def test_refs_pair_same_rules_and_codec_and_event_negative_control(method):
    history, source = fixture(method)
    control, cm = prepare_replacement(history, source, method, "refs_control", len)
    expanded, em = prepare_replacement(history, source, method, "refs_expanded", len)
    assert cm["common_diagnostic_rule"] == em["common_diagnostic_rule"] == REF_RULE
    assert cm["encoded"] == source["encoded"]
    assert cm["encoded"]["encoding"] == em["encoded"]["encoding"]
    if method == "event":
        assert control == expanded
        assert em["diagnostic"]["expanded_references"] == 0
        assert em["diagnostic"]["no_shared_codec"]
    else:
        assert em["diagnostic"]["expanded_references"] > 0
        assert em["encoded"]["shared_values"] == cm["encoded"]["shared_values"]


def test_mismatched_source_or_prefix_rejected():
    history, source = fixture("state")
    with pytest.raises(ValueError, match="codec"):
        prepare_replacement(history, source, "event", "goal_inline", len)
    history[-1]["output"] = "changed"
    with pytest.raises(AssertionError, match="checkpoint"):
        prepare_replacement(history, source, "state", "goal_inline", len)


def test_metrics_separate_live_emissions_executions_and_descriptive_repeats():
    call = {"type": "function_call", "name": "ls", "arguments": "{}"}
    records = [{"source": "replay", "response": {"output": [call]}},
               {"source": "live", "response": {"output": [call, call]}},
               {"source": "live", "response": {"output": [{"type": "message"}]}}]
    executions = [{"source": "replay", "execution_results": ['{"error":"old"}']},
                  {"source": "live", "execution_results": ['{"success":false}', 'plain text preserved']}]
    decoding = [{"source": "replay", "decoded": False, "error": "old"},
                {"source": "live", "decoded": False, "error": "new"}]
    metrics = _action_metrics(records, executions, decoding)
    assert metrics["model_requests"] == 2
    assert metrics["emitted_function_items"] == 2
    assert metrics["executed_tool_returns"] == 2
    assert metrics["same_name_and_raw_arguments_candidates"] == 1
    assert metrics["parser_error_count"] == 1
    assert metrics["explicit_structured_tool_error_returns"] == 1
    assert "not redundancy labels" in metrics["repeat_interpretation"]


def test_task_does_not_reuse_nonempty_attempt(tmp_path):
    from workflows.diagnostic_task import main
    (tmp_path / "manifest.json").write_text("{}")
    with pytest.raises(ValueError, match="Never overwrite"):
        main(["--task", "task", "--category", "category", "--seed", "10", "--method", "state",
              "--arm", "goal_inline", "--identity", "unused", "--source-graph", "unused",
              "--output", str(tmp_path)])


def test_identity_retains_roles_raw_arguments_and_order_without_graph_or_instruction(monkeypatch):
    history, _ = fixture("state")
    history.insert(2, {"role": "assistant", "content": "I will inspect it."})
    history[-2]["arguments"] = ' { "all" : false } '
    original = deepcopy(history)
    def forbidden(*args, **kwargs):
        raise AssertionError("Identity must not construct or decode a graph")
    monkeypatch.setattr(optimized_graph, "build_memory", forbidden)
    monkeypatch.setattr(lossless_state, "decode", forbidden)
    messages, meta = prepare_identity_passthrough(history, 1096)
    assert messages == original == meta["identity_history"]
    assert meta["replacement_messages"] == original[1:]
    assert meta["instruction"] == meta["common_diagnostic_rule"] == ""
    assert meta["instruction_tokens"] == meta["common_rule_tokens"] == 0
    assert meta["graph"] is meta["encoded"] is meta["payload_decode_exact"] is None
    assert meta["identity_history_exact"] and meta["total_tokens"] == 1096
    messages[-1]["output"] = "changed caller copy"
    assert history == original == meta["identity_history"]


def test_identity_and_graph_arm_selection_cannot_be_crossed():
    assert validate_arm_selection("identity", "identity_reference", None)
    assert not validate_arm_selection("state", "goal_inline", "graph-path")
    for method, arm, source in [("identity", "goal_inline", None),
                                ("state", "identity_reference", "graph-path"),
                                ("identity", "identity_reference", "graph-path"),
                                ("state", "goal_inline", None)]:
        with pytest.raises(ValueError):
            validate_arm_selection(method, arm, source)


@pytest.mark.parametrize("runner", ["qwen", "muse"])
def test_identity_cli_needs_no_graph_and_still_preserves_existing_attempts(tmp_path, runner):
    if runner == "qwen":
        from workflows.diagnostic_task import main
    else:
        from workflows.muse_diagnostic_task import main
    (tmp_path / "manifest.json").write_text("{}")
    with pytest.raises(ValueError, match="Never overwrite"):
        main(["--task", "task", "--category", "category", "--seed", "1", "--method", "identity",
              "--arm", "identity_reference", "--identity", "unused", "--output", str(tmp_path),
              "--max-output-tokens", "16384"])
