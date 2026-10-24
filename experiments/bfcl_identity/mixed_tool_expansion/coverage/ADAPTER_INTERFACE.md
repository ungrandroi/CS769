# Shared mixed-domain adapter and State schema

Status: implemented separately from historical builders; awaiting final independent integration audit/freeze. No model calls were made by the State adapter agent.

## Shared observation contract

`core.mixed_observations.domain_effect(tool, args, raw)` accepts only a visible call and return. It returns a JSON-safe structure containing:

```text
domain, method, status, error, basis, coverage, footprint,
parsed_output,
updates: [{entity, fields}],
invalidations: [{domain, entity, fields, reason}],
observations: [{kind, value}],
operation: {} or {kind: "delete_latest_message", receiver_id}
```

- `status`: success / error / noop / unknown. This is an operation/execution result, not task completion.
- `coverage`: modeled / observation_only / unmodeled; delegated filesystem operations use filesystem_adapter.
- `footprint`: read / write / unknown.
- Namespaced entity IDs are `Domain:type:<JSON scalar ID>`. Integer `4` and string `"4"` remain distinct, and IDs may contain punctuation without becoming ambiguous when split at the first two colons.
- Apply invalidations before updates. Null entity means all matching domain entities; null domain means globally unknown scope. Null fields means all current assertions for those entities. Retired versions are retained.
- Known-domain failures do not imply successful mutation or log out an existing session. Unknown-tool failure still has unknown side effects, so it explicitly invalidates all current state assertions conservatively.
- `parse_visible_return` returns a parsed JSON value, a guarded literal interpretation of BFCL list/dict repr, or unchanged raw text. It never evaluates code; non-JSON-safe literal structures remain raw. Raw source history is always retained separately.

`registry()` contains all 68 public tool names from the five pinned catalogs, method/domain/footprint routing and hashes for all five catalogs and five simulator contracts. It does not read a task's private state, reference actions or future text. Both bare public names and correctly class-qualified public names resolve. Its catalog must not be passed wholesale into model context; the runner separately controls currently available tools.

### Implemented semantics

- Filesystem behavior delegates to the historical adapter for recognized successful outcomes; executor errors and unrecognized writes do not fabricate success effects. Known non-filesystem domains do not clear filesystem state.
- Math produces per-execution result observations.
- Twitter extracts returned tweet fields and lists of returned tweets; comment/mention mutations invalidate the affected incomplete aggregate view; following snapshots and operations are represented conservatively; statistics and retweets are observations.
- Message extracts returned user bindings, contact creation and sent-message identifiers. The actual simulator's nested `message_id: {new_id: ...}` is supported. Read snapshots are observations.
- Ticket extracts returned fields and successful create/get/list/close/resolve/edit contracts; partial edits do not clear unchanged fields or apply null updates.
- Login/status operations use method-aware booleans. Successful login replaces the current session view; failed attempts leave it unchanged. False status queries are valid logged-out observations. Credentials are never copied into semantic entities or observations.
- Unsupported or malformed known writes invalidate only their own domain; unsupported reads remain explicit observations/unmodeled outcomes without clearing unrelated state.

### Deliberate limitations

- `delete_message` returns a receiver, not a deleted message identity. In addition, the simulator removes by value from a list. Both new builders therefore invalidate `exists` for all known messages to that receiver instead of inventing a particular deleted ID; historical sent/content evidence remains.
- List/query results do not imply that omitted entities are nonexistent. No complete hidden catalog, inbox or ticket queue is inferred.
- Social statistics are dated observations, not durable counters updated by guessed arithmetic. No attempt is made to reconstruct every domain's full private state.
- A raw response and its call remain available even when no semantic extractor handles it. Coverage remains explicit in event/edge metadata and top-level summaries.

## State graph contract

`core.mixed_state_graph.MixedStateGraph().build(history)` preserves the old State graph fields, source protocol messages, one node per paired result and one edge per executed call. It adds `state.domain_state` to every node, including `s0`:

```text
domain_state:
  entities:
    <namespace ID>:
      domain, entity_type, local_id
      fields: current values by field
      evidence: current supporting message refs by field
      versions:
        <field>: [
          {version, value, valid_from, retired_at, retired_reason,
           confirmations: [{event, at_step, messages}]}
        ]
  observations: [{kind, value, domain, at_step, event, evidence}]
```

`local_id` stores the JSON spelling used in the namespace ID. Version numbers distinguish new observations after retirement even if the value recurs; repeated observations of an active unchanged field add confirmations. Every state snapshot is copied, so later updates do not alter older nodes. Current evidence is removed on invalidation, while historical versions remain.

Each edge adds `domain`, `coverage`, `outcome_basis`. There is no duplicate full `domain_effect` payload on the edge. Top-level markers are `semantic_schema_version`, `adapter_version`, `registry_version`, `domain_coverage`; coverage lists only tools actually observed. Contract hashes and compatibility aliases remain audit metadata, not mandatory model-facing token overhead.

The mixed renderer must serialize and exactly reconstruct **all** declared state fields, including domain entities, evidence, versions and observations. The existing cwd/objects-only renderer is insufficient. The coordinator owns the separate mixed renderer and its full-state delta audits.

## Validation performed

At implementation handoff:

- Shared adapters and State builder: 14 tests passed.
- Shared + State + Event + renderer integration: 36 tests passed at the later cross-review checkpoint.
- Historical State tests in the BFCL conda environment: 12 passed.
- Event agent independently reviewed shared/State code. Its findings on JSON-safe parsing and unknown-error invalidation were addressed before integration.
- State agent independently reviewed Event code and its tests; no unaddressed domain isolation, identity or versioning defect was found in that read-only review.

Test counts describe specific checkpoints, not a final whole-project audit. No capability claim or benchmark performance result follows from these tests. The coordinator must freeze adapters, registry contracts, renderer and selected codecs only after final audit, and use identical adapted semantics for each baseline/optimized pair.
