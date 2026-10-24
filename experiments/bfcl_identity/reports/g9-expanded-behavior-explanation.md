原生历史 A 与 G9 图替代 R 在本批有效续跑上的官方结果相同：GPT-4.1 都为 6/8，Claude 都为 9/10；18 个成对条件里没有新增官方失败，也没有恢复，但这不能推出行为等价或统计非劣。[冻结汇总](evidence/g9/g9-expanded-unmasked-summary.json)

| 模型 | 每组轨迹／可见续跑轮次 | 零工具轮 A/R | 报错后阻塞确认 A/R | 错对象或来源 observed A/R | 来源 unclear A/R |
|---|---:|---:|---:|---:|---:|
| GPT-4.1 | 8／13 | 0/0 | 0/0 | 0/0 | 0/0 |
| Claude | 10／16 | 0/0 | 0/0 | 1/0 | 2/3 |

以上按冻结盲审的“用户轮次”计数，只统计可见续跑部分；`unclear` 单列，不能当成正确，也不能把完成后的可选帮助邀请当成阻塞确认。[计数与口径](evidence/g9/g9-expanded-behavior-explanation.json)

三个共同失败条件的具体原因：

- **GPT-4.1 long_context_190：** A、R 都联系了正确预订的客服、创建了工单，但都在指定 description 后追加解释，原 checker 因工单状态与标准描述不同判失败。[F190：原始参数与 checker 指针](evidence/g9/g9-expanded-behavior-explanation.json)
- **GPT-4.1 long_context_196：** 同为失败掩盖了重要差异：A 按给定描述新建 ID2，随后原 checker 报缺少历史 ID1 的创建输出；R 还扩写描述并指定 priority=3，而标准状态为1，因此先出现状态不匹配。R 独有的字段偏离需要保留，不能因两组都失败而忽略；盲审对它是否构成额外副作用仍标为 `unclear`。[F196：参数、状态差异和原盲审](evidence/g9/g9-expanded-behavior-explanation.json)
- **Claude long_context_188：** 两组都成功发布指定推文，但官方要求的执行结果 `authentication_status:false` 没有出现，因此均失败；这对应可见第5轮，不是第6轮的转推来源问题。[F188：原 checker 缺失项](evidence/g9/g9-expanded-behavior-explanation.json)

还有两处不能被总分遮住的差异：

- **两组均通过的 GPT-4.1 long_context_170：** R 在取消后尝试联系客服退款，返回 `Booking not found`，没有重试；A 本轮没有联系客服。两组都无退款到账证据，却分别给出退款会自动发起／客服会处理的表述。R 多了一次失败尝试，但该调用响应了用户的明确请求，不能算额外成功写入或新增官方退化，也不属于盲审中的“报错后索要确认”。[P170：调用、返回与原文](evidence/g9/g9-expanded-behavior-explanation.json)
- **Claude long_context_188 的转推：** 两组都执行 `retweet(0)`。A 转推后查询原帖，才发现作者与用户描述不符；R 没查询，并承认未核对。因此 A 的来源错误是 `observed`，R 是 `unclear`。不能把 R 的较低 observed 数解释为更准确，也不能把 A 的查询结果借给 R 判错；A 也未实际撤销或修复。[D188：两条原始轨迹](evidence/g9/g9-expanded-behavior-explanation.json)

Claude base95 两组都通过，但当前发件账号是否为用户指定的 USR005，在两组中均无法由工具返回确认；这属于共同的不确定性。[U095：冻结盲审](evidence/g9/g9-expanded-behavior-explanation.json)

这些是标签冻结后的只读解释，不重评官方分数，不改标签，也不根据单次差异认定图结构导致某种行为；后续优先关注固定写入字段的遵循、失败操作恢复，以及来源未核查与来源正确之间的区别。[完整证据与限制](evidence/g9/g9-expanded-behavior-explanation.json)
