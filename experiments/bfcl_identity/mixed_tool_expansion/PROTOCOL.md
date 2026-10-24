# Mixed-tool graph-memory expansion

Status: adapters and orchestration implemented; independent preflight pending.
No mixed-tool model evaluation has started.

## Scope and distinction from the completed study

The pinned BFCL inventory contains 37 additional filesystem-plus-other-tool
families. Each appears in Base, Long Context, Missing Function and Missing
Parameter conditions: 148 task-condition instances. Partner domains are
Twitter (12 families), Math (12), Message (8) and Ticket (5). “Additional”
means outside the completed thirteen-family study, not a claim that none
were ever inspected elsewhere in this project.

This is a separately versioned semantic extension. The historical builders,
trajectories and frozen source remain unchanged. The old builders invalidated
all known file facts after external tool calls and did not extract facts for
the four partner domains. The new builders isolate known domains, distinguish
method-specific outcomes, and extract explicitly observed entities/fields or
calculation observations. Unsupported effects are marked as such.

Both original-format and optimized graph arms use the **same new semantic
payload**. Comparisons estimate encoding differences conditional on these
adapters; they do not isolate the effect of adapters themselves. There is no
unadapted mixed-domain transfer arm in this registered seven-arm study.

## Fixed methods and model

The model remains local Qwen3.8-27B-Q8_0, context 131072, temperature 0.6,
top-p 0.95, top-k 20, repetition penalty 1.0, maximum output 4096.
The same native request accounting and sampler-seed derivation as the prior
study are retained. Unspecified server defaults, including min-p approximately
0.05, are recorded in `runtime/props.json` and `runtime/slots.json`; this study
reuses the same single-slot server and disables reasoning output as before.

| Arm | Encoding | External explanation |
| --- | --- | --- |
| Identity | Original working history | None |
| State original-format | Mixed State graph payload | Minimal |
| State selected | `state-shared-v1` | Minimal |
| Event original-format | Mixed Event graph payload | Full |
| Event selected | `tables-v1` | Minimal |
| Dedup original-format | Mixed Event provenance-dedup payload | None |
| Dedup selected | `shared-v1` | None |

Selected codecs and explanation choices are copied from the completed
`lossless_encoding_v1/selection.json`, with its hash. No new codec selection
or parameter search is permitted using this expansion's fresh outcomes.
The Event comparison still changes the external explanation from full to
minimal, so it is an overall input-format comparison, not a codec-only effect.

## Shared-prefix protocol

Each task/seed first runs Identity. The conversion boundary is the first
request with **native full input tokens minus native fixed-only template
tokens strictly greater than 1000**, with all preceding calls paired with
returns. Fixed tools and system/developer prompts are excluded from the
trigger. Turn boundaries and a minimum call count are not extra conditions.

Six graph arms replay exactly that Identity prefix and start at the same
boundary, model configuration and per-request seed schedule. History is
replaced once by the graph payload; subsequent messages are appended until
the task ends. Neither the graph nor the explanation is reinserted as a new
message each step. Retained graph, inline rules and external explanation
still count in every actual request that carries them.

The adapter sees only visible history. It cannot inspect benchmark reference
actions, hidden simulator initial state, future requests or task answers.
Source messages remain exact, assistant text remains unverified, and raw
credential-bearing source arguments are not multiplied into semantic facts.

## Development, review and fresh evaluation

The development families are selected by domain coverage before any new
model outcomes: Twitter 0, Ticket 2, Message 14 and Math 15. Only their Base
and Long Context conditions are used, with seeds 1103, 2207 and 3301:
24 Identity runs and up to 144 graph continuations. Development checks
integration and semantic correctness; it does not reselect codecs.

Fresh seeds **15013, 16033 and 17041** were reserved before model inference
and were absent from existing experiment manifest seed fields. Fresh
evaluation covers all 148 task-condition instances: 444 Identity runs and
at most 2664 graph continuations. Actual graph continuations depend on the
trigger; untriggered cases are recorded separately.

Before starting development, an independent preflight must approve the exact
frozen source, task split, selection and vendor pins. After development, the
controller waits for an independent review tied to those same hashes and
the complete development manifest digest. It cannot enter fresh evaluation
without that matching review. Any semantic defect requires a documented
new version and preserved prior attempts; failed scores are never retried
to select a favorable outcome. Fresh outcomes cannot change adapters.

## Evidence and reporting

The controller runs detached, serially, from a frozen source snapshot.
It stores launch commands, hashes, status, logs and each native model
request/response. Source or protocol changes, incomplete attempts and
configuration mismatches stop with `needs_review`; existing attempts are
never overwritten. Public contracts, catalogs, benchmark data and evaluator
code are pinned separately in `vendor-pins.json`.

For every graph, audit the actual delivered payload and direct codec decode;
also restore full original source history and the deterministic full mixed
graph. State audits reconstruct every declared domain field at every node,
including deletions and appended versions. Event audits retain domain
object/fact metadata, execution coverage/outcome metadata, and nonderived
relation attributes. These semantic checks are additional to encoding
losslessness, not a replacement for it.

Report official success counts, paired gains/losses, first-boundary input,
per-trajectory mean actual subsequent input, working/fixed decomposition,
per-request and per-user-turn CSVs, and family-clustered uncertainty. Separate
the eight exact development conditions, all four development families, other
families, and the four BFCL conditions. Only the first post-conversion request
is aligned to the same continuation boundary; later ordinal requests may
represent different actions. Equal total success counts are not proof of
per-task preservation or statistical equivalence.

Automatic mechanical checks and reports are followed by independent final
review. `visualization/`, historical studies, source snapshots and credentials
remain protected. Other BFCL domains require a separate later coverage audit.
