"""Engineering and reporting invariants; no server or model calls."""
import json
from copy import deepcopy
from pathlib import Path

import pytest

from workflows.diagnostic_controller import (
    ARMS, METHODS, DIAGNOSTIC_LIMITS, aggregate, execution_metrics, input_comparison,
    paired_summary, release_inputs, run_metrics, sha, validate_plan, verify_release, write, write_once,
)


def plan():
    return dict(schema="mixed-diagnostic-v1", expected_prefixes=81,
                methods=list(METHODS), arms=list(ARMS), threshold=1000, context=131072,
                max_tokens=4096, explanation="minimal",
                sampling=dict(temperature=0.6, top_p=0.95, top_k=20, repeat_penalty=1.0),
                diagnostic_limits=deepcopy(DIAGNOSTIC_LIMITS),
                base_url="http://127.0.0.1:11436/v1",
                samples=[dict(case_id=f"prefix-{i}", sample_id=f"sample-{i}", task=f"task-{i}",
                              seed=i, source_paths={label: label for label in (
                                  "identity", "state-optimized", "event-optimized", "dedup-optimized")})
                         for i in range(81)], pilot_case_ids=[f"prefix-{i}" for i in range(4)])


def test_fixed_81_paired_matrix_and_local_runtime():
    assert len(validate_plan(plan())) == 81
    for key, value in (("expected_prefixes", 80), ("methods", ["event"]),
                       ("arms", list(ARMS[:-1])), ("base_url", "https://api.openai.com/v1"),
                       ("pilot_case_ids", ["prefix-0"]), ("explanation", "none")):
        changed = deepcopy(plan())
        changed[key] = value
        with pytest.raises(RuntimeError):
            validate_plan(changed)


def test_release_requires_exact_source_and_preflight(tmp_path):
    snapshot = tmp_path / "source_code/readout-v1"
    source = snapshot / "scripts/example.py"
    source.parent.mkdir(parents=True)
    source.write_text("pass\n")
    write(snapshot / "hashes.json", {"scripts/example.py": sha(source)})
    for relative in ("task-split.json", "runtime/runtime-contract.json", "vendor-pins.json", "source-inputs.json"):
        write(tmp_path / relative, {})
    (tmp_path / "PROTOCOL.md").write_text("Frozen diagnostic protocol.\n")
    write(tmp_path / "preflight-review.json", {"status": "pass"})
    release = dict(status="pass", preflight_status="pass", input_sha256=release_inputs(tmp_path, snapshot))
    write(tmp_path / "release.json", release)
    verify_release(tmp_path, snapshot)
    source.write_text("raise RuntimeError\n")
    with pytest.raises(RuntimeError, match="Pinned input changed"):
        verify_release(tmp_path, snapshot)


def test_release_cannot_accept_subset_of_pins(tmp_path):
    snapshot = tmp_path / "source_code/readout-v1"
    for relative in ("task-split.json", "runtime/runtime-contract.json", "vendor-pins.json", "source-inputs.json",
                     "source_code/readout-v1/hashes.json"):
        write(tmp_path / relative, {})
    (tmp_path / "PROTOCOL.md").write_text("Frozen.\n")
    write(tmp_path / "preflight-review.json", {"status": "pass"})
    write(tmp_path / "release.json", dict(status="pass", preflight_status="pass", input_sha256={}))
    with pytest.raises(RuntimeError, match="exact frozen inputs"):
        verify_release(tmp_path, snapshot)


def test_preserve_existing_attempt_file(tmp_path):
    path = tmp_path / "launch.json"
    write_once(path, {"first": True})
    with pytest.raises(FileExistsError):
        write_once(path, {"first": False})
    assert json.loads(path.read_text()) == {"first": True}


def metric(case_id, passed, calls, arm):
    return dict(case_id=case_id, family="same-family", category="base", seed=1,
                method="event", arm=arm, passed=passed, first_input=100,
                mean_post_input=110, emitted_calls=calls, model_requests=calls + 1)


def test_failure_with_fewer_calls_gets_no_success_credit_and_missing_stays_visible():
    rows = [metric("a", False, 0, "refs_control"), metric("b", True, 3, "refs_control")]
    summary = aggregate(rows)
    assert (summary["planned"], summary["completed"], summary["missing"], summary["successes"]) == (81, 2, 79, 1)
    assert summary["success_with_call_budget"][0] == dict(budget=0, successful=0, denominator=81)
    assert summary["fixed_denominator_success_bounds"] == [1 / 81, 80 / 81]


def test_paired_counts_do_not_select_successful_subset():
    rows = [metric("a", True, 1, "refs_control"), metric("a", False, 0, "refs_expanded"),
            metric("b", False, 0, "refs_control"), metric("b", True, 2, "refs_expanded")]
    identity = {case: metric(case, True, 1, "historical_identity") for case in ("a", "b")}
    result = paired_summary(rows, identity, "refs_control", "refs_expanded", "event")
    assert (result["gains"], result["losses"], result["both_success"], result["missing_pairs"]) == (1, 1, 0, 79)
    assert len(result["pairs"]) == 2


def test_execution_items_counted_only_after_shared_boundary(tmp_path):
    log = [dict(step_0=[dict(role="tool", content='{"error":"before boundary"}')],
                step_1=[dict(role="tool", content='{"error":"after boundary"}'),
                        dict(role="tool", content='{"result":"ok"}')],
                step_2=[dict(role="handler_log", content="Error decoding the model response. Proceed to next turn.")])]
    write(tmp_path / "full.json", dict(metadata=dict(inference_log=log)))
    assert execution_metrics(tmp_path, [{}, {}, {}], 1) == dict(
        executed_tool_items=2, explicit_error_returns=1, parse_errors=1,
        execution_count_unavailable_reason=None)
    assert execution_metrics(tmp_path, [{}], 0)["executed_tool_items"] is None


def test_cost_gate_ratio_of_means_is_not_mean_of_ratios():
    identity = {"a": {"first_input": 10}, "b": {"first_input": 100}}
    rows = [dict(case_id="a", first_input=20), dict(case_id="b", first_input=100)]
    result = input_comparison(rows, identity, "first_input")
    assert result["mean_paired_ratio"] == 1.5
    assert result["ratio_of_means"] == 120 / 110
    assert result["measured"] == 2


def test_unrequested_context_limit_is_failed_but_not_charged(tmp_path):
    write(tmp_path / "manifest.json", dict(trigger_index=0, status="protocol_failure", passed=False, max_tokens=4096))
    write(tmp_path / "api.json", [])
    write(tmp_path / "accounting.json", [dict(index=0, input_tokens=130000, requested=False)])
    write(tmp_path / "executions.json", [])
    write(tmp_path / "decoding.json", [])
    write(tmp_path / "memory-metadata.json", dict(diagnostic={"expanded_references": 0}))
    (tmp_path / "native.jsonl").write_text(json.dumps(dict(event="context_limit", index=0)) + "\n")
    sample = dict(case_id="prefix-0", sample_id="sample-0", task="task-0", family="f", category="base", seed=1)
    row = run_metrics(tmp_path, sample, "event", "refs_expanded")
    assert row["passed"] is False and row["official_score_available"] is False
    assert row["first_input"] is None and row["mean_post_input"] is None
    assert row["model_requests"] == row["cumulative_post_input"] == row["executed_tool_items"] == 0
    assert row["unrequested_context_limit_inputs"] == [130000]
    assert aggregate([row])["successes"] == 0


def test_real_predeclared_plan_schema_when_present():
    path = Path(__file__).resolve().parents[1] / "experiments/bfcl_identity/mixed_history_diagnostics_v1/task-split.json"
    if not path.exists():
        pytest.skip("Study inputs are not installed in this checkout")
    assert len(validate_plan(json.loads(path.read_text()))) == 81
