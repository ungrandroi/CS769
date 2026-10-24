"""Independent recomputation of mixed summaries, pairs, uncertainty and CSVs."""
from pathlib import Path
import sys,json,csv,math,random,time
from statistics import mean
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'source_code/adapters-v1/scripts'))
from core.local_qwen_tokenizer import LocalQwenTokenizer
read=lambda p:json.loads(p.read_text())
plan=read(R/'task-split.json');s=read(R/'reports/summary.json');a=read(R/'reports/paired-analysis.json');tasks={t['id']:t for t in plan['tasks']}
rows=[];expected_requests=[];untriggered=[]
labels=('identity','state-baseline','state-optimized','event-baseline','event-optimized','dedup-baseline','dedup-optimized')
for task in plan['tasks']:
 for seed in plan['seeds']:
  base=R/'evaluation'/task['id']/f'seed{seed}';im=read(base/'identity/manifest.json')
  assert im['status']=='complete'
  if not im['triggered']:
   untriggered.append(dict(task=task['id'],seed=seed,passed=im['passed']));continue
  for label in labels:
   p=base/label;m=read(p/'manifest.json');assert m['status']=='complete'
   acc=[x for x in read(p/'accounting.json') if x['index']>=m['trigger_index']]
   rows.append(dict(task=task['id'],seed=seed,split=task['split'],family=task['family'],category=task['category'],method=label,passed=m['passed'],first_input=acc[0]['input_tokens'],mean_post_input=mean(x['input_tokens'] for x in acc),peak_input=max(x['input_tokens'] for x in acc),mean_fixed=mean(x['fixed_tokens'] for x in acc),mean_working=mean(x['working_tokens'] for x in acc),live_requests=len(acc),memory_tokens=m.get('memory_tokens'),instruction_tokens=m.get('instruction_tokens')))
   for n,x in enumerate(acc,1):expected_requests.append(dict(task=task['id'],seed=seed,split=task['split'],method=label,post_conversion_request=n,request_index=x['index'],user_turn=x['turn'],input_tokens=x['input_tokens'],fixed_tokens=x['fixed_tokens'],working_tokens=x['working_tokens']))
assert rows==s['rows'] and untriggered==s['untriggered'];assert len(rows)==297*7 and len(untriggered)==147
by={(r['task'],r['seed'],r['method']):r for r in rows}
def subset(group):
 if group=='all':return rows
 if group=='development_conditions':return [r for r in rows if r['split']=='development']
 if group=='other_conditions':return [r for r in rows if r['split']!='development']
 if group=='development_families':return [r for r in rows if r['family'] in plan['development_families']]
 if group=='other_families':return [r for r in rows if r['family'] not in plan['development_families']]
 return [r for r in rows if r['category']==group]
for group,methods in s['groups'].items():
 sub=subset(group)
 for label,v in methods.items():
  x=[r for r in sub if r['method']==label]
  assert v==dict(n=len(x),passed=sum(r['passed'] for r in x),first_input=mean(r['first_input'] for r in x),mean_post_input=mean(r['mean_post_input'] for r in x),mean_peak_input=mean(r['peak_input'] for r in x))
for p in s['pairs']:
 o=by[p['task'],p['seed'],p['method']+'-optimized'];b=by[p['task'],p['seed'],p['method']+'-baseline'];i=by[p['task'],p['seed'],'identity']
 assert p==dict(task=o['task'],seed=o['seed'],method=p['method'],family=o['family'],category=o['category'],split=o['split'],identity_passed=i['passed'],baseline_passed=b['passed'],optimized_passed=o['passed'],ratio_to_baseline=o['mean_post_input']/b['mean_post_input'],ratio_to_identity=o['mean_post_input']/i['mean_post_input'])
cluster_results={}
for group,methods in a['statistics'].items():
 keys={(x['task'],x['seed']) for x in subset(group)}
 for method,comparisons in methods.items():
  ps=[p for p in s['pairs'] if p['method']==method and (p['task'],p['seed']) in keys]
  for control in ['baseline','identity']:
   deltas=[int(p['optimized_passed'])-int(p[control+'_passed']) for p in ps];families={}
   for p,d in zip(ps,deltas):families.setdefault(p['family'],[]).append(d)
   o=comparisons['versus_'+control];g=deltas.count(1);l=deltas.count(-1)
   assert (o['gains'],o['losses'],o['n'],o['families'])==(g,l,len(deltas),len(families));assert o['success_difference']==mean(deltas)
   n=g+l;pv=min(1,2*sum(math.comb(n,k) for k in range(min(g,l)+1))/2**n) if n else 1
   assert pv==o['descriptive_exact_mcnemar_p']
   rng=random.Random(o['bootstrap_seed']);names=list(families);draws=[]
   for _ in range(o['bootstrap_replicates']):
    pick=[rng.choice(names) for _ in names];ds=[d for f in pick for d in families[f]];draws.append(sum(ds)/len(ds))
   draws.sort();assert [draws[249],draws[9749]]==o['family_cluster_bootstrap_95_interval']
   vals=sorted(p['ratio_to_'+control] for p in ps)
   for q,result in comparisons['paired_input_ratio_to_'+control].items():
    pos=(len(vals)-1)*float(q);lo=int(pos);assert result==vals[lo]+(vals[min(lo+1,len(vals)-1)]-vals[lo])*(pos-lo)
   cluster_results[group+'/'+method+'/'+control]=o
req=list(csv.DictReader((R/'reports/per-request-input.csv').open()));turns=list(csv.DictReader((R/'reports/per-user-turn-input.csv').open()));first=list(csv.DictReader((R/'reports/paired-first-request-input.csv').open()))
assert req==[{k:str(v) for k,v in r.items()} for r in expected_requests]
groups={}
for x in req:groups.setdefault((x['task'],x['seed'],x['method'],x['user_turn']),[]).append(x)
assert len(groups)==len(turns)
for x in turns:
 vals=groups[x['task'],x['seed'],x['method'],x['user_turn']]
 exp=dict(requests=len(vals),first_input_tokens=int(vals[0]['input_tokens']),mean_input_tokens=mean(int(v['input_tokens']) for v in vals),max_input_tokens=max(int(v['input_tokens']) for v in vals),mean_working_tokens=mean(int(v['working_tokens']) for v in vals))
 assert all(float(x[k])==v for k,v in exp.items())
firstby={(x['task'],x['seed'],x['method']):x for x in req if int(x['post_conversion_request'])==1}
assert len(first)==297*3
for x in first:
 o=firstby[x['task'],x['seed'],x['method']];b=firstby[x['task'],x['seed'],x['method'].replace('-optimized','-baseline')];i=firstby[x['task'],x['seed'],'identity']
 for name,v in [('optimized',o),('baseline',b),('identity',i)]:
  assert int(x[name+'_input'])==int(v['input_tokens']);assert int(x[name+'_working'])==int(v['working_tokens'])
 for kind,v in [('baseline',b),('identity',i)]:
  assert float(x['input_ratio_to_'+kind])==int(o['input_tokens'])/int(v['input_tokens'])
  assert float(x['working_ratio_to_'+kind])==int(o['working_tokens'])/int(v['working_tokens'])
t=LocalQwenTokenizer();decomp=0
for x in a['decomposition']:
 row=by[x['task'],x['seed'],x['method']];p=R/'evaluation'/x['task']/f"seed{x['seed']}"/x['method'];m=read(p/'memory-metadata.json');encoded=m.get('encoded',{})
 assert x['external_instruction_tokens']==t.count(m['instruction']);assert x['encoded_body_tokens']==t.count(m['body']);assert x['exact_baseline_body_tokens']==m.get('baseline_body_tokens',m['body_tokens'])
 assert x['mean_dynamic_and_wrapper_residual']==row['mean_working']-m['total_tokens']
 rules={k:v for k,v in encoded.items() if k=='decoding' or k.endswith('_rule')};none={k:v for k,v in encoded.items() if k not in rules}
 assert x['codec_rules_text_tokens']==sum(t.count(v) for v in rules.values())
 assert x['codec_rules_marginal_body_tokens']==(t.count(m['body'])-t.count(json.dumps(none,ensure_ascii=False,separators=(',',':'),allow_nan=False)) if encoded else 0)
 decomp+=1
t.close()
result=dict(status='pass',created_at=time.time(),summary_rows=len(rows),untriggered=len(untriggered),paired_ratios=len(s['pairs']),per_request_rows=len(req),per_turn_rows=len(turns),paired_first_request_rows=len(first),decomposition_rows=decomp,cluster_statistics=cluster_results,groups=s['groups'])
(R/'independent_audit/final-reports-evidence.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ('cluster_statistics','groups')},indent=2))
