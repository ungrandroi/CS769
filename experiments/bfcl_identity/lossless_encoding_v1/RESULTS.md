# Lossless graph encoding: completed results

Inference, automatic checks and the [independent final audit](analysis/independent_audit/final.md)
are complete. The codecs preserve their original delivered graph payloads
exactly, but the practical input-size objective is only partly met.

## Setup

Local **Qwen3.8-27B-Q8_0** evaluated 52 conditions: 13 historically seen
GorillaFileSystem task families under `multi_turn_base`, `multi_turn_long_context`,
`multi_turn_miss_func` and `multi_turn_miss_param`. These use simulated file
tools, not a real Bash shell. Three fresh seeds (4409, 5519, 6637) produce
156 Identity runs, not 156 independent tasks.

Each graph branch shares its Identity run's exact prefix. Conversion occurs
once, at the earliest complete tool-call/return boundary where native working
input exceeds 1,000 tokens. Working input is the rendered full prompt minus
its fixed-only system/tool template; dynamic user and assistant messages,
call/return content and wrappers count. The converted graph remains in context
and subsequent interactions are appended normally.

An explanation is inserted once with the graph. While retained in context,
its tokens are still sent and counted on every request. Inline decoding rules
also count; no external explanation does not mean no instructions at all.

Candidates were selected on six old task conditions and three old seeds,
before fresh evaluation. An [amendment](DEVELOPMENT_AMENDMENT_1.md) added short
explanation controls before Event/Dedup development inference and all fresh
runs. See [PROTOCOL.md](PROTOCOL.md) and [selection.json](selection.json).

| Method | Selected codec | External explanation |
|---|---|---|
| State-Transition Graph | `state-shared-v1` | Minimal, 32 tokens |
| Event Graph | `tables-v1` | Minimal, 32 tokens |
| Event Graph-Dedup | `shared-v1` | None |

The controls are the frozen `readable-graph-1` implementations from
`work1000_research`, not the early historical Compact experiments. State's
control uses minimal explanation, Event's uses full explanation (151 tokens),
and Dedup's uses none. Event's comparison therefore measures the combined
codec-and-explanation change, not the codec alone. All codecs restore exact
typed JSON payloads and ordered histories; none prune, summarize or merge
semantic nodes. A reversible shared-value table is serialization reuse, not
semantic merging. State's shared-value dictionary was empty in 12 of its 13
triggered development cases, so development gains cannot be attributed to
actual value sharing.

## Main paired results

**120 Identity prefixes trigger conversion; 36 do not.** Untriggered runs are
reported separately and provide no graph-conversion evidence.

| Method | Official passes | First post-conversion input | Mean input per post-conversion request |
|---|---:|---:|---:|
| Identity | 51/120 (42.5%) | 4,258.49 | 4,655.73 |
| State-Transition Graph — control | 49/120 (40.8%) | 6,259.27 | 6,716.66 |
| State-Transition Graph — optimized | 51/120 (42.5%) | 6,029.82 | 6,516.47 |
| Event Graph — control | 46/120 (38.3%) | 7,697.19 | 8,122.46 |
| Event Graph — optimized | 51/120 (42.5%) | 7,198.70 | 7,702.46 |
| Event Graph-Dedup — control | 49/120 (40.8%) | 6,709.02 | 7,245.93 |
| Event Graph-Dedup — optimized | 49/120 (40.8%) | 6,613.66 | 7,224.76 |

Inputs include fixed overhead and all visible instructions. The final column
first averages actual requests within each trajectory, including the first
post-conversion request, then averages trajectories. It is not cumulative
input consumption. Only the first post-conversion request shares the same
continuation boundary across methods; later actions and request counts diverge.

Compared with each method's own control, mean input decreases by **2.98%**,
**5.17%** and **0.29%**, respectively. Optimized inputs remain approximately
**40%**, **65%** and **55%** larger than Identity. Dedup's median paired
mean-input ratio is 1.0117: its tiny aggregate reduction is not a typical
per-trajectory improvement.

Against Identity, optimized State and Event each gain 8 cases and lose 8;
Dedup gains 7 and loses 9. Equal aggregate passes do not mean the same cases
succeed. All full-cohort family-bootstrap intervals include zero; the study
does not establish equivalence, noninferiority or stable superiority.

Eighteen triggered trajectories already have a diagnosed official failure in
a completed prefix turn; every continuation fails on those cases. They remain
in the main 120-pair denominator. No detected early failure is not proof that
a prefix is valid. The fresh seeds repeat historically seen families; they
are not an unseen-task evaluation. The nondevelopment-condition stratum still
includes some development families under other conditions.

## Evidence and navigation

- [Summary](reports/summary.json): paired scores and trajectory means.
- [Every request](reports/per-request-input.csv), [user-turn aggregates](reports/per-user-turn-input.csv),
  and [paired first requests](reports/paired-first-request-input.csv): input measurements without cumulative-token substitution.
- [Paired analysis](reports/paired-analysis.json): descriptive uncertainty and instruction/body decomposition.
- [Final diagnostics](reports/final-diagnostics.json): family strata and prefix diagnostics.
- [Final audit](analysis/independent_audit/final.md): independent score recomputation, native token checks, exact restoration and source integrity.
- `development/` and `evaluation/`: immutable attempt records; `source_code/`: frozen implementations.

The 1,344 records comprise 182 actual development continuations, 70 development
skips, 156 fresh Identity runs, 720 actual fresh graph continuations and 216
fresh graph skips. Skips are not model runs. The independent audit rechecked
all 1,058 real completed runs, 9,963 actual requests and 902 graph payloads;
all 542 optimized payloads decode exactly. No failed score was selectively
retried.

Some runtime and automatic-report status labels intentionally retain their
historical `pending` wording. The final independent audit is the completion
evidence; those original files were not rewritten to change labels. See the
[CLI guide](../../../scripts/README.md) for working entry points. Preserve
snapshots and trajectories; snapshot `vendor` symlinks are machine-local,
ignored by Git, and must be recreated appropriately when migrating a copy.
