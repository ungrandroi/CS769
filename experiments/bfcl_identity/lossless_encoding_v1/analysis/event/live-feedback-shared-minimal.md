# Development feedback: event-shared-v1-minimal

Actual graph continuations: 13. Untriggered: 5 (excluded below).

| Method | Official passes | First input mean | Mean post input per trajectory |
|---|---:|---:|---:|
| identity | 11/13 | 4,871.85 | 5,444.91 |
| event-full | 11/13 | 9,766.46 | 10,804.30 |
| event-none | 10/13 | 9,614.46 | 10,686.82 |
| event-minimal | 10/13 | 9,647.46 | 10,313.96 |
| candidate | 9/13 | 8,318.92 | 9,515.70 |

All input token counts include fixed tools/system costs; these are not cumulative input counts.

| Paired reference | Gains | Losses | Both pass | Both fail |
|---|---:|---:|---:|---:|
| identity | 0 | 2 | 9 | 2 |
| event-full | 0 | 2 | 9 | 2 |
| event-none | 1 | 2 | 8 | 2 |
| event-minimal | 2 | 3 | 7 | 1 |

Every candidate payload was decoded directly and checked against the old Event-full delivered payload; histories and rebuilt original graphs also match. The first native request contains exactly the saved memory text. No payload loss was observed.

**Attribution limit:** minimal versus full changes both encoding and external explanation. Compare event-minimal separately; one development sample does not establish stable effects.

## Next decision

This development candidate currently loses completion relative to frozen Event-full; token savings alone do not justify accepting it. Wait for all preplanned instruction/shared-value comparisons before selection. Do not change running frozen code or retry failures. Exact recoverability does not imply identical model behavior.
