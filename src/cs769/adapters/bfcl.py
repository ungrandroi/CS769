"""Pinned official BFCL drives the tools and turns; only model/memory hooks are injected."""
from contextlib import contextmanager
from copy import deepcopy
import json,os
from pathlib import Path
from types import MethodType
from ..config import ExperimentConfig
from ..history import normalize,balanced,history_counter_text
from ..metrics import Usage
from ..bootstrap import ensure_bfcl
from ..pipeline import prepare
from .qwen_transport import plain,chat_messages

@contextmanager
def sdk_placeholder():
    names=("OPENAI_API_KEY","OPENAI_BASE_URL","OPENAI_DEFAULT_HEADERS")
    before={n:os.environ.get(n) for n in names}
    os.environ.update(OPENAI_API_KEY="offline-placeholder",OPENAI_BASE_URL="http://127.0.0.1:9/v1")
    os.environ.pop("OPENAI_DEFAULT_HEADERS",None)
    try:yield
    finally:
        for n,v in before.items():
            if v is None:os.environ.pop(n,None)
            else:os.environ[n]=v

def history_tokens(history,count,*,sort_keys=True):
    return count(history_counter_text(history,sort_keys=sort_keys))

def official_score(task,category,result,*,model="gpt-4.1",model_key="azure/gpt-4.1-FC"):
    global _USED_PROCESS,_SCORED_PROCESS
    if _SCORED_PROCESS:raise RuntimeError("Official BFCL scoring also requires one trajectory per process")
    _SCORED_PROCESS=True
    if _USED_PROCESS is None:_USED_PROCESS=-os.getpid()
    ensure_bfcl()
    from bfcl_eval.model_handler.api_inference.openai_response import OpenAIResponsesHandler
    from bfcl_eval.utils import load_dataset_entry,load_ground_truth_entry,make_json_serializable
    from bfcl_eval.eval_checker.eval_runner import _evaluate_single_multi_turn_entry
    entry=next(x for x in load_dataset_entry(category) if x["id"]==task)
    truth=next(x["ground_truth"] for x in load_ground_truth_entry(category) if x["id"]==task)
    with sdk_placeholder():
        handler=OpenAIResponsesHandler(model,0,model_key,True)
        diag=_evaluate_single_multi_turn_entry(handler,task,deepcopy(result),deepcopy(truth),
                                              deepcopy(entry),"cs769",category)
    return {"passed":bool(diag["valid"]),"diagnostics":make_json_serializable(diag),
            "evaluator":"official BFCL _evaluate_single_multi_turn_entry; unchanged"}

_USED_PROCESS = None
_SCORED_PROCESS = False

class BFCLRunner:
    def __init__(self,config,count):
        self.config=config if isinstance(config,ExperimentConfig) else ExperimentConfig.from_dict(config)
        self.config.validate();self.count=count

    def run(self,task,category,transport,*,trigger_index=None,source_tape=None,prefix_passed=None,emit=None,model_key="azure/gpt-4.1-FC"):
        global _USED_PROCESS
        if _USED_PROCESS is not None:
            raise RuntimeError("BFCL task state is process-global; use one worker process per trajectory")
        _USED_PROCESS = os.getpid()
        ensure_bfcl()
        from bfcl_eval.model_handler.api_inference.openai_response import OpenAIResponsesHandler
        from bfcl_eval.utils import load_dataset_entry,make_json_serializable
        from openai.types.responses import Response
        cfg=self.config
        entry=next(x for x in load_dataset_entry(category) if x["id"]==task)
        original_entry=deepcopy(entry)
        emit=emit or (lambda event:None)
        records=[];prepared=None;intervention=None;captured_boundary=None;checkpoint_sha256=None;failures=[];turn=0;replay_outputs={}
        with sdk_placeholder():
            handler=OpenAIResponsesHandler(cfg.model["name"],cfg.model["sampling"].get("temperature",0),model_key,True)
            add=handler._add_next_turn_user_message_FC
            def add_user(self,data,message):
                nonlocal turn
                turn+=1
                return add(data,message)
            handler._add_next_turn_user_message_FC=MethodType(add_user,handler)
            parse=handler._parse_query_response_FC
            def parse_response(self,response):
                parsed=parse(response)
                if response.id in replay_outputs:
                    parsed["model_responses_message_for_chat_history"]=replay_outputs.pop(response.id)
                return parsed
            handler._parse_query_response_FC=MethodType(parse_response,handler)
            query=handler._query_FC
            def query_fc(self,data):
                nonlocal prepared,intervention,captured_boundary,checkpoint_sha256
                history=plain(data["message"]);index=len(records)
                do=False
                if prepared is None and captured_boundary is None:
                    norm,_=normalize(history)
                    if balanced(norm):
                        kind=cfg.checkpoint["kind"]
                        if trigger_index is not None:do=index==trigger_index
                        elif kind=="manual":do=True
                        elif kind=="completed_turn":do=turn-1>=cfg.checkpoint["turns"] and history[-1].get("role")=="user"
                        else:
                            mode=cfg.checkpoint.get("counter")
                            if mode not in ("history_json","history_json_sorted"):raise ValueError("BFCL live boundary requires history_json; other counters need explicit measured metadata")
                            tokens=history_tokens(history,self_outer.count,sort_keys=mode=="history_json_sorted")
                            do=tokens>cfg.checkpoint["threshold"] if cfg.checkpoint.get("strict",True) else tokens>=cfg.checkpoint["threshold"]
                if do:
                    import hashlib
                    captured_boundary=index
                    checkpoint_sha256=hashlib.sha256(json.dumps(history,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()
                if do and cfg.delivery["mode"]!="native":
                    if cfg.selection.get("require_prefix_pass") and prefix_passed is not True:
                        raise ValueError("Official prefix pass is required before this intervention")
                    if source_tape is not None:
                        expected=source_tape[index]["request"]
                        if history!=expected["input"] or plain(data["tools"])!=expected.get("tools",[]):
                            raise AssertionError("Restored boundary or tool definitions changed")
                    archived=history;following=[]
                    if cfg.checkpoint["kind"]=="completed_turn":
                        archived=history[:-1];following=history[-1:]
                    native=chat_messages(archived);native_context=None
                    if cfg.model["provider"]=="anthropic":
                        from .provider import anthropic_messages
                        system,native=anthropic_messages(native)
                        native_context={"system":system}
                    prepared=prepare(archived,cfg,self_outer.count,native_history=native,native_context=native_context,
                                     next_messages=following,counter_name="o200k_base")
                    if not prepared["eligible"]:raise ValueError("Selected checkpoint ineligible")
                    data["message"]=plain(prepared["messages"])
                    intervention=index
                    emit({"event":"intervention","index":index,"prepared":prepared})
                return query(data)
            self_outer=self
            def checked_query(self,data):
                try:return query_fc(self,data)
                except BaseException as error:
                    failures.append(type(error).__name__+": "+str(error));raise
            handler._query_FC=MethodType(checked_query,handler)
            def generate(**kwargs):
                req=plain(kwargs)
                try:
                    if len(records)>=cfg.execution["max_requests"]:raise RuntimeError("Configured model request limit reached")
                    emit({"event":"request","index":len(records),"request":req})
                    raw=transport.send(req)
                    replay_outputs[raw["id"]]=plain(raw["output"])
                    record={"request":req,"response":plain(raw),"turn":turn,"source":getattr(transport,"last_source","replay")}
                    if getattr(transport,"last_raw",None) is not None:record["raw_response"]=deepcopy(transport.last_raw)
                    records.append(record);emit({"event":"request_response","index":len(records)-1,**record})
                    return Response.model_validate(raw),0
                except BaseException as e:
                    failures.append(type(e).__name__+": "+str(e));raise
            handler.generate_with_backoff=generate
            result,metadata=handler.inference(deepcopy(entry),True,False)
            if failures:raise RuntimeError(failures[0])
            if hasattr(transport,"finish"):transport.finish()
            if entry!=original_entry:raise AssertionError("Dataset entry mutated")
        if trigger_index is not None and cfg.delivery["mode"]!="native" and intervention!=trigger_index:
            raise AssertionError("Expected memory boundary was never applied")
        all_usage=Usage();live_usage=Usage();suffix_usage=Usage()
        for i,r in enumerate(records):
            packet=r.get("raw_response",r["response"])
            for usage in [all_usage]+([live_usage]if r["source"]=="live"else [])+([suffix_usage]if (trigger_index if trigger_index is not None else captured_boundary) is None or i>=(trigger_index if trigger_index is not None else captured_boundary) else []):
                usage.add(packet,cfg.model["provider"])
        return {"usage_all":all_usage.report(),"usage_live":live_usage.report(),"usage_suffix":suffix_usage.report(),"task":task,"category":category,"result":plain(result),"metadata":plain(make_json_serializable(metadata)),
                "records":records,"prepared":prepared,"trigger_index":captured_boundary,"checkpoint_sha256":checkpoint_sha256,
                "tool_calls":sum(x.get("type")=="function_call" for r in records for x in r["response"].get("output",[])),
                "requests":len(records)}
