import unittest,json
from copy import deepcopy
from cs769.tasks.memory import prepare
from cs769.base.config import ExperimentConfig
from cs769.cli import counter
from cs769.models.edits import dependency_slice as ds, paired_graph
from cs769.models.edits.record_edits import evidence
class SliceTests(unittest.TestCase):
 def setUp(self):self.count=counter("o200k_base");self.cur=[{"role":"user","content":"Get the invoice for the booking."}]
 def graph(self,value,args=None,later=None):
  h=[{"role":"user","content":"Create a booking."},{"type":"function_call","call_id":"c1","name":"book","arguments":json.dumps(args or {})},{"type":"function_call_output","call_id":"c1","output":value if isinstance(value,str) else json.dumps(value)}]
  if later:h += [{"type":"function_call","call_id":"c2","name":"invoice","arguments":json.dumps(later)},{"type":"function_call_output","call_id":"c2","output":'{"success":true}'}]
  return prepare(h,ExperimentConfig(),self.count)["graph"]
 def decision(self,g,selected,cur=None):
  c=ds.catalog(g,self.count,cur or self.cur)
  return dict(version=ds.VERSION,source_sha256=c["source_sha256"],current_sha256=c["current_sha256"],drop_member_ids=selected)
 def test_partial_collection_keeps_referenced_record(self):
  g=self.graph({"booking_id":"B123","history":{"old":{"booking_id":"B000","details":["unused"]*100},"B123":{"booking_id":"B123","details":["needed"]*100}}},later={"booking_id":"B123"})
  c=ds.catalog(g,self.count,self.cur);cs=c["candidates"]
  self.assertNotIn(["history"],[x["path"] for x in cs])
  mid=next(x["id"] for x in cs if x["path"]==["history","old"])
  before=deepcopy(g);out,a,r=ds.prune(g,self.count,self.cur,decision=self.decision(g,[mid]))
  self.assertTrue(a["pruned"]);self.assertEqual(g,before)
  n=next(n for n in evidence(out)["evidence_view"]["nodes"] if n["category"]=="tool_result")
  v=json.loads(ds.fields(n)["output"]);self.assertEqual(list(v["history"]),["B123"]);self.assertEqual(v["booking_id"],"B123")
 def test_literal_scalar_and_error_preservation(self):
  raw='{ "price": 1.2300e+2, "extras": '+json.dumps(list(range(120)))+' }'
  g=self.graph(raw);m=ds.catalog(g,self.count,self.cur)["candidates"][0]["id"]
  out,a,r=ds.prune(g,self.count,self.cur,decision=self.decision(g,[m]))
  self.assertTrue(a["pruned"]);self.assertIn("1.2300e+2",r(out))
  bad=self.graph({"error":"failure","extras":list(range(100))})
  self.assertEqual(ds.catalog(bad,self.count,self.cur)["candidates"],[])
 def test_consumed_array_is_protected(self):
  v=list(range(100));g=self.graph({"array":v},later={"data":v})
  self.assertEqual(ds.catalog(g,self.count,self.cur)["candidates"],[])
 def test_historical_or_explicit_field_request(self):
  g=self.graph({"MA(20)":list(range(100))})
  for text in ["Compute MA20.","What were the earlier values?"]:
   self.assertEqual(ds.catalog(g,self.count,[{"role":"user","content":text}])["candidates"],[])
 def test_overlaps_and_stale_rejected(self):
  g=self.graph({"details":{"a":list(range(100)),"b":list(range(100))}})
  cs=ds.catalog(g,self.count,self.cur)["candidates"];ids=[x["id"] for x in cs]
  bounded=ds.bounded_selection(ids,cs,16)
  self.assertEqual(len(bounded),1)
  with self.assertRaises(ValueError):ds.prune(g,self.count,self.cur,decision=self.decision(g,ids))
  d=self.decision(g,bounded);d["current_sha256"]="wrong"
  with self.assertRaises(ValueError):ds.prune(g,self.count,self.cur,decision=d)
 def test_noop_equals_frozen_lossless(self):
  g=self.graph({"price":1});out,a,r=ds.prune(g,self.count,self.cur,decision=self.decision(g,[]))
  b,_,br=paired_graph.compact(g,self.count,self.cur);self.assertEqual(r(out),br(b));self.assertFalse(a["pruned"])
if __name__=="__main__":unittest.main()
