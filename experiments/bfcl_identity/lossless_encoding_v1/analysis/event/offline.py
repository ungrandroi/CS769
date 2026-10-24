"""Development-only exact local tokenizer evaluation; never invokes inference."""
import hashlib
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / 'scripts'))
from core.lossless_event import VARIANTS, encode, decode, dumps
from core.local_qwen_tokenizer import LocalQwenTokenizer
from core.optimized_graph import _same, restore_history, rebuild_original_graph, audit_semantic_index

old = ROOT / 'experiments/bfcl_identity/work1000_research'
out = ROOT / 'experiments/bfcl_identity/lossless_encoding_v1/analysis'
split = json.loads((old / 'task-split.json').read_text())
tokenizer = LocalQwenTokenizer()
count = tokenizer.count
all_rows = []
for task in split['tasks']:
    if task['split'] != 'development':
        continue
    for seed in split['seeds']:
        for method in ('event', 'dedup'):
            source = old / 'tasks' / task['id'] / f'seed{seed}' / f'{method}-none'
            path = source / 'memory-metadata.json'
            if not path.exists():
                continue
            metadata = json.loads(path.read_text())
            payload = metadata['graph']
            history = json.loads((source / 'checkpoint-history.json').read_text())
            original = rebuild_original_graph(payload)
            assert _same(restore_history(payload), history)
            assert audit_semantic_index(original, payload)
            sample_out = out / method / 'samples' / task['id'] / f'seed{seed}'
            sample_out.mkdir(parents=True, exist_ok=True)
            base_tokens = count(dumps(payload))
            for variant in VARIANTS:
                encoded = encode(payload, variant)
                text = dumps(encoded)
                decoded = decode(json.loads(text))
                assert _same(payload, decoded)
                assert _same(history, restore_history(decoded))
                assert _same(original, rebuild_original_graph(decoded))
                assert audit_semantic_index(original, decoded)
                (sample_out / f'{variant}.json').write_text(text + '\n')
                all_rows.append({'task': task['id'], 'seed': seed, 'method': method,
                    'variant': variant, 'baseline_body_tokens': base_tokens,
                    'encoded_body_tokens': count(text),
                    'ratio': count(text) / base_tokens,
                    'payload_exact': True, 'history_exact': True, 'original_graph_exact': True,
                    'dictionary_order_policy': 'Original table/source-message order retained; other dictionary order immaterial.',
                    'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                    'encoded_sha256': hashlib.sha256(text.encode()).hexdigest(),
                    'packed_tables': encoded['packed_tables'],
                    'shared_values': len(encoded.get('shared_values', {}))})
for method in ('event', 'dedup'):
    rows = [r for r in all_rows if r['method'] == method]
    summary = []
    for variant in VARIANTS:
        items = [r for r in rows if r['variant'] == variant]
        summary.append({'variant': variant, 'checkpoints': len(items),
                        'baseline_body_tokens_mean': statistics.mean(r['baseline_body_tokens'] for r in items),
                        'encoded_body_tokens_mean': statistics.mean(r['encoded_body_tokens'] for r in items),
                        'mean_per_checkpoint_ratio': statistics.mean(r['ratio'] for r in items),
                        'all_payload_history_original_graph_exact': all(r['payload_exact'] and r['history_exact'] and r['original_graph_exact'] for r in items)})
    report = {'scope': '13 development triggered checkpoints only. Plain memory body includes all visible codec rules; excludes fixed request overhead. No inference.',
              'codec_sha256': hashlib.sha256((ROOT / 'scripts/core/lossless_event.py').read_bytes()).hexdigest(),
              'tokenizer': tokenizer.provenance, 'summary': summary, 'rows': rows}
    (out / method / 'offline-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(method, json.dumps(summary))
