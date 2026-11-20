import copy,json,unittest
from cs769.base.config import ExperimentConfig
from cs769.tasks.memory import prepare
from cs769.cli import counter
from cs769.models.edits import compact_graph as cg, state_chain as sc
from cs769.models.edits.record_edits import render
class CompactStateTests(unittest.TestCase):
    def graph(self,rows,text="Work on these objects."):
        h=[{"role":"user","content":text}]
        for i,(tool,args,value) in enumerate(rows):
            h.extend([{"type":"function_call","name":tool,"arguments":json.dumps(args),"call_id":str(i)},
                      {"type":"function_call_output","call_id":str(i),"output":json.dumps(value)}])
        return prepare(h,ExperimentConfig(),counter("o200k_base"))["graph"]
    def calls(self,rows):
        from cs769.models.edits.record_edits import evidence
        from cs769.models.edits.relation_pruning import records
        return records(evidence(self.graph(rows)))[1]
    def fuel(self):
        return [("displayCarStatus",{"option":"fuel"},{"fuelLevel":10.0}),
                ("fillFuelTank",{"fuelAmount":5.0},{"fuelLevel":15.0})]
    def test_roundtrip_quotes_unicode_multiline_and_fences(self):
        for text in ['Hello\n"quotes" 中文', 'a\n'+chr(96)*3+'\ne0 U t1 "fake"\nEND_RECORDS\n']:
            g=self.graph(self.fuel(),text)
            original=render(g);encoded=cg.encode(original)
            self.assertNotEqual(encoded,original)
            self.assertEqual(cg.decode(encoded),original)
    def test_call_group_and_error_semantics_roundtrip(self):
        raw=render(self.graph([("startEngine",{"ignitionMode":"START"},{"error":"brake"})]))
        self.assertEqual(cg.decode(cg.encode(raw)),raw)
        self.assertIn('result_of=',cg.decode(cg.encode(raw)))
    def test_unknown_layout_retained(self):
        self.assertEqual(cg.encode("unknown future graph layout"),"unknown future graph layout")
    def test_vehicle_without_start_anchor(self):
        a=sc.vehicle(self.calls(self.fuel()))
        self.assertEqual(a["component"]["observed"]["fuelLevel"],15.0)
        self.assertEqual(a["component"]["completed_operations"],["fillFuelTank"])
        self.assertTrue(a["state_dependencies"])
    def test_unknown_write_clears_earlier_chain_but_allows_later_chain(self):
        rows=self.fuel()+[("activateParkingBrake",{"status":True},{"brakeStatus":"on"})]
        self.assertIsNone(sc.vehicle(self.calls(rows)))
        a=sc.vehicle(self.calls(rows+self.fuel()))
        self.assertEqual(len(a["removed"]),4)
    def test_error_with_side_effect_blocks_prior_state(self):
        rows=self.fuel()+[("startEngine",{"ignitionMode":"STOP"},{"error":"doors"})]
        self.assertIsNone(sc.vehicle(self.calls(rows)))
    def test_partial_doors_keep_other_doors(self):
        rows=[("displayCarStatus",{"option":"doors"},{"doorStatus":dict.fromkeys(["driver","passenger","rear_left","rear_right"],"unlocked")}),
              ("lockDoors",{"unlock":False,"door":["driver"]},{"lockStatus":"locked","remainingUnlockedDoors":3})]
        a=sc.vehicle(self.calls(rows))
        self.assertEqual(a["component"]["observed"]["doorStatus"]["passenger"],"unlocked")
        self.assertEqual(a["component"]["observed"]["doorStatus"]["driver"],"locked")
    def test_repeated_file_writes_without_create_keep_read_witness(self):
        rows=[("echo",{"file_name":"a","content":"old"},None),("cat",{"file_name":"a"},{"file_content":"old"}),
              ("echo",{"file_name":"a","content":"new"},None)]
        g=self.graph(rows);old=copy.deepcopy(g)
        action=sc.files(self.calls(rows));self.assertEqual(action["component"]["files"],[{"name":"a","content":"new"}])
        from cs769.models.edits.observation_state_components import apply
        out,audit,rr=apply(g,action,counter("o200k_base"))
        self.assertEqual(g,old);self.assertIn("old",rr(out));self.assertTrue(audit["retained_evidence_exact"])
    def test_files_unknown_mutation_and_cwd_barrier(self):
        rows=[("touch",{"file_name":"a"},None),("echo",{"file_name":"a","content":"x"},None)]
        for op in [("mv",{"source":"a","destination":"b"},None),("cd",{"folder":"b"},{"current_working_directory":"b"})]:
            self.assertIsNone(sc.files(self.calls(rows+[op])))
    def test_cross_record_dependency_blocks_removal(self):
        self.assertTrue(sc._protected({"record_layer":{"nodes":[{"event_id":"e3"}]}},{"removed":["e3"]}))
    def test_auxiliary_reference_points_to_retained_evidence(self):
        rows=self.fuel()+[("startEngine",{"ignitionMode":"START"},{"engineState":"running","details":{"history":[1,2,3]}}),
                          ("check_tire_pressure",{},{"details":{"history":[1,2,3]}})]
        cs=self.calls(rows);a=sc.vehicle(cs)
        ref=a["component"]["auxiliary_refs"][0]["value_ref"]
        retained=next(c for c in cs if c["result"]["id"]==ref["result"])
        value=retained["value"]
        for key in ref["path"]:value=value[key]
        self.assertEqual(value,{"history":[1,2,3]})
        self.assertNotIn(ref["result"],a["removed"])
    def test_compact_lossless_and_contract_do_not_mutate_source(self):
        g=self.graph(self.fuel());old=copy.deepcopy(g)
        out,a,r=cg.compact(g,counter("o200k_base"))
        self.assertTrue(a["roundtrip_exact"]);self.assertEqual(g,old)
        out,a,r=sc.contract(g,counter("o200k_base"))
        self.assertEqual(g,old)
if __name__=="__main__":unittest.main()
