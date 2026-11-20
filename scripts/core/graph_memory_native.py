"""Lossless native conversation evidence with an optional graph state index.

The event graph is derived only from normalized visible BFCL evidence. Native
messages, including opaque provider blocks, remain authoritative for replay.
The index is a snapshot at the completed first-turn boundary, never a policy.
"""
from copy import deepcopy
import hashlib
import json

from core.event_graph import GraphMemoryV2
from core.graph_memory_readable import _state_index


INDEX_HEADER = "GRAPH INDEX (snapshot at end of first user turn; references use tool call IDs)\n"
ARCHIVED_INDEX_HEADER = "GRAPH INDEX (snapshot at archived history checkpoint; references use tool call IDs)\n"
SNAPSHOT_BOUNDARIES = ("end_of_first_user_turn", "archived_history_checkpoint")


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _arguments(value):
    return json.loads(value) if isinstance(value, str) else value


def _result_text(value):
    if isinstance(value, list):
        if not all(isinstance(block, dict) and block.get("type") == "text"
                   and isinstance(block.get("text"), str) for block in value):
            raise ValueError("BFCL tool result normalization requires text-only content")
        return "\n".join(block["text"] for block in value)
    return value


def _normalized_exchanges(messages):
    calls, results = {}, {}
    for message in messages:
        source_calls = message.get("tool_calls") or []
        if message.get("type") == "function_call":
            source_calls = [{"id": message["call_id"], "function": message}]
        for call in source_calls:
            identity, function = call["id"], call["function"]
            if identity in calls:
                raise ValueError("Duplicate normalized tool call ID")
            calls[identity] = {"name": function["name"], "arguments": _arguments(function["arguments"])}
        if message.get("type") == "function_call_output" or message.get("role") == "tool":
            identity = message.get("call_id", message.get("tool_call_id"))
            if identity not in calls or identity in results:
                raise ValueError("Unmatched normalized tool result")
            results[identity] = message["output"] if "output" in message else message["content"]
    if calls.keys() != results.keys():
        raise ValueError("Normalized evidence has pending tool results")
    return calls, results


def validate_native_history(messages, provider, *, snapshot_boundary="end_of_first_user_turn"):
    """Check a completed native turn and return its exact-ID tool exchanges.

    Non-tool blocks are deliberately opaque: signed thinking, refusals, and
    future provider blocks are copied without parsing or re-serialization.
    """
    if provider not in ("openai", "anthropic"):
        raise ValueError("provider must be openai or anthropic")
    if snapshot_boundary not in SNAPSHOT_BOUNDARIES:
        raise ValueError("Unknown native graph snapshot boundary")
    if not isinstance(messages, list) or not messages:
        raise ValueError("Native history must be a nonempty list")
    calls, results, pending = {}, {}, set()
    for message in messages:
        role = message.get("role")
        allowed = ("system", "developer", "user", "assistant", "tool") if provider == "openai" else ("user", "assistant")
        if role not in allowed:
            raise ValueError("Invalid native message role")
        if provider == "openai":
            if pending and role != "tool":
                raise ValueError("Native tool results must immediately follow their calls")
            if role == "tool":
                identity = message.get("tool_call_id")
                if identity not in pending:
                    raise ValueError("Unmatched or duplicate native tool result")
                pending.remove(identity)
                results[identity] = message["content"]
            source_calls = message.get("tool_calls") or []
            if source_calls and role != "assistant":
                raise ValueError("Tool calls require assistant role")
            for call in source_calls:
                identity, function = call["id"], call["function"]
                if identity in calls:
                    raise ValueError("Duplicate native tool call ID")
                calls[identity] = {"name": function["name"], "arguments": _arguments(function["arguments"])}
                pending.add(identity)
        else:
            content = message.get("content")
            blocks = content if isinstance(content, list) else []
            native_calls = [block for block in blocks if block.get("type") == "tool_use"]
            native_results = [block for block in blocks if block.get("type") == "tool_result"]
            if native_calls and role != "assistant":
                raise ValueError("Anthropic tool_use requires assistant role")
            if native_results and role != "user":
                raise ValueError("Anthropic tool_result requires user role")
            if pending:
                result_ids = [block.get("tool_use_id") for block in native_results]
                if (role != "user" or len(set(result_ids)) != len(result_ids)
                        or set(result_ids) != pending):
                    raise ValueError("All Anthropic tool results must immediately follow their calls")
                if any(block.get("type") != "tool_result" for block in blocks[:len(native_results)]):
                    raise ValueError("Anthropic tool results must precede other user content")
            elif native_results:
                raise ValueError("Unmatched native tool result")
            for block in native_results:
                identity = block["tool_use_id"]
                results[identity] = _result_text(block.get("content", ""))
                pending.remove(identity)
            for block in native_calls:
                identity = block["id"]
                if identity in calls:
                    raise ValueError("Duplicate native tool call ID")
                calls[identity] = {"name": block["name"], "arguments": deepcopy(block["input"])}
                pending.add(identity)
    if pending:
        raise ValueError("Native history has pending tool results")
    if snapshot_boundary == "end_of_first_user_turn" and messages[-1].get("role") != "assistant":
        raise ValueError("Index boundary must follow a completed assistant turn")
    return calls, results


def build_native_graph(normalized_messages, native_messages, *, provider,
                       native_context=None, call_id_map=None,
                       snapshot_boundary="end_of_first_user_turn"):
    """Retain exact native evidence and derive a known-facts graph from BFCL.

    ``native_context`` may contain unchanged system/tools request fields.
    ``call_id_map`` maps normalized evidence IDs to actual native call IDs;
    omitted IDs are identity-mapped. This never changes native messages.
    """
    normalized = deepcopy(normalized_messages)
    native = deepcopy(native_messages)
    native_calls, native_results = validate_native_history(native, provider,
                                                          snapshot_boundary=snapshot_boundary)
    normalized_calls, normalized_results = _normalized_exchanges(normalized)
    mapping = dict(call_id_map or {})
    if not set(mapping).issubset(normalized_calls):
        raise ValueError("Call ID map contains unknown normalized IDs")
    mapping = {identity: mapping.get(identity, identity) for identity in normalized_calls}
    if len(set(mapping.values())) != len(mapping) or set(mapping.values()) != set(native_calls):
        raise ValueError("Normalized/native tool call coverage differs")
    for old_id, native_id in mapping.items():
        if normalized_calls[old_id] != native_calls[native_id]:
            raise ValueError("Normalized/native tool call contents differ")
        if _result_text(normalized_results[old_id]) != native_results[native_id]:
            raise ValueError("Normalized/native tool results differ")
    graph = GraphMemoryV2().build(normalized)
    if graph["pending_calls"]:
        raise ValueError("Cannot build a graph at an incomplete tool boundary")
    graph["delivery"] = "native_history_plus_graph_index_v3"
    graph["native_evidence"] = {
        "version": 1, "provider": provider, "messages": native,
        "snapshot_boundary": snapshot_boundary,
        "context": deepcopy(native_context or {}), "call_id_map": mapping,
        "messages_sha256": _digest(native),
        "context_sha256": _digest(native_context or {}),
        "normalized_sha256": _digest(normalized),
    }
    state = _state_index(graph, mapping)
    index = render_native_index(graph)
    graph["native_audit"] = {
        "native_message_count": len(native), "normalized_message_count": len(normalized),
        "tool_exchange_count": len(native_calls), "roundtrip_verified": True,
        "index_nonempty": bool(index), "index_characters": len(index),
        "index_sha256": _digest(index), "indexed_fact_ids": state["fact_ids"],
        "snapshot_boundary": snapshot_boundary,
        "provenance": "event confirmations and derived_from edges; native call IDs in rendered references",
    }
    assert reconstruct_native_history(graph) == native
    assert reconstruct_normalized_history(graph) == normalized
    return graph


def reconstruct_native_history(graph):
    evidence = graph["native_evidence"]
    if _digest(evidence["messages"]) != evidence["messages_sha256"]:
        raise ValueError("Native evidence integrity check failed")
    if _digest(evidence["context"]) != evidence["context_sha256"]:
        raise ValueError("Native context integrity check failed")
    validate_native_history(evidence["messages"], evidence["provider"],
                            snapshot_boundary=evidence["snapshot_boundary"])
    return deepcopy(evidence["messages"])


def reconstruct_normalized_history(graph):
    if _digest(graph["source_messages"]) != graph["native_evidence"]["normalized_sha256"]:
        raise ValueError("Normalized evidence integrity check failed")
    return deepcopy(graph["source_messages"])


def reconstruct_native_context(graph):
    reconstruct_native_history(graph)
    return deepcopy(graph["native_evidence"]["context"])


def render_native_index(graph):
    """Use the existing fact renderer, with references to actual native IDs."""
    state = _state_index(graph, graph["native_evidence"]["call_id_map"])["text"]
    if not state:
        return ""
    if not state.startswith("CURRENT STATE\n"):
        raise ValueError("Unexpected state renderer header")
    boundary = graph["native_evidence"]["snapshot_boundary"]
    if boundary not in SNAPSHOT_BOUNDARIES:
        raise ValueError("Unknown native graph snapshot boundary")
    header = INDEX_HEADER if boundary == "end_of_first_user_turn" else ARCHIVED_INDEX_HEADER
    return header + state[len("CURRENT STATE\n"):].rstrip() + "\n"


def append_native_index(graph):
    if graph["native_evidence"]["snapshot_boundary"] != "end_of_first_user_turn":
        raise ValueError("Archived history checkpoints are offline only; cannot append index")
    messages = reconstruct_native_history(graph)
    index = render_native_index(graph)
    if index:
        messages.append({"role": "assistant", "content": index})
    return messages


def render_application_memory(graph):
    """Label an existing index as harness data, without adding behavioral rules."""
    if graph["native_evidence"]["snapshot_boundary"] != "end_of_first_user_turn":
        raise ValueError("Archived history checkpoints are offline only; cannot attach context")
    index = render_native_index(graph)
    if not index:
        return ""
    return ('<application_memory source="harness" snapshot="after_turn_1">\n'
            + index + '</application_memory>\n\n')


def attach_application_memory(graph, user_messages):
    """Prepend data to the next user message, preserving its original text verbatim.

    BFCL's current categories provide one text user message at this boundary.
    Reject unsupported shapes rather than silently flattening or dropping data.
    The frozen historical messages are never modified by this projection.
    """
    if (not isinstance(user_messages, list) or len(user_messages) != 1
            or user_messages[0].get("role") != "user"
            or not isinstance(user_messages[0].get("content"), str)):
        raise ValueError("Application memory requires one plain-text user message")
    result = deepcopy(user_messages)
    result[0]["content"] = render_application_memory(graph) + result[0]["content"]
    return result
