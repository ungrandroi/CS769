"""Replacement boundary, evidence completeness, and protocol isolation tests."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest

from core.graph_memory_replace import (DELIVERY, GraphMemoryReplacement, GraphMemoryV2Replacement,
                                  assert_replacement_request)
from test_state_transition_graph import history

CLASSES = (GraphMemoryReplacement, GraphMemoryV2Replacement)


class ReplacementMemoryTest(unittest.TestCase):
    def test_protocols_replace_history_and_preserve_instructions(self):
        for cls in CLASSES:
            for chat in (False, True):
                with self.subTest(cls=cls.__name__, chat=chat):
                    instructions = [{"role": "system", "content": "Keep this system instruction."},
                                    {"role": "developer", "content": "Keep this developer instruction."}]
                    source = instructions + history([("pwd", {}, {"current_working_directory": "/document"})], chat)
                    source += [{"role": "assistant", "content": "I have finished."}]
                    before = deepcopy(source)
                    memory = cls(); result = memory.compress(source)
                    self.assertEqual(source, before)
                    self.assertEqual(len(result), 3)
                    self.assertTrue(all(a is b for a, b in zip(instructions, result)))
                    self.assertEqual(result[-1]["role"], "assistant")
                    self.assertEqual(memory.graph["delivery"], DELIVERY)
                    self.assertEqual(memory.graph["source_messages"], source)
                    payload = json.loads(result[-1]["content"].split("\n")[-1])
                    self.assertNotIn("source_messages", payload)
                    self.assertEqual(payload["requests"][0]["content"], source[2]["content"])
                    self.assertEqual(payload["assistant_statements"][0]["content"], "I have finished.")
                    self.assertFalse(payload["assistant_statements"][0]["verified_state"])
                    key = "messages" if chat else "input"
                    request = {key: result + [{"role": "user", "content": "Now continue."}]}
                    assert_replacement_request(request, result, source)
                    request[key] += source[3:5]
                    with self.assertRaisesRegex(AssertionError, "Old tool protocol"):
                        assert_replacement_request(request, result, source)

    def test_tool_results_are_self_contained_including_unknown_tools_and_errors(self):
        steps = [("cat", {"file_name": "report.pdf"}, {"file_content": "EVIDENCE_SENTINEL"}),
                 ("grep", {"file_name": "absent", "pattern": "x"}, {"error": "FAILURE_SENTINEL"}),
                 ("unmodeled_tool", {}, {"nested": ["OPAQUE_RESULT_SENTINEL"]})]
        for cls in CLASSES:
            memory = cls(); memory.compress(history(steps))
            payload = json.loads(memory.render().split("\n")[-1])
            events = payload["edges"] if payload["schema_version"] == 1 else [
                n for n in payload["nodes"] if n["category"] == "event"]
            self.assertEqual([json.loads(e["output_raw"]) for e in events], [s[2] for s in steps])
            for event in events:
                for field, kind in (("call_evidence", "tool_input"), ("output_evidence", "tool_return")):
                    self.assertIn({"kind": kind, "target": event["id"]}, payload["evidence_index"][event[field]])
            self.assertEqual(events[1]["status"], "error")

    def test_drops_opaque_reasoning_and_api_metadata(self):
        from openai.types.responses import ResponseReasoningItem
        for cls in CLASSES:
            source = history([]) + [ResponseReasoningItem.model_validate({
                "id": "OLD_RESPONSE_ITEM_SENTINEL", "type": "reasoning", "summary": [],
                "encrypted_content": "ENCRYPTED_SENTINEL"})]
            memory = cls(); result = memory.compress(source)
            self.assertNotIn("ENCRYPTED_SENTINEL", json.dumps(result))
            self.assertNotIn("OLD_RESPONSE_ITEM_SENTINEL", json.dumps(result))
            self.assertIn("ENCRYPTED_SENTINEL", json.dumps(memory.graph))
            for key in ("previous_response_id", "conversation"):
                with self.assertRaisesRegex(AssertionError, "Server-side history"):
                    assert_replacement_request({"input": result + [{"role": "user", "content": "Continue"}],
                                                key: "old_id"}, result, source)

    def test_pending_and_orphaned_results_rejected(self):
        complete = history([("mkdir", {"dir_name": "x"}, None)])
        for cls in CLASSES:
            with self.assertRaises(ValueError):
                cls().compress(complete[:-1])
            with self.assertRaises(ValueError):
                cls().compress(complete[-1:])



if __name__ == "__main__":
    unittest.main()
