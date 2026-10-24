"""Independent full-artifact audit. CPU only. Writes only into its own directory."""
import os,sys,json,csv,hashlib,time,importlib,copy,random,math
from pathlib import Path
from collections import Counter,defaultdict
from statistics import mean
R=Path(__file__).resolve().parents[2]; OUT=Path(__file__).parent
sys.path.insert(0,str(R/'source_code/candidates-v2/scripts'))
os.environ['OPENAI_API_KEY']='local-no-key'
os.environ['PYTHONDONTWRITEBYTECODE']='1'
from core.optimized_graph import _same,restore_history,rebuild_original_graph,build_memory,dumps
from core.local_qwen_tokenizer import LocalQwenTokenizer
from core.qwen_transport import chat_messages
from core.qwen_prompt_accounting import to_chat_tools
from core.model_config import MODEL_KEY,SERVING_MODEL
from bfcl_eval.model_handler.api_inference.openai_response import OpenAIResponsesHandler
from bfcl_eval.eval_checker.eval_runner import _evaluate_single_multi_turn_entry
from bfcl_eval.utils import load_dataset_entry,load_ground_truth_entry
read=lambda p:json.loads(Path(p).read_text())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
plan=read(R/'task-split.json');selection=read(R/'selection.json'); summary=read(R/'reports/summary.json');paired=read(R/'reports/paired-analysis.json')
tasks={t['id']:t for t in plan['tasks']};stats=Counter();failures=[];checked=[];csvexpected=[];native_samples=[];allrows=[]
handler=OpenAIResponsesHandler(SERVING_MODEL,0.6,MODEL_KEY,True)
data={};gt={}
for category in {t['category'] for t in plan['tasks']}:
 data.update({x['id']:x for x in load_dataset_entry(category,include_prereq=False,include_language_specific_hint=False)})
 gt.update({x['id']:x for x in load_ground_truth_entry(category)})
tok=LocalQwenTokenizer()

def paired_history(h):
 seen=set();pending=set()
 for x in h:
  if x.get('type')=='function_call':
   k=x['call_id']; assert k and k not in seen; seen.add(k);pending.add(k)
  elif x.get('type')=='function_call_output':
   assert x['call_id'] in pending;pending.remove(x['call_id'])
 assert not pending

def audit_run(path,phase):
 m=read(path/'manifest.json');launch=read(path/'launch.json');task=tasks[m['task']]
 assert m['status'] in ('complete','not_triggered')
 assert m['category']==task['category'] and m['threshold']==1000
 assert m['sampling']==dict(temperature=.6,top_p=.95,top_k=20,repeat_penalty=1.)
 assert m['context']==131072 and m['max_tokens']==4096
 source=Path(m['identity']) if m['identity'] else None
 if m['status']=='not_triggered':
  assert not read(source/'manifest.json')['triggered'];assert not (path/'native.jsonl').exists()
  stats[phase+'_skipped']+=1;return
 stats[phase+'_actual']+=1
 tape=read(path/'api.json');acc=read(path/'accounting.json')
 raw=[json.loads(s) for s in (path/'native.jsonl').read_text().splitlines()]
 req={x['index']:x for x in raw if x['event']=='request'};res={x['index']:x for x in raw if x['event']=='response'}
 assert len(req)==len(res)==len(acc)==m['live_requests']
 assert set(req)==set(res)=={a['index'] for a in acc}
 boundary=m.get('trigger_index'); actual_work=[]
 for a in acc:
  i=a['index'];body=req[i]['request'];response=res[i]['response'];sdk=tape[i]['request']
  assert a['input_tokens']==response['usage']['prompt_tokens']==req[i]['input_tokens']
  assert a['working_tokens']==a['input_tokens']-a['fixed_tokens']>=0
  assert body['messages']==chat_messages(sdk['input']) and body['tools']==to_chat_tools(sdk['tools'])
  assert body['seed']==a['seed']==m['seed']+i*1000003
  assert body['max_tokens']==4096 and body['chat_template_kwargs']==dict(enable_thinking=False,preserve_thinking=False)
  assert response['model']==SERVING_MODEL
  assert all(body[k]==v for k,v in m['sampling'].items())
  paired_history(sdk['input']);stats['native_requests']+=1
  if a['working_tokens']>1000:actual_work.append(i)
 if not source:
  assert boundary==(actual_work[0] if actual_work else None)
 else:
  sm=read(source/'manifest.json');st=read(source/'api.json')
  assert boundary==sm['trigger_index']
  for k in ['task','category','seed','sampling','threshold']:assert m[k]==sm[k]
  assert len(tape[:boundary])==boundary
  for i in range(boundary):
   assert tape[i]['request']==st[i]['request'] and tape[i]['response']==st[i]['response']
  h=read(path/'checkpoint-history.json');assert h==st[boundary]['request']['input'];paired_history(h)
  w=[x for x in h if x.get('role') not in ('system','developer')]
  md=read(path/'memory-metadata.json');original=md['graph']
  assert _same(restore_history(original),w)
  _,ref=build_memory(w,original['method'],m['explanation'],tok.count)
  assert _same(original,ref['graph']) and md['instruction']==ref['instruction']
  if 'encoded' in md:
   codec=importlib.import_module(md['codec_module']);restored=codec.decode(json.loads(dumps(md['encoded'])))
   assert _same(restored,original)
   assert list(restored['source_messages'])==list(original['source_messages'])
   assert _same(rebuild_original_graph(restored),rebuild_original_graph(original))
   body=dumps(md['encoded']);stats['strict_candidate_decodes']+=1
  else:body=dumps(original)
  text=md['instruction']+'\n'+body if md['instruction'] else body
  assert text==(path/'memory.txt').read_text() and tok.count(text)==m['memory_tokens']==md['total_tokens']
  assert tok.count(body)==md['body_tokens'] and tok.count(md['instruction'])==md['instruction_tokens']
  initial=tape[boundary]['request']['input']
  assert initial==[*(x for x in h if x.get('role') in ('system','developer')),dict(role='user',content=text)]
  assert all(x['request']['input'][:len(initial)]==initial for x in tape[boundary:])
  stats['graph_payload_checks']+=1
 result_path=list((path/'result').rglob('*_result.json'));assert len(result_path)==1
 result=read(result_path[0]);assert result['id']==m['task']
 from bfcl_eval.eval_checker.multi_turn_eval import multi_turn_utils
 for key in list(vars(multi_turn_utils)):
  if key.endswith('_instance'): delattr(multi_turn_utils,key)
 scored=_evaluate_single_multi_turn_entry(handler,m['task'],copy.deepcopy(result['result']),copy.deepcopy(gt[m['task']]['ground_truth']),copy.deepcopy(data[m['task']]),MODEL_KEY,m['category'])
 saved=read(path/'official-score.json');assert bool(scored['valid'])==saved['passed']==m['passed']
 assert sha(result_path[0])==saved['result_sha256'] and sha(path/saved['score_file'])==saved['score_sha256']
 stats['official_scores_recomputed']+=1
 if phase=='evaluation' and m['triggered']:
  post=[a for a in acc if a['index']>=boundary];assert post
  row=dict(task=m['task'],seed=m['seed'],split=task['split'],method=path.name,passed=m['passed'],first_input=post[0]['input_tokens'],mean_post_input=mean(a['input_tokens'] for a in post),peak_input=max(a['input_tokens'] for a in post),mean_fixed=mean(a['fixed_tokens'] for a in post),mean_working=mean(a['working_tokens'] for a in post),live_requests=len(post),memory_tokens=m.get('memory_tokens'),instruction_tokens=m.get('instruction_tokens'))
  allrows.append(row)
  for n,a in enumerate(post,1):csvexpected.append(dict(task=m['task'],seed=m['seed'],split=task['split'],method=path.name,post_conversion_request=n,request_index=a['index'],user_turn=a['turn'],input_tokens=a['input_tokens'],fixed_tokens=a['fixed_tokens'],working_tokens=a['working_tokens']))
  if m['seed']==4409 and int(m['task'].rsplit('_',1)[1]) in (3,9,37):
   for a in [post[0],post[-1]]:
    native_samples.append(dict(path=str(path),index=a['index'],body=req[a['index']]['request'],accounting=a))
 checked.append(dict(path=str(path),passed=m['passed'],phase=phase))

for snapshot in (R/'source_code').iterdir():
 if (snapshot/'hashes.json').exists():
  hashes=read(snapshot/'hashes.json');assert all(sha(snapshot/p)==h for p,h in hashes.items());stats['snapshot_files_verified']+=len(hashes)
for name in ('preregistered-input-hashes.json','amendment-input-hashes.json'):
 for p,h in read(R/'runtime'/name).items():assert sha(R/p)==h
for phase in ['development','evaluation']:
 paths=sorted((R/phase).glob('*/*/*/manifest.json'))
 assert len(paths)==(252 if phase=='development' else 1092)
 for n,mp in enumerate(paths):
  try:audit_run(mp.parent,phase)
  except Exception as e:failures.append(dict(path=str(mp.parent),error=repr(e)))
  if n%100==0:print(phase,n,dict(stats),flush=True)
assert not failures,failures[:10]
# All stored aggregates must derive from the actual accounting, not inherited results.
by=lambda rows:{(x['task'],x['seed'],x['method']):x for x in rows}
assert by(allrows)==by(summary['rows'])
allrows=[by(allrows)[(r['task'],r['seed'],r['method'])] for r in summary['rows']]
observed=list(csv.DictReader((R/'reports/per-request-input.csv').open()))
assert len(observed)==len(csvexpected)
sortkey=lambda r:(r['task'],str(r['seed']),r['method'],int(r['request_index']))
assert sorted([{k:str(v) for k,v in row.items()} for row in csvexpected],key=sortkey)==sorted(observed,key=sortkey)
for split,groups in summary['groups'].items():
 subset=[x for x in allrows if split=='all' or (x['split']=='development')==(split=='development')]
 for label,g in groups.items():
  rows=[x for x in subset if x['method']==label]
  assert g==dict(n=len(rows),passed=sum(x['passed'] for x in rows),first_input=mean(x['first_input'] for x in rows),mean_post_input=mean(x['mean_post_input'] for x in rows),mean_peak_input=mean(x['peak_input'] for x in rows))
# Recompute development ranking from attempts independently, prior to fresh evaluations.
reg=read(R/'candidate-registry-v2.json')
for method in ['state','event','dedup']:
 choices=[]
 for v in [x for x in reg if x['method']==method]:
  rows=[]
  for t in tasks.values():
   if t['split']!='development':continue
   for seed in plan['development_seeds']:
    p=R/'development'/t['id']/f'seed{seed}'/v['label'];m=read(p/'manifest.json')
    if m['status']=='not_triggered':continue
    rows.append((m['passed'],mean(a['input_tokens'] for a in read(p/'accounting.json'))))
  choices.append((-sum(x[0] for x in rows),mean(x[1] for x in rows),v['label']))
 assert sorted(choices)[0][2]==selection['selected'][method]['label']
selection_time=(R/'selection.json').stat().st_mtime
first_fresh=min(read(p)['started_at'] for p in (R/'evaluation').glob('*/*/identity/manifest.json'))
last_dev=max(read(p).get('finished_at',read(p)['started_at']) for p in (R/'development').glob('*/*/*/manifest.json'))
assert last_dev<=selection_time<=first_fresh
# Recompute paired counts and clustered bootstrap without using the production analyzer.
rb=by(allrows);cluster_results={}
for split,methods in paired['statistics'].items():
 for method,comparisons in methods.items():
  cand=[x for x in allrows if x['method']==method+'-optimized' and (split=='all' or (x['split']=='development')==(split=='development'))]
  for control in ['baseline','identity']:
   delta=[];families={}
   for x in cand:
    other=rb[(x['task'],x['seed'],method+'-baseline' if control=='baseline' else 'identity')]
    d=int(x['passed'])-int(other['passed']);delta.append(d);families.setdefault(int(x['task'].rsplit('_',1)[1]),[]).append(d)
   o=comparisons['versus_'+control];g=delta.count(1);l=delta.count(-1);assert (o['gains'],o['losses'],o['n'])==(g,l,len(delta))
   assert o['success_difference']==mean(delta)
   n=g+l; p=min(1,2*sum(math.comb(n,k) for k in range(min(g,l)+1))/2**n) if n else 1
   assert p==o['descriptive_exact_mcnemar_p']
   # Match declared cluster sampling unit and seed; insertion ordering matches table order.
   rng=random.Random(574941);names=list(families);draws=[]
   for _ in range(10000):
    pick=rng.choices(names,k=len(names)) if False else [rng.choice(names) for _ in names]
    ds=[d for f in pick for d in families[f]];draws.append(sum(ds)/len(ds))
   draws.sort();assert [draws[249],draws[9749]]==o['family_cluster_bootstrap_95_interval']
   cluster_results[split+'/'+method+'/'+control]=dict(gains=g,losses=l,n=len(delta),interval=[draws[249],draws[9749]])
tok.close()
final=dict(status='artifact_checks_pass',time=time.time(),stats=dict(stats),failures=failures,selection_order=dict(last_development_finished=last_dev,selection_mtime=selection_time,first_fresh_started=first_fresh),official_scoring='Independently reran official _evaluate_single_multi_turn_entry for every actual completed run, including force-terminated outcomes; no output files or model requests.',csv_rows_verified=len(observed),cluster_statistics=cluster_results)
(OUT/'final-check-evidence.json').write_text(json.dumps(final,indent=2)+'\n')
(OUT/'native-accounting-samples.json').write_text(json.dumps(native_samples)+'\n')
print(json.dumps(final,indent=2),flush=True)
