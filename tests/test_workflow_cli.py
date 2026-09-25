import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import rpa_connector
import rpa_dynamic_client as dynamic
import test_yuntu_analysis as analysis_tests


class WorkflowCliTests(unittest.TestCase):
    def test_analysis_navigation_and_section_cli_use_existing_bound_workspace(self):
        from test_analysis_navigation import image_fixture
        from yuntu_analysis_workspace import begin_workspace
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, manifest = image_fixture(root / "facts", count=2)
            workspace = root / "drafts"
            begin_workspace(manifest, workspace)
            for command, extra in (("analysis-overview", []),
                                   ("read-frame-batch", ["--batch", "0"]),
                                   ("read-analysis", ["--part", "material-101", "--section", "facts"])):
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    code = rpa_connector.main([command, "--workspace", str(workspace), *extra])
                self.assertEqual(code, 0)
                result = json.loads(out.getvalue())
                if command == "analysis-overview":
                    self.assertEqual(result["frames"]["successfulCount"], 2)
                elif command == "read-frame-batch":
                    self.assertEqual(len(result["frames"]), 2)
                else:
                    self.assertEqual(result["section"], "facts")

    def test_local_only_preparation_never_attempts_missing_video_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            analysis_tests.YuntuAnalysisTests()._write_input(root,
                [{"material_id": "1", "title": "素材", "metrics": {}}],
                [{"rank": 1, "material_id": "1", "detailRecordPath": "normalized/detail-records/1.json"}],
                {"1": {"material_id": "1", "high_points": [], "loss_points": [], "video_url": "https://example.invalid/1.mp4"}})
            with patch("yuntu_highlights.download_video", side_effect=AssertionError("must remain offline")):
                status = rpa_connector.main(["prepare-analysis", "--local-only", "--input-dir", str(root),
                                             "--output-dir", str(root / "analysis")])
            self.assertEqual(status, 0)
            facts = json.loads((root / "analysis/report-data.json").read_text())
            self.assertEqual(facts["materialFacts"][0]["highlightFrames"], [])

    def test_validate_extracts_only_explicit_batch_section_then_uses_live_schema(self):
        schema = {"inParamJsonSchemaText": json.dumps({"type": "object", "properties": {"industry": {"type": "string"}},
                  "required": ["industry"], "additionalProperties": False})}
        parser = dynamic.build_parser()
        args = parser.parse_args(["validate", "--params-section", "list", "--params-json",
                                  '{"list":{"industry":"美妆"},"detail":{},"target_top_n":30}'])
        with patch.object(dynamic, "fetch_connector_detail", return_value=schema), contextlib.redirect_stdout(io.StringIO()) as out:
            args.func(args)
        self.assertEqual(json.loads(out.getvalue())["businessParams"], {"industry": "美妆"})
        args.params_json = '{"list":{"industry":42},"detail":{}}'
        with patch.object(dynamic, "fetch_connector_detail", return_value=schema):
            with self.assertRaises(dynamic.ValidationContractError):
                args.func(args)
        args.params_json = '{"detail":{}}'
        with self.assertRaises(dynamic.ValidationContractError):
            dynamic.load_params(args)


if __name__ == "__main__":
    unittest.main()
