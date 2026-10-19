"""Check evidence boundaries and state effects, including BFCL-specific traps."""
import json
import unittest
from copy import deepcopy

from core.state_transition_graph import GraphMemory


def history(steps, chat=False):
    messages = [{"role": "user", "content": "Work on report.pdf in document."}]
    for index, (tool, args, output) in enumerate(steps):
        call_id = f"call_{index}"
        raw = json.dumps(output) if output is not None else "None"
        if chat:
            messages += [{"role": "assistant", "content": None, "tool_calls": [
                {"id": call_id, "function": {"name": tool, "arguments": json.dumps(args)}, "type": "function"}]},
                {"role": "tool", "tool_call_id": call_id, "content": raw}]
        else:
            messages += [{"type": "function_call", "call_id": call_id, "name": tool, "arguments": json.dumps(args)},
                         {"type": "function_call_output", "call_id": call_id, "output": raw}]
    return messages


def state(graph):
    return graph["nodes"][-1]["state"]


def obj(graph, name, scope=None):
    scope = scope or state(graph)["cwd"]["location_id"]
    return next(o for o in state(graph)["objects"] if o["name"] == name and o["location_id"] == scope)


class StateGraphTest(unittest.TestCase):
    def test_goal_and_assistant_claim_are_not_environment_facts(self):
        messages = [{"role": "user", "content": "Create secret.txt and enter hidden."},
                    {"role": "assistant", "content": "I created secret.txt in hidden."}]
        g = GraphMemory().build(messages)
        self.assertEqual(state(g)["objects"], [])
        self.assertIsNone(state(g)["cwd"]["value"])
        self.assertEqual(state(g)["task_completion"], "unknown")
        self.assertFalse(g["annotations"][0]["verified_state"])

    def test_protocols_match_and_source_is_unchanged(self):
        steps = [("pwd", {}, {"current_working_directory": "/document"}),
                 ("mkdir", {"dir_name": "temp"}, None)]
        for chat in (False, True):
            messages = history(steps, chat)
            before = deepcopy(messages)
            memory = GraphMemory()
            result = memory.compress(messages)
            self.assertEqual(messages, before)
            self.assertTrue(all(a is b for a, b in zip(result, messages)))
            self.assertEqual(len(result), len(messages) + 1)
            self.assertEqual(obj(memory.graph, "temp")["kind"], "directory")
            self.assertEqual(state(memory.graph)["cwd"]["value"], "/document")

    def test_failed_call_keeps_error_without_asserting_success(self):
        g = GraphMemory().build(history([("mv", {"source": "a", "destination": "b"}, {"error": "not found"})]))
        self.assertEqual(g["edges"][0]["status"], "error")
        self.assertEqual(state(g)["objects"], [])
        self.assertEqual(state(g)["task_completion"], "unknown")

    def test_directory_scopes_and_cd_parent(self):
        g = GraphMemory().build(history([
            ("mkdir", {"dir_name": "temp"}, None),
            ("cd", {"folder": "document"}, {"current_working_directory": "document"}),
            ("mkdir", {"dir_name": "temp"}, None),
            ("cd", {"folder": ".."}, {})]))
        dirs = [o for o in state(g)["objects"] if o["name"] == "temp"]
        self.assertEqual(len(dirs), 2)
        self.assertNotEqual(dirs[0]["location_id"], dirs[1]["location_id"])
        self.assertEqual(state(g)["cwd"]["location_id"], "l0")
        self.assertIsNone(state(g)["cwd"]["value"])

    def test_move_return_disambiguates_rename_from_directory(self):
        prefix = [("touch", {"file_name": "a"}, None), ("echo", {"file_name": "a", "content": "text"}, None)]
        renamed = GraphMemory().build(history(prefix + [("mv", {"source": "a", "destination": "temp"}, {"result": "'a' moved to 'temp'"})]))
        self.assertEqual(obj(renamed, "temp")["kind"], "file")
        self.assertEqual(obj(renamed, "temp")["content"], "text")
        self.assertFalse(obj(renamed, "a")["exists"])
        moved = GraphMemory().build(history(prefix + [("mkdir", {"dir_name": "temp"}, None),
            ("mv", {"source": "a", "destination": "temp"}, {"result": "'a' moved to 'temp/a'"})]))
        self.assertEqual(obj(moved, "temp")["kind"], "directory")
        live_a = [o for o in state(moved)["objects"] if o["name"] == "a" and o["exists"]]
        self.assertEqual(len(live_a), 1)
        self.assertNotEqual(live_a[0]["location_id"], state(moved)["cwd"]["location_id"])

    def test_read_only_sort_and_overwrite_content(self):
        steps = [("cat", {"file_name": "a"}, {"file_content": "b\na"}),
                 ("sort", {"file_name": "a"}, {"sorted_content": "a\nb"})]
        g = GraphMemory().build(history(steps))
        self.assertEqual(obj(g, "a")["content"], "b\na")
        steps += [("echo", {"file_name": "a", "content": "new"}, None)]
        g = GraphMemory().build(history(steps))
        self.assertEqual(obj(g, "a")["content"], "new")
        self.assertEqual(g["nodes"][1]["state"]["objects"][0]["content"], "b\na")

    def test_ls_preserves_hidden_unknowns_and_does_not_infer_types(self):
        g = GraphMemory().build(history([("touch", {"file_name": ".hidden"}, None),
            ("ls", {"a": False}, {"current_directory_content": ["maybe.pdf"]})]))
        self.assertTrue(obj(g, ".hidden")["exists"])
        self.assertIsNone(obj(g, "maybe.pdf")["kind"])

    def test_outputs_are_bound_by_call_id_not_position(self):
        messages = history([]) + [
            {"type": "function_call", "call_id": "a", "name": "mkdir", "arguments": '{"dir_name":"x"}'},
            {"type": "function_call", "call_id": "b", "name": "mkdir", "arguments": '{"dir_name":"y"}'},
            {"type": "function_call_output", "call_id": "b", "output": '{"error":"bad"}'},
            {"type": "function_call_output", "call_id": "a", "output": "None"}]
        g = GraphMemory().build(messages)
        self.assertEqual([(e["call_id"],e["status"]) for e in g["edges"]], [("b","error"),("a","success")])
        self.assertEqual([o["name"] for o in state(g)["objects"]], ["x"])

    def test_unmodeled_mutation_invalidates_inferred_state(self):
        g = GraphMemory().build(history([("touch", {"file_name": "x"}, None), ("custom_tool", {}, {"result": "ok"})]))
        self.assertIsNone(state(g)["objects"][0]["exists"])

    def test_pending_or_orphaned_results_cannot_be_injected(self):
        with self.assertRaises(ValueError):
            GraphMemory().compress(history([("mkdir", {"dir_name": "x"}, None)])[:-1])
        with self.assertRaises(ValueError):
            GraphMemory().build([{"role": "tool", "tool_call_id": "missing", "content": "None"}])

    def test_provenance_and_prefix_causality(self):
        prefix = history([("ls", {}, {"current_directory_content": ["a"]})])
        first = GraphMemory().build(prefix)
        later = GraphMemory().build(prefix + [{"role":"user","content":"FUTURE_SENTINEL"}])
        self.assertEqual(first["nodes"], later["nodes"])
        self.assertNotIn("FUTURE_SENTINEL", json.dumps(first))
        for node in first["nodes"]:
            for ref in node["evidence"]:
                self.assertLess(int(ref[1:]), len(prefix))

    def test_rehydrated_sdk_wire_aliases(self):
        import httpx
        from openai import OpenAI
        from openai.types.responses import ResponseFunctionToolCall
        from core.qwen_transport import plain
        message = ResponseFunctionToolCall.model_validate({"type":"function_call", "call_id":"c",
            "name":"pwd", "arguments":"{}", "async":None})
        bodies = []
        def handle(request):
            bodies.append(json.loads(request.content))
            return httpx.Response(200,json={"id":"test","created_at":0,"object":"response",
                "model":"test","output":[],"parallel_tool_calls":True,"tool_choice":"auto","tools":[]})
        with OpenAI(api_key="offline-test",base_url="http://offline.invalid/v1",
                    http_client=httpx.Client(transport=httpx.MockTransport(handle))) as client:
            client.responses.create(**plain({"model":"test", "input":[message]}))
        self.assertIn("async", bodies[0]["input"][0])
        self.assertNotIn("async_", bodies[0]["input"][0])


if __name__ == "__main__":
    unittest.main()
