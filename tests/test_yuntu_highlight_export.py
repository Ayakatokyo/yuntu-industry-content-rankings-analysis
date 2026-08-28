import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from yuntu_highlight_export import build_highlight_export_rows  # noqa: E402


class HighlightExportTests(unittest.TestCase):
    def test_builds_report_aligned_rows_and_excludes_unavailable_frames(self):
        fact_pack = {
            "filters": {"brands": ["小仙炖"]},
            "materialFacts": [{
                "material_id": "101",
                "rank": 3,
                "title": "小仙炖测试素材",
                "highlightFrames": [
                    {"frame_ref": "highlight:101:cover:0", "second": 0, "frame_type": "cover", "available": True, "relative_path": "highlights/101/01-000s.jpg"},
                    {"frame_ref": "highlight:101:click_peak:2", "second": 2, "frame_type": "click_peak", "peak_rank": 1, "click_value": 0.8, "available": True, "relative_path": "highlights/101/02-002s.jpg"},
                    {"frame_ref": "highlight:101:click_peak:9", "second": 9, "frame_type": "click_peak", "available": False, "relative_path": ""},
                ],
            }],
        }
        rows = build_highlight_export_rows(fact_pack)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["品牌"], "小仙炖")
        self.assertEqual(rows[0]["画面类型"], "封面画面")
        self.assertEqual(rows[1]["画面类型"], "点击 Top1 波峰画面")
        self.assertEqual(rows[1]["秒数"], 2)
        self.assertEqual(rows[1]["点击指数"], 0.8)
        self.assertEqual(rows[1]["素材标题"], "小仙炖测试素材")


if __name__ == "__main__":
    unittest.main()
