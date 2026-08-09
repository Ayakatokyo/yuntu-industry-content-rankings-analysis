import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


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
    def test_skill_documents_unified_report_delivery_contract(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("assets/report/", skill)
        self.assertIn("内联", skill)
        self.assertIn("不得手工修改", skill)
        self.assertIn("1440x1000", skill)
        self.assertNotIn("390x844", skill)

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
            for title in ("榜单竞争格局", "内容表现地图", "内容与人群机会", "竞品内容模式", "秒级创意结构", "机会与实验"):
                self.assertNotIn(title, rendered)
        self.assertNotIn("一、品牌筛选条件下", markdown)
        self.assertNotIn("二、各品牌 TOP30", markdown)
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
        self.assertIn('aria-label="五个女博士，标题匹配归属"', html)
        self.assertNotIn('当前品牌：', html)
        self.assertIn('.brand-panel[hidden]{display:none!important}', html)
        self.assertIn('<noscript><style>.brand-panel[hidden]{display:block!important}</style></noscript>', html)
        self.assertNotIn('class="section-divider"', html)
        self.assertIn("ArrowRight", html)
        self.assertNotIn("假设：通勤开场提升 3 秒播放率", markdown)
        self.assertNotIn("成功指标：play_3s_rate", markdown)
        self.assertNotIn("附：秒级趋势洞察", markdown)
        self.assertIn("<html", html)

    def test_render_report_inlines_unified_assets_and_emits_unified_structure(self):
        report = load_module()
        fact_pack = {
            "filters": {
                "industry": "食品饮料",
                "brands": ["万益蓝/WONDERLAB", "五个女博士", "燕之屋"],
                "custom_start_date": "2026-07-26",
                "custom_end_date": "2026-08-01",
            }
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis_path = root / "analysis.json"
            analysis_path.write_text(
                json.dumps(self.analysis_json(), ensure_ascii=False), encoding="utf-8"
            )
            report.render_report(
                analysis_json=analysis_path,
                output_dir=root / "final-report",
                fact_pack=fact_pack,
            )
            rendered = (root / "final-report" / "final-report.html").read_text(
                encoding="utf-8"
            )

        self.assertIn(
            '<body class="unified-report unified-yuntu" data-unified-report-version="2026-08-09">',
            rendered,
        )
        self.assertIn("云图 TOP 素材池商业诊断报告", rendered)
        self.assertNotIn("云图行业内容策略", rendered)
        self.assertNotIn("TOP30 素材组合结论", rendered)
        self.assertNotIn("来源：Top1000 榜单数据", rendered)
        self.assertNotIn("基于筛选品牌集合与标题匹配品牌", rendered)
        self.assertEqual(rendered.count(' yuntu-content-card"'), 3)
        self.assertIn(".unified-report .report-shell", rendered)
        self.assertIn("data-unified-report-ready", rendered)
        self.assertNotIn('rel="stylesheet"', rendered)
        self.assertNotIn('script src=', rendered)

    def test_render_report_rejects_missing_unified_asset(self):
        report = load_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis_path = root / "analysis.json"
            analysis_path.write_text(
                json.dumps(self.analysis_json(), ensure_ascii=False), encoding="utf-8"
            )
            with patch.object(
                report,
                "REPORT_STYLE_PATH",
                ROOT / "assets" / "report" / "missing.css",
            ):
                with self.assertRaisesRegex(report.YuntuReportError, "report style"):
                    report.render_report(
                        analysis_json=analysis_path,
                        output_dir=root / "final-report",
                    )
            self.assertFalse((root / "final-report" / "final-report-data.json").exists())
            self.assertFalse((root / "final-report" / "final-report.md").exists())
            self.assertFalse((root / "final-report" / "final-report.html").exists())
    def test_render_report_writes_audience_dashboard_from_fact_pack(self):
        report = load_module()
        audience_dashboard = {
            "sample": {
                "scope": "candidate_pool_top_1000",
                "requestedLimit": 1000,
                "recordCount": 3,
            },
            "dimensions": {
                "age": {
                    "labelMode": "normalized_tag_share",
                    "recordCount": 3,
                    "labeledRecordCount": 2,
                    "unlabeledRecordCount": 1,
                    "tagOccurrenceCount": 2,
                    "buckets": [
                        {"label": "24-30", "materialCount": 2, "materialShare": 2 / 3, "chartShare": 1},
                    ],
                },
                "gender": {
                    "labelMode": "normalized_tag_share",
                    "recordCount": 3,
                    "labeledRecordCount": 3,
                    "unlabeledRecordCount": 0,
                    "tagOccurrenceCount": 3,
                    "buckets": [
                        {"label": "女", "materialCount": 3, "materialShare": 1, "chartShare": 1},
                    ],
                },
                "crowd": {
                    "labelMode": "normalized_tag_share",
                    "recordCount": 3,
                    "labeledRecordCount": 2,
                    "unlabeledRecordCount": 1,
                    "tagOccurrenceCount": 3,
                    "buckets": [
                        {"label": "新锐白领", "materialCount": 2, "materialShare": 2 / 3, "chartShare": 2 / 3},
                        {"label": "精致妈妈", "materialCount": 1, "materialShare": 1 / 3, "chartShare": 1 / 3},
                    ],
                },
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis_path = root / "analysis.json"
            analysis_path.write_text(json.dumps(self.analysis_json(), ensure_ascii=False), encoding="utf-8")
            report.render_report(
                analysis_json=analysis_path,
                output_dir=root / "final-report",
                fact_pack={"audienceDashboard": audience_dashboard},
            )
            markdown = (root / "final-report" / "final-report.md").read_text(encoding="utf-8")
            html = (root / "final-report" / "final-report.html").read_text(encoding="utf-8")

        for rendered in (markdown, html):
            self.assertIn("02｜人群洞察", rendered)
            self.assertIn("年龄", rendered)
            self.assertIn("性别", rendered)
            self.assertIn("八大人群", rendered)
        self.assertIn("候选池 TOP1000", markdown)
        self.assertIn("实际 3 条", markdown)
        self.assertNotIn("候选池 TOP1000", html)
        self.assertNotIn("图表按素材标签出现次数归一化展示", html)
        self.assertNotIn("用于观察标签结构，不代表真实人群分布", html)
        self.assertIn('href="#audience-insights"', html)
        self.assertIn("conic-gradient(", html)
        self.assertEqual(html.count(' data-audience-pie '), 2)
        self.assertEqual(html.count(' data-audience-column '), 1)
        self.assertIn('class="chart-card audience-chart audience-chart-age"', html)
        self.assertIn('class="chart-card audience-chart audience-chart-gender"', html)
        self.assertIn('class="chart-card audience-chart audience-chart-crowd"', html)
        self.assertIn('class="audience-column-chart"', html)
        self.assertIn('class="audience-column-label">新锐白领</span>', html)
        self.assertIn('class="legend-label"><i class="legend-swatch"', html)
        self.assertIn('class="legend-count">2 条</span>', html)
        self.assertIn('class="legend-share">100.0%</span>', html)
        self.assertIn('class="chart-tooltip"', html)
        self.assertIn('.page{width:min(1180px,calc(100% - 32px));', html)
        self.assertIn('.audience-pie-layout{display:grid;grid-template-columns:minmax(0,45fr) minmax(0,55fr);', html)
        self.assertIn('.audience-chart-age,.audience-chart-gender{display:flex;flex-direction:column}', html)
        self.assertIn('flex:1;min-height:0;gap:14px;align-items:center', html)
        self.assertIn('@container (max-width:360px){.audience-pie-layout{grid-template-columns:1fr}', html)
        self.assertIn('.pie-chart{position:relative;width:min(260px,100%);', html)
        self.assertIn('.audience-chart-gender .pie-chart{width:min(240px,100%)}', html)
        self.assertIn('.pie-legend .legend-item{position:relative;display:grid;grid-template-columns:minmax(80px,1fr) auto auto;', html)
        self.assertIn('.audience-column-chart{position:relative;min-height:300px;', html)
        self.assertIn('.unified-report :is(.pie-layout, .audience-pie-layout)', html)
        self.assertIn('flex-direction: column;', html)
        self.assertIn('width: min(320px, 100%) !important;', html)
        self.assertIn('.unified-report .pie-legend {', html)
        self.assertIn('overflow-x: auto;', html)
        self.assertNotIn('class="pie-tooltip"', html)
        self.assertNotIn('class="audience-bar-chart"', html)

    def test_render_report_keeps_unlabeled_dimension_out_of_pie_chart(self):
        report = load_module()
        audience_dashboard = {
            "sample": {"recordCount": 2},
            "dimensions": {
                "age": {
                    "labelMode": "normalized_tag_share",
                    "recordCount": 2,
                    "labeledRecordCount": 0,
                    "unlabeledRecordCount": 2,
                    "tagOccurrenceCount": 0,
                    "buckets": [],
                },
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis_path = root / "analysis.json"
            analysis_path.write_text(json.dumps(self.analysis_json(), ensure_ascii=False), encoding="utf-8")
            report.render_report(
                analysis_json=analysis_path,
                output_dir=root / "final-report",
                fact_pack={"audienceDashboard": audience_dashboard},
            )
            html = (root / "final-report" / "final-report.html").read_text(encoding="utf-8")

        self.assertIn("暂无可视化数据。", html)
        self.assertIn("未识别到该维度标签：2 条素材。", html)
        self.assertEqual(html.count(' data-audience-pie '), 0)

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

    def test_render_report_renders_only_top_material_combination(self):
        report = load_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis_path = root / "analysis.json"
            analysis_path.write_text(json.dumps(self.analysis_json(), ensure_ascii=False), encoding="utf-8")
            report.render_report(analysis_json=analysis_path, output_dir=root / "report")
            markdown = (root / "report" / "final-report.md").read_text(encoding="utf-8")
            rendered = (root / "report" / "final-report.html").read_text(encoding="utf-8")
        self.assertEqual(rendered.count('class="section"'), 1)
        self.assertIn('class="report-nav"', rendered)
        self.assertIn('href="#top-material-combination"', rendered)
        self.assertNotIn('href="#landscape"', rendered)
        self.assertIn('</article></section>', rendered)
        self.assertNotIn('</article></div></section>', rendered)
        self.assertNotIn("榜单竞争格局", markdown)

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

    def test_render_report_renders_styled_cover_without_legacy_gallery(self):
        report = load_module()
        fact_pack = {"materialFacts": [{"material_id": "101", "highlightFrames": [{"second": 0, "available": True, "relative_path": "../highlights/101/01-000s.jpg", "is_cover": True, "reasons": [{"type": "cover"}]}]}]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis_path = root / "analysis.json"
            analysis_path.write_text(json.dumps(self.analysis_json(), ensure_ascii=False), encoding="utf-8")
            report.render_report(analysis_json=analysis_path, output_dir=root / "final-report", fact_pack=fact_pack)
            rendered = (root / "final-report" / "final-report.html").read_text(encoding="utf-8")
        self.assertIn('class="report-cover"', rendered)
        self.assertNotIn('class="highlight-gallery"', rendered)
        self.assertNotIn('src="../highlights/101/01-000s.jpg"', rendered)

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
        self.assertNotIn('class="insight-row"', rendered)
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

    def test_render_report_uses_accessible_brand_tabs_without_legacy_dialog(self):
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
        self.assertIn('aria-label="各品牌 TOP30 分析"', rendered)
        self.assertNotIn('aria-label="查看 101 封面 高光帧"', rendered)
        self.assertNotIn('aria-label="关闭高光帧预览"', rendered)

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

    def test_render_report_excludes_legacy_second_level_sections(self):
        report = load_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis_path = root / "analysis.json"
            analysis_path.write_text(json.dumps(self.analysis_json(), ensure_ascii=False), encoding="utf-8")
            report.render_report(analysis_json=analysis_path, output_dir=root / "final-report")
            rendered = (root / "final-report" / "final-report.html").read_text(encoding="utf-8")
        self.assertNotIn('id="competitor"', rendered)
        self.assertNotIn('id="second-by-second"', rendered)

    def test_render_report_excludes_legacy_highlight_images(self):
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
        self.assertNotIn(".highlight-gallery{display:grid", rendered)
        self.assertNotIn(".frame-button img{display:block;width:100%", rendered)
        self.assertNotIn("minmax(88px,1fr)", rendered)

    def test_render_report_excludes_legacy_charts_and_source_labels(self):
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
        self.assertNotIn('id="material-tag-chart"', rendered)
        self.assertNotIn('id="people-tag-chart"', rendered)
        self.assertNotIn('class="pie-layout"', rendered)
        self.assertNotIn('class="pie-legend"', rendered)
        self.assertNotIn('data-pie-slices=', rendered)
        self.assertNotIn('class="pie-tooltip"', rendered)
        self.assertNotIn('class="performance-insights"', rendered)
        self.assertNotIn("CTR 位于候选池高位。", rendered)
        self.assertNotIn('id="frame-material"', rendered)
        self.assertNotIn("来源：Top1000 榜单数据", rendered)
        self.assertNotIn("来源：单素材秒级详情", rendered)
        self.assertNotIn("来源：榜单 + 秒级详情派生", rendered)
        self.assertNotIn("高光帧汇总", rendered)
        self.assertNotIn('<dialog id="lightbox">', rendered)


if __name__ == "__main__":
    unittest.main()
