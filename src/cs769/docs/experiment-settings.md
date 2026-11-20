# 历史实验差异 → 统一配置

这是研究设置的对应关系，不是所有历史轨迹的逐字节复现认证。配置默认费用为 0，不继承任何旧实验授权。

| 历史变化 | 新配置／参数 |
|---|---|
| Identity | `identity`；原生消息保留 |
| 最初 State/Event compact、Dedup | `state_legacy`、`event_legacy`、`event_dedup_legacy` |
| Bofeng 原始／优化编码 | semantic builder；kind、codec、explanation、semantics 四个参数 |
| Event tables-v1 + minimal | `event_table_encoding`；混合语义选 `mixed_domain_event_table_encoding` |
| State tables/shared/columnar；Event shared/source-json | codec 参数，直接使用同一套可逆编码模块 |
| V2 readable + user/assistant | `readable_history_user_role` / `readable_history_assistant_role` |
| V3/V5 的 B | `native_history_index`；明确保留原生历史并追加索引 |
| V4 application_memory | `memory_before_user_request`；索引放进下一条用户消息 |
| complete evidence graph 完整证据及语义附录 | `complete_evidence_graph` |
| structure-first evidence graph 结构前置 | `complete_evidence_structure_first` |
| local-relation evidence graph 关系放到来源节点附近 | `complete_evidence_local_relations` |
| assistant-carried evidence graph assistant 角色 | `complete_evidence_assistant_role` |
| entity-origin evidence graph 实体来源显示 | `complete_evidence_entity_origin` |
| interaction evidence layer 只保留完整事件证据 | `interaction_evidence_graph` |
| identifier anchor layer 引用锚点／仅出现节点 | `evidence_shared_anchors` / `evidence_occurrences_only` |
| observation layer 观察字段／观察节点 | `observation_fields` / `observation_nodes_only` |
| payload layer 内容树地址 | `payload_addresses` |
| evidence graph 同类型、同命名空间 ID 连接 | `evidence_graph_full_view` / `evidence_graph_history_threshold` |
| evidence graph 内联、外部引用、隐藏关系消融 | render=inline/external/visibility/view；view=base/nodes/full |
| event and exchange blocks 事件块／交互块编码 | `evidence_graph_event_blocks` / `evidence_graph_exchange_blocks` |
| lexical references 字面路径关系 | `evidence_graph_lexical_references` |
| call signatures 调用签名 | `evidence_graph_call_signatures` |
| role-based sections 多角色／仅 assistant 分段 | `evidence_graph_historical_user_role` / `evidence_graph_assistant_role` |
| content storage 内容存储（历史上仅离线原型） | `evidence_graph_content_store`；配置可用不代表做过效果验证 |
| selected-exchange ordering 基于已选交互的布局 | `g9-query_layout-C/S/G`；显式 seeds、query_arm、query_branch |
| 首轮／第 k 轮结束接入 | checkpoint kind=completed_turn、turns=k |
| 历史 JSON 严格超过 1000 | kind=history_tokens、counter=history_json、strict=true |
| 工具调用／返回计数 | counter=tool_payload；当前统一 JSON 口径，非旧计数的逐字节保证 |
| 原生请求减固定开销 | counter=native_minus_fixed；调用者必须提供实际测量值，不估造 |
| 第一轮通过／索引非空资格筛选 | selection.require_prefix_pass / require_nonempty_index |
| 手工选定、更晚或轮内断点 | checkpoint kind=manual；断点恢复由环境适配器负责 |
| 单节点／字段删除早期试验 | `coarse_delete` / `coarse_project` |
| Delete-1 oldest/recent/largest | `delete-1-*`；同一完整交互删除函数 |
| Delete-2 / Delete-3 | `delete_two_interactions` / `delete_three_interactions`；保留至少一次交互 |
| 完整输出共享、子树共享、schema 共享 | `share_outputs` / `share_subtrees` / `share_schema` |
| 相邻重复读取／辅助字段／上下文字段／已解决错误 | `repeat_reads` / `ancillary_fields` / `trim_context` / `resolved_errors` |
| 数值摘要 v1/v2 | `numeric-summary-v1/v2`，同一模块按阈值和数字资格切换 |
| 跨观察共享并保护已知 ID | `share_observations` |
| GPT-4.1 / mini / Claude / Qwen | model.provider、name、sampling；工具格式仍由对应适配器提供 |
| Claude 旧 thinking 统一处理 | model.old_thinking=omit；源历史由调用者另行归档 |
| 单次／三次／十次与随机交错 | execution.repeats、order_seed + schedule()；每次采样 seed 可在该作业配置中指定 |

## 未冒充已完成的部分

- 此次测试的是离线表示与编辑、请求组装、接入和统计，不是所有任务的最终成功率。
- 各个实验的题目清单、种子清单、预算账本、失败重试和人工审查属于数据与执行策略，不嵌在图模块里。当前不自动导入/重启这些历史实验。
- selected-exchange ordering 接收显式已选交互，不包含旧实验的付费 selector/verifier。旧哈希锁定和临时修复不逐一移植；若研究它们，应新增适配器与配置，而不是复制 core。
- 公共 schema/工具契约仍由 BFCL 提供。官方评分不在 core 内实现，也不修改。
- `prepare` 的 `*_units` 是明确命名计数器的离线结果；首次 API 输入、累计输入/输出、缓存、工具调用由 `Usage` 统计。不能把 JSON 字符数当成计费 token。
- `paired()` 以题目＋断点哈希＋重复编号配对；新增工具调用同时报告净增量和逐题正增量。
- 费用用显式价格参数计算；没有硬编码当前价格，也没有把新的 token 数直接当作实际扣费。
