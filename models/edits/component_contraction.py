"""Contract a dependency-connected historical tool component to its boundary.

No task identifiers, future turns, answers, evaluator, transport or filesystem.
Facts are copied/verified from visible records. Contracts are tool semantics,
not safety certificates for unknown future questions.
"""
from copy import deepcopy
from functools import partial
import json, re, time
from cs769.models.edits.record_edits import evidence, _refresh, _digest, render as full_render
from cs769.models.edits.relation_pruning import records, fields, eq, children
from cs769.models.edits.witness_pruning import _share
from cs769.models.edits.dependency_projection import field_referenced
from cs769.models.graphs.graph_memory_records import audit_record_graph

VERSION = "g9-component-contraction-v1"
DOORS = {"driver", "passenger", "rear_left", "rear_right"}
READS = {"pwd", "ls", "find", "cat", "head", "tail", "wc", "grep", "diff", "sort"}

def dump(v):
    return json.dumps(v, ensure_ascii=False, separators=(",", ":"), sort_keys=True)

def success(c):
    v = c["value"]
    return (c["result"] is not None and not c["result"].get("native_is_error")
            and isinstance(v, dict) and "error" not in v
            and v.get("success") is not False)

def serial(old, new):
    return (old["result"] is not None
            and old["result"]["ordinal"] < new["call"]["ordinal"]
            and old["call"]["call_group"] != new["call"]["call_group"])

def exchange(c):
    return [c["call"]["id"], c["result"]["id"]]

def query_text(current):
    return dump(current)

def action(kind, removed, anchor, facts, edges):
    # Every removed exchange must have a reviewed connection to the anchor.
    ids = sorted({i for c in removed for i in exchange(c)})
    return {"kind": kind, "delete_events": ids,
            "anchor_call": anchor["call"]["id"],
            "anchor_result": anchor["result"]["id"],
            "facts": facts, "dependency_edges": edges}

def _actions(g, current):
    _, cs = records(evidence(g)); q = query_text(current)
    out = []
    for pos, end in enumerate(cs):
        if not success(end) or not isinstance(end["args"], dict):
            continue
        earlier = [c for c in cs[:pos] if success(c) and isinstance(c["args"],dict) and serial(c, end)]
        args, value, name = end["args"], end["value"], end["tool"]

        # Selected object in the same observed relative-directory frame.
        if name == "cat" and isinstance(value.get("file_content"), str):
            filename = args.get("file_name")
            listings = [c for c in earlier if c["tool"] == "ls"
                        and c["scope"] == end["scope"]
                        and isinstance(c["value"].get("current_directory_content"), list)
                        and c["value"]["current_directory_content"].count(filename) == 1]
            if listings and isinstance(filename, str):
                old = listings[-1]
                between = cs[cs.index(old)+1:pos]
                # An unreviewed write invalidates this directory-version claim.
                if all(c["tool"] in READS for c in between):
                    removed = [old,end]
                    edges = [{"from": old["result"]["id"], "to": end["call"]["id"],
                              "relation": "selected_filename_in_same_scope"}]
                    fact = {"selected_file": filename,
                            "file_content": value["file_content"],
                            "observed_by": "cat",
                            "listed_position_one_based": old["value"]["current_directory_content"].index(filename)+1,
                            "listed_count": len(old["value"]["current_directory_content"]),
                            "scope": list(end["scope"]),
                            "source_result": end["result"]["id"]}
                    # Capture the actually observed relative cwd, never invent /.
                    cds = [c for c in cs[:cs.index(old)] if c["tool"] == "cd"
                           and success(c) and serial(c, old)
                           and isinstance(c["value"].get("current_working_directory"), str)]
                    if cds:
                        cd = cds[-1]
                        if all(c["tool"] in READS for c in cs[cs.index(cd)+1:pos]):
                            removed.insert(0, cd)
                            fact["cwd_observed"] = cd["value"]["current_working_directory"]
                            edges.append({"from": cd["result"]["id"], "to": old["call"]["id"],
                                          "relation": "establishes_relative_directory_scope"})
                    out.append(action("selected_file_boundary", removed, end, [fact], edges))

        # Same-file derived count, verified against the actual visible version.
        if name == "wc" and type(value.get("count")) is int:
            mode = args.get("mode", "l")
            if mode not in ("l", "w", "c"):
                continue
            for old in reversed(earlier):
                if old["tool"] not in ("cat", "sort") or old["scope"] != end["scope"]:
                    continue
                if old["args"].get("file_name") != args.get("file_name"):
                    continue
                key = "file_content" if old["tool"] == "cat" else "sorted_content"
                body = old["value"].get(key)
                if not isinstance(body, str) or (old["tool"] == "sort" and mode == "c"):
                    continue
                if any(c["tool"] not in READS for c in cs[cs.index(old)+1:pos]):
                    continue
                expected = {"l": len(body.splitlines()), "w": len(body.split()), "c": len(body)}[mode]
                unit = {"l": "lines", "w": "words", "c": "characters"}[mode]
                if value["count"] != expected or value.get("type") != unit:
                    continue
                if re.search(r"\b(verbatim|entire|original|quote|full content)\b", q, re.I):
                    continue
                out.append(action("verified_file_count_boundary", [old], end,
                    [{"file_name": args["file_name"], "count": expected, "unit": unit,
                      "scope": list(end["scope"]), "verified_from": old["result"]["id"],
                      "retained_result": end["result"]["id"]}],
                    [{"from": old["result"]["id"], "to": end["result"]["id"],
                      "relation": "same_version_verified_count"}]))
                break

        # The current state is backed by a successful setter, not equal field names.
        if name == "lockDoors":
            affected = args.get("door")
            expected = "unlocked" if args.get("unlock") is True else "locked"
            if (type(args.get("unlock")) is not bool or not isinstance(affected, list)
                    or any(not isinstance(d,str) for d in affected)
                    or not set(affected) <= DOORS or value.get("lockStatus") != expected
                    or type(value.get("remainingUnlockedDoors")) is not int
                    or not 0<=value["remainingUnlockedDoors"]<=4):
                continue
            if set(affected)==DOORS and value["remainingUnlockedDoors"]!=(4 if args["unlock"] else 0):
                continue
            if re.search(r"\b(old|previous|earlier|before|history|compare|metadata|manual)\b", q, re.I):
                continue
            for old in reversed(earlier):
                doors = old["value"].get("doorStatus")
                if old["tool"] != "displayCarStatus" or old["args"] != {"option": "doors"}:
                    continue
                if (not isinstance(doors, dict) or not doors or not set(doors) <= set(affected)
                        or not set(old["value"])<={"doorStatus","metadata"}
                        or any(v not in ("locked","unlocked") for v in doors.values())):
                    continue
                if any(c["tool"] not in ("displayCarStatus", "check_tire_pressure")
                       for c in cs[cs.index(old)+1:pos]):
                    continue
                if not any(x != expected for x in doors.values()):
                    continue
                out.append(action("confirmed_door_state_boundary", [old], end,
                    [{"doors": {d: expected for d in sorted(doors)},
                      "confirmed_by": end["result"]["id"]}],
                    [{"from": old["result"]["id"], "to": end["result"]["id"],
                      "relation": "same_vehicle_property_overwritten"}]))
                break

        # A terminal observation can itself be a boundary: discard route details,
        # keep its actual distance and actual arguments, with no made-up result.
        if name == "estimate_distance" and type(value.get("distance")) in (int, float):
            cities = value.get("intermediaryCities")
            if (not isinstance(cities, list) or not cities
                    or re.search(r"\b(cities|city|route|waypoints?|intermediar\w*|stops|via)\b", q, re.I)):
                continue
            # Do not remove city information already consumed by another record.
            later = cs[pos+1:]
            if any(eq(cities, v) for c in later for v in children(c["args"])):
                continue
            # This read has no side effect; its verified observation is materialized.
            out.append(action("distance_result_boundary", [end], end,
                [{"observation": "estimate_distance", "arguments": deepcopy(args),
                  "result": {k:deepcopy(v) for k,v in value.items() if k!="intermediaryCities"}, "source_result": end["result"]["id"]}],
                [{"from": end["result"]["id"], "to": "fact:0",
                  "relation": "projects_observed_distance"}]))

        if name == "place_order" and type(value.get("order_id")) in (int,str) and str(value["order_id"]):
            quotes = [c for c in earlier if c["tool"] == "get_stock_info"
                      and isinstance(c["args"], dict) and c["args"].get("symbol") == args.get("symbol")
                      and eq(c["value"].get("price"), args.get("price"))]
            if not quotes or re.search(r"\b(stock details|all stocks|moving averages?|historical prices)\b|\b(other|second|third|last)\b.{0,35}\b(stock|symbol)\b", q, re.I):
                continue
            quote = quotes[-1]
            dropped_keys = {k for k,v in quote["value"].items() if isinstance(v,(list,dict))}
            if any(field_referenced(k, current) for k in dropped_keys):
                continue
            # A non-boundary field consumed elsewhere remains a live dependency.
            others = [c for c in cs[cs.index(quote)+1:] if c is not end]
            if any(isinstance(quote["value"][k], (list, dict))
                   and any(eq(quote["value"][k], v) for c in others for v in children(c["args"]))
                   for k in dropped_keys):
                continue
            removed = [quote]
            edges = [{"from": quote["result"]["id"], "to": end["call"]["id"],
                      "relation": "same_symbol_price_used_by_successful_order"}]
            catalogs = [c for c in cs[:cs.index(quote)] if success(c) and serial(c, quote)
                        and c["tool"] == "get_available_stocks"
                        and isinstance(c["value"].get("stock_list"), list)
                        and c["value"]["stock_list"].count(args.get("symbol")) == 1]
            if catalogs:
                cat = catalogs[-1]; removed.insert(0, cat)
                edges.append({"from": cat["result"]["id"], "to": quote["call"]["id"],
                              "relation": "selected_stock_membership"})
            out.append(action("successful_order_boundary", removed, end,
                [{"symbol": args.get("symbol"), "price": args.get("price"),
                  "amount": args.get("amount"), "order_id": value["order_id"],
                  "observed_stock_scalars":{k:deepcopy(v) for k,v in quote["value"].items() if not isinstance(v,(list,dict))},
                  "receipt_retained_at": end["result"]["id"]}], edges))

        if (name == "book_flight" and value.get("booking_status") is True
                and type(value.get("booking_id")) in (int,str) and str(value["booking_id"])):
            scope = ("travel_from", "travel_to", "travel_date", "travel_class")
            quotes = [c for c in earlier if c["tool"] == "get_flight_cost"
                      and isinstance(c["args"], dict)
                      and all(k in args and c["args"].get(k) == args[k] for k in scope)
                      and isinstance(c["value"].get("travel_cost_list"), list)]
            if not quotes or re.search(r"\b(quote|prices|cheapest|alternative|cost list|history|past|previous)\b", q, re.I):
                continue
            quote = quotes[-1]
            # A total-price request is not answered by a booking ID.
            if re.search(r"\b(total|calculate|sum|average)\b.{0,35}\b(cost|price|paid)\b", q, re.I):
                continue
            out.append(action("successful_booking_boundary", [quote], end,
                [{"itinerary": {k: args[k] for k in scope},
                  "booking_id": value.get("booking_id"),
                  "transaction_id": value.get("transaction_id"),
                  "receipt_and_original_payment_binding_retained_at": end["call"]["id"]}],
                [{"from": quote["result"]["id"], "to": end["result"]["id"],
                  "relation": "same_itinerary_quote_precedes_successful_booking_not_price_causality"}]))
    return out

def _losses(original, retained, removed, facts):
    kept = [f["value"] for n in retained["evidence_view"]["nodes"]
            for f in n.get("fields", [])] + facts
    all_values = [v for x in kept for v in children(x)]
    texts = [x for x in all_values if isinstance(x, str)]
    # Unpack actual JSON argument/result strings before testing retained copies.
    for text in list(texts):
        try: all_values.extend(children(json.loads(text)))
        except (ValueError, TypeError): pass
    witnesses = []
    for n in original["evidence_view"]["nodes"]:
        if n["id"] not in removed or n["category"] != "tool_result":
            continue
        raw = fields(n).get("output")
        try: value = json.loads(raw) if isinstance(raw, str) else raw
        except (ValueError, TypeError): continue
        if not isinstance(value, dict):
            continue
        for key, v in value.items():
            if isinstance(v, (list, dict)) and v and not any(type(x) is type(v) and x == v for x in all_values):
                if isinstance(v, list) and all(isinstance(z, str) for z in v):
                    missing = [z for z in v if not any(z in t for t in texts)]
                    if not missing: continue
                else:
                    if any(dump(v) in re.sub(r"\s+", "", t) for t in texts): continue
                witnesses.append({"source": n["id"], "field": key,
                    "kind": "structured_detail_not_retained",
                    "items": len(v), "value_sha256": _digest(v)})
            elif isinstance(v, str) and len(v) >= 128 and not any(v in t for t in texts):
                witnesses.append({"source": n["id"], "field": key,
                    "kind": "text_detail_not_retained", "characters": len(v),
                    "value_sha256": _digest(v)})
    return witnesses

def _render(g, *, renderer):
    base = deepcopy(g); layer = base.pop("component_contraction")
    view={"kind":layer["kind"],"facts":layer["facts"],"archived_source":layer["source_refs"]}
    if layer["anchor_in_retained_graph"] is not None:view["anchor"]=layer["anchor_in_retained_graph"]
    return renderer(base) + "\nCOMPONENT_FACTS " + dump(view)

def apply(g, a, count):
    if a not in candidates(g, a["current"]):
        raise ValueError("Action not in current component space")
    source_hash = _digest(g); old = evidence(g); ev = deepcopy(old)
    removed = set(a["delete_events"])
    ev["evidence_view"]["nodes"] = [n for n in ev["evidence_view"]["nodes"] if n["id"] not in removed]
    out, mapping = _refresh(ev)
    src = {n["id"]: n for n in old["evidence_view"]["nodes"] if n["category"] != "episode"}
    dst = {n["id"]: n for n in evidence(out)["evidence_view"]["nodes"] if n["category"] != "episode"}
    if set(mapping) != set(src)-removed: raise AssertionError("Undeclared contraction")
    for oldid, newid in mapping.items():
        want = deepcopy(src[oldid]); want.update(id=newid, ordinal=dst[newid]["ordinal"])
        if "result_of" in want: want["result_of"] = mapping[want["result_of"]]
        if want != dst[newid]: raise AssertionError("Retained evidence changed")
    loss = _losses(old, evidence(out), removed, a["facts"])
    sh, sharing, renderer = _share(out, count, a["current"])
    facts=deepcopy(a["facts"])
    ref_keys={"content_retained_at","confirmed_by","source_result","verified_from",
              "retained_result","receipt_retained_at","receipt_and_original_payment_binding_retained_at"}
    for fact in facts:
        for key in ref_keys & set(fact):
            oldid=fact[key]
            if oldid in mapping:fact[key]=mapping[oldid]
            elif oldid in removed:fact[key]="source:"+oldid
    sh["component_contraction"] = {
        "kind": a["kind"], "facts": facts,
        "source_refs": ["source:"+i for i in a["delete_events"]],
        "source_refs_are_archived_not_available_payload": True,
        "anchor_in_retained_graph": mapping.get(a["anchor_result"]),
    }
    if _digest(g) != source_hash: raise AssertionError("Source mutated")
    return sh, {"source_sha256": source_hash, "removed_events": sorted(removed),
                "old_to_new": mapping, "dependency_edges": a["dependency_edges"],
                "loss_witnesses": loss, "sharing": sharing,
                "retained_evidence_exact": True,
                "source_graph_not_attached_to_model": True}, partial(_render, renderer=renderer)

def candidates(g, current):
    return [dict(a, current=deepcopy(current)) for a in _actions(g, current)]

def contract(g, count, current, *, minimum_saving=1):
    start = time.perf_counter()
    if type(minimum_saving) is not int or minimum_saving < 1:
        raise ValueError("Invalid saving threshold")
    base, ba, br = _share(g, count, current); before = count(br(base))
    choices = []; considered = []
    for a in candidates(g, current):
        out, audit, renderer = apply(g, a, count)
        saved = before-count(renderer(out))
        considered.append({"kind": a["kind"], "saved_vs_shared": saved,
                           "loss_witnesses": audit["loss_witnesses"]})
        if saved >= minimum_saving:
            choices.append((saved, a["kind"], a["anchor_call"], out, audit, renderer))
    if not choices:
        return base, {"version": VERSION, "pruned": False, "reason": "no_profitable_component",
            "considered": considered, "sharing": ba, "editor_seconds": time.perf_counter()-start}, br
    saved, kind, _, out, audit, renderer = sorted(choices, key=lambda x: (-x[0], x[1], x[2]))[0]
    return out, {"version": VERSION, "pruned": True, "kind": kind,
        "additional_saved_vs_shared": saved, "considered": considered,
        "loss_witnesses": audit["loss_witnesses"], "edit": audit,
        "task_preservation_certified": False, "editor_api_tokens": 0,
        "editor_seconds": time.perf_counter()-start}, renderer
