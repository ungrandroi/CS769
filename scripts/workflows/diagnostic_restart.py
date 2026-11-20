"""Fresh 16K diagnostic matrix with a matched-budget Identity continuation.

All arms replay the same old prefix. Old completed diagnostic outcomes are never
reused. A precisely verified malformed model argument may leave a full-batch
branch unscored for review while other branches proceed; it is never repaired,
retried, silently omitted, or converted to a task failure.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from workflows import diagnostic_controller as shared

read, sha, write, write_once, require = shared.read, shared.sha, shared.write, shared.write_once, shared.require
BRANCHES = (("identity", "identity_reference"), *[(m, a) for m in shared.METHODS for a in shared.ARMS])


def validate_plan(plan, model):
    require(model in ("qwen", "muse"), "Unknown model profile")
    require(shared.output_budget(plan) == 16384 and plan.get("source_max_tokens", 4096) == 4096,
            "Restart requires explicit 16384 live budget and frozen 4096 source prefixes")
    require(plan.get("threshold") == 1000 and plan.get("context") == 131072,
            "History trigger or native context changed")
    require(tuple(plan["methods"]) == shared.METHODS and tuple(plan["arms"]) == shared.ARMS,
            "Diagnostic graph matrix changed")
    require(plan.get("sampling") == dict(temperature=0.6, top_p=0.95, top_k=20, repeat_penalty=1.0)
            and plan.get("explanation") == "minimal", "Sampling or common graph explanation changed")
    require(plan.get("diagnostic_limits") == shared.DIAGNOSTIC_LIMITS, "Report limits changed")
    samples = plan["samples"]
    require(len(samples) == plan["expected_prefixes"] > 0 and plan["expected_jobs"] == len(samples) * 19,
            "Expected exactly one Identity and 18 graph branches per frozen prefix")
    require(len({s["case_id"] for s in samples}) == len(samples)
            and len({s["sample_id"] for s in samples}) == len(samples), "Duplicate frozen prefix")
    for s in samples:
        require(Path(s["case_id"]).name == s["case_id"] and s["case_id"].startswith("prefix-"), "Unsafe case ID")
        require(set(s["source_paths"]) == {"identity", *(m + "-optimized" for m in shared.METHODS)},
                "Incomplete archived source pairing")
    require(4 <= len(plan["pilot_case_ids"]) <= 6 and len(set(plan["pilot_case_ids"])) == len(plan["pilot_case_ids"])
            and set(plan["pilot_case_ids"]) <= {s["case_id"] for s in samples}, "Invalid prespecified pilot")
    expected_endpoint = f"http://127.0.0.1:{11436 if model == 'qwen' else 11437}/v1"
    require(plan["base_url"] == expected_endpoint, "Endpoint is not the registered local model")
    if model == "muse":
        require(Path(plan["depends_on_root"]).is_absolute()
                and len(plan.get("depends_on_release_sha256", "")) == 64,
                "Muse must wait on an exact released Qwen restart")
    return {s["case_id"]: s for s in samples}


def malformed_arguments_evidence(path):
    """Recognize only a recorded live JSON-argument failure; never change it."""
    path = Path(path)
    m, api, decode = read(path / "manifest.json"), read(path / "api.json"), read(path / "decoding.json")
    require(m.get("status") == "infrastructure_error" and m.get("passed") is None
            and str(m.get("error", "")).startswith("JSONDecodeError("), "Not the recognized malformed-arguments failure")
    boundary, index = m["trigger_index"], len(api) - 1
    require(index >= boundary and api[index].get("source") == "live", "Failure lacks a recorded live response")
    failures = [d for d in decode if d.get("source") == "live" and d.get("index") == index and d.get("decoded") is False]
    require(failures and str(failures[-1].get("error", "")).startswith("JSONDecodeError("),
            "Failure was not diagnosed by the actual tool-call decoder")
    requests, responses = shared.native_records(path)
    require(index in requests and index in responses, "Missing raw native request/response evidence")
    raw = responses[index]["response"]
    calls = raw["choices"][0]["message"].get("tool_calls") or []
    logical = [item for item in api[index]["response"]["output"] if item.get("type") == "function_call"]
    require(len(calls) == len(logical) > 0, "Malformed call is not preserved in both native and logical logs")
    malformed = []
    for native, item in zip(calls, logical):
        fn = native["function"]
        require(fn["name"] == item["name"] and fn["arguments"] == item["arguments"], "Raw model arguments were rewritten")
        require(isinstance(fn["arguments"], str), "Unexpected native argument type")
        try:
            json.loads(fn["arguments"])
        except json.JSONDecodeError as error:
            malformed.append(dict(name=fn["name"], argument_characters=len(fn["arguments"]), error=str(error)))
    require(malformed, "Raw model arguments are valid JSON; cannot isolate this error")
    accounts = read(path / "accounting.json")
    last = [a for a in accounts if a["index"] == index]
    require(len(last) == 1 and last[0].get("requested") is True and last[0].get("usage_verified") is True,
            "Model response cost was not completely recorded")
    require(last[0]["input_tokens"] == raw["usage"]["prompt_tokens"]
            and last[0]["output_tokens"] == raw["usage"]["completion_tokens"], "Malformed response usage mismatch")
    shared.verify_hash_map(m["source_sha256"])
    require(m["engineering_audit"].get("source_files_unchanged") is True, "Source preservation failed")
    require(not (path / "official-score.json").exists(), "Unresolved parser failure unexpectedly has a score")
    return dict(status="needs_review", outcome=None, kind="unscored_malformed_model_arguments",
                terminal_response_index=index, finish_reason=raw["choices"][0].get("finish_reason"),
                malformed_calls=malformed, input_tokens=last[0]["input_tokens"], output_tokens=last[0]["output_tokens"],
                raw_arguments_preserved=True, retried=False, scored_as_failure=False)


def validate_job(path, sample, method, arm, plan, project, model, allow_unscored=False):
    if model == "muse":
        from core.muse_transport import MODEL_NAME, MODEL_KEY, REASONING_POLICY
        m = read(path / "manifest.json")
        require(m.get("model") == MODEL_NAME and m.get("model_key") == MODEL_KEY
                and m.get("reasoning_policy") == REASONING_POLICY, "Muse profile changed")
    return shared.validate_job(path, sample, method, arm, plan, project, transport=model,
                               allow_unscored_parser_error=allow_unscored)


def dependency_ready(plan):
    if not plan.get("depends_on_root"):
        return True, {}
    root = Path(plan["depends_on_root"])
    require(sha(root / "release.json") == plan["depends_on_release_sha256"], "Qwen restart release changed")
    if not (root / "runtime/status.json").exists():
        return False, {"status": "not_started"}
    state = read(root / "runtime/status.json")
    require(state.get("status") != "needs_review", "Upstream engineering/infrastructure failure needs review")
    terminal = state.get("status") in ("diagnostic_complete_pending_independent_review", "all_planned_attempted_pending_review")
    if not terminal:
        return False, state
    source_plan, summary = read(root / "task-split.json"), read(root / "reports/summary.json")
    require(state.get("attempted_jobs") == source_plan["expected_jobs"] == summary.get("attempted_jobs")
            and summary.get("not_started_jobs") == 0, "Upstream terminal status lacks complete attempted matrix")
    require(read(root / "runtime/pilot-gate.json").get("status") == "pass", "Upstream engineering pilot did not pass")
    return True, dict(status=state["status"], attempted_jobs=state["attempted_jobs"],
                      unresolved_jobs=summary["unresolved_jobs"], summary_sha256=sha(root / "reports/summary.json"))


def report(root, plan, accepted, unresolved):
    n = plan["expected_prefixes"]
    known = list(accepted.values())
    identities = {row["case_id"]: row for row in known if row["method"] == "identity"}
    attempted = len(accepted) + len(unresolved)
    groups, flags, paired = {}, {}, []
    for method, arm in BRANCHES:
        label = "identity" if method == "identity" else method + "/" + arm
        rows = [r for r in known if r["method"] == method and r["arm"] == arm]
        groups[label] = shared.aggregate(rows, n)
        if method == "identity":
            continue
        matched = [r for r in rows if r["case_id"] in identities]
        first = shared.input_comparison(matched, identities, "first_input")
        later = shared.input_comparison(matched, identities, "mean_post_input")
        all_known = len(matched) == n
        loss = (sum(identities[r["case_id"]]["passed"] - r["passed"] for r in matched) / n * 100) if all_known else None
        flags[label] = dict(matched_identity_pairs=len(matched), missing_pairs=n - len(matched),
                            success_loss_pp=loss, loss_exceeds_3pp=loss > 3 if loss is not None else None,
                            first_input=first, mean_input=later,
                            mean_input_overhead_above_35pct=later["ratio_of_means"] > 1.35 if all_known and later["measured"] == n else None,
                            interpretation="Matched 16384-output-budget continuations; descriptive flags only, no noninferiority claim.")
    for method in shared.METHODS:
        for control, treatment in shared.PAIRS.values():
            left = {r["case_id"]: r for r in known if r["method"] == method and r["arm"] == control}
            right = {r["case_id"]: r for r in known if r["method"] == method and r["arm"] == treatment}
            rows = [dict(case_id=k, family=right[k]["family"], category=right[k]["category"], seed=right[k]["seed"],
                         control_passed=left[k]["passed"], treatment_passed=right[k]["passed"],
                         identity_passed=identities[k]["passed"] if k in identities else None,
                         emitted_call_difference=right[k]["emitted_calls"] - left[k]["emitted_calls"],
                         request_difference=right[k]["model_requests"] - left[k]["model_requests"])
                    for k in sorted(set(left) & set(right))]
            paired.append(dict(method=method, control=control, treatment=treatment, planned_pairs=n,
                               completed_pairs=len(rows), missing_pairs=n - len(rows), pairs=rows,
                               gains=sum(not r["control_passed"] and r["treatment_passed"] for r in rows),
                               losses=sum(r["control_passed"] and not r["treatment_passed"] for r in rows)))
    full = attempted == plan["expected_jobs"]
    status = ("all_planned_attempted_pending_review" if unresolved else "diagnostic_complete_pending_independent_review") if full else "partial_diagnostic"
    result = dict(status=status, expected_prefixes=n, expected_jobs=plan["expected_jobs"],
                  attempted_jobs=attempted, completed_jobs=len(accepted), unresolved_jobs=len(unresolved),
                  not_started_jobs=plan["expected_jobs"] - attempted,
                  output_budgets=dict(source_prefix=4096, matched_identity_continuation=16384, graph_continuation=16384),
                  original_4096_identity_outcomes_used=False, historical_diagnostic_outcomes_reused=False,
                  capability_acceptance_available=full and not unresolved,
                  capability_acceptance="not_assessed_requires_prespecified_paired_family_interval",
                  groups=groups, diagnostic_flags=flags, paired_comparisons=paired,
                  rows=known, unresolved=list(unresolved.values()),
                  limitations=["Original 4096-budget prefixes are common initial conditions; all 19 new continuations use 16384.",
                      "Unrenderable model outputs remain unscored needs-review outcomes, not failures, exclusions, or successful completions.",
                      "All fixed prefixes remain in denominators. Missing outcomes prevent capability acceptance.",
                      "No outcome-based retries or prompt retuning; old diagnostic results are not pooled with this fresh matrix.",
                      "Per-request input means depend on continuation paths. Repeated arguments are not automatically redundant."])
    write(root / "reports/summary.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--snapshot-label", default="restart-v1")
    parser.add_argument("--model", choices=("qwen", "muse"), required=True)
    args = parser.parse_args()
    root, project = args.root.resolve(), args.project.resolve()
    runtime, snapshot = root / "runtime", root / "source_code" / args.snapshot_label
    runtime.mkdir(parents=True, exist_ok=True)
    lock = (runtime / "controller.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    state = dict(pid=os.getpid(), status="starting", stage="release_validation", started_at=time.time(),
                 attempted_jobs=0, completed_jobs=0, unresolved_jobs=0, model=args.model)
    accepted, unresolved = {}, {}

    def update(**values):
        state.update(values, updated_at=time.time())
        write(runtime / "status.json", state)

    try:
        update()
        frozen, release_hash = shared.verify_release(root, snapshot)
        require(Path(__file__).resolve().is_relative_to(snapshot), "Restart must execute its released source snapshot")
        plan = read(root / "task-split.json")
        samples = validate_plan(plan, args.model)
        pins, vendor = read(root / "source-inputs.json"), read(root / "vendor-pins.json")
        shared.verify_hash_map(pins)
        contract = read(runtime / "runtime-contract.json")
        key = "max_tokens" if args.model == "qwen" else "request_max_tokens"
        require(contract.get(key) == 16384, "Runtime contract output budget is not 16384")
        env = dict(os.environ, PYTHONPATH=str(snapshot / "scripts"), PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1")

        def check(sample=None, live=False):
            require(sha(root / "release.json") == release_hash
                    and shared.release_inputs(root, snapshot) == frozen, "Restart release changed")
            shared.verify_hash_map(read(snapshot / "hashes.json"), snapshot)
            shared.verify_hash_map(vendor, snapshot)
            if sample:
                paths = [Path(p) for p in sample["source_paths"].values()]
                relevant = {p: h for p, h in pins.items() if any(Path(p).is_relative_to(base) for base in paths)}
                require(relevant, "No archived source pins for this prefix")
                shared.verify_hash_map(relevant)
            if live:
                shared.check_live_runtime(plan["base_url"], contract)

        while True:
            check()
            ready, evidence = dependency_ready(plan)
            if ready:
                break
            update(status="waiting_for_dependencies", stage="queued_no_inference", dependency=evidence)
            time.sleep(30)
        if evidence:
            write_once(runtime / "dependency-complete.json", evidence)

        def run(sample, method, arm, pilot):
            dest = root / "evaluation" / sample["case_id"] / method / arm
            boot = runtime / "jobs" / sample["case_id"] / method / arm
            module = "workflows.diagnostic_task" if args.model == "qwen" else "workflows.muse_diagnostic_task"
            cmd = [sys.executable, "-m", module, "--task", sample["task"], "--category", sample["category"],
                   "--seed", str(sample["seed"]), "--method", method, "--arm", arm,
                   "--identity", sample["source_paths"]["identity"], "--output", str(dest),
                   "--base-url", plan["base_url"], "--max-output-tokens", "16384"]
            if method != "identity":
                cmd += ["--source-graph", sample["source_paths"][method + "-optimized"]]
            if args.model == "muse":
                cmd += ["--runtime-contract", str(runtime / "runtime-contract.json")]
            check(sample, live=True)
            provenance = dict(command=cmd, release_sha256=release_hash, source_snapshot=str(snapshot),
                              source_hashes=read(snapshot / "hashes.json"))
            update(current=dict(case_id=sample["case_id"], method=method, arm=arm, destination=str(dest)))
            if (dest / "manifest.json").exists():
                saved = read(boot / "launch.json")
                require(all(saved.get(k) == v for k, v in provenance.items()), "Existing attempt is from another release")
            else:
                require((not dest.exists() or not any(dest.iterdir())) and (not boot.exists() or not any(boot.iterdir())),
                        "Partial attempt exists; never retry or overwrite it")
                write_once(boot / "launch.json", dict(provenance, time=time.time()))
                with (boot / "runner.log").open("x") as log:
                    subprocess.run(cmd, cwd=snapshot, env=env, stdout=log, stderr=subprocess.STDOUT, check=False)
            m = read(dest / "manifest.json")
            if m.get("status") in ("complete", "protocol_failure"):
                accepted[str(dest)] = validate_job(dest, sample, method, arm, plan, project, args.model)
            else:
                why = malformed_arguments_evidence(dest)
                row = validate_job(dest, sample, method, arm, plan, project, args.model, allow_unscored=True)
                record = dict(case_id=sample["case_id"], method=method, arm=arm, path=str(dest),
                              evidence=why, recorded_costs=row)
                if not (boot / "needs-review.json").exists():
                    write_once(boot / "needs-review.json", record)
                unresolved[str(dest)] = record
                require(not pilot, "Engineering pilot contains an unscored model-output error; pilot cannot pass")
            check(sample, live=True)
            update(attempted_jobs=len(accepted) + len(unresolved), completed_jobs=len(accepted),
                   unresolved_jobs=len(unresolved), last_attempted=str(dest))

        update(status="running", stage="pilot", expected_jobs=plan["expected_jobs"], expected_prefixes=len(samples))
        for case_id in plan["pilot_case_ids"]:
            for method, arm in BRANCHES:
                run(samples[case_id], method, arm, pilot=True)
        gate = dict(status="pass", gate="engineering_only_no_score_selection", release_sha256=release_hash,
                    pilot_case_ids=plan["pilot_case_ids"], checked_jobs=len(accepted), unresolved_jobs=0,
                    manifest_sha256={p: sha(Path(p) / "manifest.json") for p in accepted})
        if (runtime / "pilot-gate.json").exists():
            require(read(runtime / "pilot-gate.json") == gate, "Existing engineering pilot gate changed")
        else:
            write_once(runtime / "pilot-gate.json", gate)
        report(root, plan, accepted, unresolved)
        update(stage="all_prefixes", pilot_gate="pass")
        for sample in plan["samples"]:
            for method, arm in BRANCHES:
                key = str(root / "evaluation" / sample["case_id"] / method / arm)
                if key not in accepted and key not in unresolved:
                    run(sample, method, arm, pilot=False)
            report(root, plan, accepted, unresolved)
        check()
        shared.verify_hash_map(pins)
        final = report(root, plan, accepted, unresolved)
        require(final["attempted_jobs"] == plan["expected_jobs"], "Not all planned branches were attempted")
        update(status=final["status"], stage="independent_final_review_pending", finished_at=time.time())
    except BaseException as error:
        update(status="needs_review", error=repr(error), failed_at=time.time(),
               attempted_jobs=len(accepted) + len(unresolved), completed_jobs=len(accepted), unresolved_jobs=len(unresolved))
        if "plan" in locals():
            report(root, plan, accepted, unresolved)
        raise
    finally:
        lock.close()


if __name__ == "__main__":
    main()
