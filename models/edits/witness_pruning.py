"""Observed successor evidence edits, composed with the existing exact sharing.

These contracts establish graph-edit eligibility, never task safety. Inputs are
only the current graph and current request; no task IDs, answers or evaluator.
"""
from copy import deepcopy
from functools import partial
import json
import posixpath
import re

from cs769.models.edits.record_edits import evidence, _refresh, _digest, render as full_render
from cs769.models.edits.relation_pruning import records, fields, ok, HISTORY_QUERY
from cs769.models.edits import field_pruning

VERSION = "g9-witness-pruning-v1"
READS = {"pwd", "ls", "find", "cat", "head", "tail", "wc", "grep", "diff"}
VEHICLE_BETWEEN = {
    "startEngine", "pressBrakePedal", "lockDoors", "displayCarStatus",
    "activateParkingBrake", "fillFuelTank", "check_tire_pressure",
}
RELATIONS = ("relocated_location", "resolved_error")
RESOLVED_CONTRACTS = ("start_engine", "created_file", "authenticated_send", "located_read")
DEFAULT_RESOLVED_CONTRACTS = ("start_engine",)


def _restore_check(source, edited, mapping, removed):
    old = {n["id"]: n for n in evidence(source)["evidence_view"]["nodes"]
           if n["category"] != "episode"}
    new = {n["id"]: n for n in evidence(edited)["evidence_view"]["nodes"]
           if n["category"] != "episode"}
    if set(mapping) != set(old) - set(removed):
        raise AssertionError("Undeclared event deletion")
    for prior, current in mapping.items():
        expected = deepcopy(old[prior])
        expected.update(id=current, ordinal=new[current]["ordinal"])
        if "result_of" in expected:
            expected["result_of"] = mapping[expected["result_of"]]
        if expected != new[current]:
            raise AssertionError("Retained evidence changed")


def relocation_candidates(graph):
    """Single visible find match -> serial successful mv of that same object.

    Only reviewed filesystem read/cd operations may intervene. Unknown writes,
    failed context changes and all identity changes invalidate pending matches.
    No hidden initial cwd is used. Other find result fields prevent deletion.
    """
    _, calls = records(evidence(graph))
    cwd = None
    observations = []
    actions = []

    def absolute(value):
        if not isinstance(value, str):
            return None
        if value.startswith("/"):
            return posixpath.normpath(value)
        return posixpath.normpath(posixpath.join(cwd, value)) if cwd is not None else None

    for call in calls:
        name, args, value = call["tool"], call["args"], call["value"]
        args = args if isinstance(args, dict) else {}
        success = ok(call["result"])
        if name == "pwd":
            path = value.get("current_working_directory") if isinstance(value, dict) else None
            if success and isinstance(path, str) and path.startswith("/"):
                cwd = posixpath.normpath(path)
            else:
                cwd = None
                observations = []
            continue
        if name == "cd":
            destination = absolute(args.get("folder")) if success else None
            if destination is None:
                observations = []
            cwd = destination
            continue
        if name == "find" and success:
            matches = value.get("matches") if isinstance(value, dict) else None
            if isinstance(value, dict) and set(value) == {"matches"} and isinstance(matches, list) and len(matches) == 1:
                path = absolute(matches[0])
                if path is not None:
                    observations.append((call, path))
            continue
        if name == "mkdir":
            # Reviewed BFCL contract: add one directory, or return an error
            # without relocating existing objects. Preserve this event itself.
            directory = args.get("dir_name")
            local = isinstance(directory, str) and directory not in ("", ".", "..") and "/" not in directory
            raw = fields(call["result"]).get("output") if call["result"] else None
            null_result = isinstance(raw, str) and raw.strip() == "null"
            error_result = isinstance(value, dict) and set(value) == {"error"} and isinstance(value["error"], str)
            if not (set(args) == {"dir_name"} and local and call["result"]
                    and not call["result"].get("native_is_error") and (null_result or error_result)):
                observations = []
            continue
        if name == "mv":
            if success and isinstance(value, dict) and set(value) == {"result"}:
                receipt = re.fullmatch(r"'([^']+)' moved to '([^']+)'", value["result"])
                source = absolute(args.get("source"))
                destination = absolute(args.get("destination"))
                if receipt and receipt[1] == args.get("source") and source and destination:
                    final = absolute(receipt[2])
                    possible = {destination, posixpath.join(destination, posixpath.basename(source))}
                    if final in possible and final != source:
                        for prior, path in observations:
                            if path != source or prior["result"]["ordinal"] >= call["call"]["ordinal"]:
                                continue
                            if prior["call"]["call_group"] == call["call"]["call_group"]:
                                continue
                            actions.append({
                                "relation": "relocated_location",
                                "source_call": prior["call"]["id"],
                                "source_result": prior["result"]["id"],
                                "witness_call": call["call"]["id"],
                                "witness_result": call["result"]["id"],
                                "object": source, "new_location": final,
                                "source_ordinal": prior["call"]["ordinal"],
                                "delete_events": [prior["call"]["id"], prior["result"]["id"]],
                            })
            observations = []
            continue
        if name not in READS:
            observations = []
    return actions


def _relocate(graph, action):
    source = evidence(graph)
    edited = deepcopy(source)
    removed = set(action["delete_events"])
    edited["evidence_view"]["nodes"] = [
        n for n in edited["evidence_view"]["nodes"] if n["id"] not in removed]
    out, mapping = _refresh(edited)
    _restore_check(graph, out, mapping, removed)
    notice = "\nPruned history: earlier state observation removed; updated-state evidence: " + mapping[action["witness_result"]] + "."
    return out, {
        "action": action, "removed_event_ids": sorted(removed),
        "old_to_new_event_ids": mapping, "retained_evidence_exact": True,
    }, notice


def _serial_repairs(old, new, between):
    """A prerequisite cannot be claimed from parallel/unreturned operations."""
    left = old["result"]["ordinal"]
    for call in between:
        result = call["result"]
        if result is None or call["call"]["ordinal"] <= left:
            return False
        if result["ordinal"] >= new["call"]["ordinal"]:
            return False
        left = result["ordinal"]
    return left < new["call"]["ordinal"]


def _created_file_contract(old, new, between):
    args = old["args"]
    name = args.get("file_name") if isinstance(args, dict) else None
    if (old["tool"] != "cat" or not isinstance(args, dict) or set(args) != {"file_name"} or
            not isinstance(name, str) or name in ("", ".", "..") or "/" in name):
        return False
    if old["value"] != {"error": f"cat: '{name}': No such file or directory"}:
        return False
    if not (ok(new["result"]) and isinstance(new["value"], dict) and
            set(new["value"]) == {"file_content"} and
            isinstance(new["value"]["file_content"], str)):
        return False
    creates = [c for c in between if c["tool"] == "touch"]
    if len(creates) != 1:
        return False
    create = creates[0]
    # Official touch returns None after creation; errors are JSON objects.
    if (create["args"] != {"file_name": name} or create["result"] is None or
            create["result"].get("native_is_error") or
            fields(create["result"]).get("output") not in ("null", "None")):
        return False
    # Relative object identity is preserved by unchanged cwd. Even a failed cd
    # or unknown operation is a barrier; never infer scope from filename alone.
    return all(c["tool"] in READS or c is create for c in between)


def _authenticated_send_contract(old, new, between):
    args = old["args"]
    if (old["tool"] != "send_message" or not isinstance(args, dict) or
            set(args) != {"receiver_id", "message"} or
            not isinstance(args["receiver_id"], str) or not args["receiver_id"] or
            not isinstance(args["message"], str)):
        return False
    # This reviewed error occurs before ID allocation or inbox mutation.
    if old["value"] != {"error": "No user is currently logged in."}:
        return False
    if not (ok(new["result"]) and isinstance(new["value"], dict) and
            new["value"].get("sent_status") is True and "message_id" in new["value"]):
        return False
    logins = [c for c in between if c["tool"] == "message_login"]
    if len(logins) != 1:
        return False
    login = logins[0]
    if not (isinstance(login["args"], dict) and set(login["args"]) == {"user_id"} and
            isinstance(login["args"]["user_id"], str) and login["args"]["user_id"] and
            ok(login["result"]) and isinstance(login["value"], dict) and
            login["value"].get("login_status") is True):
        return False
    # Only a single observed unauthenticated -> authenticated transition.
    # Logout, another sender, another send, or unknown calls invalidate it.
    reads = {"message_get_login_status", "get_user_id", "list_users"}
    return all(c["tool"] in reads or c is login for c in between)


def _located_read_contract(old, new, between, calls):
    """Retire a failed lookup; failed and successful paths remain distinct."""
    args = old["args"]
    name = args.get("file_name") if isinstance(args, dict) else None
    if (old["tool"] != "cat" or set(args or {}) != {"file_name"} or
            not isinstance(name, str) or name in ("", ".", "..") or "/" in name):
        return False
    if (old["value"] != {"error": f"cat: '{name}': No such file or directory"} or
            old["result"].get("native_is_error")):
        return False
    if not (ok(new["result"]) and isinstance(new["value"], dict) and
            set(new["value"]) == {"file_content"} and
            isinstance(new["value"]["file_content"], str)):
        return False
    # Latest matching lookup only; no older convenient match or hidden cwd.
    finds = [c for c in calls if c["tool"] == "find" and
             isinstance(c["args"], dict) and c["args"].get("name") == name and
             c["call"]["ordinal"] < old["call"]["ordinal"]]
    if not finds:
        return False
    found = finds[-1]
    if (found["args"] not in ({"name": name}, {"name": name, "path": "."}) or
            not ok(found["result"]) or not isinstance(found["value"], dict) or
            set(found["value"]) != {"matches"}):
        return False
    matches = found["value"]["matches"]
    if not (isinstance(matches, list) and len(matches) == 1 and isinstance(matches[0], str)):
        return False
    path = matches[0]
    if not path.startswith("./"):
        return False
    parts = path[2:].split("/")
    # Official BFCL cd supports one directory level at a time.
    if len(parts) != 2 or parts[1] != name or parts[0] in ("", ".", ".."):
        return False
    directory = parts[0]
    before = [c for c in calls if found["call"]["ordinal"] <
              c["call"]["ordinal"] < old["call"]["ordinal"]]
    if not _serial_repairs(found, new, before + [old] + between):
        return False
    # Preserve the symbolic find scope: no cd, writes or unknown calls.
    if any(c["tool"] not in READS or not ok(c["result"]) for c in before):
        return False
    changes = [c for c in between if c["tool"] == "cd"]
    if len(changes) != 1:
        return False
    change = changes[0]
    if (change["args"] != {"folder": directory} or not ok(change["result"]) or
            change["value"] != {"current_working_directory": directory}):
        return False
    if any(c is not change and (c["tool"] not in READS or not ok(c["result"])) for c in between):
        return False
    return {
        "find_call": found["call"]["id"], "find_result": found["result"]["id"],
        "directory_change_call": change["call"]["id"],
        "directory_change_result": change["result"]["id"],
        "failed_path_relative_to_find_scope": "./" + name,
        "successful_path_relative_to_find_scope": path,
        "same_object_asserted": False, "failed_path_absence_superseded": False,
    }


def _resolved(graph, count, current, contracts=DEFAULT_RESOLVED_CONTRACTS):
    """Reuse old edit, then require serial, same-scope reviewed witnesses.

    The initial no-partial-side-effect error contract is startEngine(START).
    STOP is intentionally unsupported: BFCL can mutate state before failing.
    Extending tool contracts requires another explicit review/freeze.
    """
    out, audit = field_pruning.resolved_errors(graph, count, current)
    _, calls = records(evidence(graph))
    byid = {c["call"]["id"]: c for c in calls}
    proof = audit["action"]["proof"]
    location_proofs = []
    if not proof:
        raise ValueError("No eligible resolved witness")
    for pair in proof:
        old = byid[pair["removed"][0]]
        new = byid[pair["later_success"]]
        if old["args"] != new["args"] or new["tool"] != old["tool"]:
            raise AssertionError("Resolved operation changed")
        if old["result"]["ordinal"] >= new["call"]["ordinal"]:
            raise ValueError("No eligible serial resolved witness")
        if old["call"]["call_group"] == new["call"]["call_group"]:
            raise ValueError("No eligible independent resolved witness")
        between = [c for c in calls if old["call"]["ordinal"] < c["call"]["ordinal"] < new["call"]["ordinal"]]
        if old["tool"] == "startEngine" and "start_engine" in contracts:
            if old["args"] != {"ignitionMode": "START"}:
                raise ValueError("No eligible reviewed failure contract")
            if not ok(new["result"]) or not isinstance(new["value"], dict) or new["value"].get("engineState") != "running":
                raise ValueError("No eligible successful START receipt")
            if any(c["tool"] not in VEHICLE_BETWEEN for c in between):
                raise ValueError("No eligible unchanged vehicle scope")
        elif not (_serial_repairs(old, new, between) and (
                "created_file" in contracts and _created_file_contract(old, new, between) or
                "authenticated_send" in contracts and _authenticated_send_contract(old, new, between) or
                "located_read" in contracts and _located_read_contract(old, new, between, calls))):
            raise ValueError("No eligible reviewed failure contract")
        if "located_read" in contracts:
            location = _located_read_contract(old, new, between, calls)
            if location:
                location_proofs.append(location)
    audit = deepcopy(audit)
    if location_proofs:
        audit["located_read_proofs"] = location_proofs
    audit["source_ordinal"] = min(byid[p["removed"][0]]["call"]["ordinal"] for p in proof)
    audit["reviewed_failure_contract"] = ("startEngine/START/no_error_side_effects"
        if tuple(contracts) == DEFAULT_RESOLVED_CONTRACTS else list(contracts))
    return out, audit, ""


def _share(graph, count, current):
    from cs769.models.editing import share_structure, Ineligible
    try:
        out, audit, renderer = share_structure(graph, count, current, {})
        return out, audit, renderer
    except Ineligible:
        return graph, {"operation": "identity", "saved_tokens": 0}, full_render


def _render(graph, *, renderer, notice):
    return renderer(graph) + notice


def prune(graph, count, current, *, relations=RELATIONS, min_saved_tokens=50,
          resolved_contracts=DEFAULT_RESOLVED_CONTRACTS):
    if (not isinstance(resolved_contracts, (list, tuple)) or not resolved_contracts or
            set(resolved_contracts) - set(RESOLVED_CONTRACTS)):
        raise ValueError("Unknown reviewed retry contract")
    if not isinstance(relations, (list, tuple)) or not relations or set(relations) - set(RELATIONS):
        raise ValueError("Unknown successor evidence relation")
    if type(min_saved_tokens) is not int or min_saved_tokens < 1:
        raise ValueError("Invalid minimum saving")
    query = json.dumps(current, ensure_ascii=False)
    if HISTORY_QUERY.search(query) or re.search(r"\b(originally|formerly|old|why)\b|\bused\s+to\b|之前|原来|旧|历史|对比|比较", query, re.I):
        raise ValueError("No eligible edit for historical-state request")
    before_hash = _digest(graph)
    baseline, baseline_audit, baseline_renderer = _share(graph, count, current)
    baseline_tokens = count(baseline_renderer(baseline))
    choices = []
    considered = []
    if "relocated_location" in relations:
        for action in relocation_candidates(graph):
            out, audit, notice = _relocate(graph, action)
            choices.append(("relocated_location", action["source_ordinal"], out, audit, notice))
    if "resolved_error" in relations:
        try:
            out, audit, notice = _resolved(graph, count, current, resolved_contracts)
            choices.append(("resolved_error", audit["source_ordinal"], out, audit, notice))
        except ValueError as error:
            if not str(error).startswith(("No same-argument", "No eligible", "No rendered", "Current user refers")):
                raise
            considered.append({"relation": "resolved_error", "eligible": False, "reason": str(error)})
    eligible = []
    for relation, ordinal, out, audit, notice in choices:
        shared, sharing_audit, renderer = _share(out, count, current)
        render = partial(_render, renderer=renderer, notice=notice)
        final_tokens = count(render(shared))
        additional = baseline_tokens - final_tokens
        considered.append({"relation": relation, "source_ordinal": ordinal,
                           "eligible": additional >= min_saved_tokens,
                           "additional_saved_vs_shared": additional})
        if additional >= min_saved_tokens:
            eligible.append((additional, ordinal, relation, shared, audit, sharing_audit, render))
    if _digest(graph) != before_hash:
        raise AssertionError("Input graph mutated")
    if not eligible:
        raise ValueError("No eligible positive successor edit after shared baseline")
    saved, ordinal, relation, out, audit, sharing_audit, renderer = sorted(
        eligible, key=lambda x: (-x[0], x[1], x[2]))[0]
    return out, {
        "version": ("g9-witness-pruning-v1.2" if "located_read" in resolved_contracts else
                    VERSION if tuple(resolved_contracts) == DEFAULT_RESOLVED_CONTRACTS else "g9-witness-pruning-v1.1"),
        "relation": relation, "edit": audit, "sharing": sharing_audit,
        "selection": "maximum_additional_saving_then_source_ordinal_then_relation",
        "considered": considered, "shared_baseline": baseline_audit,
        "shared_baseline_tokens": baseline_tokens, "memory_tokens_before": count(full_render(graph)),
        "memory_tokens_after": count(renderer(out)), "saved_tokens": count(full_render(graph)) - count(renderer(out)),
        "additional_saved_vs_shared": saved, "source_graph_sha256": before_hash,
        "edited_graph_sha256": _digest(out), "retained_evidence_exact": True,
        "full_original_evidence_preserved": False, "task_preservation_certified": False,
    }, renderer
