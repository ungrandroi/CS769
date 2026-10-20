"""Summarize the all-GPT rerun and compare it with the frozen all-Qwen baseline."""
import argparse
from collections import Counter
import csv
from copy import deepcopy
import json
from pathlib import Path
from statistics import mean
from core.research_modes import MODES, LABELS
from core.graph_memory_serialization import decode_compact, normalize

ROOT=Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT=ROOT/'experiments/bfcl_identity/gpt41_experiment'
QWEN_SUMMARY=ROOT/'experiments/bfcl_identity/qwen27b_experiment/summary.json'
# USD per 1M tokens: input, cached input, output.
PRICES={'gpt-4.1':(2.00,0.50,8.00),'gpt-4.1-mini':(0.40,0.10,1.60)}


def read(p):return json.loads(p.read_text())


def aggregate(rows):
    first=[r['first_continuation_input_tokens'] for r in rows if r['first_continuation_input_tokens'] is not None]
    return {'tasks':len(rows),'passed':sum(r['passed'] for r in rows),'accuracy':sum(r['passed'] for r in rows)/len(rows) if rows else None,
            **{'mean_'+k:mean(r[k] for r in rows) if rows else None for k in ('prefix_input_tokens','continuation_input_tokens','continuation_requests','whole_trajectory_input_tokens')},
            'mean_first_continuation_input_tokens':mean(first) if first else None}


def summarize():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=DEFAULT_OUTPUT)
    args=parser.parse_args();out=args.output.resolve()
    plan=read(out/'plan.json');progress=read(out/'progress.json')
    assert progress['status']=='complete' and len(progress['runs'])==plan['planned_records']
    from bfcl_eval.eval_checker.eval_runner import _evaluate_single_multi_turn_entry
    from bfcl_eval.model_handler.api_inference.openai_response import OpenAIResponsesHandler
    from bfcl_eval.utils import load_dataset_entry,load_ground_truth_entry
    from core.graph_memory_replace import GraphMemoryReplacement, GraphMemoryV2Replacement
    handler=object.__new__(OpenAIResponsesHandler);handler.is_fc_model=True
    entries={c:{e['id']:e for e in load_dataset_entry(c)} for c in ('multi_turn_base','multi_turn_long_context')}
    answers={c:{e['id']:e['ground_truth'] for e in load_ground_truth_entry(c)} for c in entries}
    rows=[];usage=Counter();served=set();finish=Counter()
    for task in plan['tasks']:
        tid=task['id'];base=out/'tasks'/tid
        identity=read(base/'identity/manifest.json');source=read(base/'identity'/f'{tid}.api.json');source_full=read(base/'identity'/f'{tid}.full.json')
        n=identity['first_turn_requests']
        prompt=deepcopy(entries[task['category']][tid]);prompt['question']=prompt['question'][:1]
        diag=_evaluate_single_multi_turn_entry(handler,tid,deepcopy(source_full['result'][:1]),deepcopy(answers[task['category']][tid][:1]),prompt,'gpt_first_turn_audit',task['category'])
        for mode in MODES:
            d=base/mode;m=read(d/'manifest.json');tape=read(d/f'{tid}.api.json');score=read(d/'official-score.json')
            assert m['status'] in ('complete','not_reached') and m['agent_deployment']==plan['serving_model']
            assert m['first_turn_requests']==n and m['tools_sha256']==identity['tools_sha256']
            assert [(r['request'],r['response']) for r in tape[:n]]==[(r['request'],r['response']) for r in source[:n]]
            assert score['passed']==progress['runs'][tid+'/'+mode]['passed']
            if mode!='identity' and m['boundary_reached']:
                history=read(d/'prefix-history.json');assert history==read(base/'identity/prefix-history.json')
                builder=(GraphMemoryReplacement if mode=='v1-compact' else GraphMemoryV2Replacement)();builder.compress(history)
                assert read(d/f'{tid}.graph.json')==builder.graph
                text=(d/f'{tid}.memory.txt').read_text()
                assert normalize(decode_compact(text.split('\n',2)[2]))==normalize(json.loads(builder.render().split('\n',2)[2]))
            native=[json.loads(x) for x in (d/'native.jsonl').read_text().splitlines()] if (d/'native.jsonl').exists() else []
            first=None
            for item in native:
                if item['event']!='response':continue
                u=item['response']['usage'];served.add(item['response']['model']);finish.update([item['response']['choices'][0]['finish_reason']])
                usage.update({'input':u['prompt_tokens'],'output':u['completion_tokens'],'requests':1,
                              'cached_input':(u.get('prompt_tokens_details') or {}).get('cached_tokens',0)})
                if item['turn']>0 and first is None:first=u['prompt_tokens']
            prefix=identity['prefix_usage'];cont=m['continuation_usage']
            reason='passed' if score['passed'] else ';'.join(dict.fromkeys(x.get('error',{}).get('error_type','unknown') for x in score['diagnostics']))
            rows.append({'id':tid,'category':task['category'],'mode':mode,'passed':score['passed'],'boundary_reached':m['boundary_reached'],
                         'first_turn_passed':diag['valid'],'official_reason':reason,'memory_tokens':m.get('memory_tokens'),
                         'prefix_input_tokens':prefix['prompt_tokens'],'continuation_input_tokens':cont['prompt_tokens'],
                         'continuation_requests':m['continuation_requests'],'whole_trajectory_input_tokens':prefix['prompt_tokens']+cont['prompt_tokens'],
                         'first_continuation_input_tokens':first})
    qwen=[r for r in read(QWEN_SUMMARY)['rows']]
    def scopes(rs):
        groups={'all':rs,**{c:[r for r in rs if r['category']==c] for c in entries}}
        return {g:{m:aggregate([r for r in v if r['mode']==m]) for m in MODES} for g,v in groups.items()}
    gpt_scopes,qwen_scopes=scopes(rows),scopes(qwen)
    def lookup(rs):return {(r['id'],r['mode']):r for r in rs}
    g,q=lookup(rows),lookup(qwen)
    drops={name:{mode:[t['id'] for t in plan['tasks'] if rs[(t['id'],'identity')]['passed'] and not rs[(t['id'],mode)]['passed']] for mode in MODES[1:]}
           for name,rs in (('gpt',g),('qwen',q))}
    gains={name:{mode:[t['id'] for t in plan['tasks'] if not rs[(t['id'],'identity')]['passed'] and rs[(t['id'],mode)]['passed']] for mode in MODES[1:]}
           for name,rs in (('gpt',g),('qwen',q))}
    price=PRICES.get(plan['serving_model'])
    cost=None
    if price:
        cost=((usage['input']-usage['cached_input'])*price[0]+usage['cached_input']*price[1]+usage['output']*price[2])/1e6
    summary={'status':'complete','deployment':plan['serving_model'],'served_models':sorted(served),'rows':rows,'scopes':gpt_scopes,
             'qwen_scopes':qwen_scopes,'identity_to_graph_drops':drops,'identity_to_graph_gains':gains,
             'actual_compute':dict(usage),'finish_reason_counts':dict(finish),'estimated_cost_usd':cost}
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    with (out/'task-results.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

    name=plan['serving_model']
    def pct(v):return '-' if v is None else f"{100*v:.1f}%"
    def tok(v):return '-' if v is None else f"{v:,.0f}"
    lines=[f'# {name} 与 Qwen3.8-27B 对照：图记忆基线',
           '',
           f"{plan['task_conditions']} 个条件（GorillaFileSystem 题族 × `multi_turn_base` / `multi_turn_long_context`，与 Qwen 基线同一批题），每种记忆每题跑一次。"
           f"{name} 全程生成，包括第一轮；两种图回放这段第一轮恢复模拟器，在第二轮用户消息之前把历史换成图。"
           '图的构建、替换时机和题目顺序与 Qwen 基线相同。官方 BFCL 整题评分，第一轮失败也计入。',
           '',
           f"实际服务模型：{', '.join(sorted(served))}。温度 0，seed 42，`max_tokens` 4096。",
           '',
           f"## 汇总（{name} {plan['task_conditions']} 个条件；Qwen 26 个条件）",
           '',
           f'| 方法 | {name} 通过 | {name} 比例 | {name} 整段平均输入 | Qwen 通过 | Qwen 比例 | Qwen 整段平均输入 |',
           '| --- | --- | --- | --- | --- | --- | --- |']
    for mode in MODES:
        a,b=gpt_scopes['all'][mode],qwen_scopes['all'][mode]
        lines.append(f"| {LABELS[mode]} | {a['passed']}/{a['tasks']} | {pct(a['accuracy'])} | {tok(a['mean_whole_trajectory_input_tokens'])} | "
                     f"{b['passed']}/{b['tasks']} | {pct(b['accuracy'])} | {tok(b['mean_whole_trajectory_input_tokens'])} |")
    lines+=['','整段输入 = 共用第一轮 + 该方法续跑，每次请求的 `prompt_tokens` 相加（含工具定义和缓存命中部分）。'
            f'{name} 用自己的 tokenizer 计数，Qwen 用 Qwen 的 tokenizer，两边 token 数只能看量级，不能逐个比较。','',
            '## 按切分','',
            f'| 切分 | 方法 | {name} 通过 | Qwen 通过 |','| --- | --- | --- | --- |']
    for c in entries:
        for mode in MODES:
            a,b=gpt_scopes[c][mode],qwen_scopes[c][mode]
            lines.append(f"| `{c}` | {LABELS[mode]} | {a['passed']}/{a['tasks']} | {b['passed']}/{b['tasks']} |")
    lines+=['','## 原文通过、换成图后失败的题','',f'| 方法 | {name} | Qwen |','| --- | --- | --- |']
    for mode in MODES[1:]:
        lines.append(f"| {LABELS[mode]} | {', '.join(drops['gpt'][mode]) or '无'} | {', '.join(drops['qwen'][mode]) or '无'} |")
    lines+=['','反过来，原文失败、换成图后通过：']
    for mode in MODES[1:]:
        lines.append(f"- {LABELS[mode]}：{name} {', '.join(gains['gpt'][mode]) or '无'}；Qwen {', '.join(gains['qwen'][mode]) or '无'}")
    lines+=['','## 逐题','','1 = 通过，0 = 失败。顺序是原文 / 状态转移图 / 事件图。','',
            f'| 题目 | {name} | Qwen | {name} 第一轮 | {name} 失败原因（图） |','| --- | --- | --- | --- | --- |']
    for t in plan['tasks']:
        gs=[g[(t['id'],m)] for m in MODES];qs=[q[(t['id'],m)] for m in MODES]
        reasons='; '.join(f"{LABELS[r['mode']]}: {r['official_reason']}" for r in gs[1:] if not r['passed'])
        lines.append(f"| {t['id']} | {' / '.join(str(int(r['passed'])) for r in gs)} | {' / '.join(str(int(r['passed'])) for r in qs)} | "
                     f"{'通过' if gs[0]['first_turn_passed'] else '失败'} | {reasons or '-'} |")
    lines+=['','## 用量','',
            f"实际请求 {usage['requests']} 次，输入 {usage['input']:,} token（其中缓存命中 {usage['cached_input']:,}），输出 {usage['output']:,} token。"
            +(f" 按牌价估算约 ${cost:.2f}。" if cost is not None else ''),
            f"结束原因：{json.dumps(dict(finish),ensure_ascii=False)}。"]
    (out/'comparison.md').write_text('\n'.join(lines)+'\n')
    print('\n'.join(lines[:20]))
    return summary


if __name__=='__main__':summarize()
