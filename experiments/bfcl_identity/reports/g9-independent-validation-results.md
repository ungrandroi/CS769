# G9 完整记录视图：独立小规模验证

2026-10-24。**这批新题中，R 与 identity 的逐题通过情况一致；尚未观察到新增掉点，也没有证明关联边提高成功率。**这是每个合格条件各一次的条件续跑，不能据此宣称普遍保持通过率；此前 GPT-4.1 `base_43/k2` 的已复现图退化仍未修复。[冻结结果](evidence/g9/g9-independent-unmasked-summary.json)、[此前开发记录](evidence/g9/dev02-structural-repeat-independent-audit.json)

## 方法与范围

A 是完整可见原生历史 identity；Claude 已结束前缀的 thinking 在三组中统一移除，接入后的 thinking 设置保持原协议。E 是图生成的完整 G5 证据正文；R 使用同一完整 G9 图，在 E 正文后显示有来源支持的 typed-ID 记录成员关系。G8 的字段内容所有权、G9 的记录/标识节点及支持关系保存在图中，R 只由图编译，替换已结束的原生历史前缀；不另附 identity，不压缩，不修改官方 eval。G7 的派生观察显示关闭，接入后的实时工具交互保持原协议。[实际结构示例](g9-structure-method.md)、[冻结协议](evidence/g9/g9-independent-increment-scope-v1.json)

选择最初保留、未参与本轮开发的 12 个题族，车辆、交易、旅行各 4 个；10 题在完成 3 轮后接入，2 题在完成 2 轮后接入。两个模型分别生成前缀，24 个前缀全部保留在筛选分母中；GPT 的 `base_71/k3`、`long_context_79/k2` 未通过官方前缀检查而排除，Claude 无排除，不补题、不按候选结果或关联边是否为空筛选。[题目清单](evidence/g9/g9-independent-fixed12-selection-v1.json)、[资格记录](evidence/g9/g9-independent-unmasked-summary.json)

## 官方结果

| 模型 | 登记/合格题数 | 每组次数 | A：identity | E：G5 正文 | R：G9 完整记录 | R 对 A 新增掉点/恢复 |
|---|---:|---:|---:|---:|---:|---:|
| GPT-4.1 | 12 / 10 | 1 | 6/10（60.0%） | 6/10（60.0%） | 6/10（60.0%） | 0 / 0 |
| Claude Sonnet 5.5 | 12 / 12 | 1 | 10/12（83.3%） | 9/12（75.0%） | 10/12（83.3%） | 0 / 0 |

共 66 条续跑：GPT 30、Claude 36；同一题的两个模型并非两个独立题族。上表及全部逐题配对结果均来自原官方评分，不包含语义重评分。[完整结果与原评分哈希](evidence/g9/g9-independent-unmasked-summary.json)

真正有 G9 成员关系的条件，每个模型只有 4 个，均在交易领域；这 4 个条件内，两模型各自 A/E/R 都为 3/4。其余 GPT 6 个、Claude 8 个条件的 E/R 首请求完全相同；Claude 的唯一 R 对 E 增益恰在这样的零关联条件 `long_context_79`，所以不能归因于关联边。[结构覆盖与配对分层](evidence/g9/g9-independent-unmasked-summary.json)

## 行为与失败原因

独立审查覆盖 22 个匿名条件、66 条轨迹、111 个后续用户回合、183 次工具调用，先完成标签再揭盲。审查子代理在平台额度中断前已写完标签；恢复时只核验覆盖、723 处证据指向、429 段逐字摘录和 183 份调用参数子集并冻结，没有改标签。审查原本未交付的说明文件由本报告补充，不冒称中断后又完成了一轮独立审查。[原盲标签](evidence/g9/g9-independent-blind-labels.json)、[中断恢复与冻结记录](evidence/g9/g9-independent-blind-recovery-freeze.json)

| 观察 | 具体证据及解释 |
|---|---|
| Claude `long_context_79` 的 E 失败 | E 先执行 `releaseBrakePedal`，再设巡航；官方报告刹车状态不匹配。A/R 直接设巡航并通过。E/R 初始输入相同，属于本次运行行为差异，不能说 R 的图关系修复了问题。 |
| GPT `base_59`、`long_context_80` 的共同失败 | A/E/R 都在启动引擎报错后询问是否锁门或踩刹车，没有在该轮完成恢复；官方引擎等状态不匹配。这是三组共有问题。 |
| GPT `base_121` 的共同失败 | 三组都实际提款，但官方要求的提款前账户余额返回缺失；不能把实际提款成功替代官方通过。 |
| `long_context_162` 的共同失败 | GPT A/R 的官方诊断为兑换返回不匹配；GPT E 还把兑换后的 20580 写入预算，官方主诊断为预算状态不匹配。Claude A/R 当轮先澄清而未调工具，Claude E 虽调用兑换仍未设置预算。三组均未通过；20580 的预算参数问题仅属于 GPT E。 |
| Claude `long_context_138` 的共同失败 | 三组都看到订单仍为 Open，暂缓发送用户指定的“已完成”消息，后续也没有可撤回的目标消息；官方消息状态不匹配。不能改评分，也不将它归因于图。 |
| 通过率相同但执行更长 | Claude `base_71` 中 A 先锁门再启动，E/R 首次启动报错后才锁门重试；三组最终都通过，E/R 多一次工具调用、两次模型请求。 |

上述行为由冻结盲标签与原官方诊断联合解释；并未把额外只读查询、完成后的可选提问一概当成退化，也没有发现可确认的 R 独有错对象操作。[逐轨迹行为、诊断类型和原记录链接](evidence/g9/g9-independent-behavior-token-explanation.json)

## Token 与费用

下表 token 为每条合格续跑的均值。首请求输入包含工具定义及完整请求；全轨迹 token 是该条续跑所有已知 provider 输入与输出之和，包含后续调用差异，不是记忆正文 token，也不包含共享前缀生成成本。[首请求账本匹配](evidence/g9/g9-independent-first-request-tokens.json)、[全请求统计](evidence/g9/g9-independent-unmasked-summary.json)

| 模型 / 组 | 首请求输入 token | 全轨迹输入＋输出 token | 本组已结算参考费用 |
|---|---:|---:|---:|
| GPT A | 6,233.5 | 29,943.7 | $0.613472 |
| GPT E | 6,749.0 | 31,281.0 | $0.635772 |
| GPT R | 6,791.0 | 31,970.9 | $0.654490 |
| Claude A | 11,952.7 | 84,106.5 | $2.112444 |
| Claude E | 12,780.8 | 61,996.9 | $1.580062 |
| Claude R | 12,845.0 | 58,970.8 | $1.498820 |

R 相对 E 的首请求输入只增加平均 42 token（GPT）和 64.25 token（Claude）。Claude 全轨迹均值下降主要来自 `long_context_138`：A 多查交易历史并多执行后续查询，共 558,490 token，R 为 226,984，两组都失败。Claude 的逐题 R−A token 差值中位数反而是 **+2,350.5**；因此不能把均值下降说成图压缩或稳定节省。[逐题 token 拆账与调用序列](evidence/g9/g9-independent-behavior-token-explanation.json)

| 独立验证阶段 | GPT | Claude |
|---|---:|---:|
| 全部 24 个前缀的生成，各模型 12 个 | $0.771086 | $1.715442 |
| 合格条件的全部 A/E/R 续跑 | $1.903734 | $5.191326 |
| 已知结算合计 | **$2.674820** | **$6.906768** |
| 本阶段新增不确定请求预留 | **$0.201766** | $0 |

费用沿用冻结的无缓存参考价，不是最终账单；GPT 的缓存输入仍包含在 token 和参考费用中。一次 GPT HTTP 429 的未知用量保留预算，没有当成零成本。G9 确定性构图不调用模型，CPU 时间未计费；此前语义抽取探索成本仍计入整个 campaign，不混入本表。[费用审计](evidence/g9/g9-independent-unmasked-summary.json)

截至最后完整账本，本轮 12 小时探索累计 GPT 已结算 **$13.959336**，另预留 **$2.464884**，距 $25 上限剩 **$8.575780**；Claude 已结算 **$31.977676**，距 $50 上限剩 **$18.022324**。当前无在途请求。[账本统计与来源哈希](evidence/g9/ind04-g9-continuation-k2-budget-totals.json)

## 当前结论

G8/G9 提供了比 G5 更明确的字段所有权及带来源的记录连接，接近 proposal 后续 projection 与支持失效检查需要的结构；本次独立小样本未观察到 R 相对 identity 的新增官方退化。但关联机制的有效覆盖仍小，未出现可归因于关联边的成功率提升，已知文件系统缺口仍在；不据此宣布整体目标完成或进入压缩阶段。[结构与可编辑性边界](g9-structure-method.md)、[完整结果与限制](evidence/g9/g9-independent-unmasked-summary.json)

报告文字已根据[独立逐句核验](g9-independent-report-grounding-review.md)明确 Claude 旧 thinking 的共同处理，以及 GPT E 与 Claude E 的行为归属；数值及原实验记录未改。
