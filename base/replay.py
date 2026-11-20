"""Strict recorded transport: every request must match before releasing its response."""
from copy import deepcopy
import json
from pathlib import Path

def first_difference(a,b,path="request"):
    if type(a)!=type(b):return path+" (type)"
    if isinstance(a,dict):
        if set(a)!=set(b):return path+" (keys)"
        for k in a:
            if a[k]!=b[k]:return first_difference(a[k],b[k],path+"."+str(k))
    elif isinstance(a,list):
        if len(a)!=len(b):return path+" (length "+str(len(a))+"/"+str(len(b))+")"
        for i,(x,y) in enumerate(zip(a,b)):
            if x!=y:return first_difference(x,y,path+"["+str(i)+"]")
    return path+" actual="+repr(a)[:160]+" expected="+repr(b)[:160]

class ReplayMismatch(AssertionError): pass

class ReplayTransport:
    def __init__(self, tape):
        self.tape = json.loads(Path(tape).read_text()) if isinstance(tape,(str,Path)) else deepcopy(tape)
        self.index = 0
        self.checked = []
    def send(self, request):
        if self.index >= len(self.tape):
            raise ReplayMismatch("Replay exhausted at request "+str(self.index))
        row=self.tape[self.index]
        if request != row["request"]:
            keys=[k for k in set(request)|set(row["request"]) if request.get(k)!=row["request"].get(k)]
            raise ReplayMismatch("Request differs at index "+str(self.index)+": "+first_difference(request,row["request"]))
        self.last_raw=deepcopy(row.get("raw_response"));self.last_source="replay"
        self.checked.append(self.index);self.index+=1
        return deepcopy(row["response"])
    def finish(self):
        if self.index!=len(self.tape):
            raise ReplayMismatch("Unused archived responses: "+str(len(self.tape)-self.index))
