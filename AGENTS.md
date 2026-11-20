# Workspace preservation

- `visualization/` is user-maintained project code. Keep it in version control. Do not delete, prune, replace, or regenerate it during cleanup unless the user explicitly requests that action.
- Preserve frozen experimental trajectories and `source_code/` snapshots. Display names can differ from historical method IDs.
- Never commit `api.txt`, credentials, local environments, model weights, or machine-specific caches.

## 当前工程维护入口

阅读 `doc/README.md` 定位组件和命令。根目录 `base/` 负责共用运行，`datasets/` 负责输入，`models/` 负责图记忆及提供方，`tasks/` 负责科研计算，`conf/` 保存默认配方。新实现放到负责目录；项目内调用直接导入负责实现，`src/cs769/` 提供命令与公开包入口。

新实验产物归 `experiment/`；历史 `experiments/`、冻结源码、已有本机改动及用户维护的 `visualization/` 按原要求保存。科研运行和测试按用户明确指定的范围执行。

<!-- researchharness:projects -->
## ResearchHarness 共同维护

本项目标识为 `cs769`。从项目根目录访问中央入口 `/home/ruqi/workspace/ResearchHarness`，共享技能已开启。
工程维护沿本项目的实际入口和调用关系。若中央有 `src/project/cs769/README.md`，可查阅项目经验和工程入口。
项目代码审阅、计划和授权沿用本项目的 GitHub 流程与当前会话授权。
人类提供研究目的、体验反馈与投入偏好，助手承担授权内的工程判断和持续处理。
值得长期保存的人类思想按 HumanInterface 整理，展示完整草稿并取得认可后保存。
项目接入由 `rh projects status cs769` 查询，用户开关指令由 `rh projects set` 应用。
本机数据与 Python 选择通过 `rh projects resources cs769` 查询。

项目接入说明位于 `.agents/skills/researchharness/SKILL.md`。
<!-- /researchharness:projects -->
