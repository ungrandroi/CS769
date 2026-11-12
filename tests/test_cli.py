import contextlib,io,sys,unittest
from unittest.mock import patch
from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path
_spec = spec_from_file_location("cs769_compat_manage", Path(__file__).resolve().parents[1] / "scripts/manage.py")
manage = module_from_spec(_spec)
_spec.loader.exec_module(manage)
from cs769 import cli
from cs769.adapters.research_modes import LABELS,method_id

class CliTest(unittest.TestCase):
    def test_names_and_aliases(self):
        self.assertEqual(list(LABELS.values()),["Identity","State-Transition Graph","Event Graph","Event Graph-Dedup","Event Graph-Readable"])
        for key,label in LABELS.items():self.assertEqual(method_id(label),key)
    def test_old_launcher_uses_the_same_callable(self):
        self.assertIs(manage.main,cli.main)
    def test_canonical_command_set(self):
        parser=cli.build_parser()
        commands=next(a for a in parser._actions if hasattr(a,"choices") and isinstance(a.choices,dict))
        self.assertEqual(set(commands.choices),{"list","validate","prepare","replay","score","report","run","batch"})
    def test_unknown_command_is_rejected(self):
        with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):manage.main(["wrong"])
    def test_run_without_authorization_fails_before_reading_credentials(self):
        with self.assertRaises(PermissionError):
            manage.main(["run","--config","missing.json","--task","x","--category","multi_turn_base","--output","unused"])
