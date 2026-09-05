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
                "exposure": {"min": 200000, "max": 220000, "raw": "20万-22万"},
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

    def dual_highlight_analysis(self):
        analysis = self.analysis()
        refs = [
            f"highlight:{material_id}:{frame_kind}"
            for material_id in ("101", "102")
            for frame_kind in ("cover:0", "click_peak:2")
        ]
        common = [{
            "title": "主体与构图",
            "body": "同批次画面主体与构图均可观察。",
            "frame_refs": refs,
        }]
        directions = [{
            "title": "验证主体协同",
            "body": "改写动作是调整主体顺序，变体方式是比较人物先出场与产品先出场，验证指标为短时播放率。",
            "frame_refs": refs,
        }]
        standard = {
            "category": "portrait",
            "frame_refs": refs,
            "common_patterns": common,
            "derivative_directions": directions,
        }
        batch = {
            "category": "主体协同",
            "label": "主体协同",
            "rule": "人物与产品共同构成视觉焦点。",
            "frame_refs": refs,
            "common_patterns": common,
            "derivative_directions": directions,
        }
        analysis["highlightDashboard"] = {
            "frameUnderstanding": [
                {
                    "frame_ref": ref,
                    "status": "complete",
                    "subject": "主体",
                    "visual_focus": "中心",
                    "human_product_relation": "同框",
                    "action": "展示",
                    "composition": "居中",
                    "information_expression": "字幕可见",
                    "failure_reason": "",
                }
                for ref in refs
            ],
            "standardClassification": {"status": "complete", "missing_reason": "", "groups": [standard]},
            "batchClassification": {
                "status": "complete",
                "missing_reason": "",
                "rule": "按主体协同关系分组。",
                "groups": [batch],
            },
            "groups": [standard],
        }
        return analysis

    def test_projects_standard_and_batch_classification_modes_for_supported_brand(self):
        facts = self.fact_pack()
        facts["filters"]["brands"] = ["WONDERLAB/万益蓝"]
        facts["materialFacts"][0]["title"] = "WONDERLAB/万益蓝 测试素材 101"
        facts["materialFacts"][1]["title"] = "WONDERLAB/万益蓝 测试素材 102"

        payload = build_yuntu_presentation(self.dual_highlight_analysis(), facts)

        chapter04 = payload["chapters"]["chapter04"]
        for brand in chapter04["brands"]:
            self.assertEqual(
                [mode["id"] for mode in brand["classificationModes"]],
                ["standard", "batch"],
            )
        self.assertEqual(chapter04["defaultClassificationMode"], "standard")
        self.assertEqual(chapter04["brands"][0]["classificationModes"][0]["categories"][0]["label"], "portrait")
        self.assertEqual(chapter04["brands"][0]["classificationModes"][1]["categories"][0]["label"], "主体协同")

    def test_chapter05_panel_projects_script_analysis_and_evidence(self):
        facts = self.fact_pack()
        facts["materialFacts"][0].update({
            "script": {
                "text": "早餐可以不碰碳水，但鲜炖燕窝一定要坚持吃。",
                "labels": [{
                    "level1": "商品卖点",
                    "level2": "成分配方原料",
                    "evidenceRef": "script:101:商品卖点:成分配方原料",
                }],
                "formula": [{"level1": "商品卖点", "level2": "成分配方原料"}],
                "evidence": [{
                    "level2": "成分配方原料",
                    "sentence": "鲜炖燕窝一定要坚持吃。",
                    "evidenceRef": "script:101:text:鲜炖燕窝",
                }],
                "availability": {"text": {"available": True}, "formula": {"available": True}, "evidence": {"available": True}},
            },
            "content_formula": {
                "labels": [{"level_1_label": 9, "level_2_labels": [42]}],
                "detail.42": "鲜炖燕窝",
                "视频标题.text": "早餐可以不碰碳水，但鲜炖燕窝一定要坚持吃。",
                "视频画面.text": "画面字幕：鲜炖燕窝，每天一瓶。",
            },
            "evidenceIndex": {"script": [
                "script:101:商品卖点:成分配方原料",
                "script:101:text:鲜炖燕窝",
            ]},
        })
        analysis = self.analysis()
        analysis["materialDeepDives"][0]["scriptAnalysis"] = {
            "conclusion": "该素材先用早餐场景建立日常代入，再以鲜炖燕窝和坚持食用承接品质价值，表达生活化且利益点明确，适合保留具体场景与产品价值的结构；下一轮可测试场景前置和卖点前置两种改写方向，并继续核对原文证据。",
            "evidenceRefs": ["script:101:商品卖点:品质功效", "script:101:text:鲜炖燕窝"],
            "availability": "available",
        }

        payload = build_yuntu_presentation(analysis, facts)
        panel = payload["chapters"]["chapter05"]["panels"][0]
        self.assertEqual(panel["script"]["text"], "早餐可以不碰碳水，但鲜炖燕窝一定要坚持吃。")
        self.assertEqual(panel["script"]["formula"][0]["level1"], "商品卖点")
        self.assertEqual(panel["videoTitleText"], "早餐可以不碰碳水，但鲜炖燕窝一定要坚持吃。")
        self.assertEqual(panel["videoFrameText"], "画面字幕：鲜炖燕窝，每天一瓶。")
        self.assertNotIn("analysis", panel["script"])
        self.assertIn("script:101:video_title:鲜炖燕窝", panel["script"]["evidenceRefs"])
        self.assertIn("script:101:video_frame:鲜炖燕窝", panel["script"]["evidenceRefs"])

    def test_chapter05_script_evidence_matches_each_formula_term(self):
        facts = self.fact_pack()
        facts["materialFacts"][0].update({
            "script_text": "饭后喝益生菌，送礼也选益生菌。",
            "content_formula": {
                "labels": [
                    {"level_1_label": 9, "level_2_labels": [42]},
                    {"level_1_label": 15, "level_2_labels": [87]},
                ],
                "detail.42": "益生菌",
                "detail.87": "饭后、送礼",
            },
        })

        panel = build_yuntu_presentation(self.analysis(), facts)["chapters"]["chapter05"]["panels"][0]
        evidence = panel["script"]["evidence"]
        by_formula = {}
        for item in evidence:
            by_formula.setdefault(item["formulaIndex"], set()).add(item["sentence"])

        self.assertEqual(by_formula[0], {"益生菌"})
        self.assertEqual(by_formula[1], {"饭后", "送礼"})

    def test_projects_modes_for_combined_joyoung_brand_alias(self):
        facts = self.fact_pack()
        brand = "Joyoung soymilk/九阳豆浆"
        facts["filters"]["brands"] = [brand]
        facts["materialFacts"][0]["title"] = f"{brand} 测试素材 101"
        facts["materialFacts"][1]["title"] = f"{brand} 测试素材 102"

        payload = build_yuntu_presentation(self.dual_highlight_analysis(), facts)

        projected_brand = next(
            item for item in payload["chapters"]["chapter04"]["brands"]
            if item["brand"] == brand
        )
        self.assertEqual(
            [mode["id"] for mode in projected_brand["classificationModes"]],
            ["standard", "batch"],
        )

    def test_projects_modes_for_arbitrary_selected_brand(self):
        facts = self.fact_pack()
        brand = "本次用户选定品牌"
        facts["filters"]["brands"] = [brand]
        facts["materialFacts"][0]["title"] = f"{brand} 测试素材 101"
        facts["materialFacts"][1]["title"] = f"{brand} 测试素材 102"

        payload = build_yuntu_presentation(self.dual_highlight_analysis(), facts)

        projected_brand = next(item for item in payload["chapters"]["chapter04"]["brands"] if item["brand"] == brand)
        self.assertEqual(
            [mode["id"] for mode in projected_brand["classificationModes"]],
            ["standard", "batch"],
        )

    def test_projects_batch_distribution_with_scope_specific_denominators(self):
        facts = self.fact_pack()
        facts["filters"]["brands"] = ["小仙炖", "五个女博士"]
        facts["materialFacts"][0]["title"] = "小仙炖测试素材 101"
        facts["materialFacts"][1]["title"] = "五个女博士测试素材 102"
        analysis = self.dual_highlight_analysis()
        refs = [
            "highlight:101:cover:0",
            "highlight:101:click_peak:2",
            "highlight:102:cover:0",
            "highlight:102:click_peak:2",
        ]
        groups = []
        for category, group_refs, label in (
            ("人物动作", refs[:2], "人物动作"),
            ("产品信息", refs[2:3], "产品信息"),
            ("结果展示", refs[3:], "结果展示"),
        ):
            group = copy.deepcopy(analysis["highlightDashboard"]["batchClassification"]["groups"][0])
            group.update({"category": category, "label": label, "frame_refs": group_refs})
            groups.append(group)
        analysis["highlightDashboard"]["batchClassification"]["groups"] = groups

        payload = build_yuntu_presentation(analysis, facts)
        brands = payload["chapters"]["chapter04"]["brands"]
        all_batch = next(mode for mode in brands[0]["classificationModes"] if mode["id"] == "batch")
        xiaodun_batch = next(mode for mode in brands[1]["classificationModes"] if mode["id"] == "batch")

        self.assertEqual(all_batch["distribution"]["totalFrames"], 4)
        self.assertEqual(
            [(item["category"], item["count"], item["share"]) for item in all_batch["distribution"]["buckets"]],
            [("人物动作", 2, 0.5), ("产品信息", 1, 0.25), ("结果展示", 1, 0.25)],
        )
        self.assertEqual(xiaodun_batch["distribution"]["totalFrames"], 2)
        self.assertEqual(
            [(item["category"], item["count"], item["share"]) for item in xiaodun_batch["distribution"]["buckets"]],
            [("人物动作", 2, 1.0)],
        )

    def test_rejects_inconsistent_batch_distribution(self):
        payload = build_yuntu_presentation(self.dual_highlight_analysis(), self.fact_pack())
        batch = payload["chapters"]["chapter04"]["brands"][0]["classificationModes"][1]
        batch["distribution"]["buckets"][0]["count"] += 1

        with self.assertRaisesRegex(YuntuPresentationError, "distribution.*count"):
            validate_yuntu_presentation(payload)

    def test_builds_a_versioned_json_serializable_projection(self):
        analysis = self.analysis()
        facts = self.fact_pack()
        before = json.dumps({"analysis": analysis, "facts": facts}, ensure_ascii=False, sort_keys=True)

        payload = build_yuntu_presentation(analysis, facts)

        self.assertEqual(payload["presentationSchemaVersion"], 3)
        self.assertEqual(payload["report"]["sections"], ["chapter01", "chapter02", "chapter03", "chapter04", "chapter05"])
        self.assertIs(payload, validate_yuntu_presentation(payload))
        json.dumps(payload, ensure_ascii=False)
        self.assertEqual(before, json.dumps({"analysis": analysis, "facts": facts}, ensure_ascii=False, sort_keys=True))

    def test_projects_script_dashboard_for_selected_detail_materials(self):
        facts = self.fact_pack()
        facts["scriptFacts"] = {
            "scope": "selected_detail_materials",
            "coverage": {"total": 2, "script": 1, "rate": 0.5},
            "frequencies": {
                "formula_labels": {"场景引入": {"count": 1, "material_ids": ["101"]}},
                "selling_points": {}, "scenes": {}, "promotions": {},
                "marketing_formats": {"口播": {"count": 1, "material_ids": ["101"]}},
            },
            "materials": [{
                "material_id": "101", "script_text": "先提出使用场景。", "script_segments": [],
                "content_formula": {"labels": ["场景引入"]}, "creative_breakdown": {"tags": ["口播"]},
                "metrics": {"convertCnt": 17, "orderCnt": 3},
                "data_availability": {"script_text": {"available": True, "missing_reason": ""}},
            }, {
                "material_id": "102", "script_text": "", "script_segments": [],
                "content_formula": None, "creative_breakdown": None, "metrics": {},
                "data_availability": {"script_text": {"available": False, "missing_reason": "source_empty"}},
            }],
        }
        analysis = self.analysis()
        analysis["scriptInsights"] = [{
            "title": "从场景切入后接卖点",
            "summary": "已获取详情素材中可见的脚本先建立使用场景，再进入商品信息；该结构可作为下一轮变量验证方向。",
            "evidence": ["script_text", "content_formula.labels"],
            "material_ids": ["101"],
        }]

        payload = build_yuntu_presentation(analysis, facts)

        chapter = payload["chapters"]["chapter03"]
        self.assertEqual(chapter["scriptDashboard"]["scope"], "selected_detail_materials")
        self.assertEqual(chapter["scriptDashboard"]["coverage"], {"total": 2, "script": 1, "rate": 0.5})
        self.assertEqual(chapter["scriptDashboard"]["insights"][0]["materialIds"], ["101"])
        self.assertEqual(chapter["scriptDashboard"]["materials"][1]["availability"], "source_empty")
        self.assertEqual(payload["report"]["sections"], ["chapter01", "chapter02", "chapter03", "chapter04", "chapter05"])

    def test_projects_script_dashboard_dimensions_and_formula_hierarchy(self):
        facts = self.fact_pack()
        facts["scriptFacts"] = {
            "scope": "selected_detail_materials",
            "coverage": {"total": 2, "script": 2, "rate": 1.0},
            "frequencies": {
                "formula_labels": {"level_1_label:10": {"count": 2, "material_ids": ["101", "102"]}},
                "selling_points": {"优质活菌": {"count": 2, "material_ids": ["101", "102"]}},
                "scenes": {"早餐": {"count": 1, "material_ids": ["101"]}},
                "promotions": {},
                "marketing_formats": {},
            },
            "materials": [
                {
                    "material_id": "101", "script_text": "先提出场景，再展示商品。", "script_segments": [],
                    "content_formula": {"labels": [{"level_1_label": 10, "level_2_labels": [40, 55]}], "detail.40": "小蓝瓶"},
                    "creative_breakdown": {"tags": ["口播"]}, "metrics": {},
                    "data_availability": {"script_text": {"available": True, "missing_reason": ""}},
                },
                {
                    "material_id": "102", "script_text": "先讲卖点，再给出行动。", "script_segments": [],
                    "content_formula": {"labels": [{"level_1_label": 10, "level_2_labels": [40]}]},
                    "creative_breakdown": {"tags": ["口播"]}, "metrics": {},
                    "data_availability": {"script_text": {"available": True, "missing_reason": ""}},
                },
            ],
        }
        analysis = self.analysis()
        analysis["scriptInsights"] = [{
            "title": "先场景后卖点",
            "summary": "已获取详情素材中的可见脚本呈现先建立场景、再承接卖点的结构。",
            "evidence": ["script_text"],
            "material_ids": ["101", "102"],
        }]

        dashboard = build_yuntu_presentation(analysis, facts)["chapters"]["chapter03"]["scriptDashboard"]

        self.assertEqual(dashboard["conclusion"]["text"], "已获取详情素材中的可见脚本呈现先建立场景、再承接卖点的结构。")
        self.assertEqual(dashboard["conclusion"]["materialIds"], ["101", "102"])
        self.assertEqual(dashboard["dimensions"]["contentFormula"]["primary"][0]["id"], "10")
        self.assertEqual(dashboard["dimensions"]["contentFormula"]["primary"][0]["label"], "品牌印象")
        self.assertEqual(dashboard["dimensions"]["contentFormula"]["primary"][0]["count"], 2)
        self.assertEqual(dashboard["dimensions"]["contentFormula"]["secondary"]["10"][0]["id"], "40")
        self.assertEqual(dashboard["dimensions"]["contentFormula"]["secondary"]["10"][0]["label"], "产品代名词")
        self.assertEqual(dashboard["dimensions"]["contentFormula"]["secondary"]["10"][0]["count"], 2)
        self.assertEqual(dashboard["dimensions"]["contentFormula"]["secondary"]["10"][0]["detailLabels"], ["小蓝瓶"])
        self.assertEqual(dashboard["dimensions"]["scriptCopy"]["coverage"], {"total": 2, "script": 2, "rate": 1.0})
        self.assertEqual(dashboard["sellingPoints"][0]["label"], "优质活菌")
        self.assertEqual(dashboard["keywords"][0]["label"], "优质活菌")
        self.assertFalse(any(item["label"].startswith("level_") for item in dashboard["keywords"]))

    def test_projects_numeric_formula_references_as_semantic_labels_in_insight_text(self):
        facts = self.fact_pack()
        facts["scriptFacts"] = {
            "scope": "selected_detail_materials",
            "coverage": {"total": 1, "script": 1, "rate": 1.0},
            "frequencies": {"formula_labels": {}, "selling_points": {}, "scenes": {}, "promotions": {}, "marketing_formats": {}},
            "materials": [{
                "material_id": "101",
                "script_text": "文案",
                "script_segments": [],
                "content_formula": {"labels": [{"level_1_label": 10, "level_2_labels": [40]}]},
                "creative_breakdown": None,
                "metrics": {},
            }],
        }
        analysis = self.analysis()
        analysis["scriptInsights"] = [{
            "title": "一二级内容公式：产品信息形成共同骨架",
            "summary": "一级标签10和9均覆盖3个素材，二级标签40“小蓝瓶”和42“益生菌”反复出现；建议保留10/9对应的产品骨架。",
            "evidence": ["content_formula.labels"],
            "material_ids": ["101"],
        }]

        dashboard = build_yuntu_presentation(analysis, facts)["chapters"]["chapter03"]["scriptDashboard"]
        text = dashboard["insights"][0]["text"]

        self.assertIn('一级公式“品牌印象”和“商品卖点”', text)
        self.assertIn('二级公式“产品代名词”和“成分配方原料”', text)
        self.assertIn('“品牌印象”/“商品卖点”对应', text)
        self.assertNotIn("一级标签10", text)
        self.assertNotIn("二级标签40", text)

    def test_script_dashboard_keeps_legacy_missing_fields_compatible(self):
        facts = self.fact_pack()
        facts["scriptFacts"] = {
            "scope": "selected_detail_materials",
            "coverage": {"total": 1, "script": 0, "rate": 0},
            "frequencies": {},
            "materials": [{"material_id": "101", "script_text": "", "script_segments": []}],
        }

        dashboard = build_yuntu_presentation(self.analysis(), facts)["chapters"]["chapter03"]["scriptDashboard"]

        self.assertEqual(dashboard["dimensions"]["contentFormula"]["primary"], [])
        self.assertEqual(dashboard["dimensions"]["scriptCopy"]["coverage"]["script"], 0)
        self.assertEqual(dashboard["conclusion"]["source"], "coverage")

    def test_projects_keyword_cloud_with_ai_review_and_merge_without_changing_fact_frequency(self):
        facts = self.fact_pack()
        facts["scriptFacts"] = {
            "scope": "selected_detail_materials",
            "coverage": {"total": 2, "script": 2, "rate": 1.0},
            "frequencies": {},
            "keywordCloud": {
                "source": "facts.scripts.materials[*].script_text",
                "keywords": [
                    {
                        "keyword": "鲜炖",
                        "frequency": 2,
                        "materialIds": ["101"],
                        "evidenceRefs": ["script:101:text:鲜炖"],
                    },
                    {
                        "keyword": "燕窝",
                        "frequency": 1,
                        "materialIds": ["101"],
                        "evidenceRefs": ["script:101:text:燕窝"],
                    },
                ],
            },
            "materials": [
                {"material_id": "101", "script_text": "鲜炖 燕窝。", "script_segments": []},
                {"material_id": "102", "script_text": "鲜炖。", "script_segments": []},
            ],
        }
        analysis = self.analysis()
        analysis["scriptInsights"] = [
            {
                "title": "一二级内容公式：场景承接产品证明",
                "summary": "内容公式从具体场景进入产品证明。",
                "material_ids": ["101"],
                "evidence": ["content_formula.labels"],
            },
            {
                "title": "脚本文案：用产品信息承接场景",
                "summary": "脚本文案用产品信息承接具体场景。",
                "material_ids": ["101", "102"],
                "evidence": ["script_text"],
            },
        ]
        analysis["keywordCloudReview"] = [
            {"keyword": "鲜炖", "decision": "accept", "target": ""},
            {"keyword": "燕窝", "decision": "merge", "target": "鲜炖"},
        ]
        analysis["keywordCloudInsight"] = {
            "oneSentenceConclusion": "脚本以鲜炖品质承接日常使用场景。",
            "summary": "关键词集中在产品品质表达，下一轮可比较品质信息与场景信息的前置顺序。",
            "sellingPoints": [
                {
                    "title": "鲜炖品质",
                    "description": "产品品质词承担购买理由的解释。",
                    "keywordRefs": ["鲜炖"],
                    "evidenceRefs": ["script:101:text:鲜炖"],
                }
            ],
        }

        dashboard = build_yuntu_presentation(analysis, facts)["chapters"]["chapter03"]["scriptDashboard"]
        panel = dashboard["keywordCloudPanel"]

        self.assertEqual(panel["oneSentenceConclusion"], "脚本以鲜炖品质承接日常使用场景。")
        self.assertEqual(panel["summary"], "关键词集中在产品品质表达，下一轮可比较品质信息与场景信息的前置顺序。")
        self.assertEqual(panel["keywords"][0]["keyword"], "鲜炖")
        self.assertEqual(panel["keywords"][0]["frequency"], 3)
        self.assertEqual(panel["keywords"][0]["materialIds"], ["101"])
        self.assertEqual(panel["sellingPoints"][0]["keywordRefs"], ["鲜炖"])

    def test_chapter05_uses_single_panel_source_without_frame_copy_fields(self):
        payload = build_yuntu_presentation(self.analysis(), self.fact_pack())
        chapter = payload["chapters"]["chapter05"]

        self.assertNotIn("materials", payload)
        self.assertEqual(
            chapter["materialTabs"],
            payload["interactions"]["chapter05-material-tabs"]["items"],
        )
        frame = chapter["panels"][0]["frames"][0]
        self.assertEqual(chapter["panels"][0]["exposure"]["raw"], "20万-22万")
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

    def test_chapter02_projects_marketing_secondary_tags_and_raw_audit_tags(self):
        facts = self.fact_pack()
        dashboard = {
            "taxonomyVersion": 2,
            "categories": [{
                "category": "功效功能",
                "occurrenceCount": 2,
                "tags": [{
                    "tag": "补充营养_日常养护",
                    "rawTag": "功效功能_补充营养_日常养护",
                    "count": 2,
                }],
            }],
        }
        facts["chapter02Facts"]["all"]["marketingDashboard"] = dashboard
        facts["chapter02AiFacts"]["all"]["marketingDashboard"] = dashboard

        payload = build_yuntu_presentation(self.analysis(), facts)
        chart = payload["chapters"]["chapter02"]["panels"][0]["charts"][0]
        detail_bucket = payload["chapters"]["chapter02"]["panels"][0]["detailViews"][0]["pie"]["buckets"][0]

        self.assertEqual(chart["buckets"][0]["label"], "功效功能")
        self.assertEqual(detail_bucket["label"], "补充营养_日常养护")
        self.assertEqual(detail_bucket["rawTag"], "功效功能_补充营养_日常养护")
        self.assertEqual(payload["extensions"]["yuntu"]["marketingTagTaxonomyVersion"], 2)

    def test_projects_chapter01_top_material_conclusions(self):
        analysis = self.analysis()
        analysis["topMaterialCombination"] = {
            "brandConclusions": [{"brand": "WONDERLAB/万益蓝", "classificationSource": "runtime_title_rule", "dataSummary": "品牌全量素材的累计曝光、CTR、CVR 与 3 秒播放率呈现稳定。", "evidence": [{"material_id": "101"}]}],
        }

        payload = build_yuntu_presentation(analysis, self.fact_pack())

        chapter = payload["chapters"]["chapter01"]
        self.assertEqual(payload["presentationSchemaVersion"], 3)
        self.assertEqual(payload["report"]["sections"], ["chapter01", "chapter02", "chapter03", "chapter04", "chapter05"])
        self.assertNotIn("executiveInsight", chapter)
        self.assertNotIn("overallInsights", chapter)
        self.assertNotIn("brandComparisonInsight", chapter)
        self.assertEqual(set(chapter), {"brandTabs", "brandPanels"})
        self.assertEqual(chapter["brandPanels"][0]["brand"], "WONDERLAB/万益蓝")
        self.assertNotIn("topN", chapter["brandPanels"][0])
        self.assertEqual(set(chapter["brandPanels"][0]), {"id", "brand", "insights", "aiAnalysis"})
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

    def test_projects_period_comparison_and_hot_material_panel_without_raw_lists(self):
        facts = self.fact_pack()
        facts["comparisonFacts"] = {"brand": {"previousPeriod": {"sampleCountDelta": 1}}}
        facts["hotMaterialFacts"] = {
            "WONDERLAB/万益蓝": {
                "thresholdExposureMin": 200000,
                "qualifyingCount": 1,
                "materials": [{"material_id": "101", "title": "测试素材 101", "exposure": {"min": 200000, "max": 220000, "raw": "20万-22万"}, "metrics": {"ctr": 0.1}}],
                "available": True,
                "missing_reason": "",
            }
        }
        analysis = self.analysis()
        analysis["topMaterialCombination"] = {}
        analysis["topMaterialCombination"]["brandConclusions"] = [{
            "brand": "WONDERLAB/万益蓝",
            "classificationSource": "runtime_title_rule",
            "dataSummary": "品牌全量素材的累计曝光、CTR、CVR 与 3 秒播放率呈现稳定。",
            "comparisonSummary": "本周期样本较上一周期增加，整体表现高于行业大盘。",
            "hotMaterialInsight": {"title": "爆款素材表现分析", "summary": "爆款素材集中在高曝光区间，指标组合值得继续验证。", "evidence": {"scope": "brand", "material_ids": ["101"]}},
            "evidence": [{"material_id": "101"}],
            "material_ids": ["101"],
        }]

        payload = build_yuntu_presentation(analysis, facts)

        panel = payload["chapters"]["chapter01"]["brandPanels"][0]
        self.assertIn("comparison", panel)
        self.assertIn("hotMaterialPanel", panel)
        self.assertEqual(
            panel["aiAnalysis"],
            {
                "summary": (
                    "品牌全量素材的累计曝光、CTR、CVR 与 3 秒播放率呈现稳定。 "
                    "本周期样本较上一周期增加，整体表现高于行业大盘。 "
                    "爆款素材集中在高曝光区间，指标组合值得继续验证。"
                )
            },
        )
        self.assertNotIn("current", panel)
        self.assertNotIn("previousPeriod", panel)

    def test_chapter01_uses_all_brands_label_and_separate_ai_sections(self):
        facts = self.fact_pack()
        facts["comparisonFacts"] = {
            "scopes": {
                "all": {"previousPeriod": {"currentSampleCount": 2}},
                "WONDERLAB/万益蓝": {"previousPeriod": {"currentSampleCount": 1}},
            }
        }
        hot = {
            "thresholdExposureMin": 200000,
            "qualifyingCount": 1,
            "materials": [{
                "material_id": "101", "title": "测试素材 101",
                "exposure": {"min": 200000, "max": 220000, "raw": "20万-22万"},
                "metrics": {"ctr": 0.1, "cvr": 0.02, "play_3s_rate": 0.4},
            }],
            "available": True,
            "missing_reason": "",
        }
        facts["hotMaterialFacts"] = {
            "all": copy.deepcopy(hot),
            "WONDERLAB/万益蓝": copy.deepcopy(hot),
        }
        analysis = self.analysis()
        analysis["topMaterialCombination"] = {
            "brandConclusions": [{
                "brand": "WONDERLAB/万益蓝",
                "classificationSource": "runtime_title_rule",
                "dataSummary": "品牌表现段。",
                "hotMaterialInsight": {
                    "title": "爆款整体洞察",
                    "summary": "品牌爆款段。",
                    "evidence": {"scope": "brand", "material_ids": ["101"]},
                },
                "evidence": ["brand"], "material_ids": ["101"],
            }],
            "allBrandsConclusion": {
                "brand": "全品牌",
                "classificationSource": "runtime_title_rule",
                "dataSummary": "全范围表现段。",
                "hotMaterialInsight": {
                    "title": "全范围爆款整体洞察",
                    "summary": "全范围爆款段。",
                    "evidence": {"scope": "all", "material_ids": ["101"]},
                },
                "evidence": ["all"], "material_ids": ["101"],
            },
        }

        payload = build_yuntu_presentation(analysis, facts)
        chapter = payload["chapters"]["chapter01"]

        self.assertEqual(chapter["brandTabs"][0]["label"], "所有指定品牌")
        aggregate = chapter["brandPanels"][0]
        self.assertEqual(aggregate["brand"], "所有指定品牌")
        self.assertEqual(aggregate["aiAnalysis"]["dataSummary"], "全范围表现段。")
        self.assertEqual(
            aggregate["aiAnalysis"]["hotMaterialInsight"]["summary"],
            "全范围爆款段。",
        )
        self.assertIn("comparison", aggregate)
        self.assertIn("hotMaterialPanel", aggregate)
        brand_panel = chapter["brandPanels"][1]
        self.assertEqual(
            brand_panel["comparison"]["facts"]["previousPeriod"]["currentSampleCount"],
            1,
        )

    def test_chapter01_uses_industry_facts_for_legacy_aggregate_fallback(self):
        facts = self.fact_pack()
        facts["industryTop1000Facts"] = {
            "source_scope": "industry_top1000",
            "sample_count": 2,
            "metrics": {
                "show_cnt": {"total": 3000},
                "ctr": {"median": 0.2},
                "cvr": {"median": 0.1},
                "play_3s_rate": {"median": 0.4},
            },
        }
        facts.pop("brandRankingFacts", None)
        analysis = self.analysis()
        analysis["topMaterialCombination"] = {"brandConclusions": [{
                "brand": "WONDERLAB/万益蓝",
                "classificationSource": "runtime_title_rule",
                "dataSummary": "品牌全量素材的累计曝光、CTR、CVR 与 3 秒播放率呈现稳定。",
                "evidence": [{"material_id": "101"}],
            }]}
        payload = build_yuntu_presentation(analysis, facts)

        self.assertEqual(payload["chapters"]["chapter01"]["brandPanels"][0]["brand"], "所有指定品牌")
        self.assertIn("2 条素材", payload["chapters"]["chapter01"]["brandPanels"][0]["insights"][0]["text"])

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
        self.assertNotIn("secondLevelObservations", panel)
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
