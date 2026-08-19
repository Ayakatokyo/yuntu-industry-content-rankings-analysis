# 云图高光帧与样式化报告 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让当前云图批次可选择性输出 `0s` 封面帧与各指标 Top 3 波峰帧，并把帧证据呈现在样式化的目标品牌六章 HTML 报告中。

**Architecture:** 新建 `scripts/yuntu_highlights.py` 封装趋势选峰、视频下载、FFmpeg 截图和清单写入；`prepare_analysis` 可选调用它并把元数据写入事实包。报告渲染器从 AI JSON 与事实包输出语义化 HTML，不改变六章 AI 契约或 Markdown 输出。

**Tech Stack:** Python 3、标准库 `subprocess` / `tempfile`、现有 `requests`、FFmpeg、`unittest`、HTML/CSS。

---

## File Structure

- Create: `scripts/yuntu_highlights.py` - 白名单、局部波峰、下载、FFmpeg、清单与失败降级。
- Create: `tests/test_yuntu_highlights.py` - 峰选择、下载限制、截图与清单测试。
- Modify: `scripts/yuntu_analysis.py` - 高光帧执行与事实包字段。
- Modify: `scripts/rpa_connector.py` - `--highlight-trends`、报告事实包路径。
- Modify: `scripts/yuntu_report.py` - 样式化 HTML、六章数据和高光画廊。
- Modify: `tests/test_yuntu_analysis.py`, `tests/test_yuntu_report.py`, `tests/test_rpa_connector.py`, `SKILL.md`。

### Task 1: 锁定选帧算法

**Files:**
- Create: `tests/test_yuntu_highlights.py`
- Create: `scripts/yuntu_highlights.py`

- [ ] **Step 1: 写入失败的固定封面与局部波峰测试**

```python
def test_select_candidates_keeps_cover_and_three_distinct_local_peaks():
    detail = {"trend_series": [{"trend_name": "点击指数", "series": [
        {"second": 0, "value": 1}, {"second": 1, "value": 4}, {"second": 2, "value": 2},
        {"second": 3, "value": 8}, {"second": 4, "value": 1}, {"second": 5, "value": 6}, {"second": 6, "value": 1}]}]}
    got = select_highlight_candidates(detail, ["点击指数"])
    assert [item["second"] for item in got] == [0, 1, 3, 5]
    assert got[0]["is_cover"] is True
    assert [item["reasons"][0]["rank"] for item in got[1:]] == [3, 1, 2]
```

- [ ] **Step 2: 运行并确认测试因模块缺失失败**

Run: `python -m unittest tests.test_yuntu_highlights -v`

Expected: `ModuleNotFoundError: No module named 'yuntu_highlights'`。

- [ ] **Step 3: 实现白名单、局部峰与跨指标去重**

```python
ALLOWED_HIGHLIGHT_TRENDS = ("点赞指数", "流失指数", "点击指数", "互动指数", "评论指数")

def select_highlight_candidates(detail, trend_names):
    selected = {0: {"second": 0, "is_cover": True, "reasons": [{"type": "cover"}]}}
    for name in normalize_highlight_trends(trend_names):
        for rank, point in enumerate(_top_local_peaks(_series_for_name(detail, name)), 1):
            frame = selected.setdefault(point["second"], {"second": point["second"], "is_cover": False, "reasons": []})
            frame["reasons"].append({"type": "local_peak", "trend_name": name, "value": point["value"], "rank": rank, "within_high_point": _in_high_point(detail, name, point["second"])})
    return [selected[second] for second in sorted(selected)]
```

Normalize duplicate seconds to their maximum value, compress a continuous nondecreasing plateau to its earliest highest second, accept strict interior peaks and qualifying endpoints, then sort `(-value, second)` and retain three values. Reject names not in `ALLOWED_HIGHLIGHT_TRENDS`; de-duplicate valid input while retaining user order.

- [ ] **Step 4: 增加平台合并和 `highPoint` 标记测试后运行通过**

```python
def test_select_candidates_merges_metrics_at_same_second():
    detail = {"trend_series": [
        {"trend_name": "点赞指数", "series": [{"second": 1, "value": 2}, {"second": 2, "value": 9}, {"second": 3, "value": 9}, {"second": 4, "value": 1}]},
        {"trend_name": "点击指数", "series": [{"second": 1, "value": 1}, {"second": 2, "value": 8}, {"second": 3, "value": 1}]}],
        "high_points": [{"trend_name": "点赞指数", "start_sec": 2, "end_sec": 3}]}
    peak = next(x for x in select_highlight_candidates(detail, ["点赞指数", "点击指数"]) if x["second"] == 2)
    assert [x["trend_name"] for x in peak["reasons"]] == ["点赞指数", "点击指数"]
    assert peak["reasons"][0]["within_high_point"] is True
```

Run: `python -m unittest tests.test_yuntu_highlights -v`

Expected: 所有选帧测试通过。

- [ ] **Step 5: 提交**

Run: `git add scripts/yuntu_highlights.py tests/test_yuntu_highlights.py && git commit -m "feat: select yuntu highlight frame candidates"`

### Task 2: 受限视频提帧与清单降级

**Files:**
- Modify: `scripts/yuntu_highlights.py`
- Modify: `tests/test_yuntu_highlights.py`

- [ ] **Step 1: 写入失败的清单与单帧失败测试**

```python
def test_generate_highlights_writes_manifest_and_continues_after_one_frame_failure(tmp_path):
    detail = {"material_id": "101", "video_url": "https://video.example/101.mp4", "trend_series": []}
    result = generate_highlights([detail], ["点击指数"], tmp_path, downloader=FakeVideoDownloader(), frame_extractor=FailingSecondExtractor(0))
    manifest = json.loads((tmp_path / "highlights-manifest.json").read_text(encoding="utf-8"))
    assert result["101"][0]["available"] is False
    assert manifest["materials"][0]["frames"][0]["failure_reason"] == "extract_failed"
```

- [ ] **Step 2: 运行并确认 `generate_highlights` 尚未定义**

Run: `python -m unittest tests.test_yuntu_highlights.YuntuHighlightsTests.test_generate_highlights_writes_manifest_and_continues_after_one_frame_failure -v`

Expected: 导入或属性错误指出 `generate_highlights` 不存在。

- [ ] **Step 3: 实现下载、FFmpeg 和 JSON 清单**

```python
def generate_highlights(details, trend_names, output_dir, *, downloader=download_video, frame_extractor=extract_frame, ffmpeg_bin=None):
    root, result, materials = Path(output_dir), {}, []
    for detail in details:
        material_id = str(detail.get("material_id", ""))
        frames = _generate_material_frames(detail, normalize_highlight_trends(trend_names), root, downloader, frame_extractor, ffmpeg_bin)
        result[material_id] = frames
        materials.append({"material_id": material_id, "video_url": detail.get("video_url", ""), "frames": frames})
    write_json_atomically({"schemaVersion": 1, "materials": materials}, root / "highlights-manifest.json")
    return result
```

`download_video` 仅允许 HTTP(S)，将流式内容写入 `TemporaryDirectory`，使用 30 秒超时与 200 MiB 上限。`extract_frame` 依次解析 `IMAGEIO_FFMPEG_EXE`、`shutil.which("ffmpeg")`，运行 `ffmpeg -ss <second> -i <video> -frames:v 1 -q:v 2`，仅在临时 JPEG 非空时原子发布。预期下载和 FFmpeg 异常写为 `available: false`、`failure_reason`，不从 `generate_highlights` 抛出。

- [ ] **Step 4: 增加无 URL 与超限下载测试，运行通过**

```python
def test_generate_highlights_marks_missing_video_url_without_raising(tmp_path):
    result = generate_highlights([{"material_id": "101", "video_url": "", "trend_series": []}], ["评论指数"], tmp_path)
    assert result["101"][0]["failure_reason"] == "missing_video_url"

def test_download_video_rejects_response_larger_than_limit(tmp_path):
    with self.assertRaisesRegex(HighlightFrameError, "maximum size"):
        download_video("https://video.example/a.mp4", tmp_path / "a.mp4", session=OversizeSession(), max_bytes=4)
```

Run: `python -m unittest tests.test_yuntu_highlights -v`

Expected: 成功 JPEG、清单、失败帧和临时文件清理测试通过。

- [ ] **Step 5: 提交**

Run: `git add scripts/yuntu_highlights.py tests/test_yuntu_highlights.py && git commit -m "feat: extract yuntu highlight frames"`

### Task 3: 分析命令与事实包集成

**Files:**
- Modify: `scripts/yuntu_analysis.py`, `scripts/rpa_connector.py`
- Modify: `tests/test_yuntu_analysis.py`, `tests/test_rpa_connector.py`

- [ ] **Step 1: 写入失败的事实包测试**

```python
def test_prepare_analysis_includes_highlight_frames_when_trends_are_selected(self):
    analysis.prepare_analysis(input_dir=root, output_dir=root / "diagnostic-analysis", highlight_trends=["点击指数"])
    fact_pack = json.loads((root / "diagnostic-analysis" / "yuntu-analysis-data.json").read_text(encoding="utf-8"))
    self.assertIn("highlightFrames", fact_pack["materialFacts"][0])
```

- [ ] **Step 2: 运行并确认函数暂不接受 `highlight_trends`**

Run: `python -m unittest tests.test_yuntu_analysis.YuntuAnalysisTests.test_prepare_analysis_includes_highlight_frames_when_trends_are_selected -v`

Expected: `TypeError` 提示未知关键字参数。

- [ ] **Step 3: 加入可选参数、帧元数据和 CLI 接线**

```python
def prepare_analysis(*, input_dir, output_dir, highlight_trends=None):
    selected_trends = normalize_highlight_trends(highlight_trends or [])
    highlights = generate_highlights(details, selected_trends, root) if selected_trends else {}
    # 每个 materialFacts 写入 highlightFrames 与 highlightFrameAvailability。
```

```python
prepare_parser.add_argument("--highlight-trends", nargs="+", choices=ALLOWED_HIGHLIGHT_TRENDS)
return prepare_analysis(input_dir=args.input_dir, output_dir=args.output_dir, highlight_trends=args.highlight_trends)
```

Use input batch `root` for `highlights/<material_id>/` 和 `highlights-manifest.json`。无参数时 `highlightFrames` 为 `[]`、`highlightFrameAvailability` 为 `{"available": false, "missing_reason": "not_requested"}`，且不执行下载。

- [ ] **Step 4: 增加 CLI 透传与无参数兼容测试，运行通过**

```python
def test_main_prepare_analysis_passes_selected_highlight_trends(self):
    with patch.object(connector, "prepare_analysis", return_value=0) as prepare:
        connector.main(["prepare-analysis", "--input-dir", "in", "--output-dir", "out", "--highlight-trends", "点赞指数", "点击指数"])
    self.assertEqual(prepare.call_args.kwargs["highlight_trends"], ["点赞指数", "点击指数"])
```

Run: `python -m unittest tests.test_yuntu_analysis tests.test_rpa_connector -v`

Expected: 新参数可用；无参数路径不创建高光帧目录且现有测试通过。

- [ ] **Step 5: 提交**

Run: `git add scripts/yuntu_analysis.py scripts/rpa_connector.py tests/test_yuntu_analysis.py tests/test_rpa_connector.py && git commit -m "feat: add highlight frames to yuntu fact pack"`

### Task 4: 六章 HTML 和高光帧画廊

**Files:**
- Modify: `scripts/yuntu_report.py`
- Modify: `tests/test_yuntu_report.py`

- [ ] **Step 1: 写入失败的封面和画廊测试**

```python
def test_render_report_renders_styled_cover_and_highlight_gallery(self):
    facts = {"materialFacts": [{"material_id": "101", "highlightFrames": [{"second": 0, "available": True, "relative_path": "../highlights/101/01-000s.jpg", "is_cover": True, "reasons": [{"type": "cover"}]}]}]}
    report.render_report(analysis_json=analysis_path, output_dir=root / "final-report", fact_pack=facts)
    html = (root / "final-report" / "final-report.html").read_text(encoding="utf-8")
    self.assertIn('class="report-cover"', html)
    self.assertIn('class="highlight-gallery"', html)
    self.assertIn('src="../highlights/101/01-000s.jpg"', html)
```

- [ ] **Step 2: 运行并确认当前渲染器不支持 `fact_pack`**

Run: `python -m unittest tests.test_yuntu_report.YuntuReportTests.test_render_report_renders_styled_cover_and_highlight_gallery -v`

Expected: `TypeError` 提示未知关键字参数。

- [ ] **Step 3: 实现语义化 HTML 模板**

```python
def render_report(*, analysis_json, output_dir, fact_pack=None):
    analysis = _load_analysis(analysis_json)
    frames = _material_frames(fact_pack or {})
    markdown = _render_markdown(analysis)
    (Path(output_dir) / "final-report.html").write_text(_render_html(analysis, frames), encoding="utf-8")
```

`_render_html` 输出内嵌 CSS，含 `--ink: #2d2018`、`--gold: #b88a45`、`--paper: #f7f0e4`、`max-width: 1100px`，并用 `<header>`、`<main>`、`<section>`、`<article>`、`<table>` 组织已有六章。转义所有 AI 文本；仅在“单素材秒级诊断”使用有 `available: true` 且为本地相对 `.jpg` 路径的 `<img>`；实验表外套窄屏横向滚动容器。

- [ ] **Step 4: 增加无帧回退测试并运行通过**

```python
def test_render_report_omits_image_when_highlight_frame_failed(self):
    facts = {"materialFacts": [{"material_id": "101", "highlightFrames": [{"second": 0, "available": False, "failure_reason": "download_failed"}]}]}
    report.render_report(analysis_json=analysis_path, output_dir=root / "final-report", fact_pack=facts)
    html = (root / "final-report" / "final-report.html").read_text(encoding="utf-8")
    self.assertNotIn("<img", html)
    self.assertIn("第 1-2 秒出现点击高点", html)
```

Run: `python -m unittest tests.test_yuntu_report -v`

Expected: 证据校验、实验字段校验、六章、封面、画廊和无图回退全部通过。

- [ ] **Step 5: 提交**

Run: `git add scripts/yuntu_report.py tests/test_yuntu_report.py && git commit -m "feat: render styled yuntu highlight report"`

### Task 5: 报告命令、文档和真实数据验证

**Files:**
- Modify: `scripts/rpa_connector.py`, `scripts/yuntu_report.py`, `tests/test_rpa_connector.py`, `SKILL.md`

- [ ] **Step 1: 写入失败的默认事实包定位测试**

```python
def test_main_render_report_uses_sibling_fact_pack(self):
    with patch.object(connector, "render_report", return_value=0) as render:
        connector.main(["render-report", "--analysis-json", "run/diagnostic-analysis/yuntu-ai-analysis.json", "--output-dir", "run/final-report"])
    self.assertEqual(render.call_args.kwargs["fact_pack_path"], "run/diagnostic-analysis/yuntu-analysis-data.json")
```

- [ ] **Step 2: 实现同级事实包默认值和文档**

```python
report_parser.add_argument("--fact-pack-json")
fact_pack_path = args.fact_pack_json or str(Path(args.analysis_json).with_name("yuntu-analysis-data.json"))
return render_report(analysis_json=args.analysis_json, output_dir=args.output_dir, fact_pack_path=fact_pack_path)
```

Update `render_report` to load `fact_pack_path` when present and otherwise use `{}`. Update `SKILL.md` with `prepare-analysis --highlight-trends 点击指数 互动指数`, output paths, the exact `0s + Top 3 local peaks per indicator` and per-second deduplication rules, and non-blocking failure semantics.

- [ ] **Step 3: 运行 CLI 和文档测试**

Run: `python -m unittest tests.test_rpa_connector tests.test_skill_contract -v`

Expected: 新旧 CLI 均可调用，技能契约测试通过。

- [ ] **Step 4: 运行全量回归和离线检查**

Run: `python -m unittest discover -s tests -v && python scripts/rpa_connector.py self-test`

Expected: 所有测试与连接器离线检查退出码均为 `0`。

- [ ] **Step 5: 用真实数据重放并检查双视口**

Run: `python scripts/rpa_connector.py prepare-analysis --input-dir "RPA数据汇总/real-data-regression-20260803" --output-dir "RPA数据汇总/real-data-regression-20260803/diagnostic-analysis" --highlight-trends "点赞指数" "流失指数" "点击指数" "互动指数" "评论指数"`

Run: `python scripts/rpa_connector.py render-report --analysis-json "RPA数据汇总/real-data-regression-20260803/diagnostic-analysis/yuntu-ai-analysis.json" --output-dir "RPA数据汇总/real-data-regression-20260803/final-report"`

Expected: `highlights-manifest.json` 对每个素材给出成功帧或失败原因；HTML 有样式化六章，成功帧显示画廊，失败帧不输出坏图。在 `1440x1000` 与 `390x844` 浏览器视口确认封面、章节、实验表和帧标签不重叠、不溢出。

- [ ] **Step 6: 提交最终实现，保留生成数据未跟踪**

Run: `git add scripts tests SKILL.md && git commit -m "feat: complete yuntu highlight frame reporting" && git status --short`

Expected: 代码、测试和文档已经提交；`RPA数据汇总/` 可继续保持未跟踪。

## Plan Self-Review

- Spec coverage: Task 1 implements `0s`、局部峰、Top 3、跨指标去重和 `highPoint` 标识。Task 2 implements 下载限制、FFmpeg、JPEG、清单和失败降级。Task 3 implements 可选参数与事实包。Task 4 implements 既有六章的深棕暖金 HTML 与画廊。Task 5 implements CLI、文档、全量测试、真实重放和双视口验证。
- Placeholder scan: 每个代码任务包含函数名、字段名、测试断言和执行命令，没有延后或未定义实现项。
- Type consistency: 管道统一使用 `highlight_trends`、`highlightFrames`、`fact_pack_path`、`select_highlight_candidates` 与 `generate_highlights`；帧记录统一使用 `available`、`second`、`relative_path`、`is_cover`、`reasons` 和 `failure_reason`。
