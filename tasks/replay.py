"""目的和主要功能：严格回放保存轨迹并对照官方结果。

适用范围：已有 BFCL 请求、回复和评分的免费轨迹重建。
"""
from pathlib import Path
from cs769.base.io import read, counter
from cs769.base.config import ExperimentConfig

def replay_record(record,config,source=None):
    from cs769.tasks.bfcl import BFCLRunner, official_score
    from cs769.base.replay import ReplayTransport
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
