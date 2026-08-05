import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "yuntu_run_state.py"


def load_module():
    spec = importlib.util.spec_from_file_location("yuntu_run_state", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class YuntuRunStateTests(unittest.TestCase):
    def test_parameter_fingerprint_is_stable_for_equivalent_filters(self):
        state = load_module()

        first = state.parameter_fingerprint({"industry": "食品饮料", "days": 30})
        second = state.parameter_fingerprint({"days": 30, "industry": "食品饮料"})

        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)

    def test_new_run_summary_includes_collection_contract(self):
        state = load_module()
        filters = {"industry": "食品饮料"}

        summary = state.new_run_summary(Path("/tmp/yuntu-run"), filters)

        self.assertEqual(summary["schemaVersion"], 1)
        self.assertEqual(len(summary["runId"]), 32)
        self.assertEqual(summary["parameterFingerprint"], state.parameter_fingerprint(filters))
        self.assertEqual(summary["filters"], filters)
        self.assertEqual(summary["status"], "collecting")
        self.assertEqual(summary["artifacts"], {})
        self.assertEqual(summary["nextAction"], {"command": "fetch", "allowsRpa": True})

    def test_new_run_summary_snapshots_nested_filters_for_fingerprint(self):
        state = load_module()
        filters = {"industry": {"name": "食品饮料"}}

        summary = state.new_run_summary(Path("/tmp/yuntu-run"), filters)
        filters["industry"]["name"] = "美妆"

        expected_filters = {"industry": {"name": "食品饮料"}}
        self.assertEqual(summary["filters"], expected_filters)
        self.assertEqual(
            summary["parameterFingerprint"],
            state.parameter_fingerprint(expected_filters),
        )

    def test_register_artifact_writes_relative_path_checksum_and_size(self):
        state = load_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "raw-csv" / "list.csv"
            source.parent.mkdir()
            source.write_text("material_id\n101\n", encoding="utf-8")
            summary = state.new_run_summary(root, {"industry": "食品饮料"})

            state.register_artifact(summary, root, "ranking_list", source, "local_artifact")

            artifact = summary["artifacts"]["ranking_list"]
            self.assertEqual(artifact["path"], "raw-csv/list.csv")
            self.assertEqual(artifact["source"], "local_artifact")
            self.assertEqual(artifact["sizeBytes"], source.stat().st_size)
            self.assertEqual(artifact["sha256"], state.sha256_file(source))
            self.assertEqual(artifact["parseStatus"], "pending")

    def test_register_artifact_rejects_empty_and_outside_files(self):
        state = load_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            root.mkdir()
            summary = state.new_run_summary(root, {})
            empty = root / "empty.csv"
            empty.touch()
            outside = Path(directory) / "outside.csv"
            outside.write_text("value\n", encoding="utf-8")

            with self.assertRaisesRegex(state.YuntuRunStateError, "nonempty"):
                state.register_artifact(summary, root, "empty", empty, "local_artifact")
            with self.assertRaisesRegex(state.YuntuRunStateError, "within"):
                state.register_artifact(summary, root, "outside", outside, "local_artifact")

    def test_save_and_load_run_state_atomically(self):
        state = load_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "run-summary.json"
            summary = state.new_run_summary(root, {"industry": "食品饮料"})

            saved_path = state.save_run_state(summary, path)

            self.assertEqual(saved_path, path)
            self.assertEqual(state.load_run_state(path), summary)
            self.assertFalse(list(root.glob("*.tmp")))

    def test_validate_artifact_detects_file_changes(self):
        state = load_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "raw-csv" / "list.csv"
            source.parent.mkdir()
            source.write_text("material_id\n101\n", encoding="utf-8")
            summary = state.new_run_summary(root, {})
            state.register_artifact(summary, root, "ranking_list", source, "local_artifact")

            self.assertEqual(state.validate_artifact(summary, root, "ranking_list"), source)
            source.write_text("material_id\n102\n", encoding="utf-8")

            with self.assertRaisesRegex(state.YuntuRunStateError, "checksum"):
                state.validate_artifact(summary, root, "ranking_list")


if __name__ == "__main__":
    unittest.main()
