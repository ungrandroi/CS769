BFCL · V5 · FROZEN B · 2026-10-22

# 实验已完成；B 尚未证明保持通过率

[报告目录](README.md) · [GitHub 阅读版](v5-b-validation-results.md)

GPT-4.1 总分持平但有个别得失分互换；GPT-5-mini 净下降。证据完整性审计通过，失败差异同时包含评分路径问题与真实任务执行问题。

348 / 348

续跑全部完成<br>
144 次首轮筛选 → 88 个合格模型×条件

−2.67 pp

模型与题族等权主差值<br>
95% CI：−7.81 至 +2.42 pp

$9.95

成功请求的未缓存参考费用<br>
另保留 $5.60 未知重试预算；不是确认账单

服务器于 2026-10-22 05:32 UTC（芝加哥 00:32）完成运行和审查材料生成。本报告补充独立统计核验与行为审查；本次未发起新的模型请求。

## 1. 实际测试了什么

identity 使用完整原生历史。B 保留相同的完整原生历史，在第一轮结束后仅加入一次 **assistant 角色图索引**，后续追加真实交互。两组使用完全一致的工具定义；没有删除历史、压缩、动态更新索引或运行 Claude。

GPT-4.1：45 个合格条件，每组 seed 42 各 1 次。GPT-5-mini：43 个合格条件，每组 seed 42/43/44 各 3 次，即每组 129 条。每个模型覆盖 25 个题族，合并为 27 个不同题族；重复与 base/long_context 不是独立题族。全部采用预先冻结的配对随机交错计划。

## 2. 官方通过率与预先约定的判定

| 模型 | identity | B | B − identity | 新增失败 / 改善（配对） |
| --- | --- | --- | --- | --- |
| gpt-4.1 | 28/45 (62.22%) | 28/45 (62.22%) | +0.00 pp | 2 / 2 |
| gpt-5-mini | 51/129 (39.53%) | 44/129 (34.11%) | -5.43 pp | 13 / 6 |

“新增失败”指同一条件、同一 seed 下 identity 通过而 B 失败。GPT-5-mini 的 13 次新增失败涉及 10 个条件；按每个条件 3 次的净通过数比较，43 个条件中 9 个下降、3 个上升、31 个持平。GPT-4.1 则为 2 个下降、2 个上升、41 个持平。

**主结果：证据不足，不能宣称通过率已保持。**<br>
按重复→条件→题族→模型逐层等权，identity 为 52.00%，B 为 49.33%，差值 −2.67 pp；按共同题族聚类重采样 20,000 次，95% 区间为 \[-7.81, +2.42\] pp。预定标准要求下限高于 −5 pp，本轮没有达到。区间仍含 0，也不能据此断言存在已经统计确证的总体下降。

逐模型题族等权结果：GPT-4.1 为 60.00%→60.00%，差值区间 \[−8.00,+8.00\] pp；GPT-5-mini 为 44.00%→38.67%，差值区间 \[−13.46,+3.85\] pp。它们与上表按轨迹计数的比例口径不同。主结果使用各模型等权，避免 mini 的三次重复获得三倍权重。

## 3. 新增退化具体是什么

审查覆盖全部 23 个官方得失分配对的 46 条轨迹，以及所有 58 条出现零工具回合的轨迹，去重共 102 条。两位模型子代理分别在隐藏模型、组别、seed 和官方分数后审查 51 条；主代理再合并元数据进行比较。每条只有一位盲审者，未计算审稿者一致率；这不是独立人类标注。

- **工具路径与评分要求不一致。**例如 GPT-4.1 long_context_21、mini base_13 用 cat 读文件后正确比较，却没有产生 diff 的指定执行结果；mini base_31 手算得出正确均值，却未调用 mean。GPT-4.1 long_context_17 先读旧消息列表再发送，最终文字已正确合并新消息，但工具返回缺少发送后的列表。
- **利用历史正确回答，却触发逐轮工具要求。**mini base_7、long_context_7 在前一轮已经读取文件，当前轮直接返回完整内容，被判 empty_turn。索引本身只列目录事实，这些内容来自完整历史，不能说是索引提供了新的答案。
- **真实执行问题。**mini base_40 把已有 ID 当用户名查询，随后未发消息；base_35 在文件不存在时反复写入，没有用 touch 恢复；long_context_0 多建文件、手工复制长文本并损坏字符；base_14 未添加明确要求的联系人；base_27 给指定工单描述添加了额外文字。
- **保留语义歧义。**mini long_context_21 两条轨迹在认证成功后又拒绝发布，只提供草稿。官方要求已发布状态，但用户同时使用 draft 与 broadcast；盲审保留这一区别，不把未发布一概归为真实任务失败。

因此，没有证据显示这轮掉点来自历史证据被删掉；审计确认完整历史都在。B 的上下文变化伴随工具选择、查询顺序、错误恢复和行动意图解释的差异。许多同类错误也出现在 identity，且有反方向改善；个别配对不能证明唯一因果机制，也不能把全部失败归为评分器偏差。

| 模型 | 组别 | 有零工具回合的轨迹 | 零工具回合数 | 官方 empty_turn 轨迹 |
| --- | --- | --- | --- | --- |
| gpt-4.1 | identity | 0 | 0 | 0 |
| gpt-4.1 | B | 0 | 0 | 0 |
| gpt-5-mini | identity | 25 | 29 | 20 |
| gpt-5-mini | B | 33 | 37 | 25 |

对官方 empty_turn 指向的具体回合逐一核对，identity 的 20 条中有 **7 条**、B 的 25 条中有 **11 条**属于“根据完整历史给出了正确的文件内容或数值答案”，这一计数排除了所有草稿请求。这支持单列“答案正确但没有当前轮工具执行”的现象；并不代表整条任务均成功，也不足以单独证明索引导致了该行为。

2026-10-22 更正：原 8/13 因通用标签混入三条推文草稿，按声明的窄口径修正为 7/11。long_context_49 仅确认历史行数 20 的对数数值正确，保留用户精度措辞歧义。[更正记录](evidence/records/v5-auxiliary-correction.json) · [原始行为证据视图](evidence/records/v5-behavior-evidence.json)。官方分数、token、费用和置信区间不变，未推算总体“语义通过率”。

<details>
<summary>全部 15 次新增官方失败及对照原因</summary>

| 模型 | 条件 | seed | 分类 | 具体比较 |
| --- | --- | --- | --- | --- |
| gpt-4.1 | long_context_17 | 42 | 工具路径与评分要求不一致 | A 发送消息后读取已发送列表；B 先读旧列表再发送，最后把已确认的新消息合并进文字列表。盲审确认最终列表与状态正确；官方缺少含新消息的 view_messages_sent 返回。 |
| gpt-4.1 | long_context_21 | 42 | 工具路径与评分要求不一致 | A 使用 diff；B 使用 cat 读取两个文件后正确比较，后续推文也完成。官方缺少 diff_lines 执行结果。 |
| gpt-5-mini | base_13 | 42 | 工具路径与评分要求不一致 | A 使用 diff；B cat 两个文件后正确说明差异，但缺少官方期望的 diff_lines。 |
| gpt-5-mini | base_13 | 43 | 工具路径与评分要求不一致 | 与 seed 42 相同：B 正确比较文本，采用 cat 而非 diff。seed 44 反过来是 B 使用 diff、identity 采用 cat，B 因而得分。 |
| gpt-5-mini | base_14 | 44 | 实际未完成任务 | 用户明确要求添加 John Levy 并发消息；B 查询不存在的联系人后转而请求确认，没有添加或发送。A 完成。GPT-4.1 的同题则出现相反方向的改善，说明这类行为也发生在 identity。 |
| gpt-5-mini | base_27 | 44 | 写入内容偏离明确要求 | B 给首张工单的指定描述追加了额外解释段，偏离源文件原文；A 保留指定描述。seed 42 的 identity 也犯了同类错误，B 则正确。 |
| gpt-5-mini | base_31 | 44 | 工具路径与评分要求不一致 | B 通过 wc 得到唯一文件 37 字符，直接正确计算平均值 37；A 额外调用 mean(\[37\])。官方缺少 mean 的执行结果。 |
| gpt-5-mini | base_35 | 43 | 错误恢复失败 | 目标 diff.txt 尚不存在时 echo 报错。A 用 touch 创建后写入；B 反复 echo、切目录并额外建目录，没有完成文件保存，撞到步数上限。 |
| gpt-5-mini | base_40 | 42 | 误用工具参数并提前停止 | B 把已有用户 ID USR002 传给按用户名查询的 get_user_id，查询失败后认为用户不存在，未发送消息；A 直接使用 receiver_id=USR002 发送成功。 |
| gpt-5-mini | base_40 | 44 | 误用工具参数并提前停止 | 同样把 ID 当用户名查询；B 进一步列用户后请求新 ID，仍未执行已获授权的发送。 |
| gpt-5-mini | base_7 | 44 | 历史回答与逐轮工具评分不一致 | B 在上一轮已经读过目标文件，这一轮直接准确返回完整内容，没有再次调用工具，被判 empty_turn；A 在当前轮 cat，因此通过。 |
| gpt-5-mini | long_context_0 | 43 | 多余写入与文本损坏 | B 额外创建 final_report_sorted.txt、previous_report_sorted.txt，把长文本手工复制进新文件；复制中撇号发生损坏，又用副本比较。A 使用 sort、mv、diff 完成原要求。B 多出的文件状态也不符合官方预期。 |
| gpt-5-mini | long_context_21 | 43 | 工具路径差异及任务语义歧义 | B 用 cat 而非 diff，官方先因比较工具输出不匹配失败；后续已认证成功，却又拒绝使用凭据并只交付推文草稿。用户同时用了 draft 与 broadcast，盲审保留是否必须发布的语义歧义。 |
| gpt-5-mini | long_context_21 | 44 | 任务语义歧义及前后不一致 | 文件比较完成；B 调用认证成功后又拒绝发布，只给草稿。官方要求发布后的 Twitter 状态；盲审因 draft/broadcast 的混合措辞不把未发布一律定为真实失败。 |
| gpt-5-mini | long_context_7 | 42 | 历史回答与逐轮工具评分不一致 | B 前一轮已经读取文件，当前轮完整准确复述内容但零工具调用，官方判 empty_turn；A 当前轮读取后通过。 |

</details>

<details>
<summary>全部 8 次官方改善</summary>

| 模型 | 条件 | seed | 分类 | 具体比较 |
| --- | --- | --- | --- | --- |
| gpt-4.1 | base_14 | 42 | 完成了 identity 漏做的行动 | identity 查询联系人失败后停下询问；B 添加联系人并发送了要求的内容。 |
| gpt-4.1 | long_context_35 | 42 | 精确保留写入文本 | 两组都最终创建并写入 diff.txt；identity 在复制差异文本时把 12 个 U+2019 撇号改成 U+0019，B 保留了准确文本。 |
| gpt-5-mini | base_13 | 44 | 采用官方期望的比较工具 | identity 使用 cat 后自行比较；B 使用 diff，返回官方期望的 diff_lines。 |
| gpt-5-mini | base_17 | 42 | 工具调用顺序符合评分要求 | identity 先读取已发送列表再发新消息；B 先发送再读取，返回了含新消息的列表。 |
| gpt-5-mini | base_27 | 42 | 精确保留指定工单描述 | identity 给指定描述添加额外文字；B 按文件原文创建工单。 |
| gpt-5-mini | long_context_17 | 43 | 修复联系人与发送流程 | identity 把分数字串当联系人姓名，且没有真正发送消息；B 正确添加 Kelly、发送分数并读取已发送列表。 |
| gpt-5-mini | long_context_24 | 42 | 正确定位文件后改名 | identity 在移动后误把 archives 目录作为重命名对象；B 进入 archives 后重命名目标文件。 |
| gpt-5-mini | long_context_24 | 43 | 最终恢复并完成改名 | identity 的错误移动破坏了目录状态；B 也经过多次路径错误，但最终进入目录并正确重命名，代价是更多请求。 |

</details>

## 4. Token：平均续跑开销

| 模型 | 组别 | 轨迹数 | 输入 token | 输出 token | 合计 token | 请求次数 | 工具调用次数 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| gpt-4.1 | identity | 45 | 24,546 | 362 | 24,908 | 6.33 | 4.33 |
| gpt-4.1 | B | 45 | 25,321 | 404 | 25,725 | 6.38 | 4.47 |
| gpt-5-mini | identity | 129 | 32,387 | 1,304 | 33,692 | 7.47 | 5.34 |
| gpt-5-mini | B | 129 | 36,557 | 1,393 | 37,950 | 7.99 | 5.95 |

以上是**第一轮接入之后每条续跑**的平均成功请求 usage，输入包含工具定义、全部历史及重复送入的上下文，输出已包含 reasoning token。GPT-4.1 合计增加 **3.28%**，GPT-5-mini 增加 **12.64%**。首次续跑请求输入的配对平均增量仅为 **54.0 / 68.1 token**；索引正文约 50.0 / 62.1 token。后续每次请求仍会携带该索引，同时工具路径、响应内容和请求数也发生变化，不能把全部累计增量等同于索引长度。

例如 mini long_context_0 seed 43 的 B 额外建文件并复制长文本，请求从 14 次增到 26 次，配对总 token 多约 17.6 万；base_35 seed 43 从 9 次增到 23 次，多约 6.7 万 token。另一方面，long_context_24 seed 43 的 B 用更多尝试最终解决问题，说明更多 token 也可能伴随改善。

全实验成功响应共输入 13,344,786、输出 453,486，合计 13,798,272 token；其中全部 144 个新首轮实际只生成并计费一次，共 2,278,054 token，不能按 A/B 与重复数重复计费。缓存输入 12,292,480 是输入子集，推理输出 276,480 是输出子集，均不得再次相加。119 次 HTTP 429 没有服务端 usage，不虚构 token。

## 5. 筛选与排除

| 模型 | 候选条件 | 首轮通过 | 首轮未通过排除 | 通过但索引空排除 | 最终合格 | 合格题族 |
| --- | --- | --- | --- | --- | --- | --- |
| gpt-4.1 | 72 | 58 | 14 | 13 | 45 | 25 |
| gpt-5-mini | 72 | 51 | 21 | 8 | 43 | 25 |

36 个新题族各有 base/long_context 两个条件，每模型 72 个。总共筛选 144 个模型×条件，排除 56 个：35 个首轮未通过，另外 21 个虽然首轮通过但索引为空。未依据后续 identity 或 B 成败补题、删题或换样本。按全部可重叠原因统计，索引为空共 31 个，其中 10 个已包含在首轮失败中；mini 有 1 个未到达接入边界的样本，也已包含在首轮失败内。

所有入选题都按题目提供的完整工具集运行，工具类不限于文件系统；索引构图规则未为混合工具调整。结论适用于“实际首轮通过且索引非空”的条件集合，不能外推成整个 BFCL 的准确率。

<details>
<summary>完整 56 个排除条件与原因（原因可重叠）</summary>

| 模型 | 条件 | 原始排除理由 |
| --- | --- | --- |
| gpt-4.1 | base_0 | official_first_turn_failed |
| gpt-4.1 | base_2 | official_first_turn_failed, empty_graph_index |
| gpt-4.1 | long_context_2 | official_first_turn_failed |
| gpt-4.1 | base_8 | empty_graph_index |
| gpt-4.1 | long_context_8 | empty_graph_index |
| gpt-4.1 | long_context_13 | official_first_turn_failed |
| gpt-4.1 | base_18 | official_first_turn_failed |
| gpt-4.1 | base_19 | empty_graph_index |
| gpt-4.1 | long_context_19 | empty_graph_index |
| gpt-4.1 | base_22 | official_first_turn_failed, empty_graph_index |
| gpt-4.1 | long_context_22 | official_first_turn_failed, empty_graph_index |
| gpt-4.1 | long_context_24 | empty_graph_index |
| gpt-4.1 | base_27 | official_first_turn_failed, empty_graph_index |
| gpt-4.1 | base_28 | empty_graph_index |
| gpt-4.1 | long_context_28 | empty_graph_index |
| gpt-4.1 | base_34 | empty_graph_index |
| gpt-4.1 | long_context_34 | empty_graph_index |
| gpt-4.1 | base_36 | official_first_turn_failed |
| gpt-4.1 | long_context_36 | official_first_turn_failed |
| gpt-4.1 | base_41 | empty_graph_index |
| gpt-4.1 | long_context_41 | official_first_turn_failed, empty_graph_index |
| gpt-4.1 | base_42 | official_first_turn_failed |
| gpt-4.1 | long_context_42 | official_first_turn_failed |
| gpt-4.1 | base_45 | empty_graph_index |
| gpt-4.1 | long_context_45 | empty_graph_index |
| gpt-4.1 | base_47 | empty_graph_index |
| gpt-4.1 | long_context_47 | official_first_turn_failed, empty_graph_index |
| gpt-5-mini | base_0 | official_first_turn_failed, completed_first_turn_boundary_not_reached, native_evidence_not_verified, empty_graph_index |
| gpt-5-mini | base_2 | official_first_turn_failed |
| gpt-5-mini | long_context_2 | official_first_turn_failed |
| gpt-5-mini | base_8 | official_first_turn_failed |
| gpt-5-mini | long_context_8 | official_first_turn_failed |
| gpt-5-mini | long_context_13 | official_first_turn_failed |
| gpt-5-mini | base_15 | official_first_turn_failed |
| gpt-5-mini | long_context_15 | official_first_turn_failed |
| gpt-5-mini | base_18 | official_first_turn_failed |
| gpt-5-mini | long_context_18 | official_first_turn_failed |
| gpt-5-mini | base_19 | empty_graph_index |
| gpt-5-mini | long_context_19 | empty_graph_index |
| gpt-5-mini | long_context_20 | official_first_turn_failed |
| gpt-5-mini | base_23 | official_first_turn_failed |
| gpt-5-mini | base_24 | empty_graph_index |
| gpt-5-mini | long_context_30 | official_first_turn_failed |
| gpt-5-mini | base_34 | empty_graph_index |
| gpt-5-mini | long_context_34 | empty_graph_index |
| gpt-5-mini | long_context_35 | official_first_turn_failed |
| gpt-5-mini | base_36 | official_first_turn_failed |
| gpt-5-mini | long_context_36 | official_first_turn_failed |
| gpt-5-mini | base_41 | official_first_turn_failed, empty_graph_index |
| gpt-5-mini | long_context_41 | official_first_turn_failed, empty_graph_index |
| gpt-5-mini | base_42 | official_first_turn_failed, empty_graph_index |
| gpt-5-mini | long_context_42 | official_first_turn_failed |
| gpt-5-mini | base_45 | empty_graph_index |
| gpt-5-mini | long_context_45 | empty_graph_index |
| gpt-5-mini | base_47 | empty_graph_index |
| gpt-5-mini | long_context_47 | official_first_turn_failed |

</details>

<details>
<summary>完整 88 个合格条件的两组通过数</summary>

| 模型 | 条件 | 题族 | identity | B | 差值 |
| --- | --- | --- | --- | --- | --- |
| gpt-4.1 | base_11 | 11 | 0/1 | 0/1 | +0.0 pp |
| gpt-4.1 | base_13 | 13 | 0/1 | 0/1 | +0.0 pp |
| gpt-4.1 | base_14 | 14 | 0/1 | 1/1 | +100.0 pp |
| gpt-4.1 | base_15 | 15 | 1/1 | 1/1 | +0.0 pp |
| gpt-4.1 | base_17 | 17 | 1/1 | 1/1 | +0.0 pp |
| gpt-4.1 | base_20 | 20 | 1/1 | 1/1 | +0.0 pp |
| gpt-4.1 | base_21 | 21 | 1/1 | 1/1 | +0.0 pp |
| gpt-4.1 | base_23 | 23 | 1/1 | 1/1 | +0.0 pp |
| gpt-4.1 | base_24 | 24 | 1/1 | 1/1 | +0.0 pp |
| gpt-4.1 | base_30 | 30 | 0/1 | 0/1 | +0.0 pp |
| gpt-4.1 | base_31 | 31 | 1/1 | 1/1 | +0.0 pp |
| gpt-4.1 | base_32 | 32 | 0/1 | 0/1 | +0.0 pp |
| gpt-4.1 | base_33 | 33 | 1/1 | 1/1 | +0.0 pp |
| gpt-4.1 | base_35 | 35 | 1/1 | 1/1 | +0.0 pp |
| gpt-4.1 | base_4 | 4 | 0/1 | 0/1 | +0.0 pp |
| gpt-4.1 | base_40 | 40 | 1/1 | 1/1 | +0.0 pp |
| gpt-4.1 | base_43 | 43 | 1/1 | 1/1 | +0.0 pp |
| gpt-4.1 | base_44 | 44 | 1/1 | 1/1 | +0.0 pp |
| gpt-4.1 | base_48 | 48 | 1/1 | 1/1 | +0.0 pp |
| gpt-4.1 | base_49 | 49 | 0/1 | 0/1 | +0.0 pp |
| gpt-4.1 | base_5 | 5 | 1/1 | 1/1 | +0.0 pp |
| gpt-4.1 | base_7 | 7 | 1/1 | 1/1 | +0.0 pp |
| gpt-4.1 | long_context_0 | 0 | 1/1 | 1/1 | +0.0 pp |
| gpt-4.1 | long_context_11 | 11 | 0/1 | 0/1 | +0.0 pp |
| gpt-4.1 | long_context_14 | 14 | 0/1 | 0/1 | +0.0 pp |
| gpt-4.1 | long_context_15 | 15 | 1/1 | 1/1 | +0.0 pp |
| gpt-4.1 | long_context_17 | 17 | 1/1 | 0/1 | -100.0 pp |
| gpt-4.1 | long_context_18 | 18 | 0/1 | 0/1 | +0.0 pp |
| gpt-4.1 | long_context_20 | 20 | 1/1 | 1/1 | +0.0 pp |
| gpt-4.1 | long_context_21 | 21 | 1/1 | 0/1 | -100.0 pp |
| gpt-4.1 | long_context_23 | 23 | 1/1 | 1/1 | +0.0 pp |
| gpt-4.1 | long_context_27 | 27 | 0/1 | 0/1 | +0.0 pp |
| gpt-4.1 | long_context_30 | 30 | 0/1 | 0/1 | +0.0 pp |
| gpt-4.1 | long_context_31 | 31 | 1/1 | 1/1 | +0.0 pp |
| gpt-4.1 | long_context_32 | 32 | 0/1 | 0/1 | +0.0 pp |
| gpt-4.1 | long_context_33 | 33 | 1/1 | 1/1 | +0.0 pp |
| gpt-4.1 | long_context_35 | 35 | 0/1 | 1/1 | +100.0 pp |
| gpt-4.1 | long_context_4 | 4 | 0/1 | 0/1 | +0.0 pp |
| gpt-4.1 | long_context_40 | 40 | 1/1 | 1/1 | +0.0 pp |
| gpt-4.1 | long_context_43 | 43 | 0/1 | 0/1 | +0.0 pp |
| gpt-4.1 | long_context_44 | 44 | 1/1 | 1/1 | +0.0 pp |
| gpt-4.1 | long_context_48 | 48 | 1/1 | 1/1 | +0.0 pp |
| gpt-4.1 | long_context_49 | 49 | 0/1 | 0/1 | +0.0 pp |
| gpt-4.1 | long_context_5 | 5 | 1/1 | 1/1 | +0.0 pp |
| gpt-4.1 | long_context_7 | 7 | 1/1 | 1/1 | +0.0 pp |
| gpt-5-mini | base_11 | 11 | 0/3 | 0/3 | +0.0 pp |
| gpt-5-mini | base_13 | 13 | 2/3 | 1/3 | -33.3 pp |
| gpt-5-mini | base_14 | 14 | 3/3 | 2/3 | -33.3 pp |
| gpt-5-mini | base_17 | 17 | 0/3 | 1/3 | +33.3 pp |
| gpt-5-mini | base_20 | 20 | 3/3 | 3/3 | +0.0 pp |
| gpt-5-mini | base_21 | 21 | 0/3 | 0/3 | +0.0 pp |
| gpt-5-mini | base_22 | 22 | 0/3 | 0/3 | +0.0 pp |
| gpt-5-mini | base_27 | 27 | 2/3 | 2/3 | +0.0 pp |
| gpt-5-mini | base_28 | 28 | 0/3 | 0/3 | +0.0 pp |
| gpt-5-mini | base_30 | 30 | 0/3 | 0/3 | +0.0 pp |
| gpt-5-mini | base_31 | 31 | 2/3 | 1/3 | -33.3 pp |
| gpt-5-mini | base_32 | 32 | 0/3 | 0/3 | +0.0 pp |
| gpt-5-mini | base_33 | 33 | 3/3 | 3/3 | +0.0 pp |
| gpt-5-mini | base_35 | 35 | 3/3 | 2/3 | -33.3 pp |
| gpt-5-mini | base_4 | 4 | 0/3 | 0/3 | +0.0 pp |
| gpt-5-mini | base_40 | 40 | 3/3 | 1/3 | -66.7 pp |
| gpt-5-mini | base_43 | 43 | 0/3 | 0/3 | +0.0 pp |
| gpt-5-mini | base_44 | 44 | 0/3 | 0/3 | +0.0 pp |
| gpt-5-mini | base_48 | 48 | 3/3 | 3/3 | +0.0 pp |
| gpt-5-mini | base_49 | 49 | 0/3 | 0/3 | +0.0 pp |
| gpt-5-mini | base_5 | 5 | 0/3 | 0/3 | +0.0 pp |
| gpt-5-mini | base_7 | 7 | 3/3 | 2/3 | -33.3 pp |
| gpt-5-mini | long_context_0 | 0 | 3/3 | 2/3 | -33.3 pp |
| gpt-5-mini | long_context_11 | 11 | 0/3 | 0/3 | +0.0 pp |
| gpt-5-mini | long_context_14 | 14 | 3/3 | 3/3 | +0.0 pp |
| gpt-5-mini | long_context_17 | 17 | 0/3 | 1/3 | +33.3 pp |
| gpt-5-mini | long_context_21 | 21 | 2/3 | 0/3 | -66.7 pp |
| gpt-5-mini | long_context_22 | 22 | 0/3 | 0/3 | +0.0 pp |
| gpt-5-mini | long_context_23 | 23 | 3/3 | 3/3 | +0.0 pp |
| gpt-5-mini | long_context_24 | 24 | 1/3 | 3/3 | +66.7 pp |
| gpt-5-mini | long_context_27 | 27 | 0/3 | 0/3 | +0.0 pp |
| gpt-5-mini | long_context_28 | 28 | 0/3 | 0/3 | +0.0 pp |
| gpt-5-mini | long_context_31 | 31 | 0/3 | 0/3 | +0.0 pp |
| gpt-5-mini | long_context_32 | 32 | 0/3 | 0/3 | +0.0 pp |
| gpt-5-mini | long_context_33 | 33 | 3/3 | 3/3 | +0.0 pp |
| gpt-5-mini | long_context_4 | 4 | 0/3 | 0/3 | +0.0 pp |
| gpt-5-mini | long_context_40 | 40 | 3/3 | 3/3 | +0.0 pp |
| gpt-5-mini | long_context_43 | 43 | 0/3 | 0/3 | +0.0 pp |
| gpt-5-mini | long_context_44 | 44 | 0/3 | 0/3 | +0.0 pp |
| gpt-5-mini | long_context_48 | 48 | 3/3 | 3/3 | +0.0 pp |
| gpt-5-mini | long_context_49 | 49 | 0/3 | 0/3 | +0.0 pp |
| gpt-5-mini | long_context_5 | 5 | 0/3 | 0/3 | +0.0 pp |
| gpt-5-mini | long_context_7 | 7 | 3/3 | 2/3 | -33.3 pp |

</details>

## 6. 费用与运行完整性

按冻结的**未缓存参考单价**，成功请求合计 **$9.953568**：全部首轮筛选 $2.2706125（含排除样本 $0.930315），identity 续跑 $3.72040475，B 续跑 $3.96255075。另有 119 次 HTTP 429 保守预留 **$5.59667425**，当前预算占用合计 **$15.55024225**，低于本轮上限 $24.505534。

这些数字不是平台账单。冻结参考单价为 GPT-4.1 输入/输出每百万 token $2/$8，mini 为 $0.25/$2；成功请求没有计入缓存折扣。119 次失败重试的保留预算不是确认收费，也不假设免费。本轮加此前占用合计 $21.04470825，仍在最初 $30 总额度内。

| 模型 | 阶段 | 成功请求数 | 成功请求参考费用 | 未知重试保留预算 |
| --- | --- | --- | --- | --- |
| gpt-4.1 | continuation_identity | 285 | $2.339444 | $0.000000 |
| gpt-4.1 | continuation_native-graph-index | 287 | $2.424274 | $0.000000 |
| gpt-4.1 | prefix_eligible | 158 | $1.093612 | $0.000000 |
| gpt-4.1 | prefix_excluded | 103 | $0.719898 | $0.000000 |
| gpt-5-mini | continuation_identity | 963 | $1.380961 | $2.639644 |
| gpt-5-mini | continuation_native-graph-index | 1031 | $1.538277 | $2.824104 |
| gpt-5-mini | prefix_eligible | 212 | $0.246686 | $0.088356 |
| gpt-5-mini | prefix_excluded | 158 | $0.210417 | $0.044570 |

独立审计实际读取全部 492 条完成轨迹（144 首轮 + 348 续跑），核对 1,870 个首轮证据文件哈希、348 份清单和评分哈希、3,197 组请求/响应 usage，以及全部账本重试记录。**原生历史、索引位置、工具定义、后续历史追加与账本均无不一致。**没有终止错误或输出长度截断。

启动时曾遇到 mpmath 缺失，在任何相关模型请求发出前停止；通过隔离环境补齐依赖后恢复原固定计划。此前已完成的首轮保留，没有重抽已观察结果；初始零调用故障与修复证据单独留存。

## 7. 本轮结论

**可以冻结实现与本轮结果，不能写“B 已达到原始历史准确率”。**这轮支持“完整历史加轻量索引可以被稳定重建和运行”，但保通过率的统计目标仍是证据不足。继续研究压缩时，应同时保留官方分数、具体执行失败及评分路径差异这三类证据，不把第一步包装成已经成功。

本次仅完成结果核查与分析，未改格式、重跑验证集、启动 Claude 或开始压缩。

[完整结构化结果与逐例盲审](evidence/v5-b-validation-results.json) · [独立统计、证据与费用审计](evidence/v5-b-validation-audit.json)<br>
服务器原始证据：/home/ruqi/public/CS769/experiments/bfcl_identity/v5_b_validation_20261022/run<br>
报告生成：2026-10-22T16:40:38.996743+00:00。本页不包含 API 密钥、请求认证头或数据集中的原文凭据。
