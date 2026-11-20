"""Counterexamples for state and evidence policy, without model calls."""
import json
import unittest
from copy import deepcopy
from cs769.cli import counter
from cs769.base.config import ExperimentConfig
from cs769.tasks.memory import prepare
from cs769.models.edits import general_pruning as gp
from cs769.models.edits.record_edits import evidence

def graph(calls):
    h=[{"role":"user","content":"Carry out the operations."}]
    for i,(name,args,value) in enumerate(calls):
        h += [{"type":"function_call","call_id":str(i),"name":name,"arguments":json.dumps(args)},
              {"type":"function_call_output","call_id":str(i),"output":json.dumps(value)}]
    c=ExperimentConfig();c.delivery={"mode":"replace","role":"assistant"}
    return prepare(h,c,counter("o200k_base"))["graph"]

class GeneralTests(unittest.TestCase):
    def setUp(self):
        self.count=counter("o200k_base")
        self.doors={k:"unlocked" for k in gp.DOORS}
    def vehicle(self,extra=None):
        v={"doorStatus":self.doors}
        if extra:v.update(extra)
        return [("displayCarStatus",{"option":"doors"},v),
                ("lockDoors",{"unlock":False,"door":sorted(gp.DOORS)},{"lockStatus":"locked","remainingUnlockedDoors":0})]
    def test_success_and_source_immutable(self):
        g=graph(self.vehicle());before=deepcopy(g)
        out,a,r=gp.prune(g,self.count,"Start the engine",min_saved_tokens=1)
        self.assertTrue(a["pruned"]);self.assertEqual(g,before)
        self.assertIn("lockDoors",r(out));self.assertNotIn("displayCarStatus",r(out))
    def test_other_fields_remain_exact(self):
        g=graph(self.vehicle({"metadata":"Unique metadata must stay"}))
        a=gp.state_candidates(g)[0];out,audit,_=gp.apply_state(g,a,self.count)
        text=gp.rp.render(out)
        self.assertIn("Unique metadata must stay",text)
        self.assertIn("displayCarStatus",text)
        self.assertEqual(a["remove_keys"],["doorStatus"])
    def test_failed_operation_is_not_evidence(self):
        c=self.vehicle();c[-1]=(c[-1][0],c[-1][1],{"error":"failed"})
        self.assertEqual(gp.state_candidates(graph(c)),[])
    def test_partial_update_rejected(self):
        c=self.vehicle();c[-1][1]["door"]=["driver"]
        self.assertEqual(gp.state_candidates(graph(c)),[])
    def test_unknown_operation_is_barrier(self):
        c=self.vehicle();c.insert(1,("select_other_vehicle",{},{"success":True}))
        self.assertEqual(gp.state_candidates(graph(c)),[])
    def test_parallel_calls_rejected(self):
        from unittest.mock import patch
        g=graph(self.vehicle())
        ns,calls=gp.rp.records(gp.rp.evidence(g))
        calls[-1]["call"]["call_group"]=calls[0]["call"]["call_group"]
        with patch.object(gp.rp, "records", return_value=(ns,calls)):
            self.assertEqual(gp.state_candidates(g),[])
    def test_historical_question_keeps_evidence(self):
        g=graph(self.vehicle())
        for query in ["What was the door status before locking?", "Compare the earlier and current status.", "之前车门是什么状态？"]:
            out,a,r=gp.prune(g,self.count,query,min_saved_tokens=1)
            self.assertFalse(a["pruned"]);self.assertIn("unlocked",r(out))
    def test_relative_move_same_frame(self):
        c=[("find",{"name":"a.txt"},{"matches":["./a.txt"]}),
           ("mv",{"source":"a.txt","destination":"Reports"},{"result":"'a.txt' moved to 'Reports/a.txt'"})]
        g=graph(c);a=gp.state_candidates(g)
        self.assertEqual(len(a),1)
        self.assertEqual(a[0]["information_class"],"redundant_location_evidence")
        c.insert(1,("cd",{"folder":"other"},{"current_working_directory":"other"}))
        self.assertEqual(gp.state_candidates(graph(c)),[])
    def test_multiple_matches_and_copy_rejected(self):
        c=[("find",{"name":"a.txt"},{"matches":["./a.txt","./other/a.txt"]}),
           ("mv",{"source":"a.txt","destination":"Reports"},{"result":"'a.txt' moved to 'Reports/a.txt'"})]
        self.assertEqual(gp.state_candidates(graph(c)),[])
        c[0][2]["matches"]=["./a.txt"]
        c[-1]=("cp",c[-1][1],{"result":"'a.txt' copied to 'Reports/a.txt'"})
        self.assertEqual(gp.state_candidates(graph(c)),[])
    def test_stale_action_rejected(self):
        g=graph(self.vehicle());a=gp.state_candidates(g)[0]
        a["source_graph_sha256"]="stale"
        with self.assertRaises(ValueError):gp.apply_state(g,a,self.count)
    def test_fuel_is_recoverable_not_declared_lossy(self):
        g=graph([("displayCarStatus",{"option":"fuel"},{"fuelLevel":10}),
                 ("fillFuelTank",{"fuelAmount":5},{"fuelLevel":15})])
        self.assertEqual(gp.state_candidates(g)[0]["information_class"],"arithmetically_recoverable_observation")
    def test_no_candidate_falls_back_to_exact_full(self):
        g=graph([("pwd",{},{"current_working_directory":"/x"})])
        out,a,r=gp.prune(g,self.count,"Continue")
        self.assertFalse(a["pruned"]);self.assertEqual(r(out),gp.full_render(g))
