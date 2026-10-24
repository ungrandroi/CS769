"""Single threshold conversion, then retain graph plus growing suffix without artificial token limit."""
from core.research_modes import method_id
import argparse,json,os,time,urllib.request
from pathlib import Path
from types import MethodType
from core.qwen_transport import plain,chat_messages,response_from_chat
from core.qwen_prompt_accounting import to_chat_tools
from workflows.baseline_task import make_memory
from core.graph_memory_replace import retained_instructions
from core.local_qwen_tokenizer import LocalQwenTokenizer
def count_request(messages,tools,tok,base_url):
    payload={'model':'bfcl-qwen38-27b','messages':messages,'tools':tools,'temperature':0,'seed':42,'max_tokens':4096,'stream':False,'cache_prompt':True,'chat_template_kwargs':{'enable_thinking':False,'preserve_thinking':False}}
    req=urllib.request.Request(base_url.removesuffix('/v1')+'/apply-template',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=30) as r:rendered=json.load(r)
    return tok.count(rendered['prompt'],parse_special=True)
ROOT=Path(__file__).resolve().parents[2];OLD=ROOT/'experiments/bfcl_identity/qwen27b_experiment';OUT=ROOT/'experiments/bfcl_identity/history1000_eval'
class BudgetExceeded(Exception):pass

def main():
    global OUT
    p=argparse.ArgumentParser();p.add_argument('--task',required=True);p.add_argument('--mode',required=True,type=method_id,choices=['identity','v1-compact','v2-compact']);p.add_argument('--base-url',default='http://127.0.0.1:11435/v1');p.add_argument('--output-root',type=Path,default=OUT);a=p.parse_args();OUT=a.output_root.resolve()
    d=OUT/'tasks'/a.task/a.mode;d.mkdir(parents=True,exist_ok=True);assert not (d/'manifest.json').exists()
    src=OLD/'tasks'/a.task/'identity';source=json.loads((src/f'{a.task}.api.json').read_text())
    pre=json.loads((OUT/'plan.json').read_text());row=next(r for r in pre['checkpoints']['tasks'] if r['id']==a.task);boundary=row['trigger_index'];assert boundary is not None
    os.environ.update(BFCL_PROJECT_ROOT=str(d),OPENAI_API_KEY='local-no-key',OPENAI_BASE_URL=a.base_url);os.environ.pop('OPENAI_DEFAULT_HEADERS',None)
    from bfcl_eval.model_handler.api_inference.openai_response import OpenAIResponsesHandler
    from bfcl_eval.utils import load_dataset_entry,make_json_serializable
    from openai.types.responses import Response
    from core.model_config import MODEL_KEY,SERVING_MODEL
    handler=OpenAIResponsesHandler(SERVING_MODEL,0,MODEL_KEY,True);entry=next(e for e in load_dataset_entry(row['category']) if e['id']==a.task)
    records=[];native=[];turn=0;triggered=False;replacement=[];tok=LocalQwenTokenizer()
    manifest={'task':a.task,'mode':a.mode,'budget':None,'threshold':1000,'threshold_metric':'tool call and return content tokens','trigger_index':boundary,'status':'running','runtime_context':131072,'protocol':'one conversion at threshold, preserve graph and append subsequent messages; no artificial cap', 'base_url':a.base_url,'prefix_source':str(src),'temperature':0,'seed':42}
    def save():
        (d/'manifest.json').write_text(json.dumps(manifest,indent=2));(d/'api.json').write_text(json.dumps(records,ensure_ascii=False))
    def log(r):
        native.append(r)
        with (d/'native.jsonl').open('a') as f:f.write(json.dumps(r,ensure_ascii=False)+'\n')
    add=handler._add_next_turn_user_message_FC
    def add_user(self,data,msg):
        nonlocal turn
        turn+=1;return add(data,msg)
    handler._add_next_turn_user_message_FC=MethodType(add_user,handler)
    query=handler._query_FC
    def query_fc(self,data):
        nonlocal triggered,replacement
        if len(records)==boundary and not triggered:
            triggered=True;history=plain(data['message']);assert history==source[boundary]['request']['input']
            (d/'checkpoint-history.json').write_text(json.dumps(history,ensure_ascii=False))
            if a.mode!='identity':
                memory,graph=make_memory(history,'v1-compact' if a.mode=='v1-compact' else 'v2-compact',tok.count)
                (d/'memory.txt').write_text(memory);(d/'graph.json').write_text(json.dumps(graph,ensure_ascii=False))
                current_user=next(m for m in reversed(history) if m.get('role')=='user')
                data['message']=[*retained_instructions(history),{'role':'assistant','content':memory},current_user]
                replacement=plain(data['message'])
            manifest['triggered']=True;manifest['trigger_turn']=turn;save()
        return query(data)
    handler._query_FC=MethodType(query_fc,handler)
    def generate(**kwargs):
        req=plain(kwargs);i=len(records)
        if i<boundary:
            assert req==source[i]['request'];r=source[i];response=Response.model_validate(r['response']);latency=r['latency'];origin='replay'
        else:
            assert triggered
            if replacement:assert req['input'][:len(replacement)]==replacement
            body={'model':SERVING_MODEL,'messages':chat_messages(req['input']),'tools':to_chat_tools(req['tools']),'temperature':0,'seed':42,'max_tokens':4096,'stream':False,'cache_prompt':True,'chat_template_kwargs':{'enable_thinking':False,'preserve_thinking':False}}
            tokens=count_request(body['messages'],body['tools'],tok,a.base_url)
            if i==boundary:
                manifest['first_input']=tokens
                if a.mode=='identity':assert tokens==row['before']
            if tokens+4096>131072:
                manifest.update(status='budget_exceeded',blocked_input=tokens,blocked_at_index=i)
                (d/'blocked-request.json').write_text(json.dumps(body,ensure_ascii=False));raise BudgetExceeded()
            body['max_tokens']=4096
            log({'event':'request','index':i,'turn':turn,'input_tokens':tokens,'request':body})
            started=time.monotonic();request=urllib.request.Request(a.base_url+'/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(request,timeout=3600) as f:raw=json.load(f)
            latency=time.monotonic()-started;assert raw['usage']['prompt_tokens']==tokens and raw['usage']['total_tokens']<=131072
            log({'event':'response','index':i,'turn':turn,'response':raw});response=response_from_chat(raw,i);origin='live'
        records.append({'request':req,'response':plain(response),'source':origin,'turn':turn,'latency':latency});return response,latency
    handler.generate_with_backoff=generate
    try:
        result,metadata=handler.inference(entry,True,False);metadata=plain(make_json_serializable(metadata))
        handler.write({'id':a.task,'result':result,**metadata},d/'result');(d/'full.json').write_text(json.dumps({'result':plain(result),'metadata':metadata},ensure_ascii=False));manifest['status']='complete'
    except BudgetExceeded:pass
    except BaseException as e:manifest.update(status='error',error=repr(e));save();raise
    finally:tok.close()
    manifest['replayed_requests']=sum(r['source']=='replay' for r in records);manifest['live_requests']=sum(r['source']=='live' for r in records);save()
    if manifest['status']=='complete':
        from core.qwen_official_score import score_run
        score=score_run(d,{'id':a.task,'category':row['category']});manifest['passed']=score['passed'];manifest['scoring']='official BFCL'
    else:manifest['passed']=False;manifest['scoring']='budget failure, not official task evaluation'
    save();print(json.dumps(manifest))
if __name__=='__main__':main()
