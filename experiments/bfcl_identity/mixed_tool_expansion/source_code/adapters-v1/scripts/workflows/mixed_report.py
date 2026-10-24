"""Descriptive paired report for a separately adapted mixed-domain study."""
import argparse
from pathlib import Path
from statistics import mean

from workflows.lossless_analysis import export_requests, paired_statistics, quantiles
from workflows.lossless_controller import read, write
from workflows.lossless_report import summarize


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    plan = read(root / "task-split.json")
    rows, untriggered = [], []
    labels = ("identity", "state-baseline", "state-optimized", "event-baseline",
              "event-optimized", "dedup-baseline", "dedup-optimized")
    for task in plan["tasks"]:
        for seed in plan["seeds"]:
            base = root / "evaluation" / task["id"] / f"seed{seed}"
            identity = read(base / "identity/manifest.json")
            assert identity["status"] == "complete"
            if not identity["triggered"]:
                untriggered.append(dict(task=task["id"], seed=seed, passed=identity["passed"]))
                continue
            for label in labels:
                path = base / label
                manifest = read(path / "manifest.json")
                assert manifest["status"] == "complete" and manifest["triggered"]
                accounts = [row for row in read(path / "accounting.json")
                            if row["index"] >= manifest["trigger_index"]]
                rows.append(dict(
                    task=task["id"], seed=seed, split=task["split"], family=task["family"],
                    category=task["category"], method=label, passed=manifest["passed"],
                    first_input=accounts[0]["input_tokens"],
                    mean_post_input=mean(row["input_tokens"] for row in accounts),
                    peak_input=max(row["input_tokens"] for row in accounts),
                    mean_fixed=mean(row["fixed_tokens"] for row in accounts),
                    mean_working=mean(row["working_tokens"] for row in accounts),
                    live_requests=len(accounts), memory_tokens=manifest.get("memory_tokens"),
                    instruction_tokens=manifest.get("instruction_tokens")))
    groups = {}
    subsets = {
        "all": rows,
        "development_conditions": [row for row in rows if row["split"] == "development"],
        "other_conditions": [row for row in rows if row["split"] != "development"],
        "development_families": [row for row in rows if row["family"] in plan["development_families"]],
        "other_families": [row for row in rows if row["family"] not in plan["development_families"]],
    }
    for category in sorted({task["category"] for task in plan["tasks"]}):
        subsets[category] = [row for row in rows if row["category"] == category]
    for group, subset in subsets.items():
        groups[group] = {label: summarize([row for row in subset if row["method"] == label])
                         for label in labels}
    by = {(row["task"], row["seed"], row["method"]): row for row in rows}
    pairs = []
    for row in rows:
        if row["method"].endswith("-optimized"):
            method = row["method"].split("-")[0]
            baseline = by[(row["task"], row["seed"], method + "-baseline")]
            identity = by[(row["task"], row["seed"], "identity")]
            pairs.append(dict(
                task=row["task"], seed=row["seed"], method=method, family=row["family"],
                category=row["category"], split=row["split"],
                identity_passed=identity["passed"], baseline_passed=baseline["passed"],
                optimized_passed=row["passed"],
                ratio_to_baseline=row["mean_post_input"]/baseline["mean_post_input"],
                ratio_to_identity=row["mean_post_input"]/identity["mean_post_input"]))
    report = dict(
        status="automatic_report_pending_independent_review", groups=groups, rows=rows, pairs=pairs,
        untriggered=untriggered, selection=read(root / "selection.json"),
        scope=dict(families=plan["underlying_families"], task_conditions=len(plan["tasks"]),
                   seeds=plan["seeds"], semantics="mixed-domain-graph-1",
                   prior_filesystem_study_is_separate=True),
        limitations=[
            "Semantic adapters are a separately developed extension, not a lossless encoding change.",
            "Original-format and optimized arms share identical mixed-domain semantic builders.",
            "Encoding choices were fixed from the earlier filesystem study.",
            "Repeated conditions and seeds are clustered within underlying families.",
            "Development conditions, development families and other families are reported separately.",
            "No blanket claim of never-seen tasks is made; these are new relative to the thirteen-family study.",
            "Untriggered cases are excluded from graph-effect estimates, not counted as graph runs.",
            "Equal success counts do not establish per-task preservation or statistical noninferiority.",
        ])
    write(root / "reports/summary.json", report)
    exports = export_requests(root, report)
    statistics = {}
    for group, subset in subsets.items():
        keys = {(row["task"], row["seed"]) for row in subset}
        statistics[group] = {}
        for method in ("state", "event", "dedup"):
            selected = [pair for pair in pairs if pair["method"] == method
                        and (pair["task"], pair["seed"]) in keys]
            if selected:
                statistics[group][method] = dict(
                    versus_baseline=paired_statistics(selected, "baseline_passed"),
                    versus_identity=paired_statistics(selected, "identity_passed"),
                    paired_input_ratio_to_baseline=quantiles([p["ratio_to_baseline"] for p in selected]),
                    paired_input_ratio_to_identity=quantiles([p["ratio_to_identity"] for p in selected]))
    from core.local_qwen_tokenizer import LocalQwenTokenizer
    from core.optimized_graph import dumps
    tokenizer = LocalQwenTokenizer()
    decomposition = []
    try:
        for row in rows:
            if row["method"] == "identity":
                continue
            path = root / "evaluation" / row["task"] / f"seed{row['seed']}" / row["method"]
            meta = read(path / "memory-metadata.json")
            encoded = meta.get("encoded", {})
            rules = {key: value for key, value in encoded.items()
                     if key == "decoding" or key.endswith("_rule")}
            no_rules = {key: value for key, value in encoded.items() if key not in rules}
            decomposition.append(dict(
                task=row["task"], seed=row["seed"], method=row["method"],
                external_instruction_tokens=meta["instruction_tokens"],
                encoded_body_tokens=meta["body_tokens"],
                exact_baseline_body_tokens=meta.get("baseline_body_tokens", meta["body_tokens"]),
                codec_rules_text_tokens=sum(tokenizer.count(value) for value in rules.values()),
                codec_rules_marginal_body_tokens=(tokenizer.count(meta["body"])-tokenizer.count(dumps(no_rules))
                                                  if encoded else 0),
                mean_dynamic_and_wrapper_residual=row["mean_working"]-meta["total_tokens"]))
    finally:
        tokenizer.close()
    write(root / "reports/paired-analysis.json",
          dict(status="automatic_analysis_pending_independent_review", statistics=statistics,
               request_exports=exports, decomposition=decomposition,
               caution="All adapter support markers, domain-delta rules, codec rules and retained external explanation are charged in actual native inputs. Separate text counts are not additive because of token boundaries."))
    print(groups["all"])


if __name__ == "__main__":
    main()
