"""Build auditable industry content analysis fact packs from normalized records."""

import json
from pathlib import Path
from statistics import median

from rpa_io import file_sha256, write_json_atomically
from yuntu_highlights import (
    ALLOWED_HIGHLIGHT_TRENDS,
    details_missing_standard_highlights,
    generate_standard_highlights_for_detail,
    load_highlights_manifest,
    write_highlights_manifest,
)
from yuntu_top_materials import (
    build_audience_dashboard,
    build_marketing_dashboard,
    build_top_material_combination,
    select_top_materials,
)


class YuntuAnalysisError(RuntimeError):
    """Raised when analysis facts cannot be prepared."""


SECOND_LEVEL_TRENDS = ALLOWED_HIGHLIGHT_TRENDS
RANKING_FACT_METRICS = ("show_cnt", "ctr", "cvr", "play_3s_rate")
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
    "brandTopNFacts",
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
    return {
        "material_id": str(record.get("material_id", "")),
        "rank": record.get("rank"),
        "title": record.get("title", ""),
        "metrics": {
            name: record.get("metrics", {}).get(name)
            for name in RANKING_FACT_METRICS
            if name in record.get("metrics", {})
        },
        "people_tags": list(record.get("people_tags", [])),
        "material_tags": list(record.get("material_tags", [])),
    }


def _ranking_scope_facts(records, *, source_scope, requested_top_n):
    selected = select_top_materials(records, limit=requested_top_n)
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
    metrics["cpm"] = {
        "available": False,
        "missing_reason": "rpa_not_provided",
    }
    return {
        "source_scope": source_scope,
        "requested_top_n": requested_top_n,
        "sample_count": len(selected),
        "metrics": metrics,
        "materials": [_ranking_material_fact(record) for record in selected],
    }


def _audience_topn_records(records, *, limit=1000):
    return [
        {
            "material_id": str(record.get("material_id", "")),
            "rank": record.get("rank"),
            "people_tags": [
                tag for tag in record.get("people_tags", [])
                if isinstance(tag, str) and tag
            ],
        }
        for record in select_top_materials(records, limit=limit)
    ]


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
    candidate_pool,
    audience_dashboard,
    tag_insights,
    trend_summary,
    report_scopes,
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
        "reportScopes": report_scopes,
        "rankingFacts": {
            "candidatePool": candidate_pool,
            "materials": [
                {
                    "material_id": str(fact["material_id"]),
                    "rank": fact["rank"],
                    "title": fact["title"],
                    "metrics": fact["metrics"],
                    "metricComparison": fact["metricComparison"],
                }
                for fact in material_facts
            ],
        },
        "industryTop1000Facts": _ranking_scope_facts(
            pool_records,
            source_scope="industry_top1000",
            requested_top_n=1000,
        ),
        "brandTopNFacts": brand_facts,
        "chapter02AiFacts": chapter02_ai_facts,
        "audienceFacts": {
            "labelsMayOverlap": True,
            "notice": "人群标签是重叠标签，不是真实人群分布，不能相加为 100%。",
            "dashboard": audience_dashboard,
            "materials": [
                {
                    "material_id": str(fact["material_id"]),
                    "people_tags": fact["people_tags"],
                }
                for fact in material_facts
            ],
        },
        "marketingFacts": {
            "tagInsights": tag_insights,
            "materials": [
                {
                    "material_id": str(fact["material_id"]),
                    "material_tags": fact["material_tags"],
                }
                for fact in material_facts
            ],
        },
        "secondLevelFacts": {
            "trendSummary": trend_summary,
            "materials": [
                {
                    "material_id": str(fact["material_id"]),
                    "metrics": fact["secondLevelBreakdown"]["metrics"],
                }
                for fact in material_facts
            ],
        },
        "highlightFrameFacts": [
            {
                key: asset[key]
                for key in (
                    "material_id",
                    "frame_ref",
                    "second",
                    "frame_type",
                    "peak_rank",
                    "click_value",
                    "available",
                    "failure_reason",
                )
            }
            for asset in visual_assets
        ],
        "visualAssets": visual_assets,
        "dataLimitations": _data_limitations(material_facts),
    }


def _report_data(fact_pack):
    """Project only facts consumed by report validation and rendering."""
    projected = {key: fact_pack[key] for key in REPORT_DATA_FIELDS if key in fact_pack}
    industry = fact_pack.get("industryTop1000Facts", {})
    projected["industryTop1000Facts"] = {
        key: industry[key]
        for key in ("source_scope", "requested_top_n", "sample_count")
        if key in industry
    }
    brand_facts = fact_pack.get("brandTopNFacts", {})
    projected["brandTopNFacts"] = {
        "source_scope": brand_facts.get("source_scope"),
        "requested_top_n": brand_facts.get("requested_top_n"),
        "brands": {
            brand: {"source_scope": facts.get("source_scope")}
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


def _model_material_facts(material_facts):
    projected = []
    for fact in material_facts:
        copied = {
            key: fact[key]
            for key in (
                "material_id",
                "rank",
                "title",
                "metrics",
                "metricComparison",
                "people_tags",
                "material_tags",
                "secondLevelBreakdown",
                "highlightFrameAvailability",
            )
            if key in fact
        }
        copied["highlightFrames"] = []
        for frame in fact.get("highlightFrames", []):
            frame_copy = dict(frame)
            relative_path = str(frame_copy.get("relative_path") or "").replace("\\", "/")
            frame_copy["image_path"] = f"../{relative_path}" if relative_path else ""
            copied["highlightFrames"].append(frame_copy)
        projected.append(copied)
    return projected


def _ranking_output_schema():
    summary_schema = {
        "type": "object",
        "required": ["title", "summary", "evidence", "material_ids"],
        "properties": {
            "title": {"type": "string"},
            "summary": {"type": "string"},
            "evidence": {"type": "array", "items": {"type": "string"}},
            "material_ids": {"type": "array", "items": {"type": "string"}},
        },
    }
    brand_conclusion_schema = {
        "type": "object",
        "required": [
            "brand",
            "classificationSource",
            "dataSummary",
            "evidence",
            "material_ids",
        ],
        "properties": {
            "brand": {"type": "string"},
            "classificationSource": {
                "type": "string",
                "enum": ["title_rule", "runtime_title_rule"],
            },
            "dataSummary": {"type": "string"},
            "evidence": {"type": "array", "items": {"type": "string"}},
            "material_ids": {"type": "array", "items": {"type": "string"}},
        },
    }
    comparison_evidence_schema = {
        "type": "object",
        "required": ["brand", "metric", "value"],
        "properties": {
            "brand": {"type": "string"},
            "metric": {"type": "string"},
            "value": {"type": ["number", "string"]},
        },
    }
    return {
        "type": "object",
        "required": [
            "executiveSummary",
            "brandConclusions",
            "brandComparisonConclusion",
        ],
        "properties": {
            "executiveSummary": summary_schema,
            "brandConclusions": {
                "type": "array",
                "items": brand_conclusion_schema,
            },
            "brandComparisonConclusion": {
                "type": "object",
                "required": ["title", "summary", "evidence", "material_ids"],
                "properties": {
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "evidence": {
                        "type": "array",
                        "items": comparison_evidence_schema,
                    },
                    "material_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
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


def _chapter02_output_schema(fact_pack):
    scope_order = [str(scope) for scope in fact_pack["chapter02AiFacts"]["scopeOrder"]]
    scope_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "audienceSummary",
            "audienceInsights",
            "marketingSummary",
            "marketingInsights",
        ],
        "properties": {
            "audienceSummary": _analysis_insight_schema(),
            "audienceInsights": {
                "type": "array",
                "minItems": 2,
                "items": _analysis_insight_schema(),
            },
            "marketingSummary": _analysis_insight_schema(),
            "marketingInsights": {
                "type": "array",
                "minItems": 2,
                "items": _analysis_insight_schema(),
            },
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
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["groups"],
        "properties": {
            "groups": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "category",
                        "frame_refs",
                        "common_patterns",
                        "derivative_directions",
                    ],
                    "properties": {
                        "category": {
                            "type": "string",
                            "enum": ["portrait", "product", "other"],
                        },
                        "frame_refs": {
                            "type": "array",
                            "minItems": 1,
                            "items": {"type": "string"},
                        },
                        "common_patterns": {
                            "type": "array",
                            "minItems": 1,
                            "items": {"type": "string"},
                        },
                        "derivative_directions": {
                            "type": "array",
                            "items": direction_schema,
                        },
                    },
                },
            }
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
                "second_level_observations",
            ],
            "properties": {
                "material_id": {"type": "string", "enum": material_ids},
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
                "second_level_observations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["trend_name", "summary", "evidence_seconds"],
                        "properties": {
                            "trend_name": {
                                "type": "string",
                                "enum": list(SECOND_LEVEL_TRENDS),
                            },
                            "summary": {"type": "string"},
                            "evidence_seconds": {
                                "type": "array",
                                "items": {"type": "integer"},
                            },
                        },
                    },
                },
            },
        },
    }


def _analysis_output_schema(fact_pack):
    properties = {
        "topMaterialCombination": _ranking_output_schema(),
        "chapter02Insights": _chapter02_output_schema(fact_pack),
    }
    required = ["topMaterialCombination", "chapter02Insights"]
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
    units = (
        (
            "ranking-brand-input.json",
            "ranking_brand",
            "topMaterialCombination",
            {
                "reportScope": fact_pack["reportScopes"]["ranking"],
                "industryTop1000Facts": fact_pack["industryTop1000Facts"],
                "brandTopNFacts": fact_pack["brandTopNFacts"],
            },
        ),
        (
            "audience-marketing-input.json",
            "audience_marketing",
            "chapter02Insights",
            {"chapter02AiFacts": fact_pack["chapter02AiFacts"]},
        ),
        (
            "highlight-input.json",
            "highlight",
            "highlightDashboard",
            {
                "reportScope": fact_pack["reportScopes"]["detail"],
                "visualAssets": _model_visual_assets(fact_pack["visualAssets"]),
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
            "schemaVersion": 2 if unit_name == "ranking_brand" else 1,
            "unit": unit_name,
            "outputField": output_field,
            "evidence": evidence,
        }
        if unit_name == "ranking_brand":
            payload["outputSchema"] = _ranking_output_schema()
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
        "schemaVersion": 2,
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
    "__BRAND_SCOPE_LABEL__",
    "__BRANDS__",
    "__SCOPE_LABELS__",
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


def _prompt_text(*, brand_top_n, filters):
    brands = "、".join(str(brand) for brand in filters.get("brands", []) if brand)
    scope_labels = "、".join(
        ["all（全量 TOP1000）", *(str(brand) for brand in filters.get("brands", []) if brand)]
    )
    brand_scope_label = (
        f"Top {brand_top_n}"
        if isinstance(brand_top_n, int) and brand_top_n > 0
        else "全量匹配素材"
    )
    return (
        _load_prompt_template()
        .replace("__BRAND_SCOPE_LABEL__", brand_scope_label)
        .replace("__BRANDS__", brands or "未指定品牌")
        .replace("__SCOPE_LABELS__", scope_labels)
    )


def prepare_analysis(*, input_dir, output_dir, brand_top_n=30):
    root = Path(input_dir)
    output = Path(output_dir)
    manifest = _load_json(root / "batch-manifest.json")
    list_records = _load_json(root / "normalized" / "list-records.json")
    selected = manifest.get("selectedMaterials", [])
    rejected = manifest.get("rejectedMaterials", [])
    if not isinstance(selected, list) or not selected:
        raise YuntuAnalysisError("selectedMaterials must contain at least one material")
    pool_records = [record for record in list_records if isinstance(record, dict)]
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
                "title": list_record.get("title", ""),
                "metrics": list_record.get("metrics", {}),
                "metricComparison": _metric_comparison(list_record, pool_records),
                "people_tags": list_record.get("people_tags", []),
                "material_tags": list_record.get("material_tags", []),
                "high_points": detail.get("high_points", []),
                "loss_points": detail.get("loss_points", []),
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
    audience_topn_records = _audience_topn_records(pool_records)
    tag_insights = _tag_insights(pool_records, selected_ids)
    trend_summary = _trend_summary(details)
    brands = manifest.get("filters", {}).get("brands", [])
    combination = build_top_material_combination(
        pool_records,
        top_n=brand_top_n,
        brands=brands,
    )
    full_brand_combination = build_top_material_combination(
        pool_records,
        top_n=None,
        brands=brands,
    )
    list_by_id = {record.get("material_id"): record for record in pool_records}
    brand_facts = {
        "source_scope": "brand_top_n",
        "requested_top_n": brand_top_n,
        "brands": {
            brand: _ranking_scope_facts(
                [list_by_id[item["material_id"]] for item in group["topMaterials"]],
                source_scope="brand_top_n",
                requested_top_n=brand_top_n,
            )
            for brand, group in combination.get("brands", {}).items()
        },
    }
    scope_order = ["all"]
    chapter02_facts = {
        "scopeOrder": scope_order,
        "all": _chapter02_scope_fact(pool_records, label="全量 TOP1000", limit=1000),
    }
    chapter02_ai_facts = {
        "scopeOrder": scope_order,
        "all": _chapter02_scope_fact(pool_records, label="全量 TOP1000", limit=1000),
    }
    configured_brands = brands or list(brand_facts["brands"])
    for brand in configured_brands:
        if brand not in brand_facts["brands"] or brand not in full_brand_combination.get("brands", {}):
            continue
        full_brand_materials = full_brand_combination["brands"][brand].get("topMaterials", [])
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
        "schemaVersion": 4,
        "filters": manifest.get("filters", {}),
        "selectedMaterials": selected,
        "rejectedMaterials": rejected,
        "summaryMetrics": {"selectedCount": len(selected), "rejectedCount": len(rejected), "candidateCount": len(pool_records)},
        "candidatePool": candidate_pool,
        "reportScopes": report_scopes,
        "topMaterialCombination": combination,
        "audienceDashboard": audience_dashboard,
        "audienceTopNRecords": audience_topn_records,
        "tagInsights": tag_insights,
        "trendSummary": trend_summary,
        "dataAvailabilitySummary": _availability_summary(material_facts),
        "materialFacts": material_facts,
        "chapter02Facts": chapter02_facts,
        "chapter02AiFacts": chapter02_ai_facts,
    }
    fact_pack.update(
        _model_input_sections(
            material_facts,
            pool_records,
            brand_facts,
            chapter02_ai_facts,
            candidate_pool,
            audience_dashboard,
            tag_insights,
            trend_summary,
            report_scopes,
        )
    )
    write_json_atomically(
        _report_data(fact_pack), output / "report-data.json", indent=None
    )
    _write_analysis_units(fact_pack, output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "yuntu-analysis-prompt.md").write_text(
        _prompt_text(brand_top_n=brand_top_n, filters=manifest.get("filters", {})),
        encoding="utf-8",
    )
    return 0
