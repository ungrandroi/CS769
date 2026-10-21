# 用 GPT-5-mini 重跑图记忆基线

## 目的

同一套基线已经用 Qwen3.8-27B 和 GPT-4.1 各跑过一次。换成图之后，两个模型的通过数都下降。这次改用 Azure 上的 `gpt-5-mini`（推理强度 medium），题目、图的构建和替换时机不变，看这个下降是否还在。

## 设置

- 模型：Azure 部署 `gpt-5-mini`，服务端返回 `gpt-5-mini-2025-08-07`。`reasoning_effort` medium，`max_completion_tokens` 16384，seed 42。这个模型不接受温度为 0，所以请求里不带 temperature。
- 题目：与前两次相同的 13 个 GorillaFileSystem 题族，各跑 `multi_turn_base` 和 `multi_turn_long_context`，共 26 个条件。每种记忆每题跑一次，共 78 次。
- 协议：每个条件先用 GPT-5-mini 完整跑原文历史。两种图回放同一段第一轮来恢复模拟器，在第二轮用户消息之前把历史换成图，之后由 GPT-5-mini 续跑。第一轮也由 GPT-5-mini 生成，和 Qwen、GPT-4.1 是三条独立轨迹。
- 评分：官方 BFCL 整题评分，第一轮失败也计入三种方法。
- compact 编码在选择字符串字典时用 tiktoken `o200k_base` 计数。编码无损，图的内容不变。

## 结果

| 方法 | GPT-5-mini 通过 | GPT-5-mini 整段平均输入 token | Qwen 通过 | GPT-4.1 通过 |
| --- | --- | --- | --- | --- |
| 原文历史 | 12/26（46.2%） | 39,714 | 18/26（69.2%） | 13/26（50.0%） |
| 状态转移图 | 9/26（34.6%） | 50,554 | 14/26（53.8%） | 10/26（38.5%） |
| 事件图 | 9/26（34.6%） | 56,860 | 17/26（65.4%） | 11/26（42.3%） |

整段输入 = 共用的第一轮 + 该方法的续跑，把每次请求的 `prompt_tokens` 相加，包括工具定义和缓存命中部分。三个模型用各自的 tokenizer，跨模型只能比趋势和量级。三模型的完整对照在 [model_comparison.md](model_comparison.md)。

原文仍然高于两种图。和 Qwen、GPT-4.1 不同的是，这里事件图和状态转移图通过数相同，事件图没有少掉点。两种图的平均输入都比原文更高。

| 方法 | 第一次续跑输入 | 续跑累计输入 | 续跑请求数 | 图记忆平均 token |
| --- | --- | --- | --- | --- |
| 原文历史 | 2,655 | 28,205 | 9.2 | — |
| 状态转移图 | 4,347 | 39,045 | 8.9 | 2,129 |
| 事件图 | 5,581 | 45,351 | 8.5 | 3,362 |

被替换的是第一轮历史，不是整段轨迹。用同一套 tiktoken `o200k_base` 计这段历史的消息正文，26 题平均 382 token（最少 63，最多 1,240）。图记忆是 2,129 和 3,362，26 题里都比这段历史长。第一次续跑输入从 2,655 升到 4,347 和 5,581，增加的部分就是这段更长的图；整段累计输入也因此更高。

### 按切分

| 切分 | 原文历史 | 状态转移图 | 事件图 |
| --- | --- | --- | --- |
| `multi_turn_base` | 7/13 | 6/13 | 6/13 |
| `multi_turn_long_context` | 5/13 | 3/13 | 3/13 |

掉点主要在 long context。base 上只少 1 题。

### 换成图之后的成败变化

| 方法 | 原文通过、图失败 |
| --- | --- |
| 状态转移图 | base_25、long_context_29、long_context_39 |
| 事件图 | base_16、long_context_29、long_context_39 |

反方向（原文失败、图通过）没有。

这 5 次图失败的官方原因都是 `multi_turn:empty_turn_model_response`：模型在某一轮结束时去问用户，后面标准答案还要求的轮次就没有模型回复。long_context_29 的两种图都在续跑的第一轮就停下来，问 1 KB 按 1000 还是 1024 字节换算。base_25 的状态转移图复制完文件就问要不要继续。base_16 的事件图排序之后问要不要写回文件。long_context_39 的两种图做完第一段文件操作后，下一轮是空的。图本身能解码，失败来自模型提前结束任务。

## 第一轮失败

26 个条件里有 6 个第一轮就失败，三种方法一起失败。Qwen 只有 long_context_38 一个；GPT-4.1 有 8 个。

| 条件 | 第一轮发生了什么 |
| --- | --- |
| base_10 / long_context_10 | 直接 `mkdir Projects`，没有进入 workspace |
| base_37 / long_context_37 | `cd temp` 失败后停下来问用户下一步 |
| long_context_16 | 用带路径的 `mv` 做备份，随后自称已经完成 |
| long_context_38 | 删掉文件后 `rmdir` 因目录里还有注入的图片而失败，然后问用户 |

和 GPT-4.1 重叠的是 base_10、long_context_10、base_37、long_context_38。GPT-4.1 第一轮失败、这次第一轮通过的是 base_6、long_context_6、base_16、long_context_9。这次多出来的第一轮失败是 long_context_16、long_context_37。

只看第一轮通过的 20 个条件，通过数是原文 12/20、状态转移图 9/20、事件图 9/20。掉点和全量 26 题相同：第一轮失败只拉低绝对分数，不改变原文和图的比较。

## 和前两次的关系

三个模型都是原文高于图，图也没有省下输入 token。GPT-5-mini 的绝对分数接近 GPT-4.1（原文 12/26 对 13/26），低于 Qwen（18/26）。事件图在 Qwen 和 GPT-4.1 上少掉 1 题，在 GPT-5-mini 上和状态转移图打平。逐题上，三个模型掉点的题仍然不太重合，详见汇总表。

## 注意事项

- 每种方法每题只跑一次。9/26 和 12/26 差 3 题，方向稳定，具体题号不稳定。
- 推理 token 算在输出里。这次输出 140,063 token 中有 107,584 是推理 token。没有 `finish_reason=length`，16384 的上限没有截断回答。
- `multi_turn_long_context_16` 的原文历史第一次尝试中断过：模型某次工具参数 JSON 里重复了 `file_name`。BFCL 评分按普通 JSON 保留最后一个键，共享的请求编码器原来会直接报错。GPT 运行进程里改成同样保留最后一个键之后，这次尝试作废，正式结果是重跑的那一次。作废目录留在该题的 `identity.failed-duplicate-key/`，不计入分数。Qwen 用的那个严格解析函数没有改。
- 温度不能设为 0，seed 42 仍然带上。同一道题重跑，轨迹不一定逐字节相同。

## 用量

实际请求 816 次，输入 3,226,868 token（其中缓存命中 2,774,272），输出 140,063 token（其中推理 107,584）。按牌价输入 $0.25、缓存输入 $0.025、输出 $2（每百万 token）估算约 $0.46。结束原因：`tool_calls` 620 次，`stop` 196 次。

## 文件与复现

- 原始记录、冻结代码和计划：[../gpt5mini_experiment/](../gpt5mini_experiment/)
- 自动生成的逐题对照：[../gpt5mini_experiment/comparison.md](../gpt5mini_experiment/comparison.md)，汇总在同目录的 `summary.json`、`task-results.csv`
- 三模型汇总：[model_comparison.md](model_comparison.md)
- 代码：`scripts/workflows/gpt41_task.py`、`gpt41_batch.py`、`gpt41_report.py`（GPT-4.1 与 GPT-5-mini 共用这套入口，用 `--deployment` 和 `--reasoning-effort` 区分）

```bash
export PYTHONPATH=scripts:vendor/gorilla/berkeley-function-call-leaderboard
python scripts/manage.py run gpt41 --output DIR --deployment gpt-5-mini --reasoning-effort medium
python scripts/manage.py audit gpt41 --output DIR
```

Azure 密钥从 `~/.azure_openai_env` 读取，不写入记录。
