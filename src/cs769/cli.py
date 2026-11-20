"""One parser and one public command path for memory preparation and BFCL runs."""
import argparse,json,sys
from contextlib import redirect_stdout
from pathlib import Path
from cs769.base.config import load_config
from cs769.tasks.memory import prepare_files
from cs769.base.registry import BUILDERS, EDITORS

from cs769.base.io import read, write_new, counter
from cs769.base.paths import config_directory, new_output

def build_parser():
    p=argparse.ArgumentParser(description="CS769: one configurable graph-memory entry point")
    commands=p.add_subparsers(dest="command",required=True)
    commands.add_parser("list",help="list builders, edits and profiles")
    x=commands.add_parser("validate");x.add_argument("config",type=Path)
    x=commands.add_parser("prepare",help="offline graph/edit/request preparation")
    x.add_argument("--config",required=True,type=Path);x.add_argument("--history",required=True,type=Path)
    for n in ("native-history","context","next-messages"):x.add_argument("--"+n,type=Path)
    x.add_argument("--counter",choices=("characters","o200k_base"),default="o200k_base")
    x.add_argument("--output",type=Path)
    x=commands.add_parser("replay",help="strict free replay through official BFCL tools")
    x.add_argument("--config",required=True,type=Path);x.add_argument("--record",required=True,type=Path)
    x.add_argument("--source",type=Path);x.add_argument("--output",type=Path)
    x=commands.add_parser("score",help="read-only official scoring of a saved result")
    x.add_argument("--record",required=True,type=Path);x.add_argument("--output",type=Path)
    x=commands.add_parser("report",help="summarize paired rows without calling models")
    group=x.add_mutually_exclusive_group(required=True);group.add_argument("--rows",type=Path);group.add_argument("--batch",type=Path)
    x.add_argument("--baseline",default="identity");x.add_argument("--candidate",default="g9");x.add_argument("--output",type=Path)
    x=commands.add_parser("prefix-source",help="free replay and official completed-prefix qualification")
    x.add_argument("--config",required=True,type=Path);x.add_argument("--api",required=True,type=Path)
    x.add_argument("--task",required=True);x.add_argument("--category",required=True);x.add_argument("--turns",required=True,type=int);x.add_argument("--output",type=Path)
    x=commands.add_parser("inspect-prefix",help="free graph-edit eligibility from a verified prefix")
    x.add_argument("--config",required=True,type=Path);x.add_argument("--record",required=True,type=Path);x.add_argument("--output",type=Path)
    x=commands.add_parser("boundary",help="free exact prefix replay to capture the next request")
    x.add_argument("--config",required=True,type=Path);x.add_argument("--record",required=True,type=Path);x.add_argument("--output",required=True,type=Path)
    x=commands.add_parser("run",help="new run; network requires separate explicit API authorization")
    x.add_argument("--config",required=True,type=Path);x.add_argument("--task",required=True);x.add_argument("--category",required=True)
    x.add_argument("--source",type=Path);x.add_argument("--output",type=Path);x.add_argument("--repeat",type=int,default=1);x.add_argument("--arm")
    x.add_argument("--prefix-turns",type=int,help="collect only completed prefix turns using identity")
    x.add_argument("--authorize-api",action="store_true");x.add_argument("--budget-usd",type=float,default=0)
    x.add_argument("--credentials",type=Path);x.add_argument("--rates",type=Path);x.add_argument("--ledger",type=Path)
    x=commands.add_parser("campaign",help="parameterized screening and gated experiment execution")
    x.add_argument("--root",required=True,type=Path);x.add_argument("--mode",required=True,choices=("free","run","report"));x.add_argument("--max-rounds",type=int)
    x=commands.add_parser("batch",help="isolated task workers; one shared experiment ledger")
    x.add_argument("--plan",required=True,type=Path);x.add_argument("--config",required=True,type=Path);x.add_argument("--output",type=Path)
    x.add_argument("--replay",action="store_true");x.add_argument("--authorize-api",action="store_true")
    x.add_argument("--budget-usd",type=float,default=0);x.add_argument("--credentials",type=Path);x.add_argument("--rates",type=Path);x.add_argument("--workers",type=int,default=1);x.add_argument("--ledger",type=Path)
    return p

from cs769.tasks.replay import replay_record

def main(argv=None):
    a=build_parser().parse_args(argv)
    if a.command in {"prepare", "run", "batch", "prefix-source"} and a.output is None:
        a.output = new_output(a.command)
    if a.command=="list":
        result={"builders":sorted(BUILDERS),"edits":sorted(EDITORS),"profiles":[p.stem for p in sorted(config_directory().glob("*.json")) if not p.name.startswith("_")]}
    elif a.command=="validate":result=load_config(a.config).to_dict()
    elif a.command=="prepare":
        result=prepare_files(a.config,a.history,a.output,counter_name=a.counter,
                             native_history=a.native_history,context=a.context,next_messages=a.next_messages)
    elif a.command=="replay":
        with redirect_stdout(sys.stderr):result=replay_record(a.record,load_config(a.config),a.source)
    elif a.command=="prefix-source":
        from cs769.tasks.prefix import reconstruct
        with redirect_stdout(sys.stderr):result=reconstruct(load_config(a.config),a.task,a.category,a.api,a.turns,a.output)
    elif a.command=="inspect-prefix":
        from cs769.tasks.prefix import inspect
        result=inspect(load_config(a.config),a.record)
    elif a.command=="boundary":
        from cs769.tasks.bfcl import capture_prefix_boundary
        m=read(a.record/"manifest.json")
        with redirect_stdout(sys.stderr):
            result=capture_prefix_boundary(load_config(a.config),m.get("task_id",m.get("task")),m["category"],read(a.record/"api.json"))
    elif a.command=="campaign":
        from cs769.tasks.campaign import execute
        result=execute(a.root,a.mode,a.max_rounds)
    elif a.command=="batch":
        from cs769.base.batch import execute_batch
        result=execute_batch(a)
    elif a.command=="score":
        from cs769.tasks.bfcl import official_score
        m=read(a.record/"manifest.json");result=official_score(m.get("task_id",m.get("task")),m["category"],read(a.record/"full.json")["result"])
    elif a.command=="report":
        from cs769.tasks.reporting import from_rows, from_batch
        result=from_batch(a.batch,a.baseline,a.candidate) if a.batch else from_rows(read(a.rows),a.baseline,a.candidate)
    else:
        from cs769.tasks.run import execute
        result=execute(a)
    if getattr(a,"output",None) and a.command not in ("prepare","run","batch","prefix-source"):write_new(a.output,result)
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0

if __name__=="__main__":raise SystemExit(main())
