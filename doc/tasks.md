# 科研任务与结果

## 目的和主要功能

说明当前命令执行哪些研究计算、接收哪些输入以及交付哪些结果。

## 适用范围

用于图记忆准备、BFCL 轨迹、前缀、配对统计及多条件研究编排。

## 共有参数与运行记录

`--config` 指向 JSON 配方，`--output` 指向新目标。`prepare`、`run`、`batch` 和 `prefix-source` 省略输出时，在项目 `experiment/<命令>/<时间与唯一标识>/` 创建新位置。明确传入的输出路径继续沿用原有命令语义。新实验建议显式选择 `experiment/<实验用途>/<运行标识>/`。

`checkpoint` 选择手动、已完成轮次或历史大小接入；历史大小判断由具体配方指定计数方式和严格比较条件。共享前缀与配对报告依据保存的接入点身份关联。

| 命令 | 负责位置 | 输入与结果 |
| --- | --- | --- |
| `list` | `src/cs769/cli.py` | 列出构图器、编辑与 `conf/` 配方。 |
| `validate` | `base/config.py` | 加载、合并并返回生效配置。 |
| `prepare` | `tasks/memory.py` | 读取历史并执行构图、编辑、投喂，保存配置、消息、图、文本和结果。 |
| `run` | `tasks/run.py`、`tasks/bfcl.py` | 按题目、类别、模型及可选前缀执行轨迹，保存请求、预算、记忆与官方评分。 |
| `replay` | `tasks/replay.py` | 检查保存请求，重建工具结果并对照图文本和官方分数。 |
| `score` | `tasks/bfcl.py` | 将保存的工具调用结果交给官方评分。 |
| `prefix-source` | `tasks/prefix.py` | 重建指定完成轮次的前缀，保存轨迹及官方资格结果。 |
| `inspect-prefix` | `tasks/prefix.py` | 从已保存前缀计算图编辑适用情况和大小收益。 |
| `boundary` | `tasks/bfcl.py` | 回放到前缀之后的下一个请求，输出指定 JSON 文件。 |
| `batch` | `base/batch.py` | 按显式计划隔离轨迹进程，保存计划、批次状态和各条件记录。 |
| `report` | `tasks/reporting.py`、`base/metrics.py` | 读取行或批次，按模型分别汇总匹配样本、官方通过、token 和工具调用。 |
| `campaign` | `tasks/campaign.py` | 按已有研究配置安排前缀筛选、条件执行与结果交接。 |

`tasks/projection_campaign.py` 保留原有配置驱动的字段投影研究接口，使用同一命令入口、前缀和结果语义。

## 正常操作示例

从项目根执行；下面命令保留原始配方语义。

```bash
PYTHONPATH=src python -B -m cs769 list
PYTHONPATH=src python -B -m cs769 validate conf/evidence_graph_history_threshold.json
PYTHONPATH=src python -B -m cs769 prepare --config conf/evidence_graph_history_threshold.json --history src/cs769/examples/history.json --counter characters
```

最后一条命令省略输出位置时，新结果归 `experiment/prepare/`。`characters` 的数值单位为字符，API token 以原始 usage 为准。使用已有模型计数环境时可保留默认 `o200k_base`。

## 结果读取

新 `run` 的 `manifest.json` 保存状态、任务、模型、实际配置、源码身份和用量；`config.json` 保存生效配置；`api.json` / `api.jsonl` 保存请求与回复；`full.json` 保存工具结果；`score.json` 保存官方评分；`events.jsonl`、`memory-graph.json`、`memory.txt`、`edit-audit.json` 按实际发生的接入写入。预算账本记录已结算和未确定的请求预留。

批次先读 `manifest.json` 和 `plan.json`，再按条件目录读取记录。配对统计使用同任务、同接入点、同重复的两组结果；未完成及未触发接入的条件由报告单列。

## 运行条件

`run` 沿用既有 API 授权、正数预算、私有凭证及单价要求。回放与官方评分需要既有固定 BFCL 环境。测试入口继续为 `tests/run.py`；本次整理保留已有测试及本机修改，实验运行与测试按用户指定范围执行。
