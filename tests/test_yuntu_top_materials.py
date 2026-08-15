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
    def test_classify_brand_uses_runtime_brand_inputs_without_persisting_aliases(self):
        subject = load_module()
        brands = ["WONDERLAB/万益蓝", "五个女博士", "燕之屋"]

        self.assertEqual(
            subject.classify_brand("晚饭后吃万益蓝益生菌", brands=brands),
            {"value": "WONDERLAB/万益蓝", "source": "runtime_title_rule"},
        )
        self.assertEqual(
            subject.classify_brand("WONDERLAB 蓝绿组合", brands=brands),
            {"value": "WONDERLAB/万益蓝", "source": "runtime_title_rule"},
        )
        self.assertEqual(
            subject.classify_brand("未命中", brands=brands),
            {"value": "未知品牌", "source": "unclassified"},
        )

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

    def test_build_combination_uses_runtime_brands_and_full_pool(self):
        subject = load_module()
        records = [
            record("1", 1000, 1, "万益蓝蓝绿组合"),
            record("2", 900, 2, "五个女博士胶原蛋白"),
            record("3", 800, 3, "燕之屋燕窝"),
            record("4", 700, 4, "万益蓝工厂"),
        ]

        result = subject.build_top_material_combination(
            records,
            top_n=1,
            brands=["WONDERLAB/万益蓝", "五个女博士", "燕之屋"],
        )

        self.assertEqual(result["overall"]["candidateCount"], 4)
        self.assertEqual(result["brands"]["WONDERLAB/万益蓝"]["identifiedMaterialCount"], 2)
        self.assertEqual(
            result["brands"]["WONDERLAB/万益蓝"]["topMaterials"][0]["material_id"],
            "1",
        )
        self.assertEqual(result["brands"]["WONDERLAB/万益蓝"]["classificationSource"], "runtime_title_rule")

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

    def test_audience_dashboard_uses_top_1000_and_normalized_tag_shares(self):
        subject = load_module()
        records = [
            record(str(index), 2000 - index, index, people=["24-30", "女", "新锐白领"])
            for index in range(1, 1002)
        ]
        records[1]["people_tags"] = ["31-35", "男", "精致妈妈"]

        result = subject.build_audience_dashboard(records)

        self.assertEqual(result["sample"], {
            "scope": "candidate_pool_top_1000",
            "requestedLimit": 1000,
            "recordCount": 1000,
        })
        self.assertEqual(result["dimensions"]["age"]["labelMode"], "normalized_tag_share")
        self.assertEqual(result["dimensions"]["age"]["labeledRecordCount"], 1000)
        self.assertEqual(result["dimensions"]["age"]["unlabeledRecordCount"], 0)
        self.assertEqual(result["dimensions"]["age"]["tagOccurrenceCount"], 1000)
        self.assertEqual(result["dimensions"]["age"]["buckets"][0], {
            "label": "24-30", "materialCount": 999, "materialShare": 0.999, "chartShare": 0.999,
        })
        self.assertEqual(result["dimensions"]["gender"]["buckets"][1], {
            "label": "男", "materialCount": 1, "materialShare": 0.001, "chartShare": 0.001,
        })

    def test_audience_dashboard_normalizes_multi_label_dimension_for_pie_chart(self):
        subject = load_module()
        result = subject.build_audience_dashboard([
            record("1", 300, 1, people=["24-30", "女", "新锐白领", "精致妈妈"]),
            record("2", 200, 2, people=["24-30", "女", "新锐白领"]),
            record("3", 100, 3, people=[]),
        ])

        crowd = result["dimensions"]["crowd"]
        self.assertEqual(crowd["labelMode"], "normalized_tag_share")
        self.assertEqual(crowd["recordCount"], 3)
        self.assertEqual(crowd["labeledRecordCount"], 2)
        self.assertEqual(crowd["unlabeledRecordCount"], 1)
        self.assertEqual(crowd["tagOccurrenceCount"], 3)
        self.assertEqual(crowd["buckets"], [
            {"label": "新锐白领", "materialCount": 2, "materialShare": 2 / 3, "chartShare": 2 / 3},
            {"label": "精致妈妈", "materialCount": 1, "materialShare": 1 / 3, "chartShare": 1 / 3},
        ])


if __name__ == "__main__":
    unittest.main()
