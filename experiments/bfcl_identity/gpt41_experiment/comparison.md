# gpt-4.1 与 Qwen3.8-27B 对照：图记忆基线

26 个条件（GorillaFileSystem 题族 × `multi_turn_base` / `multi_turn_long_context`，与 Qwen 基线同一批题），每种记忆每题跑一次。gpt-4.1 全程生成，包括第一轮；两种图回放这段第一轮恢复模拟器，在第二轮用户消息之前把历史换成图。图的构建、替换时机和题目顺序与 Qwen 基线相同。官方 BFCL 整题评分，第一轮失败也计入。

实际服务模型：gpt-4.1-2025-04-14。请求参数：`temperature` 0, `seed` 42, `max_tokens` 4096。

## 汇总（gpt-4.1 26 个条件；Qwen 26 个条件）

| 方法 | gpt-4.1 通过 | gpt-4.1 比例 | gpt-4.1 整段平均输入 | Qwen 通过 | Qwen 比例 | Qwen 整段平均输入 |
| --- | --- | --- | --- | --- | --- | --- |
| Identity | 13/26 | 50.0% | 31,460 | 18/26 | 69.2% | 55,529 |
| State-Transition Graph | 10/26 | 38.5% | 38,786 | 14/26 | 53.8% | 77,791 |
| Event Graph | 11/26 | 42.3% | 43,408 | 17/26 | 65.4% | 89,784 |

整段输入 = 共用第一轮 + 该方法续跑，每次请求的 `prompt_tokens` 相加（含工具定义和缓存命中部分）。gpt-4.1 用自己的 tokenizer 计数，Qwen 用 Qwen 的 tokenizer，两边 token 数只能看量级，不能逐个比较。

## 按切分

| 切分 | 方法 | gpt-4.1 通过 | Qwen 通过 |
| --- | --- | --- | --- |
| `multi_turn_base` | Identity | 7/13 | 9/13 |
| `multi_turn_base` | State-Transition Graph | 6/13 | 8/13 |
| `multi_turn_base` | Event Graph | 6/13 | 9/13 |
| `multi_turn_long_context` | Identity | 6/13 | 9/13 |
| `multi_turn_long_context` | State-Transition Graph | 4/13 | 6/13 |
| `multi_turn_long_context` | Event Graph | 5/13 | 8/13 |

## 原文通过、换成图后失败的题

| 方法 | gpt-4.1 | Qwen |
| --- | --- | --- |
| State-Transition Graph | multi_turn_base_3, multi_turn_long_context_3, multi_turn_long_context_37 | multi_turn_base_1, multi_turn_long_context_1, multi_turn_long_context_9, multi_turn_long_context_10 |
| Event Graph | multi_turn_base_3, multi_turn_long_context_3 | multi_turn_base_1, multi_turn_long_context_9, multi_turn_long_context_10 |

反过来，原文失败、换成图后通过：
- State-Transition Graph：gpt-4.1 无；Qwen 无
- Event Graph：gpt-4.1 无；Qwen multi_turn_base_9, multi_turn_long_context_25

## 逐题

1 = 通过，0 = 失败。顺序是原文 / 状态转移图 / 事件图。

| 题目 | gpt-4.1 | Qwen | gpt-4.1 第一轮 | gpt-4.1 失败原因（图） |
| --- | --- | --- | --- | --- |
| multi_turn_base_1 | 1 / 1 / 1 | 1 / 0 / 0 | 通过 | - |
| multi_turn_base_3 | 1 / 0 / 0 | 1 / 1 / 1 | 通过 | State-Transition Graph: multi_turn:instance_state_mismatch; Event Graph: multi_turn:instance_state_mismatch |
| multi_turn_base_6 | 0 / 0 / 0 | 0 / 0 / 0 | 失败 | State-Transition Graph: multi_turn:instance_state_mismatch; Event Graph: multi_turn:instance_state_mismatch |
| multi_turn_base_9 | 0 / 0 / 0 | 0 / 0 / 1 | 通过 | State-Transition Graph: multi_turn:execution_response_mismatch; Event Graph: multi_turn:execution_response_mismatch |
| multi_turn_base_10 | 0 / 0 / 0 | 0 / 0 / 0 | 失败 | State-Transition Graph: multi_turn:instance_state_mismatch; Event Graph: multi_turn:force_terminated |
| multi_turn_base_12 | 1 / 1 / 1 | 1 / 1 / 1 | 通过 | - |
| multi_turn_base_16 | 0 / 0 / 0 | 1 / 1 / 1 | 失败 | State-Transition Graph: multi_turn:execution_response_mismatch; Event Graph: multi_turn:execution_response_mismatch |
| multi_turn_base_25 | 0 / 0 / 0 | 0 / 0 / 0 | 通过 | State-Transition Graph: multi_turn:execution_response_mismatch; Event Graph: multi_turn:execution_response_mismatch |
| multi_turn_base_26 | 1 / 1 / 1 | 1 / 1 / 1 | 通过 | - |
| multi_turn_base_29 | 1 / 1 / 1 | 1 / 1 / 1 | 通过 | - |
| multi_turn_base_37 | 0 / 0 / 0 | 1 / 1 / 1 | 失败 | State-Transition Graph: multi_turn:execution_response_mismatch; Event Graph: multi_turn:execution_response_mismatch |
| multi_turn_base_38 | 1 / 1 / 1 | 1 / 1 / 1 | 通过 | - |
| multi_turn_base_39 | 1 / 1 / 1 | 1 / 1 / 1 | 通过 | - |
| multi_turn_long_context_1 | 1 / 1 / 1 | 1 / 0 / 1 | 通过 | - |
| multi_turn_long_context_3 | 1 / 0 / 0 | 1 / 1 / 1 | 通过 | State-Transition Graph: multi_turn:instance_state_mismatch; Event Graph: multi_turn:instance_state_mismatch |
| multi_turn_long_context_6 | 0 / 0 / 0 | 0 / 0 / 0 | 失败 | State-Transition Graph: multi_turn:instance_state_mismatch; Event Graph: multi_turn:instance_state_mismatch |
| multi_turn_long_context_9 | 0 / 0 / 0 | 1 / 0 / 0 | 失败 | State-Transition Graph: multi_turn:execution_response_mismatch; Event Graph: multi_turn:execution_response_mismatch |
| multi_turn_long_context_10 | 0 / 0 / 0 | 1 / 0 / 0 | 失败 | State-Transition Graph: multi_turn:force_terminated; Event Graph: multi_turn:force_terminated |
| multi_turn_long_context_12 | 1 / 1 / 1 | 1 / 1 / 1 | 通过 | - |
| multi_turn_long_context_16 | 1 / 1 / 1 | 1 / 1 / 1 | 通过 | - |
| multi_turn_long_context_25 | 0 / 0 / 0 | 0 / 0 / 1 | 通过 | State-Transition Graph: multi_turn:execution_response_mismatch; Event Graph: multi_turn:execution_response_mismatch |
| multi_turn_long_context_26 | 0 / 0 / 0 | 0 / 0 / 0 | 通过 | State-Transition Graph: multi_turn:execution_response_mismatch; Event Graph: multi_turn:execution_response_mismatch |
| multi_turn_long_context_29 | 0 / 0 / 0 | 1 / 1 / 1 | 通过 | State-Transition Graph: multi_turn:instance_state_mismatch; Event Graph: multi_turn:instance_state_mismatch |
| multi_turn_long_context_37 | 1 / 0 / 1 | 1 / 1 / 1 | 通过 | State-Transition Graph: multi_turn:instance_state_mismatch |
| multi_turn_long_context_38 | 0 / 0 / 0 | 0 / 0 / 0 | 失败 | State-Transition Graph: multi_turn:instance_state_mismatch; Event Graph: multi_turn:instance_state_mismatch |
| multi_turn_long_context_39 | 1 / 1 / 1 | 1 / 1 / 1 | 通过 | - |

## 用量

实际请求 711 次，输入 2,537,365 token（其中缓存命中 2,079,872），输出 23,302 token（其中推理 0）。 按牌价估算约 $2.14。
结束原因：{"tool_calls": 515, "stop": 196}。
