# BFCL 记忆回放

逐次回放 Qwen 27B 在 BFCL 多轮任务上的运行：左侧是模拟环境（文件系统和 Twitter / Message / Ticket 等工具状态）与终端，右侧是每次调用的工作上下文（原文或图），下方是每次调用的输入构成与输入 tokens。

| 实验（页面“实验”菜单） | 方法 | 数据 |
|---|---|---|
| **1000-token 历史阈值转换**（默认） | Identity，以及 State-Transition Graph、Event Graph、Event Graph-Dedup 各自的原格式与优化编码，共 7 个分支；按任务条件 × 种子选择 | `combined_work1000/`（`lossless_encoding_v1/` + `mixed_tool_expansion/`，600 条 Identity，417 个触发前缀） |
| 早期：首轮后转换（26 项） | Identity、State-Transition Graph（`v1-compact`）、Event Graph（`v2-compact`）、Event Graph-Dedup（`v2-dedup`） | `qwen27b_experiment/`、`qwen27b_dedup_eval/` |
| 早期：history1000 旧口径 | 尚未推理：只显示工具内容累计、触发点和触发点处的图（离线构建） | `history1000_eval/checkpoints.json` |

| 文件 | 内容 |
|---|---|
| `build_memory_viewer.py` | 生成入口；早期实验的数据嵌入页面 |
| `combined_data.py` | 1000-token 主实验的数据：每个任务条件一个文件，页面按需加载 |
| `memory_viewer_template.html` | 页面模板（数据占位符 `__VIEWER_DATA__`） |
| `viewer-data.json` | 嵌入页面的数据（早期实验 + 主实验索引） |
| `data/w1000/*.b64.txt` | 主实验每个任务条件的回放数据（gzip 后 base64，200 个文件） |
| `index.html` | 生成的页面 |

## 重新生成（在项目根目录）

```
scripts/bfcl_python.sh visualization/build_memory_viewer.py
```

不调用模型，约 1 分钟。打印的 `issues:` 正常应为 0。校验内容：

- 用 BFCL 官方执行器（同样的调用字符串转换与执行）重放每次工具调用，输出与记录逐条比对；每轮结束的目录树与 BFCL 状态日志比对；
- 图分支在触发点之前的请求与 Identity 前缀完全一致，触发位置和官方评分与 `combined_work1000/paired-samples.csv` 一致；
- 主实验的图取自实际交付的 `memory-metadata.json`，其中每个步号引用都须对应到记录里的工具返回；
- 早期实验：用批次 `source_code/` 的构图代码重建图，替换点之前的节点与实际发送的图一致；history1000 触发位置与 `checkpoints.json` 一致；工具定义 token 数的渲染总数与服务端 usage 一致。

## 本地查看

主实验的数据文件按需读取，浏览器不允许 `file://` 页面读取旁边的文件，所以需要一个本地服务：

```
python -m http.server -d visualization
```

然后打开 http://localhost:8000/ 。早期实验的数据嵌在页面里，直接打开 `index.html` 也能看。

依赖：上述实验目录、`scripts/qwen_prompt_accounting.py`、`scripts/local_qwen_tokenizer.py`、`vendor/gorilla` 中的 BFCL。
