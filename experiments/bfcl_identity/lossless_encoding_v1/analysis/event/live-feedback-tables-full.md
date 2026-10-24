# Development feedback: event-tables-v1-full

Actual graph continuations: 13. Untriggered: 5 (excluded below).

| Method | Official passes | First input mean | Mean post input per trajectory |
|---|---:|---:|---:|
| identity | 11/13 | 4,871.85 | 5,444.91 |
| event-full | 11/13 | 9,766.46 | 10,804.30 |
| event-none | 10/13 | 9,614.46 | 10,686.82 |
| candidate | 10/13 | 8,605.46 | 9,722.93 |

All input token counts include fixed tools/system costs; these are not cumulative input counts.

| Paired reference | Gains | Losses | Both pass | Both fail |
|---|---:|---:|---:|---:|
| identity | 1 | 2 | 9 | 1 |
| event-full | 1 | 2 | 9 | 1 |
| event-none | 2 | 2 | 8 | 1 |

Every candidate payload was decoded directly and checked against the old Event-full delivered payload; histories and rebuilt original graphs also match. The first native request contains exactly the saved memory text. No payload loss was observed.

**Attribution limit:** The full external instruction is held identical to old Event-full; representation and its embedded decoding rules change. This is one development sample, not proof of stable improvement.

## Observed losses relative to Event-full

- **multi_turn_long_context_37/seed3301**: The prefix already returned line counts for 31 files in one batch. After conversion the model checks the files again, but sends one wc per request. It reaches the existing BFCL turn step limit before finishing the file list; later user turns are never reached. All original wc calls and results survive exact decoding. Different filenames are distinct calls, not identical-call duplication. The failure is official force_terminated, not an infrastructure failure. Baseline: Old Event-full passes; its rechecking is batched, allowing the remaining user turns to execute.
- **multi_turn_long_context_9/seed1103**: The continuation tries cd Archives while already inside it, observes the error, lists and reads the report, then answers in text without invoking sort. Official checker misses sorted_content. Current-location and original tool-return evidence remain exactly intact. Baseline: Old Event-full invokes sort and passes.

## Next decision

This development candidate currently loses completion relative to frozen Event-full; token savings alone do not justify accepting it. Wait for all preplanned instruction/shared-value comparisons before selection. Do not change running frozen code or retry failures. Exact recoverability does not imply identical model behavior.
