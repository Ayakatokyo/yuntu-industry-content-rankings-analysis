# 云图第三章脚本洞察前端样式重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 严格参考千川报告，将云图第三章重排为 AI 双维结论、左中右关键词洞察和可钻取内容公式图表。

**Architecture:** 保持现有 `chapter03.scriptDashboard` 事实和投影不变；由 `render_script_insights` 输出稳定展示骨架，模板 JS 负责公式一级/二级钻取，云图专属 CSS 负责千川风格的卡片层级和响应式布局。

**Tech Stack:** Python 3、pytest、原生 HTML/CSS/JavaScript、现有 unified report tokens。

**Spec:** `docs/superpowers/specs/2026-09-04-yuntu-script-insights-report-ui-polish-design.md`

## Global Constraints

- 不修改云图事实包、AI 提示词、CSV 解析、连接器和第五章数据语义。
- 标题/画面原文不作为 AI 分析维度；规范化内容公式标签仍用于图表。
- 前端只消费 `chapter03.scriptDashboard`，不从其他章节拼接结论。
- 关键词频次和排序使用后端确定性数据，不由 JavaScript 或 AI 重算。
- 不新增颜色体系、外部前端依赖或持久化字段。

### Task 1: 建立千川视觉基线与当前 HTML 回归

**Files:**
- Read: `/Users/shuzida/Desktop/FDE客户/小仙炖/qianchuan-video-peak-frames/templates/final-report-template.html`
- Read: `/Users/shuzida/Desktop/FDE客户/小仙炖/qianchuan-video-peak-frames/assets/report/unified-report.css`
- Modify: `tests/test_yuntu_report.py`

**Interfaces:**
- Consumes: 当前云图报告模板和 `chapter03.scriptDashboard` fixture。
- Produces: 可失败的结构断言，锁定后续 CSS/HTML 重构的验收边界。

- [ ] **Step 1: Write failing structure tests**

```python
def test_chapter03_uses_qianchuan_order_and_three_column_mounts():
    html = render_script_insights(
        script_facts=script_facts,
        script_insights=script_insights,
        script_dashboard=script_dashboard,
    )
    assert html.index('class="script-ai-insights"') < html.index('class="script-keyword-triad"')
    assert html.index('class="script-keyword-triad"') < html.index('class="script-formula-dimension"')
    assert html.count('class="script-material"') == 0
```

- [ ] **Step 2: Run focused test to verify failure**

Run: `pytest tests/test_yuntu_report.py -k "qianchuan_order_and_three_column" -v`

Expected: FAIL because the current renderer does not expose the new structural classes and still repeats material details.

- [ ] **Step 3: Record the reference contract**

Compare the generated cloud report with the Qianchuan ZIP/template and document in test comments the expected order: AI cards, keyword triad, formula dashboard. Keep assertions on semantic class names and text, not pixel values.

- [ ] **Step 4: Commit the failing-test baseline**

```bash
git add tests/test_yuntu_report.py
git commit -m "test: lock chapter03 visual structure baseline"
```

### Task 2: Rebuild the server-rendered Chapter 03 skeleton

**Files:**
- Modify: `scripts/yuntu_report_sections.py:render_script_insights`
- Modify: `tests/test_yuntu_report.py`

**Interfaces:**
- Consumes: `script_facts`, `script_insights`, `script_dashboard`.
- Produces: `.script-ai-insights`, `.script-keyword-triad`, `.script-formula-dimension`, `[data-script-formula]` mount points.

- [ ] **Step 1: Implement semantic markup for AI and triad**

Render two AI cards from `script_insights` with a dimension badge, title, conclusion and low-emphasis evidence line. Render the keyword triad from `dashboard.conclusion`, `dashboard.keywords` and `dashboard.sellingPoints`; keep text escaped and cap keyword/selling-point loops at 24/4.

- [ ] **Step 2: Remove duplicate Chapter 03 material detail markup**

Keep coverage and timestamp boundary notes, but remove the per-material script text, formula, creative breakdown and copy controls from this function. Chapter 05 remains the owner of single-material details.

- [ ] **Step 3: Run focused tests**

Run: `pytest tests/test_yuntu_report.py -k "qianchuan_order_and_three_column" -v`

Expected: PASS for semantic order, three mounts and no `.script-material` nodes.

- [ ] **Step 4: Commit**

```bash
git add scripts/yuntu_report_sections.py tests/test_yuntu_report.py
git commit -m "feat: align chapter03 markup with qianchuan structure"
```

### Task 3: Polish formula chart and drilldown behavior

**Files:**
- Modify: `scripts/templates/final-report-template.html`（`data-script-formula` script）
- Modify: `tests/test_yuntu_report.py`

**Interfaces:**
- Consumes: `dashboard.dimensions.contentFormula.primary` and `.secondary`.
- Produces: accessible level-1 buttons, level-2 drilldown, return focus behavior.

- [ ] **Step 1: Write failing interaction checks**

```python
def test_formula_dashboard_has_keyboard_and_drilldown_contract():
    template = Path("scripts/templates/final-report-template.html").read_text(encoding="utf-8")
    assert "data-script-formula-primary" in template
    assert "返回一级标签总览" in template
    assert "prefers-reduced-motion" in template
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_yuntu_report.py -k "keyboard_and_drilldown_contract" -v`

Expected: FAIL if current script lacks any required accessibility or reduced-motion branch.

- [ ] **Step 3: Implement the minimal interaction changes**

Keep the current `primary`/`secondary` payload. Add explicit `aria-controls`/`aria-live` labels, record the clicked primary button before rendering drilldown, restore focus on return, and skip transition classes when `window.matchMedia('(prefers-reduced-motion: reduce)').matches`.

- [ ] **Step 4: Run focused checks and commit**

Run: `pytest tests/test_yuntu_report.py -k "keyboard_and_drilldown_contract" -v`

Expected: PASS.

```bash
git add scripts/templates/final-report-template.html tests/test_yuntu_report.py
git commit -m "feat: improve chapter03 formula drilldown accessibility"
```

### Task 4: Apply Qianchuan-aligned CSS and responsive layout

**Files:**
- Modify: `assets/report/unified-report.css`
- Modify: `tests/test_yuntu_report.py`

**Interfaces:**
- Consumes: semantic classes from Task 2 and DOM states from Task 3.
- Produces: desktop two-column AI cards, desktop left/middle/right keyword triad, responsive 2/1-column fallbacks and consistent formula chart visuals.

- [ ] **Step 1: Write failing CSS contract checks**

```python
def test_chapter03_css_defines_qianchuan_layout_breakpoints():
    css = Path("assets/report/unified-report.css").read_text(encoding="utf-8")
    assert ".script-keyword-triad" in css
    assert "grid-template-columns: repeat(3, minmax(0, 1fr))" in css
    assert "@media (max-width: 759px)" in css
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_yuntu_report.py -k "qianchuan_layout_breakpoints" -v`

Expected: FAIL until the new scoped rules are present.

- [ ] **Step 3: Add scoped CSS**

Under `.unified-yuntu`, add shared card tokens, AI two-column grid, keyword triad three-column grid, fixed keyword font range, equal-height empty states, formula chart gridlines and drilldown layout. Add 960px/759px media rules; keep existing Chapter 02 marketing rules untouched.

- [ ] **Step 4: Run focused CSS checks**

Run: `pytest tests/test_yuntu_report.py -k "qianchuan_layout_breakpoints" -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add assets/report/unified-report.css tests/test_yuntu_report.py
git commit -m "style: polish chapter03 qianchuan-aligned layout"
```

### Task 5: End-to-end visual and regression verification

**Files:**
- Modify: `tests/test_yuntu_report.py` only for fixture assertions discovered during verification.

- [ ] **Step 1: Run all tests**

Run: `pytest -q`

Expected: all existing tests and new Chapter 03 assertions pass.

- [ ] **Step 2: Generate a real report from the supplied CSV-derived run**

Use the existing report generation command against the current CSV-backed run and inspect the resulting `final-report.html`. Confirm the third chapter contains no title/visual-text AI dimension, no Chapter 03 single-material duplication, and no changes to Chapters 04/05.

- [ ] **Step 3: Perform desktop/mobile inspection**

Inspect at desktop width (AI two columns, keyword left/middle/right, full-width formula chart) and at 759px or narrower (single-column order, readable labels, no clipping). Activate a primary formula bar with mouse and keyboard, drill down, return, and verify focus.

- [ ] **Step 4: Commit any test-only alignment**

```bash
git add tests/test_yuntu_report.py
git commit -m "test: verify chapter03 visual regression"
```
