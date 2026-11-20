"""First-turn paired continuation using event-graph provenance deduplication."""
import argparse
import sys
from pathlib import Path
from core.experiment import ROOT, read, source_hashes, prepare_plan, completed, run_attempt, run_batch
from core.qwen_official_score import score_run
OLD=ROOT/'experiments/bfcl_identity/qwen27b_experiment'
OUT=ROOT/'experiments/bfcl_identity/qwen27b_dedup_eval'

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=OUT)
    parser.add_argument('--prepare-only',action='store_true')
    args=parser.parse_args();output=args.output.resolve()
    if completed(output):return
    plan=read(OLD/'plan.json')
    plan.update(variant='v2-provenance-dedup',baseline=str(OLD),planned_records=26,modes=['v2-dedup'],shared_prefix='Same frozen Qwen Identity first turn',implementation_sha256=source_hashes())
    prepare_plan(output,plan,plan['implementation_sha256'])
    if args.prepare_only:
        print('Prepared 26 dedup continuations; no model inference.');return
    def run_one(task,mode,endpoint):
        directory=output/'tasks'/task['id']
        command=[sys.executable,str(ROOT/'scripts/manage.py'),'task','dedup','--task-id',task['id'],'--category',task['category'],'--mode','v2-compact','--output',str(directory),'--prefix-source',str(OLD/'tasks'/task['id']/'identity'),'--base-url',endpoint]
        manifest=run_attempt(directory,command)
        assert manifest['status']=='complete' and manifest['experimental_variant']=='v2-provenance-dedup'
        score=score_run(directory,task)
        return {'status':manifest['status'],'passed':score['passed'],'live_requests':manifest['live_requests']}
    run_batch(output,plan['tasks'],lambda task:['v2-dedup'],run_one,26)
if __name__=='__main__':main()
