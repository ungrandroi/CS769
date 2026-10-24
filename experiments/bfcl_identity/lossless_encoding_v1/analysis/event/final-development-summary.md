# Event Graph development comparison

All six planned configurations completed on the same 13 triggered prefixes. Five untriggered runs per configuration are excluded.

| Configuration | Passed | First input mean | Mean post input |
|---|---:|---:|---:|
| Identity | 11/13 | 4,871.85 | 5,444.91 |
| Frozen Event-full | 11/13 | 9,766.46 | 10,804.30 |
| event-tables-v1-minimal | 13/13 | 8,486.46 | 9,518.73 |
| event-shared-v1-full | 11/13 | 8,437.92 | 9,185.55 |
| event-shared-v1-none | 11/13 | 8,285.92 | 9,571.27 |
| event-tables-v1-full | 10/13 | 8,605.46 | 9,722.93 |
| event-shared-v1-minimal | 9/13 | 8,318.92 | 9,515.70 |
| event-tables-v1-none | 8/13 | 8,453.46 | 9,763.43 |

Preregistered ability-first winner: **event-tables-v1-minimal**. Development adoption criterion: **True**.

Input counts include fixed tools and system prompts. Post input averages within each trajectory first, then equally across trajectories; these are not cumulative totals.

Actual shared-value dictionaries are nonempty for 13/13 Event checkpoints, containing 78 entries with 480 references and no unused entries. Shared representation reduces graph body tokens by a mean 167.54 relative to tables, including its visible rules. Behavioral differences cannot be attributed uniquely to deduplication because the reference grammar also changes.

All actual saved memories were checked against native requests, decoded directly to the frozen delivered payload, and checked for exact history and original graph restoration. External instructions match the old same-explanation baseline.

This ranking is for development selection only; fresh-seed validation must assess whether gains survive selection. No running code, queue or trajectories were changed by this analysis.
