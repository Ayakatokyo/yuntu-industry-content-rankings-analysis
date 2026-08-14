# 云图 AI 二次分析报告深度 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将经过证据约束的 AI 二次分析完整呈现在云图行业榜单报告中，并拒绝短句和占位分析。

**Architecture:** 保持现有事实包和分析 JSON 字段不变，在 `yuntu_report.py` 对 AI 文本执行质量门禁；`yuntu_report_sections.py` 负责将已验证的单素材字段映射到 HTML。`yuntu_analysis.py` 只负责把内容配额和写作结构传递给模型。

**Tech Stack:** Python 标准库 `unittest`、JSON、现有离线 HTML 渲染器。

---

### Task 1: 定义 AI 文本质量门禁

**Files:**
- Modify: `scripts/yuntu_report.py`
- Modify: `tests/test_yuntu_report.py`

- [ ] **Step 1: 写失败测试，短句或模板化深度字段必须被拒绝**

```python
analysis = self.deep_dive_analysis()
analysis["materialDeepDives"][0]["visual_summary"] = "该素材用于观察。"
with self.assertRaisesRegex(report.YuntuReportError, "visual_summary.*minimum"):
    report.render_report(analysis_json=path, output_dir=root / "report", fact_pack_json=fact_path)
```

- [ ] **Step 2: 运行失败测试**

Run: `python -m unittest tests.test_yuntu_report.YuntuReportTests.test_render_report_rejects_shallow_ai_deep_dive -v`

Expected: FAIL，因为当前校验只检查非空文本。

- [ ] **Step 3: 在报告校验器实现长度、占位语和重复字段门禁**

```python
AI_TEXT_MINIMUMS = {"deep_dive": 80, "frame_observation": 40}
AI_PLACEHOLDER_PATTERNS = ("事实包返回", "该素材用于观察", "该指数记录")

def _validate_ai_text(value, field, minimum):
    _validate_deep_dive_text(value, field)
    if len(value.strip()) < minimum:
        raise YuntuReportError(f"{field} is below the AI quality minimum")
    if any(token in value for token in AI_PLACEHOLDER_PATTERNS):
        raise YuntuReportError(f"{field} contains placeholder text")
```

在 `_validate_material_deep_dives` 中对 13 个摘要字段和逐帧观察调用该校验，并拒绝同一素材内重复的摘要文本。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.test_yuntu_report.YuntuReportTests.test_render_report_rejects_shallow_ai_deep_dive -v`

Expected: PASS。

### Task 2: 将单素材 AI 二次分析映射到 HTML

**Files:**
- Modify: `scripts/yuntu_report_sections.py`
- Modify: `tests/test_yuntu_report.py`

- [ ] **Step 1: 写失败测试，报告必须展示 13 个 AI 字段标签和内容**

```python
rendered = report.render_report(...).read_text(encoding="utf-8")
for label, field in report.DEEP_DIVE_FIELD_LABELS:
    self.assertIn(label, rendered)
    self.assertIn(analysis["materialDeepDives"][0][field], rendered)
```

- [ ] **Step 2: 运行失败测试**

Run: `python -m unittest tests.test_yuntu_report.YuntuReportTests.test_render_report_shows_ai_deep_dive_fields -v`

Expected: FAIL，因为当前 HTML 不消费这些字段。

- [ ] **Step 3: 在单素材卡片加入 AI 二次分析区域**

```python
ai_summary = "".join(
    '<div><dt>' + esc(label) + '</dt><dd>' + esc(dive[field]) + '</dd></div>'
    for label, field in deep_dive_field_labels
)
```

将其渲染为 `<section class="material-ai-analysis"><h4>AI 二次分析</h4><dl>...</dl></section>`，置于高光观察和秒级图表之后；通过 `render_material_deep_dive` 新参数传入既有字段标签。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.test_yuntu_report.YuntuReportTests.test_render_report_shows_ai_deep_dive_fields -v`

Expected: PASS。

### Task 3: 强化模型提示词和操作说明

**Files:**
- Modify: `scripts/yuntu_analysis.py`
- Modify: `SKILL.md`
- Modify: `tests/test_yuntu_analysis.py`

- [ ] **Step 1: 写失败测试，提示词必须包含最低长度、判断结构和四条实验要求**

```python
self.assertIn("事实锚点 -> 业务判断 -> 下一步验证", prompt)
self.assertIn("至少 80 个中文字符", prompt)
self.assertIn("至少 4 条", prompt)
```

- [ ] **Step 2: 运行失败测试**

Run: `python -m unittest tests.test_yuntu_analysis.YuntuAnalysisTests.test_prepare_analysis_writes_top_material_combination_and_prompt_contract -v`

Expected: FAIL，因为当前提示词没有内容配额。

- [ ] **Step 3: 修改提示和技能契约**

为 `materialDeepDives` 的 13 个摘要字段和 `frame_observations` 指定最小内容长度、真实事实锚点、差异化要求；为 `experimentMatrix` 指定至少四条且覆盖放量、改写、验证和风险控制。保留不展示执行过程、口径说明和未经验证健康宣称的约束。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.test_yuntu_analysis.YuntuAnalysisTests.test_prepare_analysis_writes_top_material_combination_and_prompt_contract -v`

Expected: PASS。

### Task 4: 使用真实数据回归

**Files:**
- Modify: `RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-top6-real/diagnostic-analysis/yuntu-ai-analysis.json`
- Generate: `RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-top6-real/final-report/final-report.html`

- [ ] **Step 1: 按新契约补全六条素材的 AI 二次分析**

使用真实榜单指标、秒级峰值和 35 张高光帧生成差异化文本；每条都以实际素材为证据，不将 6 条详情外推为 TOP1000 结论。

- [ ] **Step 2: 生成并验证来源回执与最终报告**

Run: `python scripts/rpa_connector.py attest-analysis ... && python scripts/rpa_connector.py render-report ...`

Expected: 输出通过来源核验的 `final-report.html`。

- [ ] **Step 3: 跑完整回归和成品扫描**

Run: `python -m unittest discover -s tests -p 'test_*.py' -v && rg -n '人群标签是重叠标签|事实包返回|该素材用于观察' RPA数据汇总/.../final-report/final-report.html`

Expected: 所有测试通过，扫描没有命中。
