import csv,json,hashlib
from pathlib import Path
from statistics import mean
from collections import Counter
from qwen_transport import prefix_log,digest,chat_messages
from qwen_prompt_accounting import to_chat_tools
from graph_memory_serialization import normalize,decode_compact
from v2_provenance_dedup import decode
from graph_memory_replace import retained_instructions,assert_replacement_request
from run_qwen_task import TOOLS
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'experiments/bfcl_identity';OUT=BASE/'qwen27b_dedup_eval';OLD=BASE/'qwen27b_experiment'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    plan=read(OUT/'plan.json');progress=read(OUT/'progress.json');assert progress['status']=='complete' and len(progress['runs'])==26
    for name,h in plan['implementation_sha256'].items():assert sha(ROOT/'scripts'/name)==sha(OUT/'source_code'/name)==h
    for name,h in plan['data_sha256'].items():assert sha(ROOT/name)==h
    for name,h in read(OLD/'artifact-manifest.json')['files'].items():assert sha(OLD/name)==h
    baseline=read(OLD/'summary.json');rows=[r.copy() for r in baseline['rows'] if r['mode'] in ('identity','v2-compact')]
    new=[];finishes=Counter();usage=Counter()
    for task in plan['tasks']:
        tid=task['id'];d=OUT/'tasks'/tid;b=OLD/'tasks'/tid;source=b/'identity'
        m=read(d/'manifest.json');im=read(source/'manifest.json');tape=read(d/f'{tid}.api.json');itape=read(source/f'{tid}.api.json');n=im['first_turn_requests']
        assert m['status']=='complete' and m['experimental_variant']=='v2-provenance-dedup'
        assert m['runtime']==im['runtime'] and m['base_url']==im['base_url'] and m['tools_sha256']==im['tools_sha256']
        assert m['first_turn_requests']==m['replayed_requests']==n
        assert [(r['request'],r['response']) for r in tape[:n]]==[(r['request'],r['response']) for r in itape[:n]]
        assert all(r['source']=='qwen_prefix_replay' for r in tape[:n]) and all(r['source']=='live_local_qwen' for r in tape[n:])
        full=read(d/f'{tid}.full.json');initial=read(source/f'{tid}.full.json')
        assert prefix_log(full['metadata']['inference_log'])==prefix_log(initial['metadata']['inference_log'])
        history=read(d/'prefix-history.json');assert history==read(source/'prefix-history.json') and digest(history)==m['boundary']['history_sha256']
        memory=(d/f'{tid}.memory.txt').read_text();previous=(b/'v2-compact'/f'{tid}.memory.txt').read_text()
        assert normalize(decode(memory.split('\n',2)[2]))==normalize(decode_compact(previous.split('\n',2)[2]))
        assert memory==(BASE/'v2_provenance_dedup_probe/tasks'/tid/'v2.memory.txt').read_text()
        assert read(d/f'{tid}.graph.json')==read(b/'v2-compact'/f'{tid}.graph.json')
        replacement=[*retained_instructions(history),{'role':'assistant','content':memory}]
        for r in tape[n:]:assert_replacement_request(r['request'],replacement,history)
        native=[json.loads(x) for x in (d/'native.jsonl').read_text().splitlines()]
        sent=[x for x in native if x['event']=='request'];received=[x for x in native if x['event']=='response']
        assert len(sent)==len(received)==len(tape[n:])==m['live_requests']
        counters=Counter()
        for s,r,logical in zip(sent,received,tape[n:]):
            req=s['request'];raw=r['response'];u=raw['usage'];assert s['index']==r['index'] and s['turn']==r['turn']>0
            assert req['model']==raw['model']==plan['serving_model']
            assert req['temperature']==0 and req['seed']==42 and req['max_tokens']==4096 and req['cache_prompt'] is True
            assert req['chat_template_kwargs']=={'enable_thinking':False,'preserve_thinking':False}
            assert req['messages']==chat_messages(logical['request']['input']) and req['tools']==to_chat_tools(logical['request']['tools'])
            assert {t['function']['name'] for t in req['tools']}==TOOLS
            assert 0<u['prompt_tokens']<131072 and u['total_tokens']==u['prompt_tokens']+u['completion_tokens']
            assert logical['response']['usage']['input_tokens']==u['prompt_tokens'] and logical['response']['usage']['output_tokens']==u['completion_tokens']
            counters.update({k:u[k] for k in ('prompt_tokens','completion_tokens','total_tokens')});finishes.update([raw['choices'][0]['finish_reason']])
        assert dict(counters)==m['live_usage']==m['continuation_usage'];usage.update(counters)
        score=read(d/'official-score.json');assert score['passed']==progress['runs'][tid]['passed']
        assert sha(d/score['score_file'])==score['score_sha256'];result,=list((d/'result').rglob('*_result.json'));assert sha(result)==score['result_sha256']
        prefix=im['prefix_usage'];r={'id':tid,'category':task['category'],'mode':'v2-dedup','passed':score['passed'],
            'whole_trajectory_input_tokens':prefix['prompt_tokens']+counters['prompt_tokens'],'continuation_input_tokens':counters['prompt_tokens'],
            'whole_trajectory_output_tokens':prefix['completion_tokens']+counters['completion_tokens'],'continuation_requests':m['continuation_requests'],
            'first_continuation_input_tokens':received[0]['response']['usage']['prompt_tokens']}
        new.append(r)
    rows+=new;groups={};modes=['identity','v2-compact','v2-dedup']
    for category in ['all','multi_turn_base','multi_turn_long_context']:
        groups[category]={}
        for mode in modes:
            rs=[r for r in rows if r['mode']==mode and (category=='all' or r['category']==category)]
            groups[category][mode]={'tasks':len(rs),'passed':sum(r['passed'] for r in rs),**{'mean_'+k:mean(r[k] for r in rs) for k in ['whole_trajectory_input_tokens','continuation_input_tokens','first_continuation_input_tokens','continuation_requests']}}
    paired={}
    for reference in ['identity','v2-compact']:
        ref={r['id']:r for r in rows if r['mode']==reference}
        paired[reference]=[{'id':r['id'],'reference':ref[r['id']]['passed'],'dedup':r['passed']} for r in new if r['passed']!=ref[r['id']]['passed']]
    summary={'status':'complete','groups':groups,'paired_changes':paired,'actual_new_usage':dict(usage),'finish_reasons':dict(finishes),'new_rows':new,'audit_passed':True,'baseline_unchanged':True,'sampling':'one continuation per method per task; no score-based retry; 26 paired conditions from 13 families'}
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    with (OUT/'task-results.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(new[0]));w.writeheader();w.writerows(new)
    lines=['Qwen V2 无损来源去重：26 项固定首轮配对续跑，官方整任务评分。','原 Identity/V2 作为已有对照；所有首轮都来自同一 Qwen 记录，第二轮前只替换编码一次。','输入 token 包含缓存；整任务=共同首轮+各自续段。单次运行，不根据分数重试。']
    for category,results in groups.items():
        lines += [category,'方法 | 成功 | 平均首次续段输入 | 平均整任务累计输入 | 平均续段请求数']
        for mode,r in results.items():lines.append(f"{mode} | {r['passed']}/{r['tasks']} | {r['mean_first_continuation_input_tokens']:.2f} | {r['mean_whole_trajectory_input_tokens']:.2f} | {r['mean_continuation_requests']:.2f}")
    lines += ['成败变化：'+json.dumps(paired,ensure_ascii=False),'所有原始记录、共享首轮、编码还原、实际请求、官方评分文件核验通过。']
    (OUT/'report.txt').write_text('\n'.join(lines)+'\n');print('\n'.join(lines))
if __name__=='__main__':main()
