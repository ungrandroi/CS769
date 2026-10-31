"""G6: deterministic reference-token anchors over an unchanged G5 inference graph.

Anchors group observed tokens in declared namespaces, NOT external object identity,
causation, current state, or mutation success. All values remain in G5 fields. The
new layer contains only exact source pointers and reproducible annotations. No
archive, evaluator, tool implementation, future turn, or model is consulted.
"""
from collections import defaultdict
from copy import deepcopy
from decimal import Decimal
import hashlib
import json

from core.graph_memory_evidence import (
    EPISODIC_VIEW_VERSION, audit_evidence_graph, render_evidence_graph,
)


VERSION = "structured-evidence-anchors-v1"
RULESET = "bfcl-public-reference-fields-v1"
VARIANTS = ("anchors-v1", "occurrences-only-v1")
BASE_KEYS = frozenset(("delivery", "evidence_view", "evidence_audit"))


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _digest(value):
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key")
        result[key] = value
    return result


def _strict_json(text):
    def invalid(value):
        raise ValueError("Non-finite JSON number: " + value)
    return json.loads(text, object_pairs_hook=_unique_object,
                      parse_float=Decimal, parse_constant=invalid)


def _escape(token):
    return str(token).replace("~", "~0").replace("/", "~1")


def _pointer(root, pointer):
    if pointer == "":
        return root
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise ValueError("Invalid JSON Pointer")
    current = root
    for raw in pointer.split("/")[1:]:
        # Refuse malformed escape sequences and noncanonical list indices.
        tail = raw.replace("~1", "").replace("~0", "")
        if "~" in tail:
            raise ValueError("Invalid JSON Pointer escape")
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            if not token.isdigit() or str(int(token)) != token:
                raise ValueError("Invalid JSON Pointer array index")
            current = current[int(token)]
        elif isinstance(current, dict):
            current = current[token]
        else:
            raise ValueError("JSON Pointer enters a scalar")
    return current


def _leaves(value, pointer="", key=""):
    if isinstance(value, dict):
        for name, item in value.items():
            yield from _leaves(item, pointer + "/" + _escape(name), name)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _leaves(item, pointer + "/" + str(index), key)
    else:
        yield pointer, key, value


def _documents(value):
    """Return (document pointer, encoding, parsed value); never guess JSON in prose."""
    if isinstance(value, str):
        try:
            return [("", "json_text", _strict_json(value))]
        except (ValueError, TypeError, RecursionError):
            return []
    if isinstance(value, list) and value and all(
            isinstance(block, dict) and block.get("type") == "text"
            and isinstance(block.get("text"), str) for block in value):
        result = []
        for index, block in enumerate(value):
            try:
                result.append((f"/{index}/text", "json_text", _strict_json(block["text"])))
            except (ValueError, TypeError, RecursionError):
                pass
        return result
    if isinstance(value, (dict, list)):
        return [("", "native_json", value)]
    return []


# Static extraction locations transcribed from the public, vendored BFCL tool
# docs: data/multi_turn_func_doc/{gorilla_file_system,ticket_api,message_api,
# posting_api,travel_booking,trading_bot}.json. They are LOCATION contracts only.
# No hidden implementation or expected-answer data is read, even at build time.
_CONTRACTS = []


def _contract(tools, role, paths, namespace, value_type="str"):
    for tool in tools.split():
        for path in paths.split():
            _CONTRACTS.append((tool, role, path, namespace, value_type))


_contract("cat echo grep rm sort tail touch wc", "argument", "/file_name", "filesystem:path_literal")
_contract("cd", "argument", "/folder", "filesystem:path_literal")
_contract("cp mv", "argument", "/source /destination", "filesystem:path_literal")
_contract("diff", "argument", "/file_name1 /file_name2", "filesystem:path_literal")
_contract("mkdir rmdir", "argument", "/dir_name", "filesystem:path_literal")
_contract("find", "argument", "/path", "filesystem:path_literal")
_contract("find", "result", "/matches/*", "filesystem:path_literal")
_contract("ls", "result", "/current_directory_content/*", "filesystem:path_literal")
_contract("pwd", "result", "/current_working_directory", "filesystem:path_literal")
_contract("close_ticket edit_ticket get_ticket resolve_ticket", "argument", "/ticket_id", "tickets:ticket_id", "int")
_contract("create_ticket get_ticket", "result", "/id", "tickets:ticket_id", "int")
_contract("delete_message send_message", "argument", "/receiver_id", "message:user_id")
_contract("message_login", "argument", "/user_id", "message:user_id")
_contract("get_user_id", "result", "/user_id", "message:user_id")
_contract("comment get_tweet get_tweet_comments mention retweet", "argument", "/tweet_id", "posting:tweet_id", "int")
_contract("get_tweet post_tweet", "result", "/id", "posting:tweet_id", "int")
_contract("cancel_booking contact_customer_support purchase_insurance retrieve_invoice", "argument", "/booking_id", "travel:booking_id")
_contract("book_flight", "result", "/booking_id /booking_history/booking_id", "travel:booking_id")
_contract("book_flight get_credit_card_balance purchase_insurance", "argument", "/card_id", "travel:card_id")
_contract("register_credit_card", "result", "/card_id", "travel:card_id")
_contract("retrieve_invoice", "argument", "/insurance_id", "travel:insurance_id")
_contract("cancel_order get_order_details", "argument", "/order_id", "trading:order_id", "int")
_contract("place_order", "result", "/order_id", "trading:order_id", "int")
_contract("get_order_details", "result", "/id", "trading:order_id", "int")
_contract("get_stock_info place_order remove_stock_from_watchlist", "argument", "/symbol", "trading:stock_symbol")
_contract("add_to_watchlist", "argument", "/stock", "trading:stock_symbol")
_contract("get_order_details get_symbol_by_name", "result", "/symbol", "trading:stock_symbol")
_CONTRACTS = tuple(_CONTRACTS)
_LITERAL_KEYS = frozenset(("id", "path", "file_name", "folder", "dir_name", "source", "destination"))


def _match_pattern(pattern, pointer):
    a, b = pattern.split("/"), pointer.split("/")
    return len(a) == len(b) and all(x == y or (x == "*" and y.isdigit()) for x, y in zip(a, b))


def _classify(tool, role, pointer, key, value):
    value_type = type(value).__name__
    if value_type not in ("str", "int") or value == "":
        return None
    for name, expected_role, pattern, namespace, expected_type in _CONTRACTS:
        if tool == name and role == expected_role and _match_pattern(pattern, pointer):
            if value_type != expected_type:
                return None  # A contract type violation must not become a weak identity.
            return namespace, "contract_token", f"{tool}:{role}:{pattern}", value_type
    if key in _LITERAL_KEYS or key.endswith("_id") or key.endswith("_path"):
        # Deliberately tool-scoped; generic id=1 in two services never merges.
        return f"literal:{tool}:{key}", "weak_literal", "literal-field-v1:" + key, value_type
    return None


def strip_structured_graph(graph):
    """Remove only the added layer, recovering the exact G5 inference object."""
    return {key: deepcopy(graph[key]) for key in BASE_KEYS}


def _require_base(graph):
    if not isinstance(graph, dict) or set(graph) != BASE_KEYS:
        raise ValueError("Expected only the G5 inference graph; archives are not accepted")
    if graph["evidence_view"].get("version") != EPISODIC_VIEW_VERSION:
        raise ValueError("Structured anchors require the G5 episodic inference view")
    audit_evidence_graph(graph)


def _make_layer(base, variant):
    view = base["evidence_view"]
    by_id = {node["id"]: node for node in view["nodes"]}
    calls = {}
    group_start = {}
    for node in view["nodes"]:
        if node["category"] == "tool_call":
            name = next(f["value"] for f in node["fields"] if f["field"].endswith("name"))
            calls[node["id"]] = (node, name)
            key = node["call_group"]
            group_start[key] = min(group_start.get(key, node["ordinal"]), node["ordinal"])
    occurrences, buckets = [], defaultdict(list)
    stats = {"candidate_fields": 0, "parsed_documents": 0, "opaque_fields": 0}
    for event_id in view["recorded_order"]:
        event = by_id[event_id]
        if event["category"] not in ("tool_call", "tool_result"):
            continue
        role = "argument" if event["category"] == "tool_call" else "result"
        call, tool = calls[event_id if role == "argument" else event["result_of"]]
        for field in event["fields"]:
            if role == "argument" and not field["field"].endswith("arguments"):
                continue
            stats["candidate_fields"] += 1
            documents = _documents(field["value"])
            stats["parsed_documents"] += len(documents)
            stats["opaque_fields"] += not bool(documents)
            for document_pointer, encoding, document in documents:
                for pointer, key, value in _leaves(document):
                    classified = _classify(tool, role, pointer, key, value)
                    if classified is None:
                        continue
                    namespace, kind, rule, value_type = classified
                    source = {"event_id": event_id, "field": field["field"],
                              "document_pointer": document_pointer, "encoding": encoding,
                              "pointer": pointer, "field_sha256": _digest(field["value"])}
                    value_digest = _digest([value_type, value])
                    occurrence = {"id": "g6:o:" + _digest(source), "category": "reference_occurrence",
                                  "source": source, "role": role, "tool": tool,
                                  "namespace": namespace, "reference_kind": kind, "rule_id": rule,
                                  "value_type": value_type, "value_sha256": value_digest,
                                  "ordinal": event["ordinal"], "call": call["id"]}
                    occurrences.append(occurrence)
                    buckets[(namespace, kind, value_type, value_digest)].append(occurrence)
    anchors, edges = [], []

    def edge(start, relation, end, support):
        item = {"from": start, "relation": relation, "to": end, "supports": support}
        item["id"] = "g6:x:" + _digest(item)
        edges.append(item)

    for key, members in buckets.items():
        namespace, kind, value_type, value_digest = key
        anchor = {"id": "g6:a:" + _digest(list(key)), "category": "reference_anchor",
                  "namespace": namespace, "reference_kind": kind, "value_type": value_type,
                  "value_sha256": value_digest, "representative": deepcopy(members[0]["source"])}
        anchors.append(anchor)
        if variant == "anchors-v1":
            for member in members:
                edge(member["id"], "has_reference_token", anchor["id"],
                     [deepcopy(member["source"]), deepcopy(anchor["representative"])])
            for argument in (m for m in members if m["role"] == "argument"):
                start = group_start[calls[argument["call"]][0]["call_group"]]
                for prior in members:
                    if prior["role"] == "result" and prior["ordinal"] < start:
                        edge(prior["id"], "equal_value_prior", argument["id"],
                             [deepcopy(prior["source"]), deepcopy(argument["source"])])
    return {"version": VERSION, "ruleset": RULESET, "variant": variant,
            "relation_semantics": "shared observed reference tokens; no causal or current-state claims",
            "base_inference_sha256": _digest(base),
            "base_view_sha256": _digest(view),
            "base_visible_sha256": base["evidence_audit"]["visible_sha256"],
            "nodes": occurrences + anchors, "edges": edges, "extraction_stats": stats}


def build_structured_graph(g5_graph, variant="anchors-v1"):
    if variant not in VARIANTS:
        raise ValueError("Unknown structured graph variant")
    _require_base(g5_graph)
    result = deepcopy(g5_graph)
    result["structured_layer"] = _make_layer(g5_graph, variant)
    return result


def resolve_source(graph, source):
    """Resolve an exact field/subdocument/JSON-pointer location without archives."""
    nodes = [n for n in graph["evidence_view"]["nodes"] if n["id"] == source["event_id"]]
    if len(nodes) != 1:
        raise ValueError("Missing or duplicate source event")
    fields = [f for f in nodes[0]["fields"] if f["field"] == source["field"]]
    if len(fields) != 1:
        raise ValueError("Missing or duplicate source field")
    value = fields[0]["value"]
    if _digest(value) != source["field_sha256"]:
        raise ValueError("Source field changed")
    document = _pointer(value, source["document_pointer"])
    if source["encoding"] == "json_text":
        if not isinstance(document, str):
            raise ValueError("Expected a JSON text source")
        document = _strict_json(document)
    elif source["encoding"] != "native_json":
        raise ValueError("Unknown source encoding")
    return _pointer(document, source["pointer"])


def audit_structured_graph(graph):
    """Return an audit, including failures; never silently repair a graph."""
    errors, payload_preserved = [], False
    layer = graph.get("structured_layer", {}) if isinstance(graph, dict) else {}
    if not isinstance(layer, dict) or any(
            not isinstance(layer.get(key, []), list) or
            any(not isinstance(item, dict) for item in layer.get(key, []))
            for key in ("nodes", "edges")):
        return {"ok": False, "errors": ["Malformed structured layer"],
                "variant": None, "payload_preserved": False, "node_count": 0,
                "edge_count": 0, "new_edge_count": 0, "anchor_count": 0,
                "occurrence_count": 0, "prior_value_edge_count": 0}
    nodes, edges = layer.get("nodes", []), layer.get("edges", [])
    try:
        if set(graph) != BASE_KEYS | {"structured_layer"}:
            raise ValueError("Structured inference object has unexpected keys")
        base = strip_structured_graph(graph)
        _require_base(base)
        payload_preserved = (_digest(base) == layer.get("base_inference_sha256") and
                             _digest(base["evidence_view"]) == layer.get("base_view_sha256") and
                             base["evidence_audit"]["visible_sha256"] == layer.get("base_visible_sha256"))
        if not payload_preserved:
            errors.append("Base payload preservation proof differs")
        if layer.get("variant") not in VARIANTS:
            raise ValueError("Unknown structured variant")
        all_ids = [n["id"] for n in base["evidence_view"]["nodes"]] + [n["id"] for n in nodes]
        if len(set(all_ids)) != len(all_ids):
            errors.append("Duplicate graph node ID")
        edge_ids = [e["id"] for e in edges]
        if len(set(edge_ids)) != len(edge_ids):
            errors.append("Duplicate structured edge ID")
        by_id = {n["id"]: n for n in nodes}
        for node in nodes:
            source = node.get("source", node.get("representative"))
            value = resolve_source(graph, source)
            if type(value).__name__ != node["value_type"] or _digest([node["value_type"], value]) != node["value_sha256"]:
                errors.append("Node pointer value/type mismatch: " + node["id"])
        for edge in edges:
            if edge["from"] not in by_id or edge["to"] not in by_id:
                errors.append("Dangling structured edge: " + edge["id"])
            values = [resolve_source(graph, source) for source in edge["supports"]]
            if len(values) != 2 or type(values[0]) is not type(values[1]) or values[0] != values[1]:
                errors.append("Edge support values are not exactly equal: " + edge["id"])
        # Full rule regeneration verifies pointer choices, role, namespace, order,
        # call-group availability, missing/extra edges, and every annotation key.
        expected = _make_layer(base, layer["variant"])
        if _json(expected) != _json(layer):
            errors.append("Structured layer differs from deterministic source derivation")
    except (ValueError, KeyError, TypeError, IndexError, RecursionError) as exc:
        errors.append(str(exc))
    return {"ok": not errors, "errors": errors, "variant": layer.get("variant"),
            "payload_preserved": payload_preserved, "node_count": len(nodes),
            "edge_count": len(edges), "new_edge_count": len(edges),
            "anchor_count": sum(n.get("category") == "reference_anchor" for n in nodes),
            "occurrence_count": sum(n.get("category") == "reference_occurrence" for n in nodes),
            "prior_value_edge_count": sum(e.get("relation") == "equal_value_prior" for e in edges)}


def _source_label(source):
    document = "@" + source["document_pointer"] if source["document_pointer"] else ""
    return source["event_id"] + "." + source["field"] + document + "#" + source["pointer"]


def render_structured_graph(graph):
    audit = audit_structured_graph(graph)
    if not audit["ok"]:
        raise ValueError("Invalid structured graph: " + "; ".join(audit["errors"]))
    base = render_evidence_graph(strip_structured_graph(graph))
    layer = graph["structured_layer"]
    # Short presentation aliases do not alter stable graph IDs or payload bytes.
    aliases, counters = {}, {"o": 0, "a": 0}
    for node in layer["nodes"]:
        prefix = "o" if node["category"] == "reference_occurrence" else "a"
        aliases[node["id"]] = prefix + str(counters[prefix])
        counters[prefix] += 1
    lines = ['<reference_graph semantics="observed_tokens">',
             "Anchors group recorded tokens, not external objects or current state. # is a JSON Pointer; @ locates a text block.",
             "ANCHORS"]
    for node in (n for n in layer["nodes"] if n["category"] == "reference_anchor"):
        source = node["representative"]
        # The exact scalar is repeated ONCE per anchor for readability. All raw
        # evidence remains unchanged; this added display cost is measurable.
        lines.append(f'{aliases[node["id"]]} {node["namespace"]}={_json(resolve_source(graph, source))} '
                     f'kind={node["reference_kind"]} evidence={_source_label(source)}')
    lines.append("OCCURRENCES")
    for node in (n for n in layer["nodes"] if n["category"] == "reference_occurrence"):
        lines.append(f'{aliases[node["id"]]} {node["role"]} {node["tool"]} '
                     f'evidence={_source_label(node["source"])}')
    lines.append("EDGES (member: same typed token in namespace; prior: earlier visible result equals later argument, not causation)")
    relation_names = {"has_reference_token": "member", "equal_value_prior": "prior"}
    for edge in layer["edges"]:
        lines.append(f'{aliases[edge["from"]]} {relation_names[edge["relation"]]} {aliases[edge["to"]]}')
    lines.append("</reference_graph>")
    return base + "\n" + "\n".join(lines) + "\n"


def _source_removed(source, removed_nodes, removed_sources):
    if source["event_id"] in removed_nodes:
        return True
    for item in removed_sources:
        if source["event_id"] != item["event_id"] or source["field"] != item["field"]:
            continue
        # Even a subtree deletion changes the raw field's hash. This conservative
        # invalidation also handles array index shifts. A future transformation
        # can regenerate surviving occurrences and pointers from the edited field.
        return True
    return False


def _validate_removed_sources(graph, sources):
    nodes = {n["id"]: n for n in graph["evidence_view"]["nodes"]}
    for source in sources:
        node = nodes[source["event_id"]]
        fields = [f for f in node["fields"] if f["field"] == source["field"]]
        if len(fields) != 1:
            raise ValueError("Edit source field does not exist")
        if "pointer" in source:
            documents = [d for p, _, d in _documents(fields[0]["value"])
                         if p == source.get("document_pointer", "")]
            if len(documents) != 1:
                raise ValueError("Edit source document does not exist or is opaque")
            _pointer(documents[0], source["pointer"])


def audit_edit_proposal(graph, *, removed_node_ids=(), removed_edge_ids=(), removed_sources=()):
    """Check deletion/projection closure without editing or compressing model input.

    Sources identify actual payload fields/subtrees, not index entries. Original
    G5 edge IDs are `g5-edge:<position>`. Removing a source requires removing all
    annotations of the modified field and incident edges. Rebinding/folding is
    deliberately not automatic. `ok` means support closure only, not task safety.
    """
    audit = audit_structured_graph(graph)
    if not audit["ok"]:
        return {"ok": False, "errors": audit["errors"], "task_preservation_certified": False}
    removed_nodes, removed_edges = set(removed_node_ids), set(removed_edge_ids)
    layer = graph["structured_layer"]
    all_nodes = {n["id"] for n in graph["evidence_view"]["nodes"] + layer["nodes"]}
    edges = [("g5-edge:" + str(i), e) for i, e in enumerate(graph["evidence_view"]["edges"])]
    edges += [(e["id"], e) for e in layer["edges"]]
    all_edges = {i for i, _ in edges}
    errors = []
    if removed_nodes - all_nodes or removed_edges - all_edges:
        errors.append("Edit references unknown node/edge IDs")
    try:
        _validate_removed_sources(graph, removed_sources)
    except (KeyError, ValueError, IndexError, TypeError) as exc:
        errors.append("Invalid evidence deletion target: " + str(exc))
        return {"ok": False, "errors": errors, "task_preservation_certified": False}
    required_nodes = set(removed_nodes)
    # Embedded links are graph references too. In particular, a result cannot
    # survive deletion of its producing call, and occurrences cannot retain a
    # missing call. Propagate until source/episode/result dependencies stabilize.
    changed = True
    while changed:
        before = set(required_nodes)
        for node in graph["evidence_view"]["nodes"]:
            if node.get("episode") in required_nodes or node.get("result_of") in required_nodes:
                required_nodes.add(node["id"])
        for node in layer["nodes"]:
            source = node.get("source", node.get("representative"))
            if node.get("call") in required_nodes or _source_removed(source, required_nodes, removed_sources):
                required_nodes.add(node["id"])
        changed = before != required_nodes
    required_edges = {identity for identity, edge in edges
                      if edge["from"] in required_nodes or edge["to"] in required_nodes
                      or any(_source_removed(s, required_nodes, removed_sources) for s in edge.get("supports", []))}
    if required_nodes - removed_nodes:
        errors.append("Retained annotations refer to removed evidence")
    if required_edges - removed_edges:
        errors.append("Retained edges refer to removed nodes or source evidence")
    return {"ok": not errors, "errors": errors,
            "required_removed_node_ids": sorted(required_nodes),
            "required_removed_edge_ids": sorted(required_edges),
            "task_preservation_certified": False,
            "scope": "annotation support closure; G5 episode/order repair and behavioral preservation remain separate"}
