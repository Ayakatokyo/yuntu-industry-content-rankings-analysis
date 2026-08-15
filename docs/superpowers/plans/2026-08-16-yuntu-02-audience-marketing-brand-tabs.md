# 02｜人群及营销卖点洞察和品牌 Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 02｜人群洞察升级为“人群及营销卖点洞察”，并让全量 TOP1000 与各品牌都拥有可切换的 tab，tab 内容同时切换 AI 二次分析和下方汇总图表。

**Architecture:** 事实加工层继续由 `scripts/yuntu_top_materials.py` 和 `scripts/yuntu_analysis.py` 负责，只是从“单一 audienceDashboard”升级为“全量 + 品牌”的 chapter 02 scope bundle，并新增营销卖点聚合。报告层由 `scripts/yuntu_report.py` 和 `scripts/yuntu_report_sections.py` 消费该 bundle，按统一 tab 结构渲染 AI 结论、年龄/性别/八大人群图表和营销卖点图表。前 01 章只保留 data 维度，移除 people / marketing 的重复内容，避免 01 和 02 讲同一件事。

**Tech Stack:** Python 3、stdlib `json` / `statistics` / `collections`、现有 HTML template、现有 `assets/report/unified-report.js` 和 `assets/report/unified-report.css`、`unittest`。

---

### Task 1: 把第 02 章的事实加工拆成“全量 + 品牌” scope bundle，并新增营销卖点聚合

**Files:**
- Modify: `scripts/yuntu_top_materials.py`
- Modify: `scripts/yuntu_analysis.py`
- Test: `tests/test_yuntu_analysis.py`

- [ ] **Step 1: 写失败测试**

先补测试，固定真实批次口径：`yuntu-analysis-data.json` 中营销卖点唯一标签数为 `1399`，总命中次数为 `5825`，并且品牌 scope 也能各自产出营销卖点聚合。

建议新增断言：

```python
data = json.loads((root / "diagnostic-analysis" / "yuntu-analysis-data.json").read_text(encoding="utf-8"))
self.assertEqual(data["chapter02Facts"]["scopeOrder"][0], "all")
self.assertIn("WONDERLAB/万益蓝", data["chapter02Facts"]["scopeOrder"])
self.assertEqual(data["chapter02Facts"]["all"]["marketingDashboard"]["tagCount"], 1399)
self.assertEqual(data["chapter02Facts"]["all"]["marketingDashboard"]["occurrenceCount"], 5825)
```

- [ ] **Step 2: 跑定向测试确认失败**

Run:

```bash
python -m unittest tests.test_yuntu_analysis -v
```

Expected: 新增 `chapter02Facts` / `marketingDashboard` 断言失败，当前代码还只有 `audienceDashboard`。

- [ ] **Step 3: 实现最小事实加工**

在 `scripts/yuntu_top_materials.py` 新增营销卖点聚合函数，输出每个 scope 的：

```python
{
    "tagCount": 1399,
    "occurrenceCount": 5825,
    "categories": {
        "内容形式": {
            "tagCount": 11,
            "occurrenceCount": 877,
            "topTags": [...]
        }
    }
}
```

在 `scripts/yuntu_analysis.py` 新增 `chapter02Facts`，结构固定为：

```python
{
    "scopeOrder": ["all", "WONDERLAB/万益蓝", "五个女博士", "燕之屋"],
    "all": {
        "label": "全量 TOP1000",
        "audienceDashboard": {...},
        "marketingDashboard": {...}
    },
    "WONDERLAB/万益蓝": {
        "label": "WONDERLAB/万益蓝",
        "audienceDashboard": {...},
        "marketingDashboard": {...}
    }
}
```

全量 scope 继续沿用候选池 TOP1000；品牌 scope 从同一批 `brandTopNFacts.brands[brand].materials` 生成，不再回退到 01 章的品牌文案。

- [ ] **Step 4: 跑测试确认通过**

Run:

```bash
python -m unittest tests.test_yuntu_analysis -v
```

Expected: 新增 `chapter02Facts`、营销卖点聚合和品牌 scope 断言全部通过。

### Task 2: 收紧 AI 二次分析合同，让 01 章只保留数据，02 章同时覆盖人群和营销卖点，并按 scope 分发

**Files:**
- Modify: `scripts/yuntu_analysis.py`
- Modify: `tests/test_yuntu_analysis.py`
- Modify: `tests/test_yuntu_report.py`

- [ ] **Step 1: 写失败测试**

增加 prompt 契约断言，要求：

1. 01 章不再要求 `peopleSummary` / `marketingSummary`。
2. 02 章 prompt 明确包含 `chapter02Facts`、`scopeOrder`、`all`、每个品牌名。
3. AI 输出新增 `chapter02Insights`，且每个 scope 必须同时包含 `audienceInsights` 和 `marketingInsights`。
4. `01｜TOP 素材组合结论` 只保留 data 维度的 `overallConclusions` 与 `brandConclusions`。

建议新增的输出结构：

```json
{
  "topMaterialCombination": {
    "executiveSummary": {...},
    "overallConclusions": [
      {"dimension": "data", "summary": "...", "evidence": [...], "material_ids": [...]}
    ],
    "brandConclusions": [
      {"brand": "WONDERLAB/万益蓝", "classificationSource": "runtime_title_rule", "dataSummary": "...", "evidence": [...], "material_ids": [...]}
    ],
    "brandComparisonConclusion": {...}
  },
  "chapter02Insights": {
    "scopeOrder": ["all", "WONDERLAB/万益蓝", "五个女博士", "燕之屋"],
    "scopes": {
      "all": {
        "audienceInsights": [...],
        "marketingInsights": [...]
      }
    }
  }
}
```

- [ ] **Step 2: 跑定向测试确认失败**

Run:

```bash
python -m unittest tests.test_yuntu_analysis tests.test_yuntu_report -v
```

Expected: 当前 prompt 和报告契约仍旧只认识 `audienceInsights` / `marketingFacts`，新增断言失败。

- [ ] **Step 3: 实现固定模板**

在 `_prompt_text()` 中把 02 章写成固定模板，明确：

1. 全量 scope 是 `all`。
2. 品牌 scope 必须按 `scopeOrder` 逐个输出。
3. 每个 scope 同时写人群和营销卖点分析。
4. 每条结论必须遵守“事实锚点 -> 业务判断 -> 下一步验证”。
5. 01 章删掉人群与营销卖点要求，只保留 data 维度。

同时把 `prepare_analysis()` 写出的提示词文件替换为新的 chapter 02 版本。

- [ ] **Step 4: 跑测试确认通过**

Run:

```bash
python -m unittest tests.test_yuntu_analysis tests.test_yuntu_report -v
```

Expected: Prompt contract 和章节输出契约通过，01 章不再要求 people / marketing 文案。

### Task 3: 把报告 02 章改成统一 tab 结构，tab 内容同时切换 AI 结论和下方汇总图表

**Files:**
- Modify: `scripts/yuntu_report_sections.py`
- Modify: `scripts/yuntu_report.py`
- Modify: `scripts/templates/final-report-template.html`
- Modify: `assets/report/unified-report.js`
- Modify: `assets/report/unified-report.css`
- Test: `tests/test_yuntu_report.py`

- [ ] **Step 1: 写失败测试**

补报告测试，覆盖以下行为：

1. `02｜人群及营销卖点洞察` 的 HTML 里有一个 tablist，首个 tab 是全量 `全量 TOP1000`，后面是品牌 tab。
2. 每个 tab 都渲染 AI 二次分析和两块汇总：人群 + 营销卖点。
3. 切换 tab 时，AI 内容和下方图表同时切换。
4. 02 章 Markdown 也同步展示 scope 标题和品牌名，不再只输出单一全量版本。

建议的测试断言：

```python
self.assertIn('data-chapter02-tab="all"', html)
self.assertIn('data-chapter02-tab="WONDERLAB/万益蓝"', html)
self.assertIn('02｜人群及营销卖点洞察', html)
self.assertIn('营销卖点洞察', html)
self.assertIn('全量 TOP1000', html)
```

- [ ] **Step 2: 跑定向测试确认失败**

Run:

```bash
python -m unittest tests.test_yuntu_report -v
```

Expected: 现有 `02｜人群洞察` 单视图实现不含 tab scope bundle，新增断言失败。

- [ ] **Step 3: 实现 tab 渲染**

在 `scripts/yuntu_report_sections.py` 增加一个章节级渲染器，接受 `chapter02Facts` 和 `chapter02Insights`，生成：

```html
<div class="chapter-tabs" role="tablist">
  <button data-chapter02-tab="all">全量 TOP1000</button>
  <button data-chapter02-tab="WONDERLAB/万益蓝">WONDERLAB/万益蓝</button>
  ...
</div>
<section data-chapter02-panel="all">...</section>
<section data-chapter02-panel="WONDERLAB/万益蓝" hidden>...</section>
```

每个 panel 内固定顺序：

1. scope 标题
2. AI 二次分析
3. 人群汇总
4. 营销卖点汇总

营销卖点汇总图表建议用“类别横向条形图 + 类别内 Top 标签列表”，不用饼图。原因是当前真实批次有 `1399` 个唯一标签、`5825` 次命中，类别数量少但标签密度高，饼图会失真。

前端 tab 交互复用现有 `role=tab` / `aria-controls` / `hidden` 模式，不新增第二套交互范式。

- [ ] **Step 4: 跑测试确认通过**

Run:

```bash
python -m unittest tests.test_yuntu_report -v
```

Expected: 02 章同时切换 AI 结论和图表，移动端和桌面端都保持一致。

### Task 4: 真实批次验证和收尾清理

**Files:**
- Regenerate: `RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict/diagnostic-analysis/yuntu-analysis-prompt.md`
- Regenerate: `RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict/final-report/final-report.md`
- Regenerate: `RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict/final-report/final-report.html`

- [ ] **Step 1: 用现有真实批次重渲染，不重跑 RPA**

使用现有 `diagnostic-analysis/yuntu-analysis-data.json` 和现有 `yuntu-ai-analysis.json` / 或新生成的符合 chapter02 新合同的 AI JSON，重新渲染最终报告。不要重新执行 RPA 抓取。

- [ ] **Step 2: 检查真实产物**

确认：

1. 02 章标题变成 `02｜人群及营销卖点洞察`。
2. 02 章有全量 + 品牌 tabs。
3. 01 章不再出现 people / marketing 相关重复结论。
4. `final-report.md`、`final-report.html`、`final-report-data.json` 中的 scope、品牌名和图表数据一致。

- [ ] **Step 3: 跑完整回归**

Run:

```bash
python -m unittest discover -s tests -v
python -m py_compile scripts/*.py
git diff --check
```

Expected: 全量测试通过，代码编译通过，差异无空白错误。

### Self-Review Checklist

- [ ] `chapter02Facts` 同时覆盖全量和品牌 scope。
- [ ] 02 章 AI 输出同时覆盖人群和营销卖点。
- [ ] 02 章 tab 同时切换 AI 结论和下方汇总图表。
- [ ] 01 章已删除 people / marketing 重复内容。
- [ ] 真实批次验证不重跑 RPA。
