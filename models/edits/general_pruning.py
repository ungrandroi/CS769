"""State/evidence edits with a measured exact-sharing control.

No task identifiers, future requests, evaluator, or hidden environment state.
One relation edit per checkpoint. Eligibility is not a task-safety certificate.
"""
from copy import deepcopy
from functools import partial
import json
import posixpath
import re
from cs769.models.edits import relation_pruning as rp, booking_receipt as br, witness_pruning as wp
from cs769.models.edits.record_edits import _digest, render as full_render

VERSION = "g9-general-pruning-v1"
DOORS = {"driver", "passenger", "rear_left", "rear_right"}
READS = {"pwd", "ls", "find", "cat", "head", "tail", "wc", "grep", "diff"}
VEHICLE_READS = {"displayCarStatus", "check_tire_pressure"}
OLD_QUERY = re.compile(r"\b(originally|formerly|old|prior|previous|earlier|before|history|historical|compare|comparison|difference|trend|average)\b|之前|原来|旧|历史|对比|比较", re.I)

def historical(current):
    return bool(OLD_QUERY.search(json.dumps(current, ensure_ascii=False)))

def state_candidates(graph):
    _, calls = rp.records(rp.evidence(graph))
    actions = []
    for i, old in enumerate(calls):
        if not rp.ok(old["result"]) or not isinstance(old["args"], dict):
            continue
        value = old["value"]
        for j in range(i + 1, len(calls)):
            new = calls[j]
            between = calls[i + 1:j]
            if (not rp.ok(new["result"]) or not isinstance(new["args"], dict)
                    or old["result"]["ordinal"] >= new["call"]["ordinal"]
                    or old["call"]["call_group"] == new["call"]["call_group"]):
                continue
            prop, relation, information = None, None, None
            keys = []
            if old["tool"] == "find" and new["tool"] == "mv":
                # A direct child and a local mv source share the *unchanged*
                # visible cwd frame. No invented absolute initial directory.
                if any(c["tool"] not in READS for c in between):
                    continue
                matches = value.get("matches") if isinstance(value, dict) else None
                src, dst = new["args"].get("source"), new["args"].get("destination")
                if not (set(value or {}) == {"matches"} and isinstance(matches, list)
                        and len(matches) == 1 and isinstance(matches[0], str)
                        and isinstance(src, str) and isinstance(dst, str)
                        and src not in ("", ".", "..") and dst not in ("", ".", "..")
                        and "/" not in src and "/" not in dst
                        and matches[0] in (src, "./" + src)
                        and old["args"].get("name") == src
                        and isinstance(new["value"], dict) and set(new["value"]) == {"result"}):
                    continue
                receipt = re.fullmatch(r"'([^']+)' moved to '([^']+)'", new["value"]["result"])
                if not receipt or receipt[1] != src or receipt[2] not in (dst, dst + "/" + src):
                    continue
                if posixpath.normpath(receipt[2]) == src:
                    continue
                prop, relation = "location", "same_frame_move_receipt"
                information = "redundant_location_evidence"
            elif old["tool"] == "displayCarStatus" and isinstance(value, dict):
                if any(c["tool"] not in VEHICLE_READS for c in between):
                    continue
                nv, na = new["value"], new["args"]
                if old["args"] == {"option": "doors"} and new["tool"] == "lockDoors":
                    doors = value.get("doorStatus")
                    affected = na.get("door")
                    if not (isinstance(doors, dict) and doors and set(doors) <= DOORS
                            and all(v in ("locked", "unlocked") for v in doors.values())
                            and type(na.get("unlock")) is bool and isinstance(affected, list)
                            and all(isinstance(d, str) for d in affected)
                            and set(affected) <= DOORS and set(affected) >= set(doors)
                            and isinstance(nv, dict)
                            and nv.get("lockStatus") == ("unlocked" if na["unlock"] else "locked")
                            and type(nv.get("remainingUnlockedDoors")) is int
                            and 0 <= nv["remainingUnlockedDoors"] <= 4):
                        continue
                    if not any(v != nv["lockStatus"] for v in doors.values()):
                        continue
                    if set(affected) == DOORS and nv["remainingUnlockedDoors"] != (4 if na["unlock"] else 0):
                        continue
                    prop, relation = "doorStatus", "successful_property_overwrite"
                    information = "old_property_observation_removed"
                elif old["args"] == {"option": "fuel"} and new["tool"] == "fillFuelTank":
                    ov = value.get("fuelLevel")
                    amount = na.get("fuelAmount")
                    if not (type(ov) in (int, float) and type(amount) in (int, float)
                            and amount > 0 and isinstance(nv, dict)
                            and type(nv.get("fuelLevel")) in (int, float)
                            and abs(nv["fuelLevel"] - ov - amount) < 1e-8
                            and 0 <= ov < nv["fuelLevel"] <= 50):
                        continue
                    prop, relation = "fuelLevel", "successful_property_overwrite"
                    # Old level can be recovered from the retained increment
                    # and new level: do not call this genuinely lost information.
                    information = "arithmetically_recoverable_observation"
                else:
                    continue
                keys = [prop]
            if relation is None:
                continue
            # Do not erase values explicitly used by another visible later call.
            removed_value = value[prop] if keys else value
            if any(rp.eq(removed_value, x) for c in calls[j+1:] for x in rp.children(c["args"])):
                continue
            whole = not keys or set(value) <= set(keys)
            actions.append({
                "kind": "state", "relation": relation, "property": prop,
                "source_graph_sha256": _digest(graph),
                "source_call": old["call"]["id"], "source_result": old["result"]["id"],
                "witness_call": new["call"]["id"], "witness_result": new["result"]["id"],
                "source_ordinal": old["call"]["ordinal"],
                "remove_keys": [] if whole else keys,
                "delete_events": [old["call"]["id"], old["result"]["id"]] if whole else [],
                "information_class": information,
            })
    return actions

def apply_state(graph, action, count):
    a = deepcopy(action)
    a["kind"] = "consumed" if a["remove_keys"] else "state"
    out, audit = rp.apply(graph, a, count)
    mapping = audit["old_to_new_event_ids"]
    notice = "Pruned history: earlier state observation omitted; retained successful update: " + mapping[a["witness_result"]] + "."
    out["relation_pruning"] = {"version": VERSION, "notice": notice}
    audit.update(action=action, information_class=action["information_class"])
    return out, audit, notice

def render_with_notice(graph, *, renderer, notice):
    return renderer(graph) + ("\n" + notice if notice else "")

def prune(graph, count, current, *, min_saved_tokens=50):
    if type(min_saved_tokens) is not int or min_saved_tokens < 1:
        raise ValueError("Invalid minimum saving")
    before = _digest(graph)
    baseline, sharing, base_render = wp._share(graph, count, current)
    base_tokens = count(base_render(baseline))
    choices, considered = [], []
    if not historical(current):
        for action in state_candidates(graph):
            choices.append(("state", action, apply_state))
        for action in rp.candidates(graph, current, "consumed")[0]:
            choices.append(("evidence", action, rp.apply))
        for action in br.candidates(graph, current)[0]:
            choices.append(("booking", action, br.apply))
    eligible = []
    for kind, action, apply in choices:
        try:
            result = apply(graph, action, count)
        except ValueError as exc:
            if str(exc).startswith("No positive"):
                continue
            raise
        changed, audit = result[:2]
        notice = result[2] if len(result) == 3 else changed["relation_pruning"]["notice"]
        changed = deepcopy(changed)
        changed.pop("relation_pruning", None)
        shared, share_audit, renderer = wp._share(changed, count, current)
        rendered = partial(render_with_notice, renderer=renderer, notice=notice)
        saved = base_tokens - count(rendered(shared))
        considered.append({"relation": action["relation"], "saved_vs_shared": saved})
        if saved >= min_saved_tokens:
            eligible.append((saved, action["source_result"], kind, shared, audit, share_audit, rendered))
    if _digest(graph) != before:
        raise AssertionError("Source graph mutated")
    if not eligible:
        return baseline, {
            "version": VERSION, "pruned": False, "sharing": sharing,
            "reason": "historical_request" if historical(current) else "no_qualified_positive_edit",
            "considered": considered, "saved_tokens": count(full_render(graph))-base_tokens,
            "source_graph_sha256": before, "memory_tokens_after": base_tokens,
        }, base_render
    saved, _, kind, out, audit, share_audit, renderer = sorted(eligible, key=lambda x: (-x[0], x[1], x[2]))[0]
    return out, {
        "version": VERSION, "pruned": True, "kind": kind,
        "edit": audit, "sharing": share_audit, "shared_baseline": sharing,
        "information_class": audit.get("information_class", "upstream_detail_removed"),
        "considered": considered, "source_graph_sha256": before,
        "memory_tokens_after": count(renderer(out)),
        "saved_tokens": count(full_render(graph))-count(renderer(out)),
        "additional_saved_vs_shared": saved, "task_preservation_certified": False,
    }, renderer
