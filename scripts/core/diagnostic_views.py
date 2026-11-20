"""Offline, additive/readout diagnostics; no builders, inference, or tool execution.

These helpers do not select a current goal, repair semantic facts, or change a
frozen codec. Callers must supply the already selected verbatim goal and decoded
typed payload. Full payloads and dictionaries stay present in both study arms.
Returned audit metadata is for experiment records, not additional prompt text.
"""
from copy import deepcopy
from dataclasses import dataclass
import json

from core import lossless_event, lossless_state
from core.optimized_graph import _same


def goal_boundary_views(messages, goal_text):
    """Same exact appended text, either inside or after the final user message.

    The original goal remains in memory in *both* diagnostic arms. This tests
    message segmentation, not goal deduplication or historical role recovery.
    Native chat-template preservation of the boundary requires a later check.
    """
    if not isinstance(goal_text, str):
        raise TypeError("goal_text must be the selected verbatim string")
    if (not messages or messages[-1].get("role") != "user"
            or not isinstance(messages[-1].get("content"), str)):
        raise ValueError("Expected a final user memory message with string content")
    if messages[-1]["content"] != messages[-1]["content"].strip():
        raise ValueError("Memory outer whitespace would confound native-template trimming")
    # Native Qwen strips message-edge whitespace. Non-whitespace wrapper ends
    # keep even goal-leading/trailing whitespace identical in the two prompts.
    # No JSON quoting or escaping is added by either arm.
    goal_view = "<current_request>\n" + goal_text + "\n</current_request>"
    inline, separate = deepcopy(messages), deepcopy(messages)
    inline[-1]["content"] += goal_view
    separate.append({"role": "user", "content": goal_view})
    return {"inline": inline, "separate": separate, "goal_view": goal_view,
            "audit": {"original_payload_retained": True,
                      "goal_copies_added_per_arm": 1,
                      "native_template_boundary_verified": False}}


def _pointer(parts):
    """RFC 6901 pointer relative to the original, decoded typed payload."""
    return "".join("/" + str(part).replace("~", "~0").replace("/", "~1")
                   for part in parts)


def resolve_pointer(payload, pointer):
    """Resolve an index reference without a graph builder or external state."""
    if pointer == "":
        return payload
    if not pointer.startswith("/"):
        raise ValueError("Expected an absolute JSON pointer")
    node = payload
    for part in pointer[1:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        node = node[int(part)] if isinstance(node, list) else node[part]
    return node


def _key(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _event_index(payload):
    columns, facts = payload["fact_columns"], payload["facts"]
    if len(columns) != len(set(columns)):
        raise ValueError("Duplicate fact columns")
    required = {"subject", "predicate", "retired_at"}
    if not required.issubset(columns):
        raise ValueError("Missing fact identity or validity columns")
    active = payload["active_facts"]
    if len(active) != len(set(active)):
        raise ValueError("Duplicate active fact IDs")
    groups, omitted = {}, {"observation": 0, "missing_scope": 0, "other_scope": 0}
    for identity in active:
        row = facts[identity]
        if not isinstance(row, list) or len(row) != len(columns):
            raise ValueError("Expected unpacked typed fact rows")
        fact = dict(zip(columns, row))
        # Conflicting validity markers are an audit error, not grounds to infer
        # a replacement value or silently remove an inconvenient fact.
        if fact["retired_at"] is not None:
            raise ValueError("An active fact is marked retired")
        scope = fact.get("fact_scope")
        if scope != "state":
            reason = "missing_scope" if scope is None else (
                "observation" if scope == "observation" else "other_scope")
            omitted[reason] += 1
            continue
        key = _key([fact["subject"], fact["predicate"],
                    "key" in fact, fact.get("key")])
        if key not in groups:
            entry = {"subject_ref": _pointer(("facts", identity, columns.index("subject"))),
                     "field_ref": _pointer(("facts", identity, columns.index("predicate")))}
            if "key" in fact:
                entry["key_ref"] = _pointer(("facts", identity, columns.index("key")))
            entry["fact_refs"] = []
            groups[key] = entry
        # Multiple already-active candidates stay multiple. Values (including
        # null/unknown) remain in their source rows and are never guessed here.
        groups[key]["fact_refs"].append(_pointer(("facts", identity)))
    entries = list(groups.values())
    return entries, {"eligible_entries": len(entries),
                     "eligible_fact_count": sum(len(e["fact_refs"]) for e in entries),
                     "ambiguous_entries": sum(len(e["fact_refs"]) > 1 for e in entries),
                     "omitted_active_facts": omitted}


@dataclass(frozen=True)
class _Source:
    path: tuple


def _source_tree(value, path):
    # Empty containers and null are distinct leaves, retaining their exact type
    # by pointing to the existing value instead of serializing a new value.
    if isinstance(value, dict) and value:
        return {k: _source_tree(v, path + (k,)) for k, v in value.items()}
    if isinstance(value, list) and value:
        return [_source_tree(v, path + (i,)) for i, v in enumerate(value)]
    return _Source(path)


def _parts(tree, relative=()):
    if isinstance(tree, _Source):
        return [{"path": list(relative), "source_ref": _pointer(tree.path)}]
    items = tree.items() if isinstance(tree, dict) else enumerate(tree)
    return [part for key, child in items for part in _parts(child, relative + (key,))]


def _as_container(tree, payload):
    if isinstance(tree, _Source):
        value = resolve_pointer(payload, _pointer(tree.path))
        if value == {} and type(value) is dict:
            return {}
        if value == [] and type(value) is list:
            return []
        raise ValueError("Delta traverses a scalar")
    return tree


def _apply_source_delta(root, change, source_path, payload):
    """Follow declared set/remove/append operations with source pointers only."""
    path, operation = change["path"], change["op"]
    if operation not in ("set", "remove", "append"):
        raise ValueError("Unsupported domain delta operation")
    if not path:
        if operation == "set":
            return _source_tree(change["value"], source_path + ("value",))
        if operation == "remove":
            raise ValueError("Cannot remove the state root")
        root = _as_container(root, payload)
        if not isinstance(root, list) or not isinstance(change["value"], list):
            raise ValueError("Append requires lists")
        root.extend(_source_tree(v, source_path + ("value", i))
                    for i, v in enumerate(change["value"]))
        return root
    root = _as_container(root, payload)
    parent = root
    for key in path[:-1]:
        parent[key] = _as_container(parent[key], payload)
        parent = parent[key]
    key = path[-1]
    if operation == "set":
        parent[key] = _source_tree(change["value"], source_path + ("value",))
    elif operation == "remove":
        del parent[key]
    else:
        parent[key] = _apply_source_delta(parent[key], {**change, "path": []},
                                          source_path, payload)
    return root


def _state_index(payload):
    nodes, current = payload["state_nodes"], payload["current_state"]
    chain, seen = [], set()
    while True:
        if current in seen:
            raise ValueError("Cyclic state inheritance")
        seen.add(current)
        node = nodes[current]
        chain.append(current)
        if "inherits" not in node:
            break
        current = node["inherits"]
    chain.reverse()
    first = nodes[chain[0]]
    base = ("state_nodes", chain[0])
    cwd = _source_tree(first["cwd"], base + ("cwd",))
    objects = [_source_tree(obj, base + ("objects", i))
               for i, obj in enumerate(first["objects"])]
    domain = (_source_tree(first["domain_state"], base + ("domain_state",))
              if "domain_state" in first else None)
    for identity in chain[1:]:
        changes = nodes[identity]["changes"]
        base = ("state_nodes", identity, "changes")
        if set(changes) - {"cwd", "objects_updated", "domain_state_updates"}:
            raise ValueError("Unrecognized state update; indexing would be incomplete")
        if "cwd" in changes:
            cwd = _source_tree(changes["cwd"], base + ("cwd",))
        for i, row in enumerate(changes.get("objects_updated", [])):
            slot = row["object_index"]
            if type(slot) is not int or slot < 0 or slot > len(objects):
                raise ValueError("Invalid object index")
            if slot == len(objects):
                objects.append({})
            objects[slot] = _as_container(objects[slot], payload)
            for key, value in row.items():
                if key != "object_index":
                    objects[slot][key] = _source_tree(value, base + ("objects_updated", i, key))
        for i, change in enumerate(changes.get("domain_state_updates", [])):
            if domain is None:
                raise ValueError("Domain delta has no initial state")
            domain = _apply_source_delta(domain, change,
                                        base + ("domain_state_updates", i), payload)
    entries = [{"state_path": ["cwd"], "value_parts": _parts(cwd)}]
    for slot, obj in enumerate(objects):
        for field, tree in _as_container(obj, payload).items():
            if field != "evidence":
                entries.append({"state_path": ["objects", slot, field], "value_parts": _parts(tree)})
    if domain is not None:
        entities = _as_container(domain, payload).get("entities")
        if entities is not None:
            for identity, record in _as_container(entities, payload).items():
                record = _as_container(record, payload)
                fields = record.get("fields")
                if fields is not None:
                    for field, tree in _as_container(fields, payload).items():
                        entries.append({"state_path": ["domain_state", "entities", identity, "fields", field],
                                        "value_parts": _parts(tree)})
    # Observations, goals, task-completion statements, evidence, and retired
    # version archives are not promoted into a view of current state.
    return entries, {"eligible_entries": len(entries), "state_chain_length": len(chain),
                     "state_value_parts": sum(len(e["value_parts"]) for e in entries)}


def state_index(payload):
    """Return reference-only index plus nondelivered eligibility accounting.

    References resolve against the decoded *original* payload. A runner using a
    codec must retain its existing decoding rules; this helper never claims the
    pointers address the packed wire representation. Legacy Event payloads with
    no fact_scope yield no eligible facts rather than inferred scope labels.
    """
    if payload.get("method") == "v1-compact":
        entries, audit = _state_index(payload)
    elif payload.get("method") in ("v2-compact", "v2-dedup"):
        entries, audit = _event_index(payload)
    else:
        raise ValueError("Expected an unpacked supported semantic payload")
    return {"view": {"state_index": entries}, "audit": audit}


def _escape_event_literal(value):
    if isinstance(value, dict):
        content = {k: _escape_event_literal(v) for k, v in value.items()}
        return {"$literal": content} if lossless_event.RESERVED.intersection(value) else content
    if isinstance(value, list):
        return [_escape_event_literal(v) for v in value]
    return deepcopy(value)


def expand_shared_references(encoded):
    """Expand only real references; retain envelope, rules and full dictionary.

    This is deliberately not encode(decode(...)): table/default/column/order
    choices stay fixed. Both existing decoders already accept ordinary literals.
    Event dictionary values require escaping when moved into encoded syntax;
    State dictionary values are already escaped encoded subtrees.
    """
    encoding = encoded.get("encoding")
    if encoding == "state-shared-v1":
        codec, body_key, tag = lossless_state, "payload", "$ref"
    elif encoding == "lossless-event/shared-v1":
        codec, body_key, tag = lossless_event, "graph", "$shared"
    else:
        raise ValueError("Only state-shared-v1 and lossless-event/shared-v1 are supported")
    original = codec.decode(encoded)
    count = 0

    def expand(value):
        nonlocal count
        if isinstance(value, dict):
            if set(value) == {tag}:
                count += 1
                literal = encoded["shared_values"][value[tag]]
                return (_escape_event_literal(literal) if codec is lossless_event else deepcopy(literal))
            if set(value) == {"$literal"}:
                if codec is lossless_state:
                    return deepcopy(value)
                # The escaped object's own keys are original data; references
                # in its encoded children still need expansion.
                return {"$literal": {k: expand(v) for k, v in value["$literal"].items()}}
            return {k: expand(v) for k, v in value.items()}
        if isinstance(value, list):
            return [expand(v) for v in value]
        return deepcopy(value)

    result = deepcopy(encoded)
    result[body_key] = expand(encoded[body_key])
    if not _same(codec.decode(result), original):
        raise AssertionError("Reference expansion changed the typed semantic payload")
    return {"encoded": result,
            "audit": {"expanded_references": count, "typed_decode_equal": True,
                      "dictionary_retained": True, "rules_unchanged": True,
                      "negative_control_unchanged": count == 0 and result == encoded}}
