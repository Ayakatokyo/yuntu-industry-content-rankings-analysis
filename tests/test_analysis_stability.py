"""Regression coverage for the September 11 fact/prompt/report boundary."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import yuntu_analysis as preparation
import yuntu_report as report
from rpa_io import write_json_atomically


def fixture(root):
    scope = {"sampleCount": 1, "availability": "available", "topMaterials": [{"material_id": "101"}]}
    facts = {
        "schemaVersion": 8, "filters": {}, "reportScopes": {"ranking": {}, "detail": {}},
        "industryTop1000Facts": {"source_scope": "industry_top1000", "sample_count": 1}, "brandRankingFacts": {},
        "chapter02AiFacts": {"scopeOrder": ["all", "空品牌"], "all": scope,
                             "空品牌": {"sampleCount": 0, "availability": "unavailable", "topMaterials": []}},
        "chapter02Facts": {"scopeOrder": ["all"], "all": {**scope, "topMaterials": [{"material_id": "999"}]}},
        "scriptFacts": {"materials": [{"material_id": "101"}]},
        "visualAssets": [], "dataLimitations": [], "dataAvailabilitySummary": {},
        "selectedMaterials": [{"material_id": "101"}, {"material_id": "102"}],
        "materialFacts": [
            {"material_id": "101", "script_text": "早餐可选豆浆，方便冲泡。", "highlightFrames": [], "secondLevelBreakdown": {"metrics": []}},
            {"material_id": "102", "script_text": "", "highlightFrames": [], "secondLevelBreakdown": {"metrics": []}},
        ],
    }
    root.mkdir(parents=True, exist_ok=True)
    write_json_atomically(preparation._report_data(facts), root / "report-data.json")
    (root / "yuntu-analysis-prompt.md").write_text("模型读取事实，直接写 JSON。", encoding="utf-8")
    preparation._write_analysis_units(facts, root)
    def summary(text, ids):
        return {"title": "范围观察", "summary": text, "evidence": ["标签"] if ids else [], "material_ids": ids}
    analysis = {
        "topMaterialCombination": {"brandConclusions": []},
        "chapter02Insights": {"scopeOrder": ["all", "空品牌"], "scopes": {
            "all": {"audienceSummary": summary("早餐人群的场景需求可作为后续测试方向。", ["101"]),
                    "marketingSummary": summary("冲泡便利是当前表达的可观察卖点。", ["101"])},
            "空品牌": {"audienceSummary": summary("数据不足以判断。", []), "marketingSummary": summary("数据不足以判断。", [])}}},
        "scriptInsights": [{"title": "脚本文案：早餐", "summary": "文案表达冲泡便利。", "evidence": ["早餐"], "material_ids": ["101"]}],
        "materialDeepDives": [
            {"material_id": "101", "frame_observations": [], "scriptAnalysis": {
                "availability": "available", "evidenceRefs": ["script:101:text:早餐可选豆浆，方便冲泡。"],
                "conclusion": "文案以早餐为具体使用场景，接着说明豆浆方便冲泡，把产品名称与日常准备需求连在一起。可以保留场景开头及冲泡表达，让读者先理解使用时机，再理解准备方式。后续改写应围绕同一场景调整信息顺序，不添加原文没有提供的功效或成分承诺。建议比较场景先行与便利先行两种表达，检查读者能否准确复述核心卖点，再决定下一轮内容取舍。"}},
            {"material_id": "102", "frame_observations": [], "scriptAnalysis": {"availability": "unavailable", "evidenceRefs": [], "conclusion": "数据不足以判断。"}},
        ],
    }
    return facts, analysis, root / "analysis-units/analysis-unit-manifest.json"


class StabilityTests(unittest.TestCase):
    def test_zero_sample_scope_passes_the_public_validator(self):
        with tempfile.TemporaryDirectory() as d:
            facts, analysis, _ = fixture(Path(d))
            facts.pop("materialFacts")
            p = Path(d) / "analysis.json"
            write_json_atomically(analysis, p)
            report.validate_analysis_input(analysis_json=p, fact_pack=facts)

    def test_canonical_units_restore_ai_scope_and_script_refs(self):
        from yuntu_analysis_bundle import load_analysis_bundle
        with tempfile.TemporaryDirectory() as d:
            _, analysis, manifest = fixture(Path(d))
            bundle = load_analysis_bundle(manifest)
            self.assertEqual(bundle["facts"]["chapter02AiFacts"]["all"]["topMaterials"], [{"material_id": "101"}])
            self.assertEqual(bundle["facts"]["materialFacts"][0]["evidenceIndex"]["script"], ["script:101:text:早餐可选豆浆，方便冲泡。"])
            p = Path(d) / "analysis.json"
            write_json_atomically(analysis, p)
            report.validate_analysis_input(analysis_json=p, fact_pack=bundle["facts"])

    def test_bundle_rejects_changed_prompt_schema_or_report_projection(self):
        from yuntu_analysis_bundle import load_analysis_bundle, AnalysisBundleError
        for name in ("report-data.json", "yuntu-analysis-prompt.md", "yuntu-ai-analysis.schema.json"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as d:
                _, _, manifest = fixture(Path(d))
                path = Path(d) / name
                path.write_text(path.read_text() + " ")
                with self.assertRaises(AnalysisBundleError):
                    load_analysis_bundle(manifest)

    def test_wrong_scope_order_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            facts, analysis, _ = fixture(Path(d))
            value = analysis["chapter02Insights"]
            del value["scopes"]["空品牌"]
            value["scopeOrder"] = ["all"]
            with self.assertRaisesRegex(report.YuntuReportError, "scopeOrder"):
                report._validate_chapter02_insights(value, facts)

    def test_empty_ai_projection_never_borrows_chart_material_scope(self):
        with tempfile.TemporaryDirectory() as d:
            facts, analysis, _ = fixture(Path(d))
            facts["chapter02AiFacts"] = {"scopeOrder": ["all"], "all": {}}
            value = analysis["chapter02Insights"]
            value["scopeOrder"] = ["all"]
            value["scopes"].pop("空品牌")
            for item in value["scopes"]["all"].values():
                item["material_ids"] = ["999"]
            with self.assertRaisesRegex(report.YuntuReportError, "canonical"):
                report._validate_chapter02_insights(value, facts)

    def test_workspace_is_lossless_and_preserves_reviewed_draft_snapshots(self):
        from yuntu_analysis_workspace import begin_workspace, check_workspace, assemble_workspace, verify_assembly
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _, analysis, manifest = fixture(root / "facts")
            ws = root / "drafts"
            state = begin_workspace(manifest, ws)
            for part in state["parts"]:
                p = ws / part["path"]
                draft = json.loads(p.read_text())
                if "materialId" in part:
                    draft["content"] = next(x for x in analysis["materialDeepDives"] if x["material_id"] == part["materialId"])
                else:
                    draft["content"] = {k: analysis[k] for k in part["outputFields"]}
                write_json_atomically(draft, p)
            self.assertTrue(check_workspace(ws)["valid"])
            output = root / "assembled.json"
            assemble_workspace(ws, output)
            self.assertEqual(json.loads(output.read_text()), analysis)
            verify_assembly(output, manifest)
            from yuntu_analysis_provenance import attest_analysis, load_verified_provenance, YuntuAnalysisProvenanceError
            receipt = attest_analysis(analysis_json=output, fact_pack_json=manifest,
                                      prompt_path=root / "facts/yuntu-analysis-prompt.md",
                                      source="model_generated", generator="unit-test-fixture")
            self.assertIn("assembly", load_verified_provenance(analysis_json=output, provenance_path=receipt)["artifacts"])
            first = ws / state["parts"][0]["path"]
            first.write_text("{}")
            # Editing the working draft cannot rewrite the captured response.
            verify_assembly(output, manifest)
            output.write_text(output.read_text() + " ")
            with self.assertRaisesRegex(ValueError, "assembly"):
                verify_assembly(output, manifest)
            with self.assertRaises(YuntuAnalysisProvenanceError):
                load_verified_provenance(analysis_json=output, provenance_path=receipt)

    def test_preflight_reports_independent_material_errors_together(self):
        from yuntu_analysis_workspace import begin_workspace, check_workspace
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _, analysis, manifest = fixture(root / "facts")
            ws = root / "drafts"
            state = begin_workspace(manifest, ws)
            for part in state["parts"]:
                if "materialId" not in part:
                    continue
                p = ws / part["path"]
                draft = json.loads(p.read_text())
                draft["content"] = copy.deepcopy(next(x for x in analysis["materialDeepDives"] if x["material_id"] == part["materialId"]))
                draft["content"]["scriptAnalysis"]["evidenceRefs"] = ["script:999:text:其他素材"]
                write_json_atomically(draft, p)
            result = check_workspace(ws)
            self.assertFalse(result["valid"])
            failed = {x["part"] for x in result["errors"]}
            self.assertIn("material-101", failed)
            self.assertIn("material-102", failed)

    def test_new_contract_cannot_attest_without_model_draft_receipt(self):
        from yuntu_analysis_provenance import attest_analysis, YuntuAnalysisProvenanceError
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _, analysis, manifest = fixture(root)
            p = root / "analysis.json"
            write_json_atomically(analysis, p)
            with self.assertRaisesRegex(YuntuAnalysisProvenanceError, "assembly"):
                attest_analysis(analysis_json=p, fact_pack_json=manifest,
                                prompt_path=root / "yuntu-analysis-prompt.md", source="model_generated", generator="declared")

    def test_unavailable_batch_classification_schema_accepts_no_groups(self):
        from yuntu_analysis_bundle import schema_errors
        schema = preparation._highlight_output_schema()["properties"]["batchClassification"]
        self.assertEqual(schema_errors({"status": "unavailable", "missing_reason": "仅一张成功帧", "groups": []}, schema), [])

    def test_duplicate_frame_error_names_the_duplicated_and_missing_refs(self):
        groups = [{"category": "cup", "label": "杯子", "rule": "杯子主体", "frame_refs": ["f1"]},
                  {"category": "pack", "label": "包装", "rule": "包装主体", "frame_refs": ["f1"]}]
        with self.assertRaises(report.YuntuReportError) as caught:
            report._validate_highlight_classification_groups(groups, {"f1", "f2"}, mode="batchClassification")
        self.assertIn('"duplicates": ["f1"]', str(caught.exception))
        self.assertIn('"missing": ["f2"]', str(caught.exception))

    def test_declared_successful_image_is_verified_before_drafting(self):
        from yuntu_analysis_bundle import load_analysis_bundle, AnalysisBundleError, file_record
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _, _, manifest = fixture(root)
            image = root / "bad.jpg"
            image.write_bytes(b"not an image")
            m = json.loads(manifest.read_text())
            m["analysisContract"]["visualAssets"] = [{**file_record(image, root), "frame_ref": "f1"}]
            write_json_atomically(m, manifest)
            with self.assertRaises(AnalysisBundleError):
                load_analysis_bundle(manifest)

    def test_workspace_resume_does_not_rebind_stale_drafts_or_overwrite_work(self):
        from yuntu_analysis_workspace import begin_workspace
        from yuntu_analysis_bundle import AnalysisBundleError, file_record
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _, _, manifest = fixture(root / "facts")
            ws = root / "drafts"
            state = begin_workspace(manifest, ws)
            draft = ws / state["parts"][0]["path"]
            draft.write_text("user work")
            begin_workspace(manifest, ws)
            self.assertEqual(draft.read_text(), "user work")
            prompt = root / "facts/yuntu-analysis-prompt.md"
            prompt.write_text("Changed task")
            m = json.loads(manifest.read_text())
            m["analysisContract"]["prompt"] = file_record(prompt, prompt.parent)
            write_json_atomically(m, manifest)
            with self.assertRaises(AnalysisBundleError):
                begin_workspace(manifest, ws)

    def test_json_duplicate_fields_cannot_silently_overwrite_model_text(self):
        from yuntu_analysis_bundle import read_json, AnalysisBundleError
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "draft.json"
            p.write_text('{"content": "first", "content": "second"}')
            with self.assertRaisesRegex(AnalysisBundleError, "duplicate JSON key"):
                read_json(p)

    def test_render_preserves_explicitly_unavailable_video_fact(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "video-assets").mkdir()
            (root / "video-assets/101.mp4").write_bytes(b"unregistered later download")
            assets = report._copy_report_video_assets(
                {"materialFacts": [{"material_id": "101", "localVideo": {"available": False}}]},
                root / "report", root)
            self.assertFalse(assets["101"]["available"])
            self.assertFalse((root / "report/assets/videos/101.mp4").exists())

    def test_schema_diagnostics_do_not_repeat_long_script_allowlists(self):
        from yuntu_analysis_bundle import schema_errors
        result = schema_errors("bad ref", {"type": "string", "enum": ["script:" + "正文" * 500]})
        self.assertLess(len(json.dumps(result, ensure_ascii=False)), 500)
        length = schema_errors("过短", {"type": "string", "minLength": 120})[0]
        self.assertIn("120", length["message"])
        self.assertIn("2", length["message"])


if __name__ == "__main__":
    unittest.main()
