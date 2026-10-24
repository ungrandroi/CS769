"""Independent CPU-only final audit of all mixed-domain records; no inference."""
from pathlib import Path
import sys,os,json,hashlib,copy,importlib,time
from collections import Counter
from statistics import mean
R=Path(__file__).resolve().parents[1];S=R/'source_code/adapters-v1';sys.path.insert(0,str(S/'scripts'));os.environ['OPENAI_API_KEY']='local-no-key'
from core import mixed_graph,optimized_graph
from core.local_qwen_tokenizer import LocalQwenTokenizer
from core.qwen_transport import chat_messages
from core.qwen_prompt_accounting import to_chat_tools
from core.model_config import MODEL_KEY,SERVING_MODEL
from core.mixed_observations import tool_spec
from workflows.mixed_controller import gate_expected,validate_gate,validate_completed,development_digest
from bfcl_eval.model_handler.api_inference.openai_response import OpenAIResponsesHandler
from bfcl_eval.eval_checker.eval_runner import _evaluate_single_multi_turn_entry
from bfcl_eval.eval_checker.multi_turn_eval import multi_turn_utils
from bfcl_eval.utils import load_dataset_entry,load_ground_truth_entry
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
plan=read(R/'task-split.json');selection=read(R/'selection.json')['selected'];tasks={t['id']:t for t in plan['tasks']};snapshot_hashes=read(S/'hashes.json')
assert all(sha(S/p)==h for p,h in snapshot_hashes.items());assert all(sha(S/p)==h for p,h in read(R/'vendor-pins.json').items());validate_gate(read(R/'preflight-review.json'),gate_expected(R,S))
data={};gt={}
for cat in {t['category'] for t in tasks.values()}:
 data.update({x['id']:x for x in load_dataset_entry(cat,include_prereq=False,include_language_specific_hint=False)});gt.update({x['id']:x for x in load_ground_truth_entry(cat)})
handler=OpenAIResponsesHandler(SERVING_MODEL,.6,MODEL_KEY,True);tok=LocalQwenTokenizer();counts=Counter();results=[];failed=[];pending=[];exposure=[];native_samples=[]
def paircheck(history):
 seen=set();pending=set()
 for x in history:
  if x.get('type')=='function_call':
   assert x['call_id'] not in seen and x['call_id'];seen.add(x['call_id']);pending.add(x['call_id'])
  elif x.get('type')=='function_call_output':assert x['call_id'] in pending;pending.remove(x['call_id'])
 assert not pending

def domains(history):return dict(Counter(tool_spec(x['name'])['domain'] for x in history if x.get('type')=='function_call'))

def check(p):
 m=read(p/'manifest.json');task=tasks[m['task']];method=m['method'];assert m['seed'] in plan['development_seeds' if p.parents[2].name=='development' else 'seeds']
 optimized=p.name.endswith('-optimized');variant=selection[method]['variant'] if optimized else 'mixed-domain-graph-1';expl=selection[method]['explanation'] if optimized else ('none' if method=='identity' else plan['baseline_explanations'][method]);source=None if method=='identity' else p.parent/'identity'
 expected=dict(task=m['task'],category=task['category'],seed=m['seed'],method=method,variant=variant,explanation=expl,threshold=1000,context=131072,max_tokens=4096,base_url='http://127.0.0.1:11436/v1',identity=str(source) if source else None,sampling=plan['sampling'])
 cmd=[sys.executable,'-m','workflows.mixed_task','--task',m['task'],'--category',task['category'],'--seed',str(m['seed']),'--method',method,'--variant',variant,'--explanation',expl,'--output',str(p),'--base-url',expected['base_url']]
 if source:cmd+=['--identity',str(source)]
 if optimized:cmd+=['--codec-module',selection[method]['module'],'--codec-variant',variant]
 validate_completed(p,expected,S,cmd)
 if m['status']=='not_triggered':assert not read(source/'manifest.json')['triggered'];counts['skips']+=1;return
 tape=read(p/'api.json');acc=read(p/'accounting.json');native=[json.loads(x) for x in (p/'native.jsonl').read_text().splitlines()];req={x['index']:x for x in native if x['event']=='request'};res={x['index']:x for x in native if x['event']=='response'}
 assert len(acc)==len(req)==len(res)==m['live_requests'];assert set(req)==set(res)=={a['index'] for a in acc}
 for a in acc:
  i=a['index'];b=req[i]['request'];assert a['input_tokens']==req[i]['input_tokens']==res[i]['response']['usage']['prompt_tokens'];assert a['working_tokens']==a['input_tokens']-a['fixed_tokens']>=0
  assert b['seed']==a['seed']==m['seed']+i*1000003;assert all(b[k]==v for k,v in m['sampling'].items());assert b['max_tokens']==4096
  assert b['messages']==chat_messages(tape[i]['request']['input']) and b['tools']==to_chat_tools(tape[i]['request']['tools'])
  assert b['chat_template_kwargs']==dict(enable_thinking=False,preserve_thinking=False);assert res[i]['response']['model']==SERVING_MODEL;paircheck(tape[i]['request']['input']);counts['native_requests']+=1
 boundary=m.get('trigger_index')
 if source:
  old=read(source/'manifest.json');st=read(source/'api.json');assert boundary==old['trigger_index']
  for i in range(boundary):assert tape[i]['request']==st[i]['request'] and tape[i]['response']==st[i]['response']
  h=read(p/'checkpoint-history.json');assert h==st[boundary]['request']['input'];paircheck(h);w=[x for x in h if x.get('role') not in ('system','developer')]
  md=read(p/'memory-metadata.json');payload=md['graph'];assert optimized_graph._same(mixed_graph.restore_history(payload),w)
  _,expected_md=mixed_graph.build_memory(w,payload['method'],expl,tok.count);assert optimized_graph._same(payload,expected_md['graph']);assert md['instruction']==expected_md['instruction']
  if optimized:
   codec=importlib.import_module(md['codec_module']);restored=codec.decode(json.loads(optimized_graph.dumps(md['encoded'])));assert optimized_graph._same(restored,payload)
   assert optimized_graph._same(mixed_graph.rebuild_original_graph(restored),mixed_graph.rebuild_original_graph(payload));counts['direct_codec_decodes']+=1;body=optimized_graph.dumps(md['encoded'])
   base=read(p.parent/(method+'-baseline')/'memory-metadata.json');assert optimized_graph._same(base['graph'],payload);counts['shared_semantic_pairs']+=1
  else:body=optimized_graph.dumps(payload)
  text=md['instruction']+'\n'+body if md['instruction'] else body
  assert text==(p/'memory.txt').read_text();assert tok.count(text)==m['memory_tokens']==md['total_tokens'];assert tok.count(body)==md['body_tokens'];assert tok.count(md['instruction'])==md['instruction_tokens']
  initial=[*(x for x in h if x.get('role') in ('system','developer')),dict(role='user',content=text)]
  assert all(x['request']['input'][:len(initial)]==initial for x in tape[boundary:]);counts['graph_payload_checks']+=1
 else:
  eligible=[a['index'] for a in acc if a['working_tokens']>1000];assert boundary==(eligible[0] if eligible else None);counts['identity_runs']+=1
  prefix=read(p/'checkpoint-history.json') if m['triggered'] else [];calls=[output for row in tape for output in row['response']['output'] if output.get('type')=='function_call']
  exposure.append(dict(task=m['task'],seed=m['seed'],triggered=m['triggered'],prefix_calls=domains(prefix),all_identity_calls=domains(calls)))
 resultfile=list((p/'result').rglob('*_result.json'));assert len(resultfile)==1;result=read(resultfile[0]);saved=read(p/'official-score.json')
 for key in list(vars(multi_turn_utils)):
  if key.endswith('_instance'):delattr(multi_turn_utils,key)
 official=_evaluate_single_multi_turn_entry(handler,m['task'],copy.deepcopy(result['result']),copy.deepcopy(gt[m['task']]['ground_truth']),copy.deepcopy(data[m['task']]),MODEL_KEY,m['category'])
 assert bool(official['valid'])==m['passed']==saved['passed'];assert sha(resultfile[0])==saved['result_sha256'];assert sha(p/saved['score_file'])==saved['score_sha256'];counts['official_scores_recomputed']+=1
 post=[a for a in acc if boundary is not None and a['index']>=boundary]
 results.append(dict(phase=p.parents[2].name,task=m['task'],seed=m['seed'],label=p.name,passed=m['passed'],live_requests=len(acc),first_input=post[0]['input_tokens'] if post else None,mean_post_input=mean(a['input_tokens'] for a in post) if post else None,official_error_type=(official.get('error') or {}).get('error_type')))
 if acc:
  for a in [acc[0],acc[-1]]:native_samples.append(dict(path=str(p),request=req[a['index']]['request'],accounting=a))

paths=sorted((R/'development').glob('*/*/*/manifest.json'))+sorted((R/'evaluation').glob('*/*/*/manifest.json'))
assert len(paths)==3276
for index,mp in enumerate(paths):
 m=read(mp)
 if m['status'] not in ('complete','not_triggered'):pending.append(str(mp));continue
 try:check(mp.parent)
 except Exception as ex:
  import traceback
  failed.append(dict(path=str(mp.parent),error=repr(ex),traceback=traceback.format_exc()))
 if index%100==0:print(index,dict(counts),'failures',len(failed),flush=True)
tok.close()
validate_gate(read(R/'development-review.json'),dict(**gate_expected(R,S),development_manifest_sha256=development_digest(R)))
first_fresh=min(read(p)['started_at'] for p in (R/'evaluation').glob('*/*/identity/manifest.json'))
last_dev=max(read(p).get('finished_at',0) for p in (R/'development').glob('*/*/*/manifest.json'))
assert last_dev<=read(R/'development-review.json')['reviewed_at']<=first_fresh
report=dict(status='pass' if not pending and not failed else 'needs_review',created_at=time.time(),manifest_count=len(paths),counts=dict(counts),failures=failed,pending=pending,results=results,exposure=exposure,frozen_gate=gate_expected(R,S),development_manifest_sha256=development_digest(R),selection_order=dict(last_development_finished=last_dev,reviewed_at=read(R/'development-review.json')['reviewed_at'],first_fresh_started=first_fresh))
(Path(__file__).parent/'final-check-evidence.json').write_text(json.dumps(report,indent=2)+'\n')
(Path(__file__).parent/'final-native-samples.json').write_text(json.dumps(native_samples)+'\n')
print(json.dumps({k:v for k,v in report.items() if k not in ['results','exposure']},indent=2))
if failed:raise SystemExit(1)
