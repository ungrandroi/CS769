"""G7: public-contract field observations over complete, unchanged G5 evidence.

No simulator, archive, future input, evaluator or model is consulted. Observation
channels describe returned reports, never current external state. Projection is
an OFFLINE plan for actual payload locations, not an inference-time compression.
"""
from collections import Counter, defaultdict
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
import math

from core.graph_memory_evidence import (
    EPISODIC_VIEW_VERSION, audit_evidence_graph, render_evidence_graph,
)

VERSION = "observed-field-graph-v1"
VARIANTS = ("observed-fields-v1", "observed-nodes-only-v1")
BASE_KEYS = frozenset(("delivery", "evidence_view", "evidence_audit"))
PUBLIC_DOC_SHA256 = {
    "vehicle_control": "0c8a66292844874ef7b168f343bc394d8615d2d9e1f4387999a9ee23011eac78",
    "math_api": "83fa31708c89442bdcf12ac4dfbe3be8663ec9183a1b1524a9fda98164bc7e0b",
}


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _digest(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _strict_json(text):
    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    def invalid(value):
        raise ValueError("Non-finite JSON number: " + value)

    return json.loads(text, object_pairs_hook=object_pairs,
                      parse_float=Decimal, parse_constant=invalid)


def _pointer(value, pointer):
    if pointer == "":
        return value
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise ValueError("Invalid JSON Pointer")
    for token in pointer.split("/")[1:]:
        if "~" in token.replace("~0", "").replace("~1", ""):
            raise ValueError("Invalid JSON Pointer escape")
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(value, list):
            if not token.isdigit() or str(int(token)) != token:
                raise ValueError("Invalid array index")
            value = value[int(token)]
        elif isinstance(value, dict):
            value = value[token]
        else:
            raise ValueError("JSON Pointer enters a scalar")
    return value


def _documents(value):
    if isinstance(value, str):
        try:
            return [("", "json_text", _strict_json(value))]
        except (ValueError, TypeError, RecursionError):
            return []
    if isinstance(value, list) and value and all(
            isinstance(b, dict) and b.get("type") == "text"
            and isinstance(b.get("text"), str) for b in value):
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


def _leaf_pointers(value, pointer=""):
    if isinstance(value, dict):
        for key, item in value.items():
            escaped = key.replace("~", "~0").replace("/", "~1")
            yield from _leaf_pointers(item, pointer + "/" + escaped)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _leaf_pointers(item, pointer + "/" + str(index))
    else:
        yield pointer


def _typed(value):
    """JSON-serializable type-exact fingerprint, including Decimal spelling."""
    if isinstance(value, dict):
        return ["dict", [[k, _typed(v)] for k, v in value.items()]]
    if isinstance(value, list):
        return ["list", [_typed(v) for v in value]]
    return [type(value).__name__, str(value) if isinstance(value, Decimal) else value]


def _numeric(value):
    return type(value) in (int, float, Decimal) and (
        value.is_finite() if isinstance(value, Decimal) else
        math.isfinite(value) if isinstance(value, float) else True)


def _accept(value, kind):
    return ((kind == "number" and _numeric(value)) or
            (kind == "integer" and type(value) is int) or
            (kind == "string" and type(value) is str) or
            (kind == "boolean" and type(value) is bool) or
            (kind == "numbers" and isinstance(value, list) and all(_numeric(v) for v in value)) or
            (kind == "number_or_error" and (_numeric(value) or type(value) is str)))


def _show(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, list):
        return "[" + ",".join(_show(v) for v in value) + "]"
    return _json(value)


# Reviewed, static location/meaning contracts from the two public docs above.
# tuple: tool, role, pointer, property, unit, type, request-kind, selector-option.
_VEHICLE_RULES = []


def _vehicle(tool, role, pointer, prop, unit="none", kind="string", request="", option=""):
    _VEHICLE_RULES.append((tool, role, pointer, prop, unit, kind, request, option))


_vehicle("adjustClimateControl", "argument", "/temperature", "climate.setpoint", "$temperature_unit", "number", "target")
_vehicle("adjustClimateControl", "argument", "/fanSpeed", "climate.fan_speed", "0..100 setting", "integer", "target")
_vehicle("adjustClimateControl", "argument", "/mode", "climate.mode", request="target")
_vehicle("adjustClimateControl", "result", "/currentTemperature", "climate.setpoint", "degC", "number")
_vehicle("adjustClimateControl", "result", "/climateMode", "climate.mode")
_vehicle("adjustClimateControl", "result", "/humidityLevel", "climate.humidity", "percent", "number")
for pointer, prop, unit, kind, option in (
    ("currentACTemperature", "climate.setpoint", "degC", "number", "climate"),
    ("fanSpeed", "climate.fan_speed", "0..100 setting", "integer", "climate"),
    ("climateMode", "climate.mode", "none", "string", "climate"),
    ("humidityLevel", "climate.humidity", "percent", "number", "climate"),
    ("fuelLevel", "fuel.level", "gallon", "number", "fuel"),
    ("batteryVoltage", "battery.voltage", "volt", "number", "battery"),
    ("engineState", "engine.state", "none", "string", "engine"),
):
    _vehicle("displayCarStatus", "result", "/status/" + pointer, prop, unit, kind, option=option)
for door in ("driver", "passenger", "rear_left", "rear_right"):
    _vehicle("displayCarStatus", "result", "/status/doorStatus/" + door,
             "door." + door + ".status", option="doors")
_vehicle("fillFuelTank", "argument", "/fuelAmount", "fuel.level", "gallon", "number", "delta")
_vehicle("fillFuelTank", "result", "/fuelLevel", "fuel.level", "gallon", "number")
_vehicle("startEngine", "argument", "/ignitionMode", "engine.state", request="control")
_vehicle("startEngine", "result", "/engineState", "engine.state")
_vehicle("startEngine", "result", "/fuelLevel", "fuel.level", "gallon", "number")
_vehicle("startEngine", "result", "/batteryVoltage", "battery.voltage", "volt", "number")
_vehicle("get_current_speed", "result", "/currentSpeed", "vehicle.speed", "km/h", "number")
# Public request unit literally says m/h. Do not silently repair it to mph.
_vehicle("setCruiseControl", "argument", "/speed", "vehicle.speed", "m/h (literal)", "number", "target")
_vehicle("setCruiseControl", "result", "/currentSpeed", "vehicle.speed", "km/h", "number")
for tool in ("get_outside_temperature_from_google", "get_outside_temperature_from_weather_com"):
    _vehicle(tool, "result", "/outsideTemperature", "outside.temperature:" + tool, "degC", "number")
_VEHICLE_RULES = tuple(_VEHICLE_RULES)

# Each declared parameter is one port; list operands retain their array boundary.
_MATH = {
    "absolute_value": (("number", "number"),),
    "add": (("a", "number"), ("b", "number")),
    "divide": (("a", "number"), ("b", "number")),
    "imperial_si_conversion": (("value", "number"), ("unit_in", "string"), ("unit_out", "string")),
    "logarithm": (("value", "number"), ("base", "number"), ("precision", "integer")),
    "max_value": (("numbers", "numbers"),),
    "mean": (("numbers", "numbers"),),
    "min_value": (("numbers", "numbers"),),
    "multiply": (("a", "number"), ("b", "number")),
    "percentage": (("part", "number"), ("whole", "number")),
    "power": (("base", "number"), ("exponent", "number")),
    "round_number": (("number", "number"), ("decimal_places", "integer")),
    "si_unit_conversion": (("value", "number"), ("unit_in", "string"), ("unit_out", "string")),
    "square_root": (("number", "number"), ("precision", "integer")),
    "standard_deviation": (("numbers", "numbers"),),
    "subtract": (("a", "number"), ("b", "number")),
    "sum_values": (("numbers", "numbers"),),
}
_CONTROL_NAMES = frozenset(("unit_in", "unit_out", "precision", "decimal_places"))
RULESET_SHA256 = _digest([_VEHICLE_RULES, _MATH, PUBLIC_DOC_SHA256])


def strip_observed_graph(graph):
    return {key: deepcopy(graph[key]) for key in BASE_KEYS}


def _require_base(graph):
    if not isinstance(graph, dict) or set(graph) != BASE_KEYS:
        raise ValueError("Expected G5 inference only; no archives or other graph layers")
    if graph["evidence_view"].get("version") != EPISODIC_VIEW_VERSION:
        raise ValueError("Observed fields require G5 episodic evidence")
    audit_evidence_graph(graph)


def _source(event, field, document_pointer, encoding, pointer):
    return {"event_id": event["id"], "field": field["field"],
            "document_pointer": document_pointer, "encoding": encoding,
            "pointer": pointer, "field_sha256": _digest(field["value"])}


def resolve_source(graph, source):
    events = [n for n in graph["evidence_view"]["nodes"] if n["id"] == source["event_id"]]
    if len(events) != 1:
        raise ValueError("Missing or duplicate source event")
    fields = [f for f in events[0].get("fields", []) if f["field"] == source["field"]]
    if len(fields) != 1:
        raise ValueError("Missing or duplicate source field")
    value = fields[0]["value"]
    if _digest(value) != source["field_sha256"]:
        raise ValueError("Source field changed")
    document = _pointer(value, source["document_pointer"])
    if source["encoding"] == "json_text":
        document = _strict_json(document)
    elif source["encoding"] != "native_json":
        raise ValueError("Unknown source encoding")
    return _pointer(document, source["pointer"])


def _make_layer(base, variant):
    view = base["evidence_view"]
    events = {n["id"]: n for n in view["nodes"]}
    calls, group_start = {}, {}
    stats = Counter()
    for event in view["nodes"]:
        if event["category"] != "tool_call":
            continue
        name = next(f["value"] for f in event["fields"] if f["field"].endswith("name"))
        documents = []
        for field in event["fields"]:
            if field["field"].endswith("arguments"):
                for dp, enc, doc in _documents(field["value"]):
                    if isinstance(doc, dict):
                        documents.append((field, dp, enc, doc))
        # Ambiguous multi-document arguments do not supply selector/unit context.
        calls[event["id"]] = (event, name, documents[0] if len(documents) == 1 else None)
        group = event["call_group"]
        group_start[group] = min(group_start.get(group, event["ordinal"]), event["ordinal"])
    nodes, edges, channels = [], [], {}
    values, by_call = {}, defaultdict(list)

    def channel(scope, prop, unit):
        key = (scope, prop, unit)
        if key not in channels:
            item = {"id": "g7:p:" + _digest(key), "category": "property_channel",
                    "scope": scope, "property": prop, "unit": unit}
            channels[key] = item
            nodes.append(item)
        return channels[key]["id"]

    def add(event, call, tool, role, source, value, prop, unit, request_kind, rule, supports):
        scope = "computation:" + call["id"] if tool in _MATH else "vehicle@visible_history"
        pid = channel(scope, prop, unit)
        item = {"id": "g7:f:" + _digest([source, rule]),
                "category": "request_port" if role == "argument" else "observation",
                "call": call["id"], "tool": tool, "source": source,
                "supports": supports, "channel": pid, "scope": scope,
                "property": prop, "unit": unit, "port_kind": request_kind,
                "ordinal": event["ordinal"], "rule_id": rule,
                "value_type": type(value).__name__, "value_sha256": _digest(_typed(value))}
        if "native_is_error" in event:
            item["native_is_error"] = event["native_is_error"]
        nodes.append(item)
        values[item["id"]] = value
        by_call[call["id"]].append(item)

    registered_tools = {r[0] for r in _VEHICLE_RULES} | set(_MATH)
    for event_id in view["recorded_order"]:
        event = events[event_id]
        if event["category"] not in ("tool_call", "tool_result"):
            continue
        role = "argument" if event["category"] == "tool_call" else "result"
        call, tool, arg_document = calls[event_id if role == "argument" else event["result_of"]]
        if tool not in registered_tools:
            stats["unregistered_tool_events"] += 1
            continue
        args = arg_document[3] if arg_document else {}

        def arg_support(name):
            if arg_document and name in args:
                field, dp, enc, _ = arg_document
                return [_source(call, field, dp, enc, "/" + name)]
            return []

        for field in event["fields"]:
            if role == "argument" and not field["field"].endswith("arguments"):
                continue
            documents = _documents(field["value"])
            stats["candidate_fields"] += 1
            stats["opaque_fields"] += not bool(documents)
            for dp, enc, doc in documents:
                if not isinstance(doc, dict):
                    stats["non_object_documents"] += 1
                    continue
                stats["parsed_documents"] += 1
                qualifiers = []
                if role == "result":
                    for key in ("error", "errors", "success", "status"):
                        if key in doc and (key != "status" or not isinstance(doc[key], (dict, list))):
                            qualifiers.append(_source(event, field, dp, enc, "/" + key))
                if tool in _MATH:
                    entries = [("/" + name, name, typ) for name, typ in _MATH[tool]] if role == "argument" else [
                        ("/result", "result", "number_or_error" if tool == "square_root" else "number")]
                    for pointer, name, typ in entries:
                        if name not in doc:
                            if role == "result":
                                stats["missing_math_result_fields"] += 1
                            continue
                        value = doc[name]
                        if not _accept(value, typ):
                            stats["type_conflicts"] += 1
                            continue
                        support = list(qualifiers)
                        unit = "unknown"
                        if tool in ("imperial_si_conversion", "si_unit_conversion"):
                            unit_arg = "unit_out" if role == "result" else "unit_in"
                            if name in ("result", "value") and type(args.get(unit_arg)) is str:
                                unit = "literal:" + args[unit_arg]
                                support += arg_support(unit_arg)
                        kind = "control" if name in _CONTROL_NAMES else "operand" if role == "argument" else "reported_result"
                        add(event, call, tool, role, _source(event, field, dp, enc, pointer), value,
                            "result" if role == "result" else "input." + name,
                            unit, kind, f"math:{tool}:{role}:{pointer}", support)
                    continue
                for rule in _VEHICLE_RULES:
                    name, expected_role, pointer, prop, unit, typ, request_kind, option = rule
                    if tool != name or role != expected_role:
                        continue
                    if option and args.get("option") != option:
                        continue
                    try:
                        value = _pointer(doc, pointer)
                    except (ValueError, KeyError, IndexError):
                        if role == "result":
                            # Includes optional schema slots; absence is not an
                            # error or evidence that the property no longer exists.
                            stats["absent_registered_result_paths"] += 1
                        continue
                    if not _accept(value, typ):
                        stats["type_conflicts"] += 1
                        continue
                    support = list(qualifiers)
                    if option:
                        support += arg_support("option")
                    if unit == "$temperature_unit":
                        explicit_unit = args.get("unit")
                        unit = {"celsius": "degC", "fahrenheit": "degF"}.get(explicit_unit, "unknown") if type(explicit_unit) is str else "unknown"
                        support += arg_support("unit")
                    add(event, call, tool, role, _source(event, field, dp, enc, pointer), value,
                        prop, unit, request_kind or "reported_value",
                        f"vehicle:{tool}:{role}:{pointer}", support)

    # Coverage accounts for all parsed result leaves, including unregistered
    # tools. This is observation coverage, not a schema-validity verdict.
    observed_sources = [n["source"] for n in nodes if n["category"] == "observation"]
    for event in view["nodes"]:
        if event["category"] != "tool_result":
            continue
        for field in event["fields"]:
            for dp, _, doc in _documents(field["value"]):
                for pointer in _leaf_pointers(doc):
                    stats["result_scalar_leaf_count"] += 1
                    mapped = any(s["event_id"] == event["id"] and s["field"] == field["field"] and
                                 s["document_pointer"] == dp and (pointer == s["pointer"] or pointer.startswith(s["pointer"] + "/"))
                                 for s in observed_sources)
                    stats["unmapped_result_scalar_leaf_count"] += not mapped

    def supports_of(members):
        result = []
        for member in members:
            for source in [member["source"]] + member["supports"]:
                if source not in result:
                    result.append(deepcopy(source))
        return result

    def edge(start, relation, targets, members):
        item = {"from": start, "relation": relation, "to": list(targets),
                "supports": supports_of(members)}
        item["id"] = "g7:x:" + _digest(item)
        edges.append(item)

    if variant == "observed-fields-v1":
        fields = [n for n in nodes if n["category"] != "property_channel"]
        for node in fields:
            relation = "observed_as" if node["category"] == "observation" else "requested_for"
            # Math operand channels are call-specific ports, not state requests.
            if node["tool"] in _MATH and node["category"] == "request_port":
                continue
            edge(node["id"], relation, [node["channel"]], [node])
        for call_id, members in by_call.items():
            requests = [n for n in members if n["category"] == "request_port"]
            observations = [n for n in members if n["category"] == "observation"]
            _, tool, arg_document = calls[call_id]
            if tool in _MATH:
                # A complete declared-input set requires one unambiguous parsed
                # request, no undeclared fields and no rejected provided values.
                args = arg_document[3] if arg_document else None
                expected = {k for k, _ in _MATH[tool]}
                actual = {n["source"]["pointer"][1:] for n in requests}
                if args is not None and set(args) <= expected and actual == set(args):
                    for obs in observations:
                        edge(obs["id"], "declared_inputs", [n["id"] for n in requests], [obs] + requests)
            else:
                for req in requests:
                    for obs in observations:
                        if req["property"] == obs["property"]:
                            edge(req["id"], "reported_with", [obs["id"]], [req, obs])
        previous = {}
        for obs in (n for n in fields if n["category"] == "observation" and n["tool"] not in _MATH):
            prior = previous.get(obs["channel"])
            call = calls[obs["call"]][0]
            if prior and prior["ordinal"] < group_start[call["call_group"]]:
                edge(prior["id"], "next_visible_observation", [obs["id"]], [prior, obs])
            previous[obs["channel"]] = obs
        # Exact NUMBER equality only among Math results/operands, never vehicle
        # state flow. Equal values do not establish copy origin or dependency.
        math_obs = [n for n in fields if n["tool"] in _MATH and n["category"] == "observation" and _numeric(values[n["id"]])]
        for req in (n for n in fields if n["tool"] in _MATH and n["category"] == "request_port" and n["port_kind"] == "operand" and _numeric(values[n["id"]])):
            start = group_start[calls[req["call"]][0]["call_group"]]
            for obs in math_obs:
                if obs["ordinal"] >= start:
                    continue
                if obs["unit"] != "unknown" and req["unit"] != "unknown" and obs["unit"] != req["unit"]:
                    continue
                if Decimal(str(values[obs["id"]])) == Decimal(str(values[req["id"]])):
                    edge(obs["id"], "equal_number_prior", [req["id"]], [obs, req])
    return {"version": VERSION, "variant": variant, "ruleset_sha256": RULESET_SHA256,
            "public_doc_sha256": PUBLIC_DOC_SHA256.copy(), "base_inference_sha256": _digest(base),
            "nodes": nodes, "edges": edges, "extraction_stats": dict(sorted(stats.items()))}


def build_observed_graph(g5_graph, variant="observed-fields-v1"):
    """Node-list ablation retains channel/call/source attributes, drops edges."""
    if variant not in VARIANTS:
        raise ValueError("Unknown observed graph variant")
    _require_base(g5_graph)
    result = deepcopy(g5_graph)
    result["observed_layer"] = _make_layer(g5_graph, variant)
    return result


def audit_observed_graph(graph):
    errors, preserved = [], False
    layer = graph.get("observed_layer", {}) if isinstance(graph, dict) else {}
    nodes, edges = [], []
    try:
        if not isinstance(layer, dict) or set(graph) != BASE_KEYS | {"observed_layer"}:
            raise ValueError("Expected only G5 inference plus observed_layer")
        nodes, edges = layer["nodes"], layer["edges"]
        if not isinstance(nodes, list) or not isinstance(edges, list) or any(not isinstance(x, dict) for x in nodes + edges):
            nodes, edges = [], []
            raise ValueError("Malformed observed nodes/edges")
        base = strip_observed_graph(graph)
        _require_base(base)
        preserved = _digest(base) == layer["base_inference_sha256"]
        if not preserved:
            errors.append("Base payload preservation proof differs")
        if layer["variant"] not in VARIANTS:
            raise ValueError("Unknown observed variant")
        base_ids = [n["id"] for n in base["evidence_view"]["nodes"]]
        ids = [n["id"] for n in nodes]
        if len(set(base_ids + ids)) != len(base_ids + ids):
            errors.append("Duplicate graph node ID")
        if len({e["id"] for e in edges}) != len(edges):
            errors.append("Duplicate observed edge ID")
        for node in nodes:
            if node["category"] == "property_channel":
                continue
            value = resolve_source(graph, node["source"])
            if type(value).__name__ != node["value_type"] or _digest(_typed(value)) != node["value_sha256"]:
                errors.append("Node source value/type mismatch")
            if node["call"] not in base_ids or node["channel"] not in ids:
                errors.append("Dangling embedded node reference")
            for source in node["supports"]:
                resolve_source(graph, source)
        for edge in edges:
            if edge["from"] not in ids or any(target not in ids for target in edge["to"]):
                errors.append("Dangling observed edge")
            for source in edge["supports"]:
                resolve_source(graph, source)
        if _json(layer) != _json(_make_layer(base, layer["variant"])):
            errors.append("Observed layer differs from deterministic derivation")
    except (ValueError, KeyError, TypeError, IndexError, AttributeError, RecursionError) as exc:
        errors.append(str(exc))
    return {"ok": not errors, "errors": errors, "variant": layer.get("variant") if isinstance(layer, dict) else None,
            "payload_preserved": preserved, "node_count": len(nodes), "edge_count": len(edges),
            "new_edge_count": len(edges),
            "observation_count": sum(n.get("category") == "observation" for n in nodes),
            "request_port_count": sum(n.get("category") == "request_port" for n in nodes),
            "channel_count": sum(n.get("category") == "property_channel" for n in nodes),
            "per_relation_counts": dict(Counter(e.get("relation") for e in edges))}


def _source_label(source):
    dp = "@" + source["document_pointer"] if source["document_pointer"] else ""
    return source["event_id"] + "." + source["field"] + dp + "#" + source["pointer"]


def render_observed_graph(graph):
    audit = audit_observed_graph(graph)
    if not audit["ok"]:
        raise ValueError("Invalid observed graph: " + "; ".join(audit["errors"]))
    layer = graph["observed_layer"]
    if not layer["nodes"]:
        return render_evidence_graph(strip_observed_graph(graph))
    aliases, counts = {}, Counter()
    prefixes = {"property_channel": "p", "request_port": "q", "observation": "o"}
    for node in layer["nodes"]:
        prefix = prefixes[node["category"]]
        aliases[node["id"]] = prefix + str(counts[prefix])
        counts[prefix] += 1
    lines = ["<field_graph>", "Channels group reported properties within this history. Observations are returned reports, not current state."]
    for node in layer["nodes"]:
        alias = aliases[node["id"]]
        if node["category"] == "property_channel":
            lines.append(f'{alias} {node["scope"]}.{node["property"]} unit={_json(node["unit"])}')
        else:
            suffix = ""
            if node["supports"]:
                suffix += " context=" + ",".join(_source_label(s) for s in node["supports"])
            if "native_is_error" in node:
                suffix += " native_is_error=" + _json(node["native_is_error"])
            lines.append(f'{alias} {node["category"]}.{node["port_kind"]} {_show(resolve_source(graph, node["source"]))} '
                         f'channel={aliases[node["channel"]]} @{_source_label(node["source"])}{suffix}')
    lines.append("Relations: observed_as=reported property; requested_for=requested property; reported_with=same-call property pair; next=adjacent visible reports available before the later call; inputs=all provided declared parameters; equal=prior equal number only, not provenance or causation.")
    short = {"next_visible_observation": "next", "declared_inputs": "inputs", "equal_number_prior": "equal"}
    for edge in layer["edges"]:
        lines.append(f'{aliases[edge["from"]]} {short.get(edge["relation"], edge["relation"])} '
                     + "[" + ",".join(aliases[x] for x in edge["to"]) + "]")
    lines.append("</field_graph>")
    return render_evidence_graph(strip_observed_graph(graph)) + "\n" + "\n".join(lines) + "\n"


def _overlap(a, b):
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


def _same_field(a, b):
    return a["event_id"] == b["event_id"] and a["field"] == b["field"]


def plan_field_projection(graph, *, removed_sources):
    """Plan removal of real payload JSON subtrees; NEVER change model input.

    Semantic survivors are not an executable projected G5 graph. Surviving
    annotations of edited raw fields need new hashes/pointers (arrays may shift),
    and chronology is not silently reconnected. No task-equivalence certificate.
    """
    audit = audit_observed_graph(graph)
    if not audit["ok"]:
        raise ValueError("Cannot project an invalid observed graph")
    if not isinstance(removed_sources, (list, tuple)) or not removed_sources:
        raise ValueError("Specify at least one actual payload source")
    events = {n["id"]: n for n in graph["evidence_view"]["nodes"]}
    removals, operations = [], []
    for supplied in removed_sources:
        if not isinstance(supplied, dict) or set(supplied) - {"event_id", "field", "pointer", "document_pointer", "encoding", "field_sha256"}:
            raise ValueError("Unknown payload projection selector")
        event = events[supplied["event_id"]]
        fields = [f for f in event.get("fields", []) if f["field"] == supplied["field"]]
        if len(fields) != 1 or "pointer" not in supplied:
            raise ValueError("Projection must name an existing field and JSON Pointer")
        field = fields[0]
        dp = supplied.get("document_pointer", "")
        documents = [(enc, doc) for loc, enc, doc in _documents(field["value"]) if loc == dp]
        if len(documents) != 1:
            raise ValueError("Projection document is opaque or ambiguous")
        enc, doc = documents[0]
        value = _pointer(doc, supplied["pointer"])
        source = _source(event, field, dp, enc, supplied["pointer"])
        if any(supplied.get(k, source[k]) != source[k] for k in ("encoding", "field_sha256")):
            raise ValueError("Stale projection source")
        if source in removals:
            raise ValueError("Duplicate projection target")
        removals.append(source)
        operations.append({"operation": "remove_payload_subtree", "source": source,
                           "removed_value_sha256": _digest(_typed(value))})

    def affected(source):
        return any(_same_field(source, r) and source["document_pointer"] == r["document_pointer"]
                   and _overlap(source["pointer"], r["pointer"]) for r in removals)

    def edited_field(source):
        return any(_same_field(source, r) for r in removals)

    layer = graph["observed_layer"]
    fields = [n for n in layer["nodes"] if n["category"] != "property_channel"]
    invalid = {n["id"] for n in fields if any(affected(s) for s in [n["source"]] + n["supports"])}
    surviving_channels = {n["channel"] for n in fields if n["id"] not in invalid}
    invalid |= {n["id"] for n in layer["nodes"] if n["category"] == "property_channel" and n["id"] not in surviving_channels}
    invalid_edges = {e["id"] for e in layer["edges"] if e["from"] in invalid or any(t in invalid for t in e["to"])
                     or any(affected(s) for s in e["supports"])}
    rebind_nodes = [n["id"] for n in fields if n["id"] not in invalid and
                    any(edited_field(s) for s in [n["source"]] + n["supports"])]
    rebind_edges = [e["id"] for e in layer["edges"] if e["id"] not in invalid_edges and any(edited_field(s) for s in e["supports"])]
    return {"version": "observed-field-projection-plan-v1", "base_graph_sha256": _digest(graph),
            "payload_operations": operations, "removed_sources": removals,
            "required_removed_node_ids": sorted(invalid), "required_removed_edge_ids": sorted(invalid_edges),
            "supported_surviving_node_ids": [n["id"] for n in layer["nodes"] if n["id"] not in invalid],
            "supported_surviving_edge_ids": [e["id"] for e in layer["edges"] if e["id"] not in invalid_edges],
            "rebind_node_ids": rebind_nodes, "rebind_edge_ids": rebind_edges,
            "base_events_retained": True, "applied": False,
            "requires_source_rebuild": True, "order_edges_reconnected": False,
            "task_preservation_certified": False}


def audit_projection_plan(graph, plan):
    try:
        expected = plan_field_projection(graph, removed_sources=plan["removed_sources"])
        if _json(plan) != _json(expected):
            raise ValueError("Projection plan differs from payload/support closure")
        return {"ok": True, "errors": [], "applied": False, "task_preservation_certified": False}
    except (ValueError, KeyError, TypeError, IndexError, AttributeError) as exc:
        return {"ok": False, "errors": [str(exc)], "applied": False, "task_preservation_certified": False}
