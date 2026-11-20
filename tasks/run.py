"""目的和主要功能：执行已授权 BFCL 轨迹并保存预算、请求和官方结果。

适用范围：正常 run 命令，沿用显式预算及凭证要求。
"""
import json, os
from copy import deepcopy
from pathlib import Path
from cs769.base.config import load_config, ExperimentConfig
from cs769.base.io import read, write_new, counter

def execute(a):
    if not a.authorize_api or a.budget_usd<=0 or not a.credentials or not a.rates or os.environ.get("CS769_OFFLINE")=="1":
        raise PermissionError("Paid run requires explicit API authorization, positive new budget, credentials and rates; offline mode forbids it")
    from cs769.tasks.bfcl import BFCLRunner, official_score
    from cs769.models.http import HTTPTransport
    from cs769.models.provider import ProviderTransport
    from cs769.base.budget import PersistentBudget
    from cs769.base.replay import ReplayTransport
    if a.output.exists():raise FileExistsError("Refusing to overwrite an attempt")
    cfg_dict=load_config(a.config).to_dict();cfg_dict["execution"]["budget_usd"]=a.budget_usd
    cfg=ExperimentConfig.from_dict(cfg_dict)
    if a.prefix_turns is not None and (a.prefix_turns<1 or cfg.delivery["mode"]!="native"):
        raise ValueError("Prefix collection requires a positive turn count and native identity")
    if a.repeat<1:raise ValueError("Repeat index must be positive")
    if cfg.model["provider"]=="anthropic" and cfg.delivery["mode"]=="replace" and cfg.model.get("old_thinking")=="preserve":
        raise ValueError("Signed thinking cannot be preserved across a changed history; choose omit")
    maximum=cfg.model["sampling"].get("max_tokens",cfg.model["sampling"].get("max_completion_tokens",0))
    if type(maximum)is not int or maximum<=0:raise ValueError("A paid profile must set its maximum output tokens")
    source=read(a.source/"api.json") if a.source else None
    sm=read(a.source/"manifest.json") if a.source else {}
    source_boundary=read(a.source/"boundary-request.json") if a.source and (a.source/"boundary-request.json").is_file() else None
    if a.source:
        if sm.get("record_kind")=="completed_prefix" and source_boundary is None:raise ValueError("Completed prefix requires a verified boundary request")
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
                expected=source[i]["request"] if i<len(source) else source_boundary
                if expected is None:raise ValueError("Missing prefix boundary request")
                if dict(req,input=expected["input"])!=expected:raise AssertionError("Non-history request fields changed at boundary")
            # Normalized response IDs must continue after the replayed prefix.
            live.index=i
            raw=live.send(req)
            self.last_raw=live.last_raw;self.last_source="live"
            return raw
    from cs769.base.provenance import source_identity
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
        got=BFCLRunner(cfg,counter("o200k_base")).run(a.task,a.category,Transport(),trigger_index=boundary,source_tape=source,prefix_passed=sm.get("eligible"),emit=emit,turn_limit=a.prefix_turns,boundary_request=source_boundary)
        write_new(a.output/"api.json",got["records"]);write_new(a.output/"full.json",{"result":got["result"],"metadata":got["metadata"]})
        result=official_score(a.task,a.category,got["result"],turn_limit=a.prefix_turns);write_new(a.output/"score.json",result)
        manifest.update(status="complete",trigger_index=got["trigger_index"],checkpoint_sha256=got["checkpoint_sha256"],requests=got["requests"],tool_calls=got["tool_calls"],usage_all=got["usage_all"],usage_live=got["usage_live"],usage_suffix=got["usage_suffix"])
        if a.prefix_turns is not None:
            manifest.update(record_kind="completed_prefix",completed_turns=a.prefix_turns,eligible=result["passed"],trigger_index=len(got["records"]))
    except BaseException:
        manifest["status"]="error";raise
    finally:(a.output/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    return result
