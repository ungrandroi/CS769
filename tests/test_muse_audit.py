"""Independent Muse adapter regression checks; no model inference or network."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from core import muse_transport as transport
from workflows import muse_task as task


def response():
    return {'model': transport.SERVING_MODEL, 'created': 1, 'choices': [
        {'finish_reason': 'tool_calls', 'message': {
            'role': 'assistant', 'content': 'Checking both files.',
            'reasoning_content': 'PRIVATE_REASONING_NOT_REINSERTED',
            'tool_calls': [
                {'id': 'server-a', 'type': 'function', 'function': {
                    'name': 'cat', 'arguments': '{ "file_name": "a.txt" }'}},
                {'id': 'server-b', 'type': 'function', 'function': {
                    'name': 'cat', 'arguments': '{"file_name":"b.txt"}'}}]}}],
        'usage': {'prompt_tokens': 123, 'completion_tokens': 45,
                  'total_tokens': 168, 'completion_tokens_details': {'reasoning_tokens': 20}}}


class MuseAdapterAudit(unittest.TestCase):
    def test_visible_content_parallel_calls_and_exact_arguments_survive(self):
        raw = response()
        before = deepcopy(raw)
        bridged = transport.response_from_chat(raw, 4)
        items = transport.plain(bridged.output)
        messages = transport.chat_messages(items)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]['content'], 'Checking both files.')
        calls = messages[0]['tool_calls']
        self.assertEqual([c['function'] for c in calls],
                         [c['function'] for c in raw['choices'][0]['message']['tool_calls']])
        self.assertEqual([c['id'] for c in calls], ['muse_call_4_0', 'muse_call_4_1'])
        self.assertEqual(raw, before)  # Native evidence is not rewritten.
        self.assertNotIn('PRIVATE_REASONING_NOT_REINSERTED', str(items))
        self.assertNotIn('reasoning_content', messages[0])
        self.assertEqual(bridged.usage.output_tokens_details.reasoning_tokens, 20)
        self.assertEqual(bridged.model, transport.SERVING_MODEL)

    def test_complete_tool_returns_remain_paired(self):
        items = transport.plain(transport.response_from_chat(response(), 4).output)
        self.assertFalse(task.all_paired(items))
        items += [{'type': 'function_call_output', 'call_id': f'muse_call_4_{i}',
                   'output': f'file {i} contents'} for i in range(2)]
        self.assertTrue(task.all_paired(items))
        messages = transport.chat_messages(items)
        self.assertEqual([m['role'] for m in messages], ['assistant', 'tool', 'tool'])
        self.assertEqual([m['tool_call_id'] for m in messages[1:]],
                         ['muse_call_4_0', 'muse_call_4_1'])
        self.assertFalse(task.all_paired(items + [items[-1]]))
        self.assertFalse(task.all_paired(items + [items[1]]))

    def test_tool_only_response_does_not_fabricate_text(self):
        raw = response()
        raw['choices'][0]['message']['content'] = None
        messages = transport.chat_messages(transport.plain(transport.response_from_chat(raw, 0).output))
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]['content'], '')
        self.assertEqual(len(messages[0]['tool_calls']), 2)

    def test_new_request_targets_muse_and_keeps_fixed_sampling(self):
        req = {'input': [{'role': 'user', 'content': 'Read a.txt.'}], 'tools': []}
        wire = task.request_body(req, 4409)
        self.assertEqual(wire['model'], 'bfcl-muse-glimmer-30b')
        self.assertEqual(wire['messages'], req['input'])
        self.assertEqual(wire['seed'], 4409)
        self.assertEqual(wire['max_tokens'], 4096)
        self.assertEqual(wire['chat_template_kwargs']['reasoning_strength'], 'low')
        self.assertNotIn('reasoning_content', str(wire))
        self.assertNotIn('enable_thinking', wire['chat_template_kwargs'])

    def test_tokenizer_uses_native_endpoint_and_special_mode(self):
        with patch.object(transport, 'post', return_value={'tokens': [1, 2, 3]}) as post:
            tok = transport.NativeTokenizer('http://127.0.0.1:11437/v1')
            self.assertEqual(tok.count('<|start|>', parse_special=True), 3)
            self.assertEqual(tok.count('<|start|>', parse_special=True), 3)
            self.assertEqual(post.call_count, 1)
            self.assertEqual(post.call_args.args[1], '/tokenize')
            self.assertEqual(post.call_args.args[2],
                             {'content': '<|start|>', 'add_special': True, 'parse_special': True})
            tok.count('<|start|>', parse_special=False)
            self.assertEqual(post.call_count, 2)

    def test_source_rejects_wrong_seed_and_threshold(self):
        manifest = dict(method='identity', status='complete', task='multi_turn_base_3',
                        category='multi_turn_base', seed=4409, sampling=task.SAMPLING,
                        threshold=1000, threshold_metric='native full minus fixed-only template tokens',
                        context=131072, max_tokens=4096)
        task.validate_source(manifest, 'multi_turn_base_3', 'multi_turn_base', 4409)
        with self.assertRaises(AssertionError):
            task.validate_source(manifest, 'multi_turn_base_3', 'multi_turn_base', 5519)
        manifest['threshold'] = 1001
        with self.assertRaises(AssertionError):
            task.validate_source(manifest, 'multi_turn_base_3', 'multi_turn_base', 4409)


if __name__ == '__main__':
    unittest.main()


class MuseControllerAudit(unittest.TestCase):
    @staticmethod
    def urlopen(url, **kwargs):
        import io,json
        value = [{'n_ctx':131072}] if url.endswith('/slots') else {'model_alias':'bfcl-muse-glimmer-30b'}
        return io.BytesIO(json.dumps(value).encode())

    def setup_root(self, root):
        import json
        from workflows import muse_controller as controller
        (root/'runtime').mkdir()
        snapshot = root/'source_code/frozen'
        snapshot.mkdir(parents=True)
        def put(name, value):
            (root/name).write_text(json.dumps(value))
        put('source_code/frozen/hashes.json', {})
        put('vendor-pins.json', {})
        put('runtime/runtime-contract.json', {'props_projection': {'model_alias': 'bfcl-muse-glimmer-30b'}})
        (root/'PROTOCOL.md').write_text('registered test protocol')
        put('task-split.json', dict(tasks=[dict(id='task_1',category='category',semantics='filesystem')],
            seeds=[4409], pilot_task='task_1', sampling=task.SAMPLING,
            baseline_explanations=dict(state='minimal',event='full',dedup='none')))
        put('selection.json', {'selected': {m:dict(variant='test',explanation='minimal',module='test')
                                           for m in ('state','event','dedup')}})
        put('preflight-review.json', dict(status='pass', **controller.gate_expected(root,snapshot)))
        return snapshot

    def test_live_task_completion_then_stage_advancement_and_reuse(self):
        import json,sys,tempfile
        from pathlib import Path
        from workflows import muse_controller as controller
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);snapshot=self.setup_root(root);calls=[]
            def run(command, **kwargs):
                calls.append(command)
                if command[2]=='workflows.muse_task':
                    dest=Path(command[command.index('--output')+1])
                    launch=json.loads((dest/'launch.json').read_text())
                    manifest=dict(launch['configuration'], status='complete',triggered=True,passed=False)
                    (dest/'manifest.json').write_text(json.dumps(manifest))
            with patch.object(sys,'argv',['controller','--root',str(root),'--snapshot-label','frozen']), \
                 patch.object(controller.subprocess,'run',side_effect=run), \
                 patch.object(controller.urllib.request,'urlopen',side_effect=self.urlopen):
                controller.main()
            actual=[c for c in calls if c[2]=='workflows.muse_task']
            self.assertEqual(len(actual),7)  # Pilot is reused, not rerun by score.
            state=json.loads((root/'runtime/status.json').read_text())
            self.assertEqual(state['status'],'inference_complete_pending_independent_audit')
            self.assertEqual(state['completed_jobs'],7)
            self.assertIn('pilot_complete',state['stages'])
            self.assertIn('identity_all_complete',state['stages'])
            self.assertIn('paired_graphs_complete',state['stages'])

    def test_failure_stops_before_other_tasks(self):
        import json,sys,tempfile,subprocess
        from pathlib import Path
        from workflows import muse_controller as controller
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.setup_root(root)
            with patch.object(sys,'argv',['controller','--root',str(root),'--snapshot-label','frozen']), \
                 patch.object(controller.subprocess,'run',side_effect=subprocess.CalledProcessError(1,['task'])) as run, \
                 patch.object(controller.urllib.request,'urlopen',side_effect=self.urlopen):
                with self.assertRaises(subprocess.CalledProcessError):controller.main()
            self.assertEqual(run.call_count,1)
            state=json.loads((root/'runtime/status.json').read_text())
            self.assertEqual(state['status'],'needs_review')
            self.assertEqual(state['completed_jobs'],0)
