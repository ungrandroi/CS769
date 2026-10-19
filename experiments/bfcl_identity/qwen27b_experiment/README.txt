全 Qwen 27B 配对图记忆实验

26 项任务条件：13 个家族 × Base / Long Context。
仅使用 BFCL GorillaFileSystem 的 18 个模拟文件工具，不是真实 Bash。
方法：Mem Identity、V1-Compact、V2-Compact；每项每方法运行一次。

所有实际模型请求，包括第一轮，都使用本地 Qwen3.8-27B-Q8_0。
Identity 先执行完整任务；两种图分支精确回放它的第一轮工具轨迹，恢复相同环境，
然后在第二轮用户输入前用当前历史构建 Compact 图并替换一次历史。
后续不再压缩；保留首轮失败，不按分数重跑。
这是共享 Qwen 首轮的配对实验，不是三组独立采样的首轮。

两个相同配置的本地服务分别处理不同任务；同一任务始终使用同一个服务。
temperature=0，seed=42，max_tokens=4096，context=131072，thinking 关闭，提示缓存开启。
原始请求、响应、工具日志、图与官方评分位于 tasks/<任务>/<方法>/。

执行：scripts/bfcl_python.sh scripts/run_research_eval.py
汇总与校验：scripts/bfcl_python.sh scripts/summarize_research_eval.py
当前专用测试：PYTHONPATH=scripts scripts/bfcl_python.sh -m unittest test_qwen_experiment

报告只输出文字、CSV 和 JSON，不提供可视化。
用量分别报告公共首轮、各方法续段和整条轨迹（首轮+续段）。
实际计算总量仅计算公共首轮一次；输入 usage 包含缓存。
13 个任务家族的两种条件不是 26 个独立样本；单次运行不支持稳定泛化结论。
