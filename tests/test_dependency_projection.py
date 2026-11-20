import json,unittest
from copy import deepcopy
from cs769.base.config import ExperimentConfig
from cs769.tasks.memory import prepare
from cs769.cli import counter
from cs769.models.edits import dependency_projection as dp
from cs769.models.edits.record_edits import evidence
from cs769.models.graphs.graph_memory_evidence import _digest
class ProjectionTests(unittest.TestCase):
    def setUp(self):
        self.count=counter("o200k_base")
        self.cur=[{"role":"user","content":"Use the distance to compute its logarithm."}]
    def graph(self, value, later=None):
        h=[{"role":"user","content":"Inspect the trip."},{"type":"function_call","name":"observe","call_id":"a","arguments":"{}"},
           {"type":"function_call_output","call_id":"a","output":value if isinstance(value,str) else json.dumps(value)}]
        if later:h += [{"type":"function_call","name":"consume","call_id":"b","arguments":json.dumps(later)},
                       {"type":"function_call_output","call_id":"b","output":'{"success":true}'}]
        cfg=ExperimentConfig();cfg.delivery={"mode":"replace","role":"assistant"}
        return prepare(h,cfg,self.count)["graph"]
    def decision(self,g,cur=None,ids=None):
        c=dp.catalog(g,self.count,self.cur if cur is None else cur)
        return {"version":dp.VERSION,"source_sha256":c["source_sha256"],"current_sha256":c["current_sha256"],
                "drop_member_ids":ids if ids is not None else [x["id"] for x in c["candidates"]]}
    def test_multiple_fields_exact_scalar_and_source(self):
        raw='{ "distance" : 1.2300e+2, "cities" : '+json.dumps(["town"]*80)+', "extras":'+json.dumps(list(range(80)))+' }'
        g=self.graph(raw);before=deepcopy(g)
        out,a,r=dp.prune(g,self.count,self.cur,decision=self.decision(g))
        self.assertFalse(a["pruned"]);self.assertEqual(g,before)
        e=evidence(out);v=next(f["value"] for n in e["evidence_view"]["nodes"] if n["category"]=="tool_result" for f in n["fields"] if f["field"]=="output")
        self.assertIn("1.2300e+2",v);self.assertEqual(json.loads(v)["distance"],123)
        self.assertIn("cities",json.loads(v));self.assertIn("extras",json.loads(v))
    def test_nested_ids_status_and_path_protected(self):
        g=self.graph({"objects":[{"order_id":i,"large":list(range(40))} for i in range(4)],"directory_content":["file"]*100,"data":list(range(50))})
        c=dp.catalog(g,self.count,self.cur)
        self.assertEqual(c["candidates"],[])
        self.assertIn("no_verified_existing_replacement",next(x for x in c["fields"] if x["key"]=="data")["protected_reasons"])
        protected=next(x["id"] for x in c["fields"] if x["key"]=="objects")
        with self.assertRaises(ValueError):dp.prune(g,self.count,self.cur,decision=self.decision(g,ids=[protected]))
    def test_historical_current_query_declines(self):
        g=self.graph({"distance":123,"cities":["town"]*100})
        cur=[{"role":"user","content":"What were the earlier cities?"}]
        self.assertEqual(dp.catalog(g,self.count,cur)["candidates"],[])
    def test_stale_graph_current_and_duplicate_rejected(self):
        g=self.graph({"distance":123,"cities":["town"]*100});d=self.decision(g)
        for field in ("source_sha256","current_sha256"):
            bad=deepcopy(d);bad[field]="bad"
            with self.assertRaises(ValueError):dp.prune(g,self.count,self.cur,decision=bad)
        bad=deepcopy(d);bad["drop_member_ids"]=["fake","fake"]
        with self.assertRaises(ValueError):dp.prune(g,self.count,self.cur,decision=bad)
    def test_recorded_whole_value_dependency_protected(self):
        arr=list(range(60));g=self.graph({"values":arr,"distance":5},later={"numbers":arr})
        self.assertEqual(dp.catalog(g,self.count,self.cur)["candidates"],[])
    def test_no_selection_is_exact_shared_baseline(self):
        g=self.graph({"distance":5,"cities":["town"]*100})
        out,a,r=dp.prune(g,self.count,self.cur,decision=self.decision(g,ids=[]))
        b,_,br=dp._share(g,self.count,self.cur)
        self.assertEqual(r(out),br(b));self.assertFalse(a["pruned"])
    def test_single_field_projection_valid_empty_object(self):
        g=self.graph({"extras":list(range(100))})
        out,a,r=dp.prune(g,self.count,self.cur,decision=self.decision(g))
        self.assertFalse(a["pruned"])
        self.assertTrue(dp.audit_record_graph(out)["ok"])
    def test_global_bound_ignores_proposal_order(self):
        fs=[{"id":"b","tokens":100,"eligible":True},{"id":"a","tokens":100,"eligible":True},{"id":"x","tokens":999,"eligible":False}]
        self.assertEqual(dp.bounded_selection(["b","a"],fs,1),["a"])
        self.assertEqual(dp.bounded_selection(["a","b"],fs,1),["a"])
        with self.assertRaises(ValueError):dp.bounded_selection(["x"],fs,1)
    def test_selector_packet_has_no_unseen_data_or_payload_dump(self):
        g=self.graph({"distance":9,"cities":["town"]*1000})
        p=dp.packet(g,self.count,self.cur,[])
        self.assertLess(len(json.dumps(p)),8000)
        self.assertNotIn("expected_answer",p);self.assertNotIn("task_id",p)
class ExistingEvidenceTests(unittest.TestCase):
    setUp=ProjectionTests.setUp
    graph=ProjectionTests.graph
    decision=ProjectionTests.decision
    def repeated(self, value, second=None, args1=None, args2=None, tool2="observe", raw=False):
        h=[{"role":"user","content":"Inspect object A."}]
        for i,(v,args,name) in enumerate([(value,args1,"observe"),(value if second is None else second,args2,tool2)]):
            h += [{"type":"function_call","name":name,"call_id":str(i),"arguments":json.dumps(args or {})},
                  {"type":"function_call_output","call_id":str(i),"output":v if raw else json.dumps(v)}]
        cfg=ExperimentConfig();cfg.delivery={"mode":"replace","role":"assistant"}
        return prepare(h,cfg,self.count)["graph"]
    def test_short_digit_punctuation_aliases(self):
        for field in ["MA20","MA(20)","ma_20","ＭＡ（２０）"]:
            for name in ["MA20","MA(20)","ma 20","MA_20"]:
                self.assertTrue(dp.field_referenced(field,[{"role":"user","content":"Compute "+name+"."}]),(field,name))
        for name in ["MA200","MA2","SMA20"]:
            self.assertFalse(dp.field_referenced("MA(20)",[{"role":"user","content":name}]),name)
        self.assertTrue(dp.field_referenced("x",[{"role":"user","content":"Use x."}]))
        self.assertFalse(dp.field_referenced("x",[{"role":"user","content":"extra"}]))
    def test_required_ma_never_eligible_even_with_duplicate(self):
        g=self.repeated({"MA(20)":list(range(90)),"price":12})
        cur=[{"role":"user","content":"Average price and MA20."}]
        c=dp.catalog(g,self.count,cur)
        self.assertFalse(c["candidates"])
        for x in c["fields"]:
            if x["key"]=="MA(20)":self.assertIn("explicit_current_field_reference",x["protected_reasons"])
    def test_actual_later_exact_tool_field_required_and_retained(self):
        g=self.repeated({"distance":123,"extras":list(range(90))})
        before=deepcopy(g);c=dp.catalog(g,self.count,self.cur)
        self.assertEqual(len(c["candidates"]),1)
        old=c["candidates"][0];w=old["replacement_evidence"][0]
        latest=next(x for x in c["fields"] if x["id"]==w["member_id"])
        self.assertFalse(latest["eligible"])
        self.assertEqual(w["kind"],"exact_tool_field")
        out,a,render=dp.prune(g,self.count,self.cur,decision=self.decision(g))
        self.assertEqual(g,before);self.assertTrue(dp.audit_record_graph(out)["ok"])
        if a["pruned"]:self.assertEqual(a["replacement_evidence"][old["id"]],w)
    def test_different_scope_tool_changed_value_and_failure_do_not_substitute(self):
        v={"extras":list(range(90))}
        for kw in [dict(args1={"object":"A"},args2={"object":"B"}),
                   dict(tool2="other"),dict(second={"extras":list(range(89))}),
                   dict(second=dict(v,error="failed"))]:
            g=self.repeated(v,**kw)
            self.assertEqual(dp.catalog(g,self.count,self.cur)["candidates"],[],kw)
    def test_prefix_examples_summary_and_same_id_are_not_replacements(self):
        v={"extras":list(range(90))}
        for second in [{"extras":list(range(3))},{"extras_mean":44.5},{"id":"A","summary":"extras available"}]:
            self.assertEqual(dp.catalog(self.repeated(v,second=second),self.count,self.cur)["candidates"],[])
    def test_literal_difference_not_semantic_assumption(self):
        a='{"extras":['+','.join(['1.0']*90)+']}'
        b='{"extras":['+','.join(['1']*90)+']}'
        self.assertEqual(dp.catalog(self.repeated(a,second=b,raw=True),self.count,self.cur)["candidates"],[])
    def test_forged_replacement_cannot_authorize_drop(self):
        g=self.graph({"MA(20)":list(range(90))})
        c=dp.catalog(g,self.count,self.cur);target=next(x for x in c["fields"] if x["key"]=="MA(20)")
        d=self.decision(g,ids=[target["id"]]);d["replacement_evidence"]={target["id"]:{"kind":"future_mean","value":44.5}}
        with self.assertRaises(ValueError):dp.prune(g,self.count,self.cur,decision=d)
if __name__=="__main__":unittest.main()
