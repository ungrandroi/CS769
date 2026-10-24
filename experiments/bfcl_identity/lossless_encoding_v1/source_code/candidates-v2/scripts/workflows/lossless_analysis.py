"""Post-inference input decomposition and paired, family-clustered uncertainty.

This analysis is separate from the frozen inference implementation. It never
changes, reruns, or selects model trajectories.
"""
import argparse
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


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,required=True)
    args=parser.parse_args()
    root=args.root.resolve()
    assert read(root/'runtime/status.json')['status']=='inference_complete_pending_independent_audit'
    report=read(root/'reports/summary.json')
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
        decomposition_note='Native fixed_tokens is exact. Body and external text are tokenized separately; BPE boundaries and dynamic message wrappers remain in the explicit residual. Inline codec rules are counted in body; marginal deletion estimates include JSON keys and boundary effects. Components are not falsely asserted to be additive.',
        caution='No inference or candidate selection is performed by this report. Zero external instructions does not mean zero inline explanation.'))
    print(json.dumps(statistics,indent=2))


if __name__=='__main__':
    main()
