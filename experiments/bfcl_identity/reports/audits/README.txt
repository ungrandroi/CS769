代码整理后的离线审核输出

baseline/：读取原始26项×三方法记录，加载其已校验的冻结源码，重建图并核对共享前缀、官方评分和token统计。
event_graph_dedup/：读取来源去重26项续跑，使用该批次冻结源码验证精确还原、共享前缀和评分。
这些目录是审核报告，不是新推理实验；没有重新调用模型。

本次整理验证：
- 61项单元测试通过。
- 当前实现生成的52份Compact记忆、26份来源去重记忆与历史记录逐字一致。
- 三个批量入口的prepare-only通过；新格式源码快照可独立导入。
- 3219个冻结实验及visualization文件的SHA-256保持不变。
- 纯1000-token协议仍为prepared_not_run，没有新评分。

统一入口：scripts/bfcl_python.sh scripts/manage.py；方法名称为 Identity、State-Transition Graph、Event Graph、Event Graph-Dedup。
