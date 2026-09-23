# 云图 AI 二次分析契约升级 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让当前对话模型基于分层事实包和高光帧生成完整、可审计的视觉与单素材洞察，报告只校验和渲染这些结论。

**Architecture:** `prepare-analysis` 将既有 `materialFacts` 投影为 schema v4 的模型输入分区，同时保留旧字段。当前对话模型仍根据 `yuntu-analysis-prompt.md` 写入 JSON；`yuntu_report.py` 以事实包作为证据源，严格校验模型的帧分类、深度分析补充字段、实验引用和禁止措辞，HTML/Markdown 仅展示已校验的模型文本。

**Tech Stack:** Python 3、标准库 `unittest`、静态 HTML 模板与内联 CSS/JavaScript。

---

### Task 1: 分层事实包与图片读取清单

**Files:**
- Modify: `scripts/yuntu_analysis.py:197-307`
- Test: `tests/test_yuntu_analysis.py:53-236`

- [ ] **Step 1: Write the failing fact-pack contract test**

Add this test to `YuntuAnalysisTests` after `test_prepare_analysis_automatically_generates_standard_highlight_frames`:

```python
def test_prepare_analysis_writes_v4_model_facts_and_visual_assets(self):
    analysis = load_module()
    records = [{
        "material_id": "1", "title": "产品开盖展示", "rank": 1,
        "metrics": {"ctr": 0.2, "show_cnt": 100},
        "people_tags": ["新锐白领"], "material_tags": ["产品展示"],
        "data_availability": {"cpm": {"available": False, "missing_reason": "not_returned"}},
    }]
    selected = [{"rank": 1, "material_id": "1", "detailRecordPath": "normalized/detail-records/1.json"}]
    details = {"1": {"material_id": "1", "trend_series": [{"trend_name": "点击指数", "series": [{"second": 2, "value": 0.8}]}], "high_points": [], "loss_points": [], "data_availability": {}}}
    frames = [{"frame_ref": "highlight:1:click_peak:2", "second": 2, "frame_type": "click_peak", "peak_rank": 1, "click_value": 0.8, "available": True, "relative_path": "highlights/1/02-002s.jpg", "frame_source": "reused_local_extracted_frame"}]
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        self._write_input(root, records, selected, details)
        with mock.patch.object(analysis, "generate_standard_highlights", return_value={"1": frames}):
            analysis.prepare_analysis(input_dir=root, output_dir=root / "diagnostic-analysis")
        data = json.loads((root / "diagnostic-analysis" / "yuntu-analysis-data.json").read_text(encoding="utf-8"))
        prompt = (root / "diagnostic-analysis" / "yuntu-analysis-prompt.md").read_text(encoding="utf-8")
    self.assertEqual(data["schemaVersion"], 4)
    self.assertEqual(data["rankingFacts"]["materials"][0]["material_id"], "1")
    self.assertTrue(data["audienceFacts"]["labelsMayOverlap"])
    self.assertEqual(data["marketingFacts"]["materials"][0]["material_tags"], ["产品展示"])
    self.assertEqual(data["secondLevelFacts"]["materials"][0]["material_id"], "1")
    self.assertEqual(data["highlightFrameFacts"][0]["frame_ref"], "highlight:1:click_peak:2")
    self.assertEqual(data["visualAssets"][0]["image_path"], "highlights/1/02-002s.jpg")
    self.assertEqual(data["visualAssets"][0]["frame_source"], "reused_local_extracted_frame")
    self.assertIn("not_returned", data["dataLimitations"])
    self.assertIn("visualAssets", prompt)
    self.assertIn("实际查看每张成功 JPEG", prompt)
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
python3 -m unittest tests.test_yuntu_analysis.YuntuAnalysisTests.test_prepare_analysis_writes_v4_model_facts_and_visual_assets -v
```

Expected: FAIL because the fact pack is schema version 3 and has no `rankingFacts` or `visualAssets`.

- [ ] **Step 3: Implement the immutable projections**

In `scripts/yuntu_analysis.py`, add helpers before `prepare_analysis` that build model-facing facts from the already-normalized `material_facts`:

```python
def _model_input_sections(material_facts):
    visual_assets = []
    for fact in material_facts:
        for frame in fact.get("highlightFrames", []):
            visual_assets.append({
                "material_id": str(fact["material_id"]), "title": fact["title"], "rank": fact["rank"],
                "frame_ref": frame.get("frame_ref"), "second": frame.get("second"),
                "frame_type": frame.get("frame_type"), "peak_rank": frame.get("peak_rank"),
                "click_value": frame.get("click_value"), "image_path": frame.get("relative_path", ""),
                "available": bool(frame.get("available")), "failure_reason": frame.get("failure_reason", ""),
                "frame_source": frame.get("frame_source", "extracted_frame"),
            })
    return {
        "rankingFacts": {"materials": [{"material_id": str(fact["material_id"]), "rank": fact["rank"], "title": fact["title"], "metrics": fact["metrics"], "metricComparison": fact["metricComparison"]} for fact in material_facts]},
        "audienceFacts": {"labelsMayOverlap": True, "notice": "人群标签是重叠标签，不是真实人群分布，不能相加为 100%。", "materials": [{"material_id": str(fact["material_id"]), "people_tags": fact["people_tags"]} for fact in material_facts]},
        "marketingFacts": {"materials": [{"material_id": str(fact["material_id"]), "material_tags": fact["material_tags"]} for fact in material_facts]},
        "secondLevelFacts": {"materials": [{"material_id": str(fact["material_id"]), "metrics": fact["secondLevelBreakdown"]["metrics"]} for fact in material_facts]},
        "highlightFrameFacts": [{key: asset[key] for key in ("material_id", "frame_ref", "second", "frame_type", "peak_rank", "click_value", "available", "failure_reason")} for asset in visual_assets],
        "visualAssets": visual_assets,
        "dataLimitations": _data_limitations(material_facts),
    }
```

Use only fields already calculated in `materialFacts`; `image_path` must remain a workspace-relative asset path. `_data_limitations` must flatten unavailable list/detail states and unavailable frames into sorted, deduplicated records with `material_id`, `field`, and `reason`. Change the fact-pack schema version to `4` and merge the helper output into `fact_pack` without deleting legacy keys.

- [ ] **Step 4: Expand the current-model prompt**

Replace `_prompt_text()` with constraints that name all seven model-input partitions, require actual inspection of every successful `visualAssets[*].image_path`, and define the five ordered high-frame categories. Include this exact restriction:

```text
只能描述该帧处于点击指数峰值秒点；不得说该画面导致点击、转化或指标提升。
```

Require local frames to be reused when available even when the original video URL has expired. Preserve all existing restrictions around no scripts, no real interaction counts, no causal conclusions, and health-compliance claims.

- [ ] **Step 5: Run the focused analysis tests**

Run:

```bash
python3 -m unittest tests.test_yuntu_analysis -v
```

Expected: PASS.

### Task 2: AI output contract and evidence reference gates

**Files:**
- Modify: `scripts/yuntu_report.py:113-123, 155-169, 501-649`
- Test: `tests/test_yuntu_report.py:153-175, 610-708`

- [ ] **Step 1: Write the failing validation tests**

Update `deep_dive_analysis()` so every deep dive includes:

```python
"data_summary": "该素材在已返回的曝光和点击率指标中处于可比较范围。",
"audience_summary": "人群标签仅表示素材覆盖标签，不能相加为真实人群比例。",
"marketing_summary": "产品展示标签与画面中的产品主体共同出现。",
"replication_advice": "可测试近景产品主体与清晰包装展示的组合。",
"risk_notes": "画面结论仅限已提取帧，健康相关表达需业务与合规复核。",
"opening_judgment": "前 3 秒以稳定主体承接注意力，未推断脚本内容。",
"visual_rhythm": "已提取帧中的主体与景别有可见变化。",
"peak_frame_reading": "点击峰值秒点展示产品与人物同框的画面。",
"second_level_reading": "五类指数只按已返回秒级点位作描述。",
"audience_fit": "人群标签与画面主题的匹配仅为待验证判断。",
"replication_advice": "目标品牌可测试产品主体和日常场景的组合。",
"do_not_copy": "不直接照搬健康功效或特定人群承诺。",
```

Also add `audienceInsights` to `analysis_json()` as a normal evidence section and add an assertion that its AI-authored summary is rendered in `02｜人群洞察`. Then add three tests:

```python
def test_render_report_rejects_deep_dive_without_ai_summary_fields(self):
    report = load_module()
    analysis = self.deep_dive_analysis()
    del analysis["materialDeepDives"][0]["replication_advice"]
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        path = root / "analysis.json"
        path.write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
        with self.assertRaisesRegex(report.YuntuReportError, "replication_advice"):
            report.render_report(analysis_json=path, output_dir=root / "report", fact_pack=self.deep_dive_fact_pack())

def test_render_report_accepts_scene_and_text_overlay_highlight_groups(self):
    report = load_module()
    analysis = self.deep_dive_analysis()
    analysis["highlightDashboard"]["groups"] = [
        {"category": "scene", "frame_refs": ["highlight:101:cover:0"], "common_patterns": ["冰箱场景可见。"], "derivative_directions": []},
        {"category": "text_overlay", "frame_refs": ["highlight:101:click_peak:2", "highlight:102:cover:0", "highlight:102:click_peak:2"], "common_patterns": ["画面含可见文字信息。"], "derivative_directions": []},
    ]
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        path = root / "analysis.json"
        path.write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
        self.assertEqual(report.render_report(analysis_json=path, output_dir=root / "report", fact_pack=self.deep_dive_fact_pack()), 0)

def test_render_report_rejects_experiment_without_fact_reference(self):
    report = load_module()
    analysis = self.deep_dive_analysis()
    del analysis["experimentMatrix"][0]["evidence"]
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        path = root / "analysis.json"
        path.write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
        with self.assertRaisesRegex(report.YuntuReportError, "experimentMatrix.*reference"):
            report.render_report(analysis_json=path, output_dir=root / "report", fact_pack=self.deep_dive_fact_pack())
```

The experiment fixture must include one `evidence` item with a real `material_id`, `metric` or `frame_ref`.

- [ ] **Step 2: Run the validation tests and verify they fail**

Run:

```bash
python3 -m unittest \
  tests.test_yuntu_report.YuntuReportTests.test_render_report_rejects_deep_dive_without_ai_summary_fields \
  tests.test_yuntu_report.YuntuReportTests.test_render_report_accepts_scene_and_text_overlay_highlight_groups \
  tests.test_yuntu_report.YuntuReportTests.test_render_report_rejects_experiment_without_fact_reference -v
```

Expected: FAIL because the extra fields, categories, and reference contract are not yet enforced.

- [ ] **Step 3: Implement category and deep-dive validation**

Change the fixed labels and order to:

```python
HIGHLIGHT_CATEGORY_LABELS = {
    "portrait": "人像画面", "product": "产品画面", "scene": "场景画面",
    "text_overlay": "字幕画面", "other": "其他画面",
}
DEEP_DIVE_SUMMARY_FIELDS = (
    "visual_summary", "data_summary", "audience_summary", "marketing_summary",
    "replication_advice", "risk_notes", "opening_judgment", "visual_rhythm",
    "peak_frame_reading", "second_level_reading", "audience_fit",
    "replication_advice", "do_not_copy",
)
```

In `_validate_material_deep_dives`, call `_validate_deep_dive_text` for every `DEEP_DIVE_SUMMARY_FIELDS` value. Expand the forbidden pattern to reject `提升` in deep-dive summaries when it asserts performance causation, while retaining ordinary factual language. Keep `scene` and `text_overlay` optional and preserve strict category ordering for only the nonempty groups. In `_validate_highlight_dashboard`, apply the same safe-text validator to every common pattern and every derivative title/body so visual conclusions cannot assert scripts, real counts, conversion, or causality.

Add `audienceInsights` to `REQUIRED_FIELDS` and `EVIDENCE_FIELDS`, then call `_validate_evidence_section(analysis["audienceInsights"], "audienceInsights")`. Its summary must include `PEOPLE_TAG_OVERLAP_NOTICE`; reject an audience conclusion that presents overlapping labels as a population percentage. For schema v4 fact packs, missing `highlightDashboard` or `materialDeepDives` is a hard error whenever their corresponding successful-frame or second-level fact contracts exist; preserve the historical soft path only for pre-v4 packs.

- [ ] **Step 4: Implement experiment reference validation**

Pass `fact_pack` into experiment validation from `_load_analysis` after the pack is loaded, or run the validator inside `render_report` immediately after `_load_analysis`. Require `experimentMatrix[*].evidence` to be a nonempty list and validate each item against the fact pack:

```python
known_material_ids = set(_selected_material_ids(fact_pack))
known_frame_refs = {frame["frame_ref"] for frame in _available_highlight_frames(fact_pack)}
known_metrics = set(METRIC_LABELS) | set(SECOND_LEVEL_TRENDS)
```

An evidence item is valid only when it contains a known `material_id`, a known `frame_ref`, or a known `metric`; if it includes `second`, verify that second is present in the named material/trend. Raise `YuntuReportError("experimentMatrix items require a real fact reference")` for absent or unverifiable references.

- [ ] **Step 5: Run the focused report contract tests**

Run the command from Step 2 plus the existing unique-frame and bad-second tests:

```bash
python3 -m unittest \
  tests.test_yuntu_report.YuntuReportTests.test_render_report_rejects_invalid_material_deep_dive_frame_and_second \
  tests.test_yuntu_report.YuntuReportTests.test_render_report_rejects_highlight_frames_classified_more_than_once -v
```

Expected: PASS.

### Task 3: Render the AI-authored deep-dive fields without fallback conclusions

**Files:**
- Modify: `scripts/yuntu_report.py:405-433, 1065-1142`
- Test: `tests/test_yuntu_report.py:526-543`

- [ ] **Step 1: Write the failing rendering test**

Add this assertion to `test_render_report_renders_material_deep_dive_with_tabs_frames_and_five_charts` after updating its fixture in Task 2:

```python
self.assertIn("可测试近景产品主体与清晰包装展示的组合。", rendered)
self.assertIn("健康相关表达需业务与合规复核。", rendered)
self.assertIn("#### 数据总结", markdown)
self.assertIn("#### 复用建议", markdown)
self.assertNotIn("未输出观察。", markdown)
```

- [ ] **Step 2: Run the rendering test and verify it fails**

Run:

```bash
python3 -m unittest tests.test_yuntu_report.YuntuReportTests.test_render_report_renders_material_deep_dive_with_tabs_frames_and_five_charts -v
```

Expected: FAIL because the new model-authored summaries are not rendered.

- [ ] **Step 3: Render the six validated model fields**

In `_render_markdown`, append the fields in this exact order after `画面总结` and before `秒级拆解`:

```python
for heading, key in (
    ("数据总结", "data_summary"), ("人群总结", "audience_summary"),
    ("营销总结", "marketing_summary"), ("复用建议", "replication_advice"),
    ("风险提示", "risk_notes"),
    ("开场判断", "opening_judgment"), ("画面节奏", "visual_rhythm"),
    ("峰值帧解读", "peak_frame_reading"), ("秒级关系", "second_level_reading"),
    ("人群匹配", "audience_fit"), ("目标品牌借鉴", "replication_advice"),
    ("不建议照搬", "do_not_copy"),
):
    lines.extend([f"#### {heading}", "", dive[key], ""])
```

Replace the `未输出观察。` branch for a returned but unobserved metric with an empty string; complete new-contract analyses must include their model observation or render validation must fail. In `material_deep_dive_cards`, create one plain labeled section for every expanded summary field using these same headings and `esc(_generic_text(dive[key]))`. Do not synthesize content from frame metadata, labels, or metrics.

Render `audienceInsights` as the insight rows above the existing fact-only age, gender and crowd charts. Do not derive any audience judgement from the chart bucket values.

- [ ] **Step 4: Verify frame-first layout remains intact**

Run:

```bash
python3 -m unittest \
  tests.test_yuntu_report.YuntuReportTests.test_render_report_renders_material_deep_dive_with_tabs_frames_and_five_charts \
  tests.test_yuntu_report.YuntuReportTests.test_render_report_uses_qianchuan_style_frame_first_deep_dive_layout \
  tests.test_yuntu_report.YuntuReportTests.test_render_report_matches_reference_material_card_and_fixed_frame_strip -v
```

Expected: PASS, including no `<video>` tag and the fixed 560px 3x2 frame strip.

### Task 4: Update skill contract and run end-to-end verification

**Files:**
- Modify: `SKILL.md:112-178`
- Modify: `tests/test_yuntu_report.py:24-32`
- Test: `tests/test_yuntu_analysis.py`
- Test: `tests/test_yuntu_report.py`
- Test: `tests/test_rpa_connector.py`

- [ ] **Step 1: Write the failing documentation contract test**

Extend `test_skill_documents_unified_report_delivery_contract`:

```python
self.assertIn("rankingFacts", skill)
self.assertIn("visualAssets", skill)
self.assertIn("当前对话模型", skill)
self.assertIn("scene", skill)
self.assertIn("text_overlay", skill)
self.assertIn("replication_advice", skill)
self.assertIn("audienceInsights", skill)
self.assertIn("do_not_copy", skill)
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
python3 -m unittest tests.test_yuntu_report.YuntuReportTests.test_skill_documents_unified_report_delivery_contract -v
```

Expected: FAIL because the operating contract does not name the v4 AI input/output requirements.

- [ ] **Step 3: Update the skill operating instructions**

In `SKILL.md`, document that `prepare-analysis` writes schema v4's seven named input partitions, that the current dialogue model must read all successful local `visualAssets`, and that it writes the mandatory `highlightDashboard` and expanded `materialDeepDives` fields. State that `attest-analysis` continues to bind the output to the fact-pack/prompt hashes and that `render-report` rejects missing model conclusions rather than generating defaults.

- [ ] **Step 4: Run the complete verification suite**

Run:

```bash
python3 -m unittest discover -s tests -v
git diff --check
```

Expected: all tests pass and `git diff --check` exits with status 0.

- [ ] **Step 5: Generate and inspect a fresh report without overwriting a user artifact**

Use a new temporary output directory and the known fact pack plus a manually supplied, provenance-attested model JSON that satisfies the v4 contract. Run `render-report`, then verify:

```bash
rg -n '<video|未输出观察|脚本数据：未接入|数据总结|复用建议|风险提示' "$REPORT_PATH/final-report.html"
```

Expected: no video or rule fallback phrase; script placeholder remains; all five model-authored sections appear. Inspect the rendered deep-dive section at desktop width to confirm the 190px side tabs, 560px six-frame grid and no empty images.
