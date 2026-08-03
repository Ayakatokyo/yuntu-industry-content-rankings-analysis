import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


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
                Path(destination).write_bytes(b"jpeg")

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


if __name__ == "__main__":
    unittest.main()
