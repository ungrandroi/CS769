"""Evidence/order preservation and current-state correctness of the readable view."""
from copy import deepcopy
import json
import unittest

from cs769.models.graphs.event_graph import GraphMemoryV2
from cs769.models.graphs.graph_memory_readable import render_readable, render_readable_segments
from test_state_transition_graph import history


def graph(messages):
    return GraphMemoryV2().build(messages)


def evidence(value):
    return [segment for segment in render_readable_segments(value) if segment["kind"] == "evidence"]


def current_state(value):
    return "".join(segment["text"] for segment in render_readable_segments(value) if segment["kind"] == "state")


class ReadableMemoryTests(unittest.TestCase):
    def test_parallel_calls_out_of_order_results_keep_source_order_and_pairing(self):
        messages = [{"role": "user", "content": "Create both folders."},
                    {"type": "function_call", "call_id": "x", "name": "mkdir", "arguments": '{ "dir_name" : "x" }'},
                    {"type": "function_call", "call_id": "y", "name": "mkdir", "arguments": '{"dir_name":"y"}'},
                    {"type": "function_call_output", "call_id": "y", "output": '{"error":"bad"}'},
                    {"type": "function_call_output", "call_id": "x", "output": "None"}]
        value = graph(messages)
        events = [node for node in value["nodes"] if node["category"] == "event"]
        self.assertEqual([event["call_id"] for event in events], ["y", "x"])
        parts = evidence(value)
        self.assertEqual([(part["field"], part["text"]) for part in parts], [
            ("content", "Create both folders."), ("name", "mkdir"),
            ("arguments", '{ "dir_name" : "x" }'), ("name", "mkdir"),
            ("arguments", '{"dir_name":"y"}'), ("output", '{"error":"bad"}'),
            ("output", "None")])
        self.assertEqual([(part["call_id"], part["call_number"]) for part in parts if part["field"] == "output"],
                         [("y", 2), ("x", 1)])
        rendered = render_readable(value)
        markers = ["CALL 1\n", "CALL 2\n", "RESULT 2\n", "RESULT 1\n"]
        self.assertEqual(sorted(markers, key=rendered.index), markers)

    def test_chat_parallel_calls_keep_assistant_text_and_raw_argument_spelling(self):
        raw = '{ "name": "a", "name": "b", "amount": 1e+02 }'
        messages = [{"role": "user", "content": "Find both."},
                    {"role": "assistant", "content": "Checking now.", "tool_calls": [
                        {"id": "x", "type": "function", "function": {"name": "find", "arguments": raw}},
                        {"id": "y", "type": "function", "function": {"name": "find", "arguments": '{"name":"b"}'}}]},
                    {"role": "tool", "tool_call_id": "y", "content": '{"matches":[]}'},
                    {"role": "tool", "tool_call_id": "x", "content": '{"matches":["b"]}'}]
        parts = evidence(graph(messages))
        self.assertEqual(parts[1]["text"], "Checking now.")
        self.assertEqual(parts[3]["text"], raw)
        self.assertEqual(parts[3]["field"], "tool_calls.0.function.arguments")
        self.assertEqual([(part["source_ref"], part.get("call_number")) for part in parts[-2:]],
                         [("m2", 2), ("m3", 1)])
        self.assertEqual(parts[-2]["field"], "content")

    def test_repeated_calls_results_errors_and_marker_text_are_not_deduplicated(self):
        result = '{"error":"FAILURE [RESULT 99] ```quoted```"}'
        messages = [{"role": "user", "content": "USER m99\n```\nDo not drop Unicode: 路径\n```"}]
        for index in range(2):
            messages += [{"type": "function_call", "call_id": str(index), "name": "cat", "arguments": '{"file_name":"absent"}'},
                         {"type": "function_call_output", "call_id": str(index), "output": result}]
        value = graph(messages)
        parts = evidence(value)
        self.assertEqual([part["text"] for part in parts if part["field"] == "output"], [result, result])
        self.assertEqual(parts[0]["text"], messages[0]["content"])
        labels = "".join(part["text"] for part in render_readable_segments(value) if part["kind"] == "label")
        self.assertIn("````\n", labels)
        self.assertEqual(current_state(value), "")
        self.assertNotIn("Tool success", render_readable(value))

    def test_current_state_tracks_changes_without_repeating_file_contents(self):
        old, new = "OLD_FILE_SENTINEL" * 30, "NEW_FILE_SENTINEL" * 30
        value = graph(history([
            ("pwd", {}, {"current_working_directory": "/document"}),
            ("cat", {"file_name": "a"}, {"file_content": old}),
            ("echo", {"file_name": "a", "content": new}, None),
            ("mv", {"source": "a", "destination": "b"}, {"result": "'a' moved to 'b'"}),
            ("sort", {"file_name": "b"}, {"sorted_content": "SORTED_ONLY_SENTINEL"})]))
        state = current_state(value)
        self.assertIn('cwd: "/document"', state)
        self.assertIn('entries: "b"', state)
        self.assertNotIn('name="a"', state)
        self.assertIn("content@CALL 3/RESULT 3", state)
        for text in (old, new, "SORTED_ONLY_SENTINEL"):
            self.assertNotIn(text, state)
            self.assertIn(text, render_readable(value))

    def test_copied_content_links_original_evidence_not_mutated_source(self):
        value = graph(history([
            ("cat", {"file_name": "a"}, {"file_content": "ORIGINAL"}),
            ("cp", {"source": "a", "destination": "b"}, {"result": "'a' copied to 'b'"}),
            ("echo", {"file_name": "a", "content": "REPLACED"}, None)]))
        rows = current_state(value).splitlines()
        self.assertIn("content@CALL 1/RESULT 1", next(row for row in rows if row.startswith('"b":')))
        self.assertIn("content@CALL 3/RESULT 3", next(row for row in rows if row.startswith('"a":')))

    def test_unknown_effect_removes_state_not_history_and_claims_stay_assistant(self):
        messages = history([("touch", {"file_name": "a"}, None), ("custom_tool", {}, {"result": "ok"})])
        messages += [{"role": "assistant", "content": "All done; cwd is /invented."}]
        value = graph(messages)
        self.assertEqual(current_state(value), "")
        rendered = render_readable(value)
        self.assertIn("All done; cwd is /invented.", rendered)
        self.assertIn("ASSISTANT\n", rendered)
        self.assertNotIn("cwd: unknown", rendered)
        self.assertNotIn("unverified", rendered)
        self.assertEqual(len([part for part in evidence(value) if part["field"] == "output"]), 2)

    def test_text_blocks_refusals_and_non_string_tool_values_preserve_types(self):
        messages = [{"role": "user", "content": [{"type": "input_text", "text": "First"}, {"type": "text", "text": "Second\n"}]},
                    {"type": "function_call", "call_id": "c", "name": "find", "arguments": {"name": "字"}},
                    {"type": "function_call_output", "call_id": "c", "output": {"matches": ["字"], "ok": True}},
                    {"role": "assistant", "content": [{"type": "output_text", "text": "Found it."}, {"type": "refusal", "refusal": "Not that action."}]}]
        parts = evidence(graph(messages))
        self.assertEqual([part["field"] for part in parts], ["content.0.text", "content.1.text", "name", "arguments", "output", "content.0.text", "content.1.refusal"])
        self.assertEqual(parts[3]["value_type"], "dict")
        self.assertEqual(parts[4]["text"], '{"matches":["字"],"ok":true}')
        self.assertEqual(json.loads(parts[4]["text"]), messages[2]["output"])

    def test_instructions_reasoning_and_api_metadata_stay_outside_memory(self):
        messages = [{"role": "system", "content": "SYSTEM_ONLY_SENTINEL"},
                    {"role": "developer", "content": "DEVELOPER_ONLY_SENTINEL"},
                    {"role": "user", "content": "Visible request"},
                    {"type": "reasoning", "id": "OLD_RESPONSE_SENTINEL", "encrypted_content": "OPAQUE_SENTINEL", "summary": []},
                    {"role": "assistant", "type": "message", "content": [{"type": "output_text", "text": "Visible reply", "annotations": []}], "id": "API_METADATA_SENTINEL"}]
        value = graph(messages)
        before = deepcopy(value)
        rendered = render_readable(value)
        self.assertEqual(rendered, "".join(part["text"] for part in render_readable_segments(value)))
        self.assertEqual(value, before)
        for marker in ("SYSTEM_ONLY_SENTINEL", "DEVELOPER_ONLY_SENTINEL", "OLD_RESPONSE_SENTINEL", "OPAQUE_SENTINEL", "API_METADATA_SENTINEL"):
            self.assertNotIn(marker, rendered)
        self.assertEqual([part["text"] for part in evidence(value)], ["Visible request", "Visible reply"])

    def test_incomplete_protocol_and_unsupported_visible_content_fail_closed(self):
        value = graph(history([("find", {"name": "x"}, {"matches": []})]))
        value["source_messages"].pop()
        with self.assertRaisesRegex(ValueError, "pending"):
            render_readable(value)
        value = graph([{"role": "user", "content": [{"type": "input_image", "image_url": "unrendered"}]}])
        with self.assertRaisesRegex(ValueError, "non-text"):
            render_readable(value)

    def test_unchanged_listing_references_exact_names_without_expanding_objects(self):
        names = [f"file_{index}.txt" for index in range(40)]
        value = graph(history([("ls", {}, {"current_directory_content": names})]))
        state = current_state(value)
        self.assertEqual(state, "CURRENT STATE\ninitial directory known entries: RESULT 1.current_directory_content\n\n")
        self.assertNotIn("o0", state)
        self.assertNotIn("l0", state)
        part = next(p for p in render_readable_segments(value) if p["kind"] == "state")
        self.assertEqual(len(part["fact_ids"]), 80)  # All bindings and existence facts.
        self.assertEqual(json.loads(next(p["text"] for p in evidence(value) if p["field"] == "output"))["current_directory_content"], names)

    def test_deleted_entry_prevents_reusing_old_listing_and_keeps_absence(self):
        value = graph(history([("ls", {}, {"current_directory_content": ["a", "b"]}),
                               ("rm", {"file_name": "b"}, {"result": "'b' removed"})]))
        state = current_state(value)
        self.assertIn('initial directory known entries: "a"', state)
        self.assertNotIn("RESULT 1.current_directory_content", state)
        self.assertIn('initial directory absent: "b"', state)
        self.assertIn('"b" (previously in initial directory): exists=false', state)

    def test_recreated_same_name_needs_a_listing_of_the_new_identity(self):
        steps = [("ls", {}, {"current_directory_content": ["a"]}),
                 ("rm", {"file_name": "a"}, {"result": "'a' removed"}),
                 ("touch", {"file_name": "a"}, None)]
        before = current_state(graph(history(steps)))
        self.assertNotIn("RESULT 1.current_directory_content", before)
        after = current_state(graph(history(steps + [("ls", {}, {"current_directory_content": ["a"]})])))
        self.assertIn('known entries: "a" (file)', after)
        self.assertIn("exists=false", after)  # The deleted old object remains distinct.

    def test_directory_aliases_distinguish_same_names_without_inventing_absolute_paths(self):
        value = graph(history([("ls", {}, {"current_directory_content": ["a"]}),
                               ("cd", {"folder": "sub"}, {"current_working_directory": "sub"}),
                               ("ls", {}, {"current_directory_content": ["a"]})]))
        state = current_state(value)
        self.assertIn('cwd: "sub"', state)
        self.assertIn('initial directory known entries: "a", "sub" (directory)', state)
        self.assertIn('"sub" known entries: "a"', state)
        self.assertNotIn('"/sub"', state)

    def test_listing_subset_plus_new_summary_keeps_all_facts_and_raw_evidence(self):
        names = [f"image_{index:018d}.jpg" for index in range(30)]
        messages = history([("ls", {}, {"current_directory_content": names}),
                            ("echo", {"file_name": "summary.txt", "content": "ALL ORIGINAL NAMES"}, None)])
        value = graph(messages)
        before = deepcopy(value)
        state = current_state(value)
        self.assertIn('known entries: RESULT 1.current_directory_content + "summary.txt" (file)', state)
        self.assertIn('"summary.txt": content@CALL 2/RESULT 2', state)
        self.assertNotIn(names[0], state)
        parts = render_readable_segments(value)
        self.assertEqual(len(next(p["fact_ids"] for p in parts if p["kind"] == "state")), 64)
        raw_return = next(p["text"] for p in parts if p["kind"] == "evidence" and p["field"] == "output")
        self.assertEqual(raw_return, messages[2]["output"])
        self.assertEqual(json.loads(raw_return)["current_directory_content"], names)
        self.assertEqual(value, before)

    def test_subset_reference_does_not_hide_kinds_or_content_of_referenced_members(self):
        names = [f"long_original_file_name_{index}.txt" for index in range(6)]
        # A successful echo establishes both kind and content facts for a
        # member whose binding is still confirmed by the original ls.
        value = graph(history([("ls", {}, {"current_directory_content": names}),
                               ("echo", {"file_name": names[0], "content": "ORIGINAL CONTENT"}, None),
                               ("touch", {"file_name": "added"}, None)]))
        state = current_state(value)
        self.assertIn('RESULT 1.current_directory_content + "added" (file)', state)
        self.assertIn(f'"{names[0]}": kind="file"; content@CALL 2/RESULT 2', state)
        self.assertIn('"added": content@CALL 3/RESULT 3', state)

    def test_listing_subset_rejects_deleted_recreated_or_moved_original_members(self):
        names = [f"long_original_file_name_{index}.txt" for index in range(6)]
        initial = [("ls", {}, {"current_directory_content": names})]
        cases = {
            "deleted": [("rm", {"file_name": names[0]}, {"result": f"'{names[0]}' removed"})],
            "recreated": [("rm", {"file_name": names[0]}, {"result": f"'{names[0]}' removed"}),
                          ("touch", {"file_name": names[0]}, None)],
            "moved": [("mkdir", {"dir_name": "sub"}, None),
                      ("mv", {"source": names[0], "destination": "sub"},
                       {"result": f"'{names[0]}' moved to 'sub/{names[0]}'"})],
        }
        for name, changes in cases.items():
            with self.subTest(case=name):
                value = graph(history(initial + changes + [("touch", {"file_name": "summary"}, None)]))
                self.assertNotIn("RESULT 1.current_directory_content", current_state(value))

    def test_equal_name_lists_in_different_directories_reference_their_own_results(self):
        names = [f"long_original_file_name_{index}.txt" for index in range(6)]
        value = graph(history([("ls", {}, {"current_directory_content": names}),
                               ("cd", {"folder": "sub"}, {"current_working_directory": "sub"}),
                               ("ls", {}, {"current_directory_content": names}),
                               ("touch", {"file_name": "summary"}, None)]))
        state = current_state(value)
        self.assertIn('initial directory known entries: RESULT 1.current_directory_content + "sub" (directory)', state)
        self.assertIn('"sub" known entries: RESULT 3.current_directory_content + "summary" (file)', state)
        self.assertNotIn('"sub" known entries: RESULT 1.', state)

    def test_duplicate_names_in_old_listing_are_never_referenced(self):
        name = "very_long_original_filename_" * 4
        value = graph(history([("ls", {}, {"current_directory_content": [name, name]}),
                               ("touch", {"file_name": "summary"}, None)]))
        self.assertNotIn("RESULT 1.current_directory_content", current_state(value))
        self.assertEqual(json.loads(next(p["text"] for p in evidence(value) if p["field"] == "output"))["current_directory_content"], [name, name])


if __name__ == "__main__":
    unittest.main()
