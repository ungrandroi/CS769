import copy,json,os,socket,unittest
from pathlib import Path
from unittest.mock import patch
from cs769 import ExperimentConfig,load_config,prepare
from cs769.history import checkpoint_reached,dumps
from cs769.requests import build_request
from cs769.metrics import Usage,paired
from cs769.session import MemorySession
from cs769.runtime import continue_run
from cs769.registry import register_editor
from cs769.edits import subtree_share,series_merge

ROOT=Path(__file__).resolve().parents[1]
def config(name):return load_config(ROOT/'configs'/(name+'.json'))
def fixture(n=5):
 h=[{'role':'system','content':'Use tools.'},{'role':'user','content':'Inspect files.'}]
 for i in range(n):
  h += [{'role':'assistant','content':None,'tool_calls':[{'id':f'c{i}','type':'function','function':{'name':'cat','arguments':'{"file_name":"x.txt"}'}}]},
        {'role':'tool','tool_call_id':f'c{i}','content':json.dumps({'content':'Repeated observations remain visible. '*30})}]
 return h

class Tests(unittest.TestCase):
 def setUp(self):
  self.block=patch.object(socket.socket,'connect',side_effect=AssertionError('Network forbidden'));self.block.start()
 def tearDown(self):self.block.stop()
 def test_presets_and_isolation(self):
  history=fixture();original=copy.deepcopy(history)
  for path in (ROOT/'configs').glob('*.json'):
   c=load_config(path)
   if c.model['provider']=='anthropic' or c.memory['options'].get('semantics')=='mixed':continue
   with self.subTest(path=path.name):
    r=prepare(history,c,len,next_messages=[{'role':'user','content':'Continue.'}],counter_name='characters')
    self.assertEqual(history,original);self.assertTrue(r['messages']);self.assertEqual(r['metrics']['counter'],'characters')
    if c.delivery['mode']=='replace':self.assertFalse(any(m.get('role')=='tool' or m.get('tool_calls') for m in r['messages']))
 def test_identity_exact(self):
  h=fixture();self.assertEqual(prepare(h,config('identity'),len)['messages'],h)
 def test_pending_calls_rejected(self):
  with self.assertRaises(ValueError):prepare(fixture()[:-1],config('g9-working-history'),len)
 def test_disabled_edit(self):
  c=config('delete-2');c.edits[0]['enabled']=False
  self.assertEqual(prepare(fixture(),c,len)['memory_text'],prepare(fixture(),config('g9-view-full'),len)['memory_text'])
 def test_delete_count(self):
  for n in (1,2,3):
   c=config('delete-1-oldest' if n==1 else 'delete-'+str(n));r=prepare(fixture(),c,len)
   self.assertEqual(r['edits'][0]['audit']['removed_interactions'],n)
   self.assertFalse(r['edits'][0]['audit']['full_original_evidence_preserved'])
 def test_sharing_restores_exactly(self):
  h=fixture();full=prepare(h,config('g9-view-full'),len);r=prepare(h,config('share-observations'),len)
  self.assertEqual(r['edits'][0]['status'],'applied');self.assertEqual(subtree_share.restore(r['graph']),full['graph'])
  self.assertLess(len(r['memory_text']),len(full['memory_text']))
 def test_summary_versions(self):
  raw=dumps([400.0]*153)
  with self.assertRaises(ValueError):series_merge.array_summary(raw,min_elements=256,eligibility='noninteger')
  _,audit=series_merge.array_summary(raw,min_elements=128,tail_elements=8,eligibility='decimal_literal')
  self.assertEqual(audit['retained_individual_elements'],9)
  with self.assertRaises(ValueError):series_merge.array_summary(dumps([400]*153))
 def test_summary_edit_changes_graph(self):
  h=fixture(1);h[-1]['content']=dumps({'prices':[400.0]*153})
  r=prepare(h,config('numeric-summary-v2'),len)
  self.assertEqual(r['edits'][0]['status'],'applied');self.assertIn('__numeric_series_summary__',r['memory_text'])
 def test_unknown_config_rejected(self):
  with self.assertRaises(ValueError):ExperimentConfig.from_dict({'memroy':{}})
  c=config('g9-view-full');c.memory['options']['viwe']='full'
  with self.assertRaises(ValueError):prepare(fixture(),c,len)
 def test_no_identity_sidecar(self):
  c=config('g9-view-full');c.delivery['mode']='append'
  with self.assertRaises(ValueError):prepare(fixture(),c,len)
 def test_threshold_strict_and_balanced(self):
  h=fixture();n=len(dumps([m for m in h if m['role']!='system']))
  c={'kind':'history_tokens','counter':'history_json','threshold':n,'strict':True}
  self.assertFalse(checkpoint_reached(h,c,len));c['strict']=False;self.assertTrue(checkpoint_reached(h,c,len))
  self.assertFalse(checkpoint_reached(h[:-1],c,len))
 def test_session_once(self):
  c=config('g9-working-history');c.checkpoint['threshold']=1;s=MemorySession(c,len)
  h=fixture();first=s.project(h);suffix=[{'role':'assistant','content':'done'}]
  self.assertEqual(s.project(h+suffix),first+suffix)
  with self.assertRaises(ValueError):s.project(h[1:])
 def test_completed_turn_session(self):
  c=config('g9-view-full');s=MemorySession(c,len);h=fixture()+[{'role':'user','content':'New task.'}]
  r=s.project(h,completed_turns=1);self.assertEqual(r[-1],h[-1]);self.assertNotIn('New task.',r[-2]['content'])
 def test_selection(self):
  c=config('g9-view-full');c.selection['require_prefix_pass']=True;s=MemorySession(c,len)
  h=fixture()+[{'role':'user','content':'Next'}]
  with self.assertRaises(ValueError):s.project(h,completed_turns=1)
  self.assertEqual(s.project(h,completed_turns=1,prefix_passed=False),h);self.assertEqual(s.excluded_reason,'prefix_failed')
 def test_anthropic_visible_evidence(self):
  h=[{'role':'user','content':'Find tweet.'},{'role':'assistant','content':[{'type':'thinking','thinking':'secret','signature':'sig'},{'type':'tool_use','id':'a','name':'get_tweet','input':{'tweet_id':42}}]},
     {'role':'user','content':[{'type':'tool_result','tool_use_id':'a','content':'{"tweet_id":42,"text":"visible"}'}]}]
  c=config('g9-claude-sonnet-5-5');r=prepare(h,c,len);req=build_request(r,[])
  self.assertIn('visible',r['memory_text']);self.assertNotIn('secret',json.dumps(req));self.assertNotIn('seed',req)
 def test_plugin_mount(self):
  name='test_noop'
  if name not in __import__('cs769.registry',fromlist=['EDITORS']).EDITORS:
   register_editor(name,lambda g,count,current,opts:(copy.deepcopy(g),{'applied':True},__import__('cs769.edits.g9_edit',fromlist=['render']).render))
  c=config('g9-view-full');c.edits=[{'name':name}];self.assertEqual(prepare(fixture(),c,len)['edits'][0]['status'],'applied')
 def test_metrics_pairing(self):
  u=Usage();u.add({'usage':{'prompt_tokens':100,'completion_tokens':10},'choices':[{'message':{'tool_calls':[{},{}]}}]},'openai')
  v=copy.deepcopy(u);v.tool_calls=3;v.first_input_tokens=80
  rows=[{'task':'x','checkpoint_sha256':'s','repeat':1,'arm':a,'passed':p,'usage':q.report()} for a,p,q in [('identity',True,u),('g9',False,v)]]
  r=paired(rows);self.assertEqual(r['regressions'],['x']);self.assertEqual(r['net_added_tool_calls'],1);self.assertEqual(r['first_input_increase_percent'],-20)
  with self.assertRaises(ValueError):paired(rows+rows[:1])
 def test_anthropic_cache_accounting(self):
  u=Usage();u.add({'usage':{'input_tokens':10,'cache_read_input_tokens':20,'cache_creation_input_tokens':30,'output_tokens':5}},'anthropic')
  self.assertEqual(u.input_tokens,60);self.assertEqual(u.report()['total_tokens'],65)
 def test_runtime_injected_official_eval(self):
  class Env:
   def __init__(self):self.n=0
   def finished(self):return self.n==1
   def step(self,message):self.n+=1;return []
   def evaluate(self):return {'passed':True,'official_record':'fixture'}
  class Fake:
   def send(self,req):return {'choices':[{'message':{'role':'assistant','content':'done'}}],'usage':{'prompt_tokens':10,'completion_tokens':1}}
  class Ledger:
   limit_usd=1
   def reserve(self,req):return 'r'
   def settle(self,r,resp):pass
   def uncertain(self,r):raise AssertionError('unexpected')
  c=config('g9-view-full');c.execution['budget_usd']=1;r=prepare(fixture(),c,len)
  with self.assertRaises(PermissionError):continue_run(r,[],Env(),Fake(),Ledger())
  out=continue_run(r,[],Env(),Fake(),Ledger(),authorized=True);self.assertTrue(out['score']['passed']);self.assertEqual(out['usage']['requests'],1)
 def test_terminal_edit_composition_rejected(self):
  c=config('share-observations');c.edits+=config('delete-2').edits
  with self.assertRaisesRegex(ValueError,'last enabled'):prepare(fixture(),c,len)

 def test_active_identifier_views_and_query(self):
  h=[{'role':'user','content':'Post a tweet.'},
     {'role':'assistant','tool_calls':[{'id':'x','type':'function','function':{'name':'post_tweet','arguments':'{"content":"Hello"}'}}]},
     {'role':'tool','tool_call_id':'x','content':'{"id":42}'},
     {'role':'user','content':'Read that tweet.'},
     {'role':'assistant','tool_calls':[{'id':'y','type':'function','function':{'name':'get_tweet','arguments':'{"tweet_id":42}'}}]},
     {'role':'tool','tool_call_id':'y','content':'{"id":42,"content":"Hello"}'}]
  full=prepare(h,config('g9-view-full'),len);base=prepare(h,config('g9-view-base'),len)
  self.assertGreater(len(full['memory_text']),len(base['memory_text']))
  self.assertTrue(full['graph']['record_layer']['edges'])
  for name in ('g9-inline','g9-external','g9-signature','g9-lexical','g9-content_store'):
   with self.subTest(name=name):self.assertTrue(prepare(h,config(name),len)['memory_text'])
  call=[n for n in full['graph']['evidence_view']['nodes'] if n.get('category')=='tool_call'][-1]
  c=config('g9-query_layout-S');c.memory['options']['seeds']=[call['call_group']]
  moved=prepare(h,c,len);chronological=prepare(h,config('g9-query_layout-C'),len)
  self.assertNotEqual(moved['memory_text'],chronological['memory_text'])
  self.assertIn('Hello',moved['memory_text'])
 def test_nonempty_index_and_role(self):
  h=[{'role':'user','content':'Where am I?'},{'role':'assistant','tool_calls':[{'id':'p','type':'function','function':{'name':'pwd','arguments':'{}'}}]},
     {'role':'tool','tool_call_id':'p','content':'{"current_working_directory":"/home"}'}]
  b=prepare(h,config('b-native-index'),len)
  self.assertEqual(b['messages'][:len(h)],h);self.assertIn('/home',b['messages'][-1]['content'])
  v4=prepare(h,config('v4-application-memory'),len,next_messages=[{'role':'user','content':'Next'}])
  self.assertIn('<application_memory',v4['messages'][-1]['content']);self.assertEqual(v4['messages'][:len(h)],h)
 def test_config_inheritance_cycle(self):
  import tempfile
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'a.json';p.write_text('{"extends":"a.json"}')
   with self.assertRaisesRegex(ValueError,'cycle'):load_config(p)
 def test_custom_options_fail_without_skip(self):
  c=config('share-observations');c.edits[0]['options']['typo']=1
  with self.assertRaisesRegex(ValueError,'Unknown'):prepare(fixture(),c,len)
 def test_mixed_graphs(self):
  if not os.environ.get('CS769_BFCL_ROOT'):self.skipTest('Set external BFCL path for mixed-domain contracts')
  for path in (ROOT/'configs').glob('*.json'):
   c=load_config(path)
   if c.memory['options'].get('semantics')=='mixed':
    with self.subTest(path=path.name):self.assertTrue(prepare(fixture(),c,len)['audits']['codec_roundtrip'])

if __name__=='__main__':unittest.main()
