"""Describe actual tool exposure separately from the available tool classes.

Read-only postprocessing: this file never changes adapters, selections or runs.
Run with frozen scripts on PYTHONPATH after the requested split is complete.
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

from core.mixed_observations import tool_spec


ROOT = Path(__file__).resolve().parents[1]
ARMS = (
    "identity", "state-baseline", "state-optimized", "event-baseline",
    "event-optimized", "dedup-baseline", "dedup-optimized",
)


def read(path):
    return json.loads(path.read_text())


def calls_from_result(value):
    """BFCL result contains nested lists, call dictionaries, and final strings."""
    if isinstance(value, list):
        for child in value:
            yield from calls_from_result(child)
    elif isinstance(value, dict):
        # Every dictionary here is a decoded tool call; arguments remain opaque.
        yield from value


def summarize(rows):
    groups = defaultdict(list)
    for row in rows:
        groups["all"].append(row)
        groups["prefix:" + row["prefix_exposure"]].append(row)
        groups["available:" + "+".join(row["available_partner_domains"])].append(row)
        groups["category:" + row["category"]].append(row)
    summary = {}
    for label, members in sorted(groups.items()):
        triggered = [row for row in members if row["triggered"]]
        item = {
            "identity_runs": len(members),
            "underlying_families": len({row["family"] for row in members}),
            "triggered_runs": len(triggered),
            "nonfilesystem_prefix_runs": sum(
                row["prefix_exposure"] != "filesystem_only" for row in triggered),
            "nonfilesystem_any_identity_runs": sum(
                any(domain != "GorillaFileSystem" for domain in row["identity_calls"])
                for row in members),
            "paired_triggered_success": {
                arm: sum(row["outcomes"][arm] for row in triggered) for arm in ARMS
            },
        }
        summary[label] = item
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=("development", "evaluation"), required=True)
    args = parser.parse_args()
    task_metadata = {row["id"]: row for row in read(ROOT / "inventory.json")["tasks"]}
    identities = sorted((ROOT / args.split).glob("*/seed*/identity/manifest.json"))
    expected = 24 if args.split == "development" else 444
    if len(identities) != expected:
        raise RuntimeError(f"Refuse partial analysis: {len(identities)} / {expected} Identity runs")
    rows = []
    for path in identities:
        manifest = read(path)
        if manifest["status"] != "complete":
            raise RuntimeError(f"Incomplete Identity: {path}")
        available = task_metadata[manifest["task"]]
        triggered = manifest["triggered"]
        history = read(path.parent / "checkpoint-history.json") if triggered else []
        prefix = Counter(tool_spec(message["name"])["domain"] for message in history
                         if message.get("type") == "function_call")
        methods = Counter(message["name"] for message in history
                          if message.get("type") == "function_call")
        actual = Counter(tool_spec(name)["domain"] for name in calls_from_result(
            read(path.parent / "full.json")["result"]))
        partners = sorted(set(prefix) - {"GorillaFileSystem"})
        outcomes = {"identity": bool(manifest["passed"])}
        for arm in ARMS[1:]:
            other = read(path.parent.parent / arm / "manifest.json")
            if triggered:
                if other["status"] != "complete":
                    raise RuntimeError(f"Incomplete graph branch: {path.parent.parent / arm}")
                if other["checkpoint_sha256"] != manifest["checkpoint_sha256"]:
                    raise RuntimeError(f"Unpaired branch: {path.parent.parent / arm}")
                outcomes[arm] = bool(other["passed"])
            else:
                if other["status"] != "not_triggered":
                    raise RuntimeError(f"Unexpected untriggered branch: {other['status']}")
                outcomes[arm] = None
        rows.append({
            "task": manifest["task"], "family": available["family"],
            "category": available["category"], "seed": manifest["seed"],
            "available_partner_domains": sorted(
                set(available["involved_classes"]) - {"GorillaFileSystem"}),
            "triggered": triggered,
            "prefix_exposure": ("+".join(partners) if partners else "filesystem_only")
                               if triggered else "not_triggered",
            "prefix_calls": dict(sorted(prefix.items())),
            "prefix_methods": dict(sorted(methods.items())),
            "identity_calls": dict(sorted(actual.items())),
            "outcomes": outcomes,
        })
    output = {
        "split": args.split, "scope": "actual visible calls; no simulator-state inspection",
        "caveats": [
            "Available partner classes do not establish actual non-filesystem memory exposure.",
            "No model or adapter selection uses this postprocessing.",
            "Only triggered paired outcomes belong to graph comparisons.",
            "A domain call can be an error or read-only observation; exposure is not proof of every semantic field.",
        ],
        "summary": summarize(rows), "rows": rows,
    }
    target = ROOT / "reports" / f"{args.split}-domain-exposure.json"
    target.write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(output["summary"]["all"], indent=2))


if __name__ == "__main__":
    main()
