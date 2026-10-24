"""Pure history-token threshold experiment; no call-count or future filter."""
import argparse
import sys
from pathlib import Path
from core.experiment import ROOT, read, source_hashes, prepare_plan, completed, run_attempt, run_batch
from core.research_modes import MODES
OUT=ROOT/'experiments/bfcl_identity/history1000_eval'

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=OUT)
    parser.add_argument('--checkpoints',type=Path,default=OUT/'checkpoints.json')
    parser.add_argument('--prepare-only',action='store_true')
    args=parser.parse_args();output=args.output.resolve()
    if completed(output):return
    plan={'threshold':1000,'modes':list(MODES),'checkpoints':read(args.checkpoints),'runtime_context':131072,'max_tokens':4096,'intervention':'One conversion; graph retained plus new suffix; no artificial cap','current_user':'kept verbatim after graph','prefix':'replay same Qwen Identity checkpoint','sources':source_hashes()}
    prepare_plan(output,plan,plan['sources'])
    if args.prepare_only:
        print(f"Prepared {len(plan['checkpoints']['tasks'])} checkpoints; no model inference.");return
    def run_one(task,mode,endpoint):
        directory=output/'tasks'/task['id']/mode
        command=[sys.executable,str(ROOT/'scripts/manage.py'),'task','history1000','--task',task['id'],'--mode',mode,'--output-root',str(output),'--base-url',endpoint]
        manifest=run_attempt(directory,command)
        return {'status':manifest['status'],'passed':manifest['passed'],'live_requests':manifest['live_requests']}
    run_batch(output,plan['checkpoints']['tasks'],lambda task:MODES,run_one,len(plan['checkpoints']['tasks'])*len(MODES))
if __name__=='__main__':main()
