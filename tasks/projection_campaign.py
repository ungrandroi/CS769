"""Generic, configured four-arm field-projection study; uses the unified BFCL CLI."""
from cs769.base.io import read, write
from cs769.base.paths import project_root
from pathlib import Path
from copy import deepcopy
from datetime import datetime, timezone
from collections import Counter
import json,os,sys,subprocess,hashlib,random,fcntl
from cs769.base.config import ExperimentConfig, load_config
from cs769.base.io import counter
from cs769.tasks.prefix import digest
from cs769.base.provenance import package_hashes
from cs769.models.edits import dependency_projection as dp

ARMS=("identity","g9_full","g9_shared","g9_edited")
def call_signature(x):
    args=x["arguments"]
    if isinstance(args,str):
        try:args=json.loads(args)
        except ValueError:pass
    return x["name"],json.dumps(args,sort_keys=True,ensure_ascii=False)
def now():return datetime.now(timezone.utc).isoformat()
class Study:
    def __init__(self,root):
        self.d=Path(root);self.auth=read(self.d/"authorization.json")
        self.r=project_root();self.count=counter("o200k_base")
        self.selector_editor=self.auth.get("selector_editor","prune_dependency_fields")
        if self.selector_editor=="prune_dependency_fields":self.dp=dp
        elif self.selector_editor=="prune_dependency_slice":
            from cs769.models.edits import dependency_slice
            self.dp=dependency_slice
        else:raise ValueError("Unsupported selector editor")
        self.ledger=Path(self.auth.get("ledger_path",str(self.d/"budget.json"))).resolve()
    def state(self,status,**kw):write(self.d/"execution-state.json",dict(status=status,updated_at=now(),**kw))
    def check(self,paid=False):
        if (self.d/"STOP").exists():raise RuntimeError("STOP requested")
        if paid and datetime.now(timezone.utc)>=datetime.fromisoformat(self.auth["deadline_utc"]):raise RuntimeError("Grant deadline safety stop")
        freeze=self.d/"design/runtime-freeze.json"
        if freeze.exists() and read(freeze)!=package_hashes():raise RuntimeError("Runtime source changed after freeze")
    def cmd(self,args,log,paid=False,code=None):
        self.check(paid)
        env=dict(os.environ,CS769_OFFLINE="0" if paid else "1",PYTHONPATH=str(self.r/"src")+":"+str(self.r/"vendor/gorilla/berkeley-function-call-leaderboard"))
        cmd=[sys.executable,"-B","-c",code] if code else [sys.executable,"-B","-m","cs769",*map(str,args)]
        p=self.d/"logs"/log;p.parent.mkdir(exist_ok=True,parents=True)
        with p.open("w") as f:rc=subprocess.call(cmd,cwd=self.r,env=env,stdout=f,stderr=subprocess.STDOUT)
        if rc:raise RuntimeError("Check stopped; inspect "+str(p))
    def config(self,row,arm,decision=None):
        c=ExperimentConfig()
        c.name=arm;c.checkpoint={"kind":"completed_turn","turns":row["k"]}
        c.delivery={"mode":"replace","role":"assistant"};c.execution["max_requests"]=200
        if arm=="identity":c.memory={"kind":"identity","options":{}};c.delivery={"mode":"native"}
        if arm=="g9_shared":c.edits=[{"name":self.auth.get("shared_editor_name","share_structure"),"options":{},"on_ineligible":"skip"}]
        if arm=="g9_edited":
            name=self.auth.get("editor_name","prune_dependency_fields")
            opts={"decision":decision} if name==self.selector_editor else deepcopy(self.auth.get("editor_options",{}))
            c.edits=[{"name":name,"options":opts}]
        path=self.d/"configs"/row["task"]/(arm+".json");write(path,c.to_dict());return path
    def capture(self,row,arm):
        dest=self.d/"preflight"/row["task"]/(arm+".json")
        if dest.exists():return read(dest)
        cfg=self.d/"configs"/row["task"]/(arm+".json");src=self.d/"prefixes"/row["task"]
        code="from cs769.tasks.prefix import capture_checkpoint;from cs769.base.config import load_config;from pathlib import Path;import json;p=Path("+repr(str(dest))+");p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(capture_checkpoint(load_config(Path("+repr(str(cfg))+")),Path("+repr(str(src))+"),require_prefix_pass=False),ensure_ascii=False))"
        self.cmd([],row["task"]+"-"+arm+"-capture.log",code=code);return read(dest)
    def prepare(self,row,allow_paid_prefix=False,allow_failed_prefix=False):
        self.state("free_checks",current_task=row["task"])
        src=self.d/"prefixes"/row["task"]
        icfg=self.config(row,"identity")
        if not (src/"manifest.json").exists() and not row.get("source"):
            if not allow_paid_prefix:
                result={"task":row["task"],"prefix_passed":None,"status":"needs_prefix_generation","paid_requests":0}
                write(self.d/"preflight"/row["task"]/"status.json",result)
                return result
            self.cmd(["run","--config",icfg,"--task",row["task"],"--category",row["task"].rsplit("_",1)[0],
                      "--prefix-turns",row["k"],"--output",src,*self.paid_args()],row["task"]+"-new-prefix.log",paid=True)
        if not (src/"manifest.json").exists():
            self.cmd(["prefix-source","--config",icfg,"--api",row["source"],"--task",row["task"],"--category",row["task"].rsplit("_",1)[0],"--turns",row["k"],"--output",src],row["task"]+"-prefix.log")
        m=read(src/"manifest.json")
        if not (src/"boundary-request.json").exists():
            self.cmd(["boundary","--config",icfg,"--record",src,"--output",src/"boundary-request.json"],row["task"]+"-boundary.log")
        if not m["eligible"] and not allow_failed_prefix:
            write(self.d/"preflight"/row["task"]/"status.json",{"prefix_passed":False,"status":"prefix_failed","paid_requests":0})
            return {"task":row["task"],"prefix_passed":False,"status":"prefix_failed"}
        caps={}
        for arm in ARMS[:3]:
            self.config(row,arm);caps[arm]=self.capture(row,arm)
        full=caps["g9_full"];cur=read(src/"boundary-request.json")["input"][-1:]
        if self.auth.get("editor_name","prune_dependency_fields")!=self.selector_editor:
            self.config(row,"g9_edited");edited=self.capture(row,"g9_edited")
            audit=edited["prepared"]["edits"][0].get("audit",{})
            tools={digest(v["wire"].get("tools")) for v in [*caps.values(),edited]}
            assert len(tools)==1
            result={"task":row["task"],"k":row["k"],"prefix_passed":m["eligible"],"status":"ready",
                "candidates":audit.get("considered",[]),"proposed_pruned":audit.get("pruned",False),
                "editor_seconds":audit.get("editor_seconds"),"wire_tools_sha256":tools.pop(),"paid_requests":0}
            write(self.d/"preflight"/row["task"]/"status.json",result)
            return result
        packet=self.dp.packet(full["prepared"]["graph"],self.count,cur,full["wire"]["tools"])
        wire={"model":self.auth["model"],"messages":[{"role":"system","content":self.dp.SYSTEM_PROMPT},{"role":"user","content":json.dumps(packet,ensure_ascii=False,separators=(",",":"))}],
              "temperature":0,"seed":42,"max_tokens":2048,"response_format":{"type":"json_object"}}
        sd=self.d/"selectors"/row["task"]
        if self.auth.get("selector_gate"):
            from cs769.models.edits import selector_gate as sg, selector_interface as si
            if self.selector_editor!="prune_dependency_slice" or self.auth["selector_gate"]!=sg.VERSION or self.auth.get("selector_interface")!=si.VERSION:
                raise ValueError("Unsupported selector gate")
            packet,wire,gate=sg.prepare(full["prepared"]["graph"],self.count,cur,packet,wire)
            write(sd/"gate.json",gate)
        elif self.auth.get("selector_interface"):
            from cs769.models.edits import selector_interface as si
            if self.selector_editor!="prune_dependency_slice" or self.auth["selector_interface"]!=si.VERSION:
                raise ValueError("Unsupported selector interface")
            wire=si.request(wire,packet,self.count)
        write(sd/"packet.json",packet);write(sd/"request.json",wire)
        tools={digest(v["wire"].get("tools")) for v in caps.values()}
        assert len(tools)==1
        cand=[x for x in packet["fields"] if x["eligible"]]
        result={"task":row["task"],"k":row["k"],"prefix_passed":m["eligible"],"status":"ready","candidates":[{k:x[k] for k in ("id","event","key","tokens")} for x in cand],
                "selector_input_proxy":self.count(json.dumps(wire)),"wire_tools_sha256":tools.pop(),"paid_requests":0}
        write(self.d/"preflight"/row["task"]/"status.json",result)
        return result
    def budget(self,stage=None):
        from cs769.base.budget import PersistentBudget
        b=PersistentBudget(self.ledger,self.auth["operational_prestop_usd"],read(self.d/"rates.json"))
        if stage:
            with b.locked() as data:
                data["active_stage"]=self.auth.get("stage_budget_names",{}).get(stage,stage)
                data["stage_limits"]=self.auth["stage_caps_usd"]
                data["not_after_unix"]=datetime.fromisoformat(self.auth["deadline_utc"]).timestamp()
        return b
    def select(self,row):
        self.check(True)
        sd=self.d/"selectors"/row["task"]
        if (sd/"decision.json").exists():return read(sd/"decision.json")
        if self.auth.get("editor_name","prune_dependency_fields")!=self.selector_editor:
            cap=self.capture(row,"g9_edited");ident=self.capture(row,"identity")
            audit=cap["prepared"]["edits"][0].get("audit",{})
            delta=self.count(json.dumps(cap["wire"],ensure_ascii=False,sort_keys=True))-self.count(json.dumps(ident["wire"],ensure_ascii=False,sort_keys=True))
            decision={"editor":self.auth["editor_name"],"editor_options":self.auth.get("editor_options",{}),
                "editor_api_tokens":0,"proposed_wire_delta_vs_identity":delta,"applied":audit.get("pruned",False),
                "loss_witnesses":audit.get("loss_witnesses",[]),"reason":"deterministic_graph_contract"}
            if audit.get("pruned") and delta>=0 and self.auth.get("offline_identity_gate",True):
                rejected=self.d/"preflight"/row["task"]/"g9_proposed_rejected.json"
                (self.d/"preflight"/row["task"]/"g9_edited.json").rename(rejected)
                cfgpath=self.d/"configs"/row["task"]/"g9_edited.json";cfg=read(cfgpath)
                cfg["edits"]=[{"name":self.auth.get("shared_editor_name","share_structure"),"options":{},"on_ineligible":"skip"}];write(cfgpath,cfg)
                self.capture(row,"g9_edited")
                decision.update(applied=False,reason="no_net_input_saving_vs_identity",loss_witnesses=[])
            write(sd/"decision.json",decision);return decision
        packet=read(sd/"packet.json");eligible={x["id"] for x in packet["fields"] if x["eligible"]}
        raw=None
        if eligible:
            if self.count(json.dumps(read(sd/"request.json")))>16000:raise RuntimeError("Selector packet exceeds frozen size cap")
            if (sd/"response.json").exists():raw=read(sd/"response.json")
            else:
                if (sd/"http.jsonl").exists():raise RuntimeError("Prior selector attempt requires review; do not resend")
                from cs769.models.http import HTTPTransport
                def log(e):
                    with (sd/"http.jsonl").open("a") as f:f.write(json.dumps(e,ensure_ascii=False)+"\n")
                raw=HTTPTransport("openai",Path(self.auth["credentials_file"]),self.budget(),authorized=True,record=log).send(read(sd/"request.json"))
                write(sd/"response.json",raw)
            answer=json.loads(raw["choices"][0]["message"]["content"])
            if self.auth.get("selector_interface"):
                from cs769.models.edits.selector_interface import normalize
                answer=normalize(answer)
            ids=[x["id"] for x in answer["drop"]]
            if len(ids)!=len(set(ids)) or any(x not in eligible for x in ids):raise RuntimeError("Selector proposed invalid/protected fields")
        else:answer={"drop":[],"keep":[]};ids=[]
        ids=self.dp.bounded_selection(ids,packet["fields"],self.auth.get("max_drop_fields",1))
        decision={"version":self.dp.VERSION,"source_sha256":packet["source_sha256"],"current_sha256":packet["current_sha256"],"drop_member_ids":ids,
                  "reason":"selector_choice" if eligible else "no_eligible_fields","selector_response_sha256":digest(raw) if raw else None}
        write(sd/"selection.json",answer)
        self.config(row,"g9_edited",decision)
        cap=self.capture(row,"g9_edited")
        ident=read(self.d/"preflight"/row["task"]/"identity.json")
        # Same full wire serialization; fixed tools/settings included in both.
        delta=self.count(json.dumps(cap["wire"],ensure_ascii=False,sort_keys=True))-self.count(json.dumps(ident["wire"],ensure_ascii=False,sort_keys=True))
        if ids and delta>=0:
            decision["drop_member_ids"]=[];decision["reason"]="no_net_input_saving_vs_identity"
            (self.d/"preflight"/row["task"]/"g9_edited.json").rename(self.d/"preflight"/row["task"]/"g9_proposed_rejected.json")
            self.config(row,"g9_edited",decision);cap=self.capture(row,"g9_edited")
        if self.auth.get("selector_gate"):
            from cs769.models.edits import selector_gate as sg
            shared=read(self.d/"preflight"/row["task"]/"g9_shared.json")
            selected_check=sg.assess_selected(self.count,shared["prepared"]["memory_text"],cap["prepared"]["memory_text"],raw.get("usage",{}) if raw else {})
            selected_check["original_selected_members"]=list(decision["drop_member_ids"])
            write(sd/"selected-cost.json",selected_check)
            if decision["drop_member_ids"] and not selected_check["allowed"]:
                (self.d/"preflight"/row["task"]/"g9_edited.json").rename(self.d/"preflight"/row["task"]/"g9_rejected_by_selected_cost.json")
                decision["drop_member_ids"]=[];decision["reason"]="selected_edit_no_four_request_payback"
                self.config(row,"g9_edited",decision);cap=self.capture(row,"g9_edited")
            if not eligible:decision["reason"]=read(sd/"gate.json")["reason"]
        decision["proposed_wire_delta_vs_identity"]=delta
        write(sd/"decision.json",decision)
        return decision
    def paid_args(self):
        return ["--authorize-api","--budget-usd",self.auth["operational_prestop_usd"],"--credentials",self.auth["credentials_file"],"--rates",self.d/"rates.json","--ledger",self.ledger]
    def run(self,row,stage="development"):
        self.check(True);self.budget(stage)
        status_path=self.d/"preflight"/row["task"]/"status.json"
        status=read(status_path) if status_path.exists() else {"status":"needs_prefix_generation"}
        if status.get("status")=="needs_prefix_generation":status=self.prepare(row,allow_paid_prefix=True,allow_failed_prefix=stage!="development")
        if not status["prefix_passed"] and stage=="development":
            self.state("paused_prefix_review",task=row["task"],stage=stage)
            raise RuntimeError("Failed prefix retained; inspect common-outcome handling before continuing")
        self.state("selector_running",current_task=row["task"],stage=stage)
        decision=self.select(row)
        dest=self.d/"runs"/row["task"]
        if dest.exists():
            m=read(dest/"manifest.json")
            if m["status"]!="complete":raise RuntimeError("Prior run incomplete; inspect rather than repeat")
        else:
            hashes={};aliases={};tasks=[]
            for arm in ARMS:
                cap=self.capture(row,arm);key=digest(cap["wire"])
                if key in hashes:aliases[arm]=hashes[key];continue
                hashes[key]=arm
                tasks.append({"task":row["task"],"category":row["task"].rsplit("_",1)[0],"arm":arm,"repeat":1,
                              "config":str(self.d/"configs"/row["task"]/(arm+".json")),"source":str(self.d/"prefixes"/row["task"])})
            random.Random("projection-v1|"+row["task"]).shuffle(tasks)
            plan=self.d/"design"/(row["task"]+"-batch.json")
            write(plan,{"tasks":tasks,"gates":{}});write(self.d/"design"/(row["task"]+"-aliases.json"),aliases)
            self.state("continuations_running",current_task=row["task"],stage=stage)
            self.cmd(["batch","--plan",plan,"--config",self.d/"configs"/row["task"]/"identity.json","--output",dest,*self.paid_args(),"--workers",1],row["task"]+"-batch.log",paid=True)
        result=self.summarize_task(row)
        if any(x in ("g9_full","g9_shared") for x in result["new_regressions"]):
            self.state("paused_regression",task=row["task"],details=result["new_regressions"]);return False
        self.state("condition_complete",task=row["task"],stage=stage)
        return True
    def summarize_task(self,row):
        d=self.d;task=row["task"];batch=read(d/"runs"/task/"manifest.json");aliases=read(d/"design"/(task+"-aliases.json"))
        paths={r["arm"]:r["record"] for r in batch["results"] if "record" in r}
        for arm,alias in aliases.items():paths[arm]=paths[alias]
        selector=read(d/"selectors"/task/"response.json") if (d/"selectors"/task/"response.json").exists() else {}
        su=selector.get("usage",{});sel_tokens=su.get("prompt_tokens",0)+su.get("completion_tokens",0)
        rows=[]
        for arm in ARMS:
            p=Path(paths[arm]);m=read(p/"manifest.json");score=read(p/"score.json");u=m["usage_suffix"];all_u=m["usage_all"]
            tape=read(p/"api.json");suffix=tape[m["trigger_index"]:] if m.get("trigger_index") is not None else tape
            calls=[{"name":v.get("name"),"arguments":v.get("arguments"),"turn":a["turn"]} for a in suffix for v in a["response"]["output"] if v.get("type")=="function_call"]
            cap=read(d/"preflight"/task/(arm+".json"));prep=cap.get("prepared");ed=prep.get("edits",[]) if prep else []
            audit=ed[0].get("audit",{}) if ed else {}
            rows.append({"task":task,"k":row["k"],"prefix_passed":read(d/"prefixes"/task/"manifest.json")["eligible"],"arm":arm,"alias_of":aliases.get(arm),"record":str(p),"passed":score["passed"],
                         "pruned":audit.get("pruned",False),"loss_witnesses":audit.get("loss_witnesses",[]),"editor_seconds":audit.get("editor_seconds",0),"first_input_tokens":u["first_input_tokens"],"suffix_tokens":u["total_tokens"],
                         "whole_tokens":all_u["total_tokens"],"selector_tokens":sel_tokens if arm=="g9_edited" else 0,
                         "total_with_editing":all_u["total_tokens"]+(sel_tokens if arm=="g9_edited" else 0),
                         "suffix_with_editing":u["total_tokens"]+(sel_tokens if arm=="g9_edited" else 0),
                         "tools":u["tool_calls"],"whole_tools":all_u["tool_calls"],"calls":calls,
                         "input_tokens":u["input_tokens"],"output_tokens":u["output_tokens"],"cached_input_tokens":u["cached_input_tokens"]})
        by={r["arm"]:r for r in rows};loss=[a for a in ARMS[:-1] if by[a]["passed"] and not by["g9_edited"]["passed"]]
        for rr in rows:
            rr["added_tools"]={a:rr["tools"]-by[a]["tools"] for a in ARMS[:-1]}
            cc=Counter(call_signature(x) for x in rr["calls"])
            rr["new_call_occurrences"]={a:sum((cc-Counter(call_signature(x) for x in by[a]["calls"])).values()) for a in ARMS[:-1]}
        out={"task":task,"rows":rows,"new_regressions":loss,"selector_usage":su,"decision":read(d/"selectors"/task/"decision.json")}
        write(d/"reports"/(task+".json"),out);return out
def execute(root,mode,task=None,stage="development"):
    s=Study(root);lock=(s.d/"study.lock").open("a");fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    rows=read(s.d/("design/"+stage+".json"))
    if task:rows=[r for r in rows if r["task"]==task]
    if mode=="free":
        result=[]
        for r in rows:
            x=s.prepare(r,allow_failed_prefix=stage!="development");result.append(x);print(json.dumps(x),flush=True)
        write(s.d/("preflight/"+stage+"-summary.json"),result)
        s.state("free_checks_complete",conditions=len(result))
    elif mode=="run":
        for r in rows:
            if not s.run(r,stage):break
            print(json.dumps({"task":r["task"],"status":"condition_complete"}),flush=True)
    else:raise ValueError("Unknown mode")
if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser();p.add_argument("--root",required=True);p.add_argument("--mode",choices=("free","run"),required=True);p.add_argument("--task")
    p.add_argument("--stage",choices=("development","overall","long_history"),default="development")
    a=p.parse_args();execute(a.root,a.mode,a.task,a.stage)
