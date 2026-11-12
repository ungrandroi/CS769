"""Compatibility import; executable workflows use python -m cs769."""
import importlib,sys
from pathlib import Path
_source=str(Path(__file__).resolve().parents[2]/"src")
if _source not in sys.path:sys.path.insert(0,_source)
if __name__=="__main__":
    raise SystemExit("This standalone command is retired. Use python -m cs769 --help")
sys.modules[__name__]=importlib.import_module('cs769.adapters.frozen')
