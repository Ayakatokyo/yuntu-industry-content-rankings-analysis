# 云图报告渐进式渲染器拆分 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Functionize the five Yuntu report section renderers inside `yuntu_report.py` while preserving byte-identical generated HTML.

**Architecture:** `_render_html()` remains the orchestration boundary. Each extracted renderer returns one existing HTML fragment and receives only the values already computed by `_render_html()`. No template, CSS, JavaScript, or input-contract changes occur in this phase.

**Tech Stack:** Python standard library, unittest, existing RPA report renderer.

---

### Task 1: Capture the pre-change report baseline

**Files:**
- Test: `tests/test_yuntu_report.py`
- Verify: temporary fixture and real-data report directories under `/tmp`

- [ ] **Step 1: Add a deterministic HTML digest helper test fixture**

Use the existing test module render helpers to render the fixture report and expose a SHA-256 calculation with `hashlib.sha256(html.encode()).hexdigest()`. Do not change production behavior.

- [ ] **Step 2: Generate and record the real-data baseline**

Run the existing `rpa_connector.py render-report` command with the user-provided analysis, fact pack, and provenance files into a new `/tmp` directory. Record the HTML SHA-256 without modifying the source batch directory.

- [ ] **Step 3: Run the existing test suite**

Run `python -m unittest tests.test_yuntu_report -v` and require all current tests to pass before extraction.

### Task 2: Extract the first two section renderers

**Files:**
- Modify: `scripts/yuntu_report.py:875-1568`
- Test: `tests/test_yuntu_report.py`

- [ ] **Step 1: Add source-structure regression tests**

Assert that `_render_html()` calls named render helpers for TOP 素材组合 and 人群洞察, and that those helpers exist in the module source. The tests must not assert CSS, JS, or new DOM strings.

- [ ] **Step 2: Extract `render_top_material_combination(...)`**

Move only the existing `top_material_combination_cards` invocation and its surrounding result assignment into a helper. Pass the existing `analysis`, `fact_pack`, `facts`, `esc`, `source_label`, and `scope_badge` values as needed. Return the exact previous fragment.

- [ ] **Step 3: Extract `render_audience_insights(...)`**

Move only the existing `audience_dashboard_cards(fact_pack.get("audienceDashboard"))` assignment into a helper. Keep the nested chart helper and all generated strings unchanged.

- [ ] **Step 4: Run tests and compare fixture HTML bytes**

Run `python -m unittest tests.test_yuntu_report -v`, then render the fixture twice and compare SHA-256 values. Expected: identical output.

### Task 3: Extract the remaining three section renderers

**Files:**
- Modify: `scripts/yuntu_report.py:875-1568`
- Test: `tests/test_yuntu_report.py`

- [ ] **Step 1: Extract `render_script_insights(...)`**

Move the existing `script_insights = (...)` assembly into a helper without editing its HTML literal or source-label arguments.

- [ ] **Step 2: Extract `render_highlight_insights(...)`**

Move the existing `highlight_insights = highlight_insights_cards()` call into a helper. Keep all nested frame-label and card functions in the same lexical scope until byte equality is proven.

- [ ] **Step 3: Extract `render_material_deep_dive(...)`**

Move the existing `material_deep_dive = material_deep_dive_cards()` call into a helper. Do not change deep-dive HTML, frame ordering, or inline style strings.

- [ ] **Step 4: Run full tests and fixture digest comparison**

Run `python -m unittest tests.test_yuntu_report -v`, `python -m py_compile scripts/yuntu_report.py`, `node --check assets/report/unified-report.js`, and `git diff --check`. Fixture output SHA must remain unchanged.

### Task 4: Verify the real report and desktop structure

**Files:**
- Verify: `scripts/yuntu_report.py`, `tests/test_yuntu_report.py`, temporary `/tmp` report output

- [ ] **Step 1: Regenerate the user-provided real report into a fresh `/tmp` directory**

Use the same `render-report` command and never overwrite the original RPA batch.

- [ ] **Step 2: Compare real-report structural counts and digest**

Confirm five current sections, the expected audience and material deep-dive roots, and no unresolved template placeholders.

- [ ] **Step 3: Observe the report in the desktop browser**

Serve only the temporary report directory locally, inspect the rendered page at the desktop viewport, verify no horizontal overflow, confirm audience columns are still side by side and the deep-dive root is still grid, then close the tab and stop the server.

