"""Separately versioned mixed-domain semantics for paired encoding studies.

Historical filesystem builders and their delivered payloads remain unchanged.
Both original-format and selected-codec arms consume this same semantic payload.
"""
from copy import deepcopy
import hashlib
from pathlib import Path

from core import optimized_graph as old
from core.state_transition_graph import plain

VERSION = "mixed-domain-graph-1"
DOMAIN_FIELDS = ("domain", "coverage", "outcome_basis")
EVENT_FIELDS = DOMAIN_FIELDS + ("footprint", "operation_kind")
OBJECT_FIELDS = ("domain", "entity_type", "domain_id")
FACT_FIELDS = ("domain", "fact_scope")
GRAPH_FIELDS = ("semantic_schema_version", "adapter_version", "registry_version", "domain_coverage")


def _builders():
    from core.mixed_state_graph import MixedStateGraph
    from core.mixed_event_graph import MixedEventGraph
    return MixedStateGraph, MixedEventGraph


def domain_delta(before, after, path=()):
    """Exact changes, including deletions and list appends, without summarizing."""
    if old._same(before, after):
        return []
    if isinstance(before, dict) and isinstance(after, dict):
        changes = [{"path": list(path + (key,)), "op": "remove"}
                   for key in before if key not in after]
        for key, value in after.items():
            if key in before:
                changes.extend(domain_delta(before[key], value, path + (key,)))
            else:
                changes.append({"path": list(path + (key,)), "op": "set",
                                "value": deepcopy(value)})
        return changes
    if isinstance(before, list) and isinstance(after, list):
        if len(after) >= len(before) and old._same(before, after[:len(before)]):
            return [{"path": list(path), "op": "append", "value": deepcopy(after[len(before):])}]
        if len(before) == len(after):
            return [change for index, value in enumerate(after)
                    for change in domain_delta(before[index], value, path + (index,))]
    return [{"path": list(path), "op": "set", "value": deepcopy(after)}]


def apply_domain_delta(before, changes):
    state = deepcopy(before)
    for change in changes:
        path, operation = change["path"], change["op"]
        if not path:
            if operation == "set":
                state = deepcopy(change["value"])
            elif operation == "append":
                state.extend(deepcopy(change["value"]))
            else:
                raise ValueError("Cannot remove the state root")
            continue
        parent = state
        for key in path[:-1]:
            parent = parent[key]
        key = path[-1]
        if operation == "remove":
            del parent[key]
        elif operation == "set":
            parent[key] = deepcopy(change["value"])
        elif operation == "append":
            parent[key].extend(deepcopy(change["value"]))
        else:
            raise ValueError(f"Unknown domain delta operation: {operation}")
    return state


def render_state(original):
    payload = old._state_graph(original)
    first = original["nodes"][0]["state"]["domain_state"]
    payload["state_nodes"]["s0"]["domain_state"] = deepcopy(first)
    previous = first
    for node in original["nodes"][1:]:
        current = node["state"]["domain_state"]
        changes = domain_delta(previous, current)
        if changes:
            payload["state_nodes"][node["id"]]["changes"]["domain_state_updates"] = changes
        previous = current
    for edge in original["edges"]:
        payload["tool_call_edges"][edge["id"]].update(
            {key: deepcopy(edge[key]) for key in DOMAIN_FIELDS})
    payload["domain_delta_operations"] = {
        "set": "Replace the value at path.",
        "remove": "Remove the field at path.",
        "append": "Append value items to the list at path.",
    }
    return payload


def render_event(original, dedup):
    payload = old._event_graph(original, dedup)
    payload["event_columns"].extend(EVENT_FIELDS)
    payload["object_columns"].extend(OBJECT_FIELDS)
    payload["fact_columns"].extend(FACT_FIELDS)
    for node in original["nodes"]:
        for category, table, fields in (("event", "events", EVENT_FIELDS),
                                        ("object", "objects", OBJECT_FIELDS),
                                        ("fact", "facts", FACT_FIELDS)):
            if node["category"] == category:
                payload[table][node["id"]].extend(deepcopy(node.get(key)) for key in fields)
    derived_relations = {"describes", "supports", "confirms", "retires", "located_in",
                         "current_directory", "parent_directory"}
    retained = [edge for edge in original["edges"] if edge["relation"] not in derived_relations]
    annotations = {}
    for index, edge in enumerate(retained):
        extra = {key: deepcopy(value) for key, value in edge.items()
                 if key not in payload["relation_columns"]}
        if extra:
            annotations[str(index)] = extra
    if annotations:
        payload["relation_attributes"] = annotations
    return payload


def audit_semantics(original, payload):
    old.audit_semantic_index(original, payload)
    if payload["method"] == "v1-compact":
        state = deepcopy(payload["state_nodes"]["s0"]["domain_state"])
        for index, node in enumerate(original["nodes"]):
            if index:
                state = apply_domain_delta(state, payload["state_nodes"][node["id"]]["changes"]
                                           .get("domain_state_updates", []))
            if not old._same(state, node["state"]["domain_state"]):
                raise AssertionError(f"Lost domain state at {node['id']}")
        rendered = payload["tool_call_edges"]
        events = original["edges"]
    else:
        rendered = {key: dict(zip(payload["event_columns"], row))
                    for key, row in payload["events"].items()}
        events = [node for node in original["nodes"] if node["category"] == "event"]
        for category, table, columns, fields in (
                ("object", "objects", "object_columns", OBJECT_FIELDS),
                ("fact", "facts", "fact_columns", FACT_FIELDS)):
            decoded = {key: dict(zip(payload[columns], row)) for key, row in payload[table].items()}
            for node in original["nodes"]:
                if node["category"] == category:
                    for key in fields:
                        if not old._same(decoded[node["id"]][key], node.get(key)):
                            raise AssertionError(f"Lost {key} in {node['id']}")
        expected_relations = [edge for edge in original["edges"]
                              if edge["relation"] not in {
                                  "describes", "supports", "confirms", "retires", "located_in",
                                  "current_directory", "parent_directory"}]
        for index, edge in enumerate(expected_relations):
            row = dict(zip(payload["relation_columns"], payload["relations"][index]))
            row.update(payload.get("relation_attributes", {}).get(str(index), {}))
            expected = {key: edge.get(key) for key in payload["relation_columns"]}
            expected.update({key: value for key, value in edge.items()
                             if key not in payload["relation_columns"]})
            if not old._same(row, expected):
                raise AssertionError("Lost relation attribute")
    for event in events:
        for key in (DOMAIN_FIELDS if payload["method"] == "v1-compact" else EVENT_FIELDS):
            if not old._same(rendered[event["id"]][key], event.get(key)):
                raise AssertionError(f"Lost {key} in {event['id']}")
    for key in GRAPH_FIELDS:
        if not old._same(payload.get(key), original.get(key)):
            raise AssertionError(f"Lost graph support marker {key}")
    return True


def restore_history(payload):
    if payload["format"] != VERSION:
        raise ValueError("Unsupported mixed semantic payload version")
    return old.restore_history(payload)


def rebuild_original_graph(payload):
    state, event = _builders()
    builder = state if payload["method"] == "v1-compact" else event
    return builder().build(restore_history(payload))


def build_memory(history, method, explanation, count):
    if method not in old.METHODS or explanation not in ("none", "minimal", "full", "existing"):
        raise ValueError("Unsupported method or explanation")
    messages = plain(history)
    if any(message.get("role") in ("system", "developer") for message in messages):
        raise ValueError("Fixed instructions must remain outside working memory")
    state, event = _builders()
    original = (state if method == "v1-compact" else event)().build(messages)
    if original["pending_calls"]:
        raise ValueError("Cannot convert unpaired calls")
    packed, defaults, columns = old._pack_messages(messages)
    payload = {
        "format": VERSION, "method": method,
        "source_message_columns": columns, "message_defaults_by_type": defaults,
        "source_messages": packed,
        "user_requests": [item["id"] for item in original["requests"]],
        "unverified_assistant_statements": [item["evidence"] for item in original["annotations"]],
    }
    payload.update(render_state(original) if method == "v1-compact"
                   else render_event(original, method == "v2-dedup"))
    payload.update({key: deepcopy(original[key]) for key in GRAPH_FIELDS if key in original})
    audit_semantics(original, payload)
    if not old._same(messages, restore_history(payload)):
        raise AssertionError("Original history did not restore exactly")
    if not old._same(original, rebuild_original_graph(payload)):
        raise AssertionError("Mixed original graph did not restore exactly")
    body = old.dumps(payload)
    instruction = {"none": "", "minimal": old.MINIMAL, "full": old.FULL,
                   "existing": old.FULL}[explanation]
    text = instruction + "\n" + body if instruction else body
    files = ("mixed_observations.py", "mixed_state_graph.py", "mixed_event_graph.py",
             "mixed_graph.py", "state_transition_graph.py", "event_graph.py",
             "optimized_graph.py")
    source = Path(__file__).parent
    metadata = dict(
        candidate=VERSION, method=method, explanation=explanation, graph=payload,
        body=body, instruction=instruction, body_tokens=count(body),
        instruction_tokens=count(instruction), total_tokens=count(text), graph_tokens=count(body),
        builder_sha256={name: hashlib.sha256((source / name).read_bytes()).hexdigest() for name in files},
        reconstruction_audit=dict(history_exact=True, original_graph_rebuilt_exact=True,
                                  semantic_state_fact_event_index_verified=True,
                                  kind="Mixed adapter semantics; complete history and deterministic graph restoration"),
    )
    return text, metadata
