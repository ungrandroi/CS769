# Dedup development feedback: dedup-tables-v1-none

Primary frozen baseline: **dedup-none**. Minimal adds an external instruction relative to that baseline.

| Method | Passed | First input mean | Mean post input |
|---|---:|---:|---:|
| identity | 11/13 | 4,871.85 | 5,444.91 |
| dedup-none | 11/13 | 8,526.62 | 9,818.93 |
| candidate | 8/13 | 8,074.38 | 9,381.47 |

| Reference | Gains | Losses | Both pass | Both fail |
|---|---:|---:|---:|---:|
| identity | 0 | 3 | 8 | 2 |
| dedup-none | 0 | 3 | 8 | 2 |

Actual shared values: 0/13 nonempty, 0 entries, 0 references, 0 unused entries.

All 13 actual memories directly decode to the original delivered Dedup payload and preserve history/original graph. Native requests contain exactly the saved memory. Five untriggered records are excluded.

These are development observations. Reduced tokens or exact recovery alone do not establish preserved task ability.

## Observed baseline losses

- **multi_turn_base_9/seed3301**: After reading the archived report, continuation calls echo twice with manually alphabetized words and finishes without sort. Official required sorted_content is absent.
- **multi_turn_long_context_9/seed1103**: Continuation writes a short manually sorted word list to sorted_line.txt, then deletes it. It never invokes sort, so the official required sorted_content is absent.
- **multi_turn_long_context_9/seed2207**: Continuation lists and reads the report, then answers in text without sort. All three losses share tool-action omission/task-interpretation divergence, not identified payload corruption.
