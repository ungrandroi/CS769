# Final independent audit

**Result: PASS. No blocking experimental-integrity issue found.** This is final independent validation of the completed frozen sweep, not a claim that the optimization goal is fully achieved. No model inference was performed and no trajectory, frozen source or visualization file was changed.

## Independently checked evidence

- All 1,344 records are accounted for: 252 development records (182 real continuations, 70 skips), 156 fresh Identity runs, and 936 evaluation graph records (720 real continuations, 216 skips). There are 120 triggered Identity prefixes and 36 untriggered prefixes. Skips are not graph-effect evidence.
- Recomputed official BFCL scoring for all 1,058 real completed runs, clearing evaluator simulator instances between runs; all outcomes match saved official scores and manifests. Result/score hashes match.
- Independently verified 902 graph payloads, original visible histories, shared Identity prefixes, and retained conversion containers. All 542 actual optimized payloads directly decode to their exact typed baseline payloads; source order and rebuilt original graphs match. No builder reconstruction substitutes for direct payload decoding.
- Verified 9,963 actual requests against native usage, request mapping, seeds, sampling, completed call/return pairing and thresholds. Read-only native `/apply-template` calls plus vocabulary-only CPU tokenization verified all fixed-overhead subtractions using 19 distinct fixed configurations and 112 full native prompt samples. No completion endpoint was called.
- Recomputed summary groups and 18 paired/family-bootstrap comparisons; verified 7,029 per-request CSV rows, 1,693 per-user-turn rows, 360 paired-first-request rows, 360 paired ratios and 720 graph decomposition rows.
- Strong configuration guard verifies all 1,344 launch/source/method/variant/explanation pairings. All 177 frozen-file entries across snapshots and all four dataset hashes match. Vendor is clean at `6ea57973c7a6097fd7c5915698c54c17c5b1b6c8`; current tokenizer metadata/library match preserved provenance.

Candidate ranking was recomputed from the original six development conditions and three old seeds. Recorded final-development completion, selection-file timestamp and first fresh Identity start are in strict order. The adaptation adding Event/Dedup minimal controls remains documented; no fresh evaluation outcome enters selection.

## Verified results: all 120 actual paired conversions

| Method | Successes | First input tokens | Mean subsequent-request input tokens |
|---|---:|---:|---:|
| identity | 51/120 | 4,258.49 | 4,655.73 |
| state-baseline | 49/120 | 6,259.27 | 6,716.66 |
| state-optimized | 51/120 | 6,029.82 | 6,516.47 |
| event-baseline | 46/120 | 7,697.19 | 8,122.46 |
| event-optimized | 51/120 | 7,198.70 | 7,702.46 |
| dedup-baseline | 49/120 | 6,709.02 | 7,245.93 |
| dedup-optimized | 49/120 | 6,613.66 | 7,224.76 |

The last column averages all post-conversion requests within each trajectory, then averages trajectories; it includes the first request and fixed overhead. It is not cumulative tokens. Relative to their corresponding frozen baseline, State reduces first-input/mean-input by 3.67%/2.98%, Event by 6.48%/5.17%, and Dedup by 1.42%/0.29%. The Dedup median paired mean-input ratio is 1.0117, so the very small aggregate improvement does not represent a typical per-trajectory reduction.

Paired optimized-versus-baseline gains/losses are State 3/1, Event 9/4, Dedup 6/6. Against Identity they are 8/8, 8/8 and 7/9. All full-cohort family-cluster intervals span zero. These results do not establish equivalence, noninferiority or stable superiority.

For the 102 triggered nondevelopment-condition repetitions: Identity 39, State baseline/optimized 38/41, Event 35/39, Dedup 38/38 successes. This stratum excludes the six exact development conditions, not every condition from development families. Separate family-level strata were checked.

## Interpretation limits

- 52 conditions are 13 historically seen families × four simulated file-tool conditions. Three fresh seeds are independent repetitions, not 156 independent tasks or a blind unseen-task evaluation.
- The development label in primary tables means six exact task-condition instances. The other 46 conditions still include development families under different conditions. Family-stratified results are separately verified.
- The minimal-explanation grid was adaptively expanded after observing State development outcomes, before Event/Dedup candidate outcomes and all fresh-seed evaluation; amendment preserved and disclosed.
- No pruning, semantic node merging or summarization occurs in these codec candidates. Losslessness is exact typed JSON payload/history restoration, with list and source-message order preserved; JSON object-key spelling/order is not the losslessness criterion.
- Zero outer explanation is not zero inline explanation. Optimized State/Event outer instructions are 32 tokens; Dedup has 0. Inline rules marginal body costs are 54/35/72 tokens respectively; these costs recur in each request while retained.
- Event baseline uses full outer explanation while the selected candidate uses minimal. Final Event comparison measures the selected combined codec-and-explanation optimization, not an isolated codec effect.
- Observed success counts are not noninferiority/equivalence proofs. Paired exact McNemar p-values assume more independence than family clusters provide and are descriptive only; 13-family bootstrap intervals are also small-cluster descriptive uncertainty.
- Only the first post-conversion request is aligned to a common environment/history boundary. Subsequent request ordinals diverge; trajectory means describe actual continued workloads, not matched actions.
- 18 triggered trajectories have sufficient evidence of an official failure in an already completed prefix turn. They remain in the primary 120-pair denominator; no detected failure is not proof of a valid prefix.
- Full model weights were not rehashed during this audit. Existing download hash, current metadata/library and clean vendor revision match; source/dependency snapshots are not proof against every possible external runtime change.
- This audit validates this frozen sweep. It does not imply the optimization objective is exhausted: State/Event reductions are modest, Dedup average reduction is negligible and its median per-trajectory ratio worsens.

## Prefix diagnostics and next action

The additional diagnosis of 18 already-failed completed prefixes is supported by the official checker: execution-result lists append once per ground-truth turn before state/empty-response checks; execution-response mismatch messages report zero-based turn indexes. The runner turn index is one-based. Only failures strictly earlier than the trigger turn count. All 18 fail under every method, remain in the main denominator, and absence of a diagnosis is not a valid-prefix certificate.

Independent audit is complete. A separate cleanup agent can organize active code and documentation while preserving `visualization/`, all trajectories, frozen snapshots and audit/selection/amendment evidence. This review authorizes no deletion of research evidence. Detailed machine-readable results and reproducible independent audit scripts are listed in `final.json`.
