# Batched Highlight Frame Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract all highlighter frames for a material through one exact-seek FFmpeg invocation, while retaining the RPA wave barrier and per-frame fallback behavior.

**Architecture:** Add a low-level batch executor in `scripts/yuntu_highlights.py` that writes all JPEGs into random staging paths, validates every image, then atomically publishes the complete set. `_material_frames()` tries that executor once per downloaded video and invokes the existing single-frame extractor only if batch processing fails. `scripts/yuntu_batch.py` remains unchanged because it already waits for all highlighter futures before advancing the RPA wave.

**Tech Stack:** Python 3, `subprocess`, FFmpeg, `pathlib`, `tempfile`, `unittest`, `unittest.mock`.

---

### Task 1: Specify Batch Execution And Validation

**Files:**
- Modify: `tests/test_yuntu_highlights.py:1-16`
- Modify: `tests/test_yuntu_highlights.py:354-404`

- [ ] **Step 1: Write the failing command-construction test**

Add `from unittest import mock`, then add:

```python
def test_extract_frames_batch_uses_one_exact_decode_graph_with_limited_threads(self):
    highlights = load_module()
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        requests = [
            {"second": 0, "destination": root / "cover.jpg"},
            {"second": 2, "destination": root / "peak.jpg"},
        ]
        with mock.patch.object(highlights, "_resolve_ffmpeg", return_value="ffmpeg"), \
             mock.patch.object(highlights.subprocess, "run", return_value=mock.Mock(returncode=0, stderr="")) as run, \
             mock.patch.object(highlights, "_validate_jpeg", return_value=None):
            highlights.extract_frames_batch(root / "source.mp4", requests)
    command = run.call_args.args[0]
    graph = command[command.index("-filter_complex") + 1]
    self.assertEqual(command.count("-i"), 1)
    self.assertEqual(command[command.index("-threads") + 1], "1")
    self.assertEqual(command[command.index("-filter_threads") + 1], "1")
    self.assertIn("[0:v]split=2[s0][s1]", graph)
    self.assertIn("[s0]trim=start=0,setpts=PTS-STARTPTS[out0]", graph)
    self.assertIn("[s1]trim=start=2,setpts=PTS-STARTPTS[out1]", graph)
    self.assertEqual(command.count("-frames:v"), 2)
```

- [ ] **Step 2: Write the failing JPEG boundary test**

```python
def test_validate_jpeg_rejects_empty_and_truncated_files(self):
    highlights = load_module()
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        empty = root / "empty.jpg"
        empty.touch()
        truncated = root / "truncated.jpg"
        truncated.write_bytes(b"\xff\xd8not-complete")
        with self.assertRaisesRegex(highlights.HighlightFrameError, "empty"):
            highlights._validate_jpeg(empty)
        with self.assertRaisesRegex(highlights.HighlightFrameError, "JPEG markers"):
            highlights._validate_jpeg(truncated)
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python -m unittest tests.test_yuntu_highlights.YuntuHighlightTests.test_extract_frames_batch_uses_one_exact_decode_graph_with_limited_threads tests.test_yuntu_highlights.YuntuHighlightTests.test_validate_jpeg_rejects_empty_and_truncated_files -v`

Expected: FAIL because the batch executor and JPEG validator do not exist.

- [ ] **Step 4: Commit the test-only change**

```bash
git add tests/test_yuntu_highlights.py
git commit -m "test: specify batched highlight extraction"
```

### Task 2: Implement The Staged Batch Executor

**Files:**
- Modify: `scripts/yuntu_highlights.py:279-329`
- Modify: `tests/test_yuntu_highlights.py:354-404`

- [ ] **Step 1: Add JPEG validation**

```python
def _validate_jpeg(path, *, ffmpeg_bin=None):
    image = Path(path)
    if not image.is_file() or image.stat().st_size == 0:
        raise HighlightFrameError("JPEG output is empty")
    with image.open("rb") as handle:
        header = handle.read(2)
        handle.seek(-2, os.SEEK_END)
        trailer = handle.read(2)
    if header != b"\xff\xd8" or trailer != b"\xff\xd9":
        raise HighlightFrameError("JPEG markers are invalid")
    completed = subprocess.run(
        [_resolve_ffmpeg(ffmpeg_bin), "-hide_banner", "-loglevel", "error", "-nostdin",
         "-i", str(image), "-f", "null", "-"],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
        timeout=VIDEO_DOWNLOAD_TIMEOUT_SECONDS, check=False,
    )
    if completed.returncode != 0:
        raise HighlightFrameError("JPEG decode validation failed")
```

- [ ] **Step 2: Add the graph and executor**

```python
def _batch_filter_graph(seconds):
    labels = "".join(f"[s{index}]" for index in range(len(seconds)))
    branches = [f"[0:v]split={len(seconds)}{labels}"]
    branches.extend(
        f"[s{index}]trim=start={second:g},setpts=PTS-STARTPTS[out{index}]"
        for index, second in enumerate(seconds)
    )
    return ";".join(branches)

def extract_frames_batch(video_path, requests, *, ffmpeg_bin=None):
    staged = []
    seen_seconds = set()
    for request in requests:
        second = request["second"]
        target = Path(request["destination"])
        if second in seen_seconds:
            continue
        seen_seconds.add(second)
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            prefix="yuntu-frame-", suffix=".jpg", dir=target.parent, delete=False
        ) as handle:
            staged.append((second, target, Path(handle.name)))
    if not staged:
        raise HighlightFrameError("no frame requests")
    try:
        command = [_resolve_ffmpeg(ffmpeg_bin), "-hide_banner", "-loglevel", "error",
                   "-nostdin", "-y", "-threads", "1", "-filter_threads", "1",
                   "-i", str(video_path), "-filter_complex",
                   _batch_filter_graph([second for second, _, _ in staged])]
        for index, (_, _, staging) in enumerate(staged):
            command.extend(["-map", f"[out{index}]", "-frames:v", "1", "-an", "-sn",
                            "-dn", "-q:v", "2", "-f", "image2", str(staging)])
        completed = subprocess.run(
            command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
            timeout=VIDEO_DOWNLOAD_TIMEOUT_SECONDS, check=False,
        )
        if completed.returncode != 0:
            raise HighlightFrameError("ffmpeg batch frame extraction failed")
        for _, _, staging in staged:
            _validate_jpeg(staging, ffmpeg_bin=ffmpeg_bin)
        for _, target, staging in staged:
            staging.replace(target)
        return [target for _, target, _ in staged]
    except (OSError, subprocess.SubprocessError) as error:
        raise HighlightFrameError(f"ffmpeg batch frame extraction failed: {error}") from error
    finally:
        for _, _, staging in staged:
            staging.unlink(missing_ok=True)
```

The command must include `-threads 1 -filter_threads 1`, one input, one `-filter_complex` graph, and one `-map [outN] -frames:v 1 -an -sn -dn -q:v 2 -f image2 <staging>` sequence per output. It rejects an empty request list; uses `NamedTemporaryFile(prefix="yuntu-frame-", suffix=".jpg", dir=target.parent, delete=False)`; preserves request order; and returns the published targets. Any encoder failure, missing output, marker failure, or decode failure raises `HighlightFrameError` before publishing a new batch frame.

- [ ] **Step 3: Make the command test produce valid staging files**

Use a `subprocess.run` side effect that writes `b"\xff\xd8ok\xff\xd9"` to encoder output paths and succeeds for JPEG decode validation calls. Remove the validator mock and assert both requested targets exist after the batch call returns.

- [ ] **Step 4: Run focused tests**

Run: `python -m unittest tests.test_yuntu_highlights.YuntuHighlightTests.test_extract_frames_batch_uses_one_exact_decode_graph_with_limited_threads tests.test_yuntu_highlights.YuntuHighlightTests.test_validate_jpeg_rejects_empty_and_truncated_files -v`

Expected: PASS.

- [ ] **Step 5: Commit executor behavior**

```bash
git add scripts/yuntu_highlights.py tests/test_yuntu_highlights.py
git commit -m "feat: batch highlighter frame extraction"
```

### Task 3: Integrate Batch-First Material Extraction With Fallback

**Files:**
- Modify: `scripts/yuntu_highlights.py:405-459`
- Modify: `scripts/yuntu_highlights.py:551-635`
- Modify: `tests/test_yuntu_highlights.py:177-225`
- Modify: `tests/test_yuntu_highlights.py:328-352`

- [ ] **Step 1: Write the failing one-call integration test**

```python
def test_standard_highlights_extract_all_frames_in_one_batch_call(self):
    highlights = load_module()
    calls = []
    def downloader(_url, destination):
        Path(destination).write_bytes(b"video")
    def batch_extractor(_video, requests, *, ffmpeg_bin=None):
        calls.append(requests)
        for request in requests:
            Path(request["destination"]).write_bytes(b"\xff\xd8ok\xff\xd9")
    detail = {"material_id": "101", "video_url": "https://video.example/101.mp4", "trend_series": []}
    with tempfile.TemporaryDirectory() as directory:
        frames = highlights.generate_standard_highlights_for_detail(
            detail, directory, downloader=downloader, batch_extractor=batch_extractor
        )
    self.assertEqual(len(calls), 1)
    self.assertEqual([request["second"] for request in calls[0]], [0])
    self.assertTrue(frames[0]["available"])
```

- [ ] **Step 2: Write the failing whole-material fallback test**

```python
def test_batch_extraction_failure_falls_back_to_each_frame(self):
    highlights = load_module()
    extracted_seconds = []
    def downloader(_url, destination):
        Path(destination).write_bytes(b"video")
    def failed_batch(*_args, **_kwargs):
        raise highlights.HighlightFrameError("batch failed")
    def frame_extractor(_video, second, destination, *, ffmpeg_bin=None):
        extracted_seconds.append(second)
        Path(destination).write_bytes(b"\xff\xd8ok\xff\xd9")
    detail = {"material_id": "101", "video_url": "https://video.example/101.mp4", "trend_series": []}
    with tempfile.TemporaryDirectory() as directory:
        frames = highlights.generate_standard_highlights_for_detail(
            detail, directory, downloader=downloader, frame_extractor=frame_extractor,
            batch_extractor=failed_batch,
        )
    self.assertEqual(extracted_seconds, [0])
    self.assertTrue(frames[0]["available"])
```

- [ ] **Step 3: Run the integration tests to verify failure**

Run: `python -m unittest tests.test_yuntu_highlights.YuntuHighlightTests.test_standard_highlights_extract_all_frames_in_one_batch_call tests.test_yuntu_highlights.YuntuHighlightTests.test_batch_extraction_failure_falls_back_to_each_frame -v`

Expected: FAIL because the public highlighter does not yet accept `batch_extractor`.

- [ ] **Step 4: Route material frames through batch extraction**

Extend `_material_frames()` and all three public highlighter functions with keyword-only `batch_extractor=None`, resolving `None` to `extract_frames_batch`. Build requests from the existing indexed candidates and `_highlight_filename()`; invoke the batch extractor once; and return normal available records on success. Move the existing per-candidate loop into `_extract_frames_individually()` and call it after any batch exception. Preserve its `_reused_frame_record()` behavior and failure reasons exactly.

- [ ] **Step 5: Preserve fake extractor test semantics**

In `test_generate_highlights_writes_manifest_and_continues_after_one_frame_failure`, supply a batch extractor that raises `HighlightFrameError`. This deliberately exercises the old fake per-frame extractor and retains its cover-failure assertion.

- [ ] **Step 6: Run highlighter regressions**

Run: `python -m unittest tests.test_yuntu_highlights -v`

Expected: PASS.

- [ ] **Step 7: Commit integration and fallback**

```bash
git add scripts/yuntu_highlights.py tests/test_yuntu_highlights.py
git commit -m "feat: fall back from batched highlight extraction"
```

### Task 4: Verify The RPA Boundary And Regression Surface

**Files:**
- Verify: `scripts/yuntu_batch.py:751-862`
- Verify: `tests/test_yuntu_batch.py:120-255`
- Verify: `tests/test_yuntu_analysis.py`
- Verify: `tests/test_yuntu_highlights.py`

- [ ] **Step 1: Confirm no wave-barrier change**

Run: `git diff HEAD~3..HEAD -- scripts/yuntu_batch.py`

Expected: no output. `if not pending_details and not pending_highlights:` remains the next-wave gate.

- [ ] **Step 2: Run cross-module regression tests**

Run: `python -m unittest tests.test_yuntu_batch tests.test_yuntu_analysis tests.test_yuntu_highlights -v`

Expected: PASS.

- [ ] **Step 3: Run all tests**

Run: `python -m unittest discover -s tests -v`

Expected: PASS with no failures.

- [ ] **Step 4: Gather real-run benchmark evidence**

Run a new normal `fetch` batch. For each material, compare the old and new frame count, `(frame_type, second)` pairs, JPEG dimensions, FFmpeg decodability, and SHA-256. Record video-download duration separately from `postprocessTimingsSec.highlightSec`; do not claim an end-to-end multiplier until both are measured.
