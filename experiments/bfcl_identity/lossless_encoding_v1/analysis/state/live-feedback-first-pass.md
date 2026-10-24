# First State tables live feedback: one development loss

Scope: read-only analysis of `multi_turn_long_context_3`, seed `3301`, while the first development candidate is still running. This is a single case, not a completed-batch success-rate conclusion. No frozen codec, protocol, candidate registry or queue was changed.

## Finding

The new `state-tables-v1 / none` fails where the selected old `readable / minimal` passes. However, the old `readable / none` also fails with the same basic mistake: it repeats the completed copy operation while already inside the destination folder. This is not evidence of deleted information, and the comparison against old minimal changes both encoding and explanation.

| Condition | Official result | First post-conversion input tokens | Post-conversion model requests |
| --- | --- | ---: | ---: |
| Identity | Pass | 4772 | 1 |
| Old readable, none | Fail | 8450 | 14 |
| Old readable, minimal | Pass | 8483 | 7 |
| New tables, none | Fail | 8305 | 11 |

Identity's manifest reports 10 total live requests; subtracting the shared trigger index 9 gives one request after the fork. The graph manifests count only their new live continuation. New tables saves 145 first-input tokens against old none, or 178 against old minimal; the latter comparison also removes the 32-token external instruction and its separator effect.

## Shared checkpoint

All four manifests identify the same checkpoint SHA-256:

`e9e6fde7b07ca029597ce3d719140b345290bc1128b958c7480f33e9c51e1f05`

The fork is at absolute request index 9, in the second user turn. Before that point:

1. The user asked to copy the test image and text document into `backup_tests` in their containing directory.
2. The model successfully copied both files from `photography` into its existing `backup_tests` folder.
3. It successfully changed directory into `backup_tests`.
4. `ls()` returned the copied files alongside existing long-context distractor files.

Thus the requested filesystem operation was already accomplished when the threshold fired; continued mutation can undo the desired final state. This case is legitimately retained by the threshold-only protocol. It should not be dropped or filtered post hoc because continuation consists mainly of confirming completion.

## Subsequent actions

- **Identity:** immediately gives a final response confirming the completed copies. No further tools.
- **Old minimal:** performs `ls()` once, then `ls(a=true)` five times, then confirms completion. It passes, but its verification loop is inefficient.
- **Old none:** calls `find(name='test')`, then repeats both `cp(..., destination='backup_tests')` calls from inside the destination directory. The first creates a new file named `backup_tests`; the second fails because that name is now a file. Later navigation and verification do not remove the unwanted file. The run reaches the step limit and fails.
- **New tables none:** calls `find(path='.', name='test')`, reads both files with `cat`, then repeats the same two `cp` calls from inside the destination directory. It encounters the same file-versus-directory error, reads the newly created `backup_tests` file, removes it, creates a directory of that name, copies into it, enters it, lists it, and confirms completion. This leaves an extra nested `backup_tests/backup_tests` folder and fails the official filesystem-state check.

The new official error is `multi_turn:instance_state_mismatch`, with a `root` filesystem difference. It is not a malformed tool-call or codec-decoding failure.

## Information-preservation check

I decoded the actual live `memory-metadata.json` field `encoded` using the candidate decoder and compared the resulting payload to the old minimal run's original `graph`. Type-preserving, list-order-preserving direct equality passes (dictionary key order is immaterial).

The delivered graph retains:

- `current_state = s10`;
- `s9`'s successful current-directory update to location `l3`, named `backup_tests`;
- `s10 inherits s9`;
- location chain `l3 -> l2 (photography) -> l1 (projects) -> l0`;
- separate successful copy edges `e6` and `e7`;
- the successful directory-change edge `e8`;
- source messages `m24/m25` containing the successful `cd`, and `m26/m27` containing the final `ls` and both copied names.

No cwd, copy result, source message or event was lost by this codec. Whether the model attends to those facts correctly is a separate empirical question.

## Explanation and next comparisons

The old minimal explanation is 32 tokens and begins “Past working memory, not a plan.” It also marks assistant statements as unverified and asks the model to continue the current request. The new none candidate has only its in-band table-decoding rule, which explains representation but not the past-history-versus-new-plan distinction.

The trajectories are consistent with a history/status interpretation problem, but do not prove that this particular sentence caused the successful outcome. Stochastic generation and representation changes remain possible causes. The existing old-none failure is an important counterexample to attributing the loss uniquely to table packing.

The frozen queue already covers the necessary first contrasts:

- `tables-none` versus `tables-minimal` isolates the external explanation setting within this candidate.
- `shared-none` versus `shared-minimal` checks whether the same effect appears with references.
- `tables-minimal` versus old readable-minimal controls the explanation when comparing encodings.

A successful `shared-minimal` result alone would not establish whether sharing or the explanation helped, since both differ from tables-none.

If failures remain after those comparisons, a next **separately registered development round** could test lossless layout only: put existing `current_state` and state/edge sections before source-message tables, preserving every value, explicit predecessor link and source-message order. It could also make existing historical-status field names more prominent through reversible layout rather than adding inferred completion summaries. Do not add task-specific hints, declare success from ground truth, prune repeated calls, or mutate the current frozen run. The source-JSON prototype addresses text/token overhead; it is not specifically supported as a fix for this temporal interpretation problem.

## Evidence paths

- New run: `experiments/bfcl_identity/lossless_encoding_v1/development/multi_turn_long_context_3/seed3301/state-state-tables-v1-none/`
- Old paired runs: `experiments/bfcl_identity/work1000_research/tasks/multi_turn_long_context_3/seed3301/{identity,state-none,state-minimal}/`
- Inspected artifacts: `manifest.json`, `full.json`, `native.jsonl`, `official-score.json`, and `memory-metadata.json`.
