# 云图行业内容榜单分析任务

读取同目录的 `analysis-units/analysis-unit-manifest.json`、manifest 指向的 `yuntu-ai-analysis.schema.json` 及其列出的四个章节事实包，在同一次模型调用中生成 `yuntu-ai-analysis.json`。最终 JSON 必须严格符合统一输出 Schema；不要读取 `yuntu-analysis-data.json` 或 `report-data.json` 作为模型证据。

本提示词采用固定提示词模板；本次品牌榜单分析范围为行业 TOP1000 内按品牌匹配的全部素材，品牌范围为：__BRANDS__。

`classificationSource` 只能是 `title_rule` 或 `runtime_title_rule`，并用于标记品牌标题匹配的规则来源。

各品牌对象只分析该品牌在行业 TOP1000 内匹配到的全部素材聚合结果；全品牌对象分析所有品牌合并后的聚合结果。

`allBrandsConclusion` 是本次唯一允许的全品牌聚合对象；除该对象外，不生成综合结论、跨品牌结论或报告未展示的额外字段。

第一章收敛规则：`ranking-brand-input.json` 只提供当前周期、环比周期和同周期全行业三批榜单素材列表，以及确定性生成的比较事实和爆款事实；第一章不得读取或引用 RPA 详情、高光帧、秒级数据、视觉分析或其他章节事实。品牌素材列表必须直接使用行业 TOP1000 中按品牌标题匹配得到的全部素材，不存在品牌数量参数；标题统一使用“各品牌榜单分析”。

第一章周期比较与爆款规则：`current`、`previousPeriod` 和 `industryBenchmark` 分别代表当前查询周期、上一等长周期和当前周期全行业大盘；只能使用其中的 `comparisonFacts` 解释环比方向与相对大盘差异，不得重新计算或混用三个范围。上一周期已经按实际解析日期向前平移等长周期，引用 `actualDateRange` 时必须原样保留。`hotMaterialFacts` 只提供爆款事实与素材清单，不能把清单逐条重复写进 AI 正文。每个品牌对象及 `allBrandsConclusion` 都必须分别输出 `dataSummary` 与 `hotMaterialInsight` 两个自然段：`dataSummary` 必须先说明默认筛选条件的当前表现和四项指标，再用“环比看”明确说明环比周期变化，随后用“与全行业大盘对比看”明确说明同周期全行业差异，最后形成业务判断、可能机制、策略和验证建议；不得只用‘较行业大盘’或‘高于大盘’等模糊短语替代完整的全行业对比句式。`hotMaterialInsight` 解释当前范围爆款的整体特征、内容机会和验证建议。

`hotMaterialRule` 是本批次从配置文件读取并写入事实包的确定性规则：__HOT_MATERIAL_RULE__。只能使用 `hotMaterialRule` 指定的指标、比较关系和阈值判断，不能在 Prompt 或模型输出中自行写死另一套数值；只使用 `exposure.min` 判断，低于阈值不入选，等于阈值入选。云图列表的顶层 `show_cnt` 在返回 `200-300w`、`20-30w` 等带范围或单位的展示字符串时代表曝光区间，可由事实构建层解析；嵌套指标中的精确 `object_index.show_cnt` 仍只是辅助指标，不能替代缺失区间。不得用 CTR、互动率或排名替代缺失曝光区间，也不得自行计算命中数量。命中素材必须保留事实包中的素材 ID、名称、曝光区间 `min/max/raw` 和可用辅助指标；曝光区间不可解析时输出事实包提供的不可用状态，不伪造数值。爆款事实只作为整体分析的一个证据维度，不单独生成 AI 小节。

四个事实包分别与四个顶层输出字段一一对应：`ranking-brand-input.json` 只支撑 `topMaterialCombination`，`audience-marketing-input.json` 只支撑 `chapter02Insights`，`highlight-input.json` 只支撑 `highlightDashboard`，`material-deep-dive-input.json` 只支撑 `materialDeepDives`。章节之间不得借用其他事实包的业务证据。规则只计算事实，模型负责写业务判断。人群卖点包内的 `chapter02AiFacts` 是 02 章 AI 二次分析范围，品牌范围与用户输入一致。视觉高光包内的 `visualAssets` 是本地图片清单，`image_path` 相对于本提示词所在目录；必须实际查看每张成功 JPEG（`available=true`），原视频 URL 过期时仍使用已落盘的本地帧，不得以 URL 不可用为由跳过画面分析。

输出必须是 JSON 对象，包含：topMaterialCombination、chapter02Insights。若事实包中存在成功高光帧，还必须包含 highlightDashboard。若每条素材包含 `secondLevelBreakdown`，还必须包含 materialDeepDives。除 `allBrandsConclusion` 外，不要生成报告未展示的额外分析模块或跨品牌结论字段。

`topMaterialCombination` 必须严格符合 `ranking-brand-input.json` 的 `outputSchema`，包含各品牌的 `brandConclusions`，并新增一个 `allBrandsConclusion` 全品牌对象。每个对象只输出 `brand`、`classificationSource`、`dataSummary`、`hotMaterialInsight`、`evidence`、`material_ids`；`hotMaterialInsight` 必须包含 `title`、`summary` 和带 `scope`/`material_ids` 的 `evidence`。全品牌对象的 `brand` 固定为“全品牌”，只能引用三批榜单列表及其确定性比较/爆款事实；各品牌对象只能解释同一三批列表按标题匹配后的对应范围，不得生成 `marketingSummary` 或其他跨范围结论。第一章只分析对应范围内的全部素材聚合结果，不分析或举例任何单条素材；两个 AI 段落均不得引用单条素材的素材 ID、标题、排名或指标，也不得使用“某条素材”“其中一条”“头部素材”等方式替代素材 ID 进行个案分析。素材 ID 只保留在 `evidence`、`material_ids` 和爆款事实引用中，不进入用户可见的榜单摘要。`dataSummary` 只覆盖当前表现、环比周期和同周期全行业对比，必须覆盖曝光、CTR、CVR、3 秒播放率，并形成“事实锚点 -> 业务判断 -> 可能机制 -> 策略 -> 验证”的自然段；`hotMaterialInsight` 只写当前范围爆款素材的整体特征、内容机会和验证建议，不逐条复述爆款清单。四项指标不得省略；分别输出两个自然段，不把两个字段合并或重复成一个段落。每个 `dataSummary` 控制在 6 至 10 句、约 420 至 700 个中文字符，每个 `hotMaterialInsight.summary` 控制在 3 至 6 句、约 180 至 360 个中文字符；分析必须是业务判断，不得只是重复数字清单；不得把相关性写成因果。第一章不输出人群维度分析。第一章不输出人群图表、看板或交互数据。品牌名称必须与用户输入的完整参数一致；品牌素材来自同一合并 TOP1000 的运行时品牌匹配。

02 章必须读取 `chapter02AiFacts`，按其 `scopeOrder` 原样输出 `chapter02Insights`。`chapter02Insights` 必须是对象，只包含 `scopeOrder` 与 `scopes`；`scopes` 必须是以 scope 名称为键的对象映射，不能输出数组。本次 scope 顺序为：__SCOPE_LABELS__。scope 第一项固定为 `all`（全量 TOP1000），其后逐个输出每个品牌；每个 scope 必须同时包含人群和营销卖点两组内容，并只引用该 scope 的 `audienceDashboard` 与 `marketingDashboard`。保留双事实源边界：`chapter02Facts` 仅用于图表、标签统计、范围 Tab 和前端 TOPN 交互；`chapter02AiFacts` 仅用于 AI 二次分析。事实包不再提供顶层 `audienceRankRecords`，不得假设存在该字段，也不得在分析输出中生成任何 `audienceInsights`、`marketingInsights`、`audienceAnalysis` 或 `marketingAnalysis` 字段。品牌 scope 的 AI 二次分析使用行业 TOP1000 内按品牌匹配的全部素材；报告下方汇总图表另从 `chapter02Facts` 读取同一全量匹配素材。营销卖点分析必须围绕类别、Top 标签和命中素材展开，不把 1399 个标签逐项罗列。

`chapter02Insights.scopes` 的每个 scope 值只使用 `audienceSummary` 与 `marketingSummary` 两个字段，不在 scope 值内重复输出 `scope` 或 `label`。两个字段都必须含可直接展示的总结性标题 `title`、一段完整连贯的分析内容 `summary`、`evidence`、`material_ids`。每个 `summary` 控制在 4 至 6 句、约 240 至 420 个中文字符，必须同时包含事实锚点、业务判断、形成原因或内容机制解释、内容策略和下一步验证；不能只是对数据的陈述。人群分析必须在同一段中同时体现八大人群、性别和年龄三个维度，并连接到内容方向与验证建议；不得把三个维度拆成编号、列表或不同小节。营销卖点分析继续围绕类别、Top 标签和命中素材展开，并在同一段中给出内容取舍与验证方向。标题应为可直接展示的总结性判断，不得写“分析如下”“洞察 1”等模板化标题。兼容读取旧式 `audienceAnalysis`/`marketingAnalysis` 以及历史 insights 数组，但新输出不得使用旧式字段或 `audienceInsights`/`marketingInsights`。

第 02 章的用户可见分析必须是自然连贯的中文段落，并遵守中文标点规则：每条 `title` 是短语，不要以句号或分号结尾；每条 `summary` 必须是完整句子，以句号、问号或感叹号收束，不要以分号收束，不要以“；”开头。每个维度只输出一段，不使用“1.”、“2.”等编号、列表或分点；不要把编号写进 title。标题与 summary 拼接后应形成“标题：正文”的自然表达。避免同义重复，summary 不要重复 title 的原句。

`chapter02Insights.scopes[*].audienceSummary` 与 `chapter02Insights.scopes[*].marketingSummary` 的每项必须含 title、summary、evidence、material_ids；summary 应以具体标签、素材或内容方向形成可执行洞察，不得复述人群重叠等数据口径。人群重叠口径只保留在事实和 evidence，不进入用户可见正文。

所有结论必须引用指标、标签、素材数量或秒级趋势作为证据；除第一章可见摘要禁止素材 ID 和单素材分析外，其他章节可按各自契约引用素材 ID。事实不足时写“数据不足以判断”。解释只能描述可能关系，不得声称因果；不得生成未经业务与合规确认的滋补、孕期或健康功效宣称。不得写执行过程、重跑、补位调度、代码状态、排障细节、事实包返回、口径说明、仅限观察等处理过程话术；摘要必须基于对应分析范围内的实际指标、标签、趋势或画面写成业务判断。

所有 AI 二次分析字段采用“少量关键事实锚点 + 多句分析判断”的写法：只选最能支撑结论的指标、标签或素材数量作为依据，随后说明事实意味着什么、为什么形成这种表现、为什么值得保留或改写、如何转化为内容策略以及下一步如何验证；不得把指标或标签清单当作结论主体。用户可见的第一、二章每段分析至少 4 句，必须同时完成“事实锚点 -> 业务判断 -> 形成原因/内容机制 -> 内容策略 -> 下一步验证”的链路。数据维度应优先比较行业基线与当前分析范围的曝光、CTR、CVR 和 3 秒播放率，指出可测试的优势或短板；人群维度应把标签覆盖与内容主题连成目标人群假设；营销卖点维度应说明标签组合的内容取舍并给出拆分测试方向。解释只能描述可能关系，不得声称因果，同一模块不得重复同义文本。

`highlightDashboard` 只使用事实包中 `available=true` 的 highlightFrames，并输出 `brands` 数组，不得输出顶层 `groups` 或 `categories`。第一项 brand 固定为 `全品牌`，其后按事实包品牌顺序输出每个品牌；每个 brand 对象只含 `brand` 与 `groups`。全品牌 groups 必须覆盖全部成功帧且每帧仅出现一次；品牌 groups 只能引用标题中匹配该品牌的成功帧，不能把全品牌结论复制到各品牌。实际查看每张 JPEG 后，将每张成功帧且仅一次归入 `portrait`（人物是画面主要视觉主体，产品只是陪体或次要信息）、`product`（包装、瓶身、内容物、开箱、食用或操作动作是主要视觉主体，即使有人手或人物出现也优先归入产品）或 `other`（画面没有清晰的人物主体或产品主体，或主体无法可靠判断）中的一个主视觉分类，分类顺序固定为 portrait、product、other；不要依据标题、话题标签或素材品牌猜测视觉类型，不要输出 scene 或 text_overlay 分类。分类时以画面占比、视觉焦点和可辨识主体为准；人物与产品同框时选择占据视觉焦点更强的一类，无法区分时选择 other。每个非空 group 包含 `category`、`frame_refs`、`common_patterns` 和 `derivative_directions`。`common_patterns` 与 `derivative_directions` 使用完全一致的对象结构，每项都必须包含 `title`、`body`、`frame_refs`，两组数组长度必须一致并按索引一一对应，且 `frame_refs` 只能引用本 group 的 frame_refs；共性洞察固定按“画面主体与构图 → 信息层与动作机制 → 可迁移机会”组织，裂变方向与其逐项对应并在 body 中依次写“改写动作 → 变体方式 → 验证指标”，避免把数字清单当结论。报告必须分别展示“共性洞察”和“裂变方向”标题。没有成功帧时不得编造视觉洞察。报告不展示高光帧选择规则说明。高光帧卡片信息顺序固定为：第一行封面画面或点击 TopN 波峰画面，第二行秒数与点击指数，第三行可点击的视频标题；不再输出“查看素材”按钮。新事实包不提供 Presentation 顶层 `categories`；全品牌高光帧通过 `brands[0].categories` 承载，品牌与分类筛选统一从品牌 Tab 进入。只能描述该帧处于点击指数峰值秒点；不得说该画面导致点击、转化或指标提升，也不能声称其对应某句脚本话术或真实点击次数。

`materialDeepDives` 仅用于支撑 05｜单素材深度分析中的高光帧观察与秒级拆解。第五章专用 `material-deep-dive-input.json` 已收敛为 `material_id`、`highlightFrames`（`frame_ref`、`second`、`frame_type`、`available`、`image_path`、可选 `failure_reason`）和 `secondLevelBreakdown.metrics`（趋势点、高点、流失点及可用性）；不要要求或重新生成榜单指标、标签、排名、标题、路径来源、封面/峰值说明或其他报告展示字段。每项输出只包含 material_id、frame_observations、second_level_observations；不得输出或生成额外的单素材 AI 二次分析摘要字段。`frame_observations` 必须将该素材每一张 `available=true` 的 highlightFrames 恰好引用一次，每项只含 frame_ref 和至少 40 个中文字符的可观察 observation；不得引用其他素材或失败帧。逐帧观察按主体、人物、产品、动作、场景、构图和可见字幕组织，只写该 JPEG 中可见的具体信息；不同帧不得复用泛化句式。观察不得生成脚本、内容公式、真实互动量、转化或因果结论。`second_level_observations` 只使用 `点赞指数`、`流失指数`、`点击指数`、`互动指数`、`评论指数`，每项含 trend_name、至少 60 个中文字符的 summary、evidence_seconds；evidence_seconds 只能填写该素材对应趋势 `points` 中实际存在的秒数。该部分在报告中叫“秒级拆解”，不叫“互动时序分析”。
