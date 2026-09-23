# 云图第四部分优化收口与后续章节交接摘要

## 交接结论

第四部分“04｜高光画面洞察”本轮优化已完成并可收口。下一阶段进入后续部分优化时，不要回退第四部分既定事实口径、品牌分组、共性洞察/裂变方向结构和资源导出逻辑，除非用户明确要求回溯。

真实批次：`RPA数据汇总/yuntu-rankings-analysis-20260826-top6`

仓库：`/Users/shuzida/Desktop/FDE客户/小仙炖/yuntu-industry-content-rankings-analysis`

当前分支：`codex/yuntu-presentation-schema`。工作区有未提交变更，后续对话先执行 `git status --short`，不要覆盖或回退已有修改。

## 第一、二部分已完成优化（本轮对话汇总）

### 第一部分｜素材榜单数据洞察

- 增加“全品牌”分析 Tab，覆盖行业 TOP1000 全量素材，作为跨品牌基线。
- 各品牌分析范围改为行业 TOP1000 内按标题规则匹配的全部素材，不再使用品牌 Top N 截取。
- 全品牌与品牌分析均保留数据事实与 AI 二次分析分层；全品牌不再只有数据陈述。
- `topMaterialCombination` 仅保留 `brandConclusions` 与可选 `allBrandsConclusion`，清理旧的综合结论、品牌间比较、CPM、人群维度和额外残留字段。
- 前端删除“各品牌榜单分析”冗余标题及标题下分隔线，收紧标题与品牌 Tab/分析内容之间的垂直间距。

### 第二部分｜人群及营销卖点洞察

- 全量 TOP1000 Tab 统一命名为“全品牌”，并移除固定展示的旧品牌名称及“全量 TOP1000”残留 Tab 文案。
- `chapter02AiFacts` 专供 AI 二次分析，`chapter02Facts` 专供图表、范围 Tab 和 TOPN 交互，保持双事实源边界。
- 新输出只使用 `chapter02Insights.scopes[*].audienceSummary` 与 `marketingSummary`，每项包含 `title`、`summary`、`evidence`、`material_ids`。
- 人群摘要在同一自然段中同时覆盖八大人群、性别、年龄，并串联事实锚点、业务判断、可能机制、内容策略和验证建议。
- 营销摘要围绕类别、Top 标签、命中素材和内容取舍展开，不逐项罗列标签。
- 停止生成顶层 `audienceRankRecords`、`audienceFacts`、`marketingFacts`、`audienceInsights`、`marketingInsights` 等旧字段；TOPN 交互直接读取 `chapter02Facts[*].topMaterials`。
- 报告渲染保留历史字段回退能力，但新事实包和新分析 JSON 不再依赖这些旧字段。

第一、二部分已完成收口，后续仅在用户明确要求时回溯。

## 第四部分已完成内容

### 事实包与 Prompt

- `scripts/yuntu_analysis.py` 为每张 `available=true` 高光帧补充标题归属品牌。
- 权威输入：`diagnostic-analysis-chapter04-v4-model/analysis-units/highlight-input.json`。
- 当前成功秒级拆解素材 5 条，可用高光帧 28 张；失败帧不进入高光分析。
- `prompts/yuntu-analysis-prompt.md` 将 `highlightDashboard` 改为品牌作用域结构：`brands[{brand, groups}]`。
- 第一项 brand 固定为“全品牌”；全品牌 groups 覆盖全部成功帧，每张帧只出现一次。
- 品牌 groups 只能引用标题匹配该品牌的成功帧，不复制全品牌结论。
- 视觉分类固定为 `portrait`、`product`、`other`，顺序固定；不输出 `scene`、`text_overlay`。
- `common_patterns` 与 `derivative_directions` 使用一致的 `title`、`body`、`frame_refs` 结构，数组长度一致并逐项对应。

### Presentation、校验与前端

- `scripts/yuntu_presentation.py` 支持品牌级高光投影，并校验全品牌/品牌帧覆盖范围。
- 第四章 Presentation 不再写顶层 `categories`，分类位于 `chapters.chapter04.brands[*].categories`。
- `scripts/yuntu_report.py` 支持新 `brands` 校验，同时保留历史 `groups` 兼容读取。
- `scripts/yuntu_report_sections.py` 继续负责第四部分 HTML 卡片、品牌 Tab、分类 Tab、共性洞察和裂变方向渲染。

### 真实图片与 Excel

- 最新报告包含 28 张真实 JPEG 高光帧，HTML 引用 84 处，缺失引用 0。
- 图片目录：`final-report-chapter04-v4-model/assets/highlight-frames/`。
- Excel：`final-report-chapter04-v4-model/highlight-frames.xlsx`，已包含图片资源。
- 重新渲染时 `--highlight-asset-root` 必须传入批次根目录 `RPA数据汇总/yuntu-rankings-analysis-20260826-top6`，不要传入其 `highlights` 子目录，否则相对路径无法复制。

## 权威产物

- [事实包](../../RPA数据汇总/yuntu-rankings-analysis-20260826-top6/diagnostic-analysis-chapter04-v4-model/report-data.json)
- [高光分析输入](../../RPA数据汇总/yuntu-rankings-analysis-20260826-top6/diagnostic-analysis-chapter04-v4-model/analysis-units/highlight-input.json)
- [分析 JSON](../../RPA数据汇总/yuntu-rankings-analysis-20260826-top6/diagnostic-analysis-chapter04-v4-model/yuntu-ai-analysis.json)
- [分析 provenance](../../RPA数据汇总/yuntu-rankings-analysis-20260826-top6/diagnostic-analysis-chapter04-v4-model/yuntu-ai-analysis.provenance.json)
- [最新报告 HTML](../../RPA数据汇总/yuntu-rankings-analysis-20260826-top6/final-report-chapter04-v4-model/final-report.html)
- [Presentation JSON](../../RPA数据汇总/yuntu-rankings-analysis-20260826-top6/final-report-chapter04-v4-model/presentation-report.json)
- [高光帧 Excel](../../RPA数据汇总/yuntu-rankings-analysis-20260826-top6/final-report-chapter04-v4-model/highlight-frames.xlsx)

本次分析 provenance 标记为 `manual_model_generated`，由当前对话模型基于新事实包和真实帧资源生成，不是复用旧版 v6 分析。

## 验证结果

已通过关键 Presentation、Schema、报告渲染测试，`python -m compileall -q scripts tests` 和 `git diff --check` 通过。资源专项核验确认 28 张图片均已复制，HTML 所有高光图片引用均可解析。

## 后续对话启动提示

```text
继续优化云图行业内容榜单分析项目：
/Users/shuzida/Desktop/FDE客户/小仙炖/yuntu-industry-content-rankings-analysis

先阅读：
docs/handoffs/2026-08-28-yuntu-chapter04-closeout-and-next-handoff.md
docs/handoffs/2026-08-28-yuntu-chapter01-chapter02-closeout-and-chapter04-handoff.md

第一、二、四部分已完成并收口。当前真实批次为：
RPA数据汇总/yuntu-rankings-analysis-20260826-top6

下一阶段先梳理我指定后续部分的事实包、Prompt、Schema、Presentation、前端渲染和测试，再按具体要求修改。不要回退第四部分品牌级 highlightDashboard 契约、真实 JPEG 资源复制、Excel 导出和 frame_refs 校验。
```
