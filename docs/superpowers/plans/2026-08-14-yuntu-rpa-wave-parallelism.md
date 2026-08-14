# 云图详情 RPA 波次并行与高光帧流水线 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将详情 RPA 改为固定三并发的波次调度，并在每条详情落盘后并行执行该素材的高光帧处理，同时保持可恢复、可审计的批次语义。

**Architecture:** `yuntu_batch.py` 保持唯一主调度线程，使用独立的详情 RPA 与高光帧 `ThreadPoolExecutor`。工作线程只返回结果；主线程负责详情规范化、manifest/run-summary/highlights-manifest 的原子写入，以及波次屏障。`yuntu_highlights.py` 提供单素材、可复用的帧处理 API；`prepare-analysis` 复用已落盘帧并只补处理缺口。

**Tech Stack:** Python 3、`concurrent.futures.ThreadPoolExecutor`、`requests`、FFmpeg、`unittest`。

---

## File Structure

- Modify: `scripts/yuntu_highlights.py` - 单素材高光帧生成、manifest 读取/合并及缺口识别。
- Modify: `scripts/yuntu_batch.py` - 三并发波次调度、主线程检查点、详情与后处理状态。
- Modify: `scripts/yuntu_analysis.py` - 复用已落盘高光帧并只补处理缺口。
- Modify: `scripts/rpa_connector.py` - CLI 帮助文本说明固定波次行为，不改变参数。
- Modify: `SKILL.md` - 将详情阶段的实际三并发波次与高光帧流水线写入运行契约。
- Modify: `tests/test_yuntu_highlights.py` - 单素材帧复用和 manifest 行为。
- Modify: `tests/test_yuntu_batch.py` - 波次并发、屏障、失败和恢复行为。
- Modify: `tests/test_yuntu_analysis.py` - 已有高光帧复用与缺口补处理。

### Task 1: 建立高光帧的单素材与恢复接口

**Files:**

- Modify: `scripts/yuntu_highlights.py:405-538`
- Test: `tests/test_yuntu_highlights.py`

- [ ] **Step 1: Write the failing tests**

新增两个测试：完整的 `highlights-manifest.json` 和 JPEG 存在时，不调用 downloader 或 frame extractor；manifest 中素材的 JPEG 缺失时，`details_missing_standard_highlights()` 返回该素材。

```python
def test_single_material_highlights_reuses_complete_manifest(self):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        image = root / "highlights" / "101" / "01-000s.jpg"
        image.parent.mkdir(parents=True)
        image.write_bytes(b"jpeg")
        highlights.write_highlights_manifest(root, {"101": [cover_frame(image)]})
        frames = highlights.generate_standard_highlights_for_detail(
            detail_101(), root,
            downloader=lambda *_: self.fail("unexpected download"),
            frame_extractor=lambda *_args, **_kwargs: self.fail("unexpected extraction"),
        )
    self.assertEqual(frames[0]["frame_source"], "reused_local_extracted_frame")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_yuntu_highlights -v`

Expected: FAIL because the three new highlighter APIs do not exist.

- [ ] **Step 3: Write minimal implementation**

Add these functions below `_material_frames()`:

```python
def load_highlights_manifest(output_dir):
    path = Path(output_dir) / "highlights-manifest.json"
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {str(item.get("material_id")): item.get("frames", [])
            for item in payload.get("materials", []) if isinstance(item, dict)}

def write_highlights_manifest(output_dir, frames_by_material):
    materials = [{"material_id": material_id, "frames": frames}
                 for material_id, frames in sorted(frames_by_material.items())]
    _write_json_atomically({"schemaVersion": 2, "standard": "cover_plus_click_top5",
                            "materials": materials}, Path(output_dir) / "highlights-manifest.json")

def generate_standard_highlights_for_detail(detail, output_dir, *, downloader=download_video,
                                             frame_extractor=extract_frame, ffmpeg_bin=None):
    candidates = select_standard_highlight_candidates(detail)
    reused = _usable_manifest_frames(Path(output_dir), detail["material_id"], candidates)
    return reused if reused is not None else _material_frames(
        detail, candidates, Path(output_dir), downloader, frame_extractor, ffmpeg_bin
    )
```

`_usable_manifest_frames()` 必须逐个比对候选的 `(frame_type, second)`、`available` 和 `relative_path` 对应的非空 JPEG；任意一个不匹配则返回 `None`。`details_missing_standard_highlights()` 用它筛选详情。现有 `generate_standard_highlights()` 改为逐素材调用新函数后统一写 manifest。

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_yuntu_highlights -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/yuntu_highlights.py tests/test_yuntu_highlights.py && git commit -m "feat: add reusable per-material highlights"
```

### Task 2: 为波次调度建立失败测试

**Files:**

- Modify: `tests/test_yuntu_batch.py`
- Test: `tests/test_yuntu_batch.py`

- [ ] **Step 1: Write the failing tests**

增加按 `material_id` 返回详情的线程安全 fake invoker，并用 `threading.Event` 添加四个测试：第一波恰好启动 `101/202/303` 且在释放前不启动 `404`；`101` 的 RPA 返回而 `202/303` 仍阻塞时高光帧处理已经启动；在阻塞 `101` 的高光帧完成前不启动第二波；高光帧异常不把详情移入 `rejectedMaterials`，也不提交第四个候选。

```python
def test_wave_waits_for_highlight_terminal_state_before_fourth_detail(self):
    runner = threading.Thread(target=call_fetch_batch)
    runner.start()
    self.assertTrue(first_wave_rpa_finished.wait(timeout=1))
    self.assertTrue(first_highlight_started.wait(timeout=1))
    self.assertNotIn("404", invoker.detail_started)
    release_highlight.set()
    runner.join(timeout=2)
    self.assertIn("404", invoker.detail_started)
```

添加恢复测试：已有 `normalized/detail-records/101.json` 而 `highlights-manifest.json` 缺少 `101` 时，续跑提交 `101` 的高光帧，但 `invoke_detail` 从不接收 `101`。

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_yuntu_batch -v`

Expected: FAIL，因为详情调用仍位于串行 `for item in candidates` 循环，且没有高光帧任务。

- [ ] **Step 3: Add minimal scheduler helpers**

在 `scripts/yuntu_batch.py` 导入 `FIRST_COMPLETED`、`ThreadPoolExecutor`、`wait`，以及高光帧的单素材/manifest API。添加固定常量和无写入 worker：

```python
DETAIL_WAVE_CONCURRENCY = 3
HIGHLIGHT_CONCURRENCY = 3

def _fetch_detail_result(*, item, shop_id, detail_date_params, invoker, downloader, root):
    started = time.monotonic()
    try:
        raw, source = _materialize_records(
            invoker.invoke_detail(shop_id, _detail_request(item, detail_date_params)),
            csv_path=root / "raw-csv" / "details" / f"{item['material_id']}.csv",
            json_path=root / "raw-json" / "details" / f"{item['material_id']}.json",
            downloader=downloader,
        )
        return {"item": item, "detail": normalize_detail_records(raw, material_id=item["material_id"],
                source_path=_relative(root, source), expected_selection_group=item["selectionGroup"] if item["selectionGroupId"] != "default" else None),
                "source": source, "duration": _elapsed(started), "error": None}
    except Exception as error:
        return {"item": item, "detail": None, "source": None,
                "duration": _elapsed(started), "error": error}

def _highlight_result(detail, root):
    started = time.monotonic()
    try:
        return {"material_id": detail["material_id"], "frames": generate_standard_highlights_for_detail(detail, root),
                "duration": _elapsed(started), "error": None}
    except Exception as error:
        return {"material_id": detail["material_id"], "frames": [],
                "duration": _elapsed(started), "error": error}
```

- [ ] **Step 4: Run test to verify it remains red**

Run: `python -m unittest tests.test_yuntu_batch -v`

Expected: 新增屏障测试仍 FAIL，证明仅加入 worker 没有意外改写调度。

- [ ] **Step 5: Commit**

```bash
git add scripts/yuntu_batch.py tests/test_yuntu_batch.py && git commit -m "test: define Yuntu wave scheduler behavior"
```

### Task 3: Replace the serial detail loop with a three-item wave scheduler

**Files:**

- Modify: `scripts/yuntu_batch.py:581-679`
- Test: `tests/test_yuntu_batch.py`

- [ ] **Step 1: Write the minimal wave scheduler**

Replace the serial `for item in candidates` section with a main-thread loop whose invariant is that no next wave may be submitted while either `pending_detail_futures` or `pending_highlight_futures` is nonempty. The scheduler must retain the current candidate order and group quota semantics.

```python
frames_by_material = load_highlights_manifest(root)
with ThreadPoolExecutor(max_workers=DETAIL_WAVE_CONCURRENCY) as detail_executor, \
        ThreadPoolExecutor(max_workers=HIGHLIGHT_CONCURRENCY) as highlight_executor:
    while True:
        if not pending_detail_futures and not pending_highlight_futures:
            wave = _next_wave(candidates, selected_ids, unresolved_ids, selected_by_group, target_top_n)
            if not wave:
                break
            for item in wave:
                manifest["submittedMaterials"].append(_manifest_material(item))
                future = detail_executor.submit(_fetch_detail_result, item=item, shop_id=shop_id,
                                                detail_date_params=detail_date_params, invoker=invoker,
                                                downloader=downloader, root=root)
                pending_detail_futures[future] = item
            _checkpoint_batch(root, summary, manifest, frames_by_material)
        done, _ = wait(set(pending_detail_futures) | set(pending_highlight_futures),
                       return_when=FIRST_COMPLETED)
        for future in done:
            if future in pending_detail_futures:
                result = future.result()
                pending_detail_futures.pop(future)
                if _accept_detail_result(result, manifest, summary, root, selected_ids, selected_by_group):
                    task = highlight_executor.submit(_highlight_result, result["detail"], root)
                    pending_highlight_futures[task] = result["detail"]["material_id"]
            else:
                result = future.result()
                pending_highlight_futures.pop(future)
                _accept_highlight_result(result, manifest, frames_by_material)
        _checkpoint_batch(root, summary, manifest, frames_by_material)
```

`_next_wave()` skips persisted, unresolved, and selected IDs, checks each group against `target_top_n`, and returns at most three candidates. `_accept_detail_result()` writes `normalized/detail-records/<material_id>.json` in the main thread, registers its artifact, and appends the existing selected/rejected form. `_accept_highlight_result()` only adds `postprocessStatus`, `postprocessTimingsSec`, and `postprocessError` to the selected entry; it never rejects a detail. `_checkpoint_batch()` writes the highlights manifest before the batch manifest and summary.

- [ ] **Step 2: Run test to verify it passes**

Run: `python -m unittest tests.test_yuntu_batch -v`

Expected: PASS, including existing list reuse, persisted-detail recovery, rejection and selection-group tests.

- [ ] **Step 3: Run connector-facing regression tests**

Run: `python -m unittest tests.test_rpa_connector tests.test_rpa_io tests.test_yuntu_run_state -v`

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add scripts/yuntu_batch.py tests/test_yuntu_batch.py && git commit -m "feat: run Yuntu details in bounded waves"
```

### Task 4: Reuse frames during analysis and document execution

**Files:**

- Modify: `scripts/yuntu_analysis.py:420-503`
- Modify: `scripts/rpa_connector.py:765-797`
- Modify: `SKILL.md`
- Test: `tests/test_yuntu_analysis.py`

- [ ] **Step 1: Write the failing analysis tests**

Patch `yuntu_analysis.generate_standard_highlights_for_detail` in a test with a complete frame manifest. Assert that the helper is not called and that the fact pack uses the previous frame. Add a missing-manifest test that asserts the helper runs exactly once and the generated frame enters the fact pack.

```python
with mock.patch.object(analysis, "generate_standard_highlights_for_detail") as generate:
    analysis.prepare_analysis(input_dir=root, output_dir=root / "diagnostic-analysis")
generate.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_yuntu_analysis -v`

Expected: FAIL because `prepare_analysis()` unconditionally calls bulk `generate_standard_highlights(details, root)`.

- [ ] **Step 3: Write minimal analysis fallback and docs**

Replace the bulk call with manifest reuse and missing-only fallback:

```python
frames_by_material = load_highlights_manifest(root)
for detail in details_missing_standard_highlights(details, root):
    frames_by_material[detail["material_id"]] = generate_standard_highlights_for_detail(detail, root)
if details:
    write_highlights_manifest(root, frames_by_material)
```

Build each material fact from `frames_by_material.get(str(fact["material_id"]), [])`. Update `fetch` help and `SKILL.md` to state: detail requests run in fixed waves of three; a completed detail starts highlighter processing immediately; the next wave waits for all current highlighter tasks to reach a terminal state; a highlighter failure does not re-request the detail.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_yuntu_analysis tests.test_yuntu_highlights -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/yuntu_analysis.py scripts/rpa_connector.py SKILL.md tests/test_yuntu_analysis.py tests/test_yuntu_highlights.py && git commit -m "feat: reuse streamed Yuntu highlight frames"
```

### Task 5: Full verification

**Files:**

- Verify: `tests/test_*.py`

- [ ] **Step 1: Run the complete suite**

Run: `python -m unittest discover -s tests -p 'test_*.py' -v`

Expected: PASS with no real RPA gateway, video download, or FFmpeg dependency.

- [ ] **Step 2: Run offline connector contract verification**

Run: `python scripts/rpa_connector.py self-test`

Expected: `self-test passed`.

- [ ] **Step 3: Inspect the final patch**

Run: `git diff HEAD~3..HEAD --check && git status --short`

Expected: no whitespace errors and no uncommitted product-code changes.

- [ ] **Step 4: Commit any verification-only correction**

```bash
git add scripts tests SKILL.md && git commit -m "test: verify Yuntu wave parallelism"
```
