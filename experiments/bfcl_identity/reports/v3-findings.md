# 原生历史＋图索引：三模型 BFCL 结果

**归档说明：**这是该阶段完成时的报告，文中的“下一步／尚未启动”按当时状态理解；跨阶段结论以[总报告](experiment-summary.md)及[V5 最终结果](v5-b-validation-results.md)为准。[报告目录](README.md) · [GitHub 阅读版](v3-findings.md)

阅读范围：下文“总体通过率保持”只描述该轮小样本的通过数持平或上升，不是非劣效检验结论；[V5](v5-b-validation-results.md) 的预定保率标准未通过，结论为证据不足。

**本轮总体通过率保持，但不能声称没有任何行为退化。** GPT-4.1 持平，GPT-5-mini 和 Claude 增加通过数；仍存在一次新增错误写入，以及 Claude 将索引误认成自己上次回复的副作用。

实验于 2026-10-21 22:50 UTC 完成，共 232 条主实验轨迹，未触发 GPT-4.1 追加测试。已核查全部原生历史、评分、token 计数，并逐条查看全部 10 对评分不一致的轨迹。

| 模型 | identity | 原生历史＋图索引 | A过B不过 / A不过B过 | 逐题净下降 |
| --- | --- | --- | --- | --- |
| GPT-4.1 | 7/11（63.6%） | 7/11（63.6%） | 0 / 0 | 0 |
| GPT-5-mini | 19/48（39.6%） | 22/48（45.8%） | 1 / 4 | 0 |
| Claude Sonnet 5.5 | 32/57（56.1%） | 37/57（64.9%） | 0 / 5 | 0 |

GPT-4.1：11题×1次；GPT-5-mini：16题×3次；Claude：19题×3次。表中分母是每组轨迹数，重复不是独立题目，模型题集不同。Claude 的 A/B 重复编号只是对齐展示，不能假定随机性耦合。

**唯一新增评分失败：GPT-5-mini 的 base_16，seed 44。** 两组的 `sort` 都返回一行文本。identity 随后直接调用 `wc`，得到 1；图组先用 `echo` 插入两个换行，将文件改成三行，再得到 3。官方确认文件内容被错误修改。这是实际行为错误，不是单纯评分格式问题。

同题 seed 43 的方向相反：identity 错误插入换行，图组通过。因此该题两组都为 2/3。索引只有目录状态和文件名，不包含文件内容或行数；旧 V2-readable 也出现过同类错误。证据支持“模型共有的文件格式误读／多余写入脆弱性”，不足以证明错误由图索引造成，也不能把它当作已经排除的风险。

**Claude 的索引位置副作用。** 图组 10/57 条轨迹在可见正文中把 `GRAPH INDEX` 当成自己上次误发的笔记，identity 同口径为 0/57。这十条中五条通过、五条失败，没有新增 A过B不过，因此副作用与准确率损失要分开描述。

> The “GRAPH INDEX” block at the end of my last message didn’t belong there.

例：Claude base_38，repeat 1，native.jsonl 第4行。这里只统计模型生成的 text 块，排除了 thinking 块和输入历史。

**通过数增加的具体来源。**

| 模型与条件 | 通过次数变化 | 轨迹解释 |
| --- | --- | --- |
| GPT-5-mini · base_16 | 2/3 → 2/3 | seed43修复一次、seed44新增一次相同的换行写入错误，互相抵消。 |
| GPT-5-mini · long_context_29 | 0/3 → 1/3 | 图组写入官方要求的上一轮请求；identity写入当前指令。属于指代选择变化。 |
| GPT-5-mini · long_context_39 | 0/3 → 1/3 | 两组都正确答出index.html；图组重新ls满足评分，identity复用已有证据被判empty-turn。不能称为语义能力修复。 |
| GPT-5-mini · base_26 | 0/3 → 1/3 | identity停下来请求确认；图组克服echo报错后创建了评测要求的文件。这不是实际Word文档编码有效性的测试。 |
| Claude · base_29 / long_context_29 | 各1/3 → 3/3 | 四次增益都来自last question的指代选择：图组写上一轮请求；identity写首轮带问号的句子。图索引不含答案文本，不能据此证明图提供了推理答案。 |
| Claude · base_6 | 0/3 → 1/3 | 图组保留用户单行统计原文；identity将其改成三行。 |

**未参与调格式的新验证题，提升很小。** 总体增益主要来自开发题族，不能把全部232条视为盲测。

| 模型 | 验证条件数 | identity | 原生历史＋图索引 |
| --- | --- | --- | --- |
| GPT-4.1 | 9 | 5/9 | 5/9 |
| GPT-5-mini | 11 | 11/33 | 12/33 |
| Claude Sonnet 5.5 | 13 | 18/39 | 19/39 |

**GPT-4.1 保持评分，但工具行为并非处处改善。** 11题的通过／失败集合完全一致。base_1 的重复 ls 从15次减到3次；long_context_1 却多出7次工具调用，含错误grep和重复ls，两组最后都通过。不能把输入token下降解释成稳定消除了循环。

**两组共同失败也需要分开看。** 25题族常在复制后继续操作原目录的同名文件，没有进入目标目录，官方要求的操作返回因此缺失；Claude 10题族会保留用户未要求的扩展名；long_context_26 的实际展示列表末尾为新增图片，标准答案却仍要求file3.txt，存在指代与标准答案不一致。上述评分全部保留，不统一标成图记忆丢失或提前停止。

**Token 为辅助观察。** 在同题同编号两组都通过的子集上，续跑输入token变化如下。它包含多次请求重复输入历史，不只是索引大小；本轮没有压缩，变化来自轨迹长度和请求内容，且排除失败后的统计有选择性。

| 模型 | 共同成功次数 | identity输入token | 图组输入token | 变化 |
| --- | --- | --- | --- | --- |
| GPT-4.1 | 7 | 163,673 | 146,116 | -10.7% |
| GPT-5-mini | 18 | 332,338 | 311,147 | -6.4% |
| Claude Sonnet 5.5 | 32 | 1,175,690 | 1,186,513 | +0.9% |

**下一步优先级。** 保留当前完整原生证据作为基线，先做索引放置位置的单因素探针；同时检查base_16这类多余写入的发生频率，再扩大新验证题。暂时不压缩，不用针对单题的行为命令掩盖问题。当前结果支持继续走原生历史加索引路线，尚不覆盖纯图替代历史。

<details>
<summary>全部46个模型×题目条件</summary>

| 模型 | 题目 | 分组 | identity | 图组 | 下降编号 | 上升编号 |
| --- | --- | --- | --- | --- | --- | --- |
| Claude Sonnet 5.5 | base_1 | 验证 | 3/3 | 3/3 | — | — |
| Claude Sonnet 5.5 | base_10 | 验证 | 0/3 | 0/3 | — | — |
| Claude Sonnet 5.5 | base_12 | 开发 | 3/3 | 3/3 | — | — |
| Claude Sonnet 5.5 | base_25 | 验证 | 0/3 | 0/3 | — | — |
| Claude Sonnet 5.5 | base_26 | 验证 | 3/3 | 3/3 | — | — |
| Claude Sonnet 5.5 | base_29 | 开发 | 1/3 | 3/3 | — | 1,3 |
| Claude Sonnet 5.5 | base_37 | 验证 | 3/3 | 3/3 | — | — |
| Claude Sonnet 5.5 | base_38 | 验证 | 3/3 | 3/3 | — | — |
| Claude Sonnet 5.5 | base_39 | 开发 | 3/3 | 3/3 | — | — |
| Claude Sonnet 5.5 | base_6 | 验证 | 0/3 | 1/3 | — | 1 |
| Claude Sonnet 5.5 | long_context_1 | 验证 | 3/3 | 3/3 | — | — |
| Claude Sonnet 5.5 | long_context_10 | 验证 | 0/3 | 0/3 | — | — |
| Claude Sonnet 5.5 | long_context_12 | 开发 | 3/3 | 3/3 | — | — |
| Claude Sonnet 5.5 | long_context_25 | 验证 | 0/3 | 0/3 | — | — |
| Claude Sonnet 5.5 | long_context_26 | 验证 | 0/3 | 0/3 | — | — |
| Claude Sonnet 5.5 | long_context_29 | 开发 | 1/3 | 3/3 | — | 1,3 |
| Claude Sonnet 5.5 | long_context_37 | 验证 | 3/3 | 3/3 | — | — |
| Claude Sonnet 5.5 | long_context_39 | 开发 | 3/3 | 3/3 | — | — |
| Claude Sonnet 5.5 | long_context_6 | 验证 | 0/3 | 0/3 | — | — |
| GPT-4.1 | base_1 | 验证 | 1/1 | 1/1 | — | — |
| GPT-4.1 | base_12 | 开发 | 1/1 | 1/1 | — | — |
| GPT-4.1 | base_25 | 验证 | 0/1 | 0/1 | — | — |
| GPT-4.1 | base_26 | 验证 | 1/1 | 1/1 | — | — |
| GPT-4.1 | base_38 | 验证 | 1/1 | 1/1 | — | — |
| GPT-4.1 | base_9 | 验证 | 0/1 | 0/1 | — | — |
| GPT-4.1 | long_context_1 | 验证 | 1/1 | 1/1 | — | — |
| GPT-4.1 | long_context_12 | 开发 | 1/1 | 1/1 | — | — |
| GPT-4.1 | long_context_25 | 验证 | 0/1 | 0/1 | — | — |
| GPT-4.1 | long_context_26 | 验证 | 0/1 | 0/1 | — | — |
| GPT-4.1 | long_context_37 | 验证 | 1/1 | 1/1 | — | — |
| GPT-5-mini | base_1 | 验证 | 3/3 | 3/3 | — | — |
| GPT-5-mini | base_12 | 开发 | 3/3 | 3/3 | — | — |
| GPT-5-mini | base_16 | 开发 | 2/3 | 2/3 | 44 | 43 |
| GPT-5-mini | base_25 | 验证 | 2/3 | 2/3 | — | — |
| GPT-5-mini | base_26 | 验证 | 0/3 | 1/3 | — | 43 |
| GPT-5-mini | base_38 | 验证 | 3/3 | 3/3 | — | — |
| GPT-5-mini | base_6 | 验证 | 0/3 | 0/3 | — | — |
| GPT-5-mini | base_9 | 验证 | 0/3 | 0/3 | — | — |
| GPT-5-mini | long_context_1 | 验证 | 3/3 | 3/3 | — | — |
| GPT-5-mini | long_context_12 | 开发 | 3/3 | 3/3 | — | — |
| GPT-5-mini | long_context_25 | 验证 | 0/3 | 0/3 | — | — |
| GPT-5-mini | long_context_26 | 验证 | 0/3 | 0/3 | — | — |
| GPT-5-mini | long_context_29 | 开发 | 0/3 | 1/3 | — | 43 |
| GPT-5-mini | long_context_39 | 开发 | 0/3 | 1/3 | — | 42 |
| GPT-5-mini | long_context_6 | 验证 | 0/3 | 0/3 | — | — |
| GPT-5-mini | long_context_9 | 验证 | 0/3 | 0/3 | — | — |

</details>

<details>
<summary>Claude 误认索引的10条可见证据</summary>

**multi_turn_base_6 · repeat 3 · 失败**

> I added your statistics to `Annual_Report_2023.docx` in the `communal` folder. I read the file back to check, and it contains:<br>
> <br>
> ```<br>
> Company Earning: 2000<br>
> Company Expenditure: 500<br>
> Company Name: Gorilla<br>
> ```<br>
> <br>
> I wrote it as plain text, so a word processor may treat the file differently from a formatted .docx.<br>
> <br>
> Also, my last message ended with a "GRAPH INDEX" block that you didn't ask for. It was an error on my part, so please ignore it.

`/home/ruqi/public/CS769/experiments/bfcl_identity/v3_native_20261021_r2/continuations/runs/claude-sonnet-5-5/multi_turn_base_6/primary/3/native-graph-index/native.jsonl:6`

**multi_turn_long_context_6 · repeat 1 · 失败**

> I added your statistics to `Annual_Report_2023.docx` in the communal folder. The file now reads:<br>
> <br>
> ```<br>
> Company Earning: 2000<br>
> Company Expenditure: 500<br>
> Company Name: Gorilla<br>
> ```<br>
> <br>
> My last message ended with a block labeled "GRAPH INDEX". That was a stray internal note, not something you need to act on, so please ignore it.<br>
> <br>
> I wrote the statistics as plain text, so Word may not open the file as a formatted document. I can add more sections or change the layout if you'd like.

`/home/ruqi/public/CS769/experiments/bfcl_identity/v3_native_20261021_r2/continuations/runs/claude-sonnet-5-5/multi_turn_long_context_6/primary/1/native-graph-index/native.jsonl:6`

**multi_turn_long_context_6 · repeat 2 · 失败**

> I added the statistics to `Annual_Report_2023.docx` in the communal folder. I read the file back to check, and it contains:<br>
> <br>
> ```<br>
> Company Earning: 2000<br>
> Company Expenditure: 500<br>
> Company Name: Gorilla<br>
> ```<br>
> <br>
> I wrote the content as plain text. Word may not open it correctly as a real `.docx` file. I can add more details or change the layout if you'd like.<br>
> <br>
> My previous reply ended with a block labeled "GRAPH INDEX". It was stray text and had nothing to do with your request, so please ignore it.

`/home/ruqi/public/CS769/experiments/bfcl_identity/v3_native_20261021_r2/continuations/runs/claude-sonnet-5-5/multi_turn_long_context_6/primary/2/native-graph-index/native.jsonl:6`

**multi_turn_long_context_12 · repeat 1 · 通过**

> `summary.txt` in `Documents` now contains only "quantum computing". I read the file back to check.<br>
> <br>
> My last message ended with a "GRAPH INDEX" block that you didn't ask for. Please ignore it.

`/home/ruqi/public/CS769/experiments/bfcl_identity/v3_native_20261021_r2/continuations/runs/claude-sonnet-5-5/multi_turn_long_context_12/primary/1/native-graph-index/native.jsonl:6`

**multi_turn_long_context_12 · repeat 3 · 通过**

> `summary.txt` in `Documents` now contains only "quantum computing". I read the file back to check, and that text is all it holds.<br>
> <br>
> My previous reply ended with a "GRAPH INDEX" block of notes about the directory state. You didn't ask for it, and it didn't belong in my answer. Please ignore it.

`/home/ruqi/public/CS769/experiments/bfcl_identity/v3_native_20261021_r2/continuations/runs/claude-sonnet-5-5/multi_turn_long_context_12/primary/3/native-graph-index/native.jsonl:6`

**multi_turn_long_context_26 · repeat 2 · 失败**

> The last file in the list, `image_1912245706439755759.jpg`, is empty. The terminal showed no content for it. It may be a placeholder, or it may not hold readable text. A `.jpg` is normally binary image data, and `cat` can't display that in a useful way anyway.<br>
> <br>
> I can check the other files if you want. `file1.txt`, `file2.txt` and `file3.txt` are the most likely to have readable content.<br>
> <br>
> One more thing. The end of my previous reply had a "GRAPH INDEX" block that you didn't ask for. It was a stray note and isn't part of the directory listing, so please ignore it.

`/home/ruqi/public/CS769/experiments/bfcl_identity/v3_native_20261021_r2/continuations/runs/claude-sonnet-5-5/multi_turn_long_context_26/primary/2/native-graph-index/native.jsonl:4`

**multi_turn_long_context_26 · repeat 3 · 失败**

> The last file in the list, `image_1912245706439755759.jpg`, is empty. Its content came back as an empty string. It may be a placeholder, or it may not hold any readable text. `cat` only shows text, so it wouldn't display real image data anyway.<br>
> <br>
> My previous message ended with a "GRAPH INDEX" block. I shouldn't have included it. You didn't ask for it, and you can ignore it.

`/home/ruqi/public/CS769/experiments/bfcl_identity/v3_native_20261021_r2/continuations/runs/claude-sonnet-5-5/multi_turn_long_context_26/primary/3/native-graph-index/native.jsonl:4`

**multi_turn_base_38 · repeat 1 · 通过**

> The current directory is empty, hidden files included.<br>
> <br>
> The "GRAPH INDEX" block at the end of my last message didn't belong there. You didn't ask for it and it wasn't part of my answer, so please ignore it. The deletions themselves happened as I described.

`/home/ruqi/public/CS769/experiments/bfcl_identity/v3_native_20261021_r2/continuations/runs/claude-sonnet-5-5/multi_turn_base_38/primary/1/native-graph-index/native.jsonl:4`

**multi_turn_base_38 · repeat 2 · 通过**

> The current directory is empty. It has no files, no directories and no hidden files.<br>
> <br>
> My last message ended with a "GRAPH INDEX" block. It didn't belong there, so please ignore it. The only thing it said was that `findings_report` and `SuperResearch` no longer exist.

`/home/ruqi/public/CS769/experiments/bfcl_identity/v3_native_20261021_r2/continuations/runs/claude-sonnet-5-5/multi_turn_base_38/primary/2/native-graph-index/native.jsonl:4`

**multi_turn_long_context_39 · repeat 3 · 通过**

> I went into `WebDevProjects` and created the three files. I read each one back to check its contents:<br>
> <br>
> - `styles.css` contains "Hello World!"<br>
> - `index.html` contains "Hi World!"<br>
> - `script.js` contains "Halo World!"<br>
> <br>
> My first attempt to write the files failed because they didn't exist yet. I created them first and then wrote the contents.<br>
> <br>
> I also need to correct my first reply. It ended with a "GRAPH INDEX" note that I shouldn't have included, and it doesn't reflect anything you asked for. Please ignore it.

`/home/ruqi/public/CS769/experiments/bfcl_identity/v3_native_20261021_r2/continuations/runs/claude-sonnet-5-5/multi_turn_long_context_39/primary/3/native-graph-index/native.jsonl:12`

</details>

**完整性核查。** 全232条重建证据、46个冻结首轮、47份源码、19份测试文件均通过核对；1,927次真实续跑请求均有响应，0次重试、0次长度截断。Claude需回传的240次thinking/signature块原样保留。四条复用Claude轨迹的模型证据未变；其中一条重新离线评分，只更新了评分日志中的输出目录。

[逐题CSV](evidence/v3-success-by-case.csv) · [官方汇总JSON](evidence/v3-results.json) · [完整人工分析与审计JSON](evidence/v3-final-analysis.json)

服务器证据目录：`/home/ruqi/public/CS769/experiments/bfcl_identity/v3_native_20261021_r2`<br>
分析只读取既有结果，没有重新采样，也没有修改官方分数。
