# Readable graph development candidate

This directory contains **offline development measurements**, not task scores.
Only development families 3, 9, and 37 (Base / Long Context) are inspected.
`offline-first-turn.json` uses frozen first-turn histories for a preliminary
encoding check; it does **not** represent the new 1,000-token checkpoints.

Implementation: `scripts/core/optimized_graph.py`, candidate `readable-graph-1`.
The API is `build_memory(history, method, explanation, count) -> (text, metadata)`.
It accepts nonfixed visible messages only and rejects unmatched tool calls.

## Representations

All three candidates store original messages **once as source message nodes**.
Explicit source-message column names and shared metadata avoid repeated wrapper
keys. Original text, exact tool arguments/returns, API metadata, user inputs,
assistant statements, repeated calls, errors, and chronological order survive.
The semantic graph refers to these nodes; it does not duplicate raw tool logs.
This is a source-message graph with a sparse semantic index, not the old pure
full-graph codec. Keeping source messages readable is an intentional tradeoff.

- **State-Transition Graph:** initial state plus state deltas; unchanged object
  fields persist. Tool-call edges link state IDs and input/return message IDs.
  Unchanged complete snapshots and accumulated observation lists are not copied.
- **Event Graph:** explicit columns describe object, fact, event, relation, and
  confirmation tables. Facts retain value, versions, observation time, and
  retirement information. Derivable relation/index duplication is omitted.
- **Event Graph-Dedup:** same semantic tables, but confirmations refer to source
  events. Exceptions to the exact default provenance are retained literally.
  Distinct calls and repeated confirmations are never merged.

Source message metadata defaults and table columns are part of the graph body,
so their cost is counted even when explanation mode is `none`.

## Explanation ablation

- `none`: graph JSON only, zero separately prepended instruction tokens.
- `minimal`: short memory/status guidance.
- `full`: complete guidance for **this new representation**, not the incompatible
  old compact-codec grammar. `existing` is an API alias for this mode; it is not
  an assertion that the old explanation text was reused.

The explanation is inserted once at compaction. If retained in later requests,
its tokens remain included in those requests. Current user content is already
inside source nodes; the runner must not append a duplicate task request.

## What reconstruction means

Every source message field, type, list order, and repeated element is restored.
JSON dictionary key order is not preserved and has no semantic meaning here.
The original complete V1/V2 graph is rebuilt from restored visible messages by
its deterministic builder. This is **algorithm-dependent reconstruction**, not
field-by-field decoding of the old codec. Builder and candidate hashes are
recorded with each result. Reconstruction never accesses the task answer,
future messages, hidden environment, or simulator state.

A separate semantic audit replays delivered V1 deltas and checks the original
cwd/object states, and checks V2 fact versions/validity and distinct event
input/return/status references. Exact message and original-graph reconstruction
are additionally asserted on every build. Tests cover repeated calls, failures,
state/fact corruption, chat/Responses formats, and literal reference-like text.

## Interpretation limits

A shorter serialized memory does not establish equal task performance. Some
histories, particularly Long Context 37, still produce more tokens than the
old Dedup format. Full-input comparisons must use the actual chat template,
fixed system/tool definition overhead, and the same checkpoint. Do not treat
raw-history JSON token counts as Identity API input counts. Model continuations
and official scores are owned by the separate experiment runner.
