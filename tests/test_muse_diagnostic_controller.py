"""No model/network calls: queued dependencies, source selection and risk gates."""
from copy import deepcopy
from pathlib import Path

import pytest

from workflows import diagnostic_controller as shared
from workflows.muse_diagnostic_controller import (
    completed_source_coverage, dependencies, select_pilot, semantic_risks, validate_queue,
)


def queue(tmp_path):
    return dict(schema="muse-diagnostic-queue-v1", qwen_root=str(tmp_path / "qwen"),
                muse_source_root=str(tmp_path / "muse"), base_url="http://127.0.0.1:11437/v1",
                snapshot_label="readout-v1", poll_seconds=30, expected_source_identities=600,
                methods=list(shared.METHODS), arms=list(shared.ARMS), threshold=1000,
                context=131072, max_tokens=4096, explanation="minimal",
                sampling=dict(temperature=0.6, top_p=0.95, top_k=20, repeat_penalty=1.0),
                diagnostic_limits=deepcopy(shared.DIAGNOSTIC_LIMITS),
                selection="all_muse_actual_mixed_triggered", pilot_target=6)


def states(config, qwen, muse):
    shared.write(Path(config["qwen_root"]) / "runtime/status.json", qwen)
    shared.write(Path(config["muse_source_root"]) / "runtime/status.json", muse)


def test_waits_for_both_complete_matrices(tmp_path):
    config = queue(tmp_path)
    validate_queue(config)
    states(config, dict(status="running", completed_jobs=1457),
           dict(status="inference_complete_pending_independent_audit", completed_jobs=4200))
    assert dependencies(config)[0] is False
    states(config, dict(status="diagnostic_complete_pending_independent_review", completed_jobs=1458),
           dict(status="running", completed_jobs=4199))
    assert dependencies(config)[0] is False
    states(config, dict(status="diagnostic_complete_pending_independent_review", completed_jobs=1458),
           dict(status="inference_complete_pending_independent_audit", completed_jobs=4200))
    shared.write(Path(config["qwen_root"]) / "reports/summary.json",
                 dict(status="diagnostic_complete_pending_independent_review", expected_prefixes=81,
                      expected_graph_jobs=1458, completed_graph_jobs=1458, incomplete_graph_jobs=0))
    qroot = Path(config["qwen_root"])
    shared.write(qroot / "task-split.json", dict(pilot_case_ids=["a", "b", "c", "d"]))
    shared.write(qroot / "release.json", dict(status="pass"))
    shared.write(qroot / "runtime/pilot-gate.json", dict(status="pass", gate="engineering_only_no_score_selection",
                 pilot_case_ids=["a", "b", "c", "d"], checked_jobs=72, release_sha256=shared.sha(qroot / "release.json")))
    assert dependencies(config)[0] is True


def test_upstream_failure_stops_instead_of_infinite_queue(tmp_path):
    config = queue(tmp_path)
    states(config, dict(status="needs_review", completed_jobs=18), dict(status="running", completed_jobs=200))
    with pytest.raises(RuntimeError, match="dependency requires review"):
        dependencies(config)


def test_queue_cannot_be_repointed_to_other_population(tmp_path):
    config = queue(tmp_path)
    config["expected_source_identities"] = 81
    with pytest.raises(RuntimeError):
        validate_queue(config)


def history(name, result):
    return [dict(type="function_call", call_id="c", name=name, arguments="{}"),
            dict(type="function_call_output", call_id="c", output=result)]


def test_semantic_hazards_stop_without_guessing_shared_alias_damage():
    assert semantic_risks(history("mention", '{"mention_status":"Users mentioned successfully"}'))[0]["kind"] == "successful_mention_aliasing_review_required"
    assert semantic_risks(history("logarithm", '{"error":""}'))[0]["kind"] == "empty_error_wrapper"
    assert semantic_risks(history("mention", '{"error":"Tweet not found"}')) == []
    assert semantic_risks(history("add", '{"result":2}')) == []


def test_pilot_uses_features_and_lexical_ties_not_scores():
    samples = [dict(case_id=f"prefix-{i}", pilot_features=[f"domain:{i % 4}", f"refs:{i % 2}"], passed=i % 2)
               for i in range(10)]
    chosen = select_pilot(samples)
    swapped = [dict(row, passed=not row["passed"]) for row in reversed(samples)]
    assert chosen == select_pilot(swapped)
    assert len(chosen) == 6 and len(set(chosen)) == 6
    assert select_pilot(samples[:4]) == ["prefix-0", "prefix-1", "prefix-2", "prefix-3"]


def test_dynamic_denominator_not_qwen_81():
    result = shared.aggregate([dict(passed=False, emitted_calls=0)], expected=7)
    assert result["planned"] == 7 and result["missing"] == 6
    assert result["success_with_call_budget"] == [dict(budget=0, successful=0, denominator=7)]


def test_registered_queue_config_when_present():
    root = Path(__file__).resolve().parents[1]
    path = root / "experiments/bfcl_identity/muse_history_diagnostics_v1/queue-config.json"
    if not path.exists():
        pytest.skip("Queued study not installed")
    validate_queue(shared.read(path))


def test_source_coverage_keeps_4200_slots_but_audits_only_actual_runs(tmp_path):
    config = queue(tmp_path)
    root = Path(config["muse_source_root"])
    tasks = [dict(id=f"c{condition}_{family}", family=family, category=f"c{condition}")
             for family in range(50) for condition in range(4)]
    shared.write(root / "task-split.json", dict(tasks=tasks, seeds=[1, 2, 3], identity_runs=600))
    for task in tasks:
        for seed in (1, 2, 3):
            triggered = task["id"] == "c0_0" and seed == 1
            for label in ("identity", *(m + suffix for m in shared.METHODS for suffix in ("-baseline", "-optimized"))):
                status = "complete" if label == "identity" or triggered else "not_triggered"
                shared.write(root / "evaluation" / task["id"] / f"seed{seed}" / label / "manifest.json",
                             dict(status=status, task=task["id"], category=task["category"], seed=seed, triggered=triggered))
    shared.write(root / "reports/summary.json", dict(identity_runs=600, triggered_prefixes=1))
    shared.write(root / "reports/mechanical-audit.json", dict(status="pass", records=606))
    assert len(completed_source_coverage(config)["tasks"]) == 200
    shared.write(root / "reports/mechanical-audit.json", dict(status="pass", records=4200))
    with pytest.raises(RuntimeError, match="real-run audit"):
        completed_source_coverage(config)
