"""Queue Muse readout diagnostics behind completed Qwen and Muse studies.

The future cohort is determined only from Muse's own frozen visible prefixes.
Queued authorization pins the selection algorithm; a separate deterministic data
release pins the resulting cohort before any new model inference is allowed.
"""
import argparse
from collections import Counter
import csv
import fcntl
import hashlib
import json
import os
from pathlib import Path
from statistics import mean
import subprocess
import sys
import time
import urllib.parse

from workflows import diagnostic_controller as shared

METHODS, ARMS, PAIRS = shared.METHODS, shared.ARMS, shared.PAIRS
read, sha, write, write_once, require = shared.read, shared.sha, shared.write, shared.write_once, shared.require


def validate_queue(config):
    require(config.get("schema") == "muse-diagnostic-queue-v1", "Unknown Muse queue schema")
    require(config.get("expected_source_identities") == 600 and config.get("poll_seconds") == 30,
            "Queue source coverage or polling protocol changed")
    require(config.get("selection") == "all_muse_actual_mixed_triggered"
            and config.get("pilot_target") == 6, "Outcome-blind selection rule changed")
    require(tuple(config.get("methods", ())) == METHODS and tuple(config.get("arms", ())) == ARMS,
            "Paired diagnostic matrix changed")
    shared.output_budget(config)
    require(config.get("threshold") == 1000 and config.get("context") == 131072
            and config.get("explanation") == "minimal",
            "Diagnostic protocol changed")
    require(config.get("sampling") == dict(temperature=0.6, top_p=0.95, top_k=20, repeat_penalty=1.0),
            "Muse diagnostic sampling changed")
    require(config.get("diagnostic_limits") == shared.DIAGNOSTIC_LIMITS, "Diagnostic limits changed")
    endpoint = urllib.parse.urlparse(config["base_url"])
    require(endpoint.scheme == "http" and endpoint.hostname in ("localhost", "127.0.0.1", "::1")
            and endpoint.path == "/v1", "Muse diagnostics must use the authorized local server")
    for name in ("qwen_root", "muse_source_root"):
        require(Path(config[name]).is_absolute(), "Dependency paths must be absolute")


def queue_inputs(root, snapshot):
    names = ("queue-config.json", "PROTOCOL.md", "runtime/runtime-contract.json",
             "vendor-pins.json", "dependency-pins.json", "queue-preflight.json",
             str((snapshot / "hashes.json").relative_to(root)))
    return {name: sha(root / name) for name in names}


def verify_queue_release(root, snapshot):
    released = read(root / "queue-release.json")
    expected = queue_inputs(root, snapshot)
    require(released.get("status") == "pass" and released.get("input_sha256") == expected,
            "Queue has not been released for these exact sources/configuration")
    require(read(root / "queue-preflight.json").get("status") == "pass", "Queue preflight did not pass")
    shared.verify_hash_map(read(snapshot / "hashes.json"), snapshot)
    shared.verify_hash_map(read(root / "dependency-pins.json"))
    return expected, sha(root / "queue-release.json")


def dependencies(config):
    """Only terminal states authorize selection; a successful pilot is insufficient."""
    qwen, muse = Path(config["qwen_root"]), Path(config["muse_source_root"])
    qstate, mstate = read(qwen / "runtime/status.json"), read(muse / "runtime/status.json")
    for name, state in (("Qwen diagnostic", qstate), ("Muse transfer", mstate)):
        require(state.get("status") not in ("needs_review", "error", "failed", "infrastructure_error", "protocol_failure"),
                f"{name} dependency requires review; queued diagnostics will not retry or bypass it")
    ready = (qstate.get("status") == "diagnostic_complete_pending_independent_review"
             and qstate.get("completed_jobs") == 1458
             and mstate.get("status") == "inference_complete_pending_independent_audit"
             and mstate.get("completed_jobs") == 4200)
    evidence = dict(qwen=qstate, muse=mstate)
    if ready:
        report_path = qwen / "reports/summary.json"
        report = read(report_path)
        require(report.get("status") == "diagnostic_complete_pending_independent_review"
                and report.get("expected_prefixes") == 81 and report.get("expected_graph_jobs") == 1458
                and report.get("completed_graph_jobs") == 1458 and report.get("incomplete_graph_jobs") == 0,
                "Qwen status is terminal but its final integrity report is incomplete")
        evidence["qwen_final_report_sha256"] = sha(report_path)
        pilot_path = qwen / "runtime/pilot-gate.json"
        pilot = read(pilot_path)
        qplan = read(qwen / "task-split.json")
        require(pilot.get("status") == "pass" and pilot.get("gate") == "engineering_only_no_score_selection"
                and pilot.get("pilot_case_ids") == qplan["pilot_case_ids"]
                and pilot.get("checked_jobs") == len(qplan["pilot_case_ids"]) * 18
                and pilot.get("release_sha256") == sha(qwen / "release.json"),
                "Qwen completed status lacks its approved engineering pilot gate")
        evidence["qwen_pilot_gate_sha256"] = sha(pilot_path)
    return ready, evidence


def completed_source_coverage(config):
    """Validate all 4200 original slots, including untriggered graph markers."""
    source = Path(config["muse_source_root"])
    plan = read(source / "task-split.json")
    require(len(plan["tasks"]) == 200 and len(plan["seeds"]) == 3
            and plan.get("identity_runs") == 600, "Muse source no longer describes 600 Identity runs")
    require(len({task["family"] for task in plan["tasks"]}) == 50, "Muse source family count changed")
    paths = list((source / "evaluation").glob("*/seed*/*/manifest.json"))
    require(len(paths) == 4200, "Muse source matrix is not completely materialized")
    report = read(source / "reports/summary.json")
    audit = read(source / "reports/mechanical-audit.json")
    require(report.get("identity_runs") == 600 and audit.get("status") == "pass",
            "Muse source final report/audit is incomplete")
    seen, complete_slots, triggered = set(), 0, 0
    for task in plan["tasks"]:
        for seed in plan["seeds"]:
            base = source / "evaluation" / task["id"] / f"seed{seed}"
            identity = read(base / "identity/manifest.json")
            require(identity.get("status") == "complete", "Unfinished source Identity")
            triggered += bool(identity.get("triggered"))
            for label in ("identity", *(m + suffix for m in METHODS for suffix in ("-baseline", "-optimized"))):
                path = base / label / "manifest.json"
                item = read(path)
                expected_status = "complete" if label == "identity" or identity.get("triggered") else "not_triggered"
                require(item.get("status") == expected_status, f"Unfinished or inconsistent source slot: {path}")
                complete_slots += expected_status == "complete"
                require(item.get("task") == task["id"] and item.get("seed") == seed
                        and item.get("category") == task["category"], "Source slot configuration mismatch")
                seen.add(str(path.resolve()))
    require(seen == {str(path.resolve()) for path in paths}, "Unexpected Muse source slots")
    # The original mechanical audit counts real runs; not_triggered markers are
    # retained in the 4200-slot coverage above but contain no API executions.
    require(audit.get("records") == complete_slots == 600 + 6 * triggered
            and report.get("triggered_prefixes") == triggered,
            "Muse real-run audit and complete marker matrix disagree")
    return plan


def semantic_risks(history):
    """Fail closed on known adapter hazards without guessing hidden aliases."""
    from core.mixed_observations import parse_visible_return, tool_spec
    pending, findings = {}, []
    for index, message in enumerate(history):
        if message.get("type") == "function_call":
            pending[message["call_id"]] = (index, message)
        elif message.get("type") == "function_call_output":
            require(message["call_id"] in pending, "Unpaired visible tool return")
            call_index, call = pending.pop(message["call_id"])
            output = parse_visible_return(message.get("output"))
            spec = tool_spec(call["name"])
            if (spec["domain"] == "TwitterAPI" and spec["method"] == "mention"
                    and isinstance(output, dict)
                    and output.get("mention_status") == "Users mentioned successfully"):
                findings.append(dict(kind="successful_mention_aliasing_review_required", call_message=call_index,
                                     return_message=index, tool=call["name"],
                                     interpretation="Conservative reachability gate; shared-alias damage is not inferred."))
            if isinstance(output, dict) and "error" in output and output["error"] == "":
                findings.append(dict(kind="empty_error_wrapper", call_message=call_index,
                                     return_message=index, tool=call["name"]))
    require(not pending, "Conversion boundary has pending calls")
    return findings


def select_pilot(samples, target=6):
    """Deterministic set cover using only domains, conditions and reference use."""
    require(len(samples) >= 4, "Fewer than four eligible Muse prefixes require explicit design review")
    selected, covered = [], set()
    remaining = sorted(samples, key=lambda row: row["case_id"])
    while remaining and len(selected) < min(target, len(samples)):
        best = min(remaining, key=lambda row: (-len(set(row["pilot_features"]) - covered), row["case_id"]))
        selected.append(best["case_id"])
        covered.update(best["pilot_features"])
        remaining.remove(best)
    return selected


def prepare_data(root, config, dependency_evidence):
    """Read only original results; select on prefix eligibility, never outcomes."""
    from core import lossless_state, lossless_event, optimized_graph
    from core.mixed_observations import tool_spec
    from core.muse_transport import MODEL_NAME, MODEL_KEY, REASONING_POLICY, digest
    from workflows.muse_task import all_paired
    from workflows.diagnostic_task import prepare_replacement

    source = Path(config["muse_source_root"])
    source_plan = completed_source_coverage(config)
    require(not (root / "data-release.json").exists(), "Data already released")
    for name in ("task-split.json", "source-inputs.json", "preparation-audit.json", "coverage.json"):
        require(not (root / name).exists(), f"Partial preparation needs review; refusing overwrite: {name}")
    pins = {str(path.resolve()): sha(path) for path in (source / "evaluation").glob("*/seed*/*/manifest.json")}
    for name in ("reports/summary.json", "reports/mechanical-audit.json"):
        pins[str((source / name).resolve())] = sha(source / name)
    coverage, samples, risks, offline = [], [], [], []

    def source_json(path):
        raw = path.read_bytes()
        pins[str(path.resolve())] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw)

    for task in source_plan["tasks"]:
        for seed in source_plan["seeds"]:
            base = source / "evaluation" / task["id"] / f"seed{seed}"
            identity_path = base / "identity"
            m = source_json(identity_path / "manifest.json")
            expected = dict(model=MODEL_NAME, model_key=MODEL_KEY, reasoning_policy=REASONING_POLICY,
                            status="complete", method="identity", task=task["id"], category=task["category"],
                            seed=seed, threshold=1000, context=131072,
                            max_tokens=shared.SOURCE_MAX_OUTPUT_TOKENS, sampling=config["sampling"])
            require(all(m.get(k) == v for k, v in expected.items()), "Source is not the registered Muse configuration")
            sample_id = f"muse_transfer_v1/{task['id']}/seed{seed}"
            case_id = "prefix-" + hashlib.sha256(sample_id.encode()).hexdigest()[:16]
            cover = dict(case_id=case_id, sample_id=sample_id, task=task["id"], family=task["family"],
                         category=task["category"], seed=seed, triggered=bool(m["triggered"]), selected=False)
            coverage.append(cover)
            # Pin every manifest and retain every nontriggered coverage record;
            # full visible input is needed only where a conversion exists.
            if not m["triggered"]:
                cover["reason"] = "working_context_never_exceeded_threshold"
                continue
            api = source_json(identity_path / "api.json")
            accounting = source_json(identity_path / "accounting.json")
            history = source_json(identity_path / "checkpoint-history.json")
            boundary = m["trigger_index"]
            eligible = [a["index"] for a in accounting if a["working_tokens"] > 1000
                        and all_paired(api[a["index"]]["request"]["input"])]
            require(eligible and boundary == eligible[0], "Muse threshold is not its earliest eligible native boundary")
            require(history == api[boundary]["request"]["input"]
                    and digest(history) == m["checkpoint_sha256"], "Source Muse prefix mismatch")
            count = next(row for row in accounting if row["index"] == boundary)
            require(count["working_tokens"] == m["source_work_tokens"] > 1000, "Native threshold count mismatch")
            calls = [message for message in history if message.get("type") == "function_call"]
            nonfile = [tool_spec(call["name"]) for call in calls
                       if tool_spec(call["name"])["domain"] not in ("GorillaFileSystem", "Unknown")]
            cover["nonfilesystem_domains"] = sorted({item["domain"] for item in nonfile})
            cover["source_work_tokens"] = count["working_tokens"]
            if not nonfile:
                cover["reason"] = "no_known_nonfilesystem_call_in_visible_prefix"
                continue
            cover.update(selected=True, reason="all_triggered_actual_mixed_prefixes")
            findings = semantic_risks(history)
            risks.extend(dict(case_id=case_id, **finding) for finding in findings)
            # Selection never checks passed/score. Scores are pinned for later reporting.
            for name in ("native.jsonl", "full.json", "official-score.json"):
                pins[str((identity_path / name).resolve())] = sha(identity_path / name)
            score = read(identity_path / "official-score.json")
            pins[str((identity_path / score["score_file"]).resolve())] = sha(identity_path / score["score_file"])
            results = list((identity_path / "result").rglob(f"*{task['category']}_result.json"))
            require(len(results) == 1, "Missing official Identity result")
            pins[str(results[0].resolve())] = sha(results[0])
            paths = dict(identity=str(identity_path.resolve()))
            features = ["domain:" + domain for domain in cover["nonfilesystem_domains"]]
            features.append("condition:" + task["category"])
            for method in METHODS:
                graph_path = base / (method + "-optimized")
                gm = source_json(graph_path / "manifest.json")
                meta = source_json(graph_path / "memory-metadata.json")
                graph_checkpoint = source_json(graph_path / "checkpoint-history.json")
                require(gm["status"] == "complete" and gm["checkpoint_sha256"] == m["checkpoint_sha256"]
                        and gm["model"] == MODEL_NAME and gm["reasoning_policy"] == REASONING_POLICY
                        and graph_checkpoint == history, "Archived Muse graph is not paired to its own Identity")
                codec = lossless_state if method == "state" else lossless_event
                require(optimized_graph._same(codec.decode(meta["encoded"]), meta["graph"])
                        and optimized_graph._same(optimized_graph.restore_history(meta["graph"]),
                                                 [item for item in history if item.get("role") not in ("system", "developer")]),
                        "Archived Muse graph is not lossless at its own checkpoint")
                by_arm = {}
                for arm in ARMS:
                    messages, evidence = prepare_replacement(history, meta, method, arm, len)
                    by_arm[arm] = messages
                    offline.append(dict(case_id=case_id, method=method, arm=arm,
                                        typed_payload_exact=evidence["payload_decode_exact"],
                                        source_history_exact=evidence["source_history_exact"], diagnostic=evidence["diagnostic"]))
                    if arm == "refs_control":
                        nonempty = evidence["diagnostic"]["expanded_references"] > 0
                        features.append(f"references:{method}:{'nonempty' if nonempty else 'empty'}")
                ref_audit = next(row for row in reversed(offline)
                                 if row["case_id"] == case_id and row["method"] == method and row["arm"] == "refs_expanded")
                if not ref_audit["diagnostic"]["expanded_references"]:
                    require(by_arm["refs_control"] == by_arm["refs_expanded"], "Zero-reference negative control changed input")
                paths[method + "-optimized"] = str(graph_path.resolve())
            samples.append(dict(case_id=case_id, sample_id=sample_id, task=task["id"], family=task["family"],
                                category=task["category"], seed=seed, semantics=task["semantics"],
                                checkpoint_sha256=m["checkpoint_sha256"], source_paths=paths,
                                nonfilesystem_domains=cover["nonfilesystem_domains"], pilot_features=sorted(set(features))))
    shared.verify_hash_map(pins)
    audit = dict(status="needs_review" if risks else "pass", no_inference=True,
                 identity_coverage=len(coverage), actual_mixed_prefixes=len(samples),
                 families=len({row["family"] for row in samples}), semantic_risks=risks,
                 semantic_gate="Any successful mention or empty error wrapper blocks new inference for review; no silent repair or exclusion.",
                 prepared_inputs=offline, selection_uses_outcomes=False)
    write_once(root / "preparation-audit.json", audit)
    write_once(root / "coverage.json", coverage)
    write_once(root / "source-inputs.json", pins)
    require(not risks, "Known adapter semantic hazard present in Muse prefixes; independent review required before inference")
    pilot = select_pilot(samples, config["pilot_target"])
    plan = dict(schema="muse-mixed-diagnostic-v1", expected_prefixes=len(samples), expected_graph_jobs=len(samples) * 18,
                samples=samples, pilot_case_ids=pilot, methods=list(METHODS), arms=list(ARMS),
                model=MODEL_NAME, model_key=MODEL_KEY, reasoning_policy=REASONING_POLICY,
                sampling=config["sampling"], threshold=1000, context=131072,
                max_tokens=shared.output_budget(config), source_max_tokens=shared.SOURCE_MAX_OUTPUT_TOKENS,
                explanation="minimal", base_url=config["base_url"], diagnostic_limits=config["diagnostic_limits"],
                coverage=dict(source_identities=600, selected=len(samples), excluded=600-len(samples)),
                inference_policy="Frozen Muse own prefixes; exactly one replacement, then append-only history")
    write_once(root / "task-split.json", plan)
    write_once(root / "runtime/dependencies-complete.json", dependency_evidence)
    return plan


def data_inputs(root):
    return {name: sha(root / name) for name in ("task-split.json", "source-inputs.json", "coverage.json",
            "preparation-audit.json", "runtime/dependencies-complete.json", "runtime/native-input-preflight.json")}


def native_preflight(root, plan):
    """Full model-specific input counts; template/tokenize endpoints only."""
    from core.graph_memory_replace import retained_instructions
    from core.generation_budget import request_with_output_budget
    from core.muse_transport import NativeTokenizer, chat_messages, digest
    from workflows.muse_task import request_body, post
    from workflows.muse_diagnostic_task import MUSE_USER_BOUNDARY, prepare_replacement
    rows, tok = [], NativeTokenizer(plan["base_url"])
    live_budget = shared.output_budget(plan)
    try:
        for sample in plan["samples"]:
            identity = Path(sample["source_paths"]["identity"])
            manifest = read(identity / "manifest.json")
            boundary = manifest["trigger_index"]
            req = read(identity / "api.json")[boundary]["request"]
            history = read(identity / "checkpoint-history.json")
            fixed = retained_instructions(history)
            seed = sample["seed"] + boundary * 1000003
            fixed_body = request_with_output_budget(request_body, dict(req, input=fixed), seed, live_budget)
            fixed_prompt = post(plan["base_url"], "/apply-template", fixed_body)["prompt"]
            fixed_tokens = tok.count(fixed_prompt, parse_special=True)
            for method in METHODS:
                metadata = read(Path(sample["source_paths"][method + "-optimized"]) / "memory-metadata.json")
                prompts, audits = {}, {}
                for arm in ARMS:
                    messages, meta = prepare_replacement(history, metadata, method, arm, len)
                    body = request_with_output_budget(request_body, dict(req, input=[*fixed, *messages]), seed, live_budget)
                    prompt = post(plan["base_url"], "/apply-template", body)["prompt"]
                    tokens = tok.count(prompt, parse_special=True)
                    require(tokens >= fixed_tokens, "Invalid Muse-native fixed overhead subtraction")
                    prompts[arm], audits[arm] = prompt, meta["diagnostic"]
                    rows.append(dict(case_id=sample["case_id"], method=method, arm=arm,
                                     full_input_tokens=tokens, fixed_tokens=fixed_tokens,
                                     working_tokens=tokens-fixed_tokens, output_reservation=live_budget,
                                     native_request_sha256=digest(body),
                                     prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
                                     native_context_would_reject=tokens + live_budget > plan["context"]))
                goal = audits["goal_inline"]
                original = goal["unmodified_memory"] + goal["goal_view"]
                require(prompts["goal_inline"].count(original) == 1,
                        "Muse native goal view is absent or ambiguous")
                expected = prompts["goal_inline"].replace(original,
                    goal["unmodified_memory"] + MUSE_USER_BOUNDARY + goal["goal_view"], 1)
                require(prompts["goal_separate"] == expected, "Muse native goal arms differ beyond message boundary")
                if not audits["refs_control"]["expanded_references"]:
                    require(prompts["refs_control"] == prompts["refs_expanded"], "Muse native negative control differs")
                if not audits["index_control"]["eligible_entries"]:
                    require(prompts["index_control"] == prompts["index_view"], "Muse native empty index control differs")
            tok.cache.clear()
    finally:
        tok.close()
    result = dict(status="pass", inference_calls=0, max_output_tokens=live_budget,
                  source_max_output_tokens=shared.SOURCE_MAX_OUTPUT_TOKENS,
                  tokenization="Muse native add_special=true parse_special=true",
                  prepared_inputs=len(rows), expected_inputs=plan["expected_graph_jobs"],
                  initial_context_limit_cases=sum(row["native_context_would_reject"] for row in rows), rows=rows)
    require(len(rows) == plan["expected_graph_jobs"], "Incomplete full native input preparation")
    write_once(root / "runtime/native-input-preflight.json", result)
    return result


def validate_job(path, sample, method, arm, plan, project):
    from core.muse_transport import MODEL_NAME, MODEL_KEY, REASONING_POLICY
    expected = dict(model=MODEL_NAME, model_key=MODEL_KEY, reasoning_policy=REASONING_POLICY,
                    semantics=sample["semantics"])
    for directory in (path, Path(sample["source_paths"]["identity"])):
        m = read(directory / "manifest.json")
        require(all(m.get(k) == v for k, v in expected.items()), "Muse model/reasoning/semantic configuration mismatch")
    return shared.validate_job(path, sample, method, arm, plan, project, transport="muse")


def report(root, plan, project, checked=None):
    total, identity, rows, missing, requests = plan["expected_prefixes"], {}, [], [], []
    for sample in plan["samples"]:
        path = Path(sample["source_paths"]["identity"])
        shared.score_evidence(path, read(path / "manifest.json"))
        identity[sample["case_id"]] = shared.run_metrics(path, sample, "identity", "historical_identity", True)
        for method in METHODS:
            for arm in ARMS:
                path = root / "evaluation" / sample["case_id"] / method / arm
                m = read(path / "manifest.json") if (path / "manifest.json").exists() else {}
                if m.get("status") not in ("complete", "protocol_failure"):
                    missing.append(dict(case_id=sample["case_id"], method=method, arm=arm,
                                        status=m.get("status", "not_started"), error=m.get("error")))
                    continue
                row = checked.get(str(path)) if checked is not None else None
                row = row or validate_job(path, sample, method, arm, plan, project)
                rows.append(row)
                requests.extend(dict(case_id=sample["case_id"], method=method, arm=arm,
                                     run_seed=sample["seed"], **a) for a in read(path / "accounting.json"))
    groups = {"identity": shared.aggregate(list(identity.values()), total)}
    budget_comparison = shared.output_budget_comparison(plan, identity)
    identity_acceptance = budget_comparison["identity_acceptance_available"]
    flags, comparisons = {}, []
    for method in METHODS:
        for arm in ARMS:
            selected = [row for row in rows if row["method"] == method and row["arm"] == arm]
            label = method + "/" + arm
            groups[label] = shared.aggregate(selected, total)
            first = shared.input_comparison(selected, identity, "first_input")
            later = shared.input_comparison(selected, identity, "mean_post_input")
            loss = ((sum(row["passed"] for row in identity.values())-sum(row["passed"] for row in selected))
                    / total*100 if len(selected) == total else None)
            flags[label] = dict(success_loss_pp=loss,
                                identity_acceptance_available=identity_acceptance,
                                loss_exceeds_3pp=loss > 3 if identity_acceptance and loss is not None else None,
                                first_input=first, mean_input=later,
                                mean_input_overhead_above_35pct=later["ratio_of_means"] > 1.35 if identity_acceptance and later["measured"] == total else None,
                                interpretation=("Report-only diagnostic, not noninferiority or mechanism evidence"
                                    if identity_acceptance else budget_comparison["interpretation"]))
        for control, treatment in PAIRS.values():
            left = {r["case_id"]: r for r in rows if r["method"] == method and r["arm"] == control}
            right = {r["case_id"]: r for r in rows if r["method"] == method and r["arm"] == treatment}
            paired = [dict(case_id=key, family=right[key]["family"], category=right[key]["category"],
                           seed=right[key]["seed"], control_passed=left[key]["passed"],
                           treatment_passed=right[key]["passed"], identity_passed=identity[key]["passed"],
                           emitted_call_difference=right[key]["emitted_calls"]-left[key]["emitted_calls"],
                           model_request_difference=right[key]["model_requests"]-left[key]["model_requests"])
                      for key in sorted(set(left) & set(right))]
            comparisons.append(dict(method=method, control=control, treatment=treatment,
                                    planned_pairs=total, completed_pairs=len(paired), missing_pairs=total-len(paired),
                                    gains=sum(not p["control_passed"] and p["treatment_passed"] for p in paired),
                                    losses=sum(p["control_passed"] and not p["treatment_passed"] for p in paired), pairs=paired))
    summary = dict(status="diagnostic_complete_pending_independent_review" if not missing else "partial_diagnostic",
                   model=plan["model"], expected_prefixes=total, expected_graph_jobs=total*18,
                   completed_graph_jobs=len(rows), incomplete_graph_jobs=len(missing),
                   groups=groups, diagnostic_flags=flags, paired_comparisons=comparisons,
                   output_budget_comparison=budget_comparison,
                   identity_rows=list(identity.values()), rows=rows, incomplete=missing,
                   source_coverage=plan["coverage"], pilot_case_ids=plan["pilot_case_ids"],
                   negative_controls=[dict(case_id=r["case_id"], method=r["method"], arm=r["arm"],
                                           audit=r.get("diagnostic_audit", {})) for r in rows if r["arm"].startswith(("index_", "refs_"))],
                   limitations=["Own Muse prefixes selected only after all 600 Identity and 3600 graph slots completed.",
                       budget_comparison["interpretation"],
                       "All and actual-mixed are the same selected cohort here; this is not a 600-prefix efficacy claim.",
                       "N is fixed at data release and is not forced to equal Qwen's 81.",
                       "No pruning, semantic repair, score-based filtering, arm selection, automatic retry, or independent-confirmation claim.",
                       "Protocol failure counts as unsuccessful without fabricating an official score; rejected inputs are not charged.",
                       "Repeated calls are candidates, not automatically redundant. Later input costs depend on continuation paths.",
                       "Native Muse tokenizer and reasoning policy differ from Qwen; cross-model token counts are not interchangeable."])
    write(root / "reports/summary.json", summary)
    if requests:
        target = root / "reports/per-request-input.csv"
        columns = list(dict.fromkeys(key for row in requests for key in row))
        with target.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            writer.writerows(requests)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--snapshot-label", default="readout-v1")
    args = parser.parse_args()
    root, project = args.root.resolve(), args.project.resolve()
    runtime, snapshot = root / "runtime", root / "source_code" / args.snapshot_label
    runtime.mkdir(parents=True, exist_ok=True)
    lock = (runtime / "controller.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    state = dict(pid=os.getpid(), status="starting", started_at=time.time(), completed_jobs=0,
                 source_snapshot=str(snapshot), new_inference_started=False)
    checked = {}

    def update(**values):
        state.update(values, updated_at=time.time())
        write(runtime / "status.json", state)

    try:
        update(stage="queue_release_validation")
        frozen, release_hash = verify_queue_release(root, snapshot)
        require(Path(__file__).resolve().is_relative_to(snapshot.resolve()), "Queue must run from its frozen source snapshot")
        config = read(root / "queue-config.json")
        validate_queue(config)
        require(config["snapshot_label"] == args.snapshot_label, "Snapshot label differs from queue plan")
        source_contract = read(runtime / "runtime-contract.json")
        require(source_contract.get("request_max_tokens") == shared.output_budget(config),
                "Muse runtime contract and registered live output budget differ")
        env = dict(os.environ, PYTHONPATH=str(snapshot / "scripts"), PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1")

        def check_queue():
            require(queue_inputs(root, snapshot) == frozen and sha(root / "queue-release.json") == release_hash,
                    "Released queue configuration changed")
            shared.verify_hash_map(read(snapshot / "hashes.json"), snapshot)
            shared.verify_hash_map(read(root / "dependency-pins.json"))
            shared.verify_hash_map(read(root / "vendor-pins.json"), snapshot)

        # The wait loop never calls inference, tokenization, templates or runtime endpoints.
        while True:
            check_queue()
            ready, evidence = dependencies(config)
            if ready:
                break
            update(status="waiting_for_dependencies", stage="queued_no_inference",
                   dependencies={name: {key: value.get(key) for key in ("status", "stage", "completed_jobs")}
                                 for name, value in evidence.items()})
            time.sleep(config["poll_seconds"])
        update(status="preparing", stage="freeze_muse_own_prefixes")
        completed_source_coverage(config)
        shared.check_live_runtime(config["base_url"], source_contract)
        if (root / "data-release.json").exists():
            data_release = read(root / "data-release.json")
            require(data_release.get("status") == "pass" and data_release.get("queue_release_sha256") == release_hash
                    and data_release.get("input_sha256") == data_inputs(root), "Existing data release changed")
            plan = read(root / "task-split.json")
        else:
            plan = prepare_data(root, config, evidence)
            update(stage="native_full_input_preflight", expected_prefixes=plan["expected_prefixes"],
                   expected_graph_jobs=plan["expected_graph_jobs"])
            native_preflight(root, plan)
            shared.check_live_runtime(config["base_url"], source_contract)
            data_release = dict(status="pass", kind="automatic deterministic release under frozen queue authorization",
                                queue_release_sha256=release_hash, input_sha256=data_inputs(root),
                                expected_prefixes=plan["expected_prefixes"], expected_graph_jobs=plan["expected_graph_jobs"])
            write_once(root / "data-release.json", data_release)
        data_release_hash = sha(root / "data-release.json")
        pins = read(root / "source-inputs.json")
        shared.verify_hash_map(pins)
        samples = {sample["case_id"]: sample for sample in plan["samples"]}
        require(len(samples) == plan["expected_prefixes"] and plan["expected_graph_jobs"] == len(samples)*18,
                "Released dynamic denominator changed")

        def check(sample=None):
            check_queue()
            require(sha(root / "data-release.json") == data_release_hash
                    and data_inputs(root) == data_release["input_sha256"], "Frozen diagnostic data changed")
            if sample:
                roots = [Path(value) for value in sample["source_paths"].values()]
                shared.verify_hash_map({name: value for name, value in pins.items()
                                        if any(Path(name).is_relative_to(directory) for directory in roots)})
            shared.check_live_runtime(config["base_url"], source_contract)

        def run(sample, method, arm):
            dest = root / "evaluation" / sample["case_id"] / method / arm
            boot = runtime / "jobs" / sample["case_id"] / method / arm
            command = [sys.executable, "-m", "workflows.muse_diagnostic_task", "--task", sample["task"],
                       "--category", sample["category"], "--seed", str(sample["seed"]), "--method", method,
                       "--arm", arm, "--identity", sample["source_paths"]["identity"],
                       "--source-graph", sample["source_paths"][method+"-optimized"], "--output", str(dest),
                       "--base-url", config["base_url"], "--runtime-contract", str(runtime / "runtime-contract.json"),
                       "--max-output-tokens", str(shared.output_budget(plan))]
            check(sample)
            launch = dict(command=command, source_snapshot=str(snapshot), source_hashes=read(snapshot / "hashes.json"),
                          queue_release_sha256=release_hash, data_release_sha256=data_release_hash)
            update(current=dict(case_id=sample["case_id"], method=method, arm=arm, destination=str(dest)))
            if (dest / "manifest.json").exists():
                saved = read(boot / "launch.json")
                require(all(saved.get(k) == v for k, v in launch.items()), "Existing job belongs to a different release")
            else:
                require((not dest.exists() or not any(dest.iterdir())) and
                        (not boot.exists() or not any(boot.iterdir())), "Previous partial attempt requires review, not retry")
                write_once(boot / "launch.json", dict(launch, time=time.time()))
                update(new_inference_started=True)
                with (boot / "runner.log").open("x") as log:
                    result = subprocess.run(command, cwd=snapshot, env=env, stdout=log, stderr=subprocess.STDOUT, check=False)
                require(result.returncode == 0, f"Muse task process failed ({result.returncode}); no retry: {dest}")
            checked[str(dest)] = validate_job(dest, sample, method, arm, plan, project)
            check(sample)
            update(completed_jobs=len(checked), last_completed=str(dest))

        update(status="running", stage="pilot", expected_prefixes=len(samples), expected_graph_jobs=len(samples)*18)
        for case_id in plan["pilot_case_ids"]:
            for method in METHODS:
                for arm in ARMS:
                    run(samples[case_id], method, arm)
        gate = dict(status="pass", gate="engineering_only_no_score_selection", data_release_sha256=data_release_hash,
                    pilot_case_ids=plan["pilot_case_ids"], checked_jobs=len(checked),
                    manifest_sha256={path: sha(Path(path)/"manifest.json") for path in checked})
        if (runtime / "pilot-gate.json").exists():
            require(read(runtime / "pilot-gate.json") == gate, "Existing pilot gate changed")
        else:
            write_once(runtime / "pilot-gate.json", gate)
        report(root, plan, project, checked)
        update(stage="all_released_muse_prefixes", pilot_gate="pass")
        for sample in plan["samples"]:
            for method in METHODS:
                for arm in ARMS:
                    if str(root / "evaluation" / sample["case_id"] / method / arm) not in checked:
                        run(sample, method, arm)
            report(root, plan, project, checked)
        check()
        shared.verify_hash_map(pins)
        final = report(root, plan, project)
        require(final["completed_graph_jobs"] == len(samples)*18 and not final["incomplete"], "Incomplete final Muse diagnostic")
        update(status="diagnostic_complete_pending_independent_review", stage="independent_final_review_pending",
               completed_jobs=len(samples)*18, finished_at=time.time())
    except BaseException as error:
        update(status="needs_review", error=repr(error), failed_at=time.time())
        if "plan" in locals():
            try:
                report(root, plan, project, checked)
            except BaseException as reporting_error:
                update(report_error=repr(reporting_error))
        raise
    finally:
        lock.close()


if __name__ == "__main__":
    main()
