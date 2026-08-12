# Yuntu Highlight Insights Phase 04 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `04｜高光画面洞察` classify each available cover frame and up to five click-index local-peak frames per material, then render them in a desktop 6x2, 12-item paginated overview without changing the 05 deep-dive frame set or layout.

**Architecture:** Keep the existing normalized `highlightFrames` as the common extraction output. The 04 overview validates, classifies and renders all available cover and click-peak frames; cover frames do not consume the five click-peak slots. The 05 deep-dive continues consuming its complete independent frame set. Rendered HTML declares its own page size, and the shared JavaScript reads that declaration rather than duplicating a constant.

**Tech Stack:** Python 3 standard library, `unittest`, static HTML, CSS and vanilla JavaScript.

---

### Task 1: Make the overview data contract include classified covers and click peaks

**Files:**
- Modify: `tests/test_yuntu_report.py`
- Modify: `scripts/yuntu_report.py`

- [ ] **Step 1: Write the failing test**

```python
def test_render_report_classifies_cover_and_click_peak_frames_in_highlight_dashboard(self):
    # Include cover and click-peak frames in selected materials.
    # The dashboard classifies every available overview frame.
    # Assert rendering succeeds and 04 labels both frame types correctly.
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `python -m unittest tests.test_yuntu_report.YuntuReportTests.test_render_report_uses_only_click_peak_frames_for_highlight_dashboard`

Expected: FAIL because the old overview contract excludes covers or does not render their distinct label.

- [ ] **Step 3: Write the minimal implementation**

```python
def _overview_highlight_frames(fact_pack):
    return _available_highlight_frames(fact_pack)
```

Use this helper in 04 dashboard validation, markdown and HTML rendering. Label covers as `封面画面` and peaks as `点击 TopN 波峰画面`. Keep `_material_frames()` and 05 unchanged.

- [ ] **Step 4: Run the focused test to verify it passes**

Run: `python -m unittest tests.test_yuntu_report.YuntuReportTests.test_render_report_classifies_cover_and_click_peak_frames_in_highlight_dashboard`

Expected: PASS.

### Task 2: Render a 12-card overview page with the required card copy

**Files:**
- Modify: `tests/test_yuntu_report.py`
- Modify: `scripts/yuntu_report.py`
- Modify: `scripts/templates/final-report-template.html`
- Modify: `assets/report/unified-report.js`
- Modify: `assets/report/unified-report.css`

- [ ] **Step 1: Write the failing test**

```python
def test_render_report_uses_twelve_card_highlight_pages_and_peak_card_copy(self):
    # Supply 13 click-peak JPEGs and assert 12-item pages, two pages,
    # the full extension-free title, "点击 TopN 波峰画面", and click index copy.
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `python -m unittest tests.test_yuntu_report.YuntuReportTests.test_render_report_uses_twelve_card_highlight_pages_and_peak_card_copy`

Expected: FAIL because the renderer declares 10 items per page and the card label is `峰值帧`.

- [ ] **Step 3: Write the minimal implementation**

Set `data-highlight-page-size="12"`; compute page status using 12; render the extension-free material title, `点击 Top{peak_rank} 波峰画面`, and `{second}s · 点击指数 {value}`. Make both inline-template and external JavaScript read `data-highlight-page-size`, falling back to 12.

- [ ] **Step 4: Run the focused test to verify it passes**

Run: `python -m unittest tests.test_yuntu_report.YuntuReportTests.test_render_report_uses_twelve_card_highlight_pages_and_peak_card_copy`

Expected: PASS.

### Task 3: Make the overview grid stable and responsive without altering 05

**Files:**
- Modify: `tests/test_yuntu_report.py`
- Modify: `assets/report/unified-report.css`

- [ ] **Step 1: Write the failing test**

```python
def test_unified_report_uses_six_by_two_overview_grid_without_changing_deep_dive_grid(self):
    css = (ROOT / "assets" / "report" / "unified-report.css").read_text(encoding="utf-8")
    self.assertIn("grid-template-columns: repeat(6, minmax(0, 1fr));", css)
    self.assertIn("grid-template-rows: repeat(2, minmax(0, 1fr));", css)
    self.assertIn(".unified-yuntu .deep-frame-grid.fixed-six", css)
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `python -m unittest tests.test_yuntu_report.YuntuReportTests.test_unified_report_uses_six_by_two_overview_grid_without_changing_deep_dive_grid`

Expected: FAIL because the overview grid is five columns.

- [ ] **Step 3: Write the minimal implementation**

Use six columns and two rows on desktop. Reserve two-row grid height so an incomplete page retains the intended grid geometry. Scope every selector to `.highlight-frame-grid`; leave `.deep-frame-grid.fixed-six` untouched. Tablet and mobile adaptation are out of scope for subsequent optimization.

- [ ] **Step 4: Run the focused test to verify it passes**

Run: `python -m unittest tests.test_yuntu_report.YuntuReportTests.test_unified_report_uses_six_by_two_overview_grid_without_changing_deep_dive_grid`

Expected: PASS.

### Task 4: Verify the complete report chain

**Files:**
- No production changes expected.

- [ ] **Step 1: Run focused report and highlight tests**

Run: `python -m unittest tests.test_yuntu_report tests.test_yuntu_highlights -q`

Expected: all tests pass.

- [ ] **Step 2: Run full project unit suite and syntax checks**

Run:

```bash
python -m unittest tests.test_yuntu_top_materials tests.test_yuntu_analysis tests.test_yuntu_report tests.test_yuntu_highlights -q
python -m py_compile scripts/yuntu_report.py scripts/yuntu_highlights.py
node --check assets/report/unified-report.js
git diff --check
```

Expected: all commands exit 0.
