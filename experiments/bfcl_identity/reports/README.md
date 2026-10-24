# BFCL 图记忆实验报告

最新图替代结果见 [G5 小规模验证](g5-graph-replacement.md)：图替代完整原生前缀，尚未压缩；开发与冻结验证分开报告。

此前 V2–V5 阶段先读 [实验总报告](experiment-summary.md)：方法定义、统一 token 口径、各阶段模型与样本数、官方通过率以及结论边界。每项结论链接到 [详细证据索引](experiment-evidence.md)；总表精确值见 [汇总数据](evidence/experiment-summary-data.json)。

| 阶段 | 可读报告 | 主要内容 |
| --- | --- | --- |
| 总览 | [实验总报告](experiment-summary.md) / [HTML](experiment-summary.html) | 从 main 的构图方式到 V5 的实验结果 |
| V2 | [Readable 实验](v2-readable.md) / [HTML](v2-readable.html) | A 原生历史、E compact 事件图、R 可读证据表示；两 GPT |
| V3 | [原生历史＋图索引](v3-findings.md) / [HTML](v3-findings.html) | A 与 B：B 完整保留原生历史，额外加入一次 assistant 图索引；三模型 |
| V3 token | [Token 拆账](v3-token-statistics.md) / [HTML](v3-token-statistics.html) | 全部续跑、共同成功子集、首次请求和首轮成本的不同口径 |
| V4 回归 | [旧集回归](v4-regression-review.md) / [HTML](v4-regression-review.html) | A 与 D：D 将索引放入第二轮用户消息的 application_memory 块；两 GPT |
| V4 诊断 | [180 条放置诊断](v4-placement-diagnostic.md) / [HTML](v4-placement-diagnostic.html) | GPT-5-mini，A/B/D 随机交错；随后保留 B 作为验证格式 |
| V5 | [冻结 B 的新题验证](v5-b-validation-results.md) / [HTML](v5-b-validation-results.html) | 两 GPT；筛选 144 个模型×条件，完成 348 条续跑；通过率、行为、token、费用 |
| G5 | [完整事件图替代历史](g5-graph-replacement.md) / [HTML](g5-graph-replacement.html) | GPT-4.1／Claude；开发各 4 题族 × 3 次，冻结验证分别 11／12 题族；完整证据、不压缩、官方 eval 不变 |
| 证据 | [逐句证据索引](experiment-evidence.md) / [HTML](experiment-evidence.html) | 方法代码节选、各阶段来源与计数解释 |

## 早期报告（原文件保留）

- [初始基线](baseline.txt)
- [Event Graph-Dedup 续跑](event_graph_dedup_eval.txt) 与 [离线去重](event_graph_dedup_offline.txt)
- [GPT-4.1 初始实验](gpt41_rerun.md)、[GPT-5-mini 初始实验](gpt5mini_rerun.md)、[三模型比较](model_comparison.md)

## 阅读与归档规则

Markdown 供 GitHub 直接阅读；HTML 保留原展示格式，下载仓库后可本地打开。旧阶段报告中的计划与状态是当时的记录；V2–V5 的结论见原总报告；后续 G5 图替代结论见 G5 专项报告。各阶段样本与干预不同，不将各轮通过率直接串成趋势。

总表统一使用平均**续跑输入 token**，不含共享首轮与输出；各轮详细报告还展示其他成本口径，以各表注释为准。[计数依据](experiment-evidence.md#T)

V5 的辅助行为计数已更正为 A **7**、B **11**：排除了三条推文草稿；官方分数、token、费用和置信区间未变。[更正记录](evidence/records/v5-auxiliary-correction.json)

`evidence/` 收录报告引用的结果、协议和审计附件，以及原结果文件的内容不变副本；不是完整的实验运行目录。原始轨迹与冻结 source_code 快照继续保留在原实验目录，本次不移动、不改写、不补交运行环境或实验实现。[附件说明](evidence/README.md) · [发布文件清单与 SHA-256](publication-manifest.json)

G5 附件单独列于 [G5 证据目录](evidence/g5/README.md)，本次新增及入口修改见 [G5 发布清单](g5-publication-manifest.json)。原 publication-manifest.json 保留为 V2–V5 发布时的历史清单。
