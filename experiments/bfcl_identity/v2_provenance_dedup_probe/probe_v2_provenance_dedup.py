import csv,json,hashlib,shutil
from pathlib import Path
from statistics import mean
from local_qwen_tokenizer import LocalQwenTokenizer
from graph_memory_serialization import decode_compact,normalize
from v2_provenance_dedup import encode,decode
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'experiments/bfcl_identity';OUT=BASE/'v2_provenance_dedup_probe'

def main():
    OUT.mkdir(exist_ok=True);rows=[];hashes={}
    with LocalQwenTokenizer() as tok:
        for task in json.loads((BASE/'qwen27b_experiment/plan.json').read_text())['tasks']:
            tid=task['id'];src=BASE/'qwen27b_experiment/tasks'/tid/'v2-compact'/f'{tid}.memory.txt'
            text=src.read_text();head,explanation,payload=text.split('\n',2);original=decode_compact(payload)
            hashes[str(src.relative_to(ROOT))]=hashlib.sha256(src.read_bytes()).hexdigest()
            row={'task':tid,'category':task['category'],'v2_compact':tok.count(text)}
            target=OUT/'tasks'/tid;target.mkdir(parents=True,exist_ok=True)
            for label,graph in [('v2',original)]:
                before=normalize(graph);encoded,stats=encode(graph,tok.count);restored=decode(encoded)
                assert normalize(graph)==before==normalize(restored)
                delivered=head+'\n'+explanation+'\n'+encoded
                (target/(label+'.memory.txt')).write_text(delivered)
                (target/(label+'.stats.json')).write_text(json.dumps(stats,indent=2))
                row[label+'_dedup_tokens']=tok.count(delivered)
                for k,v in stats.items():row[label+'_'+k]=v
            candidate=(target/'v2.memory.txt').read_text()
            selected=candidate if row['v2_dedup_tokens']<row['v2_compact'] else text
            (target/'selected.memory.txt').write_text(selected)
            row['selected_tokens']=min(row['v2_dedup_tokens'],row['v2_compact'])
            row['selected_format']='dedup' if selected==candidate else 'original'
            assert normalize(decode(candidate.split('\n',2)[2]))==normalize(original)
            rows.append(row)
    groups={}
    for category in ['all','multi_turn_base','multi_turn_long_context']:
        rs=[r for r in rows if category=='all' or r['category']==category]
        a={k:mean(r[k] for r in rs) for k in ['v2_compact','v2_dedup_tokens','selected_tokens']}
        a.update(selected_change_percent=100*(a['selected_tokens']/a['v2_compact']-1),tasks=len(rs),v2_change_percent=100*(a['v2_dedup_tokens']/a['v2_compact']-1),v2_smaller_tasks=sum(r['v2_dedup_tokens']<r['v2_compact'] for r in rs))
        groups[category]=a
    summary={'metric':'Qwen native tokenizer; memory only, all decoding instructions included','groups':groups,'rows':rows,'source_hashes':hashes,'exact_roundtrip_26_graphs':True,'model_inference':False,'v2_original_order_preserved':True,'literal_fallback_on_nonmatching_recipes':True}
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    with (OUT/'task-results.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    (OUT/'report.txt').write_text('V2 来源关系无损去重：固定 26 段首轮历史；原 V2 共 26 张图。\n保持所有字段、类型、顺序和重复调用；仅在可精确重建时采用关系配方，否则保留原文。\n完整解码规则计入 token；仅离线测量记忆文本，不代表整任务输入或成功率。\n'+json.dumps(groups,ensure_ascii=False,indent=2)+'\n')
    for f in ['v2_provenance_dedup.py','probe_v2_provenance_dedup.py']:shutil.copyfile(ROOT/'scripts'/f,OUT/f)
    print(json.dumps(groups,indent=2))
if __name__=='__main__':main()
