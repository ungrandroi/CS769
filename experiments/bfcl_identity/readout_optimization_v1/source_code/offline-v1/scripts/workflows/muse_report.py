"""Mechanical integrity and descriptive results for Muse; no new inference."""
import argparse
import csv
import json
import hashlib
import importlib
from pathlib import Path
from statistics import mean
from core import optimized_graph
from core.muse_transport import MODEL_NAME, REASONING_POLICY, digest
from workflows.lossless_controller import read,write
from workflows.lossless_report import summarize
from workflows.muse_task import all_paired


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--audit-only',action='store_true');args=parser.parse_args();root=args.root
    plan=read(root/'task-split.json');tasks={t['id']:t for t in plan['tasks']}
    checks=[];rows=[];untriggered=[];requests=[]
    labels=['identity','state-baseline','state-optimized','event-baseline','event-optimized','dedup-baseline','dedup-optimized']
    for f in sorted((root/'evaluation').glob('*/*/*/manifest.json')):
        m=read(f);path=f.parent;label=path.name
        assert m['model']==MODEL_NAME and m['reasoning_policy']==REASONING_POLICY
        assert m['status'] in ('complete','not_triggered')
        if m['status']=='not_triggered':
            assert m['method']!='identity';assert not read(Path(m['identity'])/'manifest.json')['triggered'];continue
        score=read(path/'official-score.json');assert score['passed']==m['passed']
        assert hashlib.sha256((path/score['score_file']).read_bytes()).hexdigest()==score['score_sha256']
        accounts=read(path/'accounting.json');api=read(path/'api.json')
        native=[json.loads(line) for line in (path/'native.jsonl').read_text().splitlines()]
        native_requests={r['index']:r for r in native if r['event']=='request'}
        native_responses={r['index']:r for r in native if r['event']=='response'}
        assert len(native_requests)==len(accounts)==len(native_responses)
        for account in accounts:
            i=account['index'];wire=native_requests[i]['request'];raw=native_responses[i]['response']
            assert raw['model']=='bfcl-muse-glimmer-30b'
            assert raw['usage']['prompt_tokens']==account['input_tokens']
            assert wire['seed']==m['seed']+i*1000003
            assert all('reasoning_content' not in message for message in wire['messages'])
        if m['method']=='identity':
            eligible=[a['index'] for a in accounts if a['working_tokens']>1000 and all_paired(api[a['index']]['request']['input'])]
            assert m.get('trigger_index')==(eligible[0] if eligible else None), 'Incorrect earliest trigger'

        if m['triggered']:
            checkpoint=read(path/'checkpoint-history.json');assert digest(checkpoint)==m['checkpoint_sha256']
            assert m['source_work_tokens']>1000
            if m['method']!='identity':
                identity=read(Path(m['identity'])/'manifest.json');assert identity['checkpoint_sha256']==m['checkpoint_sha256']
                assert checkpoint==read(Path(m['identity'])/'checkpoint-history.json')
                meta=read(path/'memory-metadata.json');payload=meta['graph']
                if meta.get('encoded'):
                    codec=importlib.import_module(meta['codec_module']);assert optimized_graph._same(codec.decode(meta['encoded']),payload)
                builder=importlib.import_module('core.mixed_graph' if m['semantics']=='mixed' else 'core.optimized_graph')
                working=[x for x in checkpoint if x.get('role') not in ('system','developer')]
                assert optimized_graph._same(builder.restore_history(payload),working)
                expected,_=builder.build_memory(working,{'state':'v1-compact','event':'v2-compact','dedup':'v2-dedup'}[m['method']],m['explanation'],len)
                expected_payload=__import__('json').loads(expected[expected.index('{'):]);assert optimized_graph._same(expected_payload,payload)
                memory=(path/'memory.txt').read_text();assert api[m['trigger_index']]['request']['input'][-1]['content']==memory
            post=[a for a in accounts if a['index']>=m['trigger_index']];assert post
            task=tasks[m['task']]
            rows.append(dict(task=m['task'],seed=m['seed'],family=task['family'],category=m['category'],
                semantics=m['semantics'],method=label,passed=m['passed'],first_input=post[0]['input_tokens'],
                mean_post_input=mean(a['input_tokens'] for a in post),peak_input=max(a['input_tokens'] for a in post),
                live_requests=len(post),mean_fixed=mean(a['fixed_tokens'] for a in post),
                mean_working=mean(a['working_tokens'] for a in post)))
        elif m['method']=='identity':untriggered.append(dict(task=m['task'],seed=m['seed'],passed=m['passed']))
        for a in accounts:
            r=api[a['index']];assert r['source']=='live';assert r['response']['usage']['input_tokens']==a['input_tokens']
            assert a['input_tokens']-a['fixed_tokens']==a['working_tokens']
            requests.append(dict(task=m['task'],run_seed=m['seed'],arm=label,**a))
        checks.append(dict(path=str(path),status='pass'))
    write(root/'reports/mechanical-audit.json',dict(status='pass',records=len(checks),checks=checks))
    if args.audit_only:return
    assert len(list((root/'evaluation').glob('*/*/identity/manifest.json')))==600
    assert len(list((root/'evaluation').glob('*/*/*/manifest.json')))==4200
    groups={}
    for semantics in ['all','filesystem','mixed']:
        groups[semantics]={label:summarize([r for r in rows if r['method']==label and (semantics=='all' or r['semantics']==semantics)]) for label in labels}
    write(root/'reports/summary.json',dict(status='automatic_report_pending_independent_review',model=MODEL_NAME,
        groups=groups,rows=rows,untriggered=untriggered,identity_runs=600,
        triggered_prefixes=sum(r['method']=='identity' for r in rows),reasoning_policy=REASONING_POLICY))
    if requests:
        with (root/'reports/per-request-input.csv').open('w') as out:
            writer=csv.DictWriter(out,fieldnames=list(requests[0]));writer.writeheader();writer.writerows(requests)

if __name__=='__main__':main()
