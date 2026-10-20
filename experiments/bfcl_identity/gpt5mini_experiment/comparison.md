# gpt-5-mini 与 Qwen3.8-27B 对照：图记忆基线

26 个条件（GorillaFileSystem 题族 × `multi_turn_base` / `multi_turn_long_context`，与 Qwen 基线同一批题），每种记忆每题跑一次。gpt-5-mini 全程生成，包括第一轮；两种图回放这段第一轮恢复模拟器，在第二轮用户消息之前把历史换成图。图的构建、替换时机和题目顺序与 Qwen 基线相同。官方 BFCL 整题评分，第一轮失败也计入。

实际服务模型：gpt-5-mini-2025-08-07。请求参数：`reasoning_effort` medium, `max_completion_tokens` 16384, `seed` 42。

## 汇总（gpt-5-mini 26 个条件；Qwen 26 个条件）

| 方法 | gpt-5-mini 通过 | gpt-5-mini 比例 | gpt-5-mini 整段平均输入 | Qwen 通过 | Qwen 比例 | Qwen 整段平均输入 |
| --- | --- | --- | --- | --- | --- | --- |
| Identity | 12/26 | 46.2% | 39,714 | 18/26 | 69.2% | 55,529 |
| State-Transition Graph | 9/26 | 34.6% | 50,554 | 14/26 | 53.8% | 77,791 |
| Event Graph | 9/26 | 34.6% | 56,860 | 17/26 | 65.4% | 89,784 |

整段输入 = 共用第一轮 + 该方法续跑，每次请求的 `prompt_tokens` 相加（含工具定义和缓存命中部分）。gpt-5-mini 用自己的 tokenizer 计数，Qwen 用 Qwen 的 tokenizer，两边 token 数只能看量级，不能逐个比较。

## 按切分

| 切分 | 方法 | gpt-5-mini 通过 | Qwen 通过 |
| --- | --- | --- | --- |
| `multi_turn_base` | Identity | 7/13 | 9/13 |
| `multi_turn_base` | State-Transition Graph | 6/13 | 8/13 |
| `multi_turn_base` | Event Graph | 6/13 | 9/13 |
| `multi_turn_long_context` | Identity | 5/13 | 9/13 |
| `multi_turn_long_context` | State-Transition Graph | 3/13 | 6/13 |
| `multi_turn_long_context` | Event Graph | 3/13 | 8/13 |

## 原文通过、换成图后失败的题

| 方法 | gpt-5-mini | Qwen |
| --- | --- | --- |
| State-Transition Graph | multi_turn_base_25, multi_turn_long_context_29, multi_turn_long_context_39 | multi_turn_base_1, multi_turn_long_context_1, multi_turn_long_context_9, multi_turn_long_context_10 |
| Event Graph | multi_turn_base_16, multi_turn_long_context_29, multi_turn_long_context_39 | multi_turn_base_1, multi_turn_long_context_9, multi_turn_long_context_10 |

反过来，原文失败、换成图后通过：
- State-Transition Graph：gpt-5-mini 无；Qwen 无
- Event Graph：gpt-5-mini 无；Qwen multi_turn_base_9, multi_turn_long_context_25

## 逐题

1 = 通过，0 = 失败。顺序是原文 / 状态转移图 / 事件图。

| 题目 | gpt-5-mini | Qwen | gpt-5-mini 第一轮 | gpt-5-mini 失败原因（图） |
| --- | --- | --- | --- | --- |
| multi_turn_base_1 | 1 / 1 / 1 | 1 / 0 / 0 | 通过 | - |
| multi_turn_base_3 | 1 / 1 / 1 | 1 / 1 / 1 | 通过 | - |
| multi_turn_base_6 | 0 / 0 / 0 | 0 / 0 / 0 | 通过 | State-Transition Graph: multi_turn:empty_turn_model_response; Event Graph: multi_turn:instance_state_mismatch |
| multi_turn_base_9 | 0 / 0 / 0 | 0 / 0 / 1 | 通过 | State-Transition Graph: multi_turn:execution_response_mismatch; Event Graph: multi_turn:execution_response_mismatch |
| multi_turn_base_10 | 0 / 0 / 0 | 0 / 0 / 0 | 失败 | State-Transition Graph: multi_turn:instance_state_mismatch; Event Graph: multi_turn:instance_state_mismatch |
| multi_turn_base_12 | 1 / 1 / 1 | 1 / 1 / 1 | 通过 | - |
| multi_turn_base_16 | 1 / 1 / 0 | 1 / 1 / 1 | 通过 | Event Graph: multi_turn:empty_turn_model_response |
| multi_turn_base_25 | 1 / 0 / 1 | 0 / 0 / 0 | 通过 | State-Transition Graph: multi_turn:empty_turn_model_response |
| multi_turn_base_26 | 0 / 0 / 0 | 1 / 1 / 1 | 通过 | State-Transition Graph: multi_turn:instance_state_mismatch; Event Graph: multi_turn:empty_turn_model_response |
| multi_turn_base_29 | 1 / 1 / 1 | 1 / 1 / 1 | 通过 | - |
| multi_turn_base_37 | 0 / 0 / 0 | 1 / 1 / 1 | 失败 | State-Transition Graph: multi_turn:execution_response_mismatch; Event Graph: multi_turn:execution_response_mismatch |
| multi_turn_base_38 | 1 / 1 / 1 | 1 / 1 / 1 | 通过 | - |
| multi_turn_base_39 | 0 / 0 / 0 | 1 / 1 / 1 | 通过 | State-Transition Graph: multi_turn:empty_turn_model_response; Event Graph: multi_turn:empty_turn_model_response |
| multi_turn_long_context_1 | 1 / 1 / 1 | 1 / 0 / 1 | 通过 | - |
| multi_turn_long_context_3 | 1 / 1 / 1 | 1 / 1 / 1 | 通过 | - |
| multi_turn_long_context_6 | 0 / 0 / 0 | 0 / 0 / 0 | 通过 | State-Transition Graph: multi_turn:instance_state_mismatch; Event Graph: multi_turn:empty_turn_model_response |
| multi_turn_long_context_9 | 0 / 0 / 0 | 1 / 0 / 0 | 通过 | State-Transition Graph: multi_turn:execution_response_mismatch; Event Graph: multi_turn:execution_response_mismatch |
| multi_turn_long_context_10 | 0 / 0 / 0 | 1 / 0 / 0 | 失败 | State-Transition Graph: multi_turn:force_terminated; Event Graph: multi_turn:force_terminated |
| multi_turn_long_context_12 | 1 / 1 / 1 | 1 / 1 / 1 | 通过 | - |
| multi_turn_long_context_16 | 0 / 0 / 0 | 1 / 1 / 1 | 失败 | State-Transition Graph: multi_turn:instance_state_mismatch; Event Graph: multi_turn:instance_state_mismatch |
| multi_turn_long_context_25 | 0 / 0 / 0 | 0 / 0 / 1 | 通过 | State-Transition Graph: multi_turn:execution_response_mismatch; Event Graph: multi_turn:empty_turn_model_response |
| multi_turn_long_context_26 | 0 / 0 / 0 | 0 / 0 / 0 | 通过 | State-Transition Graph: multi_turn:execution_response_mismatch; Event Graph: multi_turn:execution_response_mismatch |
| multi_turn_long_context_29 | 1 / 0 / 0 | 1 / 1 / 1 | 通过 | State-Transition Graph: multi_turn:empty_turn_model_response; Event Graph: multi_turn:empty_turn_model_response |
| multi_turn_long_context_37 | 0 / 0 / 0 | 1 / 1 / 1 | 失败 | State-Transition Graph: multi_turn:execution_response_mismatch; Event Graph: multi_turn:execution_response_mismatch |
| multi_turn_long_context_38 | 0 / 0 / 0 | 0 / 0 / 0 | 失败 | State-Transition Graph: multi_turn:instance_state_mismatch; Event Graph: multi_turn:instance_state_mismatch |
| multi_turn_long_context_39 | 1 / 0 / 0 | 1 / 1 / 1 | 通过 | State-Transition Graph: multi_turn:empty_turn_model_response; Event Graph: multi_turn:empty_turn_model_response |

## 用量

实际请求 816 次，输入 3,226,868 token（其中缓存命中 2,774,272），输出 140,063 token（其中推理 107,584）。 按牌价估算约 $0.46。
结束原因：{"tool_calls": 620, "stop": 196}。
