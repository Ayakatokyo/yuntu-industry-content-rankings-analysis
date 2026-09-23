# RPA Timeout And Candidate Pool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Limit both RPA request types to five minutes and default the ranked candidate pool to twice the requested successful-material count.

**Architecture:** Keep timeout enforcement at the shared gateway call in `rpa_connector.py`, so list and detail invocations use identical five-minute transport limits. Keep replacement behavior in `yuntu_batch.py`; it already treats detail-call exceptions as rejected materials and advances to later candidates. Change only the connector's default pool size and its documented contract.

**Tech Stack:** Python 3, `requests`, `unittest`.

---

### Task 1: Add Regression Expectations

**Files:**
- Modify: `tests/test_rpa_connector.py:91-104`
- Modify: `tests/test_rpa_connector.py:299-336`

- [ ] **Step 1: Write the failing test**

```python
def test_fetch_batch_uses_double_target_candidates_by_default(self):
    # target_top_n=5 must pass candidate_top_n=10 to fetch_batch.

# In the gateway payload assertion:
"timeout": 300,
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_rpa_connector.RpaConnectorTest.test_fetch_batch_uses_double_target_candidates_by_default tests.test_rpa_connector.RpaConnectorTest.test_separate_list_and_detail_invocations_use_fixed_payloads -v`

Expected: FAIL because the connector currently passes `7` candidates and `timeout=3600`.

- [ ] **Step 3: Write minimal implementation**

```python
timeout=300

candidate_top_n = (
    target_top_n * 2 if candidate_top_n is None else _validate_top_n(candidate_top_n)
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_rpa_connector.RpaConnectorTest.test_fetch_batch_uses_double_target_candidates_by_default tests.test_rpa_connector.RpaConnectorTest.test_separate_list_and_detail_invocations_use_fixed_payloads -v`

Expected: PASS.

### Task 2: Synchronize The Operator Contract

**Files:**
- Modify: `SKILL.md:44`
- Modify: `SKILL.md:62`

- [ ] **Step 1: Update the timeout and candidate-pool rules**

```markdown
榜单和详情 RPA 单次请求最多等待 300 秒。
未显式指定时为目标数量的 2 倍。
```

- [ ] **Step 2: Run the skill-contract test**

Run: `python -m unittest tests.test_skill_contract -v`

Expected: PASS.

### Task 3: Verify The Change Set

**Files:**
- Verify: `tests/test_rpa_connector.py`
- Verify: `tests/test_skill_contract.py`
- Verify: `scripts/rpa_connector.py`
- Verify: `SKILL.md`

- [ ] **Step 1: Run focused regression tests**

Run: `python -m unittest tests.test_rpa_connector tests.test_skill_contract -v`

Expected: PASS.

- [ ] **Step 2: Run the full suite**

Run: `python -m unittest discover -s tests -v`

Expected: PASS with no failures.
