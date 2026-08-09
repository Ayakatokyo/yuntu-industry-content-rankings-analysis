# 云图单素材深度分析帧优先 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 05 重构为没有视频 URL 依赖、六张高光帧填满视觉区的千川式单素材分析面板。

**Architecture:** 只改报告 HTML 视图层和其单元测试。Python 输出语义化的结构、内嵌 CSS 与 JavaScript；不修改高光帧事实生成、模型契约或云图 RPA。数据仍来自已校验的 `materialDeepDives`、`highlightFrames` 和 `secondLevelBreakdown`。

**Tech Stack:** Python 3、`unittest`、内嵌 HTML/CSS/vanilla JavaScript。

---

### Task 1: 锁定帧优先面板契约

**Files:**
- Modify: `tests/test_yuntu_report.py:526-541`
- Modify: `scripts/yuntu_report.py:1021-1135`

- [ ] **Step 1: 写入失败测试，要求千川式材料容器和无视频渲染。**

```python
self.assertIn('class="material-deep-layout side-tabs"', rendered)
self.assertIn('class="material-deep-tab-list"', rendered)
self.assertIn('class="deep-visual-strip"', rendered)
self.assertIn('class="deep-frame-grid fixed-six"', rendered)
self.assertNotIn('<video', rendered)
```

- [ ] **Step 2: 运行失败测试。**

Run: `python3 -m unittest tests.test_yuntu_report.YuntuReportTests.test_render_report_renders_material_deep_dive_with_tabs_frames_and_five_charts -v`

Expected: FAIL because the current renderer uses horizontal tabs and no `deep-visual-strip` or `fixed-six` class.

- [ ] **Step 3: 最小化改造面板和帧渲染。**

```python
return (
    '<div class="material-deep-layout side-tabs">'
    '<div class="material-deep-tab-list" role="tablist" ...>' + ''.join(tabs) + '</div>'
    '<div class="material-deep-panels">' + ''.join(panels) + '</div></div>'
)
```

面板的 `deep-visual-strip` 只包含 `deep-frame-grid fixed-six`；每帧使用 `figure`、大图按钮和 `figcaption`，不生成 `video` 相关 HTML。

- [ ] **Step 4: 运行测试验证通过。**

Run: `python3 -m unittest tests.test_yuntu_report.YuntuReportTests.test_render_report_renders_material_deep_dive_with_tabs_frames_and_five_charts -v`

Expected: PASS.

### Task 2: 实现独立高光帧观察和可用性回退

**Files:**
- Modify: `tests/test_yuntu_report.py`
- Modify: `scripts/yuntu_report.py:1021-1135`

- [ ] **Step 1: 写入失败测试，要求独立观察区和失败原因。**

```python
self.assertIn('class="deep-frame-observations"', rendered)
self.assertIn('高光帧可用：0/2', rendered)
self.assertIn('视频链接已过期', rendered)
```

测试夹具给一条素材的两个 `highlightFrames` 设为 `available=False`，并附上 `failure_reason="视频链接已过期"`。

- [ ] **Step 2: 运行失败测试。**

Run: `python3 -m unittest tests.test_yuntu_report.YuntuReportTests.test_render_report_reports_unavailable_deep_dive_frames -v`

Expected: FAIL because the renderer currently只过滤失败帧。

- [ ] **Step 3: 生成帧覆盖说明与独立观察区。**

```python
frame_note = f"高光帧可用：{len(frames)}/{len(all_frames)}"
if reasons:
    frame_note += "；" + "；".join(reasons)
```

成功帧的逐帧观察写入 `deep-frame-observations`，素材级总结保留在其后的 `deep-visual-summary`；没有成功帧时不输出图片元素。

- [ ] **Step 4: 运行测试验证通过。**

Run: `python3 -m unittest tests.test_yuntu_report.YuntuReportTests.test_render_report_reports_unavailable_deep_dive_frames -v`

Expected: PASS.

### Task 3: 将五张静态图替换为千川式单图秒级拆解

**Files:**
- Modify: `tests/test_yuntu_report.py`
- Modify: `scripts/yuntu_report.py:1021-1320`

- [ ] **Step 1: 写入失败测试，要求指标切换、单图语义与范围控制。**

```python
self.assertIn('data-second-level-metric="点赞指数"', rendered)
self.assertIn('class="second-level-timeline"', rendered)
self.assertIn('class="second-level-range-control"', rendered)
self.assertIn('data-second-level-point', rendered)
self.assertEqual(rendered.count('class="second-level-chart"'), 0)
```

- [ ] **Step 2: 运行失败测试。**

Run: `python3 -m unittest tests.test_yuntu_report.YuntuReportTests.test_render_report_renders_second_level_timeline_interactions -v`

Expected: FAIL because the report currently renders ten static mini charts.

- [ ] **Step 3: 输出五条指标数据并加入内联交互脚本。**

```python
timeline_payload = json.dumps(metrics, ensure_ascii=False)
timeline = '<div class="second-level-timeline" data-second-level-timeline data-metrics="' + html.escape(timeline_payload, quote=True) + '"></div>'
```

JavaScript 选择默认可用指标，重绘单个 SVG 的轴、区间、折线、可聚焦点位、峰值注记和 `input[type=range]`；不可用指标展示事实包的 `missing_reason`。高点与流失区间保持为不同颜色覆盖层。

- [ ] **Step 4: 运行测试验证通过。**

Run: `python3 -m unittest tests.test_yuntu_report.YuntuReportTests.test_render_report_renders_second_level_timeline_interactions -v`

Expected: PASS.

### Task 4: 对齐桌面视觉样式并回归

**Files:**
- Modify: `scripts/yuntu_report.py:1186-1235`
- Test: `tests/test_yuntu_report.py`

- [ ] **Step 1: 调整 CSS。**

```css
.material-deep-layout.side-tabs { display:grid; grid-template-columns:220px minmax(0,1fr); }
.deep-frame-grid.fixed-six { grid-template-columns:repeat(3,minmax(0,1fr)); }
.deep-frame-grid.fixed-six img { object-fit:contain; }
```

移除 05 专用的移动端网格规则；为大图按钮、纵向页签、折线点和范围控制保留可见焦点状态。

- [ ] **Step 2: 运行定向报告测试。**

Run: `python3 -m unittest tests.test_yuntu_report -v`

Expected: PASS.

- [ ] **Step 3: 运行全量回归与静态检查。**

Run: `python3 -m unittest discover -s tests -v && git diff --check`

Expected: all tests PASS and no whitespace errors.

## Plan Self-review

- 覆盖：帧替代视频、千川式侧栏/右面板、固定六帧、独立观察、五指标单图交互、失败说明和桌面 CSS 均有任务。
- 无占位任务；所有改动都有具体文件、测试和命令。
- 类型一致：继续使用既有 `highlightFrames` 和 `secondLevelBreakdown.metrics`，不改变模型输出结构。
