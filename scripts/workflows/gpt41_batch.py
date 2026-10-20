"""Paired all-GPT experiment: one generated first turn, three continuations."""
import argparse
from pathlib import Path
import sys
from core.qwen_official_score import score_run
from core.model_config import azure_model_key
from core.experiment import prepare_plan, completed, run_attempt, run_batch
from workflows.baseline_batch import make_plan as make_baseline_plan

ROOT=Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT=ROOT/'experiments/bfcl_identity/gpt41_experiment'


def make_plan(deployment, only=(), reasoning_effort=None):
    plan=make_baseline_plan()
    sampling=({'reasoning_effort':reasoning_effort,'max_completion_tokens':16384,'seed':42} if reasoning_effort
              else {'temperature':0,'seed':42,'max_tokens':4096})
    tasks=[t for t in plan['tasks'] if not only or t['id'] in only]
    assert len(tasks)==(len(set(only)) if only else 26), 'Unknown task ID in --only'
    plan.update(model=deployment,serving_model=deployment,registry_name=azure_model_key(deployment),tasks=tasks,
                planned_records=3*len(tasks),task_conditions=len(tasks),task_families=len({t['family_id'] for t in tasks}),
                protocol='Identity runs entirely with the Azure deployment; graph branches replay its identical first turn to restore the simulator, then replace history once before user turn 2. Same tasks, branch order and graph builders as the all-Qwen baseline.',
                sampling=sampling,
                memory_tokenizer='tiktoken o200k_base (selects the lossless compact string dictionary only)',
                parallelism='Two workers against one Azure deployment; all branches of a task run sequentially on one worker.')
    return plan


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=DEFAULT_OUTPUT)
    parser.add_argument('--deployment',default='gpt-4.1')
    parser.add_argument('--reasoning-effort',choices=('minimal','low','medium','high'))
    parser.add_argument('--only',nargs='*',default=[],help='Restrict to these task IDs (smoke runs)')
    parser.add_argument('--workers',type=int,default=2)
    parser.add_argument('--prepare-only',action='store_true')
    args=parser.parse_args();root=args.output.resolve()
    if completed(root):return
    plan=make_plan(args.deployment,args.only,args.reasoning_effort);prepare_plan(root,plan,plan['implementation_sha256'])
    if args.prepare_only:
        print(f"Prepared {plan['task_conditions']} conditions × 3 methods; no model inference.");return
    def run_one(task,mode,_endpoint):
        directory=root/'tasks'/task['id']/mode
        command=[sys.executable,str(ROOT/'scripts/manage.py'),'task','gpt41','--task-id',task['id'],'--category',task['category'],
                 '--mode',mode,'--output',str(directory),'--deployment',args.deployment]
        if args.reasoning_effort:command+=['--reasoning-effort',args.reasoning_effort]
        if mode!='identity':command+=['--prefix-source',str(root/'tasks'/task['id']/'identity')]
        manifest=run_attempt(directory,command);score=score_run(directory,task,plan['registry_name'])
        return {'status':manifest['status'],'passed':score['passed'],'boundary_reached':manifest['boundary_reached'],'live_requests':manifest['live_requests']}
    run_batch(root,plan['tasks'],lambda task:task['order'],run_one,plan['planned_records'],workers=args.workers)

if __name__=='__main__':main()
