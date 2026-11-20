"""Output-cap amendments remain explicit and cannot pass mismatched Identity gates."""
from copy import deepcopy
from pathlib import Path

import pytest

from workflows import diagnostic_controller as qwen
from workflows import muse_diagnostic_controller as muse


@pytest.mark.parametrize("budget", [4096, 16384])
def test_both_registered_controller_profiles_accept_output_budget(budget):
    root = Path(__file__).resolve().parents[1]
    paths = [root / "experiments/bfcl_identity/mixed_history_diagnostics_v1/task-split.json",
             root / "experiments/bfcl_identity/muse_history_diagnostics_v1/queue-config.json"]
    if not all(path.exists() for path in paths):
        pytest.skip("Frozen experiment profiles unavailable in this checkout")
    plan, config = map(qwen.read, paths)
    plan["max_tokens"] = config["max_tokens"] = budget
    assert len(qwen.validate_plan(plan)) == 81
    muse.validate_queue(config)


@pytest.mark.parametrize("budget", [None, True, 8192, 16384.0])
def test_unregistered_or_implicit_output_budget_is_rejected(budget):
    with pytest.raises(RuntimeError, match="explicitly registered"):
        qwen.output_budget({"max_tokens": budget})


@pytest.mark.parametrize("module", [qwen, muse])
@pytest.mark.parametrize("budget", [4096, 16384])
def test_reports_disable_identity_acceptance_when_only_graph_budget_changes(monkeypatch, module, budget):
    # Two complete synthetic prefixes deliberately lose all Identity successes
    # and add 50% input. Mismatched caps must not produce acceptance flags even
    # though the descriptive differences and within-pair results are retained.
    monkeypatch.setattr(qwen, "EXPECTED_PREFIXES", 2)
    monkeypatch.setattr(qwen, "EXPECTED_JOBS", 36)
    samples = [dict(case_id=f"p{i}", sample_id=f"s{i}", task=f"t{i}", family=f"f{i}",
                    category="base", seed=i, source_paths={"identity": f"/source/p{i}/identity"})
               for i in range(2)]
    plan = dict(samples=samples, max_tokens=budget, expected_prefixes=2,
                diagnostic_limits=deepcopy(qwen.DIAGNOSTIC_LIMITS), model="synthetic",
                coverage={"selected": 2}, pilot_case_ids=[s["case_id"] for s in samples])

    def read(path):
        return [] if Path(path).name == "accounting.json" else {"status": "complete"}

    def metric(path, sample, method, arm, historical=False):
        value = 100 if historical else 150
        return dict(case_id=sample["case_id"], family=sample["family"], category="base", seed=sample["seed"],
                    method=method, arm=arm, passed=historical, status="complete",
                    first_input=value, mean_post_input=value, peak_input=value,
                    cumulative_post_input=value * 2, model_requests=2, emitted_calls=1,
                    executed_tool_items=1, explicit_error_returns=0, parse_errors=0,
                    adjacent_same_arguments_candidates=0, max_output_tokens=4096 if historical else budget,
                    diagnostic_audit={})

    def checked(path, sample, method, arm, plan, project):
        return metric(path, sample, method, arm)

    monkeypatch.setattr(Path, "exists", lambda self: True)
    monkeypatch.setattr(qwen, "read", read)
    monkeypatch.setattr(muse, "read", read)
    monkeypatch.setattr(qwen, "write", lambda *args: None)
    monkeypatch.setattr(muse, "write", lambda *args: None)
    monkeypatch.setattr(qwen, "score_evidence", lambda *args: None)
    monkeypatch.setattr(qwen, "run_metrics", metric)
    monkeypatch.setattr(qwen, "validate_job", checked)
    monkeypatch.setattr(muse, "validate_job", checked)
    result = module.report(Path("/new-study"), plan, Path("/project"))
    caps = result["output_budget_comparison"]
    assert caps["historical_identity_max_output_tokens"] == 4096
    assert caps["candidate_max_output_tokens"] == budget
    assert caps["matched_output_budget"] is (budget == 4096)
    assert caps["within_diagnostic_pairs_budget_matched"] is True
    for flag in result["diagnostic_flags"].values():
        assert flag["success_loss_pp"] == 100
        assert flag["identity_acceptance_available"] is (budget == 4096)
        assert flag["loss_exceeds_3pp"] is (True if budget == 4096 else None)
        assert flag["mean_input_overhead_above_35pct"] is (True if budget == 4096 else None)
        if module is qwen:
            assert flag["first_input_overhead_above_35pct"] is (True if budget == 4096 else None)
            assert flag["mean_input_ratio_of_means"] == 1.5
        else:
            assert flag["mean_input"]["ratio_of_means"] == 1.5
    assert len(result["paired_comparisons"]) == 9
    assert all(pair["completed_pairs"] == 2 for pair in result["paired_comparisons"])


def test_historical_identity_budget_is_not_relabeled_to_match_candidate():
    with pytest.raises(RuntimeError, match="Historical Identity output budget changed"):
        qwen.output_budget_comparison({"max_tokens": 16384}, {"p": {"max_output_tokens": 16384}})
