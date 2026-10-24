"""Audit and summarize all-Qwen trajectories, counting common-prefix compute once."""
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
from statistics import mean
from core.research_modes import MODES, LABELS
from core.frozen import load_frozen_modules

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'experiments/bfcl_identity/qwen27b_experiment'


def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def summarize():
    plan=read(OUT/'plan.json');progress=read(OUT/'progress.json')
    assert progress['status']=='complete' and len(progress['runs'])==78
    frozen=load_frozen_modules(OUT/'source_code',plan['implementation_sha256'],['qwen_transport','graph_memory_serialization','graph_memory_replace','qwen_prompt_accounting','run_qwen_task'])
    transport=frozen['qwen_transport'];codec=frozen['graph_memory_serialization'];replacement_module=frozen['graph_memory_replace']
    prefix_log=transport.prefix_log;digest=transport.digest;decode_compact=codec.decode_compact;normalize=codec.normalize
    destination=ROOT/'experiments/bfcl_identity/reports/audits/baseline';destination.mkdir(parents=True,exist_ok=True)
    for name,expected in plan['data_sha256'].items():assert sha(ROOT/name)==expected,name
    from bfcl_eval.eval_checker.eval_runner import _evaluate_single_multi_turn_entry
    from bfcl_eval.model_handler.api_inference.openai_response import OpenAIResponsesHandler
    from bfcl_eval.utils import load_dataset_entry,load_ground_truth_entry
    from copy import deepcopy
    handler=object.__new__(OpenAIResponsesHandler);handler.is_fc_model=True
    entries={c:{e['id']:e for e in load_dataset_entry(c)} for c in ('multi_turn_base','multi_turn_long_context')}
    answers={c:{e['id']:e['ground_truth'] for e in load_ground_truth_entry(c)} for c in entries}
    rows=[];prefix_scores=[];actual_usage=Counter();finish_counts=Counter();max_input=0
    for task in plan['tasks']:
        task_id=task['id'];base=OUT/'tasks'/task_id
        identity=read(base/'identity/manifest.json');source=read(base/'identity'/f'{task_id}.api.json');source_full=read(base/'identity'/f'{task_id}.full.json')
        n=identity['first_turn_requests'];assert n>0
        assert all(r['source']=='live_local_qwen' for r in source)
        prompt=deepcopy(entries[task['category']][task_id]);prompt['question']=prompt['question'][:1]
        diag=_evaluate_single_multi_turn_entry(handler,task_id,deepcopy(source_full['result'][:1]),deepcopy(answers[task['category']][task_id][:1]),prompt,'qwen_first_turn_audit',task['category'])
        prefix_scores.append({'id':task_id,'passed':diag['valid'],'error_type':diag.get('error',{}).get('error_type'),'boundary_reached':identity['boundary_reached']})
        for mode in MODES:
            directory=base/mode;m=read(directory/'manifest.json');tape=read(directory/f'{task_id}.api.json');full=read(directory/f'{task_id}.full.json');score=read(directory/'official-score.json')
            assert m['status'] in ('complete','not_reached') and m['prefix_model']==plan['serving_model']
            assert m['boundary_reached']==identity['boundary_reached'] and m['first_turn_requests']==n
            assert prefix_log(full['metadata']['inference_log'])==prefix_log(source_full['metadata']['inference_log'])
            assert [(r['request'],r['response']) for r in tape[:n]]==[(r['request'],r['response']) for r in source[:n]]
            assert m['tools_sha256']==identity['tools_sha256']
            assert score['passed']==progress['runs'][task_id+'/'+mode]['passed']
            assert sha(directory/score['score_file'])==score['score_sha256']
            result,=list((directory/'result').rglob('*_result.json'));assert sha(result)==score['result_sha256']
            if not diag['valid']:assert not score['passed']
            if m['boundary_reached']:
                history=read(directory/'prefix-history.json');assert history==read(base/'identity/prefix-history.json')
                assert digest(history)==m['boundary']['history_sha256']
                if mode!='identity':
                    GraphMemoryReplacement=replacement_module.GraphMemoryReplacement;GraphMemoryV2Replacement=replacement_module.GraphMemoryV2Replacement
                    retained_instructions=replacement_module.retained_instructions;assert_replacement_request=replacement_module.assert_replacement_request
                    builder=(GraphMemoryReplacement if mode=='v1-compact' else GraphMemoryV2Replacement)();builder.compress(history)
                    graph=read(directory/f'{task_id}.graph.json');assert graph==builder.graph
                    text=(directory/f'{task_id}.memory.txt').read_text();assert normalize(decode_compact(text.split('\n',2)[2]))==normalize(json.loads(builder.render().split('\n',2)[2]))
                    replacement=[*retained_instructions(history),{'role':'assistant','content':text}]
                    for r in tape[n:]:assert_replacement_request(r['request'],replacement,history)
            native_path=directory/'native.jsonl'
            native=[json.loads(x) for x in native_path.read_text().splitlines()] if native_path.exists() else []
            requests=[r for r in native if r['event']=='request'];responses=[r for r in native if r['event']=='response']
            live=[r for r in tape if r['source']=='live_local_qwen']
            assert len(requests)==len(responses)==len(live)==m['live_requests']
            counters={k:Counter() for k in ('prefix','continuation','actual')};first_input=None
            for sent,received,record in zip(requests,responses,live):
                req,raw=sent['request'],received['response'];u=raw['usage'];assert sent['index']==received['index']
                assert req['model']==raw['model']==plan['serving_model']
                assert req['temperature']==0 and req['seed']==42 and req['max_tokens']==4096 and req['cache_prompt'] is True
                assert req['chat_template_kwargs']=={'enable_thinking':False,'preserve_thinking':False}
                TOOLS=frozen['run_qwen_task'].TOOLS;chat_messages=transport.chat_messages;to_chat_tools=frozen['qwen_prompt_accounting'].to_chat_tools
                assert req['messages']==chat_messages(record['request']['input'])
                assert req['tools']==to_chat_tools(record['request']['tools']) and {t['function']['name'] for t in req['tools']}==TOOLS
                assert record['response']['usage']['input_tokens']==u['prompt_tokens'] and record['response']['usage']['output_tokens']==u['completion_tokens']
                assert u['total_tokens']==u['prompt_tokens']+u['completion_tokens']
                assert 0<u['prompt_tokens']<131072;max_input=max(max_input,u['prompt_tokens'])
                item={'input':u['prompt_tokens'],'output':u['completion_tokens'],'requests':1,'cached_input':u.get('prompt_tokens_details',{}).get('cached_tokens',0)}
                scope='prefix' if received['turn']==0 else 'continuation'
                counters[scope].update(item);counters['actual'].update(item);actual_usage.update(item)
                finish_counts.update([raw['choices'][0]['finish_reason']])
                if received['turn']>0 and first_input is None:first_input=u['prompt_tokens']
            assert counters['actual']['input']==m['live_usage']['prompt_tokens']
            assert counters['continuation']['input']==m['continuation_usage']['prompt_tokens']
            prefix=identity['prefix_usage'];continuation=m['continuation_usage']
            reason='passed' if score['passed'] else ';'.join(dict.fromkeys(d.get('error',{}).get('error_type','unknown') for d in score['diagnostics']))
            rows.append({'id':task_id,'category':task['category'],'mode':mode,'passed':score['passed'],'boundary_reached':m['boundary_reached'],
                         'first_turn_passed':diag['valid'],'official_reason':reason,'prefix_input_tokens':prefix['prompt_tokens'],'prefix_output_tokens':prefix['completion_tokens'],
                         'continuation_input_tokens':continuation['prompt_tokens'],'continuation_output_tokens':continuation['completion_tokens'],'continuation_requests':m['continuation_requests'],
                         'whole_trajectory_input_tokens':prefix['prompt_tokens']+continuation['prompt_tokens'],
                         'whole_trajectory_output_tokens':prefix['completion_tokens']+continuation['completion_tokens'],
                         'first_continuation_input_tokens':first_input,'actual_requests':m['live_requests'],'actual_input_tokens':m['live_usage']['prompt_tokens'],
                         'actual_output_tokens':m['live_usage']['completion_tokens']})
    def aggregate(rs):
        first=[r['first_continuation_input_tokens'] for r in rs if r['first_continuation_input_tokens'] is not None]
        return {'tasks':len(rs),'passed':sum(r['passed'] for r in rs),'accuracy':sum(r['passed'] for r in rs)/len(rs) if rs else None,
                **{'mean_'+k:mean(r[k] for r in rs) if rs else None for k in ('prefix_input_tokens','continuation_input_tokens','continuation_output_tokens','continuation_requests','whole_trajectory_input_tokens','whole_trajectory_output_tokens')},
                'mean_first_continuation_input_tokens':mean(first) if first else None,'first_input_tasks':len(first)}
    groups={'overall26':rows,'boundary_reached':[r for r in rows if r['boundary_reached']],'first_turn_valid':[r for r in rows if r['first_turn_passed']]}
    for c in entries:groups[c]=[r for r in rows if r['category']==c]
    paired=[]
    for mode in MODES[1:]:
        changed=[]
        for task in plan['tasks']:
            a,b=(next(r for r in rows if r['id']==task['id'] and r['mode']==m) for m in ('identity',mode))
            if a['passed']!=b['passed']:changed.append({'id':task['id'],'identity':a['passed'],'candidate':b['passed']})
        paired.append({'reference':'identity','candidate':mode,'changed_tasks':changed})
    summary={'status':'complete','plan':plan,'rows':rows,'scopes':{k:{m:aggregate([r for r in rs if r['mode']==m]) for m in MODES} for k,rs in groups.items()},
             'paired':paired,'prefix_scores':prefix_scores,'actual_compute':dict(actual_usage),'finish_reason_counts':dict(finish_counts),'max_prompt_tokens':max_input,
             'audit':{'all_Qwen':True,'prefix_replay_and_state_exact':True,'graph_roundtrip_exact':True,'official_scores_verified':True,'no_old_GPT_inputs':True}}
    (destination/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    with (destination/'task-results.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    with (destination/'task-matrix.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['id','boundary_reached','first_turn_passed',*MODES]);w.writeheader()
        for task in plan['tasks']:
            rs=[r for r in rows if r['id']==task['id']]
            w.writerow({'id':task['id'],'boundary_reached':rs[0]['boundary_reached'],'first_turn_passed':rs[0]['first_turn_passed'],**{r['mode']:r['passed'] for r in rs}})
    lines=['全 Qwen 27B 文件系统图记忆实验','26 项任务条件 = 13 个任务家族 × Base/Long Context；每方法一次。',
           '所有生成（包括首轮）均来自本地 Qwen；图分支回放相同 Qwen 首轮恢复环境，在第二轮前替换一次历史。',
           '官方整任务评分；首轮失败不筛掉，不按分数重跑。配对任务不是独立重复样本。',
           '输入 token 包含缓存；整条轨迹用量=共同首轮+该方法续段。实际计算消耗只计共同首轮一次。','']
    for scope,values in summary['scopes'].items():
        lines += [scope,'方法 | 得分 | 首次续段平均输入 | 平均续段累计输入 | 平均整条轨迹累计输入']
        for mode in MODES:
            v=values[mode];first=v['mean_first_continuation_input_tokens'];cont=v['mean_continuation_input_tokens'];whole=v['mean_whole_trajectory_input_tokens']
            lines.append(f"{LABELS[mode]} | {v['passed']}/{v['tasks']} | {first} | {cont} | {whole}")
        lines.append('')
    lines+=['实际计算用量：'+json.dumps(summary['actual_compute'],ensure_ascii=False),'成败变化：'+json.dumps(paired,ensure_ascii=False),
            '首轮诊断：'+json.dumps(prefix_scores,ensure_ascii=False),'验证：'+json.dumps(summary['audit'],ensure_ascii=False)]
    (destination/'report.txt').write_text('\n'.join(lines)+'\n');print('\n'.join(lines[:12]));print('All raw records, shared prefixes, compact graphs and official scores verified.')
    return summary


if __name__=='__main__':summarize()
