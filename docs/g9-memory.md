# G9 evidence graph: code and integration

The maintained API is cs769.g9; see the [runtime guide](runtime.md) for the current layout and free test command. Existing scripts/core imports remain compatible. The validated G9 full-view settings remain unchanged.

This is the source for the **uncompressed G9 full-view profile** used in the
[G9 method report](../experiments/bfcl_identity/reports/g9-structure-method.md).
It replaces archived message history with one graph-derived memory text; it
does not attach the original identity history alongside the graph.

## Start here

- [Public entry point: `build_g9_memory`](../src/cs769/g9.py)
- [Offline, synthetic example](../examples/g9_memory.py)
- [G5 evidence builder: `build_evidence_graph`](../src/cs769/graphs/graph_memory_evidence.py)
- [G9 record/ID builder](../src/cs769/graphs/graph_memory_records.py) and
  [evaluated renderer](../src/cs769/graphs/graph_memory_record_views.py)
- [Source hashes and publication checks](g9-source-manifest.json)

The builder and example use only the Python standard library. From the repository
root, run:

```bash
PYTHONPATH=src python3 -B examples/g9_memory.py
```

This prints an illustrative message list. It makes no API calls, executes no
tools, and needs no credentials, BFCL dataset, or AppWorld installation.

## Minimal integration

```python
from cs769.g9 import build_g9_memory

# Two representations of the SAME completed history, not two model inputs.
# For OpenAI Chat format, the same message list can be used for both arguments.
memory = build_g9_memory(
    normalized_history,
    native_history,
    provider="openai",  # or "anthropic", with the native content-block history
    snapshot_boundary="archived_history_checkpoint",
)

messages = [
    *fixed_instruction_messages,
    {"role": "assistant", "content": memory["memory_text"]},
    current_user_message,
]
# Send messages with the original tool definitions and model settings.
# Do not append normalized_history, native_history, or memory["graph"].
```

`memory["graph"]` is a self-contained graph for local storage and inspection;
`memory["audits"]` contains integrity checks. Only `memory_text` goes into the
model's history slot. Fixed system/developer instructions, tool definitions,
and the new user request stay outside that slot. For Anthropic, system content
belongs in the API's separate system parameter, not in the messages list.

Call this at a completed history checkpoint: all tool calls must have matching
results and the archived turn must be finished. The current, unanswered user
request is not part of the archived history. The first-turn experiment boundary
is also available as `snapshot_boundary="end_of_first_user_turn"`.

Normalized history supports text messages and OpenAI-style tool calls/results
(Chat or Responses-style records). Native history preserves the provider's call
grouping and error flags. For Claude, provide the corresponding native
`tool_use`/`tool_result` blocks and use `provider="anthropic"`. Its normalized
history must contain the same visible text, calls and results. The experiment
treated old thinking consistently across identity and graph groups; signed
thinking is not rendered as visible graph evidence. This module does not provide
a general multimodal or AppWorld provider adapter.

## What is frozen

The entry point selects these settings explicitly; some low-level functions
have other defaults for earlier experiments. The function returns graph/text;
it does not choose the carrier message role. The carrier below describes the
original publication, while the runtime uses delivery.role from its selected configuration:

| Stage | Evaluated setting |
|---|---|
| G5 evidence | `build_evidence_graph(..., episodic_only=True)` |
| Observed-field layer | `observed-fields-v1`, retained internally |
| Payload tree | `build_payload_graph(...)` |
| G9 ID layer | `record-joins-v1` |
| Model-facing renderer | `render_record_view_graph(..., view="full", visible_observations=False)` |
| Historical experiment mode | `graph-record-view-full` |
| Carrier | One assistant message containing graph memory text |

G5 keeps visible user/assistant text, tool names, arguments and results as
evidence nodes, with order and call/result relationships. G9 adds a lossless
payload tree and references linking repeated identifiers. Its displayed body
is exactly the G5 evidence rendering, followed by an ID-reference appendix
when matching identifiers exist. The derived observation layer is not displayed.
This is not the older inline-marker `render_record_graph` profile, nor B's
native-history-plus-index method.

The stored G9 graph owns argument/result payloads in its payload tree rather
than duplicating their text in evidence nodes. To recover the G5 evidence view
for inspection or auditing, use the inverse functions, not a raw slice of G9:

```python
from cs769.graphs.graph_memory_observed import strip_observed_graph
from cs769.graphs.graph_memory_payload import restore_observed_graph
from cs769.graphs.graph_memory_records import strip_record_graph

evidence = strip_observed_graph(
    restore_observed_graph(strip_record_graph(memory["graph"]))
)
```

No original visible evidence is removed. The projection helpers in the frozen
modules produce offline plans with `applied=False` and
`task_preservation_certified=False`; they are not a validated compressor.

## Adapting to AppWorld

Unknown tools still retain their complete supported visible evidence. However,
the frozen cross-record ID rules are based on public BFCL tool schemas and
declared namespaces: ticket IDs, message user IDs, tweet IDs, travel booking/
card/insurance IDs, and trading order IDs. Equal values are linked only when
their namespace and value type also match. A match does not assert causality,
current state, success, or task dependency.

An AppWorld adapter should normalize its completed tool history and add explicit
rules for its own tool names, field paths and ID namespaces before expecting
these cross-record links. It should retain original visible payloads and check
round-trip integrity. Reusing G9's rendering does not by itself validate new
AppWorld extraction rules or task performance. AppWorld integration and paid
experiment runners are outside this publication.

## Offline checks and provenance

At the original source publication, ten graph modules and four test files were copied from the frozen runner. Their maintained implementations now live in src/cs769/graphs; scripts/core files are compatibility imports. The existing `event_graph.py` and
`state_transition_graph.py` dependencies were already present on `ruqi`; this
original publication did not replace them. The source manifest records that historical publication, rather than the current compatibility files. The new entry point selects the frozen
options, and the new example and integration tests make them easier to use.

The G9-specific suite contains **73 tests**. Run it against the maintained source with:

```bash
PYTHONPATH=src:tests python3 -B -m unittest \
  test_g9_memory test_graph_memory_observed test_graph_memory_payload \
  test_graph_memory_records test_graph_memory_record_render
```

The public-schema provenance test requires the repository's pinned BFCL
submodule (`git submodule update --init vendor/gorilla`). The entry-point tests
alone need no submodule: `PYTHONPATH=src:tests python3 -B -m unittest test_g9_memory`.

An offline replay of the previously published `multi_turn_base_194` example
reproduced both its complete graph hash and its **4,988-character model-facing
text byte for byte**. See the [original example and source hashes](../experiments/bfcl_identity/reports/evidence/g9/g5-g8-g9-base194-input-evidence.json)
and [original G9 model input](../experiments/bfcl_identity/reports/evidence/g9/g5-g8-g9-base194-R-memory.txt).
This check makes no new performance claim. The original source publication did not run paid inference or change official evaluation.
The later migration verified saved trajectories through unchanged official tools
and evaluation; see [the migration checks](legacy-removal.md).
