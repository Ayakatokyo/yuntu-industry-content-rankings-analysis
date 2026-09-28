"""Exercise first-batch submission barriers using landed CSV artifacts."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_yuntu_batch import FakeDownloader, FakeInvoker, load_batch


def csv_result(material_id):
    return {"status": "completed", "files": [{"fileUrl": f"https://files.example/{material_id}.csv"}]}


class FirstBatchCsvGateTests(unittest.TestCase):
    def options(self, root, invoker, downloader=None):
        return dict(shop_id="shop-42", list_params={},
                    detail_date_params={"date_type": "LAST_7_DAYS"},
                    target_top_n=4, candidate_top_n=6, output_dir=root,
                    invoker=invoker, downloader=downloader or FakeDownloader({}))

    def invoker(self, results):
        return FakeInvoker({"success": True, "data": [
            {"material_id": str(n)} for n in range(101, 107)
        ]}, {str(n): results.get(str(n), {"status": "completed", "files": []})
            for n in range(101, 107)}, csv_details=False)

    def test_zero_valid_csv_blocks_replacement_and_plain_resume(self):
        batch = load_batch()
        for body in ("materialId,trends\n", "error,message\ninvalid,wrong account\n",
                     "materialId,trends\n999,[]\n", "<html>failed</html>",
                     "materialId,error\n101,bad parameters\n", "materialId,dateType,trends\n101,LAST_7_DAYS,\n",
                     "materialId,dateType,trends\n101,LAST_7_DAYS,[broken\n", "materialId,dateType,title\n101,LAST_7_DAYS,\n",
                     "materialId,dateType,trends\n101,LAST_30_DAYS,[]\n",
                     'materialId\x01dateType\x01coreData\n101\x01LAST_7_DAYS\x01{"objectId":"999","title":"错误素材"}\n',
                     "materialId,dateType,trends\n101,LAST_7_DAYS,[]\n999,LAST_7_DAYS,[]\n"):
            with self.subTest(body=body), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                invoker = self.invoker({"101": csv_result("101")})
                options = self.options(root, invoker, FakeDownloader({"https://files.example/101.csv": body}))
                self.assertEqual(batch.fetch_batch(**options), 1)
                self.assertEqual(len(invoker.detail_calls), 3)
                manifest = json.loads((root / "batch-manifest.json").read_text())
                self.assertEqual(manifest["status"], "paused")
                self.assertEqual(manifest["firstBatchCsvGate"]["status"], "blocked")
                self.assertEqual(manifest["firstBatchCsvGate"]["errorCode"], "first_batch_no_valid_csv")
                self.assertIn("入参可能有问题", manifest["firstBatchCsvGate"]["message"])
                invoker.list_calls.clear()
                invoker.detail_calls.clear()
                self.assertEqual(batch.fetch_batch(**options), 1)
                self.assertEqual(invoker.list_calls, [])
                self.assertEqual(invoker.detail_calls, [])
                self.assertEqual(batch.collection_status(output_dir=root)["firstBatchCsvGate"]["status"], "blocked")

    def test_valid_json_payload_cannot_replace_csv_evidence(self):
        batch = load_batch()
        invoker = self.invoker({str(n): {"status": "completed", "payload": {
            "materialId": str(n), "dateType": "LAST_7_DAYS", "trends": []}}
            for n in range(101, 107)})
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(batch.fetch_batch(**self.options(Path(tmp), invoker)), 1)
            self.assertEqual(len(invoker.detail_calls), 3)

    def test_one_valid_csv_allows_later_wave_even_when_highlights_fail(self):
        batch = load_batch()
        results = {str(n): csv_result(str(n)) for n in range(103, 107)}
        invoker = self.invoker(results)
        files = {f"https://files.example/{n}.csv":
                 f"materialId,dateType,trends\n{n},LAST_7_DAYS,[]\n" for n in range(103, 107)}
        with tempfile.TemporaryDirectory() as tmp, patch.object(
                batch, "generate_standard_highlights_for_detail", side_effect=RuntimeError("video unavailable")):
            root = Path(tmp)
            self.assertEqual(batch.fetch_batch(**self.options(root, invoker, FakeDownloader(files))), 1)
            self.assertEqual(len(invoker.detail_calls), 6)
            manifest = json.loads((root / "batch-manifest.json").read_text())
            self.assertEqual(manifest["firstBatchCsvGate"]["status"], "passed")
            self.assertEqual(len(manifest["selectedMaterials"]), 4)

    def test_unconfirmed_first_batch_only_polls_existing_ids_on_resume(self):
        batch = load_batch()

        class AsyncInvoker(FakeInvoker):
            supports_detail_task_recovery = True

            def __init__(self):
                super().__init__({"success": True, "data": [
                    {"material_id": str(n)} for n in range(101, 107)]}, {})
                self.waits, self.submissions = [], []
                self.finished = False

            def submit_detail(self, shop_id, params):
                self.submissions.append(dict(params))
                return "task-" + params["material_id"]

            def wait_detail(self, task_id):
                self.waits.append(task_id)
                if not self.finished:
                    raise RuntimeError("poll timeout")
                return {"status": "completed", "files": []}

        invoker = AsyncInvoker()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            options = self.options(root, invoker)
            self.assertEqual(batch.fetch_batch(**options), 1)
            self.assertEqual(len(invoker.submissions), 3)
            self.assertEqual(batch.collection_status(output_dir=root)["firstBatchCsvGate"]["status"], "unconfirmed")
            invoker.finished = True
            invoker.list_calls.clear()
            invoker.waits.clear()
            self.assertEqual(batch.fetch_batch(**options), 1)
            self.assertEqual(len(invoker.submissions), 3)
            self.assertEqual(invoker.list_calls, [])
            self.assertEqual(set(invoker.waits), {"task-101", "task-102", "task-103"})
            self.assertEqual(batch.collection_status(output_dir=root)["firstBatchCsvGate"]["status"], "blocked")

    def test_submit_unknown_does_not_launch_second_wave(self):
        batch = load_batch()
        invoker = self.invoker({})
        invoker.supports_detail_task_recovery = True
        invoker.submit_detail = lambda *args: (_ for _ in ()).throw(RuntimeError("transport request failed"))
        invoker.wait_detail = lambda *args: self.fail("missing ID cannot be polled")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(batch.fetch_batch(**self.options(root, invoker)), 1)
            manifest = json.loads((root / "batch-manifest.json").read_text())
            self.assertEqual(len(manifest["submittedMaterials"]), 3)
            self.assertEqual(manifest["firstBatchCsvGate"]["status"], "unconfirmed")

    def test_single_material_first_batch_does_not_expand_after_failure(self):
        batch = load_batch()
        invoker = self.invoker({})
        with tempfile.TemporaryDirectory() as tmp:
            options = self.options(Path(tmp), invoker)
            options["target_top_n"] = 1
            self.assertEqual(batch.fetch_batch(**options), 1)
            self.assertEqual(len(invoker.detail_calls), 1)

    def test_cli_reports_actionable_pause_message(self):
        import contextlib
        import io
        load_batch()
        import rpa_connector

        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, patch.object(
                rpa_connector, "fetch_batch_analysis", return_value=1), patch.object(
                rpa_connector, "collection_status", return_value={"firstBatchCsvGate": {
                    "status": "blocked", "message": "入参可能有问题，请修正后使用新运行目录"}}), \
                contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(io.StringIO()):
            status = rpa_connector.main(["fetch", "--shop-id", "shop-42", "--params-json",
                                         '{"list": {}, "detail": {}}', "--output-dir", tmp])
        self.assertEqual(status, 1)
        self.assertIn("入参可能有问题", stderr.getvalue())

    def test_unknown_status_response_remains_recoverable(self):
        batch = load_batch()
        for remote_status in ("pending", "unexpected"):
            with self.subTest(status=remote_status), tempfile.TemporaryDirectory() as tmp:
                invoker = self.invoker({})
                invoker.supports_detail_task_recovery = True
                invoker.submit_detail = lambda shop, params: "task-" + params["material_id"]
                invoker.wait_detail = lambda task_id: {"status": remote_status, "files": []}
                root = Path(tmp)
                self.assertEqual(batch.fetch_batch(**self.options(root, invoker)), 1)
                manifest = json.loads((root / "batch-manifest.json").read_text())
                self.assertEqual(manifest["firstBatchCsvGate"]["status"], "unconfirmed")
                self.assertEqual(len(manifest["submittedMaterials"]), 3)
                self.assertIsNotNone(batch._active_detail_task_attempt(manifest, "101"))

    def test_normalized_write_failure_is_not_no_csv(self):
        batch = load_batch()
        invoker = self.invoker({str(n): csv_result(str(n)) for n in range(101, 107)})
        files = {f"https://files.example/{n}.csv":
                 f"materialId,dateType,trends\n{n},LAST_7_DAYS,[]\n" for n in range(101, 107)}
        real_write = batch.write_json_atomically

        def fail_normalized_detail(value, path, **kwargs):
            if Path(path).parent.name == "detail-records":
                raise OSError("disk full after CSV validated")
            return real_write(value, path, **kwargs)

        with tempfile.TemporaryDirectory() as tmp, patch.object(batch, "write_json_atomically", fail_normalized_detail):
            root = Path(tmp)
            self.assertEqual(batch.fetch_batch(**self.options(root, invoker, FakeDownloader(files))), 1)
            manifest = json.loads((root / "batch-manifest.json").read_text())
            self.assertEqual(manifest["firstBatchCsvGate"]["status"], "passed")

    def test_resume_revalidates_csv_written_before_gate_checkpoint(self):
        batch = load_batch()
        files = {"https://files.example/101.csv": "materialId,dateType,trends\n101,LAST_7_DAYS,[]\n"}
        invoker = self.invoker({"101": csv_result("101")})
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            options = self.options(root, invoker, FakeDownloader(files))
            options["target_top_n"] = 1
            self.assertEqual(batch.fetch_batch(**options), 0)
            path = root / "batch-manifest.json"
            manifest = json.loads(path.read_text())
            manifest["firstBatchCsvGate"] = {"status": "pending", "materialIds": ["101"], "outcomes": {}}
            path.write_text(json.dumps(manifest))
            invoker.list_calls.clear()
            invoker.detail_calls.clear()
            self.assertEqual(batch.fetch_batch(**options), 0)
            self.assertEqual(invoker.list_calls, [])
            self.assertEqual(invoker.detail_calls, [])

    def test_definite_remote_failure_blocks_with_input_warning(self):
        batch = load_batch()
        for raises in (False, True):
            with self.subTest(raises=raises), tempfile.TemporaryDirectory() as tmp:
                invoker = self.invoker({})
                invoker.supports_detail_task_recovery = True
                invoker.submit_detail = lambda shop, params: "task-" + params["material_id"]

                def failed(task_id):
                    if raises:
                        raise RuntimeError("RPA task failed: " + task_id)
                    return {"status": "failed", "files": []}

                invoker.wait_detail = failed
                root = Path(tmp)
                self.assertEqual(batch.fetch_batch(**self.options(root, invoker)), 1)
                manifest = json.loads((root / "batch-manifest.json").read_text())
                self.assertEqual(manifest["firstBatchCsvGate"]["status"], "blocked")
                self.assertIn("入参可能有问题", manifest["firstBatchCsvGate"]["message"])
                self.assertIsNone(batch._active_detail_task_attempt(manifest, "101"))

    def test_one_valid_csv_cannot_release_unconfirmed_batch_then_resume_can(self):
        batch = load_batch()
        invoker = self.invoker({})
        invoker.supports_detail_task_recovery = True
        submissions = []
        resolved = False

        def submit(shop, params):
            submissions.append(params["material_id"])
            return "task-" + params["material_id"]

        def wait_result(task_id):
            material_id = task_id.removeprefix("task-")
            if material_id == "102" and not resolved:
                raise RuntimeError("poll timeout")
            if material_id == "103":
                raise RuntimeError("RPA task failed: " + task_id)
            return csv_result(material_id)

        invoker.submit_detail, invoker.wait_detail = submit, wait_result
        files = {f"https://files.example/{n}.csv":
                 f"materialId,dateType,trends\n{n},LAST_7_DAYS,[]\n" for n in range(101, 107)}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            options = self.options(root, invoker, FakeDownloader(files))
            self.assertEqual(batch.fetch_batch(**options), 1)
            self.assertEqual(submissions, ["101", "102", "103"])
            self.assertEqual(batch.collection_status(output_dir=root)["firstBatchCsvGate"]["status"], "unconfirmed")
            resolved = True
            self.assertEqual(batch.fetch_batch(**options), 1)
            self.assertEqual(submissions, ["101", "102", "103", "104", "105"])
            observed = batch.collection_status(output_dir=root)
            self.assertEqual(observed["firstBatchCsvGate"]["status"], "passed")
            self.assertEqual(observed["stages"]["details"]["selectedCount"], 4)
            self.assertEqual(observed["stages"]["details"]["unresolvedCount"], 0)

    def test_dynamic_fetch_cannot_bypass_batch_gate(self):
        import argparse
        import contextlib
        import io
        from test_rpa_dynamic_refactor import load_module, LIST_CLIENT_PATH

        for operation in ("details", "list"):
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as tmp:
                client = load_module("standalone_gate_client", LIST_CLIENT_PATH)
                client.CONNECTOR_CODE = "rpa.conn.juliang.yt.industry.content.rankings." + operation
                root = Path(tmp)
                if operation == "list":
                    (root / "batch-manifest.json").write_text(json.dumps({"firstBatchCsvGate": {
                        "status": "blocked", "message": "入参可能有问题，已暂停后续所有 RPA"}}))
                args = argparse.Namespace(shop_id="shop-42", params_json="{}", params_file=None,
                    output_dir=str(root), no_download=True, preview_limit=5, include_raw_result=False)
                with patch.object(client, "fetch_connector_detail", return_value={}), \
                        patch.object(client, "validate_business_params", return_value={}), \
                        patch.object(client, "invoke", return_value={"status": "completed"}) as invoke, \
                        contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaises(client.ContractError):
                        client.cmd_fetch(args)
                    invoke.assert_not_called()


if __name__ == "__main__":
    unittest.main()
