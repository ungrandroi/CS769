import unittest,json
from copy import deepcopy
from cs769.base.config import ExperimentConfig
from cs769.tasks.memory import prepare
from cs769.cli import counter
from cs769.models.edits.observation_pruning import candidates, prune
from cs769.models.edits.record_edits import evidence

PROSE='The supporting narrative discusses organization and reliable service without changing the account conditions. '*30

def graph(payload=None,later=None,tool='get_ticket',tail=True):
    payload=payload if payload is not None else {'ticket_id':1,'status':'open','amount':12.5,'notes':PROSE}
    h=[{'role':'user','content':'Inspect the first item, then another item.'},
       {'type':'function_call','call_id':'a','name':tool,'arguments':'{"ticket_id":1}'},
       {'type':'function_call_output','call_id':'a','output':json.dumps(payload)}]
    if tail:h += [{'type':'function_call','call_id':'b','name':tool,'arguments':json.dumps(later or {'ticket_id':2})},
                  {'type':'function_call_output','call_id':'b','output':'{"ticket_id":2,"status":"open"}'}]
    h += [{'role':'assistant','content':'Checked.'}]
    cfg=ExperimentConfig();cfg.delivery={'mode':'replace','role':'assistant'}
    return prepare(h,cfg,counter('o200k_base'),next_messages=[{'role':'user','content':'Proceed.'}])['graph']

class PruningTests(unittest.TestCase):
    def setUp(self):self.count=counter('o200k_base')
    def test_retains_calls_status_numbers_ids_and_source(self):
        g=graph();old=deepcopy(g);out,a=prune(g,self.count,'Proceed.')
        self.assertEqual(g,old);self.assertGreater(a['saved_tokens'],50)
        before=evidence(g)['evidence_view'];after=evidence(out)['evidence_view']
        self.assertEqual(before['edges'],after['edges'])
        changes=[(x,y)for x,y in zip(before['nodes'],after['nodes'])if x!=y]
        self.assertEqual(len(changes),1)
        output=json.loads(next(f['value']for f in changes[0][1]['fields']if f['field']=='output'))
        self.assertEqual(output,{'ticket_id':1,'status':'open','amount':12.5})
    def test_last_observation_is_not_deleted(self):
        self.assertFalse(candidates(graph(tail=False),'Proceed.',count=self.count)[0])
    def test_only_content_source_is_protected(self):
        self.assertFalse(candidates(graph({'notes':PROSE}),'Proceed.',count=self.count)[0])
        self.assertFalse(candidates(graph({'file_name':'a.txt','content':PROSE}),'Proceed.',count=self.count)[0])
    def test_requested_or_later_copied_text_is_protected(self):
        self.assertFalse(candidates(graph(),'Explain the notes.',count=self.count)[0])
        self.assertFalse(candidates(graph(later={'ticket_id':2,'message':PROSE}),'Proceed.',count=self.count)[0])
    def test_nested_scalar_values_survive(self):
        g=graph({'ticket_id':1,'details':{'amount':12.5,'status':'open','notes':PROSE}})
        out,a=prune(g,self.count,'Proceed.')
        outputs=[json.loads(f['value'])for n in evidence(out)['evidence_view']['nodes']if n['category']=='tool_result'for f in n['fields']if f['field']=='output']
        self.assertEqual(outputs[0],{'ticket_id':1,'details':{'amount':12.5,'status':'open'}})
    def test_no_tool_name_allowlist(self):
        self.assertEqual(len(candidates(graph(tool='unseen_reader'),'Proceed.',count=self.count)[0]),1)
    def test_editor_is_reachable_in_unified_pipeline(self):
        from cs769.base.registry import EDITORS
        self.assertIn('prune_observation',EDITORS)
    def test_numeric_container_is_not_removed(self):
        g=graph({'ticket_id':1,'state':{'notes':PROSE,'amount':42}})
        actions,_=candidates(g,'Proceed.',count=self.count)
        self.assertTrue(actions);self.assertEqual({a['key']for a in actions},{'notes'})

if __name__=='__main__':unittest.main()
