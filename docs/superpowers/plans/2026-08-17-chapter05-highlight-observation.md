# Chapter 05 Highlight Observation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Chapter 05 highlight-frame workspace use the Chapter 04 tab visual language, filter AI frame observations through selectable real frames, and simplify frame metrics to time and click index.

**Architecture:** Keep `materialFacts.highlightFrames` as the deterministic source for image, second, and click index. Keep `materialDeepDives.frame_observations` as the AI-only visual-observation source, project it through `yuntu_presentation.py`, and render selection state entirely in the existing report template JavaScript.

**Tech Stack:** Python 3, JSON fact pack, HTML string renderer, inline browser JavaScript, CSS, `unittest`.

---

### Task 1: Lock the Chapter 05 output contract with tests

**Files:**
- Modify: `tests/test_yuntu_presentation.py`
- Modify: `tests/test_yuntu_report.py`

- [ ] **Step 1: Write failing projection assertions**

```python
panel = build_yuntu_presentation(analysis, facts)["chapters"]["chapter05"]["panels"][0]
self.assertEqual(panel["frameObservations"][0]["frame_ref"], panel["frames"][0]["frameRef"])
```

- [ ] **Step 2: Write failing render assertions**

```python
self.assertIn('data-deep-frame-observation', rendered)
self.assertIn('data-deep-frame-select-all', rendered)
self.assertIn('data-deep-frame-select-none', rendered)
self.assertNotIn('点击 Top1 峰值帧', rendered)
```

- [ ] **Step 3: Run focused tests and confirm failure**

Run: `python -m unittest tests.test_yuntu_presentation tests.test_yuntu_report -q`

### Task 2: Render the selectable frame workspace

**Files:**
- Modify: `scripts/yuntu_report_sections.py`
- Modify: `scripts/templates/final-report-template.html`
- Modify: `assets/report/unified-report.css`

- [ ] **Step 1: Render semantically complete controls**

Render one checkbox per available frame, `全选高光帧` and `全不选高光帧` controls, a per-frame `data-frame-ref`, and observation nodes keyed by the same reference. Render the frame caption only as `Ns · 点击指数 X`.

- [ ] **Step 2: Implement selection synchronization**

```javascript
function syncSelection() {
  checkboxes.forEach(function (checkbox) {
    var selected = checkbox.checked;
    checkbox.closest('[data-deep-frame-card]').classList.toggle('is-selected', selected);
    observationByRef[checkbox.dataset.frameRef].hidden = !selected;
  });
}
```

Run it after each checkbox change and after select-all/select-none actions.

- [ ] **Step 3: Reuse the Chapter 04 tab appearance**

Apply the same border, radius, selected background, hover and keyboard focus rules to `.material-detail-tabs button` as `.highlight-dashboard-tabs button`; retain responsive wrapping.

### Task 3: Regenerate real Chapter 05 AI observations

**Files:**
- Modify: `RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict/diagnostic-analysis/yuntu-ai-analysis.json`

- [ ] **Step 1: Inspect every local available JPEG**

Use the exact `frame_ref` from `yuntu-analysis-data.json`; make one observation per available frame, describing only visible subjects, composition, product, text, action, and setting.

- [ ] **Step 2: Replace all frame observations**

Keep `frame_ref` coverage exact. Each observation is at least 40 Chinese characters and does not claim the selected point caused clicks, conversion, or any metric outcome.

- [ ] **Step 3: Sign and render**

```bash
python scripts/rpa_connector.py attest-analysis --analysis-json "$BATCH/diagnostic-analysis/yuntu-ai-analysis.json" --fact-pack-json "$BATCH/diagnostic-analysis/yuntu-analysis-data.json" --prompt "$BATCH/diagnostic-analysis/yuntu-analysis-prompt.md" --source manual_model_generated --generator 'Codex GPT-5'
python scripts/rpa_connector.py render-report --analysis-json "$BATCH/diagnostic-analysis/yuntu-ai-analysis.json" --fact-pack-json "$BATCH/diagnostic-analysis/yuntu-analysis-data.json" --analysis-provenance "$BATCH/diagnostic-analysis/yuntu-ai-analysis.provenance.json" --highlight-asset-root "$BATCH/highlights" --output-dir "$BATCH/final-report"
```

### Task 4: Verify the output

**Files:**
- Verify: `RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict/final-report/final-report.html`

- [ ] **Step 1: Run the full suite**

Run: `python -m unittest discover -s tests -q`

- [ ] **Step 2: Check real-frame coverage and rendered controls**

Confirm every available fact-pack frame has exactly one frame observation; verify the rendered report includes all three workspace tabs, selection controls, observation nodes, and no peak-rank label in the Chapter 05 card caption.
