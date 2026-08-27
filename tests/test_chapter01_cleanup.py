import inspect
import unittest

import yuntu_analysis
import yuntu_report
import yuntu_report_sections


class Chapter01CleanupTests(unittest.TestCase):
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
