# 当前目录与直接调用关系

## 目的和主要功能

说明活动实现由谁负责，以及正常命令怎样取得输入并交付结果。

## 适用范围

用于本项目的日常维护。历史运行与冻结源码按各自保存的原始位置读取。

## 目录职责

| 位置 | 当前职责 |
| --- | --- |
| `base/` | 配置、路径、历史、会话、请求、预算、批量进程和源码身份。 |
| `datasets/` | 固定评测题目、答案与轮次前缀。 |
| `models/` | 构图、编辑、提供方转换、模型传输和分词。 |
| `tasks/` | 记忆准备、工具轨迹、回放、前缀、报告和研究编排。 |
| `conf/` | 当前具名配方，按实际用途命名。 |
| `src/cs769/` | 命令、公开包入口、历史快照工具与原有配套资料。 |
| `scripts/` | 现有人工启动命令，以及可视化实际使用的两个模型工具入口。 |
| `tests/` | 直接检查正式实现及命令行为。 |
| `doc/` | 当前组件说明；方法和历史迁移资料继续归 `docs/`。 |
| `experiment/` | 新运行的配置、状态、日志和结果。 |
| `experiments/` | 原有实验记录、报告和冻结源码。 |
| `visualization/` | 用户维护的记忆回放界面。 |
| `vendor/`、`acon-history-compression/` | 已有第三方依赖和外部材料。 |

## 正常调用

`python -m cs769` 与 `scripts/manage.py` 使用同一命令入口。命令读取请求，再直接调用 `base/`、`datasets/`、`models/` 和 `tasks/` 的负责模块。

记忆准备由 `tasks/memory.py` 统一完成构图、投喂和文件交付。结果读取、独占创建与原子更新集中在 `base/io.py`；任务仍负责结果的研究含义和保存时机。

项目内代码直接使用当前命名空间。例如：

```python
from cs769.base.config import load_config
from cs769.models.evidence_graph_memory import build_evidence_graph_memory
from cs769.tasks.memory import prepare
```

公开包入口继续提供 `from cs769 import ExperimentConfig, load_config, prepare`。内部导入统一到实际负责模块，调用者与测试共同使用这一实现。

## 配方与产物

`src/cs769/configs` 通过相对链接读取 `conf/`，配置集合集中维护。常用历史长度配方为 `conf/evidence_graph_history_threshold.json`。配置文件内的历史方法标识和结果格式保持原义。

新运行默认归项目一级目录 `experiment/`，每次运行保存实际配置及结果。历史文件保持原始位置与读取含义。

## 历史读取与可视化

`src/cs769/adapters/` 保留已有冻结源码读取、历史方法名称和旧运行辅助实现。它们承担实际功能。当前图、编辑、模型传输和预算直接使用职责目录。

可视化现有调用需要 `scripts/local_qwen_tokenizer.py` 与 `scripts/qwen_prompt_accounting.py`，这两个入口直接导入 `models/`。用户维护的可视化实现与数据保持原状。

组件和参数见 [数据与输入](datasets.md)、[模型与配方](models.md)、[科研任务](tasks.md)。
