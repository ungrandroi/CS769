import unittest
from copy import deepcopy
from v2_provenance_dedup import compact_graph,restore_graph,encode,decode,confirmation,evidence
from graph_memory_serialization import normalize

def fixture():
    e={'id':'a1','category':'event','step':1,'call_id':'c1','tool':'ls','arguments':{},'output_raw':'["D","f1"]',
       'call_evidence':'m1','output_evidence':'m2','rule':'r:ls','status':'success','error':None}
    f={'id':'f1','category':'fact','subject':'o1','predicate':'exists','value':True,'first_observed_at':1,'retired_at':None,'retired_by':None,'retired_reason':None,'confirmations':[confirmation(e)]}
    g={'nodes':[{'id':'o1','category':'object'},e,f],'edges':[
        {'id':'r0','from':'f1','relation':'describes','to':'o1','at_step':1},
        {'id':'r1','from':'a1','relation':'supports','to':'f1','at_step':1,'rule':'r:ls'}],
       'active_fact_ids':['f1'],'current_goal_refs':['m0'],'requests':[{'id':'m0','content':'ROOT\nS(a1,f1)'}],
       'assistant_statements':[],'evidence_index':{}}
    g['evidence_index']=evidence(g,{'a1':e});return g

class Tests(unittest.TestCase):
    def check(self,g):
        before=normalize(g);packed,stats=compact_graph(g)
        self.assertEqual(normalize(restore_graph(packed)),before)
        text,_=encode(g,len);self.assertEqual(normalize(decode(text)),before)
        self.assertEqual(normalize(g),before)
        return packed,stats
    def test_regular_derivations(self):
        p,s=self.check(fixture());self.assertEqual(s,{'confirmations':1,'edges':2,'indexes':3})
    def test_conflicting_evidence_preserved(self):
        g=fixture();g['nodes'][2]['confirmations'][0]['messages']=['different']
        g['edges'][1]['rule']='different';p,s=self.check(g)
        self.assertIsInstance(p['nodes'][2]['confirmations'][0],dict);self.assertIsInstance(p['edges'][1],dict)
    def test_id_order_and_extra_fields_preserved(self):
        g=fixture();g['edges'][0]['id']='custom';g['edges'][1]['extra']=True
        g['active_fact_ids']=[];g['evidence_index']=dict(reversed(list(g['evidence_index'].items())))
        p,s=self.check(g);self.assertEqual(s['edges'],0);self.assertEqual(s['indexes'],1)
    def test_error_event_and_literal_recipe_text(self):
        g=fixture();g['nodes'][1].update(status='error',error='failed',arguments={'text':['D','f1']})
        g['nodes'][1]['output_raw']='S(a1,f1)\nnull';self.check(g)
    def test_repeated_confirmation_not_merged(self):
        g=fixture();e=deepcopy(g['nodes'][1]);e.update(id='a2',step=2,call_id='c2',call_evidence='m3',output_evidence='m4');g['nodes'].insert(2,e)
        g['nodes'][3]['confirmations'].append(confirmation(e));g['edges'].append({'id':'r2','from':'a2','relation':'confirms','to':'f1','at_step':2,'rule':'r:ls'})
        g['evidence_index']=evidence(g,{'a1':g['nodes'][1],'a2':e})
        p,s=self.check(g);self.assertEqual(p['nodes'][3]['confirmations'],['a1','a2'])
    def test_retired_fact(self):
        g=fixture();g['nodes'][2].update(retired_at=1,retired_by='a1',retired_reason='superseded')
        g['edges'].append({'id':'r2','from':'a1','relation':'retires','to':'f1','at_step':1,'reason':'superseded'});g['active_fact_ids']=[]
        p,s=self.check(g);self.assertEqual(p['edges'][-1],['R','f1'])
if __name__=='__main__':unittest.main()
