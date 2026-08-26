# 云图 AI 分析输出精简设计

## 背景

当前分析提示要求对话模型生成 11 个顶层字段，但现行 HTML 只展示
`topMaterialCombination`、`chapter02Insights`、`highlightDashboard` 和
`materialDeepDives`。两个具备完整 AI JSON 与 HTML 的真实批次均证明，
其余 7 个顶层字段及 `topMaterialCombination.overallConclusions` 没有进入
最终 HTML。继续生成这些字段会增加模型推理和结构化输出耗时。

## 目标

缩短第二部分模型分析时间，同时保持当前 01 至 05 章 HTML、Markdown、
展示投影和报告压缩包正常生成。

## 输出契约

新版 AI JSON 只要求以下顶层字段：

- `topMaterialCombination`
- `chapter02Insights`
- 有成功高光帧时的 `highlightDashboard`
- 有秒级拆解契约时的 `materialDeepDives`

不再生成或要求：

- `rankingOverview`
- `audienceInsights`
- `materialComparison`
- `materialDiagnoses`
- `competitorPatterns`
- `opportunityMap`
- `experimentMatrix`
- `topMaterialCombination.overallConclusions`

`topMaterialCombination` 保留 `executiveSummary`、`brandConclusions` 和
`brandComparisonConclusion`。旧版 JSON 中存在额外字段时继续接受并忽略，
确保历史分析产物仍可重新渲染。

## 渲染与校验

报告加载器只校验当前展示字段。删除旧字段对应的证据校验、实验校验和
事实引用校验，同时保留第 01、02、04、05 章现有证据、帧覆盖和真实秒数
校验。展示投影允许缺少 `overallConclusions`，并将其视为空列表。

删除 `_render_html` 内对旧字段生成但未注入模板的中间 HTML，避免代码继续
暗示这些字段属于当前报告契约。

## 兼容性与验收

1. 精简后的测试分析 JSON 可生成 5 个章节及同级 ZIP。
2. 带全部旧字段的历史 JSON 仍可生成报告。
3. 现有两个完整真实批次分别删除旧字段后可以重新渲染。
4. 精简前后 HTML 的当前章节 ID、导航目标及核心展示文本一致。
5. Prompt 不再出现 7 个旧顶层字段、实验矩阵或 `overallConclusions` 输出要求。
6. 第一部分 RPA、规范化、事实包和高光帧处理不变。

## 非目标

- 本轮不拆分或压缩事实包。
- 本轮不新增分析维度。
- 本轮不改变报告视觉样式、章节结构或交互。
- 本轮不删除历史 JSON 文件中的已有字段。
