"""Select this checkout's pinned BFCL without changing any shared environment."""
from cs769.base.paths import project_root
from pathlib import Path
import importlib,os,sys

def ensure_bfcl():
    project=project_root()
    package=project/"vendor/gorilla/berkeley-function-call-leaderboard/bfcl_eval"
    if not (package/"__init__.py").is_file():raise RuntimeError("Pinned BFCL vendor is missing: "+str(package))
    configured=os.environ.get("CS769_BFCL_ROOT")
    if configured:
        supplied=Path(configured).resolve()
        if supplied.name!="bfcl_eval":supplied=supplied/"bfcl_eval"
        if supplied!=package.resolve():raise RuntimeError("This BFCL profile requires the project vendor; CS769_BFCL_ROOT points elsewhere")
    loaded=sys.modules.get("bfcl_eval")
    if loaded is not None and getattr(loaded,"__file__",None):
        if Path(loaded.__file__).resolve().parent!=package.resolve():
            raise RuntimeError("A different BFCL is already loaded; start a fresh cs769 process")
    parent=str(package.parent)
    if parent in sys.path:sys.path.remove(parent)
    sys.path.insert(0,parent);os.environ["CS769_BFCL_ROOT"]=str(package)
    importlib.invalidate_caches()
    module=importlib.import_module("bfcl_eval")
    if Path(module.__file__).resolve().parent!=package.resolve():raise RuntimeError("Wrong BFCL import root")
    return package
