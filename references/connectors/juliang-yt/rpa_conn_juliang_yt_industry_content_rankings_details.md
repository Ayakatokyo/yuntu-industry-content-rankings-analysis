# 云图-行业灵感-素材详情

## 固定元数据

- `function_code`: `rpa.conn.juliang.yt.industry.content.rankings.details`
- `platform`: `RPA_JULIANG_YT_ACCOUNT_PASSWORD`
- `data_source_type`: `rpa`

## 请求与任务协议

详情只接收以下业务字段：

```json
{
  "material_id": "7659409261740343346",
  "date_type": "LAST_7_DAYS"
}
```

自定义周期使用 `date_type: "CUSTOM"`，并同时传 `custom_start_date` 与 `custom_end_date`（`YYYYMMDD` 或 `YYYY-MM-DD`）。素材 ID 必须来自已验证的榜单记录；品牌、触点和候选分组只在本地调度，不能透传。

通过 `POST /adg/v1/agent/fetch/tasks` 提交，随后以 `POST /adg/v1/agent/fetch/tasks/status` 用 `task_group_id` 查询。单次 HTTP 请求为 30 秒，查询间隔 10 秒，`completed` 与 `partial_success` 是可物化的成功终态。收到任务 ID 后先原子写入 `batch-manifest.json.taskRuns`；恢复同一输出目录时只查询该 ID。

## 输出与规范化

输出可能是 CSV 文件或记录，详情区块包括 `coreData`、`audiencePortrait`、`secondTrend`、`contentFormula` 和 `creativeBreakdown`。规范化文件为 `normalized/detail-records/<material_id>.json`，保留来源路径与 SHA-256。根 `materialId` 与 `coreData.objectId` 同时存在但不一致时拒绝；相对周期只校验 `dateType`，不从目录名推断实际日期。
