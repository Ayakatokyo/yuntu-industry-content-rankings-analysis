import sys
import unittest
from contextlib import redirect_stderr
from io import StringIO
import tempfile
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from yuntu_highlight_export import (  # noqa: E402
    build_highlight_export_rows,
    export_highlight_workbook,
)


class HighlightExportTests(unittest.TestCase):
    def _write_image(self, root, relative_path, size):
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", size, color=(200, 120, 80)).save(path, format="JPEG")
        return path

    def _gallery_fixture(self, root):
        frames = []
        categories = []
        for index, (category, size) in enumerate(
            (("portrait", (100, 200)), ("product", (200, 100)), ("other", (120, 120))),
            start=1,
        ):
            ref = f"highlight:101:{category}:{index}"
            relative_path = f"highlights/101/{index:02d}.jpg"
            self._write_image(root, relative_path, size)
            frames.append({
                "frame_ref": ref,
                "second": index,
                "frame_type": "click_peak",
                "peak_rank": index,
                "click_value": 0.8,
                "available": True,
                "relative_path": relative_path,
            })
            categories.append({"id": category, "frames": [{"frameRef": ref}]})
        fact_pack = {
            "filters": {"brands": ["小仙炖"]},
            "materialFacts": [{
                "material_id": "101",
                "rank": 1,
                "title": "小仙炖测试素材",
                "highlightFrames": frames,
            }],
        }
        return fact_pack, {"categories": categories}

    def test_export_uses_openpyxl_and_pillow_by_default(self):
        fact_pack = {
            "filters": {"brands": ["小仙炖"]},
            "materialFacts": [{
                "material_id": "101",
                "title": "小仙炖测试素材",
                "highlightFrames": [{"frame_ref": "f1", "available": True}],
            }],
        }
        with tempfile.TemporaryDirectory() as tmp, redirect_stderr(StringIO()) as stderr:
            result = export_highlight_workbook(
                fact_pack, {}, Path(tmp) / "highlight-frames.xlsx"
            )
        self.assertIsNotNone(result)
        self.assertNotIn("高光帧资产导出不可用", stderr.getvalue())

    def test_export_writes_workbook_without_images(self):
        fact_pack = {
            "filters": {"brands": ["小仙炖"]},
            "materialFacts": [{
                "material_id": "101", "rank": 1, "title": "小仙炖测试素材",
                "highlightFrames": [{"frame_ref": "f1", "available": True, "second": 0}],
            }],
        }
        with tempfile.TemporaryDirectory() as tmp:
            output = export_highlight_workbook(fact_pack, {}, Path(tmp) / "highlight-frames.xlsx")
            self.assertTrue(output.is_file())
            self.assertGreater(output.stat().st_size, 0)

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

    def test_exports_highlight_images_with_source_ratio_and_covering_row_height(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fact_pack, presentation = self._gallery_fixture(root)
            output = export_highlight_workbook(
                fact_pack, presentation, root / "highlight-frames.xlsx", asset_root=root
            )
            workbook = load_workbook(output)
            sheet = workbook["高光帧资产"]
            self.assertEqual(len(sheet._images), 3)
            self.assertEqual(sheet.auto_filter.ref, "A1:J4")
            self.assertEqual(sheet.freeze_panes, "A2")
            expected_ratios = [100 / 200, 200 / 100, 1]
            for image, source_ratio in zip(sheet._images, expected_ratios):
                self.assertEqual(image.anchor._from.col, 6)
                row = image.anchor._from.row + 1
                width = image.anchor.ext.width / 9525
                height = image.anchor.ext.height / 9525
                self.assertGreaterEqual(sheet.row_dimensions[row].height, height * 0.75)
                self.assertAlmostEqual(width / height, source_ratio, places=2)
            self.assertGreaterEqual(sheet.column_dimensions["G"].width, 18)
            self.assertIsNotNone(sheet.tables["HighlightFramesTable"])

    def test_exports_highlight_gallery_with_all_categories_and_internal_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fact_pack, presentation = self._gallery_fixture(root)
            output = export_highlight_workbook(
                fact_pack, presentation, root / "highlight-frames.xlsx", asset_root=root
            )
            workbook = load_workbook(output)
            self.assertEqual(workbook.sheetnames, ["高光帧资产", "高光帧图片墙"])
            sheet = workbook["高光帧图片墙"]
            labels = [sheet.cell(1, col).value for col in range(1, 5)]
            self.assertEqual(labels, ["全量", "人像画面", "产品画面", "其他画面"])
            self.assertEqual(
                [sheet.cell(1, col).hyperlink.location for col in range(1, 5)],
                ["'高光帧图片墙'!A3", "'高光帧图片墙'!A7", "'高光帧图片墙'!A11", "'高光帧图片墙'!A15"],
            )
            self.assertEqual(len(sheet._images), 6)
            text = "\n".join(
                str(cell.value or "")
                for row in sheet.iter_rows()
                for cell in row
            )
            self.assertNotIn("素材排名", text)
            self.assertNotIn("点击指数", text)
            self.assertTrue(all(cell.hyperlink.location for cell in sheet[1]))
            self.assertGreaterEqual(sheet.column_dimensions[get_column_letter(1)].width, 18)


if __name__ == "__main__":
    unittest.main()
