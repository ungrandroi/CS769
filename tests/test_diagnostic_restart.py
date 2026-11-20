"""Fresh matched-budget matrix and unresolved-output safeguards; no inference."""
import json
from copy import deepcopy

import pytest

from workflows import diagnostic_restart as restart
from workflows.diagnostic_controller import input_comparison, write, sha


def metric(case, method, arm):
    return dict(case_id=case, method=method, arm=arm, family="f", category="base", seed=1,
                passed=True, first_input=100, mean_post_input=120, emitted_calls=2, model_requests=3)


def matrix():
    return {f"{case}/{method}/{arm}": metric(case, method, arm)
            for case in ("a", "b") for method, arm in restart.BRANCHES}


def test_input_comparison_requires_both_costs():
    identity = {"a": {"mean_post_input": None}, "b": {"mean_post_input": 100}}
    rows = [dict(case_id="a", mean_post_input=200), dict(case_id="b", mean_post_input=150)]
    result = input_comparison(rows, identity, "mean_post_input")
    assert result == dict(measured=1, mean_paired_ratio=1.5, ratio_of_means=1.5)
    assert input_comparison(rows[:1], identity, "mean_post_input") == dict(
        measured=0, mean_paired_ratio=None, ratio_of_means=None)


def test_fresh_report_uses_matched_identity_and_preserves_missing_cost(tmp_path):
    accepted = matrix()
    accepted["a/identity/identity_reference"]["mean_post_input"] = None
    result = restart.report(tmp_path, dict(expected_prefixes=2, expected_jobs=38), accepted, {})
    flag = result["diagnostic_flags"]["event/refs_expanded"]
    assert flag["matched_identity_pairs"] == 2
    assert flag["mean_input"]["measured"] == 1
    assert flag["mean_input_overhead_above_35pct"] is None
    assert result["output_budgets"] == dict(source_prefix=4096, matched_identity_continuation=16384,
                                            graph_continuation=16384)
    assert result["original_4096_identity_outcomes_used"] is False
    assert result["groups"]["identity"]["success_with_call_budget"][-1]["denominator"] == 2


def test_unresolved_is_not_scored_or_dropped(tmp_path):
    accepted = matrix()
    key = "a/event/refs_expanded"
    row = accepted.pop(key)
    row["passed"] = None
    result = restart.report(tmp_path, dict(expected_prefixes=2, expected_jobs=38), accepted,
                            {key: dict(recorded_costs=row, evidence=dict(outcome=None))})
    assert result["status"] == "all_planned_attempted_pending_review"
    assert result["attempted_jobs"] == 38 and result["completed_jobs"] == 37
    assert result["unresolved_jobs"] == 1 and result["not_started_jobs"] == 0
    assert result["capability_acceptance_available"] is False
    group = result["groups"]["event/refs_expanded"]
    assert group["planned"] == 2 and group["missing"] == 1
    assert group["fixed_denominator_success_bounds"] == [0.5, 1]
    assert result["diagnostic_flags"]["event/refs_expanded"]["success_loss_pp"] is None


def malformed_fixture(path):
    source = path / "source.json"
    write(source, {"unchanged": True})
    args = '{"x":"unterminated'
    call = dict(function=dict(name="echo", arguments=args))
    raw = dict(choices=[dict(message=dict(tool_calls=[call]), finish_reason="length")],
               usage=dict(prompt_tokens=100, completion_tokens=16384))
    write(path / "manifest.json", dict(status="infrastructure_error", passed=None, error="JSONDecodeError('bad')",
          trigger_index=0, source_sha256={str(source): sha(source)},
          engineering_audit=dict(source_files_unchanged=True)))
    write(path / "api.json", [dict(source="live", response=dict(output=[dict(type="function_call", name="echo", arguments=args)]))])
    write(path / "decoding.json", [dict(source="live", index=0, decoded=False, error="JSONDecodeError('bad')")])
    write(path / "accounting.json", [dict(index=0, requested=True, usage_verified=True, input_tokens=100, output_tokens=16384)])
    (path / "native.jsonl").write_text("\n".join(json.dumps(x) for x in [
        dict(event="request", index=0, request={}), dict(event="response", index=0, response=raw)]) + "\n")


def test_only_recorded_unmodified_malformed_output_is_isolated(tmp_path):
    malformed_fixture(tmp_path)
    result = restart.malformed_arguments_evidence(tmp_path)
    assert result["outcome"] is None and result["raw_arguments_preserved"] is True
    assert result["retried"] is False and result["scored_as_failure"] is False
    api = json.loads((tmp_path / "api.json").read_text())
    api[0]["response"]["output"][0]["arguments"] = '{}'
    write(tmp_path / "api.json", api)
    with pytest.raises(RuntimeError, match="rewritten"):
        restart.malformed_arguments_evidence(tmp_path)


@pytest.mark.parametrize("change", ["score", "source", "decoder", "valid_json"])
def test_malformed_classifier_rejects_unrelated_or_changed_failure(tmp_path, change):
    malformed_fixture(tmp_path)
    if change == "score":
        write(tmp_path / "official-score.json", {})
    elif change == "source":
        write(tmp_path / "source.json", {"unchanged": False})
    elif change == "decoder":
        write(tmp_path / "decoding.json", [])
    else:
        api = json.loads((tmp_path / "api.json").read_text())
        api[0]["response"]["output"][0]["arguments"] = '{}'
        write(tmp_path / "api.json", api)
        records = [json.loads(line) for line in (tmp_path / "native.jsonl").read_text().splitlines()]
        records[1]["response"]["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = '{}'
        (tmp_path / "native.jsonl").write_text("\n".join(json.dumps(x) for x in records) + "\n")
    with pytest.raises(RuntimeError):
        restart.malformed_arguments_evidence(tmp_path)
