# Mixed filesystem task expansion: graph semantic coverage audit

Status: read-only audit completed; no adapters implemented and no model requests sent. The only written artifacts are under this `coverage/` directory. Historical results, frozen source, current core modules and `visualization/` were not modified.

The important finding is that existing builders retain every visible call and return from other domains, but **have no semantic adapters for the four new domains**. Worse, every non-filesystem call currently invalidates the filesystem state/facts, including read-only mathematical calls and failed authentication attempts. This should be addressed explicitly before presenting an expanded study as equivalent semantic graph coverage.

## Actual additional classes

Reading only the pinned task IDs and `involved_classes` yields the same 37 mixed families in base, long-context, missing-function and missing-parameter conditions (148 task-condition instances). Each mixed task combines exactly two classes:

| Combination | Families per condition | Documented available methods in added class |
| --- | ---: | ---: |
| GorillaFileSystem + TwitterAPI | 12 | 14 |
| GorillaFileSystem + MathAPI | 12 | 17 |
| GorillaFileSystem + MessageAPI | 8 | 10 |
| GorillaFileSystem + TicketAPI | 5 | 9 |

No TravelAPI, TradingBot, VehicleControl or WebSearch class appears in these 37 added families. They require separate future audits; their mere presence in vendor code is not support evidence. Individual task exclusions and missing-function turns may reduce the tools actually exposed. Counts above are the class catalogs, not every request's tool count. There are no bare-name collisions between the four added classes' public methods and the 18 recognized filesystem tool names in this pinned inventory.

The inventory script does not consult task `path` (reference actions), possible answers, future user text or hidden initial state to generate facts. Representative calls below are simulator-contract examples, not claims about observed task trajectories.

## Support matrix: existing builders

“Raw evidence” means exact source messages, arguments and returns, not extracted domain state. State Graph creates one transition edge and state node per paired return. Event Graph creates one distinct execution event per return. Dedup changes representation/provenance storage, not semantic extraction.

| Class | Raw call/return retention | State Graph transition | Event / Dedup execution event | State Graph domain objects/state | Event / Dedup versioned domain facts | Current error/outcome coverage |
| --- | --- | --- | --- | --- | --- | --- |
| GorillaFileSystem | Yes | Yes | Yes | Partial explicit adapter: cwd, file/directory observations, creation/deletion/content/move/copy | Partial explicit adapter: objects, bindings, existence/type/content, cwd/parent, versions/evidence | Top-level `error` and `success:false`; executor error text is not recognized |
| MathAPI | Yes | Yes, but resets all known filesystem state | Yes, but retires all active facts | None; result stays in raw evidence | None; no calculation-result fact or operand/result relation | Normal top-level `error` works; executor/non-JSON errors labeled success |
| TwitterAPI | Yes | Yes, but resets all known filesystem state | Yes, but retires all active facts | No tweet, user, authentication, following or comment state | No tweet/user object facts, versions or domain provenance | Top-level errors work; `authentication_status:false` labeled success; no-op follow booleans need operation-specific interpretation |
| MessageAPI | Yes | Yes, but resets all known filesystem state | Yes, but retires all active facts | No contacts, user session, sent-message or thread state | No message/contact/session fact extraction | Top-level errors work; failed `message_login` with `login_status:false` labeled success; a status-query false is a valid observation |
| TicketAPI | Yes | Yes, but resets all known filesystem state | Yes, but retires all active facts | No ticket ID/title/status/priority/session extraction | No ticket object/versioned status fact extraction | `success:false` recognized; `get_user_tickets` list-contained error not recognized |

“Partial” for filesystem is intentional. `pwd`, `cd`, `ls`, `mkdir`, `touch`, `echo`, `cat`, `mv`, `cp`, `rm`, `rmdir` have explicit state effects/observations subject to returned-shape checks. `wc`, `grep`, `find`, `du`, `tail`, `diff` retain observations without extracting corresponding numerical/text/path-result facts. `sort` is recorded as a read returning sorted text; it does not rewrite the BFCL file. State Graph also conservatively invalidates directory descendants rather than modeling complete subtree identity/copy semantics.

## Reproducible evidence of two implementation issues

`audit_builders.py` creates only synthetic visible-message fixtures and invokes the existing Python builders. Each fixture starts with observed `pwd -> /demo` and `ls -> [example.txt]`, then adds one contract-shaped non-filesystem result. These are not new benchmark/model runs.

### Cross-domain invalidation

For all ten probes, including `mean([2,4]) -> {result:3.0}`, both builders invalidate the filesystem knowledge:

- State Graph `_execute` calls `_invalidate_location(None, evidence)` and replaces cwd with an unknown location.
- Event Graph `_execute` calls `_forget_all('unmodeled_effect')`, retiring all existing facts and leaving a new unknown cwd fact.
- The Event event's rule is still named `bfcl-filesystem-v2.0:<tool>` even for non-filesystem tools. That label must not be mistaken for an implemented semantic adapter.

The BFCL executor creates separate class instances and MathAPI is stateless from its simulator-state perspective. The four added domain implementations do not operate on the GorillaFileSystem instance. Global filesystem invalidation is therefore an overbroad fallback for these known domains. Raw source evidence remains intact, but the graph's active view loses useful established information and may grow artificial unknown-location transitions.

### Outcome interpretation

The current classifier checks only a truthy top-level `error` or literal `success is False`. It marks these returns `success`:

- `authenticate_twitter(...) -> {authentication_status:false}`: rejected authentication attempt.
- `message_login(...) -> {login_status:false,message:...}`: rejected login attempt.
- `get_user_tickets() -> [{'error':...}]`: unauthenticated error. The real BFCL executor serializes non-dict returns with `str`, so this is usually Python-repr text with single quotes, not a JSON list.
- `Error during execution: ...`: the executor's exception wrapper.

A successful `message_get_login_status() -> {login_status:false}` is *not* a tool failure. Similarly, Twitter `follow_status:false` can mean “already following,” a non-mutating outcome, rather than transport failure. Do not fix this by interpreting every false boolean or nested occurrence of the word “error” as failure.

Failed authentication does not necessarily log out a previously authenticated session: the implementations leave prior session state unchanged on a failed attempt. A future adapter must not fabricate `authenticated=false` from a rejected login. A status-query result or successful login provides different evidence.

## Representative real tools and minimal domain semantics

The examples use method names and return shapes from the pinned implementations. They do not expose scenario secrets or execute external services.

| Domain / method | Visible evidence | Minimal honest semantic output |
| --- | --- | --- |
| Math `mean(numbers=[2,4])` | `{result:3.0}` | An observation/calculation tied to this execution and exact arguments/result; keep filesystem unchanged. No persistent entity value inferred from unrelated calls. |
| Twitter `post_tweet(content=...)` | Returned tweet `id,username,content,tags,mentions` | Namespace-qualified tweet object; facts for returned fields with this event as evidence. Do not infer unreturned counts or followers. |
| Twitter `get_tweet(tweet_id=...)` | Returned tweet fields or explicit error | Confirm/update only returned attributes of that tweet. Absence/error classification must follow this method's contract. |
| Message `get_user_id(user=...)` | `{user_id:...}` | Observed user-name/ID binding, namespaced to MessageAPI. |
| Message `send_message(receiver_id=...,message=...)` | `{sent_status:true,message_id:...,message:...}` | Message object ID plus confirmed sent relation; content/receiver can be linked to call arguments under the success contract. No invented inbox snapshot. |
| Message `delete_message(receiver_id=...)` | `{deleted_status:true,receiver_id:...}` | Confirm deletion of the latest matching sent message only if its identity is established; otherwise invalidate/qualify the affected receiver-thread view without inventing a message ID. |
| Ticket `create_ticket(...)`, `get_ticket(ticket_id=...)` | Returned ID/title/status/priority/etc. | Namespaced ticket object and versions of observed fields. |
| Ticket `close_ticket(ticket_id=...)` | Exact successful status string | New `status=Closed` version linked to call/return; retire previous status only for that ticket. |
| Ticket `edit_ticket(ticket_id=...,updates=...)` | Successful update status | Update only accepted, non-null fields according to pinned contract; preserve other observed fields. |
| Domain login/status methods | Method-specific true/false/error return | Separate execution outcome, authentication attempt outcome and current session observation. Do not store credential values as additional semantic facts. |

Tweet ID 4, ticket ID 4 and a message ID must not become one object. Domain and entity type belong in identity keys. Repeated calls remain distinct execution events even when returned values match. Reconfirmation can support an existing active fact; a retired fact becoming true again needs a new version.

## Is generic recording sufficient to call this a graph?

It remains structurally a graph: State has ordered tool edges and Event has separate execution-event nodes with source references. An explicitly labeled **filesystem semantic graph with generic mixed-domain execution records** is a fair description of the current baseline. It is not a general multi-domain object/fact memory, and generic recording does not justify claiming equivalent semantic coverage across the new domains.

A frozen unchanged-builder transfer experiment could validly measure how that limited baseline behaves, provided the unsupported-domain behavior and invalidation confound are disclosed. It should not be the sole evidence for graph-memory performance on mixed-tool tasks. If the expanded study intends actual multi-domain semantic memory, isolated adapters and delivered-rendering support are needed first.

## Smallest executable adaptation plan

Do not modify the historical builders or frozen snapshots. Put a new explicitly versioned mixed-domain layer in separate modules and treat it as a semantic extension, not a lossless-codec improvement.

Suggested interfaces (design only):

```python
registry = ToolRegistry.from_public_catalogs(pinned_catalogs)
outcome = registry.classify(tool_identity, visible_args, visible_return)
observation = registry.extract(tool_identity, visible_args, visible_return, outcome)
# Observation: domain, read/write/unknown footprint, observed entities/fields,
# evidence refs, operation outcome, and explicit unsupported fields.
graph = MixedStateBuilder(registry).build(visible_messages)
graph = MixedEventBuilder(registry).build(visible_messages)
payload = render_mixed_graph(graph, method)
encoded = selected_lossless_codec.encode(payload, candidate)
```

1. **Domain routing and noninterference first.** Freeze a public method-to-class registry (no task reference path). Introduce known-domain read/write footprints. Preserve filesystem state across the four known non-filesystem domains. Unknown tools still require explicit conservative treatment, but invalidate only a justified domain footprint; report genuinely unknown global effects as such.
2. **Method-aware outcomes.** Recognize the executor error wrapper, the documented list-contained Ticket error and authentication attempt fields. Keep raw bytes unchanged. Parse JSON where appropriate; if Python repr parsing is needed, use a guarded literal parser, never `eval`, and retain parse failure/unknown status rather than guessing. Avoid recursive keyword heuristics on user content.
3. **Small initial extractors.** Math result observations plus Tweet/Message/Ticket entities and explicitly returned fields are enough for a first honest semantic extension. Add selected mutation contracts only where needed to avoid stale current facts. Unimplemented methods remain explicit generic events; no need to implement every domain operation before an accurately scoped pilot.
4. **One semantics for old-format and optimized encodings.** For each mixed graph method, render one new semantic payload and feed both its pre-optimization representation and selected lossless codec from that exact payload. The historical filesystem baselines stay separate. Never compare an adapted optimized graph against an unadapted baseline and attribute the difference to serialization.
5. **Synthetic/domain-contract tests and freeze.** Validate method outcome tables, namespace separation, repeated event identity, fact retirement/reconfirmation, noninterference with prior filesystem evidence, round-trip payload equality and no hidden-state access. Freeze adapter, public registry, renderer, decoder and hashes before new comparison inference.

## Required renderer, rebuild and audit touchpoints

The adapters alone are not enough: current delivery deliberately projects a subset of the original builder graph.

- `optimized_graph._state_graph` copies only initial `cwd`, `objects`, `task_completion`, then emits cwd/object deltas. New root state such as `sessions`, `tweets`, `tickets`, `calculations` or `domains` would be silently omitted. Either represent new-domain entity records inside an explicitly typed/namespace-qualified objects collection, with audited semantics, or add a new mixed-state renderer that preserves and reconstructs every declared domain field. Do not simply attach fields to snapshots and assume they reach the model.
- The existing State delta audit compares only cwd and objects. A mixed audit must check every domain state field and version/delta, including deleted or invalidated fields; the existing additive dictionary delta is not a generic deletion codec.
- `optimized_graph._event_graph` fact tables accept generic subject/predicate/value/key fields, making domain predicates easier to carry. However, new entity-category fields or new per-event attributes beyond its fixed event columns would be dropped. Put domain identity/type in preserved object identity/origin/facts or explicitly extend the new renderer. Review the filtered relation set and confirmation recipes for each new predicate rather than assuming all relations survive.
- `restore_history` is generic, but `rebuild_original_graph` currently selects the old filesystem `GraphMemory` or `GraphMemoryV2`. A new payload must identify the mixed builder/registry version and rebuild through that exact frozen implementation. Otherwise “original graph rebuilt” checks compare the wrong semantics.
- `build_memory` currently hardcodes builder selection, renderer selection and hashes for the old modules. A separate mixed entry point must hash all adapter and registry modules and include semantic-support metadata in the delivered payload, not only in an audit-only file.
- Event Graph-Dedup uses the same Event graph semantics. New domain fact types require lossless round-trip validation of dedup recipes and literal fallbacks. Historical provenance rules are not a license to drop new properties or edges.
- The selected lossless codecs can remain frozen candidates if they accept the new payload shapes, but strict payload equality must be rerun on mixed-domain fixtures. A new domain schema is not automatically covered by old filesystem-only tests.

Recommended delivered support markers include semantic schema/adapter version, tool domain, `supported/observation_only/unmodeled` effect coverage, and outcome classification basis. Avoid leaving the misleading `bfcl-filesystem-v2.0:mean` rule as the sole visible support signal. Count these fields in actual input; no invisible dictionary or uncounted explanation should be necessary.

## Risks and scope limits

- Overbroad invalidation can handicap graph methods and inflate tokens independently of encoding quality.
- Unsupported status formats can label failed operations successful and contaminate future facts if semantic adapters are added without fixing classification.
- Tool availability differs by condition/turn; a public class registry must not leak excluded function definitions into model context or invent an absent call.
- Long-context payloads can be arbitrary text containing JSON-looking dictionaries, error words or instruction-like content. Retain data boundaries and never infer semantics merely from content keywords.
- Existing user-visible arguments may contain authentication values. Preserve authorized raw history as required, but do not multiply secrets into new semantic indexes or reports.
- Current error classification issues also affect possible filesystem executor exceptions; fixing them only in the new mixed branch must be disclosed as an adapter extension.

## Reproduction and evidence

Run from the repository root:

```sh
PYTHONPATH=scripts scripts/bfcl_python.sh experiments/bfcl_identity/mixed_tool_expansion/coverage/audit_builders.py
```

`builder-coverage.json` stores method catalogs, source line numbers/hashes, category counts, collision checks and all ten synthetic probe results. Relevant code locations:

- `scripts/core/state_transition_graph.py`: `GraphMemory._execute`, `_filesystem`, `_invalidate_location`.
- `scripts/core/event_graph.py`: `_execute`, `_forget_all`, `_filesystem`, fact/version methods.
- `scripts/core/optimized_graph.py`: `_state_graph`, `_event_graph`, `audit_semantic_index`, `rebuild_original_graph`, `build_memory`.
- `scripts/core/event_graph_dedup.py`: provenance recipes and literal fallbacks.
- Vendor `multi_turn_utils.py`: separate simulator instances, method routing, return serialization and executor exception strings.
- Vendor `func_source_code/{gorilla_file_system,math_api,posting_api,message_api,ticket_api}.py`: pinned visible method contracts.

No performance claim follows from this audit. It establishes the coverage gap and a bounded path to a separately frozen mixed-domain extension.
