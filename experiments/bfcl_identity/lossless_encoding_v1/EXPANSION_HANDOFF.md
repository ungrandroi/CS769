# Authorized follow-up: broader BFCL task coverage

Status: mixed-domain adapters independently reviewed and frozen; development
model runs are active, while fresh-seed full evaluation has not started. This document does
not change the active frozen lossless-encoding experiment or claim that its
controller automatically implements this follow-up.

The user confirmed that broader task coverage remains part of the work.
Increasing conditions or random seeds is not a substitute for new base tasks.
The current scope contains 13 pure GorillaFileSystem families, four conditions,
and three fresh seeds (52 task-condition instances, 156 Identity runs).

Execution coordinator: lossless_runner.

1. Finish the current paired validation and independent audit; preserve all
   frozen versions, trajectories, and unsuccessful candidates.
2. Inventory the pinned BFCL tasks that involve GorillaFileSystem alongside
   other tools. Each of the four current categories contains 50 filesystem-
   involving instances, of which 13 are filesystem-only. Check actual family
   correspondence and novelty before registering the additional mixed tasks.
3. Audit graph-builder coverage for each additional tool class. Distinguish
   recording calls and returns from supported state/fact extraction. Unsupported
   semantics must remain explicit; do not invent facts or claim equivalent
   semantic coverage.
4. Develop and audit any necessary adapters separately, then freeze them and the
   evaluation protocol before collecting comparison results.
5. Evaluate Identity, the three pre-optimization graph baselines, and the three
   selected lossless graph encodings on matched prefixes with repeated seeds.
   Preserve the >1000 working-token trigger, exclusion of fixed overhead,
   complete call/return boundary, and one-time conversion protocol.
6. Extend to additional BFCL tool domains following the same coverage audit and
   development/evaluation separation. Keep scope and completion status explicit.

Preserve `visualization/`, historical experiments, and `source_code/` snapshots.
No pruning, semantic merging, summarization, or information removal is authorized
as part of the lossless encoding optimization. Adapter changes are a separate,
documented extension and must not be presented as lossless coding changes.

## Execution update

The current lossless study has completed inference, automatic reports, and an
independent final audit (all passed). A separate cleanup agent is organizing
working-code entry points and English documentation while preserving evidence.

`../mixed_tool_expansion/inventory.json` confirms 37 additional families,
148 task-condition instances, and matching family/tool-class correspondence
across all four categories. Partner domains are Twitter (12 families), Math
(12), Message (8), and Ticket (5). These families are new relative to the current
13-family study; this is not a claim that none were inspected earlier.

Coverage review found that the historical unadapted graph builders invalidate all
file facts after any non-file tool call. They preserve raw calls/returns but do
not extract state/fact semantics for the four partner domains. The next step is
an explicitly versioned adapter design, development, and independent audit.
That preflight is now complete: 61 tests, 47 public-contract synthetic calls,
53 frozen modules and 123 vendor pins passed independent checks. The detached
mixed study controller is running development integration tests and has
received genuine Qwen responses. It must pass a separate independent
development-review gate before fresh-seed full evaluation. The frozen current
study is not modified. Machine-readable progress is in
`runtime/expansion-stage-plan.json`; active execution details are under
`../mixed_tool_expansion/runtime/`.
