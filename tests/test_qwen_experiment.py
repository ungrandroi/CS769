import unittest

from cs769.models.qwen_transport import chat_messages, response_from_chat, prefix_log


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
    def test_semantic_profiles_preserve_current_history_without_tokenizer_assets(self):
        from copy import deepcopy
        from pathlib import Path
        import json
        import cs769
        from cs769.base.config import load_config
        from cs769.tasks.memory import prepare
        from test_state_transition_graph import history
        from cs769.models.graphs.graph_memory_serialization import decode_compact, normalize
        from cs769.models.graphs.graph_memory_replace import GraphMemoryReplacement, GraphMemoryV2Replacement

        source = history([("pwd", {}, {"current_working_directory": "/research"}),
                          ("mv", {"source": "a", "destination": "b"}, {"error": "MISSING"})])
        original = deepcopy(source)
        for name, cls in [("state_legacy", GraphMemoryReplacement), ("event_legacy", GraphMemoryV2Replacement)]:
            cfg = load_config(Path(cs769.__file__).parent / "configs" / (name + ".json"))
            # Structural codec test uses explicit character units, not native Qwen token claims.
            result = prepare(source, cfg, len, counter_name="characters")
            expected = cls()
            expected.compress(source)
            self.assertEqual(normalize(decode_compact(result["memory_text"])),
                             normalize(json.loads(expected.render().split("\n", 2)[2])))
            self.assertEqual(expected.graph["source_messages"], source)
            self.assertEqual(result["metrics"]["counter"], "characters")
            self.assertEqual(source, original)
