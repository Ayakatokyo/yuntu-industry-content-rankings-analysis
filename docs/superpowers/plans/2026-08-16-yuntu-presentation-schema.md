# Yuntu Presentation Schema Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add and validate a standalone `PresentationReport v1` projection for Yuntu chapters 02, 04, and 05 without changing current report HTML, CSS, RPA, AI prompts, or Qianchuan code.

**Architecture:** Add a pure `yuntu_presentation` module that accepts already-validated `analysis` and `fact_pack`, then returns JSON-serializable presentation data. The module keeps AI explanation fields and deterministic fact fields distinct, preserves the Chapter 02 dual-scope contract, and validates all cross-references before callers can persist the projection.

**Tech Stack:** Python standard library, `unittest`, existing Yuntu fact pack schema v4 and AI analysis schema.

---

### Task 1: Define the module boundary and report metadata

**Files:**
- Create: `scripts/yuntu_presentation.py`
- Create: `tests/test_yuntu_presentation.py`

- [ ] **Step 1: Write the failing import and minimal-schema test**

```python
from yuntu_presentation import build_yuntu_presentation, validate_yuntu_presentation

def test_minimal_presentation_has_stable_version_and_report_metadata(self):
    payload = build_yuntu_presentation({}, {"schemaVersion": 4})

    self.assertEqual(payload["presentationSchemaVersion"], 1)
    self.assertEqual(payload["report"]["title"], "云图行业内容榜单分析")
    self.assertEqual(payload["report"]["sections"], ["chapter02", "chapter04", "chapter05"])
    self.assertIs(payload, validate_yuntu_presentation(payload))
```

- [ ] **Step 2: Run the test and verify RED**

Run: `python -m unittest tests.test_yuntu_presentation.YuntuPresentationTests.test_minimal_presentation_has_stable_version_and_report_metadata -v`

Expected: FAIL because `yuntu_presentation` does not exist.

- [ ] **Step 3: Implement the minimal pure module**

```python
PRESENTATION_SCHEMA_VERSION = 1
REPORT_TITLE = "云图行业内容榜单分析"
SECTION_IDS = ("chapter02", "chapter04", "chapter05")

class YuntuPresentationError(ValueError):
    pass

def build_yuntu_presentation(analysis, fact_pack, *, report_meta=None):
    payload = {
        "presentationSchemaVersion": PRESENTATION_SCHEMA_VERSION,
        "report": {
            "reportId": "",
            "title": REPORT_TITLE,
            "period": {"startDate": "", "endDate": ""},
            "status": "complete",
            "sections": list(SECTION_IDS),
        },
        "scopes": [],
        "chapters": {"chapter02": {}, "chapter04": {}, "chapter05": {}},
        "materials": [],
        "interactions": {},
        "extensions": {"yuntu": {}},
    }
    validate_yuntu_presentation(payload)
    return payload

def validate_yuntu_presentation(payload):
    if not isinstance(payload, dict):
        raise YuntuPresentationError("presentation must be an object")
    if payload.get("presentationSchemaVersion") != PRESENTATION_SCHEMA_VERSION:
        raise YuntuPresentationError("unsupported presentation schema version")
    report = payload.get("report")
    if not isinstance(report, dict) or report.get("sections") != list(SECTION_IDS):
        raise YuntuPresentationError("presentation report sections are invalid")
    return payload
```

- [ ] **Step 4: Run the focused test and verify GREEN**

Run: `python -m unittest tests.test_yuntu_presentation.YuntuPresentationTests.test_minimal_presentation_has_stable_version_and_report_metadata -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/yuntu_presentation.py tests/test_yuntu_presentation.py
git commit -m "feat: add yuntu presentation schema core"
```

### Task 2: Project and validate Chapter 02 dual-scope data

**Files:**
- Modify: `scripts/yuntu_presentation.py`
- Modify: `tests/test_yuntu_presentation.py`

- [ ] **Step 1: Write failing Chapter 02 scope tests**

```python
def test_chapter02_keeps_ai_and_chart_fact_sources_separate(self):
    payload = build_yuntu_presentation(
        {"chapter02Insights": {"scopes": []}},
        self.chapter02_fact_pack(),
        report_meta={"brandTopN": 30},
    )
    scopes = {item["id"]: item for item in payload["scopes"]}

    self.assertEqual(scopes["all"]["rankScope"], "top1000")
    self.assertEqual(scopes["brand-wonderlab"]["rankScope"], "all-materials")
    self.assertEqual(scopes["brand-wonderlab"]["topN"], 30)
    panel = payload["chapters"]["chapter02"]["panels"][1]
    self.assertEqual(panel["aiFactSource"], "chapter02AiFacts")
    self.assertEqual(panel["chartFactSource"], "chapter02Facts")
    self.assertEqual(panel["topNControl"]["factSource"], "chapter02Facts")

def test_chapter02_rejects_mismatched_scope_order(self):
    fact_pack = self.chapter02_fact_pack()
    fact_pack["chapter02AiFacts"]["scopeOrder"] = ["all"]

    with self.assertRaisesRegex(YuntuPresentationError, "scope order"):
        build_yuntu_presentation({}, fact_pack)
```

- [ ] **Step 2: Run the Chapter 02 tests and verify RED**

Run: `python -m unittest tests.test_yuntu_presentation.YuntuPresentationTests.test_chapter02_keeps_ai_and_chart_fact_sources_separate tests.test_yuntu_presentation.YuntuPresentationTests.test_chapter02_rejects_mismatched_scope_order -v`

Expected: FAIL because scopes and Chapter 02 panels are not projected.

- [ ] **Step 3: Implement scope and chart projection helpers**

```python
def _scope_id(value):
    normalized = "".join(char.lower() if char.isalnum() else "-" for char in str(value))
    return "all" if normalized == "all" else "brand-" + "-".join(filter(None, normalized.split("-")))

def _chapter02_scope_orders(fact_pack):
    chart_facts = fact_pack.get("chapter02Facts", {})
    ai_facts = fact_pack.get("chapter02AiFacts", {})
    chart_order = chart_facts.get("scopeOrder", [])
    ai_order = ai_facts.get("scopeOrder", [])
    if chart_order != ai_order or not chart_order or chart_order[0] != "all":
        raise YuntuPresentationError("chapter02 scope order is invalid")
    return chart_facts, ai_facts, chart_order

def _chapter02_chart(scope_id, category):
    return {
        "id": f"{scope_id}-marketing-level1",
        "type": "column",
        "title": "营销卖点一级类别",
        "dataSource": "chapter02Facts",
        "scopeId": scope_id,
        "value": {"field": "occurrenceCount", "unit": "count"},
        "buckets": category,
        "interaction": {"type": "column-drilldown", "target": f"{scope_id}-marketing-level2"},
        "accessibility": {"label": "营销卖点一级类别柱状图"},
    }
```

The implementation must create one scope and one panel per `scopeOrder` item, copy only AI text from `analysis.chapter02Insights.scopes`, create column/pie/table descriptors from `chapter02Facts`, and set brand `topN` from `report_meta["brandTopN"]`.

- [ ] **Step 4: Run the Chapter 02 tests and verify GREEN**

Run: `python -m unittest tests.test_yuntu_presentation.YuntuPresentationTests.test_chapter02_keeps_ai_and_chart_fact_sources_separate tests.test_yuntu_presentation.YuntuPresentationTests.test_chapter02_rejects_mismatched_scope_order -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/yuntu_presentation.py tests/test_yuntu_presentation.py
git commit -m "feat: project yuntu chapter02 presentation data"
```

### Task 3: Project high-light dashboard and enforce frame coverage

**Files:**
- Modify: `scripts/yuntu_presentation.py`
- Modify: `tests/test_yuntu_presentation.py`

- [ ] **Step 1: Write failing high-light tests**

```python
def test_highlight_dashboard_projects_each_available_frame_once(self):
    payload = build_yuntu_presentation(self.highlight_analysis(), self.deep_dive_fact_pack())
    categories = payload["chapters"]["chapter04"]["categories"]
    refs = [frame["frameRef"] for category in categories for frame in category["frames"]]

    self.assertEqual(sorted(refs), sorted(self.available_frame_refs()))
    self.assertEqual(len(refs), len(set(refs)))
    self.assertTrue(all(frame["relativePath"].startswith("highlights/") for category in categories for frame in category["frames"]))

def test_highlight_dashboard_rejects_duplicate_frame_reference(self):
    analysis = self.highlight_analysis()
    analysis["highlightDashboard"]["groups"].append({
        "category": "other",
        "frame_refs": ["highlight:101:cover:0"],
        "common_patterns": ["重复"],
        "derivative_directions": [],
    })

    with self.assertRaisesRegex(YuntuPresentationError, "highlight frame coverage"):
        build_yuntu_presentation(analysis, self.deep_dive_fact_pack())
```

- [ ] **Step 2: Run the high-light tests and verify RED**

Run: `python -m unittest tests.test_yuntu_presentation.YuntuPresentationTests.test_highlight_dashboard_projects_each_available_frame_once tests.test_yuntu_presentation.YuntuPresentationTests.test_highlight_dashboard_rejects_duplicate_frame_reference -v`

Expected: FAIL because Chapter 04 is empty.

- [ ] **Step 3: Implement frame index and dashboard projection**

```python
HIGHLIGHT_CATEGORIES = ("portrait", "product", "scene", "text_overlay", "other")

def _available_frames_by_ref(fact_pack):
    return {
        str(frame["frame_ref"]): frame
        for fact in fact_pack.get("materialFacts", [])
        if isinstance(fact, dict)
        for frame in fact.get("highlightFrames", [])
        if isinstance(frame, dict) and frame.get("available") is True and frame.get("frame_ref")
    }

def _project_highlight_dashboard(analysis, fact_pack):
    available = _available_frames_by_ref(fact_pack)
    groups = (analysis.get("highlightDashboard") or {}).get("groups", [])
    seen = []
    categories = []
    for group in groups:
        category = group.get("category")
        if category not in HIGHLIGHT_CATEGORIES:
            raise YuntuPresentationError("highlight category is invalid")
        frame_refs = group.get("frame_refs", [])
        if any(reference not in available for reference in frame_refs):
            raise YuntuPresentationError("highlight frame reference is invalid")
        seen.extend(frame_refs)
        categories.append({"id": category, "frames": []})
    if set(seen) != set(available) or len(seen) != len(set(seen)):
        raise YuntuPresentationError("highlight frame coverage is invalid")
    return {"scopeId": "all", "categories": categories}
```

The final implementation must preserve category order, common patterns, derivative directions, actual frame seconds/types/ranks, and only relative local JPEG paths.

- [ ] **Step 4: Run the high-light tests and verify GREEN**

Run: `python -m unittest tests.test_yuntu_presentation.YuntuPresentationTests.test_highlight_dashboard_projects_each_available_frame_once tests.test_yuntu_presentation.YuntuPresentationTests.test_highlight_dashboard_rejects_duplicate_frame_reference -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/yuntu_presentation.py tests/test_yuntu_presentation.py
git commit -m "feat: add yuntu highlight presentation projection"
```

### Task 4: Project single-material deep dives and trend availability

**Files:**
- Modify: `scripts/yuntu_presentation.py`
- Modify: `tests/test_yuntu_presentation.py`

- [ ] **Step 1: Write failing deep-dive tests**

```python
def test_material_deep_dive_uses_fixed_metric_order_and_real_seconds(self):
    payload = build_yuntu_presentation(self.deep_dive_analysis(), self.deep_dive_fact_pack())
    panel = payload["chapters"]["chapter05"]["panels"][0]

    self.assertEqual(
        panel["secondLevel"]["metricOrder"],
        ["点赞指数", "流失指数", "点击指数", "互动指数", "评论指数"],
    )
    self.assertEqual(panel["secondLevel"]["metrics"][0]["points"][1]["second"], 2)
    self.assertEqual(panel["availability"]["status"], "complete")

def test_material_deep_dive_requires_reason_for_unavailable_metric(self):
    fact_pack = self.deep_dive_fact_pack()
    fact_pack["materialFacts"][0]["secondLevelBreakdown"]["metrics"][0] = {
        "trend_name": "点赞指数", "available": False, "missing_reason": "", "points": []
    }

    with self.assertRaisesRegex(YuntuPresentationError, "missing reason"):
        build_yuntu_presentation(self.deep_dive_analysis(), fact_pack)
```

- [ ] **Step 2: Run the deep-dive tests and verify RED**

Run: `python -m unittest tests.test_yuntu_presentation.YuntuPresentationTests.test_material_deep_dive_uses_fixed_metric_order_and_real_seconds tests.test_yuntu_presentation.YuntuPresentationTests.test_material_deep_dive_requires_reason_for_unavailable_metric -v`

Expected: FAIL because Chapter 05 panels are empty.

- [ ] **Step 3: Implement selected-material and trend projection**

```python
SECOND_LEVEL_METRIC_ORDER = ("点赞指数", "流失指数", "点击指数", "互动指数", "评论指数")

def _project_second_level(metrics):
    indexed = {item.get("trend_name"): item for item in metrics if isinstance(item, dict)}
    projected = []
    for name in SECOND_LEVEL_METRIC_ORDER:
        metric = indexed.get(name, {"trend_name": name, "available": False, "missing_reason": "趋势未返回", "points": []})
        if not metric.get("available") and not str(metric.get("missing_reason") or "").strip():
            raise YuntuPresentationError("unavailable trend requires a missing reason")
        projected.append({
            "id": name,
            "available": bool(metric.get("available")),
            "reason": str(metric.get("missing_reason") or ""),
            "points": list(metric.get("points") or []),
            "highPoints": list(metric.get("high_points") or []),
            "lossPoints": list(metric.get("loss_points") or []),
        })
    return {"metricOrder": list(SECOND_LEVEL_METRIC_ORDER), "metrics": projected}
```

The implementation must produce exactly one panel per `selectedMaterials` ID, preserve source rank/title/metrics, include only available local frames, copy frame observations by `frame_ref`, and reject observations whose seconds are not represented by the source trend points.

- [ ] **Step 4: Run the deep-dive tests and verify GREEN**

Run: `python -m unittest tests.test_yuntu_presentation.YuntuPresentationTests.test_material_deep_dive_uses_fixed_metric_order_and_real_seconds tests.test_yuntu_presentation.YuntuPresentationTests.test_material_deep_dive_requires_reason_for_unavailable_metric -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/yuntu_presentation.py tests/test_yuntu_presentation.py
git commit -m "feat: add yuntu deep-dive presentation data"
```

### Task 5: Harden validation and verify no report behavior changes

**Files:**
- Modify: `scripts/yuntu_presentation.py`
- Modify: `tests/test_yuntu_presentation.py`

- [ ] **Step 1: Write failing immutability, JSON, and safety tests**

```python
def test_presentation_is_json_serializable_and_does_not_mutate_inputs(self):
    analysis = self.deep_dive_analysis()
    fact_pack = self.deep_dive_fact_pack()
    before = json.dumps({"analysis": analysis, "factPack": fact_pack}, ensure_ascii=False, sort_keys=True)

    payload = build_yuntu_presentation(analysis, fact_pack)

    json.dumps(payload, ensure_ascii=False)
    self.assertEqual(before, json.dumps({"analysis": analysis, "factPack": fact_pack}, ensure_ascii=False, sort_keys=True))

def test_presentation_rejects_absolute_or_parent_frame_path(self):
    fact_pack = self.deep_dive_fact_pack()
    fact_pack["materialFacts"][0]["highlightFrames"][0]["relative_path"] = "../outside.jpg"

    with self.assertRaisesRegex(YuntuPresentationError, "relative frame path"):
        build_yuntu_presentation(self.deep_dive_analysis(), fact_pack)
```

- [ ] **Step 2: Run the hardening tests and verify RED**

Run: `python -m unittest tests.test_yuntu_presentation.YuntuPresentationTests.test_presentation_is_json_serializable_and_does_not_mutate_inputs tests.test_yuntu_presentation.YuntuPresentationTests.test_presentation_rejects_absolute_or_parent_frame_path -v`

Expected: FAIL because path validation is not implemented.

- [ ] **Step 3: Implement final validation boundary**

```python
from pathlib import PurePosixPath

def _safe_relative_frame_path(value):
    path = PurePosixPath(str(value or ""))
    if not str(value or "") or path.is_absolute() or ".." in path.parts:
        raise YuntuPresentationError("relative frame path is invalid")
    return path.as_posix()
```

Use copied lists/dictionaries for every projected fact value. Reject non-finite chart values, duplicate scope IDs, missing interaction targets, invalid report status, unsupported section lists, and presentation objects containing `video_url` or RPA lifecycle keys.

- [ ] **Step 4: Run focused schema tests and existing report tests**

Run: `python -m unittest tests.test_yuntu_presentation -v && python -m unittest tests.test_yuntu_report -v`

Expected: all tests PASS; no report template, CSS, or existing report output has changed.

- [ ] **Step 5: Run full verification and commit**

Run: `python -m unittest discover -s tests -v && python -m py_compile scripts/*.py && git diff --check`

Expected: all tests PASS and no diff whitespace errors.

```bash
git add scripts/yuntu_presentation.py tests/test_yuntu_presentation.py
git commit -m "test: validate yuntu presentation schema"
```
