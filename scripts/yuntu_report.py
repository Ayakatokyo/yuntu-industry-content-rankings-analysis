"""Render final Yuntu analysis reports from model-authored JSON."""

import html
import json
import math
import re
from pathlib import Path
from string import Template

from rpa_io import write_json_atomically


SKILL_ROOT = Path(__file__).resolve().parents[1]
HTML_TEMPLATE_PATH = Path(__file__).with_name("templates") / "final-report-template.html"
REPORT_STYLE_PATH = SKILL_ROOT / "assets" / "report" / "unified-report.css"
REPORT_SCRIPT_PATH = SKILL_ROOT / "assets" / "report" / "unified-report.js"
CURRENT_REPORT_SECTIONS = (
    ("top_material_combination", "top-material-combination", "01｜TOP 素材组合结论"),
    ("audience_insights", "audience-insights", "02｜人群洞察"),
)


class YuntuReportError(RuntimeError):
    """Raised when report inputs are invalid."""


def _read_report_source(path, label):
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise YuntuReportError(f"unable to read {label}: {path}") from exc


def _load_html_template():
    source = _read_report_source(HTML_TEMPLATE_PATH, "report template")
    for placeholder in (
        "$style",
        "$unified_style",
        "$unified_script",
        *(f"${name}" for name, _section_id, _title in CURRENT_REPORT_SECTIONS),
    ):
        if source.count(placeholder) != 1:
            raise YuntuReportError(
                f"report template must contain exactly one {placeholder}"
            )
    return Template(source)


def _validate_rendered_sections(rendered_html):
    for _placeholder, section_id, title in CURRENT_REPORT_SECTIONS:
        if rendered_html.count(f'id="{section_id}"') != 1:
            raise YuntuReportError(
                f"rendered report must contain exactly one section {section_id}"
            )
        if rendered_html.count(title) < 1:
            raise YuntuReportError(
                f"rendered report is missing current section title: {title}"
            )


REQUIRED_FIELDS = (
    "topMaterialCombination",
    "rankingOverview",
    "materialComparison",
    "materialDiagnoses",
    "competitorPatterns",
    "xiaoxianDunOpportunityMap",
    "experimentMatrix",
)

SECTION_TITLES = (
    ("02｜榜单竞争格局", "rankingOverview"),
    ("03｜内容表现地图", "materialComparison"),
    ("04｜内容与人群机会", "xiaoxianDunOpportunityMap"),
    ("05｜竞品内容模式", "competitorPatterns"),
    ("06｜秒级创意结构", "materialDiagnoses"),
    ("07｜机会与实验", "experimentMatrix"),
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
TOP_MATERIAL_DIMENSIONS = ("data", "people", "marketing")
TOP_MATERIAL_LABELS = {
    "data": "从数据维度看",
    "people": "从人群维度看",
    "marketing": "从营销卖点维度看",
}
BRAND_SUMMARY_FIELDS = {
    "data": "dataSummary",
    "people": "peopleSummary",
    "marketing": "marketingSummary",
}
TOP_MATERIAL_BRAND_ORDER = ("万益蓝/WONDERLAB", "五个女博士", "燕之屋")
AUDIENCE_DIMENSION_LABELS = {
    "age": "年龄",
    "gender": "性别",
    "crowd": "八大人群",
}
PEOPLE_TAG_OVERLAP_NOTICE = (
    "人群标签是重叠标签，不是真实人群分布，不能相加为 100%。"
)
AUDIT_JSON_PATTERN = re.compile(r'(?:\[\s*)?\{\s*"[^"\n]+"\s*:')


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
    _validate_top_material_combination(analysis["topMaterialCombination"])
    _validate_experiments(analysis["experimentMatrix"])
    return analysis


def _validate_evidence_section(items, field):
    if not isinstance(items, list) or not items:
        raise YuntuReportError(f"{field} must be a nonempty list")
    for item in items:
        if not isinstance(item, dict):
            raise YuntuReportError(f"{field} items must be objects")
        _validate_summary(item.get("summary"), f"{field} items summary")
        _validate_evidence_and_material_ids(item, f"{field} items")


def _validate_summary(value, field):
    if not isinstance(value, str) or not value.strip():
        raise YuntuReportError(f"{field} must be a nonempty string")
    if (
        "查看数据依据" in value
        or "证据：" in value
        or AUDIT_JSON_PATTERN.search(value)
    ):
        raise YuntuReportError(f"{field} must not contain audit evidence")


def _validate_evidence_and_material_ids(item, field):
    evidence = item.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise YuntuReportError(f"{field} must include evidence")
    material_id = item.get("material_id")
    material_ids = item.get("material_ids")
    if isinstance(material_id, str) and material_id.isdigit():
        return
    if isinstance(material_ids, list) and material_ids and all(
        isinstance(value, str) and value.isdigit() for value in material_ids
    ):
        return
    raise YuntuReportError(f"{field} must include material_id or material_ids")


def _validate_top_material_combination(value):
    if not isinstance(value, dict):
        raise YuntuReportError("topMaterialCombination must be an object")
    overall = value.get("overallConclusions")
    if not isinstance(overall, list) or len(overall) != len(TOP_MATERIAL_DIMENSIONS):
        raise YuntuReportError(
            "topMaterialCombination.overallConclusions must contain exactly three dimensions"
        )
    dimensions = []
    for item in overall:
        if not isinstance(item, dict):
            raise YuntuReportError(
                "topMaterialCombination.overallConclusions items must be objects"
            )
        dimension = item.get("dimension")
        if dimension not in TOP_MATERIAL_DIMENSIONS:
            raise YuntuReportError(
                "topMaterialCombination.overallConclusions dimension must be data, people, or marketing"
            )
        dimensions.append(dimension)
        _validate_summary(
            item.get("summary"), "topMaterialCombination.overallConclusions summary"
        )
        _validate_evidence_and_material_ids(
            item, "topMaterialCombination.overallConclusions items"
        )
    if set(dimensions) != set(TOP_MATERIAL_DIMENSIONS):
        raise YuntuReportError(
            "topMaterialCombination.overallConclusions dimensions must be unique"
        )
    brands = value.get("brandConclusions")
    if not isinstance(brands, list):
        raise YuntuReportError("topMaterialCombination.brandConclusions must be a list")
    for item in brands:
        if not isinstance(item, dict):
            raise YuntuReportError("topMaterialCombination.brandConclusions items must be objects")
        if not isinstance(item.get("brand"), str) or not item["brand"].strip():
            raise YuntuReportError("topMaterialCombination.brandConclusions items must include brand")
        if item.get("classificationSource") != "title_rule":
            raise YuntuReportError("topMaterialCombination.brandConclusions classificationSource must be title_rule")
        for summary_field in BRAND_SUMMARY_FIELDS.values():
            _validate_summary(
                item.get(summary_field),
                f"topMaterialCombination.brandConclusions {summary_field}",
            )
        _validate_evidence_and_material_ids(
            item, "topMaterialCombination.brandConclusions items"
        )
    comparison = value.get("brandComparisonConclusion")
    if not isinstance(comparison, dict):
        raise YuntuReportError(
            "topMaterialCombination.brandComparisonConclusion must be an object"
        )
    _validate_summary(
        comparison.get("summary"),
        "topMaterialCombination.brandComparisonConclusion summary",
    )
    _validate_evidence_and_material_ids(
        comparison, "topMaterialCombination.brandComparisonConclusion"
    )
    compared_brands = {
        entry.get("brand")
        for entry in comparison["evidence"]
        if isinstance(entry, dict)
        and isinstance(entry.get("brand"), str)
        and isinstance(entry.get("metric"), str)
        and entry["metric"].strip()
    }
    required_brands = {item["brand"] for item in brands}
    if not required_brands.issubset(compared_brands):
        raise YuntuReportError(
            "topMaterialCombination.brandComparisonConclusion evidence must include each brand and metric"
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
                    text = str(item.get("summary") or item.get("body") or "")
            else:
                text = str(item)
            lines.append(f"- {text}")
        return "\n".join(lines)
    return json.dumps(value, ensure_ascii=False, indent=2)


def _render_markdown(analysis, audience_dashboard=None):
    lines = ["# 云图行业内容榜单分析报告", ""]
    combination = analysis["topMaterialCombination"]
    overall = {
        item["dimension"]: item for item in combination["overallConclusions"]
    }
    lines.extend(["## 01｜TOP 素材组合结论", "", "### 品牌筛选条件下 TOP30 整体分析", ""])
    for dimension in TOP_MATERIAL_DIMENSIONS:
        summary = overall[dimension]["summary"]
        if dimension == "people":
            summary = f"{summary} {PEOPLE_TAG_OVERLAP_NOTICE}"
        lines.extend([
            f"{TOP_MATERIAL_LABELS[dimension]}，{summary}",
            "",
        ])
    lines.extend(["---", "", "### 各品牌 TOP30 对比分析", ""])
    brand_conclusions = {item["brand"]: item for item in combination["brandConclusions"]}
    ordered_brands = [
        brand_conclusions[brand]
        for brand in TOP_MATERIAL_BRAND_ORDER
        if brand in brand_conclusions
    ]
    ordered_brands.extend(
        item
        for item in combination["brandConclusions"]
        if item not in ordered_brands
    )
    for index, item in enumerate(ordered_brands):
        if index:
            lines.extend(["---", ""])
        lines.extend([
            f"### {item['brand']}",
            "",
        ])
        for dimension in TOP_MATERIAL_DIMENSIONS:
            lines.extend([
                f"{TOP_MATERIAL_LABELS[dimension]}，{item[BRAND_SUMMARY_FIELDS[dimension]]}",
                "",
            ])
    lines.extend([
        "---",
        "",
        "### 品牌间差异总结",
        "",
        combination["brandComparisonConclusion"]["summary"],
        "",
    ])
    if isinstance(audience_dashboard, dict):
        sample = audience_dashboard.get("sample", {})
        dimensions = audience_dashboard.get("dimensions", {})
        record_count = sample.get("recordCount", 0)
        lines.extend([
            "## 02｜人群洞察",
            "",
            f"候选池 TOP1000 素材标签汇总（实际 {record_count} 条）",
            "",
        ])
        for key, label in AUDIENCE_DIMENSION_LABELS.items():
            dimension = dimensions.get(key, {}) if isinstance(dimensions, dict) else {}
            notice = "图表按素材标签出现次数归一化展示，用于观察标签结构，不代表真实人群分布。"
            lines.extend([f"### {label}", "", notice, ""])
            buckets = dimension.get("buckets", [])
            if not buckets:
                lines.extend(["暂无可视化数据。", ""])
            for bucket in buckets:
                lines.append(
                    f"- {bucket['label']}：{bucket['materialCount']} 条素材，覆盖率 {bucket['materialShare'] * 100:.1f}%，归一化占比 {bucket['chartShare'] * 100:.1f}%"
                )
            unlabeled_count = dimension.get("unlabeledRecordCount", 0)
            if unlabeled_count:
                lines.append(f"- 未识别到该维度标签：{unlabeled_count} 条素材（不计入饼图归一化分母）")
            lines.append("")
    return "\n".join(lines)


def _material_frames(fact_pack):
    frames = {}
    for fact in fact_pack.get("materialFacts", []) if isinstance(fact_pack, dict) else []:
        material_id = fact.get("material_id")
        if isinstance(material_id, str):
            frames[material_id] = fact.get("highlightFrames", [])
    return frames


METRIC_LABELS = {
    "show_cnt": "曝光量",
    "ctr": "CTR",
    "cvr": "CVR",
    "play_3s_rate": "3 秒播放率",
    "play_5s_rate": "5 秒播放率",
    "play_over_rate": "完播率",
    "play_duration_avg": "平均播放时长",
    "interact_rate": "互动率",
    "pvr": "PVR",
}


def _format_metric(value, key):
    if not isinstance(value, (int, float)):
        return "-"
    if key == "show_cnt":
        return f"{value / 10000:.1f} 万" if value >= 10000 else f"{value:,.0f}"
    if key == "play_duration_avg":
        return f"{value:.1f}s"
    return f"{value * 100:.2f}%"


def _generic_text(value):
    return str(value or "").replace("小仙炖", "目标品牌")


def _render_html(analysis, material_frames, fact_pack):
    def esc(value):
        return html.escape(str(value))

    def image_src(frame):
        path = str(frame.get("relative_path", ""))
        return path if path.startswith("../") else "../" + path

    facts = {
        str(fact.get("material_id")): fact
        for fact in fact_pack.get("materialFacts", [])
        if isinstance(fact, dict) and fact.get("material_id")
    }
    selected = fact_pack.get("selectedMaterials", [])
    if not selected:
        selected = [{"material_id": material_id, "rank": "-"} for material_id in facts]
    candidate_metrics = (fact_pack.get("candidatePool") or {}).get("metrics", {})
    summary_metrics = fact_pack.get("summaryMetrics", {})
    tag_insights = (fact_pack.get("tagInsights") or {}).get("materialTags", {})
    trend_summary = (fact_pack.get("trendSummary") or {}).get("byTrendName", {})

    def source_label(text):
        return f'<span class="source-label">来源：{esc(text)}</span>'

    def insight_cards(items):
        return "".join(
            f'<article class="insight-row"><p>{esc(_generic_text(item.get("summary", "")))}</p>'
            "</article>"
            for item in items
        )

    def top_material_combination_cards(value):
        overall_by_dimension = {
            item["dimension"]: item for item in value["overallConclusions"]
        }
        overall = "".join(
            '<p><strong>'
            + TOP_MATERIAL_LABELS[dimension]
            + "，</strong>"
            + esc(_generic_text(overall_by_dimension[dimension]["summary"]))
            + (" " + esc(PEOPLE_TAG_OVERLAP_NOTICE) if dimension == "people" else "")
            + "</p>"
            for dimension in TOP_MATERIAL_DIMENSIONS
        )
        brand_conclusions = {item["brand"]: item for item in value["brandConclusions"]}
        ordered_brands = [
            brand_conclusions[brand]
            for brand in TOP_MATERIAL_BRAND_ORDER
            if brand in brand_conclusions
        ]
        ordered_brands.extend(
            item for item in value["brandConclusions"] if item not in ordered_brands
        )
        default_brand = next(
            (item["brand"] for item in ordered_brands if item["brand"] == "五个女博士"),
            ordered_brands[0]["brand"],
        )
        tabs = "".join(
            '<button class="brand-tab" type="button" role="tab" '
            + f'id="brand-tab-{index}" aria-controls="brand-panel-{index}" '
            + f'aria-selected="{str(item["brand"] == default_brand).lower()}" '
            + f'tabindex="{0 if item["brand"] == default_brand else -1}" '
            + f'data-brand-tab="{esc(item["brand"])}" data-brand-target="brand-panel-{index}">'
            + esc(item["brand"])
            + "</button>"
            for index, item in enumerate(ordered_brands)
        )
        panels = "".join(
            '<article class="brand-panel" role="tabpanel" '
            + f'id="brand-panel-{index}" aria-labelledby="brand-tab-{index}" '
            + ("hidden " if item["brand"] != default_brand else "")
            + f'aria-label="{esc(item["brand"])}，标题匹配归属" '
            + f'data-brand-panel="{esc(item["brand"])}">'
            + "".join(
                '<p><strong>'
                + TOP_MATERIAL_LABELS[dimension]
                + "，</strong>"
                + esc(_generic_text(item[BRAND_SUMMARY_FIELDS[dimension]]))
                + "</p>"
                for dimension in TOP_MATERIAL_DIMENSIONS
            )
            + "</article>"
            for index, item in enumerate(ordered_brands)
        )
        return (
            '<div class="top-material-overall yuntu-content-card"><h3>品牌筛选条件下 TOP30 整体分析</h3>'
            + overall
            + "</div>"
            + '<div class="top-material-brands yuntu-content-card"><h3>各品牌 TOP30 对比分析</h3>'
            + '<div class="brand-tabs" role="tablist" aria-label="各品牌 TOP30 分析">'
            + tabs
            + "</div><div class=\"brand-panels\">"
            + panels
            + "</div></div>"
            + '<article class="brand-difference yuntu-content-card"><h3>品牌间差异总结</h3><p>'
            + esc(_generic_text(value["brandComparisonConclusion"]["summary"]))
            + "</p></article>"
        )

    def audience_dimension_chart(key, dimension):
        label = AUDIENCE_DIMENSION_LABELS[key]
        record_count = dimension.get("recordCount", 0)
        buckets = dimension.get("buckets", [])
        unlabeled_count = dimension.get("unlabeledRecordCount", 0)
        if not buckets:
            unlabeled_note = (
                f'<p class="data-note">未识别到该维度标签：{esc(unlabeled_count)} 条素材。</p>'
                if unlabeled_count else ""
            )
            return (
                f'<article class="chart-card audience-chart"><h3>{esc(label)}分布</h3>'
                + '<p class="data-note">暂无可视化数据。</p>' + unlabeled_note + '</article>'
            )
        if dimension.get("labelMode") == "normalized_tag_share" and key == "crowd":
            max_share = max(bucket["chartShare"] for bucket in buckets)
            axis_max = max(10, math.ceil(max_share * 100 / 10) * 10)
            axis_ticks = (axis_max, axis_max * 0.75, axis_max * 0.5, axis_max * 0.25, 0)
            colors = ("#9b6a37", "#d79a4b", "#b77d54", "#c7a36a", "#a14f38", "#958268", "#ab8068", "#6d5d4d")
            columns = []
            for index, bucket in enumerate(buckets):
                material_share = bucket["materialShare"] * 100
                chart_share = bucket["chartShare"] * 100
                tooltip = (
                    '<div class="chart-tooltip" role="tooltip"><b>' + esc(bucket["label"]) + '</b>'
                    + '<span>素材数 ' + esc(bucket["materialCount"]) + ' 条</span>'
                    + '<span>覆盖率 ' + f"{material_share:.1f}%" + '</span>'
                    + '<span>归一化占比 ' + f"{chart_share:.1f}%" + '</span></div>'
                )
                columns.append(
                    '<div class="audience-column-item" role="img" tabindex="0" aria-label="'
                    + esc(bucket["label"]) + '，素材数 ' + esc(bucket["materialCount"])
                    + ' 条，覆盖率 ' + f"{material_share:.1f}%" + '，归一化占比 ' + f"{chart_share:.1f}%"
                    + '"><div class="audience-column-bar" style="height:'
                    + f"{max(2, chart_share / axis_max * 100):.2f}%" + ';background:'
                    + colors[index % len(colors)] + '"></div><span class="audience-column-label">'
                    + esc(bucket["label"]) + '</span>' + tooltip + '</div>'
                )
            return (
                '<article class="chart-card audience-chart audience-chart-crowd"><h3>' + esc(label)
                + '分布</h3><div class="audience-column-chart" data-audience-column role="group" aria-label="'
                + esc(label) + '标签出现次数归一化柱状图，素材样本共 ' + esc(record_count) + ' 条">'
                + '<div class="audience-column-y-axis">'
                + ''.join('<span>' + f"{value:.0f}%" + '</span>' for value in axis_ticks)
                + '</div><div class="audience-column-plot" style="grid-template-columns:repeat('
                + esc(len(columns)) + ',minmax(0,1fr))">' + ''.join(columns) + '</div></div></article>'
            )
        if dimension.get("labelMode") == "normalized_tag_share":
            colors = ("#9b6a37", "#d79a4b", "#6f7f5f", "#a14f38", "#6d5d4d", "#c7a36a", "#7d8f9a", "#b77d54", "#958268", "#ab8068", "#8d9a7b")
            items = [
                (bucket["label"], bucket["materialCount"], bucket["materialShare"], bucket["chartShare"])
                for bucket in buckets
            ]
            cursor = 0.0
            stops, slices, legend = [], [], []
            for index, (item_label, count, material_share, chart_share) in enumerate(items):
                color = colors[index % len(colors)]
                next_cursor = cursor + chart_share * 100
                stops.append(f"{color} {cursor:.4f}% {next_cursor:.4f}%")
                slices.append({"label": item_label, "count": count, "materialShare": round(material_share * 100, 1), "share": round(chart_share * 100, 1), "start": cursor * 3.6, "end": next_cursor * 3.6})
                legend.append(
                    '<li class="legend-item" title="' + esc(item_label) + '：' + esc(count) + ' 条素材，覆盖率 ' + f"{material_share * 100:.1f}%" + '，归一化占比 ' + f"{chart_share * 100:.1f}%" + '">'
                    + '<span class="legend-label"><i class="legend-swatch" style="background:' + color + '"></i>'
                    + esc(item_label) + '</span><span class="legend-count">' + esc(count) + ' 条</span><span class="legend-share">' + f"{chart_share * 100:.1f}%" + '</span></li>'
                )
                cursor = next_cursor
            return (
                f'<article class="chart-card audience-chart audience-chart-{esc(key)}"><h3>{esc(label)}分布</h3><div class="audience-pie-layout">'
                + f'<div class="pie-chart" data-audience-pie role="img" tabindex="0" aria-label="{esc(label)}标签出现次数归一化饼图，素材样本共 {esc(record_count)} 条" data-pie-slices="{esc(json.dumps(slices, ensure_ascii=False))}" style="background:conic-gradient({", ".join(stops)})">'
                + '<div class="chart-tooltip" role="tooltip"></div></div>'
                + '<ul class="pie-legend">' + "".join(legend) + '</ul></div></article>'
            )
        return f'<article class="chart-card audience-chart"><h3>{esc(label)}分布</h3><p class="data-note">暂无可视化数据。</p></article>'

    def audience_dashboard_cards(value):
        if not isinstance(value, dict):
            return (
                '<section class="section" id="audience-insights"><header class="section-header">'
                '<h2>02｜人群洞察</h2></header><p class="data-note">暂无人群汇总数据。</p></section>'
            )
        sample = value.get("sample", {})
        dimensions = value.get("dimensions", {})
        if not isinstance(dimensions, dict):
            return ""
        charts = "".join(
            audience_dimension_chart(key, dimension)
            for key, dimension in dimensions.items()
            if key in AUDIENCE_DIMENSION_LABELS and isinstance(dimension, dict)
        )
        if not charts:
            charts = '<p class="data-note">暂无人群汇总数据。</p>'
        return (
            '<section class="section" id="audience-insights"><header class="section-header">'
            '<h2>02｜人群洞察</h2></header><div class="audience-chart-grid">'
            + charts + '</div></section>'
        )

    def pie_chart(items, chart_id):
        colors = ("#d79a4b", "#b56e38", "#6d8c72", "#9b6a92", "#59778b", "#bd8a62", "#958268")
        total = sum(value for _, value in items) or 1
        stops = []
        slices = []
        cursor = 0.0
        legend = []
        for index, (label, value) in enumerate(items):
            share = value / total * 100
            color = colors[index % len(colors)]
            stops.append(f"{color} {cursor:.2f}% {cursor + share:.2f}%")
            slices.append(
                {
                    "label": label,
                    "value": value,
                    "share": round(share, 1),
                    "start": round(cursor * 3.6, 3),
                    "end": round((cursor + share) * 3.6, 3),
                }
            )
            cursor += share
            legend.append(
                '<li style="display:grid;grid-template-columns:11px minmax(0,1fr) auto auto;gap:9px;align-items:center;padding:5px 0;border-bottom:1px solid rgba(223,207,189,.7);font-size:.875rem">'
                f'<i style="background:{color};width:10px;height:10px;border-radius:2px"></i><span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{esc(label)}</span><b>{value}</b><small style="color:#705c50;min-width:40px;text-align:right">{share:.1f}%</small></li>'
            )
        return (
            '<div class="pie-layout" style="display:grid;grid-template-columns:300px minmax(0,400px);gap:32px;align-items:center;min-height:300px">'
            '<div style="display:grid;gap:8px;justify-items:center">'
            f'<div class="pie-chart" id="{chart_id}" aria-label="共 {total} 条标签记录" data-pie-slices="{esc(json.dumps(slices, ensure_ascii=False))}" style="position:relative;background:conic-gradient({", ".join(stops)});width:300px;height:300px;border-radius:50%;box-shadow:0 0 0 1px rgba(82,45,24,.12);flex:0 0 300px;cursor:default">'
            '<div class="pie-tooltip" role="tooltip" hidden style="position:absolute;z-index:2;left:50%;top:-72px;transform:translateX(-50%);min-width:150px;padding:10px 12px;background:#fffdf8;color:#2a170f;border:1px solid #dfcfbd;border-radius:6px;box-shadow:0 10px 24px rgba(42,23,15,.14);font-size:.78rem;line-height:1.45;pointer-events:none"></div></div>'
            f'<small style="color:#705c50;font-size:.75rem">共 {total} 条标签记录</small></div>'
            f'<ul class="pie-legend" style="display:grid;gap:4px;padding:0;margin:0;list-style:none;min-width:0;max-width:400px">{"".join(legend)}</ul></div>'
        )

    baseline = "".join(
        f'<div class="baseline"><span>{esc(METRIC_LABELS.get(key, key))}</span><b>{esc(_format_metric(value.get("median"), key))}</b><small>候选池中位数</small></div>'
        for key, value in candidate_metrics.items()
        if key in ("show_cnt", "ctr", "cvr", "play_3s_rate", "interact_rate", "play_duration_avg")
    )
    performance_rows = []
    for item in selected:
        material_id = str(item.get("material_id"))
        fact = facts.get(material_id, {})
        metrics = fact.get("metrics", {})
        comparisons = fact.get("metricComparison", {})
        cells = "".join(
            f'<td data-sort="{key}" data-value="{metrics.get(key, 0)}"><b>{esc(_format_metric(metrics.get(key), key))}</b><small>P{esc(round(comparisons.get(key, {}).get("percentile", 0) * 100, 1))}</small></td>'
            for key in ("show_cnt", "ctr", "play_3s_rate", "interact_rate", "cvr")
        )
        performance_rows.append(
            f'<tr data-title="{esc(fact.get("title", "").lower())}"><td><span class="rank">#{esc(item.get("rank", "-"))}</span></td>'
            f'<td class="material-title"><strong>{esc(fact.get("title", material_id))}</strong><span>{esc(material_id)}</span></td>{cells}</tr>'
        )

    material_tag_items = [
        (tag.replace("_", " · "), stats.get("count", 0))
        for tag, stats in sorted(tag_insights.items(), key=lambda item: -item[1].get("count", 0))
        if not tag.startswith("人群_")
    ]
    people_tag_items = [
        (tag, stats.get("count", 0))
        for tag, stats in sorted((fact_pack.get("tagInsights") or {}).get("peopleTags", {}).items(), key=lambda item: -item[1].get("count", 0))
    ]

    def top_with_other(items, limit=6):
        top = items[:limit]
        other = sum(value for _, value in items[limit:])
        return top + ([('其他', other)] if other else [])

    material_tag_chart = pie_chart(top_with_other(material_tag_items), "material-tag-chart")
    people_tag_chart = pie_chart(top_with_other(people_tag_items), "people-tag-chart")

    trend_items = "".join(
        f'<div class="trend-summary"><span>{esc(name)}</span><b>{esc(data.get("highPointCount", 0))}</b><small>高点</small><b>{esc(data.get("lossPointCount", 0))}</b><small>流失点</small></div>'
        for name, data in trend_summary.items()
    )
    diagnosis_items = "".join(
        f'<details class="diagnosis" id="material-{esc(item.get("material_id"))}"><summary><span class="rank">#{esc(facts.get(str(item.get("material_id")), {}).get("rank", "-"))}</span><strong>{esc(facts.get(str(item.get("material_id")), {}).get("title", item.get("material_id")))}</strong><span>展开秒级诊断</span></summary><p>{esc(_generic_text(item.get("summary", "")))}</p></details>'
        for item in analysis.get("materialDiagnoses", [])
    )
    frame_buttons = []
    for item in selected:
        material_id = str(item.get("material_id"))
        fact = facts.get(material_id, {})
        for frame in material_frames.get(material_id, []):
            if not frame.get("available") or not str(frame.get("relative_path", "")).endswith(".jpg"):
                continue
            label = "封面" if frame.get("is_cover") else f'{frame.get("second", 0)}s'
            reason = "/".join(str(value.get("trend_name") or value.get("type") or "") for value in frame.get("reasons", []) if isinstance(value, dict))
            frame_buttons.append(
                f'<button class="frame-button" type="button" data-material="{esc(material_id)}" data-frame="{html.escape(image_src(frame), quote=True)}" data-caption="{esc(f"#{item.get("rank", "-")} · {label} · {reason or "高光帧"}")}" aria-label="查看 {esc(material_id)} {esc(label)} 高光帧"><img loading="lazy" src="{html.escape(image_src(frame), quote=True)}" alt="{esc(fact.get("title", material_id))} {esc(label)} 高光帧"><span>#{esc(item.get("rank", "-"))} · {esc(label)}</span></button>'
            )
    frame_options = "".join(f'<option value="{esc(str(item.get("material_id")))}">#{esc(item.get("rank", "-"))} {esc(facts.get(str(item.get("material_id")), {}).get("title", item.get("material_id"))[:18])}</option>' for item in selected)

    landscape = insight_cards(analysis.get("rankingOverview", []))
    top_material_combination = top_material_combination_cards(
        analysis["topMaterialCombination"]
    )
    audience_insights = audience_dashboard_cards(fact_pack.get("audienceDashboard"))
    performance = insight_cards(analysis.get("materialComparison", []))
    opportunities = insight_cards(analysis.get("xiaoxianDunOpportunityMap", []))
    competitor_patterns = analysis.get("competitorPatterns", [])
    competitor_cards = []
    for brand in ("五个女博士", "万益蓝", "燕之屋"):
        item = next((entry for entry in competitor_patterns if brand in str(entry.get("summary", ""))), None)
        if item:
            competitor_cards.append(
                f'<article class="competitor-card"><h3>{esc(brand)}</h3><p>{esc(_generic_text(item.get("summary", "")))}</p></article>'
            )
    if not competitor_cards:
        competitor_cards.append('<p class="data-note">当前数据未识别出可归属到指定竞品的结论。</p>')
    competitor = "".join(competitor_cards)
    experiments = "".join(
        f'<article class="experiment"><span>{esc(item.get("priority", ""))}</span><div><h3>{esc(_generic_text(item.get("hypothesis", "")))}</h3><dl><div><dt>创意变量</dt><dd>{esc(_generic_text(item.get("creative_variable", "")))}</dd></div><div><dt>目标人群</dt><dd>{esc(_generic_text(item.get("target_audience", "")))}</dd></div><div><dt>成功指标</dt><dd>{esc(_generic_text(item.get("success_metric", "")))}</dd></div><div><dt>对照组</dt><dd>{esc(_generic_text(item.get("control", "")))}</dd></div></dl><details><summary>查看复盘动作</summary><p>{esc(_generic_text(item.get("review_action", "")))}</p></details></div></article>'
        for item in analysis.get("experimentMatrix", [])
    )

    style = """
:root{--bg:#170d09;--paper:#fff8ec;--surface:#fffdf8;--ink:#2a170f;--muted:#705c50;--accent:#d79a4b;--accent-dark:#8e5528;--line:#dfcfbd;--line-dark:#4a2a1b;--positive:#406955;--focus:#f0bc64}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Segoe UI",sans-serif;font-size:16px;line-height:1.55}button,select,input{font:inherit}button,select{min-height:44px}.skip-link{position:fixed;left:12px;top:-60px;background:var(--paper);color:var(--ink);padding:10px;z-index:5}.skip-link:focus{top:12px}.page{width:min(1240px,calc(100% - 32px));margin:auto;padding:28px 0 72px}.report-cover{color:#fff;border-bottom:1px solid rgba(255,255,255,.24);padding:8px 0 28px}.report-cover p{max-width:68ch;color:#ead9c9;margin:0}.report-cover h1{font-size:2.6rem;line-height:1.1;margin:10px 0 12px;text-wrap:balance}.report-cover .cover-meta{display:flex;gap:8px;flex-wrap:wrap;margin-top:18px}.cover-meta span,.source-label{font-size:.75rem;font-weight:700}.cover-meta span{color:#f9d79b;border:1px solid rgba(249,215,155,.38);padding:4px 8px;border-radius:4px}.report-shell{display:grid;grid-template-columns:184px minmax(0,900px);gap:26px;align-items:start;margin-top:24px}.report-nav{position:sticky;top:18px;display:grid;gap:4px;padding:10px 0}.report-nav a{color:#dfc7ae;text-decoration:none;border-left:1px solid rgba(223,199,174,.35);padding:8px 10px;font-size:.875rem}.report-nav a:hover,.report-nav a:focus-visible,.report-nav a.active{color:#fff;background:#2a170f;border-left-color:var(--accent)}.report-nav small{color:#ac8970;padding:8px 10px}.report-content{min-width:0}.section{scroll-margin-top:18px;background:var(--paper);border:1px solid var(--line);border-radius:10px;padding:24px;margin-bottom:18px}.section-header{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;border-bottom:1px solid var(--line);padding-bottom:14px;margin-bottom:18px}.section-header h2{font-size:1.5rem;line-height:1.2;margin:0;text-wrap:balance}.section-header p{color:var(--muted);font-size:.875rem;margin:6px 0 0}.source-label{display:inline-block;color:var(--accent-dark);background:#f7e6cb;padding:4px 7px;border-radius:4px;white-space:nowrap}.insight-stack{display:grid;gap:0}.insight-row{padding:16px 0;border-bottom:1px solid var(--line)}.insight-row:last-child{border:0;padding-bottom:0}.insight-row p{margin:0;max-width:72ch}.material-references{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}.material-reference{color:var(--accent-dark);font-size:.8125rem;font-weight:700;text-decoration:none;border-bottom:1px solid currentColor}.evidence-details,.diagnosis details,.experiment details{margin-top:10px}.evidence-details summary,.diagnosis summary,.experiment summary{cursor:pointer;color:var(--accent-dark);font-weight:700}.evidence-details ul{padding-left:18px;color:var(--muted);font-size:.875rem}.baseline-strip{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-bottom:18px}.baseline{background:#f7ebd9;padding:10px;border-radius:6px}.baseline span,.baseline small{display:block;color:var(--muted);font-size:.75rem}.baseline b{display:block;font-size:1.05rem;font-variant-numeric:tabular-nums;margin:2px 0}.toolbar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:12px}.toolbar label{font-size:.8125rem;font-weight:700;color:var(--muted)}.toolbar select,.toolbar input{border:1px solid #ba9c7d;background:var(--surface);color:var(--ink);border-radius:5px;padding:6px 8px}.toolbar input{min-width:220px}.toolbar button{border:1px solid var(--accent-dark);background:transparent;color:var(--accent-dark);padding:6px 10px;border-radius:5px;cursor:pointer}.data-table{width:100%;border-collapse:collapse;font-size:.8125rem;overflow:hidden}.table-wrap{overflow:auto;border:1px solid var(--line);border-radius:6px}.data-table th{background:#f1dfc8;color:#5e3820;text-align:right;padding:9px 8px;white-space:nowrap}.data-table th:nth-child(2),.data-table td:nth-child(2){text-align:left}.data-table td{border-top:1px solid var(--line);padding:9px 8px;text-align:right;font-variant-numeric:tabular-nums}.data-table td small,.material-title span{display:block;color:var(--muted);font-size:.72rem;font-weight:400}.material-title{min-width:240px;max-width:360px}.rank{color:var(--accent-dark);font-weight:800}.tag-table td:first-child{text-align:left}.selection-bar{display:block;width:84px;height:6px;background:#ecd9c2;border-radius:99px;overflow:hidden}.selection-bar i{display:block;height:100%;background:var(--accent)}.trend-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px;margin-bottom:18px}.trend-summary{border-bottom:2px solid var(--accent);padding:8px 0}.trend-summary span,.trend-summary small{display:block;color:var(--muted);font-size:.72rem}.trend-summary b{font-size:1.125rem;font-variant-numeric:tabular-nums;margin-right:4px}.diagnosis{border-top:1px solid var(--line);padding:12px 0}.diagnosis summary{display:grid;grid-template-columns:52px 1fr auto;gap:10px;align-items:start;color:var(--ink)}.diagnosis summary span:last-child{color:var(--accent-dark);font-size:.8125rem}.diagnosis p{margin:12px 0 0;color:#483025}.frame-library{margin-top:26px;border-top:1px solid var(--line);padding-top:18px}.frame-library-head{display:flex;align-items:center;justify-content:space-between;gap:12px}.frame-library h3{margin:0;font-size:1.125rem}.frame-library select{border:1px solid #ba9c7d;background:var(--surface);padding:6px 8px;border-radius:5px}.highlight-gallery{display:grid;grid-template-columns:repeat(auto-fill,minmax(88px,1fr));gap:8px;margin-top:14px}.frame-button{border:1px solid var(--line);background:var(--surface);padding:4px;border-radius:6px;color:var(--muted);cursor:pointer;text-align:left;transition:border-color .18s ease,transform .18s ease}.frame-button img{display:block;width:100%;aspect-ratio:9/16;object-fit:cover;border-radius:3px}.frame-button span{display:block;font-size:.7rem;padding:4px 2px 1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.frame-button:hover{border-color:var(--accent-dark);transform:translateY(-1px)}.experiment{display:grid;grid-template-columns:48px 1fr;gap:12px;padding:16px 0;border-top:1px solid var(--line)}.experiment:first-of-type{border-top:0;padding-top:0}.experiment>span{color:var(--accent-dark);font-weight:800;font-size:.875rem}.experiment h3{font-size:1rem;line-height:1.45;margin:0}.experiment dl{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin:14px 0 0}.experiment dl div{border-top:1px solid var(--line);padding-top:7px}.experiment dt{color:var(--muted);font-size:.72rem}.experiment dd{margin:3px 0 0;font-size:.875rem}.data-note{color:var(--muted);font-size:.8125rem;margin:10px 0 0}.data-note strong{color:var(--ink)}dialog{border:0;padding:0;max-width:min(720px,92vw);background:transparent}dialog::backdrop{background:rgba(13,7,4,.88)}.lightbox{position:relative;background:#fff;padding:10px;border-radius:8px}.lightbox img{display:block;max-width:min(680px,88vw);max-height:82vh}.lightbox button{position:absolute;right:8px;top:8px;border:0;background:var(--ink);color:#fff;border-radius:5px;padding:6px 9px;cursor:pointer}.lightbox p{margin:7px 2px 0;font-size:.8125rem;color:var(--muted)}button:focus-visible,a:focus-visible,select:focus-visible,input:focus-visible,summary:focus-visible{outline:3px solid var(--focus);outline-offset:2px}@media(max-width:900px){.report-shell{grid-template-columns:1fr}.report-nav{position:sticky;top:0;z-index:2;background:var(--bg);grid-auto-flow:column;grid-auto-columns:max-content;overflow:auto;padding:8px 0}.report-nav small{display:none}.report-nav a{border-left:0;border-bottom:1px solid rgba(223,199,174,.35);white-space:nowrap}.report-nav a.active{border-bottom-color:var(--accent)}.section{padding:18px}.baseline-strip{grid-template-columns:repeat(2,minmax(0,1fr))}.trend-grid{grid-template-columns:repeat(3,minmax(0,1fr)}}@media(max-width:560px){.page{width:min(100% - 20px,1240px);padding-top:16px}.report-cover h1{font-size:2rem}.section-header{display:block}.source-label{margin-top:10px}.baseline-strip{grid-template-columns:1fr 1fr}.toolbar input{min-width:0;width:100%}.trend-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.diagnosis summary{grid-template-columns:42px 1fr}.diagnosis summary span:last-child{grid-column:2}.experiment dl{grid-template-columns:1fr}.highlight-gallery{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}.frame-button{transition:none}.frame-button:hover{transform:none}}
.performance-insights{margin-top:24px;border-top:1px solid var(--line);padding-top:18px}.performance-insights h3{margin:0;font-size:1.125rem}.performance-insights .insight-stack{margin-top:4px}.opportunity-charts{display:grid;gap:26px}.opportunity-charts article{min-width:0}.opportunity-charts h3{font-size:1.05rem;margin:0}.opportunity-charts p{color:var(--muted);font-size:.8125rem;margin:4px 0 12px}.chart-layout{min-width:0}.pie-layout{display:grid;grid-template-columns:180px minmax(0,1fr);gap:24px;align-items:center;min-height:180px}.pie-chart{border-radius:50%;display:grid;place-items:center;box-shadow:0 0 0 1px rgba(82,45,24,.12)}.pie-chart>span{display:grid;place-items:center;width:78px;height:78px;border-radius:50%;background:var(--paper);font-weight:800;font-variant-numeric:tabular-nums;text-align:center}.pie-chart small{color:var(--muted);font-size:.65rem;font-weight:400}.pie-legend{display:grid;gap:6px;padding:0;margin:0;list-style:none}.pie-legend li{display:grid;grid-template-columns:10px minmax(0,1fr) auto auto;gap:8px;align-items:center;font-size:.78rem;padding:3px 0;border-bottom:1px solid rgba(223,207,189,.7)}.pie-legend li:last-child{border-bottom:0}.pie-legend i{width:10px;height:10px;border-radius:2px}.pie-legend span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.pie-legend b{font-variant-numeric:tabular-nums}.pie-legend small{color:var(--muted);min-width:40px;text-align:right}.competitor-grid{display:grid;gap:0}.competitor-card{padding:16px 0;border-top:1px solid var(--line)}.competitor-card:first-child{padding-top:0;border-top:0}.competitor-card h3{font-size:1rem;margin:0 0 6px;color:var(--accent-dark)}.competitor-card p{margin:0;max-width:76ch}@media(max-width:700px){.pie-layout{grid-template-columns:140px minmax(0,1fr);gap:14px;min-height:140px}.pie-chart{width:140px!important;height:140px!important;flex-basis:140px!important}.pie-chart>span{width:64px;height:64px}.pie-legend li{font-size:.72rem;gap:6px}}@media(max-width:480px){.pie-layout{grid-template-columns:1fr}.pie-chart{justify-self:center}.pie-legend{width:100%}}
.top-material-overall h3,.top-material-brands h3,.brand-difference h3{font-size:1.08rem;margin:0 0 12px}.top-material-overall>p,.brand-panel>p,.brand-difference>p{margin:10px 0;max-width:76ch}.section-divider{height:0;border:0;border-top:1px solid var(--line);margin:30px 0}.brand-tabs{display:flex;gap:4px;overflow-x:auto;border-bottom:1px solid var(--line);padding:0 0 10px}.brand-tab{flex:0 0 auto;min-height:38px;border:0;border-bottom:2px solid transparent;border-radius:4px;background:transparent;color:var(--muted);padding:8px 12px;cursor:pointer;white-space:nowrap}.brand-tab:hover{color:var(--accent-dark);background:#f8ecd9}.brand-tab[aria-selected="true"]{border-bottom-color:var(--accent-dark);background:#f4e4ca;color:#5e3820;font-weight:700}.brand-panels{margin-top:16px;padding:18px 20px;background:#fbf0df;border-left:2px solid var(--accent)}.brand-panel[hidden]{display:none!important}.brand-panel{padding:0}.brand-panel-header{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;border-bottom:1px solid rgba(142,85,40,.2);padding-bottom:10px;margin-bottom:12px}.brand-current-brand{margin:0;color:#5e3820;font-weight:700}.brand-source{color:var(--muted);font-size:.75rem;margin:0!important}.brand-difference p{margin-bottom:0}@media(max-width:560px){.brand-tabs{margin-right:-2px}.brand-tab{padding-inline:10px}.brand-panels{padding:16px}}
"""
    style = """
:root{--bg:#170d09;--paper:#fff8ec;--ink:#2a170f;--muted:#705c50;--accent:#d79a4b;--accent-dark:#8e5528;--line:#dfcfbd;--focus:#e8b85f}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Segoe UI",sans-serif;font-size:16px;line-height:1.65}button{font:inherit}.skip-link{position:fixed;left:12px;top:-60px;background:var(--paper);color:var(--ink);padding:10px;z-index:5}.skip-link:focus{top:12px}.page{width:min(1180px,calc(100% - 32px));margin:auto;padding:32px 0 72px}.report-cover{color:#fff;border-bottom:1px solid rgba(249,215,155,.32);padding:8px 0 28px}.report-cover p{max-width:68ch;color:#ead9c9;margin:0}.report-cover h1{font-size:2.5rem;line-height:1.15;margin:10px 0 12px;text-wrap:balance}.report-shell{display:grid;grid-template-columns:168px minmax(0,1fr);gap:28px;align-items:start;margin-top:24px}.report-nav{position:sticky;top:18px;display:grid;gap:5px;padding:10px 0}.report-nav small{color:#ac8970;padding:4px 10px;font-size:.75rem;font-weight:700}.report-nav a{border-left:1px solid rgba(223,199,174,.35);color:#dfc7ae;padding:8px 10px;font-size:.875rem;text-decoration:none}.report-nav a:hover,.report-nav a:focus-visible,.report-nav a[aria-current="location"]{border-left-color:var(--accent);background:#2a170f;color:#fff}.section{scroll-margin-top:18px;background:var(--paper);border:1px solid var(--line);border-radius:8px;padding:28px}.section-header{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;border-bottom:1px solid var(--line);padding-bottom:16px;margin-bottom:24px}.section-header h2{font-size:1.55rem;line-height:1.2;margin:0;text-wrap:balance}.section-header p{color:var(--muted);font-size:.875rem;margin:7px 0 0}.source-label{display:inline-block;color:var(--accent-dark);background:#f7e6cb;padding:4px 7px;border-radius:4px;font-size:.75rem;font-weight:700;white-space:nowrap}.top-material-overall h3,.top-material-brands h3,.brand-difference h3{font-size:1.08rem;margin:0 0 12px}.top-material-overall>p,.brand-panel>p,.brand-difference>p{margin:10px 0;max-width:76ch}.section-divider{height:0;border:0;border-top:1px solid var(--line);margin:32px 0}.brand-tabs{display:flex;gap:0;overflow-x:auto;border-bottom:1px solid var(--line);padding:0 2px}.brand-tab{position:relative;flex:0 0 auto;min-height:42px;border:0;border-radius:0;background:transparent;color:var(--muted);padding:8px 14px;cursor:pointer;white-space:nowrap}.brand-tab:hover{color:var(--accent-dark)}.brand-tab[aria-selected="true"]{color:#5e3820;font-weight:700}.brand-tab[aria-selected="true"]::after{position:absolute;right:12px;bottom:-1px;left:12px;height:2px;background:var(--accent-dark);content:""}.brand-tab:focus-visible{outline:2px solid var(--focus);outline-offset:-2px}.brand-panels{padding:18px 0 0}.brand-panel[hidden]{display:none!important}.brand-panel{border-left:2px solid var(--accent);padding:0 0 0 16px}.brand-difference p{margin-bottom:0}@media(max-width:760px){.report-shell{grid-template-columns:1fr;gap:12px}.report-nav{position:static;display:flex;align-items:center;gap:8px;padding:0}.report-nav small{padding:0}.report-nav a{padding:5px 8px;border-left:0;border-bottom:1px solid rgba(223,199,174,.35)}}@media(max-width:560px){.page{width:min(100% - 20px,1180px);padding-top:18px}.report-cover h1{font-size:2rem}.section{padding:20px}.section-header{display:block}.source-label{margin-top:10px}.brand-tab{padding-inline:10px}.brand-panel{padding-left:12px}}
"""
    style += """
.audience-chart-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.chart-card{container-type:inline-size;border:1px solid var(--line);border-radius:8px;background:#fff;padding:16px}.chart-card h3{font-size:18px;margin:0 0 12px}.audience-chart{min-width:0}.audience-chart-age,.audience-chart-gender{display:flex;flex-direction:column}.audience-chart-crowd{grid-column:1/-1}.audience-pie-layout{display:grid;grid-template-columns:minmax(0,45fr) minmax(0,55fr);flex:1;min-height:0;gap:14px;align-items:center}.pie-chart{position:relative;width:min(260px,100%);aspect-ratio:1;border-radius:50%;display:block;justify-self:center;background:conic-gradient(var(--accent) 0deg,var(--accent) 360deg);box-shadow:0 0 0 1px rgba(82,45,24,.1);cursor:default}.audience-chart-gender .pie-chart{width:min(240px,100%)}.chart-tooltip{position:absolute;z-index:2;left:50%;bottom:calc(100% + 10px);min-width:150px;transform:translateX(-50%);opacity:0;pointer-events:none;padding:10px 12px;border-radius:8px;background:rgba(255,255,255,.96);box-shadow:0 14px 34px rgba(43,23,12,.16);color:var(--ink);font-size:13px;line-height:1.5;transition:opacity .15s ease}.chart-tooltip b{display:block;margin-bottom:4px}.chart-tooltip span{display:block}.chart-tooltip.is-visible,.audience-column-item:hover .chart-tooltip,.audience-column-item:focus .chart-tooltip{opacity:1}.pie-legend{display:grid;gap:8px;margin:0;padding:0;list-style:none}.pie-legend .legend-item{position:relative;display:grid;grid-template-columns:minmax(80px,1fr) auto auto;gap:8px;align-items:center;color:var(--muted);font-size:14px;padding:0;border:0;font-variant-numeric:tabular-nums}.pie-legend .legend-label{display:flex;align-items:center;gap:8px;min-width:0;overflow:visible;white-space:normal;overflow-wrap:anywhere}.legend-swatch{display:block;flex:0 0 12px;width:12px;height:12px;border-radius:3px}.legend-count,.legend-share{white-space:nowrap;text-align:right}.audience-column-chart{position:relative;min-height:300px;display:grid;grid-template-columns:48px minmax(0,1fr);gap:12px;padding-top:8px}.audience-column-y-axis{display:flex;flex-direction:column;justify-content:space-between;align-items:flex-end;padding-bottom:42px;color:var(--muted);font-size:13px;font-variant-numeric:tabular-nums}.audience-column-plot{position:relative;display:grid;align-items:end;gap:12px;min-width:0;padding:0 8px 42px;border-bottom:1px solid rgba(82,45,24,.22);background:repeating-linear-gradient(to top,transparent 0,transparent 72px,rgba(82,45,24,.11) 73px)}.audience-column-item{position:relative;min-width:0;height:230px;display:flex;align-items:end;justify-content:center;outline:0}.audience-column-item:focus-visible{outline:3px solid var(--focus);outline-offset:2px}.audience-column-bar{width:min(64px,72%);min-height:4px;border-radius:8px 8px 0 0;cursor:default}.audience-column-label{position:absolute;left:50%;bottom:-34px;width:76px;transform:translateX(-50%);color:var(--muted);font-size:13px;line-height:1.25;text-align:center;word-break:break-word}.audience-column-item .chart-tooltip{bottom:calc(100% + 10px)}@container (max-width:360px){.audience-pie-layout{grid-template-columns:1fr}.audience-chart .pie-chart,.audience-chart-gender .pie-chart{width:min(240px,100%)!important;height:auto!important;flex-basis:auto!important}.pie-legend{width:100%}}@media(max-width:760px){.audience-chart-grid{grid-template-columns:1fr}.audience-chart-crowd{grid-column:auto}}@media(max-width:560px){.audience-pie-layout{grid-template-columns:1fr}.audience-chart .pie-chart,.audience-chart-gender .pie-chart{width:min(240px,100%)!important;height:auto!important;flex-basis:auto!important}.audience-column-chart{grid-template-columns:38px minmax(0,1fr);gap:8px}.audience-column-y-axis{font-size:11px}.audience-column-plot{gap:4px;padding-inline:2px}.audience-column-label{width:44px;font-size:11px}.audience-column-bar{width:78%}}
"""
    filters = fact_pack.get("filters", {}) if isinstance(fact_pack, dict) else {}
    industry = str(filters.get("industry") or "食品饮料")
    brands = filters.get("brands") or []
    brand_text = "、".join(str(brand) for brand in brands if brand) or "指定品牌"
    date_text = ""
    if filters.get("custom_start_date") and filters.get("custom_end_date"):
        date_text = f"｜{filters['custom_start_date']} 至 {filters['custom_end_date']}"
    subtitle = f"{industry}行业｜{brand_text}{date_text}"

    template = _load_html_template()
    unified_style = _read_report_source(REPORT_STYLE_PATH, "report style")
    unified_script = _read_report_source(REPORT_SCRIPT_PATH, "report script")
    available_frames = sum(
        len([frame for frame in material_frames.get(str(item.get("material_id")), []) if frame.get("available")])
        for item in selected
    )
    rendered = template.safe_substitute(
        style=style,
        unified_style=unified_style,
        unified_script=unified_script,
        subtitle=esc(subtitle),
        frame_count=available_frames,
        source_list=source_label("Top1000 榜单数据"),
        source_detail=source_label("单素材秒级详情"),
        source_derived=source_label("榜单 + 秒级详情派生"),
        top_material_combination=top_material_combination,
        audience_insights=audience_insights,
        landscape=landscape,
        baseline=baseline,
        performance=performance,
        material_tag_chart=material_tag_chart,
        people_tag_chart=people_tag_chart,
        competitor=competitor,
        trend_items=trend_items,
        diagnoses=diagnosis_items,
        frame_options=frame_options,
        frames="".join(frame_buttons),
        opportunities=opportunities,
        experiments=experiments,
    )
    _validate_rendered_sections(rendered)
    return rendered


def render_report(*, analysis_json, output_dir, fact_pack=None):
    analysis = _load_analysis(analysis_json)
    data = {"status": "complete", "analysis": analysis}
    audience_dashboard = fact_pack.get("audienceDashboard") if isinstance(fact_pack, dict) else None
    markdown = _render_markdown(analysis, audience_dashboard)
    rendered_html = _render_html(
        analysis, _material_frames(fact_pack or {}), fact_pack or {}
    )
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    write_json_atomically(data, output / "final-report-data.json")
    (output / "final-report.md").write_text(markdown, encoding="utf-8")
    (output / "final-report.html").write_text(rendered_html, encoding="utf-8")
    return 0
