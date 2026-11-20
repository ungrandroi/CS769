# 旧辅助模块清理

本轮将有价值的测试接到统一实现，并移除旧辅助包与旧 workflow 入口。保留实验记录、冻结源码和可视化；不调用模型 API；源码发布在用户 review 后另行授权。

## 当前入口

正式代码：src/cs769。运行入口仍是 python -m cs769；scripts/manage.py 仅转发同一个 CLI。scripts/core 的其余兼容导入继续保留，旧 workflows 包不再提供。

免费测试命令：

    scripts/bfcl_python.sh -B tests/run.py

该命令固定本项目 BFCL，禁止真实网络，同时运行项目与 core 测试。Qwen 原生分词的 4 项可选测试在缺少指定 GGUF／libllama 时明确跳过；模型权重不是图结构测试的必要依赖。

## 删除范围

- src/cs769/legacy：26 个 Python 模块，整个目录移除。
- scripts/workflows：25 个旧转发文件及 1 个包声明，整个目录移除。
- 7 个只测试旧控制器的测试文件，保护目标迁到当前模块。

迁移前源码与测试已备份到 ins04 的 /nobackup/ruqi/CS769-archive/core-migration/legacy-removal/before.tar.gz。备份不是新的活动实现。

## 测试迁移

[45 个旧测试的逐项对应表](test-migration.json)：40 个有当前测试承接其保护目标，5 个仅针对历史实验规则，随旧控制器退役。测试数量不是一对一替换；部分断言已由现有图模块测试覆盖。

| 保护目标 | 当前测试 |
|---|---|
| 完整可见证据、Unicode、原始参数、并行调用和乱序返回 | test_memory_pipeline.py，以及现有图完整性测试 |
| 重复证据不可悄悄丢失、角色和呈现篡改必须失败 | test_memory_pipeline.py |
| 历史接入阈值、完整调用／返回配对 | test_checkpoint_selection.py |
| 采样参数、reasoning 与 temperature 互斥、Claude 不伪造 seed | test_request_parameters.py |
| 前缀来源不匹配、当前用户重复、服务器隐藏历史、禁止覆盖 | test_run_validation.py、test_memory_pipeline.py、test_unified_runtime.py |
| 配对分母、掉点和改善分别保留、重复不抹除首次失败 | test_paired_metrics.py |
| 完整正文计数、缓存／推理 token 不重复累加、工具调用新增次数 | test_memory_pipeline.py、test_paired_metrics.py、test_reporting.py |
| 原始回复先保存、失败仍保留费用、不自动重试 | test_transport_records.py、test_unified_runtime.py、test_reporting.py |

6 个新测试文件共 34 项检查直接调用正式实现。原 Qwen 结构测试通过统一配置运行，计数明确使用字符，不冒充原生 tokenizer；4 项原生 tokenizer 测试仍保留真实依赖要求。冻结源码读取器的旧别名另有回归测试。

完全退役的 5 项：旧固定题目／样本数、自适应补跑触发、V2“恢复一半”验收门槛、旧探针输出签名、旧探针126／115请求数量。旧探针跨变体复用回复和其专用恢复格式也未移植；当前正式入口的保存回复重放、拒绝覆盖、独立重复和预算保护继续验证。

这张表映射保护目标，不宣称旧实验控制器、JSON格式、分类器或历史协议被逐字复刻。

## 正式实现的小修复

1. 配置入口统一校验 temperature 的有限值和范围，并拒绝 reasoning_effort 与 temperature 混用；现有 70 个配置不变。
2. 冻结源码读取器删除旧 workflow 映射，修正 3 个图模块别名到 graphs 命名空间。
3. 当前测试全部使用正式模块，不再借助旧 workflow 导入；manage.py 的兼容行为仍被实际加载验证。

配置名中的 state-legacy／event-legacy 继续表示历史编码格式，与已删除的 Python 辅助包无关。

图算法、模型投喂、工具、官方 eval、实验轨迹与可视化均不在修改范围。旧入口说明保留历史原文，已标注不可作为当前运行命令。

## 验证记录

| 检查 | 最终结果 |
|---|---|
| 单元与模拟集成测试 | 清理阶段 176 项：172 通过、4 项依赖缺失跳过；发布前并入 ruqi 已有 evidence graph 测试后共 249 项：245 通过、4 项跳过，无失败 |
| 完整旧轨迹重放 | 118 道题、identity／evidence graph 共 236 条，3,624 次请求核对一致 |
| 工具结果和官方评分 | 与原记录一致：identity 31/118、evidence graph 34/118；仅作重放校验，非新一轮模型实验 |
| Token 与工具调用统计 | 1,180 个 token／请求数值和 472 个工具调用数值与原记录一致 |
| 既有编辑案例 | 四个领域共 18 个，模型输入正文一致 |
| 接入点与采样 | 118 个接入点、236 份采样设置一致 |
| 原生 wire 请求 | 有对应记录的 223 条轨迹共 2,349 个请求一致；另 13 条未宣称直接 wire 核验 |
| 资料保护 | 23,849 个唯一保留文件和 5 个可视化文件校验一致 |
| 图、运行及模型传输源码 | 36 个对应源文件与本轮开始时相同 |
| API 请求及费用 | 0／$0 |

正式 core 现在为 157 个文件（清理前 183 个）。当前 Python 代码没有指向已删除命名空间的导入，当前文档相对链接检查通过。

详细记录在 ins04 的 /nobackup/ruqi/CS769-archive/core-migration/legacy-removal/：verification.json、replays.json、tests-current.json、static-protocol-check.json、preservation.json 与 legacy-removal.patch。验证结果采用汇总文件保存，没有新增一套实验运行器。

分支仍为 core-unification，HEAD 为 5de8a28e22bd454192ce9243768d7291ca6af841；上述为免费验证时的代码身份；用户随后授权将两次源码迁移合并发布到 ruqi。实际发布版本以 Git 提交为准。
