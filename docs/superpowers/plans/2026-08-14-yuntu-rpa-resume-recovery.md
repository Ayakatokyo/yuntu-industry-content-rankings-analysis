# 云图 RPA 中断续跑 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make interrupted Yuntu RPA batches safely resumable without duplicate collection of persisted detail records.

**Architecture:** Preserve and hydrate the existing batch manifest from normalized detail artifacts. Treat submitted-but-unpersisted requests as unresolved, and expose an explicit retry command for them. Keep request execution sequential.

**Tech Stack:** Python standard library, unittest, existing RPA connector CLI.

---

### Task 1: Preserve Successful Detail State

**Files:**
- Modify: `tests/test_yuntu_batch.py`
- Modify: `scripts/yuntu_batch.py`

- [ ] Add a failing test that seeds a valid interrupted batch with one persisted detail and asserts normal `fetch_batch` calls only the missing candidate.
- [ ] Run `python -m unittest tests.test_yuntu_batch.YuntuBatchTests.test_fetch_batch_resume_skips_persisted_detail` and confirm it fails before implementation.
- [ ] Load the old manifest, reconstruct selected records from persisted normalized detail files, and initialize per-group selection counts from the reconstructed state.
- [ ] Run the focused test and then `python -m unittest tests.test_yuntu_batch`.

### Task 2: Make Ambiguous Requests Explicitly Retryable

**Files:**
- Modify: `tests/test_yuntu_batch.py`
- Modify: `scripts/yuntu_batch.py`
- Modify: `scripts/rpa_connector.py`

- [ ] Add a failing test that verifies a submitted-but-unpersisted item is not retried by normal `fetch_batch`, and is stored as unresolved.
- [ ] Add a failing CLI test for `retry-unresolved` if the existing connector test patterns support it.
- [ ] Implement unresolved-state migration and the explicit retry command using the existing retry machinery.
- [ ] Run focused batch and connector tests.

### Task 3: Update Execution Guidance and Candidate Default

**Files:**
- Modify: `tests/test_skill_contract.py`
- Modify: `SKILL.md`
- Modify: `scripts/rpa_connector.py`

- [ ] Add contract assertions for long-task guidance and `retry-unresolved` documentation.
- [ ] Change the default candidate pool to `targetTopN + 2` when the caller does not provide `--candidate-top-n`.
- [ ] Document asynchronous execution, `status` before recovery, and explicit retry semantics.
- [ ] Run all tests with `python -m unittest discover -s tests -v`.
