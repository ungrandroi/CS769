"""Task sets and random interleaving are data, not copied controllers."""
import random

def schedule(task_ids, arms, repeats=1, seed=42):
    if len(task_ids)!=len(set(task_ids)) or len(arms)!=len(set(arms)):raise ValueError('Duplicate task or arm')
    if type(repeats) is not int or repeats<1:raise ValueError('Invalid repeats')
    jobs=[{'task':t,'arm':a,'repeat':r} for t in task_ids for r in range(1,repeats+1) for a in arms]
    random.Random(seed).shuffle(jobs)
    return jobs
