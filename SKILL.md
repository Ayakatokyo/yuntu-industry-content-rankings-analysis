---
name: 云图行业内容榜单分析
description: 适用于需要通过固定预策 RPA 连接器，将云图行业内容榜单限制在选定素材范围内并获取秒级详情的场景。
---

# 云图行业内容榜单分析

本技能使用固定连接器：

- `rpa.conn.juliang.yt.industry.content.rankings.list`
- `rpa.conn.juliang.yt.industry.content.rankings.detail`

连接器元数据已固化在脚本内部，不能让用户或 AI 覆盖 `function_code`、`platform` 或 `data_source_type`。运行前先阅读本地知识页，再执行脚本：

- `references/platforms/juliang-yt.md`
- `references/connectors/juliang-yt/rpa_conn_juliang_yt_industry_content_rankings_list.md`
- `references/connectors/juliang-yt/rpa_conn_juliang_yt_industry_content_rankings_detail.md`

主流程是：列表取数 -> 按响应顺序挑选唯一数字型 `material_id` -> 拉取秒级详情 -> 规范化 -> 准备分析事实包 -> 渲染最终报告。RPA 大概率返回 `files-envelope` 和 CSV 文件；脚本会下载原始 CSV、转换为 `normalized` JSON records，再基于规范化数据生成分析事实包和报告。

## 运行环境要求

调用网关前，设置以下环境变量：

- `ENV_BACKEND_HOST`：平台运行时注入的受信任网关基地址，可为 HTTP/IP 或含 `/api` 的路径前缀；不得使用 userinfo、查询参数或片段。
- `YUCE_AUTHORIZATION`：网关授权值。
- `YUCE_SESSION_ID`：网关代理会话 ID。

凭证应保留在环境变量中。不要将凭证写入命令、输入 JSON 或输出路径。保留平台运行时注入的 `ENV_BACKEND_HOST`，不要用 `.env` 中的值覆盖它。未知 `shop_id` 时，运行 `list-accounts`。

## 参数

`fetch` 接受列表连接器可选的 `--industry`、时间范围、年龄、性别、人群、品牌范围、品牌和榜单限制筛选项。`ages`、`genders`、`crowd_groups` 只做格式校验，不做本地枚举阻断，以兼容平台新增或未固化值。列表自定义日期与列表技能使用相同的 Asia/Shanghai 限制。

详情日期使用 `--detail-date-range-type`（`LAST_7_DAYS`、`LAST_30_DAYS` 或 `CUSTOM`）；详情自定义日期必须同时提供 `--detail-custom-start-date` 和 `--detail-custom-end-date`，且结束日期不得早于开始日期。

`--top-n` 必须为正整数，默认值为 `10`，兼容旧用法。新增批次口径中，`--target-top-n` 表示最终希望分析成功的素材数量；`--candidate-top-n` 表示从榜单中保留的候选池上限，默认可按目标数量的 3 倍理解。`material_id` 始终从列表响应中选择，不能作为详情覆盖参数提供。

列表筛选标志为 `--industry`、`--time-range-type`、`--custom-start-date`、`--custom-end-date`、`--ages`、`--genders`、`--crowd-groups`、`--brand-scope-type`、`--brands` 和 `--ranking-limit-type`。

## 命令

从工作区根目录运行命令。此技能需要 Python 和 `requests>=2.31,<3`。先把 `<skill-root>` 替换为当前技能目录。

列出已授权账户：

```bash
python <skill-root>/scripts/rpa_connector.py list-accounts
```

输出分析参数元数据：

```bash
python <skill-root>/scripts/rpa_connector.py schema
```

运行不访问网关的离线检查：

```bash
python <skill-root>/scripts/rpa_connector.py self-test
```

获取列表以及最多十个入选素材的秒级详情：

```bash
python <skill-root>/scripts/rpa_connector.py fetch \
  --shop-id "<shop_id>" \
  --industry "食品饮料" \
  --time-range-type "LAST_7_DAYS" \
  --detail-date-range-type "LAST_7_DAYS" \
  --target-top-n 10 \
  --candidate-top-n 30 \
  --output-dir "RPA数据汇总/yuntu-rankings-analysis"
```

对于自定义详情范围，添加 `--detail-date-range-type "CUSTOM"`，并同时提供 `--detail-custom-start-date` 与 `--detail-custom-end-date`。

准备分析事实包：

```bash
python <skill-root>/scripts/rpa_connector.py prepare-analysis \
  --input-dir "RPA数据汇总/yuntu-rankings-analysis" \
  --output-dir "RPA数据汇总/yuntu-rankings-analysis/diagnostic-analysis"
```

模型读取 `diagnostic-analysis/yuntu-analysis-data.json` 和 `diagnostic-analysis/yuntu-analysis-prompt.md` 后，生成 `diagnostic-analysis/yuntu-ai-analysis.json`。渲染最终报告：

```bash
python <skill-root>/scripts/rpa_connector.py render-report \
  --analysis-json "RPA数据汇总/yuntu-rankings-analysis/diagnostic-analysis/yuntu-ai-analysis.json" \
  --output-dir "RPA数据汇总/yuntu-rankings-analysis/final-report"
```

仅重试已有批次中的失败详情：

```bash
python <skill-root>/scripts/rpa_connector.py retry-failed \
  --shop-id "<shop_id>" \
  --output-dir "RPA数据汇总/yuntu-rankings-analysis"
```

## CSV 主路径与规范化

RPA 返回 `files-envelope` 时，脚本会校验 `success`、`code`、`result_type`、`status`、`failedInstances` 和 `files[0].fileUrl`，然后下载 CSV。`fileUrl` 只作为临时下载入口，不写入后续分析产物。直接 JSON 或 payload records 仅作为兼容路径。

`fetch` 会写出：

- `raw-csv/list.csv`：榜单 RPA 原始 CSV。
- `raw-csv/details/<material_id>.csv`：单素材详情 RPA 原始 CSV。
- `raw-json/list-response.json`：直接 JSON 或 payload 兼容路径下的榜单原始响应。
- `raw-json/details/<material_id>.json`：直接 JSON 或 payload 兼容路径下的详情原始响应。
- `normalized/list-records.json`：规范化榜单 records。
- `normalized/detail-records/<material_id>.json`：规范化详情 records。
- `normalized/top-materials-rpa-ready.json`：最终可分析素材列表。
- `batch-manifest.json`：候选、提交、入选、失败、取消素材及路径和耗时。

分析阶段只读取 `normalized/` 和 `diagnostic-analysis/`，不直接读取原始 CSV、RPA response 或临时 `fileUrl`。

## 输出与失败处理

输出目录会以原子方式写入以下文件：

- `list-response.json`：原始成功列表响应。
- `details/<material_id>.json`：每个原始成功详情响应。
- `manifest.json`：旧版串行详情流程的清单输出。
- `batch-manifest.json`：CSV 主路径批次清单，区分 `selectedMaterials`、`rejectedMaterials` 和 `cancelledMaterials`。
- `diagnostic-analysis/yuntu-analysis-data.json`：分析事实包。
- `diagnostic-analysis/yuntu-analysis-prompt.md`：模型分析提示。
- `diagnostic-analysis/yuntu-ai-analysis.json`：模型生成的结构化分析结论。
- `final-report/final-report-data.json`、`final-report/final-report.md` 和 `final-report/final-report.html`：最终报告产物。

先运行 `list-accounts` 确认注入网关可用，再运行 `fetch`。若返回 404，检查注入网关是否缺少或多出平台基路径；若返回 504，保留 `batch-manifest.json` 并按网关超时排查，不要将其解释为无素材。

若列表请求失败或没有有效素材 ID，命令会写入清单并以非零状态退出，且不会开始详情请求。详情请求失败会被记录，后续选中素材仍会继续；只要任一详情失败，命令就以非零状态退出，同时成功的详情 JSON 文件仍可使用。

`retry-failed` 只重试 `batch-manifest.json` 中的 `rejectedMaterials`，不会重跑列表请求，也不会重复请求已经成功落盘的详情。

此技能不下载视频、不提取帧。报告由 `prepare-analysis` 生成事实包、模型写入 `yuntu-ai-analysis.json`、再由 `render-report` 渲染；渲染器本身不调用外部模型，也不生成新的业务判断。
