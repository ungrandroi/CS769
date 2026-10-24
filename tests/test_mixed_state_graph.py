from copy import deepcopy
import json
import unittest
from core.mixed_state_graph import MixedStateGraph
from core.mixed_observations import entity_id


def history(steps):
    out=[{'role':'user','content':'Synthetic mixed-domain task.'}]
    for i,(tool,args,result) in enumerate(steps):
        out.extend([{'type':'function_call','call_id':f'c{i}','name':tool,'arguments':json.dumps(args)},
                    {'type':'function_call_output','call_id':f'c{i}','output':result if isinstance(result,str) else json.dumps(result)}])
    return out


def state(graph):return graph['nodes'][-1]['state']

def entity(graph,domain,kind,id):return state(graph)['domain_state']['entities'][entity_id(domain,kind,id)]


class MixedStateTest(unittest.TestCase):
    def test_nonfilesystem_does_not_clear_filesystem(self):
        messages=history([('pwd',{}, {'current_working_directory':'/demo'}),('ls',{}, {'current_directory_content':['a.txt']}),
                          ('mean',{'numbers':[2,4]},{'result':3.0}),('message_login',{'user_id':'bad'},{'login_status':False})])
        before=deepcopy(messages);g=MixedStateGraph().build(messages)
        self.assertEqual(messages,before);self.assertEqual(g['source_messages'],before)
        self.assertEqual(state(g)['cwd']['value'],'/demo')
        self.assertTrue(state(g)['objects'][0]['exists'])
        self.assertEqual(len(g['edges']),4);self.assertEqual(len(g['nodes']),5)
        self.assertTrue(all('domain_state' in n['state'] for n in g['nodes']))
        self.assertEqual(state(g)['domain_state']['observations'][0]['value']['result'],3.0)

    def test_namespaces_and_version_reconfirmation(self):
        steps=[('get_tweet',{'tweet_id':1},{'id':1,'content':'tweet'}),
               ('get_ticket',{'ticket_id':1},{'id':1,'status':'Open','title':'ticket'}),
               ('get_ticket',{'ticket_id':1},{'id':1,'status':'Open','title':'ticket'}),
               ('close_ticket',{'ticket_id':1},{'status':'Ticket 1 has been closed successfully.'}),
               ('edit_ticket',{'ticket_id':1,'updates':{'status':'Open'}},{'status':'Ticket 1 has been updated successfully.'})]
        g=MixedStateGraph().build(history(steps));ticket=entity(g,'TicketAPI','ticket',1)
        self.assertEqual(entity(g,'TwitterAPI','tweet',1)['fields']['content'],'tweet')
        self.assertEqual([v['value'] for v in ticket['versions']['status']],['Open','Closed','Open'])
        self.assertEqual(len(ticket['versions']['status'][0]['confirmations']),2)
        self.assertEqual(ticket['versions']['status'][0]['retired_at'],4)
        self.assertIsNone(ticket['versions']['status'][-1]['retired_at'])
        self.assertEqual(g['nodes'][2]['state']['domain_state']['entities'][entity_id('TicketAPI','ticket',1)]['fields']['status'],'Open')

    def test_failed_login_preserves_prior_session(self):
        steps=[('ticket_login',{'username':'alice','password':'raw-secret'},{'success':True}),
               ('ticket_login',{'username':'bob','password':''},{'success':False})]
        messages=history(steps);g=MixedStateGraph().build(messages)
        self.assertEqual(entity(g,'TicketAPI','session','current')['fields']['username'],'alice')
        self.assertTrue(entity(g,'TicketAPI','session','current')['fields']['authenticated'])
        self.assertNotIn('raw-secret',json.dumps(state(g)['domain_state']))
        self.assertIn('raw-secret',json.dumps(g['source_messages']))
        g=MixedStateGraph().build(history(steps+[('ticket_get_login_status',{}, {'login_status':False})]))
        self.assertEqual(entity(g,'TicketAPI','session','current')['fields'],{'authenticated':False})

    def test_delete_does_not_guess_deleted_message_identity(self):
        steps=[('send_message',{'receiver_id':'U2','message':'same'}, {'sent_status':True,'message_id':{'new_id':1}}),
               ('send_message',{'receiver_id':'U2','message':'same'}, {'sent_status':True,'message_id':{'new_id':2}}),
               ('delete_message',{'receiver_id':'U2'},{'deleted_status':True,'receiver_id':'U2'})]
        g=MixedStateGraph().build(history(steps))
        for i in (1,2):
            e=entity(g,'MessageAPI','message',i)
            self.assertNotIn('exists',e['fields']);self.assertTrue(e['fields']['sent'])
            self.assertEqual(e['fields']['content'],'same')
            self.assertEqual(e['versions']['exists'][0]['retired_at'],3)
        self.assertEqual(state(g)['domain_state']['observations'][-1]['kind'],'message_deleted_without_identity')

    def test_unmodeled_mutation_scoped_and_error_no_effect(self):
        prefix=[('pwd',{}, {'current_working_directory':'/demo'}),
                ('get_ticket',{'ticket_id':1},{'id':1,'status':'Open'}),
                ('get_tweet',{'tweet_id':1},{'id':1,'content':'tweet'})]
        g=MixedStateGraph().build(history(prefix+[('post_tweet',{},'unrecognized result')]))
        self.assertEqual(state(g)['cwd']['value'],'/demo')
        self.assertEqual(entity(g,'TicketAPI','ticket',1)['fields']['status'],'Open')
        self.assertEqual(entity(g,'TwitterAPI','tweet',1)['fields'],{})
        g=MixedStateGraph().build(history(prefix+[('cd',{},'Error during execution: missing folder')]))
        self.assertEqual(state(g)['cwd']['value'],'/demo');self.assertEqual(g['edges'][-1]['status'],'error')
        self.assertEqual(entity(g,'TwitterAPI','tweet',1)['fields']['content'],'tweet')

    def test_unknown_tool_global_conservative_and_pairing(self):
        g=MixedStateGraph().build(history([('pwd',{}, {'current_working_directory':'/demo'}),
                                         ('unknown_tool',{},'opaque result')]))
        self.assertIsNone(state(g)['cwd']['value']);self.assertEqual(g['edges'][-1]['status'],'unknown')
        duplicate=history([('mean',{'numbers':[1]},{'result':1}),('mean',{'numbers':[1]},{'result':1})])
        duplicate[-2]['call_id']='c0';duplicate[-1]['call_id']='c0'
        with self.assertRaises(ValueError):MixedStateGraph().build(duplicate)
