# G9 的结构与实际模型输入

**代码入口：** [G9 接入说明](../../../docs/g9-memory.md) ·
[构图与渲染入口](../../../scripts/core/g9_memory.py) ·
[离线示例](../../../examples/g9_memory.py)。发布的是下文 R／full view 对应的冻结实现，包含 G5 依赖和测试。

[新增验证](g9-expanded-validation-results.md) · [上一批验证](g9-independent-validation-results.md) · [已有 G5 报告](g5-graph-replacement.md)

G5 保存完整事件、角色、轮次、顺序和工具调用—返回关系。G8 把工具字段解析成有独立内容所有权的树；G9 再连接公开工具字段规则下、同一命名空间和类型的相同 ID。每条连接有来源支持；它不是因果、任务依赖或“当前状态”推断。[实际节点、来源及冻结代码哈希](evidence/g9/g5-g8-g9-base194-input-evidence.json)

模型只收到由图生成的历史表示，不另外附带原生 identity 前缀。R 先显示完整 G5 证据正文，再显示 ID 记录连接；G8 内部地址没有全部展开，派生观察层关闭。[冻结范围](evidence/g9/g9-expanded-increment-scope-v1.json)

以既有 GPT-4.1 base_194 完成第三轮后的前缀为例，图含 3 个 episode、16 个事件；10 个工具字段中 9 个可解析 JSON、1 个 opaque。G9 有 3 个 record、4 个标识出现位置、2 个同值组和 4 条 membership 边。[实例审计](evidence/g9/g5-g8-g9-base194-input-evidence.json)

```text
book_flight 返回 /booking_id = 3426812
                  │ 相同 namespace、类型与值
purchase_insurance 参数 /booking_id = 3426812
```

实际输入可直接查看：[完整 G5 正文 E](evidence/g9/g5-g8-g9-base194-E-memory.txt)、[完整 G9 正文 R](evidence/g9/g5-g8-g9-base194-R-memory.txt)。这是冻结编译器对既有前缀的离线输出，不是新的续跑结果；不含工具定义、当前用户请求和 API 信封。字符数为 E 4,556、R 4,988，不是 token 数。[渲染核验](evidence/g9/g5-g8-g9-base194-input-evidence.json)

后续可以按字段定位内容，并检查删除后哪些关系失去来源：该例删除 booking_status 的未应用预览为 102→79 字符，连接仍有 ID 证据；删除 booking_id 的预览为 102→78 字符，对应 booking 连接失效。两份预览均 applied=false、task_preservation_certified=false；没有实际投喂压缩图，也不能把结构合法等同任务安全。[完整计划与边界](evidence/g9/g5-g8-g9-base194-input-evidence.json)
