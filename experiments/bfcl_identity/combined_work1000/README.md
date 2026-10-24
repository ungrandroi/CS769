# Combined 1,000-token conversion cohort

This is an index and descriptive aggregation, not a new experiment.
Original trajectories and frozen sources remain in their original studies.

600 fresh Identity runs cover 50 base families and 200 task-condition instances.
417 prefixes trigger conversion; each has Identity plus six graph results.
183 untriggered prefixes stay in coverage.csv and are excluded from paired scores.

| Arm | Successes | Rate | First input | Mean input per continuation request |
|---|---:|---:|---:|---:|
| Identity | 171/417 | 41.0% | 5,478 | 5,984 |
| State original | 168/417 | 40.3% | 7,651 | 8,168 |
| State optimized | 168/417 | 40.3% | 7,340 | 7,875 |
| Event original | 166/417 | 39.8% | 9,389 | 9,911 |
| Event optimized | 176/417 | 42.2% | 8,746 | 9,276 |
| Dedup original | 166/417 | 39.8% | 8,507 | 9,081 |
| Dedup optimized | 150/417 | 36.0% | 8,275 | 8,964 |

## Files

- `paired-samples.csv`: 417 rows, one shared prefix with all seven outcomes and original run paths.
- `arm-results.csv`: 2,919 rows, one method result per prefix, with input metrics and encoding/explanation.
- `coverage.csv`: all 600 Identity runs, including 183 untriggered records.
- `summary.csv` / `summary.json`: pooled and source-study results.
- `source-hashes.json`: SHA-256 of the manifests, plans and summaries read by this export.

All run paths are relative to the repository root. Source splits are preserved;
an evaluation record labelled development refers to a development task condition
repeated with fresh seeds, not a candidate-tuning run. No development-directory
runs or earlier experiments enter this export.

## Shared protocol and limits

The threshold is native full input minus fixed system/tool template tokens,
**strictly greater than 1,000**, at a complete call/return boundary. This is
not a cut at exactly 1,000 tokens. Graph conversion happens once, followed by
appending new interactions. Both studies use local Qwen3.8-27B-Q8_0;
within-prefix sampling, boundary and checkpoint fields are checked across arms.

Token metrics include fixed overhead. Mean input first averages post-conversion
requests within each trajectory (including the first), then averages trajectories.
They are not cumulative tokens. Only the first boundary request is action-aligned.

The studies use different seed sets and graph-builder versions. Mixed-tool arms
share adapted semantics within their study; this is not one identical graph builder
tested 417 times. Keep source-study strata in analysis. Only 81 of the 297 mixed
study prefixes contain non-filesystem calls; the mixed label alone does not prove
mixed history. Repeated conditions and seeds are not independent task families.

Event original/optimized also differ in outer explanation (full/minimal).
Pooled counts do not establish equivalence or stable superiority.
Independent audit details remain in the original studies:

- [Filesystem audit](../lossless_encoding_v1/analysis/independent_audit/final.md)
- [Mixed-tool audit](../mixed_tool_expansion/independent_audit/final.md)

Rebuild into a new directory from the repository root:

```bash
python scripts/workflows/combined_report.py --output /tmp/bfcl-combined-review
```
