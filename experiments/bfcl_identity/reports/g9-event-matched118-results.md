# GPT-4.1：Identity、Event Graph 与 G9 的118道配对比较

结果整理日期：2026-11-05。每个条件每组一次；完整证据、不压缩、不改官方eval。

200个固定候选中118个触发图替换；本次补跑114道G9，加已完成的4道官方API smoke。Identity和Event全部复用旧结果。

## 方法与范围

- **Identity**：保留原生用户、assistant、工具调用及返回消息。
- **Event Graph**：Bofeng新版事件图（Event tables-v1 + minimal），将历史组织为事件、实体和版本化事实表。
- **G9 / Evidence Graph**：将完整可见历史保存为结构化证据块，并连接同命名空间、类型与值的ID；模型接收图表示，不额外附带一份identity。[G9方法](../../../docs/g9-memory.md)

三组使用同一批GPT-4.1生成的历史前缀，在历史消息JSON首次严格超过1,000 token的同一保存接入点比较；图组只替换一次历史，后续按原运行器续跑。候选范围是题族0–49的Base、Long-Context、Missing-Function、Missing-Parameter四类，共200个条件，不是整个BFCL。118个达到替换阈值，82个未触发；没有增加“identity必须成功”的筛选。此前103对G9累计结果采用不同范围和接入协议，保留在[历史总表](https://github.com/ungrandroi/CS769/blob/462ecb5f6ead22a5332fb0010cf5c641f6fce0a5/experiments/bfcl_identity/reports/experiment-summary.md#g9-三模型累计结果)，不与本批合并。[协议](evidence/g9-matched118/protocol.json) · [逐题清单](https://github.com/ungrandroi/CS769/blob/462ecb5f6ead22a5332fb0010cf5c641f6fce0a5/experiments/bfcl_identity/reports/evidence/g9-matched118/paired-results.json)

118个接入点中只有4个出现G9的ID连接；本轮主要检验完整证据图表示，不能单独证明新增ID关系提高了成功率。[审计汇总](evidence/g9-matched118/summary.json)

## 结果总表

| 方法 | 通过数 | 通过率 | 首次请求平均输入token | 接入后累计输入token | 累计输出token |
|---|---:|---:|---:|---:|---:|
| Identity | 31/118 | 26.3% | 3,586.98 | 2,638,366 | 33,483 |
| Event Graph | 33/118 | 28.0% | 6,599.48 | 4,245,726 | 36,458 |
| G9（Evidence Graph） | 34/118 | 28.8% | 4,366.73 | 3,005,118 | 34,604 |

来源：[汇总及费用](evidence/g9-matched118/summary.json)、[逐题结果](https://github.com/ungrandroi/CS769/blob/462ecb5f6ead22a5332fb0010cf5c641f6fce0a5/experiments/bfcl_identity/reports/evidence/g9-matched118/paired-results.json)。首次输入含系统提示和工具定义，缓存输入仍计入token数量。

| BFCL类别 | 有效配对数 | Identity通过 | Event通过 | G9通过 |
|---|---:|---:|---:|---:|
| multi_turn_base | 13 | 7 | 6 | 7 |
| multi_turn_long_context | 39 | 16 | 15 | 15 |
| multi_turn_miss_func | 41 | 3 | 7 | 6 |
| multi_turn_miss_param | 25 | 5 | 5 | 6 |

相对identity：G9新增掉点4道，改善7道，通过率差+2.54个百分点；按题族聚类的描述性95%区间为[−1.69，+7.14]个百分点。
首次请求输入差为+779.75 token（+21.74%）。
新增掉点：multi_turn_long_context_38, multi_turn_miss_param_15, multi_turn_long_context_35, multi_turn_long_context_24
改善：multi_turn_miss_func_46, multi_turn_long_context_20, multi_turn_miss_param_38, multi_turn_miss_param_14, multi_turn_miss_func_35, multi_turn_long_context_17, multi_turn_miss_func_43

相对event：G9新增掉点6道，改善7道，通过率差+0.85个百分点；按题族聚类的描述性95%区间为[−5.56，+7.32]个百分点。
首次请求输入差为-2,232.75 token（-33.83%）。
新增掉点：multi_turn_long_context_25, multi_turn_miss_func_45, multi_turn_miss_func_26, multi_turn_miss_func_14, multi_turn_long_context_35, multi_turn_long_context_24
改善：multi_turn_miss_param_1, multi_turn_long_context_5, multi_turn_base_2, multi_turn_miss_func_5, multi_turn_long_context_46, multi_turn_long_context_17, multi_turn_miss_func_43

本次114道G9费用按usage及缓存优惠计算为$2.879028，未缓存保守口径为$6.172596。加之前4道官方smoke，118道G9合计$2.944540；最短配置探活$0.000030另列。旧identity/Event未重新付费。

另有82个未触发条件，identity通过42道。它们没有接受图替换，不放入118道配对比较的分母。详见[未触发清单](https://github.com/ungrandroi/CS769/blob/462ecb5f6ead22a5332fb0010cf5c641f6fce0a5/experiments/bfcl_identity/reports/evidence/g9-matched118/untriggered.json)。

完整性：全部历史重放、证据还原、工具/采样参数、评分轨迹哈希、冻结源码检查通过；未压缩、未附带identity、未改官方eval。

本轮冻结图格式，没有根据结果调参；每个条件只运行一次。通过率差异的区间跨过0，不能据此宣布G9显著优于两个对照。[协议和来源](evidence/g9-matched118/protocol.json)

新增掉点的原始轨迹已核查，具体观察见下节；这些观察不能单独证明某条图关系导致了行为变化。

## 新增掉点的行为核查

以下为原始工具轨迹中观察到的差异，不把它们直接归因于某条图关系。相对Identity掉点4道、相对Event掉点6道，去重后共8道；其中只有long_context_35和long_context_24是两个对照都通过而G9失败。来源：[20道分歧题的行为证据](https://github.com/ungrandroi/CS769/blob/462ecb5f6ead22a5332fb0010cf5c641f6fce0a5/experiments/bfcl_identity/reports/evidence/g9-matched118/behavior-evidence.json)，其中包含逐组工具序列、官方诊断和服务器原始日志路径。

| 条件（均带multi_turn_前缀） | 相对哪个对照掉点 | 观察到的行为 |
|---|---|---|
| long_context_38 | Identity | 删除 findings_report 后，因 SuperResearch 里仍有其他文件，G9停下来询问；Identity继续清理并删除目录。Event也有同样失败。 |
| miss_param_15 | Identity | 最后一步应对刚得到的行数/词数/字符数 [3,16,60] 求均值；G9重新读取表格，对 [5,9,10,7] 求均值，引用了错误的一组数。Event也有同样失败。 |
| long_context_35 | Identity、Event | echo 写 diff.txt 报文件不存在后，G9询问是否创建；两个对照均继续 touch 后写入，完成任务。 |
| long_context_24 | Identity、Event | 两个对照直接 get_ticket(987654) 后 resolve_ticket；G9改用 get_user_tickets，遇到登录要求后询问账号，未完成后续操作。 |
| long_context_25 | Event | G9在原目录 sort(summary.txt)，没有进入刚复制到的 Research2023；Event进入目标目录后排序。Identity也失败。 |
| miss_func_45 | Event | G9延续重复 ls 的循环直到步数上限，未进入后续轮；Event结束当前回复后，在下一轮 cd 到 ResearchDocs 并完成复制。Identity也撞到上限。 |
| miss_func_26 | Event | G9重复 ls(a=true) 到步数上限；Event停止循环并进入下一用户轮，之后 cd tmp、读取和创建文件。Identity也撞到上限。 |
| miss_func_14 | Event | G9反复查询不存在的联系人并停下；Event在下一轮调用 add_contact，再发送消息。Identity也失败。 |

改善也并非来自同一种行为：miss_func_43中，G9继续登录并发送消息，两个旧对照未完成发送；long_context_46中，G9先退回父目录再删除Drafts，Event直接在错误目录删除；long_context_5中，G9实际调用sort，Event只在文字里声称排序；miss_func_35、miss_func_46、miss_param_38中，G9避免一直消耗步数，进入后续用户轮后完成任务。上述案例同样见[行为证据](https://github.com/ungrandroi/CS769/blob/462ecb5f6ead22a5332fb0010cf5c641f6fce0a5/experiments/bfcl_identity/reports/evidence/g9-matched118/behavior-evidence.json)。其余改善条件已在逐题清单列出，不仅凭通过/失败推断成因。

## Token与费用口径补充

首次请求指同一保存接入点之后的第一次模型请求，采用API返回的输入token，包含工具定义和系统提示；缓存命中不减少token计数。百分比使用组均值之比：100×(G9均值/对照均值−1)。这次三组使用同一批118个接入前历史，避免了此前接入点与样本不一致的问题。接入后的累计token还受步骤数影响，不能全部解释为表示开销。来源：[汇总](evidence/g9-matched118/summary.json)、[协议](evidence/g9-matched118/protocol.json)。

| 方法 | 接入后输入 | 其中缓存输入（输入的子集） | 接入后输出 | 请求数 |
|---|---:|---:|---:|---:|
| Identity | 2,638,366 | 2,441,088 | 33,483 | 696 |
| Event | 4,245,726 | 3,452,288 | 36,458 | 617 |
| G9 | 3,005,118 | 2,228,352 | 34,604 | 658 |

114道新增续跑共648个请求，无不确定失败费用。按返回usage及缓存计价为$2.879028；118道G9（包含之前4道smoke）为$2.944540，加配置探活为$2.944570。保守上限账本忽略缓存优惠，新增114道记$6.172596，仍低于$20授权。费用是按usage计算，尚未独立核对账户账单。历史identity/Event以及之前Azure smoke不计入此次新账本。来源：[费用与预算核对](evidence/g9-matched118/summary.json)、[费用汇总](evidence/g9-matched118/summary.json)。

**结论：在这批相同接入点的历史对照比较里，G9通过数略多，输入开销明显低于Event，但仍比Identity高。单次采样及当前样本范围限制了结论；不能据此宣布G9显著优于Event，或保证整体通过率不下降。**

阶段判断：冻结当前G9作为下一阶段“不删减”的基线，开始研究按图结构删减证据、降低token；本报告不包含任何删减或压缩实验。

[报告目录](https://github.com/ungrandroi/CS769/blob/462ecb5f6ead22a5332fb0010cf5c641f6fce0a5/experiments/bfcl_identity/reports/README.md) · [附件与原始记录说明](https://github.com/ungrandroi/CS769/blob/462ecb5f6ead22a5332fb0010cf5c641f6fce0a5/experiments/bfcl_identity/reports/evidence/g9-matched118/README.md)

本MR仅新增Evidence Graph实现及接入材料，保持main现有方法和默认实验流程。完整历史与逐题日志链接指向已发布的固定提交。
