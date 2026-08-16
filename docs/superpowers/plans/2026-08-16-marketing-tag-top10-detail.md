# Marketing Tag Top 10 Detail Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the Chapter 02 marketing drill-down visual design while limiting its pie chart to the ten highest-count secondary tags plus one aggregated tail slice, with an on-demand complete tag table.

**Architecture:** The report template already receives every secondary tag in `category.tags`. Its `renderMarketingDrill` function will derive two view-only collections: the first ten sorted tags and an aggregate tail slice. The full, sorted list remains in memory and is rendered into a hidden detail table only when the report reader chooses to view it.

**Tech Stack:** Python unittest, server-rendered HTML, vanilla JavaScript, CSS.

---

### Task 1: Lock the rendered interaction contract with a regression test

**Files:**
- Modify: `tests/test_yuntu_report.py:614-655`
- Test: `tests/test_yuntu_report.py`

- [ ] **Step 1: Add assertions for the Top 10 and detail-table contract**

```python
self.assertIn("var topTags = tags.slice(0, 10);", html)
self.assertIn("其他 ' + tailTags.length + ' 个标签", html)
self.assertIn("查看全部标签明细", html)
self.assertIn("marketing-tag-detail-table", html)
self.assertIn("marketing-tag-detail-toggle", html)
```

- [ ] **Step 2: Run the focused test and verify it fails because the contract does not exist yet**

Run: `python -m unittest tests.test_yuntu_report.YuntuReportTests.test_render_report_renders_all_and_brand_chapter02_tabs -v`

Expected: `FAIL` with a missing `var topTags = tags.slice(0, 10);` assertion.

### Task 2: Derive Top 10 and aggregate-tail pie slices

**Files:**
- Modify: `scripts/templates/final-report-template.html:675-719`
- Test: `tests/test_yuntu_report.py`

- [ ] **Step 1: Sort the complete tag list and split it at ten entries**

```javascript
var tags = (Array.isArray(category.tags) && category.tags.length ? category.tags : (category.topTags || [])).slice()
  .sort(function (left, right) { return Number(right.count || 0) - Number(left.count || 0); });
var topTags = tags.slice(0, 10);
var tailTags = tags.slice(10);
var total = tags.reduce(function (sum, tag) { return sum + Number(tag.count || 0); }, 0) || 1;
var pieTags = topTags.slice();
if (tailTags.length) {
  pieTags.push({ tag: '其他 ' + tailTags.length + ' 个标签', count: tailTags.reduce(function (sum, tag) { return sum + Number(tag.count || 0); }, 0), isAggregate: true });
}
```

- [ ] **Step 2: Build `slices` from `pieTags`, retaining all-tag totals for percentages**

```javascript
var slices = pieTags.map(function (tag, index) {
  var share = Number(tag.count || 0) / total;
  var slice = { label: tag.tag || '未命名标签', count: Number(tag.count || 0), share: Number((share * 100).toFixed(1)), start: cursor * 360, end: (cursor + share) * 360, color: tag.isAggregate ? '#a28d7d' : colors[index % colors.length] };
  cursor += share;
  return slice;
});
```

- [ ] **Step 3: Run the focused test and verify it passes**

Run: `python -m unittest tests.test_yuntu_report.YuntuReportTests.test_render_report_renders_all_and_brand_chapter02_tabs -v`

Expected: `OK`.

### Task 3: Add an on-demand full tag detail table without altering existing drill-down styling

**Files:**
- Modify: `scripts/templates/final-report-template.html:719-746`
- Modify: `assets/report/unified-report.css:1245-1288`
- Test: `tests/test_yuntu_report.py`

- [ ] **Step 1: Render a button and initially hidden table after the existing pie-and-legend layout**

```javascript
var detailToggle = document.createElement('button');
detailToggle.type = 'button';
detailToggle.className = 'marketing-tag-detail-toggle';
detailToggle.textContent = '查看全部标签明细';
var detailTable = document.createElement('div');
detailTable.className = 'marketing-tag-detail-table';
detailTable.hidden = true;
detailToggle.addEventListener('click', function () {
  detailTable.hidden = !detailTable.hidden;
  detailToggle.textContent = detailTable.hidden ? '查看全部标签明细' : '收起标签明细';
});
```

- [ ] **Step 2: Populate the table with the complete sorted `tags` list**

```javascript
tags.forEach(function (tag) {
  var row = document.createElement('div');
  row.className = 'marketing-tag-detail-row';
  row.append(document.createTextNode(tag.tag || '未命名标签'));
  var value = document.createElement('span');
  value.textContent = Number(tag.count || 0) + ' 次';
  row.append(value);
  detailTable.append(row);
});
```

- [ ] **Step 3: Style only the new control and table using existing report tokens**

```css
.unified-yuntu .marketing-tag-detail-toggle { border: 1px solid var(--unified-line); border-radius: 4px; background: transparent; color: var(--unified-accent-dark); }
.unified-yuntu .marketing-tag-detail-table { margin-top: 14px; border-top: 1px solid var(--unified-line); }
.unified-yuntu .marketing-tag-detail-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 12px; padding: 8px 0; border-bottom: 1px solid rgba(223, 207, 189, .68); }
```

- [ ] **Step 4: Run the focused test and verify it passes**

Run: `python -m unittest tests.test_yuntu_report.YuntuReportTests.test_render_report_renders_all_and_brand_chapter02_tabs -v`

Expected: `OK`.

### Task 4: Render and validate the real strict batch

**Files:**
- Generate: `RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict/final-report/final-report.html`

- [ ] **Step 1: Re-render using the existing strict-batch analysis and fact-pack files**

Run: `python scripts/rpa_connector.py render-report --analysis-json 'RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict/diagnostic-analysis/yuntu-ai-analysis.json' --fact-pack-json 'RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict/diagnostic-analysis/yuntu-analysis-data.json' --analysis-provenance 'RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict/diagnostic-analysis/yuntu-ai-analysis.provenance.json' --output-dir 'RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict/final-report' --highlight-asset-root 'RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict'`

Expected: exit code `0`.

- [ ] **Step 2: Run the complete verification set**

Run: `python -m unittest discover -s tests -v && python -m py_compile scripts/*.py && git diff --check`

Expected: all tests pass, no compilation errors, and no whitespace errors.
