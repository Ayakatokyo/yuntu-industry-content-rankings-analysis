# Yuntu RPA Compatibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align the skill with the platform RPA connector contract without changing the existing analysis workflow.

**Architecture:** Keep the current connector entrypoint and batch workflow intact. Relax only the multi-value validation layer, add a targeted rejected-detail retry path in `yuntu_batch.py`, then align the skill docs to the platform-style knowledge layout with local `references/` files.

**Tech Stack:** Python 3 standard library, `requests`, `unittest`, Markdown docs.

---

### Task 1: Relax Multi-Value Filter Validation

**Files:**
- Modify: `scripts/rpa_connector.py`
- Test: `tests/test_rpa_connector.py`

- [ ] Write and run the failing validation passthrough test.
- [ ] Remove whitelist enforcement for `ages`, `genders`, and `crowd_groups` while preserving structural validation.
- [ ] Re-run `python -m unittest tests.test_rpa_connector.RpaConnectorTest.test_list_validation_normalizes_filters_and_rejects_invalid_values -v`.

### Task 2: Add Rejected-Detail Retry Flow

**Files:**
- Modify: `scripts/yuntu_batch.py`
- Modify: `scripts/rpa_connector.py`
- Test: `tests/test_yuntu_batch.py`

- [ ] Write and run the failing retry test.
- [ ] Implement `retry_failed_batch()` that replays only rejected details and refreshes manifest outputs.
- [ ] Add CLI `retry-failed --shop-id --output-dir`.
- [ ] Re-run the targeted retry test and CLI help assertions.

### Task 3: Align Skill Docs to Platform Structure

**Files:**
- Modify: `SKILL.md`
- Create: `references/platforms/juliang-yt.md`
- Create: `references/connectors/juliang-yt/rpa_conn_juliang_yt_industry_content_rankings_list.md`
- Create: `references/connectors/juliang-yt/rpa_conn_juliang_yt_industry_content_rankings_detail.md`
- Test: `tests/test_skill_contract.py`

- [ ] Update command examples to `<skill-root>`.
- [ ] Add explicit references to the local platform and connector knowledge pages.
- [ ] Document `retry-failed`.
- [ ] Re-run the targeted skill contract tests.

### Task 4: Regression Verification

**Files:**
- Modify only if verification exposes a defect.

- [ ] Run `python -m unittest discover -s tests -v`.
- [ ] Run `python scripts/rpa_connector.py self-test`.
- [ ] Run `python scripts/rpa_connector.py --help`.
