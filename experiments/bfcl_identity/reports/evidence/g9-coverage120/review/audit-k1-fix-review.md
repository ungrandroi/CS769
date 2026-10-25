# Offline correction for the frozen k=1 audit contract

The first coverage stage stopped after its original audit reported `official_qualification_only` for every prefix. Inspection of the frozen runner identified an auditor adaptation error: k=1 reuses the official first-turn score object, while the first auditor required the completed-prefix score schema used for k=2/3. The runner and official evaluation behavior were correct and remain unchanged.

Only new files were added: `analysis/audit-coverage-stage-v2.py`, `tests/test_coverage_audit_v2.py`, and this review. The original auditor, helper, runner, official evaluator, model requests and recorded experiment artifacts were not edited. The parent will re-audit the existing stage with the new auditor before deciding whether to resume; no repeated prefix/model execution is needed to correct this audit error.

The v2 correction is deliberately boundary-specific:

- For k=1, `prefix-score.json` must equal `first-turn-score.json` exactly as JSON, have the frozen `passed`/`diagnostics`/`evaluator` shape, identify `official BFCL first turn`, and have consistent Boolean `diagnostics.valid` and `passed`. The absent `completed_user_turns` field is accepted only in this exact k=1 contract.
- For k=2/3, an integer `completed_user_turns` equal to k is still required, along with `official BFCL completed prefix`. Missing, Boolean, floating-point or wrong counts fail.
- A shared reason helper is used by both per-prefix audit and the all-prefix gate. k=1 uses controller labels `incomplete_first_turn`/`official_first_turn_failed` and child labels `completed_first_turn_boundary_not_reached`/`official_first_turn_failed`; k=2/3 retain their existing prefix labels.
- Independent graph reconstruction now uses `end_of_first_user_turn` at k=1 and `archived_history_checkpoint` at k=2/3, matching frozen `graph_gpt_task.native_projection`. This prevents a false stored-graph mismatch later in k=1 continuations; no graph representation or evidence check is relaxed.
- All-prefix gate certificates are now `analysis/<stage>-actual-audit-v2.json`, require the v2 auditor version/hash, and retain all previous source, ledger, selection, plan, progress and complete-denominator checks. The original failed certificate is preserved.

Verification: 18 offline synthetic tests passed. These include all 12 previous audit tests reused against v2, plus direct per-prefix integration tests for k=1 pass/fail, incomplete boundaries, missing or forged score fields, strict k=2/3 contracts, the all-prefix gate's k=1 exclusions, and the graph reconstruction snapshot marker at all three boundaries. Tests operate only on generated temporary data; no provider calls or evaluator calls occur. Python compilation passed. The unchanged helper digest remains `037434f6fce53f10d688499020d3ac2150a2207ad88f2f01297ce988c012d8d1`.

Run the new synthetic suite with:

```text
python -m unittest discover -s work/g9-gpt41-coverage120-20261024/tests -p test_coverage_audit_v2.py -v
```

The v2 CLI has the same arguments as v1; use `analysis/audit-coverage-stage-v2.py` and an exclusive new `analysis/<stage>-actual-audit-v2.json` output path. Actual stage re-audit and subsequent remote execution remain the root controller's responsibility.
