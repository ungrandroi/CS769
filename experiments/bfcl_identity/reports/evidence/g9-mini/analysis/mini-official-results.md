# GPT-5-mini：identity 与冻结 G9 试跑

共登记 24 个候选题，16 个前缀合格并完成两组续跑，8 个在接入前排除。每题每组一次，完整保留可见证据，不压缩、不改官方 eval；G9 替换旧历史，不额外附带 identity。[机器可核验结果与来源哈希](mini-official-results.json)

| 模型 | 合格配对 | identity | G9 | G9 新增掉点 / 恢复 |
|---|---:|---:|---:|---:|
| gpt-5-mini | 16 | 13/16 | 12/16 | 1 / 0 |

这些是单次、小样本的官方结果，不能据此宣布整体通过率保持或 G9 更优；两组同分也不代表行为相同，具体行为尚待独立审查。[机器可核验结果与来源哈希](mini-official-results.json)

| 领域 | 合格 / 登记 | identity | G9 | 掉点 / 恢复 |
|---|---:|---:|---:|---:|
| trading | 8/8 | 6/8 | 6/8 | 0 / 0 |
| travel | 5/8 | 4/5 | 4/5 | 0 / 0 |
| vehicle | 3/8 | 3/3 | 2/3 | 1 / 0 |

有实际新增记录关系的合格条件为 7 个，零关系为 9 个，均保留在分母中。24 题已在之前的 GPT-4.1/Claude 实验中使用，本轮是同一题池的新模型检查。[机器可核验结果与来源哈希](mini-official-results.json)

| 每条合格续跑均值 | identity | G9 |
|---|---:|---:|
| 首请求输入（含工具） | 8,015.7 | 8,554.7 |
| 整条续跑输入＋输出 | 37,549.4 | 29,952.9 |
| 其中推理输出 | 572.0 | 676.0 |

推理 token 已包含在输出 token 中，没有重复相加；共享前缀生成单列费用。费用按冻结参考价、不扣缓存折扣，不是最终账单。[机器可核验结果与来源哈希](mini-official-results.json)

| 费用项 | 已知费用 | 未知请求预留 |
|---|---:|---:|
| 全部 24 个前缀 | $0.318700 | $0.000000 |
| identity 续跑 | $0.178705 | $0.055516 |
| G9 续跑 | $0.152726 | $0.051513 |
| 其他请求 | $0.000000 | $0.000000 |

累计已知 $0.650131，未知预留 $0.107028，$3 上限内剩余 $2.242841。被排除前缀费用 $0.082255 已包含在前缀费用中，不能重复加。[机器可核验结果与来源哈希](mini-official-results.json)

## 逐题对比

| 题目 / 接入轮数 | identity | G9 | 配对结果 | 证据 |
|---|---:|---:|---|---|
| multi_turn_base_71 / k3 | 1 | 1 | 两组通过 | [identity](../mini04-continuation-k3/runs/gpt-5-mini/multi_turn_base_71/boundary-3/1/identity/official-score.json) / [G9](../mini04-continuation-k3/runs/gpt-5-mini/multi_turn_base_71/boundary-3/1/graph-record-view-full/official-score.json) |
| multi_turn_base_59 / k3 | 1 | 0 | 新增掉点 | [identity](../mini04-continuation-k3/runs/gpt-5-mini/multi_turn_base_59/boundary-3/1/identity/official-score.json) / [G9](../mini04-continuation-k3/runs/gpt-5-mini/multi_turn_base_59/boundary-3/1/graph-record-view-full/official-score.json) |
| multi_turn_long_context_138 / k3 | 0 | 0 | 两组失败 | [identity](../mini04-continuation-k3/runs/gpt-5-mini/multi_turn_long_context_138/boundary-3/1/identity/official-score.json) / [G9](../mini04-continuation-k3/runs/gpt-5-mini/multi_turn_long_context_138/boundary-3/1/graph-record-view-full/official-score.json) |
| multi_turn_base_123 / k3 | 1 | 1 | 两组通过 | [identity](../mini04-continuation-k3/runs/gpt-5-mini/multi_turn_base_123/boundary-3/1/identity/official-score.json) / [G9](../mini04-continuation-k3/runs/gpt-5-mini/multi_turn_base_123/boundary-3/1/graph-record-view-full/official-score.json) |
| multi_turn_base_121 / k3 | 0 | 0 | 两组失败 | [identity](../mini04-continuation-k3/runs/gpt-5-mini/multi_turn_base_121/boundary-3/1/identity/official-score.json) / [G9](../mini04-continuation-k3/runs/gpt-5-mini/multi_turn_base_121/boundary-3/1/graph-record-view-full/official-score.json) |
| multi_turn_long_context_111 / k3 | 1 | 1 | 两组通过 | [identity](../mini04-continuation-k3/runs/gpt-5-mini/multi_turn_long_context_111/boundary-3/1/identity/official-score.json) / [G9](../mini04-continuation-k3/runs/gpt-5-mini/multi_turn_long_context_111/boundary-3/1/graph-record-view-full/official-score.json) |
| multi_turn_long_context_157 / k2 | 1 | 1 | 两组通过 | [identity](../mini03-continuation-k2/runs/gpt-5-mini/multi_turn_long_context_157/boundary-2/1/identity/official-score.json) / [G9](../mini03-continuation-k2/runs/gpt-5-mini/multi_turn_long_context_157/boundary-2/1/graph-record-view-full/official-score.json) |
| multi_turn_long_context_167 / k3 | 1 | 1 | 两组通过 | [identity](../mini04-continuation-k3/runs/gpt-5-mini/multi_turn_long_context_167/boundary-3/1/identity/official-score.json) / [G9](../mini04-continuation-k3/runs/gpt-5-mini/multi_turn_long_context_167/boundary-3/1/graph-record-view-full/official-score.json) |
| multi_turn_long_context_162 / k3 | 0 | 0 | 两组失败 | [identity](../mini04-continuation-k3/runs/gpt-5-mini/multi_turn_long_context_162/boundary-3/1/identity/official-score.json) / [G9](../mini04-continuation-k3/runs/gpt-5-mini/multi_turn_long_context_162/boundary-3/1/graph-record-view-full/official-score.json) |
| multi_turn_base_165 / k3 | 1 | 1 | 两组通过 | [identity](../mini04-continuation-k3/runs/gpt-5-mini/multi_turn_base_165/boundary-3/1/identity/official-score.json) / [G9](../mini04-continuation-k3/runs/gpt-5-mini/multi_turn_base_165/boundary-3/1/graph-record-view-full/official-score.json) |
| multi_turn_long_context_60 / k3 | 1 | 1 | 两组通过 | [identity](../mini04-continuation-k3/runs/gpt-5-mini/multi_turn_long_context_60/boundary-3/1/identity/official-score.json) / [G9](../mini04-continuation-k3/runs/gpt-5-mini/multi_turn_long_context_60/boundary-3/1/graph-record-view-full/official-score.json) |
| multi_turn_base_135 / k3 | 1 | 1 | 两组通过 | [identity](../mini04-continuation-k3/runs/gpt-5-mini/multi_turn_base_135/boundary-3/1/identity/official-score.json) / [G9](../mini04-continuation-k3/runs/gpt-5-mini/multi_turn_base_135/boundary-3/1/graph-record-view-full/official-score.json) |
| multi_turn_long_context_107 / k3 | 1 | 1 | 两组通过 | [identity](../mini04-continuation-k3/runs/gpt-5-mini/multi_turn_long_context_107/boundary-3/1/identity/official-score.json) / [G9](../mini04-continuation-k3/runs/gpt-5-mini/multi_turn_long_context_107/boundary-3/1/graph-record-view-full/official-score.json) |
| multi_turn_base_124 / k2 | 1 | 1 | 两组通过 | [identity](../mini03-continuation-k2/runs/gpt-5-mini/multi_turn_base_124/boundary-2/1/identity/official-score.json) / [G9](../mini03-continuation-k2/runs/gpt-5-mini/multi_turn_base_124/boundary-2/1/graph-record-view-full/official-score.json) |
| multi_turn_long_context_112 / k3 | 1 | 1 | 两组通过 | [identity](../mini04-continuation-k3/runs/gpt-5-mini/multi_turn_long_context_112/boundary-3/1/identity/official-score.json) / [G9](../mini04-continuation-k3/runs/gpt-5-mini/multi_turn_long_context_112/boundary-3/1/graph-record-view-full/official-score.json) |
| multi_turn_long_context_190 / k3 | 1 | 1 | 两组通过 | [identity](../mini04-continuation-k3/runs/gpt-5-mini/multi_turn_long_context_190/boundary-3/1/identity/official-score.json) / [G9](../mini04-continuation-k3/runs/gpt-5-mini/multi_turn_long_context_190/boundary-3/1/graph-record-view-full/official-score.json) |

## 接入前排除

- `multi_turn_base_73/k2`：official_prefix_failed。[原始资格评分](../mini01-prefix-k2/runs/gpt-5-mini/multi_turn_base_73/boundary-2/1/identity/prefix-score.json)
- `multi_turn_long_context_79/k2`：official_prefix_failed。[原始资格评分](../mini01-prefix-k2/runs/gpt-5-mini/multi_turn_long_context_79/boundary-2/1/identity/prefix-score.json)
- `multi_turn_base_81/k3`：official_prefix_failed。[原始资格评分](../mini02-prefix-k3/runs/gpt-5-mini/multi_turn_base_81/boundary-3/1/identity/prefix-score.json)
- `multi_turn_long_context_170/k3`：official_prefix_failed。[原始资格评分](../mini02-prefix-k3/runs/gpt-5-mini/multi_turn_long_context_170/boundary-3/1/identity/prefix-score.json)
- `multi_turn_long_context_196/k3`：official_prefix_failed。[原始资格评分](../mini02-prefix-k3/runs/gpt-5-mini/multi_turn_long_context_196/boundary-3/1/identity/prefix-score.json)
- `multi_turn_long_context_188/k3`：official_prefix_failed。[原始资格评分](../mini02-prefix-k3/runs/gpt-5-mini/multi_turn_long_context_188/boundary-3/1/identity/prefix-score.json)
- `multi_turn_base_95/k3`：official_prefix_failed。[原始资格评分](../mini02-prefix-k3/runs/gpt-5-mini/multi_turn_base_95/boundary-3/1/identity/prefix-score.json)
- `multi_turn_long_context_80/k3`：official_prefix_failed。[原始资格评分](../mini02-prefix-k3/runs/gpt-5-mini/multi_turn_long_context_80/boundary-3/1/identity/prefix-score.json)
