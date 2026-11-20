"""Lossy quote pruning witnessed by a matching, successful booking receipt.

This is an optional relation; book_flight has no price input and recomputes its
charge. No causal consumption or future task safety is asserted.
"""
from copy import deepcopy
import json
from cs769.models.edits import relation_pruning as rp

VERSION = "g9-booking-receipt-v1"
ITINERARY = ("travel_from", "travel_to", "travel_date", "travel_class")
RELATION = "same_itinerary_quote_matched_confirmed_booking_receipt"

def same_itinerary(a, b):
    return isinstance(a, dict) and isinstance(b, dict) and all(
        isinstance(a.get(k), str) and bool(a[k]) and a[k] == b.get(k) for k in ITINERARY)

def candidates(g, current):
    if rp.HISTORY_QUERY.search(json.dumps(current, ensure_ascii=False)):
        return [], {"history_query": 1}
    _, calls = rp.records(rp.evidence(g))
    actions, reasons = [], {}
    def reject(reason):
        reasons[reason] = reasons.get(reason, 0) + 1
    for i, old in enumerate(calls):
        if old["tool"] != "get_flight_cost" or not rp.ok(old["result"]):
            continue
        value = old["value"]
        vs = value.get("travel_cost_list") if isinstance(value, dict) else None
        if not isinstance(vs, list) or len(vs) < 2 or not all(type(v) in (int, float) for v in vs):
            continue
        for j in range(i + 1, len(calls)):
            booked = calls[j]
            if booked["tool"] != "book_flight" or not rp.ok(booked["result"]):
                continue
            if booked["call"]["ordinal"] <= old["result"]["ordinal"] or not same_itinerary(old["args"], booked["args"]):
                continue
            v = booked["value"]
            if not isinstance(v, dict) or v.get("booking_status") is not True:
                reject("unsuccessful_booking"); continue
            bid, tid = v.get("booking_id"), v.get("transaction_id")
            if not isinstance(bid, str) or not bid or not isinstance(tid, str) or not tid:
                reject("missing_receipt_id"); continue
            hist = v.get("booking_history")
            receipt = hist.get(bid) if isinstance(hist, dict) else None
            if not same_itinerary(receipt, booked["args"]) or receipt.get("transaction_id") != tid:
                reject("receipt_mismatch"); continue
            price = receipt.get("travel_cost")
            if type(price) not in (int, float) or not any(rp.eq(price, x) for x in vs):
                reject("receipt_price_unavailable"); continue
            producers = [p for p in calls[:j] if p["tool"] == "get_flight_cost" and rp.ok(p["result"])
                         and p["result"]["ordinal"] < booked["call"]["ordinal"]
                         and same_itinerary(p["args"], booked["args"])]
            if len(producers) != 1:
                reject("ambiguous_quote"); continue
            if any(any(s in (p["tool"] or "").lower() for s in ("login", "logout", "authenticat"))
                   for p in calls[i + 1:j]):
                reject("authentication_barrier"); continue
            if any(p["tool"] == "book_flight" and rp.ok(p["result"])
                   and same_itinerary(p["args"], booked["args"]) for p in calls[i + 1:j]):
                reject("multiple_booking_receipts"); continue
            canceled = any(p["tool"] == "cancel_booking" and rp.ok(p["result"]) and
                            isinstance(p["args"], dict) and p["args"].get("booking_id") == bid
                            for p in calls[j + 1:])
            replaced = any(p["tool"] in ("get_flight_cost", "book_flight") and rp.ok(p["result"])
                           and same_itinerary(p["args"], booked["args"]) for p in calls[j + 1:])
            if canceled or replaced:
                reject("booking_no_longer_current"); continue
            later = [p for p in calls[i + 1:] if p["call"]["ordinal"] > old["result"]["ordinal"]]
            used = [v for v in vs if rp.eq(v, price) or any(
                rp.eq(v, a) for p in later for a in rp.children(p["args"]))]
            if len(used) == len(vs):
                continue
            actions.append({
                "kind": "consumed", "relation": RELATION,
                "source_graph_sha256": rp._digest(g),
                "source_call": old["call"]["id"], "source_result": old["result"]["id"],
                "witness_call": booked["call"]["id"], "witness_result": booked["result"]["id"],
                "replace_list": {"key": "travel_cost_list", "retained": used},
                "itinerary_keys": list(ITINERARY), "receipt_booking_id": bid,
                "receipt_actual_price": price, "not_a_proven_price_argument_dependency": True})
    return actions, reasons

def apply(g, action, count):
    # Reuse the existing checked graph mutation; only this opt-in projection has
    # a different notice. Do not change the established consumed operator.
    if action.get("relation") != RELATION:
        raise ValueError("Wrong booking receipt relation")
    out, audit = rp.apply(g, action, count)
    mapping = audit["old_to_new_event_ids"]
    out["relation_pruning"] = {
        "version": VERSION,
        "notice": "Pruned quote list: " + mapping[action["source_result"]] +
                  "/output is partial; matching booking receipt: " + mapping[action["witness_result"]] + "."}
    saved = count(rp.full_render(g)) - count(rp.render(out))
    if saved <= 0:
        raise ValueError("No positive booking receipt saving")
    audit.update(version=VERSION, edited_graph_sha256=rp._digest(out), saved_tokens=saved,
                 memory_tokens_after=count(rp.render(out)), causal_dependency_proven=False,
                 booking_receipt_exact=True)
    return out, audit

def prune(g, count, current, *, min_saved_tokens=50):
    if type(min_saved_tokens) is not int or min_saved_tokens < 1:
        raise ValueError("Invalid minimum saving")
    choices = []
    for action in candidates(g, current)[0]:
        try:
            out, audit = apply(g, action, count)
        except ValueError as error:
            if str(error).startswith("No positive"):
                continue
            raise
        if audit["saved_tokens"] >= min_saved_tokens:
            choices.append((out, audit))
    if not choices:
        raise ValueError("No eligible booking receipt edit")
    return max(choices, key=lambda x: (x[1]["saved_tokens"], x[1]["action"]["source_result"]))

render = rp.render
