"""Frozen serial mixed-domain study with explicit independent-review gates."""
import argparse
import fcntl
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import time

from workflows.lossless_controller import read, write, verify


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def gate_expected(root, snapshot):
    expected = dict(snapshot_hashes_sha256=digest(snapshot / "hashes.json"),
                    task_split_sha256=digest(root / "task-split.json"),
                    selection_sha256=digest(root / "selection.json"))
    if (root / "vendor-pins.json").exists():
        expected["vendor_pins_sha256"] = digest(root / "vendor-pins.json")
    if (root / "PROTOCOL.md").exists():
        expected["protocol_sha256"] = digest(root / "PROTOCOL.md")
    return expected


def validate_gate(gate, expected):
    if gate.get("status") != "pass":
        raise RuntimeError("Independent review did not pass")
    for key, value in expected.items():
        if gate.get(key) != value:
            raise RuntimeError(f"Independent review does not match {key}")


def development_digest(root):
    files = sorted((root / "development").glob("*/seed*/*/manifest.json"))
    if not files:
        raise RuntimeError("No development manifests")
    text = "\n".join(f"{path.relative_to(root)}:{digest(path)}" for path in files)
    return hashlib.sha256(text.encode()).hexdigest()


def validate_completed(path, expected, snapshot, command):
    manifest = read(path / "manifest.json")
    if manifest["status"] not in ("complete", "not_triggered"):
        raise RuntimeError(f"Incomplete attempt must be reviewed, never overwritten: {path}")
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise RuntimeError(f"Existing run configuration mismatch {key}: {path}")
    launch = read(path / "launch.json")
    if (launch["command"] != command or launch["source_snapshot"] != str(snapshot)
            or launch["source_hashes"] != read(snapshot / "hashes.json")):
        raise RuntimeError(f"Existing launch provenance mismatch: {path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--snapshot-label", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:11436/v1")
    args = parser.parse_args()
    root = args.root.resolve()
    runtime = root / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    lock = (runtime / "controller.lock").open("w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    snapshot = root / "source_code" / args.snapshot_label
    try:
        verify(snapshot)
        expected_gate = gate_expected(root, snapshot)
        validate_gate(read(root / "preflight-review.json"), expected_gate)
        plan = read(root / "task-split.json")
        selection = read(root / "selection.json")["selected"]
    except BaseException as error:
        write(runtime / "status.json",
              dict(pid=os.getpid(), status="needs_review", stage="startup_validation",
                   error=repr(error), failed_at=time.time()))
        raise
    status = dict(pid=os.getpid(), status="running", stage="development",
                  started_at=time.time(), completed_jobs=0, stages=[],
                  source_snapshot=str(snapshot), frozen_inputs=expected_gate)
    env = dict(os.environ, PYTHONPATH=str(snapshot / "scripts"),
               PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1")

    def update(**values):
        status.update(values, updated_at=time.time())
        write(runtime / "status.json", status)

    def check_inputs():
        verify(snapshot)
        if gate_expected(root, snapshot) != expected_gate:
            raise RuntimeError("Frozen study inputs changed")
        if "vendor_pins_sha256" in expected_gate:
            for relative, expected_hash in read(root / "vendor-pins.json").items():
                if digest(snapshot / relative) != expected_hash:
                    raise RuntimeError(f"Pinned BFCL source or data changed: {relative}")

    def run(task, seed, method, destination, identity=None, optimized=False):
        selected = selection[method] if optimized else {}
        variant = selected["variant"] if optimized else "mixed-domain-graph-1"
        explanation = selected["explanation"] if optimized else (
            "none" if method == "identity" else plan["baseline_explanations"][method])
        command = [sys.executable, "-m", "workflows.mixed_task",
                   "--task", task["id"], "--category", task["category"], "--seed", str(seed),
                   "--method", method, "--variant", variant, "--explanation", explanation,
                   "--output", str(destination), "--base-url", args.base_url]
        if identity:
            command += ["--identity", str(identity)]
        if optimized:
            command += ["--codec-module", selected["module"], "--codec-variant", variant]
        expected = dict(task=task["id"], category=task["category"], seed=seed, method=method,
                        variant=variant, explanation=explanation, threshold=1000, context=131072,
                        max_tokens=4096, base_url=args.base_url,
                        identity=str(identity) if identity else None,
                        sampling=plan["sampling"])
        check_inputs()
        if (destination / "manifest.json").exists():
            validate_completed(destination, expected, snapshot, command)
        else:
            if destination.exists() and any(destination.iterdir()):
                raise RuntimeError(f"Unmanifested attempt requires review: {destination}")
            destination.mkdir(parents=True, exist_ok=True)
            write(destination / "launch.json",
                  dict(command=command, source_snapshot=str(snapshot),
                       source_hashes=read(snapshot / "hashes.json"), time=time.time()))
            update(current=dict(task=task["id"], seed=seed, method=method,
                                optimized=optimized, destination=str(destination)))
            with (destination / "runner.log").open("w") as log:
                subprocess.run(command, cwd=snapshot, env=env, stdout=log,
                               stderr=subprocess.STDOUT, check=True)
            validate_completed(destination, expected, snapshot, command)
        check_inputs()
        status["completed_jobs"] += 1
        update(last_completed=str(destination))

    def matrix(stage, tasks, seeds):
        update(stage=f"{stage}_identity")
        for task in tasks:
            for seed in seeds:
                run(task, seed, "identity", root / stage / task["id"] / f"seed{seed}" / "identity")
        update(stage=f"{stage}_paired_graphs")
        for task in tasks:
            for seed in seeds:
                base = root / stage / task["id"] / f"seed{seed}"
                for method in ("state", "event", "dedup"):
                    for optimized in (False, True):
                        label = method + ("-optimized" if optimized else "-baseline")
                        run(task, seed, method, base / label, base / "identity", optimized)

    def child(module, *extra):
        check_inputs()
        subprocess.run([sys.executable, "-m", module, "--root", str(root), *extra],
                       cwd=snapshot, env=env, check=True)
        check_inputs()

    try:
        update()
        development = [task for task in plan["tasks"] if task["split"] == "development"]
        matrix("development", development, plan["development_seeds"])
        child("workflows.mixed_audit", "--output", str(root / "reports/development-mechanical-audit.json"))
        status["stages"].append("development_complete")
        review_expected = dict(expected_gate, development_manifest_sha256=development_digest(root))
        update(stage="waiting_for_independent_development_review")
        gate_path = root / "development-review.json"
        while not gate_path.exists():
            check_inputs()
            time.sleep(30)
            update(stage="waiting_for_independent_development_review")
        validate_gate(read(gate_path), review_expected)
        status["stages"].append("development_review_passed")
        matrix("evaluation", plan["tasks"], plan["seeds"])
        update(status="inference_complete_pending_independent_audit", stage="mechanical_audit")
        child("workflows.mixed_audit", "--output", str(root / "reports/final-mechanical-audit.json"))
        update(stage="report")
        child("workflows.mixed_report")
        status["stages"].append("automatic_reports_complete")
        update(stage="independent_final_audit_pending", finished_at=time.time())
        write(runtime / "pending-followup.json",
              dict(status="independent_final_audit_required",
                   instructions="Verify semantics, payloads, official scores and paired statistics independently. Do not call automatic checks final independent review."))
    except BaseException as error:
        update(status="needs_review", error=repr(error), failed_at=time.time())
        raise


if __name__ == "__main__":
    main()
