import importlib.util
import copy
import json
import re
import sys
import tempfile
import unittest
import zipfile
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
    LEGACY_UNUSED_ANALYSIS_FIELDS = (
        "rankingOverview",
        "audienceInsights",
        "materialComparison",
        "materialDiagnoses",
        "competitorPatterns",
        "opportunityMap",
        "experimentMatrix",
    )

    def test_render_report_creates_sibling_zip_with_final_report_directory(self):
        report = load_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis_path = root / "analysis.json"
            analysis_path.write_text(
                json.dumps(self.analysis_json(), ensure_ascii=False), encoding="utf-8"
            )
            output_dir = root / "final-report"

            status = report.render_report(
                analysis_json=analysis_path, output_dir=output_dir
            )

            archive_path = root / "final-report.zip"
            self.assertEqual(status, 0)
            self.assertTrue(archive_path.is_file())
            with zipfile.ZipFile(archive_path) as archive:
                names = set(archive.namelist())
            expected = {
                f"final-report/{path.relative_to(output_dir).as_posix()}"
                for path in output_dir.rglob("*")
                if path.is_file()
            }

        self.assertEqual(names, expected)

    def test_unused_markdown_value_helper_is_removed(self):
        report = load_module()
        self.assertFalse(hasattr(report, "_markdown_value"))

    def test_render_report_writes_valid_presentation_projection(self):
        report = load_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis_path = root / "analysis.json"
            analysis_path.write_text(json.dumps(self.analysis_json(), ensure_ascii=False), encoding="utf-8")

            status = report.render_report(analysis_json=analysis_path, output_dir=root / "final-report")

            presentation = json.loads(
                (root / "final-report" / "presentation-report.json").read_text(encoding="utf-8")
            )
            report_data = json.loads(
                (root / "final-report" / "final-report-data.json").read_text(encoding="utf-8")
            )

        self.assertEqual(status, 0)
        self.assertEqual(presentation["presentationSchemaVersion"], 3)
        self.assertEqual(report_data["presentation"], presentation)
        self.assertNotIn("categories", presentation["chapters"]["chapter04"])
        self.assertNotIn("materials", presentation)

    def test_load_analysis_adapts_legacy_chapter02_scope_insights(self):
        report = load_module()
        analysis = self.analysis_json()
        analysis["chapter02Insights"] = {
            "scopeOrder": ["all"],
            "scopes": {
                "all": {
                    "audienceAnalysis": {
                        "insights": [{
                            "conclusion": "旧版人群结论仍应作为新版报告的事实锚点和验证方向。",
                            "material_ids": ["101"],
                            "evidence": [{"material_id": "101", "metric": "people_tags"}],
                        }],
                    },
                    "marketingAnalysis": {
                        "insights": [{
                            "conclusion": "旧版营销卖点结论仍应作为新版报告的事实锚点和验证方向。",
                            "material_ids": ["101"],
                            "evidence": [{"material_id": "101", "metric": "material_tags"}],
                        }],
                    },
                },
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "analysis.json"
            path.write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
            loaded = report._load_analysis(path)

        scope = loaded["chapter02Insights"]["scopes"]["all"]
        self.assertEqual(scope["audienceInsights"][0]["summary"], "旧版人群结论仍应作为新版报告的事实锚点和验证方向。")
        self.assertEqual(scope["marketingInsights"][0]["summary"], "旧版营销卖点结论仍应作为新版报告的事实锚点和验证方向。")
        self.assertEqual(scope["audienceSummary"]["title"], "人群洞察")
        self.assertEqual(scope["audienceSummary"]["summary"], "")
        self.assertEqual(scope["audienceSummary"]["material_ids"], ["101"])
        self.assertEqual(scope["marketingSummary"]["title"], "营销卖点洞察")

    def test_progressive_section_renderers_are_explicitly_orchestrated(self):
        source = MODULE_PATH.read_text(encoding="utf-8")

        component = (ROOT / "scripts" / "yuntu_report_sections.py").read_text(encoding="utf-8")
        self.assertIn("def render_top_material_combination(", component)
        self.assertIn("def render_audience_insights(", component)
        self.assertIn("def render_highlight_insights(", component)
        self.assertIn("def render_material_deep_dive(", component)
        render_html = source.split("def _render_html", 1)[1].split("def render_report", 1)[0]
        self.assertIn("render_top_material_combination(", render_html)
        self.assertIn("render_audience_insights(", render_html)
        self.assertIn("render_script_insights(", render_html)
        self.assertIn("render_highlight_insights(", render_html)
        self.assertIn("render_material_deep_dive(", render_html)

    def test_script_insights_renderer_has_a_component_owner(self):
        source = MODULE_PATH.read_text(encoding="utf-8")
        component_path = ROOT / "scripts" / "yuntu_report_sections.py"

        self.assertTrue(component_path.exists())
        self.assertIn("from yuntu_report_sections import", source)
        self.assertNotIn("def render_script_insights():", source)
        component = component_path.read_text(encoding="utf-8")
        self.assertIn("def render_script_insights():", component)

    def test_all_progressive_section_entrypoints_have_component_owner(self):
        component = (ROOT / "scripts" / "yuntu_report_sections.py").read_text(encoding="utf-8")
        for name in (
            "render_top_material_combination",
            "render_audience_insights",
            "render_script_insights",
            "render_highlight_insights",
            "render_material_deep_dive",
        ):
            self.assertIn(f"def {name}(", component)

    def test_top_material_renderer_owns_its_markup(self):
        source = MODULE_PATH.read_text(encoding="utf-8")
        component = (ROOT / "scripts" / "yuntu_report_sections.py").read_text(encoding="utf-8")

        self.assertNotIn('class="top-material-executive yuntu-content-card"', component)
        self.assertIn('class="brand-tabs"', component)
        self.assertIn("brand-summary-data", component)
        self.assertNotIn('def top_material_combination_cards(value):', source)

    def test_audience_renderer_owns_its_markup(self):
        source = MODULE_PATH.read_text(encoding="utf-8")
        component = (ROOT / "scripts" / "yuntu_report_sections.py").read_text(encoding="utf-8")

        self.assertIn('class="audience-dashboard"', component)
        self.assertIn('data-audience-records=', component)
        self.assertNotIn('def audience_dashboard_cards(value):', source)
        self.assertNotIn('def audience_dimension_chart(key, dimension):', source)
        self.assertNotIn('def _legacy_audience_dashboard_cards(value):', source)
        self.assertNotIn('def _legacy_audience_dimension_chart(key, dimension):', source)

    def test_visual_sections_have_explicit_component_entrypoints(self):
        component = (ROOT / "scripts" / "yuntu_report_sections.py").read_text(encoding="utf-8")
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn("def render_highlight_insights(", component)
        self.assertIn("def render_material_deep_dive(", component)
        self.assertIn("highlight_insights = render_highlight_insights(", source)
        self.assertIn("material_deep_dive = render_material_deep_dive(", source)

    def test_visual_section_components_own_their_markup(self):
        source = MODULE_PATH.read_text(encoding="utf-8")
        component = (ROOT / "scripts" / "yuntu_report_sections.py").read_text(encoding="utf-8")
        self.assertIn('class="highlight-frame-card"', component)
        self.assertIn('class="material-deep-panel material-card"', component)
        self.assertNotIn("def highlight_insights_cards():", source)
        self.assertNotIn("def material_deep_dive_cards():", source)

    def test_skill_documents_offline_report_delivery_boundary(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("assets/report/", skill)
        self.assertIn("内联", skill)
        self.assertIn("不得手工修改", skill)
        self.assertIn("render-report", skill)
        self.assertIn("脚本和生成的提示词是 schema 权威", skill)
        self.assertNotIn("rankingFacts", skill)
        self.assertNotIn("visualAssets", skill)

    def analysis_json(self):
        return {
            "topMaterialCombination": {
                "executiveSummary": {
                    "summary": "综合结论：榜单、人群、卖点和已取得详情共同指向明确的内容机会。",
                    "material_ids": ["101"],
                    "evidence": [
                        {"scope": "ranking"},
                        {"scope": "detail"},
                    ],
                },
                "overallConclusions": [
                    {
                        "dimension": "data",
                        "summary": "TOP1000 总曝光占比高，头部流量集中但并非单条素材垄断。",
                        "material_ids": ["101"],
                        "evidence": [{"hidden": "evidence-sentinel-data"}],
                    },
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
            "audienceInsights": [{
                "summary": "新锐白领标签在已返回素材中更常出现，可作为后续素材分层观察线索。",
                "material_ids": ["101"],
                "evidence": [{"tag": "新锐白领"}],
            }],
            "materialComparison": [{"material_id": "101", "summary": "CTR 位于候选池高位。", "evidence": [{"metric": "ctr", "value": 0.7}]}],
            "materialDiagnoses": [{"material_id": "101", "summary": "第 1-2 秒出现点击高点。", "evidence": [{"trend_name": "点击指数", "start_sec": 1, "end_sec": 2}]}],
            "competitorPatterns": [{"summary": "价格利益点前置。", "material_ids": ["101"], "evidence": [{"tag": "限时抢购"}]}],
            "opportunityMap": [{"summary": "测试通勤场景。", "material_ids": ["101"], "evidence": [{"tag": "商品展示(有语音)"}]}],
            "experimentMatrix": [{"priority": "P1", "hypothesis": "测试通勤开场的 3 秒播放率表现", "creative_variable": "前 3 秒场景钩子", "target_audience": "新锐白领", "success_metric": "play_3s_rate", "control": "现有商品直展示素材", "review_action": "按人群拆分复盘", "evidence": [{"material_id": "101", "metric": "play_3s_rate"}]}],
        }

    def test_render_report_accepts_slim_analysis_without_unused_fields(self):
        report = load_module()
        analysis = self.analysis_json()
        for field in self.LEGACY_UNUSED_ANALYSIS_FIELDS:
            analysis.pop(field)
        analysis["topMaterialCombination"].pop("overallConclusions")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis_path = root / "analysis.json"
            analysis_path.write_text(
                json.dumps(analysis, ensure_ascii=False), encoding="utf-8"
            )

            status = report.render_report(
                analysis_json=analysis_path, output_dir=root / "final-report"
            )
            rendered = (root / "final-report" / "final-report.html").read_text(
                encoding="utf-8"
            )

        self.assertEqual(status, 0)
        self.assertEqual(rendered.count('class="section"'), 5)
        for section_id in (
            "top-material-combination",
            "audience-insights",
            "script-insights",
            "highlight-insights",
            "material-deep-dive",
        ):
            self.assertIn(f'id="{section_id}"', rendered)

    def test_render_report_ignores_unused_fields_in_legacy_analysis(self):
        report = load_module()
        analysis = self.analysis_json()
        for field in self.LEGACY_UNUSED_ANALYSIS_FIELDS:
            analysis[field] = None
        analysis["topMaterialCombination"]["overallConclusions"] = None

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis_path = root / "analysis.json"
            analysis_path.write_text(
                json.dumps(analysis, ensure_ascii=False), encoding="utf-8"
            )

            status = report.render_report(
                analysis_json=analysis_path, output_dir=root / "final-report"
            )

        self.assertEqual(status, 0)

    def highlight_dashboard(self):
        return {
            "highlightDashboard": {
                "availability": {"available": True, "reason": ""},
                "groups": [
                    {
                        "category": "portrait",
                        "frame_refs": ["highlight:101:cover:0"],
                        "common_patterns": ["人物近景占据主体，视线和产品形成清晰焦点。"],
                        "derivative_directions": [
                            {
                                "title": "保留近景人物开场",
                                "body": "以人物近景和明确主体作为可复用的开场画面方向。",
                                "frame_refs": ["highlight:101:cover:0"],
                            }
                        ],
                    }
                ],
            }
        }

    def deep_dive_fact_pack(self):
        def metric(name, value):
            return {
                "trend_name": name,
                "available": True,
                "missing_reason": "",
                "points": [{"second": 0, "value": value}, {"second": 2, "value": value + 1}],
                "high_points": [{"start_sec": 2, "end_sec": 2}],
                "loss_points": [],
            }

        facts = []
        for rank, material_id in enumerate(("101", "102"), start=1):
            facts.append({
                "material_id": material_id,
                "rank": rank,
                "title": f"测试素材 {material_id}",
                "exposure": {"min": 200000, "max": 220000, "raw": "20万-22万"},
                "metrics": {"show_cnt": 2686377, "ctr": 0.0327, "cvr": 0.0709, "play_3s_rate": 0.7441, "interact_rate": 0.0002},
                "people_tags": ["新锐白领", "都市女性"],
                "material_tags": ["睡前场景", "胶原蛋白肽"],
                "listDataAvailability": {
                    "people_tags": {"available": True, "missing_reason": ""},
                    "material_tags": {"available": True, "missing_reason": ""},
                },
                "detailDataAvailability": {
                    "script_text": {"available": False, "missing_reason": "source_empty"},
                },
                "highlightFrames": [
                    {"frame_ref": f"highlight:{material_id}:cover:0", "second": 0, "frame_type": "cover", "available": True, "relative_path": f"highlights/{material_id}/01-000s.jpg"},
                    {"frame_ref": f"highlight:{material_id}:click_peak:2", "second": 2, "frame_type": "click_peak", "peak_rank": 1, "click_value": 0.8, "available": True, "relative_path": f"highlights/{material_id}/02-002s.jpg"},
                ],
                "secondLevelBreakdown": {"metrics": [metric(name, index) for index, name in enumerate(("点赞指数", "流失指数", "点击指数", "互动指数", "评论指数"))]},
            })
        return {"schemaVersion": 4, "selectedMaterials": [{"rank": 1, "material_id": "101"}, {"rank": 2, "material_id": "102"}], "materialFacts": facts}

    def deep_dive_analysis(self):
        analysis = self.analysis_json()
        analysis["highlightDashboard"] = {
            "groups": [{
                "category": "portrait",
                "frame_refs": ["highlight:101:cover:0", "highlight:101:click_peak:2", "highlight:102:cover:0", "highlight:102:click_peak:2"],
                "common_patterns": ["画面主体明确。"],
                "derivative_directions": [],
            }]
        }
        analysis["materialDeepDives"] = [
            {
                "material_id": material_id,
                "frame_observations": [
                    {"frame_ref": f"highlight:{material_id}:cover:0", "observation": "人物近景作为开场主体，产品包装在前景可辨识，先建立生活化使用场景。"},
                    {"frame_ref": f"highlight:{material_id}:click_peak:2", "observation": "产品与人物共同处于画面中心，镜头保持近景构图，使用动作和包装信息同步可见。"},
                ],
                "visual_summary": "画面以人物近景和可辨识的产品包装构成双主体，生活化空间降低了产品理解门槛，适合观察场景与包装的并置方式。",
                "data_summary": "榜单指标与候选池基准共同提供表现参照，后续应结合曝光、点击和短时播放指标判断该画面组合是否值得保留。",
                "audience_summary": "新锐白领与都市女性标签在已返回素材中出现，可优先测试日常状态管理的信息入口，并按实际定向结果验证差异。",
                "marketing_summary": "产品展示标签与可见包装共同出现，画面先让用户识别产品主体，再承接场景信息，适合继续测试信息层级的取舍。",
                "replication_advice": "可测试近景产品主体、清晰包装展示与单一日常场景的组合，并分别比较人物先出场和产品先出场两种开场版本。",
                "risk_notes": "画面判断基于已提取帧，不把峰值同时性作为效果证明；健康相关表达和特定人群指向仍需业务与合规复核。",
                "opening_judgment": "前 3 秒以稳定人物主体承接注意力，同时保留产品露出；下一轮可测试更早出现包装是否改善产品识别。",
                "visual_rhythm": "已提取帧从人物近景过渡到产品同框，景别变化不大但信息焦点稳定，适合以单变量测试强化前段节奏。",
                "peak_frame_reading": "点击峰值秒点中人物与产品同框，说明该画面组合值得保留为候选版本，但需要与其他开场变量分组验证。",
                "second_level_reading": "五类指数只使用已返回秒级点位描述，点击高点与前段画面同时出现，可作为后续分镜测试的观察锚点。",
                "audience_fit": "人群标签与日常场景主题存在可测试的匹配线索，不能视为真实分布；应在投放定向与素材版本交叉下验证。",
                "replication_advice": "可测试产品主体和日常场景的组合，以清晰包装和单一利益点降低理解成本，并以短时播放与点击共同复盘。",
                "do_not_copy": "不直接照搬竞品的健康功效、特定人群承诺或未验证状态暗示；仅借鉴人物、产品与日常场景的视觉组织方式。",
                "second_level_observations": [{"trend_name": "点击指数", "summary": "第 2 秒为已返回的点击高点秒数，前段产品与人物同框可作为下一轮开场变量的对照锚点。", "evidence_seconds": [2]}],
            }
            for material_id in ("101", "102")
        ]
        return analysis

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
            self.assertNotIn("综合结论", rendered)
            self.assertNotIn("TOP1000 整体分析", rendered)
            self.assertNotIn("从数据维度看", rendered)
            self.assertNotIn("从营销卖点维度看", rendered)
            self.assertNotIn("人群标签是重叠标签，不是真实人群分布，不能相加为 100%。", rendered)
            self.assertIn("各品牌榜单分析", rendered)
            self.assertIn("万益蓝/WONDERLAB", rendered)
            self.assertIn("五个女博士", rendered)
            self.assertIn("燕之屋", rendered)
            self.assertNotIn("品牌间差异总结", rendered)
            self.assertNotIn("真实品牌差异结论", rendered)
            self.assertNotIn("素材列表数据分析", rendered)
            self.assertNotIn("人群维度", rendered)
            self.assertNotIn("旧版兼容字段", rendered)
            self.assertNotIn("查看数据依据", rendered)
            self.assertNotIn('<details class="evidence-details">', rendered)
            self.assertNotIn("证据：", rendered)
            self.assertNotIn("evidence-sentinel", rendered)
            self.assertNotIn("女性与新锐白领标签", rendered)
            self.assertNotIn("营销卖点以肠道健康表达为主", rendered)
            for title in ("榜单竞争格局", "内容表现地图", "内容与人群机会", "竞品内容模式", "秒级创意结构", "机会与实验"):
                self.assertNotIn(title, rendered)
        self.assertNotIn("一、品牌筛选条件下", markdown)
        self.assertNotIn("二、各品牌 TOP", markdown)
        self.assertIn("---\n\n### 各品牌榜单分析", markdown)
        self.assertIn("---\n\n### 五个女博士", markdown)
        self.assertNotIn("品牌间差异总结", markdown)
        self.assertIn('role="tablist"', html)
        self.assertIn('role="tab"', html)
        self.assertIn('role="tabpanel"', html)
        self.assertIn('aria-selected="true"', html)
        self.assertIn('data-brand-tab="五个女博士"', html)
        self.assertIn('data-brand-panel="万益蓝/WONDERLAB"', html)
        self.assertIn('data-brand-panel="五个女博士"', html)
        self.assertIn('data-brand-panel="燕之屋"', html)
        # With the current renderer the first available brand is selected by
        # default (the fixture has no aggregate ``全品牌`` conclusion), so
        # panel 0 is visible and the remaining panels are hidden.
        self.assertIn('id="brand-panel-0" aria-labelledby="brand-tab-0" ', html)
        self.assertIn('id="brand-panel-1" aria-labelledby="brand-tab-1" hidden ', html)
        self.assertIn('id="brand-panel-2" aria-labelledby="brand-tab-2" hidden ', html)
        self.assertIn('aria-label="万益蓝/WONDERLAB，标题匹配归属"', html)
        self.assertNotIn('当前品牌：', html)
        self.assertIn('.brand-panel[hidden]{display:none!important}', html)
        self.assertIn('<noscript><style>.brand-panel[hidden]{display:block!important}</style></noscript>', html)
        self.assertNotIn('class="section-divider"', html)
        self.assertIn("ArrowRight", html)
        self.assertNotIn("假设：通勤开场提升 3 秒播放率", markdown)
        self.assertNotIn("成功指标：play_3s_rate", markdown)
        self.assertNotIn("附：秒级趋势洞察", markdown)
        self.assertIn("<html", html)

    def test_report_template_requires_each_current_section_placeholder(self):
        report = load_module()
        original = (ROOT / "scripts" / "templates" / "final-report-template.html").read_text(
            encoding="utf-8"
        )
        with tempfile.TemporaryDirectory() as directory:
            template_path = Path(directory) / "template.html"
            template_path.write_text(
                original.replace("$script_insights", ""), encoding="utf-8"
            )
            with patch.object(report, "HTML_TEMPLATE_PATH", template_path):
                with self.assertRaisesRegex(report.YuntuReportError, "script_insights"):
                    report._load_html_template()

    def test_render_report_accepts_top_material_combination_without_executive_summary(self):
        report = load_module()
        analysis = self.analysis_json()
        analysis["topMaterialCombination"].pop("executiveSummary")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis_path = root / "analysis.json"
            analysis_path.write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
            report.render_report(analysis_json=analysis_path, output_dir=root / "final-report")
            rendered = (root / "final-report" / "final-report.html").read_text(encoding="utf-8")

        self.assertNotIn("综合结论", rendered)

    def test_render_report_keeps_schema_v4_brand_data_compatible_without_people_summary(self):
        report = load_module()
        analysis = self.analysis_json()
        for item in analysis["topMaterialCombination"]["brandConclusions"]:
            item.pop("peopleSummary")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis_path = root / "analysis.json"
            analysis_path.write_text(
                json.dumps(analysis, ensure_ascii=False), encoding="utf-8"
            )
            report.render_report(
                analysis_json=analysis_path,
                output_dir=root / "final-report",
                fact_pack={"schemaVersion": 4},
            )
            rendered = (root / "final-report" / "final-report.html").read_text(
                encoding="utf-8"
            )

        self.assertIn("各品牌榜单分析", rendered)
        self.assertNotIn("素材列表数据分析", rendered)
        self.assertNotIn("人群维度", rendered)

    def test_render_report_rejects_brand_conclusion_without_people_summary(self):
        report = load_module()
        analysis = self.analysis_json()
        analysis["topMaterialCombination"]["brandConclusions"][0].pop(
            "peopleSummary"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis_path = root / "analysis.json"
            analysis_path.write_text(
                json.dumps(analysis, ensure_ascii=False), encoding="utf-8"
            )
            report.render_report(
                analysis_json=analysis_path,
                output_dir=root / "final-report",
            )

    def test_new_chapter01_contract_requires_four_metrics_and_real_audience_label(self):
        report = load_module()
        analysis = {
            "topMaterialCombination": {
                "brandConclusions": [
                    {
                        "brand": "小仙炖",
                        "dataSummary": "Top 30 累计曝光 100 万，CTR 2%、CVR 3%、3 秒播放率 40%。",
                        "peopleSummary": "新锐白领标签覆盖较高。",
                        "material_ids": ["101"],
                    }
                ]
            }
        }
        fact_pack = {
            "schemaVersion": 5,
            "industryTop1000Facts": {"source_scope": "industry_top1000"},
            "filters": {"brands": ["小仙炖"]},
            "brandTopNFacts": {
                "brands": {
                    "小仙炖": {
                        "source_scope": "brand_top_n",
                        "sample_count": 1,
                        "materials": [{"material_id": "101"}],
                        "audienceFacts": {
                            "coverageIsOverlapping": True,
                            "age": [],
                            "gender": [],
                            "crowd": [{"label": "新锐白领"}],
                        },
                    }
                }
            },
        }

        report._validate_ranking_scope_contract(analysis, fact_pack)

        analysis["topMaterialCombination"]["brandConclusions"][0][
            "dataSummary"
        ] = "Top 30 累计曝光 100 万。"
        with self.assertRaisesRegex(report.YuntuReportError, "3-second play rate"):
            report._validate_ranking_scope_contract(analysis, fact_pack)

        analysis["topMaterialCombination"]["brandConclusions"][0][
            "dataSummary"
        ] = "Top 30 累计曝光 100 万，CTR 2%、CVR 3%、3 秒播放率 40%。"
        analysis["topMaterialCombination"]["brandConclusions"][0].pop("peopleSummary")
        report._validate_ranking_scope_contract(analysis, fact_pack)

    def test_schema_v6_rejects_material_id_in_chapter01_visible_summaries(self):
        report = load_module()
        material_id = "7668663443726172214"
        analysis = {
            "topMaterialCombination": {
                "brandConclusions": [
                    {
                        "brand": "小仙炖",
                        "classificationSource": "runtime_title_rule",
                        "dataSummary": (
                            "Top 30 累计曝光 100 万，CTR 2%、CVR 3%、"
                            f"3 秒播放率 40%，素材{material_id}表现突出。"
                        ),
                        "peopleSummary": "新锐白领标签覆盖较高。",
                        "evidence": ["Top 30 聚合指标与人群覆盖事实。"],
                        "material_ids": [material_id],
                    }
                ]
            }
        }
        fact_pack = {
            "schemaVersion": 6,
            "industryTop1000Facts": {"source_scope": "industry_top1000"},
            "filters": {"brands": ["小仙炖"]},
            "brandTopNFacts": {
                "brands": {
                    "小仙炖": {
                        "source_scope": "brand_top_n",
                        "sample_count": 1,
                        "materials": [{"material_id": material_id}],
                        "audienceFacts": {
                            "coverageIsOverlapping": True,
                            "age": [],
                            "gender": [],
                            "crowd": [{"label": "新锐白领"}],
                        },
                    }
                }
            },
        }

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "analysis.json"
            path.write_text(
                json.dumps(analysis, ensure_ascii=False), encoding="utf-8"
            )
            with self.assertRaisesRegex(
                report.YuntuReportError, "must not include material IDs"
            ):
                report.validate_analysis_input(
                    analysis_json=path, fact_pack=fact_pack
                )

        analysis["topMaterialCombination"]["brandConclusions"][0][
            "dataSummary"
        ] = "Top 30 累计曝光 100 万，CTR 2%、CVR 3%、3 秒播放率 40%。"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "analysis.json"
            path.write_text(
                json.dumps(analysis, ensure_ascii=False), encoding="utf-8"
            )
            validated = report.validate_analysis_input(
                analysis_json=path, fact_pack=fact_pack
            )

        self.assertEqual(
            validated["topMaterialCombination"]["brandConclusions"][0][
                "material_ids"
            ],
            [material_id],
        )

    def test_schema_v7_accepts_unified_summary_and_legacy_evidence_when_present(self):
        report = load_module()
        analysis = {
            "topMaterialCombination": {
                "brandConclusions": [{
                    "brand": "小仙炖",
                    "classificationSource": "runtime_title_rule",
                    "dataSummary": "小仙炖本周期覆盖 1 条素材，累计曝光 20 万，CTR 2%、CVR 3%、3 秒播放率 40%。",
                    "evidence": ["品牌榜单聚合事实"],
                    "material_ids": ["101"],
                    "comparisonSummary": "本周期相较上一周期样本增加，表现与行业大盘接近。",
                    "hotMaterialInsight": {
                        "title": "爆款素材表现分析",
                        "summary": "爆款素材达到曝光门槛，建议继续验证其指标组合。",
                        "evidence": {"scope": "brand", "material_ids": ["101"]},
                    },
                }]
            }
        }
        fact_pack = {
            "schemaVersion": 7,
            "filters": {"brands": ["小仙炖"]},
            "industryTop1000Facts": {"source_scope": "industry_top1000"},
            "brandRankingFacts": {"brands": {"小仙炖": {"source_scope": "brand_in_top1000", "sample_count": 1, "materials": [{"material_id": "101"}]}}},
            "comparisonFacts": {"previousPeriod": {}, "industryBenchmark": {}},
            "hotMaterialFacts": {"小仙炖": {"thresholdExposureMin": 200000, "qualifyingCount": 1, "materials": [{"material_id": "101", "exposure": {"min": 200000, "max": 220000, "raw": "20万-22万"}}], "available": True, "missing_reason": ""}},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "analysis.json"
            path.write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
            report.validate_analysis_input(analysis_json=path, fact_pack=fact_pack)
            unified_analysis = copy.deepcopy(analysis)
            unified_item = unified_analysis["topMaterialCombination"]["brandConclusions"][0]
            unified_item.pop("comparisonSummary")
            unified_item.pop("hotMaterialInsight")
            path.write_text(json.dumps(unified_analysis, ensure_ascii=False), encoding="utf-8")
            report.validate_analysis_input(analysis_json=path, fact_pack=fact_pack)
            analysis["topMaterialCombination"]["brandConclusions"][0]["hotMaterialInsight"]["evidence"]["scope"] = "all"
            path.write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(report.YuntuReportError, "scope"):
                report.validate_analysis_input(analysis_json=path, fact_pack=fact_pack)

            invalid_cases = (
                ("unknown material evidence", lambda item, facts: item["hotMaterialInsight"]["evidence"].update(material_ids=["999"]), "unknown material ID"),
                ("wrong deterministic count", lambda item, facts: facts["hotMaterialFacts"]["小仙炖"].update(qualifyingCount=2), "qualifyingCount"),
                ("below deterministic threshold", lambda item, facts: facts["hotMaterialFacts"]["小仙炖"]["materials"][0]["exposure"].update(min=199999), "below the threshold"),
            )
            for _label, mutate, expected in invalid_cases:
                invalid_analysis = copy.deepcopy(self._schema_v7_analysis_fixture(analysis))
                invalid_facts = copy.deepcopy(fact_pack)
                mutate(invalid_analysis["topMaterialCombination"]["brandConclusions"][0], invalid_facts)
                path.write_text(json.dumps(invalid_analysis, ensure_ascii=False), encoding="utf-8")
                with self.assertRaisesRegex(report.YuntuReportError, expected):
                    report.validate_analysis_input(analysis_json=path, fact_pack=invalid_facts)

    def test_schema_v7_accepts_configured_hot_material_threshold(self):
        report = load_module()
        analysis = {
            "topMaterialCombination": {
                "brandConclusions": [{
                    "brand": "小仙炖",
                    "classificationSource": "runtime_title_rule",
                    "dataSummary": "小仙炖本周期覆盖 1 条素材，累计曝光 60 万，CTR 2%、CVR 3%、3 秒播放率 40%。",
                    "evidence": ["品牌榜单聚合事实"],
                    "material_ids": ["101"],
                }]
            }
        }
        fact_pack = {
            "schemaVersion": 7,
            "filters": {"brands": ["小仙炖"]},
            "industryTop1000Facts": {"source_scope": "industry_top1000"},
            "brandRankingFacts": {"brands": {"小仙炖": {"source_scope": "brand_in_top1000", "sample_count": 1, "materials": [{"material_id": "101"}]}}},
            "comparisonFacts": {"previousPeriod": {}, "industryBenchmark": {}},
            "hotMaterialRule": {"metric": "exposure_interval_min", "comparison": "gte", "threshold": 500000},
            "hotMaterialFacts": {"小仙炖": {"thresholdExposureMin": 500000, "qualifyingCount": 1, "materials": [{"material_id": "101", "exposure": {"min": 600000, "max": 650000, "raw": "60万-65万"}}], "available": True, "missing_reason": ""}},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "analysis.json"
            path.write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")

            report.validate_analysis_input(analysis_json=path, fact_pack=fact_pack)

    @staticmethod
    def _schema_v7_analysis_fixture(analysis):
        """Restore the valid fixture after the scope mutation above."""
        restored = copy.deepcopy(analysis)
        insight = restored["topMaterialCombination"]["brandConclusions"][0].setdefault(
            "hotMaterialInsight", {}
        )
        insight.setdefault("title", "爆款素材表现分析")
        insight.setdefault("summary", "爆款素材达到曝光门槛，建议继续验证其指标组合。")
        insight["evidence"] = {"scope": "brand", "material_ids": ["101"]}
        restored["topMaterialCombination"]["brandConclusions"][0]["comparisonSummary"] = (
            "本周期相较上一周期样本增加，表现与行业大盘接近。"
        )
        return restored

    def test_render_report_renders_section_scope_labels_without_deep_frame_coverage(self):
        report = load_module()
        fact_pack = self.deep_dive_fact_pack()
        fact_pack["reportScopes"] = {
                "ranking": {"source_name": "TOP1000 榜单素材", "sample_count": 1000},
                "detail": {
                    "source_name": "成功秒级拆解素材",
                    "sample_count": 5,
                    "success_count": 5,
                    "failed_count": 1,
                },
        }
        fact_pack["brandTopNFacts"] = {"requested_top_n": 30, "brands": {}}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis_path = root / "analysis.json"
            analysis_path.write_text(
                json.dumps(self.deep_dive_analysis(), ensure_ascii=False), encoding="utf-8"
            )
            report.render_report(
                analysis_json=analysis_path,
                output_dir=root / "final-report",
                fact_pack=fact_pack,
            )
            rendered = (root / "final-report" / "final-report.html").read_text(
                encoding="utf-8"
            )
            markdown = (root / "final-report" / "final-report.md").read_text(
                encoding="utf-8"
            )

        self.assertIn('aria-label="01 章数据范围"', rendered)
        self.assertIn('aria-label="02 章数据范围"', rendered)
        self.assertIn('aria-label="04 章数据范围"', rendered)
        self.assertIn('aria-label="05 章数据范围"', rendered)
        self.assertNotIn('aria-label="03 章数据范围"', rendered)
        self.assertIn("TOP1000 榜单素材：1000 条", rendered)
        self.assertIn("成功秒级拆解素材：5 条", rendered)
        top_section = rendered.split('id="top-material-combination"', 1)[1].split(
            'id="audience-insights"', 1
        )[0]
        self.assertIn("TOP1000 榜单素材：1000 条", top_section)
        self.assertNotIn("成功秒级拆解素材：5 条", top_section)
        self.assertNotIn("高光帧可用：", rendered)
        self.assertNotIn("TOP1000 整体分析", rendered)
        self.assertIn("各品牌榜单分析", rendered)
        self.assertNotIn("各品牌榜单 Top N 分析", rendered)
        self.assertNotIn("品牌筛选 TOP30", rendered)
        self.assertNotIn("各品牌 TOP30", rendered)
        self.assertNotIn("TOP30", markdown)
        self.assertNotIn('<h3>综合结论</h3>', rendered)
        self.assertNotIn("综合结论：榜单、人群、卖点和已取得详情共同指向明确的内容机会。", rendered)
        self.assertIn('class="brand-classification-note">品牌归属：本次榜单标题匹配；分析范围：行业 TOP1000 内该品牌全部匹配素材</p>', rendered)

    def test_chapter01_renders_brand_metric_facts_instead_of_overall_block(self):
        report = load_module()
        analysis = self.analysis_json()
        analysis["topMaterialCombination"]["overallConclusions"] = [
            analysis["topMaterialCombination"]["overallConclusions"][0]
        ]
        fact_pack = {
            "filters": {"brands": ["万益蓝/WONDERLAB", "五个女博士", "燕之屋"]},
            "industryTop1000Facts": {"source_scope": "industry_top1000"},
            "brandTopNFacts": {
                "requested_top_n": 30,
                "brands": {
                    "万益蓝/WONDERLAB": {
                        "source_scope": "brand_top_n",
                        "sample_count": 12,
                        "metrics": {
                            "show_cnt": {"total": 123456},
                            "ctr": {"median": 0.0123},
                            "cvr": {"median": 0.0456},
                            "play_3s_rate": {"median": 0.321},
                        },
                    },
                    "五个女博士": {"source_scope": "brand_top_n", "sample_count": 8, "metrics": {}},
                    "燕之屋": {"source_scope": "brand_top_n", "sample_count": 6, "metrics": {}},
                },
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis_path = root / "analysis.json"
            analysis_path.write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
            report.render_report(
                analysis_json=analysis_path,
                output_dir=root / "final-report",
                fact_pack=fact_pack,
            )
            rendered = (root / "final-report" / "final-report.html").read_text(encoding="utf-8")

        self.assertNotIn("TOP1000 整体分析", rendered)
        self.assertNotIn('class="brand-metric-facts"', rendered)
        self.assertNotIn("分析样本 12 条", rendered)
        self.assertNotIn("累计曝光 12.3 万", rendered)
        self.assertNotIn("CTR 中位数 1.23%", rendered)
        self.assertNotIn("CVR 中位数 4.56%", rendered)
        self.assertNotIn("3 秒播放率中位数 32.10%", rendered)

    def test_chapter01_omits_executive_card_style(self):
        report = load_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis_path = root / "analysis.json"
            analysis_path.write_text(json.dumps(self.analysis_json(), ensure_ascii=False), encoding="utf-8")
            report.render_report(analysis_json=analysis_path, output_dir=root / "final-report")
            rendered = (root / "final-report" / "final-report.html").read_text(encoding="utf-8")

        self.assertNotIn(".unified-yuntu .top-material-executive {", rendered)

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
        self.assertEqual(rendered.count(' yuntu-content-card"'), 1)
        self.assertNotIn('class="brand-difference', rendered)
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
                        {"label": "18-19", "materialCount": 1, "materialShare": 1 / 3, "chartShare": 1 / 3},
                        {"label": "24-30", "materialCount": 2, "materialShare": 2 / 3, "chartShare": 2 / 3},
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
                fact_pack={
                    "audienceDashboard": audience_dashboard,
                    "audienceTopNRecords": [
                        {"material_id": "1", "rank": 1, "people_tags": ["24-30", "女", "新锐白领"]},
                        {"material_id": "2", "rank": 2, "people_tags": ["24-30", "女", "新锐白领", "精致妈妈"]},
                        {"material_id": "3", "rank": 3, "people_tags": ["女"]},
                    ],
                },
            )
            markdown = (root / "final-report" / "final-report.md").read_text(encoding="utf-8")
            html = (root / "final-report" / "final-report.html").read_text(encoding="utf-8")

        for rendered in (markdown, html):
            self.assertIn("02｜人群及营销卖点洞察", rendered)
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
        self.assertIn('style="background:conic-gradient(#9b6a37 0.0000%', html)
        age_chart = html[html.index('class="chart-card audience-chart audience-chart-age"'):html.index('class="chart-card audience-chart audience-chart-gender"')]
        self.assertLess(age_chart.index('&quot;24-30&quot;'), age_chart.index('&quot;18-19&quot;'))
        self.assertLess(age_chart.index('title="24-30：'), age_chart.index('title="18-19：'))
        self.assertIn('class="chart-card audience-chart audience-chart-crowd"', html)
        self.assertLess(
            html.index('class="chart-card audience-chart audience-chart-crowd"'),
            html.index('class="chart-card audience-chart audience-chart-age"'),
        )
        self.assertIn('class="audience-column-chart"', html)
        self.assertIn('class="audience-column-label">新锐白领</span>', html)
        self.assertIn('class="audience-dashboard" data-audience-records=', html)
        self.assertIn('data-collapsible-expanded-label="收起人群及营销卖点汇总数据"', html)
        self.assertIn('data-collapsible-collapsed-label="展开人群及营销卖点汇总数据"', html)
        self.assertIn('class="collapsible-toggle-action">收起人群及营销卖点汇总数据</span>', html)
        self.assertNotIn('class="collapsible-body-title">人群数据</b>', html)
        self.assertIn('data-audience-topn-range', html)
        self.assertIn('data-audience-topn-input', html)
        self.assertIn('data-audience-topn-label', html)
        self.assertIn('computeAudienceDimension', html)
        self.assertIn('renderAudienceTopN', html)
        self.assertIn('function computeMarketingCategories(selectedRecords)', html)
        self.assertIn("new CustomEvent('audience-topn-change'", html)
        self.assertIn("addEventListener('audience-topn-change'", html)
        self.assertIn('renderMarketingOverview(computeMarketingCategories(event.detail.records || []))', html)
        self.assertIn("var visualBuckets = key === 'age'", html)
        self.assertIn('var legendBuckets = visualBuckets;', html)
        self.assertIn("renderAudienceGroupDrill(item.closest('article')", html)
        self.assertIn('class="legend-label"><i class="legend-swatch"', html)
        self.assertIn('class="legend-count">2 条</span>', html)
        self.assertIn('class="legend-share">100.0%</span>', html)
        self.assertIn('class="chart-tooltip"', html)
        self.assertIn('命中素材数：2条', html)
        self.assertIn('占比：100.0%', html)
        self.assertIn("item.title = bucket.label + '：命中素材数：'", html)
        self.assertIn("'条 占比：' + pct(bucket.chartShare)", html)
        self.assertIn("tooltip.append(title, count, share);", html)
        self.assertIn("pieTooltip.replaceChildren(title, count, share);", html)
        self.assertIn("showPieTooltip", html)
        self.assertIn("hidePieTooltip", html)
        self.assertIn("data-pie-tooltip", html)
        self.assertNotIn("归一化占比", markdown)
        self.assertNotIn("归一化占比", html)
        self.assertNotIn("覆盖率", markdown)
        self.assertNotIn("覆盖率", html)

    def test_render_report_renders_all_and_brand_chapter02_tabs(self):
        report = load_module()
        chapter02 = {
            "scopeOrder": ["all", "WONDERLAB/万益蓝"],
            "all": {"label": "全量 TOP1000", "topMaterials": [{"material_id": "1", "rank": 1, "title": "素材一", "people_tags": ["24-30"], "material_tags": ["功效功能_肠道健康"]}], "audienceDashboard": {"dimensions": {"age": {"labelMode": "normalized_tag_share", "recordCount": 1, "buckets": [{"label": "24-30", "materialCount": 1, "materialShare": 1, "chartShare": 1}]} }}, "marketingDashboard": {"tagCount": 3, "occurrenceCount": 5, "categories": [{"category": "成分/原料", "tagCount": 2, "occurrenceCount": 4, "tags": [{"tag": "益生菌", "count": 3}, {"tag": "膳食纤维", "count": 1}], "topTags": [{"tag": "益生菌", "count": 3}]}]}},
            "WONDERLAB/万益蓝": {"label": "WONDERLAB/万益蓝", "topMaterials": [{"material_id": "2", "rank": 2, "title": "素材二", "people_tags": ["女"], "material_tags": ["功效功能_肠道健康"]}], "audienceDashboard": {"dimensions": {}}, "marketingDashboard": {"tagCount": 1, "occurrenceCount": 1, "categories": [{"category": "功效", "tagCount": 1, "occurrenceCount": 1, "topTags": [{"tag": "肠道健康", "count": 1}]}]}},
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis_path = root / "analysis.json"
            analysis_path.write_text(json.dumps(self.analysis_json(), ensure_ascii=False), encoding="utf-8")
            report.render_report(analysis_json=analysis_path, output_dir=root / "report", fact_pack={"chapter02Facts": chapter02})
            html = (root / "report" / "final-report.html").read_text(encoding="utf-8")
            markdown = (root / "report" / "final-report.md").read_text(encoding="utf-8")

        self.assertIn("02｜人群及营销卖点洞察", html)
        self.assertIn('data-chapter02-tab="all"', html)
        self.assertIn('data-chapter02-tab="WONDERLAB/万益蓝"', html)
        self.assertEqual(html.count('role="tabpanel" id="chapter02-panel-'), 2)
        self.assertIn("营销卖点汇总", html)
        self.assertIn('data-audience-records=', html)
        self.assertIn('id="chapter02-audience-dashboard-body-0"', html)
        self.assertIn('data-marketing-categories=', html)
        self.assertIn('class="chart-grid script-dashboard-overview marketing-column-chart"', html)
        self.assertIn('.chart-grid.script-dashboard-overview.marketing-column-chart{grid-template-columns:repeat(auto-fit,minmax(78px,1fr))', html)
        self.assertIn('class="section-title-row"><h3>营销卖点汇总</h3><p class="script-dashboard-hint chart-interaction-hint">点击一级标签柱状图可查看二级标签分布</p></div>', html)
        self.assertIn('营销卖点标签分类规则以完整营销卖点中括号里的内容为一级标签。', html)
        self.assertNotIn('由于 RPA 提取的营销卖点数据以下划线区分层级，而下划线不会透出，因此此处以云图官方界面显示作为解释。', html)
        self.assertNotIn('点击类别柱查看该类别的标签比例', html)
        self.assertIn("titleRow.className = 'section-title-row'", html)
        self.assertIn("hint.className = 'chart-interaction-hint audience-crowd-hint'", html)
        self.assertIn("hint.textContent = '点击柱状图查看对应人群 TOP3 素材'", html)
        self.assertIn("summary.textContent = '点击一级标签柱状图可查看二级标签分布'", html)
        self.assertIn('role="region" tabindex="0" aria-label="营销卖点汇总柱状图"', html)
        self.assertIn('flex-wrap:nowrap', html)
        self.assertIn('overflow-x:auto', html)
        self.assertIn('flex:0 0 86px', html)
        self.assertIn('flex:0 0 68px', html)
        self.assertIn('column-item column-item-interactive marketing-category-column', html)
        self.assertIn('data-marketing-category-column', html)
        self.assertIn('class="marketing-dashboard marketing-dashboard-card chart-card"', html)
        self.assertIn('marketing-drill-detail script-drill-detail is-entering', html)
        self.assertIn('marketing-drill-layout script-drill-layout', html)
        self.assertIn('marketing-drill-primary script-drill-primary', html)
        self.assertIn('marketing-drill-primary-plot script-drill-primary-plot', html)
        self.assertIn('&quot;tags&quot;:[{', html)
        self.assertIn('renderMarketingDrill', html)
        self.assertIn('returnToMarketingOverview', html)
        self.assertIn("var topTags = tags.slice(0, 10);", html)
        self.assertIn("其他 ' + tailTags.length + ' 个标签", html)
        self.assertIn(".sort(function (left, right) { return Number(right.count || 0) - Number(left.count || 0); });", html)
        self.assertIn('marketing-tag-detail-toggle', html)
        self.assertIn('marketing-tag-detail-table', html)
        self.assertIn('.unified-yuntu .marketing-column-chart { border:0;', html)
        self.assertIn('.unified-yuntu .marketing-drill-detail { border:0;', html)
        self.assertIn('.unified-yuntu .marketing-drill-primary-plot { height:280px; border:0; background:transparent;', html)
        self.assertIn('.unified-yuntu .marketing-drill-primary { grid-template-rows:auto 280px auto;', html)
        self.assertIn('.unified-yuntu .marketing-drill-primary { padding:16px 12px 12px;', html)
        self.assertIn('.unified-yuntu .marketing-drill-chart .pie-chart { box-shadow:none;', html)
        self.assertIn('.unified-yuntu .marketing-drill-chart { padding:16px;', html)
        self.assertIn('.unified-yuntu .marketing-drill-chart .pie-legend { align-content:start; max-height:none; overflow:visible; }', html)
        self.assertIn('.unified-yuntu .marketing-drill-chart .legend-item { padding:3px 4px; font-size:11px; line-height:1.25;', html)
        self.assertIn('.unified-yuntu .marketing-tag-detail-table { width:100%;', html)
        self.assertNotIn('class="marketing-dashboard raw-fact-card"', html)
        self.assertIn("全量 TOP1000", markdown)
        self.assertIn("WONDERLAB/万益蓝", markdown)
        self.assertIn("占比 100.0%", markdown)
        self.assertIn("占比：100.0%", html)
        self.assertIn('class="audience-data-card raw-fact-card"', html)
        self.assertIn('data-collapsible-toggle data-collapsible-expanded-label=', html)
        self.assertIn('class="collapsible-body" id="chapter02-audience-dashboard-body-0"', html)
        self.assertIn('.page{width:min(1280px,calc(100% - 20px));', html)
        self.assertIn('overflow-x: hidden;', html)
        self.assertIn('.audience-pie-layout{display:grid;grid-template-columns:minmax(0,45fr) minmax(0,55fr);', html)
        self.assertIn('.audience-chart-age,.audience-chart-gender{display:flex;flex-direction:column}', html)
        self.assertIn('flex:1;min-height:0;gap:14px;align-items:center', html)
        self.assertIn('@container (max-width:360px){.audience-pie-layout{grid-template-columns:1fr}', html)

    def test_render_report_uses_adaptive_audience_drill_and_shared_chapter02_column_styles(self):
        report = load_module()
        chapter02 = {
            "scopeOrder": ["all"],
            "all": {
                "label": "全量 TOP1000",
                "topMaterials": [{
                    "material_id": "1", "rank": 1, "title": "素材一",
                    "people_tags": ["新锐白领"],
                    "material_tags": ["功效功能_补充营养_日常养护", "未分层营销标签"],
                }],
                "audienceDashboard": {"dimensions": {"crowd": {
                    "labelMode": "normalized_tag_share", "recordCount": 1,
                    "buckets": [{"label": "新锐白领", "materialCount": 1, "chartShare": 1}],
                }}},
                "marketingDashboard": {
                    "taxonomyVersion": 2,
                    "tagCount": 2,
                    "occurrenceCount": 2,
                    "categories": [{
                        "category": "功效功能", "tagCount": 1, "occurrenceCount": 1,
                        "tags": [{"tag": "补充营养_日常养护", "rawTag": "功效功能_补充营养_日常养护", "count": 1}],
                    }, {
                        "category": "其他", "tagCount": 1, "occurrenceCount": 1,
                        "tags": [{"tag": "未分层营销标签", "rawTag": "未分层营销标签", "count": 1}],
                    }],
                },
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis_path = root / "analysis.json"
            analysis_path.write_text(json.dumps(self.analysis_json(), ensure_ascii=False), encoding="utf-8")
            report.render_report(analysis_json=analysis_path, output_dir=root / "report", fact_pack={"chapter02Facts": chapter02})
            html = (root / "report" / "final-report.html").read_text(encoding="utf-8")

        self.assertIn('data-marketing-taxonomy-version="2"', html)
        self.assertIn("function parseMarketingTag(rawTag)", html)
        self.assertNotIn("function marketingCategory(tag)", html)
        self.assertIn("rawTag: parsed.rawTag", html)
        self.assertIn("function formatExposure(record)", html)
        self.assertIn("className = 'preference-exposure'", html)
        self.assertIn("exposure.textContent = '曝光量：' + formatExposure(record)", html)
        self.assertIn("grid-template-areas", html)
        self.assertIn('.unified-yuntu .audience-drill-panel {', html)
        self.assertIn('min-height: 0;', html)
        self.assertIn('align-self: stretch;', html)
        self.assertIn('height: auto;', html)
        self.assertIn('.unified-yuntu :is(.audience-column-bar, .marketing-category-column .column-bar)', html)
        self.assertIn('linear-gradient(180deg, #e1ac61 0%, #9b6a37 100%)', html)
        self.assertIn('.unified-yuntu :is(.audience-column-item, .marketing-category-column):hover', html)
        self.assertIn('.pie-chart{position:relative;width:min(260px,100%);', html)
        self.assertIn('.audience-chart-gender .pie-chart{width:min(240px,100%)}', html)
        self.assertIn('.pie-legend .legend-item{position:relative;display:grid;grid-template-columns:minmax(80px,1fr) auto auto;', html)
        self.assertIn('.audience-column-chart{position:relative;min-height:250px;', html)
        self.assertIn('.unified-report :is(.pie-layout, .audience-pie-layout)', html)
        self.assertIn('flex-direction: column;', html)
        self.assertIn('width: min(320px, 100%) !important;', html)
        self.assertIn('.unified-report .pie-legend {', html)
        self.assertIn(".unified-yuntu .audience-chart-age .pie-legend", html)
        self.assertIn('.unified-yuntu .audience-chart-age .pie-legend .legend-label', html)
        self.assertIn('font-weight: 700;', html)
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr));", html)
        self.assertIn("grid-template-columns: max-content max-content max-content;", html)
        self.assertIn('contain: layout paint;', html)
        self.assertIn(".unified-report .section-header {", html)
        self.assertIn("border-bottom: 0;", html)
        self.assertIn(".unified-yuntu :is(#audience-insights, #highlight-insights, #material-deep-dive) > .section-header", html)
        self.assertIn(".unified-yuntu .brand-tabs {", html)
        self.assertIn("gap: 12px;", html)
        self.assertIn("padding: 0 2px 16px;", html)
        self.assertIn("scrollbar-width: thin;", html)
        self.assertNotIn('class="pie-tooltip"', html)
        self.assertNotIn('class="audience-bar-chart"', html)

    def test_render_report_renders_chapter02_dimensions_with_titles_and_details(self):
        report = load_module()
        analysis = self.analysis_json()
        analysis["chapter02Insights"] = {
            "scopeOrder": ["all"],
            "scopes": {
                "all": {
                    "audienceSummary": {
                        "title": "女性与 31-40 岁是主要内容入口",
                        "summary": "八大人群中以新锐白领和精致妈妈为主要覆盖，同时女性与31-40岁构成核心标签，应作为内容入口假设而非真实受众比例。",
                        "evidence": [{"metric": "people_tags", "value": "女/31-40"}],
                        "material_ids": ["101"],
                    },
                    "audienceInsights": [{
                        "title": "旧版人群分点不应继续编号",
                        "summary": "旧版人群分点不应继续编号。",
                        "evidence": [{"metric": "people_tags", "value": "女"}],
                        "material_ids": ["101"],
                    }, {
                        "title": "旧版人群第二分点",
                        "summary": "旧版人群第二分点也只作为兼容内容。",
                        "evidence": [{"metric": "people_tags", "value": "31-40"}],
                        "material_ids": ["101"],
                    }],
                    "marketingSummary": {
                        "title": "产品展示承担首屏识别",
                        "summary": "卖点标签显示产品展示与购买信息经常并置，后续应拆开顺序验证。",
                        "evidence": [{"metric": "material_tags", "value": "商品展示"}],
                        "material_ids": ["101"],
                    },
                    "marketingInsights": [{
                        "title": "旧版营销分点不应继续编号",
                        "summary": "旧版营销分点不应继续编号。",
                        "evidence": [{"metric": "material_tags", "value": "使用场景/促销利益"}],
                        "material_ids": ["101"],
                    }, {
                        "title": "旧版营销第二分点",
                        "summary": "旧版营销第二分点也只作为兼容内容。",
                        "evidence": [{"metric": "material_tags", "value": "促销利益"}],
                        "material_ids": ["101"],
                    }],
                }
            },
        }
        chapter02 = {
            "scopeOrder": ["all"],
            "all": {
                "label": "全量 TOP1000",
                "topMaterials": [],
                "audienceDashboard": {"dimensions": {}},
                "marketingDashboard": {"tagCount": 1, "occurrenceCount": 1, "categories": []},
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis_path = root / "analysis.json"
            analysis_path.write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
            report.render_report(analysis_json=analysis_path, output_dir=root / "report", fact_pack={"chapter02Facts": chapter02})
            html = (root / "report" / "final-report.html").read_text(encoding="utf-8")

        self.assertIn("人群", html)
        self.assertIn("女性与 31-40 岁是主要内容入口", html)
        self.assertIn("八大人群中以新锐白领和精致妈妈为主要覆盖", html)
        self.assertIn("营销卖点", html)
        self.assertIn("产品展示承担首屏识别", html)
        self.assertIn("卖点标签显示产品展示与购买信息经常并置", html)
        self.assertIn('class="chapter02-dimension-block"', html)
        self.assertIn('class="chapter02-dimension-content"', html)
        self.assertNotIn('<article class="chapter02-detail-insight"', html)
        self.assertIn('class="chapter02-dimension-lead"', html)
        self.assertNotIn('旧版人群分点不应继续编号', html)
        self.assertNotIn('旧版人群第二分点', html)
        self.assertNotIn('旧版营销分点不应继续编号', html)
        self.assertNotIn('旧版营销第二分点', html)
        self.assertNotIn('audienceInsights', html)
        self.assertNotIn('。；', html)

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
        del analysis["topMaterialCombination"]["brandConclusions"][0]["evidence"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "analysis.json"
            path.write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(report.YuntuReportError, "evidence"):
                report.render_report(analysis_json=path, output_dir=Path(directory) / "report")

    def test_render_report_accepts_top_material_contract_without_brand_comparison(self):
        report = load_module()
        analysis = self.analysis_json()
        analysis["topMaterialCombination"].pop("brandComparisonConclusion")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = Path(directory) / "analysis.json"
            path.write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
            report.render_report(analysis_json=path, output_dir=root / "report")
            rendered = (root / "report" / "final-report.html").read_text(
                encoding="utf-8"
            )

        self.assertNotIn("品牌间差异总结", rendered)

    def test_render_report_separates_chapter01_ai_blocks_and_comparison_collapse(self):
        report = load_module()
        brands = ["小仙炖"]
        analysis = {
            "topMaterialCombination": {
                "brandConclusions": [{
                    "brand": "小仙炖",
                    "classificationSource": "runtime_title_rule",
                    "dataSummary": "表现对比段落，覆盖曝光、CTR、CVR 和 3 秒播放率。",
                    "hotMaterialInsight": {
                        "title": "爆款整体洞察",
                        "summary": "爆款整体段落，说明共同内容机会和验证方向。",
                        "evidence": {"scope": "brand", "material_ids": ["101"]},
                    },
                    "evidence": ["brand"], "material_ids": ["101"],
                }],
                "allBrandsConclusion": {
                    "brand": "全品牌",
                    "classificationSource": "runtime_title_rule",
                    "dataSummary": "全范围表现对比段落，覆盖曝光、CTR、CVR 和 3 秒播放率。",
                    "hotMaterialInsight": {
                        "title": "全范围爆款整体洞察",
                        "summary": "全范围爆款段落，说明共同内容机会和验证方向。",
                        "evidence": {"scope": "all", "material_ids": ["101"]},
                    },
                    "evidence": ["all"], "material_ids": ["101"],
                },
            }
        }
        hot = {
            "thresholdExposureMin": 200000,
            "qualifyingCount": 1,
            "materials": [{
                "material_id": "101", "title": "真实爆款素材",
                "exposure": {"min": 200000, "max": 220000, "raw": "20万-22万"},
                "metrics": {"ctr": 0.1, "cvr": 0.02, "play_3s_rate": 0.4},
            }],
            "available": True, "missing_reason": "",
        }
        comparison_template = {
            "current": {
                "sampleCount": 2,
                "metrics": {
                    "show_cnt": {"total": 2686377, "median": 1343188.5},
                    "ctr": {"median": 0.0327},
                    "cvr": {"median": 0.0709},
                    "play_3s_rate": {"median": 0.7441},
                },
            },
            "previousPeriod": {
                "currentSampleCount": 2,
                "baselineSampleCount": 3,
                "metrics": {
                    "show_cnt": {"current": 2686377, "baseline": 2000000, "delta": 686377, "rate": -0.301},
                    "ctr": {"current": 0.0327, "baseline": 0.0367, "delta": -0.004, "rate": -0.109},
                    "cvr": {"current": 0.0709, "baseline": 0.0609, "delta": 0.01, "rate": 0.164},
                    "play_3s_rate": {"current": 0.7441, "baseline": 0.7641, "delta": -0.02, "rate": -0.026},
                },
            },
            "industryBenchmark": {
                "currentSampleCount": 2,
                "baselineSampleCount": 10,
                "metrics": {
                    "show_cnt": {"current": 2686377, "baseline": 3000000, "delta": -313623, "rate": 0.093},
                    "ctr": {"current": 0.0327, "baseline": 0.04, "delta": -0.0073, "rate": 0.323},
                    "cvr": {"current": 0.0709, "baseline": 0.0909, "delta": -0.02, "rate": -0.221},
                    "play_3s_rate": {"current": 0.7441, "baseline": 0.7741, "delta": -0.03, "rate": -0.039},
                },
            },
        }
        fact_pack = {
            "schemaVersion": 7,
            "filters": {"brands": brands},
            "comparisonFacts": {"scopes": {"all": copy.deepcopy(comparison_template), "小仙炖": copy.deepcopy(comparison_template)}},
            "hotMaterialFacts": {"all": copy.deepcopy(hot), "小仙炖": copy.deepcopy(hot)},
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "analysis.json"
            path.write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
            report.render_report(analysis_json=path, output_dir=root / "report", fact_pack=fact_pack)
            rendered = (root / "report" / "final-report.html").read_text(encoding="utf-8")
            markdown = (root / "report" / "final-report.md").read_text(encoding="utf-8")

        self.assertIn("所有指定品牌", rendered)
        self.assertIn("素材表现洞察", rendered)
        self.assertIn("爆款素材洞察", rendered)
        self.assertIn("aria-expanded=\"true\"", rendered)
        self.assertIn("aria-controls=\"chapter01-comparison-details-all-brands\"", rendered)
        self.assertIn("环比与全行业对比", rendered)
        self.assertIn("收起环比与全行业对比数据", rendered)
        self.assertIn("当前默认筛选条件", rendered)
        self.assertEqual(rendered.count('class="chapter01-comparison-group chapter01-comparison-card"'), 6)
        self.assertEqual(rendered.count("真实值"), 6)
        self.assertEqual(rendered.count('class="chapter01-comparison-card-change"'), 0)
        self.assertNotIn(">变化</h6>", rendered)
        self.assertIn("环比周期", rendered)
        self.assertIn("同周期全行业", rendered)
        self.assertIn("200.0 万次（变化率 -25.55%）", rendered)
        self.assertIn("300.0 万次（变化率 +11.67%）", rendered)
        self.assertIn("268.6 万次", rendered)
        self.assertNotIn("e+", rendered.lower())
        self.assertIn("收起爆款素材汇总数据", rendered)
        self.assertIn("所有指定品牌", markdown)
        self.assertIn("爆款整体段落", rendered)
        self.assertIn("素材表现洞察", markdown)
        self.assertIn("环比与全行业对比", markdown)
        self.assertIn("曝光总量：200.0 万次（变化率 -25.55%）", markdown)
        self.assertIn("曝光总量：300.0 万次（变化率 +11.67%）", markdown)
        self.assertNotIn("- 变化：", markdown)
        self.assertNotIn("e+", markdown.lower())
        self.assertLess(rendered.index("素材表现洞察"), rendered.index("环比与全行业对比"))
        self.assertLess(rendered.index("当前默认筛选条件", rendered.index("环比与全行业对比")), rendered.index("环比周期", rendered.index("环比与全行业对比")))
        self.assertLess(rendered.index("环比周期", rendered.index("环比与全行业对比")), rendered.index("同周期全行业", rendered.index("环比与全行业对比")))
        self.assertLess(rendered.index("环比与全行业对比"), rendered.index("爆款素材洞察"))
        self.assertLess(rendered.index("爆款素材洞察"), rendered.index("爆款素材面板"))

    def test_chapter01_comparison_cards_match_hot_material_style_and_responsive_layout(self):
        css = (ROOT / "assets" / "report" / "unified-report.css").read_text(encoding="utf-8")
        grid_rule = css.split(".unified-yuntu .chapter01-comparison-grid {", 1)[1].split("}", 1)[0]
        card_rule = css.split(".unified-yuntu .chapter01-comparison-card {", 1)[1].split("}", 1)[0]
        self.assertIn("grid-template-columns: repeat(3, minmax(0, 1fr));", grid_rule)
        self.assertIn("padding: 10px;", card_rule)
        self.assertIn("border-radius: 6px;", card_rule)
        self.assertIn("background: #fff;", card_rule)
        self.assertIn(".unified-yuntu .chapter01-comparison {", css)
        comparison_rule = css.split(".unified-yuntu .chapter01-comparison {", 1)[1].split("}", 1)[0]
        self.assertIn("background: #fffdf8;", comparison_rule)
        self.assertIn(
            "@media (max-width: 700px) {\n  .unified-yuntu .chapter01-comparison-grid {\n    grid-template-columns: 1fr;",
            css,
        )

    def test_render_report_rejects_audit_content_in_user_readable_summaries(self):
        report = load_module()
        for field, value in (
            ("dataSummary", "证据：{\"metric\": \"ctr\"}"),
            ("peopleSummary", "查看数据依据"),
        ):
            with self.subTest(field=field):
                analysis = self.analysis_json()
                target = analysis["topMaterialCombination"]["brandConclusions"][0]
                target[field] = value
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "analysis.json"
                    path.write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
                    with self.assertRaisesRegex(report.YuntuReportError, "audit"):
                        report.render_report(
                            analysis_json=path, output_dir=Path(directory) / "report"
                        )

    def test_render_report_renders_script_placeholder_and_highlight_unavailable_state(self):
        report = load_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis_path = root / "analysis.json"
            analysis_path.write_text(json.dumps(self.analysis_json(), ensure_ascii=False), encoding="utf-8")
            report.render_report(analysis_json=analysis_path, output_dir=root / "report")
            markdown = (root / "report" / "final-report.md").read_text(encoding="utf-8")
            rendered = (root / "report" / "final-report.html").read_text(encoding="utf-8")
        self.assertEqual(rendered.count('class="section"'), 5)
        self.assertIn('class="report-nav"', rendered)
        self.assertIn('href="#top-material-combination"', rendered)
        self.assertIn('href="#audience-insights"', rendered)
        self.assertIn('href="#script-insights"', rendered)
        self.assertIn('href="#highlight-insights"', rendered)
        self.assertIn('href="#material-deep-dive"', rendered)
        self.assertIn("脚本数据：未接入", rendered)
        self.assertIn("本次云图 RPA 未提供可用于汇总的脚本正文与时间戳段落", markdown)
        self.assertIn("暂无可用高光帧", rendered)
        self.assertNotIn("data-highlight-collapse-toggle", rendered)
        self.assertNotIn('href="#landscape"', rendered)
        self.assertIn('</div></div></section>', rendered)
        self.assertNotIn('class="brand-difference', rendered)
        self.assertNotIn("榜单竞争格局", markdown)

    def test_render_report_renders_material_deep_dive_with_tabs_frames_and_five_charts(self):
        report = load_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "analysis.json"
            path.write_text(json.dumps(self.deep_dive_analysis(), ensure_ascii=False), encoding="utf-8")
            report.render_report(analysis_json=path, output_dir=root / "report", fact_pack=self.deep_dive_fact_pack())
            rendered = (root / "report" / "final-report.html").read_text(encoding="utf-8")
            markdown = (root / "report" / "final-report.md").read_text(encoding="utf-8")
        self.assertIn('aria-label="单素材深度分析"', rendered)
        self.assertIn('data-material-tab', rendered)
        self.assertIn('data-material-id="101"', rendered)
        self.assertIn('class="deep-frame-grid fixed-six"', rendered)
        self.assertIn('class="second-level-timeline raw-fact-card"', rendered)
        self.assertIn('data-collapsible-toggle', rendered)
        self.assertIn('data-collapsible-expanded-label="收起秒级拆解数据"', rendered)
        self.assertIn('data-collapsible-collapsed-label="展开秒级拆解数据"', rendered)
        self.assertIn('class="collapsible-toggle-action">收起秒级拆解数据</span>', rendered)
        self.assertIn('<span>曝光量</span><b>20万-22万</b>', rendered)
        self.assertNotIn('<span>曝光量</span><b>20.0 万</b>', rendered)
        self.assertNotIn('class="collapsible-toggle-action">收起数据</span>', rendered)
        self.assertNotIn('class="collapsible-toggle-action">收起/展开秒级拆解数据</span>', rendered)
        self.assertEqual(rendered.count('class="second-level-chart"'), 0)
        deep_dive_section = rendered.split('id="material-deep-dive"', 1)[1]
        self.assertIn("0s · 点击指数 -", deep_dive_section)
        self.assertIn("2s · 点击指数 0.8", deep_dive_section)
        self.assertNotIn("封面画面", deep_dive_section)
        self.assertNotIn("点击 Top1 波峰画面", deep_dive_section)
        self.assertIn('data-jump-material="101"', rendered)
        self.assertIn('class="highlight-material-title"', rendered)
        self.assertIn("## 05｜单素材深度分析", markdown)
        self.assertIn("秒级拆解", markdown)
        self.assertNotIn("AI 二次分析", rendered)
        self.assertNotIn("画面总结", rendered)
        self.assertNotIn("#### 数据总结", markdown)
        self.assertNotIn("#### 复用建议", markdown)
        self.assertNotIn("#### 不建议照搬", markdown)
        self.assertNotIn("可结合画面主体、字幕和产品露出查看节奏分布", rendered)
        self.assertNotIn("未输出观察。", markdown)

        css = (ROOT / "assets" / "report" / "unified-report.css").read_text(encoding="utf-8")
        self.assertIn("gap: 12px;", css)
        self.assertIn("border-bottom: 1px solid var(--unified-line);", css)
        self.assertIn("padding: 0 2px 8px;", css)
        self.assertIn("bottom: -1px;", css)
        self.assertIn("border-top: 0;", css)
        self.assertIn(".unified-yuntu .second-level-switcher.metric-switch", css)
        metric_rule = css.split(".unified-yuntu .second-level-switcher.metric-switch", 1)[1].split("}", 1)[0]
        self.assertIn("gap: 14px;", metric_rule)
        self.assertIn(
            ".unified-yuntu :is(.brand-tabs,.chapter02-tabs,.highlight-dashboard-tabs,.highlight-brand-tabs) {\n  gap: 12px;\n  padding: 0 2px 8px;",
            css,
        )
        self.assertIn(
            '.unified-yuntu :is(.brand-tab,.chapter02-tabs button,.highlight-dashboard-tabs button,.highlight-brand-tabs button)[aria-selected="true"]::after {\n  right: 12px;\n  bottom: -1px;\n  left: 12px;',
            css,
        )
        self.assertIn("bottom: -1px;", css)
        self.assertIn(".unified-yuntu .material-detail-tabs {", css)
        material_tabs_rule = css.split(".unified-yuntu .material-detail-tabs {", 1)[1].split("}", 1)[0]
        self.assertIn("gap: 14px;", material_tabs_rule)

    def test_render_report_uses_qianchuan_style_frame_first_deep_dive_layout(self):
        report = load_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "analysis.json"
            path.write_text(json.dumps(self.deep_dive_analysis(), ensure_ascii=False), encoding="utf-8")
            report.render_report(analysis_json=path, output_dir=root / "report", fact_pack=self.deep_dive_fact_pack())
            rendered = (root / "report" / "final-report.html").read_text(encoding="utf-8")

        self.assertIn('class="material-deep-layout side-tabs"', rendered)
        self.assertIn('class="material-deep-tab-list"', rendered)
        self.assertIn('class="deep-visual-strip"', rendered)
        self.assertIn('class="deep-frame-grid fixed-six"', rendered)
        self.assertNotIn("<video", rendered)

    def test_render_report_matches_reference_material_card_and_fixed_frame_strip(self):
        report = load_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "analysis.json"
            path.write_text(json.dumps(self.deep_dive_analysis(), ensure_ascii=False), encoding="utf-8")
            report.render_report(analysis_json=path, output_dir=root / "report", fact_pack=self.deep_dive_fact_pack())
            rendered = (root / "report" / "final-report.html").read_text(encoding="utf-8")

        self.assertIn('class="material-deep-panel material-card"', rendered)
        self.assertIn('class="material-deep-header material-head"', rendered)
        self.assertIn('--visual-height:560px', rendered)
        self.assertIn('grid-template-rows:repeat(2,minmax(0,1fr))', rendered)
        self.assertIn('max-height:calc(100vh - 36px)', rendered)

    def test_render_report_reports_unavailable_deep_dive_frames(self):
        report = load_module()
        fact_pack = self.deep_dive_fact_pack()
        for frame in fact_pack["materialFacts"][0]["highlightFrames"]:
            frame.update({"available": False, "failure_reason": "视频链接已过期"})
        analysis = self.deep_dive_analysis()
        analysis["highlightDashboard"]["groups"][0]["frame_refs"] = [
            "highlight:102:cover:0", "highlight:102:click_peak:2"
        ]
        analysis["materialDeepDives"][0]["frame_observations"] = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "analysis.json"
            path.write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
            report.render_report(analysis_json=path, output_dir=root / "report", fact_pack=fact_pack)
            rendered = (root / "report" / "final-report.html").read_text(encoding="utf-8")

        self.assertIn("视频链接已过期", rendered)
        self.assertIn("暂无可用于观察的高光帧。", rendered)

    def test_render_report_renders_second_level_timeline_interactions(self):
        report = load_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "analysis.json"
            path.write_text(json.dumps(self.deep_dive_analysis(), ensure_ascii=False), encoding="utf-8")
            report.render_report(analysis_json=path, output_dir=root / "report", fact_pack=self.deep_dive_fact_pack())
            rendered = (root / "report" / "final-report.html").read_text(encoding="utf-8")

        self.assertIn('class="second-level-timeline raw-fact-card"', rendered)
        self.assertIn('data-second-level-metric="点赞指数"', rendered)
        self.assertIn('class="second-level-switcher metric-switch"', rendered)
        self.assertIn('class="second-level-range-control"', rendered)
        self.assertIn('data-second-level-point', rendered)
        self.assertIn('data-second-level-curve', rendered)
        self.assertIn("second-level-tooltip timeline-tooltip", rendered)
        self.assertIn('linearPath(coords)', rendered)
        self.assertNotIn('smoothPath(coords)', rendered)
        self.assertNotIn('class="second-level-chart"', rendered)

    def test_render_report_renders_deep_dive_inner_tabs_tags_and_frame_selection(self):
        report = load_module()
        fact_pack = self.deep_dive_fact_pack()
        fact_pack["materialFacts"][1]["listDataAvailability"]["people_tags"] = {
            "available": False, "missing_reason": "source_empty"
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "analysis.json"
            path.write_text(json.dumps(self.deep_dive_analysis(), ensure_ascii=False), encoding="utf-8")
            report.render_report(analysis_json=path, output_dir=root / "report", fact_pack=fact_pack)
            rendered = (root / "report" / "final-report.html").read_text(encoding="utf-8")

        self.assertIn('class="material-detail-tabs"', rendered)
        self.assertIn('data-material-detail-tab="visual"', rendered)
        self.assertIn('data-material-detail-tab="timeline"', rendered)
        self.assertIn('data-material-detail-tab="script"', rendered)
        self.assertIn('核心人群标签', rendered)
        self.assertIn('新锐白领', rendered)
        self.assertIn('营销卖点标签', rendered)
        self.assertIn('睡前场景', rendered)
        self.assertIn('class="deep-frame-selection-controls"', rendered)
        self.assertIn('data-deep-frame-select-all', rendered)
        self.assertIn('data-deep-frame-clear', rendered)
        self.assertIn('data-deep-frame-checkbox', rendered)
        self.assertIn('data-deep-frame-observation', rendered)
        self.assertIn('data-deep-frame-observation-empty', rendered)
        self.assertIn('全选高光帧', rendered)
        self.assertIn('全不选高光帧', rendered)
        self.assertIn('脚本数据：未接入', rendered)
        self.assertIn('核心人群标签</dt><dd>未返回</dd>', rendered)

    def test_render_report_supports_keyboard_tabs_and_filtered_highlight_observations(self):
        report = load_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "analysis.json"
            path.write_text(json.dumps(self.deep_dive_analysis(), ensure_ascii=False), encoding="utf-8")
            report.render_report(analysis_json=path, output_dir=root / "report", fact_pack=self.deep_dive_fact_pack())
            rendered = (root / "report" / "final-report.html").read_text(encoding="utf-8")

        self.assertIn('data-material-detail-tab="visual"', rendered)
        self.assertIn('tabindex="-1" data-material-detail-tab="timeline"', rendered)
        self.assertIn('data-deep-frame-select-all', rendered)
        self.assertIn('data-deep-frame-clear', rendered)
        self.assertIn('data-deep-frame-observation-empty', rendered)
        self.assertIn("var selectedRefs = new Set", rendered)
        self.assertIn("function renderObservations()", rendered)
        self.assertIn("function syncSelection()", rendered)
        self.assertIn("selectAll.disabled = selectedRefs.size === checkboxes.length", rendered)
        self.assertIn("selectNone.disabled = selectedRefs.size === 0", rendered)
        self.assertIn("caption.prepend(label)", rendered)
        self.assertIn("tab.addEventListener('keydown'", rendered)
        self.assertIn("tabs.length - 1", rendered)

    def test_render_report_rejects_invalid_material_deep_dive_frame_and_second(self):
        report = load_module()
        cases = (
            ("frame", "highlight:102:cover:0", "exactly once"),
            ("second", 9, "evidence_seconds"),
        )
        for kind, value, error in cases:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                analysis = self.deep_dive_analysis()
                if kind == "frame":
                    analysis["materialDeepDives"][0]["frame_observations"][1]["frame_ref"] = value
                else:
                    analysis["materialDeepDives"][0]["second_level_observations"][0]["evidence_seconds"] = [value]
                path = Path(directory) / "analysis.json"
                path.write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
                with self.assertRaisesRegex(report.YuntuReportError, error):
                    report.render_report(analysis_json=path, output_dir=Path(directory) / "report", fact_pack=self.deep_dive_fact_pack())

    def test_render_report_omits_ai_secondary_analysis_from_deep_dive(self):
        report = load_module()
        analysis = self.deep_dive_analysis()
        summary_fields = (
            "visual_summary", "data_summary", "audience_summary", "marketing_summary",
            "replication_advice", "risk_notes", "opening_judgment", "visual_rhythm",
            "peak_frame_reading", "second_level_reading", "audience_fit",
            "do_not_copy",
        )
        for dive in analysis["materialDeepDives"]:
            for field in summary_fields:
                del dive[field]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "analysis.json"
            path.write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
            report.render_report(
                analysis_json=path,
                output_dir=root / "report",
                fact_pack=self.deep_dive_fact_pack(),
            )
            rendered = (root / "report" / "final-report.html").read_text(encoding="utf-8")
        self.assertNotIn("AI 二次分析", rendered)
        self.assertNotIn("画面总结", rendered)

    def test_render_report_accepts_scene_and_text_overlay_highlight_groups(self):
        report = load_module()
        analysis = self.deep_dive_analysis()
        analysis["highlightDashboard"]["groups"] = [
            {
                "category": "scene",
                "frame_refs": ["highlight:101:cover:0"],
                "common_patterns": ["冰箱场景可见。"],
                "derivative_directions": [],
            },
            {
                "category": "text_overlay",
                "frame_refs": ["highlight:101:click_peak:2", "highlight:102:cover:0", "highlight:102:click_peak:2"],
                "common_patterns": ["画面含可见文字信息。"],
                "derivative_directions": [],
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "analysis.json"
            path.write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(
                report.render_report(
                    analysis_json=path,
                    output_dir=root / "report",
                    fact_pack=self.deep_dive_fact_pack(),
                ),
                0,
            )

    def test_render_report_renders_classified_highlight_frames(self):
        report = load_module()
        analysis = self.analysis_json()
        frame_refs = [
            f"highlight:101:click_peak:{second}" for second in range(1, 10)
        ]
        analysis["highlightDashboard"] = {
            "groups": [{
                "category": "portrait",
                "frame_refs": frame_refs,
                "common_patterns": ["人像主体稳定。"],
                "derivative_directions": [{
                    "title": "保留近景人物开场",
                    "body": "以人物近景作为第一视觉。",
                    "frame_refs": [frame_refs[0]],
                }],
            }]
        }
        fact_pack = {
            "selectedMaterials": [{"rank": 1, "material_id": "101"}],
            "materialFacts": [{
                "material_id": "101",
                "rank": 1,
                "title": "测试素材",
                "highlightFrames": [
                    {
                        "frame_ref": frame_ref,
                        "second": index,
                        "frame_type": "click_peak",
                        "peak_rank": index,
                        "click_value": 1 / index,
                        "available": True,
                        "relative_path": f"highlights/101/{index:02d}-{index:03d}s.jpg",
                    }
                    for index, frame_ref in enumerate(frame_refs, start=1)
                ],
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index in range(1, 10):
                source_frame = root / "highlights" / "101" / f"{index:02d}-{index:03d}s.jpg"
                source_frame.parent.mkdir(parents=True, exist_ok=True)
                source_frame.write_bytes(b"fake-jpg")
            analysis_path = root / "analysis.json"
            analysis_path.write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
            report.render_report(analysis_json=analysis_path, output_dir=root / "report", fact_pack=fact_pack)
            rendered = (root / "report" / "final-report.html").read_text(encoding="utf-8")
            data = json.loads((root / "report" / "final-report-data.json").read_text(encoding="utf-8"))
            copied_frame = (root / "report" / "assets" / "highlight-frames" / "101" / "01-001s.jpg").read_bytes()

        self.assertIn("人像画面", rendered)
        self.assertIn("保留近景人物开场", rendered)
        self.assertIn('role="tablist" aria-label="高光画面分类"', rendered)
        self.assertIn('data-highlight-category-tab', rendered)
        self.assertIn('role="tabpanel"', rendered)
        self.assertIn('class="highlight-frame-preview highlight-frame-button"', rendered)
        self.assertIn('data-highlight-frame-card', rendered)
        self.assertIn('data-highlight-pagination', rendered)
        self.assertIn('data-jump-material="101"', rendered)
        self.assertIn('src="assets/highlight-frames/101/01-001s.jpg"', rendered)
        self.assertEqual(copied_frame, b"fake-jpg")
        self.assertIn('aria-label="查看高光帧大图"', rendered)
        self.assertIn('data-highlight-page-size="12"', rendered)
        self.assertIn('data-highlight-frame-count="9"', rendered)
        self.assertIn('data-highlight-page-status', rendered)
        self.assertIn('共性洞察', rendered)
        self.assertIn('裂变方向', rendered)
        self.assertIn('class="highlight-frame-kind"', rendered)
        self.assertIn('class="highlight-frame-metric"', rendered)
        self.assertIn('class="highlight-material-title"', rendered)
        self.assertNotIn('每条素材保留封面画面', rendered)
        self.assertNotIn('查看素材：#', rendered)
        self.assertIn("1 / 1", rendered)
        highlight_header = '<header class="section-header highlight-section-header">'
        self.assertIn(highlight_header, rendered)
        highlight_header_start = rendered.index(highlight_header)
        highlight_header_end = rendered.index('</header>', highlight_header_start)
        export_toolbar_start = rendered.index('class="highlight-export-toolbar"')
        self.assertLess(highlight_header_start, export_toolbar_start)
        self.assertLess(export_toolbar_start, highlight_header_end)
        self.assertNotIn('class="highlight-export-toolbar"', rendered[highlight_header_end:])
        self.assertLess(
            rendered.index('class="highlight-analysis-pair"'),
            rendered.index('class="highlight-frame-grid"'),
        )
        self.assertGreaterEqual(rendered.count('data-highlight-collapse-toggle'), 1)
        self.assertIn('aria-expanded="true"', rendered)
        self.assertIn('data-collapsible-expanded-label="收起高光画面数据"', rendered)
        self.assertIn('data-collapsible-collapsed-label="展开高光画面数据"', rendered)
        self.assertIn('class="highlight-data-card raw-fact-card"', rendered)
        self.assertIn('data-highlight-cards-panel', rendered)
        self.assertLess(
            rendered.index('class="highlight-analysis-pair"'),
            rendered.index('class="highlight-data-card raw-fact-card"'),
        )
        self.assertLess(
            rendered.index('class="highlight-data-card raw-fact-card"'),
            rendered.index('data-highlight-collapse-toggle'),
        )
        self.assertLess(
            rendered.index('data-highlight-collapse-toggle'),
            rendered.index('data-highlight-cards-panel'),
        )
        self.assertRegex(rendered, r'aria-controls="[^"]*-cards-portrait"')
        self.assertLess(
            rendered.index('class="highlight-frame-grid"'),
            rendered.index('class="highlight-pagination"'),
        )
        self.assertIn("highlight:101:click_peak:1", data["highlightFrames"])

    def test_render_report_renders_brand_first_highlight_tabs(self):
        report = load_module()
        analysis = self.deep_dive_analysis()
        fact_pack = self.deep_dive_fact_pack()
        fact_pack["filters"] = {"brands": ["小仙炖", "五个女博士"]}
        fact_pack["materialFacts"][0]["title"] = "小仙炖测试素材"
        fact_pack["materialFacts"][1]["title"] = "五个女博士测试素材"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for material in fact_pack["materialFacts"]:
                for frame in material["highlightFrames"]:
                    source = root / frame["relative_path"]
                    source.parent.mkdir(parents=True, exist_ok=True)
                    source.write_bytes(b"fake-jpg")
            path = root / "analysis.json"
            path.write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
            report.render_report(analysis_json=path, output_dir=root / "report", fact_pack=fact_pack)
            rendered = (root / "report" / "final-report.html").read_text(encoding="utf-8")
        self.assertIn('aria-label="高光画面品牌分类"', rendered)
        self.assertIn("highlight-brand-tab-brand-u5c0f-u4ed9-u7096", rendered)
        self.assertIn("highlight-brand-tab-brand-u4e94-u4e2a-u5973-u535a-u58eb", rendered)
        self.assertIn('data-highlight-brand-tab', rendered)
        self.assertIn('data-highlight-brand-panel', rendered)
        self.assertIn('aria-label="高光画面分类"', rendered)

    def test_render_report_copies_highlight_assets_from_explicit_source_root(self):
        report = load_module()
        analysis = self.deep_dive_analysis()
        fact_pack = self.deep_dive_fact_pack()
        analysis["highlightDashboard"]["groups"][0]["frame_refs"] = [
            frame["frame_ref"]
            for fact in fact_pack["materialFacts"]
            for frame in fact["highlightFrames"]
        ]
        analysis["highlightDashboard"]["groups"][0]["derivative_directions"] = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_root = root / "source-batch"
            for fact in fact_pack["materialFacts"]:
                for frame in fact["highlightFrames"]:
                    source_frame = source_root / frame["relative_path"]
                    source_frame.parent.mkdir(parents=True, exist_ok=True)
                    source_frame.write_bytes(b"explicit-source-jpeg")
            analysis_path = root / "analysis.json"
            analysis_path.write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")

            report.render_report(
                analysis_json=analysis_path,
                output_dir=root / "separate-output" / "final-report",
                fact_pack=fact_pack,
                highlight_asset_root=source_root,
            )
            copied = (
                root / "separate-output" / "final-report" / "assets" / "highlight-frames"
                / "101" / "01-000s.jpg"
            ).read_bytes()

        self.assertEqual(copied, b"explicit-source-jpeg")

    def test_render_report_copies_highlight_assets_from_prior_report_in_source_root(self):
        report = load_module()
        analysis = self.deep_dive_analysis()
        fact_pack = self.deep_dive_fact_pack()
        analysis["highlightDashboard"]["groups"][0]["frame_refs"] = [
            frame["frame_ref"]
            for fact in fact_pack["materialFacts"]
            for frame in fact["highlightFrames"]
        ]
        analysis["highlightDashboard"]["groups"][0]["derivative_directions"] = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_root = root / "source-batch"
            source_frame = (
                source_root / "final-report" / "assets" / "highlight-frames" / "101"
                / "01-000s.jpg"
            )
            source_frame.parent.mkdir(parents=True, exist_ok=True)
            source_frame.write_bytes(b"prior-report-jpeg")
            analysis_path = root / "analysis.json"
            analysis_path.write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")

            report.render_report(
                analysis_json=analysis_path,
                output_dir=root / "separate-output" / "final-report",
                fact_pack=fact_pack,
                highlight_asset_root=source_root,
            )
            copied = (
                root / "separate-output" / "final-report" / "assets" / "highlight-frames"
                / "101" / "01-000s.jpg"
            ).read_bytes()

        self.assertEqual(copied, b"prior-report-jpeg")

    def test_render_report_classifies_cover_and_click_peak_frames_in_highlight_dashboard(self):
        report = load_module()
        analysis = self.deep_dive_analysis()
        analysis["highlightDashboard"]["groups"][0]["frame_refs"] = [
            "highlight:101:cover:0",
            "highlight:101:click_peak:2",
            "highlight:102:cover:0",
            "highlight:102:click_peak:2",
        ]
        analysis["highlightDashboard"]["groups"][0]["derivative_directions"] = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis_path = root / "analysis.json"
            analysis_path.write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
            for fact in self.deep_dive_fact_pack()["materialFacts"]:
                for frame in fact["highlightFrames"]:
                    source_frame = root / frame["relative_path"]
                    source_frame.parent.mkdir(parents=True, exist_ok=True)
                    source_frame.write_bytes(b"fake-jpeg")
            report.render_report(
                analysis_json=analysis_path,
                output_dir=root / "final-report",
                fact_pack=self.deep_dive_fact_pack(),
            )
            rendered = (root / "final-report" / "final-report.html").read_text(
                encoding="utf-8"
            )

        highlight_section = rendered.split('id="highlight-insights"', 1)[1].split(
            'id="material-deep-dive"', 1
        )[0]
        self.assertIn("点击 Top1 波峰画面", highlight_section)
        self.assertIn("封面画面", highlight_section)

    def test_render_report_uses_twelve_card_highlight_pages_and_peak_card_copy(self):
        report = load_module()
        analysis = self.analysis_json()
        frame_refs = [f"highlight:101:click_peak:{second}" for second in range(1, 14)]
        analysis["highlightDashboard"] = {
            "groups": [{
                "category": "portrait",
                "frame_refs": frame_refs,
                "common_patterns": ["人像主体稳定。"],
                "derivative_directions": [],
            }]
        }
        fact_pack = {
            "materialFacts": [{
                "material_id": "101",
                "rank": 1,
                "title": "完整素材名称.mp4",
                "highlightFrames": [
                    {
                        "frame_ref": frame_ref,
                        "second": index,
                        "frame_type": "click_peak",
                        "peak_rank": index,
                        "click_value": 20 - index,
                        "available": True,
                        "relative_path": f"highlights/101/{index:02d}-{index:03d}s.jpg",
                    }
                    for index, frame_ref in enumerate(frame_refs, start=1)
                ],
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index in range(1, 14):
                source_frame = root / "highlights" / "101" / f"{index:02d}-{index:03d}s.jpg"
                source_frame.parent.mkdir(parents=True, exist_ok=True)
                source_frame.write_bytes(b"fake-jpeg")
            analysis_path = root / "analysis.json"
            analysis_path.write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
            report.render_report(analysis_json=analysis_path, output_dir=root / "report", fact_pack=fact_pack)
            rendered = (root / "report" / "final-report.html").read_text(encoding="utf-8")

        self.assertIn('data-highlight-page-size="12"', rendered)
        self.assertIn('data-highlight-frame-count="13"', rendered)
        self.assertIn("1 / 2", rendered)
        self.assertIn("完整素材名称", rendered)
        self.assertNotIn("完整素材名称.mp4", rendered)
        self.assertIn("点击 Top1 波峰画面", rendered)
        self.assertIn("1s · 点击指数 19", rendered)

    def test_unified_report_uses_six_by_two_overview_grid_without_changing_deep_dive_grid(self):
        css = (ROOT / "assets" / "report" / "unified-report.css").read_text(
            encoding="utf-8"
        )

        self.assertIn("grid-template-columns: repeat(6, minmax(0, 1fr));", css)
        self.assertIn("grid-template-rows: repeat(2, minmax(0, 1fr));", css)
        report_source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn(".deep-frame-grid.fixed-six", report_source)
        self.assertIn("grid-template-columns:repeat(3,minmax(0,1fr))", report_source)

    def test_render_report_rejects_highlight_frames_classified_more_than_once(self):
        report = load_module()
        analysis = self.analysis_json()
        analysis.update(self.highlight_dashboard())
        analysis["highlightDashboard"]["groups"].append({
            "category": "other",
            "frame_refs": ["highlight:101:click_peak:2"],
            "common_patterns": ["其他画面。"],
            "derivative_directions": [],
        })
        fact_pack = {"materialFacts": [{"material_id": "101", "highlightFrames": [{
            "frame_ref": "highlight:101:click_peak:2", "second": 2, "frame_type": "click_peak",
            "available": True, "relative_path": "highlights/101/02-002s.jpg",
        }]}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "analysis.json"
            path.write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(report.YuntuReportError, "exactly once"):
                report.render_report(analysis_json=path, output_dir=Path(directory) / "report", fact_pack=fact_pack)

    def test_render_report_requires_dashboard_when_cover_frame_is_available(self):
        report = load_module()
        fact_pack = {"materialFacts": [{"material_id": "101", "highlightFrames": [{
            "frame_ref": "highlight:101:cover:0", "second": 0, "frame_type": "cover",
            "available": True, "relative_path": "highlights/101/01-000s.jpg",
        }]}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "analysis.json"
            path.write_text(json.dumps(self.analysis_json(), ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(report.YuntuReportError, "highlightDashboard is required"):
                report.render_report(
                    analysis_json=path,
                    output_dir=Path(directory) / "report",
                    fact_pack=fact_pack,
                )

    def test_current_schema_rejects_hidden_chapter01_residual_fields(self):
        report = load_module()
        analysis = self.analysis_json()
        analysis["topMaterialCombination"] = {
            "brandConclusions": analysis["topMaterialCombination"]["brandConclusions"],
            "brandComparisonConclusion": analysis["topMaterialCombination"]["brandComparisonConclusion"],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "analysis.json"
            path.write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(
                report.YuntuReportError,
                "must only include brandConclusions",
            ):
                report.render_report(
                    analysis_json=path,
                    output_dir=Path(directory) / "report",
                    fact_pack={"schemaVersion": 6},
                )

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
                "brands": ["品牌甲", "品牌乙"],
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
        self.assertIn("食品饮料行业｜品牌甲、品牌乙｜2026-07-26 至 2026-08-01", rendered)
        self.assertNotIn("好丽友、香飘飘", rendered)

    def test_render_report_keeps_evidence_in_json_without_rendering_it(self):
        report = load_module()
        analysis = self.analysis_json()
        evidence_sections = {
            "rankingOverview": analysis["rankingOverview"],
            "audienceInsights": analysis["audienceInsights"],
            "materialComparison": analysis["materialComparison"],
            "materialDiagnoses": analysis["materialDiagnoses"],
            "competitorPatterns": analysis["competitorPatterns"],
            "opportunityMap": analysis["opportunityMap"],
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
        self.assertIn('aria-label="各品牌榜单分析"', rendered)
        self.assertNotIn('aria-label="查看 101 封面 高光帧"', rendered)
        self.assertNotIn('aria-label="关闭高光帧预览"', rendered)

    def test_render_report_embeds_self_creating_unified_highlight_lightbox(self):
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
        self.assertIn("createUnifiedHighlightLightbox", rendered)
        self.assertIn("document.body.append(overlay)", rendered)

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

    def test_shared_style_defines_text_card_and_control_contract(self):
        css = (ROOT / "assets" / "report" / "unified-report.css").read_text(
            encoding="utf-8"
        )

        self.assertIn("--unified-text-card: #f7ead8;", css)
        self.assertIn(".yuntu-content-card", css)
        self.assertIn(".brand-tab", css)
        self.assertIn(".material-deep-tab", css)
        self.assertIn("background: var(--unified-text-card);", css)
        self.assertIn("width: min(1280px, calc(100% - 20px));", css)
        self.assertIn("grid-template-columns: 188px minmax(0, 1fr);", css)
        self.assertIn("gap: 18px;", css)
        self.assertIn(".unified-yuntu .audience-data-card", css)
        self.assertIn(".unified-yuntu .highlight-data-card", css)
        self.assertIn(".unified-yuntu .highlight-section-header", css)
        self.assertIn("padding: 18px;", css)
        self.assertIn("white-space: nowrap;", css)
        self.assertIn(".unified-yuntu .script-drill-layout", css)
        self.assertIn(".unified-yuntu .script-drill-primary", css)
        self.assertIn("grid-template-rows: auto 170px auto;", css)
        self.assertIn("min-height: 300px;", css)
        self.assertIn(".unified-yuntu .script-drill-detail {", css)
        self.assertIn("min-height: 0;", css)
        self.assertIn(".unified-yuntu .audience-drill-panel", css)
        self.assertIn("align-self: stretch;", css)
        self.assertIn("height: auto;", css)
        self.assertIn(".unified-yuntu .audience-drill-panel .preference-list", css)
        self.assertIn(".unified-yuntu .audience-drill-panel .material-link", css)
        self.assertIn("font-size: 14px;", css)
        self.assertIn(".unified-yuntu .audience-drill-panel .preference-exposure", css)
        self.assertIn('grid-template-areas:\n    "rank exposure"\n    "title title";', css)
        self.assertIn(".unified-yuntu .audience-chart-crowd .audience-column-chart", css)
        self.assertIn("min-height: var(--chapter02-column-container-height);", css)
        self.assertIn("height: var(--chapter02-column-plot-height);", css)
        self.assertIn(".unified-yuntu .brand-tab[aria-selected=\"true\"]::after", css)
        self.assertIn(".unified-yuntu .audience-chart-gender .pie-legend", css)
        self.assertIn("margin-block: auto;", css)
        self.assertIn("grid-template-columns: repeat(6, minmax(0, 1fr));", css)
        self.assertIn("grid-template-rows: repeat(2, minmax(0, 1fr));", css)
        self.assertIn("min-height: var(--highlight-grid-height);", css)
        self.assertIn("aspect-ratio: 9 / 16;", css)
        self.assertIn("object-fit: contain;", css)
        self.assertIn(".script-drill-detail.is-entering", css)
        self.assertIn(".script-drill-moving-bar", css)
        self.assertIn(".highlight-frame-card[hidden]", css)
        self.assertIn(".second-level-section {", css)
        self.assertIn("border-top: 0;", css)
        self.assertIn("padding-top: 0;", css)

    def test_shared_style_keeps_audience_drill_height_and_compacts_pies(self):
        css = (ROOT / "assets" / "report" / "unified-report.css").read_text(
            encoding="utf-8"
        )

        self.assertIn("--chapter02-audience-card-height: 420px;", css)
        self.assertIn("--chapter02-audience-drill-height: 300px;", css)
        self.assertIn(".unified-yuntu .audience-chart-crowd .script-drill-detail", css)
        self.assertIn(".unified-yuntu .audience-chart-age,", css)
        self.assertIn("min-height: var(--chapter02-audience-card-height);", css)
        self.assertIn(".unified-yuntu .audience-chart-crowd .script-drill-detail", css)
        self.assertIn("min-height: var(--chapter02-audience-drill-height);", css)
        self.assertIn(".unified-yuntu .audience-chart-age .pie-chart", css)
        self.assertIn("width: min(var(--chapter02-audience-pie-size), 100%) !important;", css)
        self.assertIn("gap: 6px 10px;", css)
        self.assertIn("padding: 2px 0;", css)
        self.assertIn(".unified-yuntu .marketing-drill-primary {", css)
        self.assertIn("align-content:center;", css)
        self.assertIn(".unified-yuntu .marketing-drill-primary-plot {", css)
        self.assertIn("justify-content: center;", css)
        self.assertIn("--chapter02-audience-crowd-height: 232px;", css)
        self.assertIn("--chapter02-audience-crowd-drill-height: 260px;", css)
        self.assertIn(".unified-yuntu .audience-chart-crowd .script-dashboard-overview", css)
        self.assertIn("min-height: var(--chapter02-audience-crowd-height);", css)
        self.assertIn("min-height: var(--chapter02-audience-crowd-drill-height);", css)
        self.assertIn("background: #fff;", css)
        self.assertIn("color: #5e3820;", css)
        self.assertIn("align-self: flex-start;", css)
        self.assertIn("justify-content: flex-start;", css)

    def test_unified_report_mobile_navigation_does_not_force_page_overflow(self):
        css = (ROOT / "assets" / "report" / "unified-report.css").read_text(
            encoding="utf-8"
        )

        self.assertIn("@media (max-width: 760px)", css)
        self.assertIn(".unified-report .report-nav", css)
        self.assertIn("flex-wrap: wrap;", css)
        self.assertIn(".unified-report .report-nav a", css)
        self.assertIn("white-space: normal;", css)
        self.assertIn("@media (max-width: 720px)", css)
        self.assertIn(".unified-yuntu .material-deep-layout.side-tabs", css)
        self.assertIn("grid-template-columns: 1fr;", css)

    def test_render_report_omits_highlight_category_heading(self):
        report = load_module()
        analysis = self.deep_dive_analysis()
        fact_pack = self.deep_dive_fact_pack()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis_path = root / "analysis.json"
            analysis_path.write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
            for fact in fact_pack["materialFacts"]:
                for frame in fact["highlightFrames"]:
                    source_frame = root / frame["relative_path"]
                    source_frame.parent.mkdir(parents=True, exist_ok=True)
                    source_frame.write_bytes(b"fake-jpeg")
            report.render_report(
                analysis_json=analysis_path,
                output_dir=root / "final-report",
                fact_pack=fact_pack,
            )
            rendered = (root / "final-report" / "final-report.html").read_text(encoding="utf-8")

        self.assertNotIn('class="highlight-category-head"', rendered)
        self.assertNotIn('class="highlight-category-count"', rendered)

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
