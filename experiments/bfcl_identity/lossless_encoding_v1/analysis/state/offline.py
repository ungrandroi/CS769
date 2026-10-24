"""Development-only direct codec recovery and local native-token measurements."""
import hashlib
import json
from pathlib import Path
from statistics import mean
from core.lossless_state import CANDIDATES, encode, decode, dumps, _same
from core.local_qwen_tokenizer import LocalQwenTokenizer
from core.optimized_graph import restore_history, rebuild_original_graph

root = Path('experiments/bfcl_identity/work1000_research')
out = Path('experiments/bfcl_identity/lossless_encoding_v1/analysis/state')
split = json.loads((root/'task-split.json').read_text())
files = []
for task in split['tasks']:
    if task['split'] != 'development': continue
    for seed in split['seeds']:
        path = root/'tasks'/task['id']/f'seed{seed}'/'state-none'/'memory-metadata.json'
        if path.exists(): files.append((task['id'],seed,path))
assert len(files) == 13
rows=[]
with LocalQwenTokenizer() as tok:
    def count(text): return len(tok.encode(text))
    for task,seed,path in files:
        metadata=json.loads(path.read_text()); graph=metadata['graph']
        for candidate in CANDIDATES:
            enc=encode(graph,candidate); dec=decode(json.loads(dumps(enc)))
            assert _same(graph,dec)
            assert _same(restore_history(graph),restore_history(dec))
            assert _same(rebuild_original_graph(graph),rebuild_original_graph(dec))
            rows.append({'task':task,'seed':seed,'candidate':candidate,'baseline_tokens':count(dumps(graph)),
                         'encoded_tokens':count(dumps(enc)),'rules_tokens':count(enc['decoding']),
                         'payload_exact':True,'history_exact':True,'builder_graph_exact':True,
                         'input_payload_sha256':hashlib.sha256(dumps(graph).encode()).hexdigest()})
            (out/f'{task}-seed{seed}-{candidate}.json').write_text(json.dumps(enc,ensure_ascii=False,indent=2)+'\n')
    provenance=tok.provenance
summary=[]
for candidate in CANDIDATES:
    data=[row for row in rows if row['candidate']==candidate]
    summary.append({'id':candidate,'module':'core.lossless_state','baseline_method':'state',
                    'baseline_method_id':'v1-compact','external_explanation':'none','development_checkpoints':len(data),
                    'baseline_mean_tokens':mean(row['baseline_tokens'] for row in data),
                    'encoded_mean_tokens':mean(row['encoded_tokens'] for row in data),
                    'mean_paired_ratio':mean(row['encoded_tokens']/row['baseline_tokens'] for row in data),
                    'strict_recovery_passed':len(data),'evidence':'measurements.json'})
summary.sort(key=lambda row:row['encoded_mean_tokens'])
(out/'measurements.json').write_text(json.dumps({'scope':'development only; memory body only, no native chat wrappers',
 'codec_sha256':hashlib.sha256(Path('scripts/core/lossless_state.py').read_bytes()).hexdigest(),
 'rows':rows,'summary':summary,'tokenizer_provenance':provenance},ensure_ascii=False,indent=2)+'\n')
(out/'candidates.json').write_text(json.dumps({'candidates':summary,'recommended_live':[r['id'] for r in summary[:2]],
 'api':'encode(payload,candidate); decode(encoded); build_memory(history,method,explanation,count,candidate)',
 'limitations':'Token savings are offline body counts, not model capability evidence. All decoding text and dictionaries are in-band and counted.'},indent=2)+'\n')
print(json.dumps(summary,indent=2))
