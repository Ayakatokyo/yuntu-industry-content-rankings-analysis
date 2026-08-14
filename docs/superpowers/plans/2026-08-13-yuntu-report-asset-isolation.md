# 云图报告资源隔离 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Yuntu report render from one scoped CSS asset and one JavaScript owner while preserving the existing report data and DOM contract.

**Architecture:** `yuntu_report.py` continues to generate business HTML fragments and package the report. The template becomes a resource-and-section skeleton. `unified-report.css` owns all visual rules and `unified-report.js` owns every browser interaction, including the single highlighter paginator.

**Tech Stack:** Python 3 standard library, `unittest`, static HTML/CSS/JavaScript assets, browser validation of generated HTML.

---

### Task 1: Lock the one-resource ownership contract

**Files:**
- Modify: `tests/test_yuntu_report.py`
- Modify: `scripts/yuntu_report.py:38-51`
- Modify: `scripts/templates/final-report-template.html:1-27`

- [ ] **Step 1: Write failing template and rendered-resource tests**

Add tests that require the template to contain exactly one `$report_style` and `$report_script`, no `$style`, `$unified_style`, `$unified_script`, executable inline script, or `highlight-lightbox` element. Render the fixture report and assert it contains one `data-report-style`, one `data-report-script`, no unresolved `$` placeholders, and no `data-unified-highlight-page`.

- [ ] **Step 2: Run the focused tests and verify the contract fails**

Run: `python -m unittest tests.test_yuntu_report.YuntuReportTests.test_template_uses_single_report_asset_pair tests.test_yuntu_report.YuntuReportTests.test_rendered_report_inlines_single_asset_pair -v`

Expected: FAIL because the current template has three asset placeholders and an inline script.

- [ ] **Step 3: Replace the template asset interface and loader validation**

Replace the two style tags with `<style data-report-style="true">$report_style</style>` and the end-of-body script with `<script data-report-script="true">$report_script</script>`. Remove the template dialog and entire inline script. Update `_load_html_template` to validate the two new placeholders exactly once.

- [ ] **Step 4: Run the focused tests and verify they pass**

Run: `python -m unittest tests.test_yuntu_report.YuntuReportTests.test_template_uses_single_report_asset_pair tests.test_yuntu_report.YuntuReportTests.test_rendered_report_inlines_single_asset_pair -v`

Expected: PASS after Tasks 2 and 3 provide the two substituted values.

### Task 2: Move the cloud-report CSS into the single scoped stylesheet

**Files:**
- Modify: `tests/test_yuntu_report.py`
- Modify: `scripts/yuntu_report.py:1515-1563`
- Modify: `assets/report/unified-report.css`

- [ ] **Step 1: Write a failing style-source test**

Add a test that asserts `_render_html` contains no CSS construction (`style =` or `style +=`) and that `unified-report.css` contains stable selectors from the former report CSS, including `.highlight-frame-grid`, `.material-deep-layout.side-tabs`, and `.audience-dashboard`.

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `python -m unittest tests.test_yuntu_report.YuntuReportTests.test_report_visual_rules_have_one_stylesheet_owner -v`

Expected: FAIL because `_render_html` currently creates `$style` with Python string concatenation.

- [ ] **Step 3: Migrate the complete CSS payload without changing its rule order**

Append the CSS payload currently built in `_render_html` to `unified-report.css`, prefix the migrated rules with the existing `.unified-yuntu` scope where needed, then remove the Python CSS construction. Render substitution must pass the stylesheet contents only as `report_style`.

- [ ] **Step 4: Run the style ownership test and existing rendering tests**

Run: `python -m unittest tests.test_yuntu_report.YuntuReportTests.test_report_visual_rules_have_one_stylesheet_owner tests.test_yuntu_report.YuntuReportTests.test_render_report_uses_the_shared_background_tokens tests.test_yuntu_report.YuntuReportTests.test_unified_report_uses_six_by_two_overview_grid_without_changing_deep_dive_grid -v`

Expected: PASS; generated HTML has the migrated visual rules once.

### Task 3: Make the unified script the only interaction owner

**Files:**
- Modify: `tests/test_yuntu_report.py`
- Modify: `scripts/templates/final-report-template.html`
- Modify: `assets/report/unified-report.js`

- [ ] **Step 1: Write a failing ownership test**

Assert the template has no `paginateHighlightPanel`, `_render_html` output has no `normalizeYuntuHighlightPagination` or `data-unified-highlight-page`, and the script contains one `paginateHighlightPanel` owner using `data-highlight-current-page`.

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `python -m unittest tests.test_yuntu_report.YuntuReportTests.test_highlight_interaction_has_one_script_owner -v`

Expected: FAIL because both template and unified script currently paginate highlighters.

- [ ] **Step 3: Migrate all template behaviors into the unified script**

Move brand tabs, audience charts/drill-down, highlighter category tabs/pagination, collapse controls, material tabs/jump, and the accessible highlight lightbox to `unified-report.js`. Remove the existing duplicate normalization function and static paginator helper. Preserve current data attributes and use `data-highlight-current-page` as the only paginator state.

- [ ] **Step 4: Run interaction ownership and report regression tests**

Run: `python -m unittest tests.test_yuntu_report.YuntuReportTests.test_highlight_interaction_has_one_script_owner tests.test_yuntu_report.YuntuReportTests.test_render_report_uses_twelve_card_highlight_pages_and_peak_card_copy tests.test_yuntu_report.YuntuReportTests.test_render_report_embeds_self_creating_unified_highlight_lightbox tests.test_yuntu_report.YuntuReportTests.test_render_report_uses_accessible_brand_tabs_without_legacy_dialog -v`

Expected: PASS with no duplicate highlighter controller in the rendered HTML.

### Task 4: Verify the isolated renderer and generated report

**Files:**
- Verify: `tests/test_yuntu_report.py`
- Verify: `scripts/yuntu_report.py`
- Verify: generated temporary report directory

- [ ] **Step 1: Run the complete report test suite**

Run: `python -m unittest tests.test_yuntu_report -v`

Expected: PASS with no failures.

- [ ] **Step 2: Generate a fixture report and inspect the final artifact**

Run the existing fixture-based render test or a temporary script using `YuntuReportTests.analysis_json()` and `deep_dive_fact_pack()`. Confirm the final HTML has a single report CSS tag, a single report JS tag, all five current sections, no unresolved placeholders, no `data-unified-highlight-page`, and no template inline script.

- [ ] **Step 3: Browser-check the generated report**

Open the generated HTML only for verification at 1440x1000 and 390x844. Exercise category switching, highlighter next/previous pagination when fixture data spans two pages, material jump, collapse, and lightbox; check for horizontal overflow and abnormal empty areas.

- [ ] **Step 4: Record verification evidence**

Report the exact test command result and browser-observed state. Do not claim completion without this fresh evidence.
