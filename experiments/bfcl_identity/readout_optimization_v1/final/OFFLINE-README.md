# Second-round readout optimization: offline candidates

**Status: offline checks complete; no new model inference or server restart.** This is not a new success-rate experiment or a completed second-round optimization validation.

This development step uses the 81 Qwen and 95 Muse prefixes already exposed in the 19-branch diagnostic study. These are not held-out data. Historical trajectories, graph builders, frozen codecs, and visualization code are unchanged.

## Candidate design

- State-Transition Graph: the existing selected codec plus the common MINIMAL instruction; no diagnostic goal copy, extra index, or shared-reference expansion. This is a lean control, not a newly invented codec.
- Event Graph: keep the same lean control and test an additional compact active-state index. Subject/field pointers are reconstructed from each group’s existing fact IDs and the unchanged fact-column schema. All candidate IDs, grouping/order, ambiguities, null values and historical source facts are preserved.
- Event Graph-Dedup: the existing selected codec plus MINIMAL, without added index or reference expansion. This does not establish a new improvement over the earlier no-outer-instruction Dedup baseline.
- The full original graph payload and visible source history stay exactly recoverable in every candidate. No node pruning, semantic merging, new validity inference, current-goal duplication, or call-minimization instruction is introduced.
- The compact index has self-describing JSON keys instead of the earlier diagnostic JSON-pointer prose. The full graph still includes its codec rules. MINIMAL is installed once at conversion and remains in subsequent requests; its tokens are counted wherever present.

## Offline measurements

Only the complete first input at the shared boundary is measured. The archived native framing and actual tool definitions are retained, and only the single memory-message content is replaced. Both native tokenizers run vocabulary-only on CPU: no tensors or inference context are loaded. All 704 archived control/index prompt counts match their recorded native usage before candidate counts are accepted.

| Model | Old Event index tokens | Compact index tokens | Old complete indexed boundary input | New complete indexed boundary input | Saved |
|---|---:|---:|---:|---:|---:|
| qwen | 623.0 | 76.0 | 9666.7 | 9065.7 | 601.0 |
| muse | 676.2 | 70.6 | 9440.4 | 8781.8 | 658.6 |

The savings combine an exactly reversible index encoding and removal of diagnostic-only prose. They are not an isolated causal estimate of either change. The lean control shares the same outer instruction as the compact-index treatment.

| Model | Candidate | Complete boundary input | Increase over its Identity boundary input |
|---|---|---:|---:|
| qwen | state-minimal-base | 7808.8 | +37.2% |
| qwen | event-minimal-base | 8988.7 | +57.9% |
| qwen | event-compact-index | 9065.7 | +59.3% |
| qwen | dedup-minimal-base | 8561.0 | +50.4% |
| muse | state-minimal-base | 7587.8 | +27.3% |
| muse | event-minimal-base | 8711.2 | +46.1% |
| muse | event-compact-index | 8781.8 | +47.3% |
| muse | dedup-minimal-base | 8347.0 | +40.0% |

The lean controls save 54 Qwen / 53 Muse tokens versus the previous index_control arms by removing diagnostic-only prose. This is a small cleanup, not evidence that all graph overhead has been solved. The compact Event index adds about 77 Qwen / 71 Muse tokens to its new lean control.

## Verification and limits

- 704 candidate inputs across all 176 prefixes: typed graph/history restoration passed, existing index recovery passed, and native context plus 16,384 output reservation fits.
- Unit checks: 33 passed, one optional existing test skipped in the host environment; offline native accounting ran for both models in the project runtime. Tests reject stale/observation facts, omitted or duplicate IDs, altered grouping/order, and contradictory validity; unknown/multiple candidates and escaped IDs survive.
- No claims about task success, fewer calls, or later per-request input averages. No formal 3-percentage-point capability or 35% mean-input acceptance decision can be made from these boundary measurements.
- No successful outcome is imported from a different diagnostic arm. A new online comparison of Identity, lean controls, and compact Event index is still needed before adoption.
- Model servers remain stopped. No output-budget experiment was run here. Any future run must freeze its own protocol and disclose source-prefix versus continuation budgets.

Artifacts: STATUS.json; offline/offline-audit.json (all input measurements and source pins); offline/examples/ (representative complete prompts chosen by lexical case ID, not outcomes); source_code/offline-v1/ (frozen code).

Run offline replication into a NEW directory with the project BFCL Python and PYTHONPATH=scripts:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=scripts .conda/bfcl/bin/python \
  scripts/workflows/readout_candidate_audit.py --output /tmp/readout-candidate-check
```
