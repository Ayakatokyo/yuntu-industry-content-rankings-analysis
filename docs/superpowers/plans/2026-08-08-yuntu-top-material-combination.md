# TOP 素材组合结论 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `01｜TOP 素材组合结论` from existing normalized RPA-list artifacts, producing aggregate and title-classified brand TOP30 conclusions.

**Architecture:** A pure post-RPA fact module reads normalized list records; the existing analysis preparation adds its facts and output contract; the existing renderer validates and displays one conclusion-first report section. RPA transport, batch orchestration, retries, connector references and CSV parsing stay unchanged.

**Tech Stack:** Python standard library, `unittest`, existing atomic JSON writer, HTML `string.Template`.

---

## File Structure

- Create: `scripts/yuntu_top_materials.py` for deterministic TOP30, title rules, metric, audience and marketing facts.
- Create: `tests/test_yuntu_top_materials.py` for isolated business-rule tests.
- Modify: `scripts/yuntu_analysis.py` and `tests/test_yuntu_analysis.py` to persist `topMaterialCombination` and its model prompt contract.
- Modify: `scripts/yuntu_report.py`, `scripts/templates/final-report-template.html`, and `tests/test_yuntu_report.py` to validate and render the first conclusion block.
- Modify: `SKILL.md` and `tests/test_skill_contract.py` to document the post-RPA behavior only.

Excluded files: `scripts/rpa_connector.py`, `scripts/yuntu_batch.py`, `references/connectors/**`, all raw CSV handling and all gateway calls.

### Task 1: Build deterministic TOP30 and title classification

**Files:**
- Create: `tests/test_yuntu_top_materials.py`
- Create: `scripts/yuntu_top_materials.py`

- [ ] **Step 1: Write the failing unit tests**

```python
def test_classify_brand_and_select_top_materials(self):
    subject = load_module()
    self.assertEqual(subject.classify_brand("#万益蓝 WONDERLAB"), {"value": "万益蓝/WONDERLAB", "source": "title_rule"})
    self.assertEqual(subject.classify_brand("五个女博士富铁软糖"), {"value": "五个女博士", "source": "title_rule"})
    self.assertEqual(subject.classify_brand("燕之屋精炖燕窝"), {"value": "燕之屋", "source": "title_rule"})
    self.assertEqual(subject.classify_brand("未标注素材"), {"value": "未知品牌", "source": "unclassified"})
    rows = [record("101", 100, 3), record("102", 100, 1), record("103", 100, 1), record("104", 99, 1)]
    self.assertEqual([row["material_id"] for row in subject.select_top_materials(rows, limit=3)], ["102", "103", "101"])
```

- [ ] **Step 2: Verify the missing-module failure**

Run: `python -m unittest tests/test_yuntu_top_materials.py -v`

Expected: FAIL because `scripts/yuntu_top_materials.py` is absent.

- [ ] **Step 3: Implement the minimal API**

```python
BRAND_RULES = (("万益蓝/WONDERLAB", ("万益蓝", "wonderlab")), ("五个女博士", ("五个女博士",)), ("燕之屋", ("燕之屋",)))

def classify_brand(title):
    matches = [name for name, words in BRAND_RULES if any(word.casefold() in str(title or "").casefold() for word in words)]
    return {"value": matches[0], "source": "title_rule"} if len(matches) == 1 else {"value": "歧义品牌", "source": "ambiguous"} if matches else {"value": "未知品牌", "source": "unclassified"}

def select_top_materials(records, *, limit=30):
    return sorted((row for row in records if _positive_number(row.get("metrics", {}).get("show_cnt"))), key=lambda row: (-row["metrics"]["show_cnt"], row.get("rank", float("inf")), str(row.get("material_id", ""))))[:limit]
```

- [ ] **Step 4: Verify the unit test and commit**

Run: `python -m unittest tests/test_yuntu_top_materials.py -v`

Expected: PASS.

Commit: `git add scripts/yuntu_top_materials.py tests/test_yuntu_top_materials.py && git commit -m "feat: add top material selection facts"`

### Task 2: Generate overall and brand TOP30 facts

**Files:**
- Modify: `tests/test_yuntu_top_materials.py`
- Modify: `scripts/yuntu_top_materials.py`

- [ ] **Step 1: Write failing summary tests**

```python
def test_build_combination_calculates_metrics_people_and_brand_isolation(self):
    subject = load_module()
    result = subject.build_top_material_combination([
        record("1", 600, 2, "五个女博士", people=["24-30", "女", "新锐白领"]),
        record("2", 400, 1, "万益蓝", people=["24-30", "女", "精致妈妈"]),
        record("3", 500, 3, "未标注", people=["36-40", "男", "小镇青年"]),
        record("4", 300, 4, "万益蓝和五个女博士"),
    ], top_n=2)
    self.assertEqual(result["overall"]["exposure"]["total"], 1100)
    self.assertEqual(result["overall"]["metrics"]["ctr"]["count"], 2)
    self.assertTrue(result["overall"]["people"]["coverageIsOverlapping"])
    self.assertEqual(result["brands"]["五个女博士"]["identifiedMaterialCount"], 1)
    self.assertIn("ambiguous_brand_title", result["warnings"])
    self.assertEqual(result["overall"]["metrics"]["cpm"], {"available": False, "missingReason": "rpa_not_provided"})
```

- [ ] **Step 2: Verify the fact-builder failure**

Run: `python -m unittest tests/test_yuntu_top_materials.py -v`

Expected: FAIL because `build_top_material_combination` is absent.

- [ ] **Step 3: Implement the complete returned shape**

```python
CORE_METRICS = ("ctr", "cvr", "pvr", "play_3s_rate", "play_5s_rate", "play_over_rate", "interact_rate", "component_click_rate", "play_duration_avg")

def metric_summary(records, metric):
    values = [row["metrics"][metric] for row in records if _number(row.get("metrics", {}).get(metric)) is not None]
    return {"count": len(values), "mean": sum(values) / len(values) if values else None, "median": median(values) if values else None}
```

`build_top_material_combination(records, top_n=30)` returns `schemaVersion`, `classificationRules`, `overall`, `brands`, `warnings`, and `dataAvailability`. Overall retains unknown and ambiguous records. Brand sections include only single-match title rules. Each summary contains total, average, median, pool share and top-three exposure share; ten current metrics each have count/mean/median; absent CPM returns `rpa_not_provided`. People facts classify age, gender and eight portraits, each with material share and exposure coverage, plus an overlap disclaimer. Marketing facts preserve raw tags and classify them as 成分/原料、功效、痛点、使用场景、内容形式、促销利益 or 其他. Tag metric comparisons require at least three tagged and three untagged materials.

- [ ] **Step 4: Verify all pure-business behaviors and commit**

Run: `python -m unittest tests/test_yuntu_top_materials.py -v`

Expected: PASS for metrics, marketing, people overlap, insufficient samples, unknown brands, ambiguous brands and missing CPM.

Commit: `git add scripts/yuntu_top_materials.py tests/test_yuntu_top_materials.py && git commit -m "feat: summarize top material combinations"`

### Task 3: Extend analysis facts and the model contract

**Files:**
- Modify: `tests/test_yuntu_analysis.py`
- Modify: `scripts/yuntu_analysis.py`

- [ ] **Step 1: Write the failing integration test**

```python
def test_prepare_analysis_writes_top_material_combination_and_prompt_contract(self):
    analysis = load_module()
    records = [{"material_id": "1", "title": "五个女博士", "rank": 1, "metrics": {"show_cnt": 200, "ctr": 0.2}, "people_tags": ["24-30"], "material_tags": ["成分配方原料_铁元素"], "data_availability": {}}]
    selected = [{"rank": 1, "material_id": "1", "detailRecordPath": "normalized/detail-records/1.json"}]
    details = {"1": {"material_id": "1", "high_points": [], "loss_points": [], "data_availability": {}}}
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory); self._write_input(root, records, selected, details)
        analysis.prepare_analysis(input_dir=root, output_dir=root / "diagnostic-analysis")
        data = json.loads((root / "diagnostic-analysis" / "yuntu-analysis-data.json").read_text(encoding="utf-8"))
    self.assertEqual(data["topMaterialCombination"]["overall"]["topMaterials"][0]["material_id"], "1")
```

- [ ] **Step 2: Verify the integration test fails**

Run: `python -m unittest tests.test_yuntu_analysis.YuntuAnalysisTests.test_prepare_analysis_writes_top_material_combination_and_prompt_contract -v`

Expected: FAIL because the fact pack has no `topMaterialCombination`.

- [ ] **Step 3: Attach the new facts and prompt schema**

```python
from yuntu_top_materials import build_top_material_combination

# Add inside the fact_pack dictionary.
"topMaterialCombination": build_top_material_combination(pool_records),
```

Require the model to write this key: `{"topMaterialCombination":{"overallConclusions":[{"summary":"","evidence":[],"material_ids":[]}],"brandConclusions":[{"brand":"","classificationSource":"title_rule","summary":"","evidence":[],"material_ids":[]}]}}`. The prompt must require metrics, samples and source IDs; call brand rows 标题匹配归属; explain people coverage overlaps; prohibit causal claims; and require “数据不足以判断” for unavailable CPM or insufficient samples.

- [ ] **Step 4: Run the full analysis module suite and commit**

Run: `python -m unittest tests/test_yuntu_analysis.py -v`

Expected: PASS, including existing high-light tests.

Commit: `git add scripts/yuntu_analysis.py tests/test_yuntu_analysis.py && git commit -m "feat: add top material facts to analysis pack"`

### Task 4: Validate and render the first report block

**Files:**
- Modify: `tests/test_yuntu_report.py`
- Modify: `scripts/yuntu_report.py`
- Modify: `scripts/templates/final-report-template.html`

- [ ] **Step 1: Write failing renderer tests**

```python
def test_render_report_requires_and_renders_top_material_combination_first(self):
    report = load_module(); analysis = self.analysis_json()
    analysis["topMaterialCombination"] = {"overallConclusions": [{"summary": "TOP30 总曝光占比高。", "evidence": [{"metric": "show_cnt", "value": 1000}], "material_ids": ["101"]}], "brandConclusions": [{"brand": "五个女博士", "classificationSource": "title_rule", "summary": "标题匹配样本以女性标签覆盖为主。", "evidence": [{"metric": "ctr", "value": 0.2}], "material_ids": ["101"]}]}
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory); path = root / "analysis.json"
        path.write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
        report.render_report(analysis_json=path, output_dir=root / "report")
        markdown = (root / "report" / "final-report.md").read_text(encoding="utf-8")
        html = (root / "report" / "final-report.html").read_text(encoding="utf-8")
    self.assertLess(markdown.index("01｜TOP 素材组合结论"), markdown.index("榜单竞争格局"))
    self.assertLess(html.index("01｜TOP 素材组合结论"), html.index("榜单竞争格局"))
```

- [ ] **Step 2: Verify renderer tests fail**

Run: `python -m unittest tests/test_yuntu_report.py -v`

Expected: FAIL because validation and template values lack the new object.

- [ ] **Step 3: Implement validation and conclusion-first rendering**

Add `_validate_top_material_combination(value)` that requires both lists and reuses `_validate_evidence_section`; every brand row requires nonblank `brand` and `classificationSource == "title_rule"`. Make the key required in `_load_analysis`. Render `## 01｜TOP 素材组合结论` before existing report headings. HTML uses one `insight-stack`: overall conclusions then brand conclusions, each with evidence and material references; brand rows visibly say `标题匹配归属`. The template's first navigation item and first section use the new title. Do not add dashboards, scorecards, recommendation tables or per-material diagnostic pages.

- [ ] **Step 4: Verify report behavior and commit**

Run: `python -m unittest tests/test_yuntu_report.py -v`

Expected: PASS for legacy behavior, malformed-section rejection, first-section order and accessible HTML.

Commit: `git add scripts/yuntu_report.py scripts/templates/final-report-template.html tests/test_yuntu_report.py && git commit -m "feat: render top material combination conclusions"`

### Task 5: Document only the post-RPA contract and run regressions

**Files:**
- Modify: `SKILL.md`
- Modify: `tests/test_skill_contract.py`

- [ ] **Step 1: Write a failing contract test**

```python
def test_documents_top_material_combination_and_title_brand_limits(self):
    skill = self.read_skill()
    for phrase in ("TOP 素材组合结论", "品牌筛选条件下 TOP30", "标题匹配", "未知品牌", "CPM", "不可相加为 100%"):
        self.assertIn(phrase, skill)
```

- [ ] **Step 2: Verify it fails**

Run: `python -m unittest tests/test_skill_contract.py -v`

Expected: FAIL because the business report section has not documented this block.

- [ ] **Step 3: Update the business documentation only**

Add the calculation and display rules under “商业分析与报告”: title matching is a business classification, unknown title material stays in the selected-brand overall TOP30 but not a brand TOP30, missing CPM remains unavailable, and overlapping people-tag coverage cannot sum to 100%. Do not change connector names, gateway variables, fetch options, retry instructions, or raw artifacts.

- [ ] **Step 4: Run full verification and commit**

Run: `python -m unittest discover -s tests -p 'test_*.py' -v && git diff --check && python scripts/rpa_connector.py self-test`

Expected: all tests pass, diff check is silent, and the final command prints `self-test passed`.

Commit: `git add SKILL.md tests/test_skill_contract.py && git commit -m "docs: describe top material combination output"`

## Plan Self-Review

- Tasks 1-2 cover sorting, title brands, metrics, people, marketing, missing CPM and all classification degradations.
- Task 3 defines the fact pack and model contract; Task 4 introduces only the approved first report block; Task 5 documents it and verifies the existing connector boundary.
- The single key name is `topMaterialCombination`; its AI output is `overallConclusions` plus `brandConclusions`, and brand rows add `brand` plus `classificationSource`.
