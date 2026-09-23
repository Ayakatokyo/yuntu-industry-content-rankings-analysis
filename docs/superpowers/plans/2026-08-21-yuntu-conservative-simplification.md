# Yuntu Conservative Simplification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce the Yuntu skill entrypoint and remove verified dead connector code without changing runtime behavior or output contracts.

**Architecture:** Keep `SKILL.md` as the concise operator guide and leave schema-level validation in the existing scripts and prompt template. Delete only `_safe_error_summary`, whose repository-wide reference audit has no callers; do not alter connector dispatch, batch scheduling, state observation, retries, or report rendering.

**Tech Stack:** Python 3, `unittest`, existing CLI contract tests.

---

### Task 1: Preserve the dead-code removal contract

**Files:**
- Modify: `tests/test_rpa_connector.py:70-81`
- Modify: `scripts/rpa_connector.py:469-478`

- [ ] **Step 1: Add the failing public-surface test**

Extend the existing removed-helper list with `"_safe_error_summary"`:

```python
for name in (
    "fetch_analysis",
    "select_material_ids",
    "_manifest",
    "write_json_atomically",
    "_safe_error_summary",
):
    with self.subTest(name=name):
        self.assertFalse(hasattr(connector, name))
```

- [ ] **Step 2: Verify RED**

Run `python -m pytest tests/test_rpa_connector.py::RpaConnectorTest::test_legacy_serial_fetch_helpers_are_removed -q`.

Expected: the `_safe_error_summary` subtest fails because the private function still exists.

- [ ] **Step 3: Remove only the unused helper**

Delete the `_safe_error_summary(error, environ)` definition from `scripts/rpa_connector.py`; do not change any caller or error path.

- [ ] **Step 4: Verify GREEN**

Run the focused test from Step 2. Expected: `1 passed` and all subtests pass.

### Task 2: Reduce the skill entrypoint to operational guidance

**Files:**
- Modify: `tests/test_skill_contract.py`
- Modify: `SKILL.md`

- [ ] **Step 1: Add a failing concision contract**

Replace the existing chapter-detail assertions in `test_documents_rpa_run_state_and_five_section_report_scope`, `test_documents_closed_loop_report`, and `test_documents_top_material_combination_and_title_brand_limits` with a single operational-boundary test, while retaining the existing tests for input, fixed connectors, command availability, CSV-first artifacts, recovery, and provenance:

```python
def test_skill_keeps_operational_rules_and_defers_schema_details(self):
    skill = self.read_skill()
    self.assertLessEqual(len(skill.splitlines()), 100)
    self.assertNotIn("industryTop1000Facts", skill)
    for phrase in (
        "run-summary.json",
        "unresolvedMaterials",
        "status == success",
        "prepare-analysis",
        "attest-analysis",
        "render-report",
        "程序化兜底",
        "脚本和生成的提示词是 schema 权威",
    ):
        self.assertIn(phrase, skill)
```

- [ ] **Step 2: Verify RED**

Run `python -m pytest tests/test_skill_contract.py::AnalysisSkillContractTests::test_skill_keeps_operational_rules_and_defers_schema_details -q`.

Expected: failure because `SKILL.md` exceeds 100 lines and repeats the schema field list.

- [ ] **Step 3: Rewrite only the duplicated documentation**

Keep frontmatter plus input and relative-period rules, environment-only credentials, account discovery, status observation, fetch/prepare/attest/render/retry sequence, recovery/grouping semantics, `status == success`, no programmatic fallback, and main output paths. Remove only repeated fact-pack, analysis, report-field, report-chapter, and highlighter-algorithm details; state that scripts and the generated prompt are the schema authority. The test rewrite must not remove assertions for CLI options, CSV-first artifacts, retry boundaries, or provenance.

- [ ] **Step 4: Verify GREEN**

Run the focused test from Step 2, then `python -m pytest tests/test_skill_contract.py -q`. Expected: both commands exit 0.

### Task 3: Full verification and runtime preflight

**Files:**
- Verify: `SKILL.md`
- Verify: `scripts/rpa_connector.py`
- Verify: `tests/test_rpa_connector.py`
- Verify: `tests/test_skill_contract.py`

- [ ] **Step 1: Inspect the scoped diff**

Run `git diff --check` and inspect only `SKILL.md`, `scripts/rpa_connector.py`, `tests/test_rpa_connector.py`, and `tests/test_skill_contract.py`.

Expected: no whitespace errors and only planned documentation, test, and dead-code changes.

- [ ] **Step 2: Run the full test suite**

Run `python -m pytest -q`. Expected: exit 0 with no failures.

- [ ] **Step 3: Check safe real-RPA prerequisites without reading values**

Run a presence-only check for `ENV_BACKEND_HOST`, `YUCE_AUTHORIZATION`, `YUCE_SESSION_ID`, and `YCSESSIONID`. Only when all exist, run `self-test`, then a real RPA regression in a fresh output directory and verify `status` returns `success`; otherwise report the missing variable without printing authentication values.
