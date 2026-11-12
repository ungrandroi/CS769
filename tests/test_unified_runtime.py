"""Shared runtime safeguards, replacing tests of retired model-specific run loops."""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json,os,unittest,urllib.error
from cs769.config import ExperimentConfig,load_config
from cs769.pipeline import prepare
from cs769.requests import build_request
from cs769.adapters.replay import ReplayTransport,ReplayMismatch
from cs769.adapters.budget import PersistentBudget,BudgetExceeded
from cs769.adapters.http import HTTPTransport,ProviderError

PACKAGE=Path(__import__("cs769").__file__).parent

class UnifiedRuntimeTests(unittest.TestCase):
    def test_frozen_replay_never_releases_a_response_to_a_different_request(self):
        request={"input":[{"role":"user","content":"x"}],"tools":[]}
        t=ReplayTransport([{"request":request,"response":{"id":"r","output":[]}}])
        with self.assertRaises(ReplayMismatch):t.send({**request,"input":[]})
        self.assertEqual(t.index,0)
        self.assertEqual(t.send(request)["id"],"r");t.finish()
        with self.assertRaises(ReplayMismatch):t.send(request)

    def test_frozen_prefix_and_following_request_are_not_duplicated(self):
        history=[{"role":"user","content":"Find x"},{"role":"assistant","content":None,"tool_calls":[{"id":"c","type":"function","function":{"name":"find","arguments":"{}"}}]},
                 {"role":"tool","tool_call_id":"c","content":'{"paths":["x"]}'},{"role":"assistant","content":"Found x"}]
        original=deepcopy(history);following=[{"role":"user","content":"Read it now"}]
        for profile in ["identity","g9-view-full"]:
            cfg=load_config(PACKAGE/"configs"/(profile+".json"));got=prepare(history,cfg,len,next_messages=following)
            self.assertEqual(history,original)
            self.assertEqual(sum(m.get("content")=="Read it now"for m in got["messages"]),1)
            if profile!="identity":
                self.assertFalse(any(m.get("role")=="tool"or m.get("tool_calls")for m in got["messages"]))

    def test_reasoning_wire_omits_temperature(self):
        cfg=load_config(PACKAGE/"configs/g9-gpt-5-mini.json")
        result=prepare([{"role":"user","content":"Continue"}],cfg,len)
        wire=build_request(result,[])
        self.assertNotIn("temperature",wire)
        self.assertEqual(wire["reasoning_effort"],cfg.model["sampling"]["reasoning_effort"])

    def test_uncertain_request_is_not_retried_or_refunded(self):
        with TemporaryDirectory() as td:
            p=Path(td);key=p/"env";key.write_text("OPENAI_API_KEY=not-a-real-key\n");key.chmod(0o600)
            b=PersistentBudget(p/"budget.json",.02,{"input":1,"output":1})
            t=HTTPTransport("openai",key,b,authorized=True)
            with patch.dict(os.environ,{"CS769_OFFLINE":"0"}),patch("urllib.request.urlopen",side_effect=urllib.error.URLError("fixture"))as send:
                with self.assertRaises(ProviderError):t.send({"model":"fixture","max_tokens":10,"messages":[]})
            self.assertEqual(send.call_count,1)
            d=json.loads((p/"budget.json").read_text());self.assertEqual(len(d["requests"]),1)
            self.assertEqual(next(iter(d["requests"].values()))["status"],"uncertain")

    def test_cap_is_shared_across_budget_instances(self):
        with TemporaryDirectory() as td:
            p=Path(td)/"budget.json";rates={"input":1,"output":1}
            a=PersistentBudget(p,.004,rates);a.reserve({"model":"fixture","max_tokens":10})
            b=PersistentBudget(p,.004,rates)
            with self.assertRaises(BudgetExceeded):b.reserve({"model":"fixture","max_tokens":10})

    def test_disabled_transport_never_reads_a_key(self):
        t=HTTPTransport("openai","absent",None)
        with patch("cs769.adapters.http.read_credentials",side_effect=AssertionError("must not read")):
            with self.assertRaises(PermissionError):t.send({})

    def test_swallowed_transport_failure_cannot_be_scored_complete(self):
        from cs769.adapters.bfcl import BFCLRunner
        class Handler:
            def __init__(self,*a):pass
            def _add_next_turn_user_message_FC(self,*a):pass
            def _parse_query_response_FC(self,*a):pass
            def _query_FC(self,*a):pass
            def inference(self,*a):
                try:self.generate_with_backoff(input=[{"role":"user","content":"x"}],tools=[])
                except RuntimeError:pass
                return [[]],{}
        class Fail:
            def send(self,r):raise RuntimeError("fixture API failure")
        cfg=load_config(PACKAGE/"configs/identity.json")
        with patch("cs769.adapters.bfcl._USED_PROCESS",None),patch("bfcl_eval.model_handler.api_inference.openai_response.OpenAIResponsesHandler",Handler),patch("bfcl_eval.utils.load_dataset_entry",return_value=[{"id":"fixture"}]):
            with self.assertRaisesRegex(RuntimeError,"fixture API failure"):
                BFCLRunner(cfg,len).run("fixture","multi_turn_base",Fail())

    def test_same_process_cannot_reuse_bfcl_tool_state(self):
        from cs769.adapters.bfcl import BFCLRunner
        cfg=load_config(PACKAGE/"configs/identity.json")
        with patch("cs769.adapters.bfcl._USED_PROCESS",os.getpid()):
            with self.assertRaisesRegex(RuntimeError,"one worker process"):
                BFCLRunner(cfg,len).run("fixture","multi_turn_base",None)

    def test_budget_cannot_borrow_another_models_ledger(self):
        with TemporaryDirectory() as td:
            b=PersistentBudget(Path(td)/"ledger.json",.02,{"input":1,"output":1})
            b.reserve({"model":"model-a","max_tokens":8})
            with self.assertRaisesRegex(ValueError,"mix models"):b.reserve({"model":"model-b","max_tokens":8})

    def test_sorted_counter_accepts_chat_and_responses(self):
        from cs769.history import history_counter_text,normalize,checkpoint_reached
        raw=[{"role":"user","content":"x"},{"type":"function_call","call_id":"c","name":"ls","arguments":"{}"},
             {"type":"function_call_output","call_id":"c","output":"[]"}]
        from cs769.adapters.qwen_transport import chat_messages
        chat=chat_messages(raw)
        self.assertEqual(history_counter_text(raw,sort_keys=True),history_counter_text(chat,sort_keys=True))
        text=history_counter_text(raw,sort_keys=True)
        # A separately normalized null is not byte-identical to the native empty string.
        self.assertNotEqual(text,history_counter_text(normalize(raw)[0],sort_keys=True))
        cfg={"kind":"history_tokens","counter":"history_json_sorted","threshold":len(text),"strict":True}
        self.assertFalse(checkpoint_reached(raw,cfg,len));cfg["strict"]=False;self.assertTrue(checkpoint_reached(raw,cfg,len))

    def test_explicit_repeats_are_distinct_batch_items(self):
        from cs769.batch import execute_batch
        from types import SimpleNamespace
        with TemporaryDirectory() as td:
            p=Path(td);cfg=p/"config.json";cfg.write_text("{}")
            plan=p/"plan.json";plan.write_text(json.dumps([{"task":"fixture","arm":"g9","repeat":i,"record":"fixture"}for i in (1,2)]))
            args=SimpleNamespace(plan=plan,config=cfg,output=p/"output",replay=True,workers=1,authorize_api=False,budget_usd=0,credentials=None,rates=None)
            def run(cmd,stdout,stderr):
                stdout.write("{}");return SimpleNamespace(returncode=0)
            with patch("cs769.provenance.source_identity",return_value={"package_sha256":{}}),patch("cs769.provenance.package_hashes",return_value={}),patch("cs769.batch.subprocess.run",side_effect=run)as worker:
                got=execute_batch(args)
            self.assertEqual(worker.call_count,2);self.assertEqual({x["repeat"]for x in got["results"]},{1,2})

    def test_duplicate_same_repeat_is_rejected_before_creating_output(self):
        from cs769.batch import execute_batch
        from types import SimpleNamespace
        with TemporaryDirectory() as td:
            p=Path(td);plan=p/"plan.json";row={"task":"x","arm":"g9","repeat":1,"record":"x"}
            plan.write_text(json.dumps([row,row]))
            args=SimpleNamespace(plan=plan,config=p/"unused",output=p/"output",replay=True,workers=1)
            with self.assertRaisesRegex(ValueError,"Duplicate"):execute_batch(args)
            self.assertFalse(args.output.exists())
