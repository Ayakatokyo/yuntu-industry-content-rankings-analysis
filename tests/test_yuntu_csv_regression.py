import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from rpa_io import parse_csv_records  # noqa: E402
from yuntu_analysis import build_script_facts  # noqa: E402
from yuntu_normalizer import normalize_detail_records  # noqa: E402


REAL_SAMPLE_DIR = (
    ROOT / "RPA数据汇总"
    / "yuntu-rankings-analysis-20260810-20260820-top12"
    / "raw-csv" / "latest-details"
)


@unittest.skipUnless(REAL_SAMPLE_DIR.is_dir(), "real Yuntu detail CSV samples are unavailable")
class YuntuCsvRegressionTests(unittest.TestCase):
    def test_six_real_flat_detail_csvs_normalize_to_five_material_facts(self):
        paths = sorted(REAL_SAMPLE_DIR.glob("industry_content_rankings_details_*.csv"))
        self.assertEqual(len(paths), 6)
        details = []
        for path in paths:
            raw = parse_csv_records(path)
            self.assertEqual(len(raw), 1)
            row = raw[0]
            detail = normalize_detail_records(
                row,
                material_id=row["materialId"],
                source_path=str(path),
            )
            self.assertEqual(detail["source_schema"], "flat_detail_csv")
            self.assertEqual(detail["date_range"]["type"], "LAST_7_DAYS")
            self.assertEqual(len(detail["trend_series"]), 5)
            self.assertEqual(
                {len(trend["series"]) for trend in detail["trend_series"]},
                {detail["video_duration"] + 1},
            )
            self.assertTrue(detail["script_text"] or not detail["data_availability"]["script_text"]["available"])
            if detail["content_formula"] is None:
                self.assertEqual(
                    detail["data_availability"]["content_formula"]["missing_reason"],
                    "source_empty",
                )
            self.assertIsNotNone(detail["creative_breakdown"])
            self.assertIn("convertCnt", detail["metrics"])
            self.assertIn("orderCnt", detail["metrics"])
            details.append(detail)

        material_ids = [detail["material_id"] for detail in details]
        self.assertEqual(len(set(material_ids)), 5)
        self.assertEqual(material_ids.count("7659409261740343346"), 2)
        duplicates = [detail for detail in details if detail["material_id"] == "7659409261740343346"]
        for field in ("metrics", "trend_series", "script_text", "content_formula", "creative_breakdown"):
            self.assertEqual(duplicates[0][field], duplicates[1][field])
        self.assertNotEqual(duplicates[0]["video_url"], duplicates[1]["video_url"])

        selected = [{"material_id": material_id, "rank": index} for index, material_id in enumerate(dict.fromkeys(material_ids), start=1)]
        facts = build_script_facts(details, selected)
        self.assertEqual(facts["coverage"], {"total": 5, "script": 3, "rate": 0.6})
        self.assertEqual(len(facts["materials"]), 5)
        self.assertEqual(
            sum(item["content_formula"] is not None for item in facts["materials"]),
            3,
        )
        self.assertEqual(
            sum(item["creative_breakdown"] is not None for item in facts["materials"]),
            5,
        )
        duplicate_fact = next(item for item in facts["materials"] if item["material_id"] == "7659409261740343346")
        self.assertEqual(len(duplicate_fact["video_url_variants"]), 2)
        self.assertEqual(
            duplicate_fact["metrics"]["convertCnt"],
            duplicates[0]["metrics"]["convertCnt"],
        )
        self.assertNotEqual(
            duplicate_fact["metrics"]["convertCnt"],
            duplicate_fact["metrics"]["orderCnt"],
        )


if __name__ == "__main__":
    unittest.main()
