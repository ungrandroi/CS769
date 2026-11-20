"""Prepare pure 1000-token checkpoints from existing Qwen Identity histories; no inference."""
import json
from pathlib import Path
from core.local_qwen_tokenizer import LocalQwenTokenizer
ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'experiments/bfcl_identity'
OUT=BASE/'history1000_eval'

def history_size(history,count):
    calls=[m for m in history if m.get('type')=='function_call']
    returns=[m for m in history if m.get('type')=='function_call_output']
    ids=[m['call_id'] for m in calls]
    output_ids=[m['call_id'] for m in returns]
    if len(set(ids))!=len(ids) or len(set(output_ids))!=len(output_ids) or set(ids)!=set(output_ids):
        return None
    tokens=sum(count(m['name']+'('+m['arguments']+')') for m in calls)+sum(count(m['output']) for m in returns)
    return tokens,len(calls)

def first_checkpoint(tape,count,threshold=1000):
    for i,row in enumerate(tape):
        size=history_size(row['request']['input'],count)
        if size is not None and size[0]>=threshold:
            return dict(trigger_index=i,history_tokens=size[0],calls=size[1],returns=size[1],before=row['response']['usage']['input_tokens'])
    return None

def main():
    assert not (OUT/'plan.json').exists(), 'Do not alter checkpoints after a batch starts'
    tasks=[];untriggered=[]
    with LocalQwenTokenizer() as tok:
        for task in json.loads((BASE/'qwen27b_experiment/plan.json').read_text())['tasks']:
            tid=task['id'];p=BASE/'qwen27b_experiment/tasks'/tid/'identity'/f'{tid}.api.json'
            point=first_checkpoint(json.loads(p.read_text()),tok.count)
            row={'id':tid,'category':task['category']}
            if point is None:untriggered.append({**row,'reason':'No next-request checkpoint reached 1000 paired tool-content tokens'})
            else:tasks.append({**row,**point})
    OUT.mkdir(exist_ok=True)
    result={'status':'prepared_not_run','threshold':1000,'metric':'Sum of standalone Qwen tokens for call name(arguments) and raw returns once; excludes tools, user/assistant prose and wrappers','selection':'First complete paired checkpoint reaching threshold; no minimum calls; no future-call or success filter','tasks':tasks,'untriggered':untriggered}
    (OUT/'checkpoints.json').write_text(json.dumps(result,indent=2)+'\n')
    print(f'Prepared {len(tasks)} triggered, {len(untriggered)} untriggered; no model inference performed.')
if __name__=='__main__':main()
