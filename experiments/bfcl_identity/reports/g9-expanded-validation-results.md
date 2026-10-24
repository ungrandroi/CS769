# G9 新增独立题验证：2026-10-24

[报告目录](README.md) · [上一批独立验证](g9-independent-validation-results.md) · [方法与实际输入](g9-structure-method.md) · [证据附件](evidence/g9/README.md)

**新增这批题中，G9 与 identity 的逐题官方通过情况一致：GPT-4.1 都是 6/8，Claude 都是 9/10；没有新增官方掉点，也没有恢复题。**这是每个合格条件每组一次的结果，不能据此宣布整体通过率保持或 G9 优于 G5。[冻结结果及原评分哈希](evidence/g9/g9-expanded-unmasked-summary.json)

## 测了什么

A 是完整可见原生历史 identity；R 是原先冻结的 G9 完整记录视图：由图生成完整证据正文，再显示有来源支持的、同一命名空间和类型下相同 ID 的记录连接。R 替换已完成的原生历史前缀，不附带另一份 identity；接入后仍正常进行工具交互。本轮不压缩，不改工具或官方 eval；Claude 已结束轮次的 thinking 在两组统一不回传，新轮推理设置不变。[冻结协议](evidence/g9/g9-expanded-increment-scope-v1.json)、[图结构示例](g9-structure-method.md)

这轮固定选择新的 12 个题族，车辆、交易、旅行各 4 个；10 题在完成 3 轮后接入，2 题在完成 2 轮后接入。沿用原 G9，而非后来开发的 G15 排序变体；为把预算用于新题，正式续跑只做 A/R，没有另跑 G5 组。[固定清单](evidence/g9/g9-expanded-fixed12-selection-v1.json)、[两组预算决定](g9-expansion-two-arm-budget-addendum-v1.md)

## 官方结果

| 模型 | 登记 / 合格条件 | 每题每组次数 | identity | G9 | G9 新增掉点 / 恢复 |
|---|---:|---:|---:|---:|---:|
| GPT-4.1 | 12 / 8 | 1 | 6/8（75.0%） | 6/8（75.0%） | 0 / 0 |
| Claude Sonnet 5.5 | 12 / 10 | 1 | 9/10（90.0%） | 9/10（90.0%） | 0 / 0 |

共生成 24 个前缀并执行 36 条合格续跑；同一题在两个模型上的结果不是两个独立题族。每个合格条件两组共享同一模型生成的前缀；全部 18 对的输入都因历史表示而不同，分数一致不意味着请求或行为完全一致。[完整配对结果](evidence/g9/g9-expanded-unmasked-summary.json)

| 领域 | GPT 合格 / 登记 | GPT 两组各通过 | Claude 合格 / 登记 | Claude 两组各通过 |
|---|---:|---:|---:|---:|
| 车辆 | 1/4 | 1/1 | 4/4 | 4/4 |
| 交易 | 4/4 | 4/4 | 4/4 | 4/4 |
| 旅行 | 3/4 | 1/3 | 2/4 | 1/2 |

表中的筛选分母和成绩来自冻结结果。GPT 的车辆覆盖只有 1 道，不足以概括车辆领域；本轮没有新增文件系统题，因为已有记录显示 49 个多轮文件系统题族均已接触过，第 46 族只有单轮，不能再声称是未见验证题。[领域统计](evidence/g9/g9-expanded-unmasked-summary.json)、[候选池检查](evidence/g9/g9-expansion-feasibility-projection.json)

有实际 G9 记录连接的条件，两模型各 5 个：GPT 两组各 3/5，Claude 两组各 4/5；其余 GPT 3 个、Claude 5 个是零连接条件，仍保留。零连接时 R 正文与离线生成的 G5 正文相同，但与 identity 不同；这部分检验了完整图历史替换，不能用来证明新增连接的作用。[连接激活分层](evidence/g9/g9-expanded-unmasked-summary.json)

## 筛选与审查

GPT 排除 `base_81/k3`、`base_95/k3`、`long_context_60/k3`、`long_context_188/k3`；Claude 排除 `long_context_170/k3`、`long_context_196/k3`。原因均为第一份原生前缀未通过官方检查；未补题、未重新生成前缀，也未按 G9 的后续结果或连接是否为空筛选。[全 24 个资格记录](evidence/g9/g9-expanded-unmasked-summary.json)

三位审查 agent 在不知道组别和官方分数时，分别检查 6 个匿名条件；合并覆盖 18 个条件、36 条轨迹、58 个后续用户回合、68 次工具调用及 318 条原文证据。全部标签先冻结并校验引用，再关联官方评分；行为解释不替代官方结果。[标签及证据](evidence/g9/g9-expanded-blind-labels.json)、[冻结记录](evidence/g9/g9-expanded-blind-merge-freeze.json)

## 分数相同，行为仍有差别

| 共同失败条件 | 官方诊断及可见行为 |
|---|---|
| GPT `long_context_190` | 两组都扩写了用户指定的工单 description，官方判工单状态不匹配。 |
| GPT `long_context_196` | identity 按给定描述新建 ID2，随后直接关闭 ID1，缺少 checker 要求的关闭前 `get_ticket(1)` 查询返回；G9 还扩写描述、显式设 priority=3，而标准状态为 1，先出现状态不匹配。**两组都失败掩盖了一次 G9 独有的参数偏离。** |
| Claude `long_context_188` | 两组都发布了指定推文，但缺少 checker 要求的 `authentication_status:false` 返回，因此在可见第 5 轮失败；这不是后面转推来源问题导致的分数。 |

该表由原 checker 诊断与冻结盲审共同支持。`long_context_196` 的参数偏离值得继续跟踪，但盲审对它是否构成额外副作用仍为 `unclear`，不据单次差异断言图导致了不安全操作。[逐项原文、参数和官方诊断](evidence/g9/g9-expanded-behavior-explanation-v2.json)

两组均通过的 GPT `long_context_170` 中，G9 在取消后尝试联系客服退款，返回 `Booking not found` 后没有重试；identity 没有联系退款客服，两组都缺少退款到账证据。Claude `long_context_188` 中，两组都转推了 ID0；identity 后置查询发现来源与用户描述不符，G9 没查询而承认未核实，不能把“没有观察到错误”当成“来源正确”。[行为解释](g9-expanded-behavior-explanation-v2.md)

全部可见后续轮次中，两组都没有零工具轮或报错后的阻塞确认；这不等于每项请求都完成，也不等于没有参数问题。[按模型与组别的行为计数](evidence/g9/g9-expanded-behavior-explanation-v2.json)

## Token 与费用

下表为每条合格续跑的均值。首请求输入包括工具定义；全轨迹 token 是该条续跑所有 provider 输入与输出之和，不包含共享前缀生成。它们都不是单独的记忆正文 token，后者也没有在本表被冒充统计。[请求级统计](evidence/g9/g9-expanded-unmasked-summary.json)

| 模型 | 首请求输入：identity → G9 | 全轨迹输入＋输出：identity → G9 | 全轨迹变化 |
|---|---:|---:|---:|
| GPT-4.1 | 9,525.1 → 10,146.1 | 31,993.0 → 35,085.1 | +9.7% |
| Claude | 13,867.3 → 14,919.8 | 47,956.2 → 51,609.9 | +7.6% |

G9 的首请求平均增加 621 token（GPT）和 1,052.5 token（Claude）；本轮保留全部证据，结果没有显示 token 减少，也没有进行压缩测试。[同一统计来源](evidence/g9/g9-expanded-unmasked-summary.json)

| 本次新增验证费用 | GPT | Claude |
|---|---:|---:|
| 全部前缀生成（各 12 个） | $0.992434 | $2.176146 |
| identity 合格续跑 | $0.518200 | $0.995948 |
| G9 合格续跑 | $0.568724 | $1.074838 |
| 合计 | **$2.079358** | **$4.246932** |

以上共 $6.326290，按冻结参考价计算，并非最终账单；本阶段没有新增未知费用。被排除前缀的费用已包含在首行，GPT $0.183596、Claude $0.291048，不能再加一次。GPT 缓存 token 计入输入，参考价未扣缓存折扣；Claude 报告的缓存读写 token 均为 0。[完整费用统计](evidence/g9/g9-expanded-unmasked-summary.json)、[筛选费用拆账](evidence/g9/g9-expanded-pre-unmask-cost-summary.json)

本轮 12 小时探索累计已知费用为 GPT **$18.327114**、Claude **$39.576554**；GPT 另保留 **$3.070038** 的旧未知请求预算。按 $25/$50 上限，剩余可用分别为 **$3.602848 / $10.423446**，没有在途请求；未与之前实验账本混算。[最终账本统计与来源哈希](evidence/g9/ext04-g9-continuation-k2-budget-totals.json)

## 如何理解累计证据

| 独立验证批次 | GPT：identity / G9 | Claude：identity / G9 |
|---|---:|---:|
| 上一批 | 6/10 / 6/10 | 10/12 / 10/12 |
| 本批新增 | 6/8 / 6/8 | 9/10 / 9/10 |
| 两批描述性合计 | **12/18 / 12/18** | **19/22 / 19/22** |

两批使用相同的 A/R 方法，题族不重复，合计登记 24 个题族；两模型各自全部合格配对中，G9 与 identity 的官方通过情况一致。两批仍只有每题每组一次，资格筛选还限制了适用范围；累计表不是预先规定的非劣效检验，也不能把 40 个模型条件当成 40 个独立题族。[上一批报告](g9-independent-validation-results.md)、[本批原结果](evidence/g9/g9-expanded-unmasked-summary.json)

当前证据支持继续把 G9 作为候选表示：它保留完整证据，且已经在更多新题上没有观察到新增官方掉点。但尚无可归因于新增连接的通过率提升，本轮也没有 G5 对照；此前 GPT `base_43/k2` 的 G5 图替换缺口没有被这些新领域结果修复。后续删减是否安全仍需单独实验，不能由这份无压缩结果推出。[此前缺口](evidence/g9/dev02-structural-repeat-independent-audit.json)、[结构与删减边界](g9-structure-method.md)、[冻结结果限制](evidence/g9/g9-expanded-unmasked-summary.json)
