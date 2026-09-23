# 云图第一部分优化收口与第二部分启动交接摘要

## 交接结论

第一部分“01｜素材榜单数据洞察”已完成第二轮清理。当前权威实现基于行业 TOP1000 内按品牌匹配的全部素材，不再存在品牌 Top N 参数，也不再输出人群维度、综合结论、品牌间差异总结、CPM 分析、单素材案例或用户可见的素材 ID。

下一阶段进入第二部分“02｜人群及营销卖点洞察”优化。当前对话尚未定义第二部分的具体改动项；新阶段应先核对现有第二部分的数据、分析文字和渲染结果，再按用户后续要求逐项实施，不要自行扩展范围。

## 当前代码基线

- 仓库：`/Users/shuzida/Desktop/FDE客户/小仙炖/yuntu-industry-content-rankings-analysis`
- 分支：`codex/yuntu-presentation-schema`
- 当前提交：`285165a 聚焦品牌整体洞察，精简第一章报告`
- 远端：`origin/codex/yuntu-presentation-schema` 与当前提交一致。
- 生成本交接文档前工作区为干净状态。
- 第一部分主要提交：
  - `a7fe316 丰富品牌人群洞察，优化第一章报告展示`
  - `285165a 聚焦品牌整体洞察，精简第一章报告`
- 最近一次完整验证：219 项测试通过，`python -m compileall -q scripts tests` 通过，`git diff --check` 通过。

## 本轮用户最终确认的第一部分需求

1. 删除报告中的综合结论和人群维度。
2. 各品牌素材榜单数据直接覆盖行业 TOP1000 内该品牌的全部匹配素材，增加累计曝光、CTR、CVR 和 3 秒播放率分析。
3. 第一部分不再接受或显示品牌 Top N 参数，`pre_input` 只保留秒级拆解素材数。
4. “01｜TOP 素材组合结论”改为“01｜素材榜单数据洞察”，品牌面板不再显示“素材列表数据：”前缀。
6. 第一部分不分析 CPM；事实包、提示词和最终文字均不出现“CPM 数据不足以判断”等内容。
7. 人群结论中不显示“各标签允许重叠，不能解释为互斥人群分布”等口径说明。
8. 分析文字应比纯数据陈述多一些，但控制篇幅，形成“事实 -> 判断 -> 验证方向”。
9. 删除品牌间差异总结，并清理事实包、输出 Schema、Presentation 和渲染中的残留字段。
10. 第一部分不得分析或举例单条素材；不得在可见摘要中出现素材 ID、单条标题、排名或单条指标。分析必须基于该品牌全部 Top N 的聚合指标、整体标题主题、整体素材标签结构和整体人群覆盖。
11. 必须参考真实数据并用修改后的代码重新生成报告。
12. 不连接浏览器，由用户直接检查生成的 HTML；本轮只执行自动化产物校验。

用户已确认当前生成版本没有问题，第一部分可以收口。

## 第一部分最终契约

### 模型输出

`topMaterialCombination` 当前严格只允许：

```json
{
  "brandConclusions": [
    {
      "brand": "",
      "classificationSource": "runtime_title_rule",
      "dataSummary": "",
      "evidence": [],
      "material_ids": []
    }
  ]
}
```

已经删除且当前 Schema v6 会拒绝的字段包括：

- `executiveSummary`
- `brandComparisonConclusion`
- 其他 `topMaterialCombination` 顶层残留字段

`brandConclusions` 中不再生成 `peopleSummary` 或 `marketingSummary`。第一部分只展示榜单聚合数据洞察，营销与人群分析仍属于第二部分。

### 可见展示

每个品牌面板只显示一段：

```text
...
```

具体规则：

- `dataSummary` 必须包含行业 TOP1000 内该品牌全部匹配素材的样本量、累计曝光、CTR 中位数、CVR 中位数和 3 秒播放率中位数，并与行业 TOP1000 中位数比较。
- `dataSummary` 在数据后增加 2 至 3 个短句，解释整体指标组合、整体主题结构和分组测试方向。
- 第一部分只做品牌内聚合分析，不做跨品牌比较。
- 第一部分不展示人群图表、看板或额外交互。
- 第一部分可见摘要不出现素材 ID 或单素材分析措辞。

### 审计字段边界

`evidence` 和 `material_ids` 继续保留，用于来源审计与事实验证，但不会进入第一部分的 HTML/Markdown 可见正文。当前 Schema v6 校验会收集该品牌 Top N 的真实素材 ID，并拒绝 `dataSummary` 或 `peopleSummary` 中出现其中任一 ID。

不要因为用户要求可见文字不出现 ID 而删除审计字段；也不要把审计字段重新投影到第一部分 Presentation 或 HTML。

## 真实数据基线

真实批次：

`RPA数据汇总/yuntu-rankings-analysis-20260826-top6`

范围：

- 行业：食品饮料
- 时间：`LAST_7_DAYS`
- 行业榜单：TOP1000，共 1000 条
- 品牌：小仙炖、五个女博士、燕之屋
- 各品牌第一部分分析量级：行业 TOP1000 内该品牌全部匹配素材
- 秒级详情成功素材：5 条，仅用于第 04、05 章，不进入第一部分分析

行业 TOP1000 中位数：

| 指标 | 中位数 |
|---|---:|
| CTR | 2.22% |
| CVR | 3.06% |
| 3 秒播放率 | 31.43% |

各品牌 Top30 聚合指标：

| 品牌 | 累计曝光 | CTR 中位数 | CVR 中位数 | 3 秒播放率中位数 |
|---|---:|---:|---:|---:|
| 小仙炖 | 1,620,138 | 0.89% | 2.79% | 19.88% |
| 五个女博士 | 3,688,678 | 2.09% | 5.18% | 37.43% |
| 燕之屋 | 1,599,596 | 1.67% | 2.22% | 33.30% |

第一部分使用的主要人群聚合事实：

| 品牌 | 主要聚合事实 |
|---|---|
| 小仙炖 | 新锐白领 30/30；24-30 岁 24/30、84.76% 曝光覆盖；女性 28/30、95.16%；精致妈妈 15/30、59.82%。 |
| 五个女博士 | 女性与 36-40 岁均为 30/30；精致妈妈 27/30、95.66%；小镇青年 26/30、89.90%。 |
| 燕之屋 | 36-40 岁 30/30；新锐白领 28/30、94.54%；资深中产 15/30、52.63%；男性 22/30、76.23%；女性 21/30、62.08%。 |

用于补充整体内容判断的 Top30 标题主题统计：

- 小仙炖：孕产相关 10 条，礼赠相关 12 条。
- 五个女博士：虾青素 14 条，胶原 12 条，富铁或气色 4 条。
- 燕之屋：三伏或夏季 9 条，礼赠 4 条，孕期 4 条。

这些统计来自 `ranking-brand-input.json` 中完整的品牌 Top30 素材，不是从个别素材外推。

## 代码改动位置

| 文件 | 第一部分当前职责与改动 |
|---|---|
| `scripts/yuntu_analysis.py` | 事实包 Schema 升至 v6；ranking unit/manifest 升至 v4；Top N 指标增加曝光、CTR、CVR、3 秒播放率和 `audienceFacts`；第一部分输出 Schema 只允许 `brandConclusions`。 |
| `prompts/yuntu-analysis-prompt.md` | 删除综合/跨品牌/CPM要求；要求 Top N 聚合分析；禁止第一部分可见摘要引用素材 ID 或单素材案例。 |
| `scripts/yuntu_report.py` | Schema v6 严格字段校验；四项指标、人群标签和 Top N ID 范围校验；拒绝可见摘要出现真实素材 ID；Markdown 删除综合及品牌差异段。 |
| `scripts/yuntu_presentation.py` | Presentation Schema 升至 v3；第一部分只投影 `brandTabs` 和 `brandPanels`，面板只含 data/people 两种 insight。 |
| `scripts/yuntu_report_sections.py` | 第一部分 HTML 只渲染“素材列表数据”和“人群维度”，不渲染证据、综合结论、跨品牌总结或人群图表。 |
| `assets/report/unified-report.css` | 为同一品牌面板内两段结论补充分段样式。 |
| `tests/test_yuntu_analysis.py` | 覆盖事实包、Schema、Prompt、四项指标、人群事实、无 CPM 和聚合分析规则。 |
| `tests/test_yuntu_report.py` | 覆盖残留字段拒绝、四项指标、人群标签、素材 ID 可见摘要门禁和渲染结果。 |
| `tests/test_yuntu_presentation.py` | 覆盖 Presentation v3 及第一部分只保留品牌 Tab/面板。 |

## 当前权威产物

诊断目录：

`RPA数据汇总/yuntu-rankings-analysis-20260826-top6/diagnostic-analysis-chapter01-v2`

关键文件：

- `analysis-units/ranking-brand-input.json`
- `analysis-units/audience-marketing-input.json`
- `analysis-units/highlight-input.json`
- `analysis-units/material-deep-dive-input.json`
- `analysis-units/analysis-unit-manifest.json`
- `report-data.json`
- `yuntu-analysis-prompt.md`
- `yuntu-ai-analysis.schema.json`
- `yuntu-ai-analysis.json`
- `yuntu-ai-analysis.provenance.json`

最终报告：

`RPA数据汇总/yuntu-rankings-analysis-20260826-top6/final-report-chapter01-v2`

包含：

- `final-report.html`
- `final-report.md`
- `final-report-data.json`
- `presentation-report.json`
- 同级归档 `final-report-chapter01-v2.zip`

当前版本：

- `report-data.json`：Schema v6
- ranking analysis unit：Schema v4
- Presentation：Schema v3
- `presentation.chapters.chapter01` 只含 `brandTabs`、`brandPanels`；第二章不再输出品牌 TopN 控件
- 生成来源：`manual_model_generated`
- 生成器：`Codex current-dialog model`

来源证明哈希：

| 产物 | SHA-256 |
|---|---|
| `yuntu-ai-analysis.json` | `068e9e18fa65ebe36d3485deb04495ea4a2221bba3ffd2f04244c2f618f148e9` |
| `analysis-unit-manifest.json` | `202f24aa6d77c13dae9c118ea43b374661262a149ba4643b9d67d3fd3fd6fef7` |
| `yuntu-analysis-prompt.md` | `a3a6084ac7c2e3771ca412bab290508cdde011bdeb6496d589220be5df7709ab` |

模型输入与报告投影当前体积：

| 文件 | 字节数 |
|---|---:|
| `ranking-brand-input.json` | 537,818 |
| `audience-marketing-input.json` | 649,859 |
| `highlight-input.json` | 14,283 |
| `material-deep-dive-input.json` | 80,573 |
| `analysis-unit-manifest.json` | 2,273 |
| `report-data.json` | 1,189,085 |
| Prompt | 10,512 |
| AI JSON | 47,418 |

## 已执行的清理

批次根目录下以下旧诊断目录已移入 macOS 废纸篓，不再位于项目批次目录：

- `diagnostic-analysis`
- `diagnostic-analysis-attempt1`
- `diagnostic-analysis-attempt2`
- `diagnostic-analysis-latest-code`

废纸篓恢复位置：

`/Users/shuzida/.Trash/yuntu-rankings-analysis-20260826-top6-old-diagnostics-codex-cleanup`

总计约 27 MB。当前批次根目录只保留 `diagnostic-analysis-chapter01-v2` 作为权威诊断目录。旧的 `final-report` 和 `final-report-latest-code` 目录仍在批次根目录，本轮没有删除。

## 第一部分仍未实现的延期需求

用户最初提出第一部分还需要增加：

- 环比上周。
- 对比大盘，即相同条件下的全行业筛选结果。
- 因此一次任务可能需要执行三次列表 RPA：当前周期品牌范围、上周品牌范围、当前周期全行业范围。

该项改动较大，可能同时涉及 RPA、事实包、Prompt、校验、Presentation 和报告渲染，用户明确同意先实现前三项，因此本轮没有实施。

这个延期需求仍属于第一部分列表数据对比能力。进入第二部分优化时不要顺手实现，也不要把它误并入第二部分的人群/营销分析；只有用户重新明确要求时再单独设计。

## 第二部分当前契约

第二部分标题为“02｜人群及营销卖点洞察”，当前模型输出为：

```text
chapter02Insights
  scopeOrder
  scopes
    <scope>
      audienceSummary
      audienceInsights[]
      marketingSummary
      marketingInsights[]
```

当前 scope 顺序：

```text
all（全量 TOP1000）
小仙炖
五个女博士
燕之屋
```

第二部分必须继续保留双事实源边界：

| 数据源 | 用途 | 品牌数据量级 |
|---|---|---|
| `chapter02AiFacts` | 模型二次分析唯一来源 | 用户输入的品牌 Top N，当前为 Top30 |
| `chapter02Facts` | 前端图表、范围 Tab 和 Top N 控件唯一来源 | 该品牌在 TOP1000 中的全量匹配素材 |

当前每个 scope 同时包含人群与营销卖点：

- 人群：`audienceSummary` 和至少 2 条 `audienceInsights`。
- 营销：`marketingSummary` 和至少 2 条 `marketingInsights`。
- 人群 Dashboard：年龄、性别、八大人群标签桶。
- 营销 Dashboard：类别、标签数量、命中次数与标签明细。
- Presentation 第二部分当前只包含 `scopeTabs` 与 `panels`，每个 panel 显式声明 `aiFactSource=chapter02AiFacts`、`chartFactSource=chapter02Facts`。

第二部分优化时，先判断新增内容属于：

1. 只需要 AI 分析：进入 `chapter02AiFacts`，同步 Prompt、Schema 和证据校验。
2. 只需要图表/交互：进入 `chapter02Facts` 与 Presentation，不应复制给模型。
3. 分析与图表都需要：分别设计 AI 事实和展示事实，不能混用一个全量对象。

## 第二部分启动建议

1. 先阅读当前权威报告的第二部分，以及 `audience-marketing-input.json`、`report-data.json` 中的 `chapter02AiFacts` / `chapter02Facts`。
2. 使用同一真实批次作为基线，不重新执行 RPA，除非用户明确要求采集新数据。
3. 先记录用户对第二部分的具体修改项，再判断影响事实包、Prompt、Schema、校验、Presentation、HTML/Markdown 中的哪些层。
4. 保持第一部分已经确认的输出不变，第二部分改动不得恢复综合结论、跨品牌总结、CPM 或单素材分析到第一部分。
5. 修改后重新执行 `prepare-analysis -> 当前对话模型分析 -> attest-analysis -> render-report`。
6. 继续使用真实数据生成新报告，不做浏览器检查；由用户检查报告。
7. 完成后运行全量测试、Python 编译、`git diff --check`，并扫描第二部分是否存在未展示但仍残留的分析字段。

## 关键命令

仅重新构造分析事实，不执行 RPA：

```bash
python scripts/rpa_connector.py prepare-analysis \
  --input-dir 'RPA数据汇总/yuntu-rankings-analysis-20260826-top6' \
  --output-dir '<新的第二部分诊断目录>' \
  --brand-top-n 30
```

生成模型 JSON 后绑定来源：

```bash
python scripts/rpa_connector.py attest-analysis \
  --analysis-json '<诊断目录>/yuntu-ai-analysis.json' \
  --fact-pack-json '<诊断目录>/analysis-units/analysis-unit-manifest.json' \
  --prompt '<诊断目录>/yuntu-analysis-prompt.md' \
  --source manual_model_generated \
  --generator 'Codex current-dialog model'
```

渲染报告：

```bash
python scripts/rpa_connector.py render-report \
  --analysis-json '<诊断目录>/yuntu-ai-analysis.json' \
  --fact-pack-json '<诊断目录>/report-data.json' \
  --analysis-provenance '<诊断目录>/yuntu-ai-analysis.provenance.json' \
  --highlight-asset-root 'RPA数据汇总/yuntu-rankings-analysis-20260826-top6' \
  --output-dir '<新的第二部分报告目录>'
```

验证：

```bash
python -m unittest discover -s tests -v
python -m compileall -q scripts tests
git diff --check
```

## 新对话启动提示词

```text
继续优化项目：

/Users/shuzida/Desktop/FDE客户/小仙炖/yuntu-industry-content-rankings-analysis

当前分支：
codex/yuntu-presentation-schema

先完整阅读交接摘要：
docs/handoffs/2026-08-27-yuntu-chapter01-closeout-and-chapter02-handoff.md

第一部分“01｜TOP 素材组合结论”已经由用户确认通过并收口。当前权威真实批次为：
RPA数据汇总/yuntu-rankings-analysis-20260826-top6

当前权威诊断目录：
RPA数据汇总/yuntu-rankings-analysis-20260826-top6/diagnostic-analysis-chapter01-v2

当前权威报告：
RPA数据汇总/yuntu-rankings-analysis-20260826-top6/final-report-chapter01-v2/final-report.html

下一阶段只优化第二部分“02｜人群及营销卖点洞察”。先读取当前报告、audience-marketing-input.json、report-data.json、Prompt、Schema、校验、Presentation 和第二部分渲染代码，等待用户给出具体修改项后再实施。

必须保持：
1. 第一部分只含逐品牌 Top N 的“素材列表数据”和“人群维度”聚合分析。
2. 第一部分不恢复综合结论、品牌间差异总结、CPM、单素材分析或可见素材 ID。
3. 第二部分继续区分 chapter02AiFacts 与 chapter02Facts：前者只供 AI 分析，后者只供图表、Tab 和 Top N 控件。
4. 使用真实批次数据，不重新拉取 RPA，除非用户明确要求。
5. 修改后用当前对话模型重新生成分析 JSON，再执行 attest-analysis 与 render-report。
6. 不连接浏览器，由用户检查最终报告。
7. 第一部分尚未实现的环比上周/对比大盘三次列表 RPA 是独立延期需求，不要混入本轮第二部分优化。
```
