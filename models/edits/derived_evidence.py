"""Prune source detail after a retained, checked observation relationship.

Selectors inspect only current graph evidence and the current user request.
They never read tasks, future turns, expected answers, or evaluator state.
"""
from copy import deepcopy
import json
import re

from cs769.models.edits import record_edits
from cs769.models.edits.relation_pruning import base_graph, records, fields, load, ok, eq, children, identities
from cs769.models.graphs.graph_memory_records import audit_record_graph

VERSION = "g9-derived-evidence-v1"
KINDS = {"auto", "file_count", "distance_feasibility"}
FILE_READS = {"pwd", "ls", "find", "cat", "wc", "sort", "grep", "tail", "diff", "du"}
FILE_QUERY = re.compile(
    r"\b(full|entire|verbatim|original|previous|prior|earlier|before|compare|comparison|"
    r"diff|quote|quotation|ordering|alphabetical)\b|"
    r"\b(read|show|display|print|summarize|extract)\b.{0,60}\b(file|content|text|lines)\b",
    re.I,
)
ROUTE_QUERY = re.compile(r"\b(route|routing|waypoints?|intermediate|intermediary|cities|stops|via|directions)\b", re.I)


def text_leaves(value):
    """Unpack JSON strings too, so nested call arguments cannot hide a duplicate."""
    if isinstance(value, str):
        decoded = load(value)
        if decoded is not None and decoded != value:
            yield from text_leaves(decoded)
        else:
            yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from text_leaves(child)
    elif isinstance(value, list):
        for child in value:
            yield from text_leaves(child)


def evidence(graph):
    return record_edits.evidence(base_graph(graph))


def render(graph):
    text = record_edits.render(base_graph(graph))
    notice = graph.get("relation_pruning", {}).get("notice")
    return text + ("\n" + notice if notice else "")


def candidates(graph, current, kind="auto"):
    if kind not in KINDS:
        raise ValueError("Unknown derived evidence kind")
    nodes, calls = records(evidence(graph))
    query = json.dumps(current, ensure_ascii=False)
    actions, rejected = [], {}
    source_hash = record_edits._digest(graph)

    def reject(reason):
        rejected[reason] = rejected.get(reason, 0) + 1

    def action(old, witness, rule, **extra):
        return dict(
            kind=rule, source_graph_sha256=source_hash,
            source_call=old["call"]["id"], source_result=old["result"]["id"],
            witness_call=witness["call"]["id"], witness_result=witness["result"]["id"],
            **extra,
        )

    if kind in {"auto", "file_count"} and not FILE_QUERY.search(query):
        for old in calls:
            if old["tool"] not in {"cat", "sort"} or not ok(old["result"]):
                continue
            key = "file_content" if old["tool"] == "cat" else "sorted_content"
            body = old["value"].get(key) if isinstance(old["value"], dict) else None
            filename = old["args"].get("file_name") if isinstance(old["args"], dict) else None
            if not isinstance(body, str) or not body or not isinstance(filename, str) or not filename:
                continue
            for witness in calls:
                if witness["tool"] != "wc" or not ok(witness["result"]):
                    continue
                if not isinstance(witness["args"], dict) or witness["args"].get("file_name") != filename:
                    continue
                # Results may be from parallel read-only calls. This is a same-version
                # observation relation, not an assertion that cat caused wc.
                if witness["result"]["ordinal"] <= old["call"]["ordinal"]:
                    continue
                start = min(old["call"]["ordinal"], witness["call"]["ordinal"])
                end = max(old["result"]["ordinal"], witness["result"]["ordinal"])
                overlap = [
                    c for c in calls
                    if c["call"]["ordinal"] <= end
                    and (c["result"] is None or c["result"]["ordinal"] >= start)
                ]
                if any(c["tool"] not in FILE_READS for c in overlap):
                    reject("mutation_or_unknown_call_between_reads")
                    continue
                mode = witness["args"].get("mode", "l")
                if mode not in {"l", "w", "c"} or (old["tool"] == "sort" and mode == "c"):
                    reject("unsupported_count_mode")
                    continue
                result = witness["value"]
                expected = {"l": len(body.splitlines()), "w": len(body.split()), "c": len(body)}[mode]
                unit = {"l": "lines", "w": "words", "c": "characters"}[mode]
                if not isinstance(result, dict) or type(result.get("count")) is not int or result["count"] != expected or result.get("type") != unit:
                    reject("count_not_verified")
                    continue
                removed = {old["call"]["id"], old["result"]["id"]}
                other_text = [s for n in nodes if n["id"] not in removed for s in text_leaves([f["value"] for f in n.get("fields", [])])]
                if any(body in s for s in other_text):
                    reject("whole_body_retained_elsewhere")
                    continue
                actions.append(action(old, witness, "file_count", delete_events=sorted(removed),
                                      file_name=filename, read_tool=old["tool"],
                                      count_mode=mode, retained_count=expected,
                                      same_file_derived_count_verified=True,
                                      observational_relation_not_causal_order=True))
    elif kind in {"auto", "file_count"}:
        reject("current_request_needs_file_detail")

    if kind in {"auto", "distance_feasibility"} and not ROUTE_QUERY.search(query):
        projections = record_edits.candidates(base_graph(graph))[1]
        producers = [
            c for c in calls if c["tool"] == "estimate_distance" and ok(c["result"])
            and isinstance(c["value"], dict) and type(c["value"].get("distance")) in (int, float)
        ]
        for old in producers:
            cities = old["value"].get("intermediaryCities")
            if not isinstance(cities, list) or not cities:
                continue
            city_strings = list(text_leaves(cities))
            if identities(cities):
                reject("identifier_in_removed_field")
                continue
            remaining_text = [s for n in nodes if n["id"] != old["result"]["id"] for s in text_leaves([f["value"] for f in n.get("fields", [])])]
            if not city_strings or all(any(s in other for other in remaining_text) for s in city_strings):
                reject("whole_field_retained_elsewhere")
                continue
            later = [c for c in calls if c["call"]["ordinal"] > old["result"]["ordinal"]]
            if any(eq(value, operand) for value in children(cities) for c in later for operand in children(c["args"])):
                reject("removed_value_referenced_by_later_argument")
                continue
            if any(len(s) >= 3 and s.casefold() in query.casefold() for s in city_strings):
                reject("removed_value_mentioned_by_current_request")
                continue
            witnesses = [
                c for c in later if c["tool"] == "estimate_drive_feasibility_by_mileage"
                and ok(c["result"]) and isinstance(c["args"], dict)
                and eq(c["args"].get("distance"), old["value"]["distance"])
                and isinstance(c["value"], dict) and type(c["value"].get("canDrive")) is bool
            ]
            for witness in witnesses:
                competing = [p for p in producers
                             if p["result"]["ordinal"] < witness["call"]["ordinal"]
                             and eq(p["value"]["distance"], witness["args"]["distance"])]
                if len(competing) != 1:
                    reject("ambiguous_distance_producer")
                    continue
                matches = [p for p in projections if p["event_id"] == old["result"]["id"] and p["key"] == "intermediaryCities"]
                if len(matches) != 1:
                    reject("missing_projection")
                    continue
                actions.append(action(old, witness, "distance_feasibility", projection=matches[0],
                                      retained_distance=old["value"]["distance"],
                                      retained_canDrive=witness["value"]["canDrive"],
                                      unit_conversion_certified=False))
    elif kind in {"auto", "distance_feasibility"}:
        reject("current_request_needs_route_detail")
    return actions, rejected


def apply(graph, action, count):
    if action["source_graph_sha256"] != record_edits._digest(graph):
        raise ValueError("Stale derived evidence action")
    source = evidence(graph)
    if action["kind"] == "file_count":
        removed = set(action["delete_events"])
        original = {n["id"]: deepcopy(n) for n in source["evidence_view"]["nodes"] if n["category"] != "episode"}
        out = deepcopy(source)
        out["evidence_view"]["nodes"] = [n for n in out["evidence_view"]["nodes"] if n["id"] not in removed]
        edited, mapping = record_edits._refresh(out)
        retained = {n["id"]: n for n in record_edits.evidence(edited)["evidence_view"]["nodes"] if n["category"] != "episode"}
        if set(mapping) != set(original) - removed:
            raise AssertionError("Undeclared evidence removal")
        for old_id, new_id in mapping.items():
            wanted = deepcopy(original[old_id])
            wanted.update(id=new_id, ordinal=retained[new_id]["ordinal"])
            if "result_of" in wanted:
                wanted["result_of"] = mapping[wanted["result_of"]]
            if wanted != retained[new_id]:
                raise AssertionError("Retained evidence changed")
        notice = "Pruned evidence: a file-content observation was removed; retained count: " + mapping[action["witness_result"]] + "."
    elif action["kind"] == "distance_feasibility":
        edited, projection_audit = record_edits.apply(base_graph(graph), action["projection"], count)
        mapping = projection_audit["old_to_new_event_ids"]
        removed = set()
        notice = "Pruned evidence: " + mapping[action["source_result"]] + "/output is partial; retained distance was used in " + mapping[action["witness_call"]] + "."
    else:
        raise ValueError("Unknown derived evidence action")
    if not audit_record_graph(edited)["ok"]:
        raise AssertionError("Invalid edited graph")
    edited["relation_pruning"] = {"version": VERSION, "notice": notice}
    before, after = count(record_edits.render(base_graph(graph))), count(render(edited))
    if before <= after:
        raise ValueError("No positive derived evidence saving")
    if action["source_graph_sha256"] != record_edits._digest(graph):
        raise AssertionError("Original graph mutated")
    return edited, {
        "version": VERSION, "action": deepcopy(action), "old_to_new_event_ids": mapping,
        "removed_event_ids": sorted(removed), "memory_tokens_before": before,
        "memory_tokens_after": after, "saved_tokens": before - after,
        "source_graph_sha256": action["source_graph_sha256"],
        "edited_graph_sha256": record_edits._digest(edited),
        "retained_evidence_exact": True, "full_original_evidence_preserved": False,
        "task_preservation_certified": False, "causal_dependency_proven": False,
    }


def prune(graph, count, current, *, kind="auto", min_saved_tokens=50):
    if type(min_saved_tokens) is not int or min_saved_tokens < 1:
        raise ValueError("Invalid minimum saving")
    choices = []
    for action in candidates(graph, current, kind)[0]:
        try:
            edited, audit = apply(graph, action, count)
        except ValueError as error:
            if str(error).startswith("No positive"):
                continue
            raise
        if audit["saved_tokens"] >= min_saved_tokens:
            choices.append((edited, audit))
    if not choices:
        raise ValueError("No eligible derived evidence edit")
    return max(choices, key=lambda item: (item[1]["saved_tokens"], json.dumps(item[1]["action"], sort_keys=True)))
