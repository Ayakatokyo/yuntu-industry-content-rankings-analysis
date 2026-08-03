# 小仙炖云图行业内容榜单分析闭环 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert real Yuntu RPA CSV exports into complete normalized facts and render evidence-backed Xiaoxian Dun content-strategy reports.

**Architecture:** Keep file download and batch orchestration unchanged. Extend `rpa_io.py` to safely decode Python-literal CSV cells, make the normalizer attach field-level availability metadata, then calculate comparison and video-trend facts in `yuntu_analysis.py`. A stricter analysis JSON contract supplies the six fixed Xiaoxian Dun report chapters to `yuntu_report.py`; rendering remains presentation-only.

**Tech Stack:** Python 3 standard library (`ast`, `csv`, `statistics`, `json`, `unittest`), existing `requests` connector, Markdown and HTML.

---

## File Structure

- Modify: `scripts/rpa_io.py` - safely decode JSON and Python-literal nested CSV cells.
- Modify: `scripts/yuntu_normalizer.py` - normalize source fields and record availability/missing reasons.
- Modify: `scripts/yuntu_analysis.py` - create per-material, candidate-pool, tag, trend, and Xiaoxian Dun opportunity facts.
- Modify: `scripts/yuntu_report.py` - validate structured conclusions and render the confirmed six chapters.
- Modify: `SKILL.md` - document the Xiaoxian Dun closed-loop process and analysis JSON contract.
- Modify: `tests/test_rpa_io.py`, `tests/test_yuntu_normalizer.py`, `tests/test_yuntu_analysis.py`, `tests/test_yuntu_report.py`, `tests/test_skill_contract.py`.
- Create: `tests/fixtures/yuntu_rpa_export_sample.csv` - scrubbed representative rows using the observed `\x01` delimiter and Python literals; no credentials or time-limited URLs.

### Task 1: Parse real RPA CSV nested values safely

**Files:**

- Modify: `scripts/rpa_io.py:18-32,132-153`
- Modify: `tests/test_rpa_io.py:178-205`
- Create: `tests/fixtures/yuntu_rpa_export_sample.csv`

- [ ] **Step 1: Write failing fixture tests**

Create this scrubbed fixture:

```text
title\x01material_id\x01object_index\x01people_tag_entry\x01material_tag_entry
重新养自己\x017634882327689232430\x01{'ctr': 0.0179577342, 'show_cnt': '316521', 'publish_time': '20260502'}\x01[{'people_tag_type': 4, 'tag_name_list': ['都市银发', '新锐白领']}]\x01[{'material_tag_type': 43, 'tag_name_list': ['全场五折']}]
```

Add to `RpaIoTests`:

```python
def test_parse_csv_records_decodes_python_literal_cells_from_rpa_fixture(self):
    record = load_module().parse_csv_records(ROOT / "tests" / "fixtures" / "yuntu_rpa_export_sample.csv")[0]
    self.assertEqual(record["object_index"]["ctr"], 0.0179577342)
    self.assertEqual(record["object_index"]["show_cnt"], "316521")
    self.assertEqual(record["people_tag_entry"][0]["tag_name_list"], ["都市银发", "新锐白领"])

def test_parse_csv_records_keeps_unparseable_nested_cell_as_text(self):
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "broken.csv"
        source.write_text("material_id\\x01object_index\\n101\\x01{'ctr': nope}\\n", encoding="utf-8")
        record = load_module().parse_csv_records(source)[0]
    self.assertEqual(record["object_index"], "{'ctr': nope}")
```

- [ ] **Step 2: Run the focused tests and verify the first test fails**

Run: `python -m unittest tests.test_rpa_io.RpaIoTests.test_parse_csv_records_decodes_python_literal_cells_from_rpa_fixture tests.test_rpa_io.RpaIoTests.test_parse_csv_records_keeps_unparseable_nested_cell_as_text -v`

Expected: the literal fixture test fails because `_decode_json_cell` only calls `json.loads`; malformed input remains a string.

- [ ] **Step 3: Implement safe literal decoding**

Add `import ast`, then replace `_decode_json_cell` with:

```python
def _decode_json_cell(value):
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text or text[0] not in "[{":
        return "" if not text else value
    for decoder in (json.loads, ast.literal_eval):
        try:
            decoded = decoder(text)
        except (ValueError, SyntaxError, json.JSONDecodeError):
            continue
        if isinstance(decoded, (dict, list)):
            return decoded
    return value
```

Never use `eval`; only decoded `dict` and `list` values may enter structured downstream processing.

- [ ] **Step 4: Run focused and module-level IO tests**

Run: `python -m unittest tests.test_rpa_io -v`

Expected: PASS, preserving existing JSON, delimiter, envelope, and download behavior.

- [ ] **Step 5: Commit parser compatibility**

Run: `git add scripts/rpa_io.py tests/test_rpa_io.py tests/fixtures/yuntu_rpa_export_sample.csv && git commit -m "fix: parse yuntu RPA literal CSV fields"`

### Task 2: Preserve normalization availability and second-level trend data

**Files:**

- Modify: `scripts/yuntu_normalizer.py:63-165`
- Modify: `tests/test_yuntu_normalizer.py:19-111`

- [ ] **Step 1: Write failing availability tests**

Extend the existing normalized list assertion with:

```python
self.assertEqual(records[0]["data_availability"], {
    "metrics": {"available": True, "missing_reason": ""},
    "people_tags": {"available": True, "missing_reason": ""},
    "material_tags": {"available": True, "missing_reason": ""},
})
```

Add a list input whose nested fields remain strings and expect `unparsed_source_value`. Extend the detail test with:

```python
self.assertEqual(record["data_availability"]["trends"], {"available": True, "missing_reason": ""})
self.assertTrue(record["data_availability"]["high_points"]["available"])
self.assertTrue(record["data_availability"]["loss_points"]["available"])
```

Add a detail input with `trends: "not a list"` and expect a trend reason of `unparsed_source_value`.

- [ ] **Step 2: Run tests and verify availability assertions fail**

Run: `python -m unittest tests.test_yuntu_normalizer -v`

Expected: FAIL because records lack `data_availability`.

- [ ] **Step 3: Implement availability helpers and attach them**

Add these helpers above `normalize_list_records`:

```python
def _availability(value, *, has_values):
    if has_values:
        return {"available": True, "missing_reason": ""}
    if value in (None, "") or value == []:
        return {"available": False, "missing_reason": "source_empty"}
    if isinstance(value, str):
        return {"available": False, "missing_reason": "unparsed_source_value"}
    return {"available": False, "missing_reason": "no_usable_values"}

def _detail_availability(trends, trend_series, high_points, loss_points):
    return {
        "trends": _availability(trends, has_values=bool(trend_series)),
        "high_points": _availability(trends, has_values=bool(high_points)),
        "loss_points": _availability(trends, has_values=bool(loss_points)),
    }
```

Within list normalization retain the raw nested values and attach an availability object for metrics, people tags, and material tags. Within detail normalization attach `_detail_availability(trends, trend_series, high_points, loss_points)`.

- [ ] **Step 4: Run normalizer and batch tests**

Run: `python -m unittest tests.test_yuntu_normalizer tests.test_yuntu_batch -v`

Expected: PASS; batch status and retry semantics remain unchanged.

- [ ] **Step 5: Commit normalization fidelity**

Run: `git add scripts/yuntu_normalizer.py tests/test_yuntu_normalizer.py && git commit -m "feat: expose yuntu normalized data availability"`

### Task 3: Build auditable commercial-analysis facts

**Files:**

- Modify: `scripts/yuntu_analysis.py:1-101`
- Modify: `tests/test_yuntu_analysis.py:20-130`

- [ ] **Step 1: Write failing comparison, sample-rule, trend, and degradation tests**

Replace the one-material test fixture with four list records and two selected materials. Include `ctr`, `show_cnt`, `play_3s_rate`, `play_5s_rate`, `play_over_rate`, `play_duration_avg`, tags, and click/loss trend points. Assert:

```python
self.assertEqual(data["schemaVersion"], 2)
self.assertEqual(data["candidatePool"]["count"], 4)
self.assertEqual(data["candidatePool"]["metrics"]["ctr"]["median"], 0.25)
self.assertEqual(data["materialFacts"][0]["metricComparison"]["ctr"]["tier"], "high")
self.assertTrue(data["tagInsights"]["eligibleForAssociation"])
self.assertEqual(data["trendSummary"]["byTrendName"]["点击指数"]["highPointCount"], 2)
self.assertEqual(data["trendSummary"]["byTrendName"]["流失指数"]["lossPointCount"], 2)
```

Add a separate three-candidate case that asserts `eligibleForAssociation is False`, no `high` tier is emitted, and unavailable selected fields contribute their missing reason to `dataAvailabilitySummary`.

- [ ] **Step 2: Run analysis tests and verify failure**

Run: `python -m unittest tests.test_yuntu_analysis -v`

Expected: FAIL because the current fact pack has schema version 1 without candidate-pool, metric-comparison, trend-summary, or availability-summary structures.

- [ ] **Step 3: Implement deterministic metric helpers**

Add `from statistics import median`, then add:

```python
def _numeric_metric_values(records, metric_name):
    return [record["metrics"][metric_name] for record in records
            if isinstance(record.get("metrics", {}).get(metric_name), (int, float))]

def _percentile_rank(values, value):
    return sum(candidate <= value for candidate in values) / len(values)

def _metric_summary(records, metric_name):
    values = _numeric_metric_values(records, metric_name)
    if not values:
        return None
    return {"count": len(values), "mean": sum(values) / len(values), "median": median(values)}

def _metric_comparison(record, pool_records, pool_size):
    comparison = {}
    for name in sorted(record.get("metrics", {})):
        values = _numeric_metric_values(pool_records, name)
        if values:
            percentile = _percentile_rank(values, record["metrics"][name])
            comparison[name] = {"value": record["metrics"][name], "percentile": percentile,
                                "tier": "high" if pool_size >= 4 and percentile >= 0.75 else "observed"}
    return comparison
```

Implement companion helpers that aggregate tags as `{count, materialCount, selectedMaterialCount}`, set association eligibility only when the pool has at least four records and a tag covers at least two materials, count high/loss points by `trend_name`, and count unavailable reasons across selected list/detail facts.

- [ ] **Step 4: Replace fact-pack assembly and the model prompt contract**

Set `schemaVersion` to `2`; add `candidatePool`, `dataAvailabilitySummary`, `tagInsights`, `trendSummary`, and per-material `metricComparison`, while retaining raw metrics, tags, high points, and loss points. Use all list records as the pool and selected materials as the detail-diagnosis subset.

Require six model keys in `_prompt_text()`: `rankingOverview`, `materialComparison`, `materialDiagnoses`, `competitorPatterns`, `xiaoxianDunOpportunityMap`, and `experimentMatrix`. Require evidence and material IDs for material conclusions. Require every experiment to have `priority`, `hypothesis`, `creative_variable`, `target_audience`, `success_metric`, `control`, and `review_action`. Require “数据不足以判断” for absent facts and prohibit unverified health or efficacy claims.

- [ ] **Step 5: Run analysis tests**

Run: `python -m unittest tests.test_yuntu_analysis -v`

Expected: PASS with deterministic means, medians, percentiles, sample-size gates, trend counts, availability summaries, and the six-key prompt contract.

- [ ] **Step 6: Commit commercial facts**

Run: `git add scripts/yuntu_analysis.py tests/test_yuntu_analysis.py && git commit -m "feat: add xiaoxian dun commercial analysis facts"`

### Task 4: Validate and render the six-chapter Xiaoxian Dun report

**Files:**

- Modify: `scripts/yuntu_report.py:12-93`
- Modify: `tests/test_yuntu_report.py:20-92`

- [ ] **Step 1: Write failing tests for the structured six-section input**

Make `analysis_json()` return:

```python
{
    "rankingOverview": [{"summary": "竞品出现价格利益点。", "material_ids": ["101"], "evidence": [{"metric": "ctr", "value": 0.7}]}],
    "materialComparison": [{"material_id": "101", "summary": "CTR 位于候选池高位。", "evidence": [{"metric": "ctr", "value": 0.7}]}],
    "materialDiagnoses": [{"material_id": "101", "summary": "第 1-2 秒出现点击高点。", "evidence": [{"trend_name": "点击指数", "start_sec": 1, "end_sec": 2}]}],
    "competitorPatterns": [{"summary": "价格利益点前置。", "material_ids": ["101"], "evidence": [{"tag": "限时抢购"}]}],
    "xiaoxianDunOpportunityMap": [{"summary": "测试通勤滋补场景。", "material_ids": ["101"], "evidence": [{"tag": "商品展示(有语音)"}]}],
    "experimentMatrix": [{"priority": "P1", "hypothesis": "通勤开场提升 3 秒播放率", "creative_variable": "前 3 秒场景钩子", "target_audience": "新锐白领", "success_metric": "play_3s_rate", "control": "现有商品直展示素材", "review_action": "按人群拆分复盘"}],
}
```

Assert Markdown contains all six confirmed titles. Delete an `evidence` field and a `control` field in separate tests, each expecting `YuntuReportError`.

- [ ] **Step 2: Run report tests and verify failure**

Run: `python -m unittest tests.test_yuntu_report -v`

Expected: FAIL because the old generic eight-key contract is still enforced.

- [ ] **Step 3: Implement the report contract and nested validation**

Replace the top-level fields and titles with:

```python
REQUIRED_FIELDS = ("rankingOverview", "materialComparison", "materialDiagnoses", "competitorPatterns", "xiaoxianDunOpportunityMap", "experimentMatrix")
SECTION_TITLES = (("01｜榜单机会总览", "rankingOverview"), ("02｜素材表现对比", "materialComparison"), ("03｜单素材秒级诊断", "materialDiagnoses"), ("04｜竞品创意模式", "competitorPatterns"), ("05｜小仙炖机会地图", "xiaoxianDunOpportunityMap"), ("06｜下一轮实验矩阵", "experimentMatrix"))
```

Add `_validate_evidence_section(items, field)` to require a nonempty list, an `evidence` list, and either numeric-string `material_id` or a nonempty `material_ids` list in the first five sections. Add `_validate_experiments(items)` to require the seven experiment keys from Task 3, each with a nonblank string. Call both from `_load_analysis`. Render only these six sections; remove the separate “秒级趋势洞察” appendix.

- [ ] **Step 4: Run report tests and inspect report output**

Run: `python -m unittest tests.test_yuntu_report -v`

Expected: PASS; Markdown and HTML contain exactly six business chapters and reject missing evidence or incomplete experiments.

- [ ] **Step 5: Commit the report contract**

Run: `git add scripts/yuntu_report.py tests/test_yuntu_report.py && git commit -m "feat: render xiaoxian dun strategy report"`

### Task 5: Document the complete skill workflow and run regression

**Files:**

- Modify: `SKILL.md:1-139`
- Modify: `tests/test_skill_contract.py:111-140`
- Verify: `scripts/rpa_connector.py:701-806`

- [ ] **Step 1: Write a failing skill-contract test**

Add this method to `AnalysisSkillContractTests`:

```python
def test_documents_xiaoxian_dun_closed_loop_report(self):
    skill = self.read_skill()
    for chapter in (
        "榜单机会总览", "素材表现对比", "单素材秒级诊断",
        "竞品创意模式", "小仙炖机会地图", "下一轮实验矩阵",
    ):
        self.assertIn(chapter, skill)
    self.assertIn("Python 字面量", skill)
    self.assertIn("数据不足以判断", skill)
    self.assertNotIn("数据范围与可信度", skill)
    self.assertNotIn("风险与待补数据", skill)
```

- [ ] **Step 2: Run the new contract test and verify failure**

Run: `python -m unittest tests.test_skill_contract.AnalysisSkillContractTests.test_documents_xiaoxian_dun_closed_loop_report -v`

Expected: FAIL because `SKILL.md` documents a generic fact/report flow without the six Xiaoxian Dun chapters or literal-cell behavior.

- [ ] **Step 3: Document the operator workflow in `SKILL.md`**

Update the description and workflow prose to state that the skill produces a Xiaoxian Dun competitive-content strategy report. Add a `## 商业分析与报告` section with the six confirmed chapter titles, safe support for standard JSON and Python literals in CSV nested fields, the mandatory fallback “数据不足以判断”, and the six-key AI JSON contract before `render-report`. Do not add the two excluded chapter names anywhere in `SKILL.md`.

- [ ] **Step 4: Run contractual and offline end-to-end regression**

Run: `python -m unittest tests.test_skill_contract tests.test_rpa_io tests.test_yuntu_normalizer tests.test_yuntu_batch tests.test_yuntu_analysis tests.test_yuntu_report -v`

Expected: PASS.

Run: `python scripts/rpa_connector.py self-test`

Expected: `self-test passed`.

- [ ] **Step 5: Run the full suite and inspect the final change set**

Run: `python -m unittest discover -s tests -v && git diff --check && git status --short`

Expected: all tests PASS, no whitespace errors, and the pre-existing untracked `RPA数据汇总/` remains unstaged.

- [ ] **Step 6: Commit operator documentation**

Run: `git add SKILL.md tests/test_skill_contract.py && git commit -m "docs: complete xiaoxian dun analysis workflow"`

## Plan Self-Review

- Spec coverage: Tasks 1-2 cover safe CSV conversion and field-level availability. Task 3 covers candidate-pool comparison, tag and trend analysis, degradation, and the Xiaoxian Dun prompt contract. Task 4 implements evidence-based six-section report validation and rendering. Task 5 documents the operator flow and runs the complete regression suite.
- Placeholder scan: every task specifies exact target files, assertions, functions or fields, commands, expected outcomes, and commit boundaries.
- Type consistency: CSV parsing emits only safely decoded `dict`/`list` nested values; normalizers write `data_availability`; the fact pack consumes that structure and requires the six analysis keys; the renderer validates and renders those same keys.
