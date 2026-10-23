# 图记忆表示实验简报

[报告目录](README.md) · [GitHub 阅读版](experiment-summary.md)

截至 2026-10-22 · 已完成的 BFCL 实验 · 每个引用均连接至具体实验记录或代码证据

## 实验做了什么

我们的实验以 `main@a7f8492` 已有的构图与 compact 编解码为基础：从 identity 的可见对话历史中，按顺序读取用户要求、assistant 陈述、工具调用及返回，构建图后再改变模型接收记忆的形式。 [\[M0\]](experiment-evidence.md#M0)

**A（identity）**保留原生多消息历史；最早的图分支在第一轮用户任务结束、第二轮请求之前，把这段历史替换成一条 assistant 记忆消息。 [\[M1\]](experiment-evidence.md#M1)

**S（状态转移图，v1-compact）**将已观察知识表示为状态快照节点，以工具调用连接前后状态；**E（事件图，v2-compact）**拆成执行事件、共享对象和版本化事实，旧事实退出当前有效集合但仍保留证据。 [\[M2\]](experiment-evidence.md#M2)

两种 compact 都保存源消息用于审计，并向模型提供用户目标、工具输入、原始返回和 assistant 陈述等图文本证据；“可逆”指图数据编解码，不等于原生消息协议逐字恢复，也不保证节省 token。 [\[M3\]](experiment-evidence.md#M3)

**ED（Event Graph-Dedup）**进一步去重可精确重建的来源关系；后来的 **R（V2-readable）**改为“已知状态索引＋按顺序排列的完整可见历史证据”，减少审计字段的展示，但仍是一条 assistant 记忆消息。 [\[E2\]](experiment-evidence.md#E2)[\[M4\]](experiment-evidence.md#M4)

**B（V3 开始采用）**从图的证据层完整恢复原生消息、角色及工具调用—返回关联，再额外附加一条简短 assistant 图索引；索引是第一轮结束时的快照，后续不动态刷新。 [\[M5\]](experiment-evidence.md#M5)[\[E4\]](experiment-evidence.md#E4)

**D（V4 用户块方案）**保留同一原生历史，把索引及来源包装放到第二轮原用户消息的 `application_memory` 块中；V4 先做两 GPT 旧集回归，再对 GPT-5-mini 的 6 个条件随机交错运行 A/B/D 各 10 次，随后 V5 冻结 B，扩大到含文件系统工具的 base/long_context 全部合格新题。 [\[M6\]](experiment-evidence.md#M6)[\[E5\]](experiment-evidence.md#E5)[\[E6\]](experiment-evidence.md#E6)[\[E7\]](experiment-evidence.md#E7)

这些阶段没有训练或运行风险驱动的压缩器；后期 B 的实验检验的是“完整历史旁加入图索引”的影响，尚未检验删除原始历史后仅依赖图的能力。 [\[M7\]](experiment-evidence.md#M7)

## 结果

| 实验阶段 | 模型 | 样本与重复 | 表示顺序 | 官方通过数／率 | 平均续跑输入 token | 记录 |
| --- | --- | --- | --- | --- | --- | --- |
| 最初图替换 | Qwen（27B，Q8_0） | 26 条件 / 13 族<br>× 1 次 = 26 条/组 | A<br>S<br>E | 18/26（69.2%）<br>14/26（53.8%）<br>17/26（65.4%） | 38,257<br>60,519<br>72,512 | [\[E1\]](experiment-evidence.md#E1) |
| 最初图替换 | GPT-4.1 | 26 条件 / 13 族<br>× 1 次 = 26 条/组 | A<br>S<br>E | 13/26（50.0%）<br>10/26（38.5%）<br>11/26（42.3%） | 23,428<br>30,755<br>35,376 | [\[E1\]](experiment-evidence.md#E1) |
| 最初图替换 | GPT-5-mini | 26 条件 / 13 族<br>× 1 次 = 26 条/组 | A<br>S<br>E | 12/26（46.2%）<br>9/26（34.6%）<br>9/26（34.6%） | 28,205<br>39,045<br>45,351 | [\[E1\]](experiment-evidence.md#E1) |
| 关系编码去重 | Qwen（27B，Q8_0） | 26 条件 / 13 族<br>× 1 次 = 26 条/组 | A<br>E<br>ED | 18/26（69.2%）<br>17/26（65.4%）<br>15/26（57.7%） | 38,257<br>72,512<br>63,983 | [\[E2\]](experiment-evidence.md#E2) |
| V2 可读格式 | GPT-4.1 | 4 条件 / 2 族<br>× 3 次 = 12 条/组 | A<br>E<br>R | 12/12（100.0%）<br>6/12（50.0%）<br>9/12（75.0%） | 11,250<br>16,725<br>9,642 | [\[E3\]](experiment-evidence.md#E3) |
| V2 可读格式 | GPT-5-mini | 5 条件 / 4 族<br>× 3 次 = 15 条/组 | A<br>E<br>R | 12/15（80.0%）<br>11/15（73.3%）<br>10/15（66.7%） | 16,244<br>32,076<br>16,576 | [\[E3\]](experiment-evidence.md#E3) |
| V3 原生历史＋B | GPT-4.1 | 11 条件 / 7 族<br>× 1 次 = 11 条/组 | A<br>B | 7/11（63.6%）<br>7/11（63.6%） | 22,560<br>20,052 | [\[E4\]](experiment-evidence.md#E4) |
| V3 原生历史＋B | GPT-5-mini | 16 条件 / 10 族<br>× 3 次 = 48 条/组 | A<br>B | 19/48（39.6%）<br>22/48（45.8%） | 29,352<br>26,406 | [\[E4\]](experiment-evidence.md#E4) |
| V3 原生历史＋B | Claude Sonnet 5.5 | 19 条件 / 10 族<br>× 3 次 = 57 条/组 | A<br>B | 32/57（56.1%）<br>37/57（64.9%） | 43,507<br>45,226 | [\[E4\]](experiment-evidence.md#E4) |
| V4 用户块回归 | GPT-4.1 | 16 条件 / 10 族<br>× 1 次 = 16 条/组 | A<br>D | 11/16（68.8%）<br>11/16（68.8%） | 21,243<br>21,165 | [\[E5\]](experiment-evidence.md#E5) |
| V4 用户块回归 | GPT-5-mini | 19 条件 / 11 族<br>× 3 次 = 57 条/组 | A<br>D | 32/57（56.1%）<br>26/57（45.6%） | 26,672<br>26,349 | [\[E5\]](experiment-evidence.md#E5) |
| 三组放置诊断 | GPT-5-mini | 6 条件 / 5 族<br>× 10 次 = 60 条/组 | A<br>B<br>D | 32/60（53.3%）<br>27/60（45.0%）<br>24/60（40.0%） | 22,739<br>25,554<br>24,641 | [\[E6\]](experiment-evidence.md#E6) |
| V5 新验证集 | GPT-4.1 | 45 条件 / 25 族<br>× 1 次 = 45 条/组 | A<br>B | 28/45（62.2%）<br>28/45（62.2%） | 24,546<br>25,321 | [\[E7\]](experiment-evidence.md#E7) |
| V5 新验证集 | GPT-5-mini | 43 条件 / 25 族<br>× 3 次 = 129 条/组 | A<br>B | 51/129（39.5%）<br>44/129（34.1%） | 32,387<br>36,557 | [\[E7\]](experiment-evidence.md#E7) |

表内每列按“表示顺序”逐行对应；token 是每条续跑中全部请求的输入 token 之和再取平均，包含工具定义、重复送入的历史和缓存命中部分，不含输出 token，也不加共享首轮生成成本。 [\[T\]](experiment-evidence.md#T)

各阶段样本与筛选规则不同，不能把跨阶段通过率变化当成受控改进；ED 行的 A/E 复用原基线，重复次数及 base/long_context 也不能当成独立题族。 [\[T\]](experiment-evidence.md#T)[\[E2\]](experiment-evidence.md#E2)[\[E7\]](experiment-evidence.md#E7)

Qwen 的本地记录名为 `Qwen3.8-27B-Q8_0`，Claude 的服务端记录名为 `claude-sonnet-5-5`；跨模型 token 不作为统一尺度，本表主要用于同一行内的表示对比。 [\[M8\]](experiment-evidence.md#M8)[\[E4\]](experiment-evidence.md#E4)[\[T\]](experiment-evidence.md#T)

## 重点发现

最初三个模型在 S/E 图替换下均出现通过数下降、续跑输入增加；ED 虽把 Qwen 的输入从 E 的 72,512 降至 63,983 token，通过数却由 17/26 降至 15/26，因此缩短图编码没有自动改善成功率。 [\[E1\]](experiment-evidence.md#E1)[\[E2\]](experiment-evidence.md#E2)

V2 的 9 个首轮边界上，R 的记忆正文合计为 3,077 token，E 为 26,794，减少 88.5%，但 R 的正式通过率仍低于 A；9 个 history1000 既有检查点也完成了离线计数，这不是新增 Qwen 续跑。 [\[E3\]](experiment-evidence.md#E3)[\[O1\]](experiment-evidence.md#O1)

V3 的小样本中，B 在三模型的总通过数持平或上升，但 mini 仍出现一次多余写入导致的新增失败，Claude 也出现把 assistant 索引当作先前自己回复来评论的现象；这些结果不能证明 B 与 A 等价。 [\[E4\]](experiment-evidence.md#E4)

V4 的旧集回归与 180 条放置诊断没有建立 D 的优势；诊断中 A/B/D 为 32/60、27/60、24/60，选择 B 是保留后续研究格式，而非已通过准确率验收。 [\[E5\]](experiment-evidence.md#E5)[\[E6\]](experiment-evidence.md#E6)

V5 共筛选 144 个模型×条件，排除 35 个首轮失败及另外 21 个首轮通过但索引为空的条件，完成 348 条正式续跑；按预定的模型、题族等权主分析，B−A 为 −2.67 个百分点，95% 区间为 \[−7.81，+2.42\]，没有达到下限高于 −5 的保率标准，结论为证据不足。 [\[E7\]](experiment-evidence.md#E7)

V5 中 GPT-4.1 虽总分持平，仍有 2 次新增失败与 2 次改善；mini 有 13 次新增失败、6 次改善，其中既有正确回答却未产生官方期望工具结果的情况，也有把用户 ID 当姓名查询后漏发消息、反复写不存在的文件及多余写入等实际执行问题。 [\[E7\]](experiment-evidence.md#E7)

按排除推文草稿后的更正口径，官方 empty_turn 失败中 A 有 7 次、B 有 11 次给出了正确的文件内容或数值答案；报告保留官方分数，同时单列行为解释，不将这些回合直接改判为整题成功。 [\[E7\]](experiment-evidence.md#E7)

当前能支持的结论是：图数据保留、原生历史重建和轻量索引接入已经实现并通过完整性核对，R 相对 E 减少了离线记忆正文开销；“加入图后保持原始历史通过率”尚未得到 V5 的统计证据支持。 [\[M5\]](experiment-evidence.md#M5)[\[O1\]](experiment-evidence.md#O1)[\[E7\]](experiment-evidence.md#E7)

详细来源：[逐句证据索引、原始报告与字段定位](experiment-evidence.md) · [总表精确数据](evidence/experiment-summary-data.json) · [最新 V5 完整结果报告](v5-b-validation-results.md)
