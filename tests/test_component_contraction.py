import json, unittest
from copy import deepcopy
from cs769.base.config import ExperimentConfig
from cs769.tasks.memory import prepare
from cs769.cli import counter
from cs769.models.edits import component_contraction as cc
from cs769.models.edits.record_edits import evidence

class ComponentTests(unittest.TestCase):
    def setUp(self):
        self.count=counter("o200k_base")
        self.current=[{"role":"user","content":"Fetch the order I just placed."}]
    def graph(self, rows):
        h=[{"role":"user","content":"Complete the recorded operations."}]
        for i,(name,args,value) in enumerate(rows):
            h.extend([{"type":"function_call","name":name,"call_id":str(i),"arguments":json.dumps(args)},
                      {"type":"function_call_output","call_id":str(i),"output":json.dumps(value)}])
        c=ExperimentConfig();c.delivery={"mode":"replace","role":"assistant"}
        return prepare(h,c,self.count)["graph"]
    def stock(self, symbol="ABC", price=12):
        return self.graph([
          ("get_available_stocks",{"sector":"tech"},{"stock_list":["ABC","DEF","GHI"]}),
          ("get_stock_info",{"symbol":"ABC"},{"price":12,"volume":150,"MA(20)":list(range(100))}),
          ("place_order",{"symbol":symbol,"price":price,"amount":2,"order_type":"Buy"},
           {"order_id":123,"status":"Pending","amount":2,"price":price})])
    def test_order_boundary_keeps_receipt_scalars_and_source_immutable(self):
        g=self.stock();before=deepcopy(g);a=next(x for x in cc.candidates(g,self.current) if x["kind"]=="successful_order_boundary")
        self.assertEqual(len(a["delete_events"]),4)
        out,audit,render=cc.apply(g,a,self.count)
        self.assertEqual(g,before);self.assertTrue(audit["retained_evidence_exact"])
        self.assertTrue(any(x["field"]=="MA(20)" for x in audit["loss_witnesses"]))
        self.assertNotIn("source_graph",out["component_contraction"])
        self.assertEqual(out["component_contraction"]["facts"][0]["observed_stock_scalars"]["volume"],150)
        self.assertIn("place_order",render(out));self.assertIn('"order_id":123',render(out))
    def test_same_price_different_symbol_and_wrong_order_price_do_not_join(self):
        for g in [self.stock(symbol="DEF"),self.stock(price=99)]:
            self.assertFalse(any(x["kind"]=="successful_order_boundary" for x in cc.candidates(g,self.current)))
    def test_ma_alias_requirement_prevents_array_deletion(self):
        for q in ["Use MA20 to compute the average.","Use MA(20).","Get moving averages."]:
            self.assertFalse(cc.candidates(self.stock(),[{"role":"user","content":q}]))
    def test_live_array_used_elsewhere_blocks_contraction(self):
        g=self.graph([
          ("get_stock_info",{"symbol":"ABC"},{"price":12,"MA(20)":list(range(100))}),
          ("place_order",{"symbol":"ABC","price":12},{"order_id":3}),
          ("mean",{"numbers":list(range(100))},{"result":49.5})])
        self.assertFalse(cc.candidates(g,self.current))
    def test_booking_requires_same_itinerary_and_confirmed_receipt(self):
        scope={"travel_from":"SFO","travel_to":"FRA","travel_date":"2026-01-01","travel_class":"economy"}
        for changed,success in [(True,True),(False,False),(False,True)]:
            args=dict(scope,travel_to="LHR") if changed else scope
            g=self.graph([("get_flight_cost",scope,{"travel_cost_list":list(range(100))}),
                          ("book_flight",dict(args,card_id="card-ref"),{"booking_status":success,"booking_id":"b"})])
            choices=cc.candidates(g,[{"role":"user","content":"Retrieve my invoice."}])
            self.assertEqual(bool(choices),not changed and success)
            if choices:
                out,a,r=cc.apply(g,choices[0],self.count)
                self.assertIn("card-ref",r(out))  # Original payment binding remains.
    def test_partial_door_write_does_not_drop_full_snapshot(self):
        g=self.graph([("displayCarStatus",{"option":"doors"},{"doorStatus":dict.fromkeys(cc.DOORS,"unlocked")}),
          ("lockDoors",{"unlock":False,"door":["driver"]},{"lockStatus":"locked","remainingUnlockedDoors":3})])
        self.assertFalse(cc.candidates(g,[{"role":"user","content":"Start engine."}]))
    def test_full_door_write_but_inconsistent_remaining_count_rejected(self):
        g=self.graph([("displayCarStatus",{"option":"doors"},{"doorStatus":dict.fromkeys(cc.DOORS,"unlocked")}),
          ("lockDoors",{"unlock":False,"door":sorted(cc.DOORS)},{"lockStatus":"locked","remainingUnlockedDoors":1})])
        self.assertFalse(cc.candidates(g,[{"role":"user","content":"Start engine."}]))
    def test_old_door_question_keeps_old_state(self):
        g=self.graph([("displayCarStatus",{"option":"doors"},{"doorStatus":dict.fromkeys(cc.DOORS,"unlocked")}),
          ("lockDoors",{"unlock":False,"door":sorted(cc.DOORS)},{"lockStatus":"locked","remainingUnlockedDoors":0})])
        cur=[{"role":"user","content":"Which doors were unlocked before?"}]
        self.assertFalse(cc.candidates(g,cur))
        new=[{"role":"user","content":"Start engine."}]
        a=cc.candidates(g,new)[0];out,_,render=cc.apply(g,a,self.count)
        layer=out["component_contraction"]
        self.assertEqual(set(layer["facts"][0]["doors"].values()),{"locked"})
        self.assertEqual(layer["facts"][0]["confirmed_by"],layer["anchor_in_retained_graph"])
    def test_file_selection_requires_same_scope_and_retains_content(self):
        rows=[("cd",{"folder":"tmp"},{"current_working_directory":"tmp"}),
              ("ls",{},{"current_directory_content":["a.txt","b.txt","c.txt"]}),
              ("cat",{"file_name":"c.txt"},{"file_content":"necessary exact body"})]
        g=self.graph(rows);cur=[{"role":"user","content":"Copy the last file with the same content."}]
        a=cc.candidates(g,cur)[0];out,_,render=cc.apply(g,a,self.count)
        self.assertIn("necessary exact body",render(out))
        self.assertEqual(out["component_contraction"]["facts"][0]["cwd_observed"],"tmp")
        g=self.graph(rows[:2]+[("cd",{"folder":"other"},{"current_working_directory":"other"})]+rows[2:])
        self.assertFalse(any(x["kind"]=="selected_file_boundary" for x in cc.candidates(g,cur)))
    def test_count_is_verified_and_does_not_relabel_unexecuted_calculation(self):
        for reported in [2,999]:
            g=self.graph([("cat",{"file_name":"f"},{"file_content":"hello world"}),
                          ("wc",{"file_name":"f","mode":"w"},{"count":reported,"type":"words"})])
            cur=[{"role":"user","content":"Store the word count."}]
            self.assertEqual(bool(cc.candidates(g,cur)),reported==2)
    def test_failure_records_outside_component_retained(self):
        g=self.graph([("cat",{"file_name":"missing"},{"error":"not found"}),
                      ("estimate_distance",{"cityA":"a","cityB":"b"},{"distance":10,"intermediaryCities":["x"]*100})])
        cur=[{"role":"user","content":"Start engine."}]
        a=cc.candidates(g,cur)[0];out,_,render=cc.apply(g,a,self.count)
        self.assertIn("not found",render(out))
        self.assertEqual(out["component_contraction"]["facts"][0]["result"],{"distance":10})
    def test_current_route_question_declines_distance_edit(self):
        g=self.graph([("estimate_distance",{"cityA":"a","cityB":"b"},{"distance":10,"intermediaryCities":["x"]*100})])
        self.assertFalse(cc.candidates(g,[{"role":"user","content":"List the intermediary cities."}]))
    def test_tampered_component_rejected(self):
        g=self.stock();a=cc.candidates(g,self.current)[0]
        a["facts"][0]["price"]=999
        with self.assertRaises(ValueError):cc.apply(g,a,self.count)

if __name__=="__main__":unittest.main()
