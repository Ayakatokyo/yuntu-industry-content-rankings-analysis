import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
BATCH_PATH = SCRIPTS_DIR / "yuntu_batch.py"


def load_batch():
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    spec = importlib.util.spec_from_file_location("yuntu_batch", BATCH_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeInvoker:
    def __init__(self, list_result, detail_results):
        self.list_result = list_result
        self.detail_results = list(detail_results)
        self.list_calls = []
        self.detail_calls = []

    def invoke_list(self, shop_id, list_params):
        self.list_calls.append((shop_id, list_params))
        return self.list_result

    def invoke_detail(self, shop_id, detail_params):
        self.detail_calls.append((shop_id, detail_params))
        return self.detail_results.pop(0)


class FakeDownloader:
    def __init__(self, contents_by_url):
        self.contents_by_url = contents_by_url
        self.downloads = []

    def download_file(self, file_url, target_path):
        self.downloads.append((file_url, str(target_path)))
        target = Path(target_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.contents_by_url[file_url], encoding="utf-8")
        return target


class YuntuBatchTests(unittest.TestCase):
    def files_result(self, url):
        return {
            "success": True,
            "code": "200",
            "data": {
                "result_type": "files",
                "result_content": {
                    "status": "COMPLETED",
                    "failedInstances": 0,
                    "files": [{"fileUrl": url}],
                },
            },
        }

    def test_fetch_batch_downloads_csv_normalizes_and_writes_manifest(self):
        batch = load_batch()
        invoker = FakeInvoker(
            self.files_result("https://files.example/list.csv"),
            [
                self.files_result("https://files.example/101.csv"),
                self.files_result("https://files.example/202.csv"),
            ],
        )
        downloader = FakeDownloader(
            {
                "https://files.example/list.csv": (
                    "material_id\x01title\x01object_index\x01people_tag_entry\x01material_tag_entry\x01page_industry\n"
                    '101\x01A\x01{"ctr":0.7}\x01[]\x01[]\x01食品饮料\n'
                    '202\x01B\x01{"ctr":0.4}\x01[]\x01[]\x01食品饮料\n'
                ),
                "https://files.example/101.csv": (
                    "materialId\x01dateRangeType\x01trends\n"
                    '101\x01LAST_7_DAYS\x01[{"trendName":"点击指数","tendList":[{"x":1,"y":1}],"highPoint":{"start_point":"1","end_point":"2"}}]\n'
                ),
                "https://files.example/202.csv": (
                    "materialId\x01dateRangeType\x01trends\n"
                    "202\x01LAST_7_DAYS\x01[]\n"
                ),
            }
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            status = batch.fetch_batch(
                shop_id="shop-42",
                list_params={"industry": "食品饮料"},
                detail_date_params={"date_range_type": "LAST_7_DAYS"},
                target_top_n=2,
                candidate_top_n=3,
                output_dir=root,
                invoker=invoker,
                downloader=downloader,
            )
            manifest = json.loads(
                (root / "batch-manifest.json").read_text(encoding="utf-8")
            )

            self.assertEqual(status, 0)
            self.assertEqual(
                [item["material_id"] for item in manifest["selectedMaterials"]],
                ["101", "202"],
            )
            self.assertEqual(manifest["rejectedMaterials"], [])
            self.assertTrue((root / "normalized" / "list-records.json").exists())
            self.assertTrue(
                (root / "normalized" / "detail-records" / "101.json").exists()
            )
            self.assertTrue((root / "raw-csv" / "details" / "101.csv").exists())
            detail_requests = json.loads(
                (root / "normalized" / "detail-request-params.json").read_text(encoding="utf-8")
            )
            self.assertEqual(detail_requests, [
                {"material_id": "101", "date_range_type": "LAST_7_DAYS"},
                {"material_id": "202", "date_range_type": "LAST_7_DAYS"},
            ])
            self.assertEqual(manifest["detailRequestPath"], "normalized/detail-request-params.json")

    def test_fetch_batch_reuses_completed_list_artifact_after_detail_interruption(self):
        batch = load_batch()
        invoker = FakeInvoker(
            {"success": False},
            [
                {
                    "success": True,
                    "data": [{"materialId": "101", "dateRangeType": "LAST_7_DAYS", "trends": []}],
                }
            ],
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "raw-csv").mkdir(parents=True)
            (root / "raw-csv" / "list.csv").write_text(
                "material_id\x01title\x01object_index\x01people_tag_entry\x01material_tag_entry\x01page_industry\n"
                '101\x01A\x01{"ctr":0.7}\x01[]\x01[]\x01食品饮料\n',
                encoding="utf-8",
            )
            (root / "batch-manifest.json").write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "status": "running",
                        "filters": {"industry": "食品饮料"},
                        "detailDateRange": {"date_range_type": "LAST_7_DAYS"},
                        "targetTopN": 1,
                        "candidateTopN": 1,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            contract = batch.run_state.collection_contract(
                shop_id="shop-42",
                list_params={"industry": "食品饮料"},
                detail_date_params={"date_range_type": "LAST_7_DAYS"},
                target_top_n=1,
                candidate_top_n=1,
            )
            batch.run_state.save_run_state(
                batch.run_state.new_collection_summary(contract), root / "run-summary.json"
            )
            status = batch.fetch_batch(
                shop_id="shop-42",
                list_params={"industry": "食品饮料"},
                detail_date_params={"date_range_type": "LAST_7_DAYS"},
                target_top_n=1,
                candidate_top_n=1,
                output_dir=root,
                invoker=invoker,
            )

        self.assertEqual(status, 0)
        self.assertEqual(len(invoker.list_calls), 0)
        self.assertEqual(len(invoker.detail_calls), 1)

    def test_fetch_batch_rejects_unverifiable_existing_list_before_any_rpa_call(self):
        batch = load_batch()
        invoker = FakeInvoker({"success": False}, [])
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "raw-csv").mkdir(parents=True)
            (root / "raw-csv" / "list.csv").write_text(
                "material_id\x01title\x01object_index\x01people_tag_entry\x01material_tag_entry\n"
                '101\x01A\x01{"ctr":0.7}\x01[]\x01[]\n',
                encoding="utf-8",
            )
            (root / "batch-manifest.json").write_text(
                json.dumps({"filters": {"industry": "食品饮料"}}), encoding="utf-8"
            )

            with self.assertRaisesRegex(batch.YuntuBatchError, "unverifiable existing batch"):
                batch.fetch_batch(
                    shop_id="shop-42",
                    list_params={"industry": "食品饮料"},
                    detail_date_params={"date_range_type": "LAST_7_DAYS"},
                    target_top_n=1,
                    candidate_top_n=1,
                    output_dir=root,
                    invoker=invoker,
                )

        self.assertEqual(invoker.list_calls, [])
        self.assertEqual(invoker.detail_calls, [])

    def test_fetch_batch_rejects_a_different_verified_contract_before_any_rpa_call(self):
        batch = load_batch()
        invoker = FakeInvoker({"success": False}, [])
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            original_contract = batch.run_state.collection_contract(
                shop_id="shop-42",
                list_params={"industry": "食品饮料"},
                detail_date_params={"date_range_type": "LAST_7_DAYS"},
                target_top_n=1,
                candidate_top_n=1,
            )
            batch.run_state.save_run_state(
                batch.run_state.new_collection_summary(original_contract),
                root / "run-summary.json",
            )

            with self.assertRaisesRegex(batch.YuntuBatchError, "different collection contract"):
                batch.fetch_batch(
                    shop_id="shop-42",
                    list_params={"industry": "食品饮料"},
                    detail_date_params={"date_range_type": "LAST_7_DAYS"},
                    target_top_n=2,
                    candidate_top_n=6,
                    output_dir=root,
                    invoker=invoker,
                )

        self.assertEqual(invoker.list_calls, [])
        self.assertEqual(invoker.detail_calls, [])

    def test_fetch_batch_persists_a_contract_for_same_request_resume(self):
        batch = load_batch()
        first = FakeInvoker(
            {"success": True, "data": [{"material_id": "101", "page_industry": "食品饮料"}]},
            [{"success": True, "data": [{"materialId": "101", "trends": []}]}],
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.assertEqual(
                batch.fetch_batch(
                    shop_id="shop-42",
                    list_params={"industry": "食品饮料"},
                    detail_date_params={"date_range_type": "LAST_7_DAYS"},
                    target_top_n=1,
                    candidate_top_n=1,
                    output_dir=root,
                    invoker=first,
                ),
                0,
            )
            summary = json.loads((root / "run-summary.json").read_text(encoding="utf-8"))
            observed = batch.collection_status(output_dir=root)

        self.assertEqual(summary["collectionContract"]["shopId"], "shop-42")
        self.assertEqual(summary["collectionContract"]["targetTopN"], 1)
        self.assertEqual(summary["stages"]["list"]["contextVerified"], True)
        self.assertEqual(observed["status"], "success")
        self.assertEqual(observed["stages"]["details"]["persistedRecordCount"], 1)

    def test_fetch_batch_stops_before_detail_when_list_context_does_not_match(self):
        batch = load_batch()
        invoker = FakeInvoker(
            {
                "success": True,
                "data": [{"material_id": "101", "page_industry": "美妆"}],
            },
            [{"success": True, "data": [{"materialId": "101", "trends": []}]}],
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            status = batch.fetch_batch(
                shop_id="shop-42",
                list_params={"industry": "食品饮料"},
                detail_date_params={"date_range_type": "LAST_7_DAYS"},
                target_top_n=1,
                candidate_top_n=1,
                output_dir=root,
                invoker=invoker,
            )
            manifest = json.loads((root / "batch-manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(status, 1)
        self.assertEqual(manifest["status"], "list_context_mismatch")
        self.assertEqual(invoker.detail_calls, [])

    def test_collection_status_counts_persisted_details_before_manifest_writeback(self):
        batch = load_batch()
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            contract = batch.run_state.collection_contract(
                shop_id="shop-42",
                list_params={"industry": "食品饮料"},
                detail_date_params={"date_range_type": "LAST_7_DAYS"},
                target_top_n=1,
                candidate_top_n=1,
            )
            summary = batch.run_state.new_collection_summary(contract)
            summary["stages"]["details"]["requestStatus"] = "running"
            batch.run_state.save_run_state(summary, root / "run-summary.json")
            (root / "normalized" / "detail-records").mkdir(parents=True)
            (root / "normalized" / "detail-request-params.json").write_text(
                json.dumps([{"material_id": "101", "date_range_type": "LAST_7_DAYS"}]),
                encoding="utf-8",
            )
            (root / "normalized" / "detail-records" / "101.json").write_text(
                json.dumps({"material_id": "101"}), encoding="utf-8"
            )
            (root / "batch-manifest.json").write_text(
                json.dumps(
                    {
                        "status": "running",
                        "submittedMaterials": [{"material_id": "101"}],
                        "selectedMaterials": [],
                        "rejectedMaterials": [],
                        "cancelledMaterials": [],
                    }
                ),
                encoding="utf-8",
            )

            observed = batch.collection_status(output_dir=root)

        self.assertEqual(observed["status"], "collecting")
        self.assertEqual(observed["stages"]["details"]["submittedCount"], 1)
        self.assertEqual(observed["stages"]["details"]["persistedRecordCount"], 1)

    def test_retry_failed_batch_rejects_a_different_collection_contract_before_rpa(self):
        batch = load_batch()
        invoker = FakeInvoker({"success": False}, [])
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            contract = batch.run_state.collection_contract(
                shop_id="shop-42",
                list_params={"industry": "食品饮料"},
                detail_date_params={"date_range_type": "LAST_7_DAYS"},
                target_top_n=1,
                candidate_top_n=1,
            )
            batch.run_state.save_run_state(
                batch.run_state.new_collection_summary(contract), root / "run-summary.json"
            )
            (root / "batch-manifest.json").write_text(
                json.dumps(
                    {
                        "detailDateRange": {"date_range_type": "LAST_7_DAYS"},
                        "targetTopN": 1,
                        "selectedMaterials": [],
                        "rejectedMaterials": [{"rank": 1, "material_id": "101"}],
                    }
                ),
                encoding="utf-8",
            )
            (root / "normalized").mkdir()
            (root / "normalized" / "list-records.json").write_text(
                json.dumps([{"material_id": "101"}]), encoding="utf-8"
            )

            with self.assertRaisesRegex(batch.YuntuBatchError, "different collection contract"):
                batch.retry_failed_batch(
                    shop_id="shop-99", output_dir=root, invoker=invoker
                )

        self.assertEqual(invoker.detail_calls, [])

    def test_fetch_batch_rejects_failed_details_and_continues_to_candidate_replacement(
        self,
    ):
        batch = load_batch()
        invoker = FakeInvoker(
            {
                "success": True,
                "data": [
                    {"material_id": "101"},
                    {"material_id": "202"},
                    {"material_id": "303"},
                ],
            },
            [
                {"success": False},
                {
                    "success": True,
                    "data": [
                        {
                            "materialId": "202",
                            "dateRangeType": "LAST_7_DAYS",
                            "trends": [],
                        }
                    ],
                },
                {
                    "success": True,
                    "data": [
                        {
                            "materialId": "303",
                            "dateRangeType": "LAST_7_DAYS",
                            "trends": [],
                        }
                    ],
                },
            ],
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            status = batch.fetch_batch(
                shop_id="shop-42",
                list_params={},
                detail_date_params={"date_range_type": "LAST_7_DAYS"},
                target_top_n=2,
                candidate_top_n=3,
                output_dir=temporary_directory,
                invoker=invoker,
            )
            manifest = json.loads(
                (Path(temporary_directory) / "batch-manifest.json").read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual(status, 1)
        self.assertEqual(
            [item["material_id"] for item in manifest["selectedMaterials"]],
            ["202", "303"],
        )
        self.assertEqual(
            [item["material_id"] for item in manifest["rejectedMaterials"]], ["101"]
        )
        self.assertEqual(len(invoker.detail_calls), 3)

    def test_retry_failed_batch_retries_only_rejected_materials(self):
        batch = load_batch()
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            contract = batch.run_state.collection_contract(
                shop_id="shop-42",
                list_params={"industry": "食品饮料"},
                detail_date_params={"date_range_type": "LAST_7_DAYS"},
                target_top_n=2,
                candidate_top_n=3,
            )
            batch.run_state.save_run_state(
                batch.run_state.new_collection_summary(contract), root / "run-summary.json"
            )
            (root / "normalized" / "detail-records").mkdir(parents=True)
            (root / "normalized" / "list-records.json").write_text(
                json.dumps(
                    [
                        {"material_id": "101", "title": "A"},
                        {"material_id": "202", "title": "B"},
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (root / "normalized" / "detail-records" / "202.json").write_text(
                json.dumps(
                    {
                        "material_id": "202",
                        "date_range": {"type": "LAST_7_DAYS"},
                        "trend_series": [],
                        "high_points": [],
                        "loss_points": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (root / "batch-manifest.json").write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "status": "partial",
                        "filters": {"industry": "食品饮料"},
                        "detailDateRange": {"date_range_type": "LAST_7_DAYS"},
                        "targetTopN": 2,
                        "candidateTopN": 3,
                        "candidateMaterials": [
                            {"rank": 1, "material_id": "101"},
                            {"rank": 2, "material_id": "202"},
                        ],
                        "submittedMaterials": [
                            {"rank": 1, "material_id": "101"},
                            {"rank": 2, "material_id": "202"},
                        ],
                        "selectedMaterials": [
                            {
                                "rank": 2,
                                "material_id": "202",
                                "listRecordPath": "normalized/list-records.json",
                                "detailRecordPath": "normalized/detail-records/202.json",
                                "rawDetailPath": "raw-json/details/202.json",
                                "timingsSec": {"detailFetchSec": 0.1},
                            }
                        ],
                        "rejectedMaterials": [
                            {
                                "rank": 1,
                                "material_id": "101",
                                "reason": "RpaIoError",
                                "error": "temporary failure",
                                "timingsSec": {"detailFetchSec": 0.1},
                            }
                        ],
                        "cancelledMaterials": [],
                        "timingsSec": {"totalSec": 0.2},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            invoker = FakeInvoker(
                None,
                [
                    {
                        "success": True,
                        "data": [
                            {
                                "materialId": "101",
                                "dateRangeType": "LAST_7_DAYS",
                                "trends": [],
                            }
                        ],
                    }
                ],
            )

            status = batch.retry_failed_batch(
                shop_id="shop-42",
                output_dir=root,
                invoker=invoker,
            )
            manifest = json.loads(
                (root / "batch-manifest.json").read_text(encoding="utf-8")
            )
            ready = json.loads(
                (root / "normalized" / "top-materials-rpa-ready.json").read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual(status, 0)
        self.assertEqual(len(invoker.detail_calls), 1)
        self.assertEqual(invoker.detail_calls[0][1]["material_id"], "101")
        self.assertEqual(manifest["status"], "success")
        self.assertEqual(manifest["rejectedMaterials"], [])
        self.assertEqual(
            [item["material_id"] for item in manifest["selectedMaterials"]],
            ["101", "202"],
        )
        self.assertEqual(
            [item["material_id"] for item in ready["materials"]],
            ["101", "202"],
        )


if __name__ == "__main__":
    unittest.main()
