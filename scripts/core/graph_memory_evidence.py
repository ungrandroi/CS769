"""Lossless graph replacement of completed visible conversation evidence.

The default inference view contains typed evidence nodes, entity/fact nodes and edges.
The explicit episodic view retains all visible evidence and only its event structure.
It cannot read archived source messages. Raw strings live once in evidence-node
fields; facts refer to content evidence instead of copying file contents.
"""
from copy import deepcopy
import hashlib
import json
import re

from core.event_graph import GraphMemoryV2
from core.graph_memory_native import build_native_graph, validate_native_history


VIEW_VERSION = "evidence-graph-g0-v1"
ENTITY_ORIGIN_VIEW_VERSION = "evidence-graph-g4-origin-v1"
EPISODIC_VIEW_VERSION = "evidence-graph-g5-episodic-v1"
EVIDENCE_CATEGORIES = frozenset(("user_request", "assistant_statement", "tool_call", "tool_result"))


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _field(name, value):
    return {"field": name, "value": deepcopy(value), "value_type": type(value).__name__}


def _visible_fields(message):
    content = message.get("content")
    if content is None:
        return []
    if isinstance(content, str):
        return [_field("content", content)]
    if not isinstance(content, list):
        raise ValueError("Unsupported visible content")
    result = []
    for index, block in enumerate(content):
        kind = block.get("type")
        name = "refusal" if kind == "refusal" else "text"
        if kind not in ("text", "input_text", "output_text", "refusal") or not isinstance(block.get(name), str):
            raise ValueError("Unsupported visible content block")
        result.append(_field(f"content.{index}.{name}", block[name]))
    return result


def _records(messages):
    """Canonical evidence records; API metadata and opaque reasoning stay outside."""
    records, calls, returned, turn = [], {}, set(), 0
    for index, message in enumerate(messages):
        role, kind = message.get("role"), message.get("type")
        if role in ("system", "developer") or kind == "reasoning":
            continue
        if role == "user":
            turn += 1
        if role in ("user", "assistant"):
            fields = _visible_fields(message)
            if fields:
                records.append({"category": "user_request" if role == "user" else "assistant_statement",
                    "source_role": role, "source_ref": f"m{index}", "turn": turn,
                    "fields": fields})
        source_calls = message.get("tool_calls") or []
        if kind == "function_call":
            source_calls = [{"id": message["call_id"], "function": message}]
        for call_index, call in enumerate(source_calls):
            identity, function = call["id"], call["function"]
            if not isinstance(identity, str) or identity in calls:
                raise ValueError("Duplicate or invalid tool call ID")
            if not isinstance(function.get("name"), str) or "arguments" not in function:
                raise ValueError("Invalid tool call evidence")
            prefix = "" if kind == "function_call" else f"tool_calls.{call_index}.function."
            calls[identity] = len(records)
            records.append({"category": "tool_call", "source_role": "assistant",
                "source_ref": f"m{index}", "turn": turn,
                "call_id": identity, "fields": [_field(prefix + "name", function["name"]),
                _field(prefix + "arguments", function["arguments"])]})
        if kind == "function_call_output" or role == "tool":
            identity = message.get("call_id", message.get("tool_call_id"))
            if identity not in calls or identity in returned:
                raise ValueError("Unmatched or duplicate tool result")
            field = "output" if kind == "function_call_output" else "content"
            if field not in message:
                raise ValueError("Missing tool result evidence")
            returned.add(identity)
            records.append({"category": "tool_result", "source_role": "tool",
                "source_ref": f"m{index}", "turn": turn, "call_id": identity,
                "fields": [_field(field, message[field])]})
        elif role not in ("user", "assistant") and kind != "function_call":
            raise ValueError("Unsupported normalized evidence message")
    if set(calls) != returned:
        raise ValueError("Graph replacement requires all pending tool results")
    if not turn:
        raise ValueError("Graph replacement requires a visible user request")
    return records


def _semantic_records(records):
    """Compare native/normalized visible content, not provider wrapper metadata."""
    result = []
    for record in records:
        category, fields = record["category"], record["fields"]
        if category in ("user_request", "assistant_statement"):
            for field in fields:
                if field["value"] != "":
                    result.append((record["source_role"], field["value"]))
        elif category == "tool_call":
            arguments = fields[1]["value"]
            arguments = json.loads(arguments) if isinstance(arguments, str) else arguments
            result.append(("call", record["call_id"], fields[0]["value"], arguments))
        else:
            value = fields[0]["value"]
            if isinstance(value, list) and all(isinstance(b, dict) and b.get("type") == "text" for b in value):
                value = "\n".join(b["text"] for b in value)
            result.append(("result", record["call_id"], value))
    return result


def _native_records(messages, provider):
    if provider == "openai":
        return _records(messages)
    result = []
    for index, message in enumerate(messages):
        content = message.get("content")
        if isinstance(content, str):
            result.append({"role": message["role"], "content": content})
            continue
        for block in content or []:
            kind = block.get("type")
            if kind in ("thinking", "redacted_thinking"):
                continue
            if kind == "text":
                result.append({"role": message["role"], "content": block["text"]})
            elif kind == "tool_use":
                result.append({"type": "function_call", "call_id": block["id"],
                               "name": block["name"], "arguments": block["input"]})
            elif kind == "tool_result":
                result.append({"type": "function_call_output", "call_id": block["tool_use_id"],
                               "output": deepcopy(block.get("content", ""))})
            else:
                raise ValueError(f"Unsupported native visible block: {kind}")
    return _records(result)


def _native_attributes(messages, provider):
    groups, errors = {}, {}
    for index, message in enumerate(messages or []):
        if provider == "openai":
            for call in message.get("tool_calls") or []:
                groups[call["id"]] = f"g{index}"
        else:
            content = message.get("content")
            for block in content if isinstance(content, list) else []:
                if block.get("type") == "tool_use":
                    groups[block["id"]] = f"g{index}"
                elif block.get("type") == "tool_result" and "is_error" in block:
                    errors[block["tool_use_id"]] = block["is_error"]
    return groups, errors


def build_evidence_graph(normalized_history, native_history=None, *, provider="openai",
                         native_context=None, snapshot_boundary="end_of_first_user_turn",
                         include_entity_origin=False, episodic_only=False):
    """Build archives plus a self-contained graph preserving complete visible evidence."""
    if type(include_entity_origin) is not bool:
        raise ValueError("Entity origin visibility must be explicitly boolean")
    if type(episodic_only) is not bool:
        raise ValueError("Episodic-only visibility must be explicitly boolean")
    if episodic_only and include_entity_origin:
        raise ValueError("Episodic-only and entity-origin views are mutually exclusive")
    if provider not in ("openai", "anthropic"):
        raise ValueError("Unsupported evidence provider")
    if snapshot_boundary not in ("end_of_first_user_turn", "archived_history_checkpoint"):
        raise ValueError("Unknown evidence snapshot boundary")
    source = deepcopy(normalized_history)
    records = _records(source)
    if native_history is not None:
        graph = build_native_graph(source, native_history, provider=provider,
                                   native_context=native_context, snapshot_boundary=snapshot_boundary)
        if _semantic_records(records) != _semantic_records(_native_records(native_history, provider)):
            raise ValueError("Normalized/native visible evidence differs")
    else:
        graph = GraphMemoryV2().build(source)
    groups, errors = _native_attributes(native_history, provider)
    nodes, edges, ordered, calls, results, episodes = [], [], [], {}, {}, {}

    def edge(start, relation, end, **attrs):
        item = {"from": start, "relation": relation, "to": end, **attrs}
        if item not in edges:
            edges.append(item)

    for ordinal, record in enumerate(records):
        turn = record["turn"]
        if turn not in episodes:
            episodes[turn] = f"t{turn}"
            nodes.append({"id": episodes[turn], "category": "episode", "turn": turn})
        identity = f"e{ordinal}"
        node = {"id": identity, "ordinal": ordinal, **deepcopy(record)}
        node["episode"] = episodes[turn]
        if node["category"] == "tool_call":
            calls[node["call_id"]] = identity
            node["call_group"] = groups.get(node["call_id"], node["source_ref"])
        if node["category"] == "tool_result":
            results[node["call_id"]] = identity
            node["result_of"] = calls[node["call_id"]]
            if node["call_id"] in errors:
                node["native_is_error"] = errors[node["call_id"]]
            edge(identity, "result_of", node["result_of"])
        nodes.append(node)
        edge(identity, "in_turn", episodes[turn])
        if ordered:
            edge(ordered[-1], "precedes", identity)
        ordered.append(identity)

    original = {node["id"]: node for node in graph["nodes"]}
    event_to_result = {node["id"]: results[node["call_id"]] for node in original.values()
                       if node["category"] == "event"}
    event_to_call = {node["id"]: calls[node["call_id"]] for node in original.values()
                     if node["category"] == "event"}
    steps = {node["step"]: event_to_result[node["id"]] for node in original.values()
             if node["category"] == "event"}
    fact_order = []
    for fact in original.values():
        if fact["category"] != "fact":
            continue
        # Identity placeholders were never observations and are not facts to tell the model.
        if fact["predicate"] == "cwd" and fact["value"].get("value") is None:
            continue
        support = [event_to_result[c["event"]] for c in fact["confirmations"]]
        if not support:
            raise ValueError("Derived fact lacks visible provenance")
        item = {"id": fact["id"], "category": "fact", "subject": fact["subject"],
                "predicate": fact["predicate"], "key": deepcopy(fact["key"]),
                "version": fact["version"], "valid_from": steps[fact["first_observed_at"]],
                "valid_until": steps.get(fact["retired_at"]),
                "current": fact["retired_at"] is None}
        if fact["predicate"] == "content":
            derived = [e["to"] for e in graph["edges"]
                       if e["from"] == fact["id"] and e["relation"] == "derived_from"]
            item["value_reference"] = {"facts": derived, "observations": support}
        else:
            item["value"] = deepcopy(fact["value"])
        nodes.append(item)
        fact_order.append(item["id"])
        edge(item["id"], "refers_to", item["subject"])
        for observation in support:
            edge(observation, "supports", item["id"])
    visible_facts = set(fact_order)
    for node in original.values():
        if node["category"] == "object":
            item = {"id": node["id"], "category": "entity",
                    "observed_at": steps.get(node["first_observed_at"])}
            if include_entity_origin:
                if not isinstance(node.get("origin"), str):
                    raise ValueError("Entity origin must be an existing source string")
                item["origin"] = node["origin"]
            nodes.append(item)
    for relation in graph["edges"]:
        left, right, kind = relation["from"], relation["to"], relation["relation"]
        if kind in ("supersedes", "derived_from") and left in visible_facts and right in visible_facts:
            edge(left, kind, right)
        elif kind == "acts_on":
            edge(event_to_call[left], "refers_to", right)
        elif kind == "resolved_using" and right in visible_facts:
            edge(event_to_call[left], "refers_to", right, role="resolution_context")
        elif kind in ("located_in", "current_directory", "parent_directory") and left in visible_facts:
            edge(left, "refers_to", right, role=kind)
        elif kind == "copied_from":
            edge(left, "copied_from", right)
    version = ENTITY_ORIGIN_VIEW_VERSION if include_entity_origin else VIEW_VERSION
    view = {"version": version, "snapshot_boundary": snapshot_boundary, "provider": provider,
            "nodes": nodes, "edges": edges, "recorded_order": ordered, "fact_order": fact_order}
    if episodic_only:
        view = episodic_evidence_view(view)
    graph.update(delivery="graph_replaces_native_visible_prefix", evidence_view=view,
                 evidence_audit={"view_sha256": _digest(view), "visible_sha256": _digest(records),
                                 "normalized_visible_record_count": len(records),
                                 "native_visible_compared": native_history is not None})
    if include_entity_origin:
        graph["delivery_entity_origin"] = True
    if episodic_only:
        graph["delivery_episodic_only"] = True
    audit_evidence_graph(graph, normalized_history=source, native_history=native_history)
    return graph


def episodic_evidence_view(view):
    """Uniform schema-layer ablation; complete visible evidence, not full semantic graph.

    Only the supplied graph view is read. All non-derived nodes and their induced
    edges remain exact; no source history, task text or relevance rule is used.
    """
    if view.get("version") not in (VIEW_VERSION, ENTITY_ORIGIN_VIEW_VERSION):
        raise ValueError("Episodic projection requires a known full evidence view")
    if set(view) != {"version", "snapshot_boundary", "provider", "nodes", "edges", "recorded_order", "fact_order"}:
        raise ValueError("Unknown evidence view fields for episodic projection")
    known = EVIDENCE_CATEGORIES | {"episode", "entity", "fact"}
    if any(node.get("category") not in known for node in view["nodes"]):
        raise ValueError("Unknown node category for episodic projection")
    all_ids = [node["id"] for node in view["nodes"]]
    if len(all_ids) != len(set(all_ids)):
        raise ValueError("Duplicate graph node")
    kept = {node["id"] for node in view["nodes"] if node["category"] not in ("entity", "fact")}
    known_relations = {"in_turn", "precedes", "result_of", "refers_to", "supports", "supersedes", "derived_from", "copied_from"}
    if any(edge.get("relation") not in known_relations for edge in view["edges"]):
        raise ValueError("Unknown edge relation for episodic projection")
    if any(edge.get("from") not in all_ids or edge.get("to") not in all_ids for edge in view["edges"]):
        raise ValueError("Dangling evidence graph edge before episodic projection")
    result = deepcopy(view)
    result["version"] = EPISODIC_VIEW_VERSION
    result["nodes"] = [node for node in result["nodes"] if node["id"] in kept]
    result["edges"] = [edge for edge in result["edges"] if edge["from"] in kept and edge["to"] in kept]
    result["fact_order"] = []
    _audit_episodic_view(result)
    return result


def _audit_episodic_view(view):
    """Validate the self-contained event graph even if an attacker rehashes it."""
    if view.get("version") != EPISODIC_VIEW_VERSION or view.get("fact_order") != []:
        raise ValueError("Invalid episodic view version or derived fact order")
    nodes = {node["id"]: node for node in view["nodes"]}
    if len(nodes) != len(view["nodes"]):
        raise ValueError("Duplicate episodic graph node")
    episodes = {}
    records = []
    for node in view["nodes"]:
        category = node.get("category")
        if category == "episode":
            if (set(node) != {"id", "category", "turn"} or type(node["turn"]) is not int or
                    node["turn"] < 0 or node["id"] != f't{node["turn"]}' or node["turn"] in episodes):
                raise ValueError("Malformed episodic boundary")
            episodes[node["turn"]] = node["id"]
        elif category in EVIDENCE_CATEGORIES:
            records.append(node)
        else:
            raise ValueError("Episodic view contains a derived or unknown node")
    if not records or view.get("recorded_order") != [node["id"] for node in records]:
        raise ValueError("Episodic recorded order differs from evidence nodes")
    expected_edges, expected_node_ids, visited_episodes = [], [], set()
    calls, results, groups = {}, set(), {}
    previous_turn = -1
    for ordinal, node in enumerate(records):
        category = node["category"]
        expected_role = {"user_request": "user", "assistant_statement": "assistant",
                         "tool_call": "assistant", "tool_result": "tool"}[category]
        required = {"id", "category", "ordinal", "source_role", "source_ref", "turn", "fields", "episode"}
        optional = set()
        if category == "tool_call":
            required |= {"call_id", "call_group"}
        elif category == "tool_result":
            required |= {"call_id", "result_of"}
            optional = {"native_is_error"}
        if not required <= set(node) or set(node) - required - optional:
            raise ValueError("Malformed episodic evidence node fields")
        if (node["id"] != f"e{ordinal}" or type(node["ordinal"]) is not int or node["ordinal"] != ordinal or
                node["source_role"] != expected_role or not isinstance(node["source_ref"], str) or
                not re.fullmatch(r"m[0-9]+", node["source_ref"]) or type(node["turn"]) is not int or
                node["turn"] < previous_turn or episodes.get(node["turn"]) != node["episode"]):
            raise ValueError("Malformed episodic source, order or episode reference")
        previous_turn = node["turn"]
        if node["episode"] not in visited_episodes:
            visited_episodes.add(node["episode"])
            expected_node_ids.append(node["episode"])
        expected_node_ids.append(node["id"])
        fields = node["fields"]
        if not isinstance(fields, list) or not fields:
            raise ValueError("Missing episodic visible evidence fields")
        if any(not isinstance(field, dict) or set(field) != {"field", "value", "value_type"} or
               not isinstance(field["field"], str) or field["value_type"] != type(field["value"]).__name__
               for field in fields):
            raise ValueError("Malformed episodic visible field type")
        names = [field["field"] for field in fields]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate episodic visible field")
        if category in ("user_request", "assistant_statement"):
            if any(not isinstance(field["value"], str) or
                   not re.fullmatch(r"content(?:\.[0-9]+\.(?:text|refusal))?", field["field"]) for field in fields):
                raise ValueError("Malformed episodic visible text")
        elif category == "tool_call":
            if (len(fields) != 2 or not isinstance(fields[0]["value"], str) or
                    not re.fullmatch(r"(?:tool_calls\.[0-9]+\.function\.)?name", names[0]) or
                    names[1] != names[0][:-4] + "arguments" or
                    not isinstance(node["call_id"], str) or node["call_id"] in calls or
                    not isinstance(node["call_group"], str) or not re.fullmatch(r"[gm][0-9]+", node["call_group"])):
                raise ValueError("Malformed episodic tool call or group")
            if node["call_group"] in groups and groups[node["call_group"]] != node["episode"]:
                raise ValueError("Episodic call group crosses episodes")
            groups[node["call_group"]] = node["episode"]
            calls[node["call_id"]] = node
        else:
            call = calls.get(node["call_id"])
            if (len(fields) != 1 or names[0] not in ("content", "output") or call is None or
                    node["call_id"] in results or node["result_of"] != call["id"] or
                    node["episode"] != call["episode"] or
                    ("native_is_error" in node and type(node["native_is_error"]) is not bool)):
                raise ValueError("Malformed episodic tool-result link")
            results.add(node["call_id"])
            expected_edges.append({"from": node["id"], "relation": "result_of", "to": node["result_of"]})
        expected_edges.append({"from": node["id"], "relation": "in_turn", "to": node["episode"]})
        if ordinal:
            expected_edges.append({"from": records[ordinal-1]["id"], "relation": "precedes", "to": node["id"]})
    if set(calls) != results:
        raise ValueError("Missing episodic tool results")
    if set(episodes.values()) != visited_episodes or [node["id"] for node in view["nodes"]] != expected_node_ids:
        raise ValueError("Episodic boundary or node sequence differs")
    if view["edges"] != expected_edges:
        raise ValueError("Episodic edges differ from recorded episode, call-result and order structure")


def inference_graph(graph):
    """No archive, original native messages, or alternative raw transcript survives."""
    return {key: deepcopy(graph[key]) for key in ("delivery", "evidence_view", "evidence_audit")}


def reconstruct_visible_evidence(graph):
    """Recover every visible source field from typed graph nodes, without archives."""
    view = graph["evidence_view"]
    nodes = {node["id"]: node for node in view["nodes"]}
    result = []
    for identity in view["recorded_order"]:
        node = nodes[identity]
        record = {key: deepcopy(node[key]) for key in
                  ("category", "source_role", "source_ref", "turn", "fields")}
        if "call_id" in node:
            record["call_id"] = node["call_id"]
        result.append(record)
    return result


def audit_evidence_graph(graph, normalized_history=None, native_history=None):
    view = graph["evidence_view"]
    if view.get("version") not in (VIEW_VERSION, ENTITY_ORIGIN_VIEW_VERSION, EPISODIC_VIEW_VERSION):
        raise ValueError("Unsupported evidence view")
    if _digest(view) != graph["evidence_audit"]["view_sha256"]:
        raise ValueError("Evidence graph integrity hash mismatch")
    nodes = {node["id"]: node for node in view["nodes"]}
    if len(nodes) != len(view["nodes"]):
        raise ValueError("Duplicate graph node")
    for node in nodes.values():
        if node["category"] == "entity":
            if view["version"] == ENTITY_ORIGIN_VIEW_VERSION:
                if not isinstance(node.get("origin"), str):
                    raise ValueError("Entity origin must be an existing source string")
            elif "origin" in node:
                raise ValueError("Entity origin requires the explicit origin view version")
    for edge in view["edges"]:
        if edge["from"] not in nodes or edge["to"] not in nodes:
            raise ValueError("Dangling evidence graph edge")
    if view["version"] == EPISODIC_VIEW_VERSION:
        _audit_episodic_view(view)
    records = reconstruct_visible_evidence(graph)
    if _digest(records) != graph["evidence_audit"]["visible_sha256"]:
        raise ValueError("Visible evidence integrity hash mismatch")
    if normalized_history is not None:
        expected_records = _records(normalized_history)
        if records != expected_records or (view["version"] == EPISODIC_VIEW_VERSION and
                _digest(records) != _digest(expected_records)):
            raise ValueError("Visible evidence roundtrip mismatch")
    if native_history is not None:
        validate_native_history(native_history, view["provider"], snapshot_boundary=view["snapshot_boundary"])
        semantic_records = _semantic_records(records)
        native_records = _semantic_records(_native_records(native_history, view["provider"]))
        if semantic_records != native_records or (view["version"] == EPISODIC_VIEW_VERSION and
                _digest(semantic_records) != _digest(native_records)):
            raise ValueError("Normalized/native visible evidence differs")
        if view["version"] == EPISODIC_VIEW_VERSION:
            groups, errors = _native_attributes(native_history, view["provider"])
            for node in nodes.values():
                if node["category"] == "tool_call" and node["call_group"] != groups.get(node["call_id"], node["source_ref"]):
                    raise ValueError("Episodic call group differs from native source")
                if node["category"] == "tool_result" and (
                        ("native_is_error" in node) != (node["call_id"] in errors) or
                        node.get("native_is_error") != errors.get(node["call_id"])):
                    raise ValueError("Episodic error attribute differs from native source")
    return {"integrity_ok": True, "visible_record_count": len(records),
            "visible_field_count": sum(len(record["fields"]) for record in records),
            "tool_exchange_count": sum(record["category"] == "tool_call" for record in records),
            "fact_count": len(view["fact_order"]), "graph_node_count": len(nodes),
            "view_sha256": _digest(view), "visible_sha256": _digest(records)}


def render_evidence_segments(graph, *, layout="chronological-first"):
    """Render only the self-contained graph; raw strings are unmodified segments."""
    if layout not in ("chronological-first", "structure-first"):
        raise ValueError("Unsupported graph evidence layout")
    audit_evidence_graph(graph)
    view = graph["evidence_view"]
    nodes = {node["id"]: node for node in view["nodes"]}
    field_texts = [field["value"] if isinstance(field["value"], str) else _json(field["value"])
                   for identity in view["recorded_order"] for field in nodes[identity]["fields"]]
    fence = "`" * max(3, 1 + max((len(m.group()) for text in field_texts
                                 for m in re.finditer(r"`+", text)), default=0))
    segments = [{"kind": "format", "text": '<memory_graph scope="completed_prior_turns">\n'
        'Nodes contain prior visible evidence. IDs link episodes, calls, results, entities and fact versions. '
        'order is recorded sequence; call_group identifies calls in the same assistant message. '
        'Fact intervals use result observations and exclude their end.\n'}]
    if view["version"] == EPISODIC_VIEW_VERSION:
        segments[0]["text"] = ('<memory_graph scope="completed_prior_turns">\n'
            'Nodes contain prior visible evidence. IDs link episodes, calls and results. '
            'order is recorded sequence; call_group identifies calls in the same assistant message.\n')
    current_episode = None
    for identity in view["recorded_order"]:
        node = nodes[identity]
        if node["episode"] != current_episode:
            current_episode = node["episode"]
            segments.append({"kind": "label", "text": f'EPISODE {current_episode}\n'})
        label = (f'{node["category"]} {identity} source_role={node["source_role"]} '
                 f'in_turn={current_episode} order={node["ordinal"]}')
        if node["category"] == "tool_call":
            label += f' call_id={_json(node["call_id"])} call_group={node["call_group"]}'
        if node["category"] == "tool_result":
            label += f' result_of={node["result_of"]}'
            if "native_is_error" in node:
                label += f' native_is_error={_json(node["native_is_error"])}'
        segments.append({"kind": "label", "text": label + "\n"})
        for field in node["fields"]:
            name = field["field"].rsplit(".", 1)[-1]
            text = field["value"] if isinstance(field["value"], str) else _json(field["value"])
            segments.append({"kind": "label", "text": f'{name} [{field["value_type"]}]\n{fence}\n'})
            segments.append({"kind": "evidence", "text": text, "node_id": identity,
                             "field": field["field"], "value_type": field["value_type"]})
            segments.append({"kind": "label", "text": f"\n{fence}\n"})
    if view["recorded_order"]:
        segments.append({"kind": "relations", "text": "precedes: " + " -> ".join(view["recorded_order"]) + "\n"})
    entities = [node for node in view["nodes"] if node["category"] == "entity"]
    if entities:
        def entity_line(node):
            origin = (f' origin={_json(node["origin"])}'
                      if view["version"] == ENTITY_ORIGIN_VIEW_VERSION else "")
            return f'{node["id"]}{origin} observed_at={node["observed_at"] or "initial_boundary"}'
        segments.append({"kind": "state", "text": "ENTITIES\n" + "\n".join(
            entity_line(node) for node in entities) + "\n"})
    if view["fact_order"]:
        segments.append({"kind": "state", "text": "FACT VERSIONS\n"})
    for identity in view["fact_order"]:
        node = nodes[identity]
        value = ("evidence@" + _json(node["value_reference"]) if "value_reference" in node
                 else _json(node["value"]))
        key = "" if node["key"] is None else f'[{_json(node["key"])}]'
        interval = f'[{node["valid_from"]},{node["valid_until"] or "snapshot_end"})'
        segments.append({"kind": "state", "text": f'{identity} {node["subject"]}.{node["predicate"]}{key}={value} '
            f'version={node["version"]} interval={interval} current={str(node["current"]).lower()}\n'})
    structural = [edge for edge in view["edges"] if edge["relation"] not in ("precedes", "in_turn", "result_of")]
    if structural:
        segments.append({"kind": "relations", "text": "RELATIONS\n"})
    for edge in structural:
        role = f' ({edge["role"]})' if edge.get("role") else ""
        segments.append({"kind": "relations", "text": f'{edge["from"]} {edge["relation"]}{role} {edge["to"]}\n'})
    segments.append({"kind": "format", "text": "</memory_graph>\n"})
    if layout == "structure-first":
        # A controlled permutation, not a different graph or a shorter memory:
        # every original segment survives verbatim. The chronological evidence
        # sequence stays intact; only the graph-structure appendix moves.
        structure_start = next((index for index, segment in enumerate(segments)
                                if segment["kind"] in ("state", "relations")), len(segments) - 1)
        segments = (segments[:1] + segments[structure_start:-1]
                    + segments[1:structure_start] + segments[-1:])
    return segments


def render_evidence_graph(graph, *, layout="chronological-first"):
    return "".join(segment["text"] for segment in render_evidence_segments(graph, layout=layout))
