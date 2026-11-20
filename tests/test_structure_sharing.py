"""Exact sharing keeps observations distinct and does not read the task query."""
import json
import unittest
from copy import deepcopy
from cs769.base.config import ExperimentConfig
from cs769.tasks.memory import prepare
from cs769.cli import counter
from cs769.models.editing import share_structure, Ineligible
from cs769.models.edits import subtree_share, schema_share

class StructuralSharingTests(unittest.TestCase):
    def setUp(self):
        self.count = counter('o200k_base')

    def graph(self, outputs):
        history = [{'role':'user','content':'Inspect the records.'}]
        for i, output in enumerate(outputs):
            history += [
                {'type':'function_call','call_id':str(i),'name':'read_records',
                 'arguments':json.dumps({'version':i})},
                {'type':'function_call_output','call_id':str(i),
                 'output':json.dumps(output,ensure_ascii=False)}]
        cfg = ExperimentConfig()
        cfg.delivery = {'mode':'replace','role':'assistant'}
        return prepare(history,cfg,self.count)['graph']

    def test_duplicate_payload_restores_every_observation_exactly(self):
        payload = {'record_id':7,'text':'保留原文 | punctuation, and repeated prose. '*120}
        g = self.graph([payload,payload])
        original = deepcopy(g)
        out,audit,_ = share_structure(g,self.count,'Use record 7.',{})
        module = {'share_subtrees':subtree_share,'share_schema':schema_share}[audit['operation']]
        self.assertEqual(module.restore(out),original)
        self.assertEqual(g,original)
        self.assertGreater(audit['saved_tokens'],0)
        other,other_audit,_ = share_structure(g,self.count,'Completely different request.',{})
        self.assertEqual(out,other)
        self.assertEqual(audit,other_audit)

    def test_schema_preserves_different_values_types_and_order(self):
        rows = [{'long_record_identifier':i,'detailed_status_description':'open' if i%2 else 'closed',
                 'observed_numeric_value':1.0 if i%2 else 1,
                 'source_reference_string':'字'+str(i),'nullable_property':None}
                for i in range(30)]
        g = self.graph([{'records':rows}])
        out,audit,_ = share_structure(g,self.count,'Proceed.',{})
        module = {'share_subtrees':subtree_share,'share_schema':schema_share}[audit['operation']]
        self.assertEqual(json.dumps(module.restore(out),ensure_ascii=False),
                         json.dumps(g,ensure_ascii=False))
        self.assertGreater(audit['saved_tokens'],0)

    def test_no_profitable_structure_is_not_silent_deletion(self):
        g = self.graph([{'id':1,'value':2}])
        original = deepcopy(g)
        with self.assertRaises(Ineligible):
            share_structure(g,self.count,'Delete everything.',{})
        self.assertEqual(g,original)
