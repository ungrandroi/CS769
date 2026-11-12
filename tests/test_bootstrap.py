"""The installed entry must not depend on a manually assembled vendor PYTHONPATH."""
import json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
import cs769
PROJECT=Path(cs769.__file__).resolve().parents[2]
GUARD="import socket\n"+"def blocked(*a,**k):raise AssertionError('Network forbidden')\n"+"socket.socket.connect=blocked\n"
class BootstrapTest(unittest.TestCase):
    def environment(self):
        env=dict(os.environ,CS769_OFFLINE="1",PYTHONDONTWRITEBYTECODE="1")
        env.pop("PYTHONPATH",None);env.pop("CS769_BFCL_ROOT",None)
        return env
    def test_installed_package_selects_project_vendor_from_another_directory(self):
        code=GUARD+"from cs769.bootstrap import ensure_bfcl\np=ensure_bfcl()\nimport bfcl_eval,json\nprint(json.dumps({'file':bfcl_eval.__file__}))\n"
        with tempfile.TemporaryDirectory()as td:
            r=subprocess.run([sys.executable,"-B","-c",code],env=self.environment(),cwd=td,text=True,capture_output=True)
        self.assertEqual(r.returncode,0,r.stderr)
        actual=Path(json.loads(r.stdout)["file"]).resolve()
        self.assertEqual(actual,PROJECT/"vendor/gorilla/berkeley-function-call-leaderboard/bfcl_eval/__init__.py")
    def test_already_imported_foreign_bfcl_is_rejected(self):
        code=GUARD+"""import types,sys
fake=types.ModuleType("bfcl_eval");fake.__file__="/tmp/not-the-project/bfcl_eval/__init__.py"
sys.modules["bfcl_eval"]=fake
from cs769.bootstrap import ensure_bfcl
try:ensure_bfcl()
except RuntimeError as e:
 print(str(e))
else:raise AssertionError("Foreign dependency was accepted")
"""
        r=subprocess.run([sys.executable,"-B","-c",code],env=self.environment(),text=True,capture_output=True)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn("different BFCL is already loaded",r.stdout)
