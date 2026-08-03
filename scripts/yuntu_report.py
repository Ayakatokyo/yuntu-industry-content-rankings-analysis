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


def _material_frames(fact_pack):
    frames = {}
    for fact in fact_pack.get("materialFacts", []) if isinstance(fact_pack, dict) else []:
        material_id = fact.get("material_id")
        if isinstance(material_id, str):
            frames[material_id] = fact.get("highlightFrames", [])
    return frames


def _render_html(analysis, material_frames):
    sections = []
    for title, field in SECTION_TITLES:
        cards = []
        for item in analysis[field]:
            summary = html.escape(str(item.get("summary", item.get("hypothesis", ""))))
            material_id = item.get("material_id")
            gallery = ""
            if field == "materialDiagnoses" and isinstance(material_id, str):
                usable = [frame for frame in material_frames.get(material_id, []) if frame.get("available") and str(frame.get("relative_path", "")).endswith(".jpg")]
                if usable:
                    gallery = '<div class="highlight-gallery">' + "".join(
                        '<figure><img src="%s" alt="%ss 高光帧"><figcaption>%s</figcaption></figure>' % (html.escape(frame["relative_path"], quote=True), frame.get("second", 0), "封面" if frame.get("is_cover") else f'{frame.get("second", 0)}s')
                        for frame in usable
                    ) + "</div>"
            cards.append(f'<article class="insight-card"><p>{summary}</p>{gallery}</article>')
        sections.append(f'<section class="report-section"><p class="section-number">{html.escape(title.split("｜")[0])}</p><h2>{html.escape(title.split("｜", 1)[1])}</h2>{"".join(cards)}</section>')
    return '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>云图行业内容榜单分析报告</title><style>
:root{--ink:#2d2018;--gold:#b88a45;--paper:#f7f0e4;--line:#d9c9b1}*{box-sizing:border-box}body{margin:0;background:#2d2018;color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}main{width:min(1100px,calc(100% - 32px));margin:auto;padding:32px 0 64px}.report-cover{padding:42px 34px;color:#fff;border-bottom:3px solid var(--gold)}.report-cover p{color:#d9bd91;font-size:13px;letter-spacing:0}.report-cover h1{font-size:42px;margin:14px 0 0}.report-section{margin-top:20px;padding:28px;background:var(--paper);border:1px solid var(--line);border-radius:8px}.section-number{color:var(--gold);font-weight:700;margin:0 0 8px}.report-section h2{margin:0 0 18px;font-size:26px}.insight-card{padding:16px 0;border-top:1px solid var(--line);line-height:1.7}.highlight-gallery{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-top:14px}.highlight-gallery figure{margin:0;background:#fff;padding:8px}.highlight-gallery img{display:block;width:100%;aspect-ratio:16/9;object-fit:cover}.highlight-gallery figcaption{font-size:13px;color:#765b40;margin-top:6px}@media(max-width:560px){main{width:min(100% - 20px,1100px);padding-top:10px}.report-cover{padding:30px 20px}.report-cover h1{font-size:32px}.report-section{padding:20px}.highlight-gallery{grid-template-columns:1fr 1fr}}</style></head><body><main><header class="report-cover"><p>小仙炖｜行业内容策略</p><h1>云图行业内容榜单分析报告</h1></header>''' + "".join(sections) + "</main></body></html>"


def render_report(*, analysis_json, output_dir, fact_pack=None):
    analysis = _load_analysis(analysis_json)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    data = {"status": "complete", "analysis": analysis}
    write_json_atomically(data, output / "final-report-data.json")
    markdown = _render_markdown(analysis)
    (output / "final-report.md").write_text(markdown, encoding="utf-8")
    (output / "final-report.html").write_text(_render_html(analysis, _material_frames(fact_pack or {})), encoding="utf-8")
    return 0
