---
name: 云图行业内容榜单分析
description: 适用于通过固定预策 RPA 连接器获取竞品内容榜单与秒级详情，并生成小仙炖内容策略报告的场景。
argument_hint: 输入行业、分析时间范围（优先填云图界面显示的真实起止日期）、榜单筛选项、品牌榜单Top素材数和秒级拆解素材数，生成小仙炖行业内容榜单分析报告。
metadata:
  pre_input: 帮我生成云图行业内容榜单分析报告，行业是 ____，分析时间范围是 ____（云图界面真实起止日期，如 2026-07-26 至 2026-08-01；未填写则列表和素材详情均使用云图默认近七天），榜单筛选项是 ____，品牌榜单Top素材数是 ____（默认30），秒级拆解素材数是 ____（默认10）。
---

# 云图行业内容榜单分析

## 用户输入与时间口径

调用本技能时，提示词应提供以下业务信息：

- `行业`：必填，例如“食品饮料”。
- `分析时间范围`：榜单和素材详情共用。优先填写云图界面日期控件实际展示的闭区间，例如截图中的“近七天”应写为 `2026-07-26 至 2026-08-01`，不要只写“近七天”。未填写时，二者均使用云图默认“近七天”。
- `榜单筛选项`：按需填写品牌范围、指定品牌、年龄、性别、八大人群和榜单限制；未填写的筛选项保持云图默认，不擅自补充。
- `品牌榜单Top素材数`：从本次已获取的合并 TOP1000 榜单中按用户输入品牌筛选后，每个品牌纳入 01 章的榜单素材数；未填写时为 `30`。
- `秒级拆解素材数`：最终希望完成秒级拆解并纳入 04/05 章的素材数；未填写时为 `10`。它不参与 01 章的行业或品牌榜单分析。

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
`material_id`，按固定波次调用 `rpa.conn.juliang.yt.industry.content.rankings.detail`。
列表连接器完成后必须先完成结构化落盘：`normalized/list-records.json` 保存素材本身的标题、身份、发布时间、指标、标签和列表筛选上下文；`normalized/detail-request-params.json` 保存下一步详情连接器所需的 `material_id` 与详情日期参数。详情连接器只消费后者，分析事实包消费前者和成功详情记录。
`fetch` 是长任务：详情 RPA 单次调用可能超过 300 秒，必须使用平台提供的异步/长任务会话执行，并通过 `status` 定期观察落盘进度；不得在 300 秒同步窗口中等待完整批次。详情阶段固定每波最多并行 2 个素材；某条详情持久化后立即在独立后处理线程中下载视频并提取标准高光帧，但下一波详情只能在本波全部详情和高光帧任务均进入终态后启动。高光帧失败只记录具体失败原因，不会重发详情 RPA 或触发额外补位。详情阶段中断后，只能以完全相同的运行契约续跑。契约包含 `shop_id`、全部列表筛选、详情日期、`targetTopN` 与 `candidateTopN`；参数不一致时，脚本会在调用 RPA 前拒绝该目录，必须新建输出目录。旧目录缺少可验证的 `run-summary.json` 时同样拒绝，不得把历史 CSV 当作本次列表。

## 运行环境要求

调用网关前，设置以下环境变量：

- `ENV_BACKEND_HOST`：平台运行时注入的受信任网关基地址，可为 HTTP/IP 或含 `/api` 的路径前缀；不得使用 userinfo、查询参数或片段。
- `YUCE_AUTHORIZATION`：网关授权值。
- `YUCE_SESSION_ID`：网关代理会话 ID。

凭证应保留在环境变量中。不要将凭证写入命令、输入 JSON 或输出路径。保留平台运行时注入的 `ENV_BACKEND_HOST`，不要用 `.env` 中的值覆盖它。未知 `shop_id` 时，运行 `list-accounts`。

## 参数

`fetch` 接受列表连接器可选的 `--industry`、时间范围、年龄、性别、人群、品牌范围、品牌和榜单限制筛选项。`ages`、`genders`、`crowd_groups` 只做格式校验，不做本地枚举阻断，以兼容平台新增或未固化值。列表自定义日期与列表技能使用相同的 Asia/Shanghai 限制。

详情日期使用 `--detail-date-range-type`（`LAST_7_DAYS`、`LAST_30_DAYS` 或 `CUSTOM`），但必须与榜单时间范围一致；详情自定义日期必须同时提供 `--detail-custom-start-date` 和 `--detail-custom-end-date`，且结束日期不得早于开始日期。

`--top-n` 必须为正整数，默认值为 `10`，兼容旧用法。新增批次口径中，`--target-top-n` 表示最终希望分析成功的素材数量；`--candidate-top-n` 表示从榜单中保留的候选池上限，未显式指定时为目标数量加 2，用于避免无故拉取过多详情。`material_id` 始终从列表响应中选择，不能作为详情覆盖参数提供。

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

只读检查已有批次的真实阶段和落盘证据：

```bash
python <skill-root>/scripts/rpa_connector.py status \
  --output-dir "RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-top5"
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

详情 RPA 成功持久化后会立即为该素材生成标准高光帧；`prepare-analysis` 优先复用 `highlights-manifest.json` 中完整的本地帧集，只为中断后缺失或不完整的素材补处理，无需也不支持额外的趋势选择参数。每条素材固定截取 `0s` 封面帧，并从“点击指数”完整序列中按局部峰值的点击值降序、秒数升序选取最多 5 帧。连续相等的平台只取最早秒数；峰值不足 5 个时保留实际数量，不用其他指标或高点区间补足。帧写入 `highlights/<material_id>/`，清单为 `highlights-manifest.json`。

视频下载、FFmpeg 或单帧截图失败只记录具体失败原因，不阻断事实包或最终报告；HTML 只展示成功 JPEG，不输出损坏图片。这里的“点击指数”不是实际点击次数，局部峰值也不能用于推断转化因果。

当前对话模型读取 `diagnostic-analysis/yuntu-analysis-data.json` 和 `diagnostic-analysis/yuntu-analysis-prompt.md` 后，生成 `diagnostic-analysis/yuntu-ai-analysis.json`。模型或人工模型步骤完成后，必须登记来源回执；未经回执核验不得渲染最终报告：

```bash
python <skill-root>/scripts/rpa_connector.py attest-analysis \
  --analysis-json "RPA数据汇总/yuntu-rankings-analysis/diagnostic-analysis/yuntu-ai-analysis.json" \
  --fact-pack-json "RPA数据汇总/yuntu-rankings-analysis/diagnostic-analysis/yuntu-analysis-data.json" \
  --prompt "RPA数据汇总/yuntu-rankings-analysis/diagnostic-analysis/yuntu-analysis-prompt.md" \
  --source model_generated \
  --generator "<模型或人工执行者>"
```

`--source` 只能是 `model_generated` 或 `manual_model_generated`。最终报告禁止使用程序化兜底分析；即使传入 `programmatic_fallback` 或 `--allow-programmatic-fallback`，CLI 也必须拒绝。固定规则只允许用于事实包统计、品牌标题归类、指标聚合和图表数据，不得生成最终业务结论文字。

渲染最终报告：

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

仅在用户确认可能重复请求后，重试因进程中断而未完成本地落盘的详情：

```bash
python <skill-root>/scripts/rpa_connector.py retry-unresolved \
  --shop-id "<shop_id>" \
  --output-dir "RPA数据汇总/yuntu-rankings-analysis"
```

## RPA 批次门禁与状态

真实 RPA 运行前，先执行 `list-accounts` 并确认目标账号与 `shop_id` 对应。每次业务条件变化必须使用新的输出目录，目录名至少带日期和 TopN，例如 `yuntu-rankings-analysis-20260730-20260805-top5`。指定品牌时，必须成对传入 `--brand-scope-type SPECIFIED_BRANDS` 与单个逗号分隔的 `--brands '品牌1,品牌2,品牌3'`；不得把多个品牌拆成多个 shell 参数。

`run-summary.json` 保存运行 ID、参数指纹、不可变契约、列表/详情阶段和互不混用的计数。`batch-manifest.json` 保存候选、提交、入选、拒绝、`unresolvedMaterials` 和取消素材。命令运行中，`status --output-dir` 必须同时反读 `run-summary.json`、`batch-manifest.json`、`normalized/list-records.json`、`normalized/detail-request-params.json` 与 `normalized/detail-records/`；manifest 仍为 `running` 但详情文件已落盘时，应报告“详情已持久化、状态待回写”，不得重跑或覆盖目录。

常规续跑会从 `normalized/detail-records/` 恢复已持久化详情，且不重复提交这些素材。已提交但因进程终止而没有本地详情文件的项目会写入 `unresolvedMaterials`；这不代表 RPA 失败，也不能自动补拉。先用 `status` 核对证据，只有用户确认接受可能重复请求后才能运行 `retry-unresolved`。

列表规范化后，脚本会校验首条 `list_context` 的行业、自定义日期、品牌范围、指定品牌和榜单限制是否与本次请求相符。校验失败立即停止，状态为 `list_context_mismatch`，不得调用详情、生成事实包或报告。报告前必须确认 `status == success`、`selectedCount == targetTopN`、`rejectedCount == 0`；否则按部分完成交付并说明缺口。

当 RPA 返回 `selectionGroupId`、品牌和触点字段时，批次会把每个 `品牌 × 触点` 作为隔离组：`candidateTopN` 和 `targetTopN` 按组计算，详情失败只能从同组候选补位；同组耗尽则该组保持部分完成，禁止跨组借用素材。详情回传必须与列表中的组一致。详情规范化产物会保留 `script_text`、`content_formula`、带 `start_ms/end_ms/text` 的 `script_segments`，并用 `data_availability` 标记字段缺失或无效；不得从标题、趋势或其他字段推造脚本、公式或时间戳。

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
- `batch-manifest.json`：候选、提交、入选、失败、未确认、取消素材及路径和耗时。
- `run-summary.json`：不可变运行契约、参数指纹、状态阶段、计数和已核实产物。

分析阶段只读取 `normalized/` 和 `diagnostic-analysis/`，不直接读取原始 CSV、RPA response 或临时 `fileUrl`。CSV 单元格同时兼容标准 JSON 和安全的 Python 字面量；RPA 导出的字段边缘控制字符与控制字符空行会被清理，不会被误识别为素材。无法安全解析的嵌套字段保留原文本，并在规范化产物中标记缺失原因。

## 商业分析与报告

`prepare-analysis` 会以完整榜单作为行业 TOP1000 候选池，并从同一榜单池按本次用户输入品牌的运行时标题匹配结果生成各品牌 Top N；以成功详情素材作为秒级诊断范围，计算指标均值、中位数、分位与分层，汇总人群和内容标签覆盖，并归纳高点与流失区间。该阶段只生成可审计事实和图表数据，不生成最终业务结论文字。候选池少于四条时不输出高表现分层或标签关联；缺少指标、标签或趋势时在事实包中标记数据不足，不得补造结论。

`prepare-analysis` 生成 schema v4 事实包，在保留既有统计字段外，明确提供 `industryTop1000Facts`、`brandTopNFacts`、`rankingFacts`、`audienceFacts`、`marketingFacts`、`secondLevelFacts`、`highlightFrameFacts`、`visualAssets` 和 `dataLimitations`。当前对话模型必须读取这些结构化事实；对每一张 `visualAssets` 中 `available=true` 的本地 JPEG 实际查看后再写视觉结论。视频 URL 过期时复用已落盘帧，`frame_source: reused_local_extracted_frame` 只说明资产来源，不改变帧的事实身份。

模型读取事实包后，必须写入包含以下八个基础键的 `yuntu-ai-analysis.json`：

1. `topMaterialCombination`：TOP 素材组合结论
2. `rankingOverview`：榜单机会总览
3. `audienceInsights`：人群结构洞察
4. `materialComparison`：素材表现对比
5. `materialDiagnoses`：单素材秒级诊断
6. `competitorPatterns`：竞品创意模式
7. `xiaoxianDunOpportunityMap`：小仙炖机会地图
8. `experimentMatrix`：下一轮实验矩阵

`topMaterialCombination` 包含 `overallConclusions`、`brandConclusions` 与 `brandComparisonConclusion`。`overallConclusions` 必须且只能包含 `data`、`people`、`marketing` 三个维度；`brandConclusions` 的每个品牌必须包含 `dataSummary`、`peopleSummary`、`marketingSummary`；`brandComparisonConclusion` 必须基于同一合并 TOP1000 中各品牌榜单 Top N 的指标证据总结横向差异。01 章的数据维度只分析曝光、CTR、CVR、3s 播放率和 CPM；CPM 未由 RPA 提供时显示不可用，不得推算。品牌名在 RPA 请求中保留用户输入的完整形式；列表落盘后，仅在当前运行中将包含 `/` 的品牌参数拆为匹配词，Tab 和事实中的品牌名称始终保留完整用户参数。标题匹配是业务分类，不是 RPA 原生品牌字段；未知品牌和歧义标题不进入品牌 Top N，但保留在行业 TOP1000 事实中。

人群标签同时给出素材数量占比和曝光加权覆盖率。标签可以重叠，因此曝光加权覆盖率不可相加为 100%，也不得写成真实人群比例。CPM 未由 RPA 提供时必须显示不可用，禁止从曝光或其他指标推算。卖点与指标只能描述共现，不得声称因果；某标签的有/无标签比较任一侧样本少于 3 条时写“数据不足以判断”。

`audienceInsights` 的每项必须带有 `summary`、`evidence` 及 `material_id` 或 `material_ids`。人群标签重叠、不可相加等数据口径只保留在结构化事实包和 evidence，不进入用户可见正文；正文应使用具体标签、素材和内容方向形成业务洞察。前五章中每项必须带有 `summary`、`evidence` 及 `material_id` 或 `material_ids`。实验矩阵每项必须包含 `priority`、`hypothesis`、`creative_variable`、`target_audience`、`success_metric`、`control`、`review_action` 和 `evidence`；evidence 至少引用一个真实素材 ID、指标、`frame_ref` 或已返回的秒级点。涉及滋补、孕期、功效或健康人群的方向只能作为需业务和合规确认的测试假设。

`render-report` 会拒绝缺少章节、证据、素材引用或实验字段的 JSON；CLI 会先拒绝缺少、不匹配或非模型来源的分析回执。它只将已验证的模型洞察渲染为 Markdown/HTML，不新增业务判断。当前用户可见报告交付五个板块：`01｜TOP 素材组合结论`、`02｜人群洞察`、`03｜脚本洞察`、`04｜高光画面洞察` 与 `05｜单素材深度分析`。

`03｜脚本洞察` 为固定占位：当前云图 RPA 未提供可用于汇总的脚本正文与时间戳段落，报告只显示“脚本数据：未接入”，不输出话术、内容公式或帧-话术对应关系，也不得基于标题、标签或画面推断脚本。

`04｜高光画面洞察` 只消费成功落盘的高光 JPEG。模型在实际查看每张图片后，必须通过 `highlightDashboard` 将每张成功帧且仅一次归入 `portrait`、`product`、`scene`、`text_overlay`、`other` 五类主视觉之一，分类顺序固定；每个非空分类包含帧引用、可观察的共同画面特征和仅引用本类帧的裂变方向。失败帧不得被分类；没有成功帧时不编造视觉洞察。高光帧只能表述为处于点击指数峰值秒点，不能被宣称对应某句脚本、真实点击次数、转化表现或因果关系。渲染器会校验报告占位符、目录锚点、分类完整性与最终 HTML。

`05｜单素材深度分析` 为每个入选素材提供可键盘操作的页签，默认显示榜单排名最高的素材。它展示按秒数排序的成功高光帧、逐帧画面观察，以及固定顺序的 `点赞指数`、`流失指数`、`点击指数`、`互动指数`、`评论指数` 五项“秒级拆解”小图。`0s` 同时命中点击峰值时仅展示一张封面帧卡片，但保留封面与点击峰值的双重入选原因和峰值信息。新事实包中的 `materialDeepDives` 只要求逐帧观察和秒级观察；每张成功帧仅观察一次，指标观察的秒数必须存在于对应趋势。该部分不再生成或渲染单素材 AI 二次分析摘要字段，不输出脚本、话术、真实互动次数、转化或因果结论；没有新事实包契约的历史报告可重渲染为无数据状态。

AI 二次分析使用固定提示词模板，并在每次运行时注入本次品牌范围和品牌榜单 Top N；它不是随机生成的提示词。分析采用“少量关键事实锚点 + 多句分析判断”及“事实锚点 -> 业务判断 -> 下一步验证”结构：数据维度比较行业基线与品牌 Top N 的曝光、CTR、CVR、3 秒播放率；人群维度形成内容定向假设；营销卖点维度说明标签组合取舍并给出拆分测试方向；品牌对比指出相对优势、短板或指标取舍。每条正文至少 80 个中文字符，不得只罗列指标或标签。05 章节只展示高光帧观察和秒级拆解，不再展示单素材 AI 二次分析摘要。短句、重复文本、“事实包返回”等处理过程话术和已知占位语会被渲染门禁拒绝。实验矩阵至少四条，分别覆盖放量、改写、验证和风险控制。

HTML 报告使用深棕、暖金、米白的离线视觉系统。报告正文只展示结论与必要关键数字，结构化 `evidence` 保留在 `final-report-data.json`，不进入用户可读报告正文，也不展示为可展开区域。高光帧预览必须支持点击、键盘焦点和 Escape 关闭；失败帧不输出损坏图片，素材诊断继续保留。

报告统一视觉与交互资产位于本技能 `assets/report/`，`render-report` 会将 CSS 和 JavaScript 自动内联到 `final-report.html`，成品不依赖外部样式或脚本文件。不得手工修改成品 HTML 绕过渲染器。

交付前使用桌面 `1440x1000` 与移动端 `390x844` 视口检查封面、目录、章节卡片、人群图表、高光帧网格和预览层，确认无文本遮挡、正文横向溢出或不可见的键盘焦点。HTML 不得依赖远程图片、脚本或数据请求；归档为单文件时，高光帧须压缩后以 data URI 内嵌。

## 输出与失败处理

输出目录会以原子方式写入以下文件：

- `list-response.json`：原始成功列表响应。
- `details/<material_id>.json`：每个原始成功详情响应。
- `manifest.json`：旧版串行详情流程的清单输出。
- `batch-manifest.json`：CSV 主路径批次清单，区分 `selectedMaterials`、`rejectedMaterials` 和 `cancelledMaterials`。
- `diagnostic-analysis/yuntu-analysis-data.json`：分析事实包。
- `diagnostic-analysis/yuntu-analysis-prompt.md`：模型分析提示。
- `diagnostic-analysis/yuntu-ai-analysis.json`：模型生成的结构化分析结论。
- `final-report/final-report-data.json`、`final-report/final-report.md` 和 `final-report/final-report.html`：包含 01 至 05 板块的最终报告产物；`final-report-data.json` 保留高光帧、分类引用和素材深度洞察。

先运行 `list-accounts` 确认注入网关可用，再运行 `fetch`。若返回 404，检查注入网关是否缺少或多出平台基路径；若返回 504 网关超时，保留 `run-summary.json` 和 `batch-manifest.json`，通过 `status` 交叉检查后再排查，不要将其解释为无素材。

若列表请求失败或没有有效素材 ID，命令会写入清单并以非零状态退出，且不会开始详情请求。详情请求失败会被记录，后续选中素材仍会继续；只要任一详情失败，命令就以非零状态退出，同时成功的详情 JSON 文件仍可使用。

`retry-failed` 只重试 `batch-manifest.json` 中的 `rejectedMaterials`，不会重跑列表请求，也不会重复请求已经成功落盘的详情。`retry-unresolved` 只重试 `unresolvedMaterials`，必须先获得用户确认，因为中断时 RPA 后台可能已经完成但响应未被本地进程写盘。

`fetch` 会在详情 RPA 波次中并行完成可用视频的标准高光帧处理；`prepare-analysis` 仅复用或补处理缺失帧；`render-report` 本身不下载视频、不提取帧、不调用外部模型，也不生成新的业务判断。
