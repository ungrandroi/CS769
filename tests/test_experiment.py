"""Safety and isolation checks for the shared experiment harness; no model calls."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from core.experiment import read, write, run_batch, run_attempt, sha, verify_sources
from core.frozen import load_frozen_modules
from core.research_modes import MODES, LABELS

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
            with patch('core.experiment.subprocess.run') as command:
                with self.assertRaises(RuntimeError):run_attempt(out,['unused'])
                command.assert_not_called()

    def test_completed_attempt_never_rerun(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);write(out/'manifest.json',{'status':'complete'})
            with patch('core.experiment.subprocess.run') as command:
                self.assertEqual(run_attempt(out,['unused'])['status'],'complete')
                command.assert_not_called()

    def test_frozen_package_restores_current_modules(self):
        import core.research_modes as current
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);(out/'core').mkdir()
            (out/'core/__init__.py').write_text('')
            (out/'core/research_modes.py').write_text("MODES=('frozen',)\n")
            hashes={str(p.relative_to(out)):sha(p) for p in out.rglob('*.py')}
            modules=load_frozen_modules(out,hashes,['core.research_modes'])
            self.assertEqual(modules['core.research_modes'].MODES,('frozen',))
            import core.research_modes as restored
            self.assertIs(restored,current)
            (out/'core/research_modes.py').write_text('MODES=()')
            with self.assertRaises(ValueError):verify_sources(out,hashes)

    def test_dedup_is_not_added_to_three_arm_protocol(self):
        self.assertEqual(MODES,('identity','v1-compact','v2-compact'))
        self.assertIn('v2-dedup',LABELS)

if __name__=='__main__':unittest.main()
