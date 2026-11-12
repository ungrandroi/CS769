"""Isolated invocations of one CLI. Paid batches share a locked ledger and are serial."""
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import json,os,subprocess,sys

def execute_batch(args):
    rows=json.loads(args.plan.read_text())
    if isinstance(rows,dict):rows=rows["tasks"]
    if not rows:raise ValueError("Empty task plan")
    keys=[(r["task"],r.get("arm",""),r.get("repeat",1)) for r in rows]
    if len(keys)!=len(set(keys)):raise ValueError("Duplicate task/arm in plan")
    if args.output.exists():raise FileExistsError("Refusing to overwrite a batch")
    if not 1<=args.workers<=4:raise ValueError("Use 1 to 4 isolated workers")
    if not args.replay and (args.workers!=1 or not args.authorize_api or args.budget_usd<=0 or not args.credentials or not args.rates or os.environ.get("CS769_OFFLINE")=="1"):
        raise PermissionError("Paid batch needs explicit authorization, one worker and one shared budget")
    args.output.mkdir(parents=True)
    (args.output/"plan.json").write_text(json.dumps(rows,indent=2)+"\n")
    (args.output/"config.json").write_bytes(args.config.read_bytes())
    from .provenance import source_identity,package_hashes
    identity=source_identity();expected_sources=identity["package_sha256"]
    manifest={"source_identity":identity,"status":"running","mode":"replay" if args.replay else "new_run","workers":args.workers,"results":[]}
    target=args.output/"manifest.json"
    def worker(item):
        if package_hashes()!=expected_sources:raise RuntimeError("Source changed after batch preparation")
        i,row=item
        if not args.replay:
            from .config import load_config
            base_model=load_config(args.config).model;current=load_config(Path(row.get("config",args.config))).model
            if (current["provider"],current["name"])!=(base_model["provider"],base_model["name"]):
                raise ValueError("Paid batch cannot borrow another model's budget")
        stem=str(i).zfill(4)+"-"+row["task"]+"-"+row.get("arm","")
        cmd=[sys.executable,"-B","-m","cs769","replay" if args.replay else "run","--config",str(row.get("config",args.config))]
        if args.replay:cmd+=["--record",str(row["record"])]
        else:cmd+=["--task",row["task"],"--category",row["category"],"--output",str(args.output/stem),
                  "--authorize-api","--budget-usd",str(args.budget_usd),"--credentials",str(args.credentials),
                  "--rates",str(args.rates),"--ledger",str(args.output/"budget.json"),"--repeat",str(row.get("repeat",1)),"--arm",row.get("arm",load_config(args.config).name)]
        if row.get("source"):cmd+=["--source",str(row["source"])]
        with (args.output/(stem+".stdout")).open("w") as out,(args.output/(stem+".stderr")).open("w") as err:
            proc=subprocess.run(cmd,stdout=out,stderr=err)
        result={"task":row["task"],"arm":row.get("arm"),"repeat":row.get("repeat",1),"returncode":proc.returncode}
        if proc.returncode==0 and args.replay:result["verification"]=json.loads((args.output/(stem+".stdout")).read_text())
        return result
    try:
        if not args.replay:
            for item in enumerate(rows):
                result=worker(item);manifest["results"].append(result)
                target.write_text(json.dumps(manifest,indent=2)+"\n")
                if result["returncode"]:raise RuntimeError("Worker failed; batch stopped: "+result["task"])
        else:
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                futures=[pool.submit(worker,item)for item in enumerate(rows)]
                for future in as_completed(futures):
                    try:result=future.result()
                    except BaseException:
                        for pending in futures:pending.cancel()
                        raise
                    manifest["results"].append(result)
                    target.write_text(json.dumps(manifest,indent=2)+"\n")
                    if result["returncode"]:
                        for f in futures:f.cancel()
                        raise RuntimeError("Worker failed; batch stopped: "+result["task"])
        manifest["status"]="complete"
    except BaseException:
        manifest["status"]="error";raise
    finally:target.write_text(json.dumps(manifest,indent=2)+"\n")
    return manifest
