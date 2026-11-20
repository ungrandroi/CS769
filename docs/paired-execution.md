# 工具调用与返回结果的配对视图

The optional `paired_graph` editor compiles adjacent matching tool-call and tool-result records into one X row. Original call/result IDs, call ID, assistant-message group, argument and output strings, error flags, turn boundaries, user/assistant text, and trailing graph relations are retained. Decoding restores the exact prior compact rendering.

This is a model-facing paired-node view backed by the original evidence graph, not a replacement of the archived graph with reconstructed prose. Node mappings are in the edit audit. No identity transcript is appended.

Non-adjacent calls/results, including parallel-call layouts that cannot be fused without reordering, remain in their original form. Unknown layouts retain their current representation. The paired renderer is selected only if measured token count is lower than the existing compact renderer.

`paired_state_chain` first applies the existing `state_chain.contract` without changing its candidate choice, dependency checks or state rules, then compiles its output using the same paired view. The lossless and lossy arms therefore share the new representation.

Example:
```text
e1 C ["call_1","g1","read","{\"id\":\"business123\"}"]
e2 R ["e1","{\"value\":980}",false]
```
becomes an X row with label `e1/e2`, preserving both IDs and all six payload fields. Business IDs inside arguments and outputs are unchanged.

Report paired-node coverage separately from actual lossy state-edit coverage. Neither applicability nor exact serialization roundtrip certifies unchanged agent task success.

Tests: `tests/test_paired_graph.py`. Frozen pilot records are stored outside the repository under the paired-execution-pilot8-20261116 evidence directory. No official evaluator code is modified.
