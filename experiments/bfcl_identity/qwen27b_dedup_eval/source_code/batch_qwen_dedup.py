import os,sys,json,subprocess,shutil,hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from qwen_official_score import score_run
ROOT=Path(__file__).resolve().parents[1];OLD=ROOT/'experiments/bfcl_identity/qwen27b_experiment';OUT=ROOT/'experiments/bfcl_identity/qwen27b_dedup_eval'
def read(p):return json.loads(p.read_text())
def write(p,d):
    t=p.with_suffix('.tmp');t.write_text(json.dumps(d,indent=2)+'\n');t.replace(p)
def main():
    OUT.mkdir(exist_ok=True);os.environ['PYTHONDONTWRITEBYTECODE']='1';os.environ['BFCL_PROJECT_ROOT']=str(OUT)
    plan=read(OLD/'plan.json');plan['variant']='v2-provenance-dedup';plan['baseline']=str(OLD);plan['planned_records']=26;plan['modes']=['v2-provenance-dedup'];plan['shared_prefix']='Replay frozen all-Qwen Identity first turn; same task-to-GPU assignment as baseline.'
    for n in ['run_qwen_dedup_task.py','v2_provenance_dedup.py','batch_qwen_dedup.py']:
        plan['implementation_sha256'][n]=hashlib.sha256((ROOT/'scripts'/n).read_bytes()).hexdigest()
    if (OUT/'plan.json').exists():assert read(OUT/'plan.json')==plan
    else:
        write(OUT/'plan.json',plan);(OUT/'source_code').mkdir(exist_ok=True)
        for n,h in plan['implementation_sha256'].items():
            assert hashlib.sha256((ROOT/'scripts'/n).read_bytes()).hexdigest()==h
            shutil.copyfile(ROOT/'scripts'/n,OUT/'source_code'/n)
    progress={'status':'running','runs':{},'active':{}};lock=Lock();write(OUT/'progress.json',progress)
    def worker(w):
        for i,task in enumerate(plan['tasks']):
            if i%2!=w:continue
            tid=task['id'];d=OUT/'tasks'/tid
            with lock:progress['active'][str(w)]=tid;write(OUT/'progress.json',progress)
            try:
                if not (d/'manifest.json').exists():
                    d.mkdir(parents=True,exist_ok=True)
                    cmd=[sys.executable,str(ROOT/'scripts/run_qwen_dedup_task.py'),'--task-id',tid,'--category',task['category'],'--mode','v2-compact','--output',str(d),'--prefix-source',str(OLD/'tasks'/tid/'identity'),'--base-url',f'http://127.0.0.1:{11435+w}/v1']
                    with (d/'runner.log').open('w') as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True,cwd=ROOT)
                m=read(d/'manifest.json');assert m['status']=='complete' and m['experimental_variant']=='v2-provenance-dedup'
                score=score_run(d,task)
                with lock:
                    progress['runs'][tid]={'passed':score['passed'],'live_requests':m['live_requests']};write(OUT/'progress.json',progress)
                    print(tid,score['passed'],flush=True)
            except BaseException as e:
                with lock:progress['status']='infrastructure_error';progress['error']=str(e);write(OUT/'progress.json',progress)
                raise
        with lock:progress['active'].pop(str(w),None);write(OUT/'progress.json',progress)
    with ThreadPoolExecutor(max_workers=2) as pool:
        fs=[pool.submit(worker,w) for w in range(2)]
        for f in fs:f.result()
    assert len(progress['runs'])==26;progress['status']='complete';write(OUT/'progress.json',progress)
if __name__=='__main__':main()
