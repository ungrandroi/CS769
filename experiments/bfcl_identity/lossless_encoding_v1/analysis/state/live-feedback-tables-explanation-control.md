# State tables: completed none/minimal development comparison

These are 13 triggered development checkpoints, not fresh held-out runs. The original selected State baseline is readable/minimal. The frozen shared-none/minimal queue remains untouched.

## Paired outcomes and token observations

| Configuration | Passes | Mean first input | Mean of trajectory post-fork input means |
| --- | ---: | ---: | ---: |
| Old readable/minimal | 10/13 | 7588 | 8466.32 |
| Tables/none | 8/13 | 7109.69 | 8383.05 |
| Tables/minimal | 10/13 | 7142.69 | 7808.81 |

Tables/minimal saves approximately 5.9% on first input and 7.8% on the post-fork mean relative to the selected old baseline. All real request inputs include fixed tools/system overhead and any retained explanation. These results do **not** show item-by-item capability preservation:

- 8 checkpoints pass in both tables/minimal and old baseline.
- 2 gains: `multi_turn_base_9 / 3301`, `multi_turn_long_context_9 / 1103`.
- 2 losses: `multi_turn_long_context_37 / 2207`, `multi_turn_long_context_37 / 3301`.
- 1 shared failure: `multi_turn_long_context_9 / 3301`.

Compared with tables/none, adding minimal has 3 gains (the two above plus long-context task 3 seed 3301) and 1 loss (long-context task 37 seed 3301). A net gain does not establish a universal benefit of the instruction. The three seeds for one task are repeated trajectories, not three independent task families.

## Remaining long-context task 37 failures

The user first asks for line counts, then asks to find mentions of `server error`, then asks to name a new text file using the number of lines. Correct line count for `dev_summary.txt` is 1.

| Seed | Old readable/minimal | Tables/none | Tables/minimal |
| --- | --- | --- | --- |
| 1103 | Pass, `1.txt` | Pass | Pass, `1.txt` |
| 2207 | Pass, `1.txt` | Fail, `7.txt` | Fail, `9.txt` |
| 3301 | Pass, `1.txt` | Pass | Fail, `8.txt` |

For tables/minimal seeds 2207 and 3301:

1. Immediately after compaction, the model gives a correct plain-language line-count table including `dev_summary.txt | 1`.
2. It executes `grep` and generates a summary claiming respectively 9 and 8 mentions of `server error`.
3. It uses those mention counts as the filename (`9.txt` / `8.txt`), explicitly explaining that choice in its final answer.
4. The written sentence is the expected sentence. Official failure is filesystem `root` state mismatch because the filename differs.

This is a cross-turn quantity-binding error: the model uses a salient quantity from the intervening search instead of the requested earlier line count. The count 1 remains visible in both preserved tool evidence and newly generated plain-language output. Wrong mention counting itself is secondary: even a correct mention count of 7 is still the wrong filename criterion.

Unlike tables/none seed 2207, neither minimal failure replays the full navigation and 31 `wc` calls. The minimal instruction therefore coincides with removal of that particular replay, but does not eliminate the later quantity-binding failure. This is direct evidence that the two failure behaviors must be analyzed separately.

The passing tables/minimal seed 1103 does make extra verification calls (`wc` for one image, `ls`, `wc` for the summary) and uses 11 continuation requests versus 6 for its old baseline. Passing alone does not imply equally efficient behavior.

## Losslessness and matched-instruction checks

For both minimal failures I verified against the corresponding old baseline:

- checkpoint SHA-256 matches;
- actual delivered `encoded` decodes exactly to the old complete graph payload (primitive types and list order preserved);
- external minimal instruction text matches exactly.

All original source messages, the `wc` count 1, event distinctions, state nodes and provenance references remain. This matched-instruction comparison removes the explanation-setting difference present in the original tables-none analysis. It still does not causally identify a particular table field: small stochastic experiments with changed prompt layout cannot do that.

The model must use both source-message columns and the newer object/edge tables. Software-decoding equality establishes recoverability, not equivalent model comprehension or attention. The fact that the final failure happens after a correct plain-language re-expression of the relevant number is especially important: this cannot be described as the codec having removed the line count.

## What to do next

1. Complete the existing shared-none/minimal comparisons before choosing a State candidate.
2. Preserve the paired gain/loss lists alongside aggregate rates. Tables/minimal currently matches total passes while swapping which cases succeed.
3. Do not promote tables/minimal as proved non-inferior solely from 10/13 versus 10/13. Use the planned frozen-candidate fresh-seed validation, and report uncertainty and task-family dependence.
4. Interpret lower follow-up mean tokens alongside actions and errors: a shorter or wrong continuation can reduce average input without being desirable.

If another registered development round is needed, the most informative lossless layout controls remain:

- Keep executed tool edges as named dictionaries while table-packing repeated object fields.
- Reorder existing state and event sections before source-message tables without adding facts, summaries, completion claims or task-specific instructions.
- Keep the same minimal instruction while changing one layout factor, rather than simultaneously editing explanation and encoding.

An offline, **unregistered** diagnostic replaced the encoded `tool_call_edges` table with its original named dictionaries and checked exact restoration on all 13 development payloads. Native memory-body means were original 4437, full tables 3991.69, and named-edge tables 4166. For long-context task 37, named edges cost 446 more tokens than full tables while still saving 963 versus the original body. This quantifies a possible readability/token tradeoff; it is not a tested capability improvement and is not added to the current queue.

No frozen source, candidate manifest, run record or queue was edited. This report and development-only reads are the only changes in this task.

## Evidence

- `analysis/state/dev-tables-none.json`
- `analysis/state/dev-tables-minimal.json`
- `development/multi_turn_long_context_37/seed{1103,2207,3301}/state-state-tables-v1-minimal/{manifest.json,native.jsonl,memory-metadata.json,official-score.json}`
- Corresponding old `work1000_research/tasks/.../state-minimal/` records.
