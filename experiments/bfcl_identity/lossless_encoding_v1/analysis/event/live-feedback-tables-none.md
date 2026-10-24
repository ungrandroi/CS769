# Development feedback: event-tables-v1-none

Actual graph continuations: 13. Untriggered: 5 (excluded below).

| Method | Official passes | First input mean | Mean post input per trajectory |
|---|---:|---:|---:|
| identity | 11/13 | 4,871.85 | 5,444.91 |
| event-full | 11/13 | 9,766.46 | 10,804.30 |
| event-none | 10/13 | 9,614.46 | 10,686.82 |
| candidate | 8/13 | 8,453.46 | 9,763.43 |

All input token counts include fixed tools/system costs; these are not cumulative input counts.

| Paired reference | Gains | Losses | Both pass | Both fail |
|---|---:|---:|---:|---:|
| identity | 1 | 4 | 7 | 1 |
| event-full | 1 | 4 | 7 | 1 |
| event-none | 0 | 2 | 8 | 3 |

Every candidate payload was decoded directly and checked against the old Event-full delivered payload; histories and rebuilt original graphs also match. The first native request contains exactly the saved memory text. No payload loss was observed.

**Attribution limit:** none versus full changes both encoding and external explanation. Compare event-none separately; one development sample does not establish stable effects.

## Observed losses relative to Event-full

- **multi_turn_base_9/seed3301**: Instead of sorting ArchivedFinalReport2024.txt, continuation creates line1.txt, writes alphabetized words, sorts that temporary file, and removes it. Official checker misses sorted_content for the report.  Baseline: Event-full invokes sort on ArchivedFinalReport2024.txt; Event-none also passes.
- **multi_turn_long_context_3/seed3301**: Prefix already copied both test files and entered backup_tests. Candidate repeats cp from inside backup_tests, creating a plain file named backup_tests; the next cp fails Not a directory. It ends by asking permission instead of accepting the already completed copies. Decoded active cwd fact f21 is backup_tests; successful cp events a7/a8 and cd a9 remain intact. Source returns and complete original payload match the baseline exactly. Baseline: Event-full lists the completed backup and stops successfully; Event-none already fails this case.
- **multi_turn_long_context_37/seed2207**: Candidate creates 7.txt from its count of server-error mentions. User requested file name from line count; earlier wc returned count 1 and official target is 1.txt. Decoded payload retains active cwd /temp and original wc responses. Candidate also rechecks wc after compaction and receives 1 again. Baseline: Event-full creates 1.txt; Event-none also passes.
- **multi_turn_long_context_9/seed1103**: Candidate calls cat then gives a textual word-sorting response without invoking sort on the archived report. Official checker misses required sorted_content result.  Baseline: Event-full invokes sort and passes; Event-none already fails.

## Next decision

This development candidate currently loses completion relative to frozen Event-full; token savings alone do not justify accepting it. Wait for all preplanned instruction/shared-value comparisons before selection. Do not change running frozen code or retry failures. Exact recoverability does not imply identical model behavior.
