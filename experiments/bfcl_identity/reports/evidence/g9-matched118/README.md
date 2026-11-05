# 118道配对比较的证据附件

[可读报告](../../g9-event-matched118-results.md) · [总报告](../../experiment-summary.md)

- `summary.json`：精确汇总、四类结果、配对得失、描述性置信区间、usage费用与审计状态。
- `paired-results.json` / `.csv`：118个条件的逐组结果、首次和累计token；JSON保留服务器原始日志路径。
- `untriggered.json`：82个未触发条件，单列、不加入图替换分母。
- `behavior-evidence.json`：20道结果有分歧的题的工具轨迹摘要；长字符串为便于阅读而截短，完整原始证据没有改动。
- `protocol.json`：本轮范围、接入点、复用和预算设置；省略凭据配置路径。
- `preflight-result.json` / `preparation-audit.json`：114道不收费重放检查、来源覆盖核对。
- `frozen-sha256.json`：冻结代码文件校验值；`dependency-repair.json`记录数学库缺失的环境修复，发生在任何付费请求之前。

除整理的protocol外，上述JSON/CSV都是已完成实验记录的内容不变副本。未搬移、改写原始轨迹，未提交凭据、运行环境或全部API日志。原始目录：`/home/ruqi/public/CS769/experiments/bfcl_identity/g9_eventprotocol_official_118_20261104`；旧对照与smoke来源见protocol。完整检查：114新增＋4复用＝118，全部冻结哈希、完整证据和官方评分轨迹核对通过。新增114道648个请求，无不确定计费请求。
