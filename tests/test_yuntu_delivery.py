import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from PIL import Image
from openpyxl import Workbook
from openpyxl.drawing.image import Image as WorkbookImage

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import rpa_connector


class DeliveryTests(unittest.TestCase):
    def fixture(self, root):
        output = root / "final-report"
        output.mkdir()
        (output / "assets").mkdir()
        Image.new("RGB", (8, 8), "red").save(output / "assets/frame.jpg")
        (output / "assets/video.mp4").write_bytes(b"retained-local-video")
        sections = ["top-material-combination", "audience-insights", "script-insights",
                    "highlight-insights", "material-deep-dive"]
        html = '<script>if (x !== undefined) {}</script>' + ''.join(
            f'<a href="#{key}">go</a><section id="{key}">正文</section>' for key in sections
        ) + ('<img src="assets/frame.jpg"><video src="assets/video.mp4" controls></video>'
             '<a href="highlight-frames.xlsx">Excel</a>')
        (output / "final-report.html").write_text(html)
        (output / "final-report.md").write_text("# 完整报告")
        (output / "presentation-report.json").write_text('{"chapters": {}}')
        (output / "final-report-data.json").write_text(json.dumps({
            "status": "complete", "analysis": {}, "highlightFrames": {"f": {"available": True}}
        }))
        book = Workbook()
        book.active.title = "高光帧资产"
        book.active.add_image(WorkbookImage(output / "assets/frame.jpg"), "A1")
        book.create_sheet("标准分类")
        book.create_sheet("本批次标准")
        book.save(output / "highlight-frames.xlsx")
        return output

    def verify(self, output):
        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            code = rpa_connector.main(["verify-report", "--output-dir", str(output)])
        return code, json.loads(stdout.getvalue())

    def test_verifies_report_directory_without_sibling_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = self.fixture(Path(tmp))
            code, result = self.verify(output)
            self.assertEqual(code, 0)
            self.assertTrue(result["valid"])
            self.assertEqual(result["errors"], [])
            self.assertEqual(result["localReferenceCount"], 3)
            self.assertFalse(output.with_suffix(".zip").exists())

    def test_reports_directory_file_statistics_without_archive_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = self.fixture(Path(tmp))
            _, result = self.verify(output)
            self.assertFalse([key for key in result if key.startswith("archive")])
            self.assertIn("reportFileCount", result)
            self.assertEqual(result["reportFileCount"], 7)
            self.assertEqual(result["reportBytes"], sum(
                path.stat().st_size for path in output.rglob("*") if path.is_file()
            ))

    def test_ignores_existing_invalid_sibling_zip_without_modifying_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = self.fixture(Path(tmp))
            archive = output.with_suffix(".zip")
            archive.write_bytes(b"old invalid ZIP preserved as user data")
            original_bytes, original_mtime = archive.read_bytes(), archive.stat().st_mtime_ns
            code, result = self.verify(output)
            self.assertEqual(archive.read_bytes(), original_bytes)
            self.assertEqual(archive.stat().st_mtime_ns, original_mtime)
            self.assertEqual(code, 0)
            self.assertTrue(result["valid"])
            self.assertEqual(result["errors"], [])
            self.assertFalse([key for key in result if key.startswith("archive")])

    def test_rejects_missing_local_image_or_video_with_actionable_paths(self):
        for relative_path in ("assets/frame.jpg", "assets/video.mp4"):
            with self.subTest(path=relative_path), tempfile.TemporaryDirectory() as tmp:
                output = self.fixture(Path(tmp))
                (output / relative_path).unlink()
                code, result = self.verify(output)
                self.assertEqual(code, 1)
                self.assertFalse(result["valid"])
                self.assertIn(
                    f"missing or outside report local reference: {relative_path}",
                    result["errors"],
                )
                self.assertFalse(any("ZIP" in error for error in result["errors"]))

    def test_rejects_workbook_with_missing_embedded_frames_even_with_valid_crc(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = self.fixture(Path(tmp))
            book = Workbook()
            book.active.title = "高光帧资产"
            book.create_sheet("标准分类")
            book.create_sheet("本批次标准")
            book.save(output / "highlight-frames.xlsx")
            code, result = self.verify(output)
            self.assertEqual(code, 1)
            self.assertTrue(any("embedded" in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
