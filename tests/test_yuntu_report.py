import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
MODULE_PATH = SCRIPTS_DIR / "yuntu_report.py"


def load_module():
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    spec = importlib.util.spec_from_file_location("yuntu_report", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class YuntuReportTests(unittest.TestCase):
    def analysis_json(self):
        return {
            "overallConclusion": "本批次素材以价格钩子和独立包装卖点表现突出。",
            "rankingInsights": ["101 CTR 高于批次均值。"],
            "audienceInsights": ["都市银发标签出现 1 次。"],
            "tagInsights": ["包装_独立包装出现 1 次。"],
            "trendInsights": ["101 点击指数在 1-2 秒形成高点。"],
            "materialAnalyses": [{"material_id": "101", "summary": "首秒承接点击。"}],
            "creativePatterns": ["价格利益点前置。"],
            "nextActions": ["测试小仙炖礼盒装价格锚点表达。"],
        }

    def test_render_report_writes_data_markdown_and_html(self):
        report = load_module()
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            analysis_path = root / "diagnostic-analysis" / "yuntu-ai-analysis.json"
            analysis_path.parent.mkdir()
            analysis_path.write_text(
                json.dumps(self.analysis_json(), ensure_ascii=False), encoding="utf-8"
            )
            status = report.render_report(
                analysis_json=analysis_path,
                output_dir=root / "final-report",
            )

            data = json.loads(
                (root / "final-report" / "final-report-data.json").read_text(
                    encoding="utf-8"
                )
            )
            markdown = (root / "final-report" / "final-report.md").read_text(
                encoding="utf-8"
            )
            html = (root / "final-report" / "final-report.html").read_text(
                encoding="utf-8"
            )

        self.assertEqual(status, 0)
        self.assertEqual(data["status"], "complete")
        self.assertIn("行业榜单整体结论", markdown)
        self.assertIn("本批次素材以价格钩子", markdown)
        self.assertIn("<html", html)

    def test_render_report_rejects_missing_required_sections(self):
        report = load_module()
        with tempfile.TemporaryDirectory() as temporary_directory:
            analysis_path = Path(temporary_directory) / "analysis.json"
            analysis_path.write_text(
                json.dumps({"overallConclusion": "只有结论"}, ensure_ascii=False),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(report.YuntuReportError, "missing"):
                report.render_report(
                    analysis_json=analysis_path,
                    output_dir=Path(temporary_directory) / "report",
                )


if __name__ == "__main__":
    unittest.main()
