"""One HTTP sender; credentials are read only when explicitly authorized."""
from pathlib import Path
import json,os,shlex,stat,urllib.request,urllib.error

def read_credentials(path):
    p=Path(path).expanduser()
    if stat.S_IMODE(p.stat().st_mode)&0o077:raise PermissionError("Credential file must be private")
    values={}
    for line in p.read_text().splitlines():
        parts=shlex.split(line,comments=True)
        if parts and parts[0]=="export":parts=parts[1:]
        for part in parts:
            if "=" in part:
                k,v=part.split("=",1);values[k]=v
    return values

class ProviderError(RuntimeError):pass

class HTTPTransport:
    def __init__(self,provider,key_file,budget,*,authorized=False,timeout=600,record=None):
        self.provider=provider;self.key_file=key_file;self.budget=budget;self.budget_owner=budget;self.authorized=authorized;self.timeout=timeout;self.record=record or (lambda event:None)
    def send(self,body):
        if not self.authorized or os.environ.get("CS769_OFFLINE")=="1":
            raise PermissionError("Network/API execution is disabled")
        values=read_credentials(self.key_file)
        if self.provider=="anthropic":
            url=values.get("ANTHROPIC_BASE_URL","https://api.anthropic.com").rstrip("/")+"/v1/messages"
            headers={"content-type":"application/json","anthropic-version":"2023-06-01","x-api-key":values["ANTHROPIC_API_KEY"]}
        else:
            url=values.get("OPENAI_BASE_URL","https://api.openai.com/v1").rstrip("/")+"/chat/completions"
            headers={"content-type":"application/json","authorization":"Bearer "+values["OPENAI_API_KEY"]}
        reservation=self.budget.reserve(body)
        self.record({"kind":"request","reservation":reservation,"body":body})
        try:
            req=urllib.request.Request(url,data=json.dumps(body,ensure_ascii=False).encode(),headers=headers,method="POST")
            with urllib.request.urlopen(req,timeout=self.timeout) as resp:result=json.loads(resp.read())
            self.record({"kind":"response","reservation":reservation,"body":result})
            self.budget.settle(reservation,result)
            return result
        except urllib.error.HTTPError as error:
            self.budget.uncertain(reservation)
            try:
                item=json.loads(error.read()).get("error",{})
                message=str(item.get("message","Request failed"));kind=str(item.get("type","http_error"))
            except (ValueError,AttributeError):message="Request failed";kind="http_error"
            for secret in values.values():
                if len(secret)>3:message=message.replace(secret,"[redacted]");kind=kind.replace(secret,"[redacted]")
            raise ProviderError("HTTP "+str(error.code)+" "+kind[:120]+": "+message[:600]) from None
        except BaseException:
            self.budget.uncertain(reservation)
            raise ProviderError("Network/request failure; reservation retained") from None
