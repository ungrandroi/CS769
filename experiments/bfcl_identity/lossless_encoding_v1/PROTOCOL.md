# Lossless graph encoding experiment

This study optimizes the delivered `readable-graph-1` payloads from
`work1000_research`. It does not reinterpret the earlier Compact experiments.
The frozen baseline explanations are State-Transition Graph: minimal,
Event Graph: full, Event Graph-Dedup: none.

Every candidate must decode to the exact original delivered JSON payload,
preserving types, list ordering, all source messages, graph entities, facts,
events, relationships, validity, and provenance. JSON object key ordering is
not semantic. Source-history and deterministic full-graph restoration remain
additional checks, not substitutes for payload decoding. No pruning, semantic
merging, summarization, or relevance selection is allowed. All conventions
visible to the model, including inline encoding rules, count toward input.

Development uses the existing six base/long-context conditions from families
3, 9, and 37 with seeds 1103, 2207, and 3301. The 13 triggered prefixes are
paired with existing current-format baselines. Candidates are evaluated with
no external explanation and, where different, the baseline explanation.
Per-method selection prioritizes development success count, then mean
post-conversion request tokens (first average within trajectory, then across
trajectories). An optimized candidate is not declared adopted unless it has
at least baseline success count and lower mean input. Otherwise the best
candidate is still independently evaluated as a failed/Pareto exploration,
with its status explicitly disclosed.

Before new evaluation, seeds 4409, 5519, and 6637 are registered for all 52
conditions (base, long_context, miss_func, miss_param). Candidates and selection
freeze before those Identity trajectories are generated. Each fresh Identity
prefix is used for current baseline and selected candidate for each of the
three methods. No new evaluation outcomes inform candidate design. These are
independent repetitions on historically seen conditions, not an unseen-task
test. Development conditions are reported separately from other conditions.

The local model remains Qwen3.8-27B-Q8_0, context 131072, output limit 4096,
temperature 0.6, top_p .95, top_k 20, repeat penalty 1, thinking disabled.
Native request evidence records all wire settings, service properties, and
model identity. Absolute-request seed is run_seed + request_index * 1000003.

Working history is native rendered full input minus the same request's
fixed-only template baseline. It must be strictly greater than 1000 tokens,
at the earliest complete tool-call/return boundary. System instructions and
tool definitions remain outside the threshold; dynamic user, assistant, call,
return, and message-wrapper tokens remain inside. Convert exactly once;
retain graph and any one-time inserted explanation as the context prefix and
append subsequent interactions. Retained instructions are charged on every
actual request. No hidden state, ground truth, or future actions enter memory.

Report official paired pass/fail changes, repeated-run uncertainty, first
post-conversion input, trajectory-weighted per-request mean, distributions and
peaks, and input decomposition. Total input is secondary. Untriggered cases
are reported separately and are not graph-conversion evidence. Diverged
request indices do not imply corresponding semantic actions.

Frozen source execution, launch hashes, native requests/responses, checkpoints,
logs and source code are retained. One detached controller owns the GPU queue.
Errors stop with `needs_review`; existing attempts are never overwritten and
failed scores are never selectively retried. Resumption verifies the saved
selection rather than reselecting. Independent audit and code cleanup follow
inference. User-maintained `visualization/`, credentials, and old experimental
records are not modified.
