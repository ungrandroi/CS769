# 模型与图记忆方法

## 目的和主要功能

说明图记忆构造、独立编辑、模型提供方和现有配方的选择关系。

## 适用范围

用于当前输入准备、图记忆实验、原生模型传输和组件扩展。

## 共有配置参数

| 参数 | 含义与默认处理 |
| --- | --- |
| `memory.kind`、`memory.options` | 选择已登记构图器及专用参数；专用参数由构图器检查。 |
| `edits` | 有序编辑列表。每项包含 `name`、`enabled`、`options`、`on_ineligible`；默认列表为空。 |
| `delivery.mode` | `replace` 替换旧历史；`native` 使用 identity；历史配方还支持 `append` 和 `prepend_user`。 |
| `delivery.role` | 替换记忆的承载角色，默认 `user`，可选 `assistant`。 |
| `model.provider`、`model.name` | 提供方为 `openai`、`anthropic` 或 `qwen`；模型名称沿具体配方传入。 |
| `model.sampling` | 请求采样参数；继承时整体替换。采用推理强度的配方省去 temperature。 |
| `model.old_thinking` | `omit` 或 `preserve`；带签名的思考块按原生消息约束处理。 |

配置从 `conf/` 读取 JSON。`extends` 相对当前配置文件解析；普通字典递归合并，`sampling` 和 `checkpoint` 整体替换。`ExperimentConfig` 最后填入缺省字段并检查组合。代码依据为 `base/config.py`。

## 图记忆构造

证据图（evidence graph）是本项目的正式方法名称。公开构图入口为 `build_evidence_graph_memory`，配置选择使用 `memory.kind=evidence_graph`。原编号仅用于读取早期格式和历史结果。

| 方法名称 | 原有构图标识 | 功能、输入与交付 |
| --- | --- | --- |
| 原始历史对照 | `identity` | 保留原生消息，配合 `native` 投喂，作为对照。 |
| 原生历史索引与可读历史 | `native_index`、`readable` | 从历史形成原生索引或可读表示，支持显式历史投喂方式。 |
| 基础交互证据层 | `evidence` | 从历史和原生上下文构造证据图，保留来源与构图审计。 |
| 证据图与分层构造 | `evidence_graph`、`layered` | 在证据图上选择观测、载荷、锚点或记录层及呈现方式；默认记录层。 |
| 事件与状态转换图 | `semantic` | 选择事件图、状态转换图或去重事件图，以及 filesystem / mixed 语义和编码方式。 |

证据图将用户请求、工具调用、返回结果和助手陈述组织为可追溯记录，并通过具有相同类型的标识符连接相关记录。分层证据图支持选择锚点、观测、载荷或记录层。

构图登记在 `models/builders.py`，具体表示归 `models/graphs/`。构图结果包含图、呈现函数和审计数据；`tasks/memory.py` 组合编辑和投喂，交付 `graph`、`memory_text`、`messages`、`edits` 和大小统计。公开调用继续使用 `cs769.models.evidence_graph_memory.build_evidence_graph_memory`，实现归 `models/evidence_graph_memory.py`。

## 图编辑

`models/editing.py` 登记统一接口，`models/edits/` 保存删除、数字摘要、观察与结构共享、字段裁剪、状态收缩和依赖选择等具体实现。调用顺序采用 `edits` 配置顺序。操作需要证据图；未满足条件时按 `on_ineligible` 的 `error` 或 `skip` 处理，逐项保存审计。

`delete_interactions` 支持删除一至三个完整交互及 oldest、recent、largest、id_linked 选择；`numeric_summary` 由 `min_elements`、`tail_elements` 和 `eligibility` 控制数组摘要。其他编辑的参数由各实现的 `options` 检查及具体配方确定。

## 模型提供方与分词

`models/provider.py` 转换官方处理器请求；`models/http.py` 读取显式提供的私有凭证并执行请求；`base/budget.py` 保存共享预算预留和结算。Anthropic 原生块处理归 `models/anthropic_transport.py`，Qwen 消息转换和文本计数归相应 `qwen_*.py` 及 `local_qwen_tokenizer.py`。

`o200k_base` 用于当前离线文本计数；`characters` 用于结构操作中的字符计数。原生 Qwen 计数依赖既有 GGUF 和匹配的原生库，所需文件按原环境说明提供。

## 按用途选择配方

下表的名称说明配方的实际用途，点击名称打开对应配置。配置文件名、构图标识和语言模型正式名称沿用既有接口原名。

| 配方名称 |
| --- |
| [上下文字段裁剪](../conf/trim_context.json) |
| [事件图的历史编码](../conf/event_legacy.json) |
| [事件图的原始编码](../conf/event_original.json) |
| [事件图的表格编码](../conf/event_table_encoding.json) |
| [交互证据图](../conf/interaction_evidence_graph.json) |
| [仅保留出现位置的交互证据图](../conf/evidence_occurrences_only.json) |
| [仅保留观测节点的图](../conf/observation_nodes_only.json) |
| [以助手角色投喂的可读历史](../conf/readable_history_assistant_role.json) |
| [以助手角色投喂的完整证据图](../conf/complete_evidence_assistant_role.json) |
| [以用户角色投喂的可读历史](../conf/readable_history_user_role.json) |
| [使用词项引用的证据图](../conf/evidence_graph_lexical_references.json) |
| [保持时间顺序的证据图](../conf/evidence_graph_chronological_order.json) |
| [保留历史用户角色的证据图](../conf/evidence_graph_historical_user_role.json) |
| [全部交互由助手角色承载的记录图](../conf/evidence_graph_assistant_role.json) |
| [关系就近呈现的完整证据图](../conf/complete_evidence_local_relations.json) |
| [关联交互优先的证据图](../conf/evidence_graph_related_exchanges_first.json) |
| [内容集中存储的证据图](../conf/evidence_graph_content_store.json) |
| [删除三个交互](../conf/delete_three_interactions.json) |
| [删除两个交互](../conf/delete_two_interactions.json) |
| [删除最早的一个交互](../conf/delete_oldest_interaction.json) |
| [删除最近的一个交互](../conf/delete_recent_interaction.json) |
| [删除节省最多的一个交互](../conf/delete_largest_interaction.json) |
| [包含可见性信息的证据图](../conf/evidence_graph_visibility.json) |
| [包含实体来源的完整证据图](../conf/complete_evidence_entity_origin.json) |
| [历史长度触发的事件图](../conf/event_working_history.json) |
| [历史长度触发的证据图](../conf/evidence_graph_history_threshold.json) |
| [原始历史对照](../conf/identity.json) |
| [原生历史索引](../conf/native_history_index.json) |
| [去重事件图的历史编码](../conf/event_dedup_legacy.json) |
| [去重事件图的原始编码](../conf/event_dedup_original.json) |
| [去重事件图的表格编码](../conf/deduplicated_event_table_encoding.json) |
| [多工具领域事件图的原始编码](../conf/event_mixed_original.json) |
| [多工具领域事件图的表格编码](../conf/mixed_domain_event_table_encoding.json) |
| [多工具领域去重事件图的原始编码](../conf/event_dedup_mixed_original.json) |
| [多工具领域去重事件图的表格编码](../conf/mixed_domain_deduplicated_event_table_encoding.json) |
| [多工具领域状态转换图的原始编码](../conf/state_mixed_original.json) |
| [多工具领域状态转换图的表格编码](../conf/mixed_domain_state_table_encoding.json) |
| [完整证据图](../conf/complete_evidence_graph.json) |
| [证据图的基础视图](../conf/evidence_graph_base_view.json) |
| [证据图的完整视图](../conf/evidence_graph_full_view.json) |
| [证据图的节点视图](../conf/evidence_graph_nodes_view.json) |
| [已解决错误裁剪](../conf/resolved_errors.json) |
| [带共享锚点的交互证据图](../conf/evidence_shared_anchors.json) |
| [按事件分块的证据图](../conf/evidence_graph_event_blocks.json) |
| [按字段组织的观测图](../conf/observation_fields.json) |
| [按工具交换分块的交互记录图](../conf/evidence_graph_exchange_blocks.json) |
| [按调用签名呈现的证据图](../conf/evidence_graph_call_signatures.json) |
| [按载荷地址组织的观测图](../conf/payload_addresses.json) |
| [整段交互删除](../conf/coarse_delete.json) |
| [整段交互投影](../conf/coarse_project.json) |
| [状态转换图的历史编码](../conf/state_legacy.json) |
| [状态转换图的原始编码](../conf/state_original.json) |
| [状态转换图的表格编码](../conf/state_table_encoding.json) |
| [用于 Claude Sonnet 的证据图](../conf/evidence_graph_claude.json) |
| [使用 GPT-5-mini 的证据图](../conf/evidence_graph_openai_mini.json) |
| [用于本机 Qwen 的证据图](../conf/evidence_graph_local_qwen.json) |
| [结构优先的交互证据图](../conf/interaction_evidence_structure_first.json) |
| [结构优先的完整证据图](../conf/complete_evidence_structure_first.json) |
| [至少一百二十八项的小数数组摘要](../conf/summarize_decimal_arrays.json) |
| [至少两百五十六项的非整数数组摘要](../conf/summarize_noninteger_arrays.json) |
| [记录内容内联的证据图](../conf/evidence_graph_inline_payloads.json) |
| [记录内容外置的证据图](../conf/evidence_graph_external_payloads.json) |
| [选定交互优先的证据图](../conf/evidence_graph_selected_exchanges_first.json) |
| [重复子树共享](../conf/share_subtrees.json) |
| [重复字段结构共享](../conf/share_schema.json) |
| [重复观测共享](../conf/share_observations.json) |
| [重复读取裁剪](../conf/repeat_reads.json) |
| [重复输出共享](../conf/share_outputs.json) |
| [附在新用户消息前的应用记忆](../conf/memory_before_user_request.json) |
| [附属字段裁剪](../conf/ancillary_fields.json) |
