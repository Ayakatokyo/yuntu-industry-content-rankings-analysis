"""Render final Yuntu analysis reports from model-authored JSON."""

import html
import json
from pathlib import Path

from rpa_io import write_json_atomically


class YuntuReportError(RuntimeError):
    """Raised when report inputs are invalid."""


REQUIRED_FIELDS = (
    "rankingOverview",
    "materialComparison",
    "materialDiagnoses",
    "competitorPatterns",
    "xiaoxianDunOpportunityMap",
    "experimentMatrix",
)

SECTION_TITLES = (
    ("01｜榜单机会总览", "rankingOverview"),
    ("02｜素材表现对比", "materialComparison"),
    ("03｜单素材秒级诊断", "materialDiagnoses"),
    ("04｜竞品创意模式", "competitorPatterns"),
    ("05｜小仙炖机会地图", "xiaoxianDunOpportunityMap"),
    ("06｜下一轮实验矩阵", "experimentMatrix"),
)

EVIDENCE_FIELDS = tuple(field for _, field in SECTION_TITLES[:-1])
EXPERIMENT_FIELDS = (
    "priority",
    "hypothesis",
    "creative_variable",
    "target_audience",
    "success_metric",
    "control",
    "review_action",
)


def _load_analysis(path):
    try:
        analysis = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        raise YuntuReportError(f"unable to read analysis JSON: {exc}") from exc
    if not isinstance(analysis, dict):
        raise YuntuReportError("analysis JSON must be an object")
    missing = [field for field in REQUIRED_FIELDS if field not in analysis]
    if missing:
        raise YuntuReportError(
            "analysis JSON is missing required fields: " + ", ".join(missing)
        )
    for field in EVIDENCE_FIELDS:
        _validate_evidence_section(analysis[field], field)
    _validate_experiments(analysis["experimentMatrix"])
    return analysis


def _validate_evidence_section(items, field):
    if not isinstance(items, list) or not items:
        raise YuntuReportError(f"{field} must be a nonempty list")
    for item in items:
        if not isinstance(item, dict):
            raise YuntuReportError(f"{field} items must be objects")
        evidence = item.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise YuntuReportError(f"{field} items must include evidence")
        material_id = item.get("material_id")
        material_ids = item.get("material_ids")
        if isinstance(material_id, str) and material_id.isdigit():
            continue
        if isinstance(material_ids, list) and material_ids and all(
            isinstance(value, str) and value.isdigit() for value in material_ids
        ):
            continue
        raise YuntuReportError(
            f"{field} items must include material_id or material_ids"
        )


def _validate_experiments(items):
    if not isinstance(items, list) or not items:
        raise YuntuReportError("experimentMatrix must be a nonempty list")
    for item in items:
        if not isinstance(item, dict):
            raise YuntuReportError("experimentMatrix items must be objects")
        for field in EXPERIMENT_FIELDS:
            if not isinstance(item.get(field), str) or not item[field].strip():
                raise YuntuReportError(
                    f"experimentMatrix items must include {field}"
                )


def _markdown_value(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, dict):
                if "hypothesis" in item:
                    text = (
                        f"{item['priority']}｜假设：{item['hypothesis']}；变量："
                        f"{item['creative_variable']}；目标人群：{item['target_audience']}；"
                        f"成功指标：{item['success_metric']}；对照：{item['control']}；"
                        f"复盘：{item['review_action']}"
                    )
                else:
                    material_ids = item.get("material_ids") or [item.get("material_id")]
                    material_text = "、".join(
                        str(material_id) for material_id in material_ids if material_id
                    )
                    evidence = json.dumps(
                        item.get("evidence", []), ensure_ascii=False, sort_keys=True
                    )
                    text = (
                        f"{item.get('summary') or item.get('body') or ''} "
                        f"素材：{material_text}；证据：{evidence}"
                    ).strip()
            else:
                text = str(item)
            lines.append(f"- {text}")
        return "\n".join(lines)
    return json.dumps(value, ensure_ascii=False, indent=2)


def _render_markdown(analysis):
    lines = ["# 云图行业内容榜单分析报告", ""]
    for title, field in SECTION_TITLES:
        lines.extend([f"## {title}", "", _markdown_value(analysis[field]), ""])
    return "\n".join(lines)


def _render_html(markdown):
    body = html.escape(markdown).replace("\n", "<br>\n")
    return (
        '<!doctype html>\n<html lang="zh-CN">\n<meta charset="utf-8">\n'
        "<title>云图行业内容榜单分析报告</title>\n<body>\n"
        + body
        + "\n</body>\n</html>\n"
    )


def render_report(*, analysis_json, output_dir):
    analysis = _load_analysis(analysis_json)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    data = {"status": "complete", "analysis": analysis}
    write_json_atomically(data, output / "final-report-data.json")
    markdown = _render_markdown(analysis)
    (output / "final-report.md").write_text(markdown, encoding="utf-8")
    (output / "final-report.html").write_text(_render_html(markdown), encoding="utf-8")
    return 0
