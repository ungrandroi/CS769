# G5：完整事件证据图替代原生历史的小规模验证

[报告目录](README.md) · [此前 V2–V5 总结](experiment-summary.md) · [HTML 阅读版](g5-graph-replacement.html) · [证据附件](evidence/g5/README.md)

截至 2026-10-24。**G5 已在这批小样本中满足预先约定的运行级保率条件；尚未证明总体非劣效、跨领域适用性或压缩效果。** 下表分开报告用于选格式的开发集和冻结后的 C2 验证集，不把两者混算。[最终判定及范围](evidence/g5/campaign02-final-scientific-decision.json)

## 结果总表

| 阶段 | 模型 | 不同题族 × 每题重复＝每组轨迹 | Identity 官方通过数／率 | G5 官方通过数／率 | 平均续跑输入 token：A → G5 | 平均续跑总 token：A → G5 |
| --- | --- | --- | --- | --- | --- | --- |
| 固定开发与确认 | GPT-4.1 | 4 × 3＝12 | 12/12（100%） | 12/12（100%） | 20,462 → 22,151 | 20,637 → 22,340 |
| 固定开发与确认 | Claude Sonnet 5.5 | 4 × 3＝12 | 12/12（100%） | 12/12（100%） | 33,301 → 39,703 | 33,679 → 40,158 |
| 冻结后 C2 验证 | GPT-4.1 | 11 × 1＝11 | 6/11（54.5%） | 7/11（63.6%） | 23,882 → 27,439 | 24,301 → 27,828 |
| 冻结后 C2 验证 | Claude Sonnet 5.5 | 12 × 1＝12 | 9/12（75.0%） | 9/12（75.0%） | 42,859 → 46,222 | 43,551 → 47,017 |

表中 token 四舍五入到整数；每个数字按相同题目、相同组别的完整续跑取平均。开发表依据 [开发判定](evidence/g5/round-05-development-decision.json) 和 [开发 token 精确值](evidence/g5/round-05-development-token-summary.json)；验证表依据 [验证判定](evidence/g5/campaign02-final-scientific-decision.json)、[验证 token 精确值](evidence/g5/campaign02-primary-token-summary.json) 和 [46 条首跑明细](evidence/g5/primary-runs.csv)。

续跑 token 是接入之后所有 API 请求的 provider usage 之和，包括反复发送的历史、工具定义以及 provider 报告的输出／推理 token；不包含共享首轮生成，不减去缓存命中输入。验证集中，G5 的平均总 token 相对 A 增加 **GPT-4.1 14.52%、Claude 7.96%**；平均输入分别增加 **14.89%、7.84%**。这些差异同时包含表示开销和后续调用行为差异，不能全归因于图标签。[口径及精确统计](evidence/g5/campaign02-primary-token-summary.json)

## G5 是什么，与 B、V2 有何区别

G5 将已经完成的历史前缀转换为类型明确的事件证据图，并把其序列化文本放在一条 assistant 消息中，替代原生前缀；当前用户请求保持原样。模型不会同时收到一份原生 identity 前缀作为备用上下文，归档的 source history 只供审计和环境回放使用。[实际出站与无旁路审计](evidence/g5/g5-final-method-scope-review.json)

图中保留 episode、user_request、assistant_statement、tool_call、tool_result 节点，以及 in_turn、precedes、result_of 关系；节点完整保存可见文本、工具名称和参数、返回值、来源角色与调用配对。字符串不做摘要或截断，非字符串保留其类型语义。[节点、字段与关系审计](evidence/g5/g5-final-method-scope-review.json)

| 表示 | 模型收到的历史形式 | 原生历史是否仍在模型输入中 |
| --- | --- | --- |
| V2-readable | 已知状态索引＋按顺序排列的完整历史证据 | 作为可读证据文本，而非原生多消息协议 |
| B | 完整重建的原生历史＋简短图索引 | **在** |
| G5 | 保留完整可见证据的事件图文本 | **原生前缀已被替换** |

V2/B 的定义见 [历史方法证据](experiment-evidence.md#M4) 与 [B 的定义](experiment-evidence.md#M5)；G5 的区别见 [实现审计](evidence/g5/g5-final-method-scope-review.json)。G5 因此验证的是图表示替代历史，而 B 验证的是在原生历史旁加入索引。

G5 沿用此前的 assistant 载体、时间顺序和原始证据格式，统一省略模型投喂视图中的派生实体、事实及其关联边；完整父图仍留档。因此，“完整保留”指原始可见证据，不表示整个丰富语义图的所有派生层都被投喂，也不宣称当前图是最优或最小表示。[G5 设计变化](evidence/g5/round-05-mechanism-review.json) · [方法边界](evidence/g5/g5-final-method-scope-review.json)

## 实验范围与判定

开发条件固定为 base_43、long_context_31、base_3、base_12，两个模型各自对 A/G5 完成每题 3 次；这是 4 个题族，不是 12 个独立题族。冻结后 C2 分两批验证，GPT-4.1 为 6＋5 个、Claude 为 6＋6 个题族，共 46 条 A/G5 首跑轨迹。[开发规则](evidence/g5/registered-decision-rules.json) · [开发判定](evidence/g5/round-05-development-decision.json) · [验证判定](evidence/g5/campaign02-final-scientific-decision.json)

本轮仅覆盖 BFCL Multi-Turn Base／Long-Context 中含文件系统工具的题目，**在第一轮用户任务完成、第二轮请求之前替换一次历史**；后续新交互仍按原生消息累积。两组使用相同前缀、环境回放、工具和执行设置，官方 eval／工具实现未修改。Claude 两组均不回传已完成前缀的 thinking／redacted_thinking，这些内容完整归档，续跑中新产生的内容块保持原样。[边界、工具及 thinking 审计](evidence/g5/g5-final-method-scope-review.json)

此前登记的 C1 尝试因前缀资格不足结束：GPT-4.1 合格 4 个、Claude 合格 6 个，未执行 A/G 验证续跑，也未混入 C2 分数。C2 的全部登记候选及候补中，GPT-4.1 筛选 15 个、首轮失败排除 4 个，最终 11 个；Claude 筛选 14 个、首轮失败排除 2 个，最终 12 个。[C1 关闭记录](evidence/g5/campaign01-qualification-closure.json) · [C2 筛选与排除明细](evidence/g5/campaign02-qualification-summary.json)

验证首跑中，两个模型均未出现 A 通过而 G5 失败的配对；GPT-4.1 的 long_context_17 出现一次 A 失败／G5 通过。该条件对称补跑后，累计为 A **0/3**、G5 **1/3**，因此不能把首跑多通过一道解释为稳定提升；补跑没有覆盖主表的首跑分数。[最终分歧记录](evidence/g5/campaign02-final-scientific-decision.json)

行为审查也没有证明模型不再犯错：首跑中 GPT-4.1 的 long_context_34 两组均被标记写入内容问题，且审查记录指出原请求存在一定歧义；long_context_17 的补跑中，两组都出现了阻塞式确认和额外内容写入的案例。两个批次最终审查完成后未确认 G5 新增退化，官方失败结果仍全部保留。[批次一行为审查](evidence/g5/campaign02-batch01-continuations-behavior-review.json) · [分歧补跑审查](evidence/g5/campaign02-batch01-discordance-confirmation-behavior-review.json) · [批次一最终裁定](evidence/g5/campaign02-batch01-completion-decision.json) · [批次二最终裁定](evidence/g5/campaign02-batch02-completion-decision.json)

## 成本与结论边界

截至本轮旧周期结束，累计参考费用为 GPT-4.1 **$9.466962**、Claude **$15.921166**。这是包含前期图替代尝试、资格筛选及诊断等的累计费用，**不是 G5 单次验证费用**，也不是供应商账单金额。[旧周期最终费用记录](evidence/g5/campaign02-final-scientific-decision.json)

目前支持的结论是：**完整可见证据可以通过 G5 事件图文本替代这批任务的原生前缀，并在已测小样本中保持官方通过数。** 记录中的 operational_goal_criteria_met／status=achieved 仅指当时锁定的小样本运行级标准；不等于总体非劣效已建立，也不等于整个项目完成。[原判定的 scope 与 limitations](evidence/g5/campaign02-final-scientific-decision.json)

项目的下一步需要可编辑、可删减的工作记忆，最终以更少 token 支持任务完成。当前允许图表示增加 token；但 G5 的通过率结果尚未验证删除、字段投影、过程折叠、风险预测或编辑后的任务保持效果，也未完成更晚边界、多次替换及其他主工具领域的验证。G5 可以作为后续研究的候选表示，不能仅凭本表宣称它已经是有效的压缩方案。[当前未压缩及单边界范围](evidence/g5/g5-final-method-scope-review.json)

后续扩领域实验目前按用户要求暂停；本次发布仅整理已有 G5 结果，没有新增模型调用、改写评分或修改原始实验记录。
