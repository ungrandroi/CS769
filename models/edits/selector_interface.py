"""Optional lossless selector-packet interning and compact decisions.

This does not change graph candidates, guards, graph rendering or evaluation.
Default campaign requests are unchanged unless the interface is explicitly selected.
"""
from collections import Counter
from copy import deepcopy
import json

VERSION = "shared-packet-short-decision-v2"
NOTE = "The user JSON may contain shared_values and packet. In packet, an object with only $shared is a reference to the exact value in shared_values. Expand references when interpreting evidence; references do not imply semantic equivalence between different IDs."
def dumps(x):
    return json.dumps(x, ensure_ascii=False, separators=(",", ":"))
def restore(payload):
    def walk(x):
        if isinstance(x, dict):
            if set(x) == {"$shared"}:
                return deepcopy(payload["shared_values"][x["$shared"]])
            return {k: walk(v) for k, v in x.items()}
        if isinstance(x, list):
            return [walk(v) for v in x]
        return x
    return walk(payload["packet"])
def pack(packet, count):
    counts=Counter()
    collision=False
    def scan(x):
        nonlocal collision
        if isinstance(x, dict) and "$shared" in x: collision=True
        if isinstance(x,(dict,list,str)):
            key=dumps(x)
            if len(key)>120: counts[key]+=1
        if isinstance(x,dict):
            for v in x.values():scan(v)
        elif isinstance(x,list):
            for v in x:scan(v)
    scan(packet)
    if collision:
        return deepcopy(packet), False
    values={}; lookup={}
    def encode(x):
        key=dumps(x)
        if counts[key]>1 and len(key)>120:
            if key not in lookup:
                sid="s"+str(len(lookup));lookup[key]=sid;values[sid]=deepcopy(x)
            return {"$shared":lookup[key]}
        if isinstance(x,dict):return {k:encode(v) for k,v in x.items()}
        if isinstance(x,list):return [encode(v) for v in x]
        return x
    wrapped={"shared_values":values,"packet":encode(packet)}
    # encode populates values by reference.
    assert restore(wrapped)==packet
    if count(dumps(wrapped))+count(NOTE)<count(dumps(packet)):
        return wrapped, True
    return deepcopy(packet),False
def request(wire, packet, count):
    out=deepcopy(wire)
    prompt=out["messages"][0]["content"]
    start=prompt.index('{"drop":')
    end=prompt.index("Read only",start)
    prompt=prompt[:start]+'{"drop_ids":["candidate ID"],"reason":"One concise explanation of the graph relationships and retained evidence; group common reasons. All unlisted candidates are kept."}.\n'+prompt[end:]
    packed,shared=pack(packet,count)
    out["messages"][0]["content"]=prompt+("\n"+NOTE if shared else "")
    out["messages"][1]["content"]=dumps(packed)
    # Event IDs and payload member IDs coexist in the packet. Bind the output
    # to the actual candidate member IDs instead of trusting textual instructions.
    eligible=[x["id"] for x in packet["fields"] if x["eligible"]]
    out["messages"][0]["content"] += "\nOnly fields[].id values are legal deletion targets. Event IDs identify evidence and cannot be selected. Return an empty drop_ids list when no legal candidate can be deleted."
    item={"type":"string",**({"enum":eligible} if eligible else {})}
    out["response_format"]={"type":"json_schema","json_schema":{"name":"graph_member_selection","strict":True,
        "schema":{"type":"object","properties":{"drop_ids":{"type":"array","items":item},
        "reason":{"type":"string"}},"required":["drop_ids","reason"],"additionalProperties":False}}}
    return out
def normalize(answer):
    if not isinstance(answer,dict) or not isinstance(answer.get("drop_ids"),list) or not isinstance(answer.get("reason"),str):
        raise ValueError("Invalid compact selector response")
    ids=answer["drop_ids"]
    if any(not isinstance(x,str) for x in ids) or len(ids)!=len(set(ids)):
        raise ValueError("Invalid or duplicate compact selection")
    return {"drop":[{"id":i,"reason":answer["reason"]} for i in ids],"keep":[],"interface":VERSION}
