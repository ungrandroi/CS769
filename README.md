# CS769 — Graph Memory for Tool-Using Agents

BFCL 文件操作场景下的图记忆研究。被测模型为本地 Qwen3.8-27B-Q8_0；数据来自 `multi_turn_base` 和 `multi_turn_long_context`，共 13 个任务家族 × 2 种条件。工具是 GorillaFileSystem 的 18 个模拟文件工具，不是真实 Bash。

## 记忆方法

| 方法 | 历史 ID | 说明 |
|---|---|---|
| 原始历史记忆 / Identity | `identity` | 保留原始消息历史 |
| 状态转移图记忆 · Compact / State Graph | `v1-compact` | 状态快照节点与工具调用转移边 |
| 事件图记忆 · Compact / Event Graph | `v2-compact` | 执行事件、共享对象和版本化事实 |
| 事件图记忆 · 来源去重版 / Event Graph–Dedup | `v2-dedup` | 无损去重重复来源关系，不合并实际调用 |

## 实验与代码

- `scripts/`：实验运行、图构建和编码、评分、校验与测试。
- `experiments/bfcl_identity/qwen27b_experiment/`：首轮后替换历史的完整 26 项 × 三方法基线。官方通过数分别为 18/26、14/26、17/26。
- `experiments/bfcl_identity/v2_provenance_dedup_probe/`：事件图来源去重离线验证。
- `experiments/bfcl_identity/qwen27b_dedup_eval/`：来源去重版的 26 项实际续跑，官方通过 15/26。
- `experiments/bfcl_identity/history1000_eval/`：仅按调用与返回内容累计 1000 tokens 触发的检查点。当前为 **prepared_not_run**：9 项触发、17 项未触发，尚无新评分。
- `experiments/bfcl_identity/reports/`：统一展示名称的报告；原始记录使用历史 ID。
- `visualization/`：用户维护的记忆回放界面，包含源代码和可直接打开的 `index.html`。
- `workflow_graph_memory_research_proposal.md`：研究提案。

各方法每项只运行一次；这些结果不是重复试验的统计估计。Compact 是相对完整图的紧凑编码，不保证比原始历史短。已实现图构建和编码，尚未实现可学习压缩器或风险模型。

## 获取与环境

```bash
git clone --recurse-submodules https://github.com/ungrandroi/CS769.git
cd CS769
```

`vendor/gorilla` 固定到原实验使用的上游提交。Python 环境的精确记录位于 `experiments/bfcl_identity/conda-explicit.txt` 和 `requirements.lock.txt`。例如在兼容的 Linux 平台恢复：

```bash
conda create --prefix "$PWD/.conda/bfcl" --file experiments/bfcl_identity/conda-explicit.txt
scripts/bfcl_python.sh -m pip install -r experiments/bfcl_identity/requirements.lock.txt
```

锁文件、冻结脚本和运行配置可能包含原机器的绝对路径，迁移机器时需要调整。BFCL 源代码位于子模块的 `berkeley-function-call-leaderboard/`；本地 editable 安装按该项目说明配置。

模型权重、模型服务二进制、conda 环境及本机 tokenizer 动态库不提交。精确 tokenizer 的版本和 SHA-256 记录在 `vendor/qwen-tokenizer-631109b34/`；需要恢复匹配的动态库与 GGUF 路径后，才能进行精确 token 计数与完整校验。推理服务设置见各实验的 `runtime/`。本仓库不包含 API 凭据。

详细运行入口见 [实验使用说明](experiments/bfcl_identity/USAGE.txt)，协议状态见 [ACTIVE_SCOPE](experiments/bfcl_identity/ACTIVE_SCOPE.txt)。直接打开 [可视化页面](visualization/index.html) 可查看已生成的结果，无需调用模型；重新生成的依赖见 [可视化说明](visualization/README.md)。

历史实验目录中的 `source_code/` 是不可随意修改的复现快照。上游 BFCL 和 tokenizer 头文件遵循其各自许可证。
