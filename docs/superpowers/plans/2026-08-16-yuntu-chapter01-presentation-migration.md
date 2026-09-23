# Yuntu Chapter 01 Presentation Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Yuntu Chapter 01 HTML consume a validated `PresentationReport v1` chapter projection.

**Architecture:** Project the existing validated `topMaterialCombination` into `chapters.chapter01`, including user-selected brand Top N metadata and tab interaction. The existing renderer receives this projection, adapts it to its established markup contract, and retains its legacy input branch.

**Tech Stack:** Python standard library, `unittest`, existing HTML renderer.

---

### Task 1: Define a failing Chapter 01 presentation contract

**Files:**
- Modify: `tests/test_yuntu_presentation.py`

- [ ] Add a test asserting `chapter01` contains the executive insight, overall insight, brand panels with Top N and the brand-tab interaction.
- [ ] Run `python -m unittest tests.test_yuntu_presentation.YuntuPresentationTests.test_projects_chapter01_top_material_conclusions -v` and verify it fails.

### Task 2: Project Chapter 01

**Files:**
- Modify: `scripts/yuntu_presentation.py`

- [ ] Add `_project_chapter01(analysis, fact_pack)` that copies validated conclusion text and evidence without recalculation.
- [ ] Include `chapter01` in `SECTION_IDS`, `chapters`, and interaction declarations.
- [ ] Run the focused presentation test and verify it passes.

### Task 3: Consume the projection in the HTML renderer

**Files:**
- Modify: `scripts/yuntu_report.py`
- Modify: `scripts/yuntu_report_sections.py`
- Modify: `tests/test_yuntu_report.py`

- [ ] Add a report test that confirms the Chapter 01 schema is persisted and its existing brand-tab markup remains present.
- [ ] Add an optional `presentation` input to `render_top_material_combination`; when complete, construct its existing internal value only from the chapter projection.
- [ ] Route `presentation.chapters.chapter01` from `_render_html`.
- [ ] Run focused report tests and verify they pass.

### Task 4: Validate production output

**Files:**
- Generated: `RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict/final-report/*`

- [ ] Run all unit tests, compiler check and whitespace check.
- [ ] Re-render the supplied strict batch without re-running RPA.
- [ ] Confirm `presentation-report.json` and HTML contain the Chapter 01 projection and brand tabs.
