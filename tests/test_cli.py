import importlib
import sys
import unittest
from unittest.mock import patch
import manage
from core.research_modes import LABELS, method_id

class CliTest(unittest.TestCase):
    def test_names_and_aliases(self):
        self.assertEqual(list(LABELS.values()),['Identity','State-Transition Graph','Event Graph','Event Graph-Dedup'])
        for key,label in LABELS.items():self.assertEqual(method_id(label),key)

    def test_lazy_dispatch_and_argument_forwarding(self):
        original=sys.argv
        with patch('workflows.history_batch.main') as command:
            command.side_effect=lambda:list(sys.argv[1:])
            self.assertEqual(manage.main(['run','history1000','--prepare-only']),['--prepare-only'])
        self.assertIs(sys.argv,original)

    def test_all_routes_have_callable_entries(self):
        for module,entry in manage.COMMANDS.values():
            self.assertTrue(callable(getattr(importlib.import_module(module),entry)))

    def test_unknown_command_is_rejected(self):
        with self.assertRaises(SystemExit):manage.main(['wrong'])

if __name__=='__main__':unittest.main()
