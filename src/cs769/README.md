# CS769 统一实现

这份代码位于正式仓库的 `src/cs769/`，通过现有环境的 editable 安装使用；不要再复制进每个实验目录。

唯一入口：`python -m cs769`。旧 manage.py 只转发同一个入口。使用、配置、预算、验证范围与可选依赖见 [运行说明](../../docs/runtime.md)。

默认 G9 替换旧历史，不附带 identity；编辑通过配置独立开关。图和呈现、模型请求、BFCL 恢复及官方评分、统计、预算分开组织。历史表示配置继续保留，旧独立模型循环及旧辅助模块已移除。

完整使用示例为 `configs/g9-working-history.json`。公开构图 API 为 `cs769.g9.build_g9_memory`。

`docs/source-manifest.json` 保留原模块来源，并注明本次命名空间迁移后的哈希；历史实验本身及冻结源码不改写。本轮未运行付费实验，实际 API 仍需后续单独授权 smoke。

免费测试命令：`scripts/bfcl_python.sh -B tests/run.py`（在项目根目录）。旧 workflows 导入已停用，测试与运行均使用正式模块。清理对应关系见 [说明](../../docs/legacy-removal.md)。
