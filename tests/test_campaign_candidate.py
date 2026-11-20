import json,tempfile,unittest
from pathlib import Path
from cs769.tasks.campaign import Campaign
class CandidateArmTests(unittest.TestCase):
 def test_report_uses_configured_edit_and_preserves_both_losses(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);c=Campaign.__new__(Campaign);c.root=root
   c.auth={'candidate_arm':'pruned_g9','candidate_pools':{'vehicle':['case']},'arms':['identity','g9_full','pruned_g9'],'hard_cap_usd':15,'operational_prestop_usd':14}
   (root/'rates.json').write_text(json.dumps({'input':2,'output':8,'cached_input':0.5,'cache_write':2}))
   for arm,ok,calls in [('identity',True,2),('g9_full',True,3),('pruned_g9',False,5)]:
    d=root/'runs'/'case'/arm;d.mkdir(parents=True)
    u={'input_tokens':100,'output_tokens':10,'cached_input_tokens':0,'cache_write_tokens':0,'requests':1,'tool_calls':calls,'first_input_tokens':100,'total_tokens':110}
    (d/'manifest.json').write_text(json.dumps({'status':'complete','usage_live':u,'checkpoint_sha256':'same'}))
    (d/'score.json').write_text(json.dumps({'passed':ok}))
   report=c.report()
   self.assertEqual(report['complete_triples'],1)
   self.assertEqual(report['new_losses'],[{'task':'case','baseline':'identity'},{'task':'case','baseline':'g9_full'}])
   self.assertEqual(report['groups']['all']['identity']['net_added_tool_calls'],3)
   self.assertEqual(report['groups']['all']['g9_full']['positive_added_tool_calls'],2)

   # A completed pair must pause the campaign before the third arm runs.
   m=root/'runs'/'case'/'identity'/'manifest.json'
   incomplete=json.loads(m.read_text());incomplete['status']='running'
   m.write_text(json.dumps(incomplete))
   partial=c.report()
   self.assertEqual(partial['complete_triples'],0)
   self.assertEqual(partial['new_losses'],[{'task':'case','baseline':'g9_full'}])
   candidate_manifest=root/'runs'/'case'/'pruned_g9'/'manifest.json'
   mismatch=json.loads(candidate_manifest.read_text());mismatch['checkpoint_sha256']='other'
   candidate_manifest.write_text(json.dumps(mismatch))
   with self.assertRaises(AssertionError):c.report()
if __name__=='__main__':unittest.main()
