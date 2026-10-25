# GPT-4.1 × 冻结 G9：120 候选题验证完成报告

[报告目录](README.md) · [三模型累计总表](experiment-summary.md#g9-三模型累计结果) · [G9 结构与实际输入](g9-structure-method.md)

**恢复后六阶段全部完成并通过实际请求审计。85 道有效配对中，identity 为 68/85（80.00%），G9 为 66/85（77.65%）；新增失败 2 道、恢复 0 道，差 −2.35 个百分点。**每道题每组一次，这两处是本轮观察到的差异，尚未重复验证。[完成状态](evidence/g9-coverage120/snapshots/completed/execution-state.json) · [逐题成绩及来源哈希](evidence/g9-coverage120/analysis/coverage-selection-summary.json)

## 范围与方法

只跑 GPT-4.1，temperature=0、seed=42、max_tokens=4096。identity 保留原生历史；冻结的 G9-active-record-views-v1 用图生成完整可见证据表示，在完成 k=min(3,用户轮数−1) 轮时替换旧历史前缀，之后的新交互正常追加。G9 没有附带另一份 identity，不压缩，不改官方 eval。两组共享同一条模型生成的合格前缀，随机交错运行。[授权与参数](evidence/g9-coverage120/authorization.json) · [冻结题单与协议](evidence/g9-coverage120/design/selection-review.md)

候选来自文件系统、车辆、交易、旅行四领域，各 15 个题族的 Base/Long-Context 两版本，共 60 族、120 条；这是冻结 Base＋Long-Context 400 条中的 30%，不是整个 BFCL 的 30%。120 个前缀全部生成，35 个官方前缀检查失败，没有替换题，留下 46 个题族、85 个有效配对与 170 条续跑；有效条件为该 400 条范围的 21.25%。[筛选和逐题数据](evidence/g9-coverage120/analysis/coverage-selection-summary.json)

## 官方通过率

| 领域 | 候选 | 前缀排除 | 有效题数 | identity | G9 | 新增失败 / 恢复 |
|---|---:|---:|---:|---:|---:|---:|
| 文件系统 | 30 | 11 | 19 | 19/19（100.00%） | 19/19（100.00%） | 0 / 0 |
| 车辆 | 30 | 17 | 13 | 9/13（69.23%） | 9/13（69.23%） | 0 / 0 |
| 交易 | 30 | 3 | 27 | 25/27（92.59%） | 25/27（92.59%） | 0 / 0 |
| 旅行 | 30 | 4 | 26 | 15/26（57.69%） | 13/26（50.00%） | 2 / 0 |
| **合计** | **120** | **35** | **85** | **68/85（80.00%）** | **66/85（77.65%）** | **2 / 0** |

前三领域逐题结果一致；旅行领域 identity 15/26、G9 13/26。85 对中 66 对共同通过、17 对共同失败；35 个排除均是官方前缀失败，不按 G9 结果或关系是否为空筛题。车辆有 17/30 被排除，因此续跑分母并不均衡。[官方结果汇总](evidence/g9-coverage120/analysis/coverage-selection-summary.md) · [配对表 CSV](evidence/g9-coverage120/analysis/coverage-selection-summary.csv)

## 新增掉点及可观察原因

- **long_context_176，第 2 轮：没有原样填写指定文本。** 两组都取消了预订并创建工单；G9 在用户指定的 description 后额外加了一句有关立即处理和退款的文字，identity 原样填写。官方失败为 TicketAPI 的状态字段不一致。该题新增 ID 关系为零，G9 正文与离线 G5 正文一致，不能将此掉点归因于新增关系。[两组调用、用户原文与评分证据](evidence/g9-coverage120/analysis/coverage-behavior-review.json)
- **long_context_199，第 4 轮：误解用户 ID，随后停止执行。** identity 直接 message_login(USR001)，再向 USR003 发送指定消息；G9 把 USR001 当作用户名传给 get_user_id，报错后继续查用户并要求用户确认，最终没有登录或发消息。官方失败为 MessageAPI 的状态不一致，是真实未完成操作，不是答案正确却少一次查询。这题有 booking_id 连接，但没有把用户登录 ID 连接错的直接证据；当前请求本身已给出登录和收件人 ID。[两组调用、用户原文与评分证据](evidence/g9-coverage120/analysis/coverage-behavior-review.json)

两题都通过了完整可见证据审计，观察到的差异是行为选择或参数填写变化；单次对比不足以证明其稳定性，也不足以定位为某一种新增关系造成的因果影响。[实际请求及完整性证书](evidence/g9-coverage120/analysis/coverage-selection-summary.json) · [行为核查](evidence/g9-coverage120/analysis/coverage-behavior-review.json)

## Token

下表是每道有效题在接入点之后，**整条续跑所有成功请求的输入＋输出 token 均值**，包含工具定义和多次携带的上下文，不含共享前缀生成，也不是单独的记忆正文 token；两组都保留全部 85 道题，包括失败题。[逐请求核对与详细口径](evidence/g9-coverage120/review/coverage-token-cost-review.md)

| 领域 | 每组题数 | identity 平均总 token | G9 平均总 token | 变化 |
|---|---:|---:|---:|---:|
| 文件系统 | 19 | 12,255.1 | 13,901.7 | +13.44% |
| 车辆 | 13 | 13,539.5 | 14,921.2 | +10.20% |
| 交易 | 27 | 50,508.1 | 52,209.9 | +3.37% |
| 旅行 | 26 | 14,935.8 | 17,196.2 | +15.13% |
| **总体** | **85** | **25,422.5** | **27,233.8** | **+7.13%** |

首次续跑请求的平均输入为 7,277.3 → 7,813.2 token（+7.36%，含工具定义）。identity 完整续跑共 2,142,047 输入＋18,862 输出；G9 为 2,296,545 输入＋18,331 输出。成功续跑请求数为 270 → 271。当前无压缩，不能把此结果当作压缩收益。[请求级 token 与费用明细](evidence/g9-coverage120/analysis/coverage-token-cost-summary.json)

## 费用

金额均按冻结无缓存参考价（输入 $2/百万、输出 $8/百万）由已知 usage 计算，不是已核实的 Azure 账单。共享前缀只生成一次；35 个排除前缀的 $2.181052 已包含在前缀项中，不再重复相加。[费用核对](evidence/g9-coverage120/review/coverage-token-cost-review.md)

| 领域 | 全部前缀 | identity 续跑 | G9 续跑 | 已知参考费用 | 未知请求保守预留 |
|---|---:|---:|---:|---:|---:|
| 文件系统 | $1.483702 | $0.479618 | $0.542532 | $2.505852 | $0.000000 |
| 车辆 | $1.775836 | $0.360548 | $0.396400 | $2.532784 | $0.000000 |
| 交易 | $3.392758 | $2.790778 | $2.877186 | $9.060722 | $2.125852 |
| 旅行 | $1.236534 | $0.804046 | $0.923620 | $2.964200 | $0.000000 |
| **合计** | **$7.888830** | **$4.434990** | **$4.739738** | **$17.063558** | **$2.125852** |

总预算占用 **$19.189410 / $35**，剩余 $15.810590，没有在途请求或自动追加实验。1,319 个成功请求与 usage 逐项对齐，另 10 个重试的未知费用保留完整预留，全部来自交易领域。全活动已知输入 8,222,587、输出 77,298 token；其中 6,710,656 cached-input token 是输入子集，没有额外累加，也没有从参考费用扣缓存折扣。[完整账本与对账结果](evidence/g9-coverage120/analysis/coverage-token-cost-summary.json)

## 解释边界与运行记录

新增 ID 关系实际激活 26/85 道，其中 identity 16/26、G9 15/26；零关系的其余 59 道为 52/59、51/59。两部分题目不同，不能据分组成功率判断关系的因果收益。本批含既往暴露题，不能整体称为全新的独立保留集。[关系与暴露分层](evidence/g9-coverage120/analysis/coverage-selection-summary.md)

按 46 个题族做 50,000 次成对聚类 bootstrap，差值的事后描述性 95% 区间为 [−5.88，0.00] 个百分点；这不是预注册非劣检验，区间包含 0 不等于证明通过率保持。当前直接证据是前三领域本批保持逐题结果、旅行新增两处失败，尚不能宣称整体目标完成。[算法与限制](evidence/g9-coverage120/analysis/coverage-selection-summary.json)

最初 k1 完成后因外围审计器不兼容第一轮评分格式而暂停；修复只涉及审计器的 k1 评分格式、原因标签和图快照重建，冻结 runner/graph/eval 未改。80 项断网检查及已有 26 条离线复审通过后，从 k2 继续，没有重跑原前缀或清零费用。随后六阶段全部通过；本次汇总没有调用模型、没有重新评分。[修复说明](evidence/g9-coverage120/review/audit-k1-fix-review.md) · [续跑准入](evidence/g9-coverage120/snapshots/completed/launch-admission-resume-01.json) · [最终状态](evidence/g9-coverage120/snapshots/completed/execution-state.json)
