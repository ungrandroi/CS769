# V4 旧集回归已完成，暂不冻结格式

**归档说明：**这是该阶段完成时的报告，文中的“下一步／尚未启动”按当时状态理解；跨阶段结论以[总报告](experiment-summary.md)及[V5 最终结果](v5-b-validation-results.md)为准。[报告目录](README.md) · [GitHub 阅读版](v4-regression-review.md)

GPT-4.1 保持官方通过率；GPT-5-mini 出现净下降。新验证集尚未启动，格式尚未批准。

完整保留原生历史，不压缩。候选把图索引放在第二条用户消息之前的 `application_memory` 块内，标注 harness 来源。旧集共 35 个模型×题目条件，146 条轨迹。

| 模型 | 题目与重复 | identity | 原生历史＋索引 | 差值 | 配对掉点 / 改善 |
| --- | --- | --- | --- | --- | --- |
| GPT-4.1 | 16 题 × 1 次 / 组 | 11/16（68.8%） | 11/16（68.8%） | 0 | 0 / 0 |
| GPT-5-mini | 19 题 × 3 次 / 组 | 32/57（56.1%） | 26/57（45.6%） | −10.5 个百分点 | 9 / 3 |

控制题 base_12、long_context_12 两组都全部通过。GPT-5-mini 有 5 个条件净下降、1 个条件净改善。以上均为原始 BFCL 官方分数，原因审核没有修改分数。

3 次反向改善中，long_context_1 的两次也是 cat 与 grep 的执行返回差异；long_context_29 seed42 则是候选正确处理了上一条问题的指代。

## 9 次配对掉点的证据

5 次主要是评分路径差异，另 4 次有任务行为问题。此分类解释观察结果，不构成对图索引的因果归因，也不用于扣除失败。

<details>
<summary>multi_turn_base_16 · seed 42 · 任务行为问题</summary>

候选在计数前用 echo 把文件改写为三行；identity 直接 wc 得到一行。类似多余写入在旧版 identity 中也出现过，不能归为图独有错误。

### identity · 官方通过：True

```text
turn 2, request 10
sort {"file_name":"2024_research_backup.txt"}
turn 2, request 11
I sorted the lines in research/archives/2024_research_backup.txt alphabetically. The file now contains the lines in this order:
- Line 3: Experiment results
- Line 1: Introduction
- Line 2: Methodology

Would you like me to save a separate sorted copy (for example 2024_research_backup_sorted.txt) and keep the unsorted version as well?
turn 3, request 12
wc {"file_name":"2024_research_backup.txt","mode":"l"}
turn 3, request 13
The sorted file currently contains 1 line.

Explanation: the file's contents are all on a single line ("Line 3: Experiment results Line 1: Introduction Line 2: Methodology"), so wc reports 1 line. I can:

- Reformat the file so each entry is on its own line and then recount, or
- Save a separate properly newline-separated copy (e.g., 2024_research_backup_sorted.txt), or
- Show the full file contents.

Which would you like me to do?
```

### native-graph-context · 官方通过：False

```text
turn 2, request 10
sort {"file_name":"2024_research_backup.txt"}
turn 2, request 11
I sorted the lines in archives/2024_research_backup.txt alphabetically and produced the following sorted content:
- Line 1: Introduction
- Line 2: Methodology
- Line 3: Experiment results

Would you like me to overwrite the existing backup file with this sorted version, save it as a new file, or just display/download the sorted content?
turn 3, request 12
cat {"file_name":"2024_research_backup.txt"}
turn 3, request 13
echo {"content":"Line 1: Introduction\nLine 2: Methodology\nLine 3: Experiment results","file_name":"2024_research_backup.txt"}
turn 3, request 14
wc {"file_name":"2024_research_backup.txt","mode":"l"}
turn 3, request 15
The sorted file contains 3 lines.
```

</details>

<details>
<summary>multi_turn_base_26 · seed 42 · 任务未执行</summary>

候选询问要有效 Word 包还是仅改扩展名的文本，未创建文件。identity 按模拟器流程创建并写入；官方通过不证明生成了真实 Word 格式。

### identity · 官方通过：True

```text
turn 2, request 5
cat {"file_name":"file3.txt"}
turn 2, request 6
file3.txt contains:
"Nothing important here. Yet another line."
turn 3, request 7
echo {"file_name":"file3.docx","content":"Nothing important here. Yet another line."}
turn 3, request 8
pwd {}
turn 3, request 9
echo {"file_name":"file3.docx","content":"Nothing important here. Yet another line."}
turn 3, request 10
touch {"file_name":"file3.docx"}
turn 3, request 11
echo {"file_name":"file3.docx","content":"Nothing important here. Yet another line."}
turn 3, request 12
ls {"a":true}
turn 3, request 13
I created file3.docx in /alex/tmp and wrote the same content into it as file3.txt.
- file3.docx now exists alongside file3.txt.
- Both contain: "Nothing important here. Yet another line."

Would you like me to open or convert the docx to verify formatting, or download it?
```

### native-graph-context · 官方通过：False

```text
turn 2, request 5
cat {"file_name":"file3.txt"}
turn 2, request 6
The last file I displayed, file3.txt, contains:
"Nothing important here. Yet another line."
turn 3, request 7
Do you want a valid Word (.docx) package that Word will open properly, or is it OK to create a plain text file named with a .docx extension containing the same text?
```

</details>

<details>
<summary>multi_turn_base_26 · seed 43 · 评分路径差异</summary>

候选 cp 成功，最终模拟器文件内容与 identity 相同；但 BFCL 要求参考 touch＋echo 的返回结果，判 execution_response_mismatch。

### identity · 官方通过：True

```text
turn 2, request 5
cat {"file_name":"file3.txt"}
turn 2, request 6
file3.txt contains:
"Nothing important here. Yet another line."
turn 3, request 7
echo {"content":"Nothing important here. Yet another line.","file_name":"file3.docx"}
turn 3, request 8
touch {"file_name":"file3.docx"}
turn 3, request 9
echo {"content":"Nothing important here. Yet another line.","file_name":"file3.docx"}
turn 3, request 10
I created file3.docx in /alex/tmp with the same text content as file3.txt. Would you like me to open or download it?
```

### native-graph-context · 官方通过：False

```text
turn 2, request 5
cat {"file_name":"file3.txt"}
turn 2, request 6
file3.txt contains:
Nothing important here. Yet another line.
turn 3, request 7
cat {"file_name":"file3.txt"}
turn 3, request 8
echo {"file_name":"file3.docx","content":"Nothing important here. Yet another line."}
turn 3, request 9
cp {"source":"file3.txt","destination":"file3.docx"}
turn 3, request 10
I created file3.docx in /alex/tmp by copying file3.txt. Both files now contain the same text: "Nothing important here. Yet another line."
```

</details>

<details>
<summary>multi_turn_base_26 · seed 44 · 评分路径差异</summary>

候选 cp 成功，最终模拟器文件内容与 identity 相同；但 BFCL 要求参考 touch＋echo 的返回结果，判 execution_response_mismatch。

### identity · 官方通过：True

```text
turn 2, request 5
cat {"file_name":"file3.txt"}
turn 2, request 6
file3.txt contains:
Nothing important here. Yet another line.
turn 3, request 7
echo {"file_name":"file3.docx","content":"Nothing important here. Yet another line."}
turn 3, request 8
pwd {}
turn 3, request 9
echo {"file_name":"file3.docx","content":"PK\u0003\u0004\u0014\u0000\u0008\u0000\u0008\u0000\u0000!?\u0000\u0000\u0000\u0000\u0000\u0000\u0000\u0000\u0000\u0000\u0000\u0000word/","}cargo run --release --bin something":""}
turn 3, request 10
echo {"file_name":"file3.docx","content":"Nothing important here. Yet another line."}
turn 3, request 11
touch {"file_name":"file3.docx"}
turn 3, request 12
echo {"file_name":"file3.docx","content":"Nothing important here. Yet another line."}
turn 3, request 13
Done — I created file3.docx in /alex/tmp and wrote the same text from file3.txt into it. Would you like me to download it, open it, or list its details?
```

### native-graph-context · 官方通过：False

```text
turn 2, request 5
cat {"file_name":"file3.txt"}
turn 2, request 6
file3.txt contains:
Nothing important here. Yet another line.
turn 3, request 7
echo {"content":"Nothing important here. Yet another line.","file_name":"file3.docx"}
turn 3, request 8
cp {"source":"file3.txt","destination":"file3.docx"}
turn 3, request 9
ls {"a":true}
turn 3, request 10
Done — I created file3.docx in /alex/tmp by copying file3.txt. It contains the same text as file3.txt. Would you like me to open or download it?
```

</details>

<details>
<summary>multi_turn_base_39 · seed 42 · 评分路径差异</summary>

候选前一轮已 ls，本轮正确回答 index.html，但未再次调用工具，判 empty_turn_model_response。

### identity · 官方通过：True

```text
turn 2, request 2
cd {"folder":"WebDevProjects"}
turn 2, request 3
echo {"file_name":"styles.css","content":"Hello World!"}
turn 2, request 4
ls {"a":false}
turn 2, request 5
echo {"file_name":"index.html","content":"Hi World!"}
turn 2, request 6
touch {"file_name":"styles.css"}
turn 2, request 7
echo {"file_name":"styles.css","content":"Hello World!"}
turn 2, request 8
touch {"file_name":"index.html"}
turn 2, request 9
echo {"file_name":"index.html","content":"Hi World!"}
turn 2, request 10
touch {"file_name":"script.js"}
turn 2, request 11
echo {"file_name":"script.js","content":"Halo World!"}
turn 2, request 12
All set — I entered the WebDevProjects folder and created three files with the requested contents:

- styles.css containing: Hello World!
- index.html containing: Hi World!
- script.js containing: Halo World!

Would you like me to open or edit any of these files, or create a README or project structure?
turn 3, request 13
ls {"a":false}
turn 3, request 14
index.html
turn 4, request 15
cat {"file_name":"styles.css"}
turn 4, request 16
Here is the content of the first file (styles.css):

Hello World!
```

### native-graph-context · 官方通过：False

```text
turn 2, request 2
cd {"folder":"WebDevProjects"}
turn 2, request 3
echo {"file_name":"styles.css","content":"Hello World!"}
turn 2, request 4
touch {"file_name":"styles.css"}
turn 2, request 5
echo {"file_name":"styles.css","content":"Hello World!"}
turn 2, request 6
touch {"file_name":"index.html"}
turn 2, request 7
echo {"file_name":"index.html","content":"Hi World!"}
turn 2, request 8
touch {"file_name":"script.js"}
turn 2, request 9
echo {"file_name":"script.js","content":"Halo World!"}
turn 2, request 10
ls {"a":true}
turn 2, request 11
All set — I entered the WebDevProjects folder and created three files with the requested contents:
- styles.css — "Hello World!"
- index.html — "Hi World!"
- script.js — "Halo World!"

Would you like me to open or edit any of these files, or add a README and standard folder structure?
turn 3, request 12
index.html
turn 4, request 13
cat {"file_name":"styles.css"}
turn 4, request 14
Hello World!
```

</details>

<details>
<summary>multi_turn_long_context_29 · seed 43 · 指代错误</summary>

候选将当前 Finally... 写进文件，identity 写的是前一条 Create...。两组都出现过这种指代错误，未见复制索引正文。

### identity · 官方通过：True

```text
turn 2, request 5
du {}
turn 2, request 6
touch {"file_name":"3354.pdf"}
turn 2, request 7
Created file "3354.pdf" in the VisionX folder.
turn 3, request 8
echo {"file_name":"3354.pdf","content":"Create a file name based on the number of byte used. It should be in 'number.pdf' format."}
turn 3, request 9
Wrote your last question into 3354.pdf.
```

### native-graph-context · 官方通过：False

```text
turn 2, request 5
du {}
turn 2, request 6
touch {"file_name":"3354.pdf"}
turn 2, request 7
Done — I created the file named 3354.pdf in the VisionX directory.
turn 3, request 8
echo {"content":"Finally, in that file, Write my last question in it.","file_name":"3354.pdf"}
turn 3, request 9
I wrote your last question into 3354.pdf.
```

</details>

<details>
<summary>multi_turn_long_context_29 · seed 44 · 指代错误及多余格式内容</summary>

候选先构造 PDF 骨架，再将当前 Finally... 放进注释；identity 写前一条 Create... 的原文。

### identity · 官方通过：True

```text
turn 2, request 5
du {"human_readable":false}
turn 2, request 6
touch {"file_name":"3354.pdf"}
turn 2, request 7
Done — I created a file named 3354.pdf in the VisionX folder.
turn 3, request 8
echo {"content":"Create a file name based on the number of byte used. It should be in 'number.pdf' format.","file_name":"3354.pdf"}
turn 3, request 9
Done — I wrote your last question into 3354.pdf.
```

### native-graph-context · 官方通过：False

```text
turn 2, request 5
du {}
turn 2, request 6
echo {"content":"%PDF-1.4\n% Created by assistant\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Count 0 >>\nendobj\nxref\n0 3\n0000000000 65535 f \n0000000010 00000 n \n0000000060 00000 n \ntrailer\n<< /Size 3 /Root 1 0 R >>\nstartxref\n120\n%%EOF\n","file_name":"3354.pdf"}
turn 2, request 7
touch {"file_name":"3354.pdf"}
turn 2, request 8
echo {"content":"%PDF-1.4\n% Created by assistant\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Count 0 >>\nendobj\nxref\n0 3\n0000000000 65535 f \n0000000010 00000 n \n0000000060 00000 n \ntrailer\n<< /Size 3 /Root 1 0 R >>\nstartxref\n120\n%%EOF\n","file_name":"3354.pdf"}
turn 2, request 9
ls {"a":false}
turn 2, request 10
I created the file named 3354.pdf in the VisionX folder.
turn 3, request 11
echo {"content":"%PDF-1.4\n% Finally, in that file, Write my last question in it.\n% Created by assistant\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Count 0 >>\nendobj\nxref\n0 3\n0000000000 65535 f \n0000000010 00000 n \n0000000060 00000 n \ntrailer\n<< /Size 3 /Root 1 0 R >>\nstartxref\n120\n%%EOF\n","file_name":"3354.pdf"}
turn 3, request 12
cat {"file_name":"3354.pdf"}
turn 3, request 13
Done — I updated 3354.pdf to include your last question: "Finally, in that file, Write my last question in it."
```

</details>

<details>
<summary>multi_turn_long_context_39 · seed 42 · 评分路径差异</summary>

候选前一轮已 ls，本轮正确回答 index.html，但未再次调用工具，判 empty_turn_model_response。

### identity · 官方通过：True

```text
turn 2, request 2
cd {"folder":"WebDevProjects"}
turn 2, request 3
echo {"file_name":"styles.css","content":"Hello World!"}
turn 2, request 4
touch {"file_name": "styles.css"}
touch {"file_name": "index.html"}
touch {"file_name": "script.js"}
turn 2, request 5
echo {"file_name":"styles.css","content":"Hello World!"}
turn 2, request 6
echo {"file_name":"index.html","content":"Hi World!"}
turn 2, request 7
echo {"file_name":"script.js","content":"Halo World!"}
turn 2, request 8
All set — I've entered the WebDevProjects folder and created three files with the requested contents:
- styles.css — "Hello World!"
- index.html — "Hi World!"
- script.js — "Halo World!"

Would you like me to open or display any of these files, or make additional changes?
turn 3, request 9
ls {"a":false}
turn 3, request 10
index.html
turn 4, request 11
cat {"file_name":"styles.css"}
turn 4, request 12
Here is the content of the first file (styles.css):

Hello World!
```

### native-graph-context · 官方通过：False

```text
turn 2, request 2
cd {"folder":"WebDevProjects"}
turn 2, request 3
echo {"file_name":"styles.css","content":"Hello World!"}
turn 2, request 4
ls {"a":false}
turn 2, request 5
touch {"file_name":"styles.css"}
turn 2, request 6
echo {"file_name":"styles.css","content":"Hello World!"}
turn 2, request 7
touch {"file_name":"index.html"}
turn 2, request 8
echo {"file_name":"index.html","content":"Hi World!"}
turn 2, request 9
touch {"file_name":"script.js"}
turn 2, request 10
echo {"file_name":"script.js","content":"Halo World!"}
turn 2, request 11
ls {"a":false}
turn 2, request 12
All set — I entered the WebDevProjects folder and created three files with the requested contents:

- styles.css — contains: Hello World!
- index.html — contains: Hi World!
- script.js — contains: Halo World!

Would you like me to open or edit any of these files, or add a README and basic HTML structure linking the CSS and JS?
turn 3, request 13
index.html
turn 4, request 14
cat {"file_name":"styles.css"}
turn 4, request 15
Here is the content of styles.css:

Hello World!
```

</details>

<details>
<summary>multi_turn_long_context_39 · seed 43 · 评分路径差异</summary>

候选前一轮已 ls，本轮正确回答 index.html，但未再次调用工具，判 empty_turn_model_response。

### identity · 官方通过：True

```text
turn 2, request 2
cd {"folder":"WebDevProjects"}
turn 2, request 3
echo {"file_name":"styles.css","content":"Hello World!"}
turn 2, request 4
touch {"file_name":"styles.css"}
turn 2, request 5
echo {"file_name":"styles.css","content":"Hello World!"}
turn 2, request 6
touch {"file_name":"index.html"}
turn 2, request 7
echo {"file_name":"index.html","content":"Hi World!"}
turn 2, request 8
touch {"file_name":"script.js"}
turn 2, request 9
echo {"file_name":"script.js","content":"Halo World!"}
turn 2, request 10
All set — I entered the WebDevProjects folder and created three files with the requested contents:

- styles.css — "Hello World!"
- index.html — "Hi World!"
- script.js — "Halo World!"

Would you like me to open or display any of these files, or add additional starter content (like an HTML template linking to the CSS/JS)?
turn 3, request 11
ls {"a":false}
turn 3, request 12
The second file by system order is: index.html
turn 4, request 13
cat {"file_name":"styles.css"}
turn 4, request 14
Here is the content of the first file (styles.css):

Hello World!
```

### native-graph-context · 官方通过：False

```text
turn 2, request 2
cd {"folder":"WebDevProjects"}
turn 2, request 3
echo {"file_name":"styles.css","content":"Hello World!"}
turn 2, request 4
ls {"a":false}
turn 2, request 5
touch {"file_name":"styles.css"}
turn 2, request 6
echo {"file_name":"styles.css","content":"Hello World!"}
turn 2, request 7
touch {"file_name":"index.html"}
turn 2, request 8
echo {"file_name":"index.html","content":"Hi World!"}
turn 2, request 9
touch {"file_name":"script.js"}
turn 2, request 10
echo {"file_name":"script.js","content":"Halo World!"}
turn 2, request 11
ls {"a":true}
turn 2, request 12
All set — I entered the WebDevProjects folder and created three files with the requested contents:

- styles.css — contains: Hello World!
- index.html — contains: Hi World!
- script.js — contains: Halo World!

Would you like me to open or modify any of these files, or add a README or starter template?
turn 3, request 13
index.html
turn 4, request 14
cat {"file_name":"styles.css"}
turn 4, request 15
Hello World!
```

</details>

## 逐题通过次数

| 模型 | 题目 | identity | 候选 |
| --- | --- | --- | --- |
| gpt-4.1 | multi_turn_base_1 | 1/1 | 1/1 |
| gpt-4.1 | multi_turn_base_12 | 1/1 | 1/1 |
| gpt-4.1 | multi_turn_base_25 | 0/1 | 0/1 |
| gpt-4.1 | multi_turn_base_26 | 1/1 | 1/1 |
| gpt-4.1 | multi_turn_base_29 | 1/1 | 1/1 |
| gpt-4.1 | multi_turn_base_38 | 1/1 | 1/1 |
| gpt-4.1 | multi_turn_base_39 | 1/1 | 1/1 |
| gpt-4.1 | multi_turn_base_9 | 0/1 | 0/1 |
| gpt-4.1 | multi_turn_long_context_1 | 1/1 | 1/1 |
| gpt-4.1 | multi_turn_long_context_12 | 1/1 | 1/1 |
| gpt-4.1 | multi_turn_long_context_16 | 1/1 | 1/1 |
| gpt-4.1 | multi_turn_long_context_25 | 0/1 | 0/1 |
| gpt-4.1 | multi_turn_long_context_26 | 0/1 | 0/1 |
| gpt-4.1 | multi_turn_long_context_29 | 0/1 | 0/1 |
| gpt-4.1 | multi_turn_long_context_37 | 1/1 | 1/1 |
| gpt-4.1 | multi_turn_long_context_39 | 1/1 | 1/1 |
| gpt-5-mini | multi_turn_base_1 | 3/3 | 3/3 |
| gpt-5-mini | multi_turn_base_12 | 3/3 | 3/3 |
| gpt-5-mini | multi_turn_base_16 | 3/3 | 2/3 |
| gpt-5-mini | multi_turn_base_25 | 3/3 | 3/3 |
| gpt-5-mini | multi_turn_base_26 | 3/3 | 0/3 |
| gpt-5-mini | multi_turn_base_29 | 1/3 | 1/3 |
| gpt-5-mini | multi_turn_base_3 | 3/3 | 3/3 |
| gpt-5-mini | multi_turn_base_38 | 3/3 | 3/3 |
| gpt-5-mini | multi_turn_base_39 | 2/3 | 1/3 |
| gpt-5-mini | multi_turn_base_6 | 0/3 | 0/3 |
| gpt-5-mini | multi_turn_base_9 | 0/3 | 0/3 |
| gpt-5-mini | multi_turn_long_context_1 | 1/3 | 3/3 |
| gpt-5-mini | multi_turn_long_context_12 | 3/3 | 3/3 |
| gpt-5-mini | multi_turn_long_context_25 | 0/3 | 0/3 |
| gpt-5-mini | multi_turn_long_context_26 | 0/3 | 0/3 |
| gpt-5-mini | multi_turn_long_context_29 | 2/3 | 1/3 |
| gpt-5-mini | multi_turn_long_context_39 | 2/3 | 0/3 |
| gpt-5-mini | multi_turn_long_context_6 | 0/3 | 0/3 |
| gpt-5-mini | multi_turn_long_context_9 | 0/3 | 0/3 |

## 完整性与解释范围

服务器源码、数据、依赖和运行环境冻结校验通过；服务器没有格式批准文件，也没有新验证集目录。旧集共 1,239 次实际请求，参考费用约 $2.43，无未结算请求。

未见候选在可见回复中把索引当作自己或用户的原话。完整性审核与独立审查细节保存在同目录 JSON 中。

- 这是旧开发/回归集，不是未见新验证集的结论。
- GPT-4.1 每条件一次，GPT-5-mini 每条件三次；重复不是独立题族。
- 行为差异已观察到，但未通过放置方式消融证明因果。
- 没有发现可见索引归属误认，不等于证明模型内部不受格式影响。
- 预算为全部输入按未缓存参考单价计的估算，不是 Azure 实际账单。

原始结果 SHA256：2984782f320464ce9d9c5879536eb27ab31665532b4d0bc0b9d8fbb57f4c0808

[逐轨迹结果及原生证据](evidence/v4-regression-review.json) · [后续身份请求一致性与波动复核](evidence/v4-feedback-audit.json) · [冻结协议](evidence/v4-protocol.json)
