"""Provider tests migrated from the retired per-model CLI; all HTTP is fake."""
from copy import deepcopy
import json,unittest
from cs769.base.config import ExperimentConfig
from cs769.models.provider import ProviderTransport, anthropic_messages
from cs769.models.anthropic_transport import MODEL
from cs769.models.qwen_transport import plain

class FakeHTTP:
    def __init__(self):self.requests=[]
    def send(self,body):
        self.requests.append(deepcopy(body))
        first=len(self.requests)==1
        return {"id":"m"+str(len(self.requests)),"role":"assistant","model":MODEL,
                "content":[{"type":"thinking","thinking":"internal","signature":"sig"},
                           {"type":"tool_use","id":"c1","name":"ls","input":{}}] if first else [{"type":"text","text":"Done"}],
                "usage":{"input_tokens":10,"output_tokens":5},"stop_reason":"tool_use" if first else "end_turn"}

class ClaudeRunnerTest(unittest.TestCase):
    def config(self):
        d=ExperimentConfig.from_dict({}).to_dict()
        d["model"]={"provider":"anthropic","name":MODEL,"sampling":{"max_tokens":512},"old_thinking":"omit"}
        return ExperimentConfig.from_dict(d)
    def test_native_blocks_and_error_flags_survive_current_round(self):
        http=FakeHTTP();t=ProviderTransport(self.config(),http)
        first={"input":[{"role":"user","content":"Inspect files"}],"tools":[]}
        response=t.send(first)
        history=first["input"]+response["output"]+[{"type":"function_call_output","call_id":"c1","output":'{"error":"missing"}'}]
        t.send({"input":history,"tools":[]})
        body=http.requests[1]
        self.assertEqual(body["messages"][-2]["content"][0]["type"],"thinking")
        self.assertEqual(body["messages"][-2]["content"][0]["signature"],"sig")
        self.assertTrue(body["messages"][-1]["content"][0]["is_error"])
        self.assertEqual(body["messages"][-1]["content"][0]["tool_use_id"],"c1")
    def test_changed_memory_drops_old_signed_thinking(self):
        http=FakeHTTP();t=ProviderTransport(self.config(),http)
        t.send({"input":[{"role":"user","content":"Inspect"}],"tools":[]})
        t.send({"input":[{"role":"user","content":"Compiled evidence graph memory"}],"tools":[]})
        self.assertFalse(any(b["type"]=="thinking" for m in http.requests[1]["messages"]for b in m["content"]))
    def test_real_bfcl_directory_diagnostic_uses_official_serializer(self):
        from bfcl_eval.eval_checker.multi_turn_eval.func_source_code.gorilla_file_system import Directory
        from bfcl_eval.utils import make_json_serializable
        obj=Directory("regression")
        with self.assertRaises(TypeError):json.dumps({"state":obj})
        self.assertEqual(json.loads(json.dumps(make_json_serializable({"state":obj})))["state"],str(obj))

class CompletedThinkingPolicyTest(unittest.TestCase):
    config=ClaudeRunnerTest.config
    def advance_round(self,preserve):
        cfg=self.config()
        cfg.model["old_thinking"]="preserve" if preserve else "omit"
        http=FakeHTTP();transport=ProviderTransport(cfg,http)
        first={"input":[{"role":"user","content":"Inspect files"}],"tools":[]}
        a=transport.send(first)
        second=first["input"]+a["output"]+[{"type":"function_call_output","call_id":"c1","output":"{}"}]
        b=transport.send({"input":second,"tools":[]})
        transport.send({"input":second+b["output"]+[{"role":"user","content":"Next task"}],"tools":[]})
        return http.requests[2]
    def test_completed_round_omits_thinking_when_configured(self):
        body=self.advance_round(False)
        self.assertFalse(any(b["type"]=="thinking"for m in body["messages"]for b in m["content"]))
    def test_preserve_policy_is_not_silently_ignored(self):
        body=self.advance_round(True)
        self.assertTrue(any(b["type"]=="thinking"for m in body["messages"]for b in m["content"]))
