import unittest,tempfile,time
from pathlib import Path
from cs769.base.budget import PersistentBudget, BudgetExceeded
class GuardTests(unittest.TestCase):
 def test_deadline_prevents_reservation(self):
  with tempfile.TemporaryDirectory() as d:
   b=PersistentBudget(Path(d)/"b.json",1,{"input":2,"output":8})
   with b.locked() as x:x["not_after_unix"]=time.time()-1
   with self.assertRaises(BudgetExceeded):b.reserve({"model":"gpt-4.1","messages":[],"max_tokens":10})
   with b.locked() as x:self.assertEqual(x["requests"],{})
 def test_stage_cap_retains_uncertain_and_global_cap(self):
  with tempfile.TemporaryDirectory() as d:
   b=PersistentBudget(Path(d)/"b.json",1,{"input":2,"output":8})
   with b.locked() as x:x.update(active_stage="dev",stage_limits={"dev":0.006})
   k=b.reserve({"model":"gpt-4.1","messages":[],"max_tokens":10});b.uncertain(k)
   with self.assertRaises(BudgetExceeded):b.reserve({"model":"gpt-4.1","messages":[],"max_tokens":10})
   with b.locked() as x:self.assertEqual(x["requests"][k]["stage"],"dev");self.assertEqual(x["requests"][k]["status"],"uncertain")
