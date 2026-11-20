"""目的和主要功能：读取固定 BFCL 题目、官方答案与完成轮次前缀。

适用范围：工具调用任务的正式输入；原始题目及官方类别由项目 vendor 提供。
"""
from copy import deepcopy
from cs769.base.bootstrap import ensure_bfcl

def load_entry(task, category):
    ensure_bfcl()
    from bfcl_eval.utils import load_dataset_entry
    return next(x for x in load_dataset_entry(category) if x["id"] == task)

def load_truth(task, category):
    ensure_bfcl()
    from bfcl_eval.utils import load_ground_truth_entry
    return next(x["ground_truth"] for x in load_ground_truth_entry(category) if x["id"] == task)

def limited_entry(entry, turn_limit=None):
    """Prefix qualification only; the full dataset and final evaluation remain intact."""
    selected=deepcopy(entry)
    if turn_limit is not None:
        if type(turn_limit) is not int or not 1 <= turn_limit <= len(entry["question"]):
            raise ValueError("Invalid completed-prefix turn count")
        selected["question"]=selected["question"][:turn_limit]
    return selected
