import copy,itertools,json,unittest
from cs769.models.edits.state_effects import StateAccumulator, vehicle_patch, DOORS
from cs769.models.edits import observation_state_components as ed
from cs769.base.config import ExperimentConfig
from cs769.tasks.memory import prepare
from cs769.cli import counter

class StateEffectsTests(unittest.TestCase):
    def test_objects_and_partial_attributes_are_independent(self):
        s=StateAccumulator();s.update("carA",{("doorStatus","driver"):"unlocked",("fuelLevel",):15},"r1")
        s.update("carB",{("doorStatus","driver"):"unlocked"},"r2")
        s.update("carA",{("doorStatus","driver"):"locked"},"r3")
        self.assertEqual(s.observed("carA"),{"doorStatus":{"driver":"locked"},"fuelLevel":15})
        self.assertEqual(s.observed("carB")["doorStatus"]["driver"],"unlocked")
        self.assertEqual(s.edges[0]["attribute"],["doorStatus","driver"])
        self.assertEqual((s.edges[0]["old"],s.edges[0]["new"]),("r1","r3"))

    def test_all_partial_lock_unlock_subsets_against_tool_implementation(self):
        import importlib
        m=importlib.import_module("bfcl_eval.eval_checker.multi_turn_eval.func_source_code.vehicle_control")
        cls=next(x for x in vars(m).values() if isinstance(x,type) and hasattr(x,"lockDoors"))
        for bits in itertools.product((False,True),repeat=4):
            initial={d:"locked" if b else "unlocked" for d,b in zip(DOORS,bits)}
            for n in range(1,5):
                for subset in itertools.combinations(DOORS,n):
                    for unlock in (False,True):
                        obj=cls.__new__(cls);obj.doorStatus=copy.deepcopy(initial);obj.remainingUnlockedDoors=sum(v=="unlocked" for v in initial.values())
                        s=StateAccumulator();s.update("vehicle",vehicle_patch("displayCarStatus",{"option":"doors"},{"doorStatus":initial})[0],"read")
                        args={"unlock":unlock,"door":list(subset)};v=obj.lockDoors(**args)
                        patch=vehicle_patch("lockDoors",args,v);self.assertIsNotNone(patch)
                        s.update("vehicle",patch[0],"write")
                        self.assertEqual(s.observed("vehicle")["doorStatus"],obj.doorStatus)
                        self.assertEqual(s.observed("vehicle")["remainingUnlockedDoors"],obj.remainingUnlockedDoors)
                        self.assertNotIn("lockStatus",s.observed("vehicle"))

    def test_unknown_doors_not_invented_and_contradictions_rejected(self):
        s=StateAccumulator();s.update("vehicle",vehicle_patch("lockDoors",{"unlock":False,"door":["driver"]},{"lockStatus":"locked","remainingUnlockedDoors":3})[0],"r")
        self.assertEqual(s.observed("vehicle")["doorStatus"],{"driver":"locked"})
        self.assertIsNone(vehicle_patch("lockDoors",{"unlock":False,"door":list(DOORS)},{"lockStatus":"locked","remainingUnlockedDoors":2}))
        self.assertIsNone(vehicle_patch("displayCarStatus",{"option":"doors"},{"doorStatus":{"roof":"locked"}}))
        self.assertIsNone(vehicle_patch("startEngine",{"ignitionMode":"STOP"},{"error":"doors"}))

    def graph(self,rows):
        h=[{"role":"user","content":"Prepare the vehicle."}]
        for i,(tool,args,value) in enumerate(rows):
            h.extend([{"type":"function_call","name":tool,"arguments":json.dumps(args),"call_id":str(i)},
                      {"type":"function_call_output","call_id":str(i),"output":json.dumps(value)}])
        return prepare(h,ExperimentConfig(),counter("o200k_base"))["graph"]

    def rows(self):
        return [("displayCarStatus",{"option":"doors"},{"doorStatus":{d:"unlocked" for d in DOORS}}),
                ("lockDoors",{"unlock":False,"door":list(DOORS)},{"lockStatus":"locked","remainingUnlockedDoors":0}),
                ("pressBrakePedal",{"pedalPosition":1},{"brakePedalStatus":"pressed","brakePedalForce":1000}),
                ("startEngine",{"ignitionMode":"START"},{"engineState":"running","fuelLevel":15,"batteryVoltage":12.8})]

    def test_read_write_graph_keeps_latest_and_source_unchanged(self):
        g=self.graph(self.rows());original=copy.deepcopy(g);a=ed.pack_state(g)
        self.assertTrue(all(v=="locked"for v in a["component"]["observed"]["doorStatus"].values()))
        out,audit,render=ed.apply(g,a,counter("o200k_base"))
        self.assertEqual(g,original);self.assertTrue(audit["retained_evidence_exact"])
        self.assertEqual(len([e for e in audit["state_dependencies"]if e["attribute"][0]=="doorStatus"]),4)
        self.assertNotIn('"lockStatus"',render(out))

    def test_error_side_effect_and_later_write_block_contraction(self):
        rows=self.rows();rows.insert(2,("startEngine",{"ignitionMode":"STOP"},{"error":"brake needed"}))
        self.assertIsNone(ed.pack_state(self.graph(rows)))
        rows=self.rows()+[("lockDoors",{"unlock":True,"door":["driver"]},{"lockStatus":"unlocked","remainingUnlockedDoors":1})]
        self.assertIsNone(ed.pack_state(self.graph(rows)))

    def test_start_error_is_retained_instead_of_declared_removed(self):
        rows=self.rows();rows.insert(1,("startEngine",{"ignitionMode":"START"},{"error":"doors unlocked"}))
        g=self.graph(rows);a=ed.pack_state(g);self.assertEqual(len(a["errors_retained"]),1)
        out,audit,render=ed.apply(g,a,counter("o200k_base"));self.assertIn("doors unlocked",render(out))

if __name__=="__main__":unittest.main()
