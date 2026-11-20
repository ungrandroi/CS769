"""Load trusted local experimental snapshots independently of active modules."""
import importlib
import sys
from .experiment import verify_sources

MODULE_ALIASES = {
    'run_qwen_task': 'workflows.baseline_task',
    'v2_provenance_dedup': 'core.event_graph_dedup',
    'graph_memory': 'core.state_transition_graph',
    'graph_memory_v2': 'core.event_graph',
    'evaluate_qwen_compact': 'core.model_config',
}

def snapshot_module(directory, name):
    for candidate in (name, 'core.'+name, MODULE_ALIASES.get(name,name)):
        if (directory / (candidate.replace('.', '/')+'.py')).exists():
            return candidate
    raise ImportError(f'Module absent from frozen snapshot: {name}')

def load_frozen_modules(directory, hashes, names):
    verify_sources(directory, hashes)
    roots = {p.stem for p in directory.glob('*.py')} | {p.name for p in directory.iterdir() if p.is_dir() and (p/'__init__.py').exists()}
    legacy = roots | {name for name in sys.modules if name.split('.')[0] in roots}
    previous = {name: sys.modules[name] for name in legacy if name in sys.modules}
    path = list(sys.path)
    try:
        for name in legacy:
            sys.modules.pop(name, None)
        sys.path.insert(0, str(directory))
        return {name: importlib.import_module(snapshot_module(directory,name)) for name in names}
    finally:
        sys.path[:] = path
        for name in list(sys.modules):
            if name.split('.')[0] in roots:
                sys.modules.pop(name, None)
        sys.modules.update(previous)
