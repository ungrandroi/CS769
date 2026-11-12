"""Native replay integrity, protocol pairing, and graph-index provenance."""
from copy import deepcopy
import json
import unittest

from cs769.graphs.graph_memory_native import (
    append_native_index, build_native_graph, reconstruct_native_context,
    reconstruct_native_history, reconstruct_normalized_history,
    render_native_index, validate_native_history,
)
from cs769.adapters.qwen_transport import chat_messages


def normalized(tool="cat", arguments=None, output=None, identity="c1"):
    return [
        {"role": "system", "content": "System sentinel"},
        {"role": "user", "content": "Read it."},
        {"type": "function_call", "call_id": identity, "name": tool,
         "arguments": json.dumps(arguments if arguments is not None else {"file_name": "a"})},
        {"type": "function_call_output", "call_id": identity,
         "output": json.dumps(output if output is not None else {"file_content": "first\nsecond\n路径"})},
        {"role": "assistant", "content": "Done."},
    ]


def anthropic(source, identity="c1"):
    call, result = source[2], source[3]
    return [
        {"role": "user", "content": "Read it."},
        {"role": "assistant", "content": [
            {"type": "thinking", "thinking": "OPAQUE_THINKING", "signature": "KEEP_SIGNATURE"},
            {"type": "text", "text": "Checking."},
            {"type": "tool_use", "id": identity, "name": call["name"], "input": json.loads(call["arguments"])},
        ]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": identity,
                                          "content": result["output"]}]},
        {"role": "assistant", "content": [
            {"type": "redacted_thinking", "data": "OPAQUE_REDACTED"},
            {"type": "text", "text": "Done."},
        ]},
    ]


class NativeGraphTests(unittest.TestCase):
    def test_openai_roundtrip_and_append_preserve_entire_native_prefix(self):
        source = normalized()
        native = chat_messages(source)
        graph = build_native_graph(source, native, provider="openai", native_context={"tools": [{"name": "cat"}]})
        self.assertEqual(reconstruct_native_history(graph), native)
        self.assertEqual(reconstruct_normalized_history(graph), source)
        candidate = append_native_index(graph)
        self.assertEqual(candidate[:-1], native)
        self.assertEqual(candidate[-1]["role"], "assistant")
        self.assertIn("snapshot at end of first user turn", candidate[-1]["content"])
        self.assertIn("content@CALL c1/RESULT c1", candidate[-1]["content"])
        self.assertNotIn("first\nsecond", candidate[-1]["content"])
        self.assertNotIn("unknown", candidate[-1]["content"])

    def test_anthropic_all_blocks_types_order_and_context_are_lossless(self):
        source = normalized()
        native = anthropic(source)
        context = {"system": [{"type": "text", "text": "System sentinel"}],
                   "tools": [{"name": "cat", "input_schema": {"type": "object"}}]}
        before = deepcopy(native)
        graph = build_native_graph(source, native, provider="anthropic", native_context=context)
        self.assertEqual(reconstruct_native_history(graph), before)
        self.assertEqual(reconstruct_native_context(graph), context)
        self.assertEqual(append_native_index(graph)[:len(before)], before)
        self.assertNotIn("OPAQUE", render_native_index(graph))
        native[1]["content"][0]["signature"] = "mutated caller"
        context["system"][0]["text"] = "mutated caller"
        restored = reconstruct_native_history(graph)
        restored[1]["content"][0]["signature"] = "mutated return"
        self.assertEqual(reconstruct_native_history(graph), before)

    def test_native_call_id_mapping_points_content_to_real_tool_evidence(self):
        source = normalized(identity="normalized_0")
        native = anthropic(source, identity="toolu_native_123")
        graph = build_native_graph(source, native, provider="anthropic",
                                   call_id_map={"normalized_0": "toolu_native_123"})
        self.assertIn("CALL toolu_native_123/RESULT toolu_native_123", render_native_index(graph))
        self.assertNotIn("normalized_0", render_native_index(graph))

    def test_empty_index_emits_no_extra_message_or_behavior_prompt(self):
        source = normalized(tool="find", arguments={"name": "a"}, output={"matches": ["a", "b"]})
        native = chat_messages(source)
        graph = build_native_graph(source, native, provider="openai")
        self.assertEqual(render_native_index(graph), "")
        self.assertEqual(append_native_index(graph), native)
        self.assertFalse(graph["native_audit"]["index_nonempty"])

    def test_error_return_is_preserved_and_not_promoted_to_known_state(self):
        source = normalized(output={"error": "File not found\nERROR_SENTINEL"})
        native = anthropic(source)
        native[2]["content"][0]["is_error"] = True
        graph = build_native_graph(source, native, provider="anthropic")
        self.assertEqual(reconstruct_native_history(graph), native)
        self.assertEqual(render_native_index(graph), "")

    def test_multiple_tool_results_are_complete_immediate_and_before_text(self):
        messages = [
            {"role": "user", "content": "Get both"},
            {"role": "assistant", "content": [
                {"type": "tool_use", "id": "x", "name": "pwd", "input": {}},
                {"type": "tool_use", "id": "y", "name": "ls", "input": {}}]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "y", "content": "second"},
                {"type": "tool_result", "tool_use_id": "x", "content": "first"},
                {"type": "text", "text": "More context"}]},
            {"role": "assistant", "content": "Done"},
        ]
        calls, results = validate_native_history(messages, "anthropic")
        self.assertEqual(set(calls), {"x", "y"})
        self.assertEqual(results, {"x": "first", "y": "second"})
        missing = deepcopy(messages)
        missing[2]["content"].pop(0)
        with self.assertRaisesRegex(ValueError, "immediately"):
            validate_native_history(missing, "anthropic")
        late = deepcopy(messages)
        late[2]["content"] = list(reversed(late[2]["content"]))
        with self.assertRaisesRegex(ValueError, "precede"):
            validate_native_history(late, "anthropic")

    def test_incomplete_or_interrupted_openai_tool_turn_rejected(self):
        native = chat_messages(normalized())
        with self.assertRaisesRegex(ValueError, "immediately"):
            validate_native_history(native[:2] + native[2:3] + native[4:], "openai")
        with self.assertRaisesRegex(ValueError, "completed assistant"):
            validate_native_history(native[:-1], "openai")
        with self.assertRaisesRegex(ValueError, "pending"):
            validate_native_history(native[:3], "openai")

    def test_normalized_evidence_mismatch_and_non_bijective_map_rejected(self):
        source = normalized()
        native = anthropic(source)
        native[1]["content"][2]["input"] = {"file_name": "other"}
        with self.assertRaisesRegex(ValueError, "call contents"):
            build_native_graph(source, native, provider="anthropic")
        native = anthropic(source)
        native[2]["content"][0]["content"] = "altered result"
        with self.assertRaisesRegex(ValueError, "results differ"):
            build_native_graph(source, native, provider="anthropic")
        with self.assertRaisesRegex(ValueError, "coverage"):
            build_native_graph(source, anthropic(source), provider="anthropic", call_id_map={"c1": "other"})

    def test_tampering_fails_integrity_and_index_is_pure(self):
        source = normalized()
        graph = build_native_graph(source, chat_messages(source), provider="openai")
        before = deepcopy(graph)
        render_native_index(graph)
        append_native_index(graph)
        self.assertEqual(graph, before)
        graph["native_evidence"]["messages"][-1]["content"] = "altered"
        with self.assertRaisesRegex(ValueError, "integrity"):
            reconstruct_native_history(graph)
        graph = deepcopy(before)
        graph["source_messages"][-1]["content"] = "altered"
        with self.assertRaisesRegex(ValueError, "integrity"):
            reconstruct_normalized_history(graph)

    def test_long_listing_references_native_result_without_numbering_alias(self):
        source = normalized(tool="ls", arguments={},
                            output={"current_directory_content": [f"file_{i}.txt" for i in range(100)]})
        graph = build_native_graph(source, chat_messages(source), provider="openai")
        index = render_native_index(graph)
        self.assertIn("RESULT c1.current_directory_content", index)
        self.assertNotIn("RESULT 1", index)

    def test_archived_complete_tool_checkpoint_restores_without_synthetic_message(self):
        source = normalized()[:-1]
        native = chat_messages(source)
        with self.assertRaisesRegex(ValueError, "completed assistant"):
            build_native_graph(source, native, provider="openai")
        graph = build_native_graph(source, native, provider="openai",
                                   snapshot_boundary="archived_history_checkpoint")
        self.assertEqual(reconstruct_native_history(graph), native)
        self.assertEqual(reconstruct_normalized_history(graph), source)
        self.assertEqual(reconstruct_native_history(graph)[-1]["role"], "tool")
        self.assertIn("snapshot at archived history checkpoint", render_native_index(graph))
        self.assertNotIn("first user turn", render_native_index(graph))
        with self.assertRaisesRegex(ValueError, "offline only"):
            append_native_index(graph)

    def test_archived_anthropic_result_boundary_still_requires_all_results(self):
        source = normalized()
        native = anthropic(source)[:-1]
        graph = build_native_graph(source[:-1], native, provider="anthropic",
                                   snapshot_boundary="archived_history_checkpoint")
        self.assertEqual(reconstruct_native_history(graph), native)
        with self.assertRaisesRegex(ValueError, "pending"):
            build_native_graph(source[:-2], native[:-1], provider="anthropic",
                               snapshot_boundary="archived_history_checkpoint")
        with self.assertRaisesRegex(ValueError, "Unknown"):
            build_native_graph(source, anthropic(source), provider="anthropic",
                               snapshot_boundary="invented")


if __name__ == "__main__":
    unittest.main()
