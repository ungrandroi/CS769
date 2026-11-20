"""Task-blind current-state contraction with reviewed read/write effects.
Candidates are bounded by unknown mutations; errors and read witnesses survive.
No future user turns, expected answers, task numbers, or evaluator input.
"""
from cs769.base.paths import project_root
from copy import deepcopy
from functools import partial
from pathlib import Path
import ast,json,time
from cs769.models.edits.record_edits import evidence, _digest
from cs769.models.edits.relation_pruning import records, fields
from cs769.models.edits.state_effects import StateAccumulator, vehicle_patch, DOORS
from cs769.models.edits.observation_state_components import apply, WRITES, READS
from cs769.models.edits import compact_graph
VERSION="g9-state-chain-v1"
def _methods(filename):
    p=project_root()/"vendor/gorilla/berkeley-function-call-leaderboard/bfcl_eval/eval_checker/multi_turn_eval/func_source_code"/filename
    return {f.name for c in ast.parse(p.read_text()).body if isinstance(c,ast.ClassDef)
            for f in c.body if isinstance(f,ast.FunctionDef) and not f.name.startswith("_")}
def _nodes(cs):return [n["id"] for c in cs for n in (c["call"],c["result"])]
def vehicle(calls):
    state=StateAccumulator();selected=[];ops=[];extras=[]
    owned=_methods("vehicle_control.py")
    read_only={"displayCarStatus","check_tire_pressure","find_nearest_tire_shop"}
    for c in calls:
        tool,args,value=c["tool"],c["args"],c["value"]
        if tool not in owned:continue
        # Unknown writes can invalidate earlier state; later reviewed chains remain eligible.
        if tool not in WRITES|read_only:
            state=StateAccumulator();selected=[];ops=[];extras=[];continue
        if tool in {"check_tire_pressure","find_nearest_tire_shop"}:continue
        if tool=="displayCarStatus" and isinstance(args,dict) and args.get("option") not in {"fuel","battery","engine","doors"}:continue
        patch=vehicle_patch(tool,args,value)
        if patch is None:
            # Official START errors do not mutate state. STOP errors can mutate it.
            if tool=="startEngine" and args=={"ignitionMode":"START"} and isinstance(value,dict) and value.get("error"):continue
            state=StateAccumulator();selected=[];ops=[];extras=[];continue
        if c["call"].get("native_is_error") or c["result"].get("native_is_error"):
            state=StateAccumulator();selected=[];ops=[];extras=[];continue
        values,aux=patch
        state.update("vehicle",values,c["result"]["id"])
        observed=state.observed("vehicle");doors=observed.get("doorStatus",{})
        if set(doors)==set(DOORS) and "remainingUnlockedDoors" in observed and sum(x=="unlocked" for x in doors.values())!=observed["remainingUnlockedDoors"]:
            return None
        selected.append(c)
        if tool in WRITES:ops.append(tool)
        if aux:extras.append({"operation":tool,"fields":aux})
    if len(selected)<2 or not ops:return None
    if any(a["result"]["ordinal"]>=b["call"]["ordinal"] for a,b in zip(selected,selected[1:])):return None
    component={"kind":"vehicle_state","observed":state.observed("vehicle"),"completed_operations":ops}
    # Preserve non-state outputs exactly, including references used by other tools.
    if extras:
        removed=set(_nodes(selected))
        retained=[c for c in calls if c.get("result") and c["result"]["id"] not in removed]
        def paths(value,path=()):
            yield path,value
            if isinstance(value,dict):
                for k,v in value.items():yield from paths(v,path+(k,))
            elif isinstance(value,list):
                for i,v in enumerate(value):yield from paths(v,path+(i,))
        unmatched=[];refs=[]
        for item in extras:
            for key,value in item["fields"].items():
                match=next(((c["result"]["id"],list(path)) for c in retained for path,v in paths(c["value"])
                            if type(v)==type(value) and v==value),None)
                if match:refs.append({"operation":item["operation"],"field":key,
                                      "value_ref":{"result":match[0],"path":match[1]}})
                else:unmatched.append({"operation":item["operation"],"field":key,"value":value})
        if unmatched:component["auxiliary"]=unmatched
        if refs:component["auxiliary_refs"]=refs
    return {"component":component,"removed":_nodes(selected),
            "relation":"reviewed object-scoped successful state writes and observations after last unknown mutation",
            "information":"latest state preserved; prior versions and successful call arguments retired; all errors and other reads retained",
            "state_dependencies":state.edges}
def files(calls):
    owned=_methods("gorilla_file_system.py")
    read_only={"ls","cat","head","tail","wc","grep","find","diff","pwd","du","sort"}
    objects={};epoch=0
    for c in calls:
        tool,args=c["tool"],c["args"]
        if tool=="cd":objects={};epoch+=1;continue
        if tool not in owned:continue
        if tool not in {"touch","echo"}:
            if tool not in read_only:objects={}
            continue
        if tool=="echo" and isinstance(args,dict) and args.get("file_name") is None:continue
        name=args.get("file_name") if isinstance(args,dict) else None
        output=fields(c["result"]).get("output") if c.get("result") else object()
        success=bool(c.get("result")) and not c["result"].get("native_is_error") and (output is None or isinstance(output,str) and output.strip() in ("None","null"))
        if not success or not isinstance(name,str) or not name or "/" in name or name in (".",".."):
            objects={};continue
        if tool=="touch":
            # Creation alone does not establish the prior content of an existing file.
            objects[name]={"creation":c,"writes":[]}
        else:
            if not isinstance(args.get("content"),str):objects={};continue
            objects.setdefault(name,{"creation":None,"writes":[]})["writes"].append(c)
    selected=[];states=[];edges=[]
    for name,obj in objects.items():
        chain=([obj["creation"]] if obj["creation"] else [])+obj["writes"]
        if len(chain)<2 or not obj["writes"]:continue
        if any(a["result"]["ordinal"]>=b["call"]["ordinal"] for a,b in zip(chain,chain[1:])):continue
        selected.extend(chain)
        states.append({"name":name,"content":obj["writes"][-1]["args"]["content"]})
        for a,b in zip(chain,chain[1:]):
            edges.append({"object":name,"scope":"cwd@"+str(epoch),"attribute":["content"],
                          "old":a["result"]["id"],"new":b["result"]["id"],"relation":"successful_content_write"})
    if not states:return None
    return {"component":{"kind":"file_states","frame":"cwd@"+str(epoch),"files":states},
            "removed":_nodes(selected),"relation":"same scoped file identity and successful content writes",
            "information":"latest contents retained; intermediate writes retired; read witnesses/errors and directory order retained in evidence",
            "state_dependencies":edges}
def _protected(g,action):
    # Cross-record ID links are evidence dependencies, never presumed dispensable.
    targets=set(action["removed"])
    def mentions(x):
        if isinstance(x,dict):
            return any((k in {"event_id","event","source_event","target_event","observed_at","from","to"} and isinstance(v,str) and v in targets) or mentions(v) for k,v in x.items())
        if isinstance(x,list):return any(map(mentions,x))
        return False
    return mentions(g.get("record_layer",{}))
def contract(g,count,current=None):
    start=time.perf_counter();before=_digest(g)
    baseline,ba,br=compact_graph.compact(g,count,current)
    _,calls=records(evidence(g));choices=[];considered=[]
    for kind,fn in [("vehicle",vehicle),("files",files)]:
        action=fn(calls)
        if action is None:considered.append({"kind":kind,"eligible":False,"reason":"no_reviewed_chain"});continue
        if _protected(g,action):considered.append({"kind":kind,"eligible":False,"reason":"cross_record_dependency"});continue
        out,audit,render=apply(g,action,count)
        renderer=partial(compact_graph.render,renderer=render)
        if compact_graph.decode(renderer(out))!=render(out):raise AssertionError("Edited rendering cannot round trip")
        saving=count(br(baseline))-count(renderer(out))
        considered.append({"kind":kind,"eligible":saving>0,"saving_vs_lossless":saving,"removed":action["removed"]})
        if saving>0:choices.append((saving,kind,out,audit,renderer))
    assert _digest(g)==before
    if not choices:
        return baseline,{"version":VERSION,"pruned":False,"lossless":True,"reason":"no_profitable_reviewed_chain",
                         "considered":considered,"editor_api_tokens":0,"editor_seconds":time.perf_counter()-start},br
    saving,kind,out,audit,renderer=max(choices,key=lambda x:(x[0],x[1]))
    return out,{"version":VERSION,"pruned":True,"kind":kind,"additional_saved_vs_shared":saving,"edit":audit,
                "considered":considered,"editor_api_tokens":0,"editor_seconds":time.perf_counter()-start,
                "task_preservation_certified":False},renderer
