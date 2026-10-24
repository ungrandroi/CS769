# Final independent audit

**Result: PASS for experimental integrity. The optimization objective is not uniformly achieved.**

All model inference has finished. This audit independently recomputed scores, checked delivered payloads and paired histories, and validated reported statistics. It performed no model inference, modified no experimental trajectory or frozen source, and did not touch `visualization/`.

## Checked evidence

- 3,276 records: 168 development records (24 Identity and 144 real graph continuations), plus 3,108 fresh-evaluation records (444 Identity, 1,782 real graph continuations, 882 untriggered graph skips). Fresh evaluation has 297 triggered prefixes and 147 untriggered prefixes.
- Recomputed official BFCL scores for all 2,394 actual completed runs, resetting evaluator simulator instances between runs. All scores and saved result/score hashes agree.
- Checked 1,926 delivered graph payloads/history restorations and exact common prefixes. All 963 optimized payloads decode directly to the original typed semantic payload, and match the paired original-format graph. Reconstruction by a builder does not substitute for direct codec decoding.
- Checked 21,167 native requests for actual usage, request mapping, sampler settings, seed schedule, complete call/return pairing and earliest eligible threshold. Read-only native template rendering plus CPU tokenization verified 58 fixed configurations across all requests and 56 full-prompt samples. No completion endpoint was called.
- Independently recomputed 2,079 summary rows, 891 paired comparisons/first-boundary CSV rows, 15,368 per-request CSV rows, 4,279 user-turn CSV rows, 1,782 token-decomposition rows, all subgroup summaries, paired gains/losses and family-cluster bootstrap intervals.
- Verified frozen source and vendor/data pins, all launch configurations, matched preflight/development approval, and review-before-fresh-evaluation ordering. No evaluation outcome entered codec selection.
- 41 mixed-domain unit tests passed using the frozen module path. The BFCL conda environment lacks pytest; the initial unittest discovery encountered two import errors, then the existing system pytest ran the complete targeted suite successfully. This test harness issue did not affect any model run.

## Fresh evaluation: all 297 triggered prefixes

The 37 additional base families have four conditions each (148 task-condition instances), repeated with three fresh seeds. These are not 444 independent task families.

| Method | Successes | First input tokens | Mean input per post-conversion request |
|---|---:|---:|---:|
| identity | 120/297 | 5,970.65 | 6,520.20 |
| state-baseline | 119/297 | 8,212.83 | 8,754.72 |
| state-optimized | 117/297 | 7,869.00 | 8,423.48 |
| event-baseline | 120/297 | 10,072.62 | 10,633.91 |
| event-optimized | 125/297 | 9,371.48 | 9,912.41 |
| dedup-baseline | 117/297 | 9,233.04 | 9,821.87 |
| dedup-optimized | 101/297 | 8,946.17 | 9,666.69 |

The last column averages requests within each trajectory, then averages trajectories. It includes the first boundary request and fixed tool/system overhead; it is not cumulative input. Relative to each own baseline, State saves 4.19%/3.78% first/mean input, Event 6.96%/6.78%, and Dedup 3.11%/1.58%.

**Selected Dedup does not meet the intended capability-preservation goal on the observed expansion results:** 117 to 101 successes, with 17 paired gains and 33 losses. Its codec remains exactly lossless; that does not imply identical model behavior. State has 15 gains/17 losses (119 to 117), Event 18 gains/13 losses (120 to 125). Against Identity the selected arms have 20/23, 24/19 and 18/37 gains/losses respectively.

Family-cluster intervals versus own baseline are State [-5.07, +3.67], Event [-2.88, +5.84], and Dedup [-10.99, 0.00] percentage points. Dedup has a negative observed signal; the 37-family descriptive interval reaches zero. Unclustered McNemar p-values are descriptive and do not establish family-independent significance. No equivalence, noninferiority or stable superiority claim is warranted.

## Actual domain exposure matters

Only **81 of the 297 converted prefixes contain non-filesystem calls**: MessageAPI 26, TwitterAPI 14, TicketAPI 19, MathAPI 22. All converted prefixes contain filesystem calls. The other 216 prefixes have mixed tools available but contain only filesystem history at conversion. Across all 444 Identity trajectories, 277 execute a non-filesystem tool somewhere.

| Actual prefix content | Identity | State original → selected | Event original → selected | Dedup original → selected |
|---|---:|---:|---:|---:|
| Contains non-filesystem calls (81) | 49 | 44 → 39 | 43 → 42 | 46 → 40 |
| Filesystem-only history (216) | 71 | 75 → 78 | 77 → 83 | 71 → 61 |

This exposure stratification is descriptive, not used to retune or select candidates. In particular, Event’s overall gain cannot be presented as evidence of improved compression of genuinely mixed-domain histories. All three selected graphs have lower success counts in the actual mixed-prefix stratum.

## Interpretation and preservation limits

- Mixed semantic adapters are a separately developed extension. Original-format and optimized arms share the same adapted semantic graph; this experiment does not isolate the adapter effect against unadapted graphs. Semantic audits preserve state deltas/deletions, event outcome/support markers, domain objects/facts, source links and unknown/unsupported markers.
- No pruning, semantic node merging, summarization or information deletion occurs in the codecs. Exact storage restoration is distinct from the model successfully interpreting a representation.
- Event changes both encoding and outer explanation (full to minimal), so its comparison is a combined input-format optimization, not a codec-only causal estimate. Zero outer explanation for Dedup is not zero inline codec rules; all retained rules/instructions count in each actual input.
- Only the first post-conversion request is aligned to a common environment/history boundary. Later request ordinals can correspond to different actions.
- Development conditions, development families, other conditions, other families and categories were independently checked. Other-family counts are available separately; repeated conditions and seeds remain clustered.
- 28 triggered Identity trajectories have sufficient official diagnostic evidence of an already failed completed prefix turn. These remain in the primary denominator. Absence of such a diagnosis is not proof the prefix was valid.
- No failed outcome was discarded or retried to improve reported scores. Unsupported domains outside this study still require a separate coverage audit.
- Automatic controller/report status files retain their historical `pending_independent_audit` labels. This `final.json` and report record the completed independent review; historical logs were not rewritten. Code cleanup and any further domain expansion are separate remaining tasks.

Evidence files: `final-check-evidence.json`, `final-native-evidence.json`, `final-reports-evidence.json`, `final-exposure-evidence.json`, and `final-tests-system.log`.
