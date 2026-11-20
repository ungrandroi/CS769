"""Read-only post-run audit and descriptive paired analysis of a frozen restart.

Run with PYTHONPATH pointing to that experiment's source snapshot. No inference,
source edits, scorer changes, outcome selection, or formal acceptance decisions.
"""
import argparse
from copy import deepcopy
from collections import Counter
import json
from pathlib import Path
import time

import numpy as np

from workflows import diagnostic_controller as checks
from workflows import diagnostic_restart as restart
from workflows.diagnostic_task import prepare_replacement


def interval(left, right, field="passed", ratio=False):
    """Prefix-weighted paired family bootstrap, all repeats/conditions together."""
    families = sorted({str(r["family"]) for r in left})
    groups = [[i for i, r in enumerate(left) if str(r["family"]) == f] for f in families]
    a = np.array([float(r[field]) for r in left])
    b = np.array([float(r[field]) for r in right])
    sizes = np.array([len(g) for g in groups])
    sa = np.array([a[g].sum() for g in groups])
    sb = np.array([b[g].sum() for g in groups])
    draw = np.random.default_rng(20261029).integers(0, len(groups), (10000, len(groups)))
    boot = ((sb[draw].sum(1) / sa[draw].sum(1) - 1) if ratio else
            (sb[draw].sum(1) - sa[draw].sum(1)) / sizes[draw].sum(1))
    estimate = b.mean() / a.mean() - 1 if ratio else (b - a).mean()
    bounds = np.quantile(boot, [.025, .975]).tolist()
    return dict(estimate=float(estimate), interval95=bounds, families=len(groups),
                pairs=len(left), degenerate=bool(bounds[0] == bounds[1]),
                interpretation="Descriptive, unadjusted for multiple comparisons; not untouched-family acceptance.")


def comparison(left, right):
    assert [r["case_id"] for r in left] == [r["case_id"] for r in right]
    return dict(success=interval(left, right), calls=interval(left, right, "emitted_calls"),
                requests=interval(left, right, "model_requests"),
                mean_input_overhead=interval(left, right, "mean_post_input", ratio=True),
                first_input_overhead=interval(left, right, "first_input", ratio=True),
                gains=sum(not a["passed"] and b["passed"] for a, b in zip(left, right)),
                losses=sum(a["passed"] and not b["passed"] for a, b in zip(left, right)))


def visible_output(raw):
    message = raw["choices"][0]["message"]
    return dict(content=message.get("content") or "", calls=[c["function"] for c in message.get("tool_calls", [])])


def normalize_ids(value):
    """Remove generated call identifiers only, preserving roles/content/arguments."""
    result, mapping = deepcopy(value), {}
    def mapped(original):
        if original not in mapping:
            mapping[original] = "CALL_" + str(len(mapping))
        return mapping[original]
    for message in result.get("messages", []):
        for call in message.get("tool_calls", []):
            if "id" in call:
                call["id"] = mapped(call["id"])
        if "tool_call_id" in message:
            message["tool_call_id"] = mapped(message["tool_call_id"])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--model", choices=("qwen", "muse"), required=True)
    args = parser.parse_args()
    root, project = args.root.resolve(), args.project.resolve()
    out = root / "reports/postrun-review-20261029"
    out.mkdir(parents=True, exist_ok=True)
    plan = checks.read(root / "task-split.json")
    snapshot = root / "source_code/restart-v1"
    assert Path(checks.__file__).resolve().is_relative_to(snapshot)
    frozen, release = checks.verify_release(root, snapshot)
    samples = restart.validate_plan(plan, args.model)
    checks.verify_hash_map(checks.read(root / "source-inputs.json"))
    checks.verify_hash_map(checks.read(root / "vendor-pins.json"), snapshot)
    summary = checks.read(root / "reports/summary.json")
    old_rows = {(r["case_id"], r["method"], r["arm"]): r for r in summary["rows"]}
    rows, native, errors = [], {}, []
    reasons, output_caps = Counter(), Counter()
    decoder_outcomes = Counter()
    invalid_json_calls = 0
    request_count = max_output = max_input = 0
    began = time.time()
    expected_paths = set()
    for sample in samples.values():
        for method, arm in restart.BRANCHES:
            path = root / "evaluation" / sample["case_id"] / method / arm
            expected_paths.add(path / "manifest.json")
            try:
                row = restart.validate_job(path, sample, method, arm, plan, project, args.model)
                assert row == old_rows[(sample["case_id"], method, arm)], "Recomputed metrics differ from published summary"
                launch = checks.read(root / "runtime/jobs" / sample["case_id"] / method / arm / "launch.json")
                assert launch["release_sha256"] == release
                assert launch["source_hashes"] == checks.read(snapshot / "hashes.json")
                manifest = checks.read(path / "manifest.json")
                checks.verify_hash_map(manifest["source_sha256"])
                if method != "identity":
                    history = checks.read(path / "checkpoint-history.json")
                    archived = checks.read(Path(sample["source_paths"][method + "-optimized"]) / "memory-metadata.json")
                    replacement, meta = prepare_replacement(history, archived, method, arm, lambda s: 0)
                    saved = checks.read(path / "memory-metadata.json")
                    assert replacement == saved["replacement_messages"], "Actual view differs from recomputed controlled transformation"
                    assert meta["body"] == saved["body"] and meta["view"] == saved["view"]
                req, resp = checks.native_records(path)
                for decoded in checks.read(path / "decoding.json"):
                    if decoded.get("source") == "live" and not decoded.get("decoded"):
                        calls = resp[decoded["index"]]["response"]["choices"][0]["message"].get("tool_calls") or []
                        decoder_outcomes["with_tool_calls" if calls else "without_tool_calls"] += 1
                # Keep only reference pairs for the negative-control drift audit.
                if arm.startswith("refs_"):
                    native[(sample["case_id"], method, arm)] = (req, resp)
                for index, r in resp.items():
                    raw = r["response"]
                    reasons[raw["choices"][0].get("finish_reason")] += 1
                    output_caps[req[index]["request"]["max_tokens"]] += 1
                    max_output = max(max_output, raw["usage"]["completion_tokens"])
                    max_input = max(max_input, raw["usage"]["prompt_tokens"])
                    for call in raw["choices"][0]["message"].get("tool_calls") or []:
                        arguments = call["function"]["arguments"]
                        if isinstance(arguments, str):
                            try:
                                json.loads(arguments)
                            except json.JSONDecodeError:
                                invalid_json_calls += 1
                request_count += len(req)
                rows.append(row)
            except Exception as error:
                errors.append(dict(case_id=sample["case_id"], method=method, arm=arm, error=repr(error)))
        if len(rows) % 190 == 0:
            print(args.model, "verified", len(rows), "errors", len(errors), flush=True)
    actual_paths = set((root / "evaluation").glob("*/*/*/manifest.json"))
    assert actual_paths == expected_paths, "Missing or unexpected branch manifests"
    audit = dict(status="pass" if not errors else "fail", model=args.model, errors=errors,
                 verified_jobs=len(rows), planned_jobs=plan["expected_jobs"], release_sha256=release,
                 source_files=len(checks.read(root / "source-inputs.json")), inference_calls=0,
                 audit_scope="Post-run artifact/configuration/controlled-view audit, using frozen validator plus independently recomputed views and statistics; not a new blind semantic audit or scorer rerun.",
                 verified_live_requests=request_count, output_caps=dict(output_caps), finish_reasons=dict(reasons),
                 maximum_observed_output_tokens=max_output, maximum_observed_input_tokens=max_input,
                 decoder_rejections=dict(decoder_outcomes), invalid_json_function_calls=invalid_json_calls,
                 recomputed_metrics_match_summary=not errors, elapsed_seconds=time.time()-began)
    checks.write(out / "audit.json", audit)
    assert not errors, errors[:3]
    by_arm = {(m, a): sorted([r for r in rows if r["method"] == m and r["arm"] == a], key=lambda r: r["case_id"])
              for m, a in restart.BRANCHES}
    identity = by_arm[("identity", "identity_reference")]
    against_identity = {m+"/"+a: comparison(identity, v) for (m, a), v in by_arm.items() if m != "identity"}
    contrasts = {m+"/"+name: comparison(by_arm[(m, control)], by_arm[(m, treatment)])
                 for m in checks.METHODS for name, (control, treatment) in checks.PAIRS.items()}
    negatives = []
    for m in checks.METHODS:
        for a, b in zip(by_arm[(m, "refs_control")], by_arm[(m, "refs_expanded")]):
            if a["diagnostic_audit"]["expanded_references"]:
                continue
            ka, kb = (a["case_id"], m, "refs_control"), (a["case_id"], m, "refs_expanded")
            ra, oa = native[ka]; rb, ob = native[kb]
            first = min(ra)
            assert ra[first]["request"] == rb[first]["request"], "Negative control changed first native request"
            divergence = []
            for i in sorted(set(ra) & set(rb)):
                if normalize_ids(ra[i]["request"]) == normalize_ids(rb[i]["request"]):
                    if visible_output(oa[i]["response"]) != visible_output(ob[i]["response"]):
                        divergence.append(i)
            negatives.append(dict(method=m, case_id=a["case_id"], same_initial_request=True,
                                  same_input_different_output_indices=divergence,
                                  control_passed=a["passed"], treatment_passed=b["passed"]))
    strata = {}
    for field in ("family", "category"):
        strata[field] = {}
        for value in sorted({str(r[field]) for r in identity}):
            strata[field][value] = {m+"/"+a: dict(n=len(sub), successes=sum(r["passed"] for r in sub))
                                   for (m, a), group in by_arm.items()
                                   for sub in [[r for r in group if str(r[field]) == value]]}
    groups = {m+"/"+a: checks.aggregate(v, len(identity)) for (m, a), v in by_arm.items()}
    checks.write(out / "analysis.json", dict(model=args.model, n=len(identity),
                 families=len({str(r["family"]) for r in identity}), groups=groups,
                 comparisons_to_identity=against_identity, paired_ablations=contrasts,
                 negative_controls=negatives, strata=strata,
                 bootstrap=dict(replicates=10000, seed=20261029, unit="original family",
                                estimand="prefix-weighted, paired; preserve all conditions/repeats within sampled family",
                                interval="two-sided percentile 95%; exploratory, no multiplicity correction",
                                degenerate_policy="Zero-width intervals do not establish population noninferiority"),
                 formal_acceptance=False, rows=rows))
    print(args.model, "AUDIT PASS", len(rows), "outputs", out, flush=True)


if __name__ == "__main__":
    main()
