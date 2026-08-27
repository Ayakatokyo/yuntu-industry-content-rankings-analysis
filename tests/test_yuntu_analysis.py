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
            ):
                self.assertTrue((output / relative_path).is_file(), relative_path)

    def test_prompt_template_is_loaded_and_runtime_scope_is_injected(self):
        analysis = load_module()

        template = analysis.PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
        prompt = analysis._prompt_text(
            brand_top_n=18,
            filters={"brands": ["万益蓝", "燕之屋"]},
        )

        self.assertIn("__BRAND_SCOPE_LABEL__", template)
        self.assertIn("__BRANDS__", template)
        self.assertIn("__SCOPE_LABELS__", template)
        self.assertIn("Top 18", prompt)
        self.assertIn("万益蓝、燕之屋", prompt)
        self.assertIn("all（全量 TOP1000）、万益蓝、燕之屋", prompt)
        self.assertNotIn("__BRAND_SCOPE_LABEL__", prompt)
        self.assertNotIn("__BRANDS__", prompt)
        self.assertNotIn("__SCOPE_LABELS__", prompt)

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
        self.assertEqual(data["schemaVersion"], 4)
        self.assertEqual(data["candidatePool"]["count"], 4)
        self.assertEqual(data["candidatePool"]["metrics"]["ctr"]["median"], 0.25)
        self.assertEqual(data["industryTop1000Facts"]["sample_count"], 4)
        self.assertEqual(data["brandTopNFacts"]["brands"], {})
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

        self.assertEqual(ranking["schemaVersion"], 2)
        self.assertEqual(
            ranking["evidence"]["industryTop1000Facts"]["materials"][0]["material_id"],
            "1",
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
        self.assertEqual(
            deep_dive["evidence"]["materialFacts"][0]["material_id"], "1"
        )
        self.assertEqual(
            deep_dive["evidence"]["materialFacts"][0]["material_tags"],
            ["产品展示"],
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
        self.assertEqual(
            report["brandTopNFacts"]["brands"]["五个女博士"],
            {"source_scope": "brand_top_n"},
        )
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
        self.assertEqual(
            output_schema["properties"]["chapter02Insights"]["required"],
            ["scopeOrder", "scopes"],
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
        self.assertEqual(
            [item["outputField"] for item in unit_manifest["units"]],
            [
                "topMaterialCombination",
                "chapter02Insights",
                "highlightDashboard",
                "materialDeepDives",
            ],
        )
        self.assertEqual(ranking["outputField"], "topMaterialCombination")
        self.assertEqual(ranking["schemaVersion"], 2)
        brand_item_schema = ranking["outputSchema"]["properties"][
            "brandConclusions"
        ]["items"]
        self.assertEqual(
            brand_item_schema["properties"]["classificationSource"]["enum"],
            ["title_rule", "runtime_title_rule"],
        )
        comparison_evidence_schema = ranking["outputSchema"]["properties"][
            "brandComparisonConclusion"
        ]["properties"]["evidence"]["items"]
        self.assertEqual(
            comparison_evidence_schema["required"],
            ["brand", "metric", "value"],
        )
        self.assertEqual(
            set(ranking["evidence"]),
            {"reportScope", "industryTop1000Facts", "brandTopNFacts"},
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
            {"reportScope", "visualAssets", "dataLimitations"},
        )
        self.assertEqual(highlight["evidence"]["visualAssets"][0]["frame_ref"], frame["frame_ref"])
        self.assertEqual(deep_dive["outputField"], "materialDeepDives")
        self.assertEqual(
            set(deep_dive["evidence"]), {"reportScope", "materialFacts"}
        )
        self.assertEqual(deep_dive["evidence"]["materialFacts"][0]["material_id"], "1")
        self.assertIn("analysis-unit-manifest.json", prompt)
        self.assertIn("同一次模型调用", prompt)
        self.assertIn("ranking-brand-input.json` 的 `outputSchema", prompt)
        self.assertIn(
            '`classificationSource` 只能是 `title_rule` 或 `runtime_title_rule`',
            prompt,
        )
        self.assertIn(
            '`brandComparisonConclusion.evidence` 必须是对象数组',
            prompt,
        )
        self.assertIn('`brand`、`metric`、`value`', prompt)
        self.assertNotIn("读取同目录的 `yuntu-analysis-data.json`", prompt)

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
            set(ranking["evidence"]["brandTopNFacts"]["brands"]),
            {"万益蓝/WONDERLAB", "五个女博士"},
        )
        self.assertIn("topMaterialCombination", prompt)
        self.assertIn("运行时品牌匹配", prompt)
        self.assertIn("brandComparisonConclusion", prompt)
        self.assertIn("title", prompt)
        self.assertIn("dataSummary", prompt)
        self.assertIn("chapter02Insights", prompt)
        self.assertIn("industryTop1000Facts", prompt)
        self.assertIn("brandTopNFacts", prompt)
        self.assertIn("同一合并 TOP1000", prompt)
        self.assertNotIn("成功秒级拆解素材集合", prompt)
        self.assertNotIn(
            "人群标签是重叠标签，不是真实人群分布，不能相加为 100%。",
            prompt,
        )
        self.assertIn("不进入用户可见正文", prompt)
        self.assertIn("不得写执行过程", prompt)
        self.assertIn("事实锚点 -> 业务判断 -> 下一步验证", prompt)
        self.assertIn("少量关键事实锚点 + 多句分析判断", prompt)
        self.assertIn("为什么值得保留或改写", prompt)
        self.assertIn("下一步如何验证", prompt)
        self.assertIn("本次品牌榜单分析范围为Top 30", prompt)
        self.assertIn("chapter02AiFacts", prompt)
        self.assertIn("audienceSummary", prompt)
        self.assertIn("marketingSummary", prompt)
        self.assertIn("总结性标题", prompt)
        self.assertIn("标点", prompt)
        self.assertIn("编号", prompt)
        self.assertIn("固定提示词模板", prompt)
        self.assertNotIn("至少 80 个中文字符", prompt)
        self.assertNotIn("至少 4 条", prompt)
        self.assertIn("portrait、product、other", prompt)
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

    def test_prepare_analysis_defaults_brand_ai_scope_to_top_30(self):
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

        scope = ranking["evidence"]["brandTopNFacts"]["brands"]["五个女博士"]
        self.assertEqual(ranking["evidence"]["brandTopNFacts"]["requested_top_n"], 30)
        self.assertEqual(scope["sample_count"], 2)
        self.assertEqual(report["chapter02Facts"]["五个女博士"]["audienceDashboard"]["sample"]["recordCount"], 2)
        self.assertEqual(audience["evidence"]["chapter02AiFacts"]["五个女博士"]["sampleCount"], 2)
        self.assertIn("Top 30", prompt)

    def test_prepare_analysis_keeps_chapter02_dashboard_full_when_brand_ai_uses_top_n(self):
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
                brand_top_n=1,
            )
            report = json.loads((root / "diagnostic-analysis" / "report-data.json").read_text(encoding="utf-8"))
            ranking = json.loads(
                (root / "diagnostic-analysis" / "analysis-units" / "ranking-brand-input.json").read_text(encoding="utf-8")
            )
            audience = json.loads(
                (root / "diagnostic-analysis" / "analysis-units" / "audience-marketing-input.json").read_text(encoding="utf-8")
            )

        self.assertEqual(ranking["evidence"]["brandTopNFacts"]["brands"]["五个女博士"]["sample_count"], 1)
        self.assertEqual(audience["evidence"]["chapter02AiFacts"]["五个女博士"]["sampleCount"], 1)
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
