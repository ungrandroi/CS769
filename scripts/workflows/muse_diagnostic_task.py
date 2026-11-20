"""Muse-only replay and continuation for the predeclared readout diagnostics.

Uses Muse's own frozen Identity prefix, graph, tokenizer, native template, and
low-reasoning policy. No running/frozen Qwen or Muse experiment code is changed.
Only pure input transforms/metrics are shared with diagnostic_task. This module
must be launched by the dependency-gated controller after earlier runs finish.
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
import urllib.request

from core.diagnostic_views import goal_boundary_views
from core.generation_budget import (DEFAULT_MAX_OUTPUT_TOKENS, fits_context,
                                    request_with_output_budget, validate_max_output_tokens)
from workflows.diagnostic_task import (ARMS, READOUT_ARMS, METHODS, RuntimeContextExceeded,
                                       _action_metrics, _latest_goal,
                                       prepare_replacement, prepare_identity_passthrough,
                                       validate_arm_selection, sha)

MUSE_USER_BOUNDARY = "<|eot|><|start|>user<|message|>"


def validate_muse_pair(identity, graph, model, model_key, reasoning_policy):
    """Reject Qwen prefixes and model/profile mismatches before any inference."""
    for source in (identity, graph):
        for field, expected in (("model", model), ("model_key", model_key),
                                ("reasoning_policy", reasoning_policy)):
            if source.get(field) != expected:
                raise AssertionError(f"Muse source mismatch: {field}")
        if source.get("semantics") not in ("filesystem", "mixed"):
            raise AssertionError("Muse semantic source must be explicit")
    if identity["semantics"] != graph["semantics"]:
        raise AssertionError("Muse graph and Identity use different semantic adapters")


def get_runtime_props(base):
    with urllib.request.urlopen(base.removesuffix('/v1') + '/props', timeout=30) as response:
        return json.load(response)


def validate_runtime_contract(props, contract, serving_model,
                              max_output_tokens=DEFAULT_MAX_OUTPUT_TOKENS):
    """Pin the serving template/profile; GGUF metadata alone is insufficient."""
    expected = contract["props_projection"]
    if props.get("model_alias") != serving_model:
        raise AssertionError("Wrong model at Muse endpoint")
    template_hash = hashlib.sha256(props["chat_template"].encode()).hexdigest()
    if template_hash != contract["chat_template_sha256"]:
        raise AssertionError("Muse serving template changed")
    for key in contract["props_projection_keys"]:
        if props.get(key) != expected.get(key):
            raise AssertionError(f"Muse runtime contract changed: {key}")
    if contract["rendered_tokenization"] != {"add_special": True, "parse_special": True}:
        raise AssertionError("Unexpected Muse rendered-token policy")
    if contract["plain_tokenization"] != {"add_special": False, "parse_special": False}:
        raise AssertionError("Unexpected Muse plain-token policy")
    validate_max_output_tokens(max_output_tokens)
    if (contract.get("reasoning_strength") != "low"
            or contract.get("request_max_tokens") != max_output_tokens):
        raise AssertionError("Unexpected Muse reasoning/output budget")


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
    parser.add_argument("--runtime-contract", type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:11437/v1")
    parser.add_argument("--max-output-tokens", type=int, default=DEFAULT_MAX_OUTPUT_TOKENS)
    args = parser.parse_args(argv)
    validate_max_output_tokens(args.max_output_tokens)
    identity_mode = validate_arm_selection(args.method, args.arm, args.source_graph)
    parsed_url = urlparse(args.base_url)
    if parsed_url.scheme != "http" or parsed_url.hostname not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("This workflow is restricted to the authorized local Muse service")
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        raise ValueError("Never overwrite or reuse a nonempty attempt directory")
    # Imports of runtime dependencies are delayed so prepare_replacement can be
    # audited/tested with pure Python without loading a tokenizer or any model.
    from workflows.muse_task import (SAMPLING, all_paired, content_tokens,
                                         post, request_body, validate_source, write)
    from core.graph_memory_replace import retained_instructions
    from core.muse_transport import (NativeTokenizer, MODEL_KEY, SERVING_MODEL, MODEL_NAME,
                                     REASONING_POLICY, chat_messages, digest, plain, response_from_chat)
    os.environ.update(BFCL_PROJECT_ROOT=str(out), OPENAI_API_KEY="local-no-key",
                      OPENAI_BASE_URL=args.base_url)
    os.environ.pop("OPENAI_DEFAULT_HEADERS", None)
    from bfcl_eval.model_handler.api_inference.openai_response import OpenAIResponsesHandler
    from bfcl_eval.utils import load_dataset_entry, make_json_serializable
    from openai.types.responses import Response
    files = [args.identity / name for name in ("manifest.json", "api.json", "checkpoint-history.json")]
    if not identity_mode:
        files += [args.source_graph / name for name in ("manifest.json", "memory-metadata.json")]
    contract_path = (args.runtime_contract or args.identity.resolve().parents[3] / "runtime" / "runtime-contract.json").resolve()
    files.append(contract_path)
    source_hashes = {str(path.resolve()): sha(path) for path in files}
    contract = json.loads(contract_path.read_text())
    source_manifest = json.loads((args.identity / "manifest.json").read_text())
    validate_source(source_manifest, args.task, args.category, args.seed)
    source = json.loads((args.identity / "api.json").read_text())
    graph_manifest = source_meta = None
    if not identity_mode:
        graph_manifest = json.loads((args.source_graph / "manifest.json").read_text())
        source_meta = json.loads((args.source_graph / "memory-metadata.json").read_text())
    validate_muse_pair(source_manifest, source_manifest if identity_mode else graph_manifest,
                       MODEL_NAME, MODEL_KEY, REASONING_POLICY)
    boundary = source_manifest.get("trigger_index")
    if type(boundary) is not int or not source_manifest.get("source_work_tokens", 0) > 1000:
        raise ValueError("Diagnostic requires an eligible >1000-token Identity prefix")
    checkpoint = source[boundary]["request"]["input"]
    for i, record in enumerate(source[:boundary+1]):
        if record["request"].get("model") != SERVING_MODEL:
            raise AssertionError("Identity prefix request was not made to Muse")
        if i < boundary and record["response"].get("model") != SERVING_MODEL:
            raise AssertionError("Identity prefix response did not come from Muse")
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
                    explanation="none" if identity_mode else "minimal", model=MODEL_NAME, model_key=MODEL_KEY, serving_model=SERVING_MODEL,
                    reasoning_policy=REASONING_POLICY, generated_reasoning_policy=REASONING_POLICY,
                    semantics=source_manifest["semantics"], runtime_contract=str(contract_path),
                    seed=args.seed, sampling=SAMPLING, threshold=1000,
                    threshold_metric="native full minus fixed-only template tokens",
                    base_url=args.base_url, context=131072, max_tokens=args.max_output_tokens,
                    source_max_tokens=source_manifest["max_tokens"],
                    additional_input_cap=None, diagnostic_cost_gate_applied=False,
                    thinking=True, reasoning_strength="low", preserve_thinking=False, identity=str(args.identity.resolve()),
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
        props = get_runtime_props(args.base_url)
        validate_runtime_contract(props, contract, SERVING_MODEL, args.max_output_tokens)
        tok = NativeTokenizer(args.base_url)
        manifest["tokenizer_provenance"] = dict(model=MODEL_NAME, native_service=args.base_url,
              runtime_contract_sha256=sha(contract_path), chat_template_sha256=contract["chat_template_sha256"],
              rendered_tokenization={"add_special": True, "parse_special": True},
              plain_tokenization={"add_special": False, "parse_special": False},
              source="same loaded Muse runtime; full prompts include native BOS")
        write(out / "runtime-props.json", props)
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
            if body["chat_template_kwargs"] != {"reasoning_strength": "low", "preserve_thinking": False}:
                raise AssertionError("Muse generation/reasoning profile changed")
            if any("reasoning_content" in message for message in body["messages"]):
                raise AssertionError("Historical reasoning was reinserted into the Muse prompt")
            prompt = post(args.base_url, "/apply-template", body)["prompt"]
            full_tokens = tok.count(prompt, parse_special=True)
            fixed_body = dict(body, messages=chat_messages(retained_instructions(req["input"])))
            fixed_key = digest({"messages": fixed_body["messages"], "tools": body["tools"]})
            if fixed_key not in fixed_cache:
                # Muse accepts the native fixed-only prompt directly. Its BOS
                # is counted in full and fixed prompts with add_special=True.
                fixed_prompt = post(args.base_url, "/apply-template", fixed_body)["prompt"]
                fixed_cache[fixed_key] = tok.count(fixed_prompt, parse_special=True)
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
                    delimiter = MUSE_USER_BOUNDARY
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
        from core.muse_transport import score_run
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
