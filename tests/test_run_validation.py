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
from cs769.config import load_config

CONFIG = Path(cs769.__file__).parent / "configs/g9-working-history.json"

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
                     patch("cs769.adapters.http.HTTPTransport.send", side_effect=AssertionError("must not send")) as send, \
                     patch("cs769.adapters.http.read_credentials", side_effect=AssertionError("must not read key")) as keys:
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
