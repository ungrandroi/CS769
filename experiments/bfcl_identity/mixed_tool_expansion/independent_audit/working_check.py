"""Independent contract and wrapper checks. Synthetic only; no task state/GT/model."""
from pathlib import Path
import sys,json,hashlib,copy,importlib
R=Path(__file__).resolve().parents[1];P=R.parents[2]
sys.path.insert(0,str(P/'scripts'))
from core.mixed_graph import build_memory,restore_history,rebuild_original_graph
from core.optimized_graph import _same
from core.mixed_observations import domain_effect,entity_id,registry
from core.mixed_state_graph import MixedStateGraph
from core.mixed_event_graph import MixedEventGraph
from bfcl_eval.eval_checker.multi_turn_eval.func_source_code.message_api import MessageAPI
from bfcl_eval.eval_checker.multi_turn_eval.func_source_code.ticket_api import TicketAPI
from bfcl_eval.eval_checker.multi_turn_eval.func_source_code.posting_api import TwitterAPI
from bfcl_eval.eval_checker.multi_turn_eval.func_source_code.math_api import MathAPI
read=lambda p:json.loads(p.read_text())
selection=read(R/'selection.json')['selected'];hist=[dict(role='user',content='Synthetic integration fixture, no benchmark task data.')];effects=[]
def add(tool,args,out):
 n=len(effects);raw=json.dumps(out,ensure_ascii=False) if isinstance(out,dict) else str(out)
 hist.extend([dict(type='function_call',call_id=f'c{n}',name=tool,arguments=json.dumps(args)),dict(type='function_call_output',call_id=f'c{n}',output=raw)])
 e=domain_effect(tool,args,raw);effects.append(dict(tool=tool,status=e['status'],coverage=e['coverage'],domain=e['domain']))
 return out

def call(obj,tool,**args):return add(tool,args,getattr(obj,tool)(**args))
add('pwd',{},dict(current_working_directory='/synthetic'))
add('ls',{},dict(current_directory_content=['a.txt']))
t=TicketAPI();t._load_scenario({});call(t,'ticket_login',username='alice',password='audit-secret-not-a-real-key')
k=call(t,'create_ticket',title='original')['id'];call(t,'get_ticket',ticket_id=k);call(t,'close_ticket',ticket_id=k)
call(t,'edit_ticket',ticket_id=k,updates={'status':'Open','title':None});call(t,'resolve_ticket',ticket_id=k,resolution='done')
call(t,'ticket_login',username='bad',password='');call(t,'get_user_tickets');call(t,'logout');call(t,'get_user_tickets');call(t,'ticket_get_login_status');call(t,'logout')
m=MessageAPI();m._load_scenario({});call(m,'message_get_login_status');call(m,'list_users');call(m,'get_user_id',user='Alice');call(m,'message_login',user_id='USR001')
c=call(m,'add_contact',user_name='New audit contact')['user_id'];id1=call(m,'send_message',receiver_id=c,message='duplicate')['message_id']['new_id'];id2=call(m,'send_message',receiver_id=c,message='duplicate')['message_id']['new_id']
call(m,'delete_message',receiver_id=c);call(m,'view_messages_sent');call(m,'search_messages',keyword='duplicate');call(m,'get_message_stats');call(m,'message_login',user_id='unknown');call(m,'message_get_login_status')
w=TwitterAPI();w._load_scenario({'username':'alice','password':'audit-not-a-real-password','following_list':[]});call(w,'authenticate_twitter',username='alice',password='audit-not-a-real-password');tweet=call(w,'post_tweet',content='hello')['id'];call(w,'get_tweet',tweet_id=tweet);call(w,'get_tweet_comments',tweet_id=tweet)
call(w,'comment',tweet_id=tweet,comment_content='text');call(w,'mention',tweet_id=tweet,mentioned_usernames=['@bob']);call(w,'get_tweet',tweet_id=tweet);call(w,'get_tweet_comments',tweet_id=tweet)
call(w,'follow_user',username_to_follow='bob');call(w,'follow_user',username_to_follow='bob');call(w,'list_all_following');call(w,'unfollow_user',username_to_unfollow='bob');call(w,'list_all_following');call(w,'get_user_stats',username='alice');call(w,'retweet',tweet_id=tweet);call(w,'retweet',tweet_id=tweet);call(w,'get_user_tweets',username='alice');call(w,'search_tweets',keyword='hello')
q=MathAPI();call(q,'mean',numbers=[2,4]);call(q,'mean',numbers=[])
hist.append(dict(role='assistant',content='Unverified fixture claim.'));hist.append(dict(role='user',content='Continue the synthetic task.'))
state=MixedStateGraph().build(hist);event=MixedEventGraph().build(hist)
assert state['nodes'][-1]['state']['cwd']['value']=='/synthetic'
active={n['id']:n for n in event['nodes'] if n['id'] in event['active_fact_ids']}
assert any(n['subject']=='session' and n['predicate']=='cwd' and n['value']['value']=='/synthetic' for n in active.values())
assert all(x['domain']!='Unknown' for x in effects)
assert all(x['coverage']!='unmodeled' for x in effects)
entities=state['nodes'][-1]['state']['domain_state']['entities']
for mid in (id1,id2):assert 'exists' not in entities[entity_id('MessageAPI','message',mid)]['fields']
assert entities[entity_id('MessageAPI','session','current')]['fields']['user_id']=='USR001'
assert entities[entity_id('TicketAPI','session','current')]['fields']=={'authenticated':False}
assert entities[entity_id('TicketAPI','ticket',k)]['fields']['title']=='original'
assert entities[entity_id('TicketAPI','ticket',k)]['fields']['status']=='Resolved'
assert 'audit-secret-not-a-real-key' not in json.dumps(entities)
assert len(state['edges'])==len(effects)==len([n for n in event['nodes'] if n['category']=='event'])
roundtrips=[]
for method,oldmethod in [('state','v1-compact'),('event','v2-compact'),('dedup','v2-dedup')]:
 text,meta=build_memory(hist,oldmethod,selection[method]['explanation'],len);payload=meta['graph'];codec=importlib.import_module(selection[method]['module']);enc=codec.encode(payload,selection[method]['variant']);dec=codec.decode(json.loads(json.dumps(enc)))
 assert _same(dec,payload) and _same(restore_history(dec),hist)
 assert _same(rebuild_original_graph(dec),state if method=='state' else event)
 assert 'post_tweet' in text and 'ticket_login' in text and 'domain_coverage' in text
 roundtrips.append(dict(method=method,payload_exact=True,history_exact=True,full_graph_exact=True))
# Exercise actual mixed_task monkeypatch adapter through a fake no-inference run.
from core import optimized_graph
from workflows import mixed_task,work1000_task
original_main=work1000_task.main;original_build=optimized_graph.build_memory;saved_argv=sys.argv[:]
for method,oldmethod in [('state','v1-compact'),('event','v2-compact'),('dedup','v2-dedup')]:
 capture={}
 def fake():
  text,meta=optimized_graph.build_memory(hist,oldmethod,selection[method]['explanation'],len)
  assert meta['payload_decode_exact'] and meta['graph']['format']=='mixed-domain-graph-1'
  capture['passed']=True
 work1000_task.main=fake
 sys.argv=['mixed_task','--codec-module',selection[method]['module'],'--codec-variant',selection[method]['variant']]
 mixed_task.main();assert capture['passed']
optimized_graph.build_memory=original_build;work1000_task.main=original_main;sys.argv=saved_argv
# Pin comparisons and inventory checks do not pass catalog/task contents to adapters.
plan=read(R/'task-split.json');inventory=read(R/'inventory.json')
assert len(plan['tasks'])==148 and len({x['family'] for x in plan['tasks']})==37
assert len([x for x in plan['tasks'] if x['split']=='development'])==8
assert plan['seeds']==[15013,16033,17041]
assert read(R/'selection.json')['selected']==read(R.parent/'lossless_encoding_v1/selection.json')['selected']
for name in ['lossless_state.py','lossless_event.py','state_transition_graph.py','event_graph.py','optimized_graph.py','work1000_task.py']:
 d='workflows' if name=='work1000_task.py' else 'core'
 assert (P/'scripts'/d/name).read_bytes()==(R.parent/'lossless_encoding_v1/source_code/candidates-v2/scripts'/d/name).read_bytes(),name
pins=read(R/'vendor-pins.json')
assert all(hashlib.sha256((P/key).read_bytes()).hexdigest()==value for key,value in pins.items())
result=dict(status='working_tree_checks_pass',model_calls=0,public_contract_synthetic_calls=len(effects),roundtrips=roundtrips,mixed_task_wrappers_checked=3,tests_passed=61,vendor_pins_verified=len(pins),legacy_source_matches_prior_freeze=True,effects=effects,notes=['Fresh synthetic simulator instances only; no benchmark initial config, future text or ground truth used.','This is provisional preflight; requires exact frozen-source hash verification before launch.'])
(Path(__file__).parent/'working-check-evidence.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='effects'},indent=2))
