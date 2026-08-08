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
            "topMaterialCombination": {
                "overallConclusions": [
                    {
                        "summary": "TOP30 总曝光占比高。",
                        "material_ids": ["101"],
                        "evidence": [{"metric": "show_cnt", "value": 1000}],
                    }
                ],
                "brandConclusions": [
                    {
                        "brand": "五个女博士",
                        "classificationSource": "title_rule",
                        "summary": "标题匹配样本以女性标签覆盖为主。",
                        "material_ids": ["101"],
                        "evidence": [{"metric": "ctr", "value": 0.2}],
                    }
                ],
            },
            "rankingOverview": [{"summary": "竞品出现价格利益点。", "material_ids": ["101"], "evidence": [{"metric": "ctr", "value": 0.7}]}],
            "materialComparison": [{"material_id": "101", "summary": "CTR 位于候选池高位。", "evidence": [{"metric": "ctr", "value": 0.7}]}],
            "materialDiagnoses": [{"material_id": "101", "summary": "第 1-2 秒出现点击高点。", "evidence": [{"trend_name": "点击指数", "start_sec": 1, "end_sec": 2}]}],
            "competitorPatterns": [{"summary": "价格利益点前置。", "material_ids": ["101"], "evidence": [{"tag": "限时抢购"}]}],
            "xiaoxianDunOpportunityMap": [{"summary": "测试通勤滋补场景。", "material_ids": ["101"], "evidence": [{"tag": "商品展示(有语音)"}]}],
            "experimentMatrix": [{"priority": "P1", "hypothesis": "通勤开场提升 3 秒播放率", "creative_variable": "前 3 秒场景钩子", "target_audience": "新锐白领", "success_metric": "play_3s_rate", "control": "现有商品直展示素材", "review_action": "按人群拆分复盘"}],
        }

    def test_render_report_writes_the_six_revised_chapters(self):
        report = load_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis_path = root / "analysis.json"
            analysis_path.write_text(json.dumps(self.analysis_json(), ensure_ascii=False), encoding="utf-8")
            status = report.render_report(analysis_json=analysis_path, output_dir=root / "final-report")
            data = json.loads((root / "final-report" / "final-report-data.json").read_text(encoding="utf-8"))
            markdown = (root / "final-report" / "final-report.md").read_text(encoding="utf-8")
            html = (root / "final-report" / "final-report.html").read_text(encoding="utf-8")

        self.assertEqual(status, 0)
        self.assertEqual(data["status"], "complete")
        for title in ("榜单竞争格局", "内容表现地图", "内容与人群机会", "竞品内容模式", "秒级创意结构", "机会与实验"):
            self.assertIn(title, markdown)
        self.assertIn("素材：101", markdown)
        self.assertIn("证据：", markdown)
        self.assertIn("假设：通勤开场提升 3 秒播放率", markdown)
        self.assertIn("成功指标：play_3s_rate", markdown)
        self.assertNotIn("附：秒级趋势洞察", markdown)
        self.assertIn("<html", html)

    def test_render_report_rejects_evidence_less_conclusion(self):
        report = load_module()
        analysis = self.analysis_json()
        del analysis["materialComparison"][0]["evidence"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "analysis.json"
            path.write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(report.YuntuReportError, "evidence"):
                report.render_report(analysis_json=path, output_dir=Path(directory) / "report")

    def test_render_report_rejects_top_material_conclusion_without_evidence(self):
        report = load_module()
        analysis = self.analysis_json()
        del analysis["topMaterialCombination"]["overallConclusions"][0]["evidence"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "analysis.json"
            path.write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(report.YuntuReportError, "topMaterialCombination.*evidence"):
                report.render_report(analysis_json=path, output_dir=Path(directory) / "report")

    def test_render_report_renders_top_material_combination_first(self):
        report = load_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis_path = root / "analysis.json"
            analysis_path.write_text(json.dumps(self.analysis_json(), ensure_ascii=False), encoding="utf-8")
            report.render_report(analysis_json=analysis_path, output_dir=root / "report")
            markdown = (root / "report" / "final-report.md").read_text(encoding="utf-8")
            rendered = (root / "report" / "final-report.html").read_text(encoding="utf-8")
        self.assertLess(markdown.index("01｜TOP 素材组合结论"), markdown.index("榜单竞争格局"))
        self.assertLess(rendered.index("01｜TOP 素材组合结论"), rendered.index("榜单竞争格局"))
        self.assertIn("标题匹配归属", rendered)

    def test_render_report_rejects_incomplete_experiment(self):
        report = load_module()
        analysis = self.analysis_json()
        del analysis["experimentMatrix"][0]["control"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "analysis.json"
            path.write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(report.YuntuReportError, "control"):
                report.render_report(analysis_json=path, output_dir=Path(directory) / "report")

    def test_render_report_renders_styled_cover_and_highlight_gallery(self):
        report = load_module()
        fact_pack = {"materialFacts": [{"material_id": "101", "highlightFrames": [{"second": 0, "available": True, "relative_path": "../highlights/101/01-000s.jpg", "is_cover": True, "reasons": [{"type": "cover"}]}]}]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis_path = root / "analysis.json"
            analysis_path.write_text(json.dumps(self.analysis_json(), ensure_ascii=False), encoding="utf-8")
            report.render_report(analysis_json=analysis_path, output_dir=root / "final-report", fact_pack=fact_pack)
            rendered = (root / "final-report" / "final-report.html").read_text(encoding="utf-8")
        self.assertIn('class="report-cover"', rendered)
        self.assertIn('class="highlight-gallery"', rendered)
        self.assertIn('src="../highlights/101/01-000s.jpg"', rendered)

    def test_render_report_uses_fact_pack_filters_in_cover_subtitle(self):
        report = load_module()
        fact_pack = {
            "filters": {
                "industry": "食品饮料",
                "brands": ["小仙炖", "诺特兰德"],
                "custom_start_date": "2026-07-26",
                "custom_end_date": "2026-08-01",
            }
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis_path = root / "analysis.json"
            analysis_path.write_text(json.dumps(self.analysis_json(), ensure_ascii=False), encoding="utf-8")
            report.render_report(analysis_json=analysis_path, output_dir=root / "final-report", fact_pack=fact_pack)
            rendered = (root / "final-report" / "final-report.html").read_text(encoding="utf-8")
        self.assertIn("食品饮料行业｜小仙炖、诺特兰德｜2026-07-26 至 2026-08-01", rendered)
        self.assertNotIn("好丽友、香飘飘", rendered)

    def test_render_report_separates_insight_evidence_into_details(self):
        report = load_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis_path = root / "analysis.json"
            analysis_path.write_text(json.dumps(self.analysis_json(), ensure_ascii=False), encoding="utf-8")
            report.render_report(analysis_json=analysis_path, output_dir=root / "final-report")
            rendered = (root / "final-report" / "final-report.html").read_text(encoding="utf-8")
        self.assertIn('class="insight-row"', rendered)
        self.assertNotIn('class="material-reference" href="#material-101"', rendered)
        self.assertIn('<details class="evidence-details">', rendered)
        self.assertIn("查看数据依据", rendered)

    def test_render_report_uses_accessible_highlight_gallery(self):
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
        self.assertIn('aria-label="查看 101 封面 高光帧"', rendered)
        self.assertIn('aria-label="关闭高光帧预览"', rendered)

    def test_render_report_uses_the_shared_background_tokens(self):
        report = load_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis_path = root / "analysis.json"
            analysis_path.write_text(json.dumps(self.analysis_json(), ensure_ascii=False), encoding="utf-8")
            report.render_report(analysis_json=analysis_path, output_dir=root / "final-report")
            rendered = (root / "final-report" / "final-report.html").read_text(encoding="utf-8")
        self.assertIn("body{margin:0;background:var(--bg)", rendered)
        self.assertIn("--paper:#fff8ec", rendered)

    def test_render_report_removes_summary_dashboard_and_material_nav(self):
        report = load_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis_path = root / "analysis.json"
            analysis_path.write_text(json.dumps(self.analysis_json(), ensure_ascii=False), encoding="utf-8")
            report.render_report(analysis_json=analysis_path, output_dir=root / "final-report")
            rendered = (root / "final-report" / "final-report.html").read_text(encoding="utf-8")
        self.assertNotIn('class="dashboard"', rendered)
        self.assertNotIn('class="material-nav"', rendered)
        self.assertNotIn("候选素材", rendered)
        self.assertIn('class="report-nav"', rendered)

    def test_render_report_places_second_level_structure_after_competitor_section(self):
        report = load_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis_path = root / "analysis.json"
            analysis_path.write_text(json.dumps(self.analysis_json(), ensure_ascii=False), encoding="utf-8")
            report.render_report(analysis_json=analysis_path, output_dir=root / "final-report")
            rendered = (root / "final-report" / "final-report.html").read_text(encoding="utf-8")
        self.assertLess(rendered.index('id="competitor"'), rendered.index('id="second-by-second"'))
        self.assertEqual(rendered.count('id="second-by-second"'), 1)

    def test_render_report_constrains_all_highlight_images(self):
        report = load_module()
        fact_pack = {"materialFacts": [{"material_id": "101", "highlightFrames": [
            {"second": 0, "available": True, "relative_path": "../highlights/101/01-000s.jpg", "is_cover": True},
            {"second": 2, "available": True, "relative_path": "../highlights/101/02-002s.jpg"},
        ]}]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis_path = root / "analysis.json"
            analysis_path.write_text(json.dumps(self.analysis_json(), ensure_ascii=False), encoding="utf-8")
            report.render_report(analysis_json=analysis_path, output_dir=root / "final-report", fact_pack=fact_pack)
            rendered = (root / "final-report" / "final-report.html").read_text(encoding="utf-8")
        self.assertIn(".highlight-gallery{display:grid", rendered)
        self.assertIn(".frame-button img{display:block;width:100%", rendered)
        self.assertIn("minmax(88px,1fr)", rendered)

    def test_render_report_uses_top1000_charts_and_source_traceability(self):
        report = load_module()
        fact_pack = {
            "candidatePool": {"metrics": {"ctr": {"median": 0.1}}},
            "tagInsights": {
                "materialTags": {"成分_维C": {"count": 3, "selectedMaterialCount": 1}},
                "peopleTags": {"女性": {"count": 4, "selectedMaterialCount": 1}},
            },
            "trendSummary": {"byTrendName": {"点击指数": {"highPointCount": 2, "lossPointCount": 1}}},
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis_path = root / "analysis.json"
            analysis_path.write_text(json.dumps(self.analysis_json(), ensure_ascii=False), encoding="utf-8")
            report.render_report(analysis_json=analysis_path, output_dir=root / "final-report", fact_pack=fact_pack)
            rendered = (root / "final-report" / "final-report.html").read_text(encoding="utf-8")
        self.assertNotIn('id="metric-sort"', rendered)
        self.assertNotIn('id="tag-category"', rendered)
        self.assertNotIn('id="performance-table"', rendered)
        self.assertIn('id="material-tag-chart"', rendered)
        self.assertIn('id="people-tag-chart"', rendered)
        self.assertEqual(rendered.count('class="pie-layout"'), 2)
        self.assertIn('class="pie-legend"', rendered)
        self.assertGreaterEqual(rendered.count('border-radius:50%'), 2)
        self.assertIn('grid-template-columns:300px minmax(0,400px)', rendered)
        self.assertIn('data-pie-slices=', rendered)
        self.assertIn('class="pie-tooltip"', rendered)
        self.assertIn('class="performance-insights"', rendered)
        self.assertIn("CTR 位于候选池高位。", rendered)
        self.assertIn('id="frame-material"', rendered)
        self.assertIn("来源：Top1000 榜单数据", rendered)
        self.assertIn("来源：单素材秒级详情", rendered)
        self.assertIn("来源：榜单 + 秒级详情派生", rendered)
        self.assertIn("高光帧汇总", rendered)
        self.assertIn('<dialog id="lightbox">', rendered)


if __name__ == "__main__":
    unittest.main()
