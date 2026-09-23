# 云图连接器交接简化设计

## 目标

减少连接器向批处理流程交接时重复创建 `ConnectorInvoker` 的代码，并删除重试循环中未使用的局部变量，不改变任何运行行为。

## 范围

- 在 `scripts/rpa_connector.py` 增加私有 `_batch_invoker()`，返回与现有三个调用点等价的 `ConnectorInvoker`。
- `fetch_batch_analysis()`、`retry_failed_batch_analysis()` 和 `retry_unresolved_batch_analysis()` 都改为调用该 helper。
- 删除 `scripts/yuntu_batch.py` 的 `_retry_batch_items()` 中未使用的 `rank = item.get("rank")`。

## 不变项

- CLI 参数、固定 RPA function code、网关请求、超时、认证读取与 `RpaConnectorError` 转换。
- 详情波次并发、高光并发、异步状态观察、批次落盘、恢复、分组补位与两类重试语义。
- `batch-manifest.json`、`run-summary.json`、规范化记录、事实包与报告 schema。

## 设计

`_batch_invoker()` 保留原有 lambda 转发形式，使 invoker 在调用时仍解析当前的 `invoke_list` 和 `invoke_detail`，避免将可替换的模块级入口过早绑定。三个公开包装函数只复用 invoker 构造，不合并各自的可用性错误信息、参数验证或异常转换。

批处理重试中的 `rank` 已读取但从未参与请求、状态、排序或输出。删除它不会改变数据流；排序继续基于 manifest 条目中的 `rank` 字段执行。

## 验证

- 先写 `_batch_invoker()` 的失败测试，验证其列表和详情转发仍调用公开入口。
- 先写死变量存在性测试，确认当前源码包含该无效赋值后再删除。
- 执行连接器、批处理和全量测试；检查 diff 不含调度、状态或 schema 变更。
- 真实 RPA 回归仍仅在完整运行时认证变量存在时执行，且不输出认证值。
