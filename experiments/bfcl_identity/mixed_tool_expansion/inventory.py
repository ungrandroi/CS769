"""Inventory pinned task metadata only; no reference answers or inference."""
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[2]
CATEGORIES = ("base", "long_context", "miss_func", "miss_param")


def main():
    data = PROJECT / "vendor/gorilla/berkeley-function-call-leaderboard/bfcl_eval/data"
    previous = json.loads((ROOT.parent / "lossless_encoding_v1/task-split.json").read_text())
    old_families = {int(task["id"].rsplit("_", 1)[1]) for task in previous["tasks"]}
    categories = {}
    tasks = []
    by_family = {}
    for category in CATEGORIES:
        path = data / f"BFCL_v4_multi_turn_{category}.json"
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        file_rows = [row for row in rows if "GorillaFileSystem" in row["involved_classes"]]
        mixed = [row for row in file_rows if len(row["involved_classes"]) > 1]
        counts = Counter(tool for row in mixed for tool in row["involved_classes"]
                         if tool != "GorillaFileSystem")
        categories[category] = dict(
            source=str(path.relative_to(PROJECT)),
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            all_tasks=len(rows), filesystem_involving=len(file_rows),
            filesystem_only=len(file_rows)-len(mixed), mixed=len(mixed),
            partner_class_counts=dict(sorted(counts.items())),
            mixed_families=[int(row["id"].rsplit("_", 1)[1]) for row in mixed])
        for row in mixed:
            family = int(row["id"].rsplit("_", 1)[1])
            assert family not in old_families
            item = dict(id=row["id"], category=f"multi_turn_{category}",
                        family=family, involved_classes=row["involved_classes"],
                        user_turns=len(row["question"]),
                        excluded_functions=row.get("excluded_function", []))
            tasks.append(item)
            by_family.setdefault(family, {})[category] = tuple(sorted(row["involved_classes"]))
    assert len(by_family) == 37 and len(tasks) == 148
    assert all(len(conditions) == 4 and len(set(conditions.values())) == 1
               for conditions in by_family.values())
    output = dict(
        status="inventory_complete_semantic_coverage_audit_pending",
        categories=categories, tasks=tasks,
        underlying_mixed_families=len(by_family),
        task_condition_instances=len(tasks),
        same_family_classes_across_conditions=True,
        disjoint_from_current_thirteen_families=True,
        current_families=sorted(old_families),
        proposed_three_seed_identity_runs=len(tasks)*3,
        proposed_maximum_graph_branches=len(tasks)*3*6,
        caveats=[
            "No model inference, official answers, or future tool outputs were used.",
            "New means outside the current thirteen-family study, not guaranteed never inspected in earlier project history.",
            "Partner class counts are family counts, not distinct tool functions.",
            "Model evaluation has not started. Graph semantic coverage and any adapters need separate development, audit, and freezing.",
        ])
    (ROOT / "inventory.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps({key: output[key] for key in
                      ("status", "underlying_mixed_families", "task_condition_instances",
                       "proposed_three_seed_identity_runs", "proposed_maximum_graph_branches")},
                     indent=2))


if __name__ == "__main__":
    main()
