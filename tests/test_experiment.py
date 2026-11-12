"""Safety and isolation checks for the shared experiment harness; no model calls."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from cs769.adapters.experiment import read, write, run_batch, run_attempt, sha, verify_sources
from cs769.adapters.frozen import load_frozen_modules
from cs769.adapters.research_modes import MODES, LABELS

class ExperimentTest(unittest.TestCase):
    def test_same_task_stays_on_same_worker(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);calls=[]
            def run(task,mode,url):
                calls.append((task['id'],mode,url));return {'passed':mode=='identity'}
            tasks=[{'id':'a'},{'id':'b'}]
            run_batch(out,tasks,lambda _:MODES,run,6)
            for task in tasks:
                entries=[row for row in calls if row[0]==task['id']]
                self.assertEqual([row[1] for row in entries],list(MODES))
                self.assertEqual(len({row[2] for row in entries}),1)
            self.assertEqual(read(out/'progress.json')['status'],'complete')

    def test_incomplete_attempt_never_retried(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);write(out/'manifest.json',{'status':'error'})
            with patch('cs769.adapters.experiment.subprocess.run') as command:
                with self.assertRaises(RuntimeError):run_attempt(out,['unused'])
                command.assert_not_called()

    def test_completed_attempt_never_rerun(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);write(out/'manifest.json',{'status':'complete'})
            with patch('cs769.adapters.experiment.subprocess.run') as command:
                self.assertEqual(run_attempt(out,['unused'])['status'],'complete')
                command.assert_not_called()

    def test_frozen_package_restores_current_modules(self):
        import cs769.adapters.research_modes as current
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);(out/'core').mkdir()
            (out/'core/__init__.py').write_text('')
            (out/'core/research_modes.py').write_text("MODES=('frozen',)\n")
            hashes={str(p.relative_to(out)):sha(p) for p in out.rglob('*.py')}
            modules=load_frozen_modules(out,hashes,['core.research_modes'])
            self.assertEqual(modules['core.research_modes'].MODES,('frozen',))
            import cs769.adapters.research_modes as restored
            self.assertIs(restored,current)
            (out/'core/research_modes.py').write_text('MODES=()')
            with self.assertRaises(ValueError):verify_sources(out,hashes)

    def test_dedup_is_not_added_to_three_arm_protocol(self):
        self.assertEqual(MODES,('identity','v1-compact','v2-compact'))
        self.assertIn('v2-dedup',LABELS)

if __name__=='__main__':unittest.main()

class FrozenAliasTests(unittest.TestCase):
    def test_graph_aliases_resolve_inside_canonical_snapshot(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from cs769.adapters.frozen import snapshot_module
        aliases = {"graph_memory": "state_transition_graph",
                   "graph_memory_v2": "event_graph",
                   "v2_provenance_dedup": "event_graph_dedup"}
        with TemporaryDirectory() as td:
            root = Path(td)
            target = root / "cs769/graphs"
            target.mkdir(parents=True)
            for old, module in aliases.items():
                (target / (module + ".py")).write_text("SNAPSHOT = True")
                self.assertEqual(snapshot_module(root, old), "cs769.graphs." + module)
            with self.assertRaises(ImportError):
                snapshot_module(root, "run_qwen_task")
