"""Paired all-Qwen experiment: one generated first turn, three continuations."""
import argparse
import json
from pathlib import Path
import sys
from core.qwen_official_score import score_run
from core.research_modes import MODES
from core.experiment import sha, source_hashes, prepare_plan, completed, run_attempt, run_batch

ROOT=Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT=ROOT/'experiments/bfcl_identity/qwen27b_experiment'
FAMILIES=(1,3,6,9,10,12,16,25,26,29,37,38,39)
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
            'data_sha256':hashes,'implementation_sha256':source_hashes()}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=DEFAULT_OUTPUT)
    parser.add_argument('--prepare-only',action='store_true')
    args=parser.parse_args();root=args.output.resolve()
    if completed(root):return
    plan=make_plan();prepare_plan(root,plan,plan['implementation_sha256'])
    if args.prepare_only:
        print('Prepared 26 conditions × 3 methods; no model inference.');return
    def run_one(task,mode,endpoint):
        directory=root/'tasks'/task['id']/mode
        command=[sys.executable,str(ROOT/'scripts/manage.py'),'task','baseline','--task-id',task['id'],'--category',task['category'],'--mode',mode,'--output',str(directory),'--base-url',endpoint]
        if mode!='identity':command+=['--prefix-source',str(root/'tasks'/task['id']/'identity')]
        manifest=run_attempt(directory,command);score=score_run(directory,task)
        return {'status':manifest['status'],'passed':score['passed'],'boundary_reached':manifest['boundary_reached'],'live_requests':manifest['live_requests']}
    run_batch(root,plan['tasks'],lambda task:task['order'],run_one,78)

if __name__=='__main__':main()
