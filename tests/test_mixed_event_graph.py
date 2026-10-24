"""Contract fixtures, not simulator initial state or benchmark ground truth."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from core.mixed_event_graph import MixedEventGraph, ADAPTER_VERSION
from core.mixed_observations import entity_id


def history(*calls):
    messages = [{'role':'user','content':'Continue the visible task.'}]
    for index,(tool,args,result) in enumerate(calls):
        messages.extend([{'type':'function_call','call_id':f'call{index}','name':tool,
                          'arguments':json.dumps(args)},
                         {'type':'function_call_output','call_id':f'call{index}',
                          'output':result if isinstance(result,str) else json.dumps(result)}])
    return messages


def active(graph, subject=None, predicate=None):
    ids=set(graph['active_fact_ids'])
    return [n for n in graph['nodes'] if n['id'] in ids
            and (subject is None or n['subject']==subject)
            and (predicate is None or n['predicate']==predicate)]


def nodes(graph, category):
    return [n for n in graph['nodes'] if n['category']==category]


def fs_prefix():
    return [('pwd',{}, {'current_working_directory':'/demo'}),
            ('ls',{}, {'current_directory_content':['file.txt']})]


@pytest.mark.parametrize('tool,args,result',[
    ('mean',{'numbers':[2,4]},{'result':3.0}),
    ('authenticate_twitter',{'username':'alice','password':'opaque'},{'authentication_status':False}),
    ('message_login',{'user_id':'unknown'},{'login_status':False,'message':'Unknown user'}),
    ('get_user_tickets',{},"[{'error': 'User not authenticated.'}]"),
    ('get_ticket',{'ticket_id':4},{'id':4,'title':'A','status':'Open'}),
    ('get_tweet',{'tweet_id':4},{'id':4,'content':'error is a word in content'}),
])
def test_known_domains_preserve_filesystem(tool,args,result):
    prefix=MixedEventGraph().build(history(*fs_prefix()))
    graph=MixedEventGraph().build(history(*fs_prefix(),(tool,args,result)))
    old={n['id']:n for n in active(prefix)}
    new={n['id']:n for n in active(graph) if n['domain']=='GorillaFileSystem'}
    assert old==new
    assert nodes(graph,'event')[-1]['domain']!='Unknown'
    assert len(nodes(graph,'event'))==3


def test_namespaced_ids_and_repeated_observation_confirmation():
    tweet={'id':4,'username':'alice','content':'hello','tags':[],'mentions':[]}
    graph=MixedEventGraph().build(history(
        ('get_tweet',{'tweet_id':4},tweet),
        ('get_ticket',{'ticket_id':4},{'id':4,'title':'hello','status':'Open'}),
        ('get_tweet',{'tweet_id':4},tweet)))
    tid=entity_id('TwitterAPI','tweet',4);kid=entity_id('TicketAPI','ticket',4)
    assert tid!=kid and {tid,kid}<={n['id']for n in nodes(graph,'object')}
    content=active(graph,tid,'attribute.content')[0]
    assert content['version']==1
    assert [c['event']for c in content['confirmations']]==['a1','a3']
    assert len(nodes(graph,'event'))==3


def test_ticket_versions_retirement_revival_and_partial_edit():
    kid=entity_id('TicketAPI','ticket',4)
    graph=MixedEventGraph().build(history(
        ('get_ticket',{'ticket_id':4},{'id':4,'title':'keep','status':'Open','priority':2}),
        ('close_ticket',{'ticket_id':4},{'status':'Ticket 4 has been closed successfully.'}),
        ('edit_ticket',{'ticket_id':4,'updates':{'status':'Open','title':None}},
         {'status':'Ticket 4 has been updated successfully.'})))
    versions=[n for n in nodes(graph,'fact')if n['subject']==kid and n['predicate']=='attribute.status']
    assert [f['value']for f in versions]==['Open','Closed','Open']
    assert [f['version']for f in versions]==[1,2,3]
    assert [f['retired_at']for f in versions]==[2,3,None]
    assert active(graph,kid,'attribute.title')[0]['value']=='keep'
    assert active(graph,kid,'attribute.priority')[0]['value']==2
    assert MixedEventGraph().build(history(('close_ticket',{'ticket_id':4},{'error':'not found'})))['current_step']==1


def test_failed_login_preserves_session_and_credentials_not_semantic():
    sid=entity_id('TwitterAPI','session','current')
    messages=history(
        ('authenticate_twitter',{'username':'alice','password':'secret-marker'},{'authentication_status':True}),
        ('list_all_following',{}, {'following_list':['bob']}),
        ('authenticate_twitter',{'username':'bad','password':'wrong-marker'},{'authentication_status':False}))
    graph=MixedEventGraph().build(messages)
    assert active(graph,sid,'attribute.authenticated')[0]['value'] is True
    assert active(graph,sid,'attribute.username')[0]['value']=='alice'
    assert active(graph,sid,'attribute.following_list')[0]['value']==['bob']
    assert nodes(graph,'event')[-1]['status']=='error'
    assert graph['source_messages']==messages
    assert 'secret-marker' not in json.dumps(nodes(graph,'fact'))
    assert 'wrong-marker' not in json.dumps(nodes(graph,'fact'))


def test_successful_login_changes_actor_and_invalidates_old_view():
    sid=entity_id('TwitterAPI','session','current')
    graph=MixedEventGraph().build(history(
        ('authenticate_twitter',{'username':'alice','password':'x'},{'authentication_status':True}),
        ('list_all_following',{}, {'following_list':['bob']}),
        ('authenticate_twitter',{'username':'charlie','password':'y'},{'authentication_status':True})))
    assert active(graph,sid,'attribute.username')[0]['value']=='charlie'
    assert not active(graph,sid,'attribute.following_list')


def test_math_observations_are_per_call_not_global_mutable_state():
    graph=MixedEventGraph().build(history(
        ('mean',{'numbers':[2,4]},{'result':3.0}),
        ('mean',{'numbers':[2,4]},{'result':3.0}),
        ('mean',{'numbers':[4,6]},{'result':5.0})))
    observed=[f for f in active(graph)if f['domain']=='MathAPI']
    assert len(observed)==3
    assert {f['subject']for f in observed}=={'a1','a2','a3'}
    assert all(f['fact_scope']=='observation'for f in observed)
    assert [f['value']['value']['result']for f in observed]==[3.0,3.0,5.0]
    assert all(n['coverage']=='observation_only'for n in nodes(graph,'event'))


def test_message_delete_does_not_invent_deleted_identity():
    mid1=entity_id('MessageAPI','message',41);mid2=entity_id('MessageAPI','message',42)
    graph=MixedEventGraph().build(history(
        ('send_message',{'receiver_id':'USR002','message':'same'},
         {'sent_status':True,'message_id':{'new_id':41},'message':'sent'}),
        ('send_message',{'receiver_id':'USR002','message':'same'},
         {'sent_status':True,'message_id':{'new_id':42},'message':'sent'}),
        ('delete_message',{'receiver_id':'USR002'}, {'deleted_status':True,'receiver_id':'USR002'})))
    for mid in [mid1,mid2]:
        assert not active(graph,mid,'attribute.exists')
        assert active(graph,mid,'attribute.sent')[0]['value'] is True
        assert active(graph,mid,'attribute.content')[0]['value']=='same'
    assert not any(f['predicate']=='attribute.exists'and f['value'] is False for f in nodes(graph,'fact'))
    assert nodes(graph,'event')[-1]['operation_kind']=='delete_latest_message'
    assert any(e['relation']=='resolved_using'and e.get('role')=='receiver_thread_resolution'for e in graph['edges'])


def test_executor_error_and_false_status_query_are_different():
    graph=MixedEventGraph().build(history(*fs_prefix(),
        ('mkdir',{'dir_name':'bad'},'Error during execution: invalid directory'),
        ('message_get_login_status',{}, {'login_status':False})))
    assert nodes(graph,'event')[-2]['status']=='error'
    assert nodes(graph,'event')[-1]['status']=='success'
    sid=entity_id('MessageAPI','session','current')
    assert active(graph,sid,'attribute.authenticated')[0]['value'] is False
    assert active(graph,'session','cwd')[0]['value']['value']=='/demo'


def test_unknown_coverage_is_explicit_and_observations_survive():
    graph=MixedEventGraph().build(history(*fs_prefix(),
        ('mean',{'numbers':[2,4]},{'result':3}),
        ('unregistered_action',{}, {'ok':True})))
    event=nodes(graph,'event')[-1]
    assert event['domain']=='Unknown'and event['coverage']=='unmodeled'
    assert active(graph,'session','cwd')[0]['value']['value'] is None
    assert any(f['domain']=='MathAPI'and f['fact_scope']=='observation'for f in active(graph))
    assert 'unregistered_action' in graph['domain_coverage']['Unknown']
    assert 'post_tweet' not in json.dumps(graph['domain_coverage'])


def test_malformed_filesystem_write_does_not_invalidate_other_domains():
    kid=entity_id('TicketAPI','ticket',4)
    graph=MixedEventGraph().build(history(
        ('get_ticket',{'ticket_id':4},{'id':4,'status':'Open'}),
        ('mkdir',{'dir_name':'x'}, {'unexpected':'shape'})))
    assert active(graph,kid,'attribute.status')[0]['value']=='Open'
    assert nodes(graph,'event')[-1]['coverage']=='unmodeled'


def test_visible_source_preservation_pending_pair_validation_and_no_input_mutation():
    messages=history(('TicketAPI.get_ticket',{'ticket_id':4},{'id':4,'status':'Open'}))
    messages.append({'role':'assistant','content':'Unverified completion claim'})
    original=deepcopy(messages)
    graph=MixedEventGraph().build(messages)
    assert graph['source_messages']==original and messages==original
    assert graph['annotations'][-1]['verified_state'] is False
    assert graph['adapter_version']==ADAPTER_VERSION
    assert nodes(graph,'event')[0]['tool']=='TicketAPI.get_ticket'
    with pytest.raises(ValueError):MixedEventGraph().build(messages+[messages[1]])
    pending=MixedEventGraph().build(messages[:-2])
    assert len(pending['pending_calls'])==1


def test_type_sensitive_fact_values_are_not_merged():
    kid=entity_id('TicketAPI','ticket',4)
    graph=MixedEventGraph().build(history(
        ('get_ticket',{'ticket_id':4},{'id':4,'priority':1}),
        ('get_ticket',{'ticket_id':4},{'id':4,'priority':True}),
        ('get_ticket',{'ticket_id':4},{'id':4,'priority':1.0})))
    versions=[f for f in nodes(graph,'fact')if f['subject']==kid and f['predicate']=='attribute.priority']
    assert [type(f['value'])for f in versions]==[int,bool,float]
    assert [f['version']for f in versions]==[1,2,3]


def test_unknown_execution_failure_is_conservatively_global():
    graph=MixedEventGraph().build(history(*fs_prefix(),
        ('unregistered_action',{}, 'Error during execution: interrupted after an unknown effect')))
    assert nodes(graph,'event')[-1]['status']=='error'
    assert active(graph,'session','cwd')[0]['value']['value'] is None
    assert any(f['predicate']=='cwd' and f['value']['value']=='/demo'
               and f['retired_at']==3 and f['retired_reason'] for f in nodes(graph,'fact'))


def test_domain_identity_preserves_scalar_type_and_embedded_colons():
    graph=MixedEventGraph().build(history(
        ('get_ticket',{'ticket_id':4},{'id':4,'title':'numeric'}),
        ('get_ticket',{'ticket_id':'4'},{'id':'4','title':'string'}),
        ('get_user_id',{'user':'A'},{'user_id':'U:1'})))
    objects={n['id']:n for n in nodes(graph,'object')}
    assert objects[entity_id('TicketAPI','ticket',4)]['domain_id']==4
    assert objects[entity_id('TicketAPI','ticket','4')]['domain_id']=='4'
    assert objects[entity_id('MessageAPI','user','U:1')]['domain_id']=='U:1'
