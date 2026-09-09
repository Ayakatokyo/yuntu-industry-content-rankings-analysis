import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
MODULE_PATH = SCRIPTS_DIR / "yuntu_analysis.py"


def load_module():
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    spec = importlib.util.spec_from_file_location("yuntu_analysis", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class YuntuAnalysisTests(unittest.TestCase):
    def test_second_level_breakdown_uses_canonical_trend_names_and_script_coverage(self):
        analysis = load_module()
        detail = {
            "trend_series": [
                {"trend_name": "点赞指数", "series": [{"second": 0, "value": 0.1}]},
                {"trend_name": "流失指数", "series": [{"second": 0, "value": 0.2}]},
                {"trend_name": "点击指数", "series": [{"second": 0, "value": 0.3}]},
                {"trend_name": "互动指数", "series": [{"second": 0, "value": 0.4}]},
                {"trend_name": "评论指数", "series": [{"second": 0, "value": 0.5}]},
            ],
            "high_points": [],
            "loss_points": [],
        }
        breakdown = analysis._second_level_breakdown(detail)
        facts = analysis.build_script_facts(
            [{"material_id": "101", "script_text": "", "content_formula": {"sources": {"title": {"text": "标题不计入脚本"}}}, "creative_breakdown": {"tags": ["标签不计入脚本"]}}],
            [{"material_id": "101", "rank": 1}],
        )

        self.assertTrue(all(metric["available"] for metric in breakdown["metrics"]))
        self.assertEqual(facts["coverage"], {"total": 1, "script": 0, "rate": 0})
        self.assertEqual(facts["keywordCloud"]["keywords"], [])

    def test_material_deep_dive_input_contains_script_facts_and_evidence_allowlist(self):
        analysis = load_module()
        fact_pack = {
            "reportScopes": {"ranking": {}, "detail": {"sample_count": 1}},
            "industryTop1000Facts": {},
            "brandRankingFacts": {},
            "chapter02AiFacts": {"scopeOrder": ["all"]},
            "scriptFacts": {},
            "visualAssets": [],
            "dataLimitations": [],
            "filters": {},
            "dataAvailabilitySummary": {},
            "materialFacts": [{
                "material_id": "m-001",
                "script_text": "早餐可以不碰碳水，但鲜炖燕窝一定要坚持吃。",
                "content_formula": {
                    "labels": [{"level_1_label": 9, "level_2_labels": [34]}],
                },
                "highlightFrames": [],
                "secondLevelBreakdown": {"metrics": []},
            }],
        }

        with tempfile.TemporaryDirectory() as directory:
            analysis._write_analysis_units(fact_pack, Path(directory))
            payload = json.loads(
                (Path(directory) / "analysis-units/material-deep-dive-input.json")
                .read_text(encoding="utf-8")
            )

        material = payload["evidence"]["materialFacts"][0]
        self.assertEqual(material["script"]["text"], fact_pack["materialFacts"][0]["script_text"])
        self.assertEqual(material["script"]["formula"][0], {"level1": "商品卖点", "level2": "功效功能"})
        self.assertTrue(material["script"]["evidence"])
        self.assertTrue(material["evidenceIndex"]["script"])

    def test_build_script_facts_emits_deterministic_keyword_cloud_from_script_text(self):
        analysis = load_module()
        details = [
            {
                "material_id": "101",
                "script_text": "早餐 鲜炖 鲜炖 早餐",
                "script_segments": [],
                "content_formula": None,
                "creative_breakdown": None,
                "metrics": {},
                "data_availability": {},
            },
            {
                "material_id": "102",
                "script_text": "早餐 鲜炖",
                "script_segments": [],
                "content_formula": None,
                "creative_breakdown": None,
                "metrics": {},
                "data_availability": {},
            },
        ]

        facts = analysis.build_script_facts(
            details,
            [{"material_id": "101", "rank": 1}, {"material_id": "102", "rank": 2}],
        )

        self.assertEqual(facts["keywordCloud"]["source"], "facts.scripts.materials[*].script_text")
        keyword_by_name = {
            item["keyword"]: item for item in facts["keywordCloud"]["keywords"]
        }
        self.assertEqual(keyword_by_name["鲜炖"]["frequency"], 3)
        self.assertEqual(keyword_by_name["鲜炖"]["materialIds"], ["101", "102"])
        self.assertEqual(
            keyword_by_name["鲜炖"]["evidenceRefs"],
            ["script:101:text:鲜炖", "script:102:text:鲜炖"],
        )

    def test_prompt_requires_two_script_dimensions_and_keyword_cloud_ai_contract(self):
        prompt = (ROOT / "prompts" / "yuntu-analysis-prompt.md").read_text(encoding="utf-8")

        self.assertIn("keywordCloudReview", prompt)
        self.assertIn("keywordCloudInsight", prompt)
        self.assertIn("scriptInsights` 固定输出 2 条", prompt)
        self.assertIn("一二级内容公式", prompt)
        self.assertIn("脚本文案", prompt)

    def test_prompt_requires_semantic_yuntu_content_formula_names(self):
        prompt = (ROOT / "prompts" / "yuntu-analysis-prompt.md").read_text(encoding="utf-8")

        self.assertIn("一级 ID 10 对应品牌印象", prompt)
        self.assertIn("一级 ID 9 对应商品卖点", prompt)
        self.assertIn("二级 ID 40 对应产品代名词", prompt)
        self.assertIn("二级 ID 42 对应成分配方原料", prompt)
        self.assertIn("用户可见正文只写语义名称", prompt)

    def test_build_script_facts_deduplicates_materials_and_counts_only_source_labels(self):
        analysis = load_module()
        details = [
            {
                "material_id": "101",
                "video_url": "https://video.example/101-a.mp4",
                "script_text": "先提出早餐场景，再展示低糖卖点。",
                "script_segments": [],
                "content_formula": {
                    "labels": ["场景引入", "卖点展示"],
                    "detail.商品卖点": "低糖、便携",
                    "detail.使用场景": "早餐、通勤",
                },
                "creative_breakdown": {"raw": {"素材形式": "口播、产品展示"}, "tags": ["口播", "产品展示"]},
                "metrics": {"convertCnt": 17, "orderCnt": 3},
                "source_paths": {"detail": "raw-csv/details/101.csv"},
                "source_hashes": {"detail": "a" * 64},
                "data_availability": {
                    "script_text": {"available": True, "missing_reason": ""},
                    "script_segments": {"available": False, "missing_reason": "source_empty"},
                    "content_formula": {"available": True, "missing_reason": ""},
                    "creative_breakdown": {"available": True, "missing_reason": ""},
                },
            },
            {
                "material_id": "101",
                "video_url": "https://video.example/101-b.mp4",
                "script_text": "先提出早餐场景，再展示低糖卖点。",
                "script_segments": [],
                "content_formula": {"labels": ["场景引入", "卖点展示"], "detail.商品卖点": "低糖、便携", "detail.使用场景": "早餐、通勤"},
                "creative_breakdown": {"raw": {"素材形式": "口播、产品展示"}, "tags": ["口播", "产品展示"]},
                "metrics": {"convertCnt": 17, "orderCnt": 3},
                "data_availability": {},
            },
            {"material_id": "102", "script_text": "信任表达来自原料证明。", "script_segments": [], "content_formula": {"labels": ["品质证明"], "detail.商品卖点": "原料"}, "creative_breakdown": {"raw": {"营销活动": "限时优惠"}, "tags": ["限时优惠"]}, "metrics": {}, "data_availability": {}},
            {"material_id": "103", "script_text": "展示通勤中的使用方式。", "script_segments": [], "content_formula": {"labels": ["场景引入"], "detail.使用场景": "通勤"}, "creative_breakdown": {"raw": {"素材形式": "产品展示"}, "tags": ["产品展示"]}, "metrics": {}, "data_availability": {}},
            {"material_id": "104", "script_text": "", "script_segments": [], "content_formula": None, "creative_breakdown": None, "metrics": {}, "data_availability": {}},
        ]
        selected = [{"material_id": str(index), "rank": index} for index in range(101, 105)]

        facts = analysis.build_script_facts(details, selected)

        self.assertEqual(facts["scope"], "selected_detail_materials")
        self.assertEqual(facts["coverage"], {"total": 4, "script": 3, "rate": 0.75})
        self.assertEqual([item["material_id"] for item in facts["materials"]], ["101", "102", "103", "104"])
        self.assertEqual(facts["materials"][0]["video_url_variants"], [
            "https://video.example/101-a.mp4", "https://video.example/101-b.mp4"
        ])
        self.assertEqual(facts["frequencies"]["formula_labels"]["场景引入"]["count"], 2)
        self.assertEqual(facts["frequencies"]["selling_points"]["低糖"]["count"], 1)
        self.assertEqual(facts["frequencies"]["scenes"]["通勤"]["count"], 2)
        self.assertEqual(facts["frequencies"]["marketing_formats"]["产品展示"]["count"], 2)
        self.assertNotIn("industryTop1000", json.dumps(facts, ensure_ascii=False))
        self.assertEqual(facts["materials"][0]["metrics"], {"convertCnt": 17, "orderCnt": 3})
        self.assertEqual(
            facts["materials"][0]["source_paths"],
            {"detail": "raw-csv/details/101.csv"},
        )
        self.assertEqual(facts["materials"][0]["source_hashes"], {"detail": "a" * 64})

    def test_prepare_analysis_does_not_write_legacy_complete_snapshot(self):
        analysis = load_module()
        records = [{
            "material_id": "1", "title": "素材", "rank": 1,
            "metrics": {"ctr": 0.2, "show_cnt": 100},
            "people_tags": [], "material_tags": [], "data_availability": {},
        }]
        selected = [{
            "rank": 1, "material_id": "1",
            "detailRecordPath": "normalized/detail-records/1.json",
        }]
        details = {
            "1": {
                "material_id": "1", "high_points": [], "loss_points": [],
                "data_availability": {},
            }
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_input(root, records, selected, details)
            status = analysis.prepare_analysis(
                input_dir=root, output_dir=root / "diagnostic-analysis"
            )
            output = root / "diagnostic-analysis"

            self.assertEqual(status, 0)
            self.assertFalse((output / "yuntu-analysis-data.json").exists())
            for relative_path in (
                "report-data.json",
                "yuntu-analysis-prompt.md",
                "yuntu-ai-analysis.schema.json",
                "analysis-units/analysis-unit-manifest.json",
                "analysis-units/ranking-brand-input.json",
                "analysis-units/audience-marketing-input.json",
                "analysis-units/highlight-input.json",
                "analysis-units/material-deep-dive-input.json",
                "analysis-units/script-input.json",
            ):
                self.assertTrue((output / relative_path).is_file(), relative_path)

    def test_prepare_analysis_uses_detail_title_when_material_is_not_in_ranking_pool(self):
        analysis = load_module()
        records = [{
            "material_id": "1", "title": "榜单素材", "rank": 1,
            "metrics": {"show_cnt": 100}, "people_tags": [],
            "material_tags": [], "data_availability": {},
        }]
        selected = [{
            "rank": "-", "material_id": "999",
            "detailRecordPath": "normalized/detail-records/999.json",
        }]
        details = {
            "999": {
                "material_id": "999", "title": "最新详情素材标题",
                "high_points": [], "loss_points": [], "data_availability": {},
            }
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_input(root, records, selected, details)
            analysis.prepare_analysis(input_dir=root, output_dir=root / "diagnostic-analysis")
            report = json.loads(
                (root / "diagnostic-analysis" / "report-data.json").read_text(encoding="utf-8")
            )

        self.assertEqual(report["materialFacts"][0]["title"], "最新详情素材标题")

    def test_prepare_analysis_emits_period_comparisons_and_deterministic_hot_material_facts(self):
        analysis = load_module()
        query_records = [
            {
                "material_id": "101", "title": "小仙炖鲜炖燕窝", "rank": 1,
                "metrics": {"show_cnt": 10, "ctr": 0.1},
                "exposure": {"min": 199999, "max": 210000, "raw": "19.9999万-21万"},
                "people_tags": [], "material_tags": [], "data_availability": {},
            },
            {
                "material_id": "102", "title": "小仙炖礼盒", "rank": 2,
                "metrics": {"show_cnt": 20, "ctr": 0.2},
                "exposure": {"min": 200000, "max": 240000, "raw": "20万-24万"},
                "people_tags": [], "material_tags": [], "data_availability": {},
            },
            {
                "material_id": "103", "title": "小仙炖高曝光", "rank": 3,
                "metrics": {"show_cnt": 30, "ctr": 0.3},
                "exposure": {"min": 300000, "max": 350000, "raw": "30万-35万"},
                "people_tags": [], "material_tags": [], "data_availability": {},
            },
        ]
        previous_records = [
            {**query_records[0], "material_id": "201", "exposure": {"min": 100000, "max": 120000, "raw": "10万-12万"}},
        ]
        industry_records = [
            {**query_records[0], "material_id": "301", "exposure": {"min": 250000, "max": 280000, "raw": "25万-28万"}},
        ]
        selected = [{"rank": 1, "material_id": "101", "detailRecordPath": "normalized/detail-records/101.json"}]
        details = {"101": {"material_id": "101", "high_points": [], "loss_points": [], "data_availability": {}}}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_input(root, query_records, selected, details)
            (root / "normalized" / "list-records-previous-period.json").write_text(json.dumps(previous_records), encoding="utf-8")
            (root / "normalized" / "list-records-industry.json").write_text(json.dumps(industry_records), encoding="utf-8")
            manifest_path = root / "batch-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest.update({
                "schemaVersion": 3,
                "filters": {"industry": "食品饮料", "time_range_type": "CUSTOM", "custom_start_date": "20260810", "custom_end_date": "20260820", "brands": ["小仙炖"]},
                "rankingRuns": {
                    "query": {"normalizedPath": "normalized/list-records.json", "actualDateRange": {"startDate": "2026-08-10", "endDate": "2026-08-20"}, "status": "success"},
                    "previous_period": {"normalizedPath": "normalized/list-records-previous-period.json", "actualDateRange": {"startDate": "2026-07-30", "endDate": "2026-08-09"}, "status": "success"},
                    "industry": {"normalizedPath": "normalized/list-records-industry.json", "actualDateRange": {"startDate": "2026-08-10", "endDate": "2026-08-20"}, "status": "success"},
                },
            })
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            with mock.patch.object(analysis, "generate_standard_highlights_for_detail", return_value=[]):
                analysis.prepare_analysis(input_dir=root, output_dir=root / "diagnostic-analysis")
            ranking = json.loads((root / "diagnostic-analysis" / "analysis-units" / "ranking-brand-input.json").read_text(encoding="utf-8"))

        evidence = ranking["evidence"]
        self.assertEqual(
            set(evidence),
            {"current", "previousPeriod", "industryBenchmark", "comparisonFacts", "hotMaterialFacts"},
        )
        self.assertEqual(evidence["hotMaterialFacts"]["all"]["qualifyingCount"], 2)
        self.assertEqual([item["material_id"] for item in evidence["hotMaterialFacts"]["all"]["materials"]], ["103", "102"])
        self.assertEqual(evidence["comparisonFacts"]["previousPeriod"]["sampleCountDelta"], 2)

    def test_ranking_unit_is_limited_to_three_period_lists_and_deterministic_facts(self):
        analysis = load_module()
        metrics = {
            "show_cnt": 100,
            "ctr": 0.1,
            "cvr": 0.02,
            "play_3s_rate": 0.4,
        }
        query_records = [{
            "material_id": "101", "title": "小仙炖当前素材", "rank": 1,
            "metrics": metrics, "exposure": {"min": 200000, "max": 220000, "raw": "20万-22万"},
            "people_tags": ["新锐白领"], "material_tags": ["功效功能_补充营养"], "data_availability": {},
        }]
        previous_records = [{
            **query_records[0], "material_id": "201", "title": "小仙炖环比素材",
        }]
        industry_records = [{
            **query_records[0], "material_id": "301", "title": "行业素材",
        }]
        selected = [{"rank": 1, "material_id": "101", "detailRecordPath": "normalized/detail-records/101.json"}]
        details = {"101": {"material_id": "101", "high_points": [], "loss_points": [], "data_availability": {}}}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_input(root, query_records, selected, details)
            (root / "normalized" / "list-records-previous-period.json").write_text(json.dumps(previous_records), encoding="utf-8")
            (root / "normalized" / "list-records-industry.json").write_text(json.dumps(industry_records), encoding="utf-8")
            manifest_path = root / "batch-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["rankingRuns"] = {
                "query": {"normalizedPath": "normalized/list-records.json", "status": "success"},
                "previous_period": {"normalizedPath": "normalized/list-records-previous-period.json", "status": "success"},
                "industry": {"normalizedPath": "normalized/list-records-industry.json", "status": "success"},
            }
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            with mock.patch.object(analysis, "generate_standard_highlights_for_detail", return_value=[]):
                analysis.prepare_analysis(input_dir=root, output_dir=root / "diagnostic-analysis")
            ranking = json.loads((root / "diagnostic-analysis" / "analysis-units" / "ranking-brand-input.json").read_text(encoding="utf-8"))

        self.assertEqual(
            set(ranking["evidence"]),
            {"current", "previousPeriod", "industryBenchmark", "comparisonFacts", "hotMaterialFacts"},
        )
        for scope_name in ("current", "previousPeriod", "industryBenchmark"):
            rows = ranking["evidence"][scope_name]["materials"]
            self.assertEqual(len(rows), 1)
            self.assertEqual(set(rows[0]["metrics"]), {"ctr", "cvr", "play_3s_rate"})
            self.assertEqual(rows[0]["exposure"], {"raw": "20万-22万", "available": True})
            self.assertNotIn("min", rows[0]["exposure"])
            self.assertNotIn("max", rows[0]["exposure"])
        unavailable = analysis._ranking_material_fact({
            "material_id": "999",
            "metrics": {"show_cnt": 999999, "ctr": 0.1, "cvr": 0.02, "play_3s_rate": 0.4},
            "exposure": {"min": 999999, "max": 1000000},
        })
        self.assertEqual(
            unavailable["exposure"],
            {"raw": "", "available": False, "missingReason": "exposure_interval_unavailable"},
        )
        self.assertNotIn("show_cnt", unavailable["metrics"])
        serialized = json.dumps(ranking, ensure_ascii=False)
        for forbidden in ("visualAssets", "highlightFrames", "secondLevelBreakdown", "trend_series", "script"):
            self.assertNotIn(forbidden, serialized)

    def test_brand_comparison_uses_unfiltered_industry_baseline(self):
        analysis = load_module()
        def record(material_id, title):
            return {
                "material_id": material_id, "title": title, "rank": 1,
                "metrics": {"show_cnt": 100, "ctr": 0.1, "cvr": 0.02, "play_3s_rate": 0.4},
                "exposure": {"min": 100000, "max": 110000, "raw": "10万-11万"},
                "people_tags": [], "material_tags": [], "data_availability": {},
            }
        query_records = [record("101", "小仙炖素材")]
        industry_records = [record("301", "行业素材一"), record("302", "行业素材二")]
        selected = [{"rank": 1, "material_id": "101", "detailRecordPath": "normalized/detail-records/101.json"}]
        details = {"101": {"material_id": "101", "high_points": [], "loss_points": [], "data_availability": {}}}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_input(root, query_records, selected, details)
            (root / "normalized" / "list-records-industry.json").write_text(json.dumps(industry_records), encoding="utf-8")
            manifest_path = root / "batch-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["filters"]["brands"] = ["小仙炖"]
            manifest["rankingRuns"] = {
                "query": {"normalizedPath": "normalized/list-records.json", "status": "success"},
                "previous_period": {"normalizedPath": "normalized/list-records.json", "status": "success"},
                "industry": {"normalizedPath": "normalized/list-records-industry.json", "status": "success"},
            }
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            with mock.patch.object(analysis, "generate_standard_highlights_for_detail", return_value=[]):
                analysis.prepare_analysis(input_dir=root, output_dir=root / "diagnostic-analysis")
            report = json.loads((root / "diagnostic-analysis" / "report-data.json").read_text(encoding="utf-8"))

        self.assertEqual(
            report["comparisonFacts"]["scopes"]["小仙炖"]["industryBenchmark"]["baselineSampleCount"],
            2,
        )

    def test_prepare_analysis_uses_configured_hot_material_threshold(self):
        analysis = load_module()
        query_records = [
            {
                "material_id": "101", "title": "中等曝光素材", "rank": 1,
                "metrics": {"show_cnt": 10, "ctr": 0.1},
                "exposure": {"min": 300000, "max": 350000, "raw": "30万-35万"},
                "people_tags": [], "material_tags": [], "data_availability": {},
            },
            {
                "material_id": "102", "title": "高曝光素材", "rank": 2,
                "metrics": {"show_cnt": 20, "ctr": 0.2},
                "exposure": {"min": 600000, "max": 650000, "raw": "60万-65万"},
                "people_tags": [], "material_tags": [], "data_availability": {},
            },
        ]
        selected = [{"rank": 1, "material_id": "101", "detailRecordPath": "normalized/detail-records/101.json"}]
        details = {"101": {"material_id": "101", "high_points": [], "loss_points": [], "data_availability": {}}}
        custom_config = {
            "schemaVersion": 1,
            "hotMaterialRule": {
                "metric": "exposure_interval_min",
                "comparison": "gte",
                "threshold": 500000,
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_input(root, query_records, selected, details)
            manifest_path = root / "batch-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest.update({
                "schemaVersion": 3,
                "filters": {"industry": "食品饮料", "time_range_type": "CUSTOM", "custom_start_date": "20260810", "custom_end_date": "20260820", "brands": ["小仙炖"]},
                "rankingRuns": {
                    "query": {"normalizedPath": "normalized/list-records.json", "actualDateRange": {"startDate": "2026-08-10", "endDate": "2026-08-20"}, "status": "success"},
                    "previous_period": {"normalizedPath": "normalized/list-records.json", "actualDateRange": {"startDate": "2026-07-30", "endDate": "2026-08-09"}, "status": "success"},
                    "industry": {"normalizedPath": "normalized/list-records.json", "actualDateRange": {"startDate": "2026-08-10", "endDate": "2026-08-20"}, "status": "success"},
                },
            })
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            config_path = root / "hot-material-rules.json"
            config_path.write_text(json.dumps(custom_config), encoding="utf-8")
            with mock.patch.object(analysis, "generate_standard_highlights_for_detail", return_value=[]):
                analysis.prepare_analysis(
                    input_dir=root,
                    output_dir=root / "diagnostic-analysis",
                    hot_material_config=config_path,
                )
            report_data = json.loads((root / "diagnostic-analysis" / "report-data.json").read_text(encoding="utf-8"))
            ranking = json.loads((root / "diagnostic-analysis" / "analysis-units" / "ranking-brand-input.json").read_text(encoding="utf-8"))
            prompt = (root / "diagnostic-analysis" / "yuntu-analysis-prompt.md").read_text(encoding="utf-8")

        self.assertEqual(report_data["hotMaterialRule"]["threshold"], 500000)
        self.assertEqual(report_data["hotMaterialFacts"]["all"]["thresholdExposureMin"], 500000)
        self.assertEqual(report_data["hotMaterialFacts"]["all"]["qualifyingCount"], 1)
        self.assertNotIn("hotMaterialRule", ranking["evidence"])
        self.assertIn("threshold=500000", prompt)

    def test_prompt_template_is_loaded_and_runtime_scope_is_injected(self):
        analysis = load_module()

        template = analysis.PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
        prompt = analysis._prompt_text(filters={"brands": ["万益蓝", "燕之屋"]})

        self.assertIn("__BRANDS__", template)
        self.assertIn("__SCOPE_LABELS__", template)
        self.assertIn("万益蓝、燕之屋", prompt)
        self.assertIn("all（全量 TOP1000）、万益蓝、燕之屋", prompt)
        self.assertNotIn("__BRANDS__", prompt)
        self.assertNotIn("__SCOPE_LABELS__", prompt)
        self.assertNotIn("__BRAND_SCOPE_LABEL__", prompt)
        self.assertIn("全品牌对象", prompt)
        self.assertNotIn("不得生成任何综合结论或跨品牌结论字段", prompt)

    def test_period_first_chapter_contract_uses_one_unified_brand_summary(self):
        analysis = load_module()
        schema = analysis._ranking_output_schema(include_period_contract=True)
        brand_schema = schema["properties"]["brandConclusions"]["items"]

        self.assertNotIn("comparisonSummary", brand_schema["required"])
        self.assertIn("hotMaterialInsight", brand_schema["required"])
        self.assertNotIn("comparisonSummary", brand_schema["properties"])
        self.assertIn("hotMaterialInsight", brand_schema["properties"])

        prompt = analysis._prompt_text(filters={"brands": ["小仙炖"]})
        self.assertIn("分别输出两个自然段", prompt)
        self.assertIn("每个对象只输出 `brand`、`classificationSource`、`dataSummary`、`hotMaterialInsight`、`evidence`、`material_ids`", prompt)
        self.assertIn("`hotMaterialInsight` 只写当前范围爆款素材的整体特征", prompt)

    def test_period_first_chapter_contract_requires_separate_hot_material_insight(self):
        analysis = load_module()
        schema = analysis._ranking_output_schema(include_period_contract=True)
        item_schema = schema["properties"]["brandConclusions"]["items"]

        self.assertIn("hotMaterialInsight", item_schema["required"])
        self.assertEqual(
            set(item_schema["properties"]["hotMaterialInsight"]["properties"]),
            {"title", "summary", "evidence"},
        )
        prompt = analysis._prompt_text(filters={"brands": ["小仙炖"]})
        self.assertIn("`dataSummary` 只覆盖当前表现、环比周期和同周期全行业对比", prompt)
        self.assertIn("`hotMaterialInsight` 只写当前范围爆款素材的整体特征", prompt)
        self.assertIn("分别输出两个自然段", prompt)

    def test_prompt_requires_explicit_current_previous_and_industry_comparison_order(self):
        analysis = load_module()
        prompt = analysis._prompt_text(filters={"brands": ["小仙炖"]})

        self.assertIn("先说明默认筛选条件的当前表现", prompt)
        self.assertIn("环比看", prompt)
        self.assertIn("与全行业大盘对比看", prompt)
        self.assertIn("不得只用‘较行业大盘’或‘高于大盘’等模糊短语", prompt)

    def _write_input(self, root, records, selected, details):
        (root / "normalized" / "detail-records").mkdir(parents=True)
        (root / "batch-manifest.json").write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "filters": {"industry": "食品饮料"},
                    "candidateMaterials": [
                        {"rank": index + 1, "material_id": record["material_id"]}
                        for index, record in enumerate(records)
                    ],
                    "selectedMaterials": selected,
                    "rejectedMaterials": [
                        {"rank": 9, "material_id": "999", "reason": "RpaIoError"}
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (root / "normalized" / "list-records.json").write_text(
            json.dumps(records, ensure_ascii=False), encoding="utf-8"
        )
        for material_id, detail in details.items():
            (root / "normalized" / "detail-records" / f"{material_id}.json").write_text(
                json.dumps(detail, ensure_ascii=False), encoding="utf-8"
            )

    def test_prepare_analysis_calculates_comparison_tag_and_trend_facts(self):
        analysis = load_module()
        records = [
            {
                "material_id": "101", "title": "素材一", "rank": 1,
                "metrics": {"ctr": 0.1, "show_cnt": 100, "play_3s_rate": 0.2},
                "people_tags": ["新锐白领"], "material_tags": ["限时抢购"],
                "data_availability": {"metrics": {"available": True, "missing_reason": ""}},
            },
            {
                "material_id": "102", "title": "素材二", "rank": 2,
                "metrics": {"ctr": 0.2, "show_cnt": 200, "play_3s_rate": 0.3},
                "people_tags": ["新锐白领"], "material_tags": ["限时抢购"],
                "data_availability": {"metrics": {"available": True, "missing_reason": ""}},
            },
            {
                "material_id": "103", "title": "素材三", "rank": 3,
                "metrics": {"ctr": 0.3, "show_cnt": 300, "play_3s_rate": 0.4},
                "people_tags": ["都市银发"], "material_tags": ["商品展示"],
                "data_availability": {"metrics": {"available": True, "missing_reason": ""}},
            },
            {
                "material_id": "104", "title": "素材四", "rank": 4,
                "metrics": {"ctr": 0.4, "show_cnt": 400, "play_3s_rate": 0.5},
                "people_tags": ["都市银发"], "material_tags": ["商品展示"],
                "data_availability": {"metrics": {"available": True, "missing_reason": ""}},
            },
        ]
        selected = [
            {"rank": 1, "material_id": "101", "detailRecordPath": "normalized/detail-records/101.json"},
            {"rank": 4, "material_id": "104", "detailRecordPath": "normalized/detail-records/104.json"},
        ]
        details = {
            material_id: {
                "material_id": material_id,
                "high_points": [{"trend_name": "点击指数", "start_sec": 1, "end_sec": 2}],
                "loss_points": [{"trend_name": "流失指数", "start_sec": 0, "end_sec": 1, "loss_percent": 0.5}],
                "data_availability": {"trends": {"available": True, "missing_reason": ""}},
            }
            for material_id in ("101", "104")
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_input(root, records, selected, details)
            status = analysis.prepare_analysis(input_dir=root, output_dir=root / "diagnostic-analysis")
            data = json.loads((root / "diagnostic-analysis" / "report-data.json").read_text(encoding="utf-8"))
            prompt = (root / "diagnostic-analysis" / "yuntu-analysis-prompt.md").read_text(encoding="utf-8")

        self.assertEqual(status, 0)
        self.assertEqual(data["schemaVersion"], 7)
        self.assertEqual(data["candidatePool"]["count"], 4)
        self.assertEqual(data["candidatePool"]["metrics"]["ctr"]["median"], 0.25)
        self.assertEqual(data["industryTop1000Facts"]["sample_count"], 4)
        self.assertEqual(data["brandRankingFacts"]["brands"], {})
        self.assertEqual(data["audienceDashboard"]["sample"]["recordCount"], 4)
        self.assertEqual(
            {item["label"]: item["materialCount"] for item in data["audienceDashboard"]["dimensions"]["crowd"]["buckets"]},
            {"新锐白领": 2, "都市银发": 2},
        )
        self.assertEqual(data["materialFacts"][1]["metricComparison"]["ctr"]["tier"], "high")
        self.assertTrue(data["tagInsights"]["eligibleForAssociation"])
        self.assertEqual(data["trendSummary"]["byTrendName"]["点击指数"]["highPointCount"], 2)
        self.assertEqual(data["trendSummary"]["byTrendName"]["流失指数"]["lossPointCount"], 2)
        output_contract = next(
            line for line in prompt.splitlines() if line.startswith("输出必须是 JSON 对象")
        )
        for field in (
            "rankingOverview",
            "audienceInsights",
            "materialComparison",
            "materialDiagnoses",
            "competitorPatterns",
            "opportunityMap",
            "experimentMatrix",
            "overallConclusions",
        ):
            self.assertNotIn(field, output_contract)
        for field in (
            "topMaterialCombination",
            "chapter02Insights",
            "highlightDashboard",
            "materialDeepDives",
        ):
            self.assertIn(field, prompt)
        self.assertIn("数据不足以判断", prompt)

    def test_prepare_analysis_degrades_when_candidate_pool_is_too_small(self):
        analysis = load_module()
        records = [
            {"material_id": str(index), "title": "素材", "metrics": {"ctr": index / 10}, "people_tags": [], "material_tags": [], "data_availability": {"metrics": {"available": False, "missing_reason": "source_empty"}}}
            for index in range(1, 4)
        ]
        selected = [{"rank": 1, "material_id": "1", "detailRecordPath": "normalized/detail-records/1.json"}]
        details = {"1": {"material_id": "1", "high_points": [], "loss_points": [], "data_availability": {"trends": {"available": False, "missing_reason": "source_empty"}}}}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_input(root, records, selected, details)
            analysis.prepare_analysis(input_dir=root, output_dir=root / "diagnostic-analysis")
            data = json.loads((root / "diagnostic-analysis" / "report-data.json").read_text(encoding="utf-8"))

        self.assertFalse(data["tagInsights"]["eligibleForAssociation"])
        self.assertEqual(data["materialFacts"][0]["metricComparison"]["ctr"]["tier"], "observed")
        self.assertEqual(data["dataAvailabilitySummary"]["source_empty"], 2)

    def test_prepare_analysis_emits_report_scopes_for_ranking_and_successful_detail(self):
        analysis = load_module()
        records = [
            {
                "material_id": "101", "title": "素材一", "rank": 1,
                "metrics": {"ctr": 0.1}, "people_tags": [], "material_tags": [],
                "data_availability": {},
            },
            {
                "material_id": "102", "title": "素材二", "rank": 2,
                "metrics": {"ctr": 0.2}, "people_tags": [], "material_tags": [],
                "data_availability": {},
            },
        ]
        selected = [
            {"rank": 1, "material_id": "101", "detailRecordPath": "normalized/detail-records/101.json"},
        ]
        details = {
            "101": {
                "material_id": "101", "high_points": [], "loss_points": [],
                "data_availability": {},
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_input(root, records, selected, details)
            with mock.patch.object(analysis, "generate_standard_highlights_for_detail", return_value=[]):
                status = analysis.prepare_analysis(input_dir=root, output_dir=root / "diagnostic-analysis")
            data = json.loads((root / "diagnostic-analysis" / "report-data.json").read_text(encoding="utf-8"))

        self.assertEqual(status, 0)
        self.assertEqual(data["reportScopes"]["ranking"]["source_name"], "TOP1000 榜单素材")
        self.assertEqual(set(data["reportScopes"]), {"ranking", "detail"})
        self.assertEqual(data["reportScopes"]["ranking"]["sample_count"], 2)
        self.assertEqual(data["reportScopes"]["detail"]["sample_count"], 1)
        self.assertEqual(data["reportScopes"]["detail"]["success_count"], 1)
        self.assertEqual(data["reportScopes"]["detail"]["failed_count"], 1)

    def test_prepare_analysis_automatically_generates_standard_highlight_frames(self):
        analysis = load_module()
        records = [
            {"material_id": "1", "title": "素材", "metrics": {}, "people_tags": [], "material_tags": [], "data_availability": {}},
        ]
        selected = [{"rank": 1, "material_id": "1", "detailRecordPath": "normalized/detail-records/1.json"}]
        details = {"1": {"material_id": "1", "high_points": [], "loss_points": [], "data_availability": {}}}
        frames = [{"second": 0, "is_cover": True, "reasons": [{"type": "cover"}], "available": True, "relative_path": "highlights/1/01-000s.jpg"}]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_input(root, records, selected, details)
            with mock.patch.object(analysis, "generate_standard_highlights_for_detail", return_value=frames) as generate:
                analysis.prepare_analysis(input_dir=root, output_dir=root / "diagnostic-analysis")
            data = json.loads((root / "diagnostic-analysis" / "report-data.json").read_text(encoding="utf-8"))

        generate.assert_called_once_with(mock.ANY, root)
        self.assertEqual(data["materialFacts"][0]["highlightFrames"], frames)
        self.assertEqual(data["materialFacts"][0]["highlightFrameAvailability"], {"available": True, "missing_reason": ""})

    def test_prepare_analysis_writes_v4_model_facts_and_visual_assets(self):
        analysis = load_module()
        records = [{
            "material_id": "1", "title": "产品开盖展示", "rank": 1,
            "metrics": {"ctr": 0.2, "show_cnt": 100},
            "people_tags": ["新锐白领"], "material_tags": ["产品展示"],
            "data_availability": {
                "cpm": {"available": False, "missing_reason": "not_returned"},
            },
        }]
        selected = [{
            "rank": 1, "material_id": "1",
            "detailRecordPath": "normalized/detail-records/1.json",
        }]
        details = {"1": {
            "material_id": "1",
            "trend_series": [{
                "trend_name": "点击指数", "series": [{"second": 2, "value": 0.8}],
            }],
            "high_points": [], "loss_points": [], "data_availability": {},
        }}
        frames = [{
            "frame_ref": "highlight:1:click_peak:2", "second": 2,
            "frame_type": "click_peak", "peak_rank": 1, "click_value": 0.8,
            "available": True, "relative_path": "highlights/1/02-002s.jpg",
            "frame_source": "reused_local_extracted_frame",
        }]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_input(root, records, selected, details)
            with mock.patch.object(
                analysis, "generate_standard_highlights_for_detail", return_value=frames
            ):
                analysis.prepare_analysis(
                    input_dir=root, output_dir=root / "diagnostic-analysis"
                )
            unit_dir = root / "diagnostic-analysis" / "analysis-units"
            ranking = json.loads((unit_dir / "ranking-brand-input.json").read_text(encoding="utf-8"))
            audience = json.loads((unit_dir / "audience-marketing-input.json").read_text(encoding="utf-8"))
            highlight = json.loads((unit_dir / "highlight-input.json").read_text(encoding="utf-8"))
            deep_dive = json.loads((unit_dir / "material-deep-dive-input.json").read_text(encoding="utf-8"))
            prompt = (root / "diagnostic-analysis" / "yuntu-analysis-prompt.md").read_text(
                encoding="utf-8"
            )

        self.assertEqual(ranking["schemaVersion"], 4)
        self.assertEqual(
            ranking["evidence"]["industryTop1000Facts"]["materials"][0]["material_id"],
            "1",
        )
        self.assertNotIn(
            "cpm", ranking["evidence"]["industryTop1000Facts"]["metrics"]
        )
        self.assertEqual(
            audience["evidence"]["chapter02AiFacts"]["all"]["sampleCount"], 1
        )
        self.assertEqual(
            audience["evidence"]["chapter02AiFacts"]["all"]["marketingDashboard"]["tagCount"],
            1,
        )
        self.assertEqual(
            audience["evidence"]["chapter02AiFacts"]["all"]["marketingDashboard"]["topTags"],
            [{
                "tag": "产品展示",
                "rawTag": "产品展示",
                "count": 1,
                "materialCount": 1,
                "category": "其他",
            }],
        )
        self.assertEqual(
            highlight["evidence"]["visualAssets"][0]["frame_ref"],
            "highlight:1:click_peak:2",
        )
        self.assertEqual(
            highlight["evidence"]["visualAssets"][0]["image_path"],
            "../highlights/1/02-002s.jpg",
        )
        self.assertEqual(
            highlight["evidence"]["visualAssets"][0]["frame_source"],
            "reused_local_extracted_frame",
        )
        self.assertEqual(highlight["evidence"]["visualAssets"][0]["brand"], "其他品牌")
        self.assertEqual(
            deep_dive["evidence"]["materialFacts"][0]["material_id"], "1"
        )
        deep_fact = deep_dive["evidence"]["materialFacts"][0]
        self.assertEqual(
            set(deep_fact), {"material_id", "secondLevelBreakdown", "highlightFrames", "script", "evidenceIndex"}
        )
        self.assertEqual(
            set(deep_fact["highlightFrames"][0]),
            {"frame_ref", "second", "frame_type", "available", "image_path"},
        )
        self.assertEqual(
            deep_dive["evidence"]["materialFacts"][0]["secondLevelBreakdown"]["metrics"][2],
            {
                "trend_name": "点击指数",
                "available": True,
                "missing_reason": "",
                "points": [{"second": 2, "value": 0.8}],
                "high_points": [],
                "loss_points": [],
            },
        )
        self.assertIn("visualAssets", prompt)
        self.assertIn("实际查看每张成功 JPEG", prompt)
        self.assertIn("主体、人物、产品、动作、场景、构图和可见字幕", prompt)

    def test_prepare_analysis_does_not_emit_legacy_top_level_audience_rank_records(self):
        analysis = load_module()
        records = [{
            "material_id": "1", "title": "素材", "rank": 1,
            "metrics": {"ctr": 0.2, "show_cnt": 100},
            "people_tags": ["都市女性"], "material_tags": [], "data_availability": {},
        }]
        selected = [{"rank": 1, "material_id": "1", "detailRecordPath": "normalized/detail-records/1.json"}]
        details = {"1": {"material_id": "1", "high_points": [], "loss_points": [], "data_availability": {}}}
        captured = {}

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_input(root, records, selected, details)
            original = analysis._report_data

            def capture(fact_pack):
                captured.update(fact_pack)
                return original(fact_pack)

            with mock.patch.object(analysis, "_report_data", side_effect=capture):
                analysis.prepare_analysis(input_dir=root, output_dir=root / "diagnostic-analysis")

        self.assertNotIn("audienceRankRecords", captured)
        self.assertNotIn("audienceFacts", captured)
        self.assertNotIn("marketingFacts", captured)
        self.assertNotIn("highlightFrameFacts", captured)

    def test_prepare_analysis_does_not_duplicate_industry_facts_as_all_brand_facts(self):
        analysis = load_module()
        records = [{
            "material_id": "1", "title": "素材", "rank": 1,
            "metrics": {"ctr": 0.2, "show_cnt": 100},
            "people_tags": [], "material_tags": [], "data_availability": {},
        }]
        selected = [{"rank": 1, "material_id": "1", "detailRecordPath": "normalized/detail-records/1.json"}]
        details = {"1": {"material_id": "1", "high_points": [], "loss_points": [], "data_availability": {}}}
        captured = {}

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_input(root, records, selected, details)
            original = analysis._report_data

            def capture(fact_pack):
                captured.update(fact_pack)
                return original(fact_pack)

            with mock.patch.object(analysis, "_report_data", side_effect=capture):
                analysis.prepare_analysis(input_dir=root, output_dir=root / "diagnostic-analysis")

            ranking = json.loads(
                (root / "diagnostic-analysis" / "analysis-units" / "ranking-brand-input.json").read_text(encoding="utf-8")
            )
            report = json.loads((root / "diagnostic-analysis" / "report-data.json").read_text(encoding="utf-8"))

        self.assertNotIn("allBrandsRankingFacts", captured)
        self.assertNotIn("allBrandsRankingFacts", ranking["evidence"])
        self.assertNotIn("allBrandsRankingFacts", report)
        self.assertNotIn("rankingFacts", captured)
        self.assertNotIn("secondLevelFacts", captured)
        self.assertNotIn("highlightAllBrandFacts", captured)

    def test_highlight_schema_requires_structured_common_patterns(self):
        analysis = load_module()
        schema = analysis._highlight_output_schema()
        items = schema["properties"]["groups"]["items"]["properties"]["common_patterns"]["items"]
        self.assertEqual(items["type"], "object")
        self.assertNotIn("anyOf", items)

    def test_highlight_schema_declares_frame_understanding_and_dual_classification(self):
        analysis = load_module()

        schema = analysis._highlight_output_schema()

        self.assertIn("frameUnderstanding", schema["properties"])
        self.assertIn("standardClassification", schema["properties"])
        self.assertIn("batchClassification", schema["properties"])
        understanding = schema["properties"]["frameUnderstanding"]
        self.assertEqual(understanding["items"]["required"], [
            "frame_ref", "status", "subject", "visual_focus", "human_product_relation",
            "action", "composition", "information_expression", "failure_reason",
        ])
        self.assertEqual(
            schema["properties"]["batchClassification"]["properties"]["groups"]["items"]["properties"]["category"]["type"],
            "string",
        )

    def test_highlight_prompt_requires_understanding_before_batch_taxonomy(self):
        analysis = load_module()

        prompt = analysis._prompt_text(filters={"brands": ["燕之屋"]})

        self.assertIn("逐帧图片理解", prompt)
        self.assertIn("先完成同一批次全部成功高光帧的图片理解", prompt)
        self.assertIn("standardClassification", prompt)
        self.assertIn("batchClassification", prompt)

    def test_highlight_batch_taxonomy_requires_three_paired_insights(self):
        analysis = load_module()

        schema = analysis._highlight_output_schema()
        batch_group = schema["properties"]["batchClassification"]["properties"]["groups"]["items"]
        self.assertEqual(batch_group["properties"]["common_patterns"]["minItems"], 3)
        self.assertEqual(batch_group["properties"]["common_patterns"]["maxItems"], 3)
        self.assertEqual(batch_group["properties"]["derivative_directions"]["minItems"], 3)
        self.assertEqual(batch_group["properties"]["derivative_directions"]["maxItems"], 3)

        prompt = analysis._prompt_text(filters={"brands": ["燕之屋"]})
        self.assertIn("3 条共性洞察 + 3 条裂变方向", prompt)
        self.assertIn("改写动作、变体方式和验证指标", prompt)

    def test_highlight_prompt_requires_fine_grained_batch_taxonomy(self):
        analysis = load_module()

        prompt = analysis._prompt_text(filters={"brands": ["燕之屋"]})

        self.assertIn("n≤3", prompt)
        self.assertIn("2–3 类", prompt)
        self.assertIn("4≤n≤7", prompt)
        self.assertIn("3–6 类", prompt)
        self.assertIn("n≥8", prompt)
        self.assertIn("6–10 类", prompt)
        self.assertIn("其他1/其他2", prompt)
        self.assertIn("主体、动作或信息机制", prompt)
        self.assertIn("至少两个有意义类别", prompt)

        batch_group = analysis._highlight_output_schema()["properties"]["batchClassification"]["properties"]["groups"]["items"]
        self.assertEqual(
            batch_group["required"],
            ["category", "label", "rule", "frame_refs", "common_patterns", "derivative_directions"],
        )

    def test_script_prompt_requires_qianchuan_aligned_ordered_insights(self):
        analysis = load_module()

        prompt = analysis._prompt_text(filters={"brands": ["小仙炖"]})

        self.assertIn("scriptInsights` 固定输出 2 条脚本洞察", prompt)
        self.assertIn("一二级内容公式：", prompt)
        self.assertIn("脚本文案：", prompt)
        self.assertIn("一级/二级标签的高频结构", prompt)
        self.assertIn("完整脚本文案中的利益点", prompt)
        self.assertIn("每条洞察都必须包含 `title`、`summary`、`evidence` 和 `material_ids`", prompt)
        self.assertIn("没有对应事实时必须写“数据不足以判断”", prompt)

    def test_prepare_analysis_writes_report_projection_and_single_call_unit_inputs(self):
        analysis = load_module()
        records = [
            {
                "material_id": "1",
                "title": "五个女博士胶原蛋白素材",
                "rank": 1,
                "metrics": {
                    "show_cnt": 200,
                    "ctr": 0.2,
                    "cvr": 0.1,
                    "play_3s_rate": 0.4,
                },
                "people_tags": ["24-30", "女"],
                "material_tags": ["成分配方原料_胶原蛋白"],
                "data_availability": {},
            }
        ]
        selected = [
            {
                "rank": 1,
                "material_id": "1",
                "detailRecordPath": "normalized/detail-records/1.json",
            }
        ]
        details = {
            "1": {
                "material_id": "1",
                "trend_series": [
                    {
                        "trend_name": "点击指数",
                        "series": [{"second": 0, "value": 0.5}, {"second": 1, "value": 1.0}],
                    }
                ],
                "high_points": [
                    {"trend_name": "点击指数", "start_sec": 1, "end_sec": 1}
                ],
                "loss_points": [],
                "data_availability": {},
            }
        }
        frame = {
            "frame_ref": "highlight:1:cover:0",
            "second": 0,
            "is_cover": True,
            "frame_type": "cover",
            "peak_rank": None,
            "click_value": None,
            "reasons": [{"type": "cover"}],
            "available": True,
            "relative_path": "highlights/1/01-000s.jpg",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_input(root, records, selected, details)
            manifest_path = root / "batch-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["filters"]["brands"] = ["五个女博士"]
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
            )
            image = root / "highlights" / "1" / "01-000s.jpg"
            image.parent.mkdir(parents=True)
            image.write_bytes(b"jpeg")
            analysis.write_highlights_manifest(root, {"1": [frame]})

            analysis.prepare_analysis(
                input_dir=root, output_dir=root / "diagnostic-analysis"
            )

            output = root / "diagnostic-analysis"
            report = json.loads(
                (output / "report-data.json").read_text(encoding="utf-8")
            )
            units = output / "analysis-units"
            unit_manifest = json.loads(
                (units / "analysis-unit-manifest.json").read_text(encoding="utf-8")
            )
            output_schema = json.loads(
                (output / "yuntu-ai-analysis.schema.json").read_text(encoding="utf-8")
            )
            ranking_text = (units / "ranking-brand-input.json").read_text(
                encoding="utf-8"
            )
            ranking = json.loads(ranking_text)
            audience = json.loads(
                (units / "audience-marketing-input.json").read_text(encoding="utf-8")
            )
            highlight = json.loads(
                (units / "highlight-input.json").read_text(encoding="utf-8")
            )
            deep_dive = json.loads(
                (units / "material-deep-dive-input.json").read_text(encoding="utf-8")
            )
            prompt = (output / "yuntu-analysis-prompt.md").read_text(encoding="utf-8")

        self.assertFalse((output / "yuntu-analysis-data.json").exists())
        self.assertEqual(report["chapter02AiFacts"]["scopeOrder"], ["all", "五个女博士"])
        self.assertTrue(
            all(
                report["chapter02AiFacts"][scope] == {}
                for scope in report["chapter02AiFacts"]["scopeOrder"]
            )
        )
        self.assertNotIn("visualAssets", report)
        self.assertIn("chapter02Facts", report)
        self.assertIn("materialFacts", report)
        self.assertNotIn("materials", report["industryTop1000Facts"])
        report_brand_facts = report["brandRankingFacts"]["brands"]["五个女博士"]
        self.assertEqual(report_brand_facts["source_scope"], "brand_in_top1000")
        self.assertEqual(report_brand_facts["sample_count"], 1)
        self.assertEqual(len(report_brand_facts["materials"]), 1)
        self.assertEqual(
            len(ranking_text.splitlines()),
            1,
        )
        self.assertEqual(unit_manifest["executionMode"], "single_model_call")
        self.assertEqual(
            unit_manifest["outputSchema"]["path"],
            "yuntu-ai-analysis.schema.json",
        )
        self.assertEqual(output_schema["type"], "object")
        self.assertEqual(output_schema["properties"]["scriptInsights"]["minItems"], 2)
        self.assertEqual(output_schema["properties"]["scriptInsights"]["maxItems"], 2)
        self.assertIn("keywordCloudReview", output_schema["properties"])
        self.assertIn("keywordCloudInsight", output_schema["properties"])
        self.assertEqual(
            output_schema["properties"]["chapter02Insights"]["required"],
            ["scopeOrder", "scopes"],
        )
        scope_schema = output_schema["properties"]["chapter02Insights"]["properties"]["scopes"]["properties"]["all"]
        self.assertEqual(scope_schema["required"], ["audienceSummary", "marketingSummary"])
        self.assertEqual(
            set(scope_schema["properties"]),
            {"audienceSummary", "marketingSummary"},
        )
        self.assertEqual(
            set(output_schema["properties"]["chapter02Insights"]["properties"]["scopes"]["properties"]),
            {"all", "五个女博士"},
        )
        self.assertIn(
            "groups",
            output_schema["properties"]["highlightDashboard"]["properties"],
        )
        direction_schema = output_schema["properties"]["highlightDashboard"][
            "properties"
        ]["groups"]["items"]["properties"]["derivative_directions"]["items"]
        self.assertEqual(
            direction_schema["required"], ["title", "body", "frame_refs"]
        )
        deep_dive_schema = output_schema["properties"]["materialDeepDives"]["items"]
        self.assertEqual(
            deep_dive_schema["required"], ["material_id", "frame_observations"]
        )
        self.assertEqual(
            set(deep_dive_schema["properties"]),
            {"material_id", "frame_observations", "scriptAnalysis"},
        )
        self.assertEqual(
            [item["outputField"] for item in unit_manifest["units"]],
            [
                "topMaterialCombination",
                "chapter02Insights",
                "scriptInsights",
                "highlightDashboard",
                "materialDeepDives",
            ],
        )
        self.assertEqual(ranking["outputField"], "topMaterialCombination")
        self.assertEqual(ranking["schemaVersion"], 4)
        brand_item_schema = ranking["outputSchema"]["properties"][
            "brandConclusions"
        ]["items"]
        self.assertNotIn(
            "executiveSummary",
            ranking["outputSchema"]["properties"],
        )
        self.assertEqual(
            set(ranking["outputSchema"]["properties"]), {"brandConclusions", "allBrandsConclusion"}
        )
        self.assertEqual(ranking["outputSchema"]["required"], ["brandConclusions"])
        self.assertNotIn("peopleSummary", brand_item_schema["required"])
        self.assertEqual(
            brand_item_schema["properties"]["classificationSource"]["enum"],
            ["title_rule", "runtime_title_rule"],
        )
        self.assertEqual(
            set(ranking["evidence"]),
            {
                "reportScope",
                "industryTop1000Facts",
                "brandRankingFacts",
            },
        )
        self.assertIn("industryTop1000Facts", ranking["evidence"])
        self.assertNotIn("chapter02AiFacts", ranking["evidence"])
        self.assertEqual(audience["outputField"], "chapter02Insights")
        self.assertEqual(set(audience["evidence"]), {"chapter02AiFacts"})
        self.assertIn("chapter02AiFacts", audience["evidence"])
        self.assertNotIn("industryTop1000Facts", audience["evidence"])
        self.assertEqual(highlight["outputField"], "highlightDashboard")
        self.assertEqual(
            set(highlight["evidence"]),
            {"reportScope", "visualAssets", "frameUnderstandingContract", "dataLimitations"},
        )
        self.assertEqual(highlight["evidence"]["visualAssets"][0]["frame_ref"], frame["frame_ref"])
        self.assertEqual(deep_dive["outputField"], "materialDeepDives")
        self.assertEqual(
            set(deep_dive["evidence"]), {"reportScope", "materialFacts"}
        )
        self.assertEqual(deep_dive["evidence"]["materialFacts"][0]["material_id"], "1")
        self.assertIn("analysis-unit-manifest.json", prompt)
        self.assertIn("同一次分析任务", prompt)
        self.assertIn("ranking-brand-input.json` 的 `outputSchema", prompt)
        self.assertIn(
            '`classificationSource` 只能是 `title_rule` 或 `runtime_title_rule`',
            prompt,
        )
        self.assertNotIn("brandComparisonConclusion", prompt)
        self.assertNotIn("executiveSummary", prompt)
        self.assertNotIn("peopleSummary", prompt.split("02 章必须读取", 1)[0])
        self.assertIn("每个 `dataSummary` 控制在 6 至 10 句", prompt)
        self.assertIn("分别输出两个自然段，不把两个字段合并或重复成一个段落", prompt)
        self.assertIn("第一章不输出人群维度分析", prompt)
        self.assertIn("只分析该品牌在行业 TOP1000 内匹配到的全部素材聚合结果", prompt)
        self.assertIn("不得引用单条素材的素材 ID、标题、排名或指标", prompt)
        self.assertIn("素材 ID 只保留在 `evidence`、`material_ids` 和爆款事实引用中", prompt)
        for metric in ("曝光", "CTR", "CVR", "3 秒播放率"):
            self.assertIn(metric, prompt)
        self.assertNotIn("读取同目录的 `yuntu-analysis-data.json`", prompt)
        self.assertNotIn("second_level_observations", prompt)
        self.assertNotIn("evidence_seconds", prompt)

    def test_prepare_analysis_records_standard_highlight_failure_states(self):
        analysis = load_module()
        records = [
            {"material_id": "1", "title": "素材", "metrics": {}, "people_tags": [], "material_tags": [], "data_availability": {}},
        ]
        selected = [{"rank": 1, "material_id": "1", "detailRecordPath": "normalized/detail-records/1.json"}]
        details = {"1": {"material_id": "1", "high_points": [], "loss_points": [], "data_availability": {}}}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_input(root, records, selected, details)
            frames = [{"second": 0, "frame_type": "cover", "available": False, "failure_reason": "missing_video_url"}]
            with mock.patch.object(analysis, "generate_standard_highlights_for_detail", return_value=frames) as generate:
                analysis.prepare_analysis(input_dir=root, output_dir=root / "diagnostic-analysis")
            data = json.loads((root / "diagnostic-analysis" / "report-data.json").read_text(encoding="utf-8"))
            highlight = json.loads(
                (
                    root
                    / "diagnostic-analysis"
                    / "analysis-units"
                    / "highlight-input.json"
                ).read_text(encoding="utf-8")
            )

        generate.assert_called_once_with(mock.ANY, root)
        self.assertEqual(data["materialFacts"][0]["highlightFrames"], frames)
        self.assertEqual(
            highlight["evidence"]["dataLimitations"],
            [{
                "material_id": "1",
                "field": "highlightFrames.0",
                "reason": "missing_video_url",
            }],
        )
        self.assertEqual(
            data["materialFacts"][0]["highlightFrameAvailability"],
            {"available": False, "missing_reason": "missing_video_url"},
        )

    def test_prepare_analysis_reuses_complete_streamed_highlights_without_regeneration(self):
        analysis = load_module()
        records = [
            {"material_id": "1", "title": "素材", "metrics": {}, "people_tags": [], "material_tags": [], "data_availability": {}},
        ]
        selected = [{"rank": 1, "material_id": "1", "detailRecordPath": "normalized/detail-records/1.json"}]
        details = {"1": {"material_id": "1", "trend_series": [], "high_points": [], "loss_points": [], "data_availability": {}}}
        frames = [{
            "frame_ref": "highlight:1:cover:0", "second": 0, "is_cover": True,
            "frame_type": "cover", "peak_rank": None, "click_value": None,
            "reasons": [{"type": "cover"}], "available": True,
            "relative_path": "highlights/1/01-000s.jpg",
        }]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_input(root, records, selected, details)
            image = root / "highlights" / "1" / "01-000s.jpg"
            image.parent.mkdir(parents=True)
            image.write_bytes(b"jpeg")
            analysis.write_highlights_manifest(root, {"1": frames})
            with mock.patch.object(analysis, "generate_standard_highlights_for_detail") as generate:
                analysis.prepare_analysis(input_dir=root, output_dir=root / "diagnostic-analysis")
            data = json.loads((root / "diagnostic-analysis" / "report-data.json").read_text(encoding="utf-8"))

        generate.assert_not_called()
        self.assertEqual(data["materialFacts"][0]["highlightFrames"], frames)

    def test_prepare_analysis_writes_top_material_combination_and_prompt_contract(self):
        analysis = load_module()
        records = [
            {
                "material_id": "1",
                "title": "五个女博士富铁软糖",
                "rank": 1,
                "metrics": {"show_cnt": 200, "ctr": 0.2},
                "people_tags": ["24-30", "女"],
                "material_tags": ["成分配方原料_铁元素"],
                "data_availability": {},
            },
            {
                "material_id": "2",
                "title": "万益蓝 益生菌素材",
                "rank": 2,
                "metrics": {"show_cnt": 300, "ctr": 0.3},
                "people_tags": ["36-40"],
                "material_tags": [],
                "data_availability": {},
            },
        ]
        selected = [
            {
                "rank": 1,
                "material_id": "1",
                "detailRecordPath": "normalized/detail-records/1.json",
            }
        ]
        details = {
            "1": {
                "material_id": "1",
                "high_points": [],
                "loss_points": [],
                "data_availability": {},
            }
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_input(root, records, selected, details)
            analysis.prepare_analysis(
                input_dir=root, output_dir=root / "diagnostic-analysis"
            )
            ranking = json.loads(
                (root / "diagnostic-analysis" / "analysis-units" / "ranking-brand-input.json").read_text(
                    encoding="utf-8"
                )
            )
            prompt = (root / "diagnostic-analysis" / "yuntu-analysis-prompt.md").read_text(
                encoding="utf-8"
            )

        self.assertEqual(
            ranking["evidence"]["industryTop1000Facts"]["materials"][0][
                "material_id"
            ],
                    "2",
        )
        self.assertEqual(
            set(ranking["evidence"]["brandRankingFacts"]["brands"]),
            {"万益蓝/WONDERLAB", "五个女博士"},
        )
        self.assertIn("topMaterialCombination", prompt)
        self.assertIn("运行时品牌匹配", prompt)
        self.assertNotIn("brandComparisonConclusion", prompt)
        self.assertIn("title", prompt)
        self.assertIn("dataSummary", prompt)
        self.assertIn("chapter02Insights", prompt)
        self.assertNotIn("industryTop1000Facts", prompt)
        self.assertNotIn("brandRankingFacts", prompt)
        self.assertIn("同一合并 TOP1000", prompt)
        self.assertNotIn("成功秒级拆解素材集合", prompt)
        self.assertNotIn(
            "人群标签是重叠标签，不是真实人群分布，不能相加为 100%。",
            prompt,
        )
        self.assertIn("不进入用户可见正文", prompt)
        self.assertIn("不得写执行过程", prompt)
        self.assertIn("事实锚点 -> 业务判断 -> 形成原因/内容机制 -> 内容策略 -> 下一步验证", prompt)
        self.assertIn("少量关键事实锚点 + 多句分析判断", prompt)
        self.assertIn("为什么值得保留或改写", prompt)
        self.assertIn("下一步如何验证", prompt)
        self.assertIn("本次品牌榜单分析范围为行业 TOP1000 内按品牌匹配的全部素材", prompt)
        self.assertIn("chapter02AiFacts", prompt)
        self.assertIn("audienceSummary", prompt)
        self.assertIn("marketingSummary", prompt)
        self.assertIn("每个维度只输出一段", prompt)
        self.assertIn("八大人群、性别和年龄三个维度", prompt)
        self.assertIn("至少 4 句", prompt)
        self.assertIn("每个品牌对象及 `allBrandsConclusion` 都必须分别输出 `dataSummary` 与 `hotMaterialInsight`", prompt)
        self.assertIn("为什么形成这种表现", prompt)
        self.assertIn("如何转化为内容策略", prompt)
        self.assertNotIn("渲染层会自动添加“1. ”、“2. ”等编号", prompt)
        self.assertIn("总结性标题", prompt)
        self.assertIn("标点", prompt)
        self.assertIn("编号", prompt)
        self.assertIn("固定提示词模板", prompt)
        self.assertNotIn("至少 80 个中文字符", prompt)
        self.assertNotIn("至少 4 条", prompt)
        self.assertIn("portrait", prompt)
        self.assertIn("product", prompt)
        self.assertIn("other", prompt)
        self.assertIn("共性洞察", prompt)
        self.assertIn("裂变方向", prompt)

    def test_prepare_analysis_writes_chapter02_scope_bundle_and_marketing_dashboard(self):
        analysis = load_module()
        records = [
            {
                "material_id": "1",
                "title": "五个女博士富铁软糖",
                "rank": 1,
                "metrics": {"show_cnt": 200, "ctr": 0.2},
                "people_tags": ["24-30", "女"],
                "material_tags": ["成分配方原料_铁元素", "促销利益_买一送一"],
                "data_availability": {},
            },
            {
                "material_id": "2",
                "title": "万益蓝 益生菌素材",
                "rank": 2,
                "metrics": {"show_cnt": 300, "ctr": 0.3},
                "people_tags": ["36-40"],
                "material_tags": ["成分配方原料_益生菌"],
                "data_availability": {},
            },
        ]
        selected = [{"rank": 1, "material_id": "1", "detailRecordPath": "normalized/detail-records/1.json"}]
        details = {"1": {"material_id": "1", "high_points": [], "loss_points": [], "data_availability": {}}}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_input(root, records, selected, details)
            analysis.prepare_analysis(input_dir=root, output_dir=root / "diagnostic-analysis")
            data = json.loads((root / "diagnostic-analysis" / "report-data.json").read_text(encoding="utf-8"))

        chapter = data["chapter02Facts"]
        self.assertEqual(chapter["scopeOrder"][0], "all")
        self.assertEqual(chapter["all"]["label"], "全量 TOP1000")
        self.assertIn("五个女博士", chapter["scopeOrder"])
        self.assertEqual(chapter["all"]["marketingDashboard"]["tagCount"], 3)
        self.assertEqual(chapter["all"]["marketingDashboard"]["occurrenceCount"], 3)
        self.assertEqual(chapter["五个女博士"]["marketingDashboard"]["tagCount"], 2)

    def test_prepare_analysis_uses_full_brand_scope_for_chapter02_ai(self):
        analysis = load_module()
        records = [
            {
                "material_id": "1", "title": "五个女博士富铁软糖", "rank": 1,
                "metrics": {"show_cnt": 200, "ctr": 0.2},
                "people_tags": ["24-30"], "material_tags": ["成分配方原料_铁元素"],
                "data_availability": {},
            },
            {
                "material_id": "2", "title": "五个女博士胶原蛋白", "rank": 2,
                "metrics": {"show_cnt": 180, "ctr": 0.18},
                "people_tags": ["31-35"], "material_tags": ["功效功能_补充营养"],
                "data_availability": {},
            },
        ]
        selected = [{"rank": 1, "material_id": "1", "detailRecordPath": "normalized/detail-records/1.json"}]
        details = {"1": {"material_id": "1", "high_points": [], "loss_points": [], "data_availability": {}}}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_input(root, records, selected, details)
            manifest_path = root / "batch-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["filters"]["brands"] = ["五个女博士"]
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            analysis.prepare_analysis(input_dir=root, output_dir=root / "diagnostic-analysis")
            report = json.loads((root / "diagnostic-analysis" / "report-data.json").read_text(encoding="utf-8"))
            audience = json.loads(
                (root / "diagnostic-analysis" / "analysis-units" / "audience-marketing-input.json").read_text(
                    encoding="utf-8"
                )
            )
            ranking = json.loads(
                (root / "diagnostic-analysis" / "analysis-units" / "ranking-brand-input.json").read_text(
                    encoding="utf-8"
                )
            )
            prompt = (root / "diagnostic-analysis" / "yuntu-analysis-prompt.md").read_text(encoding="utf-8")

        scope = ranking["evidence"]["brandRankingFacts"]["brands"]["五个女博士"]
        self.assertEqual(scope["sample_count"], 2)
        self.assertNotIn("cpm", scope["metrics"])
        self.assertEqual(report["chapter02Facts"]["五个女博士"]["audienceDashboard"]["sample"]["recordCount"], 2)
        self.assertEqual(audience["evidence"]["chapter02AiFacts"]["五个女博士"]["sampleCount"], 2)
        self.assertIn("行业 TOP1000 内按品牌匹配的全部素材", prompt)
        self.assertNotIn("CPM", prompt)

    def test_prepare_analysis_keeps_chapter02_chart_facts_full_for_brand_scope(self):
        analysis = load_module()
        records = [
            {
                "material_id": str(index), "title": f"五个女博士素材{index}", "rank": index,
                "metrics": {"show_cnt": 400 - index, "ctr": 0.1},
                "people_tags": ["24-30"], "material_tags": ["成分配方原料_铁元素"],
                "data_availability": {},
            }
            for index in range(1, 4)
        ]
        selected = [{"rank": 1, "material_id": "1", "detailRecordPath": "normalized/detail-records/1.json"}]
        details = {"1": {"material_id": "1", "high_points": [], "loss_points": [], "data_availability": {}}}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_input(root, records, selected, details)
            manifest_path = root / "batch-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["filters"]["brands"] = ["五个女博士"]
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            analysis.prepare_analysis(
                input_dir=root,
                output_dir=root / "diagnostic-analysis",
            )
            report = json.loads((root / "diagnostic-analysis" / "report-data.json").read_text(encoding="utf-8"))
            ranking = json.loads(
                (root / "diagnostic-analysis" / "analysis-units" / "ranking-brand-input.json").read_text(encoding="utf-8")
            )
            audience = json.loads(
                (root / "diagnostic-analysis" / "analysis-units" / "audience-marketing-input.json").read_text(encoding="utf-8")
            )

        self.assertEqual(ranking["evidence"]["brandRankingFacts"]["brands"]["五个女博士"]["sample_count"], 3)
        self.assertEqual(audience["evidence"]["chapter02AiFacts"]["五个女博士"]["sampleCount"], 3)
        self.assertEqual(report["chapter02Facts"]["五个女博士"]["sampleCount"], 3)
        self.assertEqual(
            report["chapter02Facts"]["五个女博士"]["audienceDashboard"]["sample"]["recordCount"],
            3,
        )

    def test_second_level_breakdown_keeps_five_yuntu_indices_in_fixed_order(self):
        analysis = load_module()
        detail = {
            "trend_series": [
                {"trend_name": "点击指数", "series": [{"second": 2, "value": 3}, {"second": 0, "value": 1}]},
                {"trend_name": "点赞指数", "series": [{"second": 0, "value": 2}]},
                {"trend_name": "评论指数", "series": [{"second": 1, "value": 4}]},
            ],
            "high_points": [{"trend_name": "点击指数", "start_sec": 2, "end_sec": 2}],
            "loss_points": [{"trend_name": "点击指数", "start_sec": 0, "end_sec": 1, "loss_percent": 0.2}],
            "data_availability": {"trends": {"available": True, "missing_reason": ""}},
        }

        breakdown = analysis._second_level_breakdown(detail)

        self.assertEqual(
            [metric["trend_name"] for metric in breakdown["metrics"]],
            ["点赞指数", "流失指数", "点击指数", "互动指数", "评论指数"],
        )
        click = breakdown["metrics"][2]
        self.assertTrue(click["available"])
        self.assertEqual(click["points"], [{"second": 0, "value": 1}, {"second": 2, "value": 3}])
        self.assertEqual(click["high_points"], [{"start_sec": 2, "end_sec": 2}])
        self.assertEqual(click["loss_points"], [{"start_sec": 0, "end_sec": 1, "loss_percent": 0.2}])
        self.assertFalse(breakdown["metrics"][1]["available"])
        self.assertEqual(breakdown["metrics"][1]["missing_reason"], "trend_not_returned")


if __name__ == "__main__":
    unittest.main()
