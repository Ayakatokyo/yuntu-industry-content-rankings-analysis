# 云图第五部分单素材脚本分析完善实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为第五章每个素材补齐专属脚本事实、AI 脚本结论和千川风格的脚本分析 Tab。

**Architecture:** 在现有 `material-deep-dive-input.json` 内增加每素材 `script`/`evidenceIndex` 投影，AI 在 `materialDeepDives[*].scriptAnalysis` 输出单素材结论；Presentation 将 AI 与脚本事实合并，模板以“AI → 内容公式 → 原始脚本 → 证据高亮”渲染。

**Tech Stack:** Python 3、pytest、JSON Schema、原生 HTML/CSS/JavaScript。

**Spec:** `docs/superpowers/specs/2026-09-05-yuntu-chapter05-script-analysis-design.md`

## Global Constraints

- 不接入新连接器、不新建 CSV 导入适配层、不改变第三章批量脚本事实。
- AI 只读取当前素材脚本、内容公式、证据句和证据白名单；不跨素材、不跨章节。
- 标题、画面文本、高光帧和秒级曲线不作为脚本 AI 证据；无时间戳不做帧—话术对应。
- 保留第五章既有高光帧、秒级拆解和素材 Tab 契约。
- 事实缺失时显示“数据不足以判断”，不猜测、不写因果。

### Task 1: 扩充第五章脚本事实输入

**Files:**
- Modify: `scripts/yuntu_analysis.py`（`_model_material_facts`、`_write_analysis_units`）
- Test: `tests/test_yuntu_analysis.py`

**Interfaces:**
- Consumes: 现有 `materialFacts[*].script_text`、`content_formula`、证据/可用性字段。
- Produces: `material-deep-dive-input.json` 中每素材 `script` 与 `evidenceIndex.script`。

- [ ] **Step 1: Write failing test**

```python
def test_material_deep_dive_input_contains_script_facts_and_evidence_allowlist(tmp_path):
    manifest = analysis._write_analysis_units(fact_pack_with_script, tmp_path)
    payload = json.loads((tmp_path / "analysis-units/material-deep-dive-input.json").read_text())
    material = payload["evidence"]["materialFacts"][0]
    assert material["script"]["text"]
    assert material["script"]["formula"]
    assert material["evidenceIndex"]["script"]
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_yuntu_analysis.py -k "deep_dive_input_contains_script_facts" -v`

Expected: FAIL because `_model_material_facts` currently strips script fields.

- [ ] **Step 3: Implement minimal projection**

Add a helper that maps cloud `script_text`/`content_formula`/evidence fields into `script.text`, `script.labels`, `script.formula`, `script.evidence`, `script.availability`, and builds `evidenceIndex.script` from only current-material refs. Keep frame and second-level fields unchanged.

- [ ] **Step 4: Run focused test**

Run: `pytest tests/test_yuntu_analysis.py -k "deep_dive_input_contains_script_facts" -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/yuntu_analysis.py tests/test_yuntu_analysis.py
git commit -m "feat: add chapter05 per-material script facts"
```

### Task 2: Add Chapter 05 script AI contract and validation

**Files:**
- Modify: `prompts/yuntu-analysis-prompt.md`
- Modify: `scripts/yuntu_analysis.py`（`_material_deep_dive_output_schema`）
- Modify: `scripts/yuntu_report.py`（`_validate_material_deep_dives`）
- Test: `tests/test_yuntu_report.py`

**Interfaces:**
- Consumes: `materialFacts[*].script` and `evidenceIndex.script`.
- Produces: `materialDeepDives[*].scriptAnalysis` with `conclusion`, `evidenceRefs`, `availability`.

- [ ] **Step 1: Write failing validation test**

```python
def test_material_script_analysis_rejects_cross_material_evidence():
    with pytest.raises(YuntuReportError, match="scriptAnalysis evidenceRefs"):
        report._validate_material_deep_dives(analysis_with_cross_material_script_ref, fact_pack_with_script)
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_yuntu_report.py -k "cross_material_evidence" -v`

Expected: FAIL because scriptAnalysis is not currently validated.

- [ ] **Step 3: Implement schema, prompt and validator**

Extend the generated schema with `scriptAnalysis`; add the Chapter 05 prompt rules and validate one deep-dive per selected material, conclusion length, availability enum and evidence refs against that material’s `evidenceIndex.script`. Keep frame-observation coverage checks unchanged.

- [ ] **Step 4: Run focused tests**

Run: `pytest tests/test_yuntu_report.py -k "cross_material_evidence" -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add prompts/yuntu-analysis-prompt.md scripts/yuntu_analysis.py scripts/yuntu_report.py tests/test_yuntu_report.py
git commit -m "feat: validate chapter05 script ai analysis"
```

### Task 3: Project script facts and AI conclusion into Chapter 05 panels

**Files:**
- Modify: `scripts/yuntu_presentation.py::_project_chapter05`
- Test: `tests/test_yuntu_presentation.py`

**Interfaces:**
- Consumes: material facts and validated `materialDeepDives[*].scriptAnalysis`.
- Produces: `chapters.chapter05.panels[*].script`.

- [ ] **Step 1: Write failing projection test**

```python
def test_chapter05_panel_projects_script_analysis_and_evidence():
    panel = build_yuntu_presentation(analysis_with_script_analysis, fact_pack_with_script)["chapters"]["chapter05"]["panels"][0]
    assert panel["script"]["analysis"]["conclusion"]
    assert panel["script"]["formula"][0]["level1"] == "商品卖点"
    assert panel["script"]["analysis"]["evidenceRefs"]
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_yuntu_presentation.py -k "projects_script_analysis_and_evidence" -v`

Expected: FAIL because Chapter 05 panels expose only flat script fields.

- [ ] **Step 3: Implement projection**

Build the nested `script` object, filter refs through the current material allowlist, normalize missing AI to `availability=unavailable`, and leave existing `scriptText`, `contentFormula`, frame and second-level compatibility fields untouched until the renderer migration is complete.

- [ ] **Step 4: Run focused test**

Run: `pytest tests/test_yuntu_presentation.py -k "projects_script_analysis_and_evidence" -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/yuntu_presentation.py tests/test_yuntu_presentation.py
git commit -m "feat: project chapter05 script analysis panel data"
```

### Task 4: Rebuild the Chapter 05 script Tab markup

**Files:**
- Modify: `scripts/yuntu_report_sections.py`（第五章 panel 脚本片段）
- Test: `tests/test_yuntu_report.py`

**Interfaces:**
- Consumes: panel `script` projection, with flat-field fallback for historical payloads.
- Produces: `.material-script-ai`, `.material-script-formula`, `.material-script-transcript`, `[data-script-evidence-ref]` markup.

- [ ] **Step 1: Write failing renderer test**

```python
def test_chapter05_script_tab_orders_ai_formula_transcript_and_evidence():
    html = render_material_deep_dive_html(fact_pack_with_script, presentation_with_script_panel)
    script_tab = html.split('data-material-detail-tab="script"', 1)[1]
    assert script_tab.index("material-script-ai") < script_tab.index("material-script-formula")
    assert script_tab.index("material-script-formula") < script_tab.index("material-script-transcript")
    assert "data-script-evidence-ref" in script_tab
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_yuntu_report.py -k "orders_ai_formula_transcript" -v`

Expected: FAIL because the current script panel is a single `.data-state` block.

The test module must define `render_material_deep_dive_html(fact_pack, presentation)` as a small fixture wrapper around the existing `render_material_deep_dive(...)` function, passing the repository's current formatter/image helpers and the supplied presentation panel.

- [ ] **Step 3: Implement escaped semantic renderer**

Render AI conclusion first, then formula chain, then original script with evidence spans and boundary note. Use deterministic `evidenceRef` attributes, do not render title/visual text as script evidence, and keep the flat-field fallback only for historical report data.

- [ ] **Step 4: Run focused test**

Run: `pytest tests/test_yuntu_report.py -k "orders_ai_formula_transcript" -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/yuntu_report_sections.py tests/test_yuntu_report.py
git commit -m "feat: structure chapter05 script analysis tab"
```

### Task 5: Add formula-to-evidence interaction and Qianchuan styling

**Files:**
- Modify: `scripts/templates/final-report-template.html`
- Modify: `assets/report/unified-report.css`
- Test: `tests/test_yuntu_report.py`

**Interfaces:**
- Consumes: semantic script Tab markup and `data-script-evidence-ref` attributes.
- Produces: click/keyboard evidence highlighting, Qianchuan-aligned cards, responsive single-column layout.

- [ ] **Step 1: Write failing template/style checks**

```python
def test_chapter05_script_tab_has_formula_evidence_and_responsive_contract():
    template = Path("scripts/templates/final-report-template.html").read_text(encoding="utf-8")
    css = Path("assets/report/unified-report.css").read_text(encoding="utf-8")
    assert "highlightScriptEvidence" in template
    assert ".material-script-ai" in css
    assert ".material-script-formula" in css
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_yuntu_report.py -k "formula_evidence_and_responsive" -v`

Expected: FAIL until the new behavior and scoped CSS are present.

- [ ] **Step 3: Implement interaction**

Add `highlightScriptEvidence(panel, evidenceRef)` and bind formula chips to it. Toggle `.is-evidence-active`, scroll the first matching evidence span into view, support Enter/Space and `prefers-reduced-motion`, and clear active state when changing material or detail tabs.

- [ ] **Step 4: Implement styling and run focused checks**

Add scoped styles for the AI card, formula chain, transcript, evidence highlight, missing states and mobile layout. Reuse existing colors/tokens and avoid changing Chapter 03/04/05 frame or timeline styles.

Run: `pytest tests/test_yuntu_report.py -k "formula_evidence_and_responsive" -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/templates/final-report-template.html assets/report/unified-report.css tests/test_yuntu_report.py
git commit -m "style: polish chapter05 script analysis workspace"
```

### Task 6: End-to-end report regression

**Files:**
- Modify: `tests/test_yuntu_analysis.py`, `tests/test_yuntu_presentation.py`, `tests/test_yuntu_report.py` only for fixture alignment.

- [ ] **Step 1: Run the complete suite**

Run: `pytest -q`

Expected: all existing tests and new Chapter 05 script tests pass.

- [ ] **Step 2: Generate a report using the current CSV-backed run**

Run the existing analysis/report pipeline on the supplied RPA-derived data and confirm `material-deep-dive-input.json`, `presentation-report.json` and `final-report.html` contain per-material script facts and AI conclusion slots without changing Chapters 03/04.

- [ ] **Step 3: Inspect the final HTML**

At desktop and narrow viewport widths verify the script Tab reads AI → formula → transcript → evidence, formulas highlight the intended sentence, empty states are explicit, and frame/timeline Tabs still behave as before.

- [ ] **Step 4: Commit verification-only changes**

```bash
git add tests
git commit -m "test: verify chapter05 script analysis end to end"
```
