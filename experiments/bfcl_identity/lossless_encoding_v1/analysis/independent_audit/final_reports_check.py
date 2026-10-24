from pathlib import Path
import sys,json,csv,re
from statistics import mean
R=Path(__file__).resolve().parents[2];sys.path.insert(0,str(R/'source_code/candidates-v2/scripts'))
from core.local_qwen_tokenizer import LocalQwenTokenizer
read=lambda p:json.loads(Path(p).read_text())
s=read(R/'reports/summary.json');a=read(R/'reports/paired-analysis.json');d=read(R/'reports/final-diagnostics.json')
by={(r['task'],r['seed'],r['method']):r for r in s['rows']}
for p in s['pairs']:
 o=by[p['task'],p['seed'],p['method']+'-optimized'];b=by[p['task'],p['seed'],p['method']+'-baseline'];i=by[p['task'],p['seed'],'identity']
 assert p==dict(task=p['task'],seed=p['seed'],method=p['method'],identity_passed=i['passed'],baseline_passed=b['passed'],optimized_passed=o['passed'],ratio_to_baseline=o['mean_post_input']/b['mean_post_input'],ratio_to_identity=o['mean_post_input']/i['mean_post_input'])
for split,methods in a['statistics'].items():
 for method,v in methods.items():
  pairs=[p for p in s['pairs'] if p['method']==method and (split=='all' or (by[p['task'],p['seed'],'identity']['split']=='development')==(split=='development'))]
  for kind in ('baseline','identity'):
   vals=sorted(p['ratio_to_'+kind] for p in pairs)
   for q,result in v['paired_input_ratio_to_'+kind].items():
    pos=(len(vals)-1)*float(q);lo=int(pos);assert result==vals[lo]+(vals[min(lo+1,len(vals)-1)]-vals[lo])*(pos-lo)
req=list(csv.DictReader((R/'reports/per-request-input.csv').open()));turns=list(csv.DictReader((R/'reports/per-user-turn-input.csv').open()));first=list(csv.DictReader((R/'reports/paired-first-request-input.csv').open()))
groups={}
for x in req:groups.setdefault((x['task'],x['seed'],x['method'],x['user_turn']),[]).append(x)
assert len(groups)==len(turns)
for x in turns:
 values=groups[x['task'],x['seed'],x['method'],x['user_turn']]
 expected=dict(requests=len(values),first_input_tokens=int(values[0]['input_tokens']),mean_input_tokens=mean(int(v['input_tokens']) for v in values),max_input_tokens=max(int(v['input_tokens']) for v in values),mean_working_tokens=mean(int(v['working_tokens']) for v in values))
 assert all(float(x[k])==v for k,v in expected.items())
firstby={(x['task'],x['seed'],x['method']):x for x in req if int(x['post_conversion_request'])==1}
assert len(first)==360
for x in first:
 o=firstby[x['task'],x['seed'],x['method']];b=firstby[x['task'],x['seed'],x['method'].replace('-optimized','-baseline')];i=firstby[x['task'],x['seed'],'identity']
 for name,v in [('optimized',o),('baseline',b),('identity',i)]:
  assert int(x[name+'_input'])==int(v['input_tokens']);assert int(x[name+'_working'])==int(v['working_tokens'])
 for kind,v in [('baseline',b),('identity',i)]:
  assert float(x['input_ratio_to_'+kind])==int(o['input_tokens'])/int(v['input_tokens'])
  assert float(x['working_ratio_to_'+kind])==int(o['working_tokens'])/int(v['working_tokens'])
t=LocalQwenTokenizer();decomp=0
for row in a['rows']:
 b=by[row['task'],row['seed'],row['method']]
 assert all(row[k]==v for k,v in b.items())
 p=R/'evaluation'/row['task']/f"seed{row['seed']}"/row['method']
 if not (p/'memory-metadata.json').exists():continue
 m=read(p/'memory-metadata.json');encoded=m.get('encoded')
 assert row['external_instruction_tokens']==t.count(m['instruction'])
 assert row['encoded_body_tokens']==t.count(m['body'])
 assert row['mean_dynamic_and_wrapper_residual']==row['mean_working']-m['total_tokens']
 if encoded:
  rules={k:v for k,v in encoded.items() if k=='decoding' or k.endswith('_rule')};none={k:v for k,v in encoded.items() if k not in rules}
  assert row['codec_rules_text_tokens']==sum(t.count(v) for v in rules.values())
  assert row['codec_rules_marginal_body_tokens']==t.count(m['body'])-t.count(json.dumps(none,ensure_ascii=False,separators=(',',':'),allow_nan=False))
 decomp+=1
t.close()
known=[]
for x in d['prefix_rows']:
 path=R/'evaluation'/x['task']/f"seed{x['seed']}"/'identity';m=read(path/'manifest.json');sc=read(path/'official-score.json');turns=[]
 for diagnostic in sc['diagnostics']:
  err=diagnostic.get('error',{});kind=err.get('error_type')
  if kind=='multi_turn:instance_state_mismatch':turns.append(len(err['execution_result']))
  if kind=='multi_turn:empty_turn_model_response':turns.append(len(err['details']['execution_result']))
  if kind=='multi_turn:execution_response_mismatch':turns.append(int(re.search(r'for turn (\d+)',err['error_message']).group(1))+1)
 assert x['diagnosed_error_turns_1based']==turns
 knownflag=any(z<m['trigger_turn'] for z in turns)
 assert x['diagnosed_failure_in_completed_prefix_turn']==knownflag
 if knownflag:known.append((x['task'],x['seed']))
assert len(known)==d['sufficient_prefix_failure_diagnoses']==18 and d['primary_denominator_unchanged']==120
for grouping,strata in [('category',d['categories']),('family',d['family_groups'])]:
 for key,methods in strata.items():
  for method,v in methods.items():
   rows=[r for r in s['rows'] if r['method']==method and ((r['task'].rsplit('_',1)[0]==key) if grouping=='category' else ((int(r['task'].rsplit('_',1)[1]) in (3,9,37))==(key=='development_families')))]
   assert v==dict(n=len(rows),passed=sum(r['passed'] for r in rows),first_input=mean(r['first_input'] for r in rows),mean_post_input=mean(r['mean_post_input'] for r in rows),mean_working_input=mean(r['mean_working'] for r in rows))
result=dict(status='pass',paired_ratios=len(s['pairs']),per_turn_rows=len(groups),paired_first_request_rows=len(first),decomposition_rows=decomp,known_prefix_failures=len(known),prefix_failure_semantics='Official checker appends execution_results once per zero-based ground-truth turn before state/empty-turn checking; response mismatch reports zero-based turn. Hook turn count is 1-based. Only errors strictly before conversion turn establish a completed-prefix failure. No main-denominator exclusion.',subgroup_labels='development means six exact task-condition instances; development_families means all conditions of families 3/9/37. Other families are historically seen, not blind.')
(Path(__file__).parent/'final-reports-evidence.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
