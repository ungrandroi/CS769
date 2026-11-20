"""G8: unique, lossless payload ownership in a small concrete-syntax graph.

Tool fields contain root references, never a second full payload. JSON text keeps
its original character fragments; typed sources keep the G5 deterministic display
and recover the existing JSON types/values, not pre-decoder HTTP bytes. No archive,
model, simulator, evaluator or future input is accessed. Projection is a plan only.
"""
from collections import Counter
from copy import deepcopy
import hashlib
import json
import re

from core.graph_memory_evidence import render_evidence_segments
from core.graph_memory_observed import (
    BASE_KEYS, audit_observed_graph, render_observed_graph, strip_observed_graph,
)

VERSION = "lossless-payload-field-graph-v1"
LAYOUTS = ("g7-compatible", "inline-members-v1")
MAX_DEPTH = 64
MAX_NODES_PER_FIELD = 50000
_SPACE = re.compile(r"[ \t\r\n]+")
_STRING = re.compile(r'"(?:[^"\\\x00-\x1f]|\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4}))*"')
_NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")
G7_KEYS = BASE_KEYS | {"observed_layer"}


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _display(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _digest(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _text_digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def _type_tree(value):
    if isinstance(value, dict):
        return ["dict", [[k, _type_tree(v)] for k, v in value.items()]]
    if isinstance(value, list):
        return ["list", [_type_tree(v) for v in value]]
    return [type(value).__name__, value]


class _ParseFailure(ValueError):
    pass


class _CST:
    """Only JSON grammar + layout retention. No repair, semantic coercion or I/O."""

    def __init__(self, text, prefix):
        self.text, self.prefix, self.pos, self.nodes = text, prefix, 0, []

    def node(self, kind, start, **attrs):
        if len(self.nodes) >= MAX_NODES_PER_FIELD:
            raise _ParseFailure("node-limit")
        node = {"id": self.prefix + str(len(self.nodes)), "kind": kind,
                "span": [start, start], **attrs}
        self.nodes.append(node)
        return node

    def fragment(self, end, lexical_kind):
        start = self.pos
        node = self.node("fragment", start, lexical_kind=lexical_kind,
                         text=self.text[start:end])
        self.pos = end
        node["span"][1] = end
        return node["id"]

    def space(self, parts):
        match = _SPACE.match(self.text, self.pos)
        if match:
            parts.append(self.fragment(match.end(), "whitespace"))

    def punctuation(self, expected):
        if self.text[self.pos:self.pos + 1] != expected:
            raise _ParseFailure("invalid-json")
        return self.fragment(self.pos + 1, "punctuation")

    def scalar(self, key=False):
        node = self.node("scalar", self.pos, parts=[])
        match = _STRING.match(self.text, self.pos)
        if match:
            kind, end = "string", match.end()
        elif not key and (match := _NUMBER.match(self.text, self.pos)):
            kind, end = "number", match.end()
        else:
            literal = next((x for x in ("true", "false", "null") if not key and self.text.startswith(x, self.pos)), None)
            if literal is None:
                raise _ParseFailure("invalid-json")
            kind, end = ("null" if literal == "null" else "boolean"), self.pos + len(literal)
        node["scalar_type"] = kind
        node["parts"].append(self.fragment(end, kind))
        node["span"][1] = self.pos
        return node["id"]

    def value(self, depth):
        if depth > MAX_DEPTH:
            raise _ParseFailure("depth-limit")
        char = self.text[self.pos:self.pos + 1]
        if char not in ("{", "["):
            return self.scalar()
        is_object = char == "{"
        close = "}" if is_object else "]"
        container = self.node("object" if is_object else "array", self.pos,
                              parts=[], members=[], commas=[])
        parts = container["parts"]
        parts.append(self.punctuation(char))
        self.space(parts)
        if self.text[self.pos:self.pos + 1] != close:
            while True:
                member = self.node("member" if is_object else "element", self.pos, parts=[])
                if is_object:
                    member["key"] = self.scalar(key=True)
                    member["parts"].append(member["key"])
                    self.space(member["parts"])
                    member["parts"].append(self.punctuation(":"))
                    self.space(member["parts"])
                member["value"] = self.value(depth + 1)
                member["parts"].append(member["value"])
                member["span"][1] = self.pos
                parts.append(member["id"])
                container["members"].append(member["id"])
                self.space(parts)
                if self.text[self.pos:self.pos + 1] != ",":
                    break
                comma = self.punctuation(",")
                parts.append(comma)
                container["commas"].append(comma)
                self.space(parts)
        parts.append(self.punctuation(close))
        container["span"][1] = self.pos
        return container["id"]

    def parse(self):
        root = self.node("document", 0, parts=[])
        self.space(root["parts"])
        root["value"] = self.value(0)
        root["parts"].append(root["value"])
        self.space(root["parts"])
        if self.pos != len(self.text):
            raise _ParseFailure("invalid-json")
        root["span"][1] = self.pos
        return root["id"], self.nodes, None


def _parse(text, prefix):
    try:
        return _CST(text, prefix).parse()
    except (_ParseFailure, RecursionError) as exc:
        reason = str(exc) if isinstance(exc, _ParseFailure) else "recursion-limit"
        root = {"id": prefix + "0", "kind": "opaque", "span": [0, len(text)], "text": text}
        return root["id"], [root], reason


def _expand(identity, by_id, active=None):
    active = set() if active is None else active
    if identity in active:
        raise ValueError("Cyclic payload ownership")
    node = by_id[identity]
    if node["kind"] in ("fragment", "opaque"):
        return node["text"]
    active.add(identity)
    text = "".join(_expand(child, by_id, active) for child in node["parts"])
    active.remove(identity)
    return text


def _is_tool_field(event, field):
    return event["category"] == "tool_result" or (
        event["category"] == "tool_call" and field["field"].endswith("arguments"))


def _pointer_tokens(pointer):
    if pointer == "":
        return []
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise ValueError("Invalid source pointer")
    tokens = []
    for raw in pointer.split("/")[1:]:
        if "~" in raw.replace("~0", "").replace("~1", ""):
            raise ValueError("Invalid source pointer escape")
        tokens.append(raw.replace("~1", "/").replace("~0", "~"))
    return tokens


def _locate(root, pointer, by_id):
    node = by_id[root]
    if node["kind"] == "document":
        node = by_id[node["value"]]
    if node["kind"] == "opaque":
        return node["id"], "opaque_field_root"
    for token in _pointer_tokens(pointer):
        if node["kind"] == "object":
            matching = [by_id[mid] for mid in node["members"]
                        if json.loads(_expand(by_id[mid]["key"], by_id)) == token]
            if len(matching) != 1:
                raise ValueError("Ambiguous or missing semantic payload member")
            node = by_id[matching[0]["value"]]
        elif node["kind"] == "array":
            if not token.isdigit() or str(int(token)) != token:
                raise ValueError("Noncanonical semantic array index")
            node = by_id[by_id[node["members"][int(token)]]["value"]]
        else:
            raise ValueError("Semantic pointer enters a scalar")
    return node["id"], "exact_value_node"


def _bindings(observed_layer, fields, by_id):
    by_field = {(f["event_id"], f["field"]): f for f in fields}
    sources = {}
    for owner in observed_layer["nodes"] + observed_layer["edges"]:
        for slot, source in ([('source', owner['source'])] if "source" in owner else []) + [
                ("supports/" + str(i), s) for i, s in enumerate(owner.get("supports", []))]:
            key = _json(source)
            if key not in sources:
                field = by_field[(source["event_id"], source["field"])]
                if source["document_pointer"]:
                    target, kind = _locate(field["root"], source["document_pointer"], by_id)
                    # G7 may parse JSON in an explicit provider text-block string.
                    # Its containing string remains one scalar in this CST. Do
                    # not pretend that decoded subfields own independent lexemes.
                    if kind == "exact_value_node":
                        kind = "encoded_document_scalar"
                else:
                    target, kind = _locate(field["root"], source["pointer"], by_id)
                sources[key] = {"source": deepcopy(source), "target": target,
                                "granularity": kind, "semantic_owners": []}
            sources[key]["semantic_owners"].append({"id": owner["id"], "slot": slot})
    return list(sources.values())


def build_payload_graph(g7_graph):
    audit = audit_observed_graph(g7_graph)
    if not audit["ok"]:
        raise ValueError("Expected valid G7 inference only: " + "; ".join(audit["errors"]))
    result = deepcopy(g7_graph)
    nodes, fields = [], []
    for event in result["evidence_view"]["nodes"]:
        for index, field in enumerate(event.get("fields", [])):
            if not _is_tool_field(event, field):
                continue
            value = field["value"]
            is_text = isinstance(value, str)
            text = value if is_text else _display(value)
            root, tree, reason = _parse(text, "g8:" + str(len(fields)) + ":")
            nodes.extend(tree)
            source_kind = "json-text" if is_text and reason is None else "opaque-text" if is_text else "typed-source"
            fields.append({"event_id": event["id"], "field": field["field"], "root": root,
                           "value_type": field["value_type"], "source_kind": source_kind,
                           "lexical_origin": "visible-field-characters" if is_text else "g5-deterministic-display",
                           "parse_fallback": reason, "text_length": len(text),
                           "text_sha256": _text_digest(text), "typed_value_sha256": _digest(_type_tree(value))})
            event["fields"][index] = {"field": field["field"], "value_type": field["value_type"], "payload_root": root}
    by_id = {node["id"]: node for node in nodes}
    result["payload_layer"] = {
        "version": VERSION, "parser_depth_limit": MAX_DEPTH, "parser_node_limit": MAX_NODES_PER_FIELD,
        "g7_input_sha256": _digest(g7_graph), "g7_render_sha256": _text_digest(render_observed_graph(g7_graph)),
        "fields": fields, "nodes": nodes, "source_bindings": _bindings(g7_graph["observed_layer"], fields, by_id),
    }
    return result


def _restore(graph):
    layer = graph["payload_layer"]
    by_id = {n["id"]: n for n in layer["nodes"]}
    fields = {(f["event_id"], f["field"]): f for f in layer["fields"]}
    restored = {key: deepcopy(graph[key]) for key in G7_KEYS}
    for event in restored["evidence_view"]["nodes"]:
        for index, field in enumerate(event.get("fields", [])):
            if not _is_tool_field(event, field):
                continue
            meta = fields[(event["id"], field["field"])]
            if set(field) != {"field", "value_type", "payload_root"} or field["payload_root"] != meta["root"]:
                raise ValueError("Tool field must reference its unique payload root")
            text = _expand(meta["root"], by_id)
            value = json.loads(text) if meta["source_kind"] == "typed-source" else text
            event["fields"][index] = {"field": field["field"], "value": value, "value_type": field["value_type"]}
    return restored


def _storage_check(graph):
    """Ownership edges are parts, not semantic references or metadata aliases."""
    layer = graph["payload_layer"]
    nodes, fields = layer["nodes"], layer["fields"]
    by_id = {n["id"]: n for n in nodes}
    if len(by_id) != len(nodes):
        raise ValueError("Duplicate payload node ID")
    if len({(f["event_id"], f["field"]) for f in fields}) != len(fields):
        raise ValueError("Duplicate payload field descriptor")
    seen, owner_count = set(), Counter()
    for field in fields:
        leaves = []

        def visit(identity, depth=0):
            if depth > MAX_DEPTH * 3 + 10:
                raise ValueError("Payload ownership traversal too deep")
            owner_count[identity] += 1
            if identity in seen:
                raise ValueError("Duplicate content owner or cyclic payload path")
            seen.add(identity)
            node = by_id[identity]
            if node["kind"] in ("fragment", "opaque"):
                if set(node) - {"id", "kind", "span", "text", "lexical_kind"}:
                    raise ValueError("Unexpected content-owner attribute")
                leaves.append(node)
            else:
                if "text" in node or "lexeme" in node:
                    raise ValueError("Container duplicates owned content")
                for child in node["parts"]:
                    visit(child, depth + 1)

        visit(field["root"])
        position = 0
        for leaf in leaves:
            if leaf["span"] != [position, position + len(leaf["text"])]:
                raise ValueError("Payload fragments overlap, omit, or reorder characters")
            position += len(leaf["text"])
        text = "".join(n["text"] for n in leaves)
        if position != field["text_length"] or _text_digest(text) != field["text_sha256"]:
            raise ValueError("Payload fragment coverage/hash differs")
    if seen != set(by_id):
        raise ValueError("Orphan payload node outside unique ownership roots")
    known = {n["id"] for n in graph["evidence_view"]["nodes"] + graph["observed_layer"]["nodes"]}
    if set(by_id) & known:
        raise ValueError("Payload node namespace collision")
    for binding in layer["source_bindings"]:
        if binding["target"] not in by_id:
            raise ValueError("Dangling semantic payload binding")
    return sum(max(0, n - 1) for n in owner_count.values())


def audit_payload_graph(graph):
    errors, preserved, duplicate_count = [], False, 0
    layer = graph.get("payload_layer", {}) if isinstance(graph, dict) else {}
    nodes, fields, bindings = [], [], []
    try:
        if not isinstance(graph, dict) or set(graph) != G7_KEYS | {"payload_layer"} or not isinstance(layer, dict):
            raise ValueError("Expected only payload-owned G7 inference")
        nodes, fields, bindings = layer["nodes"], layer["fields"], layer["source_bindings"]
        if any(not isinstance(items, list) or any(not isinstance(n, dict) for n in items) for items in (nodes, fields, bindings)):
            nodes, fields, bindings = [], [], []
            raise ValueError("Malformed payload layer")
        duplicate_count = _storage_check(graph)
        restored = _restore(graph)
        old_audit = audit_observed_graph(restored)
        if not old_audit["ok"]:
            errors += old_audit["errors"]
        preserved = (_digest(restored) == layer["g7_input_sha256"] and
                     _text_digest(render_observed_graph(restored)) == layer["g7_render_sha256"])
        if not preserved:
            errors.append("Restored G7 payload/render proof differs")
        by_field = {(f["event_id"], f["field"]): f for f in fields}
        for event in restored["evidence_view"]["nodes"]:
            for field in event.get("fields", []):
                if _is_tool_field(event, field):
                    meta = by_field[(event["id"], field["field"])]
                    if type(field["value"]).__name__ != meta["value_type"] or _digest(_type_tree(field["value"])) != meta["typed_value_sha256"]:
                        errors.append("Restored source type/value differs")
        if _json(build_payload_graph(restored)) != _json(graph):
            errors.append("Payload structure/bindings differ from deterministic construction")
    except (ValueError, KeyError, TypeError, IndexError, AttributeError, RecursionError, OverflowError) as exc:
        if "Duplicate content owner" in str(exc):
            duplicate_count = max(1, duplicate_count)
        errors.append(str(exc))
    return {"ok": not errors, "errors": errors, "payload_preserved": preserved,
            "field_count": len(fields), "payload_node_count": len(nodes),
            "fragment_count": sum(n.get("kind") in ("fragment", "opaque") for n in nodes),
            "binding_count": len(bindings), "address_count": sum(n.get("kind") == "member" for n in nodes),
            "lexically_parsed_field_count": sum(f.get("parse_fallback") is None for f in fields),
            "opaque_field_count": sum(f.get("parse_fallback") is not None for f in fields),
            "typed_source_field_count": sum(f.get("source_kind") == "typed-source" for f in fields),
            "duplicate_content_owner_count": duplicate_count}


def restore_observed_graph(graph):
    audit = audit_payload_graph(graph)
    if not audit["ok"]:
        raise ValueError("Invalid payload graph: " + "; ".join(audit["errors"]))
    return _restore(graph)


def _marker_delimiters(text):
    index = 0
    while True:
        left, right = "⟦" + "|" * index, "|" * index + "⟧"
        if left not in text and right not in text:
            return left, right
        index += 1


def render_payload_segments(graph, *, layout="inline-members-v1"):
    if layout not in LAYOUTS:
        raise ValueError("Unknown payload rendering layout")
    audit = audit_payload_graph(graph)
    if not audit["ok"]:
        raise ValueError("Invalid payload graph: " + "; ".join(audit["errors"]))
    restored = _restore(graph)
    original = render_observed_graph(restored)
    if layout == "g7-compatible":
        return [{"kind": "g7-compatible", "text": original}]
    base_segments = render_evidence_segments(strip_observed_graph(restored))
    base_text = "".join(s["text"] for s in base_segments)
    if not original.startswith(base_text):
        raise ValueError("G7 renderer no longer has the frozen G5 prefix")
    layer = graph["payload_layer"]
    by_id = {n["id"]: n for n in layer["nodes"]}
    by_field = {(f["event_id"], f["field"]): f for f in layer["fields"]}
    aliases = {n["id"]: "f" + str(i) for i, n in enumerate(n for n in layer["nodes"] if n["kind"] == "member")}
    left, right = _marker_delimiters(original)
    result = []

    def emit(identity):
        node = by_id[identity]
        if node["kind"] == "member":
            result.append({"kind": "payload_member_marker", "text": left + aliases[identity] + right,
                           "node_id": identity})
        if node["kind"] in ("fragment", "opaque"):
            result.append({"kind": "payload_fragment", "text": node["text"], "node_id": identity})
        else:
            for child in node["parts"]:
                emit(child)

    for segment in base_segments:
        key = (segment.get("node_id"), segment.get("field"))
        if segment["kind"] == "evidence" and key in by_field:
            emit(by_field[key]["root"])
        else:
            result.append(deepcopy(segment))
    if len(original) > len(base_text):
        result.append({"kind": "g7_appendix", "text": original[len(base_text):]})
    # Segment provenance, not textual removal of a marker-shaped substring.
    if "".join(s["text"] for s in result if s["kind"] != "payload_member_marker") != original:
        raise ValueError("Address rendering changed original G7 content")
    return result


def render_payload_graph(graph, *, layout="inline-members-v1"):
    return "".join(s["text"] for s in render_payload_segments(graph, layout=layout))


def plan_member_projection(graph, *, removed_member_ids):
    """OFFLINE member/element deletion plan, including real owned fragments.

    Removes an adjacent comma when necessary, retains untouched whitespace and
    siblings, and computes semantic support closure through payload bindings.
    Does not mutate the graph or emit a compressed inference carrier.
    """
    audit = audit_payload_graph(graph)
    if not audit["ok"]:
        raise ValueError("Cannot plan an invalid payload graph")
    if not isinstance(removed_member_ids, (list, tuple)) or not removed_member_ids:
        raise ValueError("Name at least one payload member or element")
    if len(set(removed_member_ids)) != len(removed_member_ids):
        raise ValueError("Duplicate member projection target")
    layer = graph["payload_layer"]
    by_id = {n["id"]: n for n in layer["nodes"]}
    parents = {child: n["id"] for n in layer["nodes"] for child in n.get("parts", [])}
    removed = set()

    def descendants(identity):
        found = {identity}
        for child in by_id[identity].get("parts", []):
            found |= descendants(child)
        return found

    for identity in removed_member_ids:
        if by_id[identity]["kind"] not in ("member", "element"):
            raise ValueError("Projection target is not a member/element")
        removed |= descendants(identity)
    repairs = []
    for container in layer["nodes"]:
        if container["kind"] not in ("object", "array") or container["id"] in removed:
            continue
        members = container["members"]
        if not any(member in removed for member in members):
            continue
        retained = [i for i, member in enumerate(members) if member not in removed]
        keep_commas = {container["commas"][i - 1] for i in retained[1:]}
        for comma in container["commas"]:
            if comma not in keep_commas:
                removed.add(comma)
                repairs.append({"operation": "remove_separator", "node_id": comma, "container": container["id"]})

    affected = set(removed)
    for identity in list(removed):
        while identity in parents:
            identity = parents[identity]
            affected.add(identity)
    by_field = {(f["event_id"], f["field"]): f for f in layer["fields"]}
    affected_sources = {
        _json(b["source"]) for b in layer["source_bindings"]
        if b["target"] in affected or (
            b["granularity"] != "exact_value_node" and
            by_field[(b["source"]["event_id"], b["source"]["field"])]["root"] in affected)
    }
    observed = graph["observed_layer"]
    invalid = {n["id"] for n in observed["nodes"] if n["category"] != "property_channel" and
               any(_json(s) in affected_sources for s in [n["source"]] + n["supports"])}
    surviving_channels = {n["channel"] for n in observed["nodes"] if n["category"] != "property_channel" and n["id"] not in invalid}
    invalid |= {n["id"] for n in observed["nodes"] if n["category"] == "property_channel" and n["id"] not in surviving_channels}
    invalid_edges = {e["id"] for e in observed["edges"] if e["from"] in invalid or any(t in invalid for t in e["to"])
                     or any(_json(s) in affected_sources for s in e["supports"])}
    surviving_bindings = []
    for binding in layer["source_bindings"]:
        if _json(binding["source"]) in affected_sources:
            continue
        owners = [owner for owner in binding["semantic_owners"]
                  if owner["id"] not in invalid and owner["id"] not in invalid_edges]
        if owners:
            surviving_bindings.append({**deepcopy(binding), "semantic_owners": deepcopy(owners)})
    changed_fields = []

    def projected(identity):
        if identity in removed:
            return ""
        node = by_id[identity]
        return node["text"] if node["kind"] in ("fragment", "opaque") else "".join(projected(c) for c in node["parts"])

    for field in layer["fields"]:
        if field["root"] not in affected:
            continue
        text = projected(field["root"])
        _, _, failure = _parse(text, "check:")
        if failure:
            raise ValueError("Member projection failed syntactic validation")
        changed_fields.append({"event_id": field["event_id"], "field": field["field"],
                               "original_root": field["root"], "projected_text_sha256": _text_digest(text),
                               "original_chars": field["text_length"], "projected_chars": len(text)})
    return {"version": "payload-member-projection-plan-v1", "base_graph_sha256": _digest(graph),
            "removed_member_ids": list(removed_member_ids),
            "payload_operations": [{"operation": "remove_member_subtree", "node_id": n} for n in removed_member_ids] + repairs,
            "removed_payload_node_ids": sorted(removed),
            "removed_content_owner_ids": sorted(n for n in removed if by_id[n]["kind"] in ("fragment", "opaque")),
            "retained_payload_node_ids": [n["id"] for n in layer["nodes"] if n["id"] not in removed],
            "changed_fields": changed_fields,
            "required_removed_semantic_node_ids": sorted(invalid),
            "required_removed_semantic_edge_ids": sorted(invalid_edges),
            "supported_semantic_node_ids": [n["id"] for n in observed["nodes"] if n["id"] not in invalid],
            "supported_semantic_edge_ids": [e["id"] for e in observed["edges"] if e["id"] not in invalid_edges],
            "supported_bindings": surviving_bindings,
            "requires_source_label_refresh": True, "requires_projected_graph_audit": True,
            "order_edges_reconnected": False, "applied": False, "task_preservation_certified": False}


def audit_member_projection_plan(graph, plan):
    try:
        expected = plan_member_projection(graph, removed_member_ids=plan["removed_member_ids"])
        if _json(plan) != _json(expected):
            raise ValueError("Projection plan differs from payload/semantic closure")
        return {"ok": True, "errors": [], "applied": False, "task_preservation_certified": False}
    except (ValueError, KeyError, TypeError, IndexError, AttributeError, RecursionError) as exc:
        return {"ok": False, "errors": [str(exc)], "applied": False, "task_preservation_certified": False}
