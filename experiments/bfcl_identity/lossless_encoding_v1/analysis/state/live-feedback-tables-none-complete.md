# Complete first State tables development candidate: interpretation and second loss

Scope: all 13 triggered development checkpoints for `state-tables-v1 / none`, compared with the previously selected State readable/minimal baseline. This analysis uses development records only. It does not change frozen code, registry, protocol or running queue.

## Batch observation

From `dev-tables-none.json`:

- Candidate: 8/13 passed; selected old baseline: 10/13 passed.
- Two paired losses, no paired gains: long-context task 3 seed 3301 and long-context task 37 seed 2207.
- Mean first input: 7109.69 vs 7588 tokens, about 6.3% lower.
- Mean of per-trajectory post-fork input means: 8383.05 vs 8466.32, about 1.0% lower.
- Five of the 13 trajectories have larger post-fork mean input despite lower first input: base 37 seeds 2207/3301, long-context 37 seed 2207, and long-context 9 seeds 2207/3301.

These are small development-set observations, not evidence of general performance regression or non-inferiority. The first-input saving is real; later generation and actions can consume that saving. The old comparison also includes a 32-token minimal instruction that the candidate removes, so tables-minimal is the necessary next control.

The first loss is documented in `live-feedback-first-pass.md`: history replay led to unwanted nested copies, and old readable/none already failed on that checkpoint.

## Second loss: long-context task 37, seed 2207

All branches share checkpoint hash:

`2dedb74130b265a36303d42c870843b0ba51fd7b13d8e3462cc98a278a9ebe32`

The checkpoint is at request index 3 in the first user turn, after 31 `wc` tool calls in one response had returned. The first user asked to count lines in every file in `/temp`; the recorded `dev_summary.txt` result was `{"count":1,"type":"lines"}`. The other 30 files had zero lines.

The later requests were:

1. Search `dev_summary.txt` for mentions of `server error`.
2. “Make a new file whose name is the number of line but in txt format and append the second sentence containing 'server error' to it.”

The final request refers to the earlier file line count, so the passing trajectories use `1.txt`. The candidate instead uses `7.txt`, interpreting the number as occurrences of `server error` from the intervening response. The sentence written is the same correct sentence; the filename is wrong. The official result is `multi_turn:instance_state_mismatch`, with a filesystem-root difference.

### Observable trajectory differences

| Condition | Immediately after compaction | Final file | Official result |
| --- | --- | --- | --- |
| Identity | Returns the line-count table | `1.txt` | Pass |
| Old readable/none | Returns the line-count table | `1.txt` | Pass |
| Old readable/minimal | Returns the line-count table | `1.txt` | Pass |
| New tables/none | Repeats `cd('temp')`, `pwd`, `ls`, and all 31 `wc` calls, then returns the table | `7.txt` | Fail |

Unlike the first loss, old readable/none also passes here. Removing the external minimal instruction alone therefore does not explain this case. Nonetheless, one stochastic paired outcome cannot isolate an individual syntax change as the cause.

The new trajectory explicitly outputs the correct line-count table again after repeating the tools. Therefore the later error is not simply failure to recover the number 1: that number is both in exact retained tool history and in newly generated plain-language output. The observed mistake is binding the later request to the wrong earlier quantity. The 34 extra tool calls after compaction also enlarge the suffix history, but their causal effect on that binding is unproven.

### Token accounting for this case

| Condition | First post-fork input | Post-fork request count | Mean post-fork input |
| --- | ---: | ---: | ---: |
| Old readable/minimal | 10836 | 8 | 12459.625 |
| New tables/none | 9394 | 9 | 12592.333 |

The candidate starts 1442 tokens lower, yet ends with a slightly higher per-request mean. Its additional navigation and 31-tool request introduce substantial source history. This is why static codec savings must not be substituted for end-to-end per-request measurements.

## Direct losslessness and model interpretation burden

I decoded the actual candidate `memory-metadata.json` field `encoded` and compared it against the old minimal run's original delivered `graph` using type-preserving, list-order-preserving equality. It matches exactly. All 34 graph edges, 35 state nodes and 72 source messages remain. In particular:

- `m10` contains `wc(file_name='dev_summary.txt', mode='l')`;
- `m41` contains its line count 1;
- these source-message rows are not table-packed by this candidate;
- the candidate's only table-packed areas in this case are the 31-object `objects_updated` block and the `tool_call_edges` dictionary.

Encoding preserves data, but model use requires extra interpretation: row columns must be aligned, shared defaults applied, and call edges linked back to source rows. The table rule is 33 model tokens inside the envelope; “none” means no separate external explanation, not absence of in-band explanatory text. The old minimal instruction is a different 32-token instruction about past working memory and continuation, not a table decoder.

Neither exact reconstruction by Python nor fewer tokens guarantees equivalent attention, temporal interpretation or follow-up action selection by the model. The first candidate currently does not meet the desired joint capability-and-input goal on this development sample.

## Recommendation within the frozen queue

1. Finish tables-minimal before drawing an encoding-versus-instruction conclusion.
2. Inspect whether it prevents the initial replay on both loss cases, and whether the later `1.txt` binding succeeds. A final pass alone does not show which intermediate behavior improved.
3. Use shared-none/minimal to test a distinct representation, without assuming extra references will help comprehension or reduce actual input tokens.
4. Compare matched explanation settings to old readable/none and readable/minimal. Keep the selected old minimal baseline as the primary improvement target.
5. Keep all failures and repeated actions; do not add task-specific instructions, discard checkpoints, infer task completion from ground truth, or rerun unfavorable seeds selectively.

## Possible next registered development round

If the frozen candidates still trade capability for token savings, the next representation experiment should target readability and temporal organization rather than more aggressive dictionary compression:

- **History-first semantics with no new facts:** reorder existing top-level fields to make current-state identity, state nodes and executed tool edges visible before the source table. Preserve all values, explicit references, and original source-message order. Register separately; do not alter the current queue.
- **Keep executable-history edges readable:** compare tables only for repeated object state fields while retaining tool-call edges as named dictionaries. This retains much of the large repeated-object saving in this case without adding a decoding layer to every historical call. It may cost more tokens than full tables; only a live paired test can decide whether the tradeoff is worthwhile.
- **Separate explanation ablation:** compare zero external instruction with the existing short history/status instruction, rather than treating the codec rule as equivalent. Any replacement wording must be generic, fixed before evaluation, and counted in every request that carries it.

The offline JSON-column parsing prototype is an additional storage idea, but it is not specifically supported as a remedy for these temporal and quantity-binding failures. No next-round variant is registered by this report.

## Evidence

- Aggregate: `analysis/state/dev-tables-none.json`.
- New second-loss run: `development/multi_turn_long_context_37/seed2207/state-state-tables-v1-none/`.
- Old controls: `../work1000_research/tasks/multi_turn_long_context_37/seed2207/{identity,state-none,state-minimal}/`.
- Read artifacts: `manifest.json`, `native.jsonl`, `full.json`, `official-score.json`, `memory-metadata.json`.
