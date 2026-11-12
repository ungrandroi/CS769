"""One parser and one public command path for memory preparation and BFCL runs."""
import argparse,json,sys,hashlib,os
from contextlib import redirect_stdout
from pathlib import Path
from copy import deepcopy
from .config import load_config,ExperimentConfig
from .pipeline import prepare
from .registry import BUILDERS,EDITORS

def read(p):return json.loads(Path(p).read_text())
def write_new(p,v):
    with Path(p).open("x") as f:json.dump(v,f,ensure_ascii=False,indent=2);f.write("\n")
def counter(name):
    if name=="characters":return len
    import tiktoken
    e=tiktoken.get_encoding(name)
    return lambda s:len(e.encode(s,disallowed_special=()))

def build_parser():
    p=argparse.ArgumentParser(description="CS769: one configurable graph-memory entry point")
    commands=p.add_subparsers(dest="command",required=True)
    commands.add_parser("list",help="list builders, edits and profiles")
    x=commands.add_parser("validate");x.add_argument("config",type=Path)
    x=commands.add_parser("prepare",help="offline graph/edit/request preparation")
    x.add_argument("--config",required=True,type=Path);x.add_argument("--history",required=True,type=Path)
    for n in ("native-history","context","next-messages"):x.add_argument("--"+n,type=Path)
    x.add_argument("--counter",choices=("characters","o200k_base"),default="o200k_base")
    x.add_argument("--output",required=True,type=Path)
    x=commands.add_parser("replay",help="strict free replay through official BFCL tools")
    x.add_argument("--config",required=True,type=Path);x.add_argument("--record",required=True,type=Path)
    x.add_argument("--source",type=Path);x.add_argument("--output",type=Path)
    x=commands.add_parser("score",help="read-only official scoring of a saved result")
    x.add_argument("--record",required=True,type=Path);x.add_argument("--output",type=Path)
    x=commands.add_parser("report",help="summarize paired rows without calling models")
    group=x.add_mutually_exclusive_group(required=True);group.add_argument("--rows",type=Path);group.add_argument("--batch",type=Path)
    x.add_argument("--baseline",default="identity");x.add_argument("--candidate",default="g9");x.add_argument("--output",type=Path)
    x=commands.add_parser("run",help="new run; network requires separate explicit API authorization")
    x.add_argument("--config",required=True,type=Path);x.add_argument("--task",required=True);x.add_argument("--category",required=True)
    x.add_argument("--source",type=Path);x.add_argument("--output",required=True,type=Path);x.add_argument("--repeat",type=int,default=1);x.add_argument("--arm")
    x.add_argument("--authorize-api",action="store_true");x.add_argument("--budget-usd",type=float,default=0)
    x.add_argument("--credentials",type=Path);x.add_argument("--rates",type=Path);x.add_argument("--ledger",type=Path)
    x=commands.add_parser("batch",help="isolated task workers; one shared experiment ledger")
    x.add_argument("--plan",required=True,type=Path);x.add_argument("--config",required=True,type=Path);x.add_argument("--output",required=True,type=Path)
    x.add_argument("--replay",action="store_true");x.add_argument("--authorize-api",action="store_true")
    x.add_argument("--budget-usd",type=float,default=0);x.add_argument("--credentials",type=Path);x.add_argument("--rates",type=Path);x.add_argument("--workers",type=int,default=1)
    return p

def replay_record(record,config,source=None):
    from .adapters.bfcl import BFCLRunner,official_score
    from .adapters.replay import ReplayTransport
    record=Path(record);m=read(record/"manifest.json")
    task=m.get("task_id",m.get("task"));category=m["category"]
    src=source or m.get("identity")
    source_tape=read(Path(src)/"api.json") if src else None
    tape=read(record/"api.json");transport=ReplayTransport(tape)
    frozen=m.get("sampling")
    if frozen is not None and config.model["sampling"]!=frozen:raise ValueError("Configured sampling differs from frozen record")
    if m.get("model") and m["model"]!=config.model["name"]:raise ValueError("Configured model differs from frozen record")
    d=config.to_dict();d["execution"]["max_requests"]=max(d["execution"]["max_requests"],len(tape));config=ExperimentConfig.from_dict(d)
    got=BFCLRunner(config,counter("o200k_base")).run(task,category,transport,
           trigger_index=m.get("trigger_index"),source_tape=source_tape)
    expected=read(record/"full.json")["result"]
    if got["result"]!=expected:raise AssertionError("Official tool-call result differs from archive")
    if got["prepared"] and (record/"memory.txt").is_file():
        if got["prepared"]["memory_text"]!=(record/"memory.txt").read_text():raise AssertionError("Memory text changed")
    score=official_score(task,category,got["result"])
    if (record/"score.json").is_file() and score["passed"]!=read(record/"score.json")["passed"]:
        raise AssertionError("Official binary score changed")
    return {"task":task,"category":category,"requests_checked":transport.index,
            "tool_calls":got["tool_calls"],"passed":score["passed"],
            "exact_requests":True,"exact_result":True,"paid_requests":0,"usage_reference":got["usage_suffix"]}

def main(argv=None):
    a=build_parser().parse_args(argv)
    if a.command=="list":
        result={"builders":sorted(BUILDERS),"edits":sorted(EDITORS),"profiles":[p.stem for p in sorted((Path(__file__).parent/"configs").glob("*.json")) if not p.name.startswith("_")]}
    elif a.command=="validate":result=load_config(a.config).to_dict()
    elif a.command=="prepare":
        if a.output.exists():raise FileExistsError("Output exists")
        cfg=load_config(a.config)
        if cfg.memory.get("options",{}).get("semantics")=="mixed":
            from .bootstrap import ensure_bfcl
            ensure_bfcl()
        rd=lambda p:read(p) if p else None
        result=prepare(rd(a.history),cfg,counter(a.counter),native_history=rd(a.native_history),native_context=rd(a.context),
                       next_messages=rd(a.next_messages),counter_name=a.counter)
        a.output.mkdir(parents=True)
        for n,v in (("result",result),("config",cfg.to_dict()),("messages",result["messages"]),("graph",result["graph"])):
            write_new(a.output/(n+".json"),v)
        (a.output/"memory.txt").write_text(result["memory_text"])
        result={"output":str(a.output),"eligible":result["eligible"],"metrics":result["metrics"]}
    elif a.command=="replay":
        with redirect_stdout(sys.stderr):result=replay_record(a.record,load_config(a.config),a.source)
    elif a.command=="batch":
        from .batch import execute_batch
        result=execute_batch(a)
    elif a.command=="score":
        from .adapters.bfcl import official_score
        m=read(a.record/"manifest.json");result=official_score(m.get("task_id",m.get("task")),m["category"],read(a.record/"full.json")["result"])
    elif a.command=="report":
        from .reporting import from_rows,from_batch
        result=from_batch(a.batch,a.baseline,a.candidate) if a.batch else from_rows(read(a.rows),a.baseline,a.candidate)
    else:
        if not a.authorize_api or a.budget_usd<=0 or not a.credentials or not a.rates or os.environ.get("CS769_OFFLINE")=="1":
            raise PermissionError("Paid run requires explicit API authorization, positive new budget, credentials and rates; offline mode forbids it")
        from .adapters.bfcl import BFCLRunner,official_score
        from .adapters.http import HTTPTransport
        from .adapters.provider import ProviderTransport
        from .adapters.budget import PersistentBudget
        from .adapters.replay import ReplayTransport
        if a.output.exists():raise FileExistsError("Refusing to overwrite an attempt")
        cfg_dict=load_config(a.config).to_dict();cfg_dict["execution"]["budget_usd"]=a.budget_usd
        cfg=ExperimentConfig.from_dict(cfg_dict)
        if a.repeat<1:raise ValueError("Repeat index must be positive")
        if cfg.model["provider"]=="anthropic" and cfg.delivery["mode"]=="replace" and cfg.model.get("old_thinking")=="preserve":
            raise ValueError("Signed thinking cannot be preserved across a changed history; choose omit")
        maximum=cfg.model["sampling"].get("max_tokens",cfg.model["sampling"].get("max_completion_tokens",0))
        if type(maximum)is not int or maximum<=0:raise ValueError("A paid profile must set its maximum output tokens")
        source=read(a.source/"api.json") if a.source else None
        sm=read(a.source/"manifest.json") if a.source else {}
        if a.source:
            if sm.get("status")!="complete":raise ValueError("Source attempt is not complete")
            if sm.get("task_id",sm.get("task"))!=a.task or sm["category"]!=a.category:raise ValueError("Source task/category mismatch")
            if sm.get("model") and sm["model"]!=cfg.model["name"]:raise ValueError("Source model differs")
            if sm.get("sampling") and sm["sampling"]!=cfg.model["sampling"]:raise ValueError("Source sampling differs")
            if cfg.selection.get("require_prefix_pass") and sm.get("eligible")is not True:raise ValueError("Official prefix eligibility is required")
            if cfg.delivery["mode"]!="native" and sm.get("trigger_index")is None:raise ValueError("Source did not reach the configured checkpoint")
        a.output.mkdir(parents=True)
        budget=PersistentBudget(a.ledger or a.output/"budget.json",a.budget_usd,read(a.rates))
        def record_http(event):
            with (a.output/"http.jsonl").open("a")as f:f.write(json.dumps(event,ensure_ascii=False)+"\n")
        live=ProviderTransport(cfg,HTTPTransport(cfg.model["provider"],a.credentials,budget,authorized=True,record=record_http))
        boundary=sm.get("trigger_index")
        class Transport:
            def __init__(self):self.index=0
            def send(self,req):
                i=self.index;self.index+=1
                if source is not None and boundary is not None and i<boundary:
                    if req!=source[i]["request"]:raise AssertionError("Prefix changed")
                    self.last_source="replay";self.last_raw=deepcopy(source[i].get("raw_response"))
                    return deepcopy(source[i]["response"])
                if source is not None and boundary is not None and i==boundary:
                    expected=source[i]["request"]
                    if dict(req,input=expected["input"])!=expected:raise AssertionError("Non-history request fields changed at boundary")
                raw=live.send(req)
                self.last_raw=live.last_raw;self.last_source="live"
                return raw
        from .provenance import source_identity
        manifest={"source_identity":source_identity(),"task_id":a.task,"category":a.category,"repeat":a.repeat,"config":cfg.to_dict(),
                  "arm":a.arm or cfg.name,"budget_ledger":str(a.ledger or a.output/"budget.json"),"model":cfg.model["name"],"sampling":cfg.model["sampling"],"identity":str(a.source)if a.source else None,"status":"running"}
        write_new(a.output/"config.json",cfg.to_dict());write_new(a.output/"manifest.json",manifest)
        def emit(event):
            with (a.output/"events.jsonl").open("a") as f:f.write(json.dumps(event,ensure_ascii=False)+"\n")
            if event["event"]=="intervention":
                memory=event["prepared"]
                write_new(a.output/"memory-graph.json",memory["graph"])
                (a.output/"memory.txt").write_text(memory["memory_text"])
                write_new(a.output/"edit-audit.json",memory["edits"])
            if event["event"]=="request_response":
                with (a.output/"api.jsonl").open("a") as f:f.write(json.dumps({k:v for k,v in event.items() if k not in ("event","index")},ensure_ascii=False)+"\n")
        try:
            got=BFCLRunner(cfg,counter("o200k_base")).run(a.task,a.category,Transport(),trigger_index=boundary,source_tape=source,prefix_passed=sm.get("eligible"),emit=emit)
            write_new(a.output/"api.json",got["records"]);write_new(a.output/"full.json",{"result":got["result"],"metadata":got["metadata"]})
            result=official_score(a.task,a.category,got["result"]);write_new(a.output/"score.json",result)
            manifest.update(status="complete",trigger_index=got["trigger_index"],checkpoint_sha256=got["checkpoint_sha256"],requests=got["requests"],tool_calls=got["tool_calls"],usage_all=got["usage_all"],usage_live=got["usage_live"],usage_suffix=got["usage_suffix"])
        except BaseException:
            manifest["status"]="error";raise
        finally:(a.output/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    if getattr(a,"output",None) and a.command not in ("prepare","run","batch"):write_new(a.output,result)
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0

if __name__=="__main__":raise SystemExit(main())
