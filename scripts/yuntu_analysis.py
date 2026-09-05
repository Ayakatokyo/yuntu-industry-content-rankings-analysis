"""Build auditable industry content analysis fact packs from normalized records."""

import json
from pathlib import Path
import re
from statistics import median

try:
    import jieba.posseg as pseg
except ImportError:  # pragma: no cover - the production environment provides jieba
    pseg = None

from rpa_io import file_sha256, write_json_atomically
from yuntu_highlights import (
    ALLOWED_HIGHLIGHT_TRENDS,
    details_missing_standard_highlights,
    generate_standard_highlights_for_detail,
    load_highlights_manifest,
    write_highlights_manifest,
)
from yuntu_highlight_export import match_brands_from_title
from yuntu_top_materials import (
    build_audience_dashboard,
    build_marketing_dashboard,
    build_top_material_combination,
    select_top_materials,
)
from yuntu_hot_material_config import (
    HotMaterialConfigError,
    load_hot_material_rule,
)


class YuntuAnalysisError(RuntimeError):
    """Raised when analysis facts cannot be prepared."""


SECOND_LEVEL_TRENDS = ALLOWED_HIGHLIGHT_TRENDS
RANKING_FACT_METRICS = ("show_cnt", "ctr", "cvr", "play_3s_rate")
RANKING_MATERIAL_METRICS = ("ctr", "cvr", "play_3s_rate")
SCRIPT_FORMULA_PRIMARY_LABELS = {
    "9": "商品卖点",
    "10": "品牌印象",
    "13": "人群",
    "15": "使用场景",
}
SCRIPT_FORMULA_SECONDARY_LABELS = {
    "34": "功效功能",
    "39": "使用感受和服务体验",
    "40": "产品代名词",
    "42": "成分配方原料",
    "44": "工艺科技",
    "52": "人群",
    "55": "身份认同",
    "56": "市场地位和权威背书",
    "57": "品牌调性和故事",
    "87": "使用场景",
}
REPORT_DATA_FIELDS = (
    "schemaVersion",
    "filters",
    "selectedMaterials",
    "rejectedMaterials",
    "summaryMetrics",
    "candidatePool",
    "reportScopes",
    "audienceDashboard",
    "tagInsights",
    "trendSummary",
    "dataAvailabilitySummary",
    "materialFacts",
    "chapter02Facts",
    "chapter02AiFacts",
    "industryTop1000Facts",
    "brandRankingFacts",
    "current",
    "previousPeriod",
    "industryBenchmark",
    "comparisonFacts",
    "hotMaterialRule",
    "hotMaterialFacts",
    "scriptFacts",
)


def _load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        raise YuntuAnalysisError(f"unable to read JSON {path}: {exc}") from exc


def _numeric_metric_values(records, metric_name):
    return [
        record["metrics"][metric_name]
        for record in records
        if isinstance(record.get("metrics", {}).get(metric_name), (int, float))
        and not isinstance(record["metrics"][metric_name], bool)
    ]


def _percentile_rank(values, value):
    return sum(candidate <= value for candidate in values) / len(values)


def _metric_summary(records, metric_name):
    values = _numeric_metric_values(records, metric_name)
    if not values:
        return None
    return {
        "count": len(values),
        "mean": sum(values) / len(values),
        "median": median(values),
    }


def _candidate_pool(records):
    metric_names = sorted(
        {name for record in records for name in record.get("metrics", {})}
    )
    metrics = {
        name: summary
        for name in metric_names
        if (summary := _metric_summary(records, name)) is not None
    }
    return {"count": len(records), "metrics": metrics}


def _report_scopes(pool_records, selected, rejected):
    """Describe the distinct populations used by the generated report."""
    ranking_count = len(pool_records)
    return {
        "ranking": {
            "source_name": "TOP1000 榜单素材",
            "sample_count": ranking_count,
            "selection_rule": "按请求筛选条件取得的榜单候选池",
            "limitations": [],
        },
        "detail": {
            "source_name": "成功秒级拆解素材",
            "sample_count": len(selected),
            "success_count": len(selected),
            "failed_count": len(rejected),
            "selection_rule": "实际成功取得秒级详情的素材，仅供秒级与高光章节",
            "limitations": ["执行失败素材不纳入秒级分析"],
        },
    }


def _ranking_material_fact(record):
    exposure = record.get("exposure") if isinstance(record.get("exposure"), dict) else {}
    interval = exposure.get("raw")
    interval_available = isinstance(interval, str) and bool(interval.strip())
    return {
        "material_id": str(record.get("material_id", "")),
        "rank": record.get("rank"),
        "title": record.get("title", ""),
        "metrics": {
            name: record.get("metrics", {}).get(name)
            for name in RANKING_MATERIAL_METRICS
        },
        "exposure": {
            "raw": interval.strip() if interval_available else "",
            "available": interval_available,
            **({} if interval_available else {"missingReason": "exposure_interval_unavailable"}),
        },
        "people_tags": list(record.get("people_tags", [])),
        "material_tags": list(record.get("material_tags", [])),
    }


def _ranking_aggregate(records, *, source_scope, actual_date_range=None, available=True, missing_reason=""):
    metrics = {}
    for name in RANKING_FACT_METRICS:
        summary = _metric_summary(records, name)
        if name == "show_cnt":
            metrics[name] = {
                "count": summary["count"] if summary else 0,
                "total": sum(_numeric_metric_values(records, name)),
                "mean": summary["mean"] if summary else None,
                "median": summary["median"] if summary else None,
            }
        else:
            metrics[name] = summary or {
                "count": 0,
                "mean": None,
                "median": None,
            }
    return {
        "source_scope": source_scope,
        "actualDateRange": actual_date_range,
        "sampleCount": len(records),
        "metrics": metrics,
        "materials": [_ranking_material_fact(record) for record in records],
        "available": bool(available),
        "missingReason": missing_reason,
    }


def _comparison_fact(current, baseline, *, baseline_name):
    current_sample = current.get("sampleCount", 0)
    baseline_sample = baseline.get("sampleCount", 0)
    sample_delta = current_sample - baseline_sample
    sample_rate = sample_delta / baseline_sample if baseline_sample else None
    metric_changes = {}
    for name in RANKING_FACT_METRICS:
        summary_key = "total" if name == "show_cnt" else "median"
        current_value = (current.get("metrics", {}).get(name) or {}).get(summary_key)
        baseline_value = (baseline.get("metrics", {}).get(name) or {}).get(summary_key)
        if isinstance(current_value, (int, float)) and isinstance(baseline_value, (int, float)):
            delta = current_value - baseline_value
            rate = delta / baseline_value if baseline_value else None
            metric_changes[name] = {
                "current": current_value,
                "baseline": baseline_value,
                "delta": delta,
                "rate": rate,
                "available": True,
                "missingReason": "",
            }
        else:
            metric_changes[name] = {
                "current": current_value,
                "baseline": baseline_value,
                "delta": None,
                "rate": None,
                "available": False,
                "missingReason": "current_or_baseline_metric_unavailable",
            }
    return {
        "baseline": baseline_name,
        "currentDateRange": current.get("actualDateRange"),
        "baselineDateRange": baseline.get("actualDateRange"),
        "currentSampleCount": current_sample,
        "baselineSampleCount": baseline_sample,
        "sampleCountDelta": sample_delta,
        "sampleCountRate": sample_rate,
        "metrics": metric_changes,
        "available": bool(current.get("available") and baseline.get("available")),
        "missingReason": (
            ""
            if current.get("available") and baseline.get("available")
            else baseline.get("missingReason") or "comparison_data_unavailable"
        ),
    }


def _hot_material_scope_facts(records, *, scope, hot_material_rule):
    threshold = hot_material_rule["threshold"]
    qualifying = [
        record
        for record in records
        if isinstance(record.get("exposure"), dict)
        and isinstance(record["exposure"].get("min"), (int, float))
        and not isinstance(record["exposure"].get("min"), bool)
        and record["exposure"]["min"] >= threshold
    ]
    qualifying.sort(
        key=lambda record: (
            -record["exposure"]["min"],
            record.get("rank", 0),
            str(record.get("material_id", "")),
        )
    )
    usable_count = sum(
        isinstance(record.get("exposure"), dict)
        and isinstance(record["exposure"].get("min"), (int, float))
        and not isinstance(record["exposure"].get("min"), bool)
        for record in records
    )
    return {
        "scope": scope,
        "thresholdExposureMin": threshold,
        "rule": dict(hot_material_rule),
        "qualifyingCount": len(qualifying),
        "materials": [
            {
                "material_id": str(record.get("material_id", "")),
                "rank": record.get("rank"),
                "title": record.get("title", ""),
                "exposure": dict(record["exposure"]),
                "metrics": {
                    name: record.get("metrics", {}).get(name)
                    for name in RANKING_FACT_METRICS
                    if name in record.get("metrics", {})
                },
            }
            for record in qualifying
        ],
        "sortRule": "exposure.min descending, rank ascending, material_id ascending",
        "available": bool(usable_count),
        "missing_reason": "" if usable_count else "exposure_interval_unavailable",
        "sampleCount": len(records),
    }


def _ranking_scope_facts(records, *, source_scope):
    selected = select_top_materials(records, limit=len(records))
    metrics = {
        name: _metric_summary(selected, name)
        for name in RANKING_FACT_METRICS
        if name != "show_cnt"
    }
    show_summary = _metric_summary(selected, "show_cnt")
    metrics["show_cnt"] = {
        "count": show_summary["count"] if show_summary else 0,
        "total": sum(_numeric_metric_values(selected, "show_cnt")),
        "mean": show_summary["mean"] if show_summary else None,
        "median": show_summary["median"] if show_summary else None,
    }
    return {
        "source_scope": source_scope,
        "sample_count": len(selected),
        "metrics": metrics,
        "materials": [_ranking_material_fact(record) for record in selected],
    }


def _metric_comparison(record, pool_records):
    comparison = {}
    pool_size = len(pool_records)
    for name, value in sorted(record.get("metrics", {}).items()):
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        values = _numeric_metric_values(pool_records, name)
        if not values:
            continue
        percentile = _percentile_rank(values, value)
        comparison[name] = {
            "value": value,
            "percentile": percentile,
            "tier": "high" if pool_size >= 4 and percentile >= 0.75 else "observed",
        }
    return comparison


def _tag_stats(records, key, selected_ids):
    stats = {}
    for record in records:
        material_id = record.get("material_id")
        for tag in record.get(key, []):
            if not isinstance(tag, str) or not tag:
                continue
            entry = stats.setdefault(tag, {"count": 0, "materialCount": 0, "selectedMaterialCount": 0})
            entry["count"] += 1
            entry["materialCount"] += 1
            if material_id in selected_ids:
                entry["selectedMaterialCount"] += 1
    return dict(sorted(stats.items(), key=lambda item: (-item[1]["count"], item[0])))


def _tag_insights(records, selected_ids):
    material_tags = _tag_stats(records, "material_tags", selected_ids)
    people_tags = _tag_stats(records, "people_tags", selected_ids)
    eligible = len(records) >= 4 and any(
        item["materialCount"] >= 2
        for item in [*material_tags.values(), *people_tags.values()]
    )
    return {
        "eligibleForAssociation": eligible,
        "materialTags": material_tags,
        "peopleTags": people_tags,
    }


def _script_fact_tokens(value):
    values = value if isinstance(value, list) else [value]
    tokens = []
    for item in values:
        if isinstance(item, dict):
            if item.get("level_1_label") not in (None, ""):
                tokens.append(f"level_1_label:{item['level_1_label']}")
            for label in item.get("level_2_labels", []) if isinstance(item.get("level_2_labels"), list) else []:
                if label not in (None, ""):
                    tokens.append(f"level_2_label:{label}")
            continue
        for token in re.split(r"[、，,；;\\n]+", str(item or "")):
            token = token.strip()
            if token and token not in tokens:
                tokens.append(token)
    return tokens


def _script_frequency_add(frequencies, dimension, values, material_id):
    for value in _script_fact_tokens(values):
        entry = frequencies[dimension].setdefault(value, {"count": 0, "material_ids": []})
        if material_id not in entry["material_ids"]:
            entry["material_ids"].append(material_id)
            entry["count"] += 1


_SCRIPT_KEYWORD_MIN_FREQUENCY = 2
_SCRIPT_KEYWORD_POS_PREFIXES = ("n", "v", "a", "eng")


def _script_keyword_tokens(text):
    """Extract content words from script text without using titles or labels."""
    value = str(text or "").strip()
    if not value:
        return []
    if pseg is None:
        return [
            token
            for token in re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z]{2,}", value)
            if not token.isdigit()
        ]

    tokens = []
    previous = None
    for item in pseg.cut(value):
        token = str(item.word or "").strip()
        flag = str(item.flag or "")
        if not token or not flag.startswith(_SCRIPT_KEYWORD_POS_PREFIXES):
            previous = None
            continue
        if token.isascii():
            normalized = token.lower() if len(token) >= 2 and not token.isdigit() else ""
        else:
            normalized = token if re.search(r"[\u4e00-\u9fff]", token) else ""
        if normalized:
            if len(normalized) >= 2:
                tokens.append(normalized)
            if previous and len(previous) == 1 and len(normalized) == 1:
                tokens.append(previous + normalized)
            previous = normalized
    return tokens


def _script_keyword_cloud(materials):
    stats = {}
    for material in materials:
        if not isinstance(material, dict):
            continue
        material_id = str(material.get("material_id") or "").strip()
        for keyword in _script_keyword_tokens(material.get("script_text")):
            entry = stats.setdefault(keyword, {"frequency": 0, "material_ids": set()})
            entry["frequency"] += 1
            if material_id:
                entry["material_ids"].add(material_id)

    keywords = []
    for keyword, item in sorted(stats.items(), key=lambda pair: (-pair[1]["frequency"], pair[0])):
        if item["frequency"] < _SCRIPT_KEYWORD_MIN_FREQUENCY:
            continue
        material_ids = sorted(item["material_ids"])
        keywords.append({
            "keyword": keyword,
            "frequency": item["frequency"],
            "materialIds": material_ids,
            "evidenceRefs": [
                f"script:{material_id}:text:{keyword}" for material_id in material_ids
            ],
        })
    return {
        "source": "facts.scripts.materials[*].script_text",
        "keywords": keywords,
    }


def _script_frequencies_for_detail(detail, material_id, frequencies):
    formula = detail.get("content_formula")
    if isinstance(formula, dict):
        for key, value in formula.items():
            key_text = str(key)
            if key_text == "labels" or key_text.endswith(".labels"):
                _script_frequency_add(frequencies, "formula_labels", value, material_id)
            if any(token in key_text for token in ("卖点", "selling_point", "sellingPoint")):
                _script_frequency_add(frequencies, "selling_points", value, material_id)
            if any(token in key_text for token in ("场景", "scene")):
                _script_frequency_add(frequencies, "scenes", value, material_id)
            if any(token in key_text for token in ("营销", "促销", "活动", "promotion")):
                _script_frequency_add(frequencies, "promotions", value, material_id)
            if any(token in key_text for token in ("形式", "format")):
                _script_frequency_add(frequencies, "marketing_formats", value, material_id)
    creative = detail.get("creative_breakdown")
    if isinstance(creative, dict):
        raw = creative.get("raw", creative)
        if isinstance(raw, dict):
            for key, value in raw.items():
                key_text = str(key)
                if any(token in key_text for token in ("卖点", "selling_point", "sellingPoint")):
                    _script_frequency_add(frequencies, "selling_points", value, material_id)
                if any(token in key_text for token in ("场景", "scene")):
                    _script_frequency_add(frequencies, "scenes", value, material_id)
                if any(token in key_text for token in ("营销", "促销", "活动", "promotion")):
                    _script_frequency_add(frequencies, "promotions", value, material_id)
                if any(token in key_text for token in ("形式", "format")):
                    _script_frequency_add(frequencies, "marketing_formats", value, material_id)


def _script_detail_equivalence(detail):
    return {
        "script_text": detail.get("script_text", ""),
        "script_segments": detail.get("script_segments", []),
        "content_formula": detail.get("content_formula"),
        "creative_breakdown": detail.get("creative_breakdown"),
        "metrics": detail.get("metrics", {}),
    }


def build_script_facts(details, selected_materials):
    """Build a deduplicated, source-only fact pack for chapter 03."""
    if not isinstance(details, list) or not isinstance(selected_materials, list):
        raise YuntuAnalysisError("script facts inputs must be lists")
    detail_by_id = {}
    urls_by_id = {}
    for detail in details:
        if not isinstance(detail, dict):
            continue
        material_id = str(detail.get("material_id") or "").strip()
        if not material_id:
            continue
        if material_id in detail_by_id:
            if _script_detail_equivalence(detail_by_id[material_id]) != _script_detail_equivalence(detail):
                raise YuntuAnalysisError(f"conflicting detail facts for material {material_id}")
        else:
            detail_by_id[material_id] = detail
        url = str(detail.get("video_url") or "").strip()
        if url and url not in urls_by_id.setdefault(material_id, []):
            urls_by_id[material_id].append(url)

    selected = []
    selected_ids = set()
    for item in selected_materials:
        if not isinstance(item, dict):
            continue
        material_id = str(item.get("material_id") or item.get("materialId") or "").strip()
        if not material_id or material_id in selected_ids:
            continue
        selected_ids.add(material_id)
        selected.append((material_id, item))

    frequencies = {
        "formula_labels": {},
        "selling_points": {},
        "scenes": {},
        "promotions": {},
        "marketing_formats": {},
    }
    materials = []
    for material_id, selected_item in selected:
        detail = detail_by_id.get(material_id, {})
        availability = detail.get("data_availability", {})
        material = {
            "material_id": material_id,
            "rank": selected_item.get("rank"),
            "script_text": str(detail.get("script_text") or ""),
            "script_segments": detail.get("script_segments", []) if isinstance(detail.get("script_segments", []), list) else [],
            "content_formula": detail.get("content_formula"),
            "creative_breakdown": detail.get("creative_breakdown"),
            "metrics": dict(detail.get("metrics", {})) if isinstance(detail.get("metrics"), dict) else {},
            "source_paths": dict(detail.get("source_paths", {})) if isinstance(detail.get("source_paths"), dict) else {},
            "source_hashes": dict(detail.get("source_hashes", {})) if isinstance(detail.get("source_hashes"), dict) else {},
            "video_url_variants": urls_by_id.get(material_id, []),
            "data_availability": dict(availability) if isinstance(availability, dict) else {},
        }
        if not material["data_availability"]:
            material["data_availability"] = {
                "script_text": {"available": bool(material["script_text"]), "missing_reason": "" if material["script_text"] else "source_empty"},
                "script_segments": {"available": bool(material["script_segments"]), "missing_reason": "" if material["script_segments"] else "source_empty"},
                "content_formula": {"available": material["content_formula"] is not None, "missing_reason": "" if material["content_formula"] is not None else "source_empty"},
                "creative_breakdown": {"available": material["creative_breakdown"] is not None, "missing_reason": "" if material["creative_breakdown"] is not None else "source_empty"},
            }
        materials.append(material)
        _script_frequencies_for_detail(detail, material_id, frequencies)

    script_count = sum(bool(item["script_text"].strip()) for item in materials)
    total = len(materials)
    for dimension in frequencies:
        frequencies[dimension] = dict(sorted(frequencies[dimension].items()))
    return {
        "schemaVersion": 1,
        "scope": "selected_detail_materials",
        "coverage": {"total": total, "script": script_count, "rate": script_count / total if total else 0},
        "frequencies": frequencies,
        "keywordCloud": _script_keyword_cloud(materials),
        "materials": materials,
        "limitations": [
            "脚本时间戳段落未提供，不能建立秒点或高光帧与话术的对应关系。",
            "该事实包只覆盖已获取详情素材，不代表行业 TOP1000 普遍规律。",
        ],
    }


def _trend_summary(details):
    by_name = {}
    for detail in details:
        for point in detail.get("high_points", []):
            name = point.get("trend_name")
            if name:
                by_name.setdefault(name, {"highPointCount": 0, "lossPointCount": 0})["highPointCount"] += 1
        for point in detail.get("loss_points", []):
            name = point.get("trend_name")
            if name:
                by_name.setdefault(name, {"highPointCount": 0, "lossPointCount": 0})["lossPointCount"] += 1
    return {"byTrendName": dict(sorted(by_name.items()))}


def _second_level_breakdown(detail):
    """Project normalized Yuntu trends into the fixed five-index report contract."""
    series_by_name = {}
    for trend in detail.get("trend_series", []):
        if not isinstance(trend, dict) or trend.get("trend_name") not in SECOND_LEVEL_TRENDS:
            continue
        series_by_name.setdefault(trend["trend_name"], []).extend(
            trend.get("series", []) if isinstance(trend.get("series"), list) else []
        )

    metrics = []
    for trend_name in SECOND_LEVEL_TRENDS:
        by_second = {}
        conflict = False
        for point in series_by_name.get(trend_name, []):
            if not isinstance(point, dict):
                continue
            second = point.get("second")
            value = point.get("value")
            if (
                not isinstance(second, int)
                or isinstance(second, bool)
                or not isinstance(value, (int, float))
                or isinstance(value, bool)
            ):
                continue
            previous = by_second.get(second)
            if previous is not None and previous != value:
                conflict = True
            by_second[second] = value
        if conflict:
            available = False
            missing_reason = "conflicting_seconds"
            points = []
        elif not series_by_name.get(trend_name):
            available = False
            missing_reason = "trend_not_returned"
            points = []
        elif not by_second:
            available = False
            missing_reason = "no_usable_points"
            points = []
        else:
            available = True
            missing_reason = ""
            points = [
                {"second": second, "value": by_second[second]}
                for second in sorted(by_second)
            ]
        metrics.append(
            {
                "trend_name": trend_name,
                "available": available,
                "missing_reason": missing_reason,
                "points": points,
                "high_points": [
                    {"start_sec": item.get("start_sec"), "end_sec": item.get("end_sec")}
                    for item in detail.get("high_points", [])
                    if isinstance(item, dict) and item.get("trend_name") == trend_name
                ],
                "loss_points": [
                    {
                        "start_sec": item.get("start_sec"),
                        "end_sec": item.get("end_sec"),
                        "loss_percent": item.get("loss_percent"),
                    }
                    for item in detail.get("loss_points", [])
                    if isinstance(item, dict) and item.get("trend_name") == trend_name
                ],
            }
        )
    return {"metrics": metrics}


def _availability_summary(material_facts):
    summary = {}
    for fact in material_facts:
        for source in (fact.get("listDataAvailability", {}), fact.get("detailDataAvailability", {})):
            for state in source.values():
                if not isinstance(state, dict) or state.get("available"):
                    continue
                reason = state.get("missing_reason") or "no_usable_values"
                summary[reason] = summary.get(reason, 0) + 1
    return dict(sorted(summary.items()))


def _highlight_frame_availability(frames, *, requested):
    if not requested:
        return {"available": False, "missing_reason": "not_requested"}
    if any(frame.get("available") for frame in frames if isinstance(frame, dict)):
        return {"available": True, "missing_reason": ""}
    reasons = sorted(
        {
            frame.get("failure_reason")
            for frame in frames
            if isinstance(frame, dict) and frame.get("failure_reason")
        }
    )
    return {
        "available": False,
        "missing_reason": reasons[0] if len(reasons) == 1 else "no_available_frames",
    }


def _data_limitations(material_facts):
    limitations = []
    for fact in material_facts:
        material_id = str(fact.get("material_id", ""))
        for source_name, source in (
            ("list", fact.get("listDataAvailability", {})),
            ("detail", fact.get("detailDataAvailability", {})),
        ):
            for field, state in source.items() if isinstance(source, dict) else ():
                if not isinstance(state, dict) or state.get("available"):
                    continue
                limitations.append(
                    {
                        "material_id": material_id,
                        "field": f"{source_name}.{field}",
                        "reason": state.get("missing_reason") or "no_usable_values",
                    }
                )
        for frame in fact.get("highlightFrames", []):
            if not isinstance(frame, dict) or frame.get("available"):
                continue
            limitations.append(
                {
                    "material_id": material_id,
                    "field": f"highlightFrames.{frame.get('frame_ref', frame.get('second', 'unknown'))}",
                    "reason": frame.get("failure_reason") or "no_available_frame",
                }
            )
    return sorted(
        limitations,
        key=lambda item: (item["material_id"], item["field"], item["reason"]),
    )


def _chapter02_scope_fact(records, *, label, limit):
    selected = select_top_materials(records, limit=limit)
    return {
        "label": label,
        "sampleCount": len(selected),
        "topMaterials": [_ranking_material_fact(record) for record in selected],
        "audienceDashboard": build_audience_dashboard(selected, limit=len(selected) or 1),
        "marketingDashboard": build_marketing_dashboard(selected, limit=len(selected) or 1),
    }


def _model_input_sections(
    material_facts,
    pool_records,
    brand_facts,
    chapter02_ai_facts,
    brands,
    ranking_period_facts=None,
    comparison_facts=None,
    hot_material_rule=None,
    hot_material_facts=None,
):
    visual_assets = []
    for fact in material_facts:
        for frame in fact.get("highlightFrames", []):
            if not isinstance(frame, dict):
                continue
            visual_assets.append(
                {
                    "material_id": str(fact["material_id"]),
                    "title": fact["title"],
                    "brand": "、".join(match_brands_from_title(fact["title"], brands)) or "其他品牌",
                    "rank": fact["rank"],
                    "frame_ref": frame.get("frame_ref"),
                    "second": frame.get("second"),
                    "frame_type": frame.get("frame_type"),
                    "peak_rank": frame.get("peak_rank"),
                    "click_value": frame.get("click_value"),
                    "image_path": frame.get("relative_path", ""),
                    "available": bool(frame.get("available")),
                    "failure_reason": frame.get("failure_reason", ""),
                    "frame_source": frame.get(
                        "frame_source", "newly_extracted_frame"
                    ),
                }
            )
    return {
        "industryTop1000Facts": _ranking_scope_facts(
            pool_records,
            source_scope="industry_top1000",
        ),
        "brandRankingFacts": brand_facts,
        **(
            {
                "current": (ranking_period_facts or {}).get("current", {}),
                "previousPeriod": (ranking_period_facts or {}).get("previousPeriod", {}),
                "industryBenchmark": (ranking_period_facts or {}).get("industryBenchmark", {}),
                "comparisonFacts": comparison_facts or {},
                "hotMaterialRule": dict(hot_material_rule or {}),
                "hotMaterialFacts": hot_material_facts or {},
            }
            if hot_material_facts is not None
            else {}
        ),
        "chapter02AiFacts": chapter02_ai_facts,
        "visualAssets": visual_assets,
        "dataLimitations": _data_limitations(material_facts),
    }


def _report_data(fact_pack):
    """Project only facts consumed by report validation and rendering."""
    projected = {key: fact_pack[key] for key in REPORT_DATA_FIELDS if key in fact_pack}
    industry = fact_pack.get("industryTop1000Facts", {})
    projected["industryTop1000Facts"] = {
        key: industry[key]
        for key in ("source_scope", "sample_count")
        if key in industry
    }
    brand_facts = fact_pack.get("brandRankingFacts", {})
    projected["brandRankingFacts"] = {
        "source_scope": brand_facts.get("source_scope"),
        "brands": {
            brand: {
                "source_scope": facts.get("source_scope"),
                "sample_count": facts.get("sample_count"),
                "materials": [
                    {"material_id": str(item["material_id"])}
                    for item in facts.get("materials", [])
                    if isinstance(item, dict) and item.get("material_id")
                ],
            }
            for brand, facts in brand_facts.get("brands", {}).items()
            if isinstance(facts, dict)
        },
    }
    chapter02_ai = fact_pack.get("chapter02AiFacts", {})
    scope_order = chapter02_ai.get("scopeOrder", [])
    projected["chapter02AiFacts"] = {
        "scopeOrder": scope_order,
        **{str(scope): {} for scope in scope_order},
    }
    return projected


def _model_visual_assets(visual_assets):
    projected = []
    for asset in visual_assets:
        copied = dict(asset)
        image_path = str(copied.get("image_path") or "").replace("\\", "/")
        copied["image_path"] = f"../{image_path}" if image_path else ""
        projected.append(copied)
    return projected


def _script_formula_label(level, value):
    labels = (
        SCRIPT_FORMULA_PRIMARY_LABELS
        if level == "primary"
        else SCRIPT_FORMULA_SECONDARY_LABELS
    )
    if isinstance(value, dict):
        explicit = str(value.get("label") or "").strip()
        value = value.get("value") or value.get("id")
    else:
        explicit = ""
    value = str(value or "").strip()
    return labels.get(value) or (explicit if explicit and not explicit.isdigit() else value)


def _script_formula_projection(value):
    """Normalize cloud formula labels without carrying numeric taxonomy IDs."""
    if isinstance(value, dict):
        raw_labels = value.get("labels")
    elif isinstance(value, list):
        raw_labels = value
    else:
        raw_labels = []
    if not isinstance(raw_labels, list):
        raw_labels = [raw_labels] if raw_labels else []

    formula = []
    labels = []
    for item in raw_labels:
        if isinstance(item, dict):
            primary_value = item.get("level1") or item.get("level_1") or item.get("level1_label") or item.get("level_1_label")
            primary = _script_formula_label("primary", primary_value)
            secondary_values = item.get("level2") or item.get("level_2") or item.get("level2_labels") or item.get("level_2_labels") or []
            if not isinstance(secondary_values, list):
                secondary_values = [secondary_values]
        else:
            primary = _script_formula_label("primary", item)
            secondary_values = []
        if not primary:
            continue
        secondary = [_script_formula_label("secondary", raw) for raw in secondary_values]
        secondary = list(dict.fromkeys(item for item in secondary if item))
        if secondary:
            for level2 in secondary:
                formula.append({"level1": primary, "level2": level2})
                labels.append({
                    "level1": primary,
                    "level2": level2,
                    "evidenceRef": "",
                })
        else:
            formula.append({"level1": primary, "level2": ""})
            labels.append({"level1": primary, "level2": "", "evidenceRef": ""})
    return formula, labels


def _script_evidence_projection(material_id, script_text, formula, raw_evidence=None):
    prefix = f"script:{material_id}:"
    evidence = []
    if isinstance(raw_evidence, list):
        for item in raw_evidence:
            if not isinstance(item, dict):
                continue
            sentence = str(item.get("sentence") or item.get("text") or "").strip()
            ref = str(item.get("evidenceRef") or item.get("evidence_ref") or "").strip()
            if not sentence or (ref and not ref.startswith(prefix)):
                continue
            if not ref:
                ref = f"{prefix}text:{sentence}"
            evidence.append({
                "level2": str(item.get("level2") or item.get("level_2") or "").strip(),
                "sentence": sentence,
                "evidenceRef": ref,
            })
    if not evidence and script_text:
        sentences = re.findall(r"[^。！？；\n]+[。！？；]?", script_text)
        default_level2 = formula[0]["level2"] if formula and formula[0].get("level2") else ""
        for sentence in sentences:
            sentence = sentence.strip()
            if sentence:
                evidence.append({
                    "level2": default_level2,
                    "sentence": sentence,
                    "evidenceRef": f"{prefix}text:{sentence}",
                })
    return list({item["evidenceRef"]: item for item in evidence}.values())


def _script_projection(fact):
    material_id = str(fact.get("material_id") or "").strip()
    existing = fact.get("script") if isinstance(fact.get("script"), dict) else {}
    text = str(existing.get("text") or fact.get("script_text") or "").strip()
    formula_source = existing.get("formula") if existing.get("formula") is not None else fact.get("content_formula")
    formula, labels = _script_formula_projection(formula_source)
    existing_labels = existing.get("labels") if isinstance(existing.get("labels"), list) else []
    if existing_labels:
        labels = [dict(item) for item in existing_labels if isinstance(item, dict)]
        formula = [
            {"level1": str(item.get("level1") or "").strip(), "level2": str(item.get("level2") or "").strip()}
            for item in labels
            if str(item.get("level1") or "").strip()
        ]
    raw_evidence = existing.get("evidence") if existing.get("evidence") is not None else fact.get("script_evidence")
    evidence = _script_evidence_projection(material_id, text, formula, raw_evidence)
    evidence_refs = []
    for item in labels:
        level1 = str(item.get("level1") or "").strip()
        level2 = str(item.get("level2") or "").strip()
        if not level1:
            continue
        ref = str(item.get("evidenceRef") or f"{material_id}:{level1}:{level2}").strip()
        ref = ref if ref.startswith("script:") else f"script:{ref}"
        item["level1"], item["level2"], item["evidenceRef"] = level1, level2, ref
        evidence_refs.append(ref)
    evidence_refs.extend(item["evidenceRef"] for item in evidence)
    evidence_refs = list(dict.fromkeys(ref for ref in evidence_refs if ref.startswith(f"script:{material_id}:")))
    availability = fact.get("data_availability", {})
    if not isinstance(availability, dict):
        availability = {}
    def state(name, available, fallback):
        raw = availability.get(name, {})
        return {
            "available": bool(raw.get("available")) if isinstance(raw, dict) and "available" in raw else available,
            "missing_reason": str(raw.get("missing_reason") or "") if isinstance(raw, dict) else ("" if available else fallback),
        }
    return {
        "text": text,
        "labels": labels,
        "formula": formula,
        "evidence": evidence,
        "availability": {
            "text": state("script_text", bool(text), "source_empty"),
            "formula": state("content_formula", bool(formula), "source_empty"),
            "evidence": state("script_evidence", bool(evidence), "source_empty"),
        },
    }, {"script": evidence_refs}


def _model_material_facts(material_facts):
    projected = []
    for fact in material_facts:
        copied = {
            "material_id": str(fact.get("material_id", "")),
            "secondLevelBreakdown": fact.get("secondLevelBreakdown", {"metrics": []}),
            "highlightFrames": [],
        }
        copied["script"], copied["evidenceIndex"] = _script_projection(fact)
        for frame in fact.get("highlightFrames", []):
            frame_copy = {
                key: frame[key]
                for key in ("frame_ref", "second", "frame_type", "available")
                if key in frame
            }
            relative_path = str(
                frame.get("relative_path") or frame.get("image_path") or ""
            ).replace("\\", "/")
            if relative_path:
                frame_copy["image_path"] = (
                    relative_path
                    if relative_path.startswith("../")
                    else f"../{relative_path}"
                )
            elif "image_path" not in frame_copy:
                frame_copy["image_path"] = ""
            if frame.get("failure_reason"):
                frame_copy["failure_reason"] = frame["failure_reason"]
            copied["highlightFrames"].append(frame_copy)
        projected.append(copied)
    return projected


def _ranking_output_schema(*, include_period_contract=False):
    hot_material_insight_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["title", "summary", "evidence"],
        "properties": {
            "title": {"type": "string"},
            "summary": {"type": "string"},
            "evidence": {
                "type": "object",
                "additionalProperties": False,
                "required": ["scope", "material_ids"],
                "properties": {
                    "scope": {"type": "string", "enum": ["all", "brand"]},
                    "material_ids": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    }
    brand_conclusion_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "brand",
            "classificationSource",
            "dataSummary",
            "evidence",
            "material_ids",
        ] + (["hotMaterialInsight"] if include_period_contract else []),
        "properties": {
            "brand": {"type": "string"},
            "classificationSource": {
                "type": "string",
                "enum": ["title_rule", "runtime_title_rule"],
            },
            "dataSummary": {"type": "string"},
            **({"hotMaterialInsight": hot_material_insight_schema} if include_period_contract else {}),
            "evidence": {"type": "array", "items": {"type": "string"}},
            "material_ids": {"type": "array", "items": {"type": "string"}},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["brandConclusions", "allBrandsConclusion"]
        if include_period_contract
        else ["brandConclusions"],
        "properties": {
            "brandConclusions": {
                "type": "array",
                "items": brand_conclusion_schema,
            },
            "allBrandsConclusion": brand_conclusion_schema,
        },
    }


def _analysis_insight_schema():
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["title", "summary", "evidence", "material_ids"],
        "properties": {
            "title": {"type": "string"},
            "summary": {"type": "string"},
            "evidence": {"type": "array", "items": {"type": "string"}},
            "material_ids": {"type": "array", "items": {"type": "string"}},
        },
    }


def _keyword_cloud_review_schema():
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["keyword", "decision", "target"],
        "properties": {
            "keyword": {"type": "string"},
            "decision": {"type": "string", "enum": ["accept", "exclude", "merge"]},
            "target": {"type": "string"},
        },
    }


def _keyword_cloud_insight_schema():
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["oneSentenceConclusion", "summary", "sellingPoints"],
        "properties": {
            "oneSentenceConclusion": {"type": "string"},
            "summary": {"type": "string"},
            "sellingPoints": {
                "type": "array",
                "maxItems": 4,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["title", "description", "keywordRefs", "evidenceRefs"],
                    "properties": {
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "keywordRefs": {"type": "array", "items": {"type": "string"}},
                        "evidenceRefs": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
        },
    }


def _chapter02_output_schema(fact_pack):
    scope_order = [str(scope) for scope in fact_pack["chapter02AiFacts"]["scopeOrder"]]
    scope_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["audienceSummary", "marketingSummary"],
        "properties": {
            "audienceSummary": _analysis_insight_schema(),
            "marketingSummary": _analysis_insight_schema(),
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["scopeOrder", "scopes"],
        "properties": {
            "scopeOrder": {
                "type": "array",
                "minItems": len(scope_order),
                "maxItems": len(scope_order),
                "items": {"type": "string", "enum": scope_order},
            },
            "scopes": {
                "type": "object",
                "additionalProperties": False,
                "required": scope_order,
                "properties": {scope: scope_schema for scope in scope_order},
            },
        },
    }


def _highlight_output_schema():
    understanding_fields = (
        "frame_ref",
        "status",
        "subject",
        "visual_focus",
        "human_product_relation",
        "action",
        "composition",
        "information_expression",
        "failure_reason",
    )
    frame_understanding_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": list(understanding_fields),
        "properties": {
            "frame_ref": {"type": "string"},
            "status": {"type": "string", "enum": ["complete", "unavailable"]},
            **{
                field: {"type": "string"}
                for field in understanding_fields
                if field not in {"frame_ref", "status"}
            },
        },
    }
    direction_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["title", "body", "frame_refs"],
        "properties": {
            "title": {"type": "string"},
            "body": {"type": "string"},
            "frame_refs": {"type": "array", "items": {"type": "string"}},
        },
    }
    group_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["category", "frame_refs", "common_patterns", "derivative_directions"],
        "properties": {
            "category": {"type": "string", "enum": ["portrait", "product", "other"]},
            "frame_refs": {"type": "array", "minItems": 1, "items": {"type": "string"}},
            "common_patterns": {"type": "array", "minItems": 1, "items": direction_schema},
            "derivative_directions": {"type": "array", "items": direction_schema},
        },
    }
    batch_group_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["category", "label", "rule", "frame_refs", "common_patterns", "derivative_directions"],
        "properties": {
            "category": {"type": "string", "minLength": 1},
            "label": {"type": "string", "minLength": 1},
            "rule": {"type": "string", "minLength": 1},
            "frame_refs": {"type": "array", "minItems": 1, "items": {"type": "string"}},
            "common_patterns": {"type": "array", "minItems": 3, "maxItems": 3, "items": direction_schema},
            "derivative_directions": {"type": "array", "minItems": 3, "maxItems": 3, "items": direction_schema},
        },
    }
    classification_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["status", "missing_reason", "groups"],
        "properties": {
            "status": {"type": "string", "enum": ["complete", "unavailable"]},
            "missing_reason": {"type": "string"},
            "rule": {"type": "string"},
            "groups": {"type": "array", "items": group_schema},
        },
    }
    batch_classification_schema = {
        **classification_schema,
        "properties": {
            **classification_schema["properties"],
            "groups": {"type": "array", "minItems": 2, "items": batch_group_schema},
        },
    }
    brand_scope_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["brand", "groups"],
        "properties": {
            "brand": {"type": "string"},
            "groups": {"type": "array", "minItems": 1, "items": group_schema},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["brands"],
        "properties": {
            "brands": {"type": "array", "minItems": 1, "items": brand_scope_schema},
            # Compatibility schema for historical analysis units; new prompts must emit brands.
            "groups": {"type": "array", "minItems": 1, "items": group_schema},
            "frameUnderstanding": {
                "type": "array",
                "items": frame_understanding_schema,
            },
            "standardClassification": classification_schema,
            "batchClassification": batch_classification_schema,
        },
    }


def _material_deep_dive_output_schema(fact_pack):
    material_ids = [
        str(fact["material_id"])
        for fact in fact_pack["materialFacts"]
        if fact.get("material_id")
    ]
    return {
        "type": "array",
        "minItems": len(material_ids),
        "maxItems": len(material_ids),
        "items": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "material_id",
                "frame_observations",
            ],
            "properties": {
                "material_id": {"type": "string", "enum": material_ids},
                "scriptAnalysis": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["conclusion", "evidenceRefs", "availability"],
                    "properties": {
                        "conclusion": {"type": "string"},
                        "evidenceRefs": {"type": "array", "items": {"type": "string"}},
                        "availability": {"type": "string", "enum": ["available", "unavailable"]},
                    },
                },
                "frame_observations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["frame_ref", "observation"],
                        "properties": {
                            "frame_ref": {"type": "string"},
                            "observation": {"type": "string"},
                        },
                    },
                },
            },
        },
    }


def _analysis_output_schema(fact_pack):
    include_period_contract = "hotMaterialFacts" in fact_pack
    properties = {
        "topMaterialCombination": _ranking_output_schema(
            include_period_contract=include_period_contract
        ),
        "chapter02Insights": _chapter02_output_schema(fact_pack),
    }
    required = ["topMaterialCombination", "chapter02Insights"]
    if "scriptFacts" in fact_pack:
        script_schema = {
            "type": "array",
            "items": _analysis_insight_schema(),
        }
        script_facts = fact_pack.get("scriptFacts", {})
        if isinstance(script_facts, dict) and "keywordCloud" in script_facts:
            script_schema.update({"minItems": 2, "maxItems": 2})
            properties["keywordCloudReview"] = {
                "type": "array",
                "items": _keyword_cloud_review_schema(),
            }
            properties["keywordCloudInsight"] = _keyword_cloud_insight_schema()
            required.extend(["keywordCloudReview", "keywordCloudInsight"])
        properties["scriptInsights"] = script_schema
        required.append("scriptInsights")
    if any(asset.get("available") for asset in fact_pack.get("visualAssets", [])):
        properties["highlightDashboard"] = _highlight_output_schema()
        required.append("highlightDashboard")
    if any("secondLevelBreakdown" in fact for fact in fact_pack.get("materialFacts", [])):
        properties["materialDeepDives"] = _material_deep_dive_output_schema(fact_pack)
        required.append("materialDeepDives")
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": required,
        "properties": properties,
    }


def _write_analysis_units(fact_pack, output):
    unit_dir = Path(output) / "analysis-units"
    if "hotMaterialFacts" in fact_pack:
        ranking_evidence = {
            "current": fact_pack["current"],
            "previousPeriod": fact_pack["previousPeriod"],
            "industryBenchmark": fact_pack["industryBenchmark"],
            "comparisonFacts": fact_pack["comparisonFacts"],
            "hotMaterialFacts": fact_pack["hotMaterialFacts"],
        }
    else:
        ranking_evidence = {
            "reportScope": fact_pack["reportScopes"]["ranking"],
            "industryTop1000Facts": fact_pack["industryTop1000Facts"],
            "brandRankingFacts": fact_pack["brandRankingFacts"],
        }
    units = (
        (
            "ranking-brand-input.json",
            "ranking_brand",
            "topMaterialCombination",
            ranking_evidence,
        ),
        (
            "audience-marketing-input.json",
            "audience_marketing",
            "chapter02Insights",
            {"chapter02AiFacts": fact_pack["chapter02AiFacts"]},
        ),
        (
            "script-input.json",
            "script_insights",
            "scriptInsights",
            {"scriptFacts": fact_pack["scriptFacts"]},
        ),
        (
            "highlight-input.json",
            "highlight",
            "highlightDashboard",
            {
                "reportScope": fact_pack["reportScopes"]["detail"],
                "visualAssets": _model_visual_assets(fact_pack["visualAssets"]),
                "frameUnderstandingContract": {
                    "stage": "per_frame_visual_understanding_before_batch_classification",
                    "requiredFields": [
                        "frame_ref",
                        "status",
                        "subject",
                        "visual_focus",
                        "human_product_relation",
                        "action",
                        "composition",
                        "information_expression",
                        "failure_reason",
                    ],
                    "successfulFrameRule": "每张 available=true 的 JPEG 必须恰好有一条 understanding；无法可靠理解时 status=unavailable 并填写 failure_reason。",
                },
                "dataLimitations": [
                    item
                    for item in fact_pack["dataLimitations"]
                    if str(item.get("field") or "").startswith("highlightFrames.")
                ],
            },
        ),
        (
            "material-deep-dive-input.json",
            "material_deep_dive",
            "materialDeepDives",
            {
                "reportScope": fact_pack["reportScopes"]["detail"],
                "materialFacts": _model_material_facts(fact_pack["materialFacts"]),
            },
        ),
    )
    manifest_units = []
    for filename, unit_name, output_field, evidence in units:
        path = unit_dir / filename
        payload = {
            "schemaVersion": (
                6 if unit_name == "ranking_brand" and "hotMaterialFacts" in fact_pack
                else 4 if unit_name == "ranking_brand" else 1
            ),
            "unit": unit_name,
            "outputField": output_field,
            "evidence": evidence,
        }
        if unit_name == "ranking_brand":
            payload["outputSchema"] = _ranking_output_schema(
                include_period_contract="hotMaterialFacts" in fact_pack
            )
        elif unit_name == "script_insights":
            payload["outputSchema"] = {
                "type": "array",
                "items": _analysis_insight_schema(),
            }
        write_json_atomically(payload, path, indent=None)
        manifest_units.append(
            {
                "unit": unit_name,
                "path": f"analysis-units/{filename}",
                "outputField": output_field,
                "bytes": path.stat().st_size,
                "sha256": file_sha256(path),
            }
        )
    output_schema_path = Path(output) / "yuntu-ai-analysis.schema.json"
    write_json_atomically(_analysis_output_schema(fact_pack), output_schema_path)
    manifest = {
        "schemaVersion": 5 if "hotMaterialFacts" in fact_pack else 4,
        "executionMode": "single_model_call",
        "sharedContext": {
            "filters": fact_pack["filters"],
            "reportScopes": fact_pack["reportScopes"],
            "dataAvailabilitySummary": fact_pack["dataAvailabilitySummary"],
            "assetRoot": "..",
        },
        "outputSchema": {
            "path": "yuntu-ai-analysis.schema.json",
            "bytes": output_schema_path.stat().st_size,
            "sha256": file_sha256(output_schema_path),
        },
        "units": manifest_units,
    }
    write_json_atomically(manifest, unit_dir / "analysis-unit-manifest.json")
    return manifest


PROMPT_TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "prompts" / "yuntu-analysis-prompt.md"
PROMPT_PLACEHOLDERS = (
    "__BRANDS__",
    "__SCOPE_LABELS__",
    "__HOT_MATERIAL_RULE__",
)


def _load_prompt_template():
    try:
        template = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        raise YuntuAnalysisError(
            f"unable to read prompt template {PROMPT_TEMPLATE_PATH}: {exc}"
        ) from exc
    missing = [token for token in PROMPT_PLACEHOLDERS if token not in template]
    if missing:
        raise YuntuAnalysisError(
            "prompt template is missing placeholders: " + ", ".join(missing)
        )
    return template


def _format_hot_material_rule(hot_material_rule=None):
    rule = hot_material_rule or load_hot_material_rule()
    return (
        f"metric=`{rule['metric']}`，comparison=`{rule['comparison']}`，"
        f"threshold={rule['threshold']}（本批次配置）"
    )


def _prompt_text(*, filters, hot_material_rule=None):
    brands = "、".join(str(brand) for brand in filters.get("brands", []) if brand)
    scope_labels = "、".join(
        ["all（全量 TOP1000）", *(str(brand) for brand in filters.get("brands", []) if brand)]
    )
    return (
        _load_prompt_template()
        .replace("__BRANDS__", brands or "未指定品牌")
        .replace("__SCOPE_LABELS__", scope_labels)
        .replace(
            "__HOT_MATERIAL_RULE__",
            _format_hot_material_rule(hot_material_rule),
        )
    )


def _load_ranking_run(root, manifest, run_key, fallback_records=None):
    runs = manifest.get("rankingRuns", {})
    run = runs.get(run_key) if isinstance(runs, dict) else None
    if not isinstance(run, dict) or run.get("status") != "success":
        return fallback_records if fallback_records is not None else []
    path = run.get("normalizedPath")
    if not isinstance(path, str) or not path:
        return fallback_records if fallback_records is not None else []
    try:
        records = _load_json(root / path)
    except YuntuAnalysisError:
        return fallback_records if fallback_records is not None else []
    return records if isinstance(records, list) else []


def _scope_records(records, scope, brands):
    if scope == "all":
        return list(records)
    return [
        record
        for record in records
        if scope in match_brands_from_title(record.get("title", ""), brands)
    ]


def _build_period_facts(manifest, query_records, previous_records, industry_records):
    runs = manifest.get("rankingRuns", {})
    runs = runs if isinstance(runs, dict) else {}

    def aggregate(records, run_key, source_scope, unavailable_reason=""):
        run = runs.get(run_key, {}) if isinstance(runs.get(run_key, {}), dict) else {}
        return _ranking_aggregate(
            records,
            source_scope=source_scope,
            actual_date_range=run.get("actualDateRange"),
            available=bool(records) and run.get("status") == "success",
            missing_reason=(
                unavailable_reason
                or ("" if records and run.get("status") == "success" else "comparison_data_unavailable")
            ),
        )

    current = aggregate(query_records, "query", "query")
    previous = aggregate(
        previous_records,
        "previous_period",
        "previous_period",
        "previous_period_not_collected" if not previous_records else "",
    )
    industry = aggregate(
        industry_records,
        "industry",
        "industry",
        "industry_benchmark_not_collected" if not industry_records else "",
    )
    return {
        "current": current,
        "previousPeriod": previous,
        "industryBenchmark": industry,
    }, {
        "previousPeriod": _comparison_fact(current, previous, baseline_name="previousPeriod"),
        "industryBenchmark": _comparison_fact(current, industry, baseline_name="industryBenchmark"),
    }


def _scope_period_facts(manifest, records_by_run, *, scope, brands):
    runs = manifest.get("rankingRuns", {})
    runs = runs if isinstance(runs, dict) else {}
    periods = {}
    for run_key, records in records_by_run.items():
        run = runs.get(run_key, {}) if isinstance(runs.get(run_key, {}), dict) else {}
        scoped_records = (
            records
            if run_key == "industry"
            else _scope_records(records, scope, brands)
        )
        periods[run_key] = _ranking_aggregate(
            scoped_records,
            source_scope=run_key,
            actual_date_range=run.get("actualDateRange"),
            available=bool(records) and run.get("status") == "success",
            missing_reason=("comparison_data_unavailable" if not records else ""),
        )
    return periods, {
        "current": periods["query"],
        "previousPeriod": _comparison_fact(
            periods["query"], periods["previous_period"], baseline_name="previousPeriod"
        ),
        "industryBenchmark": _comparison_fact(
            periods["query"], periods["industry"], baseline_name="industryBenchmark"
        ),
    }


def prepare_analysis(*, input_dir, output_dir, hot_material_config=None):
    root = Path(input_dir)
    output = Path(output_dir)
    try:
        hot_material_rule = load_hot_material_rule(hot_material_config)
    except HotMaterialConfigError as exc:
        raise YuntuAnalysisError(str(exc)) from exc
    manifest = _load_json(root / "batch-manifest.json")
    list_records = _load_json(root / "normalized" / "list-records.json")
    selected = manifest.get("selectedMaterials", [])
    rejected = manifest.get("rejectedMaterials", [])
    if not isinstance(selected, list) or not selected:
        raise YuntuAnalysisError("selectedMaterials must contain at least one material")
    pool_records = [record for record in list_records if isinstance(record, dict)]
    previous_records = _load_ranking_run(root, manifest, "previous_period")
    industry_records = _load_ranking_run(root, manifest, "industry")
    list_by_id = {record.get("material_id"): record for record in pool_records}
    selected_ids = {item.get("material_id") for item in selected}
    details = []
    material_facts = []
    for item in selected:
        material_id = item.get("material_id")
        detail_path = item.get("detailRecordPath")
        if not material_id or not detail_path:
            raise YuntuAnalysisError("selected material is missing material_id or detailRecordPath")
        detail = _load_json(root / detail_path)
        list_record = list_by_id.get(material_id, {})
        details.append(detail)
        material_facts.append(
            {
                "material_id": material_id,
                "rank": item.get("rank"),
                "title": list_record.get("title") or detail.get("title", ""),
                "metrics": list_record.get("metrics", {}),
                "exposure": list_record.get("exposure", {"min": None, "max": None, "raw": ""}),
                "metricComparison": _metric_comparison(list_record, pool_records),
                "people_tags": list_record.get("people_tags", []),
                "material_tags": list_record.get("material_tags", []),
                "high_points": detail.get("high_points", []),
                "loss_points": detail.get("loss_points", []),
                "script_text": detail.get("script_text", ""),
                "script_segments": detail.get("script_segments", []),
                "content_formula": detail.get("content_formula"),
                "creative_breakdown": detail.get("creative_breakdown"),
                "detailMetrics": detail.get("metrics", {}),
                "secondLevelBreakdown": _second_level_breakdown(detail),
                "listDataAvailability": list_record.get("data_availability", {}),
                "detailDataAvailability": detail.get("data_availability", {}),
            }
        )
    highlights = load_highlights_manifest(root)
    for detail in details_missing_standard_highlights(details, root):
        highlights[str(detail["material_id"])] = generate_standard_highlights_for_detail(
            detail, root
        )
    if details:
        write_highlights_manifest(root, highlights)
    for fact in material_facts:
        frames = highlights.get(str(fact["material_id"]), [])
        fact["highlightFrames"] = frames
        fact["highlightFrameAvailability"] = _highlight_frame_availability(
            frames, requested=True
        )
    candidate_pool = _candidate_pool(pool_records)
    report_scopes = _report_scopes(pool_records, selected, rejected)
    audience_dashboard = build_audience_dashboard(pool_records)
    tag_insights = _tag_insights(pool_records, selected_ids)
    trend_summary = _trend_summary(details)
    script_facts = build_script_facts(details, selected)
    brands = manifest.get("filters", {}).get("brands", [])
    ranking_period_facts, comparison_facts = _build_period_facts(
        manifest, pool_records, previous_records, industry_records
    )
    has_period_contract = bool(manifest.get("rankingRuns"))
    combination = build_top_material_combination(
        pool_records,
        top_n=len(pool_records),
        brands=brands,
    )
    list_by_id = {record.get("material_id"): record for record in pool_records}
    brand_facts = {
        "source_scope": "brand_in_top1000",
        "brands": {
            brand: {
                **_ranking_scope_facts(
                    [list_by_id[item["material_id"]] for item in group["topMaterials"]],
                    source_scope="brand_in_top1000",
                ),
            }
            for brand, group in combination.get("brands", {}).items()
        },
    }
    configured_brands = brands or list(brand_facts["brands"])
    comparison_facts["scopes"] = {}
    records_by_run = {
        "query": pool_records,
        "previous_period": previous_records,
        "industry": industry_records,
    }
    for scope in ["all", *configured_brands]:
        _periods, scope_comparisons = _scope_period_facts(
            manifest, records_by_run, scope=scope, brands=configured_brands
        )
        comparison_facts["scopes"][scope] = scope_comparisons
    hot_material_facts = None
    if has_period_contract:
        hot_material_facts = {
            "all": _hot_material_scope_facts(
                pool_records, scope="all", hot_material_rule=hot_material_rule
            )
        }
        for brand in configured_brands:
            brand_records = _scope_records(pool_records, brand, configured_brands)
            hot_material_facts[brand] = _hot_material_scope_facts(
                brand_records, scope="brand", hot_material_rule=hot_material_rule
            )
    scope_order = ["all"]
    chapter02_facts = {
        "scopeOrder": scope_order,
        "all": _chapter02_scope_fact(pool_records, label="全量 TOP1000", limit=1000),
    }
    chapter02_ai_facts = {
        "scopeOrder": scope_order,
        "all": _chapter02_scope_fact(pool_records, label="全量 TOP1000", limit=1000),
    }
    for brand in configured_brands:
        if brand not in brand_facts["brands"]:
            continue
        full_brand_materials = brand_facts["brands"][brand].get("materials", [])
        full_brand_records = [
            list_by_id[item["material_id"]]
            for item in full_brand_materials
            if item.get("material_id") in list_by_id
        ]
        ai_brand_materials = brand_facts["brands"][brand].get("materials", [])
        ai_brand_records = [
            list_by_id[item["material_id"]]
            for item in ai_brand_materials
            if item.get("material_id") in list_by_id
        ]
        scope_order.append(brand)
        chapter02_facts[brand] = _chapter02_scope_fact(
            full_brand_records,
            label=brand,
            limit=len(full_brand_records) or 1,
        )
        chapter02_ai_facts[brand] = _chapter02_scope_fact(
            ai_brand_records,
            label=brand,
            limit=len(ai_brand_records) or 1,
        )
    fact_pack = {
        "schemaVersion": 7 if has_period_contract else 6,
        "filters": manifest.get("filters", {}),
        "selectedMaterials": selected,
        "rejectedMaterials": rejected,
        "summaryMetrics": {"selectedCount": len(selected), "rejectedCount": len(rejected), "candidateCount": len(pool_records)},
        "candidatePool": candidate_pool,
        "reportScopes": report_scopes,
        "audienceDashboard": audience_dashboard,
        "tagInsights": tag_insights,
        "trendSummary": trend_summary,
        "scriptFacts": script_facts,
        "dataAvailabilitySummary": _availability_summary(material_facts),
        "materialFacts": material_facts,
        "chapter02Facts": chapter02_facts,
        "chapter02AiFacts": chapter02_ai_facts,
        **(
            {
                "current": ranking_period_facts["current"],
                "previousPeriod": ranking_period_facts["previousPeriod"],
                "industryBenchmark": ranking_period_facts["industryBenchmark"],
                "comparisonFacts": comparison_facts,
                "hotMaterialRule": dict(hot_material_rule),
                "hotMaterialFacts": hot_material_facts,
            }
            if has_period_contract
            else {}
        ),
    }
    fact_pack.update(
        _model_input_sections(
            material_facts,
            pool_records,
            brand_facts,
            chapter02_ai_facts,
            brands,
            ranking_period_facts,
            comparison_facts,
            hot_material_rule,
            hot_material_facts,
        )
    )
    write_json_atomically(
        _report_data(fact_pack), output / "report-data.json", indent=None
    )
    _write_analysis_units(fact_pack, output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "yuntu-analysis-prompt.md").write_text(
        _prompt_text(
            filters=manifest.get("filters", {}),
            hot_material_rule=hot_material_rule,
        ),
        encoding="utf-8",
    )
    return 0
