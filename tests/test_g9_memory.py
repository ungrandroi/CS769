"""Public entry-point integrity checks, with no model or benchmark execution."""
from copy import deepcopy
import json
import unittest

from core.g9_memory import build_g9_memory
from core.graph_memory_evidence import audit_evidence_graph, render_evidence_graph
from core.graph_memory_observed import strip_observed_graph
from core.graph_memory_payload import restore_observed_graph
from core.graph_memory_records import strip_record_graph
from core.graph_memory_record_views import render_record_view_graph


def history():
    return [
        {"role": "user", "content": "Check order 7. 完整保留\n"},
        {"role": "assistant", "content": "Checking.", "tool_calls": [
            {"id": "c1", "type": "function", "function": {
                "name": "get_order_details", "arguments": '{ "order_id":7 }',
            }},
        ]},
        {"role": "tool", "tool_call_id": "c1",
         "content": '{ "id":7, "status":"Completed", "note":"⟦f1⟧" }'},
        {"role": "assistant", "content": "Order 7 is completed."},
    ]


def restored_evidence(graph):
    return strip_observed_graph(restore_observed_graph(strip_record_graph(graph)))


class G9MemoryTests(unittest.TestCase):
    def test_full_evidence_survives_without_identity_archive(self):
        source = history()
        original = deepcopy(source)
        output = build_g9_memory(source, source)
        graph = output["graph"]
        self.assertEqual(source, original)
        self.assertEqual(output, build_g9_memory(source, source))
        evidence = restored_evidence(graph)
        self.assertTrue(audit_evidence_graph(evidence, source, source)["integrity_ok"])
        self.assertTrue(output["audits"]["record"]["active"])
        base = render_evidence_graph(evidence)
        self.assertTrue(output["memory_text"].startswith(base))
        self.assertGreater(len(output["memory_text"]), len(base))
        self.assertEqual(set(graph), {"delivery", "evidence_view", "evidence_audit",
                                     "observed_layer", "payload_layer", "record_layer"})
        restored = json.loads(json.dumps(graph, ensure_ascii=False))
        self.assertEqual(render_record_view_graph(
            restored, view="full", visible_observations=False), output["memory_text"])

    def test_unknown_tool_keeps_payload_without_guessing_id_links(self):
        source = history()
        source[1]["tool_calls"][0]["function"]["name"] = "appworld_unknown_tool"
        output = build_g9_memory(source, source)
        self.assertFalse(output["audits"]["record"]["active"])
        self.assertEqual(output["memory_text"],
                         render_evidence_graph(restored_evidence(output["graph"])))
        self.assertTrue(audit_evidence_graph(restored_evidence(output["graph"]), source, source)["integrity_ok"])

    def test_anthropic_visible_evidence_and_error_flag(self):
        normalized = history()
        native = [
            normalized[0],
            {"role": "assistant", "content": [
                {"type": "text", "text": "Checking."},
                {"type": "tool_use", "id": "c1", "name": "get_order_details",
                 "input": {"order_id": 7}},
            ]},
            {"role": "user", "content": [{"type": "tool_result",
                "tool_use_id": "c1", "content": normalized[2]["content"], "is_error": False}]},
            {"role": "assistant", "content": [{"type": "text", "text": normalized[3]["content"]}]},
        ]
        output = build_g9_memory(normalized, native, provider="anthropic")
        self.assertTrue(audit_evidence_graph(restored_evidence(output["graph"]), normalized, native)["integrity_ok"])
        result = next(n for n in output["graph"]["evidence_view"]["nodes"]
                      if n["category"] == "tool_result")
        self.assertIs(result["native_is_error"], False)

    def test_missing_or_mismatched_native_evidence_is_rejected(self):
        normalized = history()
        with self.assertRaises(ValueError):
            build_g9_memory(normalized, None)
        changed = deepcopy(normalized)
        changed[2]["content"] = '{"id":8}'
        with self.assertRaises(ValueError):
            build_g9_memory(normalized, changed)

    def test_pending_tool_result_is_rejected(self):
        pending = history()[:2]
        with self.assertRaises(ValueError):
            build_g9_memory(pending, pending)


if __name__ == "__main__":
    unittest.main()
