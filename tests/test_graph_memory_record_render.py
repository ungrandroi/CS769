"""Offline tests of G9 serialization only; frozen graph semantics are reused."""
from copy import deepcopy
import json
import unittest

from core import graph_memory_payload as p
from core import graph_memory_records as r
from core import graph_memory_record_render as x
from test_graph_memory_records import graph_for, orders, records, member
from test_graph_memory_observed import climate
from core.graph_memory_observed import build_observed_graph


class ExternalRecordRenderTests(unittest.TestCase):
    def test_body_is_exact_g7_and_graph_is_unchanged(self):
        graph = orders(); before = deepcopy(graph)
        segments = x.render_external_record_segments(graph)
        base = p.render_payload_graph(r.strip_record_graph(graph), layout='g7-compatible')
        self.assertEqual(segments[0], {'kind': 'g7-compatible', 'text': base})
        self.assertEqual([s['kind'] for s in segments], ['g7-compatible', 'g9_external_references'])
        text = x.render_external_record_graph(graph)
        self.assertEqual(text, base + segments[1]['text'])
        self.assertIn('⟦f1⟧', base)  # genuine source text must survive
        self.assertEqual(text.count('12446'), base.count('12446'))
        self.assertNotIn('12446', segments[1]['text'])
        self.assertNotIn('Completed', segments[1]['text'])
        self.assertEqual(graph, before)

    def test_root_and_occurrence_addresses_are_explicit(self):
        text = x.render_external_record_segments(orders())[1]['text']
        self.assertIn('r0 e2["output"] pointer=""', text)
        self.assertIn('r1 e3["arguments"] pointer=""', text)
        self.assertIn('o0 [r0] e2["output"] pointer="/order_id"', text)
        self.assertIn('o2 [r2] e4["output"] pointer="/id"', text)
        self.assertIn('j0 trading:order_id (int): o0 o1 o2', text)

    def test_nested_record_root_is_direct_parent_not_ancestor(self):
        graph = graph_for([('book_flight', {},
            {'booking_id':'b', 'booking_history':{'booking_id':'b', 'travel_cost':8}})])
        text = x.render_external_record_segments(graph)[1]['text']
        self.assertIn('r0 e2["output"] pointer=""', text)
        self.assertIn('r1 e2["output"] pointer="/booking_history"', text)
        self.assertIn('o1 [r1] e2["output"] pointer="/booking_history/booking_id"', text)

    def test_nodes_only_removes_memberships_not_sources_or_participant_selection(self):
        full, ablated = orders(), orders('record-nodes-only-v1')
        self.assertEqual(full['record_layer']['nodes'], ablated['record_layer']['nodes'])
        a = x.render_external_record_segments(full)
        b = x.render_external_record_segments(ablated)
        self.assertEqual(a[0], b[0])
        self.assertEqual(a[1]['text'].splitlines()[:-1], b[1]['text'].splitlines()[:-1])
        self.assertEqual(b[1]['text'].splitlines()[-1], 'j0 trading:order_id (int)')
        self.assertEqual(ablated['record_layer']['edges'], [])
        for node in records(ablated, 'identifier_occurrence'):
            self.assertFalse({'anchor', 'group', 'anchor_id'} & set(node))

    def test_no_join_is_exact_g7_for_both_variants(self):
        for exchanges in ([('place_order', {}, {'order_id':7})],
                          [('unknown', {'id':7}, {'id':7})],
                          [('get_stock_info', {'symbol':'AAPL'}, {'symbol':'AAPL'})]):
            for variant in r.VARIANTS:
                graph = graph_for(exchanges, variant)
                expected = p.render_payload_graph(r.strip_record_graph(graph), layout='g7-compatible')
                self.assertEqual(x.render_external_record_graph(graph), expected)
                self.assertEqual(len(x.render_external_record_segments(graph)), 1)
                audit = x.audit_external_record_render(graph, rendered_text=expected)
                self.assertTrue(audit['ok'] and audit['payload_preserved'] and audit['exact_g7'])
                self.assertEqual(audit['added_characters'], 0)

    def test_nonempty_g7_appendix_is_preserved_with_no_join(self):
        base = p.build_payload_graph(build_observed_graph(climate()))
        self.assertTrue(base['observed_layer']['nodes'])
        for variant in r.VARIANTS:
            self.assertEqual(x.render_external_record_graph(r.build_record_graph(base, variant)),
                             p.render_payload_graph(base, layout='g7-compatible'))

    def test_ambiguous_opaque_encoded_and_unregistered_array_paths_still_abstain(self):
        for result in ('{"id":7,"id":7}', 'id=7', [{'type':'text','text':'{"id":7}'}],
                       [{'id':7}, {'id':7}]):
            graph = graph_for([('get_ticket', {'ticket_id':7}, result)])
            self.assertFalse(r.audit_record_graph(graph)['active'])
            self.assertTrue(x.audit_external_record_render(graph)['exact_g7'])

    def test_pointer_label_roundtrips_without_uri_encoding(self):
        field = 'function.args"\\\n字'
        pointer = '/a~1b/~0x/0/quote"\\\n%#'
        label = x._source_label('e1', field, pointer)
        self.assertEqual(label, 'e1[' + json.dumps(field, ensure_ascii=False) +
                         '] pointer=' + json.dumps(pointer, ensure_ascii=False))
        self.assertEqual(json.loads(label.split(' pointer=', 1)[1]), pointer)
        self.assertEqual(p._pointer_tokens(pointer), ['a/b','~x','0','quote"\\\n%#'])
        self.assertNotIn('\n', label)
        for bad in ('a', '/a~2b'):
            with self.assertRaises(ValueError): x._source_label('e1', field, bad)

    def test_array_and_escaped_pointer_resolver_without_contract_extension(self):
        # Storage/address unit test only: these unknown-tool IDs create no G9 join.
        graph = graph_for([('unknown', {}, {'a/b': [{'~key': {'x':7}}]})])
        field = next(f for f in graph['payload_layer']['fields'] if f['event_id']=='e2')
        nodes = {n['id']:n for n in graph['payload_layer']['nodes']}
        target, exact = p._locate(field['root'], '/a~1b/0/~0key', nodes)
        self.assertEqual(exact, 'exact_value_node')
        self.assertEqual(json.loads(p._expand(target, nodes)), {'x':7})
        self.assertFalse(r.audit_record_graph(graph)['active'])

    def test_parallel_calls_keep_base_order_and_have_membership_only(self):
        from core.graph_memory_evidence import build_evidence_graph, inference_graph
        history = [{'role':'user', 'content':'Keep'},
            {'role':'assistant', 'tool_calls':[
                {'id':'a','type':'function','function':{'name':'get_ticket','arguments':'{"ticket_id":7}'}},
                {'id':'b','type':'function','function':{'name':'get_ticket','arguments':'{"ticket_id":7}'}}]},
            {'role':'tool','tool_call_id':'b','content':'{"id":7}'},
            {'role':'tool','tool_call_id':'a','content':'{"id":7}'}]
        base = p.build_payload_graph(build_observed_graph(inference_graph(
            build_evidence_graph(history, episodic_only=True))))
        graph = r.build_record_graph(base)
        self.assertEqual(x.render_external_record_segments(graph)[0]['text'],
                         p.render_payload_graph(base, layout='g7-compatible'))
        self.assertEqual({e['relation'] for e in graph['record_layer']['edges']},
                         {'same_typed_identifier_member'})
        appendix = x.render_external_record_segments(graph)[1]['text']
        self.assertNotIn('prior', appendix)
        self.assertNotIn('current', appendix)

    def test_projection_plans_are_identical_before_and_after_rendering(self):
        for variant in r.VARIANTS:
            graph = orders(variant)
            for key in ('metadata', 'id'):
                args = {'removed_member_ids':[member(graph, key, 'e4')]}
                before = r.plan_record_projection(graph, **args)
                x.render_external_record_graph(graph)
                after = r.plan_record_projection(graph, **args)
                self.assertEqual(before, after)
                self.assertTrue(r.audit_record_projection_plan(graph, after)['ok'])
                self.assertFalse(after['applied'])
                self.assertEqual(len(after['supported_record_edge_ids']),
                    (3 if key=='metadata' else 2) if variant=='record-joins-v1' else 0)

    def test_audit_and_renderer_reject_tampering_or_archive_input(self):
        good = orders()
        bads = []
        bad = deepcopy(good); records(bad, 'identifier_occurrence')[0]['source']['pointer']='/price'; bads.append(bad)
        bad = deepcopy(good); bad['source_messages']=[]; bads.append(bad)
        bad = deepcopy(good); bad['record_layer']['edges'][0]['to']='absent'; bads.append(bad)
        for bad in bads:
            self.assertFalse(x.audit_external_record_render(bad)['ok'])
            with self.assertRaises(ValueError): x.render_external_record_graph(bad)
        text = x.render_external_record_graph(good)
        audit = x.audit_external_record_render(good, rendered_text=text)
        self.assertTrue(audit['ok'] and audit['payload_preserved'])
        self.assertEqual((audit['locator_count'], audit['edge_count']), (6,3))
        self.assertEqual(audit['characters'], len(text))
        self.assertFalse(x.audit_external_record_render(good, rendered_text=text+' ')['ok'])


if __name__ == '__main__':
    unittest.main()
