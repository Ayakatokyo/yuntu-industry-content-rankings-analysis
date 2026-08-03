"""Render final Yuntu analysis reports from model-authored JSON."""

import html
import json
from pathlib import Path

from rpa_io import write_json_atomically


class YuntuReportError(RuntimeError):
    """Raised when report inputs are invalid."""


REQUIRED_FIELDS = (
    "overallConclusion",
    "rankingInsights",
    "audienceInsights",
    "tagInsights",
    "trendInsights",
    "materialAnalyses",
    "creativePatterns",
    "nextActions",
)

SECTION_TITLES = (
    ("01｜行业榜单整体结论", "overallConclusion"),
    ("02｜Top 素材表现分层", "rankingInsights"),
    ("03｜人群与内容标签洞察", "audienceInsights"),
    ("04｜单素材秒级诊断", "materialAnalyses"),
    ("05｜高表现素材共性", "creativePatterns"),
    ("06｜小仙炖可借鉴创意方向", "tagInsights"),
    ("07｜下一轮素材建议", "nextActions"),
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
    return analysis


def _markdown_value(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, dict):
                text = (
                    item.get("summary")
                    or item.get("body")
                    or json.dumps(item, ensure_ascii=False, sort_keys=True)
                )
            else:
                text = str(item)
            lines.append(f"- {text}")
        return "\n".join(lines)
    return json.dumps(value, ensure_ascii=False, indent=2)


def _render_markdown(analysis):
    lines = ["# 云图行业内容榜单分析报告", ""]
    for title, field in SECTION_TITLES:
        lines.extend([f"## {title}", "", _markdown_value(analysis[field]), ""])
    lines.extend(["## 附：秒级趋势洞察", "", _markdown_value(analysis["trendInsights"]), ""])
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
