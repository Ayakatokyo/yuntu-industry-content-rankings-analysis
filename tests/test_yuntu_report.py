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
                        "dimension": "data",
                        "summary": "TOP30 总曝光占比高，头部流量集中但并非单条素材垄断。",
                        "material_ids": ["101"],
                        "evidence": [{"hidden": "evidence-sentinel-data"}],
                    },
                    {
                        "dimension": "people",
                        "summary": "女性与新锐白领标签的曝光加权覆盖更高。",
                        "material_ids": ["101"],
                        "evidence": [{"hidden": "evidence-sentinel-audience"}],
                    },
                    {
                        "dimension": "marketing",
                        "summary": "头部素材以功效理性种草和痛点触发为主。",
                        "material_ids": ["101"],
                        "evidence": [{"hidden": "evidence-sentinel-marketing"}],
                    }
                ],
                "brandConclusions": [
                    {
                        "brand": "万益蓝/WONDERLAB",
                        "classificationSource": "title_rule",
                        "summary": "旧版兼容字段，不应再渲染。",
                        "dataSummary": "数据表现以曝光获取和前段承接为主。",
                        "peopleSummary": "人群结构以女性健康关注者为主。",
                        "marketingSummary": "营销卖点以肠道健康表达为主。",
                        "material_ids": ["101"],
                        "evidence": [{"hidden": "evidence-sentinel-brand-1"}],
                    },
                    {
                        "brand": "五个女博士",
                        "classificationSource": "title_rule",
                        "summary": "旧版兼容字段，不应再渲染。",
                        "dataSummary": "数据表现以点击与转化承接为主。",
                        "peopleSummary": "人群结构以都市女性为主。",
                        "marketingSummary": "营销卖点以女性营养表达为主。",
                        "material_ids": ["101"],
                        "evidence": [{"hidden": "evidence-sentinel-brand-2"}],
                    },
                    {
                        "brand": "燕之屋",
                        "classificationSource": "title_rule",
                        "summary": "旧版兼容字段，不应再渲染。",
                        "dataSummary": "数据表现以头部曝光集中为主。",
                        "peopleSummary": "人群结构以中高年龄女性为主。",
                        "marketingSummary": "营销卖点以燕窝滋补场景为主。",
                        "material_ids": ["101"],
                        "evidence": [{"hidden": "evidence-sentinel-brand-3"}],
                    }
                ],
                "brandComparisonConclusion": {
                    "summary": "真实品牌差异结论：三个品牌在头部流量结构和卖点侧重点上存在差异。",
                    "material_ids": ["101", "102", "103"],
                    "evidence": [
                        {"brand": "万益蓝/WONDERLAB", "metric": "ctr", "value": 0.2},
                        {"brand": "五个女博士", "metric": "ctr", "value": 0.3},
                        {"brand": "燕之屋", "metric": "ctr", "value": 0.4},
                    ],
                },
            },
            "rankingOverview": [{"summary": "竞品出现价格利益点。", "material_ids": ["101"], "evidence": [{"metric": "ctr", "value": 0.7}]}],
            "materialComparison": [{"material_id": "101", "summary": "CTR 位于候选池高位。", "evidence": [{"metric": "ctr", "value": 0.7}]}],
            "materialDiagnoses": [{"material_id": "101", "summary": "第 1-2 秒出现点击高点。", "evidence": [{"trend_name": "点击指数", "start_sec": 1, "end_sec": 2}]}],
            "competitorPatterns": [{"summary": "价格利益点前置。", "material_ids": ["101"], "evidence": [{"tag": "限时抢购"}]}],
            "xiaoxianDunOpportunityMap": [{"summary": "测试通勤滋补场景。", "material_ids": ["101"], "evidence": [{"tag": "商品展示(有语音)"}]}],
            "experimentMatrix": [{"priority": "P1", "hypothesis": "通勤开场提升 3 秒播放率", "creative_variable": "前 3 秒场景钩子", "target_audience": "新锐白领", "success_metric": "play_3s_rate", "control": "现有商品直展示素材", "review_action": "按人群拆分复盘"}],
        }

    def test_render_report_writes_conclusion_only_report_without_evidence(self):
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
        for rendered in (markdown, html):
            self.assertIn("品牌筛选条件下 TOP30 整体分析", rendered)
            self.assertIn("从数据维度看", rendered)
            self.assertIn("从人群维度看", rendered)
            self.assertIn("从营销卖点维度看", rendered)
            self.assertIn("人群标签是重叠标签，不是真实人群分布，不能相加为 100%。", rendered)
            self.assertIn("各品牌 TOP30 对比分析", rendered)
            self.assertIn("万益蓝/WONDERLAB", rendered)
            self.assertIn("五个女博士", rendered)
            self.assertIn("燕之屋", rendered)
            self.assertIn("品牌间差异总结", rendered)
            self.assertIn("真实品牌差异结论", rendered)
            self.assertNotIn("旧版兼容字段", rendered)
            self.assertNotIn("查看数据依据", rendered)
            self.assertNotIn('<details class="evidence-details">', rendered)
            self.assertNotIn("证据：", rendered)
            self.assertNotIn("evidence-sentinel", rendered)
            self.assertEqual(rendered.count("从数据维度看"), 4)
            self.assertEqual(rendered.count("从人群维度看"), 4)
            self.assertEqual(rendered.count("从营销卖点维度看"), 4)
        self.assertNotIn("一、品牌筛选条件下", markdown)
        self.assertNotIn("二、各品牌 TOP30", markdown)
        self.assertIn("标题匹配归属", html)
        self.assertIn("---\n\n### 各品牌 TOP30 对比分析", markdown)
        self.assertIn("---\n\n### 五个女博士", markdown)
        self.assertIn("---\n\n### 品牌间差异总结", markdown)
        self.assertIn('role="tablist"', html)
        self.assertIn('role="tab"', html)
        self.assertIn('role="tabpanel"', html)
        self.assertIn('aria-selected="true"', html)
        self.assertIn('data-brand-tab="五个女博士"', html)
        self.assertIn('data-brand-panel="万益蓝/WONDERLAB"', html)
        self.assertIn('data-brand-panel="五个女博士"', html)
        self.assertIn('data-brand-panel="燕之屋"', html)
        self.assertIn('id="brand-panel-0" aria-labelledby="brand-tab-0" hidden ', html)
        self.assertIn('id="brand-panel-1" aria-labelledby="brand-tab-1" ', html)
        self.assertIn('id="brand-panel-2" aria-labelledby="brand-tab-2" hidden ', html)
        self.assertIn('当前品牌：五个女博士', html)
        self.assertIn('.brand-panel[hidden]{display:none!important}', html)
        self.assertIn('<noscript><style>.brand-panel[hidden]{display:block!important}</style></noscript>', html)
        self.assertIn('class="section-divider"', html)
        self.assertIn("ArrowRight", html)
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

    def test_render_report_rejects_incomplete_top_material_contract(self):
        report = load_module()
        for mutation, error in (
            (
                lambda analysis: analysis["topMaterialCombination"]["overallConclusions"][0].update({"dimension": "unknown"}),
                "dimension",
            ),
            (
                lambda analysis: analysis["topMaterialCombination"].pop("brandComparisonConclusion"),
                "brandComparisonConclusion",
            ),
        ):
            with self.subTest(error=error):
                analysis = self.analysis_json()
                mutation(analysis)
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "analysis.json"
                    path.write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
                    with self.assertRaisesRegex(report.YuntuReportError, error):
                        report.render_report(analysis_json=path, output_dir=Path(directory) / "report")

    def test_render_report_rejects_audit_content_in_user_readable_summaries(self):
        report = load_module()
        for field, value in (
            ("summary", "查看数据依据"),
            ("dataSummary", "证据：{\"metric\": \"ctr\"}"),
            ("marketingSummary", "指标对象：{\"metric\": \"ctr\"}"),
        ):
            with self.subTest(field=field):
                analysis = self.analysis_json()
                target = (
                    analysis["topMaterialCombination"]["overallConclusions"][0]
                    if field == "summary"
                    else analysis["topMaterialCombination"]["brandConclusions"][0]
                )
                target[field] = value
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "analysis.json"
                    path.write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
                    with self.assertRaisesRegex(report.YuntuReportError, "audit"):
                        report.render_report(
                            analysis_json=path, output_dir=Path(directory) / "report"
                        )

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

    def test_render_report_rejects_brand_comparison_without_each_brand_evidence(self):
        report = load_module()
        analysis = self.analysis_json()
        analysis["topMaterialCombination"]["brandComparisonConclusion"]["evidence"].pop()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "analysis.json"
            path.write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(report.YuntuReportError, "brandComparisonConclusion.*brand"):
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

    def test_render_report_keeps_evidence_in_json_without_rendering_it(self):
        report = load_module()
        analysis = self.analysis_json()
        evidence_sections = {
            "rankingOverview": analysis["rankingOverview"],
            "materialComparison": analysis["materialComparison"],
            "materialDiagnoses": analysis["materialDiagnoses"],
            "competitorPatterns": analysis["competitorPatterns"],
            "xiaoxianDunOpportunityMap": analysis["xiaoxianDunOpportunityMap"],
        }
        for name, entries in evidence_sections.items():
            entries[0]["evidence"] = [{"hidden": f"evidence-sentinel-{name}"}]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis_path = root / "analysis.json"
            analysis_path.write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
            report.render_report(analysis_json=analysis_path, output_dir=root / "final-report")
            rendered = (root / "final-report" / "final-report.html").read_text(encoding="utf-8")
            markdown = (root / "final-report" / "final-report.md").read_text(encoding="utf-8")
            data = json.loads((root / "final-report" / "final-report-data.json").read_text(encoding="utf-8"))
        self.assertIn('class="insight-row"', rendered)
        self.assertNotIn('class="material-reference" href="#material-101"', rendered)
        self.assertNotIn('<details class="evidence-details">', rendered)
        self.assertNotIn("查看数据依据", rendered)
        for name in evidence_sections:
            self.assertNotIn(f"evidence-sentinel-{name}", rendered)
            self.assertNotIn(f"evidence-sentinel-{name}", markdown)
            self.assertEqual(
                data["analysis"][name][0]["evidence"],
                [{"hidden": f"evidence-sentinel-{name}"}],
            )
        self.assertEqual(
            data["analysis"]["topMaterialCombination"]["overallConclusions"][0]["evidence"],
            [{"hidden": "evidence-sentinel-data"}],
        )

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
