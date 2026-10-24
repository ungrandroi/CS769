# Development feedback: event-tables-v1-minimal

Actual graph continuations: 13. Untriggered: 5 (excluded below).

| Method | Official passes | First input mean | Mean post input per trajectory |
|---|---:|---:|---:|
| identity | 11/13 | 4,871.85 | 5,444.91 |
| event-full | 11/13 | 9,766.46 | 10,804.30 |
| event-none | 10/13 | 9,614.46 | 10,686.82 |
| event-minimal | 10/13 | 9,647.46 | 10,313.96 |
| candidate | 13/13 | 8,486.46 | 9,518.73 |

All input token counts include fixed tools/system costs; these are not cumulative input counts.

| Paired reference | Gains | Losses | Both pass | Both fail |
|---|---:|---:|---:|---:|
| identity | 2 | 0 | 11 | 0 |
| event-full | 2 | 0 | 11 | 0 |
| event-none | 3 | 0 | 10 | 0 |
| event-minimal | 3 | 0 | 10 | 0 |

Every candidate payload was decoded directly and checked against the old Event-full delivered payload; histories and rebuilt original graphs also match. The first native request contains exactly the saved memory text. No payload loss was observed.

**Attribution limit:** minimal versus full changes both encoding and external explanation. Compare event-minimal separately; one development sample does not establish stable effects.

## Next decision

This development candidate currently matches or exceeds the frozen Event-full score; retain as a promising candidate, not a final success claim. Wait for all preplanned instruction/shared-value comparisons before selection. Do not change running frozen code or retry failures. Exact recoverability does not imply identical model behavior.
