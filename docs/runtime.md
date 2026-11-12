# 统一实验入口

正式实现位于 `src/cs769/`。`scripts/manage.py` 仅转发同一个 CLI；scripts/core 保留必要导入兼容。旧 workflows 包和旧辅助模块已移除，不再提供独立模型运行入口。测试直接调用正式实现；历史实验记录和源码快照保持原样。

## 现有环境与免费命令

在项目根目录使用现有环境，不新建每轮实验的环境：

```bash
.conda/readable/bin/python -B -m cs769 list
.conda/readable/bin/python -B -m cs769 validate src/cs769/configs/g9-working-history.json
.conda/readable/bin/python -B -m cs769 prepare \
  --config src/cs769/configs/g9-working-history.json \
  --history src/cs769/examples/history.json \
  --output /tmp/cs769-new-input
```

输出目录必须不存在。`prepare` 不调用模型；`characters` 只作结构检查，不能当成 API token。默认离线文本计数器为 `o200k_base`。

真实 BFCL 免费回放：

```bash
.conda/readable/bin/python -B -m cs769 replay \
  --config src/cs769/configs/g9-working-history.json \
  --record /nobackup/ruqi/CS769/evidence/matched118/g9/runs/multi_turn_base_39/g9
```

`replay` 在返回每条保存回复之前，严格检查当前结构化请求的字段值和列表顺序。官方 BFCL 负责执行工具、推进用户轮次及评分；不是直接把旧通过数读出来。它还检查完整工具调用结果、G9 正文和官方二元评分与旧记录一致。记录只读，结果可写到另一个新路径。

默认入口通过进程内路径选择固定到本项目的 vendor BFCL，不改共享环境；如果已加载其他 BFCL，立即拒绝混用。旧 shell 启动器也使用这里已验证的 readable 环境。

BFCL 的虚拟工具实例具有进程级共享状态。因此每条轨迹必须是独立 Python 进程，`batch` 负责隔离；在同一进程重用运行或评分会明确报错。

## 配置分工

- `model`：模型、原生提供方、采样参数、旧 thinking 的处理。
- `checkpoint`：手动接入、完成轮次接入、历史 token 接入。
- `memory`：G9、identity 或显式选择的历史表示。
- `delivery`：替换／原生历史等投喂方式，包含角色配置。
- `edits`：独立操作、参数、启用开关和不适用处理；默认 G9 不编辑。
- `execution`：请求上限、预算及计划参数。

当前 GPT-4.1 对照配置是 `identity.json` 与 `g9-working-history.json`：temperature 0、seed 42、max_tokens 4096；接入定义为历史 Chat JSON 经 o200k_base 计数严格超过 1000，排序对象键、不含工具定义。计数模式显式命名为 `history_json_sorted`；旧 `history_json` 的不排序含义保持不变。

已用的数值 v2 与观察共享配置分别为 `numeric-summary-v2.json`、`share-observations.json`。旧实验设置继续作为显式配置保留，不等于所有历史归档格式和外部依赖都已在 ins04 验证。

重复与随机交错由 `cs769.schedule` 生成显式计划；`batch` 按已审核计划运行，不因一个重复参数隐式增加 API 请求。每个条件的模型、接入点、重复和顺序须在计划中确定。

## 批量调度

`batch --replay --plan PLAN.json --config CONFIG.json --output NEW_DIR --workers 4` 可以免费并行回放。计划条目至少有 `task`、`arm`、`record`，可覆盖 `config`、`source`；输出路径必须是新目录。

计划可显式指定 repeat，相同 task／arm／repeat 不得重复。

当前付费批次只允许一个 worker，所有任务共享同一模型的持久预算账本；失败即停止后续调度。每次请求先预留，收到有效 usage 后结算，不确定失败保留预留，不自动重试。各模型不能共用额度。源码在批次开始后变化也会停止。

生成配对表：report --batch NEW_DIR --baseline identity --candidate g9，或 report --rows ROWS.json。未完成、无官方分数、未触发断点及未配对条件单列，不计入有效配对分母。不同模型分别统计。

## 实际 API 入口

`run` 默认拒绝请求。只有同时提供显式 API 授权、正数新预算、私有凭证文件、明确单价表及有效配置才能运行；`CS769_OFFLINE=1` 始终禁止 API。本次迁移没有实际调用模型，也没有探活真实账号。

密钥由程序读文件，不通过命令行展开，不写配置、仓库或日志。新运行保存请求、原始回复、图与编辑审计、官方评分和预算；不复制源码 runner、BFCL、模型或环境。代码身份采用 Git 提交、实际源码哈希和依赖版本。

从保存的 identity 继续时，先检查任务、模型、采样、状态和断点；断点之前严格复用旧回复。图组只替换该断点的历史，保持其他请求字段和工具定义一致。若原任务没有触发该断点，不会默默改为重新生成前缀。

## 公开 G9 API

```python
from cs769.g9 import build_g9_memory
memory = build_g9_memory(normalized_history, native_history, provider="openai")
text = memory["memory_text"]
```

同一份构图实现供 CLI 和 API 使用。送给 agent 的是图的呈现，不附带一份 identity 历史。模型传输、工具环境、官方评分与图表示分开挂载。

## 统计和验证范围

`usage_all` 包括整条保存轨迹；`usage_live` 只包括本次实际请求；`usage_suffix` 从接入点起统计，用于配对比较。缓存 input 是 input 的子集，reasoning 属于 output，不重复累加。工具调用计数保持现有按 assistant function/tool calls 的定义；通过数只来自官方二元评分。网络、预算、恢复或格式错误不是任务失败，不生成假的官方分数。

本次完整保存轨迹回放验证针对 GPT-4.1。Claude 的原生块、当前轮 signed thinking、工具错误标记通过模拟传输测试；不宣称已经验证真实 Claude API 连通性。

旧 Qwen27B 原生分词集成需要特定 GGUF 和 pinned libllama。这两项目前不在 ins04，相关 4 个原生分词用例按明确的依赖条件跳过，不拿 HF Qwen3-8B 或 o200k_base 冒充原计数。不下载额外权重。

官方 BFCL vendor、实验记录、现有可视化代码都不在本次迁移的修改范围。


## 免费测试

```bash
scripts/bfcl_python.sh -B tests/run.py
```

同一测试入口运行当前项目测试和 core 测试，固定本项目 BFCL，禁止真实网络。4 项 Qwen 原生分词测试只有在指定 GGUF 和 pinned libllama 同时存在时运行；结构和编解码测试无需模型权重。

旧实验的固定题号、固定样本数量、专用命令和自适应补跑规则已随旧控制器退役；证据完整性、断点、投喂、恢复、配对统计和计费保护继续在当前代码上验证。详细对应表见 [旧辅助模块清理](legacy-removal.md)。
