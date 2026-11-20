"""Lossless compact serialization of the model-visible evidence graph graph.
Decode restores the exact prior rendering, including payload spelling and links.
Unknown layouts are retained verbatim rather than guessed.
"""
import json,re,time
from functools import partial
from cs769.models.edits.witness_pruning import _share
VERSION="g9-compact-records-v1"
ORIGINAL_HEADER=('<memory_graph scope="completed_prior_turns">\n'
 'Nodes contain prior visible evidence. IDs link episodes, calls and results. '
 'order is recorded sequence; call_group identifies calls in the same assistant message.\n')
HEADER=('Prior evidence graph. TURN sets the turn; rows are ordered: id kind JSON.\n'
 'U=user text; A=assistant text; C=[call_id,group,name,arguments]; '
 'R=[call_ref,output,optional error flag]. Same group=one assistant message.\n')
KINDS={"user_request":"U","assistant_statement":"A","tool_call":"C","tool_result":"R"}
CATEGORIES={v:k for k,v in KINDS.items()}
ROLES={"U":"user","A":"assistant","C":"assistant","R":"tool"}
def encode(text):
    if not text.startswith(ORIGINAL_HEADER):return text
    try:
        pos=len(ORIGINAL_HEADER);rows=[];episode=None;fence=None
        def line():
            nonlocal pos
            end=text.index("\n",pos);out=text[pos:end];pos=end+1;return out
        while pos<len(text) and not text.startswith("precedes:",pos):
            if text.startswith("EPISODE ",pos):episode=line().split(" ",1)[1]
            label=line()
            m=re.fullmatch(r"(user_request|assistant_statement|tool_call|tool_result) (e\d+) source_role=(user|assistant|tool) in_turn=(t\d+) order=(\d+)(.*)",label)
            if not m:return text
            category,eid,role,turn,order,extra=m.groups();kind=KINDS[category]
            if turn!=episode or role!=ROLES[kind] or int(order)!=len(rows):return text
            fields=[]
            count=2 if kind=="C" else 1
            for _ in range(count):
                field=line()
                if not field.endswith(" [str]"):return text
                f=line()
                if not re.fullmatch(r"\x60{3,}",f):return text
                if fence is None:fence=f
                if f!=fence:return text
                end=text.index("\n"+f+"\n",pos);value=text[pos:end];pos=end+len(f)+2
                fields.append((field[:-6],value))
            expected={"U":["content"],"A":["text"],"C":["name","arguments"],"R":["output"]}[kind]
            if [x[0] for x in fields]!=expected:return text
            if kind in ("U","A"):
                if extra:return text
                payload=fields[0][1]
            elif kind=="C":
                m2=re.fullmatch(r" call_id=(.*) call_group=(\S+)",extra)
                if not m2:return text
                payload=[json.loads(m2[1]),m2[2],fields[0][1],fields[1][1]]
            else:
                m2=re.fullmatch(r" result_of=(e\d+)(?: native_is_error=(true|false))?",extra)
                if not m2:return text
                payload=[m2[1],fields[0][1]]
                if m2[2] is not None:payload.append(json.loads(m2[2]))
            rows.append((eid,kind,turn,payload))
        preceding=line()
        if preceding!="precedes: "+" -> ".join(r[0] for r in rows):return text
        result=HEADER+"fence="+str(len(fence or "___"))+"\n"
        last_turn=None
        for eid,kind,turn,value in rows:
            if turn!=last_turn:result+="TURN "+turn+"\n";last_turn=turn
            result+=f"{eid} {kind} "+json.dumps(value,ensure_ascii=False,separators=(",",":"))+"\n"
        result+="END_RECORDS\n"+text[pos:]
        if decode(result)!=text:raise AssertionError("Compact graph round-trip differs")
        return result
    except (ValueError,IndexError,TypeError):
        return text
def decode(text):
    if not text.startswith(HEADER):return text
    rest=text[len(HEADER):];first,rest=rest.split("\n",1)
    fence="\x60"*int(first.split("=",1)[1])
    body,tail=rest.split("END_RECORDS\n",1)
    out=ORIGINAL_HEADER;ids=[];episode=None
    for row in body.splitlines():
        if row.startswith("TURN "):turn=row.split(" ",1)[1];continue
        i=len(ids)
        eid,kind,raw=row.split(" ",2);value=json.loads(raw);ids.append(eid)
        if turn!=episode:out+="EPISODE "+turn+"\n";episode=turn
        out+=f"{CATEGORIES[kind]} {eid} source_role={ROLES[kind]} in_turn={turn} order={i}"
        if kind in ("U","A"):fields=[("content" if kind=="U" else "text",value)]
        elif kind=="C":
            cid,group,name,args=value
            out+=" call_id="+json.dumps(cid,ensure_ascii=False,separators=(",",":"))+" call_group="+group
            fields=[("name",name),("arguments",args)]
        else:
            out+=" result_of="+value[0]
            if len(value)==3:out+=" native_is_error="+json.dumps(value[2])
            fields=[("output",value[1])]
        out+="\n"
        for name,v in fields:out+=name+" [str]\n"+fence+"\n"+v+"\n"+fence+"\n"
    return out+"precedes: "+" -> ".join(ids)+"\n"+tail
def render(g,*,renderer):
    return encode(renderer(g))
def compact(g,count,current=None):
    start=time.perf_counter()
    out,audit,base=_share(g,count,{})
    raw=base(out);short=encode(raw)
    if decode(short)!=raw:raise AssertionError("Lost visible graph information")
    chosen=partial(render,renderer=base) if count(short)<count(raw) else base
    return out,{"version":VERSION,"pruned":False,"lossless":True,
                "sharing":audit,"roundtrip_exact":True,"compact_applied":chosen is not base,
                "saved_vs_shared":count(raw)-count(chosen(out)),
                "editor_api_tokens":0,"editor_seconds":time.perf_counter()-start},chosen
