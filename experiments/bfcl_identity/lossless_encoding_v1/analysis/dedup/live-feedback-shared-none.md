# Dedup development feedback: dedup-shared-v1-none

Primary frozen baseline: **dedup-none**. Minimal adds an external instruction relative to that baseline.

| Method | Passed | First input mean | Mean post input |
|---|---:|---:|---:|
| identity | 11/13 | 4,871.85 | 5,444.91 |
| dedup-none | 11/13 | 8,526.62 | 9,818.93 |
| candidate | 11/13 | 8,082.62 | 9,559.68 |

| Reference | Gains | Losses | Both pass | Both fail |
|---|---:|---:|---:|---:|
| identity | 0 | 0 | 11 | 2 |
| dedup-none | 1 | 1 | 10 | 1 |

Actual shared values: 11/13 nonempty, 27 entries, 254 references, 0 unused entries.

All 13 actual memories directly decode to the original delivered Dedup payload and preserve history/original graph. Native requests contain exactly the saved memory. Five untriggered records are excluded.

These are development observations. Reduced tokens or exact recovery alone do not establish preserved task ability.
