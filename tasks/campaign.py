"""Data-driven prefix selection and gated three-arm campaigns using the unified CLI."""
from cs769.base.io import read, write
from cs769.base.paths import project_root
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import os,sys,json,subprocess,random,fcntl
from cs769.base.provenance import package_hashes, source_identity
from cs769.base.metrics import paired, Usage, cost_from_usage

def now():return datetime.now(timezone.utc).isoformat()

def unreviewed_regressions(losses,reviews):
    """Gate on new losses while retaining every primary loss in the report."""
    acknowledged=set()
    for review in reviews:
        if review.get("decision")!="continue" or review.get("baseline") not in ("identity","g9_full") or not review.get("task"):
            raise ValueError("A continuation review must identify a task, baseline and explicit continue decision")
        acknowledged.add((review["task"],review["baseline"]))
    return [loss for loss in losses if (loss["task"],loss["baseline"]) not in acknowledged]

class Campaign:
    def __init__(self,root):
        self.root=Path(root);self.auth=read(self.root/"authorization.json")
        self.repo=project_root()
        self.choices=read(self.root/"source-choice.json")
        self.cfg=self.root/"configs";self.frozen=self.root/"runtime-freeze.json"
        self.paid=False
        data=self.repo/"vendor/gorilla/berkeley-function-call-leaderboard/bfcl_eval/data/BFCL_v4_multi_turn_long_context.json"
        self.turn_counts={x["id"]:len(x["question"])for x in (json.loads(line)for line in data.read_text().splitlines()if line.strip())}
    def state(self,status,**extra):
        write(self.root/"execution-state.json",{"status":status,"updated_at":now(),**extra})
    def call(self,args,name,paid=False):
        if self.frozen.exists() and package_hashes()!=read(self.frozen)["package_sha256"]:
            raise RuntimeError("Canonical source changed after freeze")
        log=self.root/"logs"/name;log.parent.mkdir(parents=True,exist_ok=True)
        env=dict(os.environ,CS769_OFFLINE="0"if paid else"1",PYTHONDONTWRITEBYTECODE="1")
        with log.open("w")as f:
            proc=subprocess.run([sys.executable,"-B","-m","cs769",*map(str,args)],cwd=self.repo,env=env,stdout=f,stderr=subprocess.STDOUT)
        if proc.returncode:raise RuntimeError("Command stopped; inspect "+str(log))
    def paid_options(self):
        return ["--authorize-api","--budget-usd",self.auth["operational_prestop_usd"],
                "--credentials",self.auth["credentials_file"],"--rates",self.root/"rates.json","--ledger",self.root/"budget.json"]
    def task_config(self,task,arm,turns):
        p=self.root/"task-configs"/task/(arm+".json")
        if not p.exists():
            d=read(self.cfg/(arm+".json"));d["checkpoint"]={"kind":"completed_turn","turns":turns};write(p,d)
        return p
    def qualify(self,task,paid=False):
        case=self.root/"screening"/(task+".json")
        if case.exists():
            previous=read(case)
            if previous["status"]in("selected","excluded"):return previous
        prior=None;checks=[]
        for turns in range(1,4):
            if turns>=self.turn_counts[task]:
                result={"task":task,"status":"excluded","reason":"no_remaining_turn_before_eligible_edit","checks":checks}
                write(case,result);return result
            folder=self.root/"prefixes"/task/str(turns)
            if not(folder/"manifest.json").exists():
                old=self.choices.get(task)
                if old:
                    tape=read(old)
                    max_users=max(sum(m.get("role")=="user"for m in x["request"]["input"])for x in tape)
                    if max_users>=turns:
                        self.call(["prefix-source","--config",self.cfg/"prefix_identity.json","--api",old,"--task",task,
                                   "--category","multi_turn_long_context","--turns",turns,"--output",folder],
                                  task+"-prefix-replay-"+str(turns)+".log")
                if not(folder/"manifest.json").exists():
                    if not paid:
                        result={"task":task,"status":"needs_prefix","next_turn":turns,"checks":checks};write(case,result);return result
                    self.state("collecting_prefix",task=task,turns=turns)
                    args=["run","--config",self.cfg/"prefix_identity.json","--task",task,"--category","multi_turn_long_context",
                          "--prefix-turns",turns,"--output",folder,"--arm","prefix",*self.paid_options()]
                    if prior:args+=["--source",prior]
                    self.call(args,task+"-prefix-live-"+str(turns)+".log",paid=True)
            m=read(folder/"manifest.json")
            if m["status"]!="complete":raise RuntimeError("Incomplete prefix; do not restart "+str(folder))
            if not m["eligible"]:
                result={"task":task,"status":"excluded","reason":"official_prefix_failed","turns":turns,"checks":checks,"source":str(folder)}
                write(case,result);return result
            if not(folder/"boundary-request.json").exists():
                self.call(["boundary","--config",self.cfg/"prefix_identity.json","--record",folder,
                           "--output",folder/"boundary-request.json"],task+"-boundary-"+str(turns)+".log")
            inspect=folder/"eligibility.json"
            if not inspect.exists():
                config=self.task_config(task,self.auth.get("candidate_arm","merge_series"),turns)
                self.call(["inspect-prefix","--config",config,"--record",folder,"--output",inspect],
                          task+"-inspect-"+str(turns)+".log")
            q=read(inspect);checks.append(q)
            if q["eligible"]:
                for arm in self.auth["arms"]:self.task_config(task,arm,turns)
                result={"task":task,"status":"selected","turns":turns,"source":str(folder),"checks":checks}
                write(case,result);return result
            prior=folder
        result={"task":task,"status":"excluded","reason":"no_eligible_edit_in_first_three_completed_turns","checks":checks}
        write(case,result);return result
    def free(self):
        tasks=[t for ts in self.auth["candidate_pools"].values()for t in ts]
        self.state("free_screening",candidates=len(tasks),paid_requests=0)
        with ThreadPoolExecutor(max_workers=4)as pool:results=list(pool.map(self.qualify,tasks))
        out={d:{status:sum(r["task"]in ts and r["status"]==status for r in results)
                for status in("selected","excluded","needs_prefix")}for d,ts in self.auth["candidate_pools"].items()}
        write(self.root/"free-screening.json",{"completed_at":now(),"counts":out,"results":results,"paid_requests":0})
        self.state("free_screening_complete",counts=out,paid_requests=0)
        return out
    def run(self,max_rounds=None):
        if not read(self.root/"preflight/release.json")["passed"]:raise RuntimeError("Free preflight not released")
        if not(self.root/"free-screening.json").exists():raise RuntimeError("Free screening required")
        if not self.frozen.exists():raise RuntimeError("Freeze canonical package before paid campaign")
        previous=read(self.root/"execution-state.json")
        if previous["status"].startswith(("paused","complete")):raise RuntimeError("Campaign already stopped; explicit review required")
        selected={d:[]for d in self.auth["candidate_pools"]};target=self.auth["target_per_domain"]
        for round_index in range(target):
            current=[]
            for domain,tasks in self.auth["candidate_pools"].items():
                picked=[]
                for task in tasks:
                    q=self.qualify(task,paid=True)
                    if q["status"]=="selected":
                        picked.append(q)
                        if len(picked)==round_index+1:break
                selected[domain]=picked
                if len(picked)>round_index:current.append((domain,picked[round_index]))
            write(self.root/"selection.json",selected)
            if not current:break
            jobs=[(domain,q,arm)for domain,q in current for arm in self.auth["arms"]]
            random.Random(self.auth["candidate_order_seed"]+round_index).shuffle(jobs)
            for domain,q,arm in jobs:
                task=q["task"];out=self.root/"runs"/task/arm
                if (out/"manifest.json").exists():
                    if read(out/"manifest.json")["status"]!="complete":raise RuntimeError("Attempt incomplete; no automatic rerun: "+str(out))
                    continue
                self.state("smoke"if round_index==0 else"main",round_index=round_index+1,domain=domain,task=task,arm=arm)
                self.call(["run","--config",self.task_config(task,arm,q["turns"]),"--task",task,"--category","multi_turn_long_context",
                           "--source",q["source"],"--output",out,"--arm",arm,*self.paid_options()],task+"-"+arm+".log",paid=True)
                manifest=read(out/"manifest.json")
                tape=read(out/"api.json")
                models={r.get("raw_response",r["response"]).get("model")for r in tape if r.get("source")=="live"}
                if models!={self.auth["model_snapshot"]}:raise RuntimeError("Unexpected served snapshot: "+str(models))
                interim=self.report()
                pending=unreviewed_regressions(interim["new_losses"],self.auth.get("reviewed_regressions",[]))
                if pending:
                    self.state("paused_new_regression",cases=pending,report=str(self.root/"reports/summary.json"))
                    return interim
            report=self.report()
            pending_losses=unreviewed_regressions(report["new_losses"],self.auth.get("reviewed_regressions",[]))
            if pending_losses:
                self.state("paused_new_regression",cases=pending_losses,report=str(self.root/"reports/summary.json"));return report
            if round_index==0:
                passing=sum(read(self.root/"runs"/q["task"]/"g9_full/score.json")["passed"]for _,q in current)
                if passing==0:
                    self.state("paused_smoke_controls_failed");return report
                write(self.root/"smoke-release.json",{"passed":True,"conditions":[q["task"]for _,q in current],"time":now()})
            if max_rounds and round_index+1>=max_rounds:
                self.state("smoke_complete"if round_index==0 else"batch_ready",completed_rounds=round_index+1);return report
        result=self.report();self.state("complete",completed_conditions=result["complete_triples"],paid_usd=result["budget"]["settled_usd"]);return result
    def report(self):
        rows=[];triples=[];losses=[];gains=[]
        rates=read(self.root/"rates.json")
        for domain,tasks in self.auth["candidate_pools"].items():
            for task in tasks:
                group={}
                for arm in self.auth["arms"]:
                    path=self.root/"runs"/task/arm
                    if not(path/"manifest.json").exists():continue
                    m=read(path/"manifest.json")
                    if m["status"]!="complete":continue
                    score=read(path/"score.json");usage=m["usage_live"]
                    row={"task":task,"domain":domain,"arm":arm,"repeat":1,"checkpoint_sha256":m["checkpoint_sha256"],
                         "passed":score["passed"],"usage":usage,"path":str(path)}
                    u=dict(usage);u.pop("total_tokens",None);row["cost_usd"]=cost_from_usage(Usage(**u),rates)
                    rows.append(row);group[arm]=row
                if group:
                    assert len({x["checkpoint_sha256"]for x in group.values()})==1
                if len(group)==3:
                    triples.append({"task":task,"domain":domain,"arms":group})
                candidate=group.get(self.auth.get("candidate_arm","merge_series"))
                if candidate is not None:
                    for baseline in["identity","g9_full"]:
                        if baseline not in group:continue
                        if group[baseline]["passed"]and not candidate["passed"]:losses.append({"task":task,"baseline":baseline})
                        if not group[baseline]["passed"]and candidate["passed"]:gains.append({"task":task,"baseline":baseline})
        groups={}
        for domain in [*self.auth["candidate_pools"],"all"]:
            subset=[r for r in rows if domain=="all"or r["domain"]==domain]
            groups[domain]={b:paired(subset,b,self.auth.get("candidate_arm","merge_series"))for b in["identity","g9_full"]}
        ledger=read(self.root/"budget.json")if(self.root/"budget.json").exists()else{"requests":{}}
        requests=list(ledger["requests"].values())
        budget={"settled_usd":sum(r.get("actual_usd",0)for r in requests),
                "uncertain_reserved_usd":sum(r["reserved_usd"]for r in requests if r["status"]=="uncertain"),
                "inflight_reserved_usd":sum(r["reserved_usd"]for r in requests if r["status"]=="reserved"),
                "requests":len(requests),"hard_cap_usd":self.auth["hard_cap_usd"],
                "prestop_usd":self.auth["operational_prestop_usd"]}
        result={"generated_at":now(),"complete_triples":len(triples),"rows":rows,"triples":triples,"groups":groups,
                "new_losses":losses,"gains":gains,"budget":budget,"new_primary_continuation_usd":sum(r["cost_usd"]for r in rows),
                "official_eval_unchanged":True,"first_attempts_preserved":True}
        write(self.root/"reports/summary.json",result);return result

def execute(root,mode,max_rounds=None):
    campaign=Campaign(root);lock=campaign.root/"controller.lock"
    with lock.open("a")as f:
        fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:
            if mode=="free":return campaign.free()
            if mode=="run":return campaign.run(max_rounds)
            return campaign.report()
        except BaseException as error:
            campaign.state("paused_error",error=type(error).__name__+": "+str(error))
            raise

