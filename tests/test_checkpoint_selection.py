"""Configured checkpoint selection without legacy task scanners."""
import unittest
from cs769.base.history import checkpoint_reached, history_counter_text

class CheckpointSelectionTests(unittest.TestCase):
    def source(self):
        return [{"type": "function_call", "call_id": "a", "name": "cat", "arguments": "{}"},
                {"type": "function_call_output", "call_id": "a", "output": "x" * 1000}]

    def test_balanced_final_request_can_trigger(self):
        cfg = {"kind": "history_tokens", "counter": "history_json_sorted", "threshold": 1000, "strict": True}
        self.assertTrue(checkpoint_reached(self.source(), cfg, len))

    def test_tool_payload_mode_does_not_count_user_or_tool_definitions(self):
        cfg = {"kind": "history_tokens", "counter": "tool_payload", "threshold": 1000, "strict": True}
        request = {"input": [{"role": "user", "content": "x" * 5000}], "tools": ["y" * 5000]}
        self.assertFalse(checkpoint_reached(request["input"], cfg, len))

    def test_unpaired_call_never_triggers(self):
        cfg = {"kind": "history_tokens", "counter": "history_json_sorted", "threshold": 0, "strict": True}
        self.assertFalse(checkpoint_reached(self.source()[:1], cfg, len))

    def test_strict_and_inclusive_boundaries_are_explicit(self):
        source = self.source()
        units = len(history_counter_text(source, sort_keys=True))
        cfg = {"kind": "history_tokens", "counter": "history_json_sorted", "threshold": units, "strict": True}
        self.assertFalse(checkpoint_reached(source, cfg, len))
        cfg["strict"] = False
        self.assertTrue(checkpoint_reached(source, cfg, len))

    def test_instructions_are_outside_history_counter(self):
        source = self.source()
        self.assertEqual(history_counter_text(source, sort_keys=True),
                         history_counter_text([{"role": "system", "content": "x" * 5000}] + source, sort_keys=True))
