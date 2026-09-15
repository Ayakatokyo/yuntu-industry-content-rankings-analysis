# 云图-行业灵感-行业内容榜列表

## 运行时契约

- 唯一固化身份：`connectorCode=rpa.conn.juliang.yt.industry.content.rankings.list`
- 每次先调用 `/dcConnector/v3/listByConnectorCode`，平台原样使用返回的 `platformCode`
- `inParamJsonSchemaText` 非空时按 Draft 2020-12 原文校验；仅为 `null` 时使用 `inParamList`
- `outParamList` 用于与实际 CSV 字段交叉核对，不用于伪造缺失字段

## 适用场景

采集巨量云图行业灵感页行业内容榜视频列表，支持按行业、时间、品牌范围、品牌、年龄、性别、八大人群和榜单限制筛选。

## 历史业务语义参考

行业、时间、品牌范围、品牌、年龄、性别、八大人群和榜单限制是该链路保留的业务意图。旧字段名曾包括 `industry`、`time_range_type`、`custom_start_date`、`custom_end_date`、`ages`、`genders`、`crowd_groups`、`brand_scope_type`、`brands`、`ranking_limit_type`；它们只用于理解历史批次，新任务必须以实时详情契约为准。

业务 JSON 使用 `scripts/rpa_dynamic_client.py validate --params-json/--params-file` 先校验，下发前还会再次反查和校验。

## 当前技能附加行为

- 按列表响应顺序选择最先出现的唯一数字型 `material_id`
- 以 `candidate_top_n` 建立候选池
- 为后续详情拉取和分析生成 `normalized/list-records.json`
