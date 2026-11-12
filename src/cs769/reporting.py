"""Read completed runs into the same paired token/tool-call report."""
from pathlib import Path
import json
from .metrics import paired

def read(p):return json.loads(Path(p).read_text())
def from_rows(rows,baseline="identity",candidate="g9"):
    models=sorted({r.get("model","unspecified")for r in rows})
    if len(models)>1:
        return {"models":{m:paired([r for r in rows if r.get("model","unspecified")==m],baseline,candidate)for m in models}}
    return {**paired(rows,baseline,candidate),"model":models[0]if models else None}

def from_batch(directory,baseline="identity",candidate="g9"):
    root=Path(directory);manifest=read(root/"manifest.json")
    plan=read(root/"plan.json");rows=[];excluded=[]
    for index,spec in enumerate(plan):
        stem=str(index).zfill(4)+"-"+spec["task"]+"-"+spec.get("arm","")
        attempt=root/stem
        if not (attempt/"manifest.json").is_file() or not (attempt/"score.json").is_file():
            excluded.append({"task":spec["task"],"arm":spec.get("arm"),"reason":"incomplete_or_no_official_score"});continue
        run=read(attempt/"manifest.json");score=read(attempt/"score.json")
        if run.get("status")!="complete"or type(score.get("passed"))is not bool:
            excluded.append({"task":spec["task"],"arm":spec.get("arm"),"reason":"not_scoreable"});continue
        if run.get("trigger_index")is None:
            excluded.append({"task":spec["task"],"arm":spec.get("arm"),"reason":"checkpoint_not_triggered"});continue
        rows.append({"task":run["task_id"],"arm":run.get("arm",spec.get("arm")),"repeat":run.get("repeat",spec.get("repeat",1)),
                     "checkpoint_sha256":run["checkpoint_sha256"],"model":run["model"],"passed":score["passed"],"usage":run["usage_suffix"]})
    out=from_rows(rows,baseline,candidate)
    out.update(complete_scored_rows=len(rows),excluded=excluded,fees_basis="caller-supplied rates; not a provider invoice")
    if (root/"budget.json").is_file():
        ledger=read(root/"budget.json");requests=ledger["requests"].values()
        out["known_api_usd"]=sum(x.get("actual_usd",0)for x in requests)
        out["unsettled_reserved_usd"]=sum(x["reserved_usd"]for x in requests if "actual_usd"not in x)
    return out
