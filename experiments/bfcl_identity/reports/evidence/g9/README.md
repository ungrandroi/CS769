# G9 报告证据附件

[新增验证报告](../../g9-expanded-validation-results.md) · [上一批验证](../../g9-independent-validation-results.md) · [发布清单](../../g9-publication-manifest.json)

本目录保存报告引用的评分汇总、协议、盲审标签和方法实例的内容不变副本；发布清单区分逐字副本与少量明确标注的派生统计。原始模型请求、全部轨迹、完整账本及冻结源码继续保存在 ins04 的 experiments/bfcl_identity/v9_graph_exploration_20261024，未移动或改写。

- [新增官方汇总](g9-expanded-unmasked-summary.json)、[新增行为解释 V2](g9-expanded-behavior-explanation-v2.json)、[独立复核](g9-expanded-independent-results-review.json)。
- [上一批官方汇总](g9-independent-unmasked-summary.json)、[上一批审查](g9-independent-report-grounding-review.json)。
- [新增盲审](g9-expanded-blind-labels.json)、[先冻结再揭盲记录](g9-expanded-blind-merge-freeze.json)。
- [当前累计预算统计](ext04-g9-continuation-k2-budget-totals.json)、[新增筛选与续跑成本](g9-expanded-pre-unmask-cost-summary.json)、[候选池投影](g9-expansion-feasibility-projection.json)。
- [G5 旧开发缺口](dev02-structural-repeat-independent-audit.json)：GPT base_43/k2 的 A 3/3、G5 0/3，不能被新领域结果抵消。

行为解释 V1 中把 get_ticket(1) 查询返回误称为创建输出；V2 明确勘误，原 V1 保留，盲审标签和官方分数不变。JSON 中绝对路径只是历史来源定位，不能当成 GitHub 链接。完整账本以可复算汇总及来源 SHA 发布；大型文件名盘点只发布原字段投影，未改原始筛选结果。费用沿用冻结参考价，非最终账单。
