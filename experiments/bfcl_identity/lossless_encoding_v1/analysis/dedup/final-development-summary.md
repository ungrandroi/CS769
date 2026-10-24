# Event Graph-Dedup development comparison

Frozen baseline: dedup-none; minimal is a new external-instruction condition relative to it.

| Configuration | Passed | First input mean | Mean post input |
|---|---:|---:|---:|
| Identity | 11/13 | 4,871.85 | 5,444.91 |
| Frozen Dedup-none | 11/13 | 8,526.62 | 9,818.93 |
| dedup-shared-v1-none | 11/13 | 8,082.62 | 9,559.68 |
| dedup-tables-v1-minimal | 9/13 | 8,107.38 | 9,143.54 |
| dedup-shared-v1-minimal | 9/13 | 8,115.62 | 9,286.63 |
| dedup-tables-v1-none | 8/13 | 8,074.38 | 9,381.47 |

Ability-first development winner: **dedup-shared-v1-none**; adoption criterion met: **True**.

All 52 actual candidate memories passed exact payload, history, rebuilt graph and native request checks. Counts include fixed tools/system prompts; means are per-trajectory macro means, not cumulative tokens.

This is development selection, not independent validation. Fresh-seed evaluation is run separately by the controller.
