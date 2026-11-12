"""Native protocol, signed evidence, error redaction and bounded transport retries."""
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
from cs769.adapters import anthropic_transport as transport
from cs769.graphs.graph_memory_native import build_native_graph, append_native_index, reconstruct_native_history
from cs769.adapters.qwen_transport import plain

class AnthropicTransportTest(unittest.TestCase):

    def raw(self):
        return {'id': 'msg_fixture', 'model': transport.MODEL, 'role': 'assistant', 'stop_reason': 'tool_use', 'content': [{'type': 'thinking', 'thinking': 'opaque', 'signature': 'signed-value'}, {'type': 'redacted_thinking', 'data': 'opaque-data'}, {'type': 'text', 'text': 'Checking.'}, {'type': 'tool_use', 'id': 'toolu_actual', 'name': 'pwd', 'input': {}}], 'usage': {'input_tokens': 11, 'output_tokens': 8, 'cache_read_input_tokens': 4, 'cache_creation_input_tokens': 3}}

    def test_native_signed_blocks_and_actual_ids_survive_graph_and_scoring_bridge(self):
        raw = self.raw()
        before = deepcopy(raw)
        response = transport.normalized_response(raw, 0)
        self.assertEqual(raw, before)
        self.assertEqual(response.output[-1].call_id, 'toolu_actual')
        messages = [{'role': 'user', 'content': 'Where are we?'}, {'role': 'assistant', 'content': deepcopy(raw['content'])}]
        normalized = [deepcopy(messages[0]), *plain(response.output)]
        value = '{"current_working_directory": "/fixture"}'
        transport.append_tool_results(messages, [value], ['toolu_actual'])
        normalized.append({'type': 'function_call_output', 'call_id': 'toolu_actual', 'output': value})
        messages.append({'role': 'assistant', 'content': [{'type': 'text', 'text': '/fixture'}]})
        normalized.append({'role': 'assistant', 'content': '/fixture'})
        graph = build_native_graph(normalized, messages, provider='anthropic')
        self.assertEqual(reconstruct_native_history(graph), messages)
        indexed = append_native_index(graph)
        self.assertEqual(indexed[:-1], messages)
        self.assertEqual(graph['native_evidence']['call_id_map'], {'toolu_actual': 'toolu_actual'})
        self.assertIn('/fixture', indexed[-1]['content'])
        self.assertEqual(indexed[1]['content'][:2], before['content'][:2])

    def test_multiple_results_grouped_error_marked_and_pairing_checked(self):
        messages = [{'role': 'assistant', 'content': [{'type': 'tool_use', 'id': 'a', 'name': 'pwd', 'input': {}}, {'type': 'tool_use', 'id': 'b', 'name': 'cat', 'input': {}}]}]
        with self.assertRaises(ValueError):
            transport.append_tool_results(deepcopy(messages), ['x'], ['a'])
        transport.append_tool_results(messages, ['{}', '{"error":"missing"}'], ['a', 'b'])
        self.assertEqual(messages[-1]['role'], 'user')
        self.assertEqual(len(messages[-1]['content']), 2)
        self.assertNotIn('is_error', messages[-1]['content'][0])
        self.assertTrue(messages[-1]['content'][1]['is_error'])
        self.assertEqual(messages[-1]['content'][1]['content'], '{"error":"missing"}')

    def test_usage_includes_all_input_components_and_runtime_has_no_sampling_fields(self):
        usage = transport.usage_counts(self.raw()['usage'])
        self.assertEqual(usage['prompt_tokens'], 18)
        self.assertEqual(usage['total_tokens'], 26)
        self.assertTrue({'seed', 'temperature', 'top_p', 'top_k'}.isdisjoint(transport.RUNTIME))
        self.assertEqual(transport.RUNTIME['thinking'], {'type': 'adaptive'})

    def test_shared_http_error_redacts_key_and_preserves_reservation(self):
        from cs769.adapters.http import HTTPTransport, ProviderError
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from unittest.mock import Mock, patch
        import io, json, urllib.error, os
        secret = 'fixture-secret-not-a-key'
        with TemporaryDirectory() as td:
            key = Path(td) / 'env'
            key.write_text('ANTHROPIC_API_KEY=' + secret + '\n')
            key.chmod(384)
            budget = Mock()
            budget.reserve.return_value = 'reservation'
            error = urllib.error.HTTPError('https://example.invalid', 400, 'denied', {}, io.BytesIO(json.dumps({'error': {'type': 'fixture', 'message': secret}}).encode()))
            with patch.dict(os.environ, {'CS769_OFFLINE': '0'}), patch('urllib.request.urlopen', side_effect=error) as send:
                with self.assertRaises(ProviderError) as caught:
                    HTTPTransport('anthropic', key, budget, authorized=True).send({'max_tokens': 8})
            self.assertNotIn(secret, str(caught.exception))
            self.assertIn('[redacted]', str(caught.exception))
            self.assertEqual(send.call_count, 1)
            budget.uncertain.assert_called_once_with('reservation')

    def test_credentials_read_only_expected_field_and_require_600(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'env'
            path.write_text('export ANTHROPIC_API_KEY="fixture-value"\n')
            path.chmod(384)
            self.assertEqual(transport.credentials(path), 'fixture-value')
            path.chmod(420)
            with self.assertRaises(ValueError):
                transport.credentials(path)
if __name__ == '__main__':
    unittest.main()
