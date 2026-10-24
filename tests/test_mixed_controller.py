import json
import sys
from types import SimpleNamespace

import pytest

from workflows.mixed_controller import (development_digest, gate_expected,
                                        validate_completed, validate_gate)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def test_review_gate_is_bound_to_frozen_source_plan_and_encoding_selection(tmp_path):
    snapshot = tmp_path / "source_code/adapter-v1"
    write(snapshot / "hashes.json", {"scripts/core/mixed_graph.py": "source-hash"})
    write(tmp_path / "task-split.json", {"seeds": [15013]})
    write(tmp_path / "selection.json", {"selected": {"state": "fixed"}})
    expected = gate_expected(tmp_path, snapshot)
    gate = dict(status="pass", **expected)
    validate_gate(gate, expected)
    write(tmp_path / "selection.json", {"selected": {"state": "reselected"}})
    with pytest.raises(RuntimeError, match="selection_sha256"):
        validate_gate(gate, gate_expected(tmp_path, snapshot))
    with pytest.raises(RuntimeError, match="did not pass"):
        validate_gate(dict(gate, status="needs_review"), expected)


def test_completed_attempt_provenance_and_partial_attempts_are_fail_closed(tmp_path):
    snapshot = tmp_path / "snapshot"
    write(snapshot / "hashes.json", {"module.py": "hash"})
    destination = tmp_path / "run"
    expected = dict(task="multi_turn_base_0", seed=15013, method="event",
                    explanation="minimal", variant="tables-v1")
    command = ["python", "-m", "workflows.mixed_task", "--seed", "15013"]
    write(destination / "manifest.json", dict(expected, status="complete"))
    write(destination / "launch.json",
          dict(command=command, source_snapshot=str(snapshot),
               source_hashes={"module.py": "hash"}))
    validate_completed(destination, expected, snapshot, command)
    with pytest.raises(RuntimeError, match="configuration mismatch explanation"):
        validate_completed(destination, dict(expected, explanation="none"), snapshot, command)
    write(destination / "manifest.json", dict(expected, status="running"))
    with pytest.raises(RuntimeError, match="Incomplete attempt"):
        validate_completed(destination, expected, snapshot, command)


def test_development_review_digest_changes_with_run_result(tmp_path):
    manifest = tmp_path / "development/multi_turn_base_0/seed1103/identity/manifest.json"
    write(manifest, dict(status="complete", passed=False))
    original = development_digest(tmp_path)
    write(manifest, dict(status="complete", passed=True))
    assert development_digest(tmp_path) != original


@pytest.mark.parametrize("review_status", ["pass", "needs_review"])
def test_controller_requires_development_review_before_any_fresh_model_run(
        tmp_path, monkeypatch, review_status):
    from workflows import mixed_controller as controller
    snapshot = tmp_path / "source_code/adapter-v1"
    write(snapshot / "hashes.json", {})
    sampling = dict(temperature=0.6, top_p=0.95, top_k=20, repeat_penalty=1.0)
    task = dict(id="multi_turn_base_0", category="multi_turn_base", split="development")
    write(tmp_path / "task-split.json",
          dict(tasks=[task], development_seeds=[1103], seeds=[15013], sampling=sampling,
               baseline_explanations=dict(state="minimal", event="full", dedup="none")))
    write(tmp_path / "selection.json",
          dict(selected={method: dict(variant="candidate", explanation="none", module="codec")
                         for method in ("state", "event", "dedup")}))
    write(tmp_path / "preflight-review.json", dict(status="pass", **gate_expected(tmp_path, snapshot)))
    launched_seeds = []

    def fake_run(command, **kwargs):
        module = command[2]
        if module == "workflows.mixed_task":
            options = dict(zip(command[3::2], command[4::2]))
            seed = int(options["--seed"])
            launched_seeds.append(seed)
            manifest = dict(
                task=options["--task"], category=options["--category"], seed=seed,
                method=options["--method"], variant=options["--variant"],
                explanation=options["--explanation"], threshold=1000, context=131072,
                max_tokens=4096, base_url=options["--base-url"],
                identity=options.get("--identity"), sampling=sampling, status="complete")
            write(controller.Path(options["--output"]) / "manifest.json", manifest)
        elif module == "workflows.mixed_audit" and 15013 not in launched_seeds:
            write(tmp_path / "development-review.json",
                  dict(status=review_status, **gate_expected(tmp_path, snapshot),
                       development_manifest_sha256=development_digest(tmp_path)))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(controller.subprocess, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["mixed_controller", "--root", str(tmp_path),
                                     "--snapshot-label", "adapter-v1"])
    if review_status == "pass":
        controller.main()
        assert launched_seeds == [1103]*7 + [15013]*7
        assert (tmp_path / "runtime/pending-followup.json").exists()
    else:
        with pytest.raises(RuntimeError, match="did not pass"):
            controller.main()
        assert launched_seeds == [1103]*7
        assert not (tmp_path / "evaluation").exists()
        assert json.loads((tmp_path / "runtime/status.json").read_text())["status"] == "needs_review"
