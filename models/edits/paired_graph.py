"""Paired execution-node view over evidence graph; existing evidence remains reconstructable.
Only adjacent matched call/result records are fused. Parallel/unmatched records
retain original order and links. This does not change state-chain selection.
"""
from copy import deepcopy
from functools import partial
import json,time
from cs769.models.edits import compact_graph, state_chain
VERSION="g9-paired-execution-v1"
HEADER=("Prior evidence graph. Ordered rows: U=user, A=assistant, "
        "X=[call_id,group,tool,args,output,error?]. X labels=call/result IDs; "
        "TURN=turn; equal group=same assistant message.\n")
MIXED="C=[call_id,group,tool,args]; R=[call_ref,output,error?].\n"
def encode(text):
    if not text.startswith(compact_graph.HEADER):return text
    try:
        rest=text[len(compact_graph.HEADER):]
        fence,rest=rest.split("\n",1)
        body,tail=rest.split("END_RECORDS\n",1)
        lines=body.splitlines();out=[];pairs=[];i=0;unpaired=False
        while i<len(lines):
            line=lines[i]
            if line.startswith("TURN "):out.append(line);i+=1;continue
            eid,kind,raw=line.split(" ",2);value=json.loads(raw)
            if kind=="C" and i+1<len(lines) and not lines[i+1].startswith("TURN "):
                rid,rkind,rraw=lines[i+1].split(" ",2);rv=json.loads(rraw)
                if rkind=="R" and rv[0]==eid and len(value)==4 and len(rv) in (2,3):
                    out.append(eid+"/"+rid+" X "+json.dumps(value+rv[1:],ensure_ascii=False,separators=(",",":")))
                    pairs.append((eid,rid));i+=2;continue
            unpaired|=kind in ("C","R");out.append(line);i+=1
        if not pairs:return text
        result=HEADER+(MIXED if unpaired else "")+fence+"\n"+"\n".join(out)+"\nEND_RECORDS\n"+tail
        if decode(result)!=text:raise AssertionError("Paired view roundtrip differs")
        return result
    except (ValueError,IndexError,TypeError):
        return text
def decode(text):
    if not text.startswith(HEADER):return text
    rest=text[len(HEADER):]
    if rest.startswith(MIXED):rest=rest[len(MIXED):]
    fence,rest=rest.split("\n",1)
    body,tail=rest.split("END_RECORDS\n",1);out=[]
    for line in body.splitlines():
        if line.startswith("TURN "):out.append(line);continue
        label,kind,raw=line.split(" ",2)
        if kind!="X":out.append(line);continue
        cid,rid=label.split("/");value=json.loads(raw)
        if len(value) not in (5,6):raise ValueError("Invalid execution payload")
        out.append(cid+" C "+json.dumps(value[:4],ensure_ascii=False,separators=(",",":")))
        out.append(rid+" R "+json.dumps([cid]+value[4:],ensure_ascii=False,separators=(",",":")))
    return compact_graph.HEADER+fence+"\n"+"\n".join(out)+"\nEND_RECORDS\n"+tail
def render(g,*,renderer):
    return encode(renderer(g))
def _wrap(g,count,current,lossy):
    start=time.perf_counter()
    out,base_audit,base=(state_chain.contract if lossy else compact_graph.compact)(g,count,current)
    text=base(out);short=encode(text)
    assert decode(short)==text
    use=short!=text and count(short)<count(text)
    renderer=partial(render,renderer=base) if use else base
    pairs=[]
    if use:
        for line in short.split("END_RECORDS\n",1)[0].splitlines():
            parts=line.split(" ",2)
            if len(parts)==3 and parts[1]=="X":
                c,r=parts[0].split("/");pairs.append({"call":c,"result":r,"node":parts[0]})
    out=deepcopy(out)
    audit=dict(base_audit)
    audit.update(version=VERSION,underlying_version=base_audit["version"],
                 pair_fusion_applied=use,paired_nodes=len(pairs),paired_nodes_map=pairs,
                 pair_saved_tokens=count(text)-count(renderer(out)),pair_roundtrip_exact=True,
                 editor_api_tokens=0,editor_seconds=time.perf_counter()-start)
    return out,audit,renderer
def compact(g,count,current=None):return _wrap(g,count,current,False)
def contract(g,count,current=None):return _wrap(g,count,current,True)
