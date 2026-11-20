"""Current CLI rejects bad recovery inputs and overwrites before model calls."""
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import os
import unittest
import cs769
from cs769.cli import main
from cs769.base.config import load_config

CONFIG = Path(cs769.__file__).parent / "configs/evidence_graph_history_threshold.json"

class RunValidationTests(unittest.TestCase):
    def args(self, root):
        return ["run", "--config", str(CONFIG), "--task", "multi_turn_base_39",
                "--category", "multi_turn_base", "--output", str(root / "out"),
                "--source", str(root / "source"), "--authorize-api", "--budget-usd", "1",
                "--credentials", str(root / "unused-key"), "--rates", str(root / "unused-rates")]

    def source(self, root, **changes):
        path = root / "source"
        path.mkdir(exist_ok=True)
        manifest = {"status": "complete", "task_id": "multi_turn_base_39", "category": "multi_turn_base",
                    "model": "gpt-4.1", "sampling": load_config(CONFIG).model["sampling"], "trigger_index": 1}
        manifest.update(changes)
        (path / "manifest.json").write_text(json.dumps(manifest))
        (path / "api.json").write_text("[]")

    def test_incomplete_or_mismatched_source_never_reaches_transport(self):
        variants = [{"status": "running"}, {"task_id": "another"}, {"category": "multi_turn_long_context"},
                    {"model": "another"}, {"sampling": {"seed": 43}}, {"trigger_index": None}]
        for changes in variants:
            with self.subTest(changes=changes), TemporaryDirectory() as td:
                root = Path(td)
                self.source(root, **changes)
                with patch.dict(os.environ, {"CS769_OFFLINE": "0"}), \
                     patch("cs769.models.http.HTTPTransport.send", side_effect=AssertionError("must not send")) as send, \
                     patch("cs769.models.http.read_credentials", side_effect=AssertionError("must not read key")) as keys:
                    with self.assertRaises(ValueError):
                        main(self.args(root))
                send.assert_not_called()
                keys.assert_not_called()
                self.assertFalse((root / "out").exists())

    def test_existing_attempt_is_never_overwritten(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "out").mkdir()
            marker = root / "out/preserved.txt"
            marker.write_text("original")
            with patch.dict(os.environ, {"CS769_OFFLINE": "0"}), self.assertRaises(FileExistsError):
                main(self.args(root))
            self.assertEqual(marker.read_text(), "original")

    def test_missing_record_cannot_emit_a_score(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()), self.assertRaises(FileNotFoundError):
                main(["replay", "--config", str(CONFIG), "--record", str(root / "missing"),
                      "--output", str(root / "report.json")])
            self.assertFalse((root / "report.json").exists())

    def test_report_output_is_never_overwritten(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "rows.json").write_text("[]")
            (root / "report.json").write_text('{"original":true}')
            with redirect_stdout(StringIO()), self.assertRaises(FileExistsError):
                main(["report", "--rows", str(root / "rows.json"), "--output", str(root / "report.json")])
            self.assertEqual((root / "report.json").read_text(), '{"original":true}')

    def test_resumed_cli_keeps_tool_call_ids_distinct_from_replayed_prefix(self):
        from copy import deepcopy
        from cs769.models.qwen_transport import plain, response_from_chat
        raw = {"model": "gpt-4.1", "choices": [{"message": {
            "role": "assistant", "content": None, "tool_calls": [{
                "id": "provider_call", "type": "function",
                "function": {"name": "pwd", "arguments": "{}"}}]}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}}
        first = {"input": [{"role": "user", "content": "Check"}], "tools": []}
        prefix_response = plain(response_from_chat(raw, 0))
        second = {"input": first["input"] + prefix_response["output"] + [{
            "type": "function_call_output", "call_id": "qwen_call_0_0", "output": "{}"}], "tools": []}
        def run(runner, task, category, transport, **kwargs):
            prefix = transport.send(first)
            resumed = transport.send(second)
            self.assertEqual(resumed["output"][0]["call_id"], "qwen_call_1_0")
            third = {"input": second["input"] + resumed["output"] + [{
                "type": "function_call_output", "call_id": "qwen_call_1_0", "output": "{}"}], "tools": []}
            following = transport.send(third)
            ids = [packet["output"][0]["call_id"] for packet in (prefix, resumed, following)]
            self.assertEqual(len(set(ids)), 3)
            self.assertEqual(following["output"][0]["call_id"], "qwen_call_2_0")
            return {"records": [], "result": [], "metadata": {}, "prepared": None,
                    "trigger_index": 1, "checkpoint_sha256": "fixture", "requests": 3, "tool_calls": 3,
                    "usage_all": {}, "usage_live": {}, "usage_suffix": {}}
        with TemporaryDirectory() as td:
            root = Path(td); self.source(root)
            (root / "source/api.json").write_text(json.dumps([
                {"request": first, "response": prefix_response},
                {"request": second, "response": prefix_response}]))
            (root / "unused-rates").write_text(json.dumps({"input": 2, "output": 8}))
            with patch.dict(os.environ, {"CS769_OFFLINE": "0"}), \
                 patch("cs769.models.http.HTTPTransport.send", side_effect=lambda body: deepcopy(raw)) as send, \
                 patch("cs769.models.http.read_credentials", side_effect=AssertionError("must not read key")) as keys, \
                 patch("cs769.tasks.bfcl.BFCLRunner.run", new=run), \
                 patch("cs769.tasks.bfcl.official_score", return_value={"passed": True}), \
                 redirect_stdout(StringIO()):
                main(self.args(root))
            self.assertEqual(send.call_count, 2)
            keys.assert_not_called()

