# Yuntu RPA State Guardrails Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Yuntu RPA runs resumable only for the exact same request, observable while running, and safe to deliver as the current two-section report.

**Architecture:** Persist an immutable run contract and lifecycle summary beside the batch manifest. Fetch validates an existing contract before any writes or RPA calls, records list and detail stage counts as artifacts arrive, and exposes a read-only status command. Report rendering validates the two current template sections before and after substitution.

**Tech Stack:** Python 3 standard library, unittest, existing RPA CSV normalization.

---

### Task 1: Protect and Observe RPA Batches

**Files:**
- Modify: `scripts/yuntu_run_state.py`
- Modify: `scripts/yuntu_batch.py`
- Modify: `scripts/rpa_connector.py`
- Test: `tests/test_yuntu_batch.py`
- Test: `tests/test_rpa_connector.py`
- Test: `tests/test_yuntu_run_state.py`

- [x] **Step 1: Write failing tests** for a mismatched existing contract rejecting before list invocation, a same-contract interrupted run reusing its list, persisted detail files appearing in status while the manifest is still running, and CLI `status` output.
- [x] **Step 2: Run the focused tests** and confirm they fail because the contract and status command do not yet exist.
- [x] **Step 3: Implement the minimal lifecycle contract**: persist `run-summary.json` with `runId`, the complete request fingerprint, current status, and artifact paths; read it before overwriting batch state; reject a mismatched or unverifiable directory before RPA; update counts after list normalization and each detail attempt.
- [x] **Step 4: Implement the read-only status command** by combining run summary, manifest, normalized list, detail requests, and detail records without changing the run directory.
- [x] **Step 5: Run focused lifecycle tests** and confirm they pass.

### Task 2: Gate the RPA Data Chain

**Files:**
- Modify: `scripts/yuntu_batch.py`
- Test: `tests/test_yuntu_batch.py`

- [x] **Step 1: Write a failing test** whose normalized list context has a different custom date range and asserts that no detail invocation occurs.
- [x] **Step 2: Run the focused test** and confirm it currently reaches the detail invoker.
- [x] **Step 3: Implement context validation** for industry, custom date range, brand scope, canonicalized brands, and ranking limit when each filter is requested; persist the validation result in the run summary and terminate the batch on mismatch.
- [x] **Step 4: Run the focused context test** and confirm it passes.

### Task 3: Lock the Two-Section Delivery Contract

**Files:**
- Modify: `scripts/yuntu_report.py`
- Modify: `SKILL.md`
- Test: `tests/test_yuntu_report.py`
- Test: `tests/test_skill_contract.py`

- [x] **Step 1: Write failing tests** for a template missing either `top_material_combination` or `audience_insights`, and for output missing either current report section.
- [x] **Step 2: Run the focused tests** and confirm the missing template placeholder is currently accepted.
- [x] **Step 3: Implement a centralized two-section template contract** that validates placeholders and rendered section IDs/titles; keep later analysis fields internal until their report sections are explicitly added.
- [x] **Step 4: Update the skill workflow** with the run status, resume contract, cross-check evidence, report scope, and final delivery gate.
- [x] **Step 5: Run focused report and skill-contract tests**, then the full suite.
