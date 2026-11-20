import json,csv,hashlib,shutil
from pathlib import Path
from statistics import mean
from collections import Counter
from core.research_modes import LABELS
from core.frozen import load_frozen_modules
from core.local_qwen_tokenizer import LocalQwenTokenizer
ROOT=Path(__file__).resolve().parents[2];BASE=ROOT/'experiments/bfcl_identity';OUT=BASE/'history1000_eval';OLD=BASE/'qwen27b_experiment'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 plan=read(OUT/'plan.json');progress=read(OUT/'progress.json');assert progress['status']=='complete' and len(progress['runs'])==len(plan['checkpoints']['tasks'])*3
 frozen=load_frozen_modules(OUT/'source_code',plan['sources'],['run_qwen_task','core.qwen_transport','core.qwen_prompt_accounting','core.graph_memory_replace'])
 make_memory=frozen['run_qwen_task'].make_memory;TOOLS=frozen['run_qwen_task'].TOOLS
 chat_messages=frozen['core.qwen_transport'].chat_messages;to_chat_tools=frozen['core.qwen_prompt_accounting'].to_chat_tools
 retained_instructions=frozen['core.graph_memory_replace'].retained_instructions
 for n,h in read(OLD/'artifact-manifest.json')['files'].items():assert sha(OLD/n)==h
 rows=[];finish=Counter();total=Counter()
 with LocalQwenTokenizer() as tok:
  for cp in plan['checkpoints']['tasks']:
   tid=cp['id'];src=OLD/'tasks'/tid/'identity';source=read(src/f'{tid}.api.json');boundary=cp['trigger_index']
   assert cp['calls']>0 and boundary>0
   def history_size(record):
    history=record['request']['input'];calls=[m for m in history if m.get('type')=='function_call'];returns=[m for m in history if m.get('type')=='function_call_output']
    assert len({m['call_id'] for m in calls})==len(calls)
    assert {m['call_id'] for m in calls}=={m['call_id'] for m in returns}
    return sum(tok.count(m['name']+'('+m['arguments']+')') for m in calls)+sum(tok.count(m['output']) for m in returns),len(calls)
   assert history_size(source[boundary])==(cp['history_tokens'],cp['calls'])
   assert all(n<1000 for n,calls in (history_size(r) for r in source[:boundary]))
   assert cp['history_tokens']>=1000
   assert source[boundary]['response']['usage']['input_tokens']==cp['before']
   for mode in plan['modes']:
    d=OUT/'tasks'/tid/mode;m=read(d/'manifest.json');tape=read(d/'api.json');history=read(d/'checkpoint-history.json')
    assert m['threshold']==1000 and m['budget'] is None and m['replayed_requests']==boundary and m['triggered']
    assert history==source[boundary]['request']['input']
    assert [(r['request'],r['response']) for r in tape[:boundary]]==[(r['request'],r['response']) for r in source[:boundary]]
    assert all(r['source']=='replay' for r in tape[:boundary]) and all(r['source']=='live' for r in tape[boundary:])
    if mode!='identity':
     memory,graph=make_memory(history,mode,tok.count);assert memory==(d/'memory.txt').read_text() and read(d/'graph.json')==graph
     current=next(r for r in reversed(history) if r.get('role')=='user');replacement=[*retained_instructions(history),{'role':'assistant','content':memory},current]
     for r in tape[boundary:]:assert r['request']['input'][:len(replacement)]==replacement
    native=[json.loads(x) for x in (d/'native.jsonl').read_text().splitlines()];sent=[r for r in native if r['event']=='request'];received=[r for r in native if r['event']=='response'];assert len(sent)==len(received)==m['live_requests']==len(tape)-boundary
    for s,r,logical in zip(sent,received,tape[boundary:]):
     req=s['request'];u=r['response']['usage'];assert req['messages']==chat_messages(logical['request']['input']) and req['tools']==to_chat_tools(logical['request']['tools'])
     assert {t['function']['name'] for t in req['tools']}==TOOLS
     assert req['model']==r['response']['model']=='bfcl-qwen38-27b' and req['temperature']==0 and req['seed']==42 and req['max_tokens']==4096 and req['cache_prompt'] is True
     assert req['chat_template_kwargs']=={'enable_thinking':False,'preserve_thinking':False}
     assert u['prompt_tokens']==s['input_tokens'] and u['total_tokens']<=131072
     assert logical['response']['usage']['input_tokens']==u['prompt_tokens'] and logical['response']['usage']['output_tokens']==u['completion_tokens']
     finish.update([r['response']['choices'][0]['finish_reason']]);total.update({'input':u['prompt_tokens'],'output':u['completion_tokens'],'requests':1})
    assert m['status']=='complete','Unexpected context-limit stop'
    score=read(d/'official-score.json');assert score['passed']==m['passed']==progress['runs'][tid+'/'+mode]['passed'];assert sha(d/score['score_file'])==score['score_sha256'];result,=list((d/'result').rglob('*_result.json'));assert sha(result)==score['result_sha256']
    errors=score.get('diagnostics',[]);error=errors[0].get('error',{}) if errors else {};failure_turn=len(error.get('execution_result',[])) or None
    prefix_input=sum(r['response']['usage']['input_tokens'] for r in source[:boundary]);suffix_input=sum(r['response']['usage']['prompt_tokens'] for r in received)
    live_calls=[o for r in tape[boundary:] for o in r['response']['output'] if o.get('type')=='function_call']
    rows.append({'id':tid,'category':cp['category'],'mode':mode,'passed':m['passed'],'error_type':error.get('error_type'),'first_failure_turn_one_based':failure_turn,'preconversion_failure':bool(failure_turn and failure_turn<=tape[boundary]['turn']),'checkpoint_turn_zero_based':tape[boundary]['turn'],'prefix_requests':boundary,'past_tool_calls':cp['calls'],'first_input':m['first_input'],'memory_tokens':tok.count(memory) if mode!='identity' else None,'continuation_requests':len(received),'continuation_tool_calls':len(live_calls),'continuation_input':suffix_input,'whole_trajectory_input':prefix_input+suffix_input,'continuation_output':sum(r['response']['usage']['completion_tokens'] for r in received)})
 groups={}
 for category in ['all','multi_turn_long_context']:
  groups[category]={}
  for mode in plan['modes']:
   rs=[r for r in rows if r['mode']==mode and (category=='all' or r['category']==category)]
   groups[category][mode]={'tasks':len(rs),'passed':sum(r['passed'] for r in rs),**{'mean_'+k:mean(r[k] for r in rs) for k in ['first_input','continuation_requests','continuation_tool_calls','continuation_input','whole_trajectory_input']}}
 identities={r['id']:r for r in rows if r['mode']=='identity'};changes={mode:[{'id':r['id'],'identity':identities[r['id']]['passed'],'candidate':r['passed']} for r in rows if r['mode']==mode and r['passed']!=identities[r['id']]['passed']] for mode in plan['modes'][1:]}
 oldscores={r['id']:r['passed'] for r in read(OLD/'summary.json')['rows'] if r['mode']=='identity'}
 summary={'threshold':1000,'triggered':len(plan['checkpoints']['tasks']),'groups':groups,'paired_changes':changes,'rows':rows,'actual_live_usage':dict(total),'finish_reasons':dict(finish),'audit_passed':True,'original_unchanged':True,'identity_rerun_changes':[tid for tid,r in identities.items() if r['passed']!=oldscores[tid]],'interpretation':'First paired history checkpoint reaching 1000 tool-content tokens, no call-count or future-trajectory filter. Single trial; not a long-window validation.'}
 (OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
 with (OUT/'task-results.csv').open('w') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 with (OUT/'task-matrix.csv').open('w') as f:
  w=csv.DictWriter(f,fieldnames=['id',*plan['modes']]);w.writeheader()
  for tid in identities:w.writerow({'id':tid,**{r['mode']:r['passed'] for r in rows if r['id']==tid}})
 lines=['仅以调用与返回内容累计1000 tokens触发；无最低调用次数、无未来调用筛选。','未触发任务单独列在checkpoints.json，不伪造图转换结果。','相同Qwen检查点续跑三方法；转换一次并保留图，随后追加新历史；无8000上限。']
 for c,rs in groups.items():
  lines += [c,'方法 | 成功 | 平均首次续段输入 | 平均续段累计输入 | 平均整轨迹累计输入']
  for mode,r in rs.items():lines.append(f"{LABELS[mode]} | {r['passed']}/{r['tasks']} | {r['mean_first_input']:.2f} | {r['mean_continuation_input']:.2f} | {r['mean_whole_trajectory_input']:.2f}")
 lines += ['对比原始历史记忆的成败变化：'+json.dumps(changes,ensure_ascii=False),'所有原始请求、共享前缀、图编码、保留图前缀、token计数及官方评分文件核验通过。']
 (OUT/'report.txt').write_text('\n'.join(lines)+'\n');shutil.copyfile(__file__,OUT/'source_code/workflows/history_audit.py');print('\n'.join(lines))
if __name__=='__main__':main()
