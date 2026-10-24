from copy import deepcopy
import json
import random

from core.mixed_graph import apply_domain_delta, domain_delta
from core.optimized_graph import _same


def test_domain_delta_deletions_nested_lists_and_explicit_null():
    before = {"entities": {"x": {"fields": {"old": 2, "none": None},
                                 "versions": [{"v": 1}]}},
              "observations": [1, {"a": "previous"}]}
    after = {"entities": {"x": {"fields": {"none": 3, "new": None},
                                "versions": [{"v": 1}, {"v": 2}]}},
             "observations": [1, {"a": "current"}]}
    saved = deepcopy(before)
    changes = domain_delta(before, after)
    assert any(change["op"] == "remove" for change in changes)
    assert any(change["op"] == "append" for change in changes)
    assert _same(apply_domain_delta(before, changes), after)
    assert _same(before, saved)


def test_domain_delta_strict_random_roundtrip():
    rng = random.Random(20717)

    def value(depth=0):
        scalar = rng.choice([None, False, True, 0, 1, "error", "$ref", ""])
        if depth > 3 or rng.randrange(3) == 0:
            return scalar
        if rng.randrange(2):
            return [value(depth + 1) for _ in range(rng.randrange(4))]
        return {str(key): value(depth + 1) for key in range(rng.randrange(4))}

    for _ in range(500):
        before, after = value(), value()
        assert _same(apply_domain_delta(before, domain_delta(before, after)), after)


def test_mixed_payload_all_methods_and_frozen_selected_codecs():
    from core.mixed_graph import build_memory, restore_history, rebuild_original_graph
    from core import lossless_state, lossless_event
    calls = [
        ("pwd", {}, {"current_working_directory": "/demo"}),
        ("ls", {}, {"current_directory_content": ["file.txt"]}),
        ("get_ticket", {"ticket_id": 4}, {"id": 4, "status": "Open", "title": "one"}),
        ("get_tweet", {"tweet_id": 4}, {"id": 4, "content": "hello", "username": "alice"}),
        ("get_ticket", {"ticket_id": 4}, {"id": 4, "status": "Closed", "title": "one"}),
        ("get_ticket", {"ticket_id": 4}, {"id": 4, "status": "Closed", "title": "one"}),
        ("mean", {"numbers": [2, 4]}, {"result": 3.0}),
        ("get_user_tickets", {}, "[{'error': 'User not authenticated.'}]"),
        ("message_get_login_status", {}, {"login_status": False}),
        ("mean", {"numbers": []}, "Error during execution: invalid argument"),
    ]
    history = [{"role": "user", "content": "Continue from these observations."}]
    for index, (tool, arguments, result) in enumerate(calls):
        history.extend([
            {"type": "function_call", "call_id": str(index), "name": tool,
             "arguments": json.dumps(arguments)},
            {"type": "function_call_output", "call_id": str(index),
             "output": result if isinstance(result, str) else json.dumps(result)},
        ])
    history.append({"role": "user", "content": "Now inspect the ticket and file."})
    for method, codec, variant in (
            ("v1-compact", lossless_state, "state-shared-v1"),
            ("v2-compact", lossless_event, "tables-v1"),
            ("v2-dedup", lossless_event, "shared-v1")):
        _, metadata = build_memory(history, method, "minimal", len)
        payload = metadata["graph"]
        assert _same(restore_history(payload), history)
        assert metadata["reconstruction_audit"]["semantic_state_fact_event_index_verified"]
        assert _same(codec.decode(codec.encode(payload, variant)), payload)
        assert _same(rebuild_original_graph(payload), rebuild_original_graph(
            codec.decode(codec.encode(payload, variant))))
        assert "TwitterAPI" in metadata["body"] and "TicketAPI" in metadata["body"]
