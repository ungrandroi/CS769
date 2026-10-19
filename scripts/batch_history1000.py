import json,subprocess,sys,os,shutil,hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'experiments/bfcl_identity';OUT=BASE/'history1000_eval';OLD=BASE/'qwen27b_experiment'
def read(p):return json.loads(p.read_text())
def write(p,d):
 t=p.with_suffix('.tmp');t.write_text(json.dumps(d,indent=2)+'\n');t.replace(p)
def main():
 plan={'threshold':1000,'modes':['identity','v1-compact','v2-compact'],'checkpoints':read(OUT/'checkpoints.json'),'runtime_context':131072,'max_tokens':4096,'intervention':'one conversion; graph retained plus new suffix until task ends; no 8000 cap','current_user':'kept verbatim after graph at conversion','prefix':'replay same Qwen Identity checkpoint for all methods','sources':read(OLD/'plan.json')['implementation_sha256'].copy()}
 for n in ['run_history1000_task.py','batch_history1000.py','v2_provenance_dedup.py','method_labels.py']:plan['sources'][n]=hashlib.sha256((ROOT/'scripts'/n).read_bytes()).hexdigest()
 (OUT/'source_code').mkdir(exist_ok=True)
 for n,h in plan['sources'].items():
  assert hashlib.sha256((ROOT/'scripts'/n).read_bytes()).hexdigest()==h
  shutil.copyfile(ROOT/'scripts'/n,OUT/'source_code'/n)
 write(OUT/'plan.json',plan);progress={'status':'running','runs':{},'active':{}};lock=Lock();write(OUT/'progress.json',progress);os.environ['PYTHONDONTWRITEBYTECODE']='1'
 def worker(w):
  for i,row in enumerate(plan['checkpoints']['tasks']):
   if i%2!=w:continue
   for mode in plan['modes']:
    key=row['id']+'/'+mode;d=OUT/'tasks'/row['id']/mode
    with lock:progress['active'][str(w)]=key;write(OUT/'progress.json',progress)
    try:
     d.mkdir(parents=True,exist_ok=True)
     with (d/'runner.log').open('w') as f:subprocess.run([sys.executable,str(ROOT/'scripts/run_history1000_task.py'),'--task',row['id'],'--mode',mode,'--base-url',f'http://127.0.0.1:{11435+w}/v1'],stdout=f,stderr=subprocess.STDOUT,check=True)
     m=read(d/'manifest.json')
     with lock:
      progress['runs'][key]={'status':m['status'],'passed':m['passed'],'live_requests':m['live_requests']};write(OUT/'progress.json',progress);print(key,progress['runs'][key],flush=True)
    except BaseException as e:
     with lock:progress.update(status='infrastructure_error',error=f'{key}: {e}');write(OUT/'progress.json',progress)
     raise
  with lock:progress['active'].pop(str(w),None);write(OUT/'progress.json',progress)
 with ThreadPoolExecutor(max_workers=2) as pool:
  fs=[pool.submit(worker,w) for w in range(2)]
  for f in fs:f.result()
 assert len(progress['runs'])==len(plan['checkpoints']['tasks'])*3;progress['status']='complete';write(OUT/'progress.json',progress)
if __name__=='__main__':main()
