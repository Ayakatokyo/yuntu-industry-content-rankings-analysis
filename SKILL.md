---
name: 云图行业内容榜单分析
description: 适用于需要通过固定预策 RPA 连接器，将云图行业内容榜单限制在选定素材范围内并获取秒级详情的场景。
---

# 云图行业内容榜单分析

使用此独立技能，通过 `rpa.conn.juliang.yt.industry.content.rankings.list` 获取云图行业内容榜单，按响应顺序选择最先出现的唯一数字型 `material_id`，再通过 `rpa.conn.juliang.yt.industry.content.rankings.detail` 获取每个入选素材的详情。连接器元数据在内部固定，不能提供或覆盖。

## 运行环境要求

调用网关前，设置以下环境变量：

- `ENV_BACKEND_HOST`：受信任的纯 HTTPS 网关 URL，不得使用 IP 字面量、userinfo、查询参数或片段。
- `YUCE_AUTHORIZATION`：网关授权值。
- `YUCE_SESSION_ID`：网关代理会话 ID。

凭证应保留在环境变量中。不要将凭证写入命令、输入 JSON 或输出路径。未知 `shop_id` 时，运行 `list-accounts`。

## 参数

`fetch` 接受列表连接器可选的 `--industry`、时间范围、年龄、性别、人群、品牌范围、品牌和榜单限制筛选项。列表自定义日期与列表技能使用相同的 Asia/Shanghai 限制。详情日期使用 `--detail-date-range-type`（`LAST_7_DAYS`、`LAST_30_DAYS` 或 `CUSTOM`）；详情自定义日期必须同时提供 `--detail-custom-start-date` 和 `--detail-custom-end-date`，且结束日期不得早于开始日期。

`--top-n` 必须为正整数，默认值为 `10`。它限制响应顺序中最先出现的唯一数字型素材 ID 数量。`material_id` 始终从列表响应中选择，不能作为详情覆盖参数提供。

列表筛选标志为 `--industry`、`--time-range-type`、`--custom-start-date`、`--custom-end-date`、`--ages`、`--genders`、`--crowd-groups`、`--brand-scope-type`、`--brands` 和 `--ranking-limit-type`。

## 命令

从工作区根目录运行命令。此技能需要 Python 和 `requests>=2.31,<3`。

列出已授权账户：

```bash
python yuntu-industry-content-rankings-analysis/scripts/rpa_connector.py list-accounts
```

输出分析参数元数据：

```bash
python yuntu-industry-content-rankings-analysis/scripts/rpa_connector.py schema
```

运行不访问网关的离线检查：

```bash
python yuntu-industry-content-rankings-analysis/scripts/rpa_connector.py self-test
```

获取列表以及最多十个入选素材的秒级详情：

```bash
python yuntu-industry-content-rankings-analysis/scripts/rpa_connector.py fetch \
  --shop-id "<shop_id>" \
  --industry "食品饮料" \
  --time-range-type "LAST_7_DAYS" \
  --detail-date-range-type "LAST_7_DAYS" \
  --top-n 10 \
  --output-dir "RPA数据汇总/yuntu-rankings-analysis"
```

对于自定义详情范围，添加 `--detail-date-range-type "CUSTOM"`，并同时提供 `--detail-custom-start-date` 与 `--detail-custom-end-date`。

## 输出与失败处理

输出目录会以原子方式写入以下文件：

- `list-response.json`：原始成功列表响应。
- `details/<material_id>.json`：每个原始成功详情响应。
- `manifest.json`：筛选条件、选中 ID、相对响应路径、每个素材的状态及非敏感错误摘要。

若列表请求失败或没有有效素材 ID，命令会写入清单并以非零状态退出，且不会开始详情请求。详情请求失败会被记录，后续选中素材仍会继续；只要任一详情失败，命令就以非零状态退出，同时成功的详情 JSON 文件仍可使用。

此技能不下载视频、不处理 `files` 结果、不提取帧、不重试请求，也不恢复中断任务；不生成报告。
