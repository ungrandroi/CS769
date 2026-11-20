"""One Qwen mixed-history diagnostic continuation from a frozen Identity prefix.

This independent runner reuses the work1000 transport/accounting helpers and
official BFCL execution/scoring. It never patches another module's builder:
the *archived* typed graph and encoded payload are validated and read directly.
Only one diagnostic view is installed; subsequent interaction appends normally.
"""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import time
from types import MethodType
from urllib.parse import urlparse

from core import lossless_event, lossless_state, optimized_graph
from core.diagnostic_views import (expand_shared_references, goal_boundary_views,
                                   state_index)
from core.generation_budget import (DEFAULT_MAX_OUTPUT_TOKENS, fits_context,
                                    request_with_output_budget, validate_max_output_tokens)

ARMS = ("goal_inline", "goal_separate", "index_control", "index_view",
        "refs_control", "refs_expanded")
READOUT_ARMS = ("readout_minimal", "readout_compact_index")
METHODS = {"state": ("v1-compact", "state-shared-v1", lossless_state),
           "event": ("v2-compact", "lossless-event/tables-v1", lossless_event),
           "dedup": ("v2-dedup", "lossless-event/shared-v1", lossless_event)}
INDEX_RULE = ("If present, state_index contains references into the decoded original graph, "
              "not the encoded envelope. JSON-pointer paths identify existing values; "
              "value_parts paths reconstruct a field from source_ref values. Fact references "
              "are already marked active state facts. Unknown values and multiple candidates remain unchanged.")
REF_RULE = ("A shared reference and its decoded same-type literal are interchangeable. "
            "The existing codec rules, literal escapes, table defaults and shared dictionary still apply.")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _latest_goal(history):
    for item in reversed(history):
        if item.get("role") == "user":
            if not isinstance(item.get("content"), str):
                raise ValueError("Goal boundary diagnostic requires an exact string user message")
            return item["content"]
    raise ValueError("No current user request in the frozen prefix")


def validate_arm_selection(method, arm, source_graph):
    identity = method == "identity"
    if identity != (arm == "identity_reference"):
        raise ValueError("Identity must use identity_reference; graph methods must use a diagnostic arm")
    if identity and source_graph is not None:
        raise ValueError("Identity passthrough does not accept a source graph")
    if not identity and source_graph is None:
        raise ValueError("Graph diagnostics require a source graph")
    return identity


def prepare_identity_passthrough(history, working_tokens):
    """Retain the complete source checkpoint, including roles and raw call data."""
    messages = deepcopy(history)
    working = [deepcopy(m) for m in history if m.get("role") not in ("system", "developer")]
    meta = dict(method="identity", diagnostic_method="identity", diagnostic_arm="identity_reference",
                candidate="identity_passthrough", explanation="none", graph=None, encoded=None,
                instruction="", instruction_tokens=0, common_diagnostic_rule="", common_rule_tokens=0,
                total_tokens=working_tokens, total_token_scope="native working tokens at the source checkpoint",
                replacement_messages=working, identity_history=deepcopy(history),
                diagnostic={"identity_passthrough": True}, payload_decode_exact=None,
                source_history_exact=True, identity_history_exact=True,
                adapter_rebuilt=False, semantic_editing=False)
    return messages, meta


def prepare_replacement(history, source_metadata, method, arm, count):
    """Pure transform returning (working replacement messages, audit metadata).

    Fixed instructions stay outside this function's output. No builder, hidden
    environment, ground truth, archived continuation or score is consulted.
    """
    if method not in METHODS or arm not in (*ARMS, *READOUT_ARMS):
        raise ValueError("Unsupported method or diagnostic arm")
    if arm.startswith("readout_"):
        from core.readout_candidate import prepare
        replacement, candidate = prepare(history, source_metadata, method,
            event_index=arm == "readout_compact_index")
        meta = dict(method=METHODS[method][0], diagnostic_method=method, diagnostic_arm=arm,
                    candidate=METHODS[method][1], explanation="minimal",
                    graph=deepcopy(source_metadata["graph"]), encoded=deepcopy(source_metadata["encoded"]),
                    instruction=optimized_graph.MINIMAL, instruction_tokens=count(optimized_graph.MINIMAL),
                    common_diagnostic_rule="", common_rule_tokens=0,
                    body=candidate["body"], graph_tokens=count(candidate["body"]), view=candidate["view"],
                    total_tokens=sum(count(m["content"]) for m in replacement),
                    replacement_messages=deepcopy(replacement), diagnostic=candidate,
                    payload_decode_exact=True, source_history_exact=True,
                    adapter_rebuilt=False, semantic_editing=False)
        return replacement, meta
    graph_method, expected_encoding, codec = METHODS[method]
    graph = deepcopy(source_metadata["graph"])
    encoded = deepcopy(source_metadata["encoded"])
    if graph.get("method") != graph_method or encoded.get("encoding") != expected_encoding:
        raise ValueError("Frozen method/codec does not match diagnostic assignment")
    if not optimized_graph._same(codec.decode(encoded), graph):
        raise AssertionError("Archived encoded payload does not restore its typed graph")
    working = [deepcopy(m) for m in history if m.get("role") not in ("system", "developer")]
    if not optimized_graph._same(optimized_graph.restore_history(graph), working):
        raise AssertionError("Archived graph source messages differ from the replay checkpoint")
    baseline_encoded = deepcopy(encoded)
    rule = ""
    view = None
    diagnostic = {}
    if arm.startswith("index_"):
        indexed = state_index(graph)
        diagnostic = indexed["audit"]
        rule = INDEX_RULE
        # An empty index is a genuine no-view negative control. Both arms still
        # carry the same common rule and run independently with the same seed.
        if arm == "index_view" and diagnostic["eligible_entries"]:
            view = indexed["view"]
    elif arm.startswith("refs_"):
        rule = REF_RULE
        if expected_encoding == "lossless-event/tables-v1":
            diagnostic = {"expanded_references": 0, "typed_decode_equal": True,
                          "dictionary_retained": True, "rules_unchanged": True,
                          "negative_control_unchanged": True, "no_shared_codec": True}
        else:
            expanded = expand_shared_references(encoded)
            diagnostic = expanded["audit"]
            if arm == "refs_expanded":
                encoded = expanded["encoded"]
    if not optimized_graph._same(codec.decode(encoded), graph):
        raise AssertionError("Diagnostic transform changed the typed semantic payload")
    body = optimized_graph.dumps(encoded)
    prefix = optimized_graph.MINIMAL + ("\n" + rule if rule else "")
    memory = prefix + "\n" + body
    if view is not None:
        memory += "\n" + optimized_graph.dumps(view)
    replacement = [{"role": "user", "content": memory}]
    if arm.startswith("goal_"):
        pair = goal_boundary_views(replacement, _latest_goal(working))
        replacement = pair[arm.removeprefix("goal_")]
        diagnostic = {**pair["audit"], "goal_view": pair["goal_view"],
                      "unmodified_memory": memory}
    meta = dict(method=graph_method, diagnostic_method=method, diagnostic_arm=arm,
                candidate=expected_encoding, explanation="minimal", graph=graph,
                encoded=encoded, baseline_encoded=baseline_encoded,
                instruction=optimized_graph.MINIMAL,
                instruction_tokens=count(optimized_graph.MINIMAL),
                common_diagnostic_rule=rule, common_rule_tokens=count(rule),
                graph_tokens=count(body), body=body, view=view,
                total_tokens=sum(count(m["content"]) for m in replacement),
                replacement_messages=replacement, diagnostic=diagnostic,
                payload_decode_exact=True, source_history_exact=True,
                adapter_rebuilt=False, semantic_editing=False,
                source_builder_sha256=source_metadata.get("builder_sha256"))
    return deepcopy(replacement), meta


def _action_metrics(records, execution_records, decoding_records=()):
    """Descriptive counts only; equal calls are never labeled unnecessary."""
    live = [r for r in records if r["source"] == "live"]
    calls = [item for r in live for item in r["response"]["output"]
             if item.get("type") == "function_call"]
    signatures = [(item["name"], item["arguments"]) for item in calls]
    seen, repeated, consecutive = set(), 0, 0
    for i, signature in enumerate(signatures):
        repeated += signature in seen
        consecutive += bool(i and signature == signatures[i-1])
        seen.add(signature)
    executed = [e for e in execution_records if e["source"] == "live"]
    errors = [deepcopy(d) for d in decoding_records if d["source"] == "live" and not d["decoded"]]
    explicit_tool_errors = 0
    for event in executed:
        for raw in event["execution_results"]:
            try:
                result = json.loads(raw) if isinstance(raw, str) else raw
            except (ValueError, TypeError):
                continue
            explicit_tool_errors += bool(isinstance(result, dict)
                                         and (result.get("error") or result.get("success") is False))
    return dict(model_requests=len(live), emitted_function_items=len(calls),
                executed_tool_returns=sum(len(e["execution_results"]) for e in executed),
                same_name_and_raw_arguments_candidates=repeated,
                consecutive_same_name_and_raw_arguments_candidates=consecutive,
                repeat_interpretation="Descriptive candidates; state may change; not redundancy labels",
                parser_error_count=len(errors), parser_errors=errors,
                explicit_structured_tool_error_returns=explicit_tool_errors,
                tool_error_interpretation="Only explicit error/success=false objects counted; raw text retained for review",
                tool_results_file="executions.json")


class RuntimeContextExceeded(RuntimeError):
    pass


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", required=True)
    parser.add_argument("--category", required=True)
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--method", choices=(*METHODS, "identity"), required=True)
    parser.add_argument("--arm", choices=(*ARMS, *READOUT_ARMS, "identity_reference"), required=True)
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--source-graph", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:11436/v1")
    parser.add_argument("--max-output-tokens", type=int, default=DEFAULT_MAX_OUTPUT_TOKENS)
    args = parser.parse_args(argv)
    validate_max_output_tokens(args.max_output_tokens)
    identity_mode = validate_arm_selection(args.method, args.arm, args.source_graph)
    parsed_url = urlparse(args.base_url)
    if parsed_url.scheme != "http" or parsed_url.hostname not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("This workflow is restricted to the authorized local Qwen service")
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        raise ValueError("Never overwrite or reuse a nonempty attempt directory")
    # Imports of runtime dependencies are delayed so prepare_replacement can be
    # audited/tested with pure Python without loading a tokenizer or any model.
    from workflows.work1000_task import (SAMPLING, all_paired, content_tokens,
                                         post, request_body, validate_source, write)
    from core.graph_memory_replace import retained_instructions
    from core.local_qwen_tokenizer import LocalQwenTokenizer
    from core.model_config import MODEL_KEY, SERVING_MODEL
    from core.qwen_transport import chat_messages, digest, plain, response_from_chat
    os.environ.update(BFCL_PROJECT_ROOT=str(out), OPENAI_API_KEY="local-no-key",
                      OPENAI_BASE_URL=args.base_url)
    os.environ.pop("OPENAI_DEFAULT_HEADERS", None)
    from bfcl_eval.model_handler.api_inference.openai_response import OpenAIResponsesHandler
    from bfcl_eval.utils import load_dataset_entry, make_json_serializable
    from openai.types.responses import Response
    files = [args.identity / name for name in ("manifest.json", "api.json", "checkpoint-history.json")]
    if not identity_mode:
        files += [args.source_graph / name for name in ("manifest.json", "memory-metadata.json")]
    source_hashes = {str(path.resolve()): sha(path) for path in files}
    source_manifest = json.loads((args.identity / "manifest.json").read_text())
    validate_source(source_manifest, args.task, args.category, args.seed)
    source = json.loads((args.identity / "api.json").read_text())
    graph_manifest = source_meta = None
    if not identity_mode:
        graph_manifest = json.loads((args.source_graph / "manifest.json").read_text())
        source_meta = json.loads((args.source_graph / "memory-metadata.json").read_text())
    boundary = source_manifest.get("trigger_index")
    if type(boundary) is not int or not source_manifest.get("source_work_tokens", 0) > 1000:
        raise ValueError("Diagnostic requires an eligible >1000-token Identity prefix")
    checkpoint = source[boundary]["request"]["input"]
    checkpoint_hash = digest(checkpoint)
    if checkpoint_hash != source_manifest["checkpoint_sha256"]:
        raise AssertionError("Identity checkpoint hash mismatch")
    if not identity_mode:
        for key, value in dict(task=args.task, category=args.category, seed=args.seed,
                               method=args.method, status="complete", trigger_index=boundary,
                               checkpoint_sha256=checkpoint_hash).items():
            if graph_manifest.get(key) != value:
                raise AssertionError(f"Archived graph pairing mismatch: {key}")
    if json.loads((args.identity / "checkpoint-history.json").read_text()) != checkpoint:
        raise AssertionError("Identity checkpoint file mismatch")
    if not all_paired(checkpoint):
        raise AssertionError("Conversion boundary has unpaired calls")
    manifest = dict(task=args.task, category=args.category, method=args.method,
                    arm=args.arm, diagnostic_arm=args.arm,
                    variant="identity_passthrough" if identity_mode else METHODS[args.method][1],
                    explanation="none" if identity_mode else "minimal", model_key=MODEL_KEY, serving_model=SERVING_MODEL,
                    seed=args.seed, sampling=SAMPLING, threshold=1000,
                    threshold_metric="native full minus fixed-only template tokens",
                    base_url=args.base_url, context=131072, max_tokens=args.max_output_tokens,
                    source_max_tokens=source_manifest["max_tokens"],
                    additional_input_cap=None, diagnostic_cost_gate_applied=False,
                    thinking=False, preserve_thinking=False, identity=str(args.identity.resolve()),
                    source_graph=None if identity_mode else str(args.source_graph.resolve()), source_sha256=source_hashes,
                    checkpoint_sha256=checkpoint_hash, source_work_tokens=source_manifest["source_work_tokens"],
                    status="running", triggered=False, started_at=time.time(),
                    source_code_sha256=sha(__file__), conversion_count=0, boundary_seen=False)
    records, accounting, executions, decoding_records = [], [], [], []
    turn = 0
    replacement = previous_input = previous_output = expected_query = None
    original_fixed = None
    fixed_cache, replay_outputs = {}, {}
    full_metadata = None
    tok = None
    audit = dict(status="pending", official_score_verified=False, prefix_replay_exact=False,
                 replacement_prepared_exact=False, replacement_delivered_exact=False, conversion_count=0,
                 append_only_after_conversion=True, native_input_counts_verified=True,
                 payload_decode_exact=None if identity_mode else False, identity_history_exact=False,
                 boundary_seen=False, native_requests_match_expected=True)
    manifest["engineering_audit"] = audit

    def save():
        write(out / "manifest.json", manifest)
        write(out / "api.json", records)
        write(out / "accounting.json", accounting)
        write(out / "executions.json", executions)
        write(out / "decoding.json", decoding_records)

    def log(event):
        with (out / "native.jsonl").open("a") as stream:
            stream.write(json.dumps(plain(event), ensure_ascii=False) + "\n")

    save()
    try:
        tok = LocalQwenTokenizer()
        manifest["tokenizer_provenance"] = tok.provenance
        handler = OpenAIResponsesHandler(SERVING_MODEL, 0.6, MODEL_KEY, True)
        entry = next(x for x in load_dataset_entry(args.category) if x["id"] == args.task)
        add = handler._add_next_turn_user_message_FC
        def add_user(self, data, user_message):
            nonlocal turn
            turn += 1
            return add(data, user_message)
        handler._add_next_turn_user_message_FC = MethodType(add_user, handler)
        parse_response = handler._parse_query_response_FC
        def parse_fc(self, response):
            parsed = parse_response(response)
            if response.id in replay_outputs:
                parsed["model_responses_message_for_chat_history"] = replay_outputs.pop(response.id)
            return parsed
        handler._parse_query_response_FC = MethodType(parse_fc, handler)
        decode_execute = handler.decode_execute
        def decode_calls(self, model_response, *positional, **keywords):
            item = dict(index=len(records)-1, source="replay" if len(records)-1 < boundary else "live")
            try:
                decoded = decode_execute(model_response, *positional, **keywords)
                item.update(decoded=True, result=plain(decoded))
                return decoded
            except Exception as error:
                item.update(decoded=False, error=repr(error))
                raise
            finally:
                decoding_records.append(item)
                save()
        handler.decode_execute = MethodType(decode_calls, handler)
        execute_add = handler._add_execution_results_FC
        def add_results(self, data, execution_results, model_response_data):
            executions.append(dict(index=len(records)-1, turn=turn,
                                   source="replay" if len(records)-1 < boundary else "live",
                                   tool_call_ids=plain(model_response_data.get("tool_call_ids", [])),
                                   execution_results=plain(execution_results)))
            result = execute_add(data, execution_results, model_response_data)
            save()
            return result
        handler._add_execution_results_FC = MethodType(add_results, handler)
        query = handler._query_FC
        def query_fc(self, data):
            nonlocal replacement, original_fixed, expected_query
            i = len(records)
            history = plain(data["message"])
            fixed = plain(retained_instructions(history))
            if original_fixed is None:
                original_fixed = fixed
            if fixed != original_fixed:
                raise AssertionError("Fixed instructions changed")
            if i == boundary:
                if manifest["boundary_seen"]:
                    raise AssertionError("Repeated boundary intervention attempt")
                if history != checkpoint:
                    raise AssertionError("Prefix replay changed at the shared boundary")
                write(out / "checkpoint-history.json", history)
                if identity_mode:
                    data["message"], meta = prepare_identity_passthrough(history, source_manifest["source_work_tokens"])
                    if data["message"] != checkpoint:
                        raise AssertionError("Identity passthrough changed the source checkpoint")
                else:
                    messages, meta = prepare_replacement(history, source_meta, args.method, args.arm, tok.count)
                    meta["source_metadata_sha256"] = sha(args.source_graph / "memory-metadata.json")
                    (out / "memory.txt").write_text("\n".join(m["content"] for m in messages))
                    data["message"] = [*fixed, *messages]
                write(out / "memory-metadata.json", meta)
                replacement = plain(data["message"])
                manifest.update(triggered=True, trigger_index=i, trigger_turn=turn,
                                conversion_count=0 if identity_mode else 1, boundary_seen=True,
                                memory_tokens=meta["total_tokens"], instruction_tokens=meta["instruction_tokens"],
                                instruction_insertions=0 if identity_mode else 1, common_rule_tokens=meta["common_rule_tokens"],
                                diagnostic={k: v for k, v in meta["diagnostic"].items()
                                            if k not in ("unmodified_memory", "goal_view")})
                audit.update(prefix_replay_exact=True, conversion_count=0 if identity_mode else 1,
                             boundary_seen=True, payload_decode_exact=None if identity_mode else True,
                             identity_history_exact=identity_mode)
                save()
            expected_query = dict(input=plain(data["message"]), tools=plain(data["tools"]))
            return query(data)
        handler._query_FC = MethodType(query_fc, handler)

        def generate(**kwargs):
            nonlocal previous_input, previous_output
            req = plain(kwargs)
            i = len(records)
            if req["input"] != expected_query["input"] or req.get("tools", []) != expected_query["tools"]:
                audit["native_requests_match_expected"] = False
                raise AssertionError("Handler request changed the expected complete input/tools")
            if i < boundary:
                if req != source[i]["request"]:
                    write(out / "replay-mismatch.json", {"index": i, "actual": req,
                                                         "expected": source[i]["request"]})
                    raise AssertionError(f"Exact prefix replay mismatch at {i}")
                record = dict(source[i], source="replay")
                records.append(record)
                replay_outputs[record["response"]["id"]] = plain(record["response"]["output"])
                save()
                return Response.model_validate(record["response"]), record["latency"]
            if req["input"][:len(replacement)] != replacement:
                audit["replacement_delivered_exact"] = False
                raise AssertionError("Replacement prefix changed")
            if previous_input is not None:
                expected_prefix = previous_input + previous_output
                if req["input"][:len(expected_prefix)] != expected_prefix:
                    audit["append_only_after_conversion"] = False
                    raise AssertionError("Post-conversion history was rewritten")
            if i == boundary:
                if req.get("tools", []) != source[boundary]["request"].get("tools", []):
                    raise AssertionError("Tool definitions changed at conversion")
                write(out / "expected-initial-request.json", req)
            body = request_with_output_budget(request_body, req, args.seed + i * 1000003,
                                              args.max_output_tokens)
            prompt = post(args.base_url, "/apply-template", body)["prompt"]
            full_tokens = tok.count(prompt, parse_special=True)
            fixed_body = dict(body, messages=chat_messages(retained_instructions(req["input"])))
            fixed_key = digest({"messages": fixed_body["messages"], "tools": body["tools"]})
            if fixed_key not in fixed_cache:
                fixed_body["messages"].append({"role": "user", "content": ""})
                fixed_prompt = post(args.base_url, "/apply-template", fixed_body)["prompt"]
                sentinel = "<|im_start|>user\n<|im_end|>\n"
                if fixed_prompt.count(sentinel) != 1:
                    raise AssertionError("Fixed-only sentinel changed")
                fixed_cache[fixed_key] = tok.count(fixed_prompt.replace(sentinel, "", 1), parse_special=True)
            fixed_tokens = fixed_cache[fixed_key]
            acc = dict(index=i, turn=turn, input_tokens=full_tokens, fixed_tokens=fixed_tokens,
                       working_tokens=full_tokens-fixed_tokens, content_tokens=content_tokens(req["input"], tok),
                       output_reservation=args.max_output_tokens,
                       seed=body["seed"], request_sha256=digest(req), native_request_sha256=digest(body),
                       prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
                       requested=False, usage_verified=False)
            if acc["working_tokens"] < 0:
                raise AssertionError("Invalid fixed-token subtraction")
            accounting.append(acc)
            if i == boundary:
                manifest["first_input"] = full_tokens
                (out / "initial-native-prompt.txt").write_text(prompt)
                if args.arm.startswith("goal_"):
                    meta = json.loads((out / "memory-metadata.json").read_text())
                    memory, goal_view = meta["diagnostic"]["unmodified_memory"], meta["diagnostic"]["goal_view"]
                    fixed = retained_instructions(req["input"])
                    pair = goal_boundary_views([{ "role": "user", "content": memory}], _latest_goal(checkpoint))
                    templates = {}
                    for name in ("inline", "separate"):
                        paired_body = request_with_output_budget(request_body,
                            dict(req, input=[*fixed, *pair[name]]), body["seed"], args.max_output_tokens)
                        templates[name] = post(args.base_url, "/apply-template", paired_body)["prompt"]
                    delimiter = "<|im_end|>\n<|im_start|>user\n"
                    expected = templates["inline"].replace(memory + goal_view, memory + delimiter + goal_view, 1)
                    if memory + goal_view not in templates["inline"] or templates["separate"] != expected:
                        raise AssertionError("Native goal arms differ beyond the message boundary")
                    if prompt != templates[args.arm.removeprefix("goal_")]:
                        raise AssertionError("Actual native prompt differs from checked goal arm")
                    write(out / "goal-template-audit.json", {"exact_boundary_only": True,
                          "goal_text_exact": True, "inline_tokens": tok.count(templates["inline"], parse_special=True),
                          "separate_tokens": tok.count(templates["separate"], parse_special=True)})
                audit["replacement_prepared_exact"] = True
            if not fits_context(full_tokens, args.max_output_tokens):
                write(out / "context-limit-request.json", dict(index=i, turn=turn,
                      request=req, native_request=body, expected_query=expected_query,
                      input_tokens=full_tokens, output_reservation=args.max_output_tokens, model_context=131072,
                      requested=False, prompt_sha256=acc["prompt_sha256"],
                      reason="Model runtime capacity; not an additional experimental input cap"))
                log(dict(event="context_limit", **acc, request=body))
                save()
                raise RuntimeContextExceeded(f"Model runtime context: {full_tokens}+{args.max_output_tokens} > 131072")
            acc["requested"] = True
            log(dict(event="request", **acc, request=body, expected_input_sha256=digest(expected_query["input"])))
            save()
            start = time.monotonic()
            raw = post(args.base_url, "/v1/chat/completions", body)
            elapsed = time.monotonic()-start
            log(dict(event="response", index=i, turn=turn, latency=elapsed, response=raw))
            if raw["model"] != SERVING_MODEL or raw["usage"]["prompt_tokens"] != full_tokens:
                audit["native_input_counts_verified"] = False
                raise AssertionError("Model identity or native prompt usage mismatch")
            audit["replacement_delivered_exact"] = True
            acc.update(usage_verified=True, output_tokens=raw["usage"]["completion_tokens"], latency=elapsed,
                       finish_reason=raw["choices"][0].get("finish_reason"))
            response = response_from_chat(raw, i)
            records.append(dict(request=req, response=plain(response), source="live", turn=turn, latency=elapsed))
            previous_input, previous_output = deepcopy(req["input"]), plain(response)["output"]
            save()
            return response, elapsed
        handler.generate_with_backoff = generate
        result, metadata = handler.inference(entry, True, False)
        full_metadata = plain(make_json_serializable(metadata))
        handler.write({"id": args.task, "result": result, **full_metadata}, out / "result")
        write(out / "full.json", {"result": plain(result), "metadata": full_metadata})
        if not manifest["boundary_seen"] or manifest["conversion_count"] != (0 if identity_mode else 1):
            raise AssertionError("Eligible run ended without its exact boundary intervention")
        from core.qwen_official_score import score_run
        score = score_run(out, {"id": args.task, "category": args.category})
        audit.update(official_score_verified=True, status="pass")
        manifest.update(status="complete", passed=score["passed"])
    except RuntimeContextExceeded as error:
        manifest.update(status="protocol_failure", passed=False, error=str(error),
                        failure_kind="model_context_limit", official_score_available=False)
        audit["status"] = "protocol_failure"
    except BaseException as error:
        manifest.update(status="infrastructure_error", error=repr(error))
        audit["status"] = "fail"
        raise
    finally:
        unchanged = all(sha(path) == expected for path, expected in source_hashes.items())
        if not unchanged:
            manifest.update(status="infrastructure_error", error="Archived source changed while running")
            audit["status"] = "fail"
        audit["source_files_unchanged"] = unchanged
        manifest.update(finished_at=time.time(), replayed_requests=sum(r["source"] == "replay" for r in records),
                        live_requests=sum(r["source"] == "live" for r in records),
                        action_metrics=_action_metrics(records, executions, decoding_records))
        save()
        if tok is not None:
            tok.close()
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
