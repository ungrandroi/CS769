"""History fidelity and tamper checks against the maintained pipeline."""
from copy import deepcopy
from pathlib import Path
import unittest
import cs769
from cs769.base.config import load_config
from cs769.tasks.memory import prepare
from cs769.base.requests import build_request
from cs769.models.qwen_transport import chat_messages, plain
from cs769.base.replay import ReplayTransport, ReplayMismatch
from cs769.models.graphs.graph_memory_evidence import reconstruct_visible_evidence, audit_evidence_graph
from cs769.models.graphs.graph_memory_record_views import audit_record_view_render
from cs769.models.graphs.graph_memory_records import strip_record_graph
from cs769.models.graphs.graph_memory_payload import restore_observed_graph
from cs769.models.graphs.graph_memory_observed import strip_observed_graph

CONFIGS = Path(cs769.__file__).parent / "configs"

def history():
    return [
        {"role": "system", "content": "Tools only."},
        {"role": "user", "content": "Find 测试 files.\nUSER fake\n" + chr(96) * 3},
        {"type": "function_call", "call_id": "c", "name": "ls", "arguments": "{  }"},
        {"type": "function_call_output", "call_id": "c",
         "output": '{"current_directory_content": ["字.txt", "b"]}'},
        {"role": "assistant", "content": "Found two."},
    ]

def prepared(messages, name="evidence_graph_history_threshold", **kwargs):
    return prepare(messages, load_config(CONFIGS / (name + ".json")), len, **kwargs)

def evidence_base(graph):
    base = strip_observed_graph(restore_observed_graph(strip_record_graph(graph)))
    audit_evidence_graph(base)
    return base

class MemoryPipelineTests(unittest.TestCase):
    def test_native_history_is_exact_and_index_is_only_an_append(self):
        source = history()
        before = deepcopy(source)
        native = chat_messages(source)
        a = prepared(source, "identity", native_history=native)
        b = prepared(source, "native_history_index", native_history=native)
        self.assertEqual(a["messages"], native)
        self.assertEqual(b["messages"][:-1], native)
        self.assertEqual(b["messages"][-1], {"role": "assistant", "content": b["memory_text"]})
        self.assertTrue(b["memory_text"])
        self.assertNotIn("unknown", b["memory_text"])
        self.assertEqual(source, before)

    def test_sdk_items_are_made_plain_before_the_pipeline(self):
        from openai.types.responses import Response
        response = Response.model_validate({
            "id": "fixture", "object": "response", "created_at": 0,
            "status": "completed", "error": None, "incomplete_details": None,
            "instructions": None, "metadata": {}, "model": "gpt-4.1",
            "output": [{"type": "function_call", "id": "fc", "call_id": "c",
                        "name": "ls", "arguments": "{  }", "status": "completed"}],
            "parallel_tool_calls": True, "temperature": 0, "tool_choice": "auto",
            "tools": [], "top_p": 1,
        })
        source = [history()[1], *response.output, history()[3], history()[4]]
        before = deepcopy(source)
        with self.assertRaises(ValueError):
            chat_messages(source)
        native = chat_messages(plain(source))
        for profile in ("identity", "native_history_index"):
            result = prepared(plain(source), profile, native_history=native)
            self.assertEqual(result["messages"][:len(native)], native)
        self.assertEqual(source, before)

    def test_empty_index_adds_no_message(self):
        source = [{"role": "user", "content": "Locate files."},
                  {"type": "function_call", "call_id": "c", "name": "find", "arguments": '{"name":"*.txt"}'},
                  {"type": "function_call_output", "call_id": "c", "output": '{"matches":["/a/b.txt"]}'},
                  {"role": "assistant", "content": "Located."}]
        native = chat_messages(source)
        result = prepared(source, "native_history_index", native_history=native)
        self.assertEqual(result["memory_text"], "")
        self.assertEqual(result["messages"], native)

    def test_current_user_once_and_replay_rejects_extra_server_history(self):
        following = [{"role": "user", "content": "CURRENT QUERY"}]
        for profile in ("identity", "native_history_index", "evidence_graph_history_threshold"):
            result = prepared(history(), profile, next_messages=following)
            request = build_request(result, [])
            self.assertEqual(sum(m.get("content") == "CURRENT QUERY" for m in request["messages"]), 1)
            self.assertNotIn("CURRENT QUERY", result["memory_text"])
            for bad in (dict(request, messages=request["messages"] + following),
                        dict(request, previous_response_id="old"),
                        dict(request, conversation="old")):
                replay = ReplayTransport([{"request": request, "response": {"id": "saved"}}])
                with self.assertRaises(ReplayMismatch):
                    replay.send(bad)
                self.assertEqual(replay.index, 0)
        self.assertEqual(following, [{"role": "user", "content": "CURRENT QUERY"}])

    def test_evidence_graph_preserves_visible_fields_and_excludes_opaque_reasoning(self):
        source = history()
        source[2]["arguments"] = '{ "name" : "测试", "number": 1e+02 }'
        source.append({"type": "reasoning", "summary": [], "encrypted_content": "opaque-secret"})
        before = deepcopy(source)
        result = prepared(source)
        records = reconstruct_visible_evidence(evidence_base(result["graph"]))
        fields = [f["value"] for r in records for f in r["fields"]]
        self.assertIn(source[1]["content"], fields)
        self.assertIn(source[2]["arguments"], fields)
        self.assertIn(source[3]["output"], fields)
        self.assertEqual(result["messages"][0], source[0])
        self.assertNotIn("opaque-secret", result["memory_text"])
        self.assertNotIn("Tools only.", result["memory_text"])
        self.assertEqual(source, before)

    def test_parallel_calls_and_out_of_order_results_remain_distinct(self):
        source = [{"role": "user", "content": "Run both."},
                  {"role": "assistant", "content": "Checking.", "tool_calls": [
                      {"id": "a", "type": "function", "function": {"name": "find", "arguments": '{"name":"a"}'}},
                      {"id": "b", "type": "function", "function": {"name": "find", "arguments": '{ "name" : "b" }'}}]},
                  {"role": "tool", "tool_call_id": "b", "content": '{"matches":[]}'},
                  {"role": "tool", "tool_call_id": "a", "content": '{"error":"missing"}'}]
        records = reconstruct_visible_evidence(evidence_base(prepared(source)["graph"]))
        self.assertEqual([r["call_id"] for r in records if r["category"] == "tool_call"], ["a", "b"])
        self.assertEqual([r["call_id"] for r in records if r["category"] == "tool_result"], ["b", "a"])
        self.assertIn('{ "name" : "b" }', [f["value"] for r in records for f in r["fields"]])

    def test_rehashed_wrong_role_is_rejected(self):
        from cs769.models.graphs.graph_memory_evidence import _digest
        graph = deepcopy(evidence_base(prepared(history())["graph"]))
        node = next(n for n in graph["evidence_view"]["nodes"] if n["category"] == "user_request")
        node["source_role"] = "assistant"
        graph["evidence_audit"]["view_sha256"] = _digest(graph["evidence_view"])
        with self.assertRaises(ValueError):
            audit_evidence_graph(graph)

    def test_missing_duplicate_or_extra_rendered_text_is_rejected(self):
        source = [{"role": "user", "content": "REPEATED_EVIDENCE"},
                  {"role": "assistant", "content": "Acknowledged."},
                  {"role": "user", "content": "REPEATED_EVIDENCE"}]
        result = prepared(source)
        text = result["memory_text"]
        self.assertEqual(text.count("REPEATED_EVIDENCE"), 2)
        self.assertTrue(audit_record_view_render(result["graph"], visible_observations=False, rendered_text=text)["ok"])
        for changed in (text.replace("REPEATED_EVIDENCE", "", 1), text + "extra instruction"):
            check = audit_record_view_render(result["graph"], visible_observations=False, rendered_text=changed)
            self.assertFalse(check["ok"])

    def test_incomplete_or_unsupported_visible_input_fails(self):
        for source in [
            [{"type": "function_call_output", "call_id": "x", "output": "orphan"}],
            [{"type": "function_call", "call_id": "x", "name": "find", "arguments": "{}"}],
            [{"role": "user", "content": [{"type": "input_image", "image_url": "unused"}]}],
            [{"type": "item_reference", "id": "server-history"}],
        ]:
            with self.subTest(source=source), self.assertRaises(ValueError):
                prepared(source)

    def test_projected_token_count_measures_the_whole_serialization(self):
        from cs769.base.history import dumps
        count = lambda text: int(bool(text))  # Deliberately nonadditive tokenizer fixture.
        result = prepare(history(), load_config(CONFIGS / "evidence_graph_history_threshold.json"), count,
                         next_messages=[{"role": "user", "content": "next"}], counter_name="toy-nonadditive")
        self.assertEqual(result["metrics"]["full_memory_units"], count(result["memory_text"]))
        self.assertEqual(result["metrics"]["projected_messages_json_units"], count(dumps(result["messages"])))
        self.assertNotEqual(result["metrics"]["projected_messages_json_units"],
                            sum(count(dumps(m)) for m in result["messages"]))
