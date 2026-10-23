# V2-readable：完整可见证据的可读表示实验

**归档说明：**这是该阶段完成时的报告，文中的“下一步／尚未启动”按当时状态理解；跨阶段结论以[总报告](experiment-summary.md)及[V5 最终结果](v5-b-validation-results.md)为准。[报告目录](README.md) · [GitHub 阅读版](v2-readable.md)

R 从既有事件图生成“已知状态索引＋按时间排列的完整可见历史证据”，后台保留审计信息，向模型仍提供一条 assistant 记忆消息；没有风险驱动的压缩。[实验记录](evidence/v2-findings.json) · [实现证据](experiment-evidence.md#M4)

正式续跑只运行 GPT-4.1 和 GPT-5-mini：分别为 4 个、5 个条件，每条件每组使用 seed 42/43/44，共 81 条轨迹；三组为 A、E、R。[逐轨迹结果](evidence/v2-results.json) · [逐条件通过次数](evidence/v2-success-by-case.csv)

## 结果

| 模型 | 组别 | 官方通过数／率 | 平均续跑输入 token | 平均续跑输出 token |
| --- | --- | --- | --- | --- |
| gpt-4.1 | A · identity | 12/12 (100.0%) | 11,250 | 146 |
| gpt-4.1 | E · 事件图 compact | 6/12 (50.0%) | 16,725 | 144 |
| gpt-4.1 | R · readable | 9/12 (75.0%) | 9,642 | 144 |
| gpt-5-mini | A · identity | 12/15 (80.0%) | 16,244 | 594 |
| gpt-5-mini | E · 事件图 compact | 11/15 (73.3%) | 32,076 | 951 |
| gpt-5-mini | R · readable | 10/15 (66.7%) | 16,576 | 607 |

上表从 v2-results.json 的 aggregates 读取；token 为共享首轮之后每条续跑的累计请求 usage 均值，包含成功和失败轨迹，输入包含工具定义与反复送入的历史。[精确数据](evidence/v2-results.json) · [统一口径](experiment-evidence.md#T)

## 主要发现与解释范围

R 相比 E 明显缩短了图文本，但两个模型的 R 正式通过数仍低于 A，未达到保持原始历史成功率的目标。9 个首轮边界的正文合计 A/E/R 为 1,994/26,794/3,077 token；R 相比 E 减少 88.5%，仍比 A 多 54.3%。[正式结果](evidence/v2-results.json) · [离线正文拆账](evidence/records/v2-offline-body-accounting.md)

9 个既有 history1000 检查点的正文合计 A/E/R 为 12,033/92,082/15,407 token；这是离线计数，没有新跑 Qwen 或 history1000 续跑。[检查点与计数口径](evidence/records/v2-offline-body-accounting.md)

- **gpt-4.1 · multi_turn_base_3**：原文在相同cp错误后cd重试成功，readable转向询问确认；三次正式readable均未通过。 [行为审查记录](evidence/v2-findings.json)
- **gpt-5-mini · multi_turn_base_16 · seed 42**：一行字符串包含Line N标签；readable无wc错答3行，官方empty_turn。 [行为审查记录](evidence/v2-findings.json)
- **gpt-5-mini · multi_turn_base_16 · seed 43**：readable用echo插入换行后wc=3，错误改写文件；官方instance_state_mismatch。 [行为审查记录](evidence/v2-findings.json)
- **gpt-5-mini · multi_turn_base_16 · seed 44**：readable直接wc=1，正确通过。 [行为审查记录](evidence/v2-findings.json)
- **gpt-5-mini · multi_turn_long_context_39**：9条回答都正确并继续下一轮cat；6条因本轮没有重新ls被官方判empty_turn。三组各1/3，保留官方分数，不将其归类为真实停止或答错。 [行为审查记录](evidence/v2-findings.json)

4.1恢复1/2个本轮复现掉点条件，mini恢复1/1。形式上的半数恢复门槛通过，但不等于原始历史准确率达标。 [解释与限制](evidence/v2-findings.json)

恢复条件分别属于same_family与development；other_regression没有可评估的复现退化分母，mini的base16新增失败。 [解释与限制](evidence/v2-findings.json)

共同成功token分析条件性筛选了成功交集，不能替代全部成功率；三方共同成功交集主要由控制题组成。 [解释与限制](evidence/v2-findings.json)

三次seed是固定条件的重复，不是独立题目；本结果不是完整BFCL总体性能估计。 [解释与限制](evidence/v2-findings.json)

126条探针记录包含115个唯一实际请求，11条native与identity字节相同而复用。人工修正du({})默认human_readable=false的12条自动分类；原始自动标签与人工标签均保留，正式BFCL评分未变。 [探针逐条审查](evidence/v2-probe-review.csv)

正式续跑的参考费用约 $0.4204（GPT-4.1：$0.31654；GPT-5-mini：$0.1038913）；这是标准单价估算，不是 Azure 账单，也不是所有探针及前缀生成的总费用。419 个正式返回未记录 API 错误、重试或长度截断。[费用口径](evidence/v2-results.json) · [运行计数](evidence/v2-findings.json) · [完整性审计](evidence/v2-verification.json)

本轮之后提出检验原生消息重建与独立索引接入；后续实施与结果见 [V3 报告](v3-findings.md)，不能将本轮角色格式推定为唯一失败原因。[原始结论](evidence/v2-findings.json)
