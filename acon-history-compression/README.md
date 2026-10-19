# ACON 历史压缩：AppWorld 与 BFCL

2026-10-09 到 2026-10-13 的对照实验。模型都是 `gpt-4.1-mini`。压缩阈值 4096（tiktoken `o200k_base` 的消息 token）。用户消息原文保留，最近一步 assistant 工具调用和配对的 tool 消息保留，更早的 assistant/tool 消息换成一条摘要。压缩器温度 0。

仓库里是这次用到的改动、选题和汇总。不含数据集、完整轨迹、请求 dump 和 API key。

| 数据集 | 上游 | 本次固定的提交 |
| --- | --- | --- |
| AppWorld / ACON | [microsoft/acon](https://github.com/microsoft/acon) | `d63f9ae18959dc7215ff62899c94c5e8c56847ae` |
| BFCL v4 | [ShishirPatil/gorilla](https://github.com/ShishirPatil/gorilla) | `6ea57973c7a6097fd7c5915698c54c17c5b1b6c8` |

说明见 [docs/appworld.md](docs/appworld.md) 和 [docs/bfcl.md](docs/bfcl.md)。

## 目录

- `appworld/`：UT prompt、两份 history 配置、30 题名单、`tn30_run.sh`，以及 `llm.py` 的 `max_retries=8` 补丁。
- `bfcl/`：`history_compress.py`、两份 prompt、200 题和四组重跑的脚本，以及打在 gorilla 上的补丁。
- `results/`：选题 json、`baseline_200.csv`、汇总和对照摘要。没有 result/score 目录。

## 打补丁

AppWorld：在 acon 仓库根目录

```bash
git checkout d63f9ae18959dc7215ff62899c94c5e8c56847ae
git apply /path/to/appworld/patches/llm_max_retries.patch
```

把 `appworld/prompts/context_opt/` 和 `appworld/configs/context_opt/` 拷进 `experiments/appworld/` 下的同名目录。`prompt_history_v2.jinja` 和 `gpt-4.1-mini_history.yaml` 与该提交里的上游文件一致，放在这里是为了和 UT 对照放在一起。

BFCL：在 gorilla 仓库根目录

```bash
git checkout 6ea57973c7a6097fd7c5915698c54c17c5b1b6c8
git apply /path/to/bfcl/patches/gorilla_history_compress.patch
```

再把 `bfcl/bfcl_eval/model_handler/history_compress.py` 和 `bfcl/bfcl_eval/model_handler/prompts/` 拷到 `berkeley-function-call-leaderboard/bfcl_eval/model_handler/`。

注册名决定压缩模式：`gpt-4.1-mini-azure-FC` 不压缩，`-hist-FC` 用朴素 prompt，`-ut-FC` 用 UT prompt。`BFCL_HISTORY_MODE` 可以覆盖。Azure 部署名是 `gpt-4.1-mini`，走 `OpenAICompletionsHandler`，不要用仓库里自带的 Responses handler 条目。

`appworld/tn30_run.sh` 和 `bfcl/scripts/` 里的路径是当时那台机器上的路径。
