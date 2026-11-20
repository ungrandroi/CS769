"""Lossless ownership, rendering equivalence and offline edit obligations."""
from copy import deepcopy
from itertools import combinations
import json
import math
import unittest
from unittest.mock import patch

from core.graph_memory_evidence import build_evidence_graph, inference_graph
from core.graph_memory_observed import build_observed_graph, render_observed_graph
from core.graph_memory_payload import (
    build_payload_graph, audit_payload_graph, restore_observed_graph,
    render_payload_graph, render_payload_segments, plan_member_projection,
    audit_member_projection_plan, _expand,
)
from test_graph_memory_observed import fixture, climate


def graph_for(output, args=None):
    return build_payload_graph(build_observed_graph(fixture([("unknown", args or {}, output)])))


def by_id(graph):
    return {n["id"]: n for n in graph["payload_layer"]["nodes"]}


def output_field(graph, index=0):
    return [f for f in graph["payload_layer"]["fields"] if f["field"] == "output"][index]


def root_value(graph, field=None):
    field = field or output_field(graph)
    ids = by_id(graph)
    root = ids[field["root"]]
    return ids[root["value"]] if root["kind"] == "document" else root


def key_of(graph, member):
    return json.loads(_expand(member["key"], by_id(graph)))


def member_of(graph, key, field=None):
    ids = by_id(graph)
    return next(ids[mid] for mid in root_value(graph, field)["members"] if key_of(graph, ids[mid]) == key)


def projected_text(graph, plan, field=None):
    """Test-only application of a deletion plan; never sent as inference input."""
    ids = by_id(graph)
    removed = set(plan["removed_payload_node_ids"])

    def visit(identity):
        if identity in removed:
            return ""
        node = ids[identity]
        return node["text"] if node["kind"] in ("fragment", "opaque") else "".join(visit(c) for c in node["parts"])

    return visit((field or output_field(graph))["root"])


class PayloadGraphTests(unittest.TestCase):
    def test_lossless_lexical_variants_duplicates_unicode_and_whitespace(self):
        originals = [
            ' \n { "x" : 1.0 , "x":1e0,"zero":-0,"u":"\\u0061","slash":"\\/","esc":"\\n\\t\\\\","字":"文" }\t',
            '[null,true,false,"",{},[],"1",1,1.0,-0,2E+03]',
            '"a JSON-looking string: {\\"x\\":1}"',
            '  1e400\r\n',
        ]
        for original in originals:
            with self.subTest(original=original):
                graph = graph_for(original)
                field = output_field(graph)
                self.assertEqual(_expand(field["root"], by_id(graph)), original)
                self.assertEqual(field["source_kind"], "json-text")
                self.assertEqual(audit_payload_graph(graph)["duplicate_content_owner_count"], 0)
                self.assertTrue(audit_payload_graph(graph)["ok"])
                restored = restore_observed_graph(graph)
                event = next(n for n in restored["evidence_view"]["nodes"] if n["id"] == field["event_id"])
                self.assertEqual(next(f["value"] for f in event["fields"] if f["field"] == field["field"]), original)

    def test_opaque_parser_abstention_preserves_all_characters(self):
        for original in ('', 'plain text\n keep \\ two  spaces', '{"a":1,}', '{"a":01}', '[1 2]', 'NaN', '{"bad":"\\x"}', '"unterminated'):
            graph = graph_for(original)
            field = output_field(graph)
            self.assertEqual(field["source_kind"], "opaque-text")
            self.assertEqual(field["parse_fallback"], "invalid-json")
            self.assertEqual(_expand(field["root"], by_id(graph)), original)
            self.assertTrue(audit_payload_graph(graph)["ok"])

    def test_depth_and_node_limits_keep_whole_field_as_opaque(self):
        original = '[' * 70 + '0' + ']' * 70
        graph = graph_for(original)
        self.assertEqual(output_field(graph)["parse_fallback"], "depth-limit")
        self.assertEqual(_expand(output_field(graph)["root"], by_id(graph)), original)
        self.assertTrue(audit_payload_graph(graph)["ok"])
        with patch('core.graph_memory_payload.MAX_NODES_PER_FIELD', 10):
            limited = graph_for('[1,2,3,4,5,6]')
            self.assertEqual(output_field(limited)["parse_fallback"], "node-limit")
            self.assertTrue(audit_payload_graph(limited)["ok"])

    def test_typed_sources_preserve_existing_types_order_and_negative_float_zero(self):
        native_values = [
            {"z": -0.0, "a": 1.0, "b": 1, "bool": True, "null": None, "array": ["x", {}]},
            [1, 1.0, False, None, "text"], False, None, 1, 1.0,
        ]
        for value in native_values:
            history = [{"role": "user", "content": "Keep native"},
                       {"type": "function_call", "call_id": "x", "name": "unknown", "arguments": {"z": 2, "a": 1}},
                       {"type": "function_call_output", "call_id": "x", "output": value}]
            g7 = build_observed_graph(inference_graph(build_evidence_graph(history, episodic_only=True)))
            graph = build_payload_graph(g7)
            self.assertEqual(restore_observed_graph(graph), g7)
            self.assertEqual(output_field(graph)["source_kind"], "typed-source")
            self.assertEqual(output_field(graph)["lexical_origin"], "g5-deterministic-display")
            self.assertEqual(render_payload_graph(graph, layout="g7-compatible"), render_observed_graph(g7))
            output = next(n for n in restore_observed_graph(graph)["evidence_view"]["nodes"] if n["category"] == "tool_result")["fields"][0]["value"]
            self.assertIs(type(output), type(value))
            if isinstance(value, dict):
                self.assertEqual(list(output), list(value))
                self.assertEqual(math.copysign(1, output['z']), -1)

    def test_tool_payload_has_unique_owner_and_no_event_full_value(self):
        graph = build_payload_graph(build_observed_graph(climate()))
        for event in graph["evidence_view"]["nodes"]:
            for field in event.get("fields", []):
                if event["category"] == "tool_result" or (event["category"] == "tool_call" and field["field"].endswith("arguments")):
                    self.assertNotIn("value", field)
                    self.assertIn("payload_root", field)
                else:
                    self.assertIn("value", field)
        self.assertEqual(set(graph), {"delivery", "evidence_view", "evidence_audit", "observed_layer", "payload_layer"})
        for node in graph["payload_layer"]["nodes"]:
            self.assertEqual("text" in node, node["kind"] in ("fragment", "opaque"))

    def test_duplicate_members_remain_independent_and_semantics_abstain(self):
        original = '{"result":1.0,"result":1e0}'
        graph = build_payload_graph(build_observed_graph(fixture([("add", {"a": 1, "b": 0}, original)])))
        members = root_value(graph)["members"]
        self.assertEqual(len(members), 2)
        self.assertNotEqual(members[0], members[1])
        self.assertFalse(any(n["category"] == "observation" for n in graph["observed_layer"]["nodes"]))
        plan = plan_member_projection(graph, removed_member_ids=[members[0]])
        self.assertEqual(projected_text(graph, plan), '{"result":1e0}')
        self.assertTrue(audit_member_projection_plan(graph, plan)["ok"])

    def test_inline_markers_are_only_display_difference_and_source_markers_survive(self):
        base = fixture([("unknown", '{"x":"⟦f1⟧"}', '{"x":"⟦|f2|⟧","nested":{"a":1},"arr":[1,2]}')])
        g7 = build_observed_graph(base)
        graph = build_payload_graph(g7)
        original = render_observed_graph(g7)
        segments = render_payload_segments(graph)
        self.assertEqual(''.join(s["text"] for s in segments if s["kind"] != "payload_member_marker"), original)
        candidate = render_payload_graph(graph)
        self.assertIn('⟦f1⟧', candidate)
        self.assertIn('⟦|f2|⟧', candidate)
        self.assertNotEqual(candidate, original)
        self.assertEqual(render_payload_graph(graph, layout="g7-compatible"), original)
        markers = [s for s in segments if s["kind"] == "payload_member_marker"]
        self.assertEqual(len(markers), audit_payload_graph(graph)["address_count"])
        self.assertTrue(all(by_id(graph)[s["node_id"]]["kind"] == "member" for s in markers))

    def test_unknown_domain_still_has_payload_member_addresses(self):
        graph = graph_for('{"unmapped":{"id":7,"body":"Keep"}}')
        self.assertEqual(graph["observed_layer"]["nodes"], [])
        self.assertGreater(audit_payload_graph(graph)["address_count"], 0)
        self.assertNotEqual(render_payload_graph(graph), render_payload_graph(graph, layout="g7-compatible"))

    def test_nested_json_string_not_decoded_to_fake_member_nodes(self):
        graph = graph_for('{"file_text":"{\\"inner\\":7}"}')
        ids = by_id(graph)
        members = [n for n in ids.values() if n["kind"] == "member"]
        self.assertEqual([key_of(graph, n) for n in members], ['file_text'])

    def test_semantic_sources_bind_exact_values_without_g6(self):
        g7 = build_observed_graph(climate())
        graph = build_payload_graph(g7)
        self.assertEqual(graph["observed_layer"], g7["observed_layer"])
        self.assertNotIn('structured_layer', graph)
        self.assertTrue(graph["payload_layer"]["source_bindings"])
        self.assertTrue(all(b["granularity"] == "exact_value_node" for b in graph["payload_layer"]["source_bindings"]))
        self.assertTrue(all(b["target"] in by_id(graph) for b in graph["payload_layer"]["source_bindings"]))

    def test_text_block_encoded_document_binding_is_explicitly_coarse(self):
        history = [{"role": "user", "content": "Keep"},
                   {"type": "function_call", "call_id": "x", "name": "add", "arguments": {"a": 1, "b": 2}},
                   {"type": "function_call_output", "call_id": "x", "output": [{"type": "text", "text": '{"result":3}'}]}]
        graph = build_payload_graph(build_observed_graph(inference_graph(build_evidence_graph(history, episodic_only=True))))
        coarse = [b for b in graph["payload_layer"]["source_bindings"] if b["source"]["document_pointer"]]
        self.assertTrue(coarse)
        self.assertTrue(all(b["granularity"] == "encoded_document_scalar" and by_id(graph)[b["target"]]["kind"] == "scalar" for b in coarse))
        block = by_id(graph)[by_id(graph)[root_value(graph)["members"][0]]["value"]]
        type_member = next(mid for mid in block["members"] if key_of(graph, by_id(graph)[mid]) == "type")
        plan = plan_member_projection(graph, removed_member_ids=[type_member])
        observations = [n for n in graph["observed_layer"]["nodes"] if n["category"] == "observation"]
        self.assertTrue(all(n["id"] in plan["required_removed_semantic_node_ids"] for n in observations))

    def test_audit_rejects_duplicate_ownership_gaps_orphans_and_extra_raw_payload(self):
        graph = graph_for('{"a":1,"b":2}')
        bads = []
        bad = deepcopy(graph); root_value(bad)["parts"].append(root_value(bad)["parts"][0]); bads.append(bad)
        bad = deepcopy(graph); next(n for n in bad["payload_layer"]["nodes"] if n["kind"] == "fragment")["span"][0] = 1; bads.append(bad)
        bad = deepcopy(graph); bad["payload_layer"]["nodes"].append({"id":"g8:orphan", "kind":"opaque", "span":[0,1],"text":"x"}); bads.append(bad)
        bad = deepcopy(graph); root_value(bad)["text"] = '{"a":1,"b":2}'; bads.append(bad)
        bad = deepcopy(graph); next(n for n in bad["evidence_view"]["nodes"] if n["category"] == "tool_result")["fields"][0]["value"] = '{"a":1,"b":2}'; bads.append(bad)
        bad = deepcopy(graph); bad["source_messages"] = []; bads.append(bad)
        bad = deepcopy(graph); bad["payload_layer"]["nodes"].append(deepcopy(bad["payload_layer"]["nodes"][0])); bads.append(bad)
        bad = deepcopy(graph); root_value(bad)["members"].reverse(); bads.append(bad)
        for bad in bads:
            self.assertFalse(audit_payload_graph(bad)["ok"])
            with self.assertRaises(ValueError):
                restore_observed_graph(bad)
        self.assertGreater(audit_payload_graph(bads[0])["duplicate_content_owner_count"], 0)

    def test_audit_rejects_dangling_semantic_binding_and_false_granularity(self):
        graph = build_payload_graph(build_observed_graph(climate()))
        for key, value in (("target", "missing"), ("granularity", "opaque_field_root")):
            bad = deepcopy(graph)
            bad["payload_layer"]["source_bindings"][0][key] = value
            self.assertFalse(audit_payload_graph(bad)["ok"])

    def test_object_member_projection_repairs_commas_for_all_subsets(self):
        graph = graph_for('{ "a":1, \n"b":2 , "c":3 }')
        members = root_value(graph)["members"]
        for count in (1, 2, 3):
            for chosen in combinations(members, count):
                plan = plan_member_projection(graph, removed_member_ids=list(chosen))
                text = projected_text(graph, plan)
                expected = {key: val for mid, (key, val) in zip(members, {"a":1,"b":2,"c":3}.items()) if mid not in chosen}
                self.assertEqual(json.loads(text), expected)
                self.assertTrue(audit_member_projection_plan(graph, plan)["ok"])
                self.assertFalse(plan["applied"])

    def test_array_element_projection_preserves_other_values_and_layout(self):
        graph = graph_for('[ 1 , 2, 3 ]')
        elements = root_value(graph)["members"]
        for chosen, expected in (([elements[0]], [2,3]), ([elements[1]], [1,3]), ([elements[2]], [1,2]), (elements, [])):
            plan = plan_member_projection(graph, removed_member_ids=chosen)
            self.assertEqual(json.loads(projected_text(graph, plan)), expected)
            self.assertGreater(len(plan["removed_content_owner_ids"]), 0)

    def test_payload_member_projection_drops_only_supported_observation_and_edges(self):
        graph = build_payload_graph(build_observed_graph(climate()))
        original = deepcopy(graph)
        field = next(f for f in graph["payload_layer"]["fields"] if f["field"] == "output" and 'humidityLevel' in _expand(f["root"], by_id(graph)))
        target = member_of(graph, 'humidityLevel', field)
        plan = plan_member_projection(graph, removed_member_ids=[target["id"]])
        self.assertEqual(json.loads(projected_text(graph, plan, field)), {"currentTemperature":22,"climateMode":"cool"})
        semantic = [n for n in graph["observed_layer"]["nodes"] if n["category"] == "observation" and n["source"]["event_id"] == field["event_id"]]
        for node in semantic:
            if node["property"] == "climate.humidity":
                self.assertIn(node["id"], plan["required_removed_semantic_node_ids"])
            else:
                self.assertIn(node["id"], plan["supported_semantic_node_ids"])
        self.assertFalse(plan["order_edges_reconnected"])
        self.assertFalse(plan["task_preservation_certified"])
        self.assertEqual(graph, original)

    def test_projection_parent_input_dependency_and_binding_owner_closure(self):
        graph = build_payload_graph(build_observed_graph(fixture([
            ("si_unit_conversion", {"value": 10, "unit_in": "m", "unit_out": "cm"}, {"result": 1000}),
        ])))
        args_field = next(f for f in graph["payload_layer"]["fields"] if f["field"] == "arguments")
        target = member_of(graph, 'unit_out', args_field)
        plan = plan_member_projection(graph, removed_member_ids=[target["id"]])
        removed = set(plan["required_removed_semantic_node_ids"] + plan["required_removed_semantic_edge_ids"])
        self.assertTrue(removed)
        self.assertFalse(any(owner['id'] in removed for binding in plan['supported_bindings'] for owner in binding['semantic_owners']))
        self.assertTrue(audit_member_projection_plan(graph, plan)["ok"])
        array_graph = build_payload_graph(build_observed_graph(fixture([("mean", {"numbers":[1,2,3]}, {"result":2})])))
        args_field = next(f for f in array_graph["payload_layer"]["fields"] if f["field"] == "arguments")
        numbers = by_id(array_graph)[member_of(array_graph, 'numbers', args_field)["value"]]
        arr_plan = plan_member_projection(array_graph, removed_member_ids=[numbers["members"][1]])
        inputs = [e for e in array_graph["observed_layer"]["edges"] if e["relation"] == "declared_inputs"]
        self.assertIn(inputs[0]["id"], arr_plan["required_removed_semantic_edge_ids"])

    def test_projection_plan_tampering_or_index_only_deletion_is_rejected(self):
        graph = graph_for('{"a":1,"b":2}')
        target = root_value(graph)["members"][0]
        plan = plan_member_projection(graph, removed_member_ids=[target])
        for key in ('payload_operations', 'removed_content_owner_ids', 'removed_payload_node_ids'):
            bad = deepcopy(plan); bad[key] = []
            self.assertFalse(audit_member_projection_plan(graph, bad)["ok"])
        with self.assertRaises(ValueError):
            plan_member_projection(graph, removed_member_ids=[output_field(graph)["root"]])
        with self.assertRaises(ValueError):
            plan_member_projection(graph, removed_member_ids=[target, target])

    def test_construction_and_render_are_deterministic_and_do_not_mutate_input(self):
        g7 = build_observed_graph(climate())
        before = deepcopy(g7)
        graph = build_payload_graph(g7)
        self.assertEqual(graph, build_payload_graph(g7))
        self.assertEqual(graph, json.loads(json.dumps(graph)))
        render_payload_graph(graph)
        self.assertEqual(g7, before)
        self.assertEqual(restore_observed_graph(graph), g7)


if __name__ == '__main__':
    unittest.main()
