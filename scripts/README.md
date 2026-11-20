# 实验入口

正式实现位于 `src/cs769/`，统一命令为：

```bash
.conda/readable/bin/python -B -m cs769 --help
```

`scripts/bfcl_python.sh scripts/manage.py ...` 转发同一个 CLI。

- list / validate / prepare：免费查看配置与构图。
- replay / batch --replay：使用保存回复执行官方工具及评分，不调用模型；每条轨迹独立进程。
- score / report：对保存结果评分或统计。
- run / batch 实际 API：必须另有授权、预算、私有凭证和单价；默认拒绝。

旧 workflows 包和旧实验专用命令已移除。模型工具的两个可视化脚本直接调用正式实现，可视化代码沿用现状。

免费测试：

```bash
scripts/bfcl_python.sh -B tests/run.py
```

测试入口固定本项目 BFCL 并禁止真实网络。缺失指定 GGUF／libllama 时，4 项可选 Qwen 原生分词测试明确跳过，恢复依赖后自动运行。

详细说明见 [统一运行说明](../docs/runtime.md) 和 [旧辅助模块清理](../docs/legacy-removal.md)。

evidence graph 离线接入见 [接口说明](../docs/evidence-graph-memory.md)、[示例](../examples/evidence_graph_memory.py) 和 [正式 builder](../models/evidence_graph_memory.py)。
