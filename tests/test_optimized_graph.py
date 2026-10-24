import json
import unittest
from copy import deepcopy

from core.optimized_graph import build_memory, restore_history, rebuild_original_graph, audit_semantic_index, METHODS
from core.state_transition_graph import GraphMemory
from core.event_graph import GraphMemoryV2


def history():
    messages = [{'role': 'user', 'content': 'Find the report and rename it.'}]
    actions = [('cd', {'folder': 'document'}, {'current_working_directory': 'document'}),
               ('ls', {}, {'current_directory_content': ['report']}),
               ('ls', {}, {'current_directory_content': ['report']}),
               ('mv', {'source': 'report', 'destination': 'new'}, {'result': "'report' moved to 'new'"}),
               ('cd', {'folder': 'missing'}, {'error': 'missing directory'})]
    for i, (tool, args, result) in enumerate(actions):
        messages += [{'role': 'assistant', 'content': 'Checking.', 'meta': None},
                     {'type': 'function_call', 'name': tool, 'arguments': json.dumps(args),
                      'call_id': f'c{i}', 'status': 'completed', 'extra': [None, True, 1, 1.0]},
                     {'type': 'function_call_output', 'call_id': f'c{i}', 'output': json.dumps(result)}]
    return messages


class Tests(unittest.TestCase):
    def test_exact_messages_graph_rebuild_and_no_mutation(self):
        source = history()
        before = deepcopy(source)
        for method in METHODS:
            for explanation in ('none', 'minimal', 'full'):
                text, meta = build_memory(source, method, explanation, len)
                restored = restore_history(meta['graph'])
                self.assertEqual(restored, source)
                self.assertEqual(source, before)
                builder = GraphMemory if method == 'v1-compact' else GraphMemoryV2
                self.assertEqual(rebuild_original_graph(meta['graph']), builder().build(source))
                self.assertEqual(meta['total_tokens'], len(text))
                self.assertEqual(meta['instruction_tokens'], len(meta['instruction']))
                self.assertIs(type(restored[2]['extra'][2]), int)
                self.assertIs(type(restored[2]['extra'][3]), float)

    def test_repeated_calls_errors_and_statements_are_preserved(self):
        for method in METHODS:
            _, meta = build_memory(history(), method, 'none', len)
            graph = meta['graph']
            events = graph.get('events', graph.get('tool_call_edges'))
            if 'event_columns' in graph:
                events = {key: dict(zip(graph['event_columns'], value)) for key, value in events.items()}
            self.assertEqual(len(events), 5)
            self.assertEqual(sum(e['tool'] == 'ls' for e in events.values()), 2)
            self.assertEqual(list(events.values())[-1]['status'], 'error')
            self.assertEqual(len(graph['unverified_assistant_statements']), 5)
            self.assertEqual(meta['instruction'], '')

    def test_state_deltas_reconstruct_semantic_states(self):
        _, meta = build_memory(history(), 'v1-compact', 'none', len)
        nodes = meta['graph']['state_nodes']
        original = GraphMemory().build(history())
        current = deepcopy(nodes['s0'])
        for i, node in enumerate(original['nodes']):
            if i:
                delta = nodes[node['id']]['changes']
                if 'cwd' in delta:
                    current['cwd'] = deepcopy(delta['cwd'])
                for update in delta.get('objects_updated', []):
                    update = deepcopy(update)
                    slot = update.pop('object_index')
                    if slot == len(current['objects']):
                        current['objects'].append({})
                    current['objects'][slot].update(update)
            self.assertEqual(current['cwd'], node['state']['cwd'])
            self.assertEqual(current['objects'], node['state']['objects'])

    def test_event_facts_preserve_versions_and_retirement(self):
        original = GraphMemoryV2().build(history())
        for method in ('v2-compact', 'v2-dedup'):
            _, meta = build_memory(history(), method, 'none', len)
            facts = meta['graph']['facts']
            for node in original['nodes']:
                if node['category'] == 'fact':
                    fact = dict(zip(meta['graph']['fact_columns'], facts[node['id']]))
                    for key in ('subject', 'predicate', 'value', 'version', 'retired_at'):
                        self.assertEqual(fact[key], node[key])
                    self.assertEqual(fact['valid_from'], node['first_observed_at'])
            self.assertEqual(meta['graph']['active_facts'], original['active_fact_ids'])

    def test_reject_incomplete_pair_and_fixed_instructions(self):
        for method in METHODS:
            with self.assertRaises(ValueError):
                build_memory(history()[:-1], method, 'none', len)
            with self.assertRaises(ValueError):
                build_memory([{'role': 'system', 'content': 'fixed'}] + history(), method, 'none', len)

    def test_semantic_audit_rejects_corrupted_fact_and_state(self):
        source = history()
        _, meta = build_memory(source, 'v2-dedup', 'none', len)
        graph = deepcopy(meta['graph'])
        graph['facts']['f0'][2] = {'location_id': 'wrong', 'value': '/invented'}
        with self.assertRaises(AssertionError):
            audit_semantic_index(GraphMemoryV2().build(source), graph)
        _, meta = build_memory(source, 'v1-compact', 'none', len)
        graph = deepcopy(meta['graph'])
        graph['state_nodes']['s0']['cwd']['value'] = '/invented'
        with self.assertRaises(AssertionError):
            audit_semantic_index(GraphMemory().build(source), graph)

    def test_chat_api_and_literal_reference_like_contents(self):
        source = [{'role': 'user', 'content': '{"inherits":"s1"}'},
                  {'role': 'assistant', 'content': None, 'tool_calls': [
                      {'id': 'c0', 'type': 'function', 'function': {'name': 'ls', 'arguments': '{}'}}]},
                  {'role': 'tool', 'tool_call_id': 'c0', 'content': '{"current_directory_content":["source_messages"]}'}]
        for method in METHODS:
            _, meta = build_memory(source, method, 'none', len)
            self.assertEqual(restore_history(meta['graph']), source)


if __name__ == '__main__':
    unittest.main()
