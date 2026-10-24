# Dedup development feedback: dedup-tables-v1-minimal

Primary frozen baseline: **dedup-none**. Minimal adds an external instruction relative to that baseline.

| Method | Passed | First input mean | Mean post input |
|---|---:|---:|---:|
| identity | 11/13 | 4,871.85 | 5,444.91 |
| dedup-none | 11/13 | 8,526.62 | 9,818.93 |
| dedup-minimal | 11/13 | 8,559.62 | 9,198.17 |
| candidate | 9/13 | 8,107.38 | 9,143.54 |

| Reference | Gains | Losses | Both pass | Both fail |
|---|---:|---:|---:|---:|
| identity | 1 | 3 | 8 | 1 |
| dedup-none | 0 | 2 | 9 | 2 |
| dedup-minimal | 1 | 3 | 8 | 1 |

Actual shared values: 0/13 nonempty, 0 entries, 0 references, 0 unused entries.

All 13 actual memories directly decode to the original delivered Dedup payload and preserve history/original graph. Native requests contain exactly the saved memory. Five untriggered records are excluded.

These are development observations. Reduced tokens or exact recovery alone do not establish preserved task ability.
