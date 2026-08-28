# 云图第四章品牌分层与高光帧导出实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or **superpowers:executing-plans** to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enhance Chapter 04 visual classification, add brand-first filtering, and export filtered available highlight frames to XLSX without changing Chapters 01, 02, or 05 contracts.

**Architecture:** Keep the existing highlight fact pack and model-authored common-pattern/direction fields. Add deterministic title-based brand metadata around the existing portrait/product/other classification, project a brand-first Presentation tree, render nested tabs and filters, and pre-generate one filtered Excel table during report rendering for static download.

**Tech Stack:** Python 3 standard library, JSON Schema, unittest, static HTML/CSS/vanilla JavaScript, bundled `@oai/artifact-tool` for workbook authoring.

**Spec:** `docs/superpowers/specs/2026-08-28-yuntu-chapter04-brand-filter-export-design.md`

## Global Constraints

- Use the real batch `RPA数据汇总/yuntu-rankings-analysis-20260826-top6`.
- Do not change Chapter 01 or Chapter 02 visible structure, facts, or copy contracts.
- Do not move Chapter 05 frame observations or second-level observations into Chapter 04.
- Only `available=true` local JPEG frames can be classified, rendered, or exported.
- Every available frame is classified exactly once by one brand and one visual category.
- Visual categories are `portrait`, `product`, and `other`; legacy aliases may be accepted only for backward-compatible reads.
- Common-pattern and derivative-direction field names and ordering remain unchanged.
- Excel output uses the bundled artifact runtime, not `openpyxl`, `xlsxwriter`, or `pandas.ExcelWriter`.

---

### Task 1: Add failing tests for brand projection, nested tabs, and workbook rows

**Files:**
- Modify: `tests/test_yuntu_presentation.py`
- Modify: `tests/test_yuntu_report.py`
- Create: `tests/test_yuntu_highlight_export.py`

**Interfaces:**
- `build_yuntu_presentation()` produces `chapters.chapter04.brands`.
- A pure export-row helper returns one row per available frame with brand/category/card metadata.

- [ ] **Step 1: Write the failing tests**

Add tests asserting that a chapter04 projection has brand tabs containing category tabs, an available frame is assigned to the title-matched brand, HTML contains nested brand/category controls, and export rows contain the requested fields while excluding unavailable frames.

- [ ] **Step 2: Run focused tests**

Run: `python -m unittest tests.test_yuntu_presentation tests.test_yuntu_report tests.test_yuntu_highlight_export -v`

Expected: FAIL because chapter04 has no `brands` projection, nested controls, or export-row helper.

### Task 2: Implement deterministic brand metadata and model classification contract

**Files:**
- Modify: `scripts/yuntu_analysis.py:374-480,517-524`
- Modify: `prompts/yuntu-analysis-prompt.md:27-29`
- Modify: `scripts/yuntu_report.py:614-682`
- Modify: `scripts/yuntu_presentation.py:12,325-353`

**Interfaces:**
- Add a deterministic helper that receives a title and ordered brand list and returns the single matching brand or `other`.
- Include `brand` in model visual assets and projected frames.
- Validate brand/category uniqueness and complete coverage.

- [ ] **Step 1: Write minimal implementation**

Compute brand from the title in Python, include it in `visualAssets`, require the model prompt to classify only visual type and cite visible evidence, and project `chapter04.brands` while preserving `commonConclusion` and `derivativeDirections`.

- [ ] **Step 2: Run focused tests**

Run: `python -m unittest tests.test_yuntu_presentation tests.test_yuntu_report tests.test_yuntu_analysis -v`

Expected: PASS for new brand metadata and existing chapter contracts.

### Task 3: Render brand-first filters and export controls

**Files:**
- Modify: `scripts/yuntu_report_sections.py:353-405`
- Modify: `scripts/yuntu_report.py:871-1148`
- Modify: `scripts/templates/final-report-template.html`
- Modify: `assets/report/unified-report.js`
- Modify: `assets/report/unified-report.css`

**Interfaces:**
- `render_highlight_insights()` accepts the projected brand-first chapter and renders brand/category controls.
- A report-generation helper writes one `.xlsx` artifact and returns its relative download path.

- [ ] **Step 1: Implement nested rendering**

Render a brand tab row above category tabs, scope panels/cards by `data-highlight-brand` and `data-highlight-category`, preserve existing card metadata and pagination, and keep the existing material jump behavior.

- [ ] **Step 2: Implement static XLSX export**

Use the bundled artifact runtime in a conversation-local Node builder invoked by report generation to create one worksheet named `高光帧资产`, with typed seconds/click index and text metadata. Add an Excel table with autofilter over brand and visual type, then place a download link in the HTML. Export only available frames.

- [ ] **Step 3: Run focused render/export tests**

Run: `python -m unittest tests.test_yuntu_report tests.test_yuntu_highlight_export -v` and `node --check assets/report/unified-report.js`.

### Task 4: Regenerate the real report and verify end-to-end

**Files:**
- Modify only generated files under `RPA数据汇总/yuntu-rankings-analysis-20260826-top6/diagnostic-analysis-chapter02-v2` and `final-report-chapter02-v2` if regeneration is required.

- [ ] **Step 1: Run the complete test suite**

Run: `python -m unittest discover -s tests -p 'test_*.py'`.

- [ ] **Step 2: Run syntax and diff checks**

Run: `python -m compileall -q scripts tests && node --check assets/report/unified-report.js && git diff --check`.

- [ ] **Step 3: Render the real report**

Use the existing analysis JSON and real fact pack, run analysis attestation and report rendering without RPA recollection, then inspect generated HTML for brand/type controls, 28 available frame rows, and the export control.

- [ ] **Step 4: Verify workbook output**

Create one workbook with the bundled artifact runtime, inspect the key table range and scan for formula errors, render the sheet once, and save the final `.xlsx` under the conversation output directory.
