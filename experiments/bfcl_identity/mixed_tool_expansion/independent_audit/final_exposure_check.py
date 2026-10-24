"""Describe actual cross-domain prefixes and paired score changes; no inference."""
from pathlib import Path
import sys,json,re
from collections import Counter,defaultdict
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'source_code/adapters-v1/scripts'))
from core.mixed_observations import tool_spec
read=lambda p:json.loads(p.read_text());plan=read(R/'task-split.json');summary=read(R/'reports/summary.json')
rows=[];prefix_domains=Counter();all_domains=Counter();diagnosed=[]
for p in sorted((R/'evaluation').glob('*/*/identity')):
 m=read(p/'manifest.json');t=read(p/'api.json');calls=[o for x in t for o in x['response']['output'] if o.get('type')=='function_call']
 h=read(p/'checkpoint-history.json') if m['triggered'] else []
 count=lambda a:dict(Counter(tool_spec(x['name'])['domain'] for x in a if x.get('type')=='function_call'))
 before=count(h);whole=count(calls)
 for k in before:prefix_domains[k]+=1
 for k in whole:all_domains[k]+=1
 rows.append(dict(task=m['task'],seed=m['seed'],triggered=m['triggered'],prefix_domains=before,whole_trajectory_domains=whole))
 if m['triggered']:
  sc=read(p/'official-score.json');turns=[]
  for d in sc['diagnostics']:
   e=d.get('error',{});kind=e.get('error_type')
   if kind=='multi_turn:instance_state_mismatch':turns.append(len(e['execution_result']))
   if kind=='multi_turn:empty_turn_model_response':turns.append(len(e['details']['execution_result']))
   if kind=='multi_turn:execution_response_mismatch':turns.append(int(re.search(r'for turn (\d+)',e['error_message']).group(1))+1)
  diagnosed.append(dict(task=m['task'],seed=m['seed'],trigger_turn=m['trigger_turn'],error_turns_1based=turns,completed_prefix_failure=any(x<m['trigger_turn'] for x in turns)))
keys={(r['task'],r['seed']):r for r in summary['rows'] if r['method']=='identity'}
diffs={}
for method in ['state','event','dedup']:
 ps=[x for x in summary['pairs'] if x['method']==method]
 diffs[method]=dict(gains=[dict(task=x['task'],seed=x['seed']) for x in ps if x['optimized_passed'] and not x['baseline_passed']],losses=[dict(task=x['task'],seed=x['seed']) for x in ps if x['baseline_passed'] and not x['optimized_passed']])
result=dict(status='pass',identity_runs=len(rows),triggered=sum(x['triggered'] for x in rows),prefixes_with_nonfilesystem=sum(any(k!='GorillaFileSystem' for k in x['prefix_domains']) for x in rows),identity_runs_with_nonfilesystem=sum(any(k!='GorillaFileSystem' for k in x['whole_trajectory_domains']) for x in rows),prefix_domain_runs=dict(prefix_domains),all_domain_runs=dict(all_domains),rows=rows,diagnosed_prefix_failures=sum(x['completed_prefix_failure'] for x in diagnosed),prefix_diagnostics=diagnosed,paired_changes=diffs)
mixed_keys={(r['task'],r['seed']) for r in rows if any(k!='GorillaFileSystem' for k in r['prefix_domains'])}
strata={}
for is_mixed in [True,False]:
 subset=[r for r in summary['rows'] if ((r['task'],r['seed']) in mixed_keys)==is_mixed]
 strata['actual_mixed_prefix' if is_mixed else 'filesystem_only_prefix']={label:dict(n=len([r for r in subset if r['method']==label]),passed=sum(r['passed'] for r in subset if r['method']==label)) for label in sorted({r['method'] for r in subset})}
result['actual_prefix_domain_strata']=strata
(R/'independent_audit/final-exposure-evidence.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ['rows','prefix_diagnostics','paired_changes']},indent=2));print({k:{s:len(x) for s,x in v.items()} for k,v in diffs.items()})
