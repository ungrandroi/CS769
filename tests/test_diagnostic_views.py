"""Controls for diagnostic validity, not a claim about model performance."""
from copy import deepcopy
import json
import random

import pytest

from core import lossless_event, lossless_state
from core.diagnostic_views import (expand_shared_references, goal_boundary_views,
                                   resolve_pointer, state_index)
from core.mixed_graph import domain_delta
from core.optimized_graph import _same


def test_goal_boundary_changes_segmentation_only_and_keeps_original_payload():
    goal = '\n Move "报告\\new.txt".\nDo not repeat finished steps. {"x": "$shared"} \n'
    messages = [{"role": "system", "content": "fixed tools and instructions"},
                {"role": "user", "content": '{"source_messages":{"m0":"original goal"}}',
                 "metadata": {"keep": True}}]
    before = deepcopy(messages)
    result = goal_boundary_views(messages, goal)
    inline, separate, view = result["inline"], result["separate"], result["goal_view"]
    assert messages == before
    assert inline[:-1] == separate[:-2] == messages[:-1]
    assert separate[:-1] == messages
    assert inline[-1]["metadata"] == messages[-1]["metadata"]
    assert inline[-1]["content"] == messages[-1]["content"] + view
    assert separate[-1] == {"role": "user", "content": view}
    assert view == "<current_request>\n" + goal + "\n</current_request>"
    assert "".join(m["content"] for m in inline) == "".join(m["content"] for m in separate)
    assert result["audit"]["native_template_boundary_verified"] is False


@pytest.mark.parametrize("messages,goal", [([], "x"), ([{"role": "assistant", "content": "x"}], "x"),
                                          ([{"role": "user", "content": []}], "x"),
                                          ([{"role": "user", "content": " x"}], "x"),
                                          ([{"role": "user", "content": "x\n"}], "x")])
def test_goal_boundary_refuses_unsupported_message_layout(messages, goal):
    with pytest.raises(ValueError):
        goal_boundary_views(messages, goal)


def test_native_qwen_boundary_when_local_template_available():
    pytest.importorskip("transformers")
    from core.local_qwen_tokenizer import DEFAULT_MODEL, read_gguf_metadata
    from core.qwen_prompt_accounting import render_prompt
    if not DEFAULT_MODEL.is_file():
        pytest.skip("Local Qwen GGUF metadata unavailable; native boundary remains unverified")
    metadata, _ = read_gguf_metadata(DEFAULT_MODEL)
    memory = '{"source_messages":{"m0":"preserved"}}'
    goal = '\n Move "a\\b". \n'
    pair = goal_boundary_views([{"role": "system", "content": "fixed"},
                                {"role": "user", "content": memory}], goal)
    prompts = {arm: render_prompt(pair[arm], [], metadata["tokenizer.chat_template"])
               for arm in ("inline", "separate")}
    boundary = "<|im_end|>\n<|im_start|>user\n"
    assert prompts["separate"] == prompts["inline"].replace(
        memory + pair["goal_view"], memory + boundary + pair["goal_view"], 1)
    assert all(pair["goal_view"] in prompt for prompt in prompts.values())


def event_payload(scope=True):
    columns = ["subject", "predicate", "value", "key", "retired_at"]
    rows = {"f_old": ["o/1~a", "status", "old", None, 2],
            "f_unknown": ["o/1~a", "status", None, None, None],
            "f_other": ["o/1~a", "status", "candidate", None, None],
            "f_observation": ["o/1~a", "observation.lookup", {"status": "old"}, None, None]}
    if scope:
        columns.append("fact_scope")
        for identity, row in rows.items():
            row.append("observation" if identity == "f_observation" else "state")
    return {"method": "v2-dedup", "fact_columns": columns, "facts": rows,
            "active_facts": ["f_unknown", "f_observation", "f_other"]}


def test_event_index_excludes_observations_retains_unknown_and_ambiguity():
    payload = event_payload()
    before = deepcopy(payload)
    result = state_index(payload)
    entries = result["view"]["state_index"]
    assert len(entries) == 1
    entry = entries[0]
    assert resolve_pointer(payload, entry["subject_ref"]) == "o/1~a"
    assert resolve_pointer(payload, entry["field_ref"]) == "status"
    assert entry["fact_refs"] == ["/facts/f_unknown", "/facts/f_other"]
    assert [resolve_pointer(payload, ref)[2] for ref in entry["fact_refs"]] == [None, "candidate"]
    assert result["audit"] == {"eligible_entries": 1, "eligible_fact_count": 2,
                               "ambiguous_entries": 1,
                               "omitted_active_facts": {"observation": 1, "missing_scope": 0, "other_scope": 0}}
    assert payload == before


def test_event_without_scope_is_empty_negative_control_not_inferred_state():
    result = state_index(event_payload(scope=False))
    assert result["view"]["state_index"] == []
    assert result["audit"]["eligible_entries"] == 0
    assert result["audit"]["omitted_active_facts"]["missing_scope"] == 3


def test_inconsistent_active_retired_markers_fail_without_repair():
    payload = event_payload()
    payload["active_facts"].append("f_old")
    with pytest.raises(ValueError, match="marked retired"):
        state_index(payload)


def test_event_index_distinguishes_false_zero_and_int_float_field_keys():
    payload = event_payload()
    payload["facts"] = {f"f{i}": ["o", "attribute", "x", key, None, "state"]
                        for i, key in enumerate([False, 0, 0.0, None])}
    payload["active_facts"] = list(payload["facts"])
    assert state_index(payload)["audit"]["eligible_entries"] == 4


def test_json_pointer_escapes_literal_keys_and_preserves_value_types():
    payload = {"~slash/": {"0": [None, False, 0, 0.0, {}, []]}}
    for i, expected in enumerate(payload["~slash/"]["0"]):
        actual = resolve_pointer(payload, f"/~0slash~1/0/{i}")
        assert _same(expected, actual)


def state_payload():
    domain0 = {"entities": {}, "observations": []}
    domain1 = {"entities": {"MessageAPI:message:1": {
        "fields": {"text": "old", "exists": True}, "versions": {"text": [{"value": "old"}]}}},
        "observations": [{"returned": "old"}]}
    domain2 = deepcopy(domain1)
    record = domain2["entities"]["MessageAPI:message:1"]
    record["fields"]["text"] = None
    del record["fields"]["exists"]
    record["fields"]["candidates"] = ["a", "b"]
    record["versions"]["text"].append({"value": None})
    domain2["observations"].append({"returned": "new"})
    return {"method": "v1-compact", "current_state": "s2", "state_nodes": {
        "s0": {"cwd": {"location_id": "l0", "value": None, "evidence": []},
               "objects": [], "domain_state": domain0},
        "s1": {"inherits": "s0", "changes": {
            "objects_updated": [{"object_index": 0, "name": "before", "content": "old",
                                 "exists": True, "evidence": {"name": ["m1"]}}],
            "domain_state_updates": domain_delta(domain0, domain1)}},
        "s2": {"inherits": "s1", "changes": {
            "cwd": {"location_id": "l1", "value": "document", "evidence": ["m4"]},
            "objects_updated": [{"object_index": 0, "name": "after", "content": None}],
            "domain_state_updates": domain_delta(domain1, domain2)}}}}


def entry_value(payload, entry):
    parts = entry["value_parts"]
    if len(parts) == 1 and parts[0]["path"] == []:
        return resolve_pointer(payload, parts[0]["source_ref"])
    return {tuple(part["path"]): resolve_pointer(payload, part["source_ref"]) for part in parts}


def test_state_index_follows_existing_versions_and_deletions_without_promoting_observations():
    payload = state_payload()
    before = deepcopy(payload)
    result = state_index(payload)
    entries = {tuple(e["state_path"]): e for e in result["view"]["state_index"]}
    assert entry_value(payload, entries[("objects", 0, "name")]) == "after"
    assert entry_value(payload, entries[("objects", 0, "content")]) is None
    assert entry_value(payload, entries[("objects", 0, "exists")]) is True
    assert entries[("objects", 0, "exists")]["value_parts"][0]["source_ref"].startswith("/state_nodes/s1/")
    domain = ("domain_state", "entities", "MessageAPI:message:1", "fields")
    assert entry_value(payload, entries[domain + ("text",)]) is None
    assert entry_value(payload, entries[domain + ("candidates",)]) == {(0,): "a", (1,): "b"}
    assert domain + ("exists",) not in entries
    assert all("observations" not in key and "versions" not in key and "evidence" not in key for key in entries)
    assert payload == before
    assert result["audit"]["eligible_entries"] == len(entries)


def test_state_domain_root_replacement_and_empty_field_values():
    payload = state_payload()
    replacement = {"entities": {"new": {"fields": {"empty_list": [], "empty_object": {}, "flag": False}}},
                   "observations": []}
    payload["state_nodes"]["s2"]["changes"]["domain_state_updates"] = [
        {"path": [], "op": "set", "value": replacement}]
    result = state_index(payload)
    entries = {tuple(e["state_path"]): e for e in result["view"]["state_index"]}
    for field, expected in replacement["entities"]["new"]["fields"].items():
        key = ("domain_state", "entities", "new", "fields", field)
        assert _same(entry_value(payload, entries[key]), expected)
    assert not any("MessageAPI:message:1" in key for key in entries)


def test_state_index_rejects_cycles_and_unknown_updates():
    payload = state_payload()
    payload["state_nodes"]["s0"]["inherits"] = "s2"
    with pytest.raises(ValueError, match="Cyclic"):
        state_index(payload)
    payload = state_payload()
    payload["state_nodes"]["s2"]["changes"]["new_unknown_operation"] = True
    with pytest.raises(ValueError, match="Unrecognized"):
        state_index(payload)


@pytest.mark.parametrize("codec,candidate,method,body_key", [
    (lossless_state, "state-shared-v1", "v1-compact", "payload"),
    (lossless_event, "shared-v1", "v2-compact", "graph"),
    (lossless_event, "shared-v1", "v2-dedup", "graph")])
def test_reference_expansion_retains_envelope_rules_dictionary_and_literal_collisions(codec, candidate, method, body_key):
    reserved = {"$ref": "v0", "$shared": "v0", "$literal": {"$shared": "v1"},
                "$json_string": "compact", "quotes": 'a "quote"\\\n' * 30}
    payload = {"method": method, "repeated": [reserved, reserved, deepcopy(reserved)],
               "nested": [{"$shared": "v0"}, {"$literal": {"$ref": "v1"}}],
               "types": [False, 0, 0.0, None, {}, []]}
    encoded = codec.encode(payload, candidate)
    before = deepcopy(encoded)
    result = expand_shared_references(encoded)
    expanded = result["encoded"]
    assert result["audit"]["expanded_references"] > 0
    assert list(expanded) == list(encoded)
    for key in encoded:
        if key != body_key:
            assert json.dumps(expanded[key]) == json.dumps(encoded[key])
    assert _same(codec.decode(expanded), payload)
    assert encoded == before
    # Applying again finds no references, including escaped original tag keys.
    second = expand_shared_references(expanded)
    assert second["audit"]["expanded_references"] == 0
    assert second["encoded"] == expanded


@pytest.mark.parametrize("codec,candidate,method", [
    (lossless_state, "state-shared-v1", "v1-compact"),
    (lossless_event, "shared-v1", "v2-compact")])
def test_zero_shared_references_is_byte_identical_negative_control(codec, candidate, method):
    payload = {"method": method, "literal_tags": {"$ref": "fake", "$shared": "fake"}, "nothing": None}
    encoded = codec.encode(payload, candidate)
    result = expand_shared_references(encoded)
    assert result["audit"]["expanded_references"] == 0
    assert result["audit"]["negative_control_unchanged"]
    assert codec.dumps(result["encoded"]) == codec.dumps(encoded)


def test_reference_expansion_does_not_repack_table_defaults_or_order():
    payload = {"method": "v2-compact", "event_columns": ["tool", "status", "value"],
               "events": {f"a{i}": ["ls", "success", "repeated value " * 10] for i in range(20)}}
    encoded = lossless_event.encode(payload, "shared-v1")
    assert encoded["packed_tables"] == ["events"]
    expanded = expand_shared_references(encoded)["encoded"]
    # The original table structure is restored only by expansion of its values,
    # not by re-choosing row columns, defaults, or exception structure.
    expected_table = lossless_event._unshare(encoded["graph"], encoded["shared_values"])["events"]
    assert expanded["graph"]["events"] == expected_table
    assert list(lossless_event.decode(expanded)["events"]) == list(payload["events"])


def test_seeded_nested_literal_collisions_restore_without_builders():
    rng = random.Random(20261024)
    keys = ["x", "$ref", "$shared", "$literal", "$json_string", "~a/b"]
    leaves = [None, False, True, 0, 0.0, "目录", 'quote "' * 50]
    def node(depth):
        if not depth or rng.random() < .35:
            return rng.choice(leaves)
        if rng.random() < .5:
            return [node(depth - 1) for _ in range(rng.randrange(4))]
        return {k: node(depth - 1) for k in rng.sample(keys, rng.randrange(5))}
    for _ in range(40):
        repeated = node(3)
        for codec, candidate, method in [(lossless_state, "state-shared-v1", "v1-compact"),
                                         (lossless_event, "shared-v1", "v2-dedup")]:
            payload = {"method": method, "values": [repeated, repeated, node(3)]}
            encoded = codec.encode(payload, candidate)
            expanded = expand_shared_references(encoded)["encoded"]
            assert _same(codec.decode(json.loads(json.dumps(expanded))), payload)


def test_other_codecs_rejected_instead_of_silently_changing_rules():
    with pytest.raises(ValueError, match="Only state-shared"):
        expand_shared_references(lossless_event.encode({"method": "v2-compact"}, "tables-v1"))
