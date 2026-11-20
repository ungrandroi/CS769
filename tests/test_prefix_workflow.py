"""Prefix collection must not change full-task evaluation or bypass recovery checks."""
from copy import deepcopy
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json,os,unittest,cs769
from cs769.cli import main
from cs769.tasks.bfcl import limited_entry

class PrefixWorkflowTests(unittest.TestCase):
    def test_prefix_selection_preserves_source_and_full_default(self):
        entry={"question":[[{"role":"user","content":"one"}],[{"role":"user","content":"two"}]],"initial_config":{"value":1}}
        original=deepcopy(entry)
        prefix=limited_entry(entry,1)
        self.assertEqual(len(prefix["question"]),1)
        prefix["initial_config"]["value"]=2
        self.assertEqual(entry,original)
        self.assertEqual(limited_entry(entry),entry)
        for bad in (0,-1,3,True,"1"):
            with self.assertRaises(ValueError):limited_entry(entry,bad)
    def test_graph_cannot_collect_paid_prefix(self):
        config=Path(cs769.__file__).parent/"configs/summarize_decimal_arrays.json"
        with TemporaryDirectory()as td:
            root=Path(td)
            args=["run","--config",str(config),"--task","multi_turn_long_context_151","--category","multi_turn_long_context",
                  "--prefix-turns","1","--output",str(root/"out"),"--authorize-api","--budget-usd","1",
                  "--credentials",str(root/"never-read"),"--rates",str(root/"never-read-rates")]
            with patch.dict(os.environ,{"CS769_OFFLINE":"0"}),patch("cs769.models.http.HTTPTransport.send")as send:
                with self.assertRaisesRegex(ValueError,"native identity"):main(args)
                send.assert_not_called()
            self.assertFalse((root/"out").exists())
    def test_completed_prefix_requires_captured_boundary_before_api(self):
        from cs769.base.config import load_config
        config=Path(cs769.__file__).parent/"configs/summarize_decimal_arrays.json"
        with TemporaryDirectory()as td:
            root=Path(td);src=root/"source";src.mkdir()
            (src/"manifest.json").write_text(json.dumps({"record_kind":"completed_prefix","status":"complete",
                "task_id":"multi_turn_long_context_151","category":"multi_turn_long_context",
                "model":"gpt-4.1","sampling":load_config(config).model["sampling"],"trigger_index":1,"eligible":True}))
            (src/"api.json").write_text("[]")
            args=["run","--config",str(config),"--task","multi_turn_long_context_151","--category","multi_turn_long_context",
                  "--source",str(src),"--output",str(root/"out"),"--authorize-api","--budget-usd","1",
                  "--credentials",str(root/"never-read"),"--rates",str(root/"never-read-rates")]
            with patch.dict(os.environ,{"CS769_OFFLINE":"0"}),patch("cs769.models.http.HTTPTransport.send")as send:
                with self.assertRaisesRegex(ValueError,"verified boundary"):main(args)
                send.assert_not_called()
            self.assertFalse((root/"out").exists())

