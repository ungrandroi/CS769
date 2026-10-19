import unittest

from qwen_transport import chat_messages, response_from_chat, prefix_log


class AdapterTests(unittest.TestCase):
    def test_call_and_result_preserve_arguments_and_output(self):
        raw = ' {"name": "a b", "x": 1.0} '
        messages = chat_messages([
            {'role': 'user', 'content': 'hello'},
            {'type': 'function_call', 'call_id': 'x', 'name': 'mkdir', 'arguments': raw},
            {'type': 'function_call_output', 'call_id': 'x', 'output': 'None'},
        ])
        self.assertEqual(messages[1]['tool_calls'][0]['function']['arguments'], raw)
        self.assertEqual(messages[2], {'role': 'tool', 'tool_call_id': 'x', 'content': 'None'})

    def test_response_parallel_calls_usage_and_mixed_text(self):
        raw = {'model': 'bfcl-qwen38-27b', 'created': 12,
               'choices': [{'finish_reason': 'tool_calls', 'message': {'role': 'assistant',
                   'content': 'I will inspect.', 'tool_calls': [
                       {'id': 'a', 'function': {'name': 'pwd', 'arguments': '{}'}},
                       {'id': 'b', 'function': {'name': 'ls', 'arguments': '{"a":true}'}}]}}],
               'usage': {'prompt_tokens': 100, 'completion_tokens': 30, 'total_tokens': 130}}
        response = response_from_chat(raw, 4)
        self.assertEqual(response.output_text, 'I will inspect.')
        self.assertEqual([o.name for o in response.output if o.type == 'function_call'], ['pwd', 'ls'])
        self.assertEqual(response.output[2].arguments, '{"a":true}')
        self.assertEqual(response.usage.input_tokens, 100)
        messages = chat_messages([o.model_dump(mode='json', by_alias=True) for o in response.output])
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]['content'], 'I will inspect.')
        self.assertEqual(len(messages[-1]['tool_calls']), 2)

    def test_prefix_log_excludes_later_state(self):
        self.assertEqual(prefix_log(['initial', {'step_0': []}, 'state1', {'step_0': []}, 'state2']),
                         ['initial', {'step_0': []}, 'state1'])

    def test_unsupported_protocol_rejected(self):
        with self.assertRaises(ValueError):
            chat_messages([{'type': 'reasoning', 'summary': []}])


if __name__ == '__main__':
    unittest.main()

class LiveGraphTests(unittest.TestCase):
    def test_compact_builds_from_current_qwen_history_without_changing_it(self):
        from copy import deepcopy
        import json
        from run_qwen_task import make_memory
        from test_graph_memory import history
        from graph_memory_serialization import decode_compact, normalize
        from graph_memory_replace import GraphMemoryReplacement, GraphMemoryV2Replacement
        from local_qwen_tokenizer import LocalQwenTokenizer
        source = history([('pwd', {}, {'current_working_directory': '/research'}),
                          ('mv', {'source': 'a', 'destination': 'b'}, {'error': 'MISSING'})])
        original = deepcopy(source)
        with LocalQwenTokenizer() as tokenizer:
            for mode, cls in [('v1-compact', GraphMemoryReplacement), ('v2-compact', GraphMemoryV2Replacement)]:
                text, graph = make_memory(source, mode, tokenizer.count)
                expected = cls(); expected.compress(source)
                self.assertEqual(normalize(decode_compact(text.split('\n', 2)[2])), normalize(json.loads(expected.render().split('\n', 2)[2])))
                self.assertEqual(graph['source_messages'], source)
                self.assertEqual(source, original)
