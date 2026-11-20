"""Translate the official handler protocol into a single configured provider."""
from copy import deepcopy
import json
from cs769.models.qwen_transport import chat_messages, plain, response_from_chat
from cs769.models.qwen_prompt_accounting import to_chat_tools
from cs769.models.anthropic_transport import native_tools, normalized_response, tool_error

def anthropic_messages(chat):
    system=[];out=[]
    for m in chat:
        role=m["role"]
        if role in ("system","developer"):
            system.append({"type":"text","text":m.get("content","")});continue
        if role=="tool":
            msg={"role":"user","content":[{"type":"tool_result","tool_use_id":m["tool_call_id"],"content":m.get("content",""),"is_error":tool_error(m.get("content",""))}]}
        else:
            blocks=[]
            if m.get("content"):blocks.append({"type":"text","text":m["content"]})
            for c in m.get("tool_calls",[]) or []:
                blocks.append({"type":"tool_use","id":c["id"],"name":c["function"]["name"],"input":json.loads(c["function"]["arguments"])})
            msg={"role":role,"content":blocks}
        if out and out[-1]["role"]==msg["role"]:out[-1]["content"].extend(msg["content"])
        else:out.append(msg)
    return system,out

def openai_body(request,model):
    return {"model":model["name"],"messages":chat_messages(request["input"]),
            "tools":to_chat_tools(request.get("tools",[])),**deepcopy(model["sampling"])}

class ProviderTransport:
    def __init__(self,config,http):self.config=config;self.http=http;self.index=0;self._chat=[];self._native=[];self._system=[]
    def send(self,request):
        m=self.config.model;chat=chat_messages(request["input"])
        if m["provider"]=="anthropic":
            if self._chat and chat[:len(self._chat)]==self._chat:
                current_suffix=chat[len(self._chat):]
                _,suffix=anthropic_messages(current_suffix)
                messages=deepcopy(self._native)
                if m.get("old_thinking","omit")=="omit" and any(x.get("role")=="user"for x in current_suffix):
                    for item in messages:
                        item["content"]=[b for b in item["content"]if b.get("type")not in ("thinking","redacted_thinking")]
                    messages=[item for item in messages if item["content"]]
                for item in suffix:
                    if messages and messages[-1]["role"]==item["role"]:messages[-1]["content"].extend(item["content"])
                    else:messages.append(item)
                system=deepcopy(self._system)
            else:
                system,messages=anthropic_messages(chat)
            wire={"model":m["name"],"system":system,"messages":messages,"tools":native_tools(request.get("tools",[])),**deepcopy(m["sampling"])}
            raw=self.http.send(wire);response=plain(normalized_response(raw,self.index))
            self._native=deepcopy(messages)+[{"role":"assistant","content":deepcopy(raw["content"])}]
            self._system=deepcopy(system)
            self._chat=chat_messages(request["input"]+response["output"])
        else:
            wire=openai_body(request,m)
            raw=self.http.send(wire);response=plain(response_from_chat(raw,self.index))
        self.last_raw=deepcopy(raw);self.last_wire=deepcopy(wire)
        self.last_source="live"
        self.index+=1
        return response
