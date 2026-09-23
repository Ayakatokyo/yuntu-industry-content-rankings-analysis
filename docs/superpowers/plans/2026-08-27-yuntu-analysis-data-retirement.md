# Yuntu Analysis Data Retirement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop writing `yuntu-analysis-data.json` for new analysis runs while preserving historical rendering compatibility.

**Architecture:** Keep the complete derived fact object in memory during `prepare-analysis`, then persist only the report projection and four model unit inputs. Keep the renderer's existing fallback to a historical complete snapshot when `report-data.json` is absent.

**Tech Stack:** Python 3, `unittest`, JSON CLI workflow.

---

### Task 1: Stop Persisting The Complete Snapshot

**Files:**
- Modify: `scripts/yuntu_analysis.py`
- Test: `tests/test_yuntu_analysis.py`

- [x] Add a failing test proving a successful preparation does not create `yuntu-analysis-data.json` and still creates all current outputs.
- [x] Run the focused test and confirm it fails because the legacy snapshot exists.
- [x] Remove the complete snapshot write.
- [x] Migrate preparation tests to assert against `report-data.json` and the owning analysis unit.
- [x] Run `tests.test_yuntu_analysis` and confirm it passes.

### Task 2: Update Workflow Contracts

**Files:**
- Modify: `SKILL.md`
- Modify: `tests/test_skill_contract.py`

- [x] Replace the current-snapshot language with a historical-compatibility statement.
- [x] Assert that the new output inventory excludes `diagnostic-analysis/yuntu-analysis-data.json` and documents the fallback.
- [x] Run skill contract tests.

### Task 3: Verify New And Historical CLI Paths

**Files:**
- Test: `tests/test_rpa_connector.py`

- [x] Confirm default rendering uses `report-data.json` without a complete snapshot.
- [x] Confirm a historical directory containing only `yuntu-analysis-data.json` still renders through the fallback.
- [x] Run connector and report tests.

### Task 4: Fixed Real-Batch Regression

**Artifacts:**
- Input: `RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-top10`
- Output: a new system temporary directory

- [x] Run `prepare-analysis` and prove no complete snapshot exists.
- [x] Have the current conversation model read all four units and view every available local JPEG.
- [x] Confirm the four unit inputs are byte-identical to the prior current-dialog run, then reuse its four-field model output without programmatic conclusions.
- [x] Run `attest-analysis` and `render-report`.
- [x] Verify material coverage, frame coverage, output files, presentation schema, and ZIP boundary.

### Task 5: Final Verification

- [x] Run all unit tests.
- [x] Run Python compilation.
- [x] Run `git diff --check`.
- [x] Review the final diff and report the historical compatibility boundary.
