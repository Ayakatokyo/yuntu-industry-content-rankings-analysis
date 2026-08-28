# 第五章字段收敛 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove redundant Chapter 05 model-input and presentation fields while preserving the rendered report contract.

**Architecture:** Keep the combined report fact pack backward-compatible. Slim only the Chapter 05 analysis unit and project Chapter 05 frames from a minimal field set; keep HTML behavior driven by `chapters.chapter05.panels`.

**Tech Stack:** Python 3, JSON projections, HTML renderer, unittest.

**Spec:** `docs/superpowers/specs/2026-08-28-yuntu-chapter05-field-dedup-design.md`

## Global Constraints

- Do not alter Chapter 01, Chapter 02, or Chapter 04 fact semantics.
- Keep `materialDeepDives` output fields unchanged.
- Preserve historical renderer fallbacks where they are outside the new Chapter 05 projection.

### Task 1: Add failing contract tests

**Files:**
- Modify: `tests/test_yuntu_analysis.py`
- Modify: `tests/test_yuntu_presentation.py`
- Modify: `tests/test_yuntu_report.py`

- [ ] **Step 1: Add model-input projection assertions**

Assert the generated `material-deep-dive-input.json` keeps `material_id`, `highlightFrames`, and `secondLevelBreakdown`, while omitting the listed redundant fields and frame metadata.

- [ ] **Step 2: Add Presentation dedup assertions**

Assert top-level `materials` is absent, `chapter05.materialTabs` matches the interaction items, and Chapter 05 frame cards contain no `materialId`, `rank`, `title`, or `caption`.

- [ ] **Step 3: Run focused tests and confirm they fail**

Run: `python -m unittest tests.test_yuntu_analysis tests.test_yuntu_presentation tests.test_yuntu_report -q`

Expected: failures identify the currently emitted redundant fields.

### Task 2: Implement the minimal projections

**Files:**
- Modify: `scripts/yuntu_analysis.py`
- Modify: `scripts/yuntu_presentation.py`
- Modify: `prompts/yuntu-analysis-prompt.md`

- [ ] **Step 1: Slim `_model_material_facts`**

Emit only the fields listed in the spec and normalize frame `image_path` from the existing relative path without copying presentation-only metadata.

- [ ] **Step 2: Add a Chapter 05 frame-card projection**

Project only `frameRef`, `available`, `relativePath`, `second`, `frameType`, `peakRank`, and `clickValue` for Chapter 05 panels.

- [ ] **Step 3: Remove the dead top-level `materials` alias**

Keep `chapter05.panels`, `materialTabs`, and the interaction declaration generated from one tabs list.

- [ ] **Step 4: Clarify Prompt input boundary**

Document the reduced material-deep-dive evidence fields and explicitly prohibit reintroducing report/UI fields into `materialDeepDives`.

### Task 3: Verify behavior and artifacts

**Files:**
- Verify: generated Chapter 05 analysis unit and report artifacts under the current batch.

- [ ] **Step 1: Run focused tests**

Run: `python -m unittest tests.test_yuntu_analysis tests.test_yuntu_presentation tests.test_yuntu_report -q`

- [ ] **Step 2: Run static checks**

Run: `python -m compileall -q scripts tests` and `git diff --check`.

- [ ] **Step 3: Run the full suite**

Run: `python -m unittest discover -s tests -q`.

- [ ] **Step 4: Inspect a real Chapter 05 projection**

Regenerate only the analysis units into a temporary directory from the current batch and assert the reduced field sets and unchanged `materialDeepDives` schema.
