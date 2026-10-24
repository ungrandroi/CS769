"""Reuse frozen inference harness; change only delivered V2 serialization."""
import json,sys
from pathlib import Path
from workflows import baseline_task as runner
from core.graph_memory_serialization import decode_compact,normalize
from core.event_graph_dedup import encode,decode
original_make=runner.make_memory

def make_memory(history,mode,count):
    assert mode=='v2-compact'
    memory,audit_graph=original_make(history,mode,count)
    head,explanation,payload=memory.split('\n',2)
    graph=decode_compact(payload);encoded,stats=encode(graph,count)
    assert normalize(decode(encoded))==normalize(graph)
    return head+'\n'+explanation+'\n'+encoded,audit_graph

def main():
    if '--mode' in sys.argv:
        index=sys.argv.index('--mode')+1
        if sys.argv[index] in ('Event Graph-Dedup','event-graph-dedup','v2-dedup'):
            sys.argv[index]='v2-compact'
    previous=runner.make_memory
    try:
        runner.make_memory=make_memory
        runner.main()
    finally:
        runner.make_memory=previous
    out=Path(sys.argv[sys.argv.index('--output')+1]);p=out/'manifest.json';m=json.loads(p.read_text())
    m['experimental_variant']='v2-provenance-dedup';m['serialization']='V2 PROVENANCE RECIPES 1; always applied, no shorter-format fallback'
    p.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')

if __name__ == "__main__":main()
