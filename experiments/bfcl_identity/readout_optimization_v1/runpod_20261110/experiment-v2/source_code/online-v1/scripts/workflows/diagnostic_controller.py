"""Frozen paired readout diagnostics: engineering pilot, then all 81 prefixes.

This controller never selects an arm from its task score. Completed failures are
data; incomplete or unverifiable attempts stop for review without being retried.
"""
import argparse
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
import urllib.request

METHODS = ("state", "event", "dedup")
PAIRS = {"goal": ("goal_inline", "goal_separate"),
         "index": ("index_control", "index_view"),
         "refs": ("refs_control", "refs_expanded")}
ARMS = tuple(arm for pair in PAIRS.values() for arm in pair)
EXPECTED_PREFIXES = 81
EXPECTED_JOBS = EXPECTED_PREFIXES * len(METHODS) * len(ARMS)
SOURCE_MAX_OUTPUT_TOKENS = 4096
ALLOWED_MAX_OUTPUT_TOKENS = (4096, 16384)
DIAGNOSTIC_LIMITS = dict(input_overhead_fraction=0.35, capability_loss_pp=3, L_max=None,
                         input_gate_strata=["all", "actual_mixed"],
                         diagnostic_cost_exceedance_is_not_stop=True)
ENGINEERING_FLAGS = ("official_score_verified", "prefix_replay_exact",
                     "replacement_delivered_exact", "append_only_after_conversion",
                     "native_input_counts_verified", "payload_decode_exact",
                     "native_requests_match_expected", "source_files_unchanged")


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write(path, value):
    """Only mutable status/derived reports use atomic replacement."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def write_once(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def source_path(project, name):
    path = Path(name)
    return path.resolve() if path.is_absolute() else (project / path).resolve()


def output_budget(plan):
    value = plan.get("max_tokens")
    require(type(value) is int and value in ALLOWED_MAX_OUTPUT_TOKENS,
            "Output budget must be an explicitly registered 4096 or 16384 tokens")
    return value


def output_budget_comparison(plan, identity):
    """Different continuation budgets cannot validate memory-only acceptance."""
    live = output_budget(plan)
    observed = sorted({row["max_output_tokens"] for row in identity.values()})
    require(observed == [SOURCE_MAX_OUTPUT_TOKENS], "Historical Identity output budget changed")
    matched = live == SOURCE_MAX_OUTPUT_TOKENS
    return dict(historical_identity_max_output_tokens=SOURCE_MAX_OUTPUT_TOKENS,
                candidate_max_output_tokens=live, matched_output_budget=matched,
                identity_acceptance_available=matched,
                identity_comparison_status="matched_output_budget" if matched else "descriptive_only_output_budget_mismatch",
                within_diagnostic_pairs_budget_matched=True,
                interpretation=("Identity and diagnostic continuations share the output budget."
                    if matched else "Historical Identity used 4096 output tokens; new continuations use 16384. "
                    "Identity differences are descriptive and do not isolate the memory transformation. "
                    "Capability and input-overhead acceptance flags are unavailable until a matched Identity continuation exists."))


def validate_plan(plan):
    require(plan.get("schema") == "mixed-diagnostic-v1", "Unknown diagnostic plan schema")
    require(plan.get("expected_prefixes") == EXPECTED_PREFIXES, "Fixed denominator must be 81")
    require(tuple(plan.get("methods", ())) == METHODS, "Method order/configuration changed")
    require(tuple(plan.get("arms", ())) == ARMS, "Paired arm matrix changed")
    output_budget(plan)
    require(plan.get("threshold") == 1000 and plan.get("context") == 131072
            and plan.get("explanation") == "minimal",
            "Protocol configuration changed")
    require(plan.get("sampling") == dict(temperature=0.6, top_p=0.95, top_k=20, repeat_penalty=1.0),
            "Sampling configuration changed")
    require(plan.get("diagnostic_limits") == DIAGNOSTIC_LIMITS,
            "Diagnostic report tolerances changed")
    samples = plan.get("samples", [])
    require(len(samples) == EXPECTED_PREFIXES, "Expected exactly 81 frozen prefixes")
    ids = [row["case_id"] for row in samples]
    require(len(ids) == len(set(ids)), "Duplicate prefix IDs")
    require(len({row["sample_id"] for row in samples}) == EXPECTED_PREFIXES,
            "Duplicate historical sample")
    for row in samples:
        require(row["case_id"].startswith("prefix-") and Path(row["case_id"]).name == row["case_id"],
                "Unsafe case identifier")
        require(type(row["seed"]) is int and isinstance(row["task"], str), "Invalid task/seed")
        require(set(row["source_paths"]) == {"identity", *(m + "-optimized" for m in METHODS)},
                "Missing frozen source arm")
    pilot = plan.get("pilot_case_ids", [])
    require(4 <= len(pilot) <= 6 and len(set(pilot)) == len(pilot)
            and set(pilot) <= set(ids), "Expected 4–6 predeclared pilot prefixes")
    endpoint = urllib.parse.urlparse(plan["base_url"])
    require(endpoint.scheme == "http" and endpoint.hostname in ("localhost", "127.0.0.1", "::1")
            and endpoint.path == "/v1", "Diagnostic inference must use the declared local server")
    return {row["case_id"]: row for row in samples}


def release_inputs(root, snapshot):
    names = ("task-split.json", "PROTOCOL.md", "runtime/runtime-contract.json",
             "vendor-pins.json", "source-inputs.json", "preflight-review.json",
             str((snapshot / "hashes.json").relative_to(root)))
    return {name: sha(root / name) for name in names}


def verify_hash_map(paths, root=None):
    for name, expected in paths.items():
        path = Path(name) if root is None else root / name
        require(sha(path) == expected, f"Pinned input changed: {path}")


def verify_release(root, snapshot):
    release = read(root / "release.json")
    expected = release_inputs(root, snapshot)
    require(release.get("status") == "pass" and release.get("preflight_status") == "pass",
            "Root release/preflight approval is missing")
    require(release.get("input_sha256") == expected, "Release does not match exact frozen inputs")
    require(read(root / "preflight-review.json").get("status") == "pass",
            "Independent engineering preflight did not pass")
    verify_hash_map(read(snapshot / "hashes.json"), snapshot)
    return expected, sha(root / "release.json")


def check_live_runtime(base_url, contract):
    require(contract.get("base_url") == base_url, "Runtime endpoint does not match frozen contract")
    base = base_url.removesuffix("/v1")
    with urllib.request.urlopen(base + "/props", timeout=30) as stream:
        props = json.load(stream)
    expected = contract.get("props_projection")
    require(isinstance(expected, dict) and bool(expected), "Missing live runtime projection")
    for key, value in expected.items():
        require(props.get(key) == value, f"Live model/runtime changed: {key}")
    if contract.get("chat_template_sha256"):
        actual = hashlib.sha256(props["chat_template"].encode()).hexdigest()
        require(actual == contract["chat_template_sha256"], "Live chat template changed")
    with urllib.request.urlopen(base + "/slots", timeout=30) as stream:
        slots = json.load(stream)
    require(len(slots) == 1 and slots[0].get("n_ctx") == 131072,
            "Expected one Qwen slot with the frozen context limit")


def score_evidence(path, manifest):
    score = read(path / "official-score.json")
    require(type(manifest.get("passed")) is bool and score.get("passed") is manifest["passed"],
            f"Task outcome disagrees with official scorer: {path}")
    require(score.get("evaluator") == "official BFCL", "Nonofficial scorer")
    require(score["summary"]["total_count"] == 1
            and score["summary"]["correct_count"] == int(manifest["passed"]),
            "Official score count does not describe one complete task")
    score_path = (path / score["score_file"]).resolve()
    require(score_path.is_relative_to(path.resolve()), "Score file escapes run directory")
    require(sha(score_path) == score["score_sha256"], "Official score artifact changed")
    results = list((path / "result").rglob(f"*{manifest['category']}_result.json"))
    require(len(results) == 1 and sha(results[0]) == score["result_sha256"],
            "Official result artifact changed/missing")
    data = [json.loads(line) for line in results[0].read_text().splitlines() if line.strip()]
    require(len(data) == 1 and data[0].get("id") == manifest["task"], "Official result task mismatch")
    return score


def native_records(path):
    requests, responses = {}, {}
    for line in (path / "native.jsonl").read_text().splitlines():
        row = json.loads(line)
        if row.get("event") not in ("request", "response"):
            continue
        target = requests if row["event"] == "request" else responses
        require(row["index"] not in target, f"Duplicate native request/response index: {path}")
        target[row["index"]] = row
    return requests, responses


def execution_metrics(path, api, boundary):
    """BFCL writes one tool log item per returned execution result; no state read."""
    if (path / "executions.json").exists():
        executed = [row for row in read(path / "executions.json") if row["source"] == "live"]
        tools = [dict(content=raw) for row in executed for raw in row["execution_results"]]
        decoding = read(path / "decoding.json")
        parse_errors = sum(row["source"] == "live" and not row["decoded"] for row in decoding)
    elif not (path / "full.json").exists():
        return dict(executed_tool_items=None, explicit_error_returns=None, parse_errors=None,
                    execution_count_unavailable_reason="No official step log or execution hook records")
    else:
        full = read(path / "full.json")
        steps = []
        for turn in full["metadata"]["inference_log"]:
            if not isinstance(turn, dict):
                continue
            ordered = sorted((key for key in turn if key.startswith("step_")),
                             key=lambda key: int(key.removeprefix("step_")))
            steps.extend(turn[key] for key in ordered)
        if len(steps) != len(api):
            return dict(executed_tool_items=None, explicit_error_returns=None, parse_errors=None,
                        execution_count_unavailable_reason="Official step log does not align one-to-one with API responses")
        tools = [item for step in steps[boundary:] for item in step if item.get("role") == "tool"]
        parse_errors = sum(item.get("role") == "handler_log" and
                           item.get("content") == "Error decoding the model response. Proceed to next turn."
                           for step in steps[boundary:] for item in step)
    errors = 0
    for item in tools:
        value = item.get("content")
        if isinstance(value, str) and value.startswith("Error during execution:"):
            errors += 1
            continue
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (ValueError, TypeError):
                pass
        if isinstance(value, dict) and (bool(value.get("error")) or value.get("success") is False):
            errors += 1
        elif (isinstance(value, list) and len(value) == 1 and isinstance(value[0], dict)
              and bool(value[0].get("error"))):
            errors += 1
    return dict(executed_tool_items=len(tools), explicit_error_returns=errors,
                parse_errors=parse_errors, execution_count_unavailable_reason=None)


def run_metrics(path, sample, method, arm, historical=False):
    m, api, accounting = read(path / "manifest.json"), read(path / "api.json"), read(path / "accounting.json")
    boundary = m["trigger_index"]
    attempted = [row for row in accounting if row["index"] >= boundary]
    post = [row for row in attempted if row.get("requested", True)]
    rejected = [row for row in attempted if not row.get("requested", True)]
    require(bool(attempted), f"No continuation accounting: {path}")
    emitted = [item for record in api[boundary:] for item in record["response"]["output"]
               if item.get("type") == "function_call"]
    signatures = [(item.get("name"), item.get("arguments")) for item in emitted]
    repeats = sum(left == right for left, right in zip(signatures, signatures[1:]))
    row = dict(case_id=sample["case_id"], sample_id=sample["sample_id"], task=sample["task"],
               family=sample["family"], category=sample["category"], seed=sample["seed"],
               method=method, arm=arm, path=str(path), historical_identity=historical,
               status=m["status"], passed=m.get("passed"), trigger_index=boundary,
               max_output_tokens=m["max_tokens"],
               official_score_available=m["status"] == "complete",
               first_input=post[0]["input_tokens"] if post else None,
               mean_post_input=mean(a["input_tokens"] for a in post) if post else None,
               peak_input=max(a["input_tokens"] for a in post) if post else None,
               cumulative_post_input=sum(a["input_tokens"] for a in post),
               mean_fixed_input=mean(a["fixed_tokens"] for a in post) if post else None,
               mean_working_input=mean(a["working_tokens"] for a in post) if post else None,
               unrequested_context_limit_inputs=[a["input_tokens"] for a in rejected],
               model_requests=len(post), emitted_calls=len(emitted),
               adjacent_same_arguments_candidates=repeats,
               source_api_records=len(api), replayed_requests=sum(r.get("source") == "replay" for r in api),
               native_requests=len(native_records(path)[0]), source_work_tokens=m.get("source_work_tokens"))
    row.update(execution_metrics(path, api, boundary))
    if not historical:
        metadata = read(path / "memory-metadata.json")
        row["diagnostic_audit"] = metadata["diagnostic"]
        row["instruction_tokens"] = metadata.get("instruction_tokens")
    return row


def validate_job(path, sample, method, arm, plan, project, transport="qwen", allow_unscored_parser_error=False):
    """Cross-check sent requests and native usage, not only task self-reports."""
    from core.graph_memory_replace import retained_instructions
    from core import lossless_event, lossless_state
    from core.optimized_graph import MINIMAL, _same
    from core.qwen_prompt_accounting import to_chat_tools
    if transport == "qwen":
        from core.model_config import SERVING_MODEL
        from core.qwen_transport import chat_messages, digest
        template_kwargs = dict(enable_thinking=False, preserve_thinking=False)
    elif transport == "muse":
        from core.muse_transport import SERVING_MODEL, chat_messages, digest
        template_kwargs = dict(reasoning_strength="low", preserve_thinking=False)
    else:
        raise ValueError("Unknown diagnostic transport")

    live_budget = output_budget(plan)
    identity_reference = method == "identity"
    require(not identity_reference or arm == "identity_reference", "Unknown Identity control arm")
    identity = source_path(project, sample["source_paths"]["identity"])
    source_graph = None if identity_reference else source_path(project, sample["source_paths"][method + "-optimized"])
    original = read(identity / "manifest.json")
    original_expected = dict(task=sample["task"], category=sample["category"], seed=sample["seed"],
                             method="identity", status="complete", sampling=plan["sampling"],
                             threshold=1000, context=131072, max_tokens=SOURCE_MAX_OUTPUT_TOKENS, triggered=True)
    require(all(original.get(key) == value for key, value in original_expected.items()),
            "Historical Identity configuration mismatch")
    m = read(path / "manifest.json")
    expected = dict(task=sample["task"], category=sample["category"], seed=sample["seed"],
                    method=method, arm=arm, identity=str(identity), explanation="none" if identity_reference else "minimal",
                    sampling=plan["sampling"], threshold=1000, context=131072, max_tokens=live_budget,
                    base_url=plan["base_url"], triggered=True,
                    source_graph=str(source_graph) if source_graph is not None else None)
    for key, value in expected.items():
        require(m.get(key) == value, f"Run configuration mismatch {key}: {path}")
    require(m.get("source_max_tokens", SOURCE_MAX_OUTPUT_TOKENS) == original["max_tokens"],
            "Source and live output budgets were conflated")
    protocol_failure = m.get("status") == "protocol_failure"
    parser_incomplete = allow_unscored_parser_error and m.get("status") == "infrastructure_error"
    require(m.get("status") in ("complete", "protocol_failure") or parser_incomplete,
            f"Incomplete/infrastructure failure needs review: {path}")
    audit = m.get("engineering_audit", {})
    if parser_incomplete:
        from workflows.diagnostic_restart import malformed_arguments_evidence
        malformed_arguments_evidence(path)
        require(audit.get("status") == "fail" and m.get("passed") is None,
                "Unscored parser outcome was incorrectly scored or accepted")
        flags = [key for key in ENGINEERING_FLAGS if key != "official_score_verified"]
    elif protocol_failure:
        require(audit.get("status") == "protocol_failure" and m.get("passed") is False
                and m.get("failure_kind") == "model_context_limit" and m.get("official_score_available") is False,
                "Unrecognized/unverified protocol terminal failure")
        flags = [key for key in ENGINEERING_FLAGS
                 if key not in ("official_score_verified", "replacement_delivered_exact")]
        require(audit.get("replacement_prepared_exact") is True,
                "Context-limit payload was not fully prepared/verified")
    else:
        require(audit.get("status") == "pass", f"Task engineering audit missing: {path}")
        flags = ENGINEERING_FLAGS
        score_evidence(path, m)
    if identity_reference:
        flags = [key for key in flags if key != "payload_decode_exact"]
        require(audit.get("identity_history_exact") is True, "Identity checkpoint passthrough was not verified")
    require(all(audit.get(key) is True for key in flags), "Missing task engineering verification")
    require(audit.get("conversion_count") == (0 if identity_reference else 1),
            "Identity must remain unchanged; graph replacement must happen exactly once")
    require(m["trigger_index"] == original["trigger_index"] and
            m["checkpoint_sha256"] == original["checkpoint_sha256"] == sample["checkpoint_sha256"],
            "Historical conversion boundary changed")
    require(m.get("source_work_tokens") == original["source_work_tokens"] > 1000,
            "History threshold does not match historical native accounting")
    checkpoint = read(path / "checkpoint-history.json")
    require(checkpoint == read(identity / "checkpoint-history.json") and
            digest(checkpoint) == sample["checkpoint_sha256"], "Checkpoint contents changed")
    api, source = read(path / "api.json"), read(identity / "api.json")
    boundary = m["trigger_index"]
    require(len(api) >= boundary and (protocol_failure or len(api) > boundary),
            "No continuation response or documented protocol failure")
    for index in range(boundary):
        row = api[index]
        require(row.get("source") == "replay" and row["request"] == source[index]["request"]
                and row["response"] == source[index]["response"], "Historical replay differs")
    metadata = read(path / "memory-metadata.json")
    if identity_reference:
        require(metadata.get("graph") is None and metadata.get("encoded") is None
                and metadata.get("identity_history") == checkpoint,
                "Identity control was transformed or lost its exact checkpoint")
    else:
        archived = read(source_graph / "memory-metadata.json")
        codec = lossless_state if method == "state" else lossless_event
        require(_same(metadata["graph"], archived["graph"])
                and _same(codec.decode(metadata["encoded"]), archived["graph"]),
                "Diagnostic payload differs from frozen typed graph")
        require(metadata.get("source_metadata_sha256") == sha(source_graph / "memory-metadata.json"),
                "Archived graph metadata fingerprint changed")
    replacement = metadata["replacement_messages"]
    require(isinstance(replacement, list) and bool(replacement), "Missing exact replacement messages")
    require(metadata.get("instruction") == ("" if identity_reference else MINIMAL),
            "Memory explanation changed")
    fixed = retained_instructions(checkpoint)
    delivered = [*fixed, *replacement]
    if identity_reference:
        require(delivered == checkpoint, "Identity reference did not preserve the complete original input")
    initial_request = read(path / "expected-initial-request.json")
    require(_same(initial_request["input"], delivered), "Prepared replacement differs from initial request")
    if len(api) > boundary:
        require(api[boundary]["request"] == initial_request, "Prepared initial request was not sent")
    require(initial_request["tools"] == source[boundary]["request"]["tools"],
            "Initial continuation tool definitions differ from Identity")
    all_accounts = read(path / "accounting.json")
    accounts = [row for row in all_accounts if row.get("requested") is True]
    unrequested = [row for row in all_accounts if row.get("requested") is not True]
    indices = list(range(boundary, len(api)))
    require([row["index"] for row in accounts] == indices, "Accounting missing or out of order")
    native_requests, native_responses = native_records(path)
    require(set(native_requests) == set(indices) == set(native_responses), "Native request/response count differs")
    if accounts:
        require(audit.get("replacement_delivered_exact") is True, "Actual continuation delivery was not verified")
    elif protocol_failure:
        require(audit.get("replacement_delivered_exact") is False,
                "Rejected first input must not be claimed as delivered")
    previous = None
    for record, account in zip(api[boundary:], accounts):
        index = account["index"]
        request, response = record["request"], record["response"]
        require(record.get("source") == "live", "Continuation unexpectedly replayed")
        require(_same(request["input"][:len(delivered)], delivered), "Graph replacement did not persist")
        require(retained_instructions(request["input"]) == fixed, "Fixed instructions changed")
        if previous is not None:
            prior = [*previous["request"]["input"], *previous["response"]["output"]]
            require(_same(request["input"][:len(prior)], prior), "Subsequent working history/output was replaced/truncated")
        previous = record
        wire, raw = native_requests[index]["request"], native_responses[index]["response"]
        require(wire["messages"] == chat_messages(request["input"])
                and wire["tools"] == to_chat_tools(request["tools"]), "Native sent input differs from harness input")
        require(wire["model"] == raw["model"] == SERVING_MODEL, "Native model changed")
        require(wire["seed"] == sample["seed"] + index * 1000003
                and wire["max_tokens"] == live_budget, "Native sampling schedule changed")
        require(all(wire.get(k) == v for k, v in plan["sampling"].items()), "Native sampling parameters changed")
        require(wire.get("chat_template_kwargs") == template_kwargs,
                "Reasoning policy changed")
        require(raw["usage"]["prompt_tokens"] == account["input_tokens"] == response["usage"]["input_tokens"],
                "Actual native input token count mismatch")
        require(raw["usage"]["completion_tokens"] == account["output_tokens"] == response["usage"]["output_tokens"],
                "Actual native output token count mismatch")
        require(account.get("requested") is True and account.get("usage_verified") is True,
                "Accounted input was not actually requested and verified")
        require(account["request_sha256"] == digest(request)
                and account["native_request_sha256"] == digest(wire), "Request fingerprint mismatch")
        require(account["input_tokens"] - account["fixed_tokens"] == account["working_tokens"],
                "Fixed overhead accounting mismatch")
        require(account.get("output_reservation", SOURCE_MAX_OUTPUT_TOKENS) == live_budget,
                "Accounted output reservation differs from the registered live budget")
        require(account["input_tokens"] + live_budget <= plan["context"],
                "Context overflow was not a valid completed request")
    require(sha(path / "initial-native-prompt.txt") == all_accounts[0]["prompt_sha256"],
            "Recorded first native prompt changed")
    if protocol_failure:
        require(len(unrequested) == 1 and unrequested[0] == all_accounts[-1]
                and unrequested[0]["index"] == len(api) and unrequested[0]["usage_verified"] is False
                and unrequested[0].get("output_reservation", SOURCE_MAX_OUTPUT_TOKENS) == live_budget
                and unrequested[0]["input_tokens"] + live_budget > plan["context"],
                "Protocol failure is not one terminal unrequested context-limit input")
        rejected = read(path / "context-limit-request.json")
        req, wire = rejected["request"], rejected["native_request"]
        require(rejected["output_reservation"] == wire["max_tokens"] == live_budget
                and rejected["model_context"] == plan["context"],
                "Rejected request does not use the registered output reservation")
        require(req["input"][:len(delivered)] == delivered
                and wire["messages"] == chat_messages(req["input"])
                and wire["tools"] == to_chat_tools(req["tools"]), "Rejected request payload is inconsistent")
        require(digest(req) == unrequested[0]["request_sha256"]
                and digest(wire) == unrequested[0]["native_request_sha256"], "Rejected request hash mismatch")
        if previous is not None:
            prior = [*previous["request"]["input"], *previous["response"]["output"]]
            require(req["input"][:len(prior)] == prior, "Rejected history is not append-only")
    else:
        require(not unrequested, "Completed task contains an unrequested input")
    if arm.startswith("goal_"):
        goal_audit = read(path / "goal-template-audit.json")
        require(goal_audit.get("exact_boundary_only") is True and goal_audit.get("goal_text_exact") is True,
                "Native goal boundary comparison did not pass")
    return run_metrics(path, sample, method, arm)


def aggregate(rows, expected=EXPECTED_PREFIXES):
    success = sum(row["passed"] for row in rows)
    result = dict(planned=expected, completed=len(rows), missing=expected - len(rows), successes=success,
                  success_rate_completed=success / len(rows) if rows else None,
                  fixed_denominator_success_bounds=[success / expected, (success + expected - len(rows)) / expected])
    for metric in ("first_input", "mean_post_input", "peak_input", "cumulative_post_input",
                   "model_requests", "emitted_calls", "executed_tool_items", "explicit_error_returns",
                   "parse_errors", "adjacent_same_arguments_candidates"):
        values = [row[metric] for row in rows if row.get(metric) is not None]
        result[metric] = dict(mean=mean(values) if values else None, measured=len(values))
    budgets = sorted({0, *(row["emitted_calls"] for row in rows)})
    result["success_with_call_budget"] = [dict(budget=b, successful=sum(
        row["passed"] and row["emitted_calls"] <= b for row in rows), denominator=expected)
        for b in budgets]
    return result


def paired_summary(rows, identity, control, treatment, method):
    groups = {arm: {row["case_id"]: row for row in rows if row["method"] == method and row["arm"] == arm}
              for arm in (control, treatment)}
    keys = sorted(set(groups[control]) & set(groups[treatment]))
    pairs = []
    def difference(right, left):
        return right - left if right is not None and left is not None else None
    for key in keys:
        left, right, reference = groups[control][key], groups[treatment][key], identity[key]
        pairs.append(dict(case_id=key, family=right["family"], category=right["category"], seed=right["seed"],
                          control_passed=left["passed"], treatment_passed=right["passed"],
                          identity_passed=reference["passed"],
                          first_input_difference=difference(right["first_input"], left["first_input"]),
                          mean_input_difference=difference(right["mean_post_input"], left["mean_post_input"]),
                          emitted_call_difference=right["emitted_calls"] - left["emitted_calls"],
                          model_request_difference=right["model_requests"] - left["model_requests"]))
    return dict(method=method, control=control, treatment=treatment, planned_pairs=EXPECTED_PREFIXES,
                completed_pairs=len(pairs), missing_pairs=EXPECTED_PREFIXES - len(pairs),
                gains=sum(not p["control_passed"] and p["treatment_passed"] for p in pairs),
                losses=sum(p["control_passed"] and not p["treatment_passed"] for p in pairs),
                both_success=sum(p["control_passed"] and p["treatment_passed"] for p in pairs), pairs=pairs)


def input_comparison(rows, identity, metric):
    measured = [row for row in rows if row[metric] is not None
                and row["case_id"] in identity
                and identity[row["case_id"]].get(metric) is not None
                and identity[row["case_id"]][metric] > 0]
    return dict(measured=len(measured),
                mean_paired_ratio=mean(row[metric] / identity[row["case_id"]][metric]
                                      for row in measured) if measured else None,
                ratio_of_means=(mean(row[metric] for row in measured) /
                                mean(identity[row["case_id"]][metric] for row in measured)) if measured else None)


def report(root, plan, project, checked=None):
    """Report the complete planned denominator, including unfinished attempts."""
    identity, rows, incomplete, requests = {}, [], [], []
    for sample in plan["samples"]:
        path = source_path(project, sample["source_paths"]["identity"])
        m = read(path / "manifest.json")
        score_evidence(path, m)
        identity[sample["case_id"]] = run_metrics(path, sample, "identity", "historical_identity", True)
        for method in METHODS:
            for arm in ARMS:
                path = root / "evaluation" / sample["case_id"] / method / arm
                if not (path / "manifest.json").exists():
                    incomplete.append(dict(case_id=sample["case_id"], method=method, arm=arm,
                                           status="unmanifested_attempt" if path.exists() else "not_started"))
                    continue
                manifest = read(path / "manifest.json")
                if manifest.get("status") not in ("complete", "protocol_failure"):
                    incomplete.append(dict(case_id=sample["case_id"], method=method, arm=arm,
                                           status=manifest.get("status"), error=manifest.get("error")))
                    continue
                row = checked.get(str(path)) if checked is not None else None
                if row is None:
                    row = validate_job(path, sample, method, arm, plan, project)
                rows.append(row)
                for account in read(path / "accounting.json"):
                    requests.append(dict(case_id=sample["case_id"], method=method, arm=arm,
                                         run_seed=sample["seed"], **account))
    groups = {"identity": aggregate(list(identity.values()))}
    budget_comparison = output_budget_comparison(plan, identity)
    identity_acceptance = budget_comparison["identity_acceptance_available"]
    diagnostics = {}
    for method in METHODS:
        for arm in ARMS:
            label = method + "/" + arm
            selected = [row for row in rows if row["method"] == method and row["arm"] == arm]
            groups[label] = aggregate(selected)
            complete = len(selected) == EXPECTED_PREFIXES
            first = input_comparison(selected, identity, "first_input")
            later = input_comparison(selected, identity, "mean_post_input")
            loss = ((sum(row["passed"] for row in identity.values()) - sum(row["passed"] for row in selected))
                    / EXPECTED_PREFIXES * 100 if complete else None)
            diagnostics[label] = dict(
                completed_pairs=len(selected), success_loss_pp=loss,
                identity_acceptance_available=identity_acceptance,
                loss_exceeds_3pp=loss > 3 if identity_acceptance and loss is not None else None,
                mean_paired_first_input_ratio=first["mean_paired_ratio"],
                mean_paired_mean_input_ratio=later["mean_paired_ratio"],
                first_input_ratio_of_means=first["ratio_of_means"],
                mean_input_ratio_of_means=later["ratio_of_means"],
                measured_first_pairs=first["measured"], measured_mean_pairs=later["measured"],
                first_input_overhead_above_35pct=first["ratio_of_means"] > 1.35 if identity_acceptance and first["measured"] == EXPECTED_PREFIXES else None,
                mean_input_overhead_above_35pct=later["ratio_of_means"] > 1.35 if identity_acceptance and later["measured"] == EXPECTED_PREFIXES else None,
                interpretation=("Descriptive diagnostic flag only; no stopping, selection, noninferiority or mechanism claim."
                    if identity_acceptance else budget_comparison["interpretation"]))
    summary = dict(status="diagnostic_complete_pending_independent_review" if not incomplete else "partial_diagnostic",
                   expected_prefixes=EXPECTED_PREFIXES, expected_graph_jobs=EXPECTED_JOBS,
                   completed_graph_jobs=len(rows), incomplete_graph_jobs=len(incomplete),
                   families=len({row["family"] for row in plan["samples"]}),
                   groups=groups, diagnostic_limits=plan["diagnostic_limits"], diagnostic_flags=diagnostics,
                   output_budget_comparison=budget_comparison,
                   paired_comparisons=[paired_summary(rows, identity, *pair, method)
                                       for method in METHODS for pair in PAIRS.values()],
                   identity_rows=list(identity.values()), rows=rows, incomplete=incomplete,
                   cohort="All 81 archived actual-mixed prefixes; overall and actual-mixed are the SAME cohort here.",
                   negative_controls=[dict(case_id=row["case_id"], method=row["method"], arm=row["arm"],
                                           audit=row.get("diagnostic_audit", {})) for row in rows
                                      if row["arm"] in ("refs_control", "refs_expanded", "index_control", "index_view")],
                   limitations=["This exposed 18-family cohort is diagnostic, not independent confirmation.",
                       "Historical Identity continuations are reused; no new Identity prefixes were sampled.",
                       budget_comparison["interpretation"],
                       "Task failure is retained. Missing jobs are never silently treated as success or dropped.",
                       "A context-limit protocol failure counts as unsuccessful; it has no official score, and rejected inputs are not charged as model requests.",
                       "Success intervals/noninferiority and mechanisms are not inferred by this report.",
                       "Consecutive equal tool arguments are repeat candidates, never automatically unnecessary calls.",
                       "Executed items count official executor return items, including attempted calls that return errors.",
                       "Explicit error counts cover executor-error text and error/success=false wrappers, not all domain rejection forms.",
                       "Later request means and cumulative inputs depend on the continuation path.",
                       "Additive goal/index and reference expansion are controlled diagnostics, not accepted efficient final formats."])
    write(root / "reports/summary.json", summary)
    if requests:
        columns = list(dict.fromkeys(key for row in requests for key in row))
        target = root / "reports/per-request-input.csv"
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
    parser.add_argument("--report-only", action="store_true")
    args = parser.parse_args()
    root, project = args.root.resolve(), args.project.resolve()
    runtime, snapshot = root / "runtime", root / "source_code" / args.snapshot_label
    runtime.mkdir(parents=True, exist_ok=True)
    lock = (runtime / "controller.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    state = dict(pid=os.getpid(), status="starting", started_at=time.time(), completed_jobs=0,
                 expected_graph_jobs=EXPECTED_JOBS, source_snapshot=str(snapshot))
    checked = {}

    def update(**values):
        state.update(values, updated_at=time.time())
        write(runtime / "status.json", state)

    try:
        update(stage="release_validation")
        frozen, release_hash = verify_release(root, snapshot)
        require(Path(__file__).resolve().is_relative_to(snapshot.resolve()),
                "Controller must itself run from the released source snapshot")
        plan = read(root / "task-split.json")
        samples = validate_plan(plan)
        source_hashes = read(root / "source-inputs.json")
        require(all(Path(name).is_absolute() for name in source_hashes), "Source pins must use absolute paths")
        verify_hash_map(source_hashes)
        verify_hash_map(read(root / "vendor-pins.json"), snapshot)
        contract = read(runtime / "runtime-contract.json")
        require(contract.get("max_tokens") == output_budget(plan),
                "Released runtime contract and live output budget differ")
        env = dict(os.environ, PYTHONPATH=str(snapshot / "scripts"),
                   PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1")

        def check(sample=None, live=True):
            require(sha(root / "release.json") == release_hash
                    and release_inputs(root, snapshot) == frozen, "Released configuration changed")
            verify_hash_map(read(snapshot / "hashes.json"), snapshot)
            verify_hash_map(read(root / "vendor-pins.json"), snapshot)
            if sample:
                directories = [source_path(project, p) for p in sample["source_paths"].values()]
                relevant = {name: value for name, value in source_hashes.items()
                            if any(Path(name).is_relative_to(directory) for directory in directories)}
                require(bool(relevant), "No source pins for this prefix")
                verify_hash_map(relevant)
            if live:
                check_live_runtime(plan["base_url"], contract)

        def run(sample, method, arm):
            destination = root / "evaluation" / sample["case_id"] / method / arm
            bootstrap = runtime / "jobs" / sample["case_id"] / method / arm
            identity = source_path(project, sample["source_paths"]["identity"])
            source_graph = source_path(project, sample["source_paths"][method + "-optimized"])
            command = [sys.executable, "-m", "workflows.diagnostic_task", "--task", sample["task"],
                       "--category", sample["category"], "--seed", str(sample["seed"]),
                       "--method", method, "--arm", arm, "--identity", str(identity),
                       "--source-graph", str(source_graph), "--output", str(destination),
                       "--base-url", plan["base_url"], "--max-output-tokens", str(output_budget(plan))]
            check(sample)
            provenance = dict(command=command, source_snapshot=str(snapshot),
                              source_hashes=read(snapshot / "hashes.json"),
                              release_sha256=release_hash, frozen_inputs=frozen)
            update(current=dict(case_id=sample["case_id"], method=method, arm=arm, destination=str(destination)))
            if (destination / "manifest.json").exists():
                launch = read(bootstrap / "launch.json")
                require(all(launch.get(key) == value for key, value in provenance.items()),
                        f"Existing launch differs from released configuration: {destination}")
            else:
                require(not destination.exists() or not any(destination.iterdir()),
                        f"Unmanifested attempt requires review; refusing retry: {destination}")
                require(not bootstrap.exists() or not any(bootstrap.iterdir()),
                        f"Previous launch without a completed manifest requires review: {bootstrap}")
                bootstrap.mkdir(parents=True, exist_ok=True)
                write_once(bootstrap / "launch.json", dict(provenance, time=time.time()))
                with (bootstrap / "runner.log").open("x") as log:
                    completed = subprocess.run(command, cwd=snapshot, env=env, stdout=log,
                                               stderr=subprocess.STDOUT, check=False)
                require(completed.returncode == 0,
                        f"Task process failed ({completed.returncode}); no automatic retry: {destination}")
            row = validate_job(destination, sample, method, arm, plan, project)
            check(sample)
            checked[str(destination)] = row
            update(completed_jobs=len(checked), last_completed=str(destination))

        if args.report_only:
            check(live=False)
            summary = report(root, plan, project)
            update(status=summary["status"], stage="report_only", completed_jobs=summary["completed_graph_jobs"])
            return
        update(status="running", stage="pilot", frozen_inputs=frozen, release_sha256=release_hash)
        for identity in plan["pilot_case_ids"]:
            for method in METHODS:
                for arm in ARMS:
                    run(samples[identity], method, arm)
        pilot_jobs = {path: sha(Path(path) / "manifest.json") for path in checked}
        gate = dict(status="pass", gate="engineering_only_no_score_selection", release_sha256=release_hash,
                    pilot_case_ids=plan["pilot_case_ids"], checked_jobs=len(pilot_jobs),
                    manifest_sha256=pilot_jobs, checks=list(ENGINEERING_FLAGS),
                    conversion_count_per_job=1)
        gate_path = runtime / "pilot-gate.json"
        if gate_path.exists():
            require(read(gate_path) == gate, "Existing pilot gate changed")
        else:
            write_once(gate_path, gate)
        report(root, plan, project, checked)
        update(stage="all_81", pilot_gate="pass", pilot_success_not_used_for_progression=True)
        for sample in plan["samples"]:
            for method in METHODS:
                for arm in ARMS:
                    destination = root / "evaluation" / sample["case_id"] / method / arm
                    if str(destination) not in checked:
                        run(sample, method, arm)
            report(root, plan, project, checked)
        check()
        verify_hash_map(source_hashes)
        # Re-audit every saved job before declaring the full diagnostic complete.
        summary = report(root, plan, project)
        require(summary["completed_graph_jobs"] == EXPECTED_JOBS and not summary["incomplete"],
                "Final report is incomplete")
        update(status="diagnostic_complete_pending_independent_review", stage="independent_final_review_pending",
               completed_jobs=EXPECTED_JOBS, finished_at=time.time())
    except BaseException as error:
        update(status="needs_review", error=repr(error), failed_at=time.time())
        # Partial derived reporting is best-effort and never changes source runs.
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
