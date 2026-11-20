# 数据集与输入

## 目的和主要功能

说明固定 BFCL 题目、官方答案和历史轨迹如何交给图记忆任务。

## 适用范围

用于当前 BFCL 执行、评分、保存轨迹回放、前缀选择和离线历史准备。

## 共有输入参数

| 参数 | 含义与规则 |
| --- | --- |
| `task` / `--task` | 官方题目标识；按完整标识在给定类别中读取题目。 |
| `category` / `--category` | 官方数据类别，例如 `multi_turn_base`；类别和题目标识共同选择样本。 |
| `turn_limit` / `--turns` | 已完成用户轮次的正整数；最大为该题实际轮数。前缀选择同步截取题目和答案。 |
| `--history` | 离线准备的 JSON 消息列表，支持规范化聊天记录和已有 Responses 工具交换。 |
| `--native-history`、`--context`、`--next-messages` | 可选原生历史、原生上下文和接入点之后的新用户消息；工具调用与返回需要配对。 |
| `--record`、`--source`、`--api` | 保存的轨迹目录、共享前缀目录或请求回复文件，按各任务的真实接口传入。 |

命令行相对文件路径从当前命令目录起算。中央 `{data:名称}` 可展开为本机路径再传给已有参数。固定 BFCL 使用项目内的 vendor，路径由项目位置确定。

## 固定 BFCL 多轮工具数据

负责位置为 `datasets/bfcl.py`。`load_entry` 读取题目，`load_truth` 读取官方答案，`limited_entry` 保留给定轮数的题目前缀。实际数据和工具实现来自 `vendor/gorilla/berkeley-function-call-leaderboard/bfcl_eval/`。

`base/bootstrap.py` 选择当前项目固定的 BFCL；`tasks/bfcl.py` 取得输入，交给官方处理器执行工具与推进轮次，再调用原有官方评分。每条轨迹使用独立进程，批量任务由 `base/batch.py` 分发。

## 保存的轨迹和前缀

轨迹目录中的 `manifest.json` 定位任务、类别、模型、配置及状态，`api.json` 保存请求与回复，`full.json` 保存工具调用结果，`score.json` 保存官方评分。`tasks/prefix.py` 从指定来源重建前缀；`tasks/replay.py` 逐项比较请求并重建结果。

## 离线历史样例

`src/cs769/examples/history.json` 供 `prepare` 直接读取。历史消息规范化和接入点判断归 `base/history.py`；构图归 `models/`。样例用途为准备输入和阅读流程。

## 历史资料位置

`experiments/bfcl_identity/` 保存历史实验及报告，`source_code/` 为冻结源码。原有文件、缺失状态及历史读取方式沿用迁移前情况。`visualization/` 使用现有回放材料。新产物使用项目一级目录 `experiment/`。
