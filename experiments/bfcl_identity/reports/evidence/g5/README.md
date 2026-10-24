# G5 证据附件

[G5 可读报告](../../g5-graph-replacement.md) · [本次发布清单及 SHA-256](../../g5-publication-manifest.json)

这里保存报告直接引用的原始判定、汇总、逐轨迹分析和审查文件的**内容不变副本**，以及从两份验证分析提取的 primary-runs.csv。原始轨迹、API 记录和冻结 source_code 保留在 ins04 的 experiments/bfcl_identity/v7_graph_iterations_20261023，未移动或改写。

- [开发判定](round-05-development-decision.json)、[开发 token](round-05-development-token-summary.json)：每模型 4 题族 × 3 次。
- [最终验证判定](campaign02-final-scientific-decision.json)、[验证 token](campaign02-primary-token-summary.json)、[首跑 CSV](primary-runs.csv)：每模型各组 11／12 条，排除开发、C1 和补跑。
- [批次一逐轨迹分析](campaign02-batch01-analysis.json)、[批次二逐轨迹分析](campaign02-batch02-analysis.json)：共 46 条首跑，含官方结果、provider usage、配对上下文审计及原始文件 SHA-256。
- [筛选及排除](campaign02-qualification-summary.json)、[C1 关闭记录](campaign01-qualification-closure.json)、[预登记规则](registered-decision-rules.json)。
- [方法审计](g5-final-method-scope-review.json)、[G5 设计变更](round-05-mechanism-review.json)、[实现记录](g5-implementation-record.json)。
- [行为审查一](campaign02-batch01-continuations-behavior-review.json)、[行为审查二](campaign02-batch02-continuations-behavior-review.json)、[分歧补跑](campaign02-batch01-discordance-confirmation-behavior-review.json)。行为审查文件中的 adjudication_pending 是该中间步骤的原状态，后续裁定见 [批次一最终记录](campaign02-batch01-completion-decision.json)、[批次二最终记录](campaign02-batch02-completion-decision.json)，不改写中间记录。

JSON 中原有绝对路径是来源定位信息，不是 GitHub 可点击文件链接；本目录直接可读的副本由上面的相对链接提供。未将完整运行环境、密钥、完整 API 请求日志或所有大体积原始轨迹上传到报告目录。

旧记录的 achieved 仅指其 scope 明示的小样本运行级标准；本报告不据此宣称总体非劣效、压缩已完成或项目整体达标。
