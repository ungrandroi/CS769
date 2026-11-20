import json
import unittest
from copy import deepcopy
from test_relation_pruning import graph
from cs769.tasks.memory import prepare
from cs769.base.config import ExperimentConfig
from cs769.cli import counter
from cs769.models.edits import derived_evidence as de
from cs769.models.edits import relation_pruning as rp

BODY = "\n".join("Unique record " + str(i) for i in range(120))
CITIES = ["Unvisited City " + str(i) for i in range(120)]


class DerivedEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.count = counter("o200k_base")

    def file_calls(self, tool="cat", mode="c"):
        key = "file_content" if tool == "cat" else "sorted_content"
        counts = {"c": len(BODY), "l": len(BODY.splitlines()), "w": len(BODY.split())}
        units = {"c": "characters", "l": "lines", "w": "words"}
        return [(tool, {"file_name": "a.txt"}, {key: BODY}),
                ("wc", {"file_name": "a.txt", "mode": mode}, {"count": counts[mode], "type": units[mode]})]

    def distance_calls(self):
        return [("estimate_distance", {"cityA": "A", "cityB": "B"}, {"distance": 780.0, "intermediaryCities": deepcopy(CITIES)}),
                ("estimate_drive_feasibility_by_mileage", {"distance": 780.0}, {"canDrive": False})]

    def choices(self, calls, query="Compute from the retained count.", kind="auto"):
        return de.candidates(graph(calls), query, kind)[0]

    def test_file_removes_only_full_read_and_keeps_statistic(self):
        source = graph(self.file_calls()); before = deepcopy(source)
        edited, audit = de.prune(source, self.count, "Compute the logarithm of the character count.")
        nodes, calls = rp.records(de.evidence(edited))
        self.assertEqual(source, before)
        self.assertEqual([c["tool"] for c in calls], ["wc"])
        self.assertEqual(calls[0]["value"], self.file_calls()[1][2])
        self.assertEqual(len(audit["removed_event_ids"]), 2)
        self.assertTrue(audit["retained_evidence_exact"])
        self.assertFalse(audit["full_original_evidence_preserved"])
        self.assertFalse(audit["causal_dependency_proven"])
        self.assertGreater(audit["saved_tokens"], 50)
        self.assertIn("retained count", de.render(edited))
        self.assertNotIn(BODY, de.render(edited))

    def test_wrong_file_or_count_or_unit_or_boolean_rejected(self):
        for change in ["file", "count", "unit", "boolean", "error"]:
            calls = self.file_calls()
            if change == "file": calls[1][1]["file_name"] = "b.txt"
            if change == "count": calls[1][2]["count"] += 1
            if change == "unit": calls[1][2]["type"] = "words"
            if change == "boolean": calls[1][2]["count"] = True
            if change == "error": calls[1] = ("wc", calls[1][1], {"error": "cannot read"})
            self.assertFalse(self.choices(calls), change)

    def test_sort_lines_allowed_but_character_count_not_inferred(self):
        self.assertTrue(self.choices(self.file_calls("sort", "l")))
        self.assertTrue(self.choices(self.file_calls("sort", "w")))
        self.assertFalse(self.choices(self.file_calls("sort", "c")))

    def test_directory_mutation_and_unknown_call_block_same_version(self):
        for operation in [("cd", {"folder": "other"}, {"error": "failed"}),
                          ("echo", {"file_name": "a.txt", "content": "new"}, None),
                          ("mv", {"source": "a", "destination": "b"}, None),
                          ("opaque_operation", {}, {})]:
            calls = self.file_calls()
            calls.insert(1, operation)
            self.assertFalse(self.choices(calls), operation[0])

    def test_nested_retained_arguments_are_checked_for_duplicate_body(self):
        calls = [("echo", {"file_name": "a.txt", "content": BODY}, None)] + self.file_calls()
        self.assertFalse(self.choices(calls))

    def test_full_text_and_comparison_requests_block_file_pruning(self):
        g = graph(self.file_calls())
        for query in ["Show the full file.", "Quote original content.", "Compare the previous version.", "Display its lines."]:
            self.assertFalse(de.candidates(g, query, "file_count")[0], query)

    def test_parallel_same_file_reads_work_without_a_causal_claim(self):
        h = [{"role": "user", "content": "Read and count."},
             {"type": "function_call", "call_id": "a", "name": "cat", "arguments": '{"file_name":"a.txt"}'},
             {"type": "function_call", "call_id": "b", "name": "wc", "arguments": '{"file_name":"a.txt","mode":"c"}'},
             {"type": "function_call_output", "call_id": "a", "output": json.dumps({"file_content": BODY})},
             {"type": "function_call_output", "call_id": "b", "output": json.dumps({"count": len(BODY), "type": "characters"})}]
        native = [h[0], {"role": "assistant", "content": None, "tool_calls": [
            {"id": m["call_id"], "type": "function", "function": {"name": m["name"], "arguments": m["arguments"]}}
            for m in h if m.get("type") == "function_call"]}]
        native.extend({"role": "tool", "tool_call_id": m["call_id"], "content": m["output"]}
                      for m in h if m.get("type") == "function_call_output")
        g = prepare(h, ExperimentConfig(), self.count, native_history=native)["graph"]
        out, audit = de.prune(g, self.count, "Compute the log of the count.")
        self.assertTrue(audit["action"]["observational_relation_not_causal_order"])
        self.assertEqual([c["tool"] for c in rp.records(de.evidence(out))[1]], ["wc"])

    def test_parallel_write_cannot_be_hidden_between_read_results(self):
        h = [{"role": "user", "content": "Read and count."},
             {"type": "function_call", "call_id": "a", "name": "cat", "arguments": '{"file_name":"a.txt"}'},
             {"type": "function_call", "call_id": "x", "name": "echo", "arguments": '{"file_name":"a.txt","content":"changed"}'},
             {"type": "function_call", "call_id": "b", "name": "wc", "arguments": '{"file_name":"a.txt","mode":"c"}'},
             {"type": "function_call_output", "call_id": "a", "output": json.dumps({"file_content": BODY})},
             {"type": "function_call_output", "call_id": "b", "output": json.dumps({"count": len(BODY), "type": "characters"})},
             {"type": "function_call_output", "call_id": "x", "output": "null"}]
        native = [h[0], {"role": "assistant", "content": None, "tool_calls": [
            {"id": m["call_id"], "type": "function", "function": {"name": m["name"], "arguments": m["arguments"]}}
            for m in h if m.get("type") == "function_call"]}]
        native.extend({"role": "tool", "tool_call_id": m["call_id"], "content": m["output"]}
                      for m in h if m.get("type") == "function_call_output")
        g = prepare(h, ExperimentConfig(), self.count, native_history=native)["graph"]
        self.assertFalse(de.candidates(g, "Compute the log.", "file_count")[0])

    def test_distance_keeps_operands_and_false_receipt(self):
        source = graph(self.distance_calls()); before = deepcopy(source)
        out, audit = de.prune(source, self.count, "If it cannot, fill the tank.")
        old_calls = rp.records(de.evidence(source))[1]; new_calls = rp.records(de.evidence(out))[1]
        self.assertEqual(source, before)
        self.assertEqual([c["args"] for c in old_calls], [c["args"] for c in new_calls])
        self.assertEqual(new_calls[0]["value"], {"distance": 780.0})
        self.assertEqual(new_calls[1]["value"], {"canDrive": False})
        self.assertFalse(audit["action"]["unit_conversion_certified"])
        self.assertGreater(audit["saved_tokens"], 50)

    def test_distance_requires_unique_successful_prior_numeric_flow(self):
        variants = []
        calls = self.distance_calls(); calls[1][1]["distance"] = 779; variants.append(calls)
        calls = self.distance_calls(); calls[1] = (calls[1][0], calls[1][1], {"error": "not available"}); variants.append(calls)
        calls = self.distance_calls(); calls[1][2]["canDrive"] = 0; variants.append(calls)
        calls = self.distance_calls(); calls.insert(1, deepcopy(calls[0])); variants.append(calls)
        calls = self.distance_calls(); calls[0][2]["distance"] = True; calls[1][1]["distance"] = 1; variants.append(calls)
        variants.append(list(reversed(self.distance_calls())))
        for calls in variants:
            self.assertFalse(self.choices(calls, "Proceed.", "distance_feasibility"))

    def test_current_route_or_deleted_city_or_later_reference_protected(self):
        for query in ["List the intermediate cities.", "Follow the route via Unvisited City 12."]:
            self.assertFalse(self.choices(self.distance_calls(), query, "distance_feasibility"))
        calls = self.distance_calls() + [("set_navigation", {"destination": CITIES[5]}, {"status": "ok"})]
        self.assertFalse(self.choices(calls, "Proceed.", "distance_feasibility"))

    def test_nested_identifier_prevents_city_projection(self):
        calls = self.distance_calls()
        calls[0][2]["intermediaryCities"].append({"city_id": "unique-id"})
        self.assertFalse(self.choices(calls, "Proceed.", "distance_feasibility"))

    def test_stale_action_minimum_and_invalid_options(self):
        g = graph(self.file_calls())
        action = de.candidates(g, "Compute.", "file_count")[0][0]
        other = graph(self.file_calls() + [("pwd", {}, {"current_working_directory": "/x"})])
        with self.assertRaisesRegex(ValueError, "Stale"): de.apply(other, action, self.count)
        with self.assertRaisesRegex(ValueError, "No eligible"): de.prune(g, self.count, "Compute.", min_saved_tokens=100000)
        with self.assertRaises(ValueError): de.prune(g, self.count, "Compute.", min_saved_tokens=True)
        with self.assertRaises(ValueError): de.candidates(g, "Compute.", "unknown")

    def test_registered_editor_is_optional_and_does_not_attach_identity(self):
        calls = self.file_calls();h = [{"role": "user", "content": "Count the document."}]
        for i, (tool, args, value) in enumerate(calls):
            h.extend([{"type": "function_call", "call_id": str(i), "name": tool, "arguments": json.dumps(args)},
                      {"type": "function_call_output", "call_id": str(i), "output": json.dumps(value)}])
        cfg = ExperimentConfig(); cfg.delivery = {"mode": "replace", "role": "assistant"}
        base = prepare(h, cfg, self.count)
        cfg.edits = [{"name": "prune_derived_evidence", "options": {"kind": "file_count"}}]
        edited = prepare(h, cfg, self.count, next_messages=[{"role": "user", "content": "Compute from the count."}])
        self.assertEqual(len(edited["messages"]), 2)
        self.assertNotIn(BODY, edited["memory_text"])
        self.assertEqual(edited["edits"][0]["status"], "applied")
        cfg.edits[0]["enabled"] = False
        self.assertEqual(prepare(h, cfg, self.count)["messages"], base["messages"])


if __name__ == "__main__":
    unittest.main()
