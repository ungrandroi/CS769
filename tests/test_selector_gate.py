import json,unittest
from copy import deepcopy
from cs769.models.edits import selector_gate as sg, dependency_slice as ds
from cs769.tasks.memory import prepare
from cs769.base.config import ExperimentConfig
from cs769.cli import counter
class GateTests(unittest.TestCase):
 def graph(self,output,args=None):
  h=[{"role":"user","content":"Inspect the resource."},
     {"type":"function_call","call_id":"c1","name":"read_records","arguments":json.dumps(args or {})},
     {"type":"function_call_output","call_id":"c1","output":json.dumps(output)}]
  return prepare(h,ExperimentConfig(),counter("o200k_base"))["graph"]
 def test_amortization_and_zero(self):
  e=sg.economics(1775,694);self.assertTrue(e["allowed"]);self.assertEqual(e["estimated_break_even_requests"],3)
  self.assertLess(e["scenarios"][0]["estimated_net_saved_tokens"],0)
  self.assertFalse(sg.economics(3197,173)["allowed"])
  self.assertFalse(sg.economics(10,0)["allowed"])
 def test_quoted_result_protected_and_graph_unchanged(self):
  g=self.graph({"records":["literal needle-alpha "+("filler "*100)]});before=deepcopy(g)
  cur=[{"role":"user","content":"Copy the sentence containing 'needle-alpha'."}]
  c=ds.catalog(g,counter("o200k_base"),cur);keep,reject=sg.protected_candidates(g,cur,c)
  self.assertTrue(c["candidates"]);self.assertFalse(keep);self.assertTrue(reject)
  self.assertEqual(reject[0]["relation"],"result_of");self.assertEqual(g,before)
 def test_call_argument_reference_protects_result(self):
  g=self.graph({"records":["unrelated words "*100]},{"query":"needle-alpha"})
  cur=[{"role":"user","content":"Use the results for 'needle-alpha'."}]
  c=ds.catalog(g,counter("o200k_base"),cur)
  self.assertTrue(c["candidates"]);self.assertFalse(sg.protected_candidates(g,cur,c)[0])
 def test_equal_payloads_are_not_excluded(self):
  v="generic descriptive text "*100;g=self.graph({"left":v,"right":v})
  cur=[{"role":"user","content":"Continue."}]
  c=ds.catalog(g,counter("o200k_base"),cur)
  kept,rejected=sg.protected_candidates(g,cur,c)
  self.assertEqual(len(kept),2);self.assertFalse(rejected)
 def test_actual_usage_postcheck_ignores_future(self):
  count=counter("o200k_base")
  x=sg.assess_selected(count,"some "*1000,"some "*999,{"prompt_tokens":3000,"completion_tokens":100})
  self.assertFalse(x["allowed"]);self.assertEqual(x["cost_tokens"],3100)
  self.assertFalse(x["uses_actual_future_requests"])
if __name__=="__main__":unittest.main()
