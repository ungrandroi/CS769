# 用 GPT-4.1 重跑图记忆基线

## 目的

Qwen 基线里，把历史换成图之后通过数下降：原文历史 18/26，状态转移图 14/26，事件图 17/26。这次全程改用 GPT-4.1 作为 agent，题目、图的构建和替换时机都不变，看这个下降是不是只出现在 Qwen 上。

## 设置

- 模型：Azure 部署 `gpt-4.1`，服务端返回 `gpt-4.1-2025-04-14`。温度 0，seed 42，`max_tokens` 4096。
- 题目：与 Qwen 基线相同的 13 个 GorillaFileSystem 题族（1、3、6、9、10、12、16、25、26、29、37、38、39），各跑 `multi_turn_base` 和 `multi_turn_long_context`，共 26 个条件。每种记忆每题跑一次，共 78 次。
- 协议：每个条件先用 GPT-4.1 完整跑原文历史。两种图回放同一段第一轮来恢复模拟器，在第二轮用户消息之前把历史换成图，之后由 GPT-4.1 续跑。第一轮也由 GPT-4.1 生成，所以和 Qwen 基线是两条独立的轨迹，不共用 Qwen 的前缀。
- 评分：官方 BFCL 整题评分，第一轮失败也计入三种方法，不按分数重跑。
- 与 Qwen 基线的唯一实现差异：compact 编码在选择字符串字典时，用 GPT-4.1 的 tokenizer（tiktoken `o200k_base`）计数，因为本机没有 Qwen 的原生 tokenizer。编码无损，图的内容不变。

## 结果

| 方法 | GPT-4.1 通过 | GPT-4.1 整段平均输入 token | Qwen 通过 | Qwen 整段平均输入 token |
| --- | --- | --- | --- | --- |
| 原文历史 | 13/26（50.0%） | 31,460 | 18/26（69.2%） | 55,529 |
| 状态转移图 | 10/26（38.5%） | 38,786 | 14/26（53.8%） | 77,791 |
| 事件图 | 11/26（42.3%） | 43,408 | 17/26（65.4%） | 89,784 |

整段输入 = 共用的第一轮 + 该方法的续跑，把每次请求的 `prompt_tokens` 相加，包括工具定义和缓存命中部分。两边用各自的 tokenizer，跨模型只能比趋势和量级。

两个模型的排序一致：原文 > 事件图 > 状态转移图。换成图之后，平均输入 token 也同样变多。

| 方法 | GPT-4.1 第一次续跑输入 | GPT-4.1 续跑累计输入 | GPT-4.1 续跑请求数 | Qwen 第一次续跑输入 | Qwen 续跑累计输入 | Qwen 续跑请求数 |
| --- | --- | --- | --- | --- | --- | --- |
| 原文历史 | 2,438 | 23,428 | 8.5 | 3,892 | 38,257 | 8.6 |
| 状态转移图 | 4,540 | 30,755 | 7.3 | 6,739 | 60,519 | 9.3 |
| 事件图 | 4,525 | 35,376 | 8.0 | 7,702 | 72,512 | 9.8 |

GPT-4.1 换成图之后续跑请求反而略少，但每次请求都带着平均约 2,400 token 的图记忆，所以累计输入仍然更高。图记忆在第二轮开始时比原文历史还长，第一次续跑的输入几乎翻倍。

### 按切分

| 切分 | 方法 | GPT-4.1 通过 | Qwen 通过 |
| --- | --- | --- | --- |
| `multi_turn_base` | 原文历史 | 7/13 | 9/13 |
| `multi_turn_base` | 状态转移图 | 6/13 | 8/13 |
| `multi_turn_base` | 事件图 | 6/13 | 9/13 |
| `multi_turn_long_context` | 原文历史 | 6/13 | 9/13 |
| `multi_turn_long_context` | 状态转移图 | 4/13 | 6/13 |
| `multi_turn_long_context` | 事件图 | 5/13 | 8/13 |

### 换成图之后的成败变化

| 方法 | GPT-4.1：原文通过、图失败 | Qwen：原文通过、图失败 |
| --- | --- | --- |
| 状态转移图 | base_3、long_context_3、long_context_37 | base_1、long_context_1、long_context_9、long_context_10 |
| 事件图 | base_3、long_context_3 | base_1、long_context_9、long_context_10 |

反方向（原文失败、图通过）：GPT-4.1 没有；Qwen 在事件图上有 base_9、long_context_25。

两个模型掉点的题几乎不重合。图记忆让 agent 在哪道题上出错跟模型有关，但掉点本身两个模型都有。

一个例子是 `multi_turn_base_3`。GPT-4.1 拿到图之后，第一次带路径的 `cp` 报错，就结束这一轮去回复用户了。原文跑法里遇到同样的错误，它会先 `cd` 进目录再重试，最后通过。

## GPT-4.1 原文分数为什么比 Qwen 低

GPT-4.1 的原文分数低，主要因为 26 个条件里有 8 个第一轮就失败；Qwen 只有 `multi_turn_long_context_38` 一个。

| 条件 | 用户要求 | GPT-4.1 | Qwen |
| --- | --- | --- | --- |
| base_6 / long_context_6 | 在 communal 文件夹里建文件 | 直接 `touch`，文件建在了根目录 | `pwd`、`ls`、`cd communal`，再 `touch` |
| base_10 / long_context_10 | 在 workspace 里建 Projects | 直接 `mkdir`，没进 workspace | `pwd`、`ls`、`cd workspace`，再 `mkdir` |
| base_16 | 复制到 archives 并改名 | 先复制改名，再用 `archives/...`、`../...` 这类路径来回 `mv` | `cd research`，`cp` 进 archives，`cd archives`，再改名 |
| base_37 | 进 temp，统计每个文件行数 | `cd temp` 报错（本来就在 temp 里），`ls` 之后停下来问用户 | 同样报错，接着 `pwd`、`ls`，确认位置后直接 `wc` |
| long_context_9 | “我记得 Documentation 里有 FinalReport.txt” | 用 `find` 找到后回复 | `ls`、`cd Documentation`、`ls` 后回复 |
| long_context_38 | 删掉文件和目录 | 带路径 `rm`，同时并行 `rmdir`，都失败后去问用户 | 也失败 |

这 8 个失败归成四类：

1. **不先确认位置就动手（4 个）。** GPT-4.1 默认自己已经在用户说的目录里，一次调用就做。Qwen 几乎每题都先 `pwd`、`ls`，再 `cd`。状态检查比对整棵文件树，建错一层目录就判失败。
2. **当成真实 shell，用路径当参数（base_16、long_context_38）。** 工具说明写明 `cd` 一次只能进一层，`touch`、`cat`、`mv`、`cp` 不允许路径。
3. **出错就停下来问用户（base_37、long_context_38）。** Qwen 遇到同样的报错，会自己多查一步再继续。
4. **合理的替代做法不被评分认可（long_context_9）。** BFCL 的 `response_checker` 要求标准答案每一步的执行结果都出现在模型的执行结果里。标准答案是 `cd(folder='Documentation')`；GPT-4.1 用 `find` 确认了文件，少了 `cd` 那条结果。

这和参数量关系不大。这里考的不是知识或推理，而是遵守一个非标准环境的约定，并贴合标准轨迹，主要取决于后训练学到的行为习惯。GPT-4.1 是 2025 年 4 月的通用模型，偏向少调用、回答简洁、不确定就问用户。Qwen3.x 针对智能体工具调用做过专门训练，先探查再动手的习惯正好符合这套评分。请求里也没有系统提示讲文件系统规则，GPT-4.1 只能靠自己的 shell 先验。

这和公开榜单一致。[BFCL V4 多轮榜](https://gorilla.cs.berkeley.edu/leaderboard.html)上，GPT-4.1（FC）多轮 38.88%（base 47.5%，long context 43%），Qwen3-32B（FC）47.87%。这次 GPT-4.1 原文跑法是 base 7/13（54%）、long context 6/13（46%），和榜单基本一致。

## 对图记忆结论的影响

第一轮失败的条件，三种方法都失败，所以它们只拉低 GPT-4.1 的绝对分数，不影响原文和图的比较。只看第一轮通过的 18 个条件，GPT-4.1 是原文 13/18、状态转移图 10/18、事件图 11/18，掉点和全量 26 题相同。

结论：换成图之后掉点、事件图比状态转移图掉得少，这两点在 Qwen 和 GPT-4.1 上都成立，不是 Qwen 独有的问题。两种图在两个模型上也都没有省下输入 token。

## 注意事项

- 每种方法每题只跑一次，26 题上差 2 到 3 题不算稳定。
- Azure 在温度 0 加固定 seed 下也不完全确定。同一道 `multi_turn_base_1`，冒烟测试用了 20 次请求，正式运行用了 23 次。
- 想让 GPT-4.1 的绝对分数更可比，可以在三种方法里加同一段说明文件系统规则的系统提示，但那样就和 Qwen 基线的协议不同，需要单独标注。

## 用量

实际请求 711 次，输入 2,537,365 token（其中缓存命中 2,079,872），输出 23,302 token，按牌价约 2.14 美元。

## 文件与复现

- 原始记录、冻结代码和计划：[../gpt41_experiment/](../gpt41_experiment/)
- 自动生成的逐题对照：[../gpt41_experiment/comparison.md](../gpt41_experiment/comparison.md)，汇总在同目录的 `summary.json`、`task-results.csv`
- 代码：`scripts/workflows/gpt41_task.py`、`gpt41_batch.py`、`gpt41_report.py`

复现时用 vendor 里钉住的 BFCL，Azure 密钥从 `~/.azure_openai_env` 读取，不进入记录：

```bash
export PYTHONPATH=scripts:vendor/gorilla/berkeley-function-call-leaderboard
python scripts/manage.py run gpt41 --output DIR --deployment gpt-4.1
python scripts/manage.py audit gpt41 --output DIR
```
