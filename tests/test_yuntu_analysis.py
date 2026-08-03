import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


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
    def test_prepare_analysis_writes_fact_pack_and_prompt(self):
        analysis = load_module()
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "normalized" / "detail-records").mkdir(parents=True)
            (root / "batch-manifest.json").write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "filters": {"industry": "食品饮料"},
                        "candidateMaterials": [{"rank": 1, "material_id": "101"}],
                        "selectedMaterials": [
                            {
                                "rank": 1,
                                "material_id": "101",
                                "detailRecordPath": "normalized/detail-records/101.json",
                            }
                        ],
                        "rejectedMaterials": [
                            {"rank": 2, "material_id": "202", "reason": "RpaIoError"}
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (root / "normalized" / "list-records.json").write_text(
                json.dumps(
                    [
                        {
                            "material_id": "101",
                            "title": "高点击素材",
                            "rank": 1,
                            "metrics": {"ctr": 0.7, "cvr": 0.2},
                            "people_tags": ["都市银发"],
                            "material_tags": ["包装_独立包装"],
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (root / "normalized" / "detail-records" / "101.json").write_text(
                json.dumps(
                    {
                        "material_id": "101",
                        "high_points": [
                            {"trend_name": "点击指数", "start_sec": 1, "end_sec": 2}
                        ],
                        "loss_points": [
                            {
                                "trend_name": "流失指数",
                                "start_sec": 0,
                                "end_sec": 1,
                                "loss_percent": 0.5,
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            status = analysis.prepare_analysis(
                input_dir=root, output_dir=root / "diagnostic-analysis"
            )
            data = json.loads(
                (
                    root / "diagnostic-analysis" / "yuntu-analysis-data.json"
                ).read_text(encoding="utf-8")
            )
            prompt = (
                root / "diagnostic-analysis" / "yuntu-analysis-prompt.md"
            ).read_text(encoding="utf-8")

        self.assertEqual(status, 0)
        self.assertEqual(data["schemaVersion"], 1)
        self.assertEqual(data["filters"], {"industry": "食品饮料"})
        self.assertEqual(data["summaryMetrics"]["selectedCount"], 1)
        self.assertEqual(data["summaryMetrics"]["rejectedCount"], 1)
        self.assertEqual(data["audienceAggregations"]["都市银发"], 1)
        self.assertEqual(data["tagAggregations"]["包装_独立包装"], 1)
        self.assertIn("点击指数", data["trendHighlights"]["highPointNames"])
        self.assertIn("yuntu-ai-analysis.json", prompt)


if __name__ == "__main__":
    unittest.main()
