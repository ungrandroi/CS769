# Additional short-explanation development controls

Registered during State-Transition Graph development, before any Event Graph
or Event Graph-Dedup candidate inference and before any fresh-seed evaluation.
The corresponding timestamp, process handoff and absence-of-results evidence
are recorded in `runtime/controller-v1-paused-for-amendment.json` and
`runtime/development-amendment-1.json`.

The original controller compared no external explanation with the selected
baseline explanation. This covered none/minimal for State-Transition Graph,
none/full for Event Graph, but only none for Event Graph-Dedup. To satisfy the
planned preference for no or short necessary explanations, add minimal as a
control for Event Graph and Event Graph-Dedup. State development already shows
that explanation choice can change completion; that observation motivates
the additional controls but is not evidence about Event or Dedup outcomes.

The resulting frozen grid is two codecs per method with:

- State-Transition Graph: none and minimal.
- Event Graph: none, minimal, and full (the existing baseline explanation).
- Event Graph-Dedup: none and minimal.

All inline schema/reference rules remain visible and counted. None means no
external explanation, not no inline encoding conventions. No codec, graph,
threshold, sampler, task, seed, or selection rule changes. There are now 14
development configurations, each paired with the same 18 Identity runs
(13 actual triggered conversions, 5 untriggered records).

The original controller is paused without stopping its child task. The task
finishes naturally; its attempt and score are retained regardless of outcome.
The replacement controller executes new frozen source and skips completed
attempts after validation. The original snapshot, registry, launch record and
process status are preserved. No model attempt is overwritten or retried.
Candidate selection still freezes before fresh seeds 4409, 5519, and 6637.
