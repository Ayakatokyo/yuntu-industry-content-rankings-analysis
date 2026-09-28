# 云图-行业灵感-素材详情

## 运行时契约

- 唯一固化身份：`connectorCode=rpa.conn.juliang.yt.industry.content.rankings.details`
- 平台、入参 Schema/列表和出参说明每次从 `/dcConnector/v3/listByConnectorCode` 实时读取
- 用 `scripts/rpa_dynamic_detail_client.py detail/schema/validate` 查看和校验，不使用本页的历史字段作为传参权威
- 详情动态客户端不提供独立 `fetch` 取数；所有详情采集使用 `scripts/rpa_connector.py fetch` 经过首批 CSV 门禁。不能以 `--no-download` 或独立客户端绕过。

## 素材详情首批 CSV 门禁（2026-09-25）

对 `rpa_rpa.conn.juliang.yt.industry.content.rankings.details`，首批最多 3 条（实际不足 3 条按实际数量），提交前固定首批素材 ID，必须等首批全部结果确认后再判断下一批。有效 CSV 必须实际下载、成功解析、包含目标素材的明确身份及详情业务记录，并通过周期/身份校验；仅有任务成功、fileUrl、JSON payload、空文件、只有表头、错误页面、错误信息或无法解析的业务单元格均不算有效 CSV。合法空趋势可以记录为 `source_empty`；视频下载、抽帧等后处理失败不取消已验收的 CSV。

`firstBatchCsvGate` 随 manifest 和摘要持久化，状态为 `pending / passed / blocked / unconfirmed`。首批全部结束且有效 CSV 为 0 时，整体状态写 `paused`，门禁写 `blocked` / `first_batch_no_valid_csv`，立即暂停当前运行后续所有 RPA 提交，包括下一批、候选补位、重试和普通恢复中的新榜单请求，并提示：“首批素材详情 RPA 未返回有效 CSV，当前入参可能有问题，已暂停后续所有 RPA；请检查账号、日期、筛选/素材定位参数，修正后使用新运行目录重新验证首批。”这是异常提示，不是确认入参必然错误。

提交结果不明、轮询超时、网络错误或未知远端状态记 `unconfirmed`，不能当作远端确定失败，也不得提前提交下一批；恢复只可查询已登记的首批任务 ID，没有 ID 时保持暂停。只有首批全部结果已确认且至少 1 份有效 CSV，门禁才 `passed` 并允许原有失败补位。普通 `fetch` 不会清除 `blocked`，不得删除门禁、改 manifest、换候选或把重试计为新首批来绕过；复核并修正参数后使用新运行目录重新验证。历史 JSON 仍可用于本地分析，但不能代替新采集门禁的 CSV 证据。

## 请求与任务协议

历史批次使用过以下业务结构，仅作业务语义参考：

```json
{
  "material_id": "7659409261740343346",
  "date_type": "LAST_7_DAYS"
}
```

素材 ID 必须来自已验证的榜单记录；品牌、触点和候选分组只在本地调度，不能透传。新任务的自定义周期字段、日期格式和枚举以当次实时 Schema 为准。

通过 `POST /adg/v1/agent/fetch/tasks` 提交，随后以 `POST /adg/v1/agent/fetch/tasks/status` 用 `task_group_id` 查询。单次 HTTP 请求为 30 秒，查询间隔 10 秒，`completed` 与 `partial_success` 是可物化的成功终态。收到任务 ID 后先原子写入 `batch-manifest.json.taskRuns`；恢复同一输出目录时只查询该 ID。

## 输出与规范化

输出可能是 CSV 文件或记录，详情区块包括 `coreData`、`audiencePortrait`、`secondTrend`、`contentFormula` 和 `creativeBreakdown`。规范化文件为 `normalized/detail-records/<material_id>.json`，保留来源路径与 SHA-256。根 `materialId` 与 `coreData.objectId` 同时存在但不一致时拒绝；相对周期只校验 `dateType`，不从目录名推断实际日期。
