"""Post-inference input decomposition and paired, family-clustered uncertainty.

This analysis is separate from the frozen inference implementation. It never
changes, reruns, or selects model trajectories.
"""
import argparse
import csv
import json
from math import comb
from pathlib import Path
import random
from statistics import mean
from workflows.lossless_controller import read, write


def quantiles(values):
    ordered=sorted(values)
    def at(q):
        position=(len(ordered)-1)*q
        low=int(position)
        return ordered[low]+(ordered[min(low+1,len(ordered)-1)]-ordered[low])*(position-low)
    return {str(q):at(q) for q in (0,.25,.5,.75,.9,.95,1)}


def paired_statistics(pairs, control, candidate='optimized_passed'):
    gains=sum(p[candidate] and not p[control] for p in pairs)
    losses=sum(p[control] and not p[candidate] for p in pairs)
    discordant=gains+losses
    pvalue=min(1,2*sum(comb(discordant,k) for k in range(min(gains,losses)+1))/2**discordant) if discordant else 1
    families={}
    for row in pairs:
        family=int(row['task'].rsplit('_',1)[1])
        families.setdefault(family,[]).append(int(row[candidate])-int(row[control]))
    names=list(families)
    rng=random.Random(574941)
    bootstrap=[]
    for _ in range(10000):
        picked=[rng.choice(names) for _ in names]
        values=[value for name in picked for value in families[name]]
        bootstrap.append(mean(values))
    bootstrap.sort()
    return dict(n=len(pairs),families=len(names),gains=gains,losses=losses,
                unchanged=len(pairs)-discordant,
                success_difference=(gains-losses)/len(pairs),
                descriptive_exact_mcnemar_p=pvalue,
                family_cluster_bootstrap_95_interval=[bootstrap[249],bootstrap[9749]],
                bootstrap_seed=574941,bootstrap_replicates=10000,
                caveat='Small number of historically seen families; interval is descriptive, not a noninferiority proof.')


def export_requests(root, report):
    """Expose every actual request without falsely aligning diverged trajectories."""
    requests=[]
    turns=[]
    first=[]
    for row in report['rows']:
        path=root/'evaluation'/row['task']/f"seed{row['seed']}"/row['method']
        manifest=read(path/'manifest.json')
        accounting=[a for a in read(path/'accounting.json') if a['index']>=manifest['trigger_index']]
        groups={}
        for ordinal, account in enumerate(accounting,1):
            item=dict(task=row['task'],seed=row['seed'],split=row['split'],method=row['method'],
                      post_conversion_request=ordinal,request_index=account['index'],
                      user_turn=account['turn'],input_tokens=account['input_tokens'],
                      fixed_tokens=account['fixed_tokens'],working_tokens=account['working_tokens'])
            requests.append(item)
            groups.setdefault(account['turn'],[]).append(account)
        for turn, accounts in groups.items():
            turns.append(dict(task=row['task'],seed=row['seed'],split=row['split'],method=row['method'],
                              user_turn=turn,requests=len(accounts),
                              first_input_tokens=accounts[0]['input_tokens'],
                              mean_input_tokens=mean(a['input_tokens'] for a in accounts),
                              max_input_tokens=max(a['input_tokens'] for a in accounts),
                              mean_working_tokens=mean(a['working_tokens'] for a in accounts)))
    by={(r['task'],r['seed'],r['method']):r for r in requests if r['post_conversion_request']==1}
    for key, item in by.items():
        if not key[2].endswith('-optimized'):
            continue
        baseline=by[(key[0],key[1],key[2].replace('-optimized','-baseline'))]
        identity=by[(key[0],key[1],'identity')]
        first.append(dict(task=key[0],seed=key[1],method=key[2],
                          identity_input=identity['input_tokens'],baseline_input=baseline['input_tokens'],
                          optimized_input=item['input_tokens'],
                          identity_working=identity['working_tokens'],baseline_working=baseline['working_tokens'],
                          optimized_working=item['working_tokens'],
                          input_ratio_to_identity=item['input_tokens']/identity['input_tokens'],
                          input_ratio_to_baseline=item['input_tokens']/baseline['input_tokens'],
                          working_ratio_to_identity=item['working_tokens']/identity['working_tokens'],
                          working_ratio_to_baseline=item['working_tokens']/baseline['working_tokens']))
    for name, rows in (('per-request-input.csv',requests),('per-user-turn-input.csv',turns),
                       ('paired-first-request-input.csv',first)):
        assert rows
        destination=root/'reports'/name
        with destination.open('w',newline='') as handle:
            writer=csv.DictWriter(handle,fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    return dict(requests=len(requests),turns=len(turns),paired_first_requests=len(first),
                caveat='Only the first post-conversion request has a common continuation boundary. Later request ordinals are descriptive, not semantically aligned actions. User-turn rows cover actual post-conversion requests only.')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,required=True)
    args=parser.parse_args()
    root=args.root.resolve()
    assert read(root/'runtime/status.json')['status']=='inference_complete_pending_independent_audit'
    report=read(root/'reports/summary.json')
    request_exports=export_requests(root,report)
    plan=read(root/'task-split.json')
    task_split={t['id']:t['split'] for t in plan['tasks']}
    from core.local_qwen_tokenizer import LocalQwenTokenizer
    from core.optimized_graph import dumps
    tokenizer=LocalQwenTokenizer()
    rows=[]
    try:
        for row in report['rows']:
            path=root/'evaluation'/row['task']/f"seed{row['seed']}"/row['method']
            metadata=read(path/'memory-metadata.json') if (path/'memory-metadata.json').exists() else None
            item=dict(row)
            if metadata:
                encoded=metadata.get('encoded')
                if encoded:
                    rules={k:v for k,v in encoded.items() if k=='decoding' or k.endswith('_rule')}
                    no_rules={k:v for k,v in encoded.items() if k not in rules}
                    item.update(
                        codec_rules_text_tokens=sum(tokenizer.count(v) for v in rules.values()),
                        codec_rules_marginal_body_tokens=tokenizer.count(metadata['body'])-tokenizer.count(dumps(no_rules)),
                        codec_rules_fields=list(rules),
                        external_instruction_tokens=metadata['instruction_tokens'],
                        encoded_body_tokens=metadata['body_tokens'],
                        exact_baseline_body_tokens=metadata['baseline_body_tokens'])
                else:
                    item.update(codec_rules_text_tokens=0,codec_rules_marginal_body_tokens=0,
                                external_instruction_tokens=metadata['instruction_tokens'],
                                encoded_body_tokens=metadata['body_tokens'])
                item['mean_dynamic_and_wrapper_residual']=row['mean_working']-metadata['total_tokens']
            rows.append(item)
    finally:
        tokenizer.close()
    statistics={}
    for split in ('all','development','nondevelopment'):
        statistics[split]={}
        for method in ('state','event','dedup'):
            pairs=[p for p in report['pairs'] if p['method']==method and
                   (split=='all' or (task_split[p['task']]=='development')==(split=='development'))]
            if not pairs:
                continue
            statistics[split][method]=dict(
                versus_baseline=paired_statistics(pairs,'baseline_passed'),
                versus_identity=paired_statistics(pairs,'identity_passed'),
                paired_input_ratio_to_baseline=quantiles([p['ratio_to_baseline'] for p in pairs]),
                paired_input_ratio_to_identity=quantiles([p['ratio_to_identity'] for p in pairs]))
    write(root/'reports/paired-analysis.json',dict(
        status='automatic_analysis_pending_independent_review',rows=rows,statistics=statistics,
        request_exports=request_exports,
        decomposition_note='Native fixed_tokens is exact. Body and external text are tokenized separately; BPE boundaries and dynamic message wrappers remain in the explicit residual. Inline codec rules are counted in body; marginal deletion estimates include JSON keys and boundary effects. Components are not falsely asserted to be additive.',
        caution='No inference or candidate selection is performed by this report. Zero external instructions does not mean zero inline explanation.'))
    print(json.dumps(statistics,indent=2))


if __name__=='__main__':
    main()
