# Yuntu Connector Handoff Simplification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove duplicate connector-to-batch invoker construction and one unused retry local without changing Yuntu runtime behavior.

**Architecture:** Add a private `_batch_invoker()` factory that preserves the existing lazy lambda forwarding to `invoke_list` and `invoke_detail`. Keep the three public wrappers' validation and exception boundaries unchanged. Remove only the unused `rank` assignment in `_retry_batch_items()`.

**Tech Stack:** Python 3, `unittest.mock`, existing batch and connector tests.

---

### Task 1: Deduplicate connector handoff construction

**Files:**
- Modify: `tests/test_rpa_connector.py`
- Modify: `scripts/rpa_connector.py`

- [ ] **Step 1: Write the failing delegation test**

Add a test that loads the connector, patches its public invocation functions, creates `connector._batch_invoker()`, and asserts both methods forward current arguments and return values:

```python
def test_batch_invoker_forwards_to_current_public_invocations(self):
    connector = self.connector()
    with mock.patch.object(connector, "invoke_list", return_value={"kind": "list"}) as invoke_list, mock.patch.object(
        connector, "invoke_detail", return_value={"kind": "detail"}
    ) as invoke_detail:
        invoker = connector._batch_invoker()
        self.assertEqual(invoker.invoke_list("shop-42", {"page": 1}), {"kind": "list"})
        self.assertEqual(invoker.invoke_detail("shop-42", {"material_id": "101"}), {"kind": "detail"})

    invoke_list.assert_called_once_with("shop-42", {"page": 1})
    invoke_detail.assert_called_once_with("shop-42", {"material_id": "101"})
```

- [ ] **Step 2: Verify RED**

Run `python -m pytest tests/test_rpa_connector.py::RpaConnectorTest::test_batch_invoker_forwards_to_current_public_invocations -q`.

Expected: failure because `_batch_invoker` is not defined.

- [ ] **Step 3: Implement the minimal factory and replace three constructions**

Add before `fetch_batch_analysis()`:

```python
def _batch_invoker():
    return ConnectorInvoker(
        lambda sid, params: invoke_list(sid, params),
        lambda sid, params: invoke_detail(sid, params),
    )
```

Replace only each inline `ConnectorInvoker(...)` expression in `fetch_batch_analysis`, `retry_failed_batch_analysis`, and `retry_unresolved_batch_analysis` with `_batch_invoker()`. Preserve all surrounding checks, parameters, and `except` blocks.

- [ ] **Step 4: Verify GREEN**

Run the focused test from Step 2, then `python -m pytest tests/test_rpa_connector.py -q`.

Expected: focused delegation passes; connector tests pass.

### Task 2: Remove the unused retry local

**Files:**
- Modify: `tests/test_yuntu_batch.py`
- Modify: `scripts/yuntu_batch.py`

- [ ] **Step 1: Write the failing source contract**

Import `inspect` in `tests/test_yuntu_batch.py` and add:

```python
def test_retry_batch_does_not_assign_an_unused_rank_local(self):
    batch = load_batch()
    source = inspect.getsource(batch._retry_batch_items)
    self.assertNotIn('rank = item.get("rank")', source)
```

- [ ] **Step 2: Verify RED**

Run `python -m pytest tests/test_yuntu_batch.py::YuntuBatchTests::test_retry_batch_does_not_assign_an_unused_rank_local -q`.

Expected: failure because the assignment is present.

- [ ] **Step 3: Delete only the unused assignment**

Remove `rank = item.get("rank")` from `_retry_batch_items()`; leave retry timing, selected-entry ordering, and manifest updates unchanged.

- [ ] **Step 4: Verify GREEN**

Run the focused test from Step 2, then `python -m pytest tests/test_yuntu_batch.py -q`.

Expected: focused test and all batch tests pass.

### Task 3: Full verification

**Files:**
- Verify: `scripts/rpa_connector.py`
- Verify: `scripts/yuntu_batch.py`
- Verify: `tests/test_rpa_connector.py`
- Verify: `tests/test_yuntu_batch.py`

- [ ] **Step 1: Inspect the scoped diff**

Run `git diff --check` and inspect the four files above. Confirm no change to CLI parsing, RPA request payloads, executor settings, state observation, manifest keys, or retry status handling.

- [ ] **Step 2: Run the full suite**

Run `python -m pytest -q`. Expected: exit 0 with no failures.

- [ ] **Step 3: Check runtime credentials by presence only**

Check `ENV_BACKEND_HOST`, `YUCE_AUTHORIZATION`, `YUCE_SESSION_ID`, and `YCSESSIONID` without printing values. If complete, run a fresh-output real RPA regression and verify `status: success`; if incomplete, report the missing variable and do not invoke the gateway.
