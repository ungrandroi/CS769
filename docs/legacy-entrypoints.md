> 后续更新：本文保留迁移前说明原文，仅供历史参考。这里列出的 workflows 模块和旧命令现已删除，请使用 [当前运行说明](runtime.md)。

# 迁移前入口说明（历史记录）

下文保留原说明和参数，供核对；其中独立运行命令已退役，当前入口见 runtime.md。

# 实验入口

统一命令：`scripts/bfcl_python.sh scripts/manage.py ...`

```text
scripts/
  manage.py                  唯一实验命令入口
  bfcl_python.sh             conda 环境启动器
  core/                      图记忆、编码、传输、评分和公共调度
  workflows/                 三种协议的运行、检查点、核验与报告
  local_qwen_tokenizer.py     可视化旧导入兼容入口
  qwen_prompt_accounting.py  可视化旧导入兼容入口
```

## 方法名称

| 名称 | 核心文件 | 历史 ID |
|---|---|---|
| Identity | 普通历史直传 | `identity` |
| State-Transition Graph | `core/state_transition_graph.py` | `v1-compact` |
| Event Graph | `core/event_graph.py` | `v2-compact` |
| Event Graph-Dedup | `core/event_graph_dedup.py` | `v2-dedup` |
| Event Graph Readable | `core/graph_memory_readable.py` | `v2-readable` |

名称由 `core/research_modes.py` 统一管理。两个图方法使用 Compact 编码；Event Graph-Dedup 对来源关系无损去重，不合并实际工具调用。历史 ID 和冻结目录保持不变。单任务 `--mode` 支持上述名称（含空格时加引号）。

## 常用命令

```bash
# 命令帮助
scripts/bfcl_python.sh scripts/manage.py --help

# 准备纯1000-token检查点，不调用模型
scripts/bfcl_python.sh scripts/manage.py checkpoints

# 只准备一个新批次，不调用模型
scripts/bfcl_python.sh scripts/manage.py run history1000 --prepare-only --output /tmp/history-check

# 实际批量运行，需要先启动本地模型服务
scripts/bfcl_python.sh scripts/manage.py run history1000

# 使用冻结源码核验已有实验，不调用模型
scripts/bfcl_python.sh scripts/manage.py audit baseline
scripts/bfcl_python.sh scripts/manage.py audit dedup

# 来源去重离线编码研究、统一名称报告
scripts/bfcl_python.sh scripts/manage.py probe dedup
scripts/bfcl_python.sh scripts/manage.py reports
```

协议名称是 `baseline`（首轮后转换）、`dedup`（来源去重续跑）、`history1000`（历史长度触发），与方法名称分开。`run`、`audit` 和内部 `task` 子命令均支持这三种协议；`bfcl` 子命令转交官方评分 CLI。

公共调度器保证同一任务的不同方法使用同一服务，并拒绝自动重试或覆盖未完成尝试。已完成批次不会自动重跑。源码与新实验配置一同冻结。

历史审核使用各批次冻结源码，而非当前模块；重建报告写入 `experiments/bfcl_identity/reports/audits/`，不覆盖原始记录。

`visualization/` 代码不改动；两个兼容导入文件仍有用途，不应删除。

测试：

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=scripts scripts/bfcl_python.sh -m unittest discover -s tests -p 'test_*.py'
```

## V2 readable：两个 GPT 的完整证据对照

`v2-readable` 沿用 Event Graph 的构建与状态更新规则。图和原始 source messages 完整保存；模型输入改为简短 CURRENT STATE 加完整 HISTORY，按原顺序保留可见文本、原工具参数和返回，使用 CALL/RESULT 编号配对。状态使用目录分组和可核验的原返回引用。没有风险评分、证据删除、长度截断，也没有新增行为指令。审计字段保留在图文件中，不重复送入模型。

三个正式方法为 `identity`、`v2-compact`、`v2-readable`。GPT-4.1 跑 base_3、long_context_3 和两个控制题；GPT-5-mini 跑 base_16、long_context_29、long_context_39 和相同控制题 base_12、long_context_12。每组用 seed 42/43/44，共 81 条续跑；所有方法回放对应模型的同一冻结首轮。GPT-4.1 temperature=0；GPT-5-mini reasoning_effort=medium，不传 temperature。重复用于检查复现性，不视为独立题目。

正式评分沿用 BFCL。仅在本轮 identity 至少 2/3、compact 至多 1/3 的非控制条件中统计恢复率；readable 至少 2/3 视为恢复。控制题与本轮 identity 比较。开发探针、同族题和其他退化题分别标记，不将小样本诊断解释为整体 BFCL 改进。

以下命令使用已安装 BFCL 及依赖的 Python；ins04 本次隔离环境为 `.conda/readable/bin/python`，并通过 `PYTHONPATH=scripts:vendor/gorilla/berkeley-function-call-leaderboard` 固定项目内 BFCL 源码。

```bash
# 离线证据完整性和四部分 token 拆账，包括九个归档 history1000 检查点
python scripts/manage.py audit readable --output /path/to/new-audit
# 两个决策点的六种表示；准备阶段不调用 API
python scripts/manage.py probe readable --prepare-only --output /path/to/new-probes
# 81 条正式续跑计划；准备阶段不调用 API
python scripts/manage.py run readable --prepare-only --output /path/to/new-pilot
# 顺序执行离线审计、探针、冻结记录、正式续跑；应在服务器独立后台会话中运行
python -m workflows.readable_run --output /path/to/new-pipeline
```

每个结果目录保存请求、响应、源码快照、配置、进度和官方评分。出现基础设施错误即保留现场，不自动覆盖或按失败结果重采样。缓存 token 仍计入上下文；reasoning token 属于输出，不重复相加。新费用只计算实际续跑；等价全轨迹统计将冻结首轮加一次。

探针是下一步动作诊断，不执行工具、不算任务成功率。相同请求复用响应并单独记账；当前计划 126 条样本记录、115 个唯一 API 请求。原生多消息变体如需编号映射会显式记录额外开销；它同时改变角色和包装，不能单独归因于角色。格式在获取新模型结果前固定，探针用于解释，不隐式调参。

设计参考 AriGraph 的语义事实与情景证据分层、Graphiti/Zep 的时序事实与来源关联。此处只借鉴保留证据和状态索引的组织方式，未复现其检索策略，也未将其论文结果当成本项目的效果证据。
