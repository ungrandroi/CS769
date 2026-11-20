"""Contract homogeneous read groups and completed vehicle state chains.
Deterministic development editor. No future query, task ID, evaluator or network.
"""
from cs769.base.paths import project_root
import copy,json,time
from pathlib import Path
from functools import partial
from cs769.models.edits.record_edits import evidence, _refresh, _digest
from cs769.models.edits.relation_pruning import records
from cs769.models.edits.witness_pruning import _share
VERSION="g9-observation-state-components-dev3"
from cs769.models.edits.state_effects import StateAccumulator, vehicle_patch, DOORS
def pack_counts(g=None, *, calls=None):
 if calls is None:_,calls=records(evidence(g))
 groups=[];run=[]
 def valid(c):
  a=c['args'];v=c['value']
  return c['tool']=='wc' and isinstance(a,dict) and set(a)<={'file_name','mode'} and isinstance(a.get('file_name'),str) and '/' not in a['file_name'] and isinstance(v,dict) and set(v)=={'count','type'} and type(v['count'])is int and v['type']=={'l':'lines','w':'words','c':'characters'}.get(a.get('mode','l'))
 for i,c in enumerate(calls):
  if valid(c) and (not run or c['scope']==run[-1][1]['scope'] and c['args'].get('mode','l')==run[-1][1]['args'].get('mode','l')):run.append((i,c))
  else:
   if len(run)>=2:groups.append(run)
   run=[(i,c)] if valid(c) else []
 if len(run)>=2:groups.append(run)
 if not groups:return None
 run=max(groups,key=len);first=run[0][0];items=[x[1] for x in run]
 if any(a['result']['ordinal']>=b['result']['ordinal'] for a,b in zip(items,items[1:])):return None
 end=run[-1][0]+1
 if end<len(calls) and items[-1]['result']['ordinal']>=calls[end]['call']['ordinal']:return None
 names=[c['args']['file_name'] for c in items]
 ls=calls[first-1] if first else None
 use_ls=bool(ls and ls['tool']=='ls' and ls['scope']==items[0]['scope'] and isinstance(ls['value'],dict) and set(ls['value'])=={'current_directory_content'} and isinstance(ls['value']['current_directory_content'],list) and all(isinstance(x,str) for x in ls['value']['current_directory_content']) and len(set(ls['value']['current_directory_content']))==len(ls['value']['current_directory_content']) and all(x in ls['value']['current_directory_content'] for x in names))
 node={'kind':'file_count_group','frame':'cwd@'+str(items[0]['scope'][1]),'mode':items[0]['args'].get('mode','l'),'unit':items[0]['value']['type']}
 chosen=items.copy()
 if use_ls:
  listing=ls['value']['current_directory_content'];node.update(names=listing,list_options=ls['args'],rows=[[listing.index(c['args']['file_name']),c['value']['count']] for c in items],columns=['name_index_zero_based','count']);chosen.insert(0,ls)
 else:node.update(columns=['file','count'],rows=[[c['args']['file_name'],c['value']['count']] for c in items])
 removed=[v['id'] for c in chosen for v in [c['call'],c['result']]]
 return {'component':node,'removed':removed,'relation':'same-frame immutable listing and consecutive homogeneous file reads','information':'semantic observation grouping; all observed names, order, counts and units retained','read_count':len(items)}
STATE_FIELDS={'fuelLevel','batteryVoltage','engineState','brakePedalStatus','brakePedalForce','doorStatus','lockStatus','remainingUnlockedDoors'}
WRITES={'fillFuelTank','lockDoors','pressBrakePedal','startEngine'}
READS={'displayCarStatus','check_tire_pressure'}
def pack_state(g=None, *, calls=None):
 if calls is None:_,calls=records(evidence(g))
 last=next((i for i in range(len(calls)-1,-1,-1) if calls[i]['tool']=='startEngine' and calls[i]['args']=={'ignitionMode':'START'} and isinstance(calls[i]['value'],dict) and calls[i]['value'].get('engineState')=='running'),None)
 if last is None:return None
 selected=[];state=StateAccumulator();aux=[];ops=[];errors=[]
 for c in calls[:last+1]:
  t=c['tool'];a=c['args'];v=c['value']
  if t not in WRITES|READS:continue
  if not isinstance(v,dict) or not isinstance(a,dict):return None
  if v.get('error'):
   if t=='startEngine' and a.get('ignitionMode')=='START':errors.append(c['result']['id']);continue
   return None
  if t=='check_tire_pressure':continue
  if t=='displayCarStatus' and a.get('option') not in ['fuel','battery','engine','doors']:return None
  if t=='startEngine' and a.get('ignitionMode')!='START':return None
  patch=vehicle_patch(t,a,v)
  if patch is None:return None
  values,extras=patch
  state.update("vehicle",values,c['result']['id'])
  current_state=state.observed("vehicle")
  doors=current_state.get("doorStatus",{})
  if set(doors)==set(DOORS) and "remainingUnlockedDoors" in current_state and sum(x=="unlocked" for x in doors.values())!=current_state["remainingUnlockedDoors"]:return None
  if t in WRITES:ops.append(t)
  selected.append(c)
  aux.extend((t,k,val) for k,val in extras.items())
 if len(selected)<3 or len(set(ops))<2:return None
 # Reject unreviewed vehicle mutations in this span, even when error-shaped.
 reviewed=WRITES|READS
 import ast
 src=project_root()/'vendor/gorilla/berkeley-function-call-leaderboard/bfcl_eval/eval_checker/multi_turn_eval/func_source_code/vehicle_control.py'
 tree=ast.parse(src.read_text());known_vehicle={n.name for c in tree.body if isinstance(c,ast.ClassDef) for n in c.body if isinstance(n,ast.FunctionDef) and not n.name.startswith('_')}
 # Later reviewed reads do not change this materialized state; unknown mutations abort.
 if any(c['tool'] in known_vehicle-{'displayCarStatus','check_tire_pressure','find_nearest_tire_shop'} for c in calls[last+1:]):return None
 if any(c['tool'] in known_vehicle-reviewed for c in calls[:last+1]):return None
 removed=[v['id'] for c in selected for v in [c['call'],c['result']]]
 # Auxiliary values keep their field names. Shared values point to an actual retained result.
 retained=[c for c in calls if c['result'] and c['result']['id'] not in removed]
 def paths(v,path=()):
  yield path,v
  if isinstance(v,dict):
   for k,x in v.items():yield from paths(x,path+(k,))
  elif isinstance(v,list):
   for i,x in enumerate(v):yield from paths(x,path+(i,))
 unmatched=[];refs=[]
 for tool,key,val in aux:
  match=next(((c['result']['id'],list(path)) for c in retained for path,x in paths(c['value']) if type(x)==type(val) and x==val),None)
  if match:refs.append({'operation':tool,'field':key,'value_ref':{'result':match[0],'path':match[1]}})
  else:unmatched.append({'operation':tool,'field':key,'value':val})
 node={'kind':'vehicle_state','observed':state.observed('vehicle'),'completed_operations':ops}
 if unmatched:node['auxiliary']=unmatched
 if refs:node['auxiliary_refs']=refs
 return {'component':node,'removed':removed,'relation':'same vehicle read/write succession, terminal successful START, all errors retained','information':'past state versions and successful operation arguments retired; may still be repeated in preserved assistant text','errors_retained':errors,'state_dependencies':state.edges}

def pack_files(g=None, *, calls=None):
    """Materialize created file contents in one unbroken symbolic cwd frame.
    All read records remain. Unknown filesystem mutations or cwd changes are
    barriers; no task IDs, future queries, inferred absolute paths or file order.
    """
    if calls is None:
        _, calls = records(evidence(g))
    import ast
    source = project_root() / "vendor/gorilla/berkeley-function-call-leaderboard/bfcl_eval/eval_checker/multi_turn_eval/func_source_code/gorilla_file_system.py"
    tree = ast.parse(source.read_text())
    owned = {f.name for c in tree.body if isinstance(c, ast.ClassDef)
             for f in c.body if isinstance(f, ast.FunctionDef) and not f.name.startswith("_")}
    readonly = {"ls","cat","head","tail","wc","grep","find","diff","pwd","du","sort"}
    objects = {};epoch = 0
    def void_success(c):
        # Missing/malformed output is not a successful void return. BFCL archives Python None as text.
        from cs769.models.edits.relation_pruning import fields
        result = c.get("result")
        if not result or result.get("native_is_error"):return False
        output = fields(result).get("output", "__missing__")
        return output is None or isinstance(output,str) and output.strip() in ("null","None")
    def local_name(name):
        return isinstance(name,str) and bool(name) and "/" not in name and name not in (".","..")
    for c in calls:
        tool,args,value = c["tool"],c["args"],c["value"]
        if tool == "cd":
            objects={};epoch+=1;continue
        if tool == "touch":
            name=args.get("file_name") if isinstance(args,dict) else None
            if not local_name(name) or not void_success(c):
                objects={};continue
            objects[name]={"creation":c,"writes":[]}
        elif tool == "echo":
            if not isinstance(args,dict):objects={};continue
            name=args.get("file_name")
            if name is None:continue  # terminal output only, retained
            if not local_name(name) or not void_success(c) or not isinstance(args.get("content"),str):
                objects={};continue
            if name in objects:objects[name]["writes"].append(c)
        elif tool in owned and tool not in readonly:
            objects={}
    selected=[];files=[];edges=[]
    for name,obj in objects.items():
        if not obj["writes"]:continue
        creation=obj["creation"];writes=obj["writes"]
        # Results must confirm creation before writes; independent creates may be batched.
        if creation["result"]["ordinal"]>=writes[0]["call"]["ordinal"]:continue
        if any(a["result"]["ordinal"]>=b["call"]["ordinal"] for a,b in zip(writes,writes[1:])):continue
        selected.extend([creation,*writes])
        files.append({"name":name,"content":writes[-1]["args"]["content"]})
        for a,b in zip([creation,*writes],writes):
            edges.append({"object":name,"scope":"cwd@"+str(epoch),"attribute":["content"],"old":a["result"]["id"],"new":b["result"]["id"],"relation":"successful_content_write"})
    if not files:return None
    removed=[n["id"] for c in selected for n in [c["call"],c["result"]]]
    return {"component":{"kind":"created_file_states","frame":"cwd@"+str(epoch),
                         "files_in_creation_order":files},
            "removed":removed,"relation":"same scoped file identity: successful create and content writes",
            "information":"final content and creation order retained; intermediate writes retired; reads/errors retained",
            "state_dependencies":edges}

def _render(g,*,renderer):
    base=copy.deepcopy(g);node=base.pop("observation_state_component")
    return renderer(base)+"\nSTATE_COMPONENT "+json.dumps(node,ensure_ascii=False,separators=(",",":"))

def apply(g,action,count):
    original=_digest(g);old=evidence(g);ev=copy.deepcopy(old);removed=set(action["removed"])
    ev["evidence_view"]["nodes"]=[n for n in ev["evidence_view"]["nodes"] if n["id"] not in removed]
    out,mapping=_refresh(ev)
    src={n["id"]:n for n in old["evidence_view"]["nodes"] if n["category"]!="episode"}
    dst={n["id"]:n for n in evidence(out)["evidence_view"]["nodes"] if n["category"]!="episode"}
    assert set(mapping)==set(src)-removed
    for a,b in mapping.items():
        want=copy.deepcopy(src[a]);want.update(id=b,ordinal=dst[b]["ordinal"])
        if "result_of" in want:want["result_of"]=mapping[want["result_of"]]
        assert want==dst[b],"Retained evidence changed"
    shared,audit,renderer=_share(out,count,{})
    node=copy.deepcopy(action["component"])
    for ref in node.get("auxiliary_refs",[]):ref["value_ref"]["result"]=mapping[ref["value_ref"]["result"]]
    if action.get("errors_retained"):node["resolved_error_refs"]=[mapping[x] for x in action["errors_retained"]]
    shared["observation_state_component"]=node
    assert _digest(g)==original
    return shared,{"removed_events":sorted(removed),"old_to_new":mapping,"retained_evidence_exact":True,
                  "information":action["information"],"relation":action["relation"],"sharing":audit,
                  "state_dependencies":action.get("state_dependencies",[])},partial(_render,renderer=renderer)

def contract(g,count,current,*,kind,minimum_saving=1):
    start=time.perf_counter()
    if kind not in ("counts","state","files") or type(minimum_saving)is not int or minimum_saving<1:raise ValueError("Invalid component options")
    base,ba,br=_share(g,count,{})
    action={"counts":pack_counts,"state":pack_state,"files":pack_files}[kind](g)
    if action is None:return base,{"version":VERSION,"pruned":False,"reason":"no_component","editor_api_tokens":0},br
    out,audit,renderer=apply(g,action,count);saving=count(br(base))-count(renderer(out))
    if saving<minimum_saving:return base,{"version":VERSION,"pruned":False,"reason":"no_saving_vs_shared","editor_api_tokens":0},br
    return out,{"version":VERSION,"pruned":True,"kind":kind,"additional_saved_vs_shared":saving,
                "edit":audit,"editor_api_tokens":0,"editor_seconds":time.perf_counter()-start,
                "task_preservation_certified":False},renderer
