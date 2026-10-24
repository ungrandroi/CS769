"""Post-evaluation strata, without filtering the primary paired denominator."""
import json
import re
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text())


def error_turns(score):
    """Sufficient evidence only; unrecognized/terminated errors remain unknown."""
    turns = []
    for diagnostic in score.get("diagnostics", []):
        error = diagnostic.get("error", {})
        if not isinstance(error, dict):
            continue
        kind = error.get("error_type")
        if kind == "multi_turn:instance_state_mismatch":
            execution = error.get("execution_result")
            if isinstance(execution, list):
                turns.append(len(execution))
        elif kind == "multi_turn:empty_turn_model_response":
            execution = error.get("details", {}).get("execution_result")
            if isinstance(execution, list):
                turns.append(len(execution))
        elif kind == "multi_turn:execution_response_mismatch":
            match = re.search(r"for turn (\d+)", error.get("error_message", ""))
            if match:
                turns.append(int(match.group(1)) + 1)
    return turns


def summarize(rows):
    return dict(n=len(rows), passed=sum(row["passed"] for row in rows),
                first_input=mean(row["first_input"] for row in rows),
                mean_post_input=mean(row["mean_post_input"] for row in rows),
                mean_working_input=mean(row["mean_working"] for row in rows))


def main():
    report = read(ROOT / "reports/summary.json")
    rows = report["rows"]
    prefix = []
    for row in rows:
        if row["method"] != "identity":
            continue
        path = ROOT / "evaluation" / row["task"] / f"seed{row['seed']}" / "identity"
        manifest = read(path / "manifest.json")
        turns = error_turns(read(path / "official-score.json"))
        prefix.append(dict(
            task=row["task"], seed=row["seed"], identity_passed=row["passed"],
            trigger_turn_1based=manifest["trigger_turn"],
            diagnosed_error_turns_1based=turns,
            diagnosed_failure_in_completed_prefix_turn=any(
                turn < manifest["trigger_turn"] for turn in turns)))
    labels = sorted({row["method"] for row in rows})
    categories = sorted({row["task"].rsplit("_", 1)[0] for row in rows})
    category_groups = {
        category: {label: summarize([row for row in rows
                                   if row["method"] == label
                                   and row["task"].rsplit("_", 1)[0] == category])
                   for label in labels}
        for category in categories
    }
    development_families = {3, 9, 37}
    family_groups = {
        name: {label: summarize([row for row in rows
                               if row["method"] == label
                               and (int(row["task"].rsplit("_", 1)[1]) in development_families)
                               == is_development])
               for label in labels}
        for name, is_development in [("development_families", True),
                                    ("other_historically_seen_families", False)]
    }
    diagnosed = {(row["task"], row["seed"]) for row in prefix
                 if row["diagnosed_failure_in_completed_prefix_turn"]}
    output = dict(
        primary_denominator_unchanged=len(prefix),
        sufficient_prefix_failure_diagnoses=len(diagnosed),
        prefix_rows=prefix, categories=category_groups, family_groups=family_groups,
        diagnosed_prefix_subset={label: summarize([row for row in rows
                                                  if row["method"] == label
                                                  and (row["task"], row["seed"]) in diagnosed])
                                 for label in labels} if diagnosed else {},
        limitations=[
            "This is post-evaluation descriptive analysis, not candidate selection.",
            "A diagnosed earlier completed-turn error predates conversion; absence of such evidence does not certify a valid prefix.",
            "The main 120-pair denominator is unchanged. No failed cases are discarded.",
            "Development-family strata include all four conditions for families 3, 9, and 37; the primary report's development stratum includes only the six exact development task-condition instances.",
            "All 13 families were historically seen. Other families here are not an unseen-task blind test.",
        ])
    destination = ROOT / "reports/final-diagnostics.json"
    destination.write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(dict(triggered=len(prefix), known_prefix_failures=len(diagnosed),
                         output=str(destination)), indent=2))


if __name__ == "__main__":
    main()
