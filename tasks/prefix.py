"""Reusable free source reconstruction and edit qualification for completed turns."""
from cs769.base.io import read, write
from pathlib import Path
from copy import deepcopy
import json,hashlib
from cs769.base.config import ExperimentConfig
from cs769.base.io import counter
from cs769.tasks.bfcl import BFCLRunner, official_score
from cs769.base.replay import ReplayTransport
from cs769.models.qwen_transport import chat_messages
from cs769.tasks.memory import prepare
from cs769.base.provenance import source_identity

def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def reconstruct(config,task,category,api,turns,output):
    """One saved source is selected externally before seeing continuation outcomes."""
    output=Path(output)
    if output.exists():raise FileExistsError("Source output already exists")
    if config.delivery["mode"]!="native":raise ValueError("Prefix reconstruction requires identity")
    tape=read(api)
    prefix=[]
    for row in tape:
        users=sum(m.get("role")=="user"for m in row["request"]["input"])
        if users>turns:break
        prefix.append(row)
    if not prefix:raise ValueError("Archived prefix is unavailable")
    if sum(m.get("role")=="user"for m in prefix[-1]["request"]["input"])!=turns:
        raise ValueError("Archived source does not reach requested turn")
    if any(x.get("type")=="function_call"for x in prefix[-1]["response"]["output"]):
        raise ValueError("Archived source ends within an incomplete tool exchange")
    transport=ReplayTransport(prefix)
    got=BFCLRunner(config,counter("o200k_base")).run(task,category,transport,turn_limit=turns)
    score=official_score(task,category,got["result"],turn_limit=turns)
    output.mkdir(parents=True)
    write(output/"api.json",got["records"]);write(output/"full.json",{"result":got["result"],"metadata":got["metadata"]})
    write(output/"score.json",score)
    manifest={"status":"complete","record_kind":"completed_prefix","completed_turns":turns,
              "task_id":task,"category":category,"model":config.model["name"],"sampling":config.model["sampling"],
              "trigger_index":len(got["records"]),"eligible":score["passed"],"source_identity":source_identity(),
              "source_api":str(api),"source_api_sha256":hashlib.sha256(Path(api).read_bytes()).hexdigest(),
              "exact_requests":True,"paid_requests":0,"usage_reference":got["usage_all"]}
    write(output/"manifest.json",manifest)
    return {"task":task,"turns":turns,"prefix_passed":score["passed"],"requests_replayed":len(got["records"]),"paid_requests":0}

def inspect(config,source):
    """Current and future task text never enters the numeric editor's decisions."""
    source=Path(source);manifest=read(source/"manifest.json")
    request=read(source/"boundary-request.json")
    history=request["input"][:-1];following=request["input"][-1:]
    if len(following)!=1 or following[0].get("role")!="user":raise ValueError("Expected next user turn")
    native=chat_messages(history);count=counter("o200k_base")
    result=prepare(history,config,count,native_history=native,next_messages=following,counter_name="o200k_base")
    edits=result["edits"];applied=bool(edits and all(x["status"]=="applied"for x in edits))
    return {"task":manifest["task_id"],"turns":manifest["completed_turns"],"prefix_passed":manifest["eligible"],
            "eligible":manifest["eligible"] and applied and result["metrics"]["memory_saved_units"]>0,
            "metrics":result["metrics"],"edits":edits,"source_request_sha256":digest(request),
            "memory_sha256":hashlib.sha256(result["memory_text"].encode()).hexdigest(),
            "messages_sha256":digest(result["messages"]),"graph_sha256":digest(result["graph"]),"paid_requests":0}



def capture_checkpoint(config, source, *, require_prefix_pass=True):
    """Replay a qualified completed prefix and capture one real next request.

    Runs the same BFCL handler, tool environment and graph intervention used by
    paid run, with a transport that stops before any new response or API call.
    Each invocation owns an isolated process, as with ordinary BFCL replay.
    """
    from cs769.models.provider import openai_body
    source = Path(source)
    manifest = read(source / "manifest.json")
    if manifest.get("status") != "complete" or (require_prefix_pass and manifest.get("eligible") is not True):
        raise ValueError("Capture requires a complete officially qualified prefix")
    tape = read(source / "api.json")
    boundary = read(source / "boundary-request.json")
    replay = ReplayTransport(tape)
    prepared = None
    class Reached(BaseException):
        def __init__(self, request):
            self.request = deepcopy(request)
    class Capture:
        def send(self, request):
            if replay.index == len(tape):
                if dict(request, input=boundary["input"]) != boundary:
                    raise AssertionError("Non-history fields changed at checkpoint")
                raise Reached(request)
            response = replay.send(request)
            self.last_source = "replay"
            self.last_raw = replay.last_raw
            return response
    def emit(event):
        nonlocal prepared
        if event["event"] == "intervention":
            prepared = deepcopy(event["prepared"])
    try:
        BFCLRunner(config, counter("o200k_base")).run(
            manifest["task_id"], manifest["category"], Capture(),
            trigger_index=len(tape), source_tape=tape, prefix_passed=manifest.get("eligible"),
            boundary_request=boundary, emit=emit)
    except Reached as stop:
        result = {"task": manifest["task_id"], "request": stop.request,
                  "prepared": prepared, "requests_replayed": replay.index,
                  "paid_requests": 0}
        if config.model["provider"] == "openai":
            result["wire"] = openai_body(stop.request, config.model)
        return result
    raise ValueError("Qualified prefix has no next model request")
