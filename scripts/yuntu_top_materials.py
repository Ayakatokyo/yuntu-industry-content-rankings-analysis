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


def _runtime_brand_rules(brands):
    rules = []
    for brand in brands or ():
        canonical = str(brand or "").strip()
        if not canonical:
            continue
        tokens = tuple(
            token.strip()
            for token in canonical.split("/")
            if token.strip()
        )
        if tokens:
            rules.append((canonical, tokens))
    return tuple(rules)


def classify_brand(title, *, brands=None):
    """Classify a title using only the current run's user-provided brands."""
    if brands is None:
        rules = BRAND_RULES
        source = "title_rule"
    else:
        rules = _runtime_brand_rules(brands)
        source = "runtime_title_rule"
    text = str(title or "").casefold()
    matches = [
        brand
        for brand, keywords in rules
        if any(keyword.casefold() in text for keyword in keywords)
    ]
    if len(matches) == 1:
        return {"value": matches[0], "source": source}
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


def _classified_record(record, *, brands=None):
    result = dict(record)
    result["brandClassification"] = classify_brand(record.get("title"), brands=brands)
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


def _audience_dimension(records, labels):
    counts = {label: 0 for label in labels}
    labeled_record_count = 0
    for record in records:
        people_tags = record.get("people_tags", [])
        matched = [label for label in labels if label in people_tags]
        if matched:
            labeled_record_count += 1
        for label in matched:
            counts[label] += 1
    record_count = len(records)
    tag_occurrence_count = sum(counts.values())
    return {
        "labelMode": "normalized_tag_share",
        "recordCount": record_count,
        "labeledRecordCount": labeled_record_count,
        "unlabeledRecordCount": record_count - labeled_record_count,
        "tagOccurrenceCount": tag_occurrence_count,
        "buckets": [
            {
                "label": label,
                "materialCount": count,
                "materialShare": count / record_count if record_count else None,
                "chartShare": count / tag_occurrence_count if tag_occurrence_count else None,
            }
            for label, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
            if count
        ],
    }


def build_audience_dashboard(records, *, limit=1000):
    """Build TOP candidate-pool material-tag shares for the audience report block."""
    selected = select_top_materials(records, limit=limit)
    return {
        "schemaVersion": 1,
        "sample": {
            "scope": "candidate_pool_top_1000",
            "requestedLimit": limit,
            "recordCount": len(selected),
        },
        "dimensions": {
            "age": _audience_dimension(selected, AGE_TAGS),
            "gender": _audience_dimension(selected, GENDER_TAGS),
            "crowd": _audience_dimension(selected, CROWD_TAGS),
        },
    }


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


def build_marketing_dashboard(records, *, limit=1000):
    """Build TOP material marketing-tag facts for the chapter 02 dashboard."""
    selected = select_top_materials(records, limit=limit)
    tag_counts = {}
    tag_material_ids = {}
    category_counts = {}
    category_material_ids = {}
    labeled_record_ids = set()
    for record in selected:
        material_id = record.get("material_id")
        has_marketing_tag = False
        for tag in record.get("material_tags", []):
            if not isinstance(tag, str) or not tag.strip():
                continue
            has_marketing_tag = True
            tag = tag.strip()
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
            tag_material_ids.setdefault(tag, set()).add(material_id)
            category = _marketing_category(tag)
            category_counts[category] = category_counts.get(category, 0) + 1
            category_material_ids.setdefault(category, set()).add(material_id)
        if has_marketing_tag and material_id is not None:
            labeled_record_ids.add(material_id)
    sorted_tags = sorted(tag_counts.items(), key=lambda item: (-item[1], item[0]))
    total_occurrence_count = sum(tag_counts.values())
    dashboard_categories = []
    for category, occurrence_count in sorted(
        category_counts.items(),
        key=lambda item: (-item[1], item[0]),
    ):
        category_tags = [
            {
                "tag": tag,
                "count": count,
                "materialCount": len(tag_material_ids.get(tag, set())),
            }
            for tag, count in sorted(
                ((tag, count) for tag, count in tag_counts.items() if _marketing_category(tag) == category),
                key=lambda item: (-item[1], item[0]),
            )
        ]
        dashboard_categories.append(
            {
                "category": category,
                "tagCount": len(category_tags),
                "occurrenceCount": occurrence_count,
                "materialCount": len(category_material_ids.get(category, set())),
                "share": occurrence_count / total_occurrence_count if total_occurrence_count else None,
                "tags": category_tags,
                "topTags": category_tags[:8],
            }
        )
    return {
        "labelMode": "marketing_tag_category_share",
        "recordCount": len(selected),
        "labeledRecordCount": len(labeled_record_ids),
        "unlabeledRecordCount": len(selected) - len(labeled_record_ids),
        "tagCount": len(tag_counts),
        "occurrenceCount": total_occurrence_count,
        "topTags": [
            {
                "tag": tag,
                "count": count,
                "materialCount": len(tag_material_ids.get(tag, set())),
                "category": _marketing_category(tag),
            }
            for tag, count in sorted_tags[:20]
        ],
        "categories": dashboard_categories,
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


def build_top_material_combination(records, *, top_n=30, brands=None):
    """Build auditable overall and run-scoped brand TOPN facts."""
    runtime_brands = [str(brand).strip() for brand in (brands or ()) if str(brand).strip()]
    classification_brands = runtime_brands or [brand for brand, _keywords in BRAND_RULES]
    classified = [
        _classified_record(record, brands=runtime_brands or None)
        for record in records
        if isinstance(record, dict)
    ]
    pool_records = select_top_materials(classified, limit=len(classified))
    warnings = []
    if any(record["brandClassification"]["source"] == "ambiguous" for record in classified):
        warnings.append("ambiguous_brand_title")
    brands = {}
    for brand in classification_brands:
        brand_records = [
            record for record in classified
            if record["brandClassification"] == {"value": brand, "source": "title_rule"}
            or record["brandClassification"] == {"value": brand, "source": "runtime_title_rule"}
        ]
        if not brand_records:
            continue
        summary = _group_summary(brand_records, brand_records, top_n)
        summary.update({
            "brand": brand,
            "classificationSource": "runtime_title_rule" if runtime_brands else "title_rule",
            "identifiedMaterialCount": len(brand_records),
        })
        brands[brand] = summary
    return {
        "schemaVersion": 1,
        "classificationRules": [
            {
                "brand": brand,
                "keywords": list(keywords),
                "source": "runtime_title_rule" if runtime_brands else "title_rule",
            }
            for brand, keywords in (
                _runtime_brand_rules(runtime_brands)
                if runtime_brands
                else BRAND_RULES
            )
        ],
        "overall": _group_summary(pool_records, pool_records, top_n),
        "brands": brands,
        "warnings": warnings,
        "dataAvailability": {"cpm": {"available": False, "missingReason": "rpa_not_provided"}},
    }
