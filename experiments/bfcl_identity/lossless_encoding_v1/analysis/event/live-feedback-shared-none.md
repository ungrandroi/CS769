# Development feedback: event-shared-v1-none

Actual graph continuations: 13. Untriggered: 5 (excluded below).

| Method | Official passes | First input mean | Mean post input per trajectory |
|---|---:|---:|---:|
| identity | 11/13 | 4,871.85 | 5,444.91 |
| event-full | 11/13 | 9,766.46 | 10,804.30 |
| event-none | 10/13 | 9,614.46 | 10,686.82 |
| candidate | 11/13 | 8,285.92 | 9,571.27 |

All input token counts include fixed tools/system costs; these are not cumulative input counts.

| Paired reference | Gains | Losses | Both pass | Both fail |
|---|---:|---:|---:|---:|
| identity | 2 | 2 | 9 | 0 |
| event-full | 1 | 1 | 10 | 1 |
| event-none | 2 | 1 | 9 | 1 |

Every candidate payload was decoded directly and checked against the old Event-full delivered payload; histories and rebuilt original graphs also match. The first native request contains exactly the saved memory text. No payload loss was observed.

**Attribution limit:** none versus full changes both encoding and external explanation. Compare event-none separately; one development sample does not establish stable effects.

## Observed losses relative to Event-full

- **multi_turn_base_37/seed1103**: The prefix already created 1.txt for the final user request. After conversion, the continuation returns to the earlier line-count request, tries cd temp, checks pwd/ls/wc, and reports that 1.txt is empty. It never appends the requested sentence. The current user request, touch result, and all earlier history survive direct decoding exactly. Baseline: Old Event-full and tables-none both append the sentence and pass.

## Next decision

This development candidate currently matches or exceeds the frozen Event-full score; retain as a promising candidate, not a final success claim. Wait for all preplanned instruction/shared-value comparisons before selection. Do not change running frozen code or retry failures. Exact recoverability does not imply identical model behavior.
