import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
MODULE_PATH = SCRIPTS_DIR / "yuntu_hot_material_config.py"


def load_module():
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    spec = importlib.util.spec_from_file_location("yuntu_hot_material_config", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class YuntuHotMaterialConfigTests(unittest.TestCase):
    def test_loads_global_rule_from_json_config(self):
        config = load_module()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "hot-material-rules.json"
            path.write_text(
                json.dumps({
                    "schemaVersion": 1,
                    "hotMaterialRule": {
                        "metric": "exposure_interval_min",
                        "comparison": "gte",
                        "threshold": 500000,
                    },
                }),
                encoding="utf-8",
            )

            rule = config.load_hot_material_rule(path)

        self.assertEqual(rule, {
            "metric": "exposure_interval_min",
            "comparison": "gte",
            "threshold": 500000,
        })

    def test_rejects_invalid_hot_material_config(self):
        config = load_module()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_text(
                json.dumps({
                    "schemaVersion": 1,
                    "hotMaterialRule": {
                        "metric": "show_cnt",
                        "comparison": "gte",
                        "threshold": 0,
                    },
                }),
                encoding="utf-8",
            )

            with self.assertRaises(config.HotMaterialConfigError):
                config.load_hot_material_rule(path)

    def test_default_config_is_project_scoped_and_auditable(self):
        config = load_module()

        self.assertEqual(config.DEFAULT_HOT_MATERIAL_CONFIG_PATH, ROOT / "config" / "hot-material-rules.json")
        self.assertEqual(config.load_hot_material_rule(), {
            "metric": "exposure_interval_min",
            "comparison": "gte",
            "threshold": 200000,
        })


if __name__ == "__main__":
    unittest.main()
