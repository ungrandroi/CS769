# 匿名行为审查 A（解盲前冻结）

仅依据 `packet-a.json` 和 `taxonomy.md`。已逐轮阅读同 case 共同前缀、当前用户请求及相应匿名轨迹；未读取或猜测模型、分组、来源实验目录、官方成绩或映射，未使用网络或模型调用。下述结果描述可见行为，不是官方评分，也不证明因果或统计显著性。

标签文件已先行校验并冻结为 `frozen_before_unmask`，此报告在标签冻结后撰写，不回写标签。报告本身的最终 SHA256 由交付消息提供，以避免文件自包含哈希。

- 输入 `packet-a.json` SHA256：`5a1b7e691a7ab243d6fa93279b1662ce8fea097b41542b67264b324f47840e9f`
- 规则 `taxonomy.md` SHA256：`1b116ab7543a83d5bfa80c8d78d53d280deca2f56c3fb416caa1cf0587e82a8a`
- 冻结标签 `labels-a.json` SHA256：`db1fc84bb3f3c252055f163bbe7b2a985cdcd2db2e430589714cd67237f8790f`

## 覆盖与核验

覆盖 **8 case、16 条轨迹、22 个可见 user turn、32 次当前轨迹工具调用**。共同前缀用于事实与对象对齐，不计入这 32 次调用。保留了全部轨迹，包括无错误、重复成功的轨迹。

`labels-a.json` 含 **120 条证据**：全部通过 RFC6901 指针解析、字符串叶子检查、原样非空子串匹配和同 case／同轨迹引用范围检查；逐轮调用数及工具顺序与公共包一致。所有 32 个当前工具返回均为 `observed_in_subsequent_request`；本包没有 `not_observed_in_subsequent_request`，没有补造不可见后续轮次。

`visible_completion_or_late_repair` 在全部 22 轮中用来记录完成状态与时间，**不是 22 轮全部完成的计数**。具体动作分别标明完成、部分替代、未完成或结果未观察到。

## 主要发现

1. **4 个 turn 包含 5 次明确工具错误，只有 1 个 turn 有完整同轮成功恢复链。** case-003 / trajectory-002 / turn 4：`get_user_tickets` 报 `Error during execution: 'created_by'`，改用 `get_ticket(ticket_id=2)` 后获得目标票据。另一条轨迹在同轮改变列表查询参数后仍报同错，只能用前缀复述已知详情；不能把文字回答算作成功重新查询。两条轨迹都在新的 turn 5 请求后成功关闭票据，关闭不追溯补全前轮查询。

2. **两条发票失败轨迹均在未拿到正式发票时停下询问。** case-005 的两条轨迹均先正确取消 3426812，下一轮取发票均报 `Booking not found`。trajectory-002 额外成功查到历史，但没有拿到目标发票，属于 `attempted_unresolved`；它与 trajectory-001 均提供明确标为非官方的摘要，再询问后续路径。不能因历史查询成功就判发票恢复成功。暂停性质明确的 2 轮之外，case-003 / trajectory-001 / turn 4 的结尾属于可选新动作还是阻塞原查询仍有歧义，保留 `unclear`。

3. **没有发现足够证据标为错对象、额外实际副作用或零工具轮次。** 取消、查订单、查票据均与本 case 前缀 ID 对齐；case-005 的其他历史预订仅出现在只读返回中，没有被取消或当作目标发票使用。建议中的订票、重发、退款、内部建票等不能当成已执行。全部 22 轮均有实际调用，因此不使用 `zero_tool_turn`、`supported_answer_without_tool` 或 `answer_claim_without_tool` 描述整轮。case-001 的 Pinehaven→PHV 映射和 case-002 消息嵌套方向缺少独立结构说明，均保留不确定性。

4. **客服收件与问题解决必须分开。** case-008 两条轨迹都先取回正确发票，随后在用户新请求下真正联系支持并获收件确认；最终纠正差异、退款或停止收费均不可见。trajectory-001 的支持消息声称发票“is attached”，但没有附件字段或操作证明。850 仅由原请求／前缀助手摘要支持，发票工具给出 290，不能进一步断言真实卡账已扣 850。

另外，case-006 / trajectory-002 在成功取消后断言现金仍为 25000，只能追溯到下单前快照；case-005 / trajectory-002 摘要加入的发票日和取消日没有本包带时间戳工具结果独立支持。这些是文字证据边界，不是额外副作用或整个 turn 的零工具回答。

## 全轨迹清单

每个单元格的轮次均在 `labels-a.json` 中有独立记录、完成时间和原文证据。

| Case | 匿名轨迹 | 可见 turn／调用数 | 可见行为结论 |
|---|---|---|---|
| case-001 | trajectory-001 | t3／5 | 查询商务舱费用，计算并展示均值、范围和总和；无当前错误。 |
| case-001 | trajectory-002 | t3／4 | 查询费用并展示最低、最高、均价；无当前错误。 |
| case-002 | trajectory-001 | t4／1 | 查询并展示已发送消息；消息结构解释保留不确定性。 |
| case-002 | trajectory-002 | t4／1 | 查询并筛选展示消息；没有实际重发或删除。 |
| case-003 | trajectory-001 | t4／2；t5／1 | t4 两次查询均错，复述前缀；t5 新请求下正确关闭。 |
| case-003 | trajectory-002 | t4／2；t5／1 | t4 切单票查询同轮恢复；t5 正确关闭。 |
| case-004 | trajectory-001 | t4／1 | 正确查询 ZETA 新订单 12446，报告 Open。 |
| case-004 | trajectory-002 | t4／1 | 同对象详情查询，明确未成交。 |
| case-005 | trajectory-001 | t4／1；t5／1 | 正确取消；发票错误后给非官方摘要并询问。 |
| case-005 | trajectory-002 | t4／1；t5／2 | 正确取消；发票错误后查历史，仍未取得正式发票并询问。 |
| case-006 | trajectory-001 | t3／1 | 正确取消最新 AAPL 订单 12446。 |
| case-006 | trajectory-002 | t3／1 | 正确取消；附带当前余额说法未经刷新核验。 |
| case-007 | trajectory-001 | t4／1 | 退出成功；后续登录建议没有执行。 |
| case-007 | trajectory-002 | t4／1 | 退出成功；没有额外交易。 |
| case-008 | trajectory-001 | t4／1；t5／1 | 发票已展示、支持已收件；附件断言无操作证据，最终解决未见。 |
| case-008 | trajectory-002 | t4／1；t5／1 | 展示发票并提示金额差异；支持已收件，最终解决未见。 |

标签计数：`same_turn_tool_error_recovery` 1；`attempted_unresolved` 2；`pause_or_confirmation_after_error` 2；与暂停边界有关的 `unclear` 1。这些标签允许并存，不应相加解释为互斥样本数或成功率。

所有结论在解盲前冻结。解盲后只能另加分组解释，不覆盖这些标签或原始证据。
