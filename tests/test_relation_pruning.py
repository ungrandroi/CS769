import unittest,json
from copy import deepcopy
from cs769.tasks.memory import prepare
from cs769.base.config import ExperimentConfig
from cs769.cli import counter
from cs769.models.edits import relation_pruning as rp
from cs769.models.edits.record_edits import evidence

def graph(calls):
    h=[{'role':'user','content':'Carry out these operations.'}]
    for i,(tool,args,res) in enumerate(calls):
        h += [{'type':'function_call','call_id':str(i),'name':tool,'arguments':json.dumps(args)},
              {'type':'function_call_output','call_id':str(i),'output':json.dumps(res)}]
    cfg=ExperimentConfig();cfg.delivery={'mode':'replace','role':'assistant'}
    return prepare(h,cfg,counter('o200k_base'))['graph']

class RelationTests(unittest.TestCase):
    def setUp(self):self.count=counter('o200k_base')
    def stock(self,symbol='ABC',price=10,res=None):
        return graph([('get_stock_info',{'symbol':'ABC'},{'price':10,'MA(5)':list(range(300)),'percent_change':.5}),
                      ('place_order',{'symbol':symbol,'price':price,'amount':2,'order_type':'Buy'},res or {'order_id':9,'status':'Open'})])
    def test_consumption_retains_operands_receipt_and_declares_loss(self):
        g=self.stock();before=deepcopy(g);out,a=rp.prune(g,self.count,'Check order status.',kind='consumed')
        self.assertEqual(g,before);self.assertFalse(a['full_original_evidence_preserved'])
        self.assertIn('partial',rp.render(out));self.assertGreater(a['saved_tokens'],50)
        original=evidence(g)['evidence_view']['nodes'];edited=evidence(rp.base_graph(out))['evidence_view']['nodes']
        self.assertEqual([n for n in original if n['category']=='tool_call'],[n for n in edited if n['category']=='tool_call'])
        results=[rp.load(rp.fields(n)['output']) for n in edited if n['category']=='tool_result']
        self.assertEqual(results[0],{'price':10});self.assertEqual(results[1],{'order_id':9,'status':'Open'})
    def test_numeric_coincidence_wrong_entity_and_failed_consumer_are_not_flow(self):
        for g in [self.stock('XYZ'),self.stock(price=11),self.stock(res={'error':'rejected'})]:
            self.assertFalse(rp.candidates(g,'Proceed.','consumed')[0])
    def test_requested_history_is_protected(self):
        self.assertFalse(rp.candidates(self.stock(),'Compare historical moving averages.','consumed')[0])
    def test_same_read_in_different_cwd_not_version(self):
        g=graph([('ls',{}, {'files':['a']}),('cd',{'folder':'x'},{}),('ls',{}, {'files':['b']})])
        self.assertFalse(rp.candidates(g,'Proceed.','superseded')[0])
    def test_state_change_preserves_write_and_latest_read(self):
        g=graph([('cat',{'file_name':'a'},{'file_content':'old '*100}),('echo',{'file_name':'a','content':'new'},{}),
                 ('cat',{'file_name':'a'},{'file_content':'new'})])
        out,a=rp.prune(g,self.count,'Proceed.',kind='superseded')
        self.assertEqual(len(a['removed_event_ids']),2)
        self.assertEqual([rp.fields(n).get('name') for n in evidence(rp.base_graph(out))['evidence_view']['nodes'] if n['category']=='tool_call'],['echo','cat'])
    def test_corroboration_is_provenance_loss_not_full_evidence_preservation(self):
        g=graph([('cat',{'file_name':'a'},{'file_content':'retained '*100}),('cat',{'file_name':'a'},{'file_content':'retained '*100})])
        out,a=rp.prune(g,self.count,'Proceed.',kind='corroboration')
        self.assertFalse(a['full_original_evidence_preserved'])
        self.assertEqual(len([n for n in evidence(rp.base_graph(out))['evidence_view']['nodes'] if n['category']=='tool_result']),1)
    def test_currency_units_and_partial_list(self):
        for currency,eligible in [('USD',True),('EUR',False)]:
            g=graph([('get_flight_cost',{'travel_from':'AAA','travel_to':'BBB','travel_date':'2026-01-01','travel_class':'economy'},{'travel_cost_list':list(range(100,400))}),
                     ('compute_exchange_rate',{'base_currency':currency,'target_currency':'EUR','value':100},{'exchanged_value':92})])
            actions,_=rp.candidates(g,'Continue booking.','consumed')
            self.assertEqual(bool(actions),eligible)
            if eligible:
                out,a=rp.prune(g,self.count,'Continue booking.',kind='consumed')
                result=next(n for n in evidence(rp.base_graph(out))['evidence_view']['nodes'] if n['category']=='tool_result')
                self.assertEqual(rp.load(rp.fields(result)['output']),{'travel_cost_list':[100]})
if __name__=='__main__':unittest.main()
