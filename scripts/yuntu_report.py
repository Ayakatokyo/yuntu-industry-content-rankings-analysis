"""Render final Yuntu analysis reports from model-authored JSON."""

import html
import json
import math
import re
import shutil
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
    ("script_insights", "script-insights", "03｜脚本洞察"),
    ("highlight_insights", "highlight-insights", "04｜高光画面洞察"),
    ("material_deep_dive", "material-deep-dive", "05｜单素材深度分析"),
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
    "audienceInsights",
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

EVIDENCE_FIELDS = tuple(field for _, field in SECTION_TITLES[:-1]) + (
    "audienceInsights",
)
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
HIGHLIGHT_CATEGORY_LABELS = {
    "portrait": "人像画面",
    "product": "产品画面",
    "scene": "场景画面",
    "text_overlay": "字幕画面",
    "other": "其他画面",
}
HIGHLIGHT_CATEGORY_ORDER = tuple(HIGHLIGHT_CATEGORY_LABELS)
SECOND_LEVEL_TRENDS = ("点赞指数", "流失指数", "点击指数", "互动指数", "评论指数")
DEEP_DIVE_SUMMARY_FIELDS = (
    "visual_summary",
    "data_summary",
    "audience_summary",
    "marketing_summary",
    "replication_advice",
    "risk_notes",
    "opening_judgment",
    "visual_rhythm",
    "peak_frame_reading",
    "second_level_reading",
    "audience_fit",
    "xiaoxian_dun_reference",
    "do_not_copy",
)
DEEP_DIVE_FIELD_LABELS = (
    ("画面总结", "visual_summary"),
    ("数据总结", "data_summary"),
    ("人群总结", "audience_summary"),
    ("营销总结", "marketing_summary"),
    ("复用建议", "replication_advice"),
    ("风险提示", "risk_notes"),
    ("开场判断", "opening_judgment"),
    ("画面节奏", "visual_rhythm"),
    ("峰值帧解读", "peak_frame_reading"),
    ("秒级关系", "second_level_reading"),
    ("人群匹配", "audience_fit"),
    ("小仙炖借鉴", "xiaoxian_dun_reference"),
    ("不建议照搬", "do_not_copy"),
)
AUDIT_JSON_PATTERN = re.compile(r'(?:\[\s*)?\{\s*"[^"\n]+"\s*:')
DEEP_DIVE_FORBIDDEN_CLAIM = re.compile(
    r"脚本|话术|内容公式|真实(?:点击|互动|点赞|评论)(?:量|次数)?|转化|因果|导致|提升"
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
    if not all(
        PEOPLE_TAG_OVERLAP_NOTICE in item["summary"]
        for item in analysis["audienceInsights"]
    ):
        raise YuntuReportError(
            "audienceInsights summaries must state the overlapping-label limitation"
        )
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


def _validate_deep_dive_text(value, field):
    _validate_summary(value, field)
    if DEEP_DIVE_FORBIDDEN_CLAIM.search(value):
        raise YuntuReportError(f"{field} must not contain scripts, counts, conversion, or causal claims")


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
    executive_summary = value.get("executiveSummary")
    if not isinstance(executive_summary, dict):
        raise YuntuReportError(
            "topMaterialCombination.executiveSummary must be an object"
        )
    _validate_summary(
        executive_summary.get("summary"),
        "topMaterialCombination.executiveSummary summary",
    )
    _validate_evidence_and_material_ids(
        executive_summary, "topMaterialCombination.executiveSummary"
    )
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
        evidence = item.get("evidence")
        if not isinstance(evidence, list) or not evidence or not all(
            isinstance(entry, dict) for entry in evidence
        ):
            raise YuntuReportError("experimentMatrix items require a real fact reference")


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


def _render_markdown(analysis, audience_dashboard=None, fact_pack=None):
    lines = ["# 云图行业内容榜单分析报告", ""]
    combination = analysis["topMaterialCombination"]
    overall = {
        item["dimension"]: item for item in combination["overallConclusions"]
    }
    lines.extend(["## 01｜TOP 素材组合结论", "", "### TOP1000 整体分析", ""])
    for dimension in TOP_MATERIAL_DIMENSIONS:
        summary = overall[dimension]["summary"]
        if dimension == "people":
            summary = f"{summary} {PEOPLE_TAG_OVERLAP_NOTICE}"
        lines.extend([
            f"{TOP_MATERIAL_LABELS[dimension]}，{summary}",
            "",
        ])
    lines.extend(["---", "", "### 各品牌 TOP 对比分析（成功秒级拆解素材）", ""])
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
    lines.extend(["## 02｜人群洞察", ""])
    for insight in analysis["audienceInsights"]:
        lines.extend([insight["summary"], ""])
    if isinstance(audience_dashboard, dict):
        sample = audience_dashboard.get("sample", {})
        dimensions = audience_dashboard.get("dimensions", {})
        record_count = sample.get("recordCount", 0)
        lines.extend([
            f"候选池 TOP1000 素材标签汇总（实际 {record_count} 条）",
            "",
        ])
        for key, label in AUDIENCE_DIMENSION_LABELS.items():
            dimension = dimensions.get(key, {}) if isinstance(dimensions, dict) else {}
            notice = "图表按素材标签占比展示，用于观察标签结构，不代表真实人群分布。"
            lines.extend([f"### {label}", "", notice, ""])
            buckets = dimension.get("buckets", [])
            if not buckets:
                lines.extend(["暂无可视化数据。", ""])
            for bucket in buckets:
                lines.append(
                    f"- {bucket['label']}：{bucket['materialCount']} 条素材，占比 {bucket['chartShare'] * 100:.1f}%"
                )
            unlabeled_count = dimension.get("unlabeledRecordCount", 0)
            if unlabeled_count:
                lines.append(f"- 未识别到该维度标签：{unlabeled_count} 条素材（不计入图表分母）")
            lines.append("")
    lines.extend([
        "## 03｜脚本洞察",
        "",
        "**脚本数据：未接入**",
        "",
        "本次云图 RPA 未提供可用于汇总的脚本正文与时间戳段落；本部分暂不输出话术、内容公式或帧-话术对应关系。",
        "",
        "## 04｜高光画面洞察",
        "",
        "每条素材保留封面画面，并从点击指数局部峰值中按点击值降序、秒数升序取最多 5 帧。",
        "",
    ])
    successful_frames = _overview_highlight_frames(fact_pack or {})
    dashboard = analysis.get("highlightDashboard")
    if not successful_frames:
        reason = _highlight_failure_reasons(fact_pack or {})
        lines.extend(["暂无可用高光帧。" + (f" 原因：{reason}。" if reason else ""), ""])
    elif not isinstance(dashboard, dict):
        lines.extend(["高光帧已生成，尚未完成视觉分类，因此不输出视觉洞察。", ""])
    else:
        frames_by_ref = {frame["frame_ref"]: frame for frame in successful_frames}
        for group in dashboard["groups"]:
            lines.extend([f"### {HIGHLIGHT_CATEGORY_LABELS[group['category']]}", ""])
            for pattern in group["common_patterns"]:
                lines.extend([f"- {pattern}", ""])
            for frame_ref in group["frame_refs"]:
                frame = frames_by_ref[frame_ref]
                frame_label = "封面画面" if frame["frame_type"] == "cover" else f"点击 Top{frame.get('peak_rank')} 波峰画面"
                value = "-" if frame.get("click_value") is None else str(frame["click_value"])
                lines.append(
                    f"- #{frame.get('rank', '-')}｜{frame.get('title', frame['material_id'])}｜{frame_label}｜{frame.get('second')}s｜点击指数 {value}"
                )
            lines.append("")
            for direction in group["derivative_directions"]:
                lines.extend([f"- {direction['title']}：{direction['body']}", ""])
    lines.extend(["## 05｜单素材深度分析", ""])
    deep_dives = analysis.get("materialDeepDives", [])
    facts = {
        str(fact.get("material_id")): fact
        for fact in (fact_pack or {}).get("materialFacts", [])
        if isinstance(fact, dict) and fact.get("material_id")
    }
    if not isinstance(deep_dives, list) or not deep_dives:
        lines.extend(["暂无单素材深度分析数据。", ""])
    else:
        for dive in deep_dives:
            fact = facts.get(str(dive.get("material_id")), {})
            title = fact.get("title") or dive.get("material_id")
            lines.extend([f"### #{fact.get('rank', '-')}｜{title}", "", "#### 高光帧观察", ""])
            for observation in dive.get("frame_observations", []):
                lines.extend([f"- {observation.get('frame_ref')}：{observation.get('observation')}", ""])
            lines.extend(["#### 秒级拆解", ""])
            breakdown = fact.get("secondLevelBreakdown", {}) if isinstance(fact, dict) else {}
            metrics = {item.get("trend_name"): item for item in breakdown.get("metrics", []) if isinstance(item, dict)}
            for trend_name in SECOND_LEVEL_TRENDS:
                metric = metrics.get(trend_name, {})
                if not metric.get("available"):
                    lines.extend([f"- {trend_name}：不可用（{metric.get('missing_reason') or '数据不足'}）", ""])
                else:
                    lines.extend([f"- {trend_name}：见 HTML 交互图表。", ""])
    return "\n".join(lines)


def _material_frames(fact_pack):
    frames = {}
    for fact in fact_pack.get("materialFacts", []) if isinstance(fact_pack, dict) else []:
        material_id = fact.get("material_id")
        if isinstance(material_id, str):
            frames[material_id] = fact.get("highlightFrames", [])
    return frames


def _available_highlight_frames(fact_pack):
    frames = []
    material_facts = fact_pack.get("materialFacts", []) if isinstance(fact_pack, dict) else []
    for fact in material_facts:
        if not isinstance(fact, dict):
            continue
        material_id = str(fact.get("material_id") or "")
        for frame in fact.get("highlightFrames", []):
            if not isinstance(frame, dict) or not frame.get("available"):
                continue
            second = frame.get("second")
            frame_type = frame.get("frame_type") or (
                "cover" if frame.get("is_cover") else "click_peak"
            )
            frame_ref = frame.get("frame_ref") or f"highlight:{material_id}:{frame_type}:{second}"
            frames.append(
                {
                    **frame,
                    "material_id": material_id,
                    "rank": fact.get("rank"),
                    "title": fact.get("title", material_id),
                    "frame_type": frame_type,
                    "frame_ref": frame_ref,
                }
            )
    return frames


def _overview_highlight_frames(fact_pack):
    """Return all successful overview frames, including the classified cover frame."""
    return _available_highlight_frames(fact_pack)


def _has_standard_highlight_contract(fact_pack):
    material_facts = fact_pack.get("materialFacts", []) if isinstance(fact_pack, dict) else []
    successful_frames = [
        frame
        for fact in material_facts
        if isinstance(fact, dict)
        for frame in fact.get("highlightFrames", [])
        if isinstance(frame, dict) and frame.get("available")
    ]
    return bool(successful_frames) and all(
        isinstance(frame.get("frame_ref"), str)
        and frame.get("frame_type") in {"cover", "click_peak"}
        for frame in successful_frames
    )


def _highlight_failure_reasons(fact_pack):
    material_facts = fact_pack.get("materialFacts", []) if isinstance(fact_pack, dict) else []
    reasons = {
        str(frame.get("failure_reason"))
        for fact in material_facts
        if isinstance(fact, dict)
        for frame in fact.get("highlightFrames", [])
        if isinstance(frame, dict) and frame.get("failure_reason")
    }
    return "、".join(sorted(reasons))


def _validate_highlight_dashboard(analysis, fact_pack):
    successful_frames = _overview_highlight_frames(fact_pack)
    dashboard = analysis.get("highlightDashboard")
    if not successful_frames:
        return
    if not isinstance(dashboard, dict):
        if _has_standard_highlight_contract(fact_pack):
            raise YuntuReportError(
                "highlightDashboard is required when standard highlight frames are available"
            )
        # Historical reports may be re-rendered before visual analysis exists.
        return
    groups = dashboard.get("groups")
    if not isinstance(groups, list):
        raise YuntuReportError("highlightDashboard.groups must be a list")
    known_refs = {frame["frame_ref"] for frame in successful_frames}
    actual_refs = []
    categories = []
    for group in groups:
        if not isinstance(group, dict):
            raise YuntuReportError("highlightDashboard.groups items must be objects")
        category = group.get("category")
        if category not in HIGHLIGHT_CATEGORY_ORDER:
            raise YuntuReportError("highlightDashboard category is invalid")
        categories.append(category)
        frame_refs = group.get("frame_refs")
        if not isinstance(frame_refs, list) or not frame_refs or not all(
            isinstance(frame_ref, str) for frame_ref in frame_refs
        ):
            raise YuntuReportError("highlightDashboard groups require frame_refs")
        patterns = group.get("common_patterns")
        if not isinstance(patterns, list) or not patterns or not all(
            isinstance(pattern, str) and pattern.strip() for pattern in patterns
        ):
            raise YuntuReportError("highlightDashboard groups require common_patterns")
        for pattern in patterns:
            _validate_deep_dive_text(
                pattern, "highlightDashboard groups common_patterns"
            )
        directions = group.get("derivative_directions")
        if not isinstance(directions, list):
            raise YuntuReportError("highlightDashboard groups require derivative_directions")
        for direction in directions:
            if not isinstance(direction, dict):
                raise YuntuReportError("highlightDashboard derivative directions must be objects")
            if not all(
                isinstance(direction.get(key), str) and direction[key].strip()
                for key in ("title", "body")
            ):
                raise YuntuReportError("highlightDashboard derivative directions require title and body")
            _validate_deep_dive_text(
                direction["title"], "highlightDashboard derivative direction title"
            )
            _validate_deep_dive_text(
                direction["body"], "highlightDashboard derivative direction body"
            )
            direction_refs = direction.get("frame_refs")
            if not isinstance(direction_refs, list) or not direction_refs or not set(direction_refs).issubset(set(frame_refs)):
                raise YuntuReportError("highlightDashboard derivative directions must reference their group")
        actual_refs.extend(frame_refs)
    expected_categories = [
        category for category in HIGHLIGHT_CATEGORY_ORDER if category in categories
    ]
    if categories != expected_categories:
        raise YuntuReportError(
            "highlightDashboard groups must use portrait, product, scene, text_overlay, other order"
        )
    if len(actual_refs) != len(set(actual_refs)) or set(actual_refs) != known_refs:
        raise YuntuReportError("highlightDashboard must classify each successful frame exactly once")


def _has_second_level_breakdown_contract(fact_pack):
    material_facts = fact_pack.get("materialFacts", []) if isinstance(fact_pack, dict) else []
    return any(
        isinstance(fact, dict) and "secondLevelBreakdown" in fact
        for fact in material_facts
    )


def _selected_material_ids(fact_pack):
    selected = fact_pack.get("selectedMaterials", []) if isinstance(fact_pack, dict) else []
    ids = [str(item.get("material_id")) for item in selected if isinstance(item, dict) and item.get("material_id")]
    if ids:
        return ids
    return [
        str(fact.get("material_id"))
        for fact in fact_pack.get("materialFacts", [])
        if isinstance(fact, dict) and fact.get("material_id")
    ]


def _validate_material_deep_dives(analysis, fact_pack):
    """Validate new 05 evidence without making historical packs non-renderable."""
    if not _has_second_level_breakdown_contract(fact_pack):
        return
    facts = {
        str(fact.get("material_id")): fact
        for fact in fact_pack.get("materialFacts", [])
        if isinstance(fact, dict) and fact.get("material_id")
    }
    selected_ids = _selected_material_ids(fact_pack)
    if any("secondLevelBreakdown" not in facts.get(material_id, {}) for material_id in selected_ids):
        raise YuntuReportError("secondLevelBreakdown is required for each selected material")
    deep_dives = analysis.get("materialDeepDives")
    if not isinstance(deep_dives, list) or len(deep_dives) != len(selected_ids):
        raise YuntuReportError("materialDeepDives must contain exactly one item per selected material")
    dives_by_id = {}
    for dive in deep_dives:
        if not isinstance(dive, dict) or not isinstance(dive.get("material_id"), str):
            raise YuntuReportError("materialDeepDives items must include material_id")
        material_id = dive["material_id"]
        if material_id not in selected_ids or material_id in dives_by_id:
            raise YuntuReportError("materialDeepDives material_id must be selected and unique")
        dives_by_id[material_id] = dive
        for field in DEEP_DIVE_SUMMARY_FIELDS:
            _validate_deep_dive_text(
                dive.get(field), f"materialDeepDives {field}"
            )

        frames = [
            frame for frame in facts[material_id].get("highlightFrames", [])
            if isinstance(frame, dict) and frame.get("available")
        ]
        known_refs = {frame.get("frame_ref") for frame in frames if isinstance(frame.get("frame_ref"), str)}
        observations = dive.get("frame_observations")
        if not isinstance(observations, list):
            raise YuntuReportError("materialDeepDives frame_observations must be a list")
        observation_refs = []
        for observation in observations:
            if not isinstance(observation, dict) or not isinstance(observation.get("frame_ref"), str):
                raise YuntuReportError("materialDeepDives frame_observations must include frame_ref")
            _validate_deep_dive_text(observation.get("observation"), "materialDeepDives frame observation")
            observation_refs.append(observation["frame_ref"])
        if len(observation_refs) != len(set(observation_refs)) or set(observation_refs) != known_refs:
            raise YuntuReportError("materialDeepDives must observe each successful frame exactly once")

        breakdown = facts[material_id].get("secondLevelBreakdown", {})
        metrics = breakdown.get("metrics", []) if isinstance(breakdown, dict) else []
        points_by_trend = {
            metric.get("trend_name"): {
                point.get("second") for point in metric.get("points", [])
                if isinstance(point, dict) and isinstance(point.get("second"), int)
            }
            for metric in metrics if isinstance(metric, dict)
        }
        observations = dive.get("second_level_observations")
        if not isinstance(observations, list):
            raise YuntuReportError("materialDeepDives second_level_observations must be a list")
        seen_trends = set()
        for observation in observations:
            if not isinstance(observation, dict):
                raise YuntuReportError("materialDeepDives second_level_observations items must be objects")
            trend_name = observation.get("trend_name")
            if trend_name not in SECOND_LEVEL_TRENDS or trend_name in seen_trends:
                raise YuntuReportError("materialDeepDives second_level_observations trend_name is invalid")
            seen_trends.add(trend_name)
            _validate_deep_dive_text(observation.get("summary"), "materialDeepDives second-level summary")
            seconds = observation.get("evidence_seconds")
            if not isinstance(seconds, list) or not all(isinstance(second, int) for second in seconds):
                raise YuntuReportError("materialDeepDives evidence_seconds must be integer seconds")
            if not set(seconds).issubset(points_by_trend.get(trend_name, set())):
                raise YuntuReportError("materialDeepDives evidence_seconds must exist in the material trend")
    if set(dives_by_id) != set(selected_ids):
        raise YuntuReportError("materialDeepDives must cover every selected material")


def _is_v4_fact_pack(fact_pack):
    return isinstance(fact_pack, dict) and fact_pack.get("schemaVersion") == 4


def _validate_experiment_fact_references(analysis, fact_pack):
    if not _is_v4_fact_pack(fact_pack):
        return
    facts = {
        str(fact.get("material_id")): fact
        for fact in fact_pack.get("materialFacts", [])
        if isinstance(fact, dict) and fact.get("material_id")
    }
    known_material_ids = set(facts)
    known_frame_refs = {
        frame["frame_ref"] for frame in _available_highlight_frames(fact_pack)
    }
    known_metrics = {
        metric_name
        for fact in facts.values()
        for metric_name in fact.get("metrics", {})
    }
    known_metrics.update(
        metric.get("trend_name")
        for fact in facts.values()
        for metric in fact.get("secondLevelBreakdown", {}).get("metrics", [])
        if isinstance(metric, dict) and isinstance(metric.get("trend_name"), str)
    )
    for item in analysis["experimentMatrix"]:
        valid = False
        for evidence in item["evidence"]:
            material_id = str(evidence.get("material_id", ""))
            frame_ref = evidence.get("frame_ref")
            metric = evidence.get("metric") or evidence.get("trend_name")
            if material_id and material_id in known_material_ids:
                valid = True
            if isinstance(frame_ref, str) and frame_ref in known_frame_refs:
                valid = True
            if isinstance(metric, str) and metric in known_metrics:
                valid = True
            if "second" in evidence:
                fact = facts.get(material_id)
                points = {
                    point.get("second")
                    for trend in fact.get("secondLevelBreakdown", {}).get("metrics", [])
                    if isinstance(trend, dict)
                    and trend.get("trend_name") == metric
                    for point in trend.get("points", [])
                    if isinstance(point, dict)
                } if fact else set()
                if evidence.get("second") not in points:
                    valid = False
        if not valid:
            raise YuntuReportError(
                "experimentMatrix items require a real fact reference"
            )


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


def _format_index_value(value):
    if not isinstance(value, (int, float)):
        return "-"
    return f"{value:.2f}"


def _frame_material_id(frame):
    frame_ref = str(frame.get("frame_ref", ""))
    parts = frame_ref.split(":")
    if len(parts) >= 2 and parts[0] == "highlight":
        return parts[1]
    path_parts = str(frame.get("relative_path", "")).replace("\\", "/").split("/")
    if "highlights" in path_parts:
        index = path_parts.index("highlights")
        if index + 1 < len(path_parts):
            return path_parts[index + 1]
    return "unknown"


def _report_frame_asset_path(frame):
    path = str(frame.get("relative_path", "")).replace("\\", "/")
    parts = [part for part in path.split("/") if part and part != "."]
    if "highlights" in parts:
        index = parts.index("highlights")
        if index + 2 <= len(parts):
            return "assets/highlight-frames/" + "/".join(parts[index + 1:])
    filename = Path(path).name
    if not filename:
        return ""
    return f"assets/highlight-frames/{_frame_material_id(frame)}/{filename}"


def _copy_highlight_assets(fact_pack, output_dir, source_root=None):
    output_dir = Path(output_dir)
    source_root = Path(source_root) if source_root is not None else output_dir.parent
    for frame in _available_highlight_frames(fact_pack):
        target_rel = _report_frame_asset_path(frame)
        source_rel = str(frame.get("relative_path", "")).replace("\\", "/")
        if not target_rel or not source_rel:
            continue
        source_path = Path(source_rel)
        candidates = [source_path]
        if not source_path.is_absolute():
            if source_rel.startswith("../"):
                candidates = [output_dir / source_rel]
            else:
                # Historical batches may retain extracted frames only in a prior report.
                candidates = [
                    source_root / source_rel.lstrip("/"),
                    source_root / "final-report" / target_rel,
                ]
        source_path = next((path for path in candidates if path.is_file()), None)
        if source_path is None:
            continue
        target_path = output_dir / target_rel
        if source_path.resolve() == target_path.resolve():
            continue
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)


def _generic_text(value):
    return str(value or "").replace("小仙炖", "目标品牌")


def _render_html(analysis, material_frames, fact_pack):
    def esc(value):
        return html.escape(str(value))

    def image_src(frame):
        return _report_frame_asset_path(frame)

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
    report_scopes = fact_pack.get("reportScopes", {})
    if not isinstance(report_scopes, dict):
        report_scopes = {}

    def source_label(text):
        return f'<span class="source-label">来源：{esc(text)}</span>'

    def scope_badge(scope_key):
        scope = report_scopes.get(scope_key, {})
        if not isinstance(scope, dict):
            return ""
        source_name = str(scope.get("source_name") or "").strip()
        if not source_name:
            return ""
        if scope_key == "detail":
            sample_count = scope.get("sample_count")
            text = f"{source_name}：{sample_count} 条" if isinstance(sample_count, int) else source_name
        else:
            sample_count = scope.get("sample_count")
            text = f"{source_name}：{sample_count} 条" if isinstance(sample_count, int) else source_name
        return '<span class="report-scope-badge">' + esc(text) + "</span>"

    def insight_cards(items):
        return "".join(
            f'<article class="insight-row"><p>{esc(_generic_text(item.get("summary", "")))}</p>'
            "</article>"
            for item in items
        )

    def top_material_combination_cards(value):
        scope_badges = "".join(
            scope_badge(scope_key)
            for scope_key in ("ranking", "detail")
        )
        scope_summary = (
            '<div class="top-material-scope" aria-label="01 章数据范围">'
            + scope_badges
            + "</div>"
            if scope_badges
            else ""
        )
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
            + '<p class="brand-classification-note">品牌归属：标题匹配归属；对比样本：成功秒级拆解素材</p>'
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
            scope_summary
            + '<article class="top-material-executive yuntu-content-card"><h3>综合结论</h3><p>'
            + esc(_generic_text(value["executiveSummary"]["summary"]))
            + "</p></article>"
            + '<div class="top-material-overall yuntu-content-card"><h3>TOP1000 整体分析</h3>'
            + overall
            + "</div>"
            + '<div class="top-material-brands yuntu-content-card"><h3>各品牌 TOP 对比分析（成功秒级拆解素材）</h3>'
            + '<div class="brand-tabs" role="tablist" aria-label="各品牌 TOP 对比分析（成功秒级拆解素材）">'
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
                    + '<span>命中素材数：' + esc(bucket["materialCount"]) + '条</span>'
                    + '<span>占比：' + f"{chart_share:.1f}%" + '</span></div>'
                )
                columns.append(
                    '<div class="audience-column-item" role="img" tabindex="0" aria-label="'
                    + esc(bucket["label"]) + '，素材数 ' + esc(bucket["materialCount"])
                    + ' 条，占比 ' + f"{chart_share:.1f}%"
                    + '"><div class="audience-column-bar" style="height:'
                    + f"{max(2, chart_share / axis_max * 100):.2f}%" + ';background:'
                    + colors[index % len(colors)] + '"></div><span class="audience-column-label">'
                    + esc(bucket["label"]) + '</span>' + tooltip + '</div>'
                )
            return (
                '<article class="chart-card audience-chart audience-chart-crowd"><h3>' + esc(label)
                + '分布</h3><div class="audience-column-chart" data-audience-column role="group" aria-label="'
                + esc(label) + '标签占比柱状图，素材样本共 ' + esc(record_count) + ' 条">'
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
            visual_items = (
                sorted(items, key=lambda item: (-item[3], str(item[0])))
                if key == "age"
                else items
            )
            cursor = 0.0
            stops, slices, legend = [], [], []
            colors_by_label = {}
            for index, (item_label, count, material_share, chart_share) in enumerate(visual_items):
                color = colors[index % len(colors)]
                colors_by_label[item_label] = color
                next_cursor = cursor + chart_share * 100
                stops.append(f"{color} {cursor:.4f}% {next_cursor:.4f}%")
                slices.append({"label": item_label, "count": count, "materialShare": round(material_share * 100, 1), "share": round(chart_share * 100, 1), "start": cursor * 3.6, "end": next_cursor * 3.6})
                cursor = next_cursor
            legend_items = visual_items
            for item_label, count, material_share, chart_share in legend_items:
                legend.append(
                    '<li class="legend-item" title="' + esc(item_label) + '：命中素材数：' + esc(count) + '条 占比：' + f"{chart_share * 100:.1f}%" + '">'
                    + '<span class="legend-label"><i class="legend-swatch" style="background:' + colors_by_label[item_label] + '"></i>'
                    + esc(item_label) + '</span><span class="legend-count">' + esc(count) + ' 条</span><span class="legend-share">' + f"{chart_share * 100:.1f}%" + '</span></li>'
                )
            return (
                f'<article class="chart-card audience-chart audience-chart-{esc(key)}"><h3>{esc(label)}分布</h3><div class="audience-pie-layout">'
                + f'<div class="pie-chart" data-audience-pie role="img" tabindex="0" aria-label="{esc(label)}标签占比饼图，素材样本共 {esc(record_count)} 条" data-pie-slices="{esc(json.dumps(slices, ensure_ascii=False))}" style="background:conic-gradient({", ".join(stops)})">'
                + '<div class="chart-tooltip" role="tooltip"></div></div>'
                + '<ul class="pie-legend">' + "".join(legend) + '</ul></div></article>'
            )
        return f'<article class="chart-card audience-chart"><h3>{esc(label)}分布</h3><p class="data-note">暂无可视化数据。</p></article>'

    def audience_dashboard_cards(value):
        ai_insights = insight_cards(analysis["audienceInsights"])
        if not isinstance(value, dict):
            return (
                '<section class="section" id="audience-insights"><header class="section-header">'
                '<h2>02｜人群洞察</h2></header>' + ai_insights
                + '<p class="data-note">暂无人群汇总数据。</p></section>'
            )
        sample = value.get("sample", {})
        dimensions = value.get("dimensions", {})
        if not isinstance(dimensions, dict):
            return ""
        dimension_order = ("crowd", "age", "gender")
        charts = "".join(
            audience_dimension_chart(key, dimensions[key])
            for key in dimension_order
            if key in dimensions and isinstance(dimensions[key], dict)
        )
        charts += "".join(
            audience_dimension_chart(key, dimension)
            for key, dimension in dimensions.items()
            if key not in dimension_order
            and key in AUDIENCE_DIMENSION_LABELS
            and isinstance(dimension, dict)
        )
        if not charts:
            charts = '<p class="data-note">暂无人群汇总数据。</p>'
        topn_records = fact_pack.get("audienceTopNRecords", [])
        topn_records_json = ""
        topn_controls = ""
        if isinstance(topn_records, list) and topn_records:
            topn_records = [
                {
                    **record,
                    "title": facts.get(str(record.get("material_id")), {}).get(
                        "title", str(record.get("material_id", ""))
                    ),
                }
                for record in topn_records
                if isinstance(record, dict)
            ]
            topn_records_json = html.escape(
                json.dumps(topn_records, ensure_ascii=False, separators=(",", ":")),
                quote=True,
            )
            max_topn = len(topn_records)
            topn_controls = (
                '<div class="audience-topn-controls" aria-label="人群分析素材范围">'
                '<label>分析 TOP <input type="number" min="1" max="' + esc(max_topn)
                + '" value="' + esc(max_topn)
                + '" step="1" inputmode="numeric" data-audience-topn-input></label>'
                '<input type="range" min="1" max="' + esc(max_topn)
                + '" value="' + esc(max_topn) + '" step="1" data-audience-topn-range>'
                '<span data-audience-topn-label>当前 TOP' + esc(max_topn)
                + ' / ' + esc(max_topn) + '</span></div>'
            )
        dashboard_attrs = ' class="audience-dashboard"'
        if topn_records_json:
            dashboard_attrs += ' data-audience-records="' + topn_records_json + '"'
        return (
            '<section class="section" id="audience-insights"><header class="section-header">'
            '<h2>02｜人群洞察</h2></header><div class="audience-ai-insights">'
            + ai_insights + '</div><div' + dashboard_attrs + '><div class="audience-data-card raw-fact-card">'
            + '<div class="collapsible-head"><button class="collapsible-toggle" type="button" data-collapsible-toggle data-collapsible-expanded-label="收起人群汇总数据" data-collapsible-collapsed-label="展开人群汇总数据" aria-expanded="true" aria-controls="audience-dashboard-body"><span class="collapsible-toggle-action">收起人群汇总数据</span></button></div>'
            + '<div class="collapsible-body" id="audience-dashboard-body">'
            + topn_controls + '<div class="audience-chart-grid" data-audience-chart-grid>'
            + charts + '</div></div></div></div></section>'
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

    def highlight_frame_label(frame):
        if frame.get("frame_type") == "cover":
            return "封面画面"
        return f"点击 Top{frame.get('peak_rank')} 波峰画面"

    def highlight_material_title(frame):
        return str(frame.get("title", frame["material_id"])).removesuffix(".mp4")

    def highlight_insights_cards():
        successful_frames = _overview_highlight_frames(fact_pack)
        if not successful_frames:
            reason = _highlight_failure_reasons(fact_pack)
            detail = f"（{esc(reason)}）" if reason else ""
            return '<p class="data-note">暂无可用高光帧' + detail + "。</p>"
        dashboard = analysis.get("highlightDashboard")
        if not isinstance(dashboard, dict):
            return '<p class="data-note">高光帧已生成，尚未完成视觉分类，因此不输出视觉洞察。</p>'
        frames_by_ref = {frame["frame_ref"]: frame for frame in successful_frames}
        ordered_groups = [
            group
            for category in HIGHLIGHT_CATEGORY_ORDER
            for group in dashboard["groups"]
            if group["category"] == category
        ]
        tabs = []
        panels = []
        for index, group in enumerate(ordered_groups):
            category = group["category"]
            selected = index == 0
            panel_id = f"highlight-panel-{category}"
            tab_id = f"highlight-tab-{category}"
            frame_refs = group["frame_refs"]
            tabs.append(
                '<button type="button" role="tab" id="' + esc(tab_id)
                + '" aria-controls="' + esc(panel_id)
                + '" aria-selected="' + str(selected).lower()
                + '" tabindex="' + ("0" if selected else "-1")
                + '" data-highlight-category-tab data-highlight-category-target="'
                + esc(panel_id) + '">'
                + esc(HIGHLIGHT_CATEGORY_LABELS[category])
                + " · " + esc(len(frame_refs)) + " 帧</button>"
            )
            frame_cards = []
            for frame_ref in frame_refs:
                frame = frames_by_ref[frame_ref]
                click_value = frame.get("click_value")
                click_text = f"点击指数 {_format_index_value(click_value)}"
                material_id = str(frame.get("material_id", ""))
                source_label = f"查看素材：#{frame.get('rank', '-')}"
                material_title = highlight_material_title(frame)
                caption = (
                    f"#{esc(frame.get('rank', '-'))} · {esc(material_title)} · "
                    f"{highlight_frame_label(frame)} · {esc(frame.get('second'))}s · {click_text}"
                )
                frame_cards.append(
                    '<article class="highlight-frame-card" data-highlight-frame-card data-highlight-material-id="' + esc(material_id) + '">'
                    + '<figure><button class="highlight-frame-preview highlight-frame-button" type="button" '
                    + f'data-highlight-src="{html.escape(image_src(frame), quote=True)}" '
                    + f'data-highlight-caption="{html.escape(caption, quote=True)}" '
                    + 'aria-label="查看高光帧大图">'
                    + f'<img loading="lazy" src="{html.escape(image_src(frame), quote=True)}" alt="{esc(caption)}"></button></figure>'
                    + '<div class="highlight-frame-meta"><strong>' + esc(material_title)
                    + '</strong><small>' + esc(highlight_frame_label(frame))
                    + '</small><span>' + esc(frame.get("second")) + 's · ' + esc(click_text)
                    + '</span><button class="highlight-source-link" type="button" data-jump-material="'
                    + esc(material_id) + '">' + esc(source_label) + '</button></div></article>'
                )
            patterns = "".join(f"<li>{esc(pattern)}</li>" for pattern in group["common_patterns"])
            directions = "".join(
                f'<article class="highlight-direction"><h4>{esc(direction["title"])}</h4><p>{esc(direction["body"])}</p></article>'
                for direction in group["derivative_directions"]
            )
            page_count = max(1, math.ceil(len(frame_refs) / 12))
            panels.append(
                '<article class="highlight-category highlight-category-panel" role="tabpanel" id="'
                + esc(panel_id) + '" aria-labelledby="' + esc(tab_id) + '"'
                + (" hidden" if not selected else "")
                + ' data-highlight-page-size="12" data-highlight-frame-count="' + esc(len(frame_refs)) + '"><div class="highlight-analysis-pair"><div class="highlight-summary"><h4>共性洞察</h4><ul>'
                + patterns
                + '</ul></div><div class="highlight-directions">'
                + directions
                + '</div></div><div class="highlight-frame-grid">'
                + "".join(frame_cards)
                + '</div><div class="highlight-pagination" data-highlight-pagination>'
                + '<button type="button" data-highlight-page="previous">上一页</button>'
                + '<span data-highlight-page-status>1 / ' + esc(page_count) + '</span>'
                + '<button type="button" data-highlight-page="next">下一页</button>'
                + "</div></article>"
            )
        return (
            '<p class="data-note">每条素材保留封面画面，并从点击指数局部峰值中按点击值降序、秒数升序取最多 5 帧。</p>'
            + '<div class="highlight-dashboard-tabs" role="tablist" aria-label="高光画面分类">'
            + "".join(tabs)
            + '</div><div class="highlight-dashboard-panels">'
            + "".join(panels)
            + "</div>"
        )

    def deep_frame_label(frame):
        labels = ["封面帧" if frame.get("frame_type") == "cover" else f"点击 Top{frame.get('peak_rank')} 峰值帧"]
        if frame.get("frame_type") == "cover" and frame.get("peak_rank"):
            labels.append(f"点击 Top{frame['peak_rank']} 峰值")
        return "｜".join(labels)

    def second_level_timeline(metrics, material_index):
        ordered_metrics = []
        metrics_by_name = {metric.get("trend_name"): metric for metric in metrics if isinstance(metric, dict)}
        for trend_name in SECOND_LEVEL_TRENDS:
            metric = metrics_by_name.get(trend_name, {"trend_name": trend_name, "available": False, "missing_reason": "趋势未返回"})
            ordered_metrics.append({
                "trend_name": trend_name,
                "available": bool(metric.get("available")),
                "missing_reason": str(metric.get("missing_reason") or "该指标暂无可用秒级数据"),
                "points": [
                    {"second": point.get("second"), "value": point.get("value")}
                    for point in metric.get("points", [])
                    if isinstance(point, dict) and isinstance(point.get("second"), int) and isinstance(point.get("value"), (int, float))
                ],
                "high_points": [item for item in metric.get("high_points", []) if isinstance(item, dict)],
                "loss_points": [item for item in metric.get("loss_points", []) if isinstance(item, dict)],
            })
        buttons = "".join(
            '<button type="button" data-second-level-metric="' + esc(metric["trend_name"])
            + '" aria-pressed="false">' + esc(metric["trend_name"]) + "</button>"
            for metric in ordered_metrics
        )
        payload = html.escape(json.dumps(ordered_metrics, ensure_ascii=False), quote=True)
        body_id = "second-level-body-" + str(material_index)
        return (
            '<div class="second-level-timeline raw-fact-card" data-second-level-timeline data-second-level-metrics="' + payload + '">'
            + '<div class="collapsible-head"><button class="collapsible-toggle" type="button" data-collapsible-toggle aria-expanded="true" aria-controls="'
            + esc(body_id) + '"><span class="collapsible-toggle-action">收起数据</span></button></div>'
            + '<div class="collapsible-body" id="' + esc(body_id) + '"><b class="collapsible-body-title">秒级拆解</b>'
            + '<div class="second-level-switcher metric-switch" role="group" aria-label="秒级拆解指标">' + buttons + "</div>"
            + '<div class="second-level-chart-mount" aria-live="polite"></div>'
            + '<label class="second-level-range-control">查看时长 <input type="range" min="20" max="100" value="100" step="10" data-second-level-range></label>'
            + '<p class="second-level-peak-note" data-second-level-peak></p></div></div>'
        )

    def material_deep_dive_cards():
        deep_dives = analysis.get("materialDeepDives")
        if not isinstance(deep_dives, list) or not deep_dives:
            return '<p class="data-note">暂无单素材深度分析数据。</p>'
        dives_by_id = {str(dive.get("material_id")): dive for dive in deep_dives}
        ordered_ids = [material_id for material_id in _selected_material_ids(fact_pack) if material_id in dives_by_id]
        default_id = ordered_ids[0] if ordered_ids else str(deep_dives[0].get("material_id"))
        tabs, panels = [], []
        for index, material_id in enumerate(ordered_ids):
            fact = facts.get(material_id, {})
            dive = dives_by_id[material_id]
            title = fact.get("title") or material_id
            selected_tab = material_id == default_id
            tabs.append(
                '<button class="material-deep-tab" type="button" role="tab" id="material-deep-tab-'
                + str(index) + '" aria-controls="material-deep-panel-' + str(index) + '" aria-selected="'
                + str(selected_tab).lower() + '" tabindex="' + ("0" if selected_tab else "-1")
                + '" data-material-tab data-material-target="material-deep-panel-' + str(index)
                + '" data-material-id="' + esc(material_id) + '">#'
                + esc(fact.get("rank", "-")) + " " + esc(title) + "</button>"
            )
            observations = {item.get("frame_ref"): item.get("observation") for item in dive.get("frame_observations", []) if isinstance(item, dict)}
            frame_cards = []
            all_frames = [frame for frame in material_frames.get(material_id, []) if isinstance(frame, dict)]
            frames = sorted(
                [frame for frame in all_frames if frame.get("available") and str(frame.get("relative_path", "")).endswith(".jpg")],
                key=lambda frame: (frame.get("second", 0), 0 if frame.get("frame_type") == "cover" else 1),
            )
            for frame in frames:
                caption = f"{deep_frame_label(frame)}｜{frame.get('second')}s"
                if frame.get("click_value") is not None:
                    caption += f"｜点击指数 {_format_index_value(frame['click_value'])}"
                frame_cards.append(
                    '<figure class="deep-frame-card"><button class="highlight-frame-button" type="button" data-highlight-src="'
                    + html.escape(image_src(frame), quote=True) + '" data-highlight-caption="'
                    + html.escape(caption, quote=True) + '" aria-label="查看 ' + esc(caption) + '"><img loading="lazy" src="'
                    + html.escape(image_src(frame), quote=True) + '" alt="' + esc(title + " " + caption) + '"></button><figcaption>'
                    + esc(caption) + "</figcaption></figure>"
            )
            breakdown = fact.get("secondLevelBreakdown", {})
            metrics = breakdown.get("metrics", []) if isinstance(breakdown, dict) else []
            failed_reasons = []
            for frame in all_frames:
                if frame.get("available"):
                    continue
                reason = frame.get("failure_reason") or frame.get("missing_reason") or frame.get("reason")
                if reason and str(reason) not in failed_reasons:
                    failed_reasons.append(str(reason))
            frame_coverage = "高光帧可用：" + str(len(frames)) + "/" + str(len(all_frames))
            if failed_reasons:
                frame_coverage += "；" + "；".join(failed_reasons)
            frame_observations = "".join(
                '<li><strong>' + esc(deep_frame_label(frame)) + "｜" + esc(frame.get("second")) + "s：</strong>"
                + esc(observations.get(frame.get("frame_ref"), "")) + "</li>"
                for frame in frames
            ) or "<li>暂无可用于观察的高光帧。</li>"
            metric_summary = "".join(
                '<li><span>' + esc(METRIC_LABELS[key]) + '</span><b>' + esc(_format_metric(fact.get("metrics", {}).get(key), key)) + '</b></li>'
                for key in ("show_cnt", "ctr", "cvr", "play_3s_rate", "interact_rate")
                if key in fact.get("metrics", {})
            )
            panels.append(
                '<article class="material-deep-panel material-card" role="tabpanel" id="material-deep-panel-' + str(index)
                + '" aria-labelledby="material-deep-tab-' + str(index) + '"' + ("" if selected_tab else " hidden") + '><header class="material-deep-header material-head"><span>#'
                + esc(fact.get("rank", "-")) + '</span><h3>' + esc(title) + '</h3><p class="material-deep-id">素材 ID：' + esc(material_id) + '</p></header><ul class="material-deep-metrics">'
                + metric_summary + '</ul><div class="deep-visual-strip"><div class="deep-frame-grid fixed-six">'
                + "".join(frame_cards) + '</div><p class="deep-frame-coverage">' + esc(frame_coverage)
                + '</p></div><div class="deep-frame-observations"><h4>高光帧观察</h4><ul>' + frame_observations
                + '</ul></div><div class="second-level-section">' + second_level_timeline(metrics, index)
                + '</div></article>'
            )
        return '<div class="material-deep-layout side-tabs"><div class="material-deep-tab-list" role="tablist" aria-label="单素材深度分析">' + "".join(tabs) + '</div><div class="material-deep-panels">' + "".join(panels) + "</div></div>"

    script_insights = (
        '<div class="data-state"><span>脚本数据：未接入</span><p>'
        '本次云图 RPA 未提供可用于汇总的脚本正文与时间戳段落；本部分暂不输出话术、内容公式或帧-话术对应关系。'
        "</p></div>"
    )
    highlight_insights = highlight_insights_cards()
    material_deep_dive = material_deep_dive_cards()

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
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Segoe UI",sans-serif;font-size:16px;line-height:1.65}button{font:inherit}.skip-link{position:fixed;left:12px;top:-60px;background:var(--paper);color:var(--ink);padding:10px;z-index:5}.skip-link:focus{top:12px}.page{width:min(1280px,calc(100% - 20px));margin:auto;padding:32px 0 72px}.report-cover{color:#fff;border-bottom:1px solid rgba(249,215,155,.32);padding:8px 0 28px}.report-cover p{max-width:68ch;color:#ead9c9;margin:0}.report-cover h1{font-size:2.5rem;line-height:1.15;margin:10px 0 12px;text-wrap:balance}.report-shell{display:grid;grid-template-columns:156px minmax(0,1fr);gap:18px;align-items:start;margin-top:24px}.report-nav{position:sticky;top:18px;display:grid;gap:5px;padding:10px 0}.report-nav small{color:#ac8970;padding:4px 10px;font-size:.75rem;font-weight:700}.report-nav a{border-left:1px solid rgba(223,199,174,.35);color:#dfc7ae;padding:8px 10px;font-size:.875rem;text-decoration:none}.report-nav a:hover,.report-nav a:focus-visible,.report-nav a[aria-current="location"]{border-left-color:var(--accent);background:#2a170f;color:#fff}.section{scroll-margin-top:18px;background:var(--paper);border:1px solid var(--line);border-radius:8px;padding:28px}.section-header{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;border-bottom:1px solid var(--line);padding-bottom:16px;margin-bottom:24px}.section-header h2{font-size:1.55rem;line-height:1.2;margin:0;text-wrap:balance}.section-header p{color:var(--muted);font-size:.875rem;margin:7px 0 0}.source-label{display:inline-block;color:var(--accent-dark);background:#f7e6cb;padding:4px 7px;border-radius:4px;font-size:.75rem;font-weight:700;white-space:nowrap}.top-material-overall h3,.top-material-brands h3,.brand-difference h3{font-size:1.08rem;margin:0 0 12px}.top-material-overall>p,.brand-panel>p,.brand-difference>p{margin:10px 0;max-width:76ch}.section-divider{height:0;border:0;border-top:1px solid var(--line);margin:32px 0}.brand-tabs{display:flex;gap:0;overflow-x:auto;border-bottom:1px solid var(--line);padding:0 2px}.brand-tab{position:relative;flex:0 0 auto;min-height:42px;border:0;border-radius:0;background:transparent;color:var(--muted);padding:8px 14px;cursor:pointer;white-space:nowrap}.brand-tab:hover{color:var(--accent-dark)}.brand-tab[aria-selected="true"]{color:#5e3820;font-weight:700}.brand-tab[aria-selected="true"]::after{position:absolute;right:12px;bottom:-1px;left:12px;height:2px;background:var(--accent-dark);content:""}.brand-tab:focus-visible{outline:2px solid var(--focus);outline-offset:-2px}.brand-panels{padding:18px 0 0}.brand-panel[hidden]{display:none!important}.brand-panel{border-left:2px solid var(--accent);padding:0 0 0 16px}.brand-difference p{margin-bottom:0}@media(max-width:760px){.report-shell{grid-template-columns:1fr;gap:12px}.report-nav{position:static;display:flex;align-items:center;gap:8px;padding:0}.report-nav small{padding:0}.report-nav a{padding:5px 8px;border-left:0;border-bottom:1px solid rgba(223,199,174,.35)}}@media(max-width:560px){.page{width:min(100% - 20px,1280px);padding-top:18px}.report-cover h1{font-size:2rem}.section{padding:20px}.section-header{display:block}.source-label{margin-top:10px}.brand-tab{padding-inline:10px}.brand-panel{padding-left:12px}}
"""
    style += """
.audience-chart-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.chart-card{container-type:inline-size;border:1px solid var(--line);border-radius:8px;background:#fff;padding:16px}.chart-card h3{font-size:18px;margin:0 0 12px}.audience-chart{min-width:0}.audience-chart-age,.audience-chart-gender{display:flex;flex-direction:column}.audience-chart-crowd{grid-column:1/-1}.audience-pie-layout{display:grid;grid-template-columns:minmax(0,45fr) minmax(0,55fr);flex:1;min-height:0;gap:14px;align-items:center}.pie-chart{position:relative;width:min(260px,100%);aspect-ratio:1;border-radius:50%;display:block;justify-self:center;background:conic-gradient(var(--accent) 0deg,var(--accent) 360deg);box-shadow:0 0 0 1px rgba(82,45,24,.1);cursor:default}.audience-chart-gender .pie-chart{width:min(240px,100%)}.chart-tooltip{position:absolute;z-index:2;left:50%;bottom:calc(100% + 10px);min-width:150px;transform:translateX(-50%);opacity:0;pointer-events:none;padding:10px 12px;border-radius:8px;background:rgba(255,255,255,.96);box-shadow:0 14px 34px rgba(43,23,12,.16);color:var(--ink);font-size:13px;line-height:1.5;transition:opacity .15s ease}.chart-tooltip b{display:block;margin-bottom:4px}.chart-tooltip span{display:block}.chart-tooltip.is-visible,.audience-column-item:hover .chart-tooltip,.audience-column-item:focus .chart-tooltip{opacity:1}.pie-legend{display:grid;gap:8px;margin:0;padding:0;list-style:none}.pie-legend .legend-item{position:relative;display:grid;grid-template-columns:minmax(80px,1fr) auto auto;gap:8px;align-items:center;color:var(--muted);font-size:14px;padding:0;border:0;font-variant-numeric:tabular-nums}.pie-legend .legend-label{display:flex;align-items:center;gap:8px;min-width:0;overflow:visible;white-space:normal;overflow-wrap:anywhere}.legend-swatch{display:block;flex:0 0 12px;width:12px;height:12px;border-radius:3px}.legend-count,.legend-share{white-space:nowrap;text-align:right}.audience-column-chart{position:relative;min-height:250px;display:grid;grid-template-columns:48px minmax(0,1fr);gap:12px;padding-top:8px}.audience-column-y-axis{display:flex;flex-direction:column;justify-content:space-between;align-items:flex-end;padding-bottom:42px;color:var(--muted);font-size:13px;font-variant-numeric:tabular-nums}.audience-column-plot{position:relative;display:grid;align-items:end;gap:12px;min-width:0;padding:0 8px 42px;border-bottom:1px solid rgba(82,45,24,.22);background:repeating-linear-gradient(to top,transparent 0,transparent 72px,rgba(82,45,24,.11) 73px)}.audience-column-item{position:relative;min-width:0;height:170px;display:flex;align-items:end;justify-content:center;outline:0}.audience-column-item:focus-visible{outline:3px solid var(--focus);outline-offset:2px}.audience-column-bar{width:min(64px,72%);min-height:4px;border-radius:8px 8px 0 0;cursor:default}.audience-column-label{position:absolute;left:50%;bottom:-34px;width:76px;transform:translateX(-50%);color:var(--muted);font-size:13px;line-height:1.25;text-align:center;word-break:break-word}.audience-column-item .chart-tooltip{bottom:calc(100% + 10px)}@container (max-width:360px){.audience-pie-layout{grid-template-columns:1fr}.audience-chart .pie-chart,.audience-chart-gender .pie-chart{width:min(240px,100%)!important;height:auto!important;flex-basis:auto!important}.pie-legend{width:100%}}@media(max-width:760px){.audience-chart-grid{grid-template-columns:1fr}.audience-chart-crowd{grid-column:auto}}@media(max-width:560px){.audience-pie-layout{grid-template-columns:1fr}.audience-chart .pie-chart,.audience-chart-gender .pie-chart{width:min(240px,100%)!important;height:auto!important;flex-basis:auto!important}.audience-column-chart{grid-template-columns:38px minmax(0,1fr);gap:8px}.audience-column-y-axis{font-size:11px}.audience-column-plot{gap:4px;padding-inline:2px}.audience-column-label{width:44px;font-size:11px}.audience-column-bar{width:78%}}
"""
    style += """
.data-state{border-left:3px solid var(--accent);padding:16px 18px;background:#fbf0df}.data-state span{color:var(--accent-dark);font-size:.82rem;font-weight:700}.data-state p{max-width:70ch;margin:8px 0 0}.highlight-category{border-top:1px solid var(--line);margin-top:24px;padding-top:22px}.highlight-category h3{font-size:1.12rem;margin:0 0 14px}.highlight-category h4{font-size:.9rem;margin:0 0 8px}.highlight-summary ul{margin:0;padding-left:20px}.highlight-directions{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;margin-top:16px}.highlight-direction{border:1px solid var(--line);border-radius:6px;background:var(--surface);padding:12px}.highlight-direction p{margin:6px 0 0;color:var(--muted);font-size:.875rem}.highlight-frame-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px;margin-top:18px}.highlight-frame-card{margin:0;min-width:0}.highlight-frame-button{display:block;width:100%;border:1px solid var(--line);border-radius:6px;background:var(--surface);padding:4px;cursor:zoom-in}.highlight-frame-button:hover{border-color:var(--accent-dark)}.highlight-frame-button img{display:block;width:100%;aspect-ratio:9/16;object-fit:cover;border-radius:3px}.highlight-frame-card p{margin:6px 0 0;color:var(--muted);font-size:.75rem;line-height:1.45}.highlight-lightbox{position:relative;border:0;border-radius:8px;padding:10px;max-width:min(720px,92vw);background:var(--surface)}.highlight-lightbox::backdrop{background:rgba(13,7,4,.88)}.highlight-lightbox img{display:block;max-width:min(680px,88vw);max-height:80vh}.highlight-lightbox p{margin:7px 2px 0;color:var(--muted);font-size:.8125rem}.highlight-lightbox button{position:absolute;right:12px;top:12px;border:0;border-radius:4px;background:var(--ink);color:#fff;padding:6px 9px;cursor:pointer}@media(max-width:560px){.highlight-frame-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
"""
    style += """
.highlight-dashboard-tabs{display:flex;gap:0;overflow-x:auto;border-bottom:1px solid var(--line);margin-top:16px;padding:0 2px}.highlight-dashboard-tabs button{position:relative;flex:0 0 auto;min-height:42px;border:0;background:transparent;color:var(--muted);padding:8px 14px;cursor:pointer;white-space:nowrap}.highlight-dashboard-tabs button:hover{color:var(--accent-dark)}.highlight-dashboard-tabs button[aria-selected="true"]{color:var(--accent-dark);font-weight:800}.highlight-dashboard-tabs button[aria-selected="true"]::after{position:absolute;right:12px;bottom:-1px;left:12px;height:2px;background:var(--accent-dark);content:""}.highlight-dashboard-tabs button:focus-visible{outline:2px solid var(--focus);outline-offset:-2px}.highlight-dashboard-panels{padding-top:18px}.highlight-category-panel{margin-top:0;padding-top:0;border-top:0}.highlight-category-panel[hidden]{display:none!important}.highlight-category-head{display:flex;align-items:baseline;justify-content:space-between;gap:12px;margin-bottom:14px}.highlight-category-head h3{margin:0}.highlight-category-count{color:var(--muted);font-size:.78rem;font-weight:800}.highlight-analysis-pair{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:12px;margin-bottom:18px}.highlight-summary,.highlight-directions{margin:0;border:1px solid var(--line);border-radius:8px;background:#f7ead8;padding:14px}.highlight-summary li{margin:6px 0}.highlight-directions{display:grid;grid-template-columns:1fr;gap:10px}.highlight-direction{padding:0;border:0;background:transparent}.highlight-frame-grid{margin-top:0}@media(max-width:700px){.highlight-analysis-pair{grid-template-columns:1fr}.highlight-dashboard-tabs button{padding-inline:10px}}
"""
    style += """
.material-deep-tabs{display:flex;gap:0;overflow-x:auto;border-bottom:1px solid var(--line);padding:0 2px}.material-deep-tab{position:relative;flex:0 0 auto;min-height:42px;border:0;border-radius:0;background:transparent;color:var(--muted);padding:8px 14px;cursor:pointer;white-space:nowrap}.material-deep-tab[aria-selected=\"true\"]{color:var(--accent-dark);font-weight:700}.material-deep-tab[aria-selected=\"true\"]::after{position:absolute;right:12px;bottom:-1px;left:12px;height:2px;background:var(--accent-dark);content:\"\"}.material-deep-panel[hidden]{display:none!important}.material-deep-panels{padding-top:18px}.material-deep-header{display:flex;align-items:baseline;gap:10px;border-left:2px solid var(--accent);padding-left:12px}.material-deep-header span{color:var(--accent-dark);font-weight:800}.material-deep-header h3{margin:0;font-size:1.1rem}.material-deep-id{margin:10px 0 0;color:var(--muted);font-size:.78rem}.material-deep-metrics{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px;margin:12px 0 0;padding:0;list-style:none}.material-deep-metrics li{min-width:0;border-top:1px solid var(--line);padding-top:6px}.material-deep-metrics span,.material-deep-metrics b{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.material-deep-metrics span{color:var(--muted);font-size:.7rem}.material-deep-metrics b{font-size:.85rem}.material-deep-panel>h4,.deep-visual-summary h4,.second-level-section>h4{font-size:.95rem;margin:24px 0 10px}.deep-frame-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.deep-frame-card{min-width:0}.deep-frame-card p{margin:6px 0 0;font-size:.78rem;line-height:1.45}.deep-frame-meta{color:var(--muted)}.deep-frame-observation{color:var(--ink)}.deep-visual-summary{border-top:1px solid var(--line);margin-top:22px;padding-top:2px}.deep-visual-summary p{margin:0;max-width:76ch}.second-level-section{border-top:1px solid var(--line);margin-top:22px}.second-level-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.second-level-chart{min-width:0;border:1px solid var(--line);border-radius:6px;background:var(--surface);padding:10px}.second-level-chart h4{margin:0 0 8px;font-size:.875rem}.second-level-chart svg{display:block;width:100%;height:auto}.second-level-axis{stroke:#c6ad95;stroke-width:1}.second-level-line{fill:none;stroke:var(--accent-dark);stroke-width:2.5;stroke-linecap:round;stroke-linejoin:round}.second-level-range.high{fill:rgba(215,154,75,.18)}.second-level-range.loss{fill:rgba(161,79,56,.16)}.second-level-chart text{fill:var(--muted);font-size:10px}.second-level-chart.is-unavailable{display:grid;align-content:start;min-height:122px}.second-level-chart.is-unavailable p{margin:0;color:var(--muted);font-size:.8125rem}.second-level-observations{margin-top:14px}.second-level-observations p{margin:7px 0;font-size:.875rem}@media(max-width:650px){.deep-frame-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.second-level-grid{grid-template-columns:1fr}.material-deep-tab{padding-inline:10px}.material-deep-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:390px){.deep-frame-grid{grid-template-columns:1fr}}
"""
    style += """
.material-deep-layout.side-tabs{display:grid;grid-template-columns:220px minmax(0,1fr);gap:24px;align-items:start}.material-deep-tab-list{position:sticky;top:18px;display:grid;gap:4px;border-right:1px solid var(--line);padding-right:12px}.material-deep-tab{width:100%;min-height:44px;border:0;border-left:2px solid transparent;background:transparent;color:var(--muted);padding:8px 10px;text-align:left;cursor:pointer}.material-deep-tab:hover{color:var(--accent-dark)}.material-deep-tab[aria-selected=\"true\"]{border-left-color:var(--accent-dark);background:#f7e6cb;color:var(--accent-dark);font-weight:700}.material-deep-tab[aria-selected=\"true\"]::after{display:none}.material-deep-panel[hidden]{display:none!important}.material-deep-panels{padding-top:0}.deep-visual-strip{margin-top:22px}.deep-frame-grid.fixed-six{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.deep-frame-card{min-width:0;margin:0}.deep-frame-card .highlight-frame-button{width:100%;border:1px solid var(--line);border-radius:5px;background:var(--surface);padding:4px;cursor:zoom-in}.deep-frame-card .highlight-frame-button:hover{border-color:var(--accent-dark)}.deep-frame-card img{display:block;width:100%;aspect-ratio:9/16;object-fit:contain;background:#1d120c;border-radius:2px}.deep-frame-card figcaption{margin-top:6px;color:var(--muted);font-size:.72rem;line-height:1.35}.deep-frame-coverage{margin:10px 0 0;color:var(--muted);font-size:.78rem}.deep-frame-observations{border-top:1px solid var(--line);margin-top:22px;padding-top:2px}.deep-frame-observations h4{font-size:.95rem;margin:14px 0 10px}.deep-frame-observations ul{margin:0;padding-left:20px}.deep-frame-observations li{margin:6px 0}.second-level-timeline{border:1px solid var(--line);border-radius:6px;background:var(--surface);padding:14px}.second-level-switcher{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:14px}.second-level-switcher button{min-height:34px;border:1px solid var(--line);border-radius:4px;background:transparent;color:var(--muted);padding:5px 8px;cursor:pointer;font-size:.8rem}.second-level-switcher button[aria-pressed=\"true\"]{border-color:var(--accent-dark);background:#f7e6cb;color:var(--accent-dark);font-weight:700}.second-level-chart-mount{min-height:276px}.second-level-chart-mount svg{display:block;width:100%;height:auto}.second-level-axis,.second-level-grid-line{stroke:#c6ad95;stroke-width:1}.second-level-grid-line{stroke-dasharray:3 4}.second-level-line{fill:none;stroke:var(--accent-dark);stroke-width:2.5;stroke-linecap:round;stroke-linejoin:round}.second-level-range.high{fill:rgba(215,154,75,.18)}.second-level-range.loss{fill:rgba(161,79,56,.16)}.second-level-point{fill:var(--accent-dark);cursor:help}.second-level-point:focus{outline:none;stroke:var(--ink);stroke-width:3}.second-level-tooltip{fill:var(--surface);stroke:var(--line-dark)}.second-level-chart-mount text{fill:var(--muted);font-size:11px}.second-level-range-control{display:flex;align-items:center;gap:10px;margin-top:8px;color:var(--muted);font-size:.8rem}.second-level-range-control input{flex:1;accent-color:var(--accent-dark)}.second-level-peak-note{margin:10px 0 0;color:var(--accent-dark);font-size:.82rem;font-weight:700}.second-level-observations{margin-top:14px}.second-level-observations p{margin:7px 0;font-size:.875rem}
"""
    style += """
.material-deep-layout.side-tabs{display:grid;grid-template-columns:190px minmax(0,1fr);gap:18px;align-items:stretch}.material-deep-tab-list{position:sticky;top:18px;align-self:stretch;display:flex;flex-direction:column;gap:9px;max-height:calc(100vh - 36px);overflow-y:auto;border-right:1px solid var(--line);padding:0 14px 0 0}.material-deep-tab{width:100%;min-height:0;border:1px solid var(--line);border-radius:8px;background:#fff8ec;color:var(--ink);padding:8px 9px;text-align:left;font-size:12px;line-height:1.35;white-space:normal}.material-deep-tab[aria-selected=\"true\"]{border-color:#2c1810;border-left-color:#2c1810;background:#2c1810;color:#fff}.material-deep-panels{min-width:0;padding:0}.material-deep-panel.material-card{margin:0;padding:22px;border:1px solid var(--line);border-radius:24px;background:#fffdf9;box-shadow:0 16px 40px rgba(65,34,16,.1)}.material-deep-header.material-head{display:block;border:0;padding:0}.material-deep-header.material-head span{display:block;margin:0 0 14px;color:var(--accent-dark);font-size:12px;font-weight:800;letter-spacing:.14em}.material-deep-header.material-head h3{margin:0 0 10px;font-size:24px;line-height:1.35}.material-deep-id{margin:0;color:var(--muted);font-size:14px}.material-deep-metrics{margin:14px 0 0}.deep-visual-strip{--visual-height:560px;margin:18px 0}.deep-frame-grid.fixed-six{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));grid-template-rows:repeat(2,minmax(0,1fr));gap:12px;height:var(--visual-height);margin:0}.deep-frame-card{display:grid;grid-template-rows:minmax(0,1fr) auto;overflow:hidden;border:1px solid var(--line);border-radius:18px;background:#f4e3cd}.deep-frame-card .highlight-frame-button{display:block;width:100%;min-width:0;min-height:0;padding:0;border:0;border-radius:0;background:transparent}.deep-frame-card img{width:100%;height:100%;min-height:0;aspect-ratio:auto;object-fit:contain;background:#efe6d9;border-radius:0}.deep-frame-card figcaption{margin:0;padding:10px 12px;color:var(--muted);font-size:13px;line-height:1.45}.deep-frame-coverage{margin:10px 0 0;color:var(--muted);font-size:13px}.deep-frame-observations,.deep-visual-summary{margin-top:18px;padding:17px;border:1px solid var(--line);border-radius:18px;background:#f7ead8}.deep-frame-observations h4,.deep-visual-summary h4,.second-level-section>h4{margin:0 0 10px;font-size:16px}.second-level-section{margin-top:18px}.second-level-timeline.raw-fact-card{padding:17px;border:1px solid var(--line);border-radius:18px;background:#fff}.collapsible-head{margin-bottom:12px}.collapsible-toggle{display:flex;align-items:center;justify-content:center;width:100%;border:1px solid var(--line);border-radius:12px;background:#f7ead8;color:var(--ink);padding:12px 14px;cursor:pointer;font:inherit;text-align:center;box-shadow:inset 0 1px 0 rgba(255,255,255,.52)}.collapsible-toggle:hover{border-color:rgba(82,45,24,.24);background:#fff1dc}.collapsible-toggle-action{color:#2c1810;font-size:16px;font-weight:800;line-height:1.35;white-space:nowrap}.collapsible-body{display:grid;gap:12px}.collapsible-body[hidden]{display:none}.collapsible-body-title{display:block;margin-bottom:2px;color:var(--ink);font-size:16px;font-weight:800;line-height:1.35}.second-level-switcher.metric-switch{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:0}.second-level-switcher button{border-radius:8px;background:#fff8ec;color:var(--ink);font-size:12px;font-weight:800}.second-level-switcher button[aria-pressed=\"true\"]{border-color:#2c1810;background:#2c1810;color:#fff}.second-level-chart-mount{min-height:320px}.second-level-chart-mount svg,.timeline-chart{display:block;width:100%;height:320px;border:1px solid rgba(82,45,24,.1);border-radius:14px;background:#fff8ec}.second-level-axis,.second-level-grid-line{stroke:rgba(82,45,24,.16);stroke-width:1}.second-level-grid-line{stroke-dasharray:3 4}.second-level-line.timeline-line{fill:none;stroke:#9b6a37;stroke-width:3;stroke-linecap:round;stroke-linejoin:round}.second-level-point.timeline-point-dot{fill:#9b6a37;stroke:#fff8ec;stroke-width:2}.second-level-point-hitbox{cursor:default}.second-level-tooltip{opacity:0;pointer-events:none;transition:opacity .12s ease}.second-level-point-hitbox:hover .second-level-tooltip,.second-level-point-hitbox:focus .second-level-tooltip{opacity:1}.second-level-tooltip rect{fill:rgba(255,255,255,.96);stroke:rgba(82,45,24,.16)}.second-level-tooltip-title{fill:#2a170f;font-size:12px;font-weight:800}.second-level-tooltip-value{fill:#806758;font-size:12px}.second-level-range.high{fill:rgba(215,154,75,.18)}.second-level-range.loss{fill:rgba(161,79,56,.16)}.second-level-range-control{display:grid;grid-template-columns:max-content minmax(0,1fr);align-items:center;gap:10px;margin-top:0;color:var(--muted);font-size:13px}.second-level-range-control input{width:100%;height:8px;accent-color:#9b6a37;cursor:pointer}.second-level-peak-note{margin:0;color:var(--ink);font-weight:800}.second-level-observations{margin-top:14px}.audience-dashboard{display:grid;gap:12px}.audience-topn-controls{display:flex;flex-wrap:wrap;align-items:center;gap:10px;padding:10px 12px;border:1px solid var(--line);border-radius:8px;background:#fbf0df;color:var(--muted);font-size:13px}.audience-topn-controls label{display:flex;align-items:center;gap:6px;color:var(--ink);font-weight:700}.audience-topn-controls input[type=\"number\"]{width:84px;border:1px solid var(--line);border-radius:5px;padding:6px 8px;background:#fff}.audience-topn-controls input[type=\"range\"]{flex:1;min-width:180px;accent-color:#9b6a37}.audience-topn-controls [data-audience-topn-label]{font-weight:700;color:var(--accent-dark)}.highlight-dashboard-tabs{display:flex;flex-wrap:wrap;gap:8px;border-bottom:0;margin-top:16px;padding:0}.highlight-dashboard-tabs button{position:relative;flex:0 0 auto;min-height:40px;border:1px solid var(--line);border-radius:999px;background:#f7ead8;color:var(--muted);padding:8px 12px;cursor:pointer;white-space:nowrap}.highlight-dashboard-tabs button:hover{color:var(--accent-dark);border-color:var(--accent-dark)}.highlight-dashboard-tabs button[aria-selected=\"true\"]{border-color:var(--accent-dark);background:#2c1810;color:#fff;font-weight:800}.highlight-dashboard-tabs button[aria-selected=\"true\"]::after{display:none}.highlight-dashboard-tabs button:focus-visible{outline:2px solid var(--focus);outline-offset:2px}.highlight-dashboard-panels{padding-top:18px}.highlight-category-panel{margin-top:0;padding-top:0;border-top:0}.highlight-category-panel[hidden]{display:none!important}.highlight-category-head{display:flex;align-items:baseline;justify-content:space-between;gap:12px;margin-bottom:14px}.highlight-category-head h3{margin:0}.highlight-category-count{color:var(--muted);font-size:.78rem;font-weight:800}.highlight-analysis-pair{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:12px;margin-bottom:18px}.highlight-summary,.highlight-directions{margin:0;border:1px solid var(--line);border-radius:8px;background:#f7ead8;padding:14px}.highlight-summary li{margin:6px 0}.highlight-directions{display:grid;grid-template-columns:1fr;gap:10px}.highlight-direction{padding:0;border:0;background:transparent}.highlight-frame-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-top:0}.highlight-frame-card{margin:0;min-width:0;display:grid;gap:8px}.highlight-frame-card figure{margin:0}.highlight-frame-card .highlight-frame-button{display:block;width:100%;border:1px solid var(--line);border-radius:6px;background:var(--surface);padding:4px;cursor:zoom-in}.highlight-frame-card .highlight-frame-button:hover{border-color:var(--accent-dark)}.highlight-frame-card img{display:block;width:100%;aspect-ratio:9/16;object-fit:cover;border-radius:3px}.highlight-frame-meta{display:grid;gap:4px;color:var(--muted);font-size:.75rem;line-height:1.4}.highlight-frame-meta small{font-size:.72rem;font-weight:800;color:var(--accent-dark)}.highlight-frame-meta span{font-variant-numeric:tabular-nums}.highlight-source-link{border:0;background:transparent;color:var(--accent-dark);padding:0;text-align:left;font:inherit;cursor:pointer}.highlight-source-link:hover{text-decoration:underline}.highlight-pagination{display:flex;justify-content:center;align-items:center;gap:10px;margin-top:14px}.highlight-pagination button{min-height:34px;border:1px solid var(--line);border-radius:999px;background:#fff8ec;color:var(--ink);padding:6px 12px;cursor:pointer}.highlight-pagination button[disabled]{opacity:.45;cursor:not-allowed}.highlight-pagination [data-highlight-page-status]{min-width:64px;text-align:center;color:var(--muted);font-size:13px;font-variant-numeric:tabular-nums}@media(max-width:700px){.highlight-analysis-pair{grid-template-columns:1fr}.highlight-frame-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.highlight-dashboard-tabs button{padding-inline:10px}.audience-topn-controls{align-items:stretch}.audience-topn-controls input[type=\"range\"]{min-width:0;width:100%}}@media(max-width:560px){.deep-frame-grid.fixed-six{grid-template-columns:repeat(2,minmax(0,1fr));grid-template-rows:repeat(4,minmax(0,1fr));height:auto}.highlight-frame-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.highlight-pagination{flex-wrap:wrap}}
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
        source_detail=source_label("成功秒级拆解素材"),
        source_derived=source_label("TOP1000 + 成功秒级拆解素材派生"),
        top_material_combination=top_material_combination,
        audience_insights=audience_insights,
        script_insights=script_insights,
        highlight_insights=highlight_insights,
        material_deep_dive=material_deep_dive,
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


def render_report(
    *,
    analysis_json,
    output_dir,
    fact_pack=None,
    analysis_provenance=None,
    highlight_asset_root=None,
):
    analysis = _load_analysis(analysis_json)
    fact_pack = fact_pack or {}
    _validate_highlight_dashboard(analysis, fact_pack)
    _validate_material_deep_dives(analysis, fact_pack)
    _validate_experiment_fact_references(analysis, fact_pack)
    data = {"status": "complete", "analysis": analysis}
    if analysis_provenance is not None:
        data["analysisProvenance"] = analysis_provenance
    data["highlightFrames"] = {
        frame["frame_ref"]: frame for frame in _overview_highlight_frames(fact_pack)
    }
    audience_dashboard = fact_pack.get("audienceDashboard") if isinstance(fact_pack, dict) else None
    markdown = _render_markdown(analysis, audience_dashboard, fact_pack)
    rendered_html = _render_html(
        analysis, _material_frames(fact_pack), fact_pack
    )
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    _copy_highlight_assets(fact_pack, output, highlight_asset_root)
    write_json_atomically(data, output / "final-report-data.json")
    (output / "final-report.md").write_text(markdown, encoding="utf-8")
    (output / "final-report.html").write_text(rendered_html, encoding="utf-8")
    return 0
