# G9 扩展验证独立结果审查

修正后通过，未发现剩余阻塞问题。审查对象为[结果报告](g9-expanded-validation-results.md)与[行为说明 V2](g9-expanded-behavior-explanation-v2.md)；完整复算、文件哈希及更正记录见[审查 JSON](evidence/g9/g9-expanded-independent-results-review.json)。

| 模型 | 合格条件 | identity / G9 官方通过 | G9 新增掉点 / 恢复 | 有记录连接条件的两组通过 |
|---|---:|---:|---:|---:|
| GPT-4.1 | 8/12 | 6/8 / 6/8 | 0 / 0 | 3/5 / 3/5 |
| Claude | 10/12 | 9/10 / 9/10 | 0 / 0 | 4/5 / 4/5 |

独立核对 24 个原始前缀资格、36 份官方评分及其 checker/result 文件，复算领域、连接和 18 对配对分母；所有结果一致。另检查 60 份原生记录、305 条 provider usage 和四阶段账本，费用重算为 GPT $2.079358、Claude $4.246932，合计 $6.326290；本批未知费用为零，历史 GPT 未知预算 $3.070038 仍保留。首请求与全轨迹 token 均按各自口径复算通过，G9 两项均值均增加。[逐项复算](evidence/g9/g9-expanded-independent-results-review.json)

发现并修正一处事实错误：GPT `long_context_196` identity 缺少的是关闭前 `get_ticket(1)` 查询返回，原说明误称历史创建输出；原 checker 的标准调用与实际调用直接支持更正。G9 独有的描述扩写及 priority=3 有原文证据，但盲标签仍为 `extra_side_effect=unclear`，不能据此改称已证实的不安全操作。V1、原评分和盲标签均保留；缓存措辞也已收窄为 provider 报告值。[更正及证据](evidence/g9/g9-expanded-behavior-explanation-v2.json)

行为核对覆盖 58 个可见后续回合、68 次工具调用、318 条盲审原文；V2 的 40 个引用指针、四组行为统计与两份文档的 37 个本地链接均通过核验。相同官方分数并非行为等价，报告已保留 lc196、lc170 和 Claude lc188 的差异。[审查记录](evidence/g9/g9-expanded-independent-results-review.json)

两批 A/R 的代码、接入与推理设置一致且题族不重叠，描述性合计 GPT 12/18、Claude 19/22 均可复现；这是 24 个登记题族中的 40 个合格模型条件，不能视为 40 个独立题族或非劣效证明。本轮没有 G5 付费对照或压缩实验，不支持新增连接的因果收益或整体目标完成。[方法兼容性与边界](evidence/g9/g9-expanded-independent-results-review.json)
