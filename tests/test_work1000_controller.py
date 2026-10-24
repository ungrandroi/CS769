"""Mock orchestration checks; these do not replace live inference audits."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from workflows import work1000_controller as controller
from workflows import work1000_batch as batch


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def setup(root):
    (root/'runtime').mkdir()
    put(root/'task-split.json', {'tasks': [{'id': 'task', 'category': 'category',
         'split': 'development'}], 'seeds': [1103]})
    put(root/'tasks/task/seed1103/identity/manifest.json',
        {'status': 'complete', 'triggered': True, 'passed': True, 'first_input': 2000})


class ControllerTests(unittest.TestCase):
    def test_pilot_then_remaining_stages_automatically(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); setup(root)
            with patch('sys.argv', ['controller','--root',tmp,'--snapshot-label','frozen']), \
                 patch.object(controller, 'select', return_value={'state':'none','event':'minimal','dedup':'full'}), \
                 patch.object(controller.subprocess, 'run') as run:
                controller.main()
            commands=[c.args[0] for c in run.call_args_list]
            self.assertIn('--task-only',commands[0])
            self.assertIn('--seed-only',commands[0])
            self.assertNotIn('--task-only',commands[1])
            self.assertEqual(len(commands),9)
            self.assertEqual([cmd[cmd.index('--stage')+1] for cmd in commands[:-1]],
                             ['graph-dev']*4+['identity-all']+['graph-final']*3)
            state=json.loads((root/'runtime/controller-status.json').read_text())
            self.assertEqual(state['status'],'inference_complete_pending_independent_audit')

    def test_failure_stops_before_next_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); setup(root)
            with patch('sys.argv', ['controller','--root',tmp,'--snapshot-label','frozen']), \
                 patch.object(controller.subprocess,'run',side_effect=subprocess.CalledProcessError(1,'pilot')) as run:
                with self.assertRaises(subprocess.CalledProcessError): controller.main()
            self.assertEqual(run.call_count,1)
            state=json.loads((root/'runtime/controller-status.json').read_text())
            self.assertEqual(state['status'],'needs_review')
            self.assertEqual(state['completed_stages'],[])

    def test_selection_preserves_file_and_rejects_changed_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); setup(root)
            for method in ('state','event','dedup'):
                for explanation in ('none','minimal','full'):
                    put(root/f'tasks/task/seed1103/{method}-{explanation}/manifest.json',
                        {'status':'complete','passed':True,'first_input':3000})
            first=controller.select(root)
            saved=(root/'selection.json').read_bytes()
            self.assertEqual(first,{'state':'none','event':'none','dedup':'none'})
            self.assertEqual(controller.select(root),first)
            self.assertEqual((root/'selection.json').read_bytes(),saved)
            put(root/'tasks/task/seed1103/state-full/manifest.json',
                {'status':'complete','passed':False,'first_input':3000})
            with self.assertRaisesRegex(AssertionError,'evidence changed'):controller.select(root)
            self.assertEqual((root/'selection.json').read_bytes(),saved)

    def test_batch_preserves_incomplete_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); setup(root)
            path=root/'tasks/task/seed1103/state-none/manifest.json'
            put(path,{'status':'error','error':'original error'})
            saved=path.read_bytes()
            with patch('sys.argv',['batch','--root',tmp,'--stage','graph-dev','--method-only','state']), \
                 patch.object(batch,'snapshot',return_value={}), \
                 patch.object(batch.subprocess,'run') as run, \
                 patch.object(Path,'symlink_to'):
                with self.assertRaises(SystemExit):batch.main()
            self.assertFalse(run.called)
            self.assertEqual(path.read_bytes(),saved)


if __name__=='__main__':unittest.main()
