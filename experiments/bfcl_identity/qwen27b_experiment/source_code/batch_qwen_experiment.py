"""Paired all-Qwen experiment: one generated first turn, three continuations."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Lock
from qwen_official_score import score_run
from research_modes import MODES

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT=ROOT/'experiments/bfcl_identity/qwen27b_experiment'
FAMILIES=(1,3,6,9,10,12,16,25,26,29,37,38,39)
SOURCES=('run_qwen_task.py','qwen_transport.py','qwen_prompt_accounting.py','graph_memory.py','graph_memory_v2.py',
         'graph_memory_replace.py','graph_memory_serialization.py','graph_memory_serialization_target.py',
         'local_qwen_tokenizer.py','research_modes.py','qwen_official_score.py','evaluate_qwen_compact.py','batch_qwen_experiment.py')


def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,d):
    p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n');tmp.replace(p)


def make_plan():
    data=ROOT/'vendor/gorilla/berkeley-function-call-leaderboard/bfcl_eval/data'
    tasks=[]; hashes={}
    for category in ('multi_turn_base','multi_turn_long_context'):
        path=data/f'BFCL_v4_{category}.json';hashes[str(path.relative_to(ROOT))]=sha(path)
        gt=data/'possible_answer'/path.name;hashes[str(gt.relative_to(ROOT))]=sha(gt)
        entries=[json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        selected=sorted([e for e in entries if set(e['involved_classes'])=={'GorillaFileSystem'} and len(e['question'])>=2],key=lambda e:int(e['id'].rsplit('_',1)[1]))
        assert tuple(int(e['id'].rsplit('_',1)[1]) for e in selected)==FAMILIES
        for e in selected:
            graphs=['v1-compact','v2-compact']
            if int(e['id'].rsplit('_',1)[1])%2:graphs.reverse()
            tasks.append({'id':e['id'],'category':category,'family_id':int(e['id'].rsplit('_',1)[1]),'order':['identity',*graphs]})
    return {'model':'Qwen3.8-27B-Q8_0','serving_model':'bfcl-qwen38-27b','modes':list(MODES),'tasks':tasks,
            'planned_records':78,'task_conditions':26,'task_families':13,'samples_per_method':1,
            'protocol':'Identity runs entirely with Qwen; graph branches replay its identical first turn to restore the simulator, then replace history once before user turn 2; no GPT history.',
            'sampling':{'temperature':0,'seed':42,'max_tokens':4096,'context_size':131072,'thinking':False,'cache_prompt':True},
            'parallelism':'Two identical local servers, one task at a time per server; all branches of a task use the same server.',
            'usage':'Report common first-turn usage once as actual compute, plus per-method continuation; also report equivalent whole-trajectory usage per method.',
            'score':'Unmodified official BFCL whole-task evaluator; retain first-turn failures in all three arms; no score-based retries.',
            'data_sha256':hashes,'implementation_sha256':{n:sha(ROOT/'scripts'/n) for n in SOURCES}}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=DEFAULT_OUTPUT);parser.add_argument('--prepare-only',action='store_true');args=parser.parse_args()
    root=args.output.resolve();root.mkdir(parents=True,exist_ok=True);plan=make_plan()
    if (root/'plan.json').exists():assert read(root/'plan.json')==plan,'Frozen plan changed'
    else:
        write(root/'plan.json',plan);(root/'source_code').mkdir()
        for name in SOURCES:(root/'source_code'/name).write_bytes((ROOT/'scripts'/name).read_bytes())
    if args.prepare_only:print('Prepared 26 conditions × 3 methods; no historical GPT input dependencies.');return
    os.environ['PYTHONDONTWRITEBYTECODE']='1';os.environ['BFCL_PROJECT_ROOT']=str(root)
    progress=read(root/'progress.json') if (root/'progress.json').exists() else {'runs':{},'active':{}}
    lock=Lock();progress['status']='running';write(root/'progress.json',progress)
    def worker(worker_id):
        endpoint=f'http://127.0.0.1:{11435+worker_id}/v1'
        for index,task in enumerate(plan['tasks']):
            if index%2!=worker_id:continue
            for mode in task['order']:
                key=task['id']+'/'+mode;directory=root/'tasks'/task['id']/mode
                with lock:progress['active'][str(worker_id)]=key;write(root/'progress.json',progress)
                try:
                    manifest=read(directory/'manifest.json') if (directory/'manifest.json').exists() else {}
                    if manifest.get('status') not in ('complete','not_reached'):
                        if directory.exists() and any(directory.iterdir()):raise RuntimeError(f'Incomplete attempt retained; refusing automatic retry: {directory}')
                        directory.mkdir(parents=True,exist_ok=True)
                        command=[sys.executable,str(ROOT/'scripts/run_qwen_task.py'),'--task-id',task['id'],'--category',task['category'],'--mode',mode,'--output',str(directory),'--base-url',endpoint]
                        if mode!='identity':command+=['--prefix-source',str(root/'tasks'/task['id']/'identity')]
                        with (directory/'runner.log').open('w') as f:subprocess.run(command,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,check=True)
                        manifest=read(directory/'manifest.json')
                    score=score_run(directory,task)
                    with lock:
                        progress['runs'][key]={'status':manifest['status'],'passed':score['passed'],'boundary_reached':manifest['boundary_reached'],'live_requests':manifest['live_requests']}
                        write(root/'progress.json',progress);print(key,progress['runs'][key],flush=True)
                except Exception as error:
                    with lock:progress['status']='infrastructure_error';progress['error']=f'{key}: {error}';write(root/'progress.json',progress)
                    raise
        with lock:progress['active'].pop(str(worker_id),None);write(root/'progress.json',progress)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(worker,i) for i in range(2)]
        for f in futures:f.result()
    assert len(progress['runs'])==78
    progress['status']='complete';write(root/'progress.json',progress)


if __name__=='__main__':main()
