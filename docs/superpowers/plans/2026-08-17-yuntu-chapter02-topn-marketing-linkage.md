# 云图第 02 章 Top N 营销卖点联动 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让每个第 02 章 scope 的 Top N 控件同步重算人群图表和营销卖点汇总。

**Architecture:** 使用已嵌入 `data-audience-records` 的按排名素材记录。模板脚本新增基于素材列表的营销分类函数；`renderAudienceTopN` 在刷新人群图表后调用营销总览渲染，并清除旧类别下钻状态。

**Tech Stack:** Python 3、HTML 模板内联 JavaScript、`unittest`、既有报告渲染 CLI。

---

### Task 1: 用失败测试固化联动契约

**Files:**
- Modify: `tests/test_yuntu_report.py:639-644`
- Modify: `scripts/templates/final-report-template.html:626-780`

- [ ] **Step 1: 写出失败测试**

在 `test_render_report_writes_audience_dashboard_from_fact_pack` 中追加：

```python
self.assertIn("function computeMarketingCategories(selectedRecords)", html)
self.assertIn("renderMarketingOverview(computeMarketingCategories(selected))", html)
self.assertIn("renderAudienceTopN(records.length);", html)
```

- [ ] **Step 2: 验证测试失败**

Run:

```bash
python3 -m unittest tests.test_yuntu_report.YuntuReportTests.test_render_report_writes_audience_dashboard_from_fact_pack -v
```

Expected: FAIL，因为模板中尚无基于 Top N 素材重算营销类别的函数和调用。

- [ ] **Step 3: 实现最小联动代码**

将营销初始化逻辑改为读取同一 `audience-dashboard` 的 `data-audience-records`。新增：

```javascript
function computeMarketingCategories(selectedRecords) {
  // 从 selectedRecords 的 material_tags 重新统计营销一级类别和标签计数。
}
```

使营销总览函数接受类别数组，并在 `renderAudienceTopN(topn)` 中派发当前素材集：

```javascript
dashboard.dispatchEvent(new CustomEvent('audience-topn-change', { detail: { records: selected } }));
```

类别划分沿用服务端 `build_marketing_dashboard` 的规则；每次更新均替换当前下钻视图为总览。

- [ ] **Step 4: 验证测试通过**

Run:

```bash
python3 -m unittest tests.test_yuntu_report.YuntuReportTests.test_render_report_writes_audience_dashboard_from_fact_pack -v
```

Expected: PASS。

### Task 2: 重渲染严格批次并验收

**Files:**
- Modify: `RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict/final-report/final-report.html`
- Modify: `RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict/final-report/final-report-data.json`
- Modify: `RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict/final-report/presentation-report.json`

- [ ] **Step 1: 使用正式渲染链路重建成品**

Run:

```bash
python3 scripts/rpa_connector.py render-report --analysis-json 'RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict/diagnostic-analysis/yuntu-ai-analysis.json' --fact-pack-json 'RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict/diagnostic-analysis/yuntu-analysis-data.json' --analysis-provenance 'RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict/diagnostic-analysis/yuntu-ai-analysis.provenance.json' --output-dir 'RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict/final-report' --highlight-asset-root 'RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict'
```

Expected: exit code 0，且不调用 RPA。

- [ ] **Step 2: 验证联动逻辑已嵌入成品**

Run:

```bash
node -e "const h=require('fs').readFileSync('RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict/final-report/final-report.html','utf8'); if(!h.includes('function computeMarketingCategories(selectedRecords)')||!h.includes(\"addEventListener('audience-topn-change'\")) process.exit(1); console.log('chapter02 marketing linkage is embedded')"
```

Expected: `chapter02 marketing linkage is embedded`。

- [ ] **Step 3: 运行完整回归和静态检查**

Run:

```bash
python3 -m unittest discover -s tests -q
python3 -m py_compile scripts/yuntu_presentation.py scripts/yuntu_report_sections.py scripts/yuntu_report.py
git diff --check
```

Expected: 全部通过且没有空白差异错误。

- [ ] **Step 4: Commit**

```bash
git add scripts/templates/final-report-template.html tests/test_yuntu_report.py docs/superpowers/plans/2026-08-17-yuntu-chapter02-topn-marketing-linkage.md
git commit -m "feat: link chapter02 marketing dashboard to topn"
```
