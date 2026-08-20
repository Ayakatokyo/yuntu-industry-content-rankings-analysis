---
name: 云图行业内容榜单分析
description: 适用于通过固定预策 RPA 连接器获取行业内容榜单与秒级详情，并生成内容策略报告的场景。
argument_hint: 输入行业、分析周期（近7天、近30天或自定义起止日期）、指定品牌、截取方式、年龄、性别、八大人群、品牌榜单Top素材数和秒级拆解素材数，生成行业内容榜单分析报告。
metadata:
  pre_input: 帮我生成云图行业内容榜单分析报告，行业是 ____，分析周期是 ____（近7天、近30天或自定义起止日期；近7天/近30天直接使用云图周期定义，不换算为自定义日期），指定品牌是 ____（至少3个品牌），截取方式是 ____（曝光量TOP1000、CTRTOP1000、互动率TOP1000、完播率TOP1000），年龄是 ____（可选；不填写则不筛选，即全选），性别是 ____（可选；不填写则不筛选，即全选），八大人群是 ____（可选；不填写则不筛选，即全选），品牌榜单Top素材数是 ____（默认30），秒级拆解素材数是 ____（默认10）。
---

# 云图行业内容榜单分析

## 输入与时间

- `行业`必填；`指定品牌`可选，填写时提供 3 至 10 个品牌并使用 `SPECIFIED_BRANDS`。
- `截取方式`支持曝光量TOP1000、CTRTOP1000、互动率TOP1000、完播率TOP1000；年龄、性别、八大人群不填写时不传筛选参数（全选）。品牌榜单 Top 素材数默认 30，秒级拆解素材数默认 10。
- 榜单和素材详情必须使用同一分析周期：近7天=`LAST_7_DAYS`，近30天=`LAST_30_DAYS`，不换算为自定义日期；未填写时默认近七天。明确起止日时，两端均使用 `CUSTOM` 和相同闭区间（首尾包含）。云图界面日期只作展示核对。

## 固定依赖

固定连接器：`rpa.conn.juliang.yt.industry.content.rankings.list`、`rpa.conn.juliang.yt.industry.content.rankings.detail`。元数据由脚本固化，不接受覆盖。运行前阅读：

- `references/platforms/juliang-yt.md`
- `references/connectors/juliang-yt/rpa_conn_juliang_yt_industry_content_rankings_list.md`
- `references/connectors/juliang-yt/rpa_conn_juliang_yt_industry_content_rankings_detail.md`

网关使用平台运行时注入的 `ENV_BACKEND_HOST`、`YUCE_AUTHORIZATION`、`YUCE_SESSION_ID`；凭证保留在环境变量，不写入命令、JSON 或输出路径，也不要用 `.env` 覆盖网关地址。未知 `shop_id` 先运行 `list-accounts`。404 检查基路径，504 网关超时则保留批次证据后用 `status` 排查。

## 主流程

流程固定为：列表 -> 选择唯一数字型 `material_id` -> 详情 -> 规范化 -> 事实包 -> 模型洞察 -> 报告。RPA 优先走 `files-envelope`/CSV，先落盘原始文件，再生成 `normalized` records。

```bash
python <skill-root>/scripts/rpa_connector.py list-accounts
python <skill-root>/scripts/rpa_connector.py schema
python <skill-root>/scripts/rpa_connector.py self-test
python <skill-root>/scripts/rpa_connector.py status --output-dir "RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-top5"
```

```bash
python <skill-root>/scripts/rpa_connector.py fetch \
  --shop-id "<shop_id>" --industry "食品饮料" \
  --time-range-type "LAST_7_DAYS" --detail-date-range-type "LAST_7_DAYS" \
  --target-top-n 10 --candidate-top-n 30 \
  --output-dir "RPA数据汇总/yuntu-rankings-analysis"
```

自定义范围时，两端改为 `CUSTOM` 并传入 `--custom-start-date`、`--custom-end-date`、`--detail-custom-start-date`、`--detail-custom-end-date`。`--target-top-n` 是最终成功素材数，`--candidate-top-n` 默认是其 2 倍；`--top-n` 默认 10 仅为兼容旧用法。列表筛选使用 `--industry`、时间范围、`--ages`、`--genders`、`--crowd-groups`、`--brand-scope-type`、`--brands`、`--ranking-limit-type`。

`fetch` 是长任务：通过异步会话和 `status` 观察落盘，单次 RPA 最多等待 300 秒。列表只调用一次，完成后先写 `normalized/list-records.json` 和 `normalized/detail-request-params.json`，详情只消费后者。详情每波最多并行 2 个素材；本波详情与高光任务全部终态后才启动下一波。高光固定含 `0s`，再从“点击指数”局部峰值按点击值降序、秒数升序取最多 5 帧；失败只记录原因，不补拉详情。

## 批次门禁与恢复

- 业务条件变化必须新建带日期和 TopN 的输出目录；指定品牌必须成对传入 `--brand-scope-type SPECIFIED_BRANDS` 与单个逗号分隔的 `--brands`。
- `run-summary.json` 保存运行 ID、参数指纹、不可变契约和阶段计数；`batch-manifest.json` 保存候选、提交、选中、拒绝、`unresolvedMaterials` 和取消项。续跑契约包含 `shop_id`、全部列表筛选、详情日期、`targetTopN`、`candidateTopN`；不一致或缺少可验证摘要就新建目录。
- `status --output-dir` 同时核对摘要、manifest、规范化列表、详情请求和详情文件。已落盘详情不重复提交；manifest 仍为 running 但文件已落盘时不重跑或覆盖。
- 中断且无本地详情的项目进入 `unresolvedMaterials`，不等同于 RPA 失败；用户确认可能重复请求后才运行 `retry-unresolved`。`retry-failed` 只重试 `rejectedMaterials`。
- 规范化后校验 `list_context` 与请求一致；失败停止在 `list_context_mismatch`。报告前确认 `status == success`、`selectedCount == targetTopN`、`rejectedCount == 0`，否则按部分完成交付。
- 若存在 `selectionGroupId`，每个“品牌 × 触点”为隔离组，失败只在同组候选补位，禁止跨组借用。不得从标题、趋势或其他字段推造脚本、公式或时间戳。

## 分析与报告

先运行 `prepare-analysis` 生成事实包和固定提示词，再由当前对话模型生成 `yuntu-ai-analysis.json`；固定规则只做统计、归类、聚合和图表数据，不生成业务结论。完成后登记来源回执：

```bash
python <skill-root>/scripts/rpa_connector.py prepare-analysis \
  --input-dir "RPA数据汇总/yuntu-rankings-analysis" \
  --output-dir "RPA数据汇总/yuntu-rankings-analysis/diagnostic-analysis"
python <skill-root>/scripts/rpa_connector.py attest-analysis \
  --analysis-json ".../diagnostic-analysis/yuntu-ai-analysis.json" \
  --fact-pack-json ".../diagnostic-analysis/yuntu-analysis-data.json" \
  --prompt ".../diagnostic-analysis/yuntu-analysis-prompt.md" \
  --source model_generated --generator "<模型或人工执行者>"
```

`--source` 只能为 `model_generated` 或 `manual_model_generated`，禁止程序化兜底。事实包 schema v4 至少包含 `industryTop1000Facts`、`brandTopNFacts`、`rankingFacts`、`audienceFacts`、`marketingFacts`、`secondLevelFacts`、`highlightFrameFacts`、`visualAssets`、`dataLimitations`；模型分析必须包含 `topMaterialCombination`、`rankingOverview`、`audienceInsights`、`materialComparison`、`materialDiagnoses`、`competitorPatterns`、`opportunityMap`、`experimentMatrix`。

前五章包括榜单机会总览、素材表现对比、单素材秒级诊断、竞品创意模式、机会地图与下一轮实验矩阵；每项含 `summary`、`evidence` 和素材 ID。`topMaterialCombination` 的品牌项保留 `brandComparisonConclusion`、`dataSummary`、`peopleSummary`、`marketingSummary`，并以同一合并 TOP1000 为证据。实验矩阵每项含 `priority`、`hypothesis`、`creative_variable`、`target_audience`、`success_metric`、`control`、`review_action`、`evidence`，至少四条，覆盖放量、改写、验证、风险控制。CPM 未提供时显示不可用；卖点与指标只描述共现，不作因果结论；任一标签比较侧样本少于 3 条时写“数据不足以判断”。人群标签可重叠，曝光加权覆盖率不可相加为 100%。结构化 evidence 不进入用户可读报告正文。

报告固定五章：`01｜TOP 素材组合结论`、`02｜人群洞察`、`03｜脚本洞察`、`04｜高光画面洞察`、`05｜单素材深度分析`。01 章比较曝光、CTR、CVR、3s 播放率和 CPM；标题匹配只用于品牌分类，未知品牌或歧义品牌不进入品牌 Top N。03 章固定显示“脚本数据：未接入”。04 章只消费成功 JPEG，每张帧仅归入 `portrait`、`product`、`scene`、`text_overlay`、`other` 之一；峰值帧不能解释为真实点击、脚本或转化因果。05 章展示高光帧与“点赞指数、流失指数、点击指数、互动指数、评论指数”的秒级拆解，只要求逐帧观察和秒级观察，不再生成或渲染单素材 AI 二次分析摘要字段。

```bash
python <skill-root>/scripts/rpa_connector.py render-report \
  --analysis-json "RPA数据汇总/yuntu-rankings-analysis/diagnostic-analysis/yuntu-ai-analysis.json" \
  --output-dir "RPA数据汇总/yuntu-rankings-analysis/final-report"
```

报告使用 `render-report` 只渲染已验证洞察，不新增判断；不下载视频、不调用外部模型。HTML 使用 `assets/report/` 离线资源并内联 CSS/JavaScript；高光预览支持点击、键盘焦点和 Escape，失败帧不输出损坏图片。交付前检查 `1440x1000` 与 `390x844` 视口，确认无遮挡、横向溢出或不可见焦点。

## 产物与失败处理

主要产物：`raw-csv/list.csv`、`raw-csv/details/<material_id>.csv`、`normalized/list-records.json`、`normalized/detail-records/<material_id>.json`、`batch-manifest.json`、`run-summary.json`、`diagnostic-analysis/yuntu-analysis-data.json`、`diagnostic-analysis/yuntu-ai-analysis.json`、`final-report/final-report-data.json`、`final-report/final-report.md`、`final-report/final-report.html`。兼容路径可保留旧版 `list-response.json`、`details/<material_id>.json`、`manifest.json`，但新流程不再写入它们；CSV 为主路径，兼容 JSON 与安全的 Python 字面量。

分析阶段只读 `normalized/` 和 `diagnostic-analysis/`，不读原始 CSV、RPA response 或临时 `fileUrl`。`files-envelope` 校验成功后才下载 CSV；解析失败的嵌套字段保留原文并标记缺失。列表请求失败或无有效素材时写清单、非零退出且不发详情；详情请求失败记录后继续，最终非零但保留成功文件。`prepare-analysis` 可复用或补处理缺失高光帧；`render-report` 不下载视频、不提取帧。不得手工修改成品 HTML 绕过渲染器。

```bash
python <skill-root>/scripts/rpa_connector.py retry-failed --shop-id "<shop_id>" --output-dir "RPA数据汇总/yuntu-rankings-analysis"
python <skill-root>/scripts/rpa_connector.py retry-unresolved --shop-id "<shop_id>" --output-dir "RPA数据汇总/yuntu-rankings-analysis"
```
