# 云图行业素材诊断任务

由当前对话模型在同一次分析任务中生成 `yuntu-ai-analysis.json`。先读同目录的 `analysis-units/analysis-unit-manifest.json` 与本提示词一次，再由 begin-analysis 创建各部分任务。新任务的 `scopedFacts` 是从五包确定性投影的本部分事实，`outputSchema` 是本部分输出约束；优先只读对应 `*.task.json`，无需再全文读取五包、完整 Schema 或脚本源码。旧任务没有 scopedFacts 时才读取对应章节事实包。最终 JSON 必须严格符合统一输出 Schema；不要读取 `yuntu-analysis-data.json` 或 `report-data.json` 作为模型证据。

执行入口：先用 `begin-analysis --fact-pack-json <manifest> --workspace <独立草稿目录>` 创建草稿。阅读同名 `*.task.json` 的 scopedFacts、readingRule 和 outputSchema，直接填写对应 JSON 的 `content`；不要创建业务结论生成脚本。`ranking.json`、`audience.json`、`script.json`、`highlight.json` 的 content 是它们负责的顶层字段对象，`material-<ID>.json` 的 content 是单个素材对象。字段结构、当前素材允许的脚本引用、成功帧全集、scope 素材范围和字数硬约束由 task 文件给出；引用必须原样使用，不凭记忆拼接。

每份草稿写完即保存；每完成一组相关草稿再运行一次 `check-analysis --workspace <目录> --part <key1> --part <key2>`，共享一次事实及资产校验。通常第一、二章一组，第三章及品牌草稿一组，第五章按 3–5 个素材一组，第四章整批分类完成后单独检查。仅排查某份草稿时使用单个 --part，按 `validation.json` 的具体路径修复。阅读过的成功图片引用填写到 `highlight.json.viewedFrameRefs`，不得把预置清单当作实际看图记录。各组通过后，使用 `assemble-analysis --workspace <目录> --output <新分析JSON路径>`（内部执行完整 check-analysis 等价检查，无需先重复跑全量检查）无损合并并保留原始草稿快照，再 attest 和 render。失败只修对应草稿，禁止运行时修改校验器、程序化补结论或循环扩写凑字数。新契约没有 assembly 收据不能 attest。具体业务写作要求如下；缺失事实优先，推荐篇幅不能作为补造内容的理由。

可以按章节、素材和帧批次分步阅读，及时保存模型撰写的草稿和已查看帧引用；最终无损组装为一个 JSON。草稿须绑定本次 manifest、五包及提示词哈希，恢复前核对，不能把旧事实包生成的正文直接移植到新批次。`single_model_call` 是既有契约标识，不限制当前任务的工具读取次数。每张可用 JPEG 均需实际查看：按素材连续看一小组清晰原图，同次查看完成第四章 frameUnderstanding 与第五章 frame_observations，及时保存；所有逐帧理解完成后再生成第四章两套分类和各品牌洞察。同一帧无疑点时不重复看图，不用缩略图拼图代替原图。只共享这次直接观察，不把第四章业务结论作为第五章证据；缺失或模糊时按原规则处理。保存草稿不等于完成，最终仍需通过完整引用、帧覆盖和来源校验。

缺失数据优先于篇幅和分析结构要求：有事实的维度正常分析，真正缺失的维度简洁说明“数据不足以判断”，不为凑句数或字数编写机制、策略或行业结论。可以明确写“覆盖不足以支持行业普遍结论”；这类范围限制不代表可以在同段其他句子声称行业规律或指标因果。解析失败与源字段为空须按事实包分别表达；怀疑映射异常时反馈具体素材和字段供本地诊断，不自行读取 CSV 补证。

本提示词采用固定提示词模板；本次品牌榜单分析范围为行业 TOP1000 内按品牌匹配的全部素材，品牌范围为：__BRANDS__。

`classificationSource` 只能是 `title_rule` 或 `runtime_title_rule`，并用于标记品牌标题匹配的规则来源。

各品牌对象只分析该品牌在行业 TOP1000 内匹配到的全部素材聚合结果；全品牌对象分析所有品牌合并后的聚合结果。

`allBrandsConclusion` 是第一章唯一的全品牌聚合对象。第二至四章按各自契约保留全量范围与品牌范围分析，不新增报告未展示的综合结论。

第一章收敛规则：`ranking-brand-input.json` 只提供当前周期、环比周期和同周期全行业三批榜单素材列表，以及确定性生成的比较事实和爆款事实；第一章不得读取或引用 RPA 详情、高光帧、秒级数据、视觉分析或其他章节事实。品牌素材列表必须直接使用行业 TOP1000 中按品牌标题匹配得到的全部素材，不存在品牌数量参数；标题统一使用“各品牌榜单分析”。

第一章周期比较与爆款规则：`current`、`previousPeriod` 和 `industryBenchmark` 分别代表当前查询周期、上一等长周期和当前周期全行业大盘；只能使用其中的 `comparisonFacts` 解释环比方向与相对大盘差异，不得重新计算或混用三个范围。上一周期已经按实际解析日期向前平移等长周期，引用 `actualDateRange` 时必须原样保留。`hotMaterialFacts` 只提供爆款事实与素材清单，不能把清单逐条重复写进 AI 正文。每个品牌对象及 `allBrandsConclusion` 都必须分别输出 `dataSummary` 与 `hotMaterialInsight` 两个自然段：`dataSummary` 必须先说明默认筛选条件的当前表现和四项指标，再用“环比看”明确说明环比周期变化，随后用“与全行业大盘对比看”明确说明同周期全行业差异，最后形成业务判断、可能机制、策略和验证建议；不得只用‘较行业大盘’或‘高于大盘’等模糊短语替代完整的全行业对比句式。`hotMaterialInsight` 解释当前范围爆款的整体特征、内容机会和验证建议。

`hotMaterialRule` 是本批次从配置文件读取并写入事实包的确定性规则：__HOT_MATERIAL_RULE__。只能使用 `hotMaterialRule` 指定的指标、比较关系和阈值判断，不能在 Prompt 或模型输出中自行写死另一套数值；只使用 `exposure.min` 判断，低于阈值不入选，等于阈值入选。云图列表的顶层 `show_cnt` 在返回 `200-300w`、`20-30w` 等带范围或单位的展示字符串时代表曝光区间，可由事实构建层解析；嵌套指标中的精确 `object_index.show_cnt` 仍只是辅助指标，不能替代缺失区间。不得用 CTR、互动率或排名替代缺失曝光区间，也不得自行计算命中数量。命中素材必须保留事实包中的素材 ID、名称、曝光区间 `min/max/raw` 和可用辅助指标；曝光区间不可解析时输出事实包提供的不可用状态，不伪造数值。爆款事实只作为整体分析的一个证据维度，不单独生成 AI 小节。

五个事实包分别与五个顶层输出字段一一对应：`ranking-brand-input.json` 只支撑 `topMaterialCombination`，`audience-marketing-input.json` 只支撑 `chapter02Insights`，`script-input.json` 只支撑 `scriptInsights`、`keywordCloudReview`、`keywordCloudInsight` 和 `scriptBrandInsights`，`highlight-input.json` 只支撑 `highlightDashboard`，`material-deep-dive-input.json` 只支撑 `materialDeepDives`。章节之间不得借用其他事实包的业务证据。规则只计算事实，模型负责写业务判断。脚本事实包的范围固定为 `selected_detail_materials`（已获取详情素材），每条 `scriptInsights` 必须包含 `title`、`summary`、`evidence` 和本范围 `material_ids`，只能引用事实包列出的素材 ID。脚本正文、内容公式和创意拆解缺失时输出“数据不足以判断”；当前没有 `scriptSegments`，不得把句子映射到秒点或高光帧，不得把内容公式标签写成因果证据，不得把 `convertCnt` 当成订单数，也不得将详情样本概括成行业普遍规律。视觉高光包内的 `visualAssets` 是本地图片清单，`image_path` 相对于本提示词所在目录；必须实际查看每张成功 JPEG（`available=true`），原视频 URL 过期时仍使用已落盘的本地帧，不得以 URL 不可用为由跳过画面分析。

输出必须是 JSON 对象，包含：topMaterialCombination、chapter02Insights、scriptInsights、keywordCloudReview、keywordCloudInsight、scriptBrandInsights。若事实包中存在成功高光帧，还必须包含 highlightDashboard。若每条素材包含 `secondLevelBreakdown`，还必须包含 materialDeepDives。只生成本节明确要求的字段与范围，不新增报告未展示的分析模块。

`scriptInsights` 固定输出 2 条脚本洞察，并只覆盖已获取详情素材范围：第一条标题以“`一二级内容公式：`”开头，只分析一级/二级标签的高频结构、组合方式和不同素材间的差异；第二条标题以“`脚本文案：`”开头，只分析完整脚本文案中的利益点、表达方式、场景与品质/信任证据。每条洞察都必须包含 `title`、`summary`、`evidence` 和 `material_ids`，有正文时引用至少一个本范围素材 ID；只能写整段脚本和确定性公式结构能支持的可能关系，不得声称某句脚本导致点击、转化或秒级指标变化，不得生成帧-话术对应关系。没有对应事实时必须写“数据不足以判断”，不补造脚本内容；详情样本只能作为已获取素材范围内的观察，不能外推为行业普遍规律。

脚本事实包的 `content_formula.labels` 使用云图接口数字 ID，固定语义映射为：一级 ID 9 对应商品卖点、一级 ID 10 对应品牌印象、一级 ID 13 对应人群、一级 ID 15 对应使用场景；二级 ID 34 对应功效功能、二级 ID 39 对应使用感受和服务体验、二级 ID 40 对应产品代名词、二级 ID 42 对应成分配方原料、二级 ID 44 对应工艺科技、二级 ID 52 对应人群、二级 ID 55 对应身份认同、二级 ID 56 对应市场地位和权威背书、二级 ID 57 对应品牌调性和故事、二级 ID 87 对应使用场景。用户可见正文只写语义名称，不要输出“一级标签10”“二级标签40”等数字 ID，也不要把 `detail.*` 的具体词误写成一级或二级公式类别。

### 关键词云分析

只读取 `script-input.json` 中的 `materials[*].script_text`、`materials[*].content_formula`、`materials[*].creative_breakdown` 和 `keywordCloud`。`keywordCloud` 是后端基于全部脚本文案确定性生成的候选词与频次；不得修改其中的 `keyword`、`frequency`、`materialIds` 或 `evidenceRefs`，不得从标题、榜单标签或其他事实包补充关键词。

输出 `keywordCloudReview` 审查 NLP 候选词：`accept` 保留关键词，`exclude` 排除关键词，`merge` 合并同义词并用 `target` 指定目标词。只审查候选词，不重新统计频次；`merge` 的最终频次、素材 ID 与证据引用由后端应用层重新汇总。

输出 `keywordCloudInsight`：`oneSentenceConclusion` 只保留一个核心判断，不重复频次、关键词清单或验证动作；`summary` 补充关键词组合、利益点、品质/场景承接关系，并可写下一轮验证方向；只要应用后的关键词云仍有候选词，`sellingPoints` 必须提炼 1–4 条；候选词为空时才可为空并写明数据不足。每条包含 `title`、`description`、`keywordRefs`、`evidenceRefs`，其中 `keywordRefs` 必须来自应用后的关键词云，`evidenceRefs` 必须来自这些关键词对应素材的脚本文本事实，不得引入关键词云和脚本文案之外的新事实。

`topMaterialCombination` 必须严格符合 `ranking-brand-input.json` 的 `outputSchema`，包含各品牌的 `brandConclusions`，并新增一个 `allBrandsConclusion` 全品牌对象。每个对象只输出 `brand`、`classificationSource`、`dataSummary`、`hotMaterialInsight`、`evidence`、`material_ids`；`hotMaterialInsight` 必须包含 `title`、`summary` 和带 `scope`/`material_ids` 的 `evidence`。全品牌对象的 `brand` 固定为“全品牌”，只能引用三批榜单列表及其确定性比较/爆款事实；各品牌对象只能解释同一三批列表按标题匹配后的对应范围，不得生成 `marketingSummary` 或其他跨范围结论。第一章只分析对应范围内的全部素材聚合结果，不分析或举例任何单条素材；两个 AI 段落均不得引用单条素材的素材 ID、标题、排名或指标，也不得使用“某条素材”“其中一条”“头部素材”等方式替代素材 ID 进行个案分析。素材 ID 只保留在 `evidence`、`material_ids` 和爆款事实引用中，不进入用户可见的榜单摘要。`dataSummary` 只覆盖当前表现、环比周期和同周期全行业对比，必须覆盖曝光、CTR、CVR、3 秒播放率，并形成“事实锚点 -> 业务判断 -> 可能机制 -> 策略 -> 验证”的自然段；`hotMaterialInsight` 只写当前范围爆款素材的整体特征、内容机会和验证建议，不逐条复述爆款清单。四项指标不得省略；分别输出两个自然段，不把两个字段合并或重复成一个段落。每个 `dataSummary` 控制在 6 至 10 句、约 420 至 700 个中文字符，每个 `hotMaterialInsight.summary` 控制在 3 至 6 句、约 180 至 360 个中文字符；分析必须是业务判断，不得只是重复数字清单；不得把相关性写成因果。第一章不输出人群维度分析。第一章不输出人群图表、看板或交互数据。品牌名称必须与用户输入的完整参数一致；品牌素材来自同一合并 TOP1000 的运行时品牌匹配。

02 章必须读取 `chapter02AiFacts`，按其 `scopeOrder` 原样输出 `chapter02Insights`。`chapter02Insights` 必须是对象，只包含 `scopeOrder` 与 `scopes`；`scopes` 必须是以 scope 名称为键的对象映射，不能输出数组。本次 scope 顺序为：__SCOPE_LABELS__。scope 第一项固定为 `all`（全量 TOP1000），其后逐个输出每个品牌；每个 scope 必须同时包含人群和营销卖点两组内容，并只引用该 scope 的 `audienceDashboard` 与 `marketingDashboard`。先从该 scope 的 `topMaterials`、年龄/性别/八大人群维度和营销类别/Top 标签取至少一个可见事实锚点，再写摘要；不同非空 scope 不得复用同一摘要。`evidence` 与 `material_ids` 只能引用本 scope 的 `topMaterials`。若 `sampleCount=0` 或 `availability=unavailable`，两组摘要均明确写“数据不足以判断”，并保持 `evidence` 和 `material_ids` 为空，绝不借用全量或其他品牌素材。保留双事实源边界：`chapter02Facts` 仅用于图表、标签统计、范围 Tab 和前端 TOPN 交互；`chapter02AiFacts` 仅用于 AI 二次分析。事实包不再提供顶层 `audienceRankRecords`，不得假设存在该字段，也不得在分析输出中生成任何 `audienceInsights`、`marketingInsights`、`audienceAnalysis` 或 `marketingAnalysis` 字段。品牌 scope 的 AI 二次分析使用行业 TOP1000 内按品牌匹配的全部素材；报告下方汇总图表另从 `chapter02Facts` 读取同一全量匹配素材。营销卖点分析必须围绕类别、Top 标签和命中素材展开，不把 1399 个标签逐项罗列。

`chapter02Insights.scopes` 的每个 scope 值只使用 `audienceSummary` 与 `marketingSummary` 两个字段，不在 scope 值内重复输出 `scope` 或 `label`。两个字段都必须含可直接展示的总结性标题 `title`、一段完整连贯的分析内容 `summary`、`evidence`、`material_ids`。每个 `summary` 控制在 4 至 6 句、约 200 至 420 个中文字符（非空范围最低 180 字），必须同时包含事实锚点、业务判断、形成原因或内容机制解释、内容策略和下一步验证；不能只是对数据的陈述。人群分析必须在同一段中同时体现八大人群、性别和年龄三个维度，并连接到内容方向与验证建议；不得把三个维度拆成编号、列表或不同小节。营销卖点分析继续围绕类别、Top 标签和命中素材展开，并在同一段中给出内容取舍与验证方向。标题应为可直接展示的总结性判断，不得写“分析如下”“洞察 1”等模板化标题。兼容读取旧式 `audienceAnalysis`/`marketingAnalysis` 以及历史 insights 数组，但新输出不得使用旧式字段或 `audienceInsights`/`marketingInsights`。

第 02 章的用户可见分析必须是自然连贯的中文段落，并遵守中文标点规则：每条 `title` 是短语，不要以句号或分号结尾；每条 `summary` 必须是完整句子，以句号、问号或感叹号收束，不要以分号收束，不要以“；”开头。每个维度只输出一段，不使用“1.”、“2.”等编号、列表或分点；不要把编号写进 title。标题与 summary 拼接后应形成“标题：正文”的自然表达。避免同义重复，summary 不要重复 title 的原句。

`chapter02Insights.scopes[*].audienceSummary` 与 `chapter02Insights.scopes[*].marketingSummary` 的每项必须含 title、summary、evidence、material_ids；summary 应以具体标签、素材或内容方向形成可执行洞察，不得复述人群重叠等数据口径。人群重叠口径只保留在事实和 evidence，不进入用户可见正文。

所有结论必须引用指标、标签、素材数量或秒级趋势作为证据；除第一章可见摘要禁止素材 ID 和单素材分析外，其他章节可按各自契约引用素材 ID。事实不足时写“数据不足以判断”。解释只能描述可能关系，不得声称因果；不得生成未经业务与合规确认的滋补、孕期或健康功效宣称。不得写执行过程、重跑、补位调度、代码状态、排障细节、事实包返回、口径说明、仅限观察等处理过程话术；摘要必须基于对应分析范围内的实际指标、标签、趋势或画面写成业务判断。

所有 AI 二次分析字段采用“少量关键事实锚点 + 多句分析判断”的写法：只选最能支撑结论的指标、标签或素材数量作为依据，随后说明事实意味着什么、为什么形成这种表现、为什么值得保留或改写、如何转化为内容策略以及下一步如何验证；不得把指标或标签清单当作结论主体。用户可见的第一、二章每段分析至少 4 句，必须同时完成“事实锚点 -> 业务判断 -> 形成原因/内容机制 -> 内容策略 -> 下一步验证”的链路。数据维度应优先比较行业基线与当前分析范围的曝光、CTR、CVR 和 3 秒播放率，指出可测试的优势或短板；人群维度应把标签覆盖与内容主题连成目标人群假设；营销卖点维度应说明标签组合的内容取舍并给出拆分测试方向。解释只能描述可能关系，不得声称因果，同一模块不得重复同义文本。

`highlightDashboard` 先执行“逐帧图片理解”阶段，再执行分类阶段。先完成同一批次全部成功高光帧的图片理解：每张 JPEG 必须恰好产生一条 `frameUnderstanding`，至少记录 `frame_ref`、`status`、主体、视觉焦点、人物/产品关系、动作、构图和信息表达；无法可靠理解时仍保留该帧引用，并将 `status` 设为 `unavailable`、填写明确的 `failure_reason`。理解阶段先描述画面，再逐帧填写 `standard_category`（portrait/product/other）和至少 12 字的 `category_reason`。人物作为讲解或生产操作主体归 portrait，只有手部辅助展示且产品为视觉主体归 product；other 必须说明不能归前两类的可见理由。标准分类及全部品牌范围的同一帧分类必须与逐帧判断一致，不得为省略分析而整批归入 other。随后读取同一批次全部理解结果，生成并同时输出 `standardClassification` 与 `batchClassification`：`standardClassification` 保留人像、产品、其他三类及其 frame_refs，作为默认视图；`batchClassification` 必须提供本批次专属的统一 `rule`、动态分类名称/说明及分类组。两套分类都只能使用成功高光帧，且各自覆盖全部成功 frame_ref、每帧仅出现一次；证据不足时将 `batchClassification.status` 设为 `unavailable` 并填写明确的 `missing_reason`，不得编造动态分类。现有 `brands` 数组继续输出标准分类的品牌范围投影，第一项 brand 固定为 `全品牌`，其后按事实包品牌顺序输出每个品牌；兼容历史 `groups`，但新输出必须包含 `frameUnderstanding`、`standardClassification` 和 `batchClassification`。实际查看每张 JPEG 后，标准分类按画面占比、视觉焦点和可辨识主体判断：人物主体为 `portrait`，包装/瓶身/内容物/开箱/食用或操作动作主体为 `product`，其余为 `other`；人物与产品同框时选择视觉焦点更强的一类，无法区分时选择 other，不得依据标题、标签或品牌猜测。标准分类组包含 `category`、`frame_refs`、`common_patterns` 和 `derivative_directions`；批次分类组仅包含 `category`、`label`、`rule` 与 `frame_refs`。批次分类按成功帧数 `n` 在证据允许时细分：`n≤3` 目标 2–3 类，`4≤n≤7` 目标 3–6 类，`n≥8` 目标 6–10 类，类别数不得超过成功帧数；类别必须表达可观察且可复用的主体、动作或信息机制，禁止使用“其他1/其他2”等无语义占位名。同一类别内的帧必须共享明确机制，不能仅因颜色、秒数或品牌不同拆类；证据不足时可少分但至少两个有意义类别，否则将 `batchClassification.status` 设为 `unavailable` 并填写明确的 `missing_reason`。本批次视觉主题不输出共性洞察或裂变方向；历史 JSON 即使携带 `common_patterns`、`derivative_directions` 也只读兼容，报告不投影、不展示。没有成功帧时不得编造视觉洞察。报告不展示高光帧选择规则说明。高光帧卡片信息顺序固定为：第一行封面画面或点击 TopN 波峰画面，第二行秒数与点击指数，第三行可点击的视频标题；不再输出“查看素材”按钮。只能描述该帧处于点击指数峰值秒点；不得说该画面导致点击、转化或指标提升，也不能声称其对应某句脚本话术或真实点击次数。

`materialDeepDives` 用于支撑 05｜单素材深度分析中的高光帧观察、确定性秒级拆解和单素材脚本分析。第五章专用 `material-deep-dive-input.json` 已收敛为 `material_id`、`script`、`evidenceIndex.script`、`highlightFrames`（`frame_ref`、`second`、`frame_type`、`available`、`image_path`、可选 `failure_reason`）和 `secondLevelBreakdown.metrics`（固定为点赞、流失、点击、互动、评论五类 canonical 趋势点、高点、流失点及可用性）。脚本分析只读取当前素材对象内的 `script.text`、`script.labels`、`script.formula`、`script.evidence` 和 `evidenceIndex.script`，不得从 Chapter 03 重新拼接，也不得从其他素材复制结论；标题、画面、高光帧、秒级曲线和投放指标不是脚本分析证据。每个素材都必须输出 `scriptAnalysis`，包含 `conclusion`、`evidenceRefs`、`availability`；可用时结论控制在 120–220 个中文字符，说明利益点、表达方式、场景承接、保留/改写方向和下一步验证，但不得把结构差异写成点击、转化或其他指标的因果。`evidenceRefs` 必须全部属于当前素材 `evidenceIndex.script`；无脚本事实时使用 `availability=unavailable`，写“数据不足以判断”并保持引用为空。不要将脚本句子与高光帧秒点建立无依据对应关系。

高光帧观察仍必须将该素材每一张 `available=true` 的 highlightFrames 恰好引用一次，每项只含 `frame_ref` 和至少 40 个中文字符的可观察 observation；不得引用其他素材或失败帧。逐帧观察按主体、人物、产品、动作、场景、构图和可见字幕组织，只写该 JPEG 中可见的具体信息；不同帧不得复用泛化句式。观察不得生成脚本、内容公式、真实互动量、转化或因果结论。五类指标只作为确定性事实由报告曲线展示，不生成点赞、流失、点击、互动或评论指数的自然语言二次分析。该部分在报告中叫“秒级拆解”，不叫“互动时序分析”。


### 分析充分性与品牌范围（analysisQualityVersion=4）

第二章非空范围每段至少 180 字，目标 200–420 字；第三章有正文的每个范围，两条洞察各至少 180 字，目标 200–360 字；关键词总结至少 100 字，卖点解释每条至少 60 字。段落围绕具体观察、业务含义、执行建议和验证边界展开，不重复填充。字数只是结构底线，不能证明判断正确。

第三章保留顶层三字段作为全部已获取详情素材的分析；新增 `scriptBrandInsights`，按 `scriptFacts.brandScopeOrder` 为每个品牌输出独立的 `scriptInsights`、`keywordCloudReview`、`keywordCloudInsight`。各品牌仅读取 `brandScopes[品牌]`，关键词和公式统计已独立计算，不能复制全量结论或借用其他品牌文案。`evidence` 必须摘录被引用素材脚本或公式的原文短语，不能填写“脚本事实”等泛称。正文数量为零的范围，两条洞察仍保留并说明具体缺口及“数据不足以判断”，evidence=[]，无素材时 material_ids=[]；关键词卖点=[]。缺失范围不用满足非空范围字数，但每段至少 12 字，不假装完成品牌分析。

第四章 `brands` 必须严格按“全品牌＋所有指定品牌”逐项输出。每个品牌只分类自身成功帧；无成功帧时 groups=[] 并给出至少 12 字的 missing_reason。每个非空标准分类组必须输出 2–3 条共性洞察及同样数量、一一对应的裂变方向；各条应分别分析不同的可见特征与拍摄机会，不能把同一观点拆句或换词重复，两者正文分别至少 100 字，目标 120–220 字，写清画面特征、表达作用、拍摄建议及验证方式。同一品牌范围内 `portrait`、`product`、`other` 各组的共性洞察正文和裂变方向正文都必须独立，不能复用另一组的正文、标题或模板化尾句；有样本的不同品牌范围也要结合各自帧引用独立撰写，不能把全品牌段落复制过去。少量帧不虚构跨素材共性。动态视觉主题只分类，不新增已取消的共性/裂变正文。

### 输入与执行效率

新任务的 readingRule 说明投影方式：第一章聚合 materials 改为完整 materialIds，保留四项指标、周期比较、缺失状态及完整爆款明细；第二章的 topMaterialIds 按原顺序指向 materialsById 完整对象，所有统计与长尾标签均保留，不截取样本；第三章只携带本范围正文；第五章只携带当前素材脚本与帧，秒级曲线仍由报告从正式事实读取。图片路径相对于 task.imageRoot。factInput 保留原包路径供必要溯源，不是要求重复读取。

先确定本范围的事实锚点再一次写成可展示 JSON，引用从 task 原样选取。缺失范围写具体缺口，避免反复扩写；有事实范围保留现有充分性与独立判断要求。在既有字数范围内写到足以支撑判断即可，不把目标上限当成必达字数。输入和草稿未变时不重复检查；错误只修受影响草稿，再按 --part 合并检查。workspace.inputMetrics 记录输入字节量，validation.timingsSeconds 记录本地校验耗时，两者都不能直接宣称为模型提速比例。
