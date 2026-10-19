"""Semantic invariants for the shared object/fact/event representation."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest

from core.event_graph import GraphMemoryV2
from test_state_transition_graph import history


def make(steps, chat=False):
    memory = GraphMemoryV2()
    memory.build(history(steps, chat))
    return memory


def facts(memory, predicate=None, step=None):
    return [f for f in memory.state_at(step)["facts"] if predicate is None or f["predicate"] == predicate]


def binding(memory, name, step=None):
    return next(f for f in facts(memory, "binding", step) if f["value"]["name"] == name)


class FactGraphTests(unittest.TestCase):
    def test_rename_preserves_identity_and_versions(self):
        m = make([("ls", {}, {"current_directory_content": ["a.pdf"]}),
                  ("mv", {"source": "a.pdf", "destination": "temp"}, {"result": "'a.pdf' moved to 'temp'"})])
        old, new = binding(m, "a.pdf", 1), binding(m, "temp")
        self.assertEqual(old["subject"], new["subject"])
        self.assertEqual((old["version"], new["version"]), (1, 2))
        self.assertFalse(facts(m, "kind"))  # The extension supplies no type evidence.
        self.assertTrue(any(e["relation"] == "supersedes" and e["from"] == new["id"] and e["to"] == old["id"] for e in m.graph["edges"]))
        event = m.nodes["a2"]
        self.assertEqual(event["output_raw"], '{"result": "\'a.pdf\' moved to \'temp\'"}')

    def test_copy_allocates_new_identity_and_preserves_source(self):
        m = make([("touch", {"file_name": "a"}, None),
                  ("echo", {"file_name": "a", "content": "hello"}, None),
                  ("cp", {"source": "a", "destination": "b"}, {"result": "'a' copied to 'b'"})])
        a, b = binding(m, "a")["subject"], binding(m, "b")["subject"]
        self.assertNotEqual(a, b)
        self.assertEqual({f["value"] for f in facts(m, "content")}, {"hello"})
        self.assertTrue(any(e["relation"] == "copied_from" and e["from"] == b and e["to"] == a for e in m.graph["edges"]))
        self.assertTrue(any(e["relation"] == "derived_from" for e in m.graph["edges"]))

    def test_delete_recreate_same_name_new_object(self):
        m = make([("touch", {"file_name": "a"}, None),
                  ("rm", {"file_name": "a"}, {"result": "'a' removed"}),
                  ("touch", {"file_name": "a"}, None)])
        self.assertNotEqual(binding(m, "a", 1)["subject"], binding(m, "a")["subject"])
        self.assertEqual([f["value"] for f in facts(m, "exists", 2)], [False])

    def test_repeated_observation_reuses_fact_adds_evidence(self):
        m = make([("ls", {}, {"current_directory_content": ["a"]})] * 3)
        all_bindings = [n for n in m.graph["nodes"] if n.get("predicate") == "binding"]
        self.assertEqual(len(all_bindings), 1)
        self.assertEqual([c["event"] for c in all_bindings[0]["confirmations"]], ["a1", "a2", "a3"])
        self.assertEqual(len(binding(m, "a", 1)["confirmations"]), 1)

    def test_fact_reappearance_after_change_is_new_version(self):
        m = make([("cat", {"file_name": "a"}, {"file_content": value}) for value in ("first", "second", "first")])
        versions = [n for n in m.graph["nodes"] if n.get("predicate") == "content"]
        self.assertEqual([f["version"] for f in versions], [1, 2, 3])
        self.assertEqual([f["value"] for f in facts(m, "content")], ["first"])

    def test_scope_and_context_skip_unrelated_calls(self):
        m = make([("mkdir", {"dir_name": "temp"}, None),
                  ("cd", {"folder": "document"}, {"current_working_directory": "document"}),
                  ("ls", {}, {"current_directory_content": ["a"]}),
                  ("du", {}, {"disk_usage": "something"}),
                  ("mv", {"source": "a", "destination": "temp"}, {"result": "'a' moved to 'temp'"})])
        bindings = [f for f in facts(m, "binding") if f["value"]["name"] == "temp"]
        self.assertEqual(len(bindings), 2)
        self.assertNotEqual(bindings[0]["value"]["directory"], bindings[1]["value"]["directory"])
        used = [m.nodes[e["to"]] for e in m.graph["edges"] if e["from"] == "a5" and e["relation"] == "resolved_using"]
        self.assertEqual({f["predicate"] for f in used}, {"cwd", "binding"})
        self.assertEqual({f["first_observed_at"] for f in used}, {2, 3})
        self.assertFalse(any(e["from"] == "a5" and e["to"] == "a4" for e in m.graph["edges"]))

    def test_move_into_directory_keeps_identity(self):
        m = make([("touch", {"file_name": "a"}, None),
                  ("mkdir", {"dir_name": "temp"}, None),
                  ("mv", {"source": "a", "destination": "temp"}, {"result": "'a' moved to 'temp/a'"})])
        self.assertEqual(binding(m, "a", 1)["subject"], binding(m, "a")["subject"])
        self.assertEqual(binding(m, "a")["value"]["directory"], binding(m, "temp")["subject"])

    def test_failures_preserve_facts_and_return(self):
        m = make([("touch", {"file_name": "a"}, None),
                  ("mv", {"source": "a", "destination": "bad/path"}, {"error": "path not allowed"})])
        self.assertEqual(m.state_at(1)["facts"], m.state_at(2)["facts"])
        self.assertEqual(m.nodes["a2"]["status"], "error")
        self.assertEqual(m.nodes["a2"]["error"], "path not allowed")

    def test_sort_does_not_write_and_old_content_stays_historical(self):
        m = make([("cat", {"file_name": "a"}, {"file_content": "b\na"}),
                  ("sort", {"file_name": "a"}, {"sorted_content": "a\nb"}),
                  ("echo", {"file_name": "a", "content": "c"}, None)])
        self.assertEqual([f["value"] for f in facts(m, "content", 2)], ["b\na"])
        self.assertEqual([f["value"] for f in facts(m, "content")], ["c"])

    def test_unknown_effect_is_uncertainty_not_deletion(self):
        m = make([("touch", {"file_name": "a"}, None), ("custom_tool", {}, {"result": "ok"}),
                  ("ls", {}, {"current_directory_content": ["a"]})])
        self.assertFalse(facts(m, "exists", 2))
        old = binding(m, "a", 1)
        self.assertEqual(m.nodes[old["id"]]["retired_reason"], "unmodeled_effect")
        self.assertNotEqual(old["subject"], binding(m, "a")["subject"])

    def test_listing_disappearance_then_reappearance_new_identity(self):
        m = make([("ls", {}, {"current_directory_content": names}) for names in (["a"], [], ["a"])])
        self.assertNotEqual(binding(m, "a", 1)["subject"], binding(m, "a")["subject"])
        self.assertFalse(facts(m, "exists", 2))  # Absence here does not prove deletion everywhere.
        self.assertEqual(facts(m, "entry_absent", 2)[0]["key"], "a")

    def test_hidden_names_are_not_invalidated_by_normal_ls(self):
        m = make([("touch", {"file_name": ".hidden"}, None),
                  ("ls", {"a": False}, {"current_directory_content": []})])
        self.assertEqual(binding(m, ".hidden")["value"]["name"], ".hidden")

    def test_cd_parent_reuses_directory_identity(self):
        m = make([("cd", {"folder": "document"}, {"current_working_directory": "document"}),
                  ("cd", {"folder": ".."}, {}),
                  ("cd", {"folder": "document"}, {"current_working_directory": "document"})])
        self.assertEqual(m.state_at(1)["cwd"], m.state_at(3)["cwd"])
        self.assertEqual(m.state_at(2)["cwd"]["location_id"], "l0")
        versions = [n for n in m.graph["nodes"] if n.get("predicate") == "cwd"]
        self.assertEqual(len(versions), 4)

    def test_protocols_and_pending_calls(self):
        steps = [("mkdir", {"dir_name": "temp"}, None)]
        for chat in (False, True):
            messages = history(steps, chat)
            before = deepcopy(messages)
            m = GraphMemoryV2()
            result = m.compress(messages)
            self.assertEqual(messages, before)
            self.assertTrue(all(a is b for a, b in zip(messages, result)))
            self.assertEqual(len(result), len(messages) + 1)
            self.assertIn("GraphMemory v2", result[-1]["content"])
            with self.assertRaises(ValueError):
                GraphMemoryV2().compress(messages[:-1])
        with self.assertRaises(ValueError):
            GraphMemoryV2().build([{"role": "tool", "tool_call_id": "orphan", "content": "None"}])

    def test_call_ids_not_output_position(self):
        messages = history([]) + [
            {"type": "function_call", "call_id": "x", "name": "mkdir", "arguments": '{"dir_name":"x"}'},
            {"type": "function_call", "call_id": "y", "name": "mkdir", "arguments": '{"dir_name":"y"}'},
            {"type": "function_call_output", "call_id": "y", "output": '{"error":"bad"}'},
            {"type": "function_call_output", "call_id": "x", "output": "None"}]
        m = GraphMemoryV2(); m.build(messages)
        self.assertEqual(m.nodes["a1"]["call_id"], "y")
        self.assertEqual(binding(m, "x")["value"]["name"], "x")

    def test_goals_claims_never_become_environment_facts(self):
        m = GraphMemoryV2()
        m.build([{"role": "user", "content": "Create a secret file."},
                 {"role": "assistant", "content": "All done."}])
        self.assertEqual(len(facts(m)), 1)  # Only the unknown initial location placeholder.
        self.assertEqual(m.state_at()["task_completion"], "unknown")
        self.assertFalse(m.graph["annotations"][0]["verified_state"])

    def test_prefix_projection_excludes_future_confirmation_and_retirement(self):
        steps = [("ls", {}, {"current_directory_content": ["a"]}),
                 ("ls", {}, {"current_directory_content": ["a"]}),
                 ("mv", {"source": "a", "destination": "b"}, {"result": "'a' moved to 'b'"})]
        complete = make(steps)
        for i in range(1, 4):
            self.assertEqual(complete.state_at(i), make(steps[:i]).state_at())

    def test_transfer_without_prior_observation_does_not_invent_past_binding(self):
        m = make([("mv", {"source": "a", "destination": "b"}, {"result": "'a' moved to 'b'"})])
        self.assertFalse(facts(m, "binding", 0))
        self.assertEqual(len(facts(m, "binding")), 1)
        self.assertFalse(any(n.get("predicate") == "binding" and n["value"]["name"] == "a" for n in m.graph["nodes"]))



if __name__ == "__main__":
    unittest.main()
