"""G9 offline ownership, exact-ID grouping, ablation and payload edit checks."""
from copy import deepcopy
import json
import unittest

from core.graph_memory_observed import build_observed_graph
from core.graph_memory_payload import build_payload_graph, render_payload_graph, _expand
from core.graph_memory_records import (
    build_record_graph, audit_record_graph, strip_record_graph, render_record_graph,
    render_record_segments, plan_record_projection, audit_record_projection_plan,
)
from test_graph_memory_observed import fixture
from test_graph_memory_payload import projected_text


def graph_for(exchanges, variant='record-joins-v1'):
    return build_record_graph(build_payload_graph(build_observed_graph(fixture(exchanges))), variant)


def orders(variant='record-joins-v1'):
    return graph_for([
        ('place_order', {'symbol': 'MSFT', 'amount': 2},
         '{ "order_id":12446, "price":27.0, "status":"Pending" }'),
        ('get_order_details', {'order_id': 12446},
         '{"id":12446,"price":27.0,"status":"Completed","metadata":{"note":"⟦f1⟧"}}'),
    ], variant)


def records(graph, category):
    return [n for n in graph['record_layer']['nodes'] if n['category'] == category]


def member(graph, key, event):
    nodes = {n['id']: n for n in graph['payload_layer']['nodes']}
    field = next(f for f in graph['payload_layer']['fields'] if f['event_id'] == event)
    root = nodes[nodes[field['root']]['value']]
    return next(mid for mid in root['members'] if json.loads(_expand(nodes[mid]['key'], nodes)) == key)


class RecordGraphTests(unittest.TestCase):
    def test_strict_join_binds_real_payload_nodes_without_content_copies(self):
        graph = orders()
        audit = audit_record_graph(graph)
        self.assertTrue(audit['ok'], audit)
        self.assertEqual((audit['record_count'], audit['occurrence_count'], audit['join_count'], audit['edge_count']), (3,3,1,3))
        self.assertNotIn('structured_layer', graph)
        for n in graph['record_layer']['nodes']:
            self.assertNotIn('value', n)
            self.assertNotIn('text', n)
        nodes = {n['id']: n for n in graph['payload_layer']['nodes']}
        for n in records(graph, 'identifier_occurrence'):
            self.assertEqual(nodes[n['member']]['value'], n['payload_node'])
            record = next(r for r in records(graph, 'payload_record') if r['id'] == n['record'])
            self.assertIn(n['member'], nodes[record['payload_node']]['members'])

    def test_strip_exact_render_segments_and_marker_collision(self):
        graph = orders()
        base = strip_record_graph(graph)
        before = deepcopy(base)
        self.assertEqual(strip_record_graph(build_record_graph(base)), base)
        text = render_record_graph(graph)
        original = render_payload_graph(base)
        self.assertIn('⟦f1⟧', text)
        self.assertEqual(text.count('12446'), original.count('12446'))
        self.assertEqual(''.join(s['text'] for s in render_record_segments(graph)
                                if not s['kind'].startswith('g9_')), original)
        self.assertEqual(base, before)

    def test_no_join_and_singletons_are_exact_g8_for_both_variants(self):
        for exchanges in ([('place_order', {}, {'order_id':7})],
                          [('unknown', {'id':7}, {'id':7})],
                          [('get_stock_info', {'symbol':'AAPL'}, {'symbol':'AAPL'})],
                          [('cat', {'file_name':'x'}, {'file_name':'x'})]):
            for variant in ('record-joins-v1','record-nodes-only-v1'):
                graph = graph_for(exchanges,variant)
                self.assertFalse(audit_record_graph(graph)['active'])
                self.assertEqual(graph['record_layer']['nodes'],[])
                self.assertEqual(render_record_graph(graph),render_payload_graph(strip_record_graph(graph)))

    def test_ablation_keeps_nodes_and_evidence_but_no_shared_assignment(self):
        full, ablated = orders(), orders('record-nodes-only-v1')
        self.assertEqual(strip_record_graph(full),strip_record_graph(ablated))
        self.assertEqual(full['record_layer']['nodes'],ablated['record_layer']['nodes'])
        self.assertEqual(ablated['record_layer']['edges'],[])
        self.assertEqual(audit_record_graph(ablated)['edge_count'],0)
        for n in records(ablated,'identifier_occurrence'):
            self.assertFalse({'anchor','group','anchor_id','value_sha256'} & set(n))
        text=render_record_graph(ablated)
        footer=text.split('\n\nIdentifier links')[1]
        self.assertIn('j0 trading:order_id',footer)
        self.assertNotIn('o0',footer)
        self.assertNotIn('o1',footer)
        self.assertIn('j0 trading:order_id: o0 o1 o2',render_record_graph(full))

    def test_namespace_and_types_do_not_cross_join(self):
        graph=graph_for([('get_ticket',{'ticket_id':7},{'id':7}),
                         ('get_order_details',{'order_id':7},{'id':7}),
                         ('get_order_details',{'order_id':'7'},{'id':True})])
        anchors=records(graph,'identifier_anchor')
        self.assertEqual({n['namespace'] for n in anchors},{'tickets:ticket_id','trading:order_id'})
        self.assertEqual(len(records(graph,'identifier_occurrence')),4)

    def test_duplicate_key_opaque_and_encoded_documents_abstain(self):
        for output in ('{"id":7,"id":7}', 'id=7', [{'type':'text','text':'{"id":7}'}]):
            graph=graph_for([('get_ticket',{'ticket_id':7},output)])
            self.assertFalse(audit_record_graph(graph)['active'])

    def test_nested_record_has_own_members_no_ancestor_propagation(self):
        graph=graph_for([('book_flight',{}, {'booking_id':'b','booking_history':{'booking_id':'b','travel_cost':8}})])
        self.assertEqual(audit_record_graph(graph)['record_count'],2)
        occ=records(graph,'identifier_occurrence')
        self.assertEqual({n['source']['pointer'] for n in occ},{'/booking_id','/booking_history/booking_id'})
        self.assertNotEqual(occ[0]['record'],occ[1]['record'])

    def test_array_objects_without_registered_paths_do_not_invent_contracts(self):
        graph=graph_for([('get_ticket',{'ticket_id':7},[{'id':7,'title':'a'},{'id':7,'title':'b'}])])
        self.assertFalse(audit_record_graph(graph)['active'])
        self.assertEqual(render_record_graph(graph),render_payload_graph(strip_record_graph(graph)))

    def test_multi_id_record_does_not_merge_distinct_anchors(self):
        graph=graph_for([('retrieve_invoice',{'booking_id':'x','insurance_id':'x'},{}),
                         ('retrieve_invoice',{'booking_id':'x','insurance_id':'x'}, {})])
        self.assertEqual(audit_record_graph(graph)['record_count'],2)
        self.assertEqual(audit_record_graph(graph)['anchor_count'],2)
        self.assertEqual({n['namespace'] for n in records(graph,'identifier_anchor')},
                         {'travel:booking_id','travel:insurance_id'})
        self.assertEqual(audit_record_graph(graph)['edge_count'],4)

    def test_parallel_group_adds_membership_without_temporal_edge(self):
        from core.graph_memory_evidence import build_evidence_graph,inference_graph
        history=[{'role':'user','content':'Keep'},
            {'role':'assistant','tool_calls':[
                {'id':'a','type':'function','function':{'name':'get_ticket','arguments':'{"ticket_id":7}'}},
                {'id':'b','type':'function','function':{'name':'get_ticket','arguments':'{"ticket_id":7}'}}]},
            {'role':'tool','tool_call_id':'a','content':'{"id":7}'},
            {'role':'tool','tool_call_id':'b','content':'{"id":7}'}]
        base=inference_graph(build_evidence_graph(history,episodic_only=True))
        graph=build_record_graph(build_payload_graph(build_observed_graph(base)))
        self.assertEqual({e['relation'] for e in graph['record_layer']['edges']},{'same_typed_identifier_member'})
        self.assertEqual(audit_record_graph(graph)['occurrence_count'],4)

    def test_audit_rejects_tampered_sources_memberships_ids_and_extra_payload(self):
        graph=orders()
        bads=[]
        bad=deepcopy(graph);bad['record_layer']['nodes'].append(deepcopy(bad['record_layer']['nodes'][0]));bads.append(bad)
        bad=deepcopy(graph);bad['record_layer']['edges'][0]['to']='absent';bads.append(bad)
        bad=deepcopy(graph);records(bad,'identifier_occurrence')[0]['source']['pointer']='/price';bads.append(bad)
        bad=deepcopy(graph);records(bad,'identifier_occurrence')[0]['member']='g8:absent';bads.append(bad)
        bad=deepcopy(graph);records(bad,'identifier_anchor')[0]['value']=12446;bads.append(bad)
        bad=deepcopy(graph);bad['source_messages']=[];bads.append(bad)
        for bad in bads:
            self.assertFalse(audit_record_graph(bad)['ok'])
            with self.assertRaises(ValueError):render_record_graph(bad)

    def test_real_payload_sibling_projection_preserves_all_join_memberships(self):
        graph=orders();before=deepcopy(graph)
        plan=plan_record_projection(graph,removed_member_ids=[member(graph,'metadata','e4')])
        self.assertTrue(audit_record_projection_plan(graph,plan)['ok'])
        self.assertFalse(plan['applied'])
        self.assertEqual(plan['required_removed_record_edge_ids'],[])
        self.assertEqual(plan['surviving_join_count'],1)
        base=strip_record_graph(graph)
        field=next(f for f in base['payload_layer']['fields'] if f['event_id']=='e4')
        result=json.loads(projected_text(base,plan['payload_plan'],field))
        self.assertNotIn('metadata',result)
        self.assertEqual(result['id'],12446)
        self.assertEqual(result['status'],'Completed')
        self.assertEqual(graph,before)

    def test_id_projection_removes_one_record_link_and_keeps_other_two(self):
        graph=orders()
        plan=plan_record_projection(graph,removed_member_ids=[member(graph,'id','e4')])
        self.assertEqual(len(plan['required_removed_record_edge_ids']),1)
        self.assertEqual(len(plan['supported_record_edge_ids']),2)
        self.assertEqual(plan['surviving_join_count'],1)
        base=strip_record_graph(graph)
        field=next(f for f in base['payload_layer']['fields'] if f['event_id']=='e4')
        result=json.loads(projected_text(base,plan['payload_plan'],field))
        self.assertNotIn('id',result)
        self.assertEqual(result['price'],27)
        self.assertIn('metadata',result)
        self.assertTrue(audit_record_projection_plan(graph,plan)['ok'])
        bad=deepcopy(plan);bad['required_removed_record_edge_ids']=[]
        self.assertFalse(audit_record_projection_plan(graph,bad)['ok'])

    def test_projection_removes_unsupported_singletons_and_works_in_ablation(self):
        for variant in ('record-joins-v1','record-nodes-only-v1'):
            graph=graph_for([('get_ticket',{'ticket_id':7},{'id':7,'title':'keep'})],variant)
            plan=plan_record_projection(graph,removed_member_ids=[member(graph,'id','e2')])
            self.assertEqual(plan['surviving_join_count'],0)
            self.assertEqual(plan['supported_record_node_ids'],[])
            self.assertEqual(plan['supported_record_edge_ids'],[])
            self.assertTrue(audit_record_projection_plan(graph,plan)['ok'])

    def test_bad_variant_and_archive_input_rejected(self):
        base=strip_record_graph(orders())
        with self.assertRaises(ValueError):build_record_graph(base,'unknown')
        with self.assertRaises(ValueError):build_record_graph({**base,'archive':{}})


if __name__=='__main__':
    unittest.main()
