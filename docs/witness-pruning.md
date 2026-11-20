# 按后续证据删减 evidence graph

统一编辑名：`prune_witnessed_history`。仅使用当前 evidence graph 与当前用户请求，无题号、后续答案或 eval 访问。

当前两个可独立开关的关系契约：

- `relocated_location`：可见 pwd/cd 确定作用范围，find 仅返回一个路径，后续成功 mv 明确移动同一对象；删除旧 find 调用和返回，保留路径上下文与移动回执。mkdir 按已核对契约只添加目录或报错，不移动已有文件，保留该操作记录；未知写入、身份变化、并行/尚未返回的读取会使候选失效；cp 不证明旧位置被覆盖。
- `resolved_error`：复用已有成功重试编辑，并核对串行结果、相同参数和同一作用范围。当前仅审查 startEngine(START) 的无失败副作用契约；STOP 会先改状态再报错，不能使用这项契约。保留成功回执与所有中间修复操作。

先计算相同的无损结构共享基线；各候选删减后再做同一共享，以最终正文成本选择比共享额外减少至少 50 token 的候选。平局按原节点顺序，再按关系名决定。开关 `relations` 可选择上述子集，`min_saved_tokens` 参数控制额外节省下限。共享后本编辑为终端操作。

用户当前询问旧状态或前后变化时不删。成功重试还保留已有错误/失败原因查询保护。图校验与保留证据逐字段核对只证明编辑合法；通过率需断点续跑实测，不保证任务安全。

图组以图替换旧历史，不另附 identity。identity、完整 evidence graph、无损共享、删减后共享分组比较；实际 API 计费、工具执行与官方评分仍使用同一运行入口。本轮断点、预算和结果在独立 evidence 目录，本文不包含固定题号或实验控制器。

## 可选成功重试契约扩展

resolved_contracts 默认仅为 ["start_engine"]，保留旧配置语义。明确启用 created_file 或 authenticated_send 时审计版本为 g9-witness-pruning-v1.1。

- created_file：cat 对单个本地文件返回精确“不存在”错误，随后同目录 touch 同一名称成功，再以完全相同参数 cat 成功。只允许只读操作穿插，任何 cd、其他写入或未知操作均拒绝。保留 touch、成功内容和其他历史。
- authenticated_send：send_message 因未登录返回错误，该错误发生在消息 ID 分配和 inbox 写入之前。保留一次成功 message_login、与原发送完全相同的收件人和正文以及成功回执；期间只允许账号查询，不允许再次切换账号、登出、其他发送或未知操作。
- 新契约要求失败返回、修复调用与返回、成功重试严格串行；不跨 episode。先前错误说明查询保护保持不变，实际相对共享额外节省门槛仍由 min_saved_tokens 控制。
- 这些是编辑合法性条件，不是任务安全保证；新增工具契约需要独立开发验证。未来用户请求、题号和官方答案不参与编辑选择。


## Optional located-read contract (development v1.2)
Enable only via resolved_contracts: ["located_read"]. Default and v1.1 contracts remain unchanged.
A unique find(name, path=".") result ./directory/file anchors a failed local cat,
one successful cd(directory), and a later successful identical cat in the same user turn.
Only serial reviewed reads may intervene. Ambiguity, mutations, unknown tools, directory changes
before failure, or multiple/failed changes before success reject the candidate.
Failed and successful paths are distinct: no same-object identity or obsolete absence fact is asserted.
Delete only the failed call and error return. Retain exact find, cd, successful content and all other evidence.
This is a lossy policy, not a proof of task safety; official continuation outcomes decide usefulness.
The single-level constraint follows the official BFCL cd contract. No task IDs, future turns or eval answers
enter candidate selection. Historical-state and error-explanation requests remain ineligible.
