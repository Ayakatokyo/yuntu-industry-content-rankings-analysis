import importlib.util
import hashlib
import json
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "yuntu_highlights.py"


def load_module():
    spec = importlib.util.spec_from_file_location("yuntu_highlights", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def detail_with_trends(*trends, high_points=None):
    return {
        "trend_series": list(trends),
        "high_points": high_points or [],
    }


class YuntuHighlightTests(unittest.TestCase):
    def test_normalize_highlight_trends_deduplicates_and_rejects_unknown_names(self):
        highlights = load_module()

        self.assertEqual(
            highlights.normalize_highlight_trends(["点击指数", "点赞指数", "点击指数"]),
            ["点击指数", "点赞指数"],
        )
        with self.assertRaisesRegex(ValueError, "未知"):
            highlights.normalize_highlight_trends(["播放指数"])

    def test_select_candidates_keeps_cover_and_ranks_three_local_peaks(self):
        highlights = load_module()
        detail = detail_with_trends(
            {
                "trend_name": "点击指数",
                "series": [
                    {"second": 0, "value": 0},
                    {"second": 1, "value": 9},
                    {"second": 2, "value": 1},
                    {"second": 3, "value": 8},
                    {"second": 4, "value": 1},
                    {"second": 5, "value": 7},
                    {"second": 6, "value": 1},
                    {"second": 7, "value": 0},
                ],
            }
        )

        candidates = highlights.select_highlight_candidates(detail, ["点击指数"])

        self.assertEqual([item["second"] for item in candidates], [0, 1, 3, 5])
        self.assertEqual(candidates[0], {"second": 0, "is_cover": True, "reasons": [{"type": "cover"}]})
        self.assertEqual(
            candidates[1]["reasons"],
            [{"type": "local_peak", "trend_name": "点击指数", "value": 9, "rank": 1, "within_high_point": False}],
        )
        self.assertEqual([item["reasons"][0]["rank"] for item in candidates[1:]], [1, 2, 3])

    def test_select_standard_candidates_keeps_cover_and_click_top_five(self):
        highlights = load_module()
        detail = detail_with_trends(
            {
                "trend_name": "点击指数",
                "series": [
                    {"second": 0, "value": 0},
                    {"second": 1, "value": 9}, {"second": 2, "value": 0},
                    {"second": 3, "value": 8}, {"second": 4, "value": 0},
                    {"second": 5, "value": 7}, {"second": 6, "value": 0},
                    {"second": 7, "value": 6}, {"second": 8, "value": 0},
                    {"second": 9, "value": 5}, {"second": 10, "value": 0},
                    {"second": 11, "value": 4}, {"second": 12, "value": 0},
                ],
            },
            {
                "trend_name": "点赞指数",
                "series": [{"second": 2, "value": 0}, {"second": 3, "value": 99}, {"second": 4, "value": 0}],
            },
        )

        candidates = highlights.select_standard_highlight_candidates(detail)

        self.assertEqual([item["second"] for item in candidates], [0, 1, 3, 5, 7, 9])
        self.assertEqual(candidates[0]["frame_type"], "cover")
        self.assertIsNone(candidates[0]["peak_rank"])
        self.assertEqual(
            [(item["frame_type"], item["peak_rank"], item["click_value"]) for item in candidates[1:]],
            [("click_peak", 1, 9), ("click_peak", 2, 8), ("click_peak", 3, 7), ("click_peak", 4, 6), ("click_peak", 5, 5)],
        )

    def test_standard_candidates_merge_a_zero_second_click_peak_into_the_cover(self):
        highlights = load_module()
        detail = detail_with_trends(
            {
                "trend_name": "点击指数",
                "series": [
                    {"second": 0, "value": 9}, {"second": 1, "value": 0},
                    {"second": 2, "value": 8}, {"second": 3, "value": 0},
                ],
            }
        )

        candidates = highlights.select_standard_highlight_candidates(detail)

        self.assertEqual([candidate["second"] for candidate in candidates], [0, 2])
        self.assertEqual(candidates[0]["frame_type"], "cover")
        self.assertEqual(candidates[0]["peak_rank"], 1)
        self.assertEqual(candidates[0]["click_value"], 9)
        self.assertEqual([reason["type"] for reason in candidates[0]["reasons"]], ["cover", "local_peak"])

    def test_select_candidates_uses_earliest_second_for_peak_plateau(self):
        highlights = load_module()
        detail = detail_with_trends(
            {
                "trend_name": "互动指数",
                "series": [
                    {"second": 1, "value": 1},
                    {"second": 2, "value": 4},
                    {"second": 2, "value": 5},
                    {"second": 3, "value": 5},
                    {"second": 4, "value": 1},
                ],
            }
        )

        candidates = highlights.select_highlight_candidates(detail, ["互动指数"])

        self.assertEqual([item["second"] for item in candidates], [0, 2])
        self.assertEqual(candidates[1]["reasons"][0]["value"], 5)

    def test_select_candidates_merges_same_second_across_metrics(self):
        highlights = load_module()
        detail = detail_with_trends(
            {
                "trend_name": "点击指数",
                "series": [{"second": 4, "value": 1}, {"second": 5, "value": 6}, {"second": 6, "value": 1}],
            },
            {
                "trend_name": "点赞指数",
                "series": [{"second": 4, "value": 1}, {"second": 5, "value": 4}, {"second": 6, "value": 1}],
            },
        )

        candidates = highlights.select_highlight_candidates(detail, ["点击指数", "点赞指数"])

        self.assertEqual([item["second"] for item in candidates], [0, 5])
        self.assertEqual(
            candidates[1]["reasons"],
            [
                {"type": "local_peak", "trend_name": "点击指数", "value": 6, "rank": 1, "within_high_point": False},
                {"type": "local_peak", "trend_name": "点赞指数", "value": 4, "rank": 1, "within_high_point": False},
            ],
        )

    def test_select_candidates_marks_named_high_point_membership(self):
        highlights = load_module()
        detail = detail_with_trends(
            {
                "trend_name": "评论指数",
                "series": [{"second": 4, "value": 1}, {"second": 5, "value": 3}, {"second": 6, "value": 1}],
            },
            high_points=[
                {"trend_name": "评论指数", "start_sec": 5, "end_sec": 5},
                {"trend_name": "点击指数", "start_sec": 5, "end_sec": 5},
            ],
        )

        candidates = highlights.select_highlight_candidates(detail, ["评论指数"])

        self.assertTrue(candidates[1]["reasons"][0]["within_high_point"])

    def test_generate_highlights_writes_manifest_and_continues_after_one_frame_failure(self):
        highlights = load_module()

        class Downloader:
            def __call__(self, _url, destination):
                Path(destination).write_bytes(b"video")

        class Extractor:
            def __call__(self, _video_path, second, destination, *, ffmpeg_bin=None):
                if second == 0:
                    raise highlights.HighlightFrameError("broken cover")
                Path(destination).write_bytes(b"\xff\xd8jpeg\xff\xd9")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = highlights.generate_highlights(
                [
                    {
                        "material_id": "101",
                        "video_url": "https://video.example/101.mp4",
                        "trend_series": [
                            {
                                "trend_name": "点击指数",
                                "series": [
                                    {"second": 1, "value": 1},
                                    {"second": 2, "value": 4},
                                    {"second": 3, "value": 1},
                                ],
                            }
                        ],
                    }
                ],
                ["点击指数"],
                root,
                downloader=Downloader(),
                frame_extractor=Extractor(),
            )

            manifest = json.loads(
                (root / "highlights-manifest.json").read_text(encoding="utf-8")
            )
            self.assertFalse(result["101"][0]["available"])
            self.assertEqual(result["101"][0]["failure_reason"], "extract_failed")
            self.assertTrue(result["101"][1]["available"])
            self.assertTrue((root / result["101"][1]["relative_path"]).is_file())
            self.assertEqual(
                manifest["materials"][0]["frames"][0]["failure_reason"],
                "extract_failed",
            )

    def test_generate_highlights_marks_missing_video_url_without_raising(self):
        highlights = load_module()
        with tempfile.TemporaryDirectory() as directory:
            result = highlights.generate_highlights(
                [{"material_id": "101", "video_url": "", "trend_series": []}],
                ["评论指数"],
                directory,
            )

        self.assertFalse(result["101"][0]["available"])
        self.assertEqual(result["101"][0]["failure_reason"], "missing_video_url")

    def test_standard_highlights_reject_unattributed_frames_when_video_download_fails(self):
        highlights = load_module()

        def failing_downloader(_url, _destination):
            raise highlights.HighlightFrameError("expired")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            existing = root / "highlights" / "101" / "01-000s.jpg"
            existing.parent.mkdir(parents=True)
            existing.write_bytes(b"\xff\xd8jpeg\xff\xd9")

            result = highlights.generate_standard_highlights(
                [{"material_id": "101", "video_url": "https://video.example/101.mp4", "trend_series": []}],
                root,
                downloader=failing_downloader,
            )

        self.assertFalse(result["101"][0]["available"])
        self.assertEqual(result["101"][0]["failure_reason"], "download_failed")

    def test_standard_highlights_retains_downloaded_video_and_records_it_in_manifest(self):
        highlights = load_module()

        def downloader(_url, destination):
            Path(destination).write_bytes(b"retained-video")

        def batch_extractor(_video_path, requests, *, ffmpeg_bin=None):
            for request in requests:
                Path(request["destination"]).write_bytes(b"\xff\xd8frame\xff\xd9")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            highlights.generate_standard_highlights(
                [{"material_id": "101", "video_url": "https://video.example/101.mp4", "trend_series": []}],
                root,
                downloader=downloader,
                batch_extractor=batch_extractor,
            )
            manifest = json.loads((root / "highlights-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual((root / "video-assets" / "101.mp4").read_bytes(), b"retained-video")
            self.assertEqual(manifest["materials"][0]["video"], {
                "available": True,
                "relative_path": "video-assets/101.mp4",
                "size_bytes": 14,
            })

    def test_single_material_standard_highlights_reuses_complete_manifest(self):
        highlights = load_module()
        detail = {
            "material_id": "101",
            "video_url": "https://video.example/101.mp4",
            "trend_series": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "highlights" / "101" / "01-000s.jpg"
            image.parent.mkdir(parents=True)
            image.write_bytes(b"\xff\xd8jpeg\xff\xd9")
            highlights.write_highlights_manifest(
                root,
                {
                    "101": [
                        {
                            "frame_ref": "highlight:101:cover:0",
                            "second": 0,
                            "is_cover": True,
                            "frame_type": "cover",
                            "peak_rank": None,
                            "click_value": None,
                            "reasons": [{"type": "cover"}],
                            "available": True,
                            "relative_path": "highlights/101/01-000s.jpg",
                        }
                    ]
                },
            )
            frames = highlights.generate_standard_highlights_for_detail(
                detail,
                root,
                downloader=lambda *_args: self.fail("unexpected video download"),
                frame_extractor=lambda *_args, **_kwargs: self.fail("unexpected frame extraction"),
            )

        self.assertTrue(frames[0]["available"])
        self.assertEqual(frames[0]["frame_source"], "reused_local_extracted_frame")

    def test_details_missing_standard_highlights_detects_missing_frame_file(self):
        highlights = load_module()
        details = [
            {"material_id": "101", "trend_series": []},
            {"material_id": "202", "trend_series": []},
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            highlights.write_highlights_manifest(
                root,
                {
                    "101": [
                        {
                            "frame_ref": "highlight:101:cover:0",
                            "second": 0,
                            "is_cover": True,
                            "frame_type": "cover",
                            "available": True,
                            "relative_path": "highlights/101/missing.jpg",
                        }
                    ]
                },
            )
            missing = highlights.details_missing_standard_highlights(details, root)

        self.assertEqual([item["material_id"] for item in missing], ["101", "202"])

    def test_generate_highlights_rejects_unattributed_frame_when_extraction_fails(self):
        highlights = load_module()

        def downloader(_url, destination):
            Path(destination).write_bytes(b"video")

        def failing_extractor(_video_path, _second, _destination, *, ffmpeg_bin=None):
            raise highlights.HighlightFrameError("cannot seek")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            existing = root / "highlights" / "101" / "01-000s.jpg"
            existing.parent.mkdir(parents=True)
            existing.write_bytes(b"\xff\xd8jpeg\xff\xd9")

            result = highlights.generate_highlights(
                [{"material_id": "101", "video_url": "https://video.example/101.mp4", "trend_series": []}],
                ["点击指数"],
                root,
                downloader=downloader,
                frame_extractor=failing_extractor,
            )

        self.assertFalse(result["101"][0]["available"])
        self.assertEqual(result["101"][0]["failure_reason"], "extract_failed")

    def test_orphan_frames_require_receipt_matching_current_video_and_frame(self):
        highlights = load_module()
        detail = {"material_id": "101", "trend_series": []}
        calls = []
        def extract(video, requests, **_kwargs):
            calls.append(Path(video).read_bytes())
            for request in requests:
                Path(request["destination"]).write_bytes(b"\xff\xd8" + calls[-1] + b"\xff\xd9")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "video-assets/101.mp4"
            video.parent.mkdir(parents=True)
            video.write_bytes(b"blue-video")
            cover = root / "highlights/101/01-000s.jpg"
            cover.parent.mkdir(parents=True)
            cover.write_bytes(b"\xff\xd8stale-red-frame\xff\xd9")
            highlights.generate_standard_highlights_for_detail(detail, root, batch_extractor=extract)
            self.assertEqual(cover.read_bytes(), b"\xff\xd8blue-video\xff\xd9")
            highlights.generate_standard_highlights_for_detail(detail, root, batch_extractor=extract)
            self.assertEqual(len(calls), 1)
            video.write_bytes(b"green-video")
            highlights.generate_standard_highlights_for_detail(detail, root, batch_extractor=extract)
            self.assertEqual(cover.read_bytes(), b"\xff\xd8green-video\xff\xd9")
            self.assertEqual(len(calls), 2)
            cover.write_bytes(b"\xff\xd8replaced-image\xff\xd9")
            highlights.generate_standard_highlights_for_detail(detail, root, batch_extractor=extract)
            self.assertEqual(cover.read_bytes(), b"\xff\xd8green-video\xff\xd9")
            self.assertEqual(len(calls), 3)

    def test_interrupted_highlights_reuse_valid_frames_and_extract_only_missing_seconds(self):
        highlights = load_module()
        detail = {
            "material_id": "101", "trend_series": [{"trend_name": "点击指数", "series": [
                {"second": 0, "value": 0}, {"second": 1, "value": 9},
                {"second": 2, "value": 0}, {"second": 3, "value": 8}, {"second": 4, "value": 0},
            ]}],
        }
        extracted = []
        def batch_extractor(_video, requests, **_kwargs):
            extracted.extend(request["second"] for request in requests)
            for request in requests:
                Path(request["destination"]).write_bytes(b"\xff\xd8new\xff\xd9")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "video-assets" / "101.mp4"
            video.parent.mkdir(parents=True)
            video.write_bytes(b"local-video")
            cover = root / "highlights" / "101" / "01-000s.jpg"
            cover.parent.mkdir(parents=True)
            cover.write_bytes(b"\xff\xd8old-cover\xff\xd9")
            (cover.parent / "frame-source.json").write_text(json.dumps({
                "schemaVersion": 1, "videoSha256": hashlib.sha256(video.read_bytes()).hexdigest(),
                "frames": {cover.name: {"second": 0, "sha256": hashlib.sha256(cover.read_bytes()).hexdigest()}},
            }))
            # This file exists but was interrupted before a complete JPEG landed.
            (cover.parent / "02-001s.jpg").write_bytes(b"\xff\xd8broken")
            frames = highlights.generate_standard_highlights_for_detail(
                detail, root, downloader=lambda *_args: self.fail("local video must be reused"),
                batch_extractor=batch_extractor,
            )
            self.assertEqual(extracted, [1, 3])
            self.assertEqual(cover.read_bytes(), b"\xff\xd8old-cover\xff\xd9")
            self.assertTrue(all(frame["available"] for frame in frames))
            self.assertEqual([frame["relative_path"] for frame in frames], [
                "highlights/101/01-000s.jpg", "highlights/101/02-001s.jpg", "highlights/101/03-003s.jpg",
            ])
            self.assertEqual(frames[0]["frame_source"], "reused_local_extracted_frame")
            # Files published before the manifest checkpoint are still reusable.
            again = highlights.generate_standard_highlights_for_detail(
                detail, root, downloader=lambda *_args: self.fail("unexpected download"),
                batch_extractor=lambda *_args, **_kwargs: self.fail("unexpected extraction"),
            )
            self.assertTrue(all(frame["available"] for frame in again))

    def test_extract_frames_batch_seeks_each_target_exactly_in_one_process(self):
        highlights = load_module()

        def run(command, **_kwargs):
            for index, token in enumerate(command):
                if token == "image2":
                    Path(command[index + 1]).write_bytes(b"\xff\xd8ok\xff\xd9")
            return mock.Mock(returncode=0, stderr="")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            requests = [
                {"second": 0, "destination": root / "cover.jpg"},
                {"second": 2, "destination": root / "peak.jpg"},
            ]
            with mock.patch.object(highlights, "_resolve_ffmpeg", return_value="ffmpeg"), \
                 mock.patch.object(highlights.subprocess, "run", side_effect=run) as invoke:
                targets = highlights.extract_frames_batch(root / "source.mp4", requests)

            command = invoke.call_args_list[0].args[0]
            graph = command[command.index("-filter_complex") + 1]
            self.assertEqual(command.count("-i"), 2)
            self.assertEqual([command[index + 1] for index, token in enumerate(command) if token == "-ss"], ["0", "2"])
            self.assertEqual(command[command.index("-threads") + 1], "1")
            self.assertEqual(command[command.index("-filter_complex_threads") + 1], "1")
            self.assertNotIn("-noaccurate_seek", command)
            for index, token in enumerate(command):
                if token == "-i":
                    self.assertEqual(command[index - 2], "-ss")
            self.assertIn("[0:v]setpts=PTS-STARTPTS[out0]", graph)
            self.assertIn("[1:v]setpts=PTS-STARTPTS[out1]", graph)
            self.assertEqual(command.count("-frames:v"), 2)
            self.assertEqual(invoke.call_count, 1)
            self.assertEqual(targets, [root / "cover.jpg", root / "peak.jpg"])
            self.assertTrue(all(path.is_file() for path in targets))

    def test_highlight_timings_separate_download_extraction_and_reuse(self):
        highlights = load_module()
        detail = {"material_id": "101", "video_url": "https://example.invalid/video.mp4", "trend_series": []}
        def download(_url, path):
            Path(path).write_bytes(b"local-video")
        def extract(_video, requests, **_kwargs):
            for request in requests:
                Path(request["destination"]).write_bytes(b"\xff\xd8frame\xff\xd9")
        with tempfile.TemporaryDirectory() as directory:
            timings = {}
            with mock.patch.object(time, "monotonic", side_effect=[100.0, 102.0, 105.0, 109.0]):
                highlights.generate_standard_highlights_for_detail(detail, directory, downloader=download, batch_extractor=extract, timings=timings)
            self.assertEqual(timings, {"videoDownloadSec": 2.0, "frameExtractionSec": 4.0})
            reused_timings = {}
            highlights.generate_standard_highlights_for_detail(detail, directory, downloader=download, batch_extractor=extract, timings=reused_timings)
            self.assertEqual(reused_timings, {"videoDownloadSec": 0.0, "frameExtractionSec": 0.0})

    def test_exact_seek_matches_full_decode_for_cfr_vfr_and_nonzero_start(self):
        highlights = load_module()
        try:
            ffmpeg = highlights._resolve_ffmpeg()
        except highlights.HighlightFrameError as exc:
            self.skipTest(str(exc))
        seconds = [0, 1, 2, 4]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, options in (
                ("cfr", []),
                ("vfr", ["-vf", "select='not(mod(n,3))'", "-fps_mode", "vfr"]),
                ("offset", ["-output_ts_offset", "5"]),
            ):
                with self.subTest(video=name):
                    video = root / f"{name}.mp4"
                    subprocess.run([
                        ffmpeg, "-loglevel", "error", "-f", "lavfi", "-i",
                        "testsrc2=size=192x108:rate=30000/1001:duration=6", *options,
                        "-c:v", "libx264", "-g", "30", "-bf", "2", "-y", str(video),
                    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=20)
                    # Independent baseline: decode from the beginning, then trim
                    # each target on the original presentation timeline.
                    graph = "[0:v]split=4[s0][s1][s2][s3];" + ";".join(
                        f"[s{index}]trim=start={second},setpts=PTS-STARTPTS[out{index}]"
                        for index, second in enumerate(seconds)
                    )
                    command = [ffmpeg, "-loglevel", "error", "-y", "-threads", "1", "-i", str(video), "-filter_complex", graph]
                    for index, second in enumerate(seconds):
                        command.extend(["-map", f"[out{index}]", "-frames:v", "1", "-q:v", "2", "-f", "image2", str(root / f"{name}-baseline-{second}.jpg")])
                    subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=20)
                    highlights.extract_frames_batch(video, [
                        {"second": second, "destination": root / f"{name}-seek-{second}.jpg"}
                        for second in seconds
                    ], ffmpeg_bin=ffmpeg)
                    for second in seconds:
                        self.assertEqual(
                            (root / f"{name}-baseline-{second}.jpg").read_bytes(),
                            (root / f"{name}-seek-{second}.jpg").read_bytes(),
                            f"{name} frame at {second}s changed",
                        )

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

    def test_standard_highlights_extract_all_frames_in_one_batch_call(self):
        highlights = load_module()
        calls = []

        def downloader(_url, destination):
            Path(destination).write_bytes(b"video")

        def batch_extractor(_video, requests, *, ffmpeg_bin=None):
            calls.append(requests)
            for request in requests:
                Path(request["destination"]).write_bytes(b"\xff\xd8ok\xff\xd9")

        detail = {
            "material_id": "101",
            "video_url": "https://video.example/101.mp4",
            "trend_series": [{
                "trend_name": "点击指数",
                "series": [
                    {"second": 0, "value": 0}, {"second": 1, "value": 9},
                    {"second": 2, "value": 0}, {"second": 3, "value": 8},
                    {"second": 4, "value": 0}, {"second": 5, "value": 7},
                    {"second": 6, "value": 0}, {"second": 7, "value": 6},
                    {"second": 8, "value": 0}, {"second": 9, "value": 5},
                    {"second": 10, "value": 0},
                ],
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            frames = highlights.generate_standard_highlights_for_detail(
                detail, directory, downloader=downloader, batch_extractor=batch_extractor
            )

        self.assertEqual(len(calls), 1)
        self.assertEqual([request["second"] for request in calls[0]], [0, 1, 3, 5, 7, 9])
        self.assertTrue(all(frame["available"] for frame in frames))

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
                detail,
                directory,
                downloader=downloader,
                frame_extractor=frame_extractor,
                batch_extractor=failed_batch,
            )

        self.assertEqual(extracted_seconds, [0])
        self.assertTrue(frames[0]["available"])

    def test_download_video_rejects_response_larger_than_limit(self):
        highlights = load_module()

        class Response:
            headers = {"Content-Length": "5"}

            def raise_for_status(self):
                return None

            def iter_content(self, chunk_size):
                yield b"12345"

            def close(self):
                return None

        class Session:
            def get(self, _url, *, stream, timeout):
                self.stream = stream
                self.timeout = timeout
                return Response()

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(highlights.HighlightFrameError, "maximum size"):
                highlights.download_video(
                    "https://video.example/a.mp4",
                    Path(directory) / "a.mp4",
                    session=Session(),
                    max_bytes=4,
                )

    def test_resolve_ffmpeg_uses_imageio_before_system_path(self):
        highlights = load_module()

        resolved = highlights._resolve_ffmpeg(
            environ={},
            imageio_resolver=lambda: "/tmp/imageio-ffmpeg",
            which=lambda _name: self.fail("PATH lookup must not run after imageio resolves"),
        )

        self.assertEqual(resolved, "/tmp/imageio-ffmpeg")

    def test_resolve_ffmpeg_falls_back_to_system_path_after_imageio_failure(self):
        highlights = load_module()

        resolved = highlights._resolve_ffmpeg(
            environ={},
            imageio_resolver=lambda: (_ for _ in ()).throw(RuntimeError("imageio unavailable")),
            which=lambda name: "/usr/local/bin/ffmpeg" if name == "ffmpeg" else None,
        )

        self.assertEqual(resolved, "/usr/local/bin/ffmpeg")


if __name__ == "__main__":
    unittest.main()
