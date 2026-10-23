# GPT-5-mini：180 条三组放置诊断

**归档说明：**这是该阶段完成时的报告，文中的“下一步／尚未启动”按当时状态理解；跨阶段结论以[总报告](experiment-summary.md)及[V5 最终结果](v5-b-validation-results.md)为准。[报告目录](README.md) · [GitHub 阅读版](v4-placement-diagnostic.md)

180条已完成：保留B作为后续候选，不采用D；尚不能判定保持了identity的官方通过率。新验证集未启动。

只运行GPT-5-mini。6个旧条件 × 3组 × 每组10次，共180条新轨迹；对应5个题族。seed为1000–1009，60个条件×seed块的三组顺序预先随机化并平衡，3个worker交错执行。

三组保留完整原生历史、不压缩，使用相同的模型自有第一轮证据与模拟器状态、工具定义和运行参数。仅改变预先登记的索引呈现方式。Claude未运行，新验证集未启动。

运行开始于2026-10-22 02:14:52 UTC，结束于02:58:09 UTC，约43分17秒。三位subagent分工审查全部180条可见回复、工具调用与状态，并独立核对汇总。

| 组别 | 输入格式 | 官方通过 | 通过率 |
| --- | --- | --- | --- |
| A · identity | 完整原生历史 | 32/60 | 53.3% |
| B · assistant 索引 | 完整原生历史＋第二轮用户请求之前的 assistant 索引消息（V3 方式） | 27/60 | 45.0% |
| D · 用户块索引 | 完整原生历史＋第二轮用户消息内的 application_memory 块（V4 方式） | 24/60 | 40.0% |

## 逐题结果

每格分母都是 10。base_39 与 long_context_39 属于同一题族；总共 6 个条件、5 个题族。

| 条件 | A · identity | B · assistant 索引 | D · 用户块索引 |
| --- | --- | --- | --- |
| base_16 | 9/10 | 6/10 | 7/10 |
| base_26 | 2/10 | 7/10 | 6/10 |
| base_39 | 2/10 | 0/10 | 0/10 |
| long_context_1 | 9/10 | 9/10 | 9/10 |
| long_context_29 | 4/10 | 3/10 | 1/10 |
| long_context_39 | 6/10 | 2/10 | 1/10 |

| 统计口径 | A · identity | B · assistant 索引 | D · 用户块索引 |
| --- | --- | --- | --- |
| 六条件等权（同原始通过比例） | 53.3% | 45.0% | 40.0% |
| 五题族等权 | 56.0% | 52.0% | 47.0% |

| 比较 | 配对下降 | 配对改善 | 净变化（条） |
| --- | --- | --- | --- |
| B · assistant 索引 − A · identity | 15 | 10 | -5 |
| D · 用户块索引 − A · identity | 16 | 8 | -8 |
| D · 用户块索引 − B · assistant 索引 | 9 | 6 | -3 |

按预先规定的5题族等权口径，A/B/D分别为56%/52%/47%；B−A为−4个百分点，D−A为−9个百分点，D−B为−5个百分点。这是点估计，不能用−4这个数直接宣称通过−5个百分点的非劣效标准。

原始60条比例为53.3%/45.0%/40.0%。family39重复出现base和long_context两个条件，因此原始比例与五题族等权结果不同。

B相对A净少5条，其中family39少6条，另外4个条件合计反而多1条；D相对A净少8条，其中family39少7条，另外4个条件合计少1条。总分下降不能全部解释为丢失信息，也不能全部解释为无害评分差异。

## 实际行为差异

以下为全部180条逐条核查后的描述性原因统计，所有官方分数保持原样。没有观察到图索引或harness标签被复制进用户要求写入的内容，亦未发现可见的索引来源冒认；这不等于能观察模型内部推理。

在官方失败中，A的28条可分为13条评分路径差异与15条实际任务失败；B的33条为20与13；D的36条为21与15。评分路径类包括答对但未再次ls、相同状态的cp、正确cat回答缺grep返回。

这个失败分类不是重新定义的“语义通过率”：若干官方通过样例也有错误操作表述、错误内容转述或多余写入，不能简单把评分路径失败加回通过数。

| 观察项（分母为每组该题的重复数） | A | B | D |
| --- | --- | --- | --- |
| family39答对但第三轮无工具（每组20） | 11 | 18 | 19 |
| base16实际额外分行改写（每组10） | 1 | 4 | 2 |
| base16无工具且错误回答3行（每组10） | 0 | 0 | 1 |
| base26确认停工（每组10） | 6 | 1 | 1 |
| base26写入错误PK/XML内容（每组10） | 1 | 1 | 2 |
| long29写入当前指令而非前一问题（每组10） | 6 | 7 | 8 |
| long29创建阶段状态错误（每组10；与上一行有重叠） | 0 | 0 | 4 |

<details>
<summary>family39：知道 index.html，但没有再次 ls</summary>

每组20条中，答案正确但第三轮没有再调用工具：A 11、B 18、D 19。B 相对 A 的6次配对掉点、D相对A的7次配对掉点，全部属于这一类。正确列表已在原生历史里；这份图索引仅记录 WebDevProjects 目录存在，并不包含文件顺序或 index.html 答案。

这支持“两种索引组更常复用已有历史答案”的描述，不支持“D把图当成权威信息”这一单一因果解释。官方 empty_turn 分数保持不变。

**base_39 · seed 1002 · A · identity**

```text
用户轮次 3
[
  [
    {
      "ls": "{}"
    }
  ],
  "index.html"
]

用户轮次 4
[
  [
    {
      "cat": "{\"file_name\":\"styles.css\"}"
    }
  ],
  "Here is the content of the first file (styles.css):\n\nHello World!"
]
```

**base_39 · seed 1002 · B · assistant 索引**

```text
用户轮次 3
[
  "index.html"
]

用户轮次 4
[
  [
    {
      "cat": "{\"file_name\":\"styles.css\"}"
    }
  ],
  "Hello World!"
]
```

**base_39 · seed 1002 · D · 用户块索引**

```text
用户轮次 3
[
  "index.html"
]

用户轮次 4
[
  [
    {
      "cat": "{\"file_name\":\"styles.css\"}"
    }
  ],
  "Here is the content of styles.css:\n\nHello World!"
]
```

</details>

<details>
<summary>base16：真实改写文件，以及无工具的错误回答</summary>

原始备份实际只有一行。额外把它改写为三行的次数为 A 1、B 4、D 2。D 另有一次不调用 wc，直接错答3行，因此不是所有 empty_turn 都能归为评分路径问题。

sort 在此模拟器中返回 sorted_content，并不修改文件。部分官方通过样例仍虚称已更新文件，或把真实返回顺序3/1/2描述为1/2/3；这些也已记录。

**base_16 · seed 1004 · A · identity**

```text
用户轮次 2
[
  [
    {
      "sort": "{\"file_name\":\"2024_research_backup.txt\"}"
    }
  ],
  [
    {
      "cat": "{\"file_name\":\"2024_research_backup.txt\"}"
    }
  ],
  "I sorted the lines of research/archives/2024_research_backup.txt alphabetically. The file now contains:\n\nLine 1: Introduction\nLine 2: Methodology\nLine 3: Experiment results\n\nWould you like me to create another dated copy with the sorted contents or undo the sort?"
]

用户轮次 3
[
  [
    {
      "wc": "{\"file_name\":\"2024_research_backup.txt\",\"mode\":\"l\"}"
    }
  ],
  "The file research/archives/2024_research_backup.txt contains 1 line.\n\nIt appears the entries are currently on a single line. Would you like me to split them into separate lines (one entry per line) and then recount?"
]
```

**base_16 · seed 1004 · B · assistant 索引**

```text
用户轮次 2
[
  [
    {
      "sort": "{\"file_name\":\"2024_research_backup.txt\"}"
    }
  ],
  "I sorted the backup file. The file's lines, alphabetically sorted, are:\n- Line 3: Experiment results\n- Line 1: Introduction\n- Line 2: Methodology\n\nWould you like me to overwrite the backup with the sorted contents, save the sorted version with a new name, or show the full file?"
]

用户轮次 3
[
  [
    {
      "echo": "{\"content\":\"Line 3: Experiment results\\nLine 1: Introduction\\nLine 2: Methodology\",\"file_name\":\"2024_research_backup.txt\"}"
    }
  ],
  [
    {
      "wc": "{\"file_name\":\"2024_research_backup.txt\",\"mode\":\"l\"}"
    }
  ],
  "The sorted file contains 3 lines."
]
```

**base_16 · seed 1004 · D · 用户块索引**

```text
用户轮次 2
[
  [
    {
      "sort": "{\"file_name\":\"2024_research_backup.txt\"}"
    }
  ],
  "I sorted the file and have the sorted content. Do you want me to overwrite research/archives/2024_research_backup.txt with this sorted version, or save it as a new file?"
]

用户轮次 3
[
  "The sorted version contains 3 lines. Would you like me to write the sorted content back into research/archives/2024_research_backup.txt or save it as a new file?"
]
```

</details>

<details>
<summary>base26：图组减少了确认停工，但也有错误写入</summary>

确认是否需要真正Word文件、因而未创建目标的次数为 A 6、B 1、D 1。这是本轮图组的实际改善之一。

另一方面，写入额外PK/XML片段、使目标内容不等于源文本的次数为 A 1、B 1、D 2。B seed1000虽然通过，还同值重写了源文件并删除、重建刚生成的目标；通过不等于没有多余操作。

另外每组各有1条用cp得到完全相同的已记录文件系统状态，却因缺少参考touch＋echo产生的两个None返回而失败。没有把这些失败改分。

**base_26 · seed 1000 · A · identity**

```text
用户轮次 3
[
  "Do you want a genuine Word (.docx) file that Microsoft Word can open, or is it okay if I simply create a file named \"file3.docx\" containing the same plain text? Creating a fully valid .docx requires packaging XML files into a zip structure; I can do that if you confirm. Which do you prefer?"
]
```

**base_26 · seed 1000 · B · assistant 索引**

```text
用户轮次 3
[
  [
    {
      "echo": "{\"content\":\"Nothing important here. Yet another line.\",\"file_name\":\"file3.docx\"}"
    }
  ],
  [
    {
      "ls": "{\"a\":true}"
    }
  ],
  [
    {
      "cat": "{\"file_name\":\"file3.txt\"}"
    }
  ],
  [
    {
      "echo": "{\"content\":\"Nothing important here. Yet another line.\",\"file_name\":\"file3.docx\"}"
    }
  ],
  [
    {
      "touch": "{\"file_name\":\"file3.docx\"}"
    }
  ],
  [
    {
      "echo": "{\"content\":\"Nothing important here. Yet another line.\",\"file_name\":\"file3.txt\"}"
    }
  ],
  [
    {
      "cat": "{\"file_name\":\"file3.txt\"}"
    }
  ],
  [
    {
      "cp": "{\"source\":\"file3.txt\",\"destination\":\"file3.docx\"}"
    }
  ],
  [
    {
      "rm": "{\"file_name\":\"file3.docx\"}"
    }
  ],
  [
    {
      "touch": "{\"file_name\":\"file3.docx\"}"
    }
  ],
  [
    {
      "echo": "{\"content\":\"Nothing important here. Yet another line.\",\"file_name\":\"file3.docx\"}"
    }
  ],
  [
    {
      "ls": "{\"a\":true}"
    }
  ],
  "Done — I created file3.docx in the directory and wrote the same text into it as file3.txt. The directory now contains:\n- file1.txt\n- file2.txt\n- file3.txt\n- file3.docx\n\nWould you like me to open the .docx to confirm its contents?"
]
```

</details>

<details>
<summary>long_context_29：当前问题与前一问题，以及D的额外创建内容</summary>

写入当前这条指令、而非BFCL要求的前一用户问题：A 6、B 7、D 8。三组都存在指代错误，没有发现索引、harness标签或assistant原话被当作所需问题写入。

D另有4条创建阶段的状态错误：seed1002使用3356.pdf而非3354.pdf；1003写入未经请求的说明；1004和1005写入PDF结构或头部。A/B在这10次中没有这类创建错误。

D seed1004后来写对了前一问题，但先前创建阶段已违反空文件状态要求，官方仍失败。上述类别有重叠，不能直接相加。

**long_context_29 · seed 1004 · A · identity**

```text
用户轮次 2
[
  [
    {
      "du": "{\"human_readable\":false}"
    }
  ],
  [
    {
      "touch": "{\"file_name\":\"3354.pdf\"}"
    }
  ],
  "Done — I created the file named 3354.pdf in the VisionX folder."
]

用户轮次 3
[
  [
    {
      "echo": "{\"file_name\":\"3354.pdf\",\"content\":\"Create a file name based on the number of byte used. It should be in 'number.pdf' format.\"}"
    }
  ],
  "Done — I wrote your last question into 3354.pdf."
]
```

**long_context_29 · seed 1004 · D · 用户块索引**

```text
用户轮次 2
[
  [
    {
      "du": "{\"human_readable\":false}"
    }
  ],
  [
    {
      "echo": "{\"content\":\"%PDF-1.4\\n% Placeholder PDF file for 3354 bytes\\n1 0 obj\\n<< /Type /Catalog /Pages 2 0 R >>\\nendobj\\n2 0 obj\\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\\nendobj\\n3 0 obj\\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>\\nendobj\\n4 0 obj\\n<< /Length 55 >>\\nstream\\nBT\\n/F1 24 Tf\\n100 700 Td\\n(Placeholder) Tj\\nET\\nendstream\\nendobj\\nxref\\n0 5\\n0000000000 65535 f \\n0000000010 00000 n \\n0000000065 00000 n \\n0000000123 00000 n \\n0000000200 00000 n \\ntrailer\\n<< /Root 1 0 R /Size 5 >>\\nstartxref\\n300\\n%%EOF\",\"file_name\":\"3354.pdf\"}"
    }
  ],
  [
    {
      "touch": "{\"file_name\":\"3354.pdf\"}"
    }
  ],
  [
    {
      "echo": "{\"content\":\"%PDF-1.4\\n% Placeholder PDF file for 3354 bytes\\n1 0 obj\\n<< /Type /Catalog /Pages 2 0 R >>\\nendobj\\n2 0 obj\\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\\nendobj\\n3 0 obj\\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>\\nendobj\\n4 0 obj\\n<< /Length 55 >>\\nstream\\nBT\\n/F1 24 Tf\\n100 700 Td\\n(Placeholder) Tj\\nET\\nendstream\\nendobj\\nxref\\n0 5\\n0000000000 65535 f \\n0000000010 00000 n \\n0000000065 00000 n \\n0000000123 00000 n \\n0000000200 00000 n \\ntrailer\\n<< /Root 1 0 R /Size 5 >>\\nstartxref\\n300\\n%%EOF\",\"file_name\":\"3354.pdf\"}"
    }
  ],
  [
    {
      "ls": "{\"a\":false}"
    }
  ],
  "I created the file 3354.pdf in the VisionX folder."
]

用户轮次 3
[
  [
    {
      "echo": "{\"content\":\"Create a file name based on the number of byte used. It should be in 'number.pdf' format.\",\"file_name\":\"3354.pdf\"}"
    }
  ],
  "Done — I wrote your last question into 3354.pdf."
]
```

</details>

<details>
<summary>long_context_1：cat与grep的评分路径差异</summary>

三组各9/10通过。每组失败的1条都是读取cat后正确回答大小写匹配的Error数量，但没有grep的matching_lines返回；已记录移动后的文件状态与tail回答也正确。三个失败分别为A1004、B1002、D1009。

**long_context_1 · seed 1002 · B · assistant 索引**

```text
用户轮次 2
[
  [
    {
      "cd": "{\"folder\":\"workspace\"}"
    }
  ],
  [
    {
      "find": "{\"path\":\".\",\"name\":\"log.txt\"}"
    }
  ],
  [
    {
      "mkdir": "{\"dir_name\":\"archive\"}"
    }
  ],
  [
    {
      "ls": "{\"a\":true}"
    }
  ],
  [
    {
      "mv": "{\"source\":\"log.txt\",\"destination\":\"archive\"}"
    }
  ],
  "Done. I changed into workspace, found a log.txt there, created (or used the existing) directory archive, and moved log.txt into archive/log.txt. The workspace directory now contains:\n- archive\n- .hidden_file\n\n(archive contains log.txt)"
]
```

</details>

<details>
<summary>保留的一次生成上限失败</summary>

identity / long_context_39 / seed1004 的一次响应用尽16384个completion token，均记录为reasoning token，没有可见文本，也未完成文件创建。按固定协议保留该失败，没有重跑替换；它不代表历史被压缩或证据缺失。

**服务端记录**

```text
{
  "key": "gpt-5-mini/multi_turn_long_context_39/1004/identity",
  "id": "multi_turn_long_context_39",
  "seed": 1004,
  "mode": "identity",
  "turn_zero_based": 1,
  "request_index": 5,
  "finish_reason": "length",
  "usage": {
    "completion_tokens": 16384,
    "completion_tokens_details": {
      "accepted_prediction_tokens": 0,
      "audio_tokens": 0,
      "reasoning_tokens": 16384,
      "rejected_prediction_tokens": 0
    },
    "latency_checkpoint": {
      "engine_tbt_ms": 6,
      "engine_ttft_ms": 29,
      "engine_ttlt_ms": 93524,
      "pre_inference_ms": 125,
      "service_tbt_ms": 6,
      "service_ttft_ms": 888,
      "service_ttlt_ms": 94379,
      "user_visible_ttft_ms": 763
    },
    "prompt_tokens": 2471,
    "prompt_tokens_details": {
      "audio_tokens": 0,
      "cached_tokens": 2432
    },
    "total_tokens": 18855
  },
  "visible_message": {
    "annotations": [],
    "content": "",
    "refusal": null,
    "role": "assistant"
  },
  "official_passed": false,
  "handling": "Retained in the fixed180 result and official score; no exclusion or replacement."
}
```

</details>

## Token、费用与完整性

Token 按这轮真实续跑请求累计；每组 60 条取平均，不把重放的第一轮算作新调用。推理 token 已包含在输出 token 内。

| 组别 | 平均输入 token | 平均输出 token | 平均请求数 | 平均工具调用数 | 首次续跑输入 |
| --- | --- | --- | --- | --- | --- |
| A · identity | 22,739.2 | 1,069.7 | 8.7 | 6.2 | 2,439.8 |
| B · assistant 索引 | 25,554.4 | 966.4 | 9.5 | 7.0 | 2,489.2 |
| D · 用户块索引 | 24,641.3 | 931.2 | 9.1 | 6.7 | 2,502.2 |

续跑输入＋输出token平均每条：A 23,808.9，B 26,520.8，D 25,572.5。首次续跑请求的平均实际增加量为B 49.3、D 62.3 token；完整轨迹差异还包含模型行为导致的请求次数变化，不能全部算作索引长度。

summary里的index_tokens均值43.33是离线生成的索引正文元数据，在identity行也存在；identity没有把它喂给模型。实际注入与否已通过原生请求比对核实。

identity的一条16384-token生成失败拉高输出均值；所有失败均保留。不能根据输出均值下降直接宣称索引提高了效率。

1636次有成功响应的逻辑请求，按预先冻结的未折扣参考价格计算为$1.45009575。另有39次重试前的失败尝试没有provider用量回执，保留$1.60948075的全额保守预留；本轮预算占用为$3.05957650，低于$5上限。这些预留不代表已经收费，也不是实际账单。

加上旧V4的$2.43488950，累计保守占用为$5.494466。未来若获准继续，应从原$30总预算中扣除此数，而不是只看旧账本。

独立审计29,205项检查无失败：180轨迹、60完整三组块；每次请求保留完整历史及工具；去掉预定索引后的配对首请求一致；每条官方评分、原始usage和费用记录匹配。54个实现文件、180个vendor/data文件和24个测试文件的冻结哈希均一致。

审计状态为passed_with_warnings：39次未计量的失败尝试及1次真实生成截断均保留。冻结运行器只记录了字符串异常类型str，未保留具体HTTP状态，无法把重试原因认定为429或限流。所有39次重试与相同run/request哈希及最终成功响应数量一致。

服务器已核实诊断进程退出、旧预算账本未变、没有新验证目录或格式批准文件。

## 格式选择与范围

保留B（完整原生历史＋assistant索引）作为后续工程候选，不用D替换。这个选择符合预先约定的较小变更偏好，也得到本轮D无收益、long29出现额外创建错误的观察支持。

暂不把任何候选冻结为“已满足保持通过率要求”的验收版本。B仍有base16等实际行为掉点，官方通过率也低于identity。若只是选下一轮研究所用格式，优先B；这与证明第一步目标达成是两件事。

本轮工作在结果审查处结束；没有给候选加入强制ls、特定题目修补或其他行为补丁，没有启动新验证集。

这是挑选过的6个旧条件、5个题族，用于诊断；每题10次重复不是10个独立题族，不能证明BFCL总体非劣效，也不能代表GPT-4.1或Claude。旧V3/V4结果未合并进本轮统计。

B和D同时改变消息角色、wrapper和来源标签，因此本轮比较的是整套呈现格式，无法把差异单独归因于role或“权威感”。

同一个seed仅用于随机化分块标签，不保证API输出完全可复现。没有根据中途结果扩样、提前成功停止或替换失败样例。

数据文件：[汇总与证据说明 JSON](evidence/v4-placement-diagnostic.json) · [完整性与费用审计](evidence/v4-diagnostic-integrity.json) · [全部行为审查记录](evidence/v4-diagnostic-behavior-review.json)
