# Frozen graph conversion results — 2026-11-20

Graph conversion optimization is closed by project decision. These versions are fixed baselines for subsequent lossy graph editing, not a claim that capability noninferiority or all efficiency targets have been met.

## Frozen variants

- Identity: unchanged visible history.
- State-Transition Graph: selected lossless codec + MINIMAL instruction (`state/readout_minimal`).
- Event Graph: selected lossless codec + MINIMAL instruction (`event/readout_minimal`); retain compact state index as an explicit evaluated variant (`event/readout_compact_index`), not an undisclosed default.
- Event Graph-Dedup: selected lossless codec + MINIMAL instruction (`dedup/readout_minimal`), retained for comparison; excluded from the planned three-graph lossy editing focus.

## Protocol

Qwen: 81 previously exposed actual-mixed prefixes × 5 arms = 405 continuations. Muse: 95 × 5 = 475. All 880 completed with official scores. Each model shares its own Identity prefix across arms. Conversion occurs once after native working history exceeds 1,000 tokens, excluding fixed system/tool overhead. Subsequent interactions append normally. Prefixes were generated with a 4,096 output limit; fresh continuations use 16,384. This is exploratory validation, not held-out confirmation.

The MINIMAL instruction is inserted once but remains in later requests and is charged whenever present. Full graph and visible-history payloads are retained; this experiment performs no lossy editing. Single-request input includes fixed prompts, tools and framing. Means average per-trajectory post-boundary request means. Calls are model-emitted function items after the boundary, including failed trajectories.

## Results

| Model | Arm | Successes | First input | Mean per-request input | Mean calls |
|---|---|---:|---:|---:|---:|
| qwen | identity/identity_reference | 47/81 | 5691.49 | 5874.10 | 1.84 |
| qwen | state/readout_minimal | 39/81 | 7808.83 | 8043.66 | 3.01 |
| qwen | event/readout_minimal | 42/81 | 8988.68 | 9191.29 | 2.47 |
| qwen | dedup/readout_minimal | 48/81 | 8560.98 | 8792.08 | 2.84 |
| qwen | event/readout_compact_index | 48/81 | 9065.73 | 9293.71 | 2.84 |
| muse | identity/identity_reference | 45/95 | 5961.26 | 6078.35 | 1.28 |
| muse | state/readout_minimal | 52/95 | 7587.82 | 7729.16 | 1.34 |
| muse | event/readout_minimal | 52/95 | 8711.16 | 8853.31 | 1.21 |
| muse | dedup/readout_minimal | 51/95 | 8346.96 | 8488.99 | 1.26 |
| muse | event/readout_compact_index | 50/95 | 8781.79 | 8928.56 | 1.28 |

## Interpretation and preservation

The compact Event index reduces first-request input versus the prior verbose index by approximately 601 Qwen / 659 Muse tokens. Completion changes are mixed across models. Qwen State loses capability in this sample; no universal improvement is claimed. Only Muse State meets the 35% mean-input engineering threshold relative to Identity. Formal 3-percentage-point noninferiority is not established. Frozen comparisons and intervals are included in the summary JSON files.

All failures remain in the denominator. CSVs contain all 880 per-trajectory metric rows. Raw multi-GB trajectories, native requests and machine runtime files stay local; original frozen source snapshots and records are preserved. Published source hashes identify the exact original summaries. No original record is rewritten.

The online frozen implementation is under `../runpod_20261110/experiment-v2/source_code/online-v1/`. Runtime plans contain local paths and require rebuilding on another machine; this publication does not promise a self-contained rerun of archived checkpoints. Future pruning/merging/rewiring studies must distinguish representation changes from edits and keep these conversion baselines fixed.

## Publication checks

The paired previous-round descriptive comparison is in `previous-round-comparison.json`. No inference was rerun for publication. Original snapshots retain their original whitespace and hashes.
