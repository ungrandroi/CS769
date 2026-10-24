# State-Transition Graph: completed lossless-codec development experiment

All four registered State development configurations have finished. Each uses the same 13 triggered Identity prefixes from the six registered development conditions, with three historical seeds where triggered. The comparison baseline is the current readable State graph with its selected minimal explanation. The frozen code and run queue were not edited during analysis.

## Development results

| Configuration | Official passes | Paired gains / losses vs current baseline | First post-fork input mean | Post-fork input mean per trajectory |
| --- | ---: | ---: | ---: | ---: |
| Current readable/minimal | 10/13 | — | 7588.00 | 8466.32 |
| Tables/none | 8/13 | 0 / 2 | 7109.69 (-6.3%) | 8383.05 (-1.0%) |
| Tables/minimal | 10/13 | 2 / 2 | 7142.69 (-5.9%) | 7808.81 (-7.8%) |
| Shared/none | 9/13 | 1 / 2 | 7123.62 (-6.1%) | 8464.63 (-0.02%) |
| Shared/minimal | 11/13 | 2 / 1 | 7156.62 (-5.7%) | 8047.35 (-4.9%) |

Inputs are actual complete request tokens, including fixed tools/system content and all retained explanation. Post-fork means first average requests within each trajectory, then average the 13 trajectories. Lower average input does not imply every step or checkpoint is shorter: shared/minimal adds 14 first-input tokens in each of the three short base-37 cases.

Under the preregistered rule—success count first, then post-fork mean input—**shared/minimal is the State development winner**. It meets the development point-estimate criterion of at least baseline successes and lower mean input. **Tables/minimal remains a useful tradeoff:** one fewer development success, but a larger input reduction. Neither is proved superior or non-inferior on general tasks.

## What the selected candidate preserves and changes

`state-shared-v1` retains the complete original delivered payload. It stores repeated dictionary fields as explicit table defaults and rows, and exact repeated strings/subtrees through an in-band shared-value dictionary when the codec finds eligible repetitions. It retains distinct states, executed calls, evidence, source messages and ordering; no pruning, semantic merging, summary or information selection is performed.

All decoding conventions are inside the delivered envelope and count as input. The selected configuration also retains the same 32-token external minimal instruction as the old baseline. It is therefore **not a zero-explanation result**. Python reconstruction demonstrates recoverability, not equivalent model understanding.

Direct payload, original history and original-graph reconstruction passed for 13 development checkpoints across all three offline variants. Nine State tests passed, including 900 seeded nested-data round trips, and the Event agent independently reviewed the State codec. The third columnar variant and later layout/JSON-column probes remain offline attempts; they were not injected into this live experiment.

## Important attribution limit: almost no shared references were used

Inspection of the actual shared/minimal artifacts shows **12 of 13 have `shared_values = {}`**. Only base task 9 seed 3301 uses two dictionary entries (a repeated directory-listing string and an evidence list).

For the other 12 checkpoints, the encoded payload is identical to tables/minimal. The differing model input consists of the candidate label, shared-reference explanatory text and empty dictionary envelope. Thus the LC37 improvements and the LC9 regression cannot be credited specifically to shared-reference compression. They show sensitivity to the complete prompt representation, including small envelope changes, in stochastic generation.

The selected prompt still has lower input than the old baseline because the common table encoding reduces repeated fields. The overall selection is valid under the registered empirical rule, but it does **not** establish that adding shared references improves reasoning. Do not remove the empty dictionary or explanatory text in the selected candidate after evaluation; that would be another untested prompt variant.

## Selected candidate's paired changes

Shared/minimal has:

- 9 shared successes with the current baseline;
- 2 gains: base task 9 seed 3301 and long-context task 9 seed 1103;
- 1 loss: long-context task 9 seed 2207;
- 1 shared failure: long-context task 9 seed 3301.

All three LC37 checkpoints pass under shared/minimal, unlike tables/minimal's 1/3 on that task. This is encouraging within development but is three repeated trajectories from the same task condition, not three independent task families.

### Read-only diagnosis of the selected candidate's new loss

For long-context task 9 seed 2207, the last user asks to sort the inaugural line of `ArchivedFinalReport2024.txt`.

- Old readable/minimal and tables/minimal call `sort(file_name='ArchivedFinalReport2024.txt')`, then respond. Both pass.
- Shared/none lists and reads the file, then provides a text-only attempted word sorting. It fails the official required execution-result check because it never invokes `sort`.
- Shared/minimal navigates up twice, attempts `cat` with an invalid path, returns to Documentation/Archives, reads the file, and calls `echo` with a short manually word-sorted sentence. The subsequent `cat` returns only that short sentence, demonstrating that the original long file content was overwritten, not appended. It fails the official filesystem-root state check.

The selected candidate therefore substitutes a manual word transformation and file mutation for the available line-sorting tool. The observed cause of official failure is the resulting filesystem difference. We cannot infer the model's private reasoning or blame a particular token.

For this actual run, decoded payload equality, original graph content and external minimal instruction equality all pass against the old baseline. Its shared dictionary is empty and its payload matches tables/minimal, so loss of stored information or an actual shared-reference lookup error is not supported by the evidence.

## Lessons and next action

1. The zero-external-explanation candidates were smaller but had lower observed completion than the old baseline; the selected candidate keeps minimal explanation.
2. Tables reduce static input, but model continuation behavior determines whether those savings persist. The none configurations nearly lose their benefit through additional actions and text.
3. Equal or higher total successes must be accompanied by paired gain/loss reports; some original successes are lost.
4. Keep both frozen candidate records and explanatory diagnostics. Do not perform task-specific prompt patches or selectively retry failures.
5. Proceed with the registered fresh-seed validation of the frozen selected candidate, using the same Identity prefixes for old and optimized State methods. These are independent repeated runs on historically seen conditions, not unseen-task evaluation.
6. If fresh validation shows unacceptable capability loss, consider the already documented named-edge or layout-only control in a separate development round. No extra variant is added now.

Fresh results and uncertainty are still required before claiming the optimization achieved the research objective. Development selection over four configurations can overestimate improvements.

## Artifacts

- `development-final-summary.json`: compact machine-readable result and gain/loss lists.
- `dev-tables-none.json`, `dev-tables-minimal.json`, `dev-shared-none.json`, `dev-shared-minimal.json`: complete per-checkpoint metrics.
- `live-feedback-first-pass.md`, `live-feedback-tables-none-complete.md`, `live-feedback-tables-explanation-control.md`: earlier trajectory diagnoses and retained offline suggestions.
- Live records: `development/<task>/seed<seed>/state-state-{tables,shared}-v1-{none,minimal}/`.
