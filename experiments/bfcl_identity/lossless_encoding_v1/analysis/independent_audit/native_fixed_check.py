"""CPU-only template/tokenizer audit. Never calls a completion endpoint."""
import json,sys,urllib.request,hashlib,time
from pathlib import Path
R=Path(__file__).resolve().parents[2];sys.path.insert(0,str(R/'source_code/candidates-v2/scripts'))
from core.local_qwen_tokenizer import LocalQwenTokenizer
read=lambda p:json.loads(p.read_text())
tok=LocalQwenTokenizer();fixed_cache={};count=0;samples=[];seen=set();marginals=[]
def render(body):
 request=urllib.request.Request('http://127.0.0.1:11436/apply-template',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
 return json.load(urllib.request.urlopen(request,timeout=30))['prompt']
for phase in ['development','evaluation']:
 for mp in sorted((R/phase).glob('*/*/*/manifest.json')):
  m=read(mp)
  if m['status']!='complete':continue
  path=mp.parent
  requests=[json.loads(s) for s in (path/'native.jsonl').read_text().splitlines() if json.loads(s)['event']=='request']
  for req in requests:
   b=req['request'];fixed=[x for x in b['messages'] if x.get('role') in ('system','developer')]
   key=json.dumps([fixed,b['tools']],sort_keys=True)
   if key not in fixed_cache:
    fb=dict(b,messages=[*fixed,dict(role='user',content='')]);prompt=render(fb)
    sentinel='<|im_start|>user\n<|im_end|>\n';assert prompt.count(sentinel)==1
    fixed_cache[key]=tok.count(prompt.replace(sentinel,'',1),parse_special=True)
   assert req['fixed_tokens']==fixed_cache[key]
   assert req['working_tokens']==req['input_tokens']-fixed_cache[key]
   count+=1
  for pos,req in [('first',requests[0]),('last',requests[-1])]:
   key=(phase,m['category'],path.name,pos)
   if key in seen:continue
   seen.add(key); prompt=render(req['request']);actual=tok.count(prompt,parse_special=True)
   assert actual==req['input_tokens']
   samples.append(dict(path=str(path),index=req['index'],position=pos,input_tokens=actual))
   if pos=='first' and (path/'memory-metadata.json').exists():
    md=read(path/'memory-metadata.json');encoded=md.get('encoded')
    if encoded:
     rules={k:v for k,v in encoded.items() if k=='decoding' or k.endswith('_rule')}
     pruned={k:v for k,v in encoded.items() if k not in rules}
     body=json.dumps(pruned,ensure_ascii=False,separators=(',',':'),allow_nan=False)
     text=md['instruction']+'\n'+body if md['instruction'] else body
     changed=json.loads(json.dumps(req['request']));changed['messages'][-1]['content']=text
     reduced=tok.count(render(changed),parse_special=True)
     marginals.append(dict(path=str(path),native_input_tokens=actual,native_input_without_inline_rules_tokens=reduced,marginal_inline_rules_tokens=actual-reduced,external_instruction_tokens=md['instruction_tokens'],rules=list(rules)))
result=dict(status='pass',time=time.time(),request_fixed_counts_checked=count,distinct_fixed_configurations=len(fixed_cache),native_full_render_samples=len(samples),samples=samples,native_inline_rule_marginal_samples=marginals,provenance=tok.provenance,scope='Read-only /apply-template endpoint and vocabulary-only CPU tokenization; no inference requested. Native usage checked independently in final_check.py.')
tok.close();(Path(__file__).parent/'native-fixed-evidence.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ['samples','native_inline_rule_marginal_samples','provenance']}))
