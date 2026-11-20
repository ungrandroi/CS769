# General state/evidence pruning (experimental, opt-in)

Unified editor: `prune_general_history`, implementation `src/cs769/edits/general_pruning.py`.
It receives only the current visible graph and current user request. It never reads task IDs, future questions, official answers, or hidden initial state.

Controls are native identity, full evidence graph, and exact structural sharing. The candidate uses the same exact-sharing routine and at most one checked relation edit. It selects the largest additional rendered saving over sharing, with stable tie-breaking; no eligible positive edit falls back to the sharing control. No separate identity history is appended to the graph input.

Supported reviewed relationships:
- A direct-child find result and a later serial successful local move in an unchanged cwd frame. Both paths remain in the retained move receipt. This is redundant location evidence, not a claim of information loss.
- A vehicle property observation and a successful update of that entire observed property. Partial updates and unknown intervening operations are rejected. Other fields remain intact. Fuel increments plus resulting level make the prior level arithmetically recoverable and are labelled accordingly.
- Existing stock-price/order and itinerary/booking-receipt relations. A matching booking is not claimed to causally consume a price argument.

Failed updates, ambiguous scope, parallel witnesses and explicit historical/comparison requests cannot justify deletion. These eligibility checks do not prove that unknown future questions will never need removed details.

The graph mutation reuses checked relation projection and reconstruction; exact sharing must round-trip. Only the declared event pair or fields may change. The neutral omission notice and reference overhead count toward the minimum 50-token saving.

This optional editor does not change existing evidence graph, previous edit profiles, the official BFCL evaluator, or model settings. Tests: `tests/test_general_pruning.py`.

Experiment records remain outside source under `/nobackup/ruqi/CS769/evidence/edits/general-edit-pilot-plan-20261114`. The fixed overall sample and selected history diagnostics are reported separately. Controlled short questions are not official BFCL scores.
