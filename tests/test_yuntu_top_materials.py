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


def record(material_id, show_cnt, rank, title="", *, people=None, tags=None, metrics=None):
    return {
        "material_id": material_id,
        "rank": rank,
        "title": title,
        "metrics": {"show_cnt": show_cnt, "ctr": 0.1, **(metrics or {})},
        "people_tags": people or [],
        "material_tags": tags or [],
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

    def test_build_combination_calculates_metrics_people_and_brand_isolation(self):
        subject = load_module()
        result = subject.build_top_material_combination(
            [
                record(
                    "1", 600, 2, "五个女博士", people=["24-30", "女", "新锐白领"],
                    tags=["成分配方原料_铁元素", "单人口播"], metrics={"cvr": 0.2},
                ),
                record(
                    "2", 400, 1, "万益蓝", people=["24-30", "女", "精致妈妈"],
                    tags=["痛点_低精力", "限时抢购"], metrics={"cvr": 0.1},
                ),
                record("3", 500, 3, "未标注", people=["36-40", "男", "小镇青年"]),
                record("4", 300, 4, "万益蓝和五个女博士"),
            ],
            top_n=2,
        )

        overall = result["overall"]
        self.assertEqual([item["material_id"] for item in overall["topMaterials"]], ["1", "3"])
        self.assertEqual(overall["exposure"]["total"], 1100)
        self.assertEqual(overall["exposure"]["poolShare"], 1100 / 1800)
        self.assertEqual(overall["metrics"]["ctr"]["count"], 2)
        self.assertEqual(overall["metrics"]["cpm"], {"available": False, "missingReason": "rpa_not_provided"})
        self.assertTrue(overall["people"]["coverageIsOverlapping"])
        self.assertEqual(overall["people"]["age"][0]["label"], "24-30")
        self.assertEqual(overall["people"]["age"][0]["exposureCoverage"], 600 / 1100)
        self.assertEqual(overall["marketing"]["成分/原料"][0]["rawTag"], "成分配方原料_铁元素")
        self.assertEqual(overall["marketing"]["内容形式"][0]["rawTag"], "单人口播")
        self.assertEqual(result["brands"]["五个女博士"]["identifiedMaterialCount"], 1)
        self.assertEqual(
            [item["material_id"] for item in result["brands"]["五个女博士"]["topMaterials"]],
            ["1"],
        )
        self.assertIn("ambiguous_brand_title", result["warnings"])

    def test_tag_comparison_requires_three_materials_on_each_side(self):
        subject = load_module()
        result = subject.build_top_material_combination(
            [
                record(str(index), 100 + index, index, "五个女博士", tags=["痛点_低精力"])
                for index in range(1, 4)
            ]
            + [
                record(str(index), 100 + index, index, "五个女博士")
                for index in range(4, 7)
            ]
        )

        self.assertEqual(len(result["overall"]["tagMetricComparisons"]), 1)
        self.assertEqual(result["overall"]["tagMetricComparisons"][0]["rawTag"], "痛点_低精力")


if __name__ == "__main__":
    unittest.main()
