# Yuntu Prompt Markdown Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move the long Yuntu AI analysis prompt into a repository Markdown template while preserving runtime parameter injection and batch prompt artifacts.

**Architecture:** `prompts/yuntu-analysis-prompt.md` owns stable analysis rules and uses explicit placeholders for runtime scope values. `scripts/yuntu_analysis.py` loads the template, substitutes validated runtime values, and writes the completed prompt to each batch's `diagnostic-analysis/yuntu-analysis-prompt.md`; downstream AI and provenance commands continue consuming that batch file.

**Tech Stack:** Python 3, Markdown template, unittest.

---

### Task 1: Add the prompt template

**Files:**
- Create: `prompts/yuntu-analysis-prompt.md`

- [ ] Copy the existing `_prompt_text()` body into Markdown, replacing only runtime-specific values with `{brand_scope_label}`, `{brands}`, and `{scope_labels}` placeholders.
- [ ] Preserve every output-contract, evidence, length, chapter-mapping, and JSON-schema rule exactly.

### Task 2: Load and render the template from Python

**Files:**
- Modify: `scripts/yuntu_analysis.py`

- [ ] Add a repository-root prompt path constant and a UTF-8 template loader.
- [ ] Replace the long inline f-string in `_prompt_text()` with template loading and named placeholder substitution.
- [ ] Keep the existing dynamic value semantics and batch output path unchanged.

### Task 3: Add regression coverage

**Files:**
- Modify: `tests/test_yuntu_analysis.py`

- [ ] Assert the repository template exists and contains the stable prompt contract.
- [ ] Assert generated batch prompts include runtime Top N, brands, and scope order.
- [ ] Assert the generated prompt is sourced from the template rather than an inline Python-only body.

### Task 4: Verify the real execution path

- [ ] Run focused analysis tests and the full test suite.
- [ ] Run `prepare-analysis` against the real batch inputs and confirm `diagnostic-analysis/yuntu-analysis-prompt.md` is regenerated with the expected dynamic values.
- [ ] Run `git diff --check` and inspect the diff for prompt content loss or unintended changes.
