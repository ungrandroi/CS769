"""Every alias must share one atomic budget ledger and one cap."""
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from cs769.base.budget import PersistentBudget, BudgetExceeded

RATES={'input':2,'output':8,'cached_input':0.5,'cache_write':2}
REQUEST={'model':'gpt-4.1','messages':[{'role':'user','content':'test'}],'max_tokens':1}

class SharedBudgetTests(unittest.TestCase):
    def test_aliases_share_reservations_settlement_and_limit(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);target=root/'shared.json'
            a=root/'a.json';b=root/'b.json'
            a.symlink_to(target);b.symlink_to(target)
            first=PersistentBudget(a,.01,RATES)
            second=PersistentBudget(b,.01,RATES)
            one=first.reserve(REQUEST);two=second.reserve(REQUEST)
            with self.assertRaises(BudgetExceeded):first.reserve(REQUEST)
            self.assertEqual(set(json.loads(target.read_text())['requests']),{one,two})
            first.settle(one,{'usage':{'prompt_tokens':1,'completion_tokens':1}})
            second.uncertain(two)
            for alias in (a,b):
                self.assertTrue(alias.is_symlink())
                state=json.loads(alias.read_text())['requests']
                self.assertEqual(state[one]['status'],'settled')
                self.assertEqual(state[two]['status'],'uncertain')
            self.assertEqual(first.path,second.path)
            self.assertEqual(first.path.with_suffix('.lock'),root/'shared.lock')

    def test_relative_alias_to_initially_absent_ledger_stays_linked(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'child').mkdir()
            alias=root/'child'/'budget.json';alias.symlink_to('../shared.json')
            budget=PersistentBudget(alias,1,RATES)
            key=budget.reserve(REQUEST)
            self.assertTrue(alias.is_symlink())
            self.assertIn(key,json.loads((root/'shared.json').read_text())['requests'])
