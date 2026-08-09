---
name: 云图行业内容榜单分析
description: 适用于通过固定预策 RPA 连接器获取竞品内容榜单与秒级详情，并生成小仙炖内容策略报告的场景。
argument_hint: 输入行业、分析时间范围（优先填云图界面显示的真实起止日期）、榜单筛选项和 Top素材数量，生成小仙炖行业内容榜单分析报告。
metadata:
  pre_input: 帮我生成云图行业内容榜单分析报告，行业是 ____，分析时间范围是 ____（云图界面真实起止日期，如 2026-07-26 至 2026-08-01；未填写则列表和素材详情均使用云图默认近七天），榜单筛选项是 ____，Top素材数量是 ____。
---

# 云图行业内容榜单分析

## 用户输入与时间口径

调用本技能时，提示词应提供以下业务信息：

- `行业`：必填，例如“食品饮料”。
- `分析时间范围`：榜单和素材详情共用。优先填写云图界面日期控件实际展示的闭区间，例如截图中的“近七天”应写为 `2026-07-26 至 2026-08-01`，不要只写“近七天”。未填写时，二者均使用云图默认“近七天”。
- `榜单筛选项`：按需填写品牌范围、指定品牌、年龄、性别、八大人群和榜单限制；未填写的筛选项保持云图默认，不擅自补充。
- `Top素材数量`：最终希望完成秒级拆解并纳入报告的素材数；未填写时为 `10`。

时间范围必须以云图界面当次实际显示的日期为准，且首尾日期均包含在内。用户写“近七天”或其他相对周期时，执行前先在云图界面确认并在运行记录中写明对应的真实起止日期。榜单和素材详情必须使用同一时间范围：用户给出明确起止日时，二者均使用该闭区间；不得以执行机本地日期自行推算或将示例日期当作固定默认值。

默认映射如下：未指定时间范围时，榜单和详情均使用 `LAST_7_DAYS`。提供真实起止日期时，榜单使用 `--time-range-type CUSTOM --custom-start-date/--custom-end-date`，详情同时使用 `--detail-date-range-type CUSTOM --detail-custom-start-date/--detail-custom-end-date`，两端传入相同的起止日期。

本技能使用固定连接器：

- `rpa.conn.juliang.yt.industry.content.rankings.list`
- `rpa.conn.juliang.yt.industry.content.rankings.detail`

连接器元数据已固化在脚本内部，不能让用户或 AI 覆盖 `function_code`、`platform` 或 `data_source_type`。运行前先阅读本地知识页，再执行脚本：

- `references/platforms/juliang-yt.md`
- `references/connectors/juliang-yt/rpa_conn_juliang_yt_industry_content_rankings_list.md`
- `references/connectors/juliang-yt/rpa_conn_juliang_yt_industry_content_rankings_detail.md`

主流程是：列表取数 -> 按响应顺序挑选唯一数字型 `material_id` -> 拉取秒级详情 -> 规范化 -> 准备分析事实包 -> 生成小仙炖结构化洞察 -> 渲染最终报告。RPA 大概率返回 `files-envelope` 和 CSV 文件；脚本会下载原始 CSV、转换为 `normalized` JSON records，再基于规范化数据生成分析事实包和报告。

一次 `fetch` 执行只允许调用一次列表连接器：先调用
`rpa.conn.juliang.yt.industry.content.rankings.list`，再从列表响应中按顺序选取
`material_id`，逐个调用 `rpa.conn.juliang.yt.industry.content.rankings.detail`。
列表连接器完成后必须先完成结构化落盘：`normalized/list-records.json` 保存素材本身的标题、身份、发布时间、指标、标签和列表筛选上下文；`normalized/detail-request-params.json` 保存下一步详情连接器所需的 `material_id` 与详情日期参数。详情连接器只消费后者，分析事实包消费前者和成功详情记录。
详情阶段中断后，用相同筛选参数重新执行时，若 `raw-csv/list.csv` 已完整落盘，脚本会复用该列表文件并只补调详情，不重复调用列表连接器；变更筛选参数才会重新取列表。

## 运行环境要求

调用网关前，设置以下环境变量：

- `ENV_BACKEND_HOST`：平台运行时注入的受信任网关基地址，可为 HTTP/IP 或含 `/api` 的路径前缀；不得使用 userinfo、查询参数或片段。
- `YUCE_AUTHORIZATION`：网关授权值。
- `YUCE_SESSION_ID`：网关代理会话 ID。

凭证应保留在环境变量中。不要将凭证写入命令、输入 JSON 或输出路径。保留平台运行时注入的 `ENV_BACKEND_HOST`，不要用 `.env` 中的值覆盖它。未知 `shop_id` 时，运行 `list-accounts`。

## 参数

`fetch` 接受列表连接器可选的 `--industry`、时间范围、年龄、性别、人群、品牌范围、品牌和榜单限制筛选项。`ages`、`genders`、`crowd_groups` 只做格式校验，不做本地枚举阻断，以兼容平台新增或未固化值。列表自定义日期与列表技能使用相同的 Asia/Shanghai 限制。

详情日期使用 `--detail-date-range-type`（`LAST_7_DAYS`、`LAST_30_DAYS` 或 `CUSTOM`），但必须与榜单时间范围一致；详情自定义日期必须同时提供 `--detail-custom-start-date` 和 `--detail-custom-end-date`，且结束日期不得早于开始日期。

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

对于自定义范围，榜单与详情均使用 `CUSTOM`，并传入相同的起止日期。

准备分析事实包：

```bash
python <skill-root>/scripts/rpa_connector.py prepare-analysis \
  --input-dir "RPA数据汇总/yuntu-rankings-analysis" \
  --output-dir "RPA数据汇总/yuntu-rankings-analysis/diagnostic-analysis"
```

需要截取高光帧时，在 `prepare-analysis` 增加 `--highlight-trends`，可多选“点赞指数”“流失指数”“点击指数”“互动指数”“评论指数”：

```bash
python <skill-root>/scripts/rpa_connector.py prepare-analysis \
  --input-dir "RPA数据汇总/yuntu-rankings-analysis" \
  --output-dir "RPA数据汇总/yuntu-rankings-analysis/diagnostic-analysis" \
  --highlight-trends "点击指数" "互动指数"
```

每条素材固定截取 `0s` 封面帧；每个选中指标另取最多 3 个局部波峰，跨指标同秒只保留一张并合并指标说明。帧写入 `highlights/<material_id>/`，清单为 `highlights-manifest.json`。视频下载或截图失败只记录失败原因，不阻断事实包或最终报告；HTML 会展示成功帧，不输出失败图片。

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
- `normalized/detail-request-params.json`：传入详情 RPA 的素材 ID 与日期参数。
- `normalized/detail-records/<material_id>.json`：规范化详情 records。
- `normalized/top-materials-rpa-ready.json`：最终可分析素材列表。
- `batch-manifest.json`：候选、提交、入选、失败、取消素材及路径和耗时。

分析阶段只读取 `normalized/` 和 `diagnostic-analysis/`，不直接读取原始 CSV、RPA response 或临时 `fileUrl`。CSV 单元格同时兼容标准 JSON 和安全的 Python 字面量；RPA 导出的字段边缘控制字符与控制字符空行会被清理，不会被误识别为素材。无法安全解析的嵌套字段保留原文本，并在规范化产物中标记缺失原因。

## 商业分析与报告

`prepare-analysis` 会以完整榜单作为候选池、以成功详情素材作为秒级诊断范围，计算指标均值、中位数、分位与分层，汇总人群和内容标签覆盖，并归纳高点与流失区间。候选池少于四条时不输出高表现分层或标签关联；缺少指标、标签或趋势时必须写“数据不足以判断”，不得补造结论。

模型读取事实包后，必须写入包含以下七个键的 `yuntu-ai-analysis.json`：

1. `topMaterialCombination`：TOP 素材组合结论
2. `rankingOverview`：榜单机会总览
3. `materialComparison`：素材表现对比
4. `materialDiagnoses`：单素材秒级诊断
5. `competitorPatterns`：竞品创意模式
6. `xiaoxianDunOpportunityMap`：小仙炖机会地图
7. `experimentMatrix`：下一轮实验矩阵

`topMaterialCombination` 包含 `overallConclusions`、`brandConclusions` 与 `brandComparisonConclusion`。`overallConclusions` 必须且只能包含 `data`、`people`、`marketing` 三个维度；`brandConclusions` 的每个品牌必须包含 `dataSummary`、`peopleSummary`、`marketingSummary`；`brandComparisonConclusion` 必须基于每个参与品牌的指标证据总结横向差异。整体结论分析品牌筛选条件下 TOP30 的曝光、CTR、CVR、PVR、3S/5S/完播、互动、组件点击和平均播放时长，以及年龄、性别、八大画像和营销卖点。品牌结论按标题匹配规则独立分析各品牌下 TOP30：万益蓝/WONDERLAB 命中“万益蓝”或“wonderlab”，五个女博士命中“五个女博士”，燕之屋命中“燕之屋”。标题匹配是业务分类，不是 RPA 原生品牌字段；未知品牌保留在品牌筛选条件下 TOP30，但不进入品牌 TOP30；命中多个品牌的标题标为歧义并不进入品牌对比。

人群标签同时给出素材数量占比和曝光加权覆盖率。标签可以重叠，因此曝光加权覆盖率不可相加为 100%，也不得写成真实人群比例。CPM 未由 RPA 提供时必须显示不可用，禁止从曝光或其他指标推算。卖点与指标只能描述共现，不得声称因果；某标签的有/无标签比较任一侧样本少于 3 条时写“数据不足以判断”。

前五章中每项必须带有 `summary`、`evidence` 及 `material_id` 或 `material_ids`。实验矩阵每项必须包含 `priority`、`hypothesis`、`creative_variable`、`target_audience`、`success_metric`、`control` 和 `review_action`。涉及滋补、孕期、功效或健康人群的方向只能作为需业务和合规确认的测试假设。

`render-report` 会拒绝缺少章节、证据、素材引用或实验字段的 JSON；它只将已验证的洞察渲染为 Markdown/HTML，不新增业务判断。

HTML 报告使用深棕、暖金、米白的离线视觉系统。报告正文只展示结论与必要关键数字，结构化 `evidence` 保留在 `final-report-data.json`，不进入用户可读报告正文，也不展示为可展开区域。高光帧预览必须支持点击、键盘焦点和 Escape 关闭；失败帧不输出损坏图片，素材诊断继续保留。

报告统一视觉与交互资产位于本技能 `assets/report/`，`render-report` 会将 CSS 和 JavaScript 自动内联到 `final-report.html`，成品不依赖外部样式或脚本文件。不得手工修改成品 HTML 绕过渲染器。

交付前只需用桌面 `1440x1000` 视口检查封面、左侧目录、章节卡片、人群图表和预览层，确认无文本遮挡、正文横向溢出或不可见的键盘焦点；本技能不要求移动端验收。HTML 不得依赖远程图片、脚本或数据请求；归档为单文件时，高光帧须压缩后以 data URI 内嵌。

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
