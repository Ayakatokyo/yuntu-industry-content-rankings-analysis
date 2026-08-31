import inspect
import sys
import unittest
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import yuntu_analysis
import yuntu_report
import yuntu_report_sections


class Chapter01CleanupTests(unittest.TestCase):
    def test_hot_material_cards_render_material_id_with_detail(self):
        presentation = {
            "brandPanels": [{
                "brand": "全品牌",
                "insights": [{"dimension": "data", "text": "榜单结论"}],
                "aiAnalysis": {"summary": "统一结论"},
                "comparison": {"summary": "比较结论"},
                "hotMaterialPanel": {
                    "thresholdExposureMin": 200000,
                    "qualifyingCount": 1,
                    "available": True,
                    "materials": [{
                        "material_id": "101",
                        "title": "测试素材 101",
                        "exposure": {"min": 200000, "max": 220000, "raw": "20万-22万"},
                        "metrics": {
                            "show_cnt": 2686377,
                            "ctr": 0.1,
                            "cvr": 0.2,
                            "play_3s_rate": 0.3,
                        },
                    }],
                },
            }]
        }

        rendered = yuntu_report_sections.render_top_material_combination(
            {"brandConclusions": []},
            esc=lambda value: escape(str(value)),
            generic_text=lambda value: value or "",
            brand_order=["全品牌"],
            presentation=presentation,
            jump_material_ids={"101"},
        )

        self.assertIn("测试素材 101", rendered)
        self.assertIn("素材 ID：101", rendered)
        self.assertIn("data-jump-material=\"101\"", rendered)
        self.assertIn("曝光量", rendered)
        self.assertIn("CTR", rendered)
        self.assertIn("CVR", rendered)
        self.assertIn("3 秒播放率", rendered)
        self.assertIn("收起爆款素材汇总数据", rendered)
        self.assertIn("data-collapsible-toggle", rendered)
        self.assertIn("hot-material-scroll", rendered)
        self.assertNotIn("AI二次分析", rendered)
        self.assertNotIn("chapter01-ai-analysis", rendered)
        self.assertNotIn("show_cnt", rendered)
        self.assertNotIn("play_3s_rate", rendered)

    def test_hot_material_panel_layout_contract(self):
        presentation = {
            "brandPanels": [{
                "brand": "全品牌",
                "hotMaterialPanel": {
                    "thresholdExposureMin": 200000,
                    "qualifyingCount": 0,
                    "available": True,
                    "materials": [],
                },
            }]
        }

        rendered = yuntu_report_sections.render_top_material_combination(
            {"brandConclusions": []},
            esc=lambda value: escape(str(value)),
            generic_text=lambda value: value or "",
            brand_order=["全品牌"],
            presentation=presentation,
        )
        style = (ROOT / "assets/report/unified-report.css").read_text(encoding="utf-8")

        self.assertLess(
            rendered.index("hot-material-toggle"),
            rendered.index("<h4>爆款素材面板</h4>"),
        )
        self.assertIn("color: #000", style)
        self.assertIn("width: 100%", style)
        self.assertIn("height: 180px", style)
        self.assertIn("grid-auto-rows: 180px", style)
        self.assertIn("scrollbar-color: #999 transparent", style)
        self.assertIn(".hot-material-scroll::-webkit-scrollbar-thumb", style)
        self.assertIn("font-size: 0.92rem", style)
        self.assertIn("font-size: 0.8rem", style)

    def test_first_chapter_label_contract_has_no_people_or_marketing_dimensions(self):
        self.assertFalse(hasattr(yuntu_report, "TOP_MATERIAL_LABELS"))

    def test_first_chapter_renderer_has_no_top_n_parameters(self):
        params = inspect.signature(
            yuntu_report_sections.render_top_material_combination
        ).parameters
        self.assertNotIn("brand_top_n", params)
        self.assertNotIn("brand_scope_label", params)
        self.assertFalse(hasattr(yuntu_report, "_requested_brand_top_n"))
        self.assertFalse(hasattr(yuntu_report, "_brand_scope_label"))

    def test_first_chapter_prompt_has_no_legacy_people_or_top_n_rules(self):
        prompt = yuntu_analysis._prompt_text(filters={"brands": ["小仙炖"]})
        first_chapter = prompt.split("02 章必须读取", 1)[0]
        self.assertNotIn("peopleSummary", first_chapter)
        self.assertNotIn("audienceFacts", first_chapter)
        self.assertNotIn("Top N", first_chapter)
        self.assertNotIn("用户输入的 Top N", prompt)
        self.assertNotIn("TopN 控件", prompt)

    def test_brand_ranking_facts_use_new_name_with_legacy_read_fallback(self):
        self.assertEqual(
            yuntu_report._brand_ranking_facts({"brandRankingFacts": {"source_scope": "new"}}),
            {"source_scope": "new"},
        )
        self.assertEqual(
            yuntu_report._brand_ranking_facts({"brandTopNFacts": {"source_scope": "legacy"}}),
            {"source_scope": "legacy"},
        )


if __name__ == "__main__":
    unittest.main()
