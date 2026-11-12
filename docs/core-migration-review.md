> 后续清理：本文记录 core 初次迁移时的状态；当时保留的旧辅助模块和 workflow 转发入口现已移除，最新状态见 [清理说明](legacy-removal.md)。下方原始验证结果保持历史含义。

# Core 迁移 Review

已完成 ins04 上的统一，等待用户 review；没有提交、没有 push，也没有运行付费实验。

## 现在在哪里、怎样运行

唯一维护的实现：/home/ruqi/public/CS769/src/cs769/。

唯一命令入口（在项目根目录）：

    .conda/readable/bin/python -B -m cs769 --help

旧 scripts/manage.py 与安装后的 cs769 命令转发同一个 CLI。原 /nobackup/ruqi/CS769/core 现在只是指向正式实现的链接，不再保留第二个活动代码目录。现有 readable 环境仅增加本项目的 editable 安装，没有升级依赖或新建环境。

## 改了什么

| 部分 | 迁移结果 |
|---|---|
| 构图 | graphs/ 保存图算法，builders.py 选择算法；G9 API 与 CLI 调同一个 builder |
| 编辑 | edits/ + editing.py；删除、合并、数值编辑、观察共享等按配置独立启用或关闭 |
| 实验设置 | configs/ 有 70 个配置；角色、接入点、模型、采样和编辑参数不再靠复制 runner 切换 |
| 运行与恢复 | cli.py + batch.py + adapters/bfcl.py；每条 BFCL 轨迹独立进程，执行原工具和官方评分 |
| 模型与费用 | adapters/provider.py、http.py、budget.py；共用传输及持久预算，默认禁止付费执行，不自动重试 |
| 统计 | metrics.py + reporting.py；配对通过率、首次输入、累计 token、工具调用及新增次数 |
| 旧模块 | 43 个兼容导入转发；旧模型专用运行循环关闭，可复用的历史分析辅助函数放在 legacy/ |
| 可视化 | 5 个原文件逐字节未改，不重画、不覆盖 |

目前注册了 7 个 builder 和 11 个 editor。70 个配置覆盖旧设置的可选部分，不意味着所有旧实验的外部环境和模型服务都已经逐项验证。保留的 frozen-code 是历史结果的证据，不是新的运行入口。

## 免费验证结果

| 检查 | 结果 |
|---|---|
| 单元与模拟集成测试 | 181/181 通过，涵盖配置、编辑、请求、预算、Claude 工具块和错误处理 |
| 真实 BFCL 完整轨迹重放 | 236/236 通过，覆盖 118 道题的 identity 与 G9 |
| 请求与工具结果 | 3,624 次结构化请求核对；完整工具调用结果与旧记录一致 |
| 官方二元评分 | identity 31/118、G9 34/118，均与旧记录一致；这是重放校验，不是新一轮模型实验 |
| Token 与工具调用统计 | 1,180 个 token／请求数值、472 个工具调用数值均与原记录一致 |
| 编辑产物 | 18 个四领域案例的模型输入正文完全一致；数值 v2 仅补记一个明确的 eligibility 审计参数 |
| 接入点与采样 | 118 个接入点、236 份采样设置一致 |
| 原生 wire 对照 | 已保存 wire 的 223 条轨迹共 2,349 个请求一致；另外 13 条没有相应 wire，未冒充直接核验 |
| 启动方式 | 模块命令、安装命令、旧 shell/manage 启动器输出一致，实际离线构图成功 |
| 记录保护 | 23,849 个唯一保留文件 SHA-256 一致；原 locations.jsonl 未改 |
| API 请求／费用 | 0／$0 |

回放将已保存的模型回复注入真实 BFCL 工具执行流程；它在返回每条回复前检查当前请求，再重新执行工具和官方评分，未连接模型 API。详细依据在下列操作目录中的 migration-verification.json、delivery-replay-batch/manifest.json、portable-tests.json、static-protocol-check.json、preservation-check.json 与 entry-check.json。

## 检查中修复的问题

1. BFCL 工具实例有进程级共享状态，同一进程连续跑两条轨迹会继承前一条创建的文件。batch 现在为每条轨迹启动独立进程，同进程复用明确拒绝；未改工具或 eval。
2. 现有环境默认会导入另一个项目的 BFCL。新入口在自身进程内固定到本项目 vendor；如果已混入别的 BFCL，立即拒绝。未改其他项目或共享环境配置。
3. 统一传输的预算只结算一次；不确定请求保留预留，失败不会自动发起第二次模型请求。对应行为用模拟传输检查。
4. Claude 当前工具轮中的 signed thinking 与 tool_result 错误标记保留；已结束轮次的 thinking 按配置处理。改变历史时拒绝保留绑定旧历史的签名。

## 未验证项与边界

- 旧 Qwen27B 的指定 GGUF 和 pinned libllama 目前缺失，相关 5 项测试未运行，完整列在机器结果中。没有下载权重，也没有用别的 tokenizer 替代。
- Claude 通过的是原生消息／工具链模拟测试；没有做真实 API 探活。新付费入口以后仍需独立授权 smoke，不能把免费测试等同于服务连通性验证。
- 这轮不是新的模型效果实验，也没有扩大题目、改变官方 eval 或重新计 API 分数。
- 其他三个项目的已跟踪代码及原有修改 SHA 均与原清单一致；原清单不覆盖其未跟踪文件，本轮没有删除或迁移它们。

## 原有修改和记录如何保留

开始时的 8 处已有修改都先逐文件备份，再迁移：构图／配置实现搬入新模块，baseline_task 与 gpt41_task 的辅助功能保留，独立模型循环统一；manage.py 与 CLI 测试改为验证新入口。原 scripts/README.md 原文保存在 docs/legacy-entrypoints.md。

备份、详细映射与免费检查记录：

    /nobackup/ruqi/CS769-archive/core-migration/
      core-before.tar.gz
      original-modifications/
      original-change-map.json
      compatibility-map.json
      core-source-migration-map.json
      migration-verification.json
      core-migration.patch
      delivery-replay-batch/

原 locations.jsonl 中的旧 core 校验值对应迁移前备份；新的正式源码对应 core-source-migration-map.json。没有重写历史校验记录来伪装代码未变化。

实验记录、报告、冻结源码与可视化均保留，未执行此前讨论的进一步实验记录清理。

## 待 review 的改动

分支：core-unification；HEAD 仍为 5de8a28e22bd454192ce9243768d7291ca6af841。全部改动尚未提交、尚未 push。

迁移专用 diff 以开始时工作树为基线，包含当时已有修改，不把它们覆盖成 Git HEAD，也不混入之前清理造成的实验文件删除。

Diff 共 242 个文件，新增 16,345 行、移出／删除 7,039 行；新增包中的大量行来自旧 core 的源码迁入，不代表新增同等规模的运行逻辑。完整文件清单与逐项统计见 migration-verification.json。
