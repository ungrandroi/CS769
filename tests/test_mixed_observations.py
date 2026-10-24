import json
import unittest
from core.mixed_observations import domain_effect, entity_id, parse_visible_return, registry


class MixedObservationTest(unittest.TestCase):
    def test_registry_all_public_tools_and_namespaces(self):
        reg=registry()
        self.assertEqual(len(reg['tools']),68)
        self.assertEqual(len(reg['source_sha256']),10)
        self.assertEqual(domain_effect('TwitterAPI.get_tweet',{'tweet_id':1},{'id':1,'content':'x'})['domain'],'TwitterAPI')
        self.assertEqual(domain_effect('Other.get_tweet',{}, {})['domain'],'Unknown')
        self.assertNotEqual(entity_id('TwitterAPI','tweet',1),entity_id('TicketAPI','ticket',1))
        self.assertNotEqual(entity_id('TicketAPI','ticket',1),entity_id('TicketAPI','ticket','1'))

    def test_error_formats_and_literal_parser(self):
        cases=[('mean',{},'Error during execution: invalid argument'),
               ('get_user_tickets',{},"[{'error': 'User not authenticated.'}]"),
               ('mean',{'numbers':[]},{'error':'Cannot calculate mean of an empty list'})]
        for tool,args,raw in cases:
            effect=domain_effect(tool,args,raw)
            self.assertEqual(effect['status'],'error')
            self.assertEqual(effect['updates'],[])
            self.assertEqual(effect['invalidations'],[])
        bad="__import__('os').system('echo should-not-run')"
        self.assertEqual(parse_visible_return(bad),bad)
        self.assertEqual(parse_visible_return("[{'id': 1, 'tags': []}]"),[{'id':1,'tags':[]}])

    def test_failed_login_and_false_status_query_distinct(self):
        for tool,raw in [('authenticate_twitter',{'authentication_status':False}),
                         ('message_login',{'login_status':False}),('ticket_login',{'success':False})]:
            effect=domain_effect(tool,{},raw)
            self.assertEqual(effect['status'],'error')
            self.assertEqual(effect['updates'],[])
            self.assertEqual(effect['invalidations'],[])
        effect=domain_effect('message_get_login_status',{}, {'login_status':False})
        self.assertEqual(effect['status'],'success')
        self.assertEqual(effect['updates'][0]['fields'],{'authenticated':False})
        self.assertEqual(domain_effect('logout',{}, {'success':False})['status'],'noop')

    def test_no_credential_facts_and_successful_session_replacement(self):
        effect=domain_effect('ticket_login',{'username':'alice','password':'sentinel-secret'},{'success':True})
        self.assertNotIn('sentinel-secret',json.dumps(effect))
        self.assertEqual(effect['updates'][0]['fields'],{'authenticated':True,'username':'alice'})
        self.assertIsNone(effect['invalidations'][0]['fields'])

    def test_math_and_nested_message_identifier(self):
        effect=domain_effect('mean',{'numbers':[2,4]}, {'result':3.0})
        self.assertEqual(effect['footprint'],'read')
        self.assertEqual(effect['invalidations'],[])
        self.assertEqual(effect['observations'][0]['value']['result'],3.0)
        effect=domain_effect('send_message',{'receiver_id':'USR002','message':'hi'},
                             {'sent_status':True,'message_id':{'new_id':12345},'message':'sent'})
        self.assertEqual(effect['updates'][0]['entity'],entity_id('MessageAPI','message',12345))
        effect=domain_effect('delete_message',{'receiver_id':'USR002'}, {'deleted_status':True,'receiver_id':'USR002'})
        self.assertEqual(effect['operation'],{'kind':'delete_latest_message','receiver_id':'USR002'})
        self.assertEqual(effect['updates'],[])

    def test_ticket_and_tweet_mutation_contracts(self):
        effect=domain_effect('close_ticket',{'ticket_id':4},{'status':'Ticket 4 has been closed successfully.'})
        self.assertEqual(effect['updates'][0]['fields'],{'status':'Closed'})
        effect=domain_effect('edit_ticket',{'ticket_id':4,'updates':{'title':None,'priority':3}},
                             {'status':'Ticket 4 has been updated successfully.'})
        self.assertEqual(effect['updates'][0]['fields'],{'priority':3})
        effect=domain_effect('mention',{'tweet_id':4,'mentioned_usernames':['@a']},{'mention_status':'Users mentioned successfully'})
        self.assertEqual(effect['invalidations'][0]['fields'],['mentions'])
        self.assertEqual(effect['updates'],[])
        self.assertEqual(domain_effect('follow_user',{'username_to_follow':'alice'},{'follow_status':False})['status'],'noop')

    def test_unknown_return_only_invalidates_own_domain(self):
        effect=domain_effect('post_tweet',{'content':'x'},'unrecognized write response')
        self.assertEqual(effect['status'],'unknown')
        self.assertEqual(effect['invalidations'][0]['domain'],'TwitterAPI')
        effect=domain_effect('get_tweet',{'tweet_id':4},'unrecognized read response')
        self.assertEqual(effect['invalidations'],[])
        self.assertEqual(domain_effect('completely_unknown',{},None)['invalidations'][0]['domain'],None)

    def test_list_snapshots_do_not_treat_content_as_errors(self):
        effect=domain_effect('get_user_tweets',{'username':'alice'},"[{'id': 1, 'content': 'error', 'tags': []}]")
        self.assertEqual(effect['status'],'success')
        self.assertEqual(effect['updates'][0]['fields']['content'],'error')
        effect=domain_effect('list_users',{}, {'user_list':['alice','bob']})
        self.assertEqual(effect['coverage'],'observation_only')
        self.assertEqual(effect['observations'][0]['value'],['alice','bob'])
