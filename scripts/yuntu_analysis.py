"""Build auditable Xiaoxian Dun analysis fact packs from normalized records."""

import json
from pathlib import Path
from statistics import median

from rpa_io import write_json_atomically
from yuntu_highlights import generate_highlights, normalize_highlight_trends
from yuntu_top_materials import build_audience_dashboard, build_top_material_combination


class YuntuAnalysisError(RuntimeError):
    """Raised when analysis facts cannot be prepared."""


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


def _prompt_text():
    return """# 小仙炖云图行业内容榜单分析任务

读取同目录的 `yuntu-analysis-data.json`，生成 `yuntu-ai-analysis.json`。

输出必须是 JSON 对象，包含：topMaterialCombination、rankingOverview、materialComparison、materialDiagnoses、competitorPatterns、xiaoxianDunOpportunityMap、experimentMatrix。

`topMaterialCombination` 必须是对象，包含 `overallConclusions`、`brandConclusions` 与 `brandComparisonConclusion`。`overallConclusions` 必须恰好有三项，每项含 dimension、summary、evidence、material_ids，dimension 分别且只能为 `data`、`people`、`marketing`：data 总结曝光集中度与内容表现，people 总结年龄、性别和八大人群的曝光加权覆盖，marketing 总结成分/功效/痛点/场景/内容形式/促销利益。人群结论必须明确写出“人群标签是重叠标签，不是真实人群分布，不能相加为 100%。”每个品牌结论必须含 brand、classificationSource、dataSummary、peopleSummary、marketingSummary、evidence、material_ids，且 classificationSource 必须为 `title_rule`；三个 Summary 分别只写该品牌的数据、人群、营销卖点结论。`brandComparisonConclusion` 必须含 summary、evidence、material_ids，summary 直接总结品牌间的曝光集中度、内容表现、人群覆盖与卖点结构差异。标题匹配归属是业务分类，不得称作 RPA 原生品牌字段。CPM 缺失或标签比较样本不足时写“数据不足以判断”。标签与指标只能描述共现关系，不得声称因果。

前五个章节的每一项必须含 summary、evidence，以及 material_id 或 material_ids。experimentMatrix 的每一项必须含 priority、hypothesis、creative_variable、target_audience、success_metric、control、review_action。

所有结论必须引用素材 ID、指标、标签或秒级趋势作为证据。事实不足时写“数据不足以判断”。解释只能描述可能关系，不得声称因果；不得生成未经业务与合规确认的滋补、孕期或健康功效宣称。不得写执行过程、重跑、补位调度、代码状态或排障细节。
"""


def prepare_analysis(*, input_dir, output_dir, highlight_trends=None):
    root = Path(input_dir)
    output = Path(output_dir)
    selected_trends = normalize_highlight_trends(highlight_trends or [])
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
                "listDataAvailability": list_record.get("data_availability", {}),
                "detailDataAvailability": detail.get("data_availability", {}),
            }
        )
    highlights = (
        generate_highlights(details, selected_trends, root) if selected_trends else {}
    )
    for fact in material_facts:
        frames = highlights.get(str(fact["material_id"]), [])
        fact["highlightFrames"] = frames
        fact["highlightFrameAvailability"] = _highlight_frame_availability(
            frames, requested=bool(selected_trends)
        )
    fact_pack = {
        "schemaVersion": 3,
        "filters": manifest.get("filters", {}),
        "selectedMaterials": selected,
        "rejectedMaterials": rejected,
        "summaryMetrics": {"selectedCount": len(selected), "rejectedCount": len(rejected), "candidateCount": len(pool_records)},
        "candidatePool": _candidate_pool(pool_records),
        "topMaterialCombination": build_top_material_combination(pool_records),
        "audienceDashboard": build_audience_dashboard(pool_records),
        "tagInsights": _tag_insights(pool_records, selected_ids),
        "trendSummary": _trend_summary(details),
        "dataAvailabilitySummary": _availability_summary(material_facts),
        "materialFacts": material_facts,
    }
    write_json_atomically(fact_pack, output / "yuntu-analysis-data.json")
    output.mkdir(parents=True, exist_ok=True)
    (output / "yuntu-analysis-prompt.md").write_text(_prompt_text(), encoding="utf-8")
    return 0
