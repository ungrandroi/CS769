"""Offline integration of managed billing and paired reports."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from io import BytesIO
import json,os,unittest
from cs769.reporting import from_batch,from_rows
from cs769.config import load_config,ExperimentConfig
from cs769.pipeline import prepare
from cs769.runtime import continue_run
from cs769.adapters.budget import PersistentBudget
from cs769.adapters.http import HTTPTransport

class IntegrationTests(unittest.TestCase):
    def test_managed_transport_accounts_once(self):
        with TemporaryDirectory() as td:
            p=Path(td);k=p/"env";k.write_text("OPENAI_API_KEY=fixture-only\n");k.chmod(0o600)
            cfg=load_config(Path(__import__("cs769").__file__).parent/"configs/g9-view-full.json").to_dict()
            cfg["execution"]["budget_usd"]=.1
            prepared=prepare([{"role":"user","content":"Continue"}],ExperimentConfig.from_dict(cfg),len)
            class Environment:
                done=False
                def finished(self):return self.done
                def step(self,message):self.done=True;return []
                def evaluate(self):return {"passed":True}
            b=PersistentBudget(p/"budget.json",.1,{"input":1,"output":1})
            t=HTTPTransport("openai",k,b,authorized=True)
            response={"choices":[{"message":{"role":"assistant","content":"Done"}}],"usage":{"prompt_tokens":100,"completion_tokens":10}}
            with patch.dict(os.environ,{"CS769_OFFLINE":"0"}),patch("urllib.request.urlopen",return_value=BytesIO(json.dumps(response).encode()))as send:
                result=continue_run(prepared,[],Environment(),t,b,authorized=True)
            ledger=json.loads((p/"budget.json").read_text())
            self.assertEqual(send.call_count,1);self.assertEqual(len(ledger["requests"]),1)
            self.assertEqual(next(iter(ledger["requests"].values()))["status"],"settled")
            self.assertTrue(result["score"]["passed"]);self.assertEqual(result["usage"]["input_tokens"],100)

    def test_reports_exclusions_token_and_added_tool_calls(self):
        with TemporaryDirectory() as td:
            p=Path(td);plan=[{"task":"x","arm":a}for a in ("identity","g9")]+[{"task":"z","arm":"g9"},{"task":"no","arm":"identity"}]
            (p/"plan.json").write_text(json.dumps(plan));(p/"manifest.json").write_text("{}")
            for i,spec in enumerate(plan[:3]):
                d=p/(str(i).zfill(4)+"-"+spec["task"]+"-"+spec["arm"]);d.mkdir()
                m={"task_id":spec["task"],"arm":spec["arm"],"repeat":1,"model":"fixture","checkpoint_sha256":"same","trigger_index":3 if i<2 else None,
                   "status":"complete","usage_suffix":{"first_input_tokens":100+20*i,"tool_calls":2+i,"total_tokens":200+50*i}}
                (d/"manifest.json").write_text(json.dumps(m));(d/"score.json").write_text(json.dumps({"passed":i==0}))
            (p/"budget.json").write_text(json.dumps({"requests":{"one":{"reserved_usd":.02,"actual_usd":.01},"two":{"reserved_usd":.03}}}))
            r=from_batch(p)
            self.assertEqual(r["paired_samples"],1);self.assertEqual(r["regressions"],["x"])
            self.assertEqual(r["mean_extra_first_input_tokens"],20);self.assertEqual(r["first_input_increase_percent"],20)
            self.assertEqual(r["net_added_tool_calls"],1);self.assertEqual(r["positive_added_tool_calls"],1)
            self.assertEqual(len(r["excluded"]),2);self.assertEqual(r["known_api_usd"],.01);self.assertEqual(r["unsettled_reserved_usd"],.03)

    def test_models_never_share_a_pair(self):
        rows=[{"task":"x","checkpoint_sha256":"same","repeat":1,"model":m,"arm":a,"passed":True,"usage":{"tool_calls":1,"total_tokens":1}}
              for m in ("one","two")for a in ("identity","g9")]
        r=from_rows(rows)
        self.assertEqual(set(r["models"]),{"one","two"})
        self.assertTrue(all(v["paired_samples"]==1 for v in r["models"].values()))
