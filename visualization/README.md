# BFCL 记忆回放

逐次回放 `experiments/bfcl_identity/qwen27b_experiment/` 中 26 项任务 × 3 种记忆模式（Mem Identity / V1-Compact / V2-Compact）的运行：文件环境与终端、每次调用的工作上下文、输入 tokens。

| 文件 | 内容 |
|---|---|
| `build_memory_viewer.py` | 从保存的运行记录生成数据并嵌入页面；不调用模型 |
| `memory_viewer_template.html` | 页面模板（数据占位符 `__VIEWER_DATA__`） |
| `viewer-data.json` | 生成的数据 |
| `index.html` | 生成的单文件页面，直接用浏览器打开 |

重新生成（在项目根目录）：

```
scripts/bfcl_python.sh visualization/build_memory_viewer.py
```

生成时会做三项校验，问题数打印为 `issues:`，正常应为 0：

- 用官方 GorillaFileSystem 重放每次工具调用，输出与记录逐条比对，每轮结束的目录树与 BFCL 状态日志比对；
- 用批次 `source_code/` 的构图代码重建 V1/V2 图，替换点之前的节点须与实际发送的图一致；
- 工具定义 token 数：同一请求带/不带工具各渲染一次并计数，渲染总数须与服务端 usage 一致。

依赖：`qwen27b_experiment/`（tasks、plan.json、source_code、runtime/chat-template.jinja）、`scripts/qwen_prompt_accounting.py`、`scripts/local_qwen_tokenizer.py`、`vendor/gorilla` 中的 BFCL。
