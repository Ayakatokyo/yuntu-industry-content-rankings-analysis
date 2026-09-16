import importlib.util
import inspect
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


class RecoveringDetailInvoker(FakeInvoker):
    def __init__(self, detail_result):
        super().__init__(None, [])
        self.detail_result = detail_result
        self.submissions = []
        self.waits = []

    @property
    def supports_detail_task_recovery(self):
        return True

    def submit_detail(self, shop_id, detail_params):
        self.submissions.append((shop_id, dict(detail_params)))
        return "task-new"

    def wait_detail(self, task_group_id):
        self.waits.append(task_group_id)
        return self.detail_result


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


class MultiPeriodInvoker:
    def __init__(self):
        self.list_calls = []
        self.detail_calls = []

    def invoke_list(self, shop_id, list_params):
        self.list_calls.append((shop_id, dict(list_params)))
        if list_params.get("custom_start_date") == "20260810":
            material_id, title = "101", "小仙炖当前素材"
        elif list_params.get("custom_start_date") == "20260730":
            material_id, title = "201", "小仙炖上一周期素材"
        else:
            material_id, title = "301", "行业大盘素材"
        return {
            "success": True,
            "data": [{
                "material_id": material_id,
                "title": title,
                "show_cnt": "20万-25万",
                "object_index": {"ctr": 0.2, "cvr": 0.1, "play_3s_rate": 0.3},
                "people_tag_entry": [],
                "material_tag_entry": [],
                "page_industry": "食品饮料",
                "page_brand_scope": "指定品牌",
                "page_brands": ["小仙炖", "燕之屋", "五个女博士"],
                "page_custom_date_range": (
                    "2026-08-10 ~ 2026-08-20"
                    if material_id == "101"
                    else "2026-07-30 ~ 2026-08-09"
                    if material_id == "201"
                    else "2026-08-10 ~ 2026-08-20"
                ),
            }],
        }

    def invoke_detail(self, shop_id, detail_params):
        self.detail_calls.append((shop_id, dict(detail_params)))
        result = detail_result(detail_params["material_id"])
        result["data"][0]["dateRangeType"] = detail_params.get(
            "date_type", detail_params.get("date_range_type")
        )
        if result["data"][0]["dateRangeType"] == "CUSTOM":
            result["data"][0]["customStartDate"] = detail_params["custom_start_date"]
            result["data"][0]["customEndDate"] = detail_params["custom_end_date"]
        return result


class ParallelRankingInvoker:
    def __init__(self, *, fail_keys=None, fail_details=False):
        self.fail_keys = set(fail_keys or ())
        self.fail_details = fail_details
        self.list_calls = []
        self.detail_calls = []
        self._lock = threading.Lock()
        self._active_lists = 0
        self.max_list_active = 0

    def _list_key(self, list_params):
        if list_params.get("brand_scope_type") == "ALL_INDUSTRY":
            return "industry"
        start = list_params.get("custom_start_date")
        return {
            "20260810": "query",
            "20260730": "previous_period",
        }.get(start, "industry")

    def invoke_list(self, shop_id, list_params):
        params = dict(list_params)
        run_key = self._list_key(params)
        with self._lock:
            self.list_calls.append((shop_id, params))
            self._active_lists += 1
            self.max_list_active = max(self.max_list_active, self._active_lists)
        try:
            time.sleep(0.05)
            if run_key in self.fail_keys:
                raise RuntimeError(f"{run_key} list failed")
            date_range = (
                "2026-07-30 ~ 2026-08-09"
                if run_key == "previous_period"
                else "2026-08-10 ~ 2026-08-20"
            )
            material_id = {
                "query": "101",
                "previous_period": "201",
                "industry": "301",
            }[run_key]
            return {
                "success": True,
                "data": [{
                    "material_id": material_id,
                    "title": f"素材-{material_id}",
                    "object_index": {},
                    "people_tag_entry": [],
                    "material_tag_entry": [],
                    "page_industry": "食品饮料",
                    "page_brand_scope": "指定品牌" if run_key != "industry" else "全行业",
                    "page_brands": ["小仙炖", "燕之屋", "五个女博士"],
                    "page_custom_date_range": date_range,
                }],
            }
        finally:
            with self._lock:
                self._active_lists -= 1

    def invoke_detail(self, shop_id, detail_params):
        material_id = detail_params["material_id"]
        with self._lock:
            self.detail_calls.append((shop_id, dict(detail_params)))
        if self.fail_details:
            raise RuntimeError("detail should not be requested on resume")
        return detail_result(material_id)


def detail_result(material_id):
    return {
        "success": True,
        "data": [{"materialId": material_id, "dateRangeType": "LAST_7_DAYS", "trends": []}],
    }


class YuntuBatchTests(unittest.TestCase):
    def test_fetch_batch_resumes_a_persisted_detail_task_without_resubmitting(self):
        batch = load_batch()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            detail_params = {"date_type": "LAST_7_DAYS"}
            contract = batch.run_state.collection_contract(
                shop_id="shop-42", list_params={}, detail_date_params=detail_params,
                target_top_n=1, candidate_top_n=1,
            )
            batch.run_state.save_run_state(
                batch.run_state.new_collection_summary(contract), root / "run-summary.json"
            )
            (root / "raw-csv").mkdir()
            (root / "raw-csv" / "list.csv").write_text("material_id,title\n101,素材\n", encoding="utf-8")
            (root / "batch-manifest.json").write_text(
                json.dumps(
                    {
                        "schemaVersion": 4,
                        "filters": {}, "detailDateRange": detail_params,
                        "targetTopN": 1, "candidateTopN": 1,
                        "rankingRuns": {}, "taskRuns": {
                            "detail:101": {
                                "operation": "detail",
                                "functionCode": "rpa.conn.juliang.yt.industry.content.rankings.details",
                                "businessParams": {"material_id": "101", **detail_params},
                                "attempts": [{
                                    "attempt": 1, "taskGroupId": "task-existing",
                                    "requestStatus": "submitted", "remoteStatus": "pending",
                                    "artifactStatus": "pending", "errors": [], "artifactPaths": [],
                                }],
                            }
                        },
                        "submittedMaterials": [{"rank": 1, "material_id": "101"}],
                        "selectedMaterials": [], "rejectedMaterials": [],
                        "unresolvedMaterials": [], "cancelledMaterials": [],
                    }, ensure_ascii=False
                ), encoding="utf-8"
            )
            invoker = RecoveringDetailInvoker(
                {"status": "completed", "task_group_id": "task-existing", "payload": [
                    {"materialId": "101", "dateType": "LAST_7_DAYS", "trends": []}
                ]}
            )

            status = batch.fetch_batch(
                shop_id="shop-42", list_params={}, detail_date_params=detail_params,
                target_top_n=1, candidate_top_n=1, output_dir=root, invoker=invoker,
            )
            manifest = json.loads((root / "batch-manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(status, 0)
        self.assertEqual(invoker.submissions, [])
        self.assertEqual(invoker.waits, ["task-existing"])
        attempt = manifest["taskRuns"]["detail:101"]["attempts"][0]
        self.assertEqual(attempt["artifactStatus"], "normalized")
        self.assertEqual(attempt["remoteStatus"], "completed")

    def test_new_detail_result_uses_local_selection_group_without_remote_echo(self):
        batch = load_batch()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            summary = {"artifacts": {}}
            item = {
                "rank": 1,
                "material_id": "101",
                "selectionGroupId": "brand-a:feed",
                "selectionGroup": {
                    "id": "brand-a:feed",
                    "brand_id": "brand-a",
                    "brand_name": "品牌 A",
                    "touchpoint_code": "feed",
                    "touchpoint_name": "信息流",
                },
            }
            detail, manifest_entry = batch._persist_detail(
                root=root,
                summary=summary,
                item=item,
                gateway_result={
                    "status": "completed",
                    "payload": {
                        "materialId": "101",
                        "dateType": "LAST_7_DAYS",
                        "coreData": {"objectId": "101", "title": "新详情"},
                        "secondTrend": {},
                    },
                },
                downloader=FakeDownloader({}),
                detail_fetch_sec=0.1,
            )

        self.assertEqual(detail["selection_group"]["id"], "brand-a:feed")
        self.assertEqual(manifest_entry["material_id"], "101")

    def test_retry_batch_does_not_assign_an_unused_rank_local(self):
        batch = load_batch()
        source = inspect.getsource(batch._retry_batch_items)

        self.assertNotIn('rank = item.get("rank")', source)

    def test_persist_detail_returns_common_selected_material_entry(self):
        batch = load_batch()
        item = {"rank": 1, "material_id": "101", "selectionGroupId": "default"}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract = batch.run_state.collection_contract(
                shop_id="shop-42",
                list_params={},
                detail_date_params={"date_range_type": "LAST_7_DAYS"},
                target_top_n=1,
                candidate_top_n=1,
            )
            summary = batch.run_state.new_collection_summary(contract)

            detail, entry = batch._persist_detail(
                root=root,
                summary=summary,
                item=item,
                gateway_result=detail_result("101"),
                downloader=FakeDownloader({}),
                detail_fetch_sec=0.25,
            )

        self.assertEqual(detail["material_id"], "101")
        self.assertEqual(entry["material_id"], "101")
        self.assertEqual(
            entry["detailRecordPath"], "normalized/detail-records/101.json"
        )
        self.assertEqual(entry["rawDetailPath"], "raw-json/details/101.json")
        self.assertEqual(entry["timingsSec"], {"detailFetchSec": 0.25})
        self.assertIn("detailRecord:101", summary["artifacts"])

    def test_manifest_selection_group_round_trips_to_detail_request(self):
        batch = load_batch()
        candidate = {
            "rank": 1,
            "material_id": "101",
            "selectionGroupId": "brand-a:feed",
            "selectionGroup": {
                "id": "brand-a:feed",
                "brand_id": "brand-a",
                "brand_name": "品牌 A",
                "touchpoint_code": "feed",
                "touchpoint_name": "信息流",
            },
        }
        detail_range = {"date_type": "LAST_7_DAYS"}

        manifest_item = batch._manifest_material(candidate)

        self.assertEqual(
            batch._detail_request(manifest_item, detail_range),
            batch._detail_request(candidate, detail_range),
        )
        self.assertEqual(
            batch._expected_selection_group(manifest_item),
            candidate["selectionGroup"],
        )

    def test_fetch_batch_collects_query_previous_and_industry_lists_but_details_only_query(self):
        batch = load_batch()
        invoker = MultiPeriodInvoker()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            status = batch.fetch_batch(
                shop_id="shop-42",
                list_params={
                    "industry": "食品饮料",
                    "date_type": "CUSTOM",
                    "custom_start_date": "20260810",
                    "custom_end_date": "20260820",
                    "brand_scope_type": "SPECIFIED_BRANDS",
                    "brands": ["小仙炖", "燕之屋", "五个女博士"],
                },
                detail_date_params={
                    "date_type": "CUSTOM",
                    "custom_start_date": "20260810",
                    "custom_end_date": "20260820",
                },
                target_top_n=1,
                candidate_top_n=1,
                output_dir=root,
                invoker=invoker,
            )
            manifest = json.loads((root / "batch-manifest.json").read_text(encoding="utf-8"))
            summary = json.loads((root / "run-summary.json").read_text(encoding="utf-8"))

        self.assertEqual(status, 0)
        self.assertEqual(len(invoker.list_calls), 3)
        self.assertCountEqual(
            [params["custom_start_date"] for _, params in invoker.list_calls],
            ["20260810", "20260730", "20260810"],
        )
        industry_calls = [
            params
            for _, params in invoker.list_calls
            if params.get("brand_scope_type") == "ALL_INDUSTRY"
        ]
        self.assertEqual(len(industry_calls), 1)
        self.assertNotIn("brands", industry_calls[0])
        self.assertEqual([params["material_id"] for _, params in invoker.detail_calls], ["101"])
        self.assertEqual(set(manifest["rankingRuns"]), {"query", "previous_period", "industry"})
        self.assertTrue(all(run["status"] == "success" for run in manifest["rankingRuns"].values()))
        self.assertEqual(summary["rankingRuns"]["previous_period"]["actualDateRange"], {"startDate": "2026-07-30", "endDate": "2026-08-09"})

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

    def test_list_context_accepts_comma_delimited_specified_brands(self):
        batch = load_batch()

        result = batch._validate_list_context(
            [{
                "list_context": {
                    "brand_scope": "指定品牌",
                    "brands": ["小仙炖", "五个女博士", "燕之屋"],
                }
            }],
            {
                "brand_scope_type": "SPECIFIED_BRANDS",
                "brands": "小仙炖,五个女博士,燕之屋",
            },
        )

        self.assertTrue(result["valid"])
        self.assertEqual(result["issues"], [])

    def test_list_context_accepts_slash_delimited_specified_brands(self):
        batch = load_batch()

        result = batch._validate_list_context(
            [{
                "list_context": {
                    "brand_scope": "SPECIFIED_BRANDS",
                    "brands": ["小仙炖", "五个女博士", "燕之屋"],
                }
            }],
            {
                "brand_scope_type": "SPECIFIED_BRANDS",
                "brands": "小仙炖/五个女博士/燕之屋",
            },
        )

        self.assertTrue(result["valid"])
        self.assertEqual(result["issues"], [])

    def test_list_context_accepts_json_array_specified_brands(self):
        batch = load_batch()

        result = batch._validate_list_context(
            [{
                "list_context": {
                    "brand_scope": "指定品牌",
                    "brands": ["小仙炖", "五个女博士", "燕之屋"],
                }
            }],
            {
                "brand_scope_type": "SPECIFIED_BRANDS",
                "brands": '["小仙炖", "五个女博士", "燕之屋"]',
            },
        )

        self.assertTrue(result["valid"])
        self.assertEqual(result["issues"], [])

    def test_fetch_batch_runs_three_detail_rpas_concurrently(self):
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
        self.assertEqual(invoker.max_active, 3)

    def test_fetch_batch_requests_ranking_runs_concurrently_and_commits_in_fixed_order(self):
        batch = load_batch()
        invoker = ParallelRankingInvoker()
        list_params = {
            "industry": "食品饮料",
            "time_range_type": "CUSTOM",
            "custom_start_date": "20260810",
            "custom_end_date": "20260820",
            "brand_scope_type": "SPECIFIED_BRANDS",
            "brands": "小仙炖,燕之屋,五个女博士",
        }
        with tempfile.TemporaryDirectory() as directory:
            status = batch.fetch_batch(
                shop_id="shop-42",
                list_params=list_params,
                detail_date_params={
                    "date_range_type": "CUSTOM",
                    "custom_start_date": "20260810",
                    "custom_end_date": "20260820",
                },
                target_top_n=1,
                candidate_top_n=1,
                output_dir=directory,
                invoker=invoker,
            )
            manifest = json.loads(
                (Path(directory) / "batch-manifest.json").read_text(encoding="utf-8")
            )
            summary = json.loads(
                (Path(directory) / "run-summary.json").read_text(encoding="utf-8")
            )

        self.assertEqual(status, 0)
        self.assertEqual(
            manifest["filters"]["brands"],
            ["小仙炖", "燕之屋", "五个女博士"],
        )
        requested_scopes = [
            params
            for _, params in invoker.list_calls
            if params.get("brand_scope_type") == "SPECIFIED_BRANDS"
        ]
        self.assertEqual(len(requested_scopes), 2)
        self.assertTrue(
            all(
                params["brands"] == "小仙炖,燕之屋,五个女博士"
                for params in requested_scopes
            )
        )
        self.assertEqual(invoker.max_list_active, 3)
        self.assertEqual(
            list(manifest["rankingRuns"]), ["query", "previous_period", "industry"]
        )
        self.assertEqual(
            list(summary["rankingRuns"]), ["query", "previous_period", "industry"]
        )
        self.assertEqual(
            [item["status"] for item in manifest["rankingRuns"].values()],
            ["success", "success", "success"],
        )

    def test_open_or_new_manifest_upgrades_legacy_string_brands(self):
        batch = load_batch()
        list_params = {
            "industry": "食品饮料",
            "brand_scope_type": "SPECIFIED_BRANDS",
            "brands": "小仙炖,燕之屋,五个女博士",
        }
        detail_date_params = {"date_range_type": "LAST_7_DAYS"}
        summary = {
            "runId": "run-1",
            "parameterFingerprint": "fingerprint",
            "collectionContract": {"listParams": list_params},
        }
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "batch-manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "filters": dict(list_params),
                        "detailDateRange": detail_date_params,
                        "targetTopN": 1,
                        "candidateTopN": 1,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            manifest = batch._open_or_new_manifest(
                manifest_path=manifest_path,
                list_params=list_params,
                detail_date_params=detail_date_params,
                target_top_n=1,
                candidate_top_n=1,
                summary=summary,
            )

        self.assertEqual(
            manifest["filters"]["brands"],
            ["小仙炖", "燕之屋", "五个女博士"],
        )

    def test_fetch_batch_isolates_comparison_failure_but_query_failure_blocks_details(self):
        batch = load_batch()
        list_params = {
            "industry": "食品饮料",
            "time_range_type": "CUSTOM",
            "custom_start_date": "20260810",
            "custom_end_date": "20260820",
            "brand_scope_type": "SPECIFIED_BRANDS",
            "brands": ["小仙炖", "燕之屋", "五个女博士"],
        }
        detail_params = {
            "date_range_type": "CUSTOM",
            "custom_start_date": "20260810",
            "custom_end_date": "20260820",
        }
        with tempfile.TemporaryDirectory() as directory:
            comparison_failure = ParallelRankingInvoker(fail_keys={"industry"})
            status = batch.fetch_batch(
                shop_id="shop-42",
                list_params=list_params,
                detail_date_params=detail_params,
                target_top_n=1,
                candidate_top_n=1,
                output_dir=Path(directory) / "comparison-failure",
                invoker=comparison_failure,
            )
            comparison_manifest = json.loads(
                (Path(directory) / "comparison-failure" / "batch-manifest.json").read_text(
                    encoding="utf-8"
                )
            )

            query_failure = ParallelRankingInvoker(fail_keys={"query"})
            blocked_status = batch.fetch_batch(
                shop_id="shop-42",
                list_params=list_params,
                detail_date_params=detail_params,
                target_top_n=1,
                candidate_top_n=1,
                output_dir=Path(directory) / "query-failure",
                invoker=query_failure,
            )
            blocked_manifest = json.loads(
                (Path(directory) / "query-failure" / "batch-manifest.json").read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual(status, 1)
        self.assertEqual(comparison_failure.detail_calls[0][1]["material_id"], "101")
        self.assertEqual(comparison_manifest["rankingRuns"]["industry"]["status"], "failed")
        self.assertEqual(blocked_status, 1)
        self.assertEqual(query_failure.detail_calls, [])
        self.assertEqual(blocked_manifest["status"], "list_failed")

    def test_fetch_batch_reuses_successful_ranking_runs_and_persisted_details(self):
        batch = load_batch()
        list_params = {
            "industry": "食品饮料",
            "time_range_type": "CUSTOM",
            "custom_start_date": "20260810",
            "custom_end_date": "20260820",
            "brand_scope_type": "SPECIFIED_BRANDS",
            "brands": ["小仙炖", "燕之屋", "五个女博士"],
        }
        detail_params = {
            "date_range_type": "CUSTOM",
            "custom_start_date": "20260810",
            "custom_end_date": "20260820",
        }
        with tempfile.TemporaryDirectory() as directory:
            first = ParallelRankingInvoker()
            self.assertEqual(
                batch.fetch_batch(
                    shop_id="shop-42",
                    list_params=list_params,
                    detail_date_params=detail_params,
                    target_top_n=1,
                    candidate_top_n=1,
                    output_dir=directory,
                    invoker=first,
                ),
                0,
            )
            resumed = ParallelRankingInvoker(
                fail_keys={"query", "previous_period", "industry"},
                fail_details=True,
            )
            status = batch.fetch_batch(
                shop_id="shop-42",
                list_params=list_params,
                detail_date_params=detail_params,
                target_top_n=1,
                candidate_top_n=1,
                output_dir=directory,
                invoker=resumed,
            )

        self.assertEqual(status, 0)
        self.assertEqual(resumed.list_calls, [])
        self.assertEqual(resumed.detail_calls, [])

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
