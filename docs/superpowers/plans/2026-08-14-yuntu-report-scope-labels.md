# 云图报告章节范围标签 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为读者可见的报告章节显示实际数据范围，并删除 05 章内部高光帧覆盖率文案。

**Architecture:** 复用事实包中既有的 `reportScopes`。报告模板负责容纳每章的可选范围标签，章节渲染器按固定映射注入标签；不修改事实包或 `final-report-data.json` 的输出契约。

**Tech Stack:** Python 3、`unittest`、静态 HTML/CSS/JavaScript。

---

### Task 1: 锁定章节范围与 05 文案契约

**Files:**
- Modify: `tests/test_yuntu_report.py`

- [ ] **Step 1: 写入失败测试。**

```python
self.assertIn('aria-label="02 章数据范围"', rendered)
self.assertIn('aria-label="04 章数据范围"', rendered)
self.assertIn('aria-label="05 章数据范围"', rendered)
self.assertNotIn('aria-label="03 章数据范围"', rendered)
self.assertNotIn("高光帧可用：", rendered)
```

- [ ] **Step 2: 运行定向测试并确认失败。**

Run: `python3 -m unittest tests.test_yuntu_report.YuntuReportTests.test_render_report_renders_section_scope_labels_without_deep_frame_coverage -v`

Expected: FAIL，因为目前只有 01 章注入范围标签，05 仍输出覆盖率文案。

### Task 2: 注入范围标签并删除覆盖率文案

**Files:**
- Modify: `scripts/templates/final-report-template.html`
- Modify: `scripts/yuntu_report.py`
- Modify: `scripts/yuntu_report_sections.py`

- [ ] **Step 1: 为 01、02、04、05 章节增加可选范围标签占位符。**

```html
<header class="section-header"><h2>02｜人群洞察</h2>$audience_scope</header>
```

- [ ] **Step 2: 以最小映射生成标签。**

```python
section_scopes = {
    "top_material_scope": ("01", ("ranking", "detail")),
    "audience_scope": ("02", ("ranking",)),
    "highlight_scope": ("04", ("detail",)),
    "material_deep_dive_scope": ("05", ("detail",)),
}
```

每个标签显示事实包来源名与实际样本数；03 不传入范围标签。

- [ ] **Step 3: 从 05 正常帧区移除覆盖率段落。**

```python
"".join(frame_cards) + '</div></div><div class="deep-frame-observations">'
```

无可用帧时继续渲染现有不可用提示与失败原因。

- [ ] **Step 4: 运行定向测试并确认通过。**

Run: `python3 -m unittest tests.test_yuntu_report.YuntuReportTests.test_render_report_renders_section_scope_labels_without_deep_frame_coverage -v`

Expected: PASS。

### Task 3: 回归与真实数据验收

**Files:**
- Test: `tests/test_yuntu_report.py`

- [ ] **Step 1: 执行报告测试与静态检查。**

Run: `python3 -m unittest tests.test_yuntu_report -q && python3 -m py_compile scripts/yuntu_report.py scripts/yuntu_report_sections.py && node --check assets/report/unified-report.js && git diff --check`

Expected: PASS。

- [ ] **Step 2: 使用已验证 provenance 三件套重渲染真实报告。**

Run: `python3 scripts/rpa_connector.py render-report --analysis-json '<analysis>' --fact-pack-json '<fact-pack>' --analysis-provenance '<provenance>' --output-dir '<phase-scope-labels-report>'`

Expected: 02 为 TOP1000，04/05 为成功秒级拆解素材，03 无范围标签，05 无覆盖率文案，离线图片引用完整。

## Plan Self-review

- 覆盖了已确认的四章范围映射、03 排除、05 文案删除与真实报告验收。
- 未修改 `reportScopes` 事实包结构、04 的零秒封面规则或 `final-report-data.json`。
- 无占位实现步骤；实际输入路径在执行时使用当前已验证批次。
