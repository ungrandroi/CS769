"""Optional 1/2/4-request admission gate for the existing dependency selector.
Only visible graph/current request are inputs. No future trace or score is read.
Sharing is the measured baseline, not a reason to exclude a candidate.
"""
from copy import deepcopy
import math,re,time
from cs769.models.edits import dependency_slice as ds, paired_graph, selector_interface as si
from cs769.models.graphs.graph_memory_evidence import _digest
VERSION="dependency-selector-horizon-v1"
HORIZONS=(1,2,4)
OUTPUT_CAP=256
def quoted_literals(current):
    text="\n".join(str(x.get("content","")) for x in current if x.get("role")=="user")
    groups=re.findall(r"(?<!\w)'([^'\n]{3,})'(?!\w)|\"([^\"\n]{3,})\"|\x60([^\x60\n]{3,})\x60",text)
    return sorted({next(v for v in row if v) for row in groups})
def contains(x,literal):
    if isinstance(x,str):return literal.casefold() in x.casefold()
    if isinstance(x,dict):return any(contains(k,literal) or contains(v,literal) for k,v in x.items())
    if isinstance(x,list):return any(contains(v,literal) for v in x)
    return False
def at(value,path):
    for key in path:value=value[key]
    return value
def economics(cost,saving):
    return {"cost_tokens":cost,"saved_per_request_estimate":saving,
        "estimated_break_even_requests":math.ceil(cost/saving) if saving>0 else None,
        "scenarios":[{"requests":h,"estimated_net_saved_tokens":h*saving-cost} for h in HORIZONS],
        "allowed":saving>0 and 4*saving>cost}
def protected_candidates(g,current,catalog):
    nodes={n["id"]:n for n in ds.evidence(g)["evidence_view"]["nodes"]}
    anchors=quoted_literals(current);keep=[];reject=[]
    for c in catalog["candidates"]:
        node=nodes[c["event"]];call=nodes[node["result_of"]]
        value=at(ds.load(ds.fields(node)["output"]),c["path"])
        args=ds.load(ds.fields(call).get("arguments"))
        hits=[x for x in anchors if contains(value,x) or contains(args,x)]
        if hits:reject.append({"member":c["id"],"result":node["id"],"call":call["id"],
            "relation":"result_of","literals":hits,"reason":"current_literal_evidence"})
        else:keep.append(c)
    return keep,reject
def prepare(g,count,current,packet,wire):
    start=time.perf_counter();before=_digest(g);packet=deepcopy(packet)
    cat=ds.catalog(g,count,current);candidates,protected=protected_candidates(g,current,cat)
    ids={c["id"] for c in candidates}
    packet["fields"]=[c for c in packet["fields"] if c["id"] in ids]
    wire=deepcopy(wire);wire["max_tokens"]=OUTPUT_CAP
    request=si.request(wire,packet,count)
    base,audit,renderer=paired_graph.compact(g,count,current);base_text=renderer(base)
    out={"version":VERSION,"source_sha256":before,"current_sha256":ds.dp.current_hash(current),
        "initial_candidates":len(cat["candidates"]),"eligible_candidates":len(candidates),
        "protected":protected,"shared_candidate_exclusion":False,
        "context_policy":"Existing packet preserved; no unproved omission of outside obligations",
        "future_trajectory_used":False,"max_output_tokens":OUTPUT_CAP,
        "baseline_memory_tokens":count(base_text),"allow_selector":False,"paid_requests":0}
    if not candidates:
        out.update(reason="no_unprotected_candidate",estimated_selector_input=0,estimated_selector_cost=0,probes=[])
    else:
        cost_in=sum(count(x["content"]) for x in request["messages"])+count(si.dumps(request["response_format"]))+64
        cost=cost_in+OUTPUT_CAP
        all_ids=ds.bounded_selection([c["id"] for c in candidates],candidates,16)
        # Singleton probes expose gains hidden by shared references. The capped
        # combined probe is optimistic; neither represents semantic approval.
        probes=[];sets=[[c["id"]] for c in candidates]+[all_ids];seen=set()
        for selected in sets:
            key=tuple(selected)
            if key in seen:continue
            seen.add(key)
            decision={"version":ds.VERSION,"source_sha256":before,"current_sha256":ds.dp.current_hash(current),
                      "drop_member_ids":selected}
            edited,ea,er=ds.prune(g,count,current,decision=decision)
            saving=max(0,count(base_text)-count(er(edited)))
            probes.append({"members":selected,"saving":saving,**economics(cost,saving)})
        best=max(probes,key=lambda x:x["saving"])
        out.update(estimated_selector_input=cost_in,estimated_selector_cost=cost,
            probes=probes,best_probe=best,allow_selector=best["allowed"],
            reason="potential_four_request_payback" if best["allowed"] else "no_probe_pays_back_within_four_requests",
            cost_is_estimate=True,probe_is_not_safety_certificate=True)
        if not out["allow_selector"]:
            packet["fields"]=[]
            request=si.request(wire,packet,count)
    assert _digest(g)==before
    out["free_seconds"]=time.perf_counter()-start
    return packet,request,out
def assess_selected(count,baseline_text,edited_text,selector_usage):
    cost=selector_usage.get("prompt_tokens",0)+selector_usage.get("completion_tokens",0)
    saving=max(0,count(baseline_text)-count(edited_text))
    return dict(economics(cost,saving),cost_uses_actual_usage=True,
        saving_is_memory_token_estimate=True,uses_actual_future_requests=False)
