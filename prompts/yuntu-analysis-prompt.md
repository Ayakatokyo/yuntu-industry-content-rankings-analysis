# 云图行业内容榜单分析任务

读取同目录的 `analysis-units/analysis-unit-manifest.json`、manifest 指向的 `yuntu-ai-analysis.schema.json` 及其列出的四个章节事实包，在同一次模型调用中生成 `yuntu-ai-analysis.json`。最终 JSON 必须严格符合统一输出 Schema；不要读取 `yuntu-analysis-data.json` 或 `report-data.json` 作为模型证据。

本提示词采用固定提示词模板；本次运行参数动态注入，不随机改写分析规则。本次品牌榜单分析范围为__BRAND_SCOPE_LABEL__，品牌范围为：__BRANDS__。

四个事实包分别与四个顶层输出字段一一对应：`ranking-brand-input.json` 只支撑 `topMaterialCombination`，`audience-marketing-input.json` 只支撑 `chapter02Insights`，`highlight-input.json` 只支撑 `highlightDashboard`，`material-deep-dive-input.json` 只支撑 `materialDeepDives`。章节之间不得借用其他事实包的业务证据。规则只计算事实，模型负责写业务判断。人群卖点包内的 `chapter02AiFacts` 是 02 章 AI 二次分析范围，品牌范围与用户输入的 Top N 一致。视觉高光包内的 `visualAssets` 是本地图片清单，`image_path` 相对于本提示词所在目录；必须实际查看每张成功 JPEG（`available=true`），原视频 URL 过期时仍使用已落盘的本地帧，不得以 URL 不可用为由跳过画面分析。

输出必须是 JSON 对象，包含：topMaterialCombination、chapter02Insights。若事实包中存在成功高光帧，还必须包含 highlightDashboard。若每条素材包含 `secondLevelBreakdown`，还必须包含 materialDeepDives。不要生成报告未展示的额外分析模块。`topMaterialCombination.executiveSummary` 必须是包含 `title`、`summary`、`evidence`、`material_ids` 的对象，不得输出为字符串。

`topMaterialCombination` 必须严格符合 `ranking-brand-input.json` 的 `outputSchema`，只包含 `executiveSummary`、`brandConclusions` 与 `brandComparisonConclusion`。01 章只负责榜单数据维度：`executiveSummary` 和 `brandComparisonConclusion` 只能引用 `industryTop1000Facts` 与 `brandTopNFacts`。每个品牌结论只输出 `brand`、`classificationSource`、`dataSummary`、`evidence`、`material_ids`，其中 `classificationSource` 只能是 `title_rule` 或 `runtime_title_rule`；只能引用 `brandTopNFacts`，不得生成 `peopleSummary` 或 `marketingSummary`。`brandComparisonConclusion.evidence` 必须是对象数组，每个对象必须同时包含 `brand`、`metric`、`value`，并且覆盖 `brandConclusions` 中的每一个品牌；不能用字符串数组替代，也不能省略 `value`。`executiveSummary`、每个品牌 `dataSummary` 和品牌差异总结均需在事实允许时写明分析样本、累计曝光、CTR/CVR/3 秒播放率的中位数及其行业基线比较，再给出一个可验证的测试方向；避免空泛短句。品牌名称必须与用户输入的完整参数一致；品牌 Top N 来自同一合并 TOP1000 的运行时品牌匹配，不能引用秒级详情。CPM 未由 RPA 提供时写“数据不足以判断”，不得从其他指标推算。

02 章必须读取 `chapter02AiFacts`，按其 `scopeOrder` 原样输出 `chapter02Insights`。`chapter02Insights` 必须是对象，只包含 `scopeOrder` 与 `scopes`；`scopes` 必须是以 scope 名称为键的对象映射，不能输出数组。本次 scope 顺序为：__SCOPE_LABELS__。scope 第一项固定为 `all`（全量 TOP1000），其后逐个输出每个品牌；每个 scope 必须同时包含人群和营销卖点两组内容，并只引用该 scope 的 `audienceDashboard` 与 `marketingDashboard`。保留双事实源边界：`chapter02Facts` 仅用于图表、标签统计、范围 Tab 与 TopN 控件；`chapter02AiFacts` 仅用于 AI 二次分析。品牌 scope 的 AI 二次分析只使用用户输入的 Top N 素材；报告下方汇总图表另从 `chapter02Facts` 读取全量匹配素材。营销卖点分析必须围绕类别、Top 标签和命中素材展开，不把 1399 个标签逐项罗列。

`chapter02Insights.scopes` 的每个 scope 值使用 `audienceSummary`、`audienceInsights`、`marketingSummary`、`marketingInsights` 字段，不在 scope 值内重复输出 `scope` 或 `label`。`audienceSummary` 与 `marketingSummary` 都必须含可直接展示的总结性标题 `title`、详细洞察内容 `summary`、`evidence`、`material_ids`；两个 insights 数组都至少输出 2 条详细洞察，每条也使用 `title`、`summary`、`evidence`、`material_ids`。最终报告中人群和营销卖点分开渲染，禁止将两个数组拼成连续段落。标题应为可直接展示的总结性判断，不得写“分析如下”“洞察 1”等模板化标题。兼容读取旧式 `audienceAnalysis`/`marketingAnalysis`，但新输出不得使用旧式字段。

第 02 章的用户可见详细洞察必须是自然连贯的中文段落，并遵守中文标点规则：每条 `title` 是短语，不要以句号或分号结尾；每条 `summary` 必须是完整句子，以句号、问号或感叹号收束，不要以分号收束，不要以“；”开头。每个维度有多条详细洞察时，按业务顺序输出，渲染层会自动添加“1. ”、“2. ”等编号；不要把编号写进 title。标题与 summary 拼接后应形成“标题：正文”的自然表达；不同洞察之间由渲染层使用空格连接，不要输出用于拼接的额外分号或重复的“人群/营销卖点”标签。避免同义重复，summary 不要重复 title 的原句。

`chapter02Insights.scopes[*].audienceInsights` 与 `chapter02Insights.scopes[*].marketingInsights` 的每项必须含 summary、evidence，以及 material_id 或 material_ids；summary 应以具体标签、素材或内容方向形成可执行洞察，不得复述人群重叠等数据口径。人群重叠口径只保留在事实和 evidence，不进入用户可见正文。

所有结论必须引用素材 ID、指标、标签或秒级趋势作为证据。事实不足时写“数据不足以判断”。解释只能描述可能关系，不得声称因果；不得生成未经业务与合规确认的滋补、孕期或健康功效宣称。不得写执行过程、重跑、补位调度、代码状态、排障细节、事实包返回、口径说明、仅限观察等处理过程话术；摘要必须基于该素材的实际指标、标签、趋势或画面写成业务判断。

所有 AI 二次分析字段采用“少量关键事实锚点 + 多句分析判断”的写法：只选最能支撑结论的指标、标签或素材数量作为依据，随后说明事实意味着什么、为什么值得保留或改写、下一步如何验证；不得把指标或标签清单当作结论主体。用户可见的每条业务洞察采用“事实锚点 -> 业务判断 -> 下一步验证”结构。数据维度应优先比较行业基线与品牌__BRAND_SCOPE_LABEL__的曝光、CTR、CVR 和 3 秒播放率，指出可测试的优势或短板；人群维度应把标签覆盖与内容主题连成目标人群假设；营销卖点维度应说明标签组合的内容取舍并给出拆分测试方向；品牌对比应指出相对优势、短板或指标取舍。解释只能描述可能关系，不得声称因果，同一模块不得重复同义文本。

`highlightDashboard` 只使用事实包中 `available=true` 的 highlightFrames，并只包含 `groups` 数组，不得输出 `categories`。实际查看每张 JPEG 后，将每张成功帧且仅一次归入 `portrait`（人像画面）、`product`（产品画面）或 `other`（其他画面）中的一个主视觉分类，分类顺序固定为 portrait、product、other；不要输出 scene 或 text_overlay 分类。每个非空 group 包含 `category`、`frame_refs`、`common_patterns` 和 `derivative_directions`；每条裂变方向必须是包含 `title`、`body`、`frame_refs` 的对象，且只能引用本 group 的 frame_refs。报告必须分别展示“共性洞察”和“裂变方向”标题。没有成功帧时不得编造视觉洞察。报告不展示高光帧选择规则说明。高光帧卡片信息顺序固定为：第一行封面画面或点击 TopN 波峰画面，第二行秒数与点击指数，第三行可点击的视频标题；不再输出“查看素材”按钮。只能描述该帧处于点击指数峰值秒点；不得说该画面导致点击、转化或指标提升，也不能声称其对应某句脚本话术或真实点击次数。

`materialDeepDives` 仅用于支撑 05｜单素材深度分析中的高光帧观察与秒级拆解。每项包含 material_id、frame_observations、second_level_observations；不得输出或生成额外的单素材 AI 二次分析摘要字段。`frame_observations` 必须将该素材每一张 `available=true` 的 highlightFrames 恰好引用一次，每项只含 frame_ref 和至少 40 个中文字符的可观察 observation；不得引用其他素材或失败帧。逐帧观察按主体、人物、产品、动作、场景、构图和可见字幕组织，只写该 JPEG 中可见的具体信息；不同帧不得复用泛化句式。观察不得生成脚本、内容公式、真实互动量、转化或因果结论。`second_level_observations` 只使用 `点赞指数`、`流失指数`、`点击指数`、`互动指数`、`评论指数`，每项含 trend_name、至少 60 个中文字符的 summary、evidence_seconds；evidence_seconds 只能填写该素材对应趋势 `points` 中实际存在的秒数。该部分在报告中叫“秒级拆解”，不叫“互动时序分析”。
