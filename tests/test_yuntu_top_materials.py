import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
MODULE_PATH = SCRIPTS_DIR / "yuntu_top_materials.py"


def load_module():
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    spec = importlib.util.spec_from_file_location("yuntu_top_materials", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def record(material_id, show_cnt, rank, title=""):
    return {
        "material_id": material_id,
        "rank": rank,
        "title": title,
        "metrics": {"show_cnt": show_cnt},
    }


class YuntuTopMaterialsTests(unittest.TestCase):
    def test_classify_brand_uses_confirmed_title_rules(self):
        subject = load_module()

        self.assertEqual(
            subject.classify_brand("#万益蓝 WONDERLAB"),
            {"value": "万益蓝/WONDERLAB", "source": "title_rule"},
        )
        self.assertEqual(
            subject.classify_brand("五个女博士富铁软糖"),
            {"value": "五个女博士", "source": "title_rule"},
        )
        self.assertEqual(
            subject.classify_brand("燕之屋精炖燕窝"),
            {"value": "燕之屋", "source": "title_rule"},
        )
        self.assertEqual(
            subject.classify_brand("未标注素材"),
            {"value": "未知品牌", "source": "unclassified"},
        )

    def test_select_top_materials_uses_exposure_rank_and_material_id(self):
        subject = load_module()
        records = [
            record("101", 100, 3),
            record("102", 100, 1),
            record("103", 100, 1),
            record("104", 99, 1),
            record("105", 0, 1),
        ]

        self.assertEqual(
            [
                item["material_id"]
                for item in subject.select_top_materials(records, limit=3)
            ],
            ["102", "103", "101"],
        )


if __name__ == "__main__":
    unittest.main()
