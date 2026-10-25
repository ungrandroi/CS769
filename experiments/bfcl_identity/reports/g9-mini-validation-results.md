# GPT-5-mini：冻结 G9 小规模验证

[报告目录](README.md) · [三模型累计总表](experiment-summary.md#g9-三模型累计结果) · [G9 结构与实际输入](g9-structure-method.md)

2026-10-24。结论：本轮 identity **13/16（81.25%）**，G9 **12/16（75.00%）**，相差 −6.25 个百分点；有 1 道新增掉点、0 道新增通过，另外 12 道两组通过、3 道两组失败。每题每组仅一次，不能把这次掉点说成已复现的退化，也不能宣布总体通过率保持。[官方结果、逐题来源与哈希](evidence/g9-mini/analysis/mini-official-results.json)

| 范围 | identity | G9 | 新增掉点 / 新增通过 |
|---|---:|---:|---:|
| 全部 16 道合格题 | 13/16 | 12/16 | 1 / 0 |
| 交易，8 道 | 6/8 | 6/8 | 0 / 0 |
| 旅行，5 道 | 4/5 | 4/5 | 0 / 0 |
| 车辆，3 道 | 3/3 | 2/3 | 1 / 0 |
| 新增关系实际非空，7 道（上述题目的子集） | 5/7 | 5/7 | 0 / 0 |

表中领域和关系子集均来自完整配对汇总，关系子集不另外加到总样本数中。[分组与逐题结果](evidence/g9-mini/analysis/mini-official-results.json)

本轮做了什么：沿用 GPT-4.1／Claude 两批验证的同一组 **24 个候选题族**，交易、旅行、车辆各 8 个；由 mini 自己生成原生前缀，24 个均尝试，16 个通过官方前缀检查，8 个在接入 G9 前失败，因此没有续跑；不补题、不按 G9 结果选题。合格题中 2 道在完成第 2 轮后接入，14 道在第 3 轮后接入。每道合格题跑 identity 与 G9 各一次，共 **32 条续跑**，两组共享该题同一个 mini 前缀。[固定候选表](evidence/g9-mini/design/g9-mini-fixed24-selection-v1.json) · [完整筛选及逐题记录](evidence/g9-mini/analysis/mini-official-results.md)

方法保持冻结：使用 `G9-active-record-views-v1`；G9 用完整可见证据的图表示替换旧历史，**没有附带 identity，没有压缩，没有改官方 eval**；之后的新交互仍正常进行。两组均用 GPT-5-mini、medium reasoning、seed 42、最大输出 16,384 token，不设置 temperature。四阶段实际请求和费用审计全部通过，参考文件见完成记录。[授权与设置](evidence/g9-mini/authorization.json) · [四阶段审计入口](evidence/g9-mini/execution-state.json)

**唯一掉点：`multi_turn_base_59`。** 第 4 轮用户要求启动发动机，两组首次启动均遇到“所有门必须上锁”。identity 随后锁门，遇到刹车条件后踩刹车，再启动成功；G9 则停下来询问用户选择，没有完成启动。官方失败是 `instance_state_mismatch`：发动机仍停止、门仍未锁、刹车仍未按下。因此这里确实有动作未完成，不只是“答案正确但少了一次工具调用”的评分差异。[identity 官方记录](evidence/g9-mini/mini04-continuation-k3/runs/gpt-5-mini/multi_turn_base_59/boundary-3/1/identity/official-score.json) · [G9 官方记录](evidence/g9-mini/mini04-continuation-k3/runs/gpt-5-mini/multi_turn_base_59/boundary-3/1/graph-record-view-full/official-score.json) · [冻结盲审 B，case-011](evidence/g9-mini/blind-review/review-b.md)

同题第 5 轮，identity 调用对数工具并给出结果，G9 再次澄清而未计算；这是额外观察，不能代替已经在第 4 轮发生的官方失败原因。这道题的新增关系为零，审计确认其 G9 请求与离线 G5 表示相同；**不能把此次失败归因于 G9 新增关系**，也没有实际 G5 续跑组可作三组比较。[解盲后的逐轮证据](evidence/g9-mini/analysis/mini-behavior-results.json) · [实际请求审计](evidence/g9-mini/analysis/mini04-continuation-k3-actual-audit.json)

行为检查由两名未见分组及成绩的审查代理分别覆盖全部 16 道题、32 条轨迹、52 个可见后续轮次，224 条原文证据经指针和原样摘录校验；标签固定后才连接分组。下表为可重叠的行为标签，不是另一套评分，也不是因果估计。[解盲前冻结记录](evidence/g9-mini/analysis/pre-unmask-label-freeze.json) · [审查 A](evidence/g9-mini/blind-review/review-a.md) · [审查 B](evidence/g9-mini/blind-review/review-b.md)

| 后续行为 | identity | G9 |
|---|---:|---:|
| 可见后续轮次 | 26 | 26 |
| 工具调用次数 | 40 | 32 |
| 零工具轮次 | 3 | 4 |
| 同一轮报错后成功恢复 | 3 | 1 |
| 报错后停下询问 | 2 | 2 |

这些差异说明同分题的行为也可能不同；本次盲审没有发现足够证据确认错对象操作或额外已发生的副作用，不等于证明不存在任何此类问题。[完整分组行为记录](evidence/g9-mini/analysis/mini-behavior-results.json)

| 每条合格续跑的 token 均值，n=16/组 | identity | G9 |
|---|---:|---:|
| 第一个后续请求的输入，含工具定义 | 8,015.7 | 8,554.7 |
| 整条续跑输入 | 36,531.3 | 28,777.4 |
| 整条续跑输出，含推理 | 1,018.1 | 1,175.5 |
| 整条续跑输入＋输出 | 37,549.4 | 29,952.9 |

首请求输入平均增加 **539 token（6.72%）**。整条续跑总 token 虽少约 **20.23%**，但不能解释为压缩或效率提升：`long_context_138` 两组都失败，G9 后续没有调用工具；加上 `base_59` 未继续恢复，这两题合计少 176,345 token，其余 **14 道题的 G9 token 全部增加**，合计多 54,802。12 道两组通过题的总 token 也从 327,810 增到 368,733（+12.48%；仅为按结果划分的描述性子集）。以上续跑 token 不含共享前缀生成，推理 token 已包含在输出中，不重复相加。[逐题 token 与调用记录](evidence/g9-mini/analysis/mini-official-results.json) · [行为证据](evidence/g9-mini/analysis/mini-behavior-results.json)

| 独立 mini 账本 | 按 usage 参考价计费 | 未确定费用的保守预留 |
|---|---:|---:|
| 全部 24 个前缀 | $0.318700 | $0 |
| identity 的 16 条续跑 | $0.178705 | $0.055516 |
| G9 的 16 条续跑 | $0.152726 | $0.051513 |
| 合计 | **$0.650131** | **$0.107028** |

共 293 次已记录 usage 的成功请求，另 2 次 HTTP 429 保留完整费用预留；预算占用约 **$0.7572 / $3**，无在途请求。费用按冻结参考价计算、未扣输入缓存折扣，不是服务商最终账单；被排除前缀的 $0.082255 已含在前缀费用中。此账本与旧 GPT-4.1／Claude 账本独立。[账本](evidence/g9-mini/mini-budget.json) · [核对后的费用与 token](evidence/g9-mini/analysis/mini-official-results.json)

本轮是冻结方法在同一题池上的新模型检查，24 个题族此前已用于其他模型；不是未见题目的独立大样本验证，也没有测试压缩或单独验证新增关系的因果收益。当前观察支持“mini 有一例需要进一步复现的行为掉点”，不支持“G9 已普遍保持通过率”或“新增关系造成失败”；本轮已结束，没有自动补跑或改格式。[固定设计](evidence/g9-mini/design/g9-mini-fixed24-selection-v1.json) · [完整完成状态](evidence/g9-mini/execution-state.json)
