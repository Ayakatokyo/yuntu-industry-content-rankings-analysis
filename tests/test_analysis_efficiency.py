"""Reading-volume reductions must preserve facts, scope and final output."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from test_analysis_stability import fixture
from rpa_io import write_json_atomically
from yuntu_analysis_bundle import AnalysisBundleError, load_analysis_bundle
from yuntu_analysis_inputs import audience_view, ranking_view, model_reading_view, json_bytes
from yuntu_analysis_workspace import begin_workspace, check_workspace


class ModelReadingTests(unittest.TestCase):
    def test_ranking_preserves_all_aggregates_refs_and_hot_materials(self):
        rows = [{"material_id": str(i), "title": "榜单素材" * 40, "metrics": {"ctr": i / 1000}}
                for i in range(100)]
        aggregate = {"sampleCount": 100, "materials": rows, "available": True,
                     "metrics": {"ctr": {"median": 0.05}}, "actualDateRange": None}
        evidence = {"current": aggregate, "previousPeriod": {"available": False, "missingReason": "missing"},
                    "comparisonFacts": {"scopes": {"all": {"current": aggregate}}},
                    "hotMaterialFacts": {"all": {"materials": rows[:2], "qualifyingCount": 2}}}
        before = copy.deepcopy(evidence)
        view = ranking_view(evidence)
        self.assertEqual(evidence, before)
        self.assertEqual(view["current"]["materialIds"], [str(i) for i in range(100)])
        self.assertEqual({k: v for k, v in view["current"].items() if k != "materialIds"},
                         {k: v for k, v in aggregate.items() if k != "materials"})
        self.assertEqual(view["hotMaterialFacts"], evidence["hotMaterialFacts"])
        self.assertEqual(view["previousPeriod"], evidence["previousPeriod"])
        self.assertLess(json_bytes(view), json_bytes(evidence) / 5)

    def test_audience_view_reconstructs_every_scope_without_sampling(self):
        rows = [{"material_id": "1", "title": "甲", "people_tags": ["女", "24-30"], "metrics": {"ctr": None}},
                {"material_id": "2", "title": "乙", "material_tags": ["冲泡"], "exposure": {"raw": "1-2w"}}]
        dashboard = {"categories": [{"category": "其他", "tags": [{"tag": str(i)} for i in range(200)]}]}
        source = {"chapter02AiFacts": {"scopeOrder": ["all", "乙", "空"],
                  "all": {"sampleCount": 2, "topMaterials": rows, "marketingDashboard": dashboard},
                  "乙": {"sampleCount": 1, "topMaterials": rows[1:], "audienceDashboard": {}},
                  "空": {"sampleCount": 0, "topMaterials": [], "availability": "unavailable"}}}
        original = copy.deepcopy(source)
        view = audience_view(source)
        self.assertEqual(source, original)
        for name in view["chapter02AiFacts"]["scopeOrder"]:
            scope = view["chapter02AiFacts"][name]
            scope["topMaterials"] = [view["materialsById"][mid] for mid in scope.pop("topMaterialIds")]
        del view["materialsById"]
        self.assertEqual(view, original)

    def test_conflicting_same_id_does_not_overwrite_audience_evidence(self):
        source = {"chapter02AiFacts": {"scopeOrder": ["all", "brand"],
                  "all": {"topMaterials": [{"material_id": "1", "title": "甲"}]},
                  "brand": {"topMaterials": [{"material_id": "1", "title": "乙"}]}}}
        self.assertEqual(audience_view(source), source)

    def test_material_view_retains_own_script_and_frames_without_curves(self):
        own = {"material_id": "1", "script": {"text": "冲泡", "formula": {}},
               "evidenceIndex": {"script": ["script:1:text:冲泡"]},
               "highlightFrames": [{"frame_ref": "f1", "image_path": "../frames/f1.jpg", "available": True}],
               "secondLevelBreakdown": {"metrics": [{"points": list(range(10000))}]}}
        bundle = {"units": {"material_deep_dive": {"evidence": {"materialFacts": [own, {"material_id": "2"}]}}}}
        view = model_reading_view(bundle, {"unit": "material_deep_dive", "materialId": "1"})
        self.assertEqual(view, {k: v for k, v in own.items() if k != "secondLevelBreakdown"})
        self.assertIn("secondLevelBreakdown", own)

    def test_script_brand_view_cannot_include_other_brand_facts(self):
        scoped = {"materials": [{"material_id": "2", "script_text": "乙"}]}
        facts = {"materials": [{"material_id": "1", "script_text": "甲"}],
                 "brandScopeOrder": ["乙"], "brandScopes": {"乙": scoped}}
        bundle = {"units": {"script_insights": {"evidence": {"scriptFacts": facts}}}}
        self.assertEqual(model_reading_view(bundle, {"unit": "script_insights", "brand": "乙"}), scoped)
        self.assertNotIn("brandScopes", model_reading_view(bundle, {"unit": "script_insights"}))

    def test_workspace_tasks_are_self_contained_bound_and_resume_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _, _, manifest = fixture(root / "facts")
            workspace = root / "drafts"
            state = begin_workspace(manifest, workspace)
            task_path = workspace / "material-101.task.json"
            task = json.loads(task_path.read_text())
            self.assertEqual(task["scopedFacts"]["material_id"], "101")
            self.assertIn("早餐", task["scopedFacts"]["script"]["text"])
            self.assertEqual(state, begin_workspace(manifest, workspace))
            task["scopedFacts"]["script"]["text"] = "changed"
            write_json_atomically(task, task_path)
            with self.assertRaisesRegex(AnalysisBundleError, "model task input"):
                check_workspace(workspace, "material-101")

    def test_group_check_loads_once_reports_all_errors_and_rejects_unknown_key(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _, analysis, manifest = fixture(root / "facts")
            workspace = root / "drafts"
            begin_workspace(manifest, workspace)
            for content in analysis["materialDeepDives"]:
                path = workspace / f"material-{content['material_id']}.json"
                draft = json.loads(path.read_text())
                draft["content"] = copy.deepcopy(content)
                draft["content"]["scriptAnalysis"]["evidenceRefs"] = ["wrong"]
                write_json_atomically(draft, path)
            with patch("yuntu_analysis_workspace.load_analysis_bundle", wraps=load_analysis_bundle) as loader:
                result = check_workspace(workspace, ["material-102", "material-101", "material-101"])
                self.assertEqual(loader.call_count, 1)
            self.assertFalse(result["valid"])
            self.assertEqual(result["checkedParts"], ["material-101", "material-102"])
            self.assertEqual({x["part"] for x in result["errors"]}, {"material-101", "material-102"})
            self.assertIn("loadAndVerifyInputs", result["timingsSeconds"])
            with self.assertRaisesRegex(AnalysisBundleError, "unknown draft part"):
                check_workspace(workspace, ["material-101", "typo"])

    def test_old_workspace_still_resumes_without_changing_drafts(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _, _, manifest = fixture(root / "facts")
            workspace = root / "drafts"
            state = begin_workspace(manifest, workspace)
            for key in ("readingViewVersion", "taskInputs", "inputMetrics"):
                state.pop(key)
            write_json_atomically(state, workspace / "workspace.json")
            before = (workspace / "material-101.json").read_bytes()
            self.assertEqual(begin_workspace(manifest, workspace), state)
            self.assertEqual((workspace / "material-101.json").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
