import unittest
from cs769.base.batch import gate_reason
class GateTests(unittest.TestCase):
 def test_pending_candidate_is_not_failure(self):
  self.assertIsNone(gate_reason([{'task':'a','arm':'full','passed':True}],{'candidate':'edit','baselines':['full']}))
 def test_checks_each_case_not_only_aggregate(self):
  rows=[{'task':'a','arm':'full','passed':True},{'task':'a','arm':'edit','passed':False},{'task':'b','arm':'edit','passed':True}]
  self.assertEqual(gate_reason(rows,{'candidate':'edit','baselines':['full']})['task'],'a')
 def test_common_failure_not_regression(self):
  rows=[{'task':'a','arm':'full','passed':False},{'task':'a','arm':'edit','passed':False}]
  self.assertIsNone(gate_reason(rows,{'candidate':'edit','baselines':['full']}))
 def test_control_gate_stops_before_candidate(self):
  self.assertEqual(gate_reason([{'task':'a','arm':'full','passed':False}],{'require_pass':['full']})['reason'],'control_failed')
