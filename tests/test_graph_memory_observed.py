"""Offline public-contract/causality/projection boundaries; no model calls."""
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import unittest

from core.graph_memory_evidence import (
    build_evidence_graph, inference_graph, render_evidence_graph,
    reconstruct_visible_evidence,
)
from core.graph_memory_observed import (
    build_observed_graph, audit_observed_graph, strip_observed_graph,
    render_observed_graph, resolve_source, plan_field_projection,
    audit_projection_plan, PUBLIC_DOC_SHA256, _VEHICLE_RULES, _MATH,
)


def fixture(exchanges):
    history = [{"role": "user", "content": "Keep all payloads. 字\n"}]
    for index, (name, args, result) in enumerate(exchanges):
        history += [
            {"type": "function_call", "call_id": str(index), "name": name,
             "arguments": args if isinstance(args, str) else json.dumps(args)},
            {"type": "function_call_output", "call_id": str(index),
             "output": result if isinstance(result, str) else json.dumps(result)},
        ]
    history.append({"role": "assistant", "content": "Finished.\n"})
    return inference_graph(build_evidence_graph(history, episodic_only=True))


def nodes(graph, category=None):
    return [n for n in graph["observed_layer"]["nodes"] if category is None or n["category"] == category]


def edges(graph, relation=None):
    return [e for e in graph["observed_layer"]["edges"] if relation is None or e["relation"] == relation]


def climate():
    return fixture([
        ("displayCarStatus", {"option": "climate"}, {"status": {"currentACTemperature": 18, "fanSpeed": 50, "climateMode": "auto"}}),
        ("adjustClimateControl", {"temperature": 22, "unit": "celsius", "fanSpeed": 40, "mode": "cool"},
         {"currentTemperature": 22, "climateMode": "cool", "humidityLevel": 45}),
        ("displayCarStatus", {"option": "climate"}, {"status": {"currentACTemperature": 21, "fanSpeed": 40, "climateMode": "cool"}}),
    ])


class ObservedGraphTests(unittest.TestCase):
    def test_contract_hash_locations_and_types_match_public_docs(self):
        directory = Path(__file__).resolve().parents[1] / "vendor/gorilla/berkeley-function-call-leaderboard/bfcl_eval/data/multi_turn_func_doc"
        docs = {}
        for name, digest in PUBLIC_DOC_SHA256.items():
            path = directory / (name + ".json")
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
            for line in path.read_text().splitlines():
                item = json.loads(line)
                docs[item["name"]] = item
        for tool, role, pointer, prop, unit, kind, request, option in _VEHICLE_RULES:
            with self.subTest(tool=tool, pointer=pointer):
                schema = docs[tool]["parameters" if role == "argument" else "response"]
                for token in pointer.split("/")[1:]:
                    schema = schema["properties"][token]
                self.assertEqual(schema["type"], {"number": "float"}.get(kind, kind))
        for tool, ports in _MATH.items():
            self.assertEqual(set(dict(ports)), set(docs[tool]["parameters"]["properties"]))
            for name, kind in ports:
                self.assertEqual(docs[tool]["parameters"]["properties"][name]["type"],
                                 {"number": "float", "numbers": "array"}.get(kind, kind))

    def test_full_payload_strip_and_exact_render_prefix_without_archive(self):
        base = climate()
        original = deepcopy(base)
        graph = build_observed_graph(base)
        self.assertEqual(strip_observed_graph(graph), base)
        self.assertEqual(base, original)
        self.assertEqual(reconstruct_visible_evidence(graph), reconstruct_visible_evidence(base))
        self.assertTrue(render_observed_graph(graph).startswith(render_evidence_graph(base)))
        self.assertTrue(audit_observed_graph(graph)["ok"])
        self.assertEqual(graph, build_observed_graph(base))
        self.assertEqual(graph, json.loads(json.dumps(graph)))
        self.assertNotIn("structured_layer", graph)
        self.assertNotIn("source_messages", graph)
        with self.assertRaises(ValueError):
            build_observed_graph({**base, "source_messages": []})

    def test_nodes_only_ablation_identical_nodes_values_and_payload(self):
        graph = build_observed_graph(climate())
        control = build_observed_graph(climate(), "observed-nodes-only-v1")
        self.assertEqual(nodes(graph), nodes(control))
        self.assertEqual(strip_observed_graph(graph), strip_observed_graph(control))
        self.assertEqual(edges(control), [])
        self.assertGreater(audit_observed_graph(graph)["edge_count"], 0)
        self.assertTrue(audit_observed_graph(control)["ok"])

    def test_outside_contract_scope_renders_exact_g5_without_empty_appendix(self):
        base = fixture([("unknown", {"number": 1}, {"result": 2})])
        graph = build_observed_graph(base)
        self.assertEqual(nodes(graph), [])
        self.assertEqual(render_observed_graph(graph), render_evidence_graph(base))
        self.assertEqual(graph["observed_layer"]["extraction_stats"]["unmapped_result_scalar_leaf_count"], 1)

    def test_cross_tool_observation_versions_and_request_return_separation(self):
        graph = build_observed_graph(climate())
        obs = [n for n in nodes(graph, "observation") if n["property"] == "climate.setpoint"]
        self.assertEqual([resolve_source(graph, n["source"]) for n in obs], [18, 22, 21])
        self.assertEqual(len({n["channel"] for n in obs}), 1)
        prior = [e for e in edges(graph, "next_visible_observation") if e["from"] in {n["id"] for n in obs}]
        self.assertEqual([(e["from"], e["to"][0]) for e in prior], [(obs[0]["id"], obs[1]["id"]), (obs[1]["id"], obs[2]["id"])])
        self.assertEqual(len(edges(graph, "reported_with")), 2)  # temperature and mode, no fabricated fan return
        fan = [n for n in nodes(graph, "observation") if n["property"] == "climate.fan_speed"]
        self.assertEqual([resolve_source(graph, n["source"]) for n in fan], [50, 40])
        text = render_observed_graph(graph)
        self.assertNotIn("supersedes", text)
        self.assertNotIn("current=", text)
        self.assertNotIn("operation_succeeded", text)

    def test_fuel_delta_and_engine_control_not_synthesized_states(self):
        graph = build_observed_graph(fixture([
            ("fillFuelTank", {"fuelAmount": 5}, {"fuelLevel": 12}),
            ("startEngine", {"ignitionMode": "START"}, {"engineState": "stopped", "fuelLevel": 11}),
            ("displayCarStatus", {"option": "fuel"}, {"status": {"fuelLevel": 10}}),
        ]))
        requests = nodes(graph, "request_port")
        self.assertEqual([n["port_kind"] for n in requests], ["delta", "control"])
        self.assertEqual([resolve_source(graph, n["source"]) for n in nodes(graph, "observation") if n["property"] == "fuel.level"], [12, 11, 10])
        self.assertEqual(len(edges(graph, "reported_with")), 2)
        self.assertFalse(any(n.get("value") == 17 for n in nodes(graph)))

    def test_units_defaults_and_aggregate_door_results_do_not_create_facts(self):
        graph = build_observed_graph(fixture([
            ("adjustClimateControl", {"temperature": 68, "unit": "fahrenheit"}, {"currentTemperature": 20}),
            ("adjustClimateControl", {"temperature": 21}, {"currentTemperature": 21}),
            ("setCruiseControl", {"speed": 50, "activate": True, "distanceToNextVehicle": 20}, {"currentSpeed": 80}),
            ("lockDoors", {"unlock": False, "door": ["driver", "passenger"]}, {"lockStatus": "locked", "remainingUnlockedDoors": 0}),
        ]))
        reqs = nodes(graph, "request_port")
        self.assertEqual([n["unit"] for n in reqs], ["degF", "unknown", "m/h (literal)"])
        self.assertFalse(any(n["tool"] == "lockDoors" for n in nodes(graph, "observation")))
        self.assertFalse(edges(graph, "equal_number_prior"))
        self.assertTrue(audit_observed_graph(graph)["ok"])

    def test_display_selector_and_weather_source_qualification(self):
        graph = build_observed_graph(fixture([
            ("displayCarStatus", {"option": "fuel"}, {"status": {"fuelLevel": 9, "currentACTemperature": 22}}),
            ("displayCarStatus", {}, {"status": {"fuelLevel": 10}}),
            ("get_outside_temperature_from_google", {}, {"outsideTemperature": 5}),
            ("get_outside_temperature_from_weather_com", {}, {"outsideTemperature": 6}),
        ]))
        obs = nodes(graph, "observation")
        self.assertEqual(len(obs), 3)
        self.assertEqual(obs[0]["supports"][0]["pointer"], "/option")
        self.assertNotEqual(obs[1]["channel"], obs[2]["channel"])
        self.assertFalse(edges(graph, "next_visible_observation"))

    def test_schema_wrapper_mismatch_abstains_and_reports_unmapped_fields(self):
        graph = build_observed_graph(fixture([
            ("displayCarStatus", {"option": "doors"}, {"doorStatus": {"driver": "unlocked"}}),
            ("imperial_si_conversion", {"value": 20, "unit_in": "liter", "unit_out": "gallon"}, {"gallon": 5.2}),
        ]))
        self.assertEqual(nodes(graph, "observation"), [])
        stats = graph["observed_layer"]["extraction_stats"]
        self.assertEqual(stats["absent_registered_result_paths"], 4)
        self.assertEqual(stats["missing_math_result_fields"], 1)
        self.assertEqual(stats["unmapped_result_scalar_leaf_count"], 2)
        self.assertTrue(audit_observed_graph(graph)["ok"])

    def test_math_input_hyperedges_and_exact_prior_numeric_equality(self):
        graph = build_observed_graph(fixture([
            ("subtract", {"a": 50, "b": 20}, {"result": 30}),
            ("divide", {"a": 30, "b": 10}, {"result": 3}),
            ("round_number", {"number": 3, "decimal_places": 0}, {"result": 3}),
        ]))
        self.assertEqual(len({n["scope"] for n in nodes(graph, "observation")}), 3)
        self.assertEqual(len(edges(graph, "declared_inputs")), 3)
        self.assertTrue(all(len(e["to"]) == 2 for e in edges(graph, "declared_inputs")))
        self.assertEqual(len(edges(graph, "equal_number_prior")), 2)
        self.assertFalse(edges(graph, "next_visible_observation"))
        self.assertFalse(edges(graph, "reported_with"))
        self.assertTrue(audit_observed_graph(graph)["ok"])

    def test_math_missing_or_wrong_type_inputs_not_called_complete_set(self):
        graph = build_observed_graph(fixture([
            ("square_root", {"number": -1, "precision": 10}, {"result": "undefined"}),
            ("add", {"a": True, "b": 1}, {"result": 2}),
            ("add", {"a": 1, "b": 1, "unknown": 7}, {"result": 2}),
            ("add", '{"a":1,"a":2,"b":3}', {"result": 5}),
        ]))
        self.assertEqual(len(edges(graph, "declared_inputs")), 1)
        self.assertEqual(nodes(graph, "observation")[0]["value_type"], "str")
        self.assertFalse(edges(graph, "equal_number_prior"))
        self.assertGreater(graph["observed_layer"]["extraction_stats"]["type_conflicts"], 0)

    def test_math_unit_literals_forbid_known_different_units(self):
        graph = build_observed_graph(fixture([
            ("si_unit_conversion", {"value": 1, "unit_in": "m", "unit_out": "cm"}, {"result": 100}),
            ("si_unit_conversion", {"value": 100, "unit_in": "kg", "unit_out": "g"}, {"result": 100000}),
        ]))
        self.assertFalse(edges(graph, "equal_number_prior"))
        self.assertEqual(nodes(graph, "observation")[0]["unit"], "literal:cm")

    def test_decimal_precision_and_boolean_are_not_conflated(self):
        graph = build_observed_graph(fixture([
            ("add", '{"a":0.1,"b":0.2}', '{"result":0.3000000000000000001}'),
            ("add", '{"a":0.3,"b":1}', '{"result":1.3}'),
            ("add", '{"a":0.3000000000000000001,"b":1}', '{"result":1.3}'),
        ]))
        equality = edges(graph, "equal_number_prior")
        self.assertEqual(len(equality), 1)
        self.assertEqual(resolve_source(graph, equality[0]["supports"][0]), Decimal("0.3000000000000000001"))
        self.assertIn("0.3000000000000000001", render_observed_graph(graph))

    def test_parallel_calls_do_not_gain_return_order_or_future_inputs(self):
        for tools in [("get_current_speed", "get_current_speed"), ("add", "add")]:
            history = [
                {"role": "user", "content": "Both"},
                {"role": "assistant", "tool_calls": [
                    {"id": "a", "function": {"name": tools[0], "arguments": '{"a":1,"b":1}' if tools[0] == "add" else '{}'}},
                    {"id": "b", "function": {"name": tools[1], "arguments": '{"a":2,"b":1}' if tools[1] == "add" else '{}'}},
                ]},
                {"role": "tool", "tool_call_id": "a", "content": '{"result":2}' if tools[0] == "add" else '{"currentSpeed":10}'},
                {"role": "tool", "tool_call_id": "b", "content": '{"result":3}' if tools[1] == "add" else '{"currentSpeed":20}'},
                {"role": "assistant", "content": "Done"},
            ]
            base = inference_graph(build_evidence_graph(history, history, episodic_only=True))
            graph = build_observed_graph(base)
            self.assertFalse(edges(graph, "next_visible_observation"))
            self.assertFalse(edges(graph, "equal_number_prior"))
            self.assertTrue(audit_observed_graph(graph)["ok"])

    def test_partial_error_fields_remain_reports_with_qualifier_support(self):
        graph = build_observed_graph(fixture([
            ("adjustClimateControl", {"temperature": 20}, {"currentTemperature": 19, "error": "partial effect", "success": False}),
            ("adjustClimateControl", {"temperature": 21}, {"error": "failed"}),
        ]))
        obs = nodes(graph, "observation")
        self.assertEqual(len(obs), 1)
        self.assertEqual({s["pointer"] for s in obs[0]["supports"]}, {"/error", "/success"})
        self.assertEqual(resolve_source(graph, obs[0]["source"]), 19)
        plan = plan_field_projection(graph, removed_sources=[obs[0]["supports"][0]])
        self.assertIn(obs[0]["id"], plan["required_removed_node_ids"])

    def test_malformed_unit_and_duplicate_result_keys_stay_unasserted(self):
        graph = build_observed_graph(fixture([
            ("adjustClimateControl", {"temperature": 20, "unit": ["celsius"]}, {"currentTemperature": 20}),
            ("adjustClimateControl", {"temperature": 21}, '{"currentTemperature":21,"currentTemperature":22}'),
        ]))
        self.assertEqual(nodes(graph, "request_port")[0]["unit"], "unknown")
        self.assertEqual(len(nodes(graph, "observation")), 1)
        self.assertTrue(audit_observed_graph(graph)["ok"])

    def test_native_json_and_text_block_locations_resolve(self):
        history = [
            {"role": "user", "content": "Keep native"},
            {"type": "function_call", "call_id": "x", "name": "add", "arguments": {"a": 1, "b": 2}},
            {"type": "function_call_output", "call_id": "x", "output": [{"type": "text", "text": '{"result":3}'}, {"type": "text", "text": "opaque"}]},
        ]
        graph = build_observed_graph(inference_graph(build_evidence_graph(history, episodic_only=True)))
        obs = nodes(graph, "observation")[0]
        self.assertEqual(obs["source"]["document_pointer"], "/0/text")
        self.assertEqual(resolve_source(graph, obs["source"]), 3)
        self.assertTrue(audit_observed_graph(graph)["ok"])

    def test_audit_rejects_tampered_pointers_edges_payload_and_duplicate_ids(self):
        graph = build_observed_graph(climate())
        bads = []
        bad = deepcopy(graph); nodes(bad, "observation")[0]["source"]["pointer"] = "/missing"; bads.append(bad)
        bad = deepcopy(graph); nodes(bad, "observation")[0]["call"] = "missing"; bads.append(bad)
        bad = deepcopy(graph); bad["observed_layer"]["nodes"].append(deepcopy(nodes(bad)[0])); bads.append(bad)
        bad = deepcopy(graph); edges(bad)[0]["to"] = ["missing"]; bads.append(bad)
        bad = deepcopy(graph); bad["observed_layer"]["edges"].append(deepcopy(edges(bad)[0])); bads.append(bad)
        bad = deepcopy(graph); bad["observed_layer"]["edges"] = []; bads.append(bad)
        bad = deepcopy(graph); bad["evidence_view"]["nodes"][1]["fields"][0]["value"] = "changed"; bads.append(bad)
        bad = deepcopy(graph); bad["observed_layer"]["public_doc_sha256"]["math_api"] = "bad"; bads.append(bad)
        bad = deepcopy(graph); bad["source_messages"] = []; bads.append(bad)
        for bad in bads:
            self.assertFalse(audit_observed_graph(bad)["ok"])
            with self.assertRaises(ValueError):
                render_observed_graph(bad)
        for bad in (None, {}, {"observed_layer": []}, {**graph, "observed_layer": {"nodes": "bad", "edges": []}}):
            self.assertFalse(audit_observed_graph(bad)["ok"])

    def test_actual_field_projection_removes_version_edges_and_rebinds_siblings(self):
        graph = build_observed_graph(climate())
        original = deepcopy(graph)
        target = [n for n in nodes(graph, "observation") if n["tool"] == "adjustClimateControl" and n["property"] == "climate.setpoint"][0]
        plan = plan_field_projection(graph, removed_sources=[target["source"]])
        self.assertEqual(plan["payload_operations"][0]["operation"], "remove_payload_subtree")
        self.assertEqual(plan["payload_operations"][0]["source"]["pointer"], "/currentTemperature")
        self.assertIn(target["id"], plan["required_removed_node_ids"])
        sibling = [n for n in nodes(graph, "observation") if n["tool"] == "adjustClimateControl" and n["property"] == "climate.mode"][0]
        self.assertIn(sibling["id"], plan["supported_surviving_node_ids"])
        self.assertIn(sibling["id"], plan["rebind_node_ids"])
        self.assertTrue(audit_projection_plan(graph, plan)["ok"])
        self.assertFalse(plan["applied"])
        self.assertFalse(plan["order_edges_reconnected"])
        self.assertFalse(plan["task_preservation_certified"])
        self.assertEqual(graph, original)
        bad = deepcopy(plan); bad["supported_surviving_node_ids"].append(target["id"])
        self.assertFalse(audit_projection_plan(graph, bad)["ok"])
        bad = deepcopy(plan); bad["payload_operations"] = []
        self.assertFalse(audit_projection_plan(graph, bad)["ok"])

    def test_projection_selector_and_units_close_dependent_annotations(self):
        graph = build_observed_graph(climate())
        observation = nodes(graph, "observation")[0]
        selector = next(s for s in observation["supports"] if s["pointer"] == "/option")
        plan = plan_field_projection(graph, removed_sources=[selector])
        first_call = observation["call"]
        self.assertTrue(all(n["id"] in plan["required_removed_node_ids"] for n in nodes(graph, "observation") if n["call"] == first_call))
        req = next(n for n in nodes(graph, "request_port") if n["property"] == "climate.setpoint")
        unit_plan = plan_field_projection(graph, removed_sources=req["supports"])
        self.assertIn(req["id"], unit_plan["required_removed_node_ids"])
        self.assertFalse(any(n["id"] in unit_plan["required_removed_node_ids"] for n in nodes(graph, "observation")))

    def test_projection_math_inputs_and_array_members_remove_complete_input_claim(self):
        graph = build_observed_graph(fixture([
            ("mean", {"numbers": [1, 2, 3]}, {"result": 2}),
            ("square_root", {"number": 4, "precision": 20}, {"result": 2}),
        ]))
        port = nodes(graph, "request_port")[0]
        source = {**port["source"], "pointer": "/numbers/1"}
        plan = plan_field_projection(graph, removed_sources=[source])
        self.assertIn(port["id"], plan["required_removed_node_ids"])
        first_input_edge = edges(graph, "declared_inputs")[0]
        self.assertIn(first_input_edge["id"], plan["required_removed_edge_ids"])
        self.assertIn(nodes(graph, "observation")[0]["id"], plan["supported_surviving_node_ids"])
        precision = next(n for n in nodes(graph, "request_port") if n["source"]["pointer"] == "/precision")
        precision_plan = plan_field_projection(graph, removed_sources=[precision["source"]])
        self.assertIn(edges(graph, "declared_inputs")[1]["id"], precision_plan["required_removed_edge_ids"])

    def test_projection_rejects_nonexistent_and_stale_sources(self):
        graph = build_observed_graph(climate())
        source = nodes(graph, "observation")[0]["source"]
        for bad in ({**source, "pointer": "/missing"}, {**source, "field_sha256": "bad"},
                    {**source, "event_id": "missing"}, {**source, "index_only": True}):
            with self.assertRaises((ValueError, KeyError)):
                plan_field_projection(graph, removed_sources=[bad])
        with self.assertRaises(ValueError):
            plan_field_projection(graph, removed_sources=[])


if __name__ == "__main__":
    unittest.main()
