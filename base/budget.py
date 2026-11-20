"""Locked, persistent reservations. Uncertain requests retain their full reservation."""
from contextlib import contextmanager
from pathlib import Path
import fcntl,json,os,time,uuid

class BudgetExceeded(RuntimeError):pass
class PersistentBudget:
    def __init__(self,path,limit_usd,rates):
        self.path=Path(path).resolve();self.limit_usd=float(limit_usd);self.rates=dict(rates)
        self.rates.setdefault("cached_input",self.rates.get("cached",self.rates["input"]));self.rates.setdefault("cache_write",self.rates["input"])
        if self.limit_usd<=0 or any(float(self.rates.get(k,0))<=0 for k in ("input","output")):
            raise ValueError("Explicit positive cap and input/output rates are required")
        self.path.parent.mkdir(parents=True,exist_ok=True)
    @contextmanager
    def locked(self):
        with self.path.with_suffix(".lock").open("a") as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            d=json.loads(self.path.read_text()) if self.path.exists() else {"limit_usd":self.limit_usd,"rates":self.rates,"requests":{}}
            if d["limit_usd"]!=self.limit_usd or d["rates"]!=self.rates:raise ValueError("Ledger settings changed")
            yield d
            tmp=self.path.with_suffix(".tmp");tmp.write_text(json.dumps(d,indent=2)+"\n");os.replace(tmp,self.path)
    def reserve(self,request):
        # UTF-8 bytes plus framing provide a conservative text-only input bound.
        inp=len(json.dumps(request,ensure_ascii=False).encode())+2048
        out=request.get("max_tokens",request.get("max_completion_tokens",0))
        if type(out)is not int or out<=0:raise ValueError("Explicit maximum output is required")
        estimate=(inp*max(self.rates["input"],self.rates["cached_input"],self.rates["cache_write"])+out*self.rates["output"])/1e6
        with self.locked() as d:
            model=request.get("model")
            if not isinstance(model,str)or not model:raise ValueError("A model name is required for the ledger")
            if d.get("model")not in (None,model):raise ValueError("A budget ledger cannot mix models")
            d["model"]=model
            if d.get("not_after_unix") is not None and time.time() >= d["not_after_unix"]:
                raise BudgetExceeded("Experiment deadline reached")
            stage=d.get("active_stage")
            if stage is not None:
                if stage not in d.get("stage_limits",{}):raise ValueError("Unknown ledger stage")
                stage_occupied=sum(x.get("actual_usd",x["reserved_usd"]) for x in d["requests"].values() if x.get("stage")==stage)
                if stage_occupied+estimate>d["stage_limits"][stage]:raise BudgetExceeded("Stage budget reached")
            occupied=sum(x.get("actual_usd",x["reserved_usd"]) for x in d["requests"].values())
            if occupied+estimate>self.limit_usd:raise BudgetExceeded("Next request would exceed budget")
            key=uuid.uuid4().hex
            d["requests"][key]={"reserved_usd":estimate,"status":"reserved","time":time.time(),**({"stage":stage} if stage is not None else {})}
        return key
    def settle(self,reservation,response):
        u=response.get("usage",{});inp=u.get("prompt_tokens",u.get("input_tokens"));out=u.get("completion_tokens",u.get("output_tokens"))
        if type(inp)is not int or type(out)is not int:raise ValueError("Missing billable usage; reservation retained")
        cached=u.get("prompt_tokens_details",{}).get("cached_tokens",u.get("cache_read_input_tokens",0))
        creation=u.get("cache_creation_input_tokens",0)
        if "prompt_tokens" in u:uncached=inp-cached
        else:uncached=inp  # Anthropic input excludes cache read/write.
        if min(uncached,cached,creation)<0:raise ValueError("Invalid usage")
        cost=(uncached*self.rates["input"]+cached*self.rates.get("cached_input",self.rates["input"])+creation*self.rates.get("cache_write",self.rates["input"])+out*self.rates["output"])/1e6
        with self.locked() as d:d["requests"][reservation].update(status="settled",actual_usd=cost,usage=u)
    def uncertain(self,reservation):
        with self.locked() as d:d["requests"][reservation]["status"]="uncertain"
