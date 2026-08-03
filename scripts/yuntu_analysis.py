"""Build Yuntu analysis fact packs from normalized records."""

import json
from pathlib import Path

from rpa_io import write_json_atomically


class YuntuAnalysisError(RuntimeError):
    """Raised when analysis facts cannot be prepared."""


def _load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        raise YuntuAnalysisError(f"unable to read JSON {path}: {exc}") from exc


def _count_values(records, key):
    counts = {}
    for record in records:
        for value in record.get(key, []):
            counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _trend_highlights(details_by_id):
    high_names = []
    loss_names = []
    for detail in details_by_id.values():
        for point in detail.get("high_points", []):
            name = point.get("trend_name")
            if name and name not in high_names:
                high_names.append(name)
        for point in detail.get("loss_points", []):
            name = point.get("trend_name")
            if name and name not in loss_names:
                loss_names.append(name)
    return {"highPointNames": high_names, "lossPointNames": loss_names}


def _prompt_text():
    return (
        "# 云图行业内容榜单分析任务\n\n"
        "读取同目录的 `yuntu-analysis-data.json`，生成 `yuntu-ai-analysis.json`。\n\n"
        "输出必须包含：overallConclusion、rankingInsights、audienceInsights、tagInsights、"
        "trendInsights、materialAnalyses、creativePatterns、nextActions。\n\n"
        "所有结论必须引用素材 ID、指标、标签或秒级趋势作为证据。事实不足时写“数据不足以判断”。\n"
        "不得写执行过程、重跑、补位调度、代码状态或排障细节。\n"
    )


def prepare_analysis(*, input_dir, output_dir):
    root = Path(input_dir)
    output = Path(output_dir)
    manifest = _load_json(root / "batch-manifest.json")
    list_records = _load_json(root / "normalized" / "list-records.json")
    selected = manifest.get("selectedMaterials", [])
    rejected = manifest.get("rejectedMaterials", [])
    if not isinstance(selected, list) or not selected:
        raise YuntuAnalysisError("selectedMaterials must contain at least one material")

    list_by_id = {
        record.get("material_id"): record for record in list_records if isinstance(record, dict)
    }
    details_by_id = {}
    material_facts = []
    for item in selected:
        material_id = item.get("material_id")
        detail_path = item.get("detailRecordPath")
        if not material_id or not detail_path:
            raise YuntuAnalysisError(
                "selected material is missing material_id or detailRecordPath"
            )
        detail = _load_json(root / detail_path)
        details_by_id[material_id] = detail
        list_record = list_by_id.get(material_id, {})
        material_facts.append(
            {
                "material_id": material_id,
                "rank": item.get("rank"),
                "title": list_record.get("title", ""),
                "metrics": list_record.get("metrics", {}),
                "people_tags": list_record.get("people_tags", []),
                "material_tags": list_record.get("material_tags", []),
                "high_points": detail.get("high_points", []),
                "loss_points": detail.get("loss_points", []),
            }
        )

    fact_pack = {
        "schemaVersion": 1,
        "filters": manifest.get("filters", {}),
        "selectedMaterials": selected,
        "rejectedMaterials": rejected,
        "summaryMetrics": {
            "selectedCount": len(selected),
            "rejectedCount": len(rejected),
            "candidateCount": len(manifest.get("candidateMaterials", [])),
        },
        "audienceAggregations": _count_values(list_by_id.values(), "people_tags"),
        "tagAggregations": _count_values(list_by_id.values(), "material_tags"),
        "trendHighlights": _trend_highlights(details_by_id),
        "materialFacts": material_facts,
    }
    write_json_atomically(fact_pack, output / "yuntu-analysis-data.json")
    output.mkdir(parents=True, exist_ok=True)
    (output / "yuntu-analysis-prompt.md").write_text(_prompt_text(), encoding="utf-8")
    return 0
