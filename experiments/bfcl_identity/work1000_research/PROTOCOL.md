# Working-history graph conversion study

Status: protocol proposed before new inference. This directory is distinct from
the historical `history1000_eval` protocol, which counted tool content only.

## Question

After an agent has accumulated working history, can a graph replace that history
without materially worsening task completion, while keeping representation and
instruction overhead moderate? Fewer tokens than Identity is not a requirement.
Neither invertible serialization nor a matching point estimate proves equivalent
model behavior.

## Paired design

Use local Qwen3.8-27B-Q8_0 with thinking and historical thinking disabled.
Generate three independent Identity runs per task using predeclared seeds
1103, 2207, and 3301. Proposed common sampling settings: temperature 0.6,
top_p 0.95, top_k 20, repeat_penalty 1.0, maximum output 4096 tokens,
runtime context 131072. Verify which settings the server actually accepts and
record resolved settings and model hashes before inference. Do not silently
change sampling settings after observing scores.

### Recorded implementation details

The per-request seed is `run_seed + request_index * 1000003`, using zero-based
absolute request index shared by the Identity and graph branches. Distinct seeds
do not guarantee distinct trajectories; report actual diversity. The resolved
server sampler also uses min_p=0.05, typical_p=1, disabled XTC/DRY/Mirostat,
and zero presence/frequency penalties. These are recorded in
`runtime/slots-validation.json`; they are not interchangeable with a sampler
that sets min_p to zero. Historical temperature-zero scores are not controls.

At each next-model-request boundary, consider all working messages already
available, including the current user request. Trigger at the first boundary
where working tokens are strictly greater than 1000 and all tool calls have
their corresponding returns. Never split an assistant tool-call group from its
returns. There is no minimum-call, remaining-call, future-success, or final-score
eligibility filter. Preserve non-triggered and failed runs in the denominator.

Define working tokens as the exact native-template token count of the full
request minus the same request's fixed system/developer and tool-definition
template baseline. Thus user text, assistant text, tool arguments, results, and
their dynamic message wrappers contribute; fixed tool and system text do not.
Compute the baseline with that request's actual available tools, since missing-
function tasks can change tool availability. Record this operational definition,
the two token counts, the signed difference, and the complete checkpoint.
Audit unexpected negative or implausibly small differences; also report a
standalone dynamic-content token count as a reference, not a second trigger.
Any task-specific *dynamic* instruction must not be classified as fixed merely
because it has system/developer role.

The local server refuses rendering with no user message. The implementation
renders fixed messages and tools plus one empty user sentinel, requires exactly
one native `<|im_start|>user\n<|im_end|>\n` occurrence, removes that occurrence,
and tokenizes the remaining native prompt. This preserves the assistant
generation prefix in the fixed baseline. The exact native template/tokenizer,
not a generic chat-template estimate, determines this accounting.

At each eligible checkpoint compare Identity, State-Transition Graph, Event
Graph, and Event Graph-Dedup. Replay the identical prefix against a fresh BFCL
environment and verify exact history and tool-result equality before branching.
The original live Identity continuation is the paired control. Graph branches
share its prefix, runtime settings, task, and per-request seed schedule.
After one conversion retain the graph and append new interactions until the
task ends. Do not repeatedly compact or rewrite the growing suffix.

Graph construction may only read the prefix visible to the model. Ground truth,
future Identity actions, scorer states, and hidden simulator state must not enter
the memory. Simulator state may be read separately for independent replay audit.
Retain the current user goal explicitly and label assistant statements as
statements rather than verified environment facts.

## Dataset and development separation

The pinned local BFCL snapshot has 13 pure GorillaFileSystem tasks in each of
base, long_context, miss_func, and miss_param: 52 task-condition cases. All four
categories use the same 13 families: 1, 3, 6, 9, 10, 12, 16, 25, 26, 29, 37, 38,
39. They use simulated file tools, not a real Bash shell. The unused composite
dataset is excluded from this official-scoring study.

Predeclare development families 3, 9, 37; use their base and long_context cases
for candidate prompt/format selection. Remaining families are reserved for
this optimization cycle. Since historical experiments already exposed all
13 families, this is not a previously unseen benchmark. New miss_func and
miss_param conditions test transfer across conditions, not new-family generality.
Never tune on reserved/new-condition scores and still describe them as held out.

The full frozen-format study is 52 tasks x 3 prefixes = 156 Identity runs,
plus three graph continuations for each triggered prefix (at most 468 graph
continuations). Non-triggered graph entries are explicitly not applicable, not
fabricated live runs or evidence of graph success. Candidate-format ablations
are separate development records.

## Optimization and selection

Compare existing instructions, a minimal instruction, and no external
instruction on development cases. An instruction is inserted once at conversion;
if retained, its tokens still occur in subsequent requests. Record instruction
length and actual full input length separately. Do not reappend instructions.

Prefer self-descriptive representations, eliminating redundant records and
deterministically recoverable fields. Preserve frozen legacy codecs. Verify
round trips where claiming losslessness, including values, types, ordering,
duplicate events, exact tool returns, user goals, and assistant statements.
If a format omits graph annotations or facts and is not exactly reversible,
label that transformation explicitly rather than calling it lossless.

The initial `readable-graph-1` candidate is a new representation: a packed exact
source-message table plus a sparse graph index. Its full original graph is
recoverable by rerunning the pinned graph builder on the restored messages;
the model itself does not receive that builder or all original graph fields.
This is algorithm-dependent recoverability, not the historical codec's direct
full-graph decoding. Report this distinction when interpreting results. Its
`full` explanation is the candidate's full explanation, not a byte-identical
legacy instruction. An ablation of genuine legacy instructions must be named
and recorded separately rather than silently treating these as equivalent.

Select candidates using development results and freeze their code/hash before
reserved evaluation. Prioritize paired completion over token reduction. Report
all candidate attempts, not only the chosen configuration. Do not interpret
selection on a handful of trajectories as evidence of reliable equivalence.

## Required reports

* All-run official pass counts, triggered-only paired pass counts, and explicit
  untriggered, pre-trigger failure, execution-error, and resource-limit counts.
* Paired wins/losses versus Identity by task, seed, condition, and family.
  Report exact discordant-pair counts; aggregate uncertainty at family level
  because repeated seeds/conditions are not independent tasks.
* First post-conversion full input tokens, absolute difference and ratio to
  the paired Identity request; graph and instruction token components.
* Each subsequent request's full input, peak input, output tokens, tool errors,
  and request count. Requests after branching are not action-aligned.
* Cumulative input is a secondary cost metric only. Report medians, quartiles,
  tail inflation, and per-case values rather than a mean alone.
* Prefix diversity per task: unique normalized tool-name/argument trajectories,
  exact working-history hashes, trigger locations, and prefix outcome types.
  Strip generated call IDs before diversity comparison. Do not discard duplicate
  histories or reseed them until they become different.
* Artifact/source hashes, local model identity, resolved server configuration,
  actual input token accounting, and official scorer provenance.

Do not claim noninferiority without a prespecified margin and sufficient evidence.
Report observed paired differences and uncertainty; a small study can remain
inconclusive even when pass counts match. No fixed token-ratio acceptance limit
has been requested by the user; report the full distribution and visible tails.

## Preservation

Do not alter `visualization/`, historical experimental trajectories, or frozen
`source_code/` snapshots. Do not commit credentials, environments, weights, or
machine caches. New protocol, code, reports, and records must be clearly separated
from earlier experiments.

### Frozen selection rule before graph continuations

For each graph method independently, select among none/minimal/full using all
triggered development prefixes: highest official pass count, then lowest mean
first post-conversion full-input ratio to paired Identity, then the fixed order
none, minimal, full. Errors stop the study rather than being omitted or retried.
A one-branch live pilot is followed automatically by the full development stage;
its result is reused, never regenerated. The controller runs from a frozen source
snapshot and verifies snapshot hashes around every task. Final reporting requires
independent audit; inference completion does not itself certify results.

### Native-template delivery and replay compatibility

All three graph methods deliver the single converted memory in a user-role
container, with fixed instructions and tool definitions unchanged. Original user
requests remain exactly once inside the source-message table. No extra goal copy
or template instruction is appended. This role choice is required because the
native model template rejects an assistant-only conversation; it is recorded in
every actual request. Existing replayed SDK responses use their archived output
records when extending history, avoiding new null fields inserted by a newer SDK.
Full replay request equality remains mandatory. Two preflight attempts stopped
before any inference and remain preserved under failed-preflight/.
