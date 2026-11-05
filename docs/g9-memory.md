# G9 evidence graph: code and integration

This is the source for the **uncompressed G9 full-view profile** used in the
[118-condition comparison](../experiments/bfcl_identity/reports/g9-event-matched118-results.md).
It replaces archived message history with one graph-derived memory text; it
does not attach the original identity history alongside the graph.

## Start here

- [Public entry point: `build_g9_memory`](../scripts/core/g9_memory.py)
- [Offline, synthetic example](../examples/g9_memory.py)
- [G5 evidence builder: `build_evidence_graph`](../scripts/core/graph_memory_evidence.py)
- [G9 record/ID builder](../scripts/core/graph_memory_records.py) and
  [evaluated renderer](../scripts/core/graph_memory_record_views.py)
- [Source hashes and publication checks](g9-source-manifest.json)

The builder and example use only the Python standard library. From the repository
root, run:

```bash
PYTHONPATH=scripts python3 examples/g9_memory.py
```

This prints an illustrative message list. It makes no API calls, executes no
tools, and needs no credentials, BFCL dataset, or AppWorld installation.

## Integration profiles

The builder returns graph memory; the caller chooses its placement. Two profiles have been evaluated, with the same graph settings:

| Profile | Checkpoint | Model-facing placement |
|---|---|---|
| Latest 118-condition GPT-4.1 comparison | Saved working-history JSON first exceeds 1,000 tokens; all tool calls have results, but the user turn may still be in progress | Fixed instructions followed by **one user message** containing the graph text; do not append a second copy of the current request/history |
| Earlier G9 validation | Completed archived user turn, before the next request | Fixed instructions, **one assistant message** containing graph text, then the next user request |

The threshold/counter, native-history normalization and replay belong to the experiment adapter, not this builder. The standalone example illustrates placement; it does not reproduce the BFCL runner. See the [frozen protocol](../experiments/bfcl_identity/reports/evidence/g9-matched118/protocol.json).

### Latest working-history placement

```python
from core.g9_memory import build_g9_memory

# working_history includes all visible non-system messages at the checkpoint,
# including the current user request and completed tool exchanges.
memory = build_g9_memory(working_history, native_working_history,
                         provider="openai",
                         snapshot_boundary="archived_history_checkpoint")
messages = [*fixed_instruction_messages,
            {"role": "user", "content": memory["memory_text"]}]
# Keep original tools/settings, then append only NEW continuation messages.
```

### Earlier completed-turn placement

```python
from core.g9_memory import build_g9_memory

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
model's history slot. Fixed system/developer instructions and tool definitions
stay outside that slot; request placement follows the selected profile above. For Anthropic, system content
belongs in the API's separate system parameter, not in the messages list.

In both profiles, every tool call must have its matching result before replacement.
For the earlier completed-turn profile, the next user request stays outside the
archived history. For the latest working-history profile, the current request is
already part of the history being converted. The first-turn boundary is also
available as `snapshot_boundary="end_of_first_user_turn"`.

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
have other defaults for earlier experiments:

| Stage | Evaluated setting |
|---|---|
| G5 evidence | `build_evidence_graph(..., episodic_only=True)` |
| Observed-field layer | `observed-fields-v1`, retained internally |
| Payload tree | `build_payload_graph(...)` |
| G9 ID layer | `record-joins-v1` |
| Model-facing renderer | `render_record_view_graph(..., view="full", visible_observations=False)` |
| Historical experiment mode | `graph-record-view-full` |
| Carrier | Chosen by the integration profile above; not selected by the builder |

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
from core.graph_memory_observed import strip_observed_graph
from core.graph_memory_payload import restore_observed_graph
from core.graph_memory_records import strip_record_graph

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

Ten graph modules and four existing test files were copied unchanged from the
frozen G9 experiment runner. The existing `event_graph.py` and
`state_transition_graph.py` dependencies are identical on `main` and `ruqi`; this
MR does not replace them. The new entry point selects the frozen
options, and the new example and integration tests make them easier to use.

The following command passed **73 tests** again on `main@960e6e5` plus this MR. The two public-schema fixtures were reused from the existing local BFCL snapshot and verified against their frozen hashes; they are not added to the MR:

```bash
PYTHONPATH=scripts:tests python3 -m unittest \
  test_g9_memory test_graph_memory_observed test_graph_memory_payload \
  test_graph_memory_records test_graph_memory_record_render
```

The public-schema provenance test requires the repository's pinned BFCL
submodule (`git submodule update --init vendor/gorilla`). The entry-point tests
alone need no submodule: `PYTHONPATH=scripts:tests python3 -m unittest test_g9_memory`.

An offline replay of the previously published `multi_turn_base_194` example
reproduced both its complete graph hash and its **4,988-character model-facing
text byte for byte**. See the [original example and source hashes](https://github.com/ungrandroi/CS769/blob/462ecb5f6ead22a5332fb0010cf5c641f6fce0a5/experiments/bfcl_identity/reports/evidence/g9/g5-g8-g9-base194-input-evidence.json)
and [original G9 model input](https://github.com/ungrandroi/CS769/blob/462ecb5f6ead22a5332fb0010cf5c641f6fce0a5/experiments/bfcl_identity/reports/evidence/g9/g5-g8-g9-base194-R-memory.txt).
This check makes no new performance claim. No paid experiment or official
evaluation was run or changed for this source publication.

Run `PYTHONPATH=scripts python3 examples/g9_memory.py --profile completed-turn` to see the earlier placement; the default example uses the latest working-history placement. No API calls or tool execution occur.
