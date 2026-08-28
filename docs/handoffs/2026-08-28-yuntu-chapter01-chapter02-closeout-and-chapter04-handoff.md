# 云图第一、二部分优化收口与第四部分交接摘要

## 交接结论

第一部分“01｜素材榜单数据洞察”和第二部分“02｜人群及营销卖点洞察”已按用户确认完成优化并收口。下一阶段只进入第四部分“04｜高光画面洞察”的优化，不要改动第一、二部分的展示结构、事实口径或用户可见文本，除非用户重新提出明确要求。

本摘要对应的真实批次为：

`RPA数据汇总/yuntu-rankings-analysis-20260826-top6`

当前代码基线：

- 仓库：`/Users/shuzida/Desktop/FDE客户/小仙炖/yuntu-industry-content-rankings-analysis`
- 分支：`codex/yuntu-presentation-schema`
- 当前提交：`bf74fc9 优化第二章人群营销洞察并完善第一章品牌展示`
- 当前工作区已完成验证，未提交变更为空。

## 已完成的第一、二部分契约

### 第一部分

- 标题：`01｜素材榜单数据洞察`。
- 品牌素材范围：行业 TOP1000 中按品牌标题匹配得到的全部素材，不再使用品牌 Top N 参数。
- 当前品牌全量样本：小仙炖 139 条、五个女博士 420 条、燕之屋 154 条。
- 每个品牌只输出 `brand`、`classificationSource`、`dataSummary`、`evidence`、`material_ids`。
- `dataSummary` 必须包含样本量、累计曝光、CTR 中位数、CVR 中位数和 3 秒播放率中位数，并与行业基线比较。
- 可见摘要只做品牌内聚合分析，不出现单条素材 ID、标题、排名、单条指标或单素材案例。
- 不恢复综合结论、品牌间差异总结、CPM、人群维度、额外人群图表或跨品牌结论。

### 第二部分

- 标题：`02｜人群及营销卖点洞察`。
- scope 顺序固定为：`all`（全量 TOP1000）、小仙炖、五个女博士、燕之屋。
- `chapter02AiFacts` 只供模型二次分析；`chapter02Facts` 只供图表、范围 Tab 和前端交互。
- 每个 scope 只输出 `audienceSummary` 与 `marketingSummary`，每项含 `title`、`summary`、`evidence`、`material_ids`；新输出不再使用 `audienceInsights`、`marketingInsights`。
- 人群摘要必须在同一自然段中体现八大人群、性别、年龄三个维度，并连到内容方向和验证建议，不拆成编号或不同小节。
- 营销卖点摘要继续围绕类别、Top 标签、命中素材和内容取舍展开，不改变原有营销分析思路。
- 两部分摘要均已从纯数据陈述扩展为“事实锚点 → 业务判断 → 可能形成原因/内容机制 → 内容策略 → 下一步验证”。

## 第二部分事实包核验结果

权威诊断目录：

`RPA数据汇总/yuntu-rankings-analysis-20260826-top6/diagnostic-analysis-chapter02-v2`

`analysis-units/audience-marketing-input.json` 中的 `chapter02AiFacts` 已核验：

| scope | 样本量 | marketing recordCount | 人群维度 | 八大人群桶 | 营销类别数 |
|---|---:|---:|---|---:|---:|
| all | 1000 | 1000 | age / gender / crowd | 8 | 7 |
| 小仙炖 | 139 | 139 | age / gender / crowd | 6 | 7 |
| 五个女博士 | 420 | 420 | age / gender / crowd | 8 | 7 |
| 燕之屋 | 154 | 154 | age / gender / crowd | 6 | 6 |

每个 scope 都包含完整的年龄、性别、八大人群维度，以及营销卖点类别、Top 标签、标签数量、命中素材数和标签出现次数。品牌 scope 的 AI 分析数据是行业 TOP1000 内该品牌的全部匹配素材，不是旧版 Top30 截取。

## 当前 AI 分析内容长度

- 第一章三个品牌 `dataSummary`：338 / 346 / 335 个中文字符，均为 4 句。
- 第二章人群摘要：306 / 276 / 303 / 284 个中文字符，均为 4 句。
- 第二章营销摘要：259 / 251 / 267 / 249 个中文字符，均为 4 句。

## 权威产物

新版事实与模型产物：

- `diagnostic-analysis-chapter02-v2/analysis-units/analysis-unit-manifest.json`
- `diagnostic-analysis-chapter02-v2/analysis-units/ranking-brand-input.json`
- `diagnostic-analysis-chapter02-v2/analysis-units/audience-marketing-input.json`
- `diagnostic-analysis-chapter02-v2/analysis-units/highlight-input.json`
- `diagnostic-analysis-chapter02-v2/analysis-units/material-deep-dive-input.json`
- `diagnostic-analysis-chapter02-v2/report-data.json`
- `diagnostic-analysis-chapter02-v2/yuntu-ai-analysis.json`
- `diagnostic-analysis-chapter02-v2/yuntu-ai-analysis.provenance.json`

新版报告：

`RPA数据汇总/yuntu-rankings-analysis-20260826-top6/final-report-chapter02-v2/final-report.html`

该报告仍保留全部图表、品牌 Tab、第二部分范围 Tab、高光画面和单素材深度展示。与上一版报告相比，图表/Tab/高光/单素材相关展示标记数量一致；HTML 中没有 `1. `、`2. `audienceInsights` 或 `marketingInsights` 残留。

## 第四部分当前范围与事实入口

第四部分标题为：`04｜高光画面洞察`。

代码入口：

- `scripts/yuntu_analysis.py`：构造 `highlight-input.json`。
- `scripts/yuntu_report.py`：校验 `highlightDashboard`，并渲染 Markdown/HTML。
- `scripts/yuntu_report_sections.py`：`render_highlight_insights()` 负责第四部分 HTML 展示。
- `prompts/yuntu-analysis-prompt.md`：`highlightDashboard` 规则段。
- `tests/test_yuntu_analysis.py`、`tests/test_yuntu_report.py`：事实包、输出 Schema、渲染和高光引用约束。

第四部分当前事实范围：

- 来源：成功取得秒级详情的素材。
- 成功秒级详情素材：5 条；失败素材不纳入高光/秒级 AI 分析。
- `highlight-input.json` 的 `visualAssets` 提供本地 JPEG、`frame_ref`、秒数、帧类型、点击指数和可用状态。
- 当前 AI 高光分组为 `portrait` 与 `product`，均包含共性洞察、裂变方向和 frame_refs。
- `material-deep-dive-input.json` 仍支撑第五部分的逐帧观察与秒级拆解，不要把第五部分内容误并入第四部分。

第四部分优化时优先确认：用户要改的是高光分组、共性洞察、裂变方向、卡片信息顺序，还是事实包范围。若只改 AI 文字，优先修改 Prompt 与模型 JSON；若改图表/交互，必须区分 `highlight-input.json`、Presentation 和渲染层，不能扩大到第一、二部分。

## 第四部分不可破坏的既有约束

- 只使用 `available=true` 的高光帧；不得因原视频 URL 不可用而跳过已落盘 JPEG。
- 每张成功帧只能归入一个视觉分类；当前报告分类顺序和展示结构需先保留。
- 高光观察只能描述画面可见内容或“处于点击指数峰值秒点”，不得声称画面导致点击、转化或指标提升。
- 裂变方向必须引用本分组已有的 `frame_refs`，不能引用其他分组或失败帧。
- 第四部分不恢复旧的 `scene`、`text_overlay` 分类，除非用户明确要求并同步修改校验、Prompt、Presentation 和渲染。
- 不把第五部分的秒级趋势观察、脚本判断或单素材结论写入第四部分。

## 验证证据

最近一次验证：

```bash
python -m unittest discover -s tests -p 'test_*.py'
python -m compileall -q scripts tests
git diff --check
```

结果：223 项测试通过，编译通过，`git diff --check` 通过；事实包、摘要长度、图表/Tab 保留和旧字段清理也已执行断言核验。

## 新对话启动提示词

```text
继续优化云图行业内容榜单分析项目：

/Users/shuzida/Desktop/FDE客户/小仙炖/yuntu-industry-content-rankings-analysis

先完整阅读：
docs/handoffs/2026-08-28-yuntu-chapter01-chapter02-closeout-and-chapter04-handoff.md

第一部分“01｜素材榜单数据洞察”和第二部分“02｜人群及营销卖点洞察”已经完成并收口，不要改动其已确认的事实口径和展示结构。当前真实批次为：
RPA数据汇总/yuntu-rankings-analysis-20260826-top6

当前权威诊断目录：
RPA数据汇总/yuntu-rankings-analysis-20260826-top6/diagnostic-analysis-chapter02-v2

当前权威报告：
RPA数据汇总/yuntu-rankings-analysis-20260826-top6/final-report-chapter02-v2/final-report.html

下一阶段只优化第四部分“04｜高光画面洞察”。先读取 highlight-input.json、material-deep-dive-input.json、yuntu-ai-analysis.json、Prompt、Schema、校验、Presentation 和第四部分渲染代码，等待我给出具体优化要求后再改。

必须保持：
1. 第一部分使用行业 TOP1000 内各品牌全部匹配素材，不恢复 Top N、CPM、综合结论、品牌间总结或可见素材 ID。
2. 第二部分继续区分 chapter02AiFacts（AI 分析）与 chapter02Facts（图表/Tab/交互）。
3. 第四部分只使用 available=true 的本地高光帧，遵守 frame_refs 唯一归类和不可因果归因约束。
4. 第五部分的逐帧观察和秒级拆解不要并入第四部分。
5. 使用真实批次，不重新执行 RPA，除非我明确要求。
6. 修改后用当前对话模型生成分析 JSON，再执行 attest-analysis、render-report 和完整自动化验证。
7. 不连接浏览器，由我检查最终 HTML。
```
