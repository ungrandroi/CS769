# Experiment index

This index separates current results from historical and development evidence.
Directories stay at their original paths because manifests, frozen code and the
user-maintained visualization reference them. “Archived” below means retained
for reference, not moved, deleted, or invalidated.

## Main completed results

For a single view of both fresh-evaluation cohorts, use the
[combined 417-prefix index](combined_work1000/README.md). It links each common
prefix to all seven original runs, pools success/input metrics, and retains
source-study strata and all 600 Identity coverage records. It does not copy or
modify original trajectories. This aggregation is not an additional experiment.

| Study | Scope | Results and evidence |
|---|---|---|
| [Lossless encoding](lossless_encoding_v1/RESULTS.md) | 13 filesystem families × 4 conditions × 3 fresh seeds; 156 Identity runs, 120 triggered prefixes, 720 graph continuations | [Independent final audit](lossless_encoding_v1/analysis/independent_audit/final.md); [summary](lossless_encoding_v1/reports/summary.json); [per-request input](lossless_encoding_v1/reports/per-request-input.csv) |
| [Mixed-tool expansion](mixed_tool_expansion/PROTOCOL.md) | 37 additional families × 4 conditions × 3 fresh seeds; 444 Identity runs, 297 triggered prefixes, 1,782 graph continuations | [Independent final audit](mixed_tool_expansion/independent_audit/final.md); [summary](mixed_tool_expansion/reports/summary.json); [per-request input](mixed_tool_expansion/reports/per-request-input.csv) |

Both studies use local Qwen3.8-27B-Q8_0 and simulated tools. The trigger is native
full input minus the same request's fixed system/tool template, strictly greater
than 1,000 tokens, at a complete call/return boundary. One conversion replaces
the history, then new interactions are appended until completion. Untriggered
records are retained but are not graph-conversion evidence.

## Muse cross-model replication

*In progress: this study is still running, so `muse_transfer_v1/` and its `muse_*` scripts are kept local and not yet committed to the repository.*

[Muse transfer protocol](muse_transfer_v1/PROTOCOL.md) registers the same 50 task
families and 200 conditions with three repetitions (600 Muse Identity runs).
It generates Muse's own histories and evaluates the same six frozen graph arms
at eligible checkpoints; it does not reuse Qwen's 417 prefixes. Consult the
study's runtime status and audit records for progress rather than assuming the
completed Qwen studies also establish completion for Muse.

The local Muse model is Q4_K_XL with low reasoning strength and a shared 4096-token
generation budget. Native reasoning is logged but not reinserted into the working
history. These settings differ from Qwen Q8_0 with reasoning disabled; model
comparisons must disclose both differences. Token counts use Muse's own tokenizer,
including its BOS behavior. Exact graph restoration concerns the visible working
history, not every byte of generated reasoning.

## Versions to retain

| Role | Version | Outer instruction |
|---|---|---|
| Control | Identity | None |
| Main direction and control | State-Transition Graph selected encoding and original-format baseline | Minimal, 32 tokens, both |
| Main direction and control | Event Graph selected Tables encoding and original-format baseline | Minimal, 32 tokens, selected; full, 151 tokens, baseline |
| Additional control | Original Event Graph-Dedup | None |
| Negative result | Newly optimized Event Graph-Dedup Shared encoding | None |

Inline table/reference rules are also delivered and counted; “none” refers only
to the outer instruction. Do not relabel the Event baseline as minimal or add
instructions to Dedup without a new experiment. The Event comparison changes
both encoding and outer instruction. Selected encodings do not prune, merge
semantic nodes, summarize, or remove information.

The expanded Dedup encoding loses 16 successes relative to its control and is
not a replacement default. In the 81 expanded prefixes with actual non-file
calls, all three selected encodings have lower success counts than their
controls. Keep these results alongside the aggregate results.

## Historical baselines and archived exploration

| Directory | Why retained | Status |
|---|---|---|
| [qwen27b_experiment/](qwen27b_experiment/) | User-requested early 26-condition first-turn conversion baseline | Completed; preserve full trajectories and snapshots |
| [qwen27b_dedup_eval/](qwen27b_dedup_eval/) | Original provenance-dedup continuation, 15/26 official passes | Completed historical control |
| [v2_provenance_dedup_probe/](v2_provenance_dedup_probe/) | Original lossless provenance restoration and token evidence | Offline only |
| [history1000_eval/](history1000_eval/) | Earlier threshold counted tool-call/return content only | Prepared, not run; 9/26 checkpoints trigger; distinct from current protocol |
| [work1000_research/](work1000_research/PROTOCOL.md) | Original-format representation and explanation selection; source of optimization controls | Completed precursor; its records remain frozen |
| [graph_optimization_dev/](graph_optimization_dev/README.md) | Early offline encoding measurements on first-turn histories | Archived exploration, not continuation scores |
| [reports/](reports/) | Reports for early baselines and provenance-dedup experiments | Historical exports, not the latest aggregate |

Development candidates and failed attempts remain inside their parent studies.
They document selection and infrastructure recovery; unsuccessful candidates are
not discarded. The newer study's State/Event/Dedup `analysis/` directories hold
candidate-specific explanations and failure analyses.

## Reading and reproducing evidence

1. Read each study's final independent audit for verified outcomes and limits.
2. Use `reports/paired-first-request-input.csv` for the common conversion boundary.
3. Use `per-request-input.csv` and `per-user-turn-input.csv` for actual continuation
   input sizes. Later request numbers are not necessarily matched actions.
4. Use manifests, native requests and `source_code/` for exact reproduction.

Historical controller status may still say `pending_independent_audit`; the
separate final audit records later completion without rewriting runtime history.
Do not restart a completed controller just to inspect results or regenerate
reports over the frozen evidence. See the [CLI guide](../../scripts/README.md)
and [usage notes](USAGE.txt).

Further evaluation on wholly non-filesystem BFCL tasks has not been completed.
Frozen snapshots, trajectories, audit scripts, selection evidence and
`visualization/` are preserved. Only verified disposable working caches are
eligible for removal during routine organization.
