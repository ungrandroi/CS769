"""Read-only coverage audit; synthetic visible records, no simulator/GT/model access."""
import ast
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from core.state_transition_graph import GraphMemory, FS_READS, FS_WRITES
from core.event_graph import GraphMemoryV2

ROOT=Path('vendor/gorilla/berkeley-function-call-leaderboard/bfcl_eval')
OUT=Path('experiments/bfcl_identity/mixed_tool_expansion/coverage')
CLASSES={'GorillaFileSystem':'gorilla_file_system','TwitterAPI':'posting_api','MathAPI':'math_api',
         'MessageAPI':'message_api','TicketAPI':'ticket_api'}
def loadlines(path):return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
manifest={'method':'static source/contracts and synthetic visible-history builder probes only',
          'no_model_calls':True,'no_gt_read':True,'no_initial_config_used':True,'classes':{},'categories':{},'probes':[],'source_sha256':{}}
for category in ['base','long_context','miss_func','miss_param']:
    path=ROOT/'data'/f'BFCL_v4_multi_turn_{category}.json'
    tasks=loadlines(path)
    mixed=[t for t in tasks if 'GorillaFileSystem' in t['involved_classes'] and len(t['involved_classes'])>1]
    manifest['categories'][category]={'mixed_count':len(mixed),'class_counts':dict(Counter(c for t in mixed for c in t['involved_classes'])),
                                    'families':sorted(int(t['id'].rsplit('_',1)[1]) for t in mixed),
                                    'class_sets':dict(Counter('+'.join(sorted(t['involved_classes'])) for t in mixed))}
    manifest['source_sha256'][str(path)]=sha(path)
for cls,module in CLASSES.items():
    path=ROOT/'eval_checker/multi_turn_eval/func_source_code'/f'{module}.py'
    node=next(n for n in ast.parse(path.read_text()).body if isinstance(n,ast.ClassDef) and n.name==cls)
    methods={n.name:n.lineno for n in node.body if isinstance(n,ast.FunctionDef) and not n.name.startswith('_')}
    docs=loadlines(ROOT/'data/multi_turn_func_doc'/f'{module}.json')
    manifest['classes'][cls]={'source':str(path),'public_methods':methods,'documented_tools':[d['name'] for d in docs],
        'filesystem_dispatch_collisions':sorted(set(methods)&(FS_READS|FS_WRITES)) if cls!='GorillaFileSystem' else [],
        'semantic_adapter': 'filesystem partial' if cls=='GorillaFileSystem' else 'none',
        'call_return_preserved':True,'v1_tool_edge':True,'v2_execution_event':True,
        'nonfilesystem_state_facts':False if cls!='GorillaFileSystem' else None}
    manifest['source_sha256'][str(path)]=sha(path)

def pair(i,name,args,result):
    return [{'type':'function_call','call_id':f'audit_{i}','name':name,'arguments':json.dumps(args)},
            {'type':'function_call_output','call_id':f'audit_{i}','output':result if isinstance(result,str) else json.dumps(result)}]
prefix=[{'role':'user','content':'Synthetic adapter coverage probe; not a benchmark trajectory.'}]
prefix+=pair(0,'pwd',{}, {'current_working_directory':'/demo'})
prefix+=pair(1,'ls',{}, {'current_directory_content':['example.txt']})
examples=[('MathAPI','mean',{'numbers':[2,4]}, {'result':3.0},'success; no filesystem effects'),
          ('MathAPI','mean',{'numbers':[]}, {'error':'Cannot calculate mean of an empty list'},'error'),
          ('TwitterAPI','authenticate_twitter',{}, {'authentication_status':False},'authentication attempt failed; no success effect'),
          ('TwitterAPI','get_tweet',{'tweet_id':4},{'id':4,'username':'example','content':'sample','tags':[],'mentions':[]},'read observed tweet'),
          ('MessageAPI','message_login',{'user_id':'missing'}, {'login_status':False,'message':"User ID 'missing' not found."},'login attempt failed'),
          ('MessageAPI','message_get_login_status',{}, {'login_status':False},'successful observation of logged-out state'),
          ('TicketAPI','ticket_login',{}, {'success':False},'login attempt failed'),
          ('TicketAPI','get_user_tickets',{}, "[{'error': 'User not authenticated. Please log in to view tickets.'}]",'error serialized by BFCL list->str'),
          ('TicketAPI','get_ticket',{'ticket_id':4}, {'id':4,'title':'Example','description':'sample','status':'Open','priority':1,'created_by':'example'},'read observed ticket'),
          ('MathAPI','mean',{}, 'Error during execution: missing required argument', 'executor error')]
for cls,tool,args,result,expected in examples:
    history=prefix+pair(2,tool,args,result)
    v1=GraphMemory().build(history);v2=GraphMemoryV2().build(history)
    event=[n for n in v2['nodes'] if n.get('category')=='event'][-1]
    active=[n for n in v2['nodes'] if n.get('category')=='fact' and n['retired_at'] is None]
    assert v1['source_messages']==history==v2['source_messages']
    manifest['probes'].append({'class':cls,'tool':tool,'fixture_kind':'contract-shaped synthetic visible return; no task execution',
        'return':result,'expected_interpretation':expected,'v1_status':v1['edges'][-1]['status'],'v2_status':event['status'],
        'v1_cwd_before':'/demo','v1_cwd_after':v1['nodes'][-1]['state']['cwd'],
        'v1_objects_after':v1['nodes'][-1]['state']['objects'],
        'v2_active_facts_after':[{'subject':f['subject'],'predicate':f['predicate'],'value':f['value']} for f in active],
        'v2_rule':event['rule'],'exact_source_retained':True})
for file in ['state_transition_graph.py','event_graph.py','optimized_graph.py','event_graph_dedup.py']:
    path=Path('scripts/core')/file;manifest['source_sha256'][str(path)]=sha(path)
(OUT/'builder-coverage.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'mixed_categories':manifest['categories'],'tools':{k:len(v['documented_tools']) for k,v in manifest['classes'].items()},
 'probes':[{k:r[k] for k in ['class','tool','v1_status','v2_status']} for r in manifest['probes']]},indent=2))
