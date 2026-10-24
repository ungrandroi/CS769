#!/usr/bin/env python3
"""One CLI for graph-memory experiments; command modules are imported lazily."""
import importlib
import sys

COMMANDS = {
    ('run', 'baseline'): ('workflows.baseline_batch', 'main'),
    ('run', 'dedup'): ('workflows.dedup_batch', 'main'),
    ('run', 'history1000'): ('workflows.history_batch', 'main'),
    ('audit', 'baseline'): ('workflows.baseline_audit', 'summarize'),
    ('audit', 'dedup'): ('workflows.dedup_audit', 'main'),
    ('audit', 'history1000'): ('workflows.history_audit', 'main'),
    ('task', 'baseline'): ('workflows.baseline_task', 'main'),
    ('task', 'dedup'): ('workflows.dedup_task', 'main'),
    ('task', 'history1000'): ('workflows.history_task', 'main'),
    ('checkpoints',): ('workflows.checkpoints', 'main'),
    ('probe', 'dedup'): ('workflows.dedup_probe', 'main'),
    ('reports',): ('workflows.reports', 'main'),
    ('bfcl',): ('core.model_config', 'main'),
}
HELP = '''Graph Memory experiments
Methods: Identity | State-Transition Graph | Event Graph | Event Graph-Dedup

Usage: scripts/bfcl_python.sh scripts/manage.py COMMAND [OPTIONS]

  run baseline|dedup|history1000      Run a batch (--prepare-only, --output DIR)
  audit baseline|dedup|history1000    Validate records and write audit reports
  checkpoints                       Prepare pure 1000-token checkpoints
  probe dedup                       Offline Event Graph-Dedup roundtrip study
  reports                           Render reports with current method names
  task baseline|dedup|history1000    Run one task (used by batch workers)
  bfcl ...                          Forward arguments to the official BFCL CLI

Example: scripts/bfcl_python.sh scripts/manage.py run history1000 --prepare-only --output /tmp/history-check
'''

def main(argv=None):
    args=list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ('-h','--help'):
        print(HELP);return
    for key in sorted(COMMANDS,key=len,reverse=True):
        if tuple(args[:len(key)])==key:
            module,entry=COMMANDS[key]
            original=sys.argv
            try:
                sys.argv=[str(original[0])+' '+' '.join(key),*args[len(key):]]
                return getattr(importlib.import_module(module),entry)()
            finally:sys.argv=original
    raise SystemExit('Unknown command. Use --help for available commands.')

if __name__=='__main__':main()
