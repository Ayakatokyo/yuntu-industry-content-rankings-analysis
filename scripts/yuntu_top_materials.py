"""Build post-RPA facts for the TOP material combination report block."""

from statistics import median


BRAND_RULES = (
    ("万益蓝/WONDERLAB", ("万益蓝", "wonderlab")),
    ("五个女博士", ("五个女博士",)),
    ("燕之屋", ("燕之屋",)),
)
CORE_METRICS = (
    "ctr",
    "cvr",
    "pvr",
    "play_3s_rate",
    "play_5s_rate",
    "play_over_rate",
    "interact_rate",
    "component_click_rate",
    "play_duration_avg",
)
AGE_TAGS = (
    "18-19", "20-23", "24-30", "31-35", "36-40", "41-45",
    "46-50", "51-55", "56-59", "60+",
)
GENDER_TAGS = ("女", "男")
CROWD_TAGS = (
    "小镇青年", "精致妈妈", "新锐白领", "资深中产", "小镇中老年",
    "都市银发", "genz", "都市蓝领",
)


def _positive_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def _number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def classify_brand(title):
    """Classify a title with an auditable business rule, never an RPA field."""
    text = str(title or "").casefold()
    matches = [
        brand
        for brand, keywords in BRAND_RULES
        if any(keyword.casefold() in text for keyword in keywords)
    ]
    if len(matches) == 1:
        return {"value": matches[0], "source": "title_rule"}
    if len(matches) > 1:
        return {"value": "歧义品牌", "source": "ambiguous"}
    return {"value": "未知品牌", "source": "unclassified"}


def select_top_materials(records, *, limit=30):
    """Return eligible material records in the documented exposure order."""
    eligible = [
        record
        for record in records
        if _positive_number(record.get("metrics", {}).get("show_cnt"))
    ]
    return sorted(
        eligible,
        key=lambda record: (
            -record["metrics"]["show_cnt"],
            record.get("rank", float("inf")),
            str(record.get("material_id", "")),
        ),
    )[:limit]


def _metric_summary(records, metric):
    values = [
        record["metrics"][metric]
        for record in records
        if _number(record.get("metrics", {}).get(metric)) is not None
    ]
    return {
        "count": len(values),
        "mean": sum(values) / len(values) if values else None,
        "median": median(values) if values else None,
    }


def _exposure_summary(records, pool_records):
    values = [record["metrics"]["show_cnt"] for record in records]
    total = sum(values)
    pool_total = sum(record["metrics"]["show_cnt"] for record in pool_records)
    return {
        "total": total,
        "mean": total / len(values) if values else None,
        "median": median(values) if values else None,
        "max": max(values) if values else None,
        "poolShare": total / pool_total if pool_total else None,
        "topThreeShare": sum(sorted(values, reverse=True)[:3]) / total if total else None,
    }


def _classified_record(record):
    result = dict(record)
    result["brandClassification"] = classify_brand(record.get("title"))
    return result


def _fact_material(record):
    return {
        "material_id": record.get("material_id"),
        "rank": record.get("rank"),
        "title": record.get("title", ""),
        "metrics": record.get("metrics", {}),
        "people_tags": record.get("people_tags", []),
        "material_tags": record.get("material_tags", []),
        "brandClassification": record["brandClassification"],
        "sourcePaths": record.get("source_paths", {}),
    }


def _people_coverage(records, labels):
    total_exposure = sum(record["metrics"]["show_cnt"] for record in records)
    values = []
    for label in labels:
        matched = [record for record in records if label in record.get("people_tags", [])]
        if not matched:
            continue
        exposure = sum(record["metrics"]["show_cnt"] for record in matched)
        values.append({
            "label": label,
            "materialCount": len(matched),
            "materialShare": len(matched) / len(records) if records else None,
            "exposure": exposure,
            "exposureCoverage": exposure / total_exposure if total_exposure else None,
        })
    return sorted(values, key=lambda item: (-item["exposure"], item["label"]))


def _marketing_category(tag):
    if tag.startswith("成分配方原料_"):
        return "成分/原料"
    if tag.startswith("功效功能_"):
        return "功效"
    if tag.startswith("痛点_"):
        return "痛点"
    if tag.startswith("使用场景_"):
        return "使用场景"
    if any(token in tag for token in ("口播", "商品展示", "图文", "情景", "动画", "无语音")):
        return "内容形式"
    if any(token in tag for token in ("优惠", "价格", "赠送", "限时", "抢购", "折", "划算", "促销")):
        return "促销利益"
    return "其他"


def _marketing_summary(records):
    categories = {name: {} for name in ("成分/原料", "功效", "痛点", "使用场景", "内容形式", "促销利益", "其他")}
    total_exposure = sum(record["metrics"]["show_cnt"] for record in records)
    for record in records:
        for tag in record.get("material_tags", []):
            if not isinstance(tag, str) or not tag:
                continue
            item = categories[_marketing_category(tag)].setdefault(tag, {"materialIds": [], "exposure": 0})
            if record["material_id"] not in item["materialIds"]:
                item["materialIds"].append(record["material_id"])
                item["exposure"] += record["metrics"]["show_cnt"]
    return {
        category: [
            {
                "rawTag": tag,
                "materialCount": len(item["materialIds"]),
                "materialIds": item["materialIds"],
                "exposure": item["exposure"],
                "exposureCoverage": item["exposure"] / total_exposure if total_exposure else None,
            }
            for tag, item in sorted(entries.items(), key=lambda pair: (-pair[1]["exposure"], pair[0]))
        ]
        for category, entries in categories.items()
    }


def _tag_metric_comparisons(records):
    tags = sorted({tag for record in records for tag in record.get("material_tags", []) if isinstance(tag, str) and tag})
    comparisons = []
    for tag in tags:
        tagged = [record for record in records if tag in record.get("material_tags", [])]
        other = [record for record in records if tag not in record.get("material_tags", [])]
        if len(tagged) < 3 or len(other) < 3:
            continue
        comparisons.append({
            "rawTag": tag,
            "taggedCount": len(tagged),
            "untaggedCount": len(other),
            "metrics": {
                metric: {"taggedMedian": _metric_summary(tagged, metric)["median"], "untaggedMedian": _metric_summary(other, metric)["median"]}
                for metric in ("ctr", "cvr", "play_3s_rate")
            },
        })
    return comparisons


def _group_summary(records, pool_records, top_n):
    top_records = select_top_materials(records, limit=top_n)
    metrics = {metric: _metric_summary(top_records, metric) for metric in CORE_METRICS}
    cpm = _metric_summary(top_records, "cpm")
    metrics["cpm"] = cpm if cpm["count"] else {"available": False, "missingReason": "rpa_not_provided"}
    return {
        "candidateCount": len(records),
        "topMaterialCount": len(top_records),
        "topMaterials": [_fact_material(record) for record in top_records],
        "exposure": _exposure_summary(top_records, pool_records),
        "metrics": metrics,
        "people": {
            "coverageIsOverlapping": True,
            "age": _people_coverage(top_records, AGE_TAGS),
            "gender": _people_coverage(top_records, GENDER_TAGS),
            "crowd": _people_coverage(top_records, CROWD_TAGS),
        },
        "marketing": _marketing_summary(top_records),
        "tagMetricComparisons": _tag_metric_comparisons(top_records),
    }


def build_top_material_combination(records, *, top_n=30):
    """Build auditable overall and title-classified brand TOP30 facts."""
    classified = [_classified_record(record) for record in records if isinstance(record, dict)]
    pool_records = select_top_materials(classified, limit=len(classified))
    warnings = []
    if any(record["brandClassification"]["source"] == "ambiguous" for record in classified):
        warnings.append("ambiguous_brand_title")
    brands = {}
    for brand, _keywords in BRAND_RULES:
        brand_records = [
            record for record in classified
            if record["brandClassification"] == {"value": brand, "source": "title_rule"}
        ]
        if not brand_records:
            continue
        summary = _group_summary(brand_records, brand_records, top_n)
        summary.update({"brand": brand, "classificationSource": "title_rule", "identifiedMaterialCount": len(brand_records)})
        brands[brand] = summary
    return {
        "schemaVersion": 1,
        "classificationRules": [
            {"brand": brand, "keywords": list(keywords), "source": "title_rule"}
            for brand, keywords in BRAND_RULES
        ],
        "overall": _group_summary(pool_records, pool_records, top_n),
        "brands": brands,
        "warnings": warnings,
        "dataAvailability": {"cpm": {"available": False, "missingReason": "rpa_not_provided"}},
    }
