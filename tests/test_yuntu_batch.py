import importlib.util
import json
import sys
import tempfile
import threading
import time
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
        self.detail_results = (
            dict(detail_results)
            if isinstance(detail_results, dict)
            else list(detail_results)
        )
        self.list_calls = []
        self.detail_calls = []

    def invoke_list(self, shop_id, list_params):
        self.list_calls.append((shop_id, list_params))
        return self.list_result

    def invoke_detail(self, shop_id, detail_params):
        self.detail_calls.append((shop_id, detail_params))
        if isinstance(self.detail_results, dict):
            return self.detail_results[detail_params["material_id"]]
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


class ConcurrentInvoker:
    def __init__(self, material_ids, detail_handler):
        self.material_ids = material_ids
        self.detail_handler = detail_handler
        self.list_calls = []
        self.detail_calls = []
        self.detail_started = []
        self._lock = threading.Lock()
        self._active = 0
        self.max_active = 0

    def invoke_list(self, shop_id, list_params):
        self.list_calls.append((shop_id, list_params))
        return {
            "success": True,
            "data": [
                {
                    "material_id": material_id,
                    "title": f"素材-{material_id}",
                    "object_index": {},
                    "people_tag_entry": [],
                    "material_tag_entry": [],
                    "page_industry": "食品饮料",
                }
                for material_id in self.material_ids
            ],
        }

    def invoke_detail(self, shop_id, detail_params):
        material_id = detail_params["material_id"]
        with self._lock:
            self.detail_calls.append((shop_id, detail_params))
            self.detail_started.append(material_id)
            self._active += 1
            self.max_active = max(self.max_active, self._active)
        try:
            return self.detail_handler(material_id)
        finally:
            with self._lock:
                self._active -= 1


def detail_result(material_id):
    return {
        "success": True,
        "data": [{"materialId": material_id, "dateRangeType": "LAST_7_DAYS", "trends": []}],
    }


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

    def test_list_context_accepts_display_formatted_custom_dates(self):
        batch = load_batch()

        result = batch._validate_list_context(
            [
                {
                    "list_context": {
                        "custom_date_range": "2026-07-30 ~ 2026-08-05",
                    }
                }
            ],
            {
                "time_range_type": "CUSTOM",
                "custom_start_date": "20260730",
                "custom_end_date": "20260805",
            },
        )

        self.assertTrue(result["valid"])
        self.assertEqual(result["issues"], [])

    def test_fetch_batch_runs_two_detail_rpas_concurrently(self):
        batch = load_batch()

        def slow_detail(material_id):
            time.sleep(0.08)
            return detail_result(material_id)

        invoker = ConcurrentInvoker(["101", "202", "303"], slow_detail)
        with tempfile.TemporaryDirectory() as directory:
            status = batch.fetch_batch(
                shop_id="shop-42",
                list_params={"industry": "食品饮料"},
                detail_date_params={"date_range_type": "LAST_7_DAYS"},
                target_top_n=3,
                candidate_top_n=3,
                output_dir=directory,
                invoker=invoker,
            )

        self.assertEqual(status, 0)
        self.assertEqual(invoker.max_active, 2)

    def test_fetch_batch_starts_highlights_before_other_wave_details_finish(self):
        batch = load_batch()
        highlights_started = threading.Event()
        release_details = threading.Event()

        def detail_handler(material_id):
            if material_id in {"202", "303"}:
                release_details.wait(timeout=1)
            return detail_result(material_id)

        def highlighter(detail, _root):
            if detail["material_id"] == "101":
                highlights_started.set()
            return []

        batch.generate_standard_highlights_for_detail = highlighter
        invoker = ConcurrentInvoker(["101", "202", "303"], detail_handler)
        result = []
        with tempfile.TemporaryDirectory() as directory:
            runner = threading.Thread(
                target=lambda: result.append(
                    batch.fetch_batch(
                        shop_id="shop-42",
                        list_params={"industry": "食品饮料"},
                        detail_date_params={"date_range_type": "LAST_7_DAYS"},
                        target_top_n=3,
                        candidate_top_n=3,
                        output_dir=directory,
                        invoker=invoker,
                    )
                )
            )
            runner.start()
            try:
                self.assertTrue(highlights_started.wait(timeout=0.3))
            finally:
                release_details.set()
                runner.join(timeout=2)

        self.assertFalse(runner.is_alive())
        self.assertEqual(result, [0])

    def test_fetch_batch_waits_for_wave_highlights_before_next_wave(self):
        batch = load_batch()
        first_highlight_started = threading.Event()
        release_highlight = threading.Event()

        def highlighter(detail, _root):
            if detail["material_id"] == "101":
                first_highlight_started.set()
                release_highlight.wait(timeout=1)
            return []

        batch.generate_standard_highlights_for_detail = highlighter
        invoker = ConcurrentInvoker(["101", "202", "303", "404"], detail_result)
        result = []
        with tempfile.TemporaryDirectory() as directory:
            runner = threading.Thread(
                target=lambda: result.append(
                    batch.fetch_batch(
                        shop_id="shop-42",
                        list_params={"industry": "食品饮料"},
                        detail_date_params={"date_range_type": "LAST_7_DAYS"},
                        target_top_n=4,
                        candidate_top_n=4,
                        output_dir=directory,
                        invoker=invoker,
                    )
                )
            )
            runner.start()
            try:
                self.assertTrue(first_highlight_started.wait(timeout=1))
                self.assertNotIn("404", invoker.detail_started)
            finally:
                release_highlight.set()
                runner.join(timeout=2)

        self.assertFalse(runner.is_alive())
        self.assertEqual(result, [0])

    def test_highlight_failure_does_not_request_an_extra_detail(self):
        batch = load_batch()

        def failing_highlighter(detail, _root):
            if detail["material_id"] == "101":
                raise RuntimeError("ffmpeg unavailable")
            return []

        batch.generate_standard_highlights_for_detail = failing_highlighter
        invoker = ConcurrentInvoker(["101", "202", "303", "404"], detail_result)
        with tempfile.TemporaryDirectory() as directory:
            status = batch.fetch_batch(
                shop_id="shop-42",
                list_params={"industry": "食品饮料"},
                detail_date_params={"date_range_type": "LAST_7_DAYS"},
                target_top_n=3,
                candidate_top_n=4,
                output_dir=directory,
                invoker=invoker,
            )
            manifest = json.loads(
                (Path(directory) / "batch-manifest.json").read_text(encoding="utf-8")
            )

        self.assertEqual(status, 0)
        self.assertNotIn("404", invoker.detail_started)
        self.assertEqual(
            next(
                item["postprocessStatus"]
                for item in manifest["selectedMaterials"]
                if item["material_id"] == "101"
            ),
            "failed",
        )

    def test_fetch_batch_downloads_csv_normalizes_and_writes_manifest(self):
        batch = load_batch()
        invoker = FakeInvoker(
            self.files_result("https://files.example/list.csv"),
            {
                "101": self.files_result("https://files.example/101.csv"),
                "202": self.files_result("https://files.example/202.csv"),
            },
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

    def test_fetch_batch_resume_skips_persisted_detail(self):
        batch = load_batch()
        invoker = FakeInvoker(
            {"success": False},
            [
                {
                    "success": True,
                    "data": [
                        {
                            "materialId": "202",
                            "dateRangeType": "LAST_7_DAYS",
                            "trends": [],
                        }
                    ],
                }
            ],
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "raw-csv").mkdir(parents=True)
            (root / "normalized" / "detail-records").mkdir(parents=True)
            (root / "raw-csv" / "list.csv").write_text(
                "material_id\x01title\x01object_index\x01people_tag_entry\x01material_tag_entry\x01page_industry\n"
                '101\x01A\x01{"ctr":0.7}\x01[]\x01[]\x01食品饮料\n'
                '202\x01B\x01{"ctr":0.4}\x01[]\x01[]\x01食品饮料\n',
                encoding="utf-8",
            )
            (root / "normalized" / "detail-records" / "101.json").write_text(
                json.dumps(
                    {
                        "material_id": "101",
                        "date_range": {"type": "LAST_7_DAYS"},
                        "trend_series": [],
                        "high_points": [],
                        "loss_points": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            contract = batch.run_state.collection_contract(
                shop_id="shop-42",
                list_params={"industry": "食品饮料"},
                detail_date_params={"date_range_type": "LAST_7_DAYS"},
                target_top_n=2,
                candidate_top_n=2,
            )
            batch.run_state.save_run_state(
                batch.run_state.new_collection_summary(contract), root / "run-summary.json"
            )
            (root / "batch-manifest.json").write_text(
                json.dumps(
                    {
                        "schemaVersion": 2,
                        "status": "running",
                        "filters": {"industry": "食品饮料"},
                        "detailDateRange": {"date_range_type": "LAST_7_DAYS"},
                        "targetTopN": 2,
                        "candidateTopN": 2,
                        "submittedMaterials": [{"rank": 1, "material_id": "101"}],
                        "selectedMaterials": [],
                        "rejectedMaterials": [],
                        "cancelledMaterials": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            status = batch.fetch_batch(
                shop_id="shop-42",
                list_params={"industry": "食品饮料"},
                detail_date_params={"date_range_type": "LAST_7_DAYS"},
                target_top_n=2,
                candidate_top_n=2,
                output_dir=root,
                invoker=invoker,
            )
            manifest = json.loads(
                (root / "batch-manifest.json").read_text(encoding="utf-8")
            )

        self.assertEqual(status, 0)
        self.assertEqual(len(invoker.list_calls), 0)
        self.assertEqual(
            [params["material_id"] for _, params in invoker.detail_calls], ["202"]
        )
        self.assertEqual(
            [item["material_id"] for item in manifest["selectedMaterials"]],
            ["101", "202"],
        )

    def test_fetch_batch_marks_unpersisted_submission_unresolved_without_retrying(self):
        batch = load_batch()
        invoker = FakeInvoker(
            {"success": False},
            [
                {
                    "success": True,
                    "data": [
                        {
                            "materialId": "202",
                            "dateRangeType": "LAST_7_DAYS",
                            "trends": [],
                        }
                    ],
                }
            ],
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "raw-csv").mkdir(parents=True)
            (root / "raw-csv" / "list.csv").write_text(
                "material_id\x01title\x01object_index\x01people_tag_entry\x01material_tag_entry\x01page_industry\n"
                '101\x01A\x01{"ctr":0.7}\x01[]\x01[]\x01食品饮料\n'
                '202\x01B\x01{"ctr":0.4}\x01[]\x01[]\x01食品饮料\n',
                encoding="utf-8",
            )
            contract = batch.run_state.collection_contract(
                shop_id="shop-42",
                list_params={"industry": "食品饮料"},
                detail_date_params={"date_range_type": "LAST_7_DAYS"},
                target_top_n=1,
                candidate_top_n=2,
            )
            batch.run_state.save_run_state(
                batch.run_state.new_collection_summary(contract), root / "run-summary.json"
            )
            (root / "batch-manifest.json").write_text(
                json.dumps(
                    {
                        "schemaVersion": 2,
                        "status": "running",
                        "filters": {"industry": "食品饮料"},
                        "detailDateRange": {"date_range_type": "LAST_7_DAYS"},
                        "targetTopN": 1,
                        "candidateTopN": 2,
                        "submittedMaterials": [{"rank": 1, "material_id": "101"}],
                        "selectedMaterials": [],
                        "rejectedMaterials": [],
                        "cancelledMaterials": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            status = batch.fetch_batch(
                shop_id="shop-42",
                list_params={"industry": "食品饮料"},
                detail_date_params={"date_range_type": "LAST_7_DAYS"},
                target_top_n=1,
                candidate_top_n=2,
                output_dir=root,
                invoker=invoker,
            )
            manifest = json.loads(
                (root / "batch-manifest.json").read_text(encoding="utf-8")
            )

        self.assertEqual(status, 0)
        self.assertEqual(
            [params["material_id"] for _, params in invoker.detail_calls], ["202"]
        )
        self.assertEqual(
            [item["material_id"] for item in manifest["unresolvedMaterials"]],
            ["101"],
        )
        self.assertEqual(
            manifest["unresolvedMaterials"][0]["reason"],
            "interrupted_before_persistence",
        )

    def test_retry_unresolved_batch_retries_only_unresolved_materials(self):
        batch = load_batch()
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "normalized").mkdir(parents=True)
            (root / "normalized" / "list-records.json").write_text(
                json.dumps(
                    [
                        {"material_id": "101", "rank": 1},
                        {"material_id": "202", "rank": 2},
                    ]
                ),
                encoding="utf-8",
            )
            contract = batch.run_state.collection_contract(
                shop_id="shop-42",
                list_params={"industry": "食品饮料"},
                detail_date_params={"date_range_type": "LAST_7_DAYS"},
                target_top_n=1,
                candidate_top_n=2,
            )
            batch.run_state.save_run_state(
                batch.run_state.new_collection_summary(contract), root / "run-summary.json"
            )
            (root / "batch-manifest.json").write_text(
                json.dumps(
                    {
                        "schemaVersion": 2,
                        "status": "partial",
                        "filters": {"industry": "食品饮料"},
                        "detailDateRange": {"date_range_type": "LAST_7_DAYS"},
                        "targetTopN": 1,
                        "candidateTopN": 2,
                        "candidateMaterials": [
                            {"rank": 1, "material_id": "101"},
                            {"rank": 2, "material_id": "202"},
                        ],
                        "submittedMaterials": [{"rank": 1, "material_id": "101"}],
                        "selectedMaterials": [],
                        "rejectedMaterials": [],
                        "unresolvedMaterials": [
                            {
                                "rank": 1,
                                "material_id": "101",
                                "reason": "interrupted_before_persistence",
                            }
                        ],
                        "cancelledMaterials": [],
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

            status = batch.retry_unresolved_batch(
                shop_id="shop-42", output_dir=root, invoker=invoker
            )
            manifest = json.loads(
                (root / "batch-manifest.json").read_text(encoding="utf-8")
            )

        self.assertEqual(status, 0)
        self.assertEqual(
            [params["material_id"] for _, params in invoker.detail_calls], ["101"]
        )
        self.assertEqual(manifest["unresolvedMaterials"], [])
        self.assertEqual(
            [item["material_id"] for item in manifest["selectedMaterials"]], ["101"]
        )

    def test_retry_failed_batch_keeps_partial_status_when_unresolved_remain(self):
        batch = load_batch()
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "normalized").mkdir(parents=True)
            (root / "normalized" / "list-records.json").write_text(
                json.dumps([{"material_id": "101", "rank": 1}]), encoding="utf-8"
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
            (root / "batch-manifest.json").write_text(
                json.dumps(
                    {
                        "status": "partial",
                        "detailDateRange": {"date_range_type": "LAST_7_DAYS"},
                        "targetTopN": 1,
                        "selectedMaterials": [{"rank": 1, "material_id": "101"}],
                        "rejectedMaterials": [],
                        "unresolvedMaterials": [
                            {"rank": 2, "material_id": "202", "reason": "interrupted_before_persistence"}
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            status = batch.retry_failed_batch(
                shop_id="shop-42",
                output_dir=root,
                invoker=FakeInvoker(None, []),
            )
            manifest = json.loads(
                (root / "batch-manifest.json").read_text(encoding="utf-8")
            )

        self.assertEqual(status, 1)
        self.assertEqual(manifest["status"], "partial")

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
            {
                "101": {"success": False},
                "202": {
                    "success": True,
                    "data": [
                        {
                            "materialId": "202",
                            "dateRangeType": "LAST_7_DAYS",
                            "trends": [],
                        }
                    ],
                },
                "303": {
                    "success": True,
                    "data": [
                        {
                            "materialId": "303",
                            "dateRangeType": "LAST_7_DAYS",
                            "trends": [],
                        }
                    ],
                },
            },
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

    def test_fetch_batch_replaces_only_within_the_same_brand_touchpoint_group(self):
        batch = load_batch()
        invoker = FakeInvoker(
            {
                "success": True,
                "data": [
                    {"material_id": "101", "selectionGroupId": "brand-a:feed", "brandId": "brand-a", "touchpointCode": "feed"},
                    {"material_id": "201", "selectionGroupId": "brand-b:feed", "brandId": "brand-b", "touchpointCode": "feed"},
                    {"material_id": "102", "selectionGroupId": "brand-a:feed", "brandId": "brand-a", "touchpointCode": "feed"},
                    {"material_id": "202", "selectionGroupId": "brand-b:feed", "brandId": "brand-b", "touchpointCode": "feed"},
                ],
            },
            {
                "101": {"success": False},
                "201": {"success": True, "data": [{"materialId": "201", "selectionGroupId": "brand-b:feed", "brandId": "brand-b", "touchpointCode": "feed", "trends": []}]},
                "102": {"success": True, "data": [{"materialId": "102", "selectionGroupId": "brand-a:feed", "brandId": "brand-a", "touchpointCode": "feed", "trends": []}]},
            },
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            status = batch.fetch_batch(
                shop_id="shop-42",
                list_params={},
                detail_date_params={"date_range_type": "LAST_7_DAYS"},
                target_top_n=1,
                candidate_top_n=2,
                output_dir=root,
                invoker=invoker,
            )
            manifest = json.loads((root / "batch-manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(status, 1)
        self.assertEqual(
            [item["material_id"] for item in manifest["submittedMaterials"]], ["101", "201", "102"]
        )
        self.assertEqual(
            {item["selectionGroupId"] for item in manifest["selectedMaterials"]},
            {"brand-a:feed", "brand-b:feed"},
        )
        self.assertEqual(
            [item["material_id"] for item in manifest["cancelledMaterials"]], ["202"]
        )

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
