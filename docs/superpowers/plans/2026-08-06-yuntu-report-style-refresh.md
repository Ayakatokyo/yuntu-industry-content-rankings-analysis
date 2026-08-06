# 云图报告样式优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改变六章、数据口径或 JSON 契约的前提下，将云图 HTML 报告升级为适合小仙炖抖音内容团队复盘的暖色、可下钻、离线可交付页面。

**Architecture:** 仅改动 `scripts/yuntu_report.py` 的 HTML 视图层：洞察卡拆分结论、素材引用和可折叠证据，统一封面、章节、指标、标签与高光帧交互样式。`_load_analysis`、Markdown、事实包读取及图片路径判断不改变。

**Tech Stack:** Python 3、`unittest`、标准库 `html`/`json`、内嵌 HTML/CSS/JavaScript。

---

## File Structure

- Modify: `scripts/yuntu_report.py` - 调整 HTML 标记、内嵌 CSS 与 lightbox 可访问性。
- Modify: `tests/test_yuntu_report.py` - 覆盖新增视图语义、证据折叠、无障碍和失败降级。
- Modify: `SKILL.md` - 固化报告的离线交付、可下钻证据与双视口验收要求。

### Task 1: 实现洞察层级

**Files:**
- Modify: `tests/test_yuntu_report.py`
- Modify: `scripts/yuntu_report.py`

- [ ] **Step 1: 写入失败的结论、素材引用与证据折叠测试**

```python
def test_render_report_separates_insight_evidence_into_details(self):
    report = load_module()
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        analysis_path = root / "analysis.json"
        analysis_path.write_text(json.dumps(self.analysis_json(), ensure_ascii=False), encoding="utf-8")
        report.render_report(analysis_json=analysis_path, output_dir=root / "final-report")
        rendered = (root / "final-report" / "final-report.html").read_text(encoding="utf-8")
    self.assertIn('class="insight-card insight-card-primary"', rendered)
    self.assertIn('class="material-reference"', rendered)
    self.assertIn('<details class="evidence-details">', rendered)
    self.assertIn("查看数据依据", rendered)
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m unittest tests.test_yuntu_report.YuntuReportTests.test_render_report_separates_insight_evidence_into_details -v`  
Expected: FAIL，因为尚无 `insight-card-primary`、`material-reference` 和 `evidence-details`。

- [ ] **Step 3: 实现 HTML 辅助函数并接入非素材章节**

```python
def _render_material_reference(item, esc):
    material_ids = item.get("material_ids") or ([item.get("material_id")] if item.get("material_id") else [])
    links = "".join(
        f'<a class="material-reference" href="#material-{esc(material_id)}">素材 {esc(material_id)}</a>'
        for material_id in material_ids if material_id
    )
    return f'<div class="material-references">{links}</div>' if links else ""

def _render_evidence(evidence, esc):
    if not evidence:
        return ""
    rows = "".join(f"<li>{esc(json.dumps(item, ensure_ascii=False))}</li>" for item in evidence)
    return f'<details class="evidence-details"><summary>查看数据依据</summary><ul>{rows}</ul></details>'
```

将章节 cards 设为 `insight-card insight-card-primary`，以 `summary` 或 `hypothesis` 作为主体，调用 `_render_material_reference`；仅有证据时调用 `_render_evidence`。实验矩阵没有 `evidence` 时不得渲染空折叠控件。

- [ ] **Step 4: 运行定向测试并确认通过**

Run: `python -m unittest tests.test_yuntu_report.YuntuReportTests.test_render_report_separates_insight_evidence_into_details -v`  
Expected: PASS。

- [ ] **Step 5: 提交本项变更**

Run: `git add scripts/yuntu_report.py tests/test_yuntu_report.py && git commit -m "feat: improve yuntu report insight hierarchy"`

### Task 2: 对齐模板视觉系统并补足高光帧无障碍

**Files:**
- Modify: `tests/test_yuntu_report.py`
- Modify: `scripts/yuntu_report.py`

- [ ] **Step 1: 写入视觉令牌和 aria 标签的失败测试**

```python
def test_render_report_uses_template_style_tokens_and_accessible_gallery(self):
    report = load_module()
    fact_pack = {"materialFacts": [{"material_id": "101", "highlightFrames": [{
        "second": 0, "available": True, "relative_path": "../highlights/101/01-000s.jpg",
        "is_cover": True, "reasons": [{"type": "cover"}],
    }]}]}
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        analysis_path = root / "analysis.json"
        analysis_path.write_text(json.dumps(self.analysis_json(), ensure_ascii=False), encoding="utf-8")
        report.render_report(analysis_json=analysis_path, output_dir=root / "final-report", fact_pack=fact_pack)
        rendered = (root / "final-report" / "final-report.html").read_text(encoding="utf-8")
    self.assertIn("--paper:#fff8ec", rendered)
    self.assertIn("--gold:#d79a4b", rendered)
    self.assertIn('aria-label="查看封面高光帧"', rendered)
    self.assertIn('aria-label="关闭高光帧预览"', rendered)
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m unittest tests.test_yuntu_report.YuntuReportTests.test_render_report_uses_template_style_tokens_and_accessible_gallery -v`  
Expected: FAIL，因为帧按钮和关闭按钮尚无匹配的 aria 标签。

- [ ] **Step 3: 替换内嵌样式并更新帧标记**

```css
:root{--bg:#120b08;--paper:#fff8ec;--panel:rgba(255,248,236,.94);--ink:#2a170f;--muted:#806758;--gold:#d79a4b;--line:rgba(82,45,24,.15);--shadow:0 28px 80px rgba(43,23,12,.18)}
.report-cover,.section,.material-card{border:1px solid var(--line);box-shadow:var(--shadow)}
.report-cover,.section{border-radius:28px}.insight-card{border:1px solid var(--line);border-radius:16px;background:rgba(255,255,255,.72);padding:15px 16px}
.insight-card-primary{background:#fff}.evidence-details{margin-top:12px;border-top:1px solid var(--line);padding-top:10px}.evidence-details summary{cursor:pointer;color:#7d4a25;font-weight:800}
.frame-button:focus-visible,.material-reference:focus-visible{outline:3px solid var(--gold);outline-offset:2px}
@media(max-width:560px){main{width:min(100% - 20px,1260px)}.report-cover,.section,.material-card{border-radius:18px}.metric-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.highlight-gallery{grid-template-columns:repeat(3,minmax(0,1fr))}}
```

为帧按钮输出 `aria-label="查看封面高光帧"` 或 `aria-label="查看 {second} 秒高光帧"`；为关闭按钮输出 `aria-label="关闭高光帧预览"`。保留遮罩点击和 Escape，不引入外部资源。

- [ ] **Step 4: 运行样式与画廊测试**

Run: `python -m unittest tests.test_yuntu_report.YuntuReportTests.test_render_report_uses_template_style_tokens_and_accessible_gallery tests.test_yuntu_report.YuntuReportTests.test_render_report_renders_styled_cover_and_highlight_gallery -v`  
Expected: PASS。

- [ ] **Step 5: 提交本项变更**

Run: `git add scripts/yuntu_report.py tests/test_yuntu_report.py && git commit -m "feat: refresh yuntu report visual style"`

### Task 3: 固化失败降级与交付验收

**Files:**
- Modify: `tests/test_yuntu_report.py`
- Modify: `scripts/yuntu_report.py`
- Modify: `SKILL.md`

- [ ] **Step 1: 写入失败帧降级测试**

```python
def test_render_report_omits_failed_frame_but_keeps_diagnosis(self):
    report = load_module()
    fact_pack = {"materialFacts": [{"material_id": "101", "highlightFrames": [{
        "second": 0, "available": False, "failure_reason": "download_failed",
    }]}]}
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        analysis_path = root / "analysis.json"
        analysis_path.write_text(json.dumps(self.analysis_json(), ensure_ascii=False), encoding="utf-8")
        report.render_report(analysis_json=analysis_path, output_dir=root / "final-report", fact_pack=fact_pack)
        rendered = (root / "final-report" / "final-report.html").read_text(encoding="utf-8")
    self.assertNotIn('src="../highlights/101/01-000s.jpg"', rendered)
    self.assertIn("第 1-2 秒出现点击高点。", rendered)
    self.assertIn("暂无可用高光帧", rendered)
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m unittest tests.test_yuntu_report.YuntuReportTests.test_render_report_omits_failed_frame_but_keeps_diagnosis -v`  
Expected: FAIL，因为降级文本和诊断尚未同时得到验证。

- [ ] **Step 3: 保留可用帧过滤并更新技能交付规范**

```python
frame_list = [
    frame for frame in material_frames.get(material_id, [])
    if frame.get("available") and str(frame.get("relative_path", "")).endswith(".jpg")
]
gallery = "".join(frame_buttons) or '<p class="muted highlight-unavailable">暂无可用高光帧</p>'
```

更新 `SKILL.md`：HTML 必须离线可交付、证据可展开、高光帧预览键盘可操作，并以 1440px 与 390px 视口验收；不改变高光帧是否默认抽取的参数行为。

- [ ] **Step 4: 运行全量报告单测和真实数据离线渲染**

Run: `python -m unittest tests.test_yuntu_report -v && python scripts/rpa_connector.py render-report --analysis-json "/Users/shuzida/Downloads/RPA数据汇总 5/yuntu-rankings-analysis/diagnostic-analysis/yuntu-ai-analysis.json" --output-dir "/Users/shuzida/Downloads/RPA数据汇总 5/yuntu-rankings-analysis/final-report-style-refresh"`  
Expected: 所有单测通过，且输出 HTML、Markdown 与 `final-report-data.json`。

- [ ] **Step 5: 执行静态交付与双视口检查**

Run: `REPORT='/Users/shuzida/Downloads/RPA数据汇总 5/yuntu-rankings-analysis/final-report-style-refresh/final-report.html'; rg -n 'https?://|fetch\(|XMLHttpRequest|NaN|Infinity|normalized/|raw-csv/|diagnostic-analysis/' "$REPORT"`  
Expected: 无匹配行。浏览器分别在 `1440x1000` 与 `390x844` 检查封面、六章、证据、标签、帧网格与 lightbox：无正文横向溢出、遮挡或失焦控件。

- [ ] **Step 6: 提交最终实现和文档**

Run: `git add scripts/yuntu_report.py tests/test_yuntu_report.py SKILL.md && git commit -m "feat: polish yuntu report delivery" && git status --short`

## Plan Self-Review

- Spec coverage: Task 1 覆盖结论、素材引用、可折叠证据；Task 2 覆盖模板视觉令牌、响应式与无障碍；Task 3 覆盖失败降级、离线交付、真实数据和双视口。
- Placeholder scan: 每个任务包含文件、测试、预期失败、实现片段和验证命令，无待定项。
- Type consistency: 仅使用既有 `analysis`、`fact_pack`、`material_id`、`highlightFrames`、`available` 与 `relative_path` 字段，不改变输入契约。
