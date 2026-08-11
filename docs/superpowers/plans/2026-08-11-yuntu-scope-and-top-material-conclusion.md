# 云图数据边界与 TOP 素材结论 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为报告生成稳定的数据范围对象，并重构 `01｜TOP 素材组合结论` 为含综合结论、可见口径和品牌 TOP 对比的可审计页面。

> **2026-08-11 口径变更：** 本计划中已完成的 `brand_top30` 实现仅作为历史阶段产物，不再符合当前目标。后续需先返工 01 章：删除“品牌筛选 TOP30”整体分析和可见范围，仅保留 `ranking`（TOP1000）与 `detail`（成功秒级拆解）两种报告口径；各品牌 TOP 对比必须以 `detail` 成功素材集合为唯一分析样本。本计划的已完成勾选记录保留，以准确反映此前实施历史。

**Architecture:** `scripts/yuntu_analysis.py` 从已存在的候选榜单、筛选参数、选中详情和拒绝详情中生成 `reportScopes`，随事实包进入分析模型。模型输出在既有 `topMaterialCombination` 下增加带证据的 `executiveSummary`。`scripts/yuntu_report.py` 负责验证并渲染这些字段；不让模板或浏览器端脚本推断数据口径。

**Tech Stack:** Python 3、`unittest`、内联 HTML/CSS/JavaScript、静态离线报告。

---

### Task 1: 生成可审计的报告数据范围

**Files:**
- Modify: `scripts/yuntu_analysis.py:24-60, 400-460`
- Test: `tests/test_yuntu_analysis.py`

- [x] **Step 1: 写入失败测试，要求事实包同时包含榜单、品牌 TOP30 与详情层范围**

```python
def test_build_fact_pack_emits_report_scopes_for_ranking_brand_and_detail(self):
    result = analysis.prepare_analysis(input_dir=root, output_dir=root / "diagnostic-analysis")
    self.assertEqual(result, 0)
    fact_pack = json.loads((root / "diagnostic-analysis" / "yuntu-analysis-data.json").read_text(encoding="utf-8"))
    self.assertEqual(fact_pack["reportScopes"]["ranking"]["sample_count"], 4)
    self.assertEqual(fact_pack["reportScopes"]["brand_top30"]["sample_count"], 4)
    self.assertEqual(fact_pack["reportScopes"]["detail"]["success_count"], 2)
    self.assertEqual(fact_pack["reportScopes"]["detail"]["failed_count"], 1)
```

- [x] **Step 2: 执行失败测试并确认失败原因是缺少 `reportScopes`**

Run: `python -m unittest tests.test_yuntu_analysis.YuntuAnalysisTests.test_build_fact_pack_emits_report_scopes_for_ranking_brand_and_detail -v`

Expected: `KeyError: 'reportScopes'`。

- [x] **Step 3: 实现最小范围生成器并写入事实包**

```python
def _report_scopes(pool_records, selected, rejected, filters):
    ranking_count = len(pool_records)
    return {
        "ranking": {
            "source_name": "TOP1000 榜单素材",
            "sample_count": ranking_count,
            "selection_rule": "按请求筛选条件取得的榜单候选池",
            "limitations": [],
        },
        "brand_top30": {
            "source_name": "品牌筛选 TOP30",
            "sample_count": min(30, ranking_count),
            "selection_rule": "按请求品牌筛选后，按榜单排名取前 30 条",
            "limitations": ["品牌归属由可审计标题规则确定，不是 RPA 原生品牌字段"],
        },
        "detail": {
            "source_name": "单素材秒级详情",
            "sample_count": len(selected) + len(rejected),
            "success_count": len(selected),
            "failed_count": len(rejected),
            "selection_rule": "从候选池入选素材中实际成功取得的秒级详情",
            "limitations": [],
        },
    }
```

将返回值放入 `fact_pack["reportScopes"]`，并将 `report_scopes` 作为 `_model_input_sections()` 的新参数，在其返回对象加入同名字段。

- [x] **Step 4: 重新运行单测并确认通过**

Run: `python -m unittest tests.test_yuntu_analysis.YuntuAnalysisTests.test_build_fact_pack_emits_report_scopes_for_ranking_brand_and_detail -v`

Expected: `OK`。

### Task 2: 扩展 01 章分析契约并验证综合结论

**Files:**
- Modify: `scripts/yuntu_analysis.py:375-390`
- Modify: `scripts/yuntu_report.py:230-305`
- Test: `tests/test_yuntu_report.py`

- [x] **Step 1: 写入失败测试，要求 01 章分析有综合结论及完整证据**

```python
def test_render_report_rejects_top_material_combination_without_executive_summary(self):
    report = load_module()
    analysis = self.analysis_json()
    analysis["topMaterialCombination"].pop("executiveSummary", None)
    analysis_path.write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
    with self.assertRaisesRegex(report.YuntuReportError, "executiveSummary"):
        report.render_report(analysis_json=analysis_path, output_dir=output_dir)
```

测试夹具中的 `executiveSummary` 使用以下最小结构：

```python
{
    "summary": "综合结论：榜单、人群、卖点和已取得详情共同指向明确的内容机会。",
    "material_ids": ["101"],
    "evidence": [{"scope": "ranking"}, {"scope": "brand_top30"}, {"scope": "detail"}],
}
```

- [x] **Step 2: 执行失败测试并确认当前校验未要求 `executiveSummary`**

Run: `python -m unittest tests.test_yuntu_report.YuntuReportTests.test_render_report_rejects_top_material_combination_without_executive_summary -v`

Expected: `FAIL`，因为当前不会抛出异常。

- [x] **Step 3: 更新模型提示和输入校验**

在 `_prompt_text()` 的 `topMaterialCombination` 契约中新增 `executiveSummary`，要求它引用 `ranking`、`brand_top30` 和 `detail` 三种范围中实际可用的证据。更新 `_validate_top_material_combination()`：

```python
executive_summary = value.get("executiveSummary")
if not isinstance(executive_summary, dict):
    raise YuntuReportError("topMaterialCombination.executiveSummary must be an object")
_validate_summary(executive_summary.get("summary"), "topMaterialCombination.executiveSummary summary")
_validate_evidence_and_material_ids(executive_summary, "topMaterialCombination.executiveSummary")
```

- [x] **Step 4: 重新运行契约单测并确认通过**

Run: `python -m unittest tests.test_yuntu_report.YuntuReportTests.test_render_report_rejects_top_material_combination_without_executive_summary -v`

Expected: `OK`。

### Task 3: 渲染 01 章综合结论和可见数据范围

**Files:**
- Modify: `scripts/yuntu_report.py:882-947, 1453-1488`
- Modify: `assets/report/unified-report.css`
- Test: `tests/test_yuntu_report.py`

- [x] **Step 1: 写入失败测试，验证读者可见的范围与综合结论**

```python
def test_render_report_shows_top_material_scope_and_executive_summary(self):
    report = load_module()
    analysis_path.write_text(json.dumps(self.analysis_json(), ensure_ascii=False), encoding="utf-8")
    report.render_report(analysis_json=analysis_path, output_dir=output_dir, fact_pack={
        "reportScopes": {
            "ranking": {"source_name": "TOP1000 榜单素材", "sample_count": 1000},
            "brand_top30": {"source_name": "品牌筛选 TOP30", "sample_count": 30},
            "detail": {"source_name": "单素材秒级详情", "success_count": 5, "failed_count": 1},
        }
    })
    rendered = (output_dir / "final-report.html").read_text(encoding="utf-8")
    self.assertIn("综合结论", rendered)
    self.assertIn("TOP1000 榜单素材：1000 条", rendered)
    self.assertIn("品牌筛选 TOP30：30 条", rendered)
    self.assertIn("单素材秒级详情：5 条成功，1 条失败", rendered)
    self.assertIn("标题匹配归属", rendered)
```

- [x] **Step 2: 执行失败测试并确认缺少可见范围信息**

Run: `python -m unittest tests.test_yuntu_report.YuntuReportTests.test_render_report_shows_top_material_scope_and_executive_summary -v`

Expected: `FAIL`，因为当前 HTML 中没有“综合结论”和范围文字。

- [x] **Step 3: 实现 01 章渲染组件**

在 `top_material_combination_cards()` 前增加 `scope_badge()`，为三种范围生成转义后的标签；在返回 HTML 的第一个元素中渲染：

```html
<div class="top-material-scope" aria-label="01 章数据范围">
  <span class="report-scope-badge">TOP1000 榜单素材：1000 条</span>
  <span class="report-scope-badge">品牌筛选 TOP30：30 条</span>
  <span class="report-scope-badge">单素材秒级详情：5 条成功，1 条失败</span>
</div>
<article class="top-material-executive yuntu-content-card">
  <h3>综合结论</h3><p>...</p>
</article>
```

为每个品牌面板在正文开头渲染：

```html
<p class="brand-classification-note">品牌归属：标题匹配归属</p>
```

在 `unified-report.css` 中使用现有暖金、米白和边框变量实现换行范围标签与结论卡；不新增内联样式，不改变其他章节布局。

- [x] **Step 4: 运行 01 章相关单测并确认通过**

Run: `python -m unittest tests.test_yuntu_report.YuntuReportTests.test_render_report_writes_conclusion_only_report_without_evidence tests.test_yuntu_report.YuntuReportTests.test_render_report_shows_top_material_scope_and_executive_summary -v`

Expected: `OK`。

### Task 4: 执行回归与真实产物重渲染

**Files:**
- Test: `tests/test_yuntu_analysis.py`
- Test: `tests/test_yuntu_report.py`

- [x] **Step 1: 运行两个模块完整测试集**

Run: `python -m unittest tests.test_yuntu_analysis tests.test_yuntu_report -v`

Expected: `OK`，无失败、无错误。

- [x] **Step 2: 使用现有真实事实包和分析 JSON 重渲染到临时目录**

Run: `python scripts/yuntu_report.py --analysis-json '<真实 yuntu-ai-analysis.json>' --fact-pack '<真实 yuntu-analysis-data.json>' --output-dir '<临时输出目录>'`

Expected: 返回码 0，输出 `final-report.html`、`final-report.md`、`final-report-data.json`。

- [x] **Step 3: 检查输出结构**

Run: `rg -n '综合结论|TOP1000 榜单素材|品牌筛选 TOP30|单素材秒级详情|标题匹配归属' '<临时输出目录>/final-report.html'`

Expected: 四类文本均存在，且不出现未替换模板占位符。
