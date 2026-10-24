"""Offline-only next idea; not a registered live candidate or code mutation."""
import json
from copy import deepcopy
from pathlib import Path
from statistics import mean
from core.lossless_state import _table,_untable,_shared,_unshare,_same,dumps,TABLE_RULE,SHARED_RULE
from core.local_qwen_tokenizer import LocalQwenTokenizer

RULE = (' json_string_columns gives each source schema/column JSON serialization options: '
        'its cell is parsed JSON, serialized with those options to restore the exact original string.')

def encode(payload):
    transformed=deepcopy(payload); formats=[]
    for schema,columns in payload['source_message_columns'].items():
        for col_index,col in enumerate(columns):
            if col not in ('arguments','output'):continue
            rows=[row for row in transformed['source_messages'].values() if row[0]==schema]
            raw=[row[col_index+1] for row in rows]
            if not rows or not all(isinstance(value,str) for value in raw): continue
            try: parsed=[json.loads(value) for value in raw]
            except (json.JSONDecodeError,ValueError):continue
            found=False
            for separators in [(',',':'),(', ',': ')]:
                for ensure_ascii in [False,True]:
                    if all(json.dumps(v,ensure_ascii=ensure_ascii,separators=separators,allow_nan=False)==s for v,s in zip(parsed,raw)):
                        formats.append({'schema':schema,'column':col,'separators':separators,'ensure_ascii':ensure_ascii})
                        for row,value in zip(rows,parsed):row[col_index+1]=value
                        found=True;break
                if found:break
    value,shared=_shared(_table(transformed))
    return {'encoding':'offline-json-column-probe','decoding':TABLE_RULE+SHARED_RULE+RULE,
            'payload':value,'shared_values':shared,'json_string_columns':formats}

def decode(encoded):
    result=_untable(_unshare(encoded['payload'],encoded['shared_values']))
    for config in encoded['json_string_columns']:
        schema=config['schema'];i=result['source_message_columns'][schema].index(config['column'])+1
        for row in result['source_messages'].values():
            if row[0]==schema:row[i]=json.dumps(row[i],separators=config['separators'],ensure_ascii=config['ensure_ascii'],allow_nan=False)
    return result

if __name__=='__main__':
    root=Path('experiments/bfcl_identity/work1000_research'); split=json.loads((root/'task-split.json').read_text()); rows=[]
    with LocalQwenTokenizer() as tok:
        for task in split['tasks']:
            if task['split']!='development':continue
            for seed in split['seeds']:
                p=root/'tasks'/task['id']/f'seed{seed}'/'state-none'/'memory-metadata.json'
                if not p.exists():continue
                graph=json.loads(p.read_text())['graph'];encoded=encode(graph);assert _same(graph,decode(json.loads(dumps(encoded))))
                rows.append({'task':task['id'],'seed':seed,'baseline':len(tok.encode(dumps(graph))),
                             'encoded':len(tok.encode(dumps(encoded)))})
    print(json.dumps({'mean_baseline':mean(r['baseline'] for r in rows),'mean_encoded':mean(r['encoded'] for r in rows),'rows':rows},indent=2))
