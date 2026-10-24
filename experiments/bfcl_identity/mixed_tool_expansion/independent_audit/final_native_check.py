"""CPU native-template audit only; never calls a completion endpoint."""
from pathlib import Path
import sys,json,urllib.request,time
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'source_code/adapters-v1/scripts'))
from core.local_qwen_tokenizer import LocalQwenTokenizer
read=lambda p:json.loads(p.read_text());tok=LocalQwenTokenizer();cache={};seen=set();samples=[];count=0;runs=0

def render(body):
 request=urllib.request.Request('http://127.0.0.1:11436/apply-template',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
 return json.load(urllib.request.urlopen(request,timeout=30))['prompt']
for mp in sorted((R/'development').glob('*/*/*/manifest.json'))+sorted((R/'evaluation').glob('*/*/*/manifest.json')):
 m=read(mp)
 if m['status']!='complete':continue
 p=mp.parent;runs+=1
 req=[json.loads(s) for s in (p/'native.jsonl').read_text().splitlines() if json.loads(s)['event']=='request']
 for x in req:
  b=x['request'];fixed=[y for y in b['messages'] if y['role'] in ('system','developer')];key=json.dumps([fixed,b['tools']])
  if key not in cache:
   body=dict(b,messages=[*fixed,dict(role='user',content='')]);prompt=render(body);sentinel='<|im_start|>user\n<|im_end|>\n';assert prompt.count(sentinel)==1
   cache[key]=tok.count(prompt.replace(sentinel,'',1),parse_special=True)
  assert cache[key]==x['fixed_tokens'];assert x['working_tokens']==x['input_tokens']-cache[key];count+=1
 for pos,x in [('first',req[0]),('last',req[-1])]:
  key=(p.name,m['category'],pos)
  if key in seen:continue
  seen.add(key);actual=tok.count(render(x['request']),parse_special=True);assert actual==x['input_tokens'];samples.append(dict(path=str(p),index=x['index'],input_tokens=actual,position=pos))
result=dict(status='pass',created_at=time.time(),completed_runs=runs,fixed_configs=len(cache),native_requests=count,full_template_samples=len(samples),samples=samples,provenance=tok.provenance,scope='Read-only apply-template requests and CPU vocabulary-only tokenizer; zero model inference.')
tok.close();(Path(__file__).parent/'final-native-evidence.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ('samples','provenance')},indent=2))
