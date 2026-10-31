# 实验入口

## G9 构图与渲染（离线使用）

无需运行实验 CLI：[接入说明](../docs/g9-memory.md)、
[build_g9_memory](core/g9_memory.py)、[最小示例](../examples/g9_memory.py)。
`PYTHONPATH=scripts python3 examples/g9_memory.py` 可从仓库根目录运行，不调用模型。
G5 的 `build_evidence_graph` 在 [graph_memory_evidence.py](core/graph_memory_evidence.py)。
该入口明确选择已报告的 G9 full-view 设置，保留完整可见证据，不附带 identity 历史。

## 既有实验 CLI

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
