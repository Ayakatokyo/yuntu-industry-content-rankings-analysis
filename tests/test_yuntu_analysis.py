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
            data = json.loads((root / "diagnostic-analysis" / "yuntu-analysis-data.json").read_text(encoding="utf-8"))
            prompt = (root / "diagnostic-analysis" / "yuntu-analysis-prompt.md").read_text(encoding="utf-8")

        self.assertEqual(status, 0)
        self.assertEqual(data["schemaVersion"], 4)
        self.assertEqual(data["candidatePool"]["count"], 4)
        self.assertEqual(len(data["audienceTopNRecords"]), 4)
        audience_topn = {
            item["material_id"]: item["people_tags"]
            for item in data["audienceTopNRecords"]
        }
        self.assertEqual(audience_topn["101"], ["新锐白领"])
        self.assertEqual(audience_topn["104"], ["都市银发"])
        self.assertEqual(data["candidatePool"]["metrics"]["ctr"]["median"], 0.25)
        self.assertEqual(data["audienceDashboard"]["sample"]["recordCount"], 4)
        self.assertEqual(
            {item["label"]: item["materialCount"] for item in data["audienceDashboard"]["dimensions"]["crowd"]["buckets"]},
            {"新锐白领": 2, "都市银发": 2},
        )
        self.assertEqual(data["materialFacts"][1]["metricComparison"]["ctr"]["tier"], "high")
        self.assertTrue(data["tagInsights"]["eligibleForAssociation"])
        self.assertEqual(data["trendSummary"]["byTrendName"]["点击指数"]["highPointCount"], 2)
        self.assertEqual(data["trendSummary"]["byTrendName"]["流失指数"]["lossPointCount"], 2)
        self.assertIn("xiaoxianDunOpportunityMap", prompt)
        self.assertIn("experimentMatrix", prompt)
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
            data = json.loads((root / "diagnostic-analysis" / "yuntu-analysis-data.json").read_text(encoding="utf-8"))

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
            with mock.patch.object(analysis, "generate_standard_highlights", return_value={"101": []}):
                status = analysis.prepare_analysis(input_dir=root, output_dir=root / "diagnostic-analysis")
            data = json.loads((root / "diagnostic-analysis" / "yuntu-analysis-data.json").read_text(encoding="utf-8"))

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
            with mock.patch.object(analysis, "generate_standard_highlights", return_value={"1": frames}) as generate:
                analysis.prepare_analysis(input_dir=root, output_dir=root / "diagnostic-analysis")
            data = json.loads((root / "diagnostic-analysis" / "yuntu-analysis-data.json").read_text(encoding="utf-8"))

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
                analysis, "generate_standard_highlights", return_value={"1": frames}
            ):
                analysis.prepare_analysis(
                    input_dir=root, output_dir=root / "diagnostic-analysis"
                )
            data = json.loads(
                (root / "diagnostic-analysis" / "yuntu-analysis-data.json").read_text(
                    encoding="utf-8"
                )
            )
            prompt = (root / "diagnostic-analysis" / "yuntu-analysis-prompt.md").read_text(
                encoding="utf-8"
            )

        self.assertEqual(data["schemaVersion"], 4)
        self.assertEqual(data["rankingFacts"]["materials"][0]["material_id"], "1")
        self.assertTrue(data["audienceFacts"]["labelsMayOverlap"])
        self.assertEqual(
            data["marketingFacts"]["materials"][0]["material_tags"], ["产品展示"]
        )
        self.assertEqual(data["secondLevelFacts"]["materials"][0]["material_id"], "1")
        self.assertEqual(
            data["highlightFrameFacts"][0]["frame_ref"], "highlight:1:click_peak:2"
        )
        self.assertEqual(
            data["visualAssets"][0]["image_path"], "highlights/1/02-002s.jpg"
        )
        self.assertEqual(
            data["visualAssets"][0]["frame_source"],
            "reused_local_extracted_frame",
        )
        self.assertEqual(data["dataLimitations"][0]["reason"], "not_returned")
        self.assertIn("visualAssets", prompt)
        self.assertIn("实际查看每张成功 JPEG", prompt)

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
            with mock.patch.object(analysis, "generate_standard_highlights", return_value={"1": frames}) as generate:
                analysis.prepare_analysis(input_dir=root, output_dir=root / "diagnostic-analysis")
            data = json.loads((root / "diagnostic-analysis" / "yuntu-analysis-data.json").read_text(encoding="utf-8"))

        generate.assert_called_once_with(mock.ANY, root)
        self.assertEqual(data["materialFacts"][0]["highlightFrames"], frames)
        self.assertEqual(
            data["materialFacts"][0]["highlightFrameAvailability"],
            {"available": False, "missing_reason": "missing_video_url"},
        )

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
            data = json.loads(
                (root / "diagnostic-analysis" / "yuntu-analysis-data.json").read_text(
                    encoding="utf-8"
                )
            )
            prompt = (root / "diagnostic-analysis" / "yuntu-analysis-prompt.md").read_text(
                encoding="utf-8"
            )

        self.assertEqual(
            data["topMaterialCombination"]["overall"]["topMaterials"][0][
                "material_id"
            ],
            "1",
        )
        self.assertEqual(
            set(data["topMaterialCombination"]["brands"]),
            {"五个女博士"},
        )
        self.assertIn("topMaterialCombination", prompt)
        self.assertIn("标题匹配归属", prompt)
        self.assertIn("brandComparisonConclusion", prompt)
        self.assertIn("dimension", prompt)
        self.assertIn("dataSummary", prompt)
        self.assertIn("peopleSummary", prompt)
        self.assertIn("marketingSummary", prompt)
        self.assertIn("成功秒级拆解素材集合", prompt)
        self.assertNotIn("品牌筛选 TOP30", prompt)
        self.assertIn(
            "人群标签是重叠标签，不是真实人群分布，不能相加为 100%。",
            prompt,
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
