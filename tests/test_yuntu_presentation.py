import copy
import json
import math
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from yuntu_presentation import (  # noqa: E402
    YuntuPresentationError,
    build_yuntu_presentation,
    validate_yuntu_presentation,
)


class YuntuPresentationTests(unittest.TestCase):
    def _metric(self, name, value):
        return {
            "trend_name": name,
            "available": True,
            "missing_reason": "",
            "points": [{"second": 0, "value": value}, {"second": 2, "value": value + 1}],
            "high_points": [{"start_sec": 2, "end_sec": 2}],
            "loss_points": [],
        }

    def fact_pack(self):
        material_facts = []
        for rank, material_id in enumerate(("101", "102"), start=1):
            material_facts.append({
                "material_id": material_id,
                "rank": rank,
                "title": f"测试素材 {material_id}",
                "metrics": {"show_cnt": 1000 * rank, "ctr": 0.1 * rank},
                "people_tags": ["都市女性"],
                "material_tags": ["营养补给"],
                "highlightFrames": [
                    {
                        "frame_ref": f"highlight:{material_id}:cover:0",
                        "second": 0,
                        "frame_type": "cover",
                        "available": True,
                        "relative_path": f"highlights/{material_id}/01-000s.jpg",
                    },
                    {
                        "frame_ref": f"highlight:{material_id}:click_peak:2",
                        "second": 2,
                        "frame_type": "click_peak",
                        "peak_rank": 1,
                        "click_value": 0.8,
                        "available": True,
                        "relative_path": f"highlights/{material_id}/02-002s.jpg",
                    },
                ],
                "secondLevelBreakdown": {
                    "metrics": [
                        self._metric(name, index)
                        for index, name in enumerate(
                            ("点赞指数", "流失指数", "点击指数", "互动指数", "评论指数")
                        )
                    ]
                },
            })
        chapter02_facts = {
            "scopeOrder": ["all", "WONDERLAB/万益蓝"],
            "all": {
                "label": "全量 TOP1000",
                "topMaterials": [{"material_id": "101", "rank": 1, "people_tags": ["都市女性"]}],
                "audienceDashboard": {"dimensions": {"age": {"buckets": [{"label": "24-30", "materialCount": 2, "chartShare": 1.0}]}}},
                "marketingDashboard": {"categories": [{"category": "功效", "tagCount": 2, "occurrenceCount": 3, "tags": [{"tag": "营养补给", "count": 2}, {"tag": "日常养护", "count": 1}], "topTags": [{"tag": "营养补给", "count": 2}]}]},
            },
            "WONDERLAB/万益蓝": {
                "label": "WONDERLAB/万益蓝",
                "topMaterials": [{"material_id": "102", "rank": 2, "people_tags": ["都市女性"]}],
                "audienceDashboard": {"dimensions": {"age": {"buckets": [{"label": "24-30", "materialCount": 1, "chartShare": 1.0}]}}},
                "marketingDashboard": {"categories": [{"category": "功效", "tagCount": 1, "occurrenceCount": 2, "tags": [{"tag": "营养补给", "count": 2}], "topTags": [{"tag": "营养补给", "count": 2}]}]},
            },
        }
        chapter02_ai_facts = copy.deepcopy(chapter02_facts)
        chapter02_ai_facts["WONDERLAB/万益蓝"]["marketingDashboard"]["categories"][0]["occurrenceCount"] = 1
        return {
            "schemaVersion": 6,
            "filters": {"brands": ["WONDERLAB/万益蓝"], "startDate": "2026-07-30", "endDate": "2026-08-05"},
            "selectedMaterials": [{"material_id": "101", "rank": 1}, {"material_id": "102", "rank": 2}],
            "materialFacts": material_facts,
            "chapter02Facts": chapter02_facts,
            "chapter02AiFacts": chapter02_ai_facts,
            "brandRankingFacts": {"source_scope": "brand_in_top1000"},
        }

    def analysis(self):
        refs = [
            f"highlight:{material_id}:{frame_kind}"
            for material_id in ("101", "102")
            for frame_kind in ("cover:0", "click_peak:2")
        ]
        return {
            "chapter02Insights": {
                "scopeOrder": ["all", "WONDERLAB/万益蓝"],
                "scopes": {
                    "all": {"audienceInsights": [{"summary": "全量人群洞察", "evidence": [{"tag": "都市女性"}], "material_ids": ["101"]}], "marketingInsights": [{"summary": "全量卖点洞察", "evidence": [{"tag": "营养补给"}], "material_ids": ["101"]}]},
                    "WONDERLAB/万益蓝": {"audienceInsights": [{"summary": "品牌人群洞察", "evidence": [{"tag": "都市女性"}], "material_ids": ["101"]}], "marketingInsights": [{"summary": "品牌卖点洞察", "evidence": [{"tag": "营养补给"}], "material_ids": ["101"]}]},
                },
            },
            "highlightDashboard": {
                "groups": [{
                    "category": "portrait",
                    "frame_refs": refs,
                    "common_patterns": ["人物或产品主体清晰。"],
                    "derivative_directions": [{"title": "保持主体清晰", "body": "验证主体前置是否提升理解效率。", "frame_refs": refs}],
                }]
            },
            "materialDeepDives": [
                {
                    "material_id": material_id,
                    "frame_observations": [{"frame_ref": f"highlight:{material_id}:{frame_kind}", "observation": "画面主体明确。"} for frame_kind in ("cover:0", "click_peak:2")],
                    "second_level_observations": [{"trend_name": name, "summary": "指数在真实秒点出现波动。", "evidence_seconds": [2]} for name in ("点赞指数", "流失指数", "点击指数", "互动指数", "评论指数")],
                }
                for material_id in ("101", "102")
            ],
        }

    def test_builds_a_versioned_json_serializable_projection(self):
        analysis = self.analysis()
        facts = self.fact_pack()
        before = json.dumps({"analysis": analysis, "facts": facts}, ensure_ascii=False, sort_keys=True)

        payload = build_yuntu_presentation(analysis, facts)

        self.assertEqual(payload["presentationSchemaVersion"], 3)
        self.assertEqual(payload["report"]["sections"], ["chapter01", "chapter02", "chapter04", "chapter05"])
        self.assertIs(payload, validate_yuntu_presentation(payload))
        json.dumps(payload, ensure_ascii=False)
        self.assertEqual(before, json.dumps({"analysis": analysis, "facts": facts}, ensure_ascii=False, sort_keys=True))

    def test_chapter05_uses_single_panel_source_without_frame_copy_fields(self):
        payload = build_yuntu_presentation(self.analysis(), self.fact_pack())
        chapter = payload["chapters"]["chapter05"]

        self.assertNotIn("materials", payload)
        self.assertEqual(
            chapter["materialTabs"],
            payload["interactions"]["chapter05-material-tabs"]["items"],
        )
        frame = chapter["panels"][0]["frames"][0]
        self.assertNotIn("materialId", frame)
        self.assertNotIn("rank", frame)
        self.assertNotIn("title", frame)
        self.assertNotIn("caption", frame)

    def test_chapter02_preserves_the_ai_and_chart_dual_scope_contract(self):
        payload = build_yuntu_presentation(self.analysis(), self.fact_pack())
        scopes = {scope["id"]: scope for scope in payload["scopes"]}
        panels = payload["chapters"]["chapter02"]["panels"]
        brand_scope = next(scope for scope in scopes.values() if scope["label"] == "WONDERLAB/万益蓝")

        self.assertEqual(scopes["all"]["rankScope"], "top1000")
        self.assertEqual(brand_scope["rankScope"], "all-materials")
        self.assertNotIn("topN", brand_scope)
        self.assertEqual(panels[1]["aiFactSource"], "chapter02AiFacts")
        self.assertEqual(panels[1]["chartFactSource"], "chapter02Facts")
        self.assertNotIn("topNControl", panels[1])
        self.assertIn("audienceSummary", panels[1]["aiInsights"])
        self.assertIn("marketingSummary", panels[1]["aiInsights"])
        self.assertEqual(set(panels[1]["aiInsights"]), {"audienceSummary", "marketingSummary"})
        self.assertEqual(panels[1]["charts"][0]["buckets"][0]["value"], 2)
        self.assertEqual(panels[1]["topMaterials"][0]["material_id"], "102")

    def test_projects_chapter01_top_material_conclusions(self):
        analysis = self.analysis()
        analysis["topMaterialCombination"] = {
            "brandConclusions": [{"brand": "WONDERLAB/万益蓝", "classificationSource": "runtime_title_rule", "dataSummary": "品牌全量素材的累计曝光、CTR、CVR 与 3 秒播放率呈现稳定。", "evidence": [{"material_id": "101"}]}],
        }

        payload = build_yuntu_presentation(analysis, self.fact_pack())

        chapter = payload["chapters"]["chapter01"]
        self.assertEqual(payload["presentationSchemaVersion"], 3)
        self.assertEqual(payload["report"]["sections"], ["chapter01", "chapter02", "chapter04", "chapter05"])
        self.assertNotIn("executiveInsight", chapter)
        self.assertNotIn("overallInsights", chapter)
        self.assertNotIn("brandComparisonInsight", chapter)
        self.assertEqual(set(chapter), {"brandTabs", "brandPanels"})
        self.assertEqual(chapter["brandPanels"][0]["brand"], "WONDERLAB/万益蓝")
        self.assertNotIn("topN", chapter["brandPanels"][0])
        self.assertEqual(set(chapter["brandPanels"][0]), {"id", "brand", "insights"})
        self.assertEqual(
            set(chapter["brandPanels"][0]["insights"][0]), {"text", "dimension"}
        )
        self.assertEqual(
            [item["dimension"] for item in chapter["brandPanels"][0]["insights"]],
            ["data"],
        )
        brand_tabs = payload["interactions"]["chapter01-brand-tabs"]
        self.assertEqual(brand_tabs["items"], chapter["brandTabs"])
        self.assertEqual(brand_tabs["defaultItemId"], chapter["brandTabs"][0]["id"])
        self.assertEqual(brand_tabs["keyboard"], ["ArrowLeft", "ArrowRight", "Home", "End"])

    def test_brand_scope_ids_remain_unique_for_chinese_brand_names(self):
        facts = self.fact_pack()
        facts["chapter02Facts"]["scopeOrder"] = ["all", "五个女博士", "燕之屋"]
        facts["chapter02AiFacts"]["scopeOrder"] = ["all", "五个女博士", "燕之屋"]
        for key in ("五个女博士", "燕之屋"):
            facts["chapter02Facts"][key] = copy.deepcopy(facts["chapter02Facts"]["WONDERLAB/万益蓝"])
            facts["chapter02AiFacts"][key] = copy.deepcopy(facts["chapter02AiFacts"]["WONDERLAB/万益蓝"])
        analysis = self.analysis()
        analysis["chapter02Insights"]["scopeOrder"] = ["all", "五个女博士", "燕之屋"]
        analysis["chapter02Insights"]["scopes"]["五个女博士"] = analysis["chapter02Insights"]["scopes"].pop("WONDERLAB/万益蓝")
        analysis["chapter02Insights"]["scopes"]["燕之屋"] = copy.deepcopy(analysis["chapter02Insights"]["scopes"]["五个女博士"])

        payload = build_yuntu_presentation(analysis, facts)

        ids = [scope["id"] for scope in payload["scopes"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_rejects_chapter02_scope_order_mismatch(self):
        facts = self.fact_pack()
        facts["chapter02AiFacts"]["scopeOrder"] = ["all"]

        with self.assertRaisesRegex(YuntuPresentationError, "scope order"):
            build_yuntu_presentation(self.analysis(), facts)

    def test_projects_each_available_highlight_frame_once(self):
        payload = build_yuntu_presentation(self.analysis(), self.fact_pack())
        chapter04 = payload["chapters"]["chapter04"]
        self.assertNotIn("categories", chapter04)
        categories = chapter04["brands"][0]["categories"]
        refs = [frame["frameRef"] for category in categories for frame in category["frames"]]

        self.assertEqual(len(refs), 4)
        self.assertEqual(len(refs), len(set(refs)))
        self.assertTrue(all(frame["relativePath"].startswith("highlights/") for category in categories for frame in category["frames"]))

    def test_projects_brand_first_highlight_categories_from_title(self):
        facts = self.fact_pack()
        facts["filters"]["brands"] = ["小仙炖", "五个女博士"]
        facts["materialFacts"][0]["title"] = "小仙炖测试素材 101"
        facts["materialFacts"][1]["title"] = "五个女博士测试素材 102"
        payload = build_yuntu_presentation(self.analysis(), facts)
        brands = payload["chapters"]["chapter04"]["brands"]
        self.assertEqual([item["brand"] for item in brands], ["全品牌", "小仙炖", "五个女博士"])
        refs = [frame["frameRef"] for category in brands[1]["categories"] for frame in category["frames"]]
        self.assertEqual(set(refs), {"highlight:101:cover:0", "highlight:101:click_peak:2"})
        self.assertTrue(all(frame["brand"] == "小仙炖" for category in brands[1]["categories"] for frame in category["frames"]))

    def test_projects_brand_scoped_highlight_insights_without_copying(self):
        facts = self.fact_pack()
        facts["filters"]["brands"] = ["小仙炖", "五个女博士"]
        facts["materialFacts"][0]["title"] = "小仙炖测试素材 101"
        facts["materialFacts"][1]["title"] = "五个女博士测试素材 102"
        analysis = self.analysis()
        analysis["highlightDashboard"] = {
            "brands": [
                {
                    "brand": "全品牌",
                    "groups": [{
                        "category": "portrait",
                        "frame_refs": [
                            "highlight:101:cover:0", "highlight:101:click_peak:2",
                            "highlight:102:cover:0", "highlight:102:click_peak:2",
                        ],
                        "common_patterns": [{"title": "全品牌主体", "body": "全品牌主体清晰。", "frame_refs": [
                            "highlight:101:cover:0", "highlight:101:click_peak:2",
                            "highlight:102:cover:0", "highlight:102:click_peak:2",
                        ]}],
                        "derivative_directions": [{"title": "全品牌方向", "body": "全品牌验证主体前置。", "frame_refs": ["highlight:101:cover:0"]}],
                    }],
                },
                {
                    "brand": "小仙炖",
                    "groups": [{
                        "category": "portrait",
                        "frame_refs": ["highlight:101:cover:0", "highlight:101:click_peak:2"],
                        "common_patterns": [{"title": "小仙炖主体", "body": "小仙炖主体清晰。", "frame_refs": ["highlight:101:cover:0", "highlight:101:click_peak:2"]}],
                        "derivative_directions": [{"title": "小仙炖方向", "body": "小仙炖验证人物开场。", "frame_refs": ["highlight:101:cover:0"]}],
                    }],
                },
                {
                    "brand": "五个女博士",
                    "groups": [{
                        "category": "portrait",
                        "frame_refs": ["highlight:102:cover:0", "highlight:102:click_peak:2"],
                        "common_patterns": [{"title": "五个女博士主体", "body": "五个女博士主体清晰。", "frame_refs": ["highlight:102:cover:0", "highlight:102:click_peak:2"]}],
                        "derivative_directions": [{"title": "五个女博士方向", "body": "五个女博士验证产品衔接。", "frame_refs": ["highlight:102:cover:0"]}],
                    }],
                },
            ]
        }

        payload = build_yuntu_presentation(analysis, facts)
        brands = payload["chapters"]["chapter04"]["brands"]
        self.assertEqual([item["brand"] for item in brands[:3]], ["全品牌", "小仙炖", "五个女博士"])
        self.assertEqual(brands[1]["categories"][0]["commonConclusion"][0]["title"], "小仙炖主体")
        self.assertEqual(brands[2]["categories"][0]["commonConclusion"][0]["title"], "五个女博士主体")

    def test_rejects_duplicate_highlight_frame_reference(self):
        analysis = self.analysis()
        analysis["highlightDashboard"]["groups"].append({
            "category": "other",
            "frame_refs": ["highlight:101:cover:0"],
            "common_patterns": ["重复帧。"],
            "derivative_directions": [],
        })

        with self.assertRaisesRegex(YuntuPresentationError, "highlight frame coverage"):
            build_yuntu_presentation(analysis, self.fact_pack())

    def test_projects_fixed_second_level_metrics_and_real_seconds(self):
        payload = build_yuntu_presentation(self.analysis(), self.fact_pack())
        panel = payload["chapters"]["chapter05"]["panels"][0]

        self.assertEqual(panel["secondLevel"]["metricOrder"], ["点赞指数", "流失指数", "点击指数", "互动指数", "评论指数"])
        self.assertEqual(panel["secondLevel"]["metrics"][0]["points"][1]["second"], 2)
        self.assertEqual(panel["availability"]["status"], "complete")

    def test_rejects_unavailable_trend_without_reason(self):
        facts = self.fact_pack()
        facts["materialFacts"][0]["secondLevelBreakdown"]["metrics"][0] = {
            "trend_name": "点赞指数", "available": False, "missing_reason": "", "points": []
        }

        with self.assertRaisesRegex(YuntuPresentationError, "missing reason"):
            build_yuntu_presentation(self.analysis(), facts)

    def test_rejects_frame_path_that_escapes_the_report_assets(self):
        facts = self.fact_pack()
        facts["materialFacts"][0]["highlightFrames"][0]["relative_path"] = "../outside.jpg"

        with self.assertRaisesRegex(YuntuPresentationError, "relative frame path"):
            build_yuntu_presentation(self.analysis(), facts)

    def test_rejects_non_finite_chart_bucket_value(self):
        facts = self.fact_pack()
        facts["chapter02Facts"]["all"]["marketingDashboard"]["categories"][0]["occurrenceCount"] = math.nan

        with self.assertRaisesRegex(YuntuPresentationError, "chart value"):
            build_yuntu_presentation(self.analysis(), facts)


if __name__ == "__main__":
    unittest.main()
