"""Untriggered controls must never masquerade as graph executions."""
import json
import tempfile
import unittest
from pathlib import Path
from workflows.work1000_report import summarize


class ReportTests(unittest.TestCase):
    def test_untriggered_inheritance_is_not_graph_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'task-split.json').write_text(json.dumps({
                'tasks': [{'id': 'task', 'family': 3, 'split': 'development'}],
                'seeds': [1103]}))
            run = root/'tasks/task/seed1103/identity'
            run.mkdir(parents=True)
            (run/'manifest.json').write_text(json.dumps({
                'status': 'complete', 'triggered': False, 'passed': True,
                'live_requests': 4}))
            result, _ = summarize(root)
            graph_rows = [r for r in result['rows'] if r['method'] != 'identity']
            self.assertEqual(len(graph_rows), 3)
            for row in graph_rows:
                self.assertEqual(row['status'], 'not_applicable')
                self.assertIsNone(row['passed'])
                self.assertTrue(row['inherited_identity_passed'])
                self.assertEqual(row['live_requests'], 0)
            self.assertTrue(all(g['method'] == 'identity' for g in result['groups']))


if __name__ == '__main__':
    unittest.main()
