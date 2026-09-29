"""Render final Yuntu analysis reports from model-authored JSON."""

import html
import json
from yuntu_analysis_quality import enabled as quality_enabled
import math
import re
import shutil
from collections import Counter
from pathlib import Path
from string import Template

from rpa_io import write_json_atomically
from yuntu_highlights import find_local_video_asset
from yuntu_presentation import build_yuntu_presentation, _chapter05_script_projection
from yuntu_highlight_export import export_highlight_workbook, match_brands_from_title
from yuntu_top_materials import aggregate_scope_label, configured_brands
from yuntu_report_sections import (
    _chapter01_baseline_metric_value,
    _chapter01_current_metric_value,
    _chapter01_rate_against_current,
    _format_chapter01_exposure,
    _format_chapter01_percentage,
    render_audience_insights,
    render_highlight_insights,
    render_material_deep_dive,
    render_script_insights,
    render_top_material_combination,
)


SKILL_ROOT = Path(__file__).resolve().parents[1]
HTML_TEMPLATE_PATH = Path(__file__).with_name("templates") / "final-report-template.html"
REPORT_STYLE_PATH = SKILL_ROOT / "assets" / "report" / "unified-report.css"
REPORT_SCRIPT_PATH = SKILL_ROOT / "assets" / "report" / "unified-report.js"
CURRENT_REPORT_SECTIONS = (
    ("top_material_combination", "top-material-combination", "01｜素材榜单数据洞察"),
    ("audience_insights", "audience-insights", "02｜人群及营销卖点洞察"),
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
        "$top_material_scope",
        "$highlight_scope",
        "$highlight_export",
        "$material_deep_dive_scope",
        *(f"${name}" for name, _section_id, _title in CURRENT_REPORT_SECTIONS),
    ):
        if len(re.findall(re.escape(placeholder) + r"(?![A-Za-z0-9_])", source)) != 1:
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
)
AUDIENCE_DIMENSION_LABELS = {
    "age": "年龄",
    "gender": "性别",
    "crowd": "八大人群",
}
HIGHLIGHT_CATEGORY_LABELS = {
    "portrait": "人像画面",
    "product": "产品画面",
    "scene": "其他画面",
    "text_overlay": "其他画面",
    "other": "其他画面",
}
HIGHLIGHT_CATEGORY_ORDER = tuple(HIGHLIGHT_CATEGORY_LABELS)
HIGHLIGHT_RENDER_CATEGORY_ORDER = ("portrait", "product", "other")
SECOND_LEVEL_TRENDS = ("点赞指数", "流失指数", "点击指数", "互动指数", "评论指数")
AI_PLACEHOLDER_TEXT = (
    "事实包返回",
    "该素材用于观察",
    "该指数记录",
    "该帧为封面或点击指数局部峰值秒点的已提取画面",
)
AUDIT_JSON_PATTERN = re.compile(r'(?:\[\s*)?\{\s*"[^"\n]+"\s*:')
DEEP_DIVE_FORBIDDEN_CLAIM = re.compile(
    r"脚本|话术|内容公式|真实(?:点击|互动|点赞|评论)(?:量|次数)?|"
    r"转化(?:率|量|次数|效果)|(?:导致|带来).{0,12}(?:曝光|点击|互动|点赞|评论|转化)|"
    r"(?:曝光|点击|互动|点赞|评论|转化)(?:率|量|次数|指数)?.{0,8}(?:提升|下降)"
)
SCRIPT_INSIGHT_FORBIDDEN_CLAIM = re.compile(
    r"导致|提升|因果|行业(?:普遍|规律)|帧[-—]?话术|话术[-—]?帧|秒点.{0,8}话术|话术.{0,8}秒点|convertCnt.{0,8}订单|订单.{0,8}convertCnt"
)
# Exempt only complete, explicit scope-limitation clauses, not the whole summary.
# Other claims in the same paragraph must still pass the existing gate.
SCRIPT_SCOPE_LIMITATION = re.compile(
    r"(?:^|[，。；！？\n])(?:当前|本批次)?(?:样本|数据|证据|覆盖)?"
    r"(?:尚)?(?:不足以支持|不足以代表|不能代表|不能外推为|无法推断|不能据此推断)"
    r"(?:行业普遍(?:结论|规律)|行业规律|因果关系)(?=$|[，。；！？\n])"
)
SCRIPT_ANALYSIS_FORBIDDEN_CLAIM = re.compile(
    r"标题|画面|高光帧|秒级|曝光(?:量|次数|指数)?|"
    r"点击(?:率|量|次数|指数|高点|峰值|波峰)|互动(?:率|量|次数|指数)|"
    r"评论(?:率|量|次数|指数)|转化(?:率|量|次数|效果)|波峰|流失"
)


def _load_analysis(
    path, *, require_people_summary=True, strict_top_material_contract=False,
    zero_sample_brands=(),
):
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
    _validate_top_material_combination(
        analysis["topMaterialCombination"],
        require_people_summary=require_people_summary,
        strict_contract=strict_top_material_contract,
        zero_sample_brands=zero_sample_brands,
    )
    if "chapter02Insights" in analysis:
        analysis["chapter02Insights"] = _normalize_chapter02_insights(
            analysis["chapter02Insights"]
        )
        # Scope availability and evidence are checked with canonical facts in
        # validate_analysis_input; a fact-free pass rejects valid empty scopes.
    return analysis


def validate_analysis_input(*, analysis_json, fact_pack=None):
    """Validate model analysis against the same contracts used by rendering."""
    fact_pack = fact_pack or {}
    require_people_summary = False
    strict_top_material_contract = (
        isinstance(fact_pack, dict) and fact_pack.get("schemaVersion", 0) >= 6
    )
    analysis = _load_analysis(
        analysis_json,
        require_people_summary=require_people_summary,
        strict_top_material_contract=strict_top_material_contract,
        zero_sample_brands=_zero_sample_brands(fact_pack),
    )
    return validate_analysis_data(analysis, fact_pack)


def validate_analysis_data(analysis, fact_pack):
    """Validate the assembled value before writing or attesting any artifact."""
    if quality_enabled(fact_pack):
        from yuntu_analysis import _analysis_output_schema
        from jsonschema import Draft202012Validator
        errors = sorted(Draft202012Validator(_analysis_output_schema(fact_pack)).iter_errors(analysis), key=lambda e: str(e.json_path))
        if errors:
            raise YuntuReportError("; ".join(f"{e.json_path}: {e.message}" for e in errors))
    _validate_ranking_scope_contract(analysis, fact_pack)
    if "chapter02Insights" in analysis:
        _validate_chapter02_insights(
            analysis["chapter02Insights"], fact_pack=fact_pack
        )
    _validate_period_and_hot_material_contract(analysis, fact_pack)
    _validate_script_insights(analysis, fact_pack)
    _validate_highlight_dashboard(analysis, fact_pack)
    _validate_material_deep_dives(analysis, fact_pack)
    return analysis


def _validate_script_insights(analysis, fact_pack):
    if "scriptInsights" not in analysis:
        return
    insights = analysis.get("scriptInsights")
    if not isinstance(insights, list):
        raise YuntuReportError("scriptInsights must be a list")
    facts = fact_pack.get("scriptFacts", {}) if isinstance(fact_pack, dict) else {}
    strict_script_contract = isinstance(facts, dict) and "keywordCloud" in facts
    if strict_script_contract and len(insights) != 2:
        raise YuntuReportError("scriptInsights must contain exactly two dimensions")
    known_ids = {
        str(item.get("material_id"))
        for item in facts.get("materials", [])
        if isinstance(item, dict) and str(item.get("material_id") or "").isdigit()
    }
    if not known_ids and not strict_script_contract:
        known_ids = {
            str(item.get("material_id"))
            for item in fact_pack.get("selectedMaterials", [])
            if isinstance(item, dict) and str(item.get("material_id") or "").isdigit()
        }
    errors = []
    for index, item in enumerate(insights, start=1):
        field = f"script insight {index}"
        if not isinstance(item, dict):
            raise YuntuReportError(f"{field} must be an object")
        if set(item) - {"title", "summary", "evidence", "material_ids"}:
            raise YuntuReportError(f"{field} contains unsupported fields")
        _validate_summary(item.get("title"), f"{field}.title")
        _validate_summary(item.get("summary"), f"{field}.summary")
        evidence = item.get("evidence")
        if quality_enabled(fact_pack) and not facts.get("coverage", {}).get("script"):
            if evidence != [] or not set(item.get("material_ids", [])).issubset(known_ids):
                raise YuntuReportError(f"{field}: unavailable script scope requires empty evidence")
            continue
        if not isinstance(evidence, list) or not evidence:
            raise YuntuReportError(f"{field} must include evidence")
        material_ids = item.get("material_ids")
        if not isinstance(material_ids, list) or not material_ids or any(
            not isinstance(value, str) or not value.isdigit() for value in material_ids
        ):
            raise YuntuReportError(f"{field} must include material IDs")
        if not set(material_ids).issubset(known_ids):
            raise YuntuReportError(f"{field} references unknown material IDs")
        if quality_enabled(fact_pack):
            scoped_materials = [m for m in facts.get("materials", []) if str(m.get("material_id")) in material_ids]
            source_parts = []
            for material in scoped_materials:
                formula = material.get("content_formula") or {}
                script_source = formula.get("sources", {}).get("script", {}) if isinstance(formula, dict) else {}
                labels = formula.get("labels", []) if isinstance(formula, dict) else []
                source_parts.extend([str(material.get("script_text") or ""), json.dumps(labels, ensure_ascii=False), json.dumps(script_source.get("detail", {}), ensure_ascii=False)])
            source_text = "\n".join(source_parts)
            if any(not isinstance(e, str) or not e.strip() or e not in source_text for e in evidence):
                errors.append(f"{field}.evidence must quote the cited materials' script or formula facts")
        claim_text = SCRIPT_SCOPE_LIMITATION.sub("", item["summary"])
        unsupported = SCRIPT_INSIGHT_FORBIDDEN_CLAIM.search(claim_text)
        if unsupported:
            errors.append(
                f"{field}.summary contains unsupported claim: {unsupported.group(0)}"
            )
        if strict_script_contract:
            expected_prefix = "一二级内容公式：" if index == 1 else "脚本文案："
            if not item["title"].startswith(expected_prefix):
                errors.append(f"{field}.title must start with {expected_prefix}")

    if errors:
        raise YuntuReportError('\n'.join(errors))

    if strict_script_contract:
        _validate_keyword_cloud_analysis(analysis, facts)
    if quality_enabled(fact_pack) and "brandScopeOrder" in facts and "scriptBrandInsights" in analysis:
        scoped = analysis.get("scriptBrandInsights", {})
        if set(scoped) != set(facts["brandScopeOrder"]):
            raise YuntuReportError("scriptBrandInsights must cover every configured brand")
        for brand in facts["brandScopeOrder"]:
            _validate_script_insights(scoped[brand], {**fact_pack, "scriptFacts": facts["brandScopes"][brand], "selectedMaterials": []})


def _validate_keyword_cloud_analysis(analysis, script_facts):
    cloud = script_facts.get("keywordCloud", {})
    raw_keywords = cloud.get("keywords", []) if isinstance(cloud, dict) else []
    if not isinstance(raw_keywords, list):
        raise YuntuReportError("keywordCloud keywords must be a list")
    candidates = {
        str(item.get("keyword")): item
        for item in raw_keywords
        if isinstance(item, dict) and str(item.get("keyword") or "").strip()
    }
    candidate_refs = {
        str(ref)
        for item in candidates.values()
        for ref in item.get("evidenceRefs", [])
        if str(ref).strip()
    }
    review = analysis.get("keywordCloudReview")
    if not isinstance(review, list):
        raise YuntuReportError("keywordCloudReview must be a list")
    reviewed_keywords = set()
    merge_targets = set()
    for index, item in enumerate(review, start=1):
        field = f"keyword cloud review {index}"
        if not isinstance(item, dict) or set(item) - {"keyword", "decision", "target"}:
            raise YuntuReportError(f"{field} is invalid")
        keyword = str(item.get("keyword") or "").strip()
        decision = str(item.get("decision") or "").strip()
        target = str(item.get("target") or "").strip()
        if keyword not in candidates:
            raise YuntuReportError(f"{field} references unknown keyword")
        if keyword in reviewed_keywords:
            raise YuntuReportError(f"{field} duplicates keyword")
        if decision not in {"accept", "exclude", "merge"}:
            raise YuntuReportError(f"{field} has invalid decision")
        if decision == "merge" and not target:
            raise YuntuReportError(f"{field} merge target is required")
        if decision != "merge" and target:
            raise YuntuReportError(f"{field} target is only allowed for merge")
        reviewed_keywords.add(keyword)
        if decision == "merge":
            merge_targets.add(target)

    review_by_keyword = {
        str(item.get("keyword")): item
        for item in review
        if isinstance(item, dict)
    }
    projected_keywords = {
        keyword for keyword in candidates
        if review_by_keyword.get(keyword, {}).get("decision", "accept") != "exclude"
    } | merge_targets
    projected_evidence_by_keyword = {}
    for keyword, item in candidates.items():
        decision = review_by_keyword.get(keyword, {}).get("decision", "accept")
        projected = review_by_keyword.get(keyword, {}).get("target", "") if decision == "merge" else keyword
        if decision != "exclude":
            projected_evidence_by_keyword.setdefault(projected, set()).update(
                str(ref) for ref in item.get("evidenceRefs", []) if str(ref).strip()
            )
    insight = analysis.get("keywordCloudInsight")
    if not isinstance(insight, dict) or set(insight) - {"oneSentenceConclusion", "summary", "sellingPoints"}:
        raise YuntuReportError("keywordCloudInsight is invalid")
    _validate_summary(insight.get("oneSentenceConclusion"), "keywordCloudInsight.oneSentenceConclusion")
    _validate_summary(insight.get("summary"), "keywordCloudInsight.summary")
    selling_points = insight.get("sellingPoints")
    if not isinstance(selling_points, list) or len(selling_points) > 4:
        raise YuntuReportError("keywordCloudInsight.sellingPoints must contain at most four items")
    if projected_keywords and not selling_points:
        raise YuntuReportError("keywordCloudInsight.sellingPoints is required when keywords remain")
    for index, item in enumerate(selling_points, start=1):
        field = f"keyword cloud selling point {index}"
        if not isinstance(item, dict) or set(item) - {"title", "description", "keywordRefs", "evidenceRefs"}:
            raise YuntuReportError(f"{field} is invalid")
        _validate_summary(item.get("title"), f"{field}.title")
        _validate_summary(item.get("description"), f"{field}.description")
        keyword_refs = item.get("keywordRefs")
        evidence_refs = item.get("evidenceRefs")
        if not isinstance(keyword_refs, list) or not keyword_refs or any(
            not isinstance(ref, str) or ref not in projected_keywords for ref in keyword_refs
        ):
            raise YuntuReportError(f"{field} keywordRefs are invalid")
        if not isinstance(evidence_refs, list) or not evidence_refs or any(
            not isinstance(ref, str) or ref not in candidate_refs for ref in evidence_refs
        ):
            raise YuntuReportError(f"{field} evidenceRefs are invalid")
        allowed_refs = set().union(*(projected_evidence_by_keyword.get(ref, set()) for ref in keyword_refs))
        if not set(evidence_refs).issubset(allowed_refs):
            raise YuntuReportError(f"{field} evidenceRefs must belong to keywordRefs")


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


def _validate_ai_text(value, field, _quality_key):
    _validate_deep_dive_text(value, field)
    if any(token in value for token in AI_PLACEHOLDER_TEXT):
        raise YuntuReportError(f"{field} contains placeholder text")


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


def _validate_top_material_combination(
    value, *, require_people_summary=True, strict_contract=False,
    zero_sample_brands=(),
):
    if not isinstance(value, dict):
        raise YuntuReportError("topMaterialCombination must be an object")
    if strict_contract and not set(value).issubset({"brandConclusions", "allBrandsConclusion"}):
        raise YuntuReportError(
            "topMaterialCombination must only include brandConclusions or allBrandsConclusion"
        )
    brands = value.get("brandConclusions")
    if not isinstance(brands, list):
        raise YuntuReportError("topMaterialCombination.brandConclusions must be a list")
    for item in brands:
        if not isinstance(item, dict):
            raise YuntuReportError("topMaterialCombination.brandConclusions items must be objects")
        if not isinstance(item.get("brand"), str) or not item["brand"].strip():
            raise YuntuReportError("topMaterialCombination.brandConclusions items must include brand")
        if item.get("classificationSource") not in {"title_rule", "runtime_title_rule"}:
            raise YuntuReportError("topMaterialCombination.brandConclusions classificationSource must be a title classification rule")
        _validate_summary(
            item.get("dataSummary"),
            "topMaterialCombination.brandConclusions dataSummary",
        )
        if require_people_summary or "peopleSummary" in item:
            _validate_summary(
                item.get("peopleSummary"),
                "topMaterialCombination.brandConclusions peopleSummary",
            )
        if item["brand"] in zero_sample_brands:
            if item.get("evidence") != [] or item.get("material_ids") != []:
                raise YuntuReportError(f"zero-sample brand {item['brand']} must keep evidence and material_ids empty")
            if "数据不足" not in item["dataSummary"]:
                raise YuntuReportError(f"empty brand conclusion must explain 数据不足 for {item['brand']}")
        else:
            _validate_evidence_and_material_ids(
                item, "topMaterialCombination.brandConclusions items"
            )
    aggregate = value.get("allBrandsConclusion")
    if aggregate is not None:
        if not isinstance(aggregate, dict) or aggregate.get("brand") != "全品牌":
            raise YuntuReportError("topMaterialCombination.allBrandsConclusion must be the 全品牌 aggregate")
        if aggregate.get("classificationSource") not in {"title_rule", "runtime_title_rule", "scope_aggregate"}:
            raise YuntuReportError("topMaterialCombination.allBrandsConclusion classificationSource is invalid")
        _validate_summary(aggregate.get("dataSummary"), "topMaterialCombination.allBrandsConclusion dataSummary")
        _validate_evidence_and_material_ids(aggregate, "topMaterialCombination.allBrandsConclusion")


def _brand_ranking_facts(fact_pack):
    if not isinstance(fact_pack, dict):
        return {}
    facts = fact_pack.get("brandRankingFacts")
    if isinstance(facts, dict):
        return facts
    legacy_facts = fact_pack.get("brandTopNFacts")
    return legacy_facts if isinstance(legacy_facts, dict) else {}


def _zero_sample_brands(fact_pack):
    if not isinstance(fact_pack, dict):
        return set()
    brand_facts = _brand_ranking_facts(fact_pack).get("brands", {})
    brand_facts = brand_facts if isinstance(brand_facts, dict) else {}
    empty = {
        brand for brand, scope in brand_facts.items()
        if isinstance(scope, dict) and scope.get("sample_count") == 0
    }
    comparison_facts = fact_pack.get("comparisonFacts")
    comparison = comparison_facts.get("scopes", {}) if isinstance(comparison_facts, dict) else {}
    if isinstance(comparison, dict):
        empty.update(
            brand for brand, scope in comparison.items()
            if brand not in brand_facts and isinstance(scope, dict)
            and isinstance(scope.get("current"), dict)
            and scope["current"].get("sampleCount") == 0
        )
    return empty


def _normalized_semantic_text(value):
    """Compare model prose without allowing seconds/spacing to hide a template."""
    return re.sub(r"[0-9０-９\s，。；、：:（）()【】\-—_]+", "", str(value or ""))


def _validate_chapter02_insights(value, fact_pack=None):
    if not isinstance(value, dict):
        raise YuntuReportError("chapter02Insights must be an object")
    order = value.get("scopeOrder")
    scopes = value.get("scopes")
    if not isinstance(order, list) or not order or order[0] != "all":
        raise YuntuReportError("chapter02Insights.scopeOrder must start with all")
    if not isinstance(scopes, dict) or set(order) != set(scopes):
        raise YuntuReportError("chapter02Insights.scopes must match scopeOrder")
    seen_by_dimension = {"audienceSummary": set(), "marketingSummary": set()}
    scope_facts = fact_pack.get("chapter02AiFacts", {}) if isinstance(fact_pack, dict) else {}
    # Empty renderer projections must be hydrated from the model input unit.
    # Chart scopes may deliberately differ and cannot authorize AI references.
    if isinstance(scope_facts, dict) and any(
        not isinstance(scope_facts.get(scope), dict) or "sampleCount" not in scope_facts[scope]
        for scope in scope_facts.get("scopeOrder", [])
    ):
        raise YuntuReportError("chapter02Insights requires canonical audience-marketing facts from the analysis manifest")
    expected_order = scope_facts.get("scopeOrder") if isinstance(scope_facts, dict) else None
    if expected_order and order != expected_order:
        raise YuntuReportError("chapter02Insights.scopeOrder must match fact scopeOrder exactly")
    for scope_key in order:
        scope = scopes[scope_key]
        if not isinstance(scope, dict):
            raise YuntuReportError("chapter02Insights scopes must be objects")
        for field in ("audienceSummary", "marketingSummary"):
            summary = scope.get(field)
            if summary is None:
                raise YuntuReportError(f"chapter02Insights {scope_key} must include {field}")
            if not isinstance(summary, dict):
                raise YuntuReportError(f"chapter02Insights {scope_key} {field} must be an object")
            if not isinstance(summary.get("title"), str) or not summary["title"].strip():
                raise YuntuReportError(f"chapter02Insights {scope_key} {field} title is required")
            if summary.get("summary") not in (None, ""):
                _validate_summary(summary.get("summary"), f"chapter02Insights {field} summary")
            if not isinstance(fact_pack, dict) or "chapter02AiFacts" not in fact_pack:
                _validate_evidence_and_material_ids(summary, f"chapter02Insights {field}")
                continue
            scope_fact = scope_facts.get(scope_key, {})
            sample_count = scope_fact.get("sampleCount") if isinstance(scope_fact, dict) else None
            known_ids = {
                str(item.get("material_id")) for item in scope_fact.get("topMaterials", [])
                if isinstance(item, dict) and str(item.get("material_id") or "")
            } if isinstance(scope_fact, dict) else set()
            evidence, material_ids = summary.get("evidence"), summary.get("material_ids")
            if sample_count == 0 or (isinstance(scope_fact, dict) and scope_fact.get("availability") == "unavailable"):
                if evidence != [] or material_ids != []:
                    raise YuntuReportError(f"chapter02Insights {scope_key} unavailable scope must not cite evidence")
                if not str(summary.get("summary") or "").strip():
                    raise YuntuReportError(f"chapter02Insights {scope_key} unavailable scope requires a reason")
                continue
            if not isinstance(evidence, list) or not evidence or not isinstance(material_ids, list) or not material_ids:
                raise YuntuReportError(f"chapter02Insights {scope_key} {field} requires scoped evidence")
            if not set(material_ids).issubset(known_ids):
                raise YuntuReportError(f"chapter02Insights {scope_key} {field} references material outside scope")
            normalized = _normalized_semantic_text(summary.get("summary"))
            if normalized in seen_by_dimension[field]:
                raise YuntuReportError(f"chapter02Insights {field} must differ across nonempty scopes")
            seen_by_dimension[field].add(normalized)
def _normalize_chapter02_insights(value):
    """Adapt attested pre-tab chapter 02 insights without changing their source file."""
    if not isinstance(value, dict) or not isinstance(value.get("scopes"), dict):
        return value
    normalized = {**value, "scopes": {}}
    legacy_fields = {
        "audience": ("audienceInsights", "audienceAnalysis", "人群洞察"),
        "marketing": ("marketingInsights", "marketingAnalysis", "营销卖点洞察"),
    }
    for scope_key, scope in value["scopes"].items():
        if not isinstance(scope, dict):
            normalized["scopes"][scope_key] = scope
            continue
        converted = dict(scope)
        for dimension, (target, legacy, default_title) in legacy_fields.items():
            legacy_section = converted.get(legacy)
            legacy_items = legacy_section.get("insights") if isinstance(legacy_section, dict) else None
            if target not in converted and isinstance(legacy_items, list):
                converted[target] = [{
                    "title": item.get("title"), "summary": item.get("conclusion"),
                    "evidence": item.get("evidence"), "material_id": item.get("material_id"),
                    "material_ids": item.get("material_ids"), "dimension": item.get("title"),
                } for item in legacy_items if isinstance(item, dict)]
            summary_field = f"{dimension}Summary"
            if summary_field not in converted and isinstance(legacy_section, dict):
                material_ids, evidence = [], []
                for item in legacy_items if isinstance(legacy_items, list) else []:
                    if isinstance(item, dict):
                        material_ids.extend(item.get("material_ids") or [])
                        if item.get("material_id"):
                            material_ids.append(item["material_id"])
                        evidence.extend(item.get("evidence") or [])
                converted[summary_field] = {
                    "title": legacy_section.get("title") or default_title,
                    "summary": legacy_section.get("overallSummary") or "",
                    "evidence": evidence,
                    "material_ids": list(dict.fromkeys(str(item) for item in material_ids if item)),
                }
            if summary_field not in converted and isinstance(converted.get(target), list):
                items = [item for item in converted[target] if isinstance(item, dict)]
                parts = []
                material_ids, evidence = [], []
                for item in items:
                    title = item.get("title") or item.get("dimension")
                    summary = item.get("summary") or item.get("conclusion")
                    if title and summary:
                        parts.append(f"{title}：{summary}")
                    elif summary:
                        parts.append(str(summary))
                    material_ids.extend(item.get("material_ids") or [])
                    if item.get("material_id"):
                        material_ids.append(item["material_id"])
                    evidence.extend(item.get("evidence") or [])
                converted[summary_field] = {
                    "title": default_title,
                    "summary": " ".join(parts),
                    "evidence": evidence,
                    "material_ids": list(dict.fromkeys(str(item) for item in material_ids if item)),
                }
        normalized["scopes"][scope_key] = converted
    return normalized


def _validate_ranking_scope_contract(analysis, fact_pack):
    """Keep the 01 chapter aligned with the processed ranking scopes."""
    if not isinstance(fact_pack, dict) or "industryTop1000Facts" not in fact_pack:
        return
    industry = fact_pack["industryTop1000Facts"]
    if industry.get("source_scope") != "industry_top1000":
        raise YuntuReportError("industryTop1000Facts must describe the industry ranking scope")
    brands = configured_brands(fact_pack.get("filters", {}))
    conclusions = analysis.get("topMaterialCombination", {}).get("brandConclusions", [])
    actual_names = [item.get("brand") for item in conclusions if isinstance(item, dict)]
    strict_brand_scope = fact_pack.get("brandScope", {}).get("version") == 1
    if strict_brand_scope and actual_names != brands:
        raise YuntuReportError("brand conclusions must preserve the configured brand scope and order")
    if strict_brand_scope:
        aggregate = analysis.get("topMaterialCombination", {}).get("allBrandsConclusion", {})
        if aggregate.get("classificationSource") != "scope_aggregate":
            raise YuntuReportError("allBrandsConclusion classificationSource must be scope_aggregate")
        if any(item.get("classificationSource") != "runtime_title_rule" for item in conclusions):
            raise YuntuReportError("brand conclusions classificationSource must be runtime_title_rule")
    if brands and set(actual_names) != set(brands):
        raise YuntuReportError("brand conclusions must preserve the complete input brand names")
    brand_facts = _brand_ranking_facts(fact_pack).get("brands", {})
    conclusions_by_brand = {
        item["brand"]: item for item in conclusions if isinstance(item, dict)
    }
    strict_audience_contract = fact_pack.get("schemaVersion", 0) >= 5
    for brand in actual_names:
        scope = brand_facts.get(brand)
        if not isinstance(scope, dict) or scope.get("source_scope") not in {"brand_in_top1000", "brand_top_n"}:
            comparison_scope = (
                (fact_pack.get("comparisonFacts") or {}).get("scopes", {}).get(brand, {})
                if isinstance(fact_pack, dict)
                else {}
            )
            current_scope = comparison_scope.get("current", {}) if isinstance(comparison_scope, dict) else {}
            if current_scope.get("sampleCount") == 0:
                # A specified brand can legitimately have zero matches in the
                # merged industry TOP1000. Keep the unavailable conclusion and
                # let the report state that the sample is insufficient.
                continue
            raise YuntuReportError(f"missing processed brand facts for {brand}")
        if strict_brand_scope and scope.get("sample_count") == 0:
            item = conclusions_by_brand[brand]
            if item.get("material_ids") or item.get("evidence"):
                raise YuntuReportError(f"empty brand conclusion must not borrow evidence for {brand}")
            if "数据不足" not in item.get("dataSummary", ""):
                raise YuntuReportError(f"empty brand conclusion must explain 数据不足 for {brand}")
            continue
        if not strict_audience_contract:
            continue
        data_summary = conclusions_by_brand[brand]["dataSummary"]
        missing_metrics = []
        for label, aliases in (
            ("曝光", ("曝光",)),
            ("CTR/点击率", ("CTR", "点击率")),
            ("CVR/转化率", ("CVR", "转化率")),
        ):
            if not any(alias in data_summary for alias in aliases):
                missing_metrics.append(label)
        if "3秒" not in data_summary and "3 秒" not in data_summary:
            missing_metrics.append("3 秒播放率")
        if missing_metrics:
            raise YuntuReportError(
                f"brand dataSummary must cover exposure, CTR, CVR, and 3-second play rate for {brand}"
            )
        material_ids = {
            str(item.get("material_id"))
            for item in scope.get("materials", [])
            if isinstance(item, dict) and item.get("material_id")
        }
        if len(material_ids) != scope.get("sample_count"):
            raise YuntuReportError(f"brand facts sample mismatch for {brand}")
        if fact_pack.get("schemaVersion", 0) >= 6:
            for field in ("dataSummary",):
                summary = conclusions_by_brand[brand][field]
                if any(material_id in summary for material_id in material_ids):
                    raise YuntuReportError(
                        f"brand dataSummary must not include material IDs for {brand}"
                    )
        referenced_ids = set(conclusions_by_brand[brand].get("material_ids", []))
        if material_ids and not referenced_ids.issubset(material_ids):
            raise YuntuReportError(f"brand conclusion references material outside brand facts for {brand}")


def _validate_hot_material_facts(fact_pack):
    hot_facts = fact_pack.get("hotMaterialFacts")
    if not isinstance(hot_facts, dict):
        raise YuntuReportError("hotMaterialFacts must be an object")
    configured_rule = fact_pack.get("hotMaterialRule")
    configured_threshold = None
    if configured_rule is not None:
        if not isinstance(configured_rule, dict):
            raise YuntuReportError("hotMaterialRule must be an object")
        if configured_rule.get("metric") != "exposure_interval_min":
            raise YuntuReportError("hotMaterialRule metric is unsupported")
        if configured_rule.get("comparison") != "gte":
            raise YuntuReportError("hotMaterialRule comparison is unsupported")
        configured_threshold = configured_rule.get("threshold")
        if (
            isinstance(configured_threshold, bool)
            or not isinstance(configured_threshold, int)
            or configured_threshold <= 0
        ):
            raise YuntuReportError("hotMaterialRule threshold must be a positive integer")
    for scope, facts in hot_facts.items():
        if not isinstance(facts, dict):
            raise YuntuReportError("hotMaterialFacts scope must be an object")
        threshold = configured_threshold
        if threshold is None:
            threshold = facts.get("thresholdExposureMin")
        if (
            isinstance(threshold, bool)
            or not isinstance(threshold, int)
            or threshold <= 0
            or facts.get("thresholdExposureMin") != threshold
        ):
            raise YuntuReportError("hotMaterialFacts threshold does not match the configured rule")
        materials = facts.get("materials")
        if not isinstance(materials, list):
            raise YuntuReportError("hotMaterialFacts materials must be a list")
        if (
            isinstance(facts.get("qualifyingCount"), bool)
            or not isinstance(facts.get("qualifyingCount"), int)
            or facts.get("qualifyingCount") != len(materials)
        ):
            raise YuntuReportError("hotMaterialFacts qualifyingCount does not match materials")
        previous_min = None
        seen_ids = set()
        for material in materials:
            if not isinstance(material, dict) or not isinstance(material.get("material_id"), str):
                raise YuntuReportError("hotMaterialFacts material identity is invalid")
            material_id = material["material_id"]
            if material_id in seen_ids:
                raise YuntuReportError("hotMaterialFacts material IDs must be unique")
            seen_ids.add(material_id)
            exposure = material.get("exposure")
            minimum = exposure.get("min") if isinstance(exposure, dict) else None
            if (
                not isinstance(minimum, (int, float))
                or isinstance(minimum, bool)
                or minimum < threshold
            ):
                raise YuntuReportError("hotMaterialFacts exposure minimum is below the threshold")
            if previous_min is not None and minimum > previous_min:
                raise YuntuReportError("hotMaterialFacts materials must be sorted by exposure minimum")
            previous_min = minimum
        if facts.get("available") is False and not facts.get("missing_reason"):
            raise YuntuReportError("unavailable hotMaterialFacts must include missing_reason")


def _validate_period_and_hot_material_contract(analysis, fact_pack):
    if not isinstance(fact_pack, dict) or not fact_pack.get("hotMaterialFacts"):
        return
    _validate_hot_material_facts(fact_pack)
    combination = analysis.get("topMaterialCombination", {})
    conclusions = list(combination.get("brandConclusions", []))
    aggregate = combination.get("allBrandsConclusion")
    if isinstance(aggregate, dict):
        conclusions.append(aggregate)
    hot_facts = fact_pack["hotMaterialFacts"]
    if "all" in hot_facts and not isinstance(combination.get("allBrandsConclusion"), dict):
        raise YuntuReportError("new chapter01 contract requires allBrandsConclusion")
    for item in conclusions:
        brand = item.get("brand")
        expected_scope = "all" if brand == "全品牌" else "brand"
        allowed = {
            "brand", "classificationSource", "dataSummary", "evidence", "material_ids",
            "comparisonSummary", "hotMaterialInsight",
        }
        if set(item) - allowed:
            raise YuntuReportError(f"{brand} contains unsupported chapter01 fields")
        if "comparisonSummary" in item and (
            not isinstance(item["comparisonSummary"], str)
            or not item["comparisonSummary"].strip()
        ):
            raise YuntuReportError(f"{brand} comparisonSummary must be nonempty when present")
        insight = item.get("hotMaterialInsight")
        if insight is None:
            continue
        if not isinstance(insight, dict):
            raise YuntuReportError(f"{brand} hotMaterialInsight must be an object when present")
        for field in ("title", "summary"):
            if not isinstance(insight.get(field), str) or not insight[field].strip():
                raise YuntuReportError(f"{brand} hotMaterialInsight {field} is required")
        evidence = insight.get("evidence")
        if not isinstance(evidence, dict) or evidence.get("scope") != expected_scope:
            raise YuntuReportError(f"{brand} hotMaterialInsight evidence scope is invalid")
        material_ids = evidence.get("material_ids")
        if not isinstance(material_ids, list) or not all(
            isinstance(value, str) and value.isdigit() for value in material_ids
        ):
            raise YuntuReportError(f"{brand} hotMaterialInsight evidence material_ids are invalid")
        scope_key = "all" if expected_scope == "all" else brand
        scope_facts = hot_facts.get(scope_key)
        if not isinstance(scope_facts, dict):
            raise YuntuReportError(f"{brand} hotMaterialInsight scope facts are missing")
        known_ids = {str(item.get("material_id")) for item in scope_facts.get("materials", []) if isinstance(item, dict)}
        if not set(material_ids).issubset(known_ids):
            raise YuntuReportError(f"{brand} hotMaterialInsight references an unknown material ID")


def _render_markdown(analysis, audience_dashboard=None, fact_pack=None):
    lines = ["# 云图行业素材全景分析报告", ""]
    combination = analysis["topMaterialCombination"]
    lines.extend(["## 01｜素材榜单数据洞察", ""])
    lines.extend(["---", "", "### 各品牌榜单分析", ""])
    brand_conclusions = {item["brand"]: item for item in combination["brandConclusions"]}
    brand_order = configured_brands((fact_pack or {}).get("filters", {}))
    aggregate = combination.get("allBrandsConclusion")
    ordered_brands = ([aggregate] if isinstance(aggregate, dict) else [])
    ordered_brands.extend([
        brand_conclusions[brand]
        for brand in brand_order
        if brand in brand_conclusions
    ])
    ordered_brands.extend(
        item
        for item in combination["brandConclusions"]
        if item not in ordered_brands
    )
    for index, item in enumerate(ordered_brands):
        if index:
            lines.extend(["---", ""])
        display_brand = aggregate_scope_label(fact_pack) if item.get("brand") == "全品牌" else item["brand"]
        lines.extend([f"### {display_brand}", ""])
        data_summary = item.get("dataSummary", "")
        if data_summary:
            lines.extend(["#### 素材表现洞察", "", data_summary, ""])
        elif item.get("comparisonSummary"):
            lines.extend(["#### 素材表现洞察", "", item["comparisonSummary"], ""])
        hot_facts = (fact_pack or {}).get("hotMaterialFacts", {}) if isinstance(fact_pack, dict) else {}
        if isinstance(hot_facts, dict) and hot_facts:
            scope_key = "all" if item.get("brand") == "全品牌" else item.get("brand")
            comparison_scopes = ((fact_pack or {}).get("comparisonFacts") or {}).get("scopes", {})
            comparison = comparison_scopes.get(scope_key, {}) if isinstance(comparison_scopes, dict) else {}
            if isinstance(comparison, dict) and comparison:
                lines.extend(["#### 环比与全行业对比", ""])
                card_specs = []
                current = comparison.get("current")
                if isinstance(current, dict):
                    card_specs.append(("当前默认筛选条件", current, "current"))
                for baseline_key, baseline_label in (("previousPeriod", "环比周期"), ("industryBenchmark", "同周期全行业")):
                    fact = comparison.get(baseline_key)
                    if isinstance(fact, dict):
                        card_specs.append((baseline_label, fact, "baseline"))
                for card_label, fact, value_source in card_specs:
                    value_parts = []
                    for key, label in (("show_cnt", "曝光总量"), ("ctr", "CTR"), ("cvr", "CVR"), ("play_3s_rate", "3 秒完播率")):
                        value = (
                            _chapter01_current_metric_value(fact, key)
                            if value_source == "current"
                            else _chapter01_baseline_metric_value(fact, key)
                        )
                        formatted = _format_chapter01_exposure(value) if key == "show_cnt" else _format_chapter01_percentage(value)
                        if value_source != "current" and isinstance(current, dict):
                            rate = _chapter01_rate_against_current(current, fact, key)
                            if rate is not None:
                                formatted += f"（变化率 {_format_chapter01_percentage(rate, signed=True)}）"
                        value_parts.append(f"{label}：{formatted}")
                    lines.extend([f"##### {card_label}", "", f"- 真实值：{'；'.join(value_parts)}。", ""])
        hot_insight = item.get("hotMaterialInsight")
        if isinstance(hot_insight, dict) and hot_insight.get("summary"):
            lines.extend(["#### 爆款素材洞察", "", hot_insight["summary"], ""])
            hot = hot_facts.get(scope_key, {})
            lines.extend(["#### 爆款素材面板", ""])
            if not hot.get("available"):
                lines.extend([f"曝光区间事实不可用：{hot.get('missing_reason') or '数据不足'}。", ""])
            else:
                lines.extend([f"规则：曝光量区间下限 ≥ {hot.get('thresholdExposureMin')}；命中 {hot.get('qualifyingCount', 0)} 条素材。", ""])
                for material in hot.get("materials", []):
                    exposure = material.get("exposure", {})
                    lines.append(
                        f"- {material.get('title') or material.get('material_id')}（ID：{material.get('material_id')}）：{exposure.get('raw') or '曝光区间不可用'}"
                    )
                lines.append("")
    lines.extend(["## 02｜人群及营销卖点洞察", ""])
    chapter02 = (fact_pack or {}).get("chapter02Facts") if isinstance(fact_pack, dict) else None
    chapter02_insights = analysis.get("chapter02Insights", {})
    if isinstance(chapter02, dict) and chapter02.get("scopeOrder"):
        scopes = chapter02_insights.get("scopes", {}) if isinstance(chapter02_insights, dict) else {}
        for scope_key in chapter02["scopeOrder"]:
            scope_fact = chapter02.get(scope_key, {})
            lines.extend([f"### {scope_fact.get('label', scope_key)}", ""])
            scope_ai = scopes.get(scope_key, {}) if isinstance(scopes, dict) else {}
            for insight in (scope_ai.get("audienceInsights", []) + scope_ai.get("marketingInsights", [])) if isinstance(scope_ai, dict) else []:
                lines.extend([insight.get("summary", ""), ""])
            dashboard = scope_fact.get("audienceDashboard", {})
            dimensions = dashboard.get("dimensions", {}) if isinstance(dashboard, dict) else {}
            for key, label in AUDIENCE_DIMENSION_LABELS.items():
                dimension = dimensions.get(key, {}) if isinstance(dimensions, dict) else {}
                lines.extend([f"#### {label}", "", "图表按素材标签占比展示，用于观察标签结构，不代表真实人群分布。", ""])
                for bucket in dimension.get("buckets", []):
                    lines.append(f"- {bucket['label']}：{bucket['materialCount']} 条素材，占比 {bucket['chartShare'] * 100:.1f}%")
                lines.append("")
            marketing = scope_fact.get("marketingDashboard", {})
            lines.extend(["#### 营销卖点汇总", "", f"共 {marketing.get('tagCount', 0)} 个标签，{marketing.get('occurrenceCount', 0)} 次命中。", ""])
            for category in marketing.get("categories", []):
                tags = "、".join(f"{tag['tag']}（{tag['count']}）" for tag in category.get("topTags", [])[:5])
                lines.extend([f"- {category.get('category')}：{category.get('occurrenceCount', 0)} 次；Top：{tags}", ""])
    else:
        for insight in (analysis.get("audienceInsights") or []):
            lines.extend([insight["summary"], ""])
    if not (isinstance(chapter02, dict) and chapter02.get("scopeOrder")) and isinstance(audience_dashboard, dict):
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
    lines.extend(["## 03｜脚本洞察", ""])
    script_facts = (fact_pack or {}).get("scriptFacts") if isinstance(fact_pack, dict) else None
    if isinstance(script_facts, dict) and script_facts.get("materials"):
        coverage = script_facts.get("coverage", {})
        lines.extend([
            "范围：已获取详情素材。",
            f"脚本文本覆盖 {coverage.get('script', 0)}/{coverage.get('total', 0)} 个素材（{coverage.get('rate', 0):.0%}），该范围不代表行业 TOP1000 普遍规律。",
            "",
        ])
        for insight in analysis.get("scriptInsights", []):
            lines.extend([f"### {insight.get('title', '脚本洞察')}", "", insight.get("summary", ""), "", f"证据素材：{'、'.join(insight.get('material_ids', []))}。", ""])
        if not analysis.get("scriptInsights"):
            lines.extend(["数据不足以判断。", ""])
        keyword_cloud = script_facts.get("keywordCloud", {})
        raw_keywords = keyword_cloud.get("keywords", []) if isinstance(keyword_cloud, dict) else []
        review = {
            str(item.get("keyword")): item
            for item in analysis.get("keywordCloudReview", [])
            if isinstance(item, dict) and str(item.get("keyword") or "").strip()
        }
        projected = {}
        for raw in raw_keywords if isinstance(raw_keywords, list) else []:
            if not isinstance(raw, dict) or not str(raw.get("keyword") or "").strip():
                continue
            keyword = str(raw["keyword"]).strip()
            decision = str(review.get(keyword, {}).get("decision", "accept"))
            if decision == "exclude":
                continue
            target = str(review.get(keyword, {}).get("target", "")).strip() if decision == "merge" else ""
            target = target or keyword
            item = projected.setdefault(target, {"frequency": 0, "evidenceRefs": []})
            item["frequency"] += raw.get("frequency", 0) if isinstance(raw.get("frequency", 0), (int, float)) else 0
            for ref in raw.get("evidenceRefs", []):
                if ref not in item["evidenceRefs"]:
                    item["evidenceRefs"].append(ref)
        keyword_insight = analysis.get("keywordCloudInsight")
        if isinstance(keyword_insight, dict):
            lines.extend([
                "#### 一句话结论", "", keyword_insight.get("oneSentenceConclusion", "数据不足以判断。"), "",
                "#### 高频关键词云", "",
            ])
            for keyword, item in sorted(projected.items(), key=lambda pair: (-pair[1]["frequency"], pair[0])):
                lines.append(f"- {keyword}（{item['frequency']} 次出现）")
            lines.append("")
            lines.extend(["#### 关键词组合摘要", "", keyword_insight.get("summary", "数据不足以判断。"), ""])
            selling_points = keyword_insight.get("sellingPoints", [])
            if isinstance(selling_points, list) and selling_points:
                lines.extend(["#### 从关键词云提炼的卖点", ""])
                for index, point in enumerate(selling_points[:4], start=1):
                    if isinstance(point, dict):
                        lines.extend([f"- {index}｜{point.get('title', '卖点')}：{point.get('description', '')}"])
                lines.append("")
        if not any(item.get("script_segments") for item in script_facts.get("materials", []) if isinstance(item, dict)):
            lines.extend(["未提供脚本时间段，暂不输出帧-话术对应关系。", ""])
    else:
        lines.extend(["**脚本数据：未接入**", "", "本次云图 RPA 未提供可用于汇总的脚本正文与时间戳段落；本部分暂不输出话术、内容公式或帧-话术对应关系。", ""])
    for brand in (script_facts or {}).get("brandScopeOrder", []):
        scoped = analysis.get("scriptBrandInsights", {}).get(brand)
        if not isinstance(scoped, dict):
            continue
        lines.extend([f"### {brand}", ""])
        for item in scoped.get("scriptInsights", []):
            lines.extend([f"#### {item['title']}", "", item["summary"], ""])
        cloud = scoped.get("keywordCloudInsight", {})
        lines.extend([cloud.get("oneSentenceConclusion", ""), "", cloud.get("summary", ""), ""])
        for point in cloud.get("sellingPoints", []):
            lines.extend([f"- {point['title']}：{point['description']}", ""])
    lines.extend(["## 04｜高光画面洞察", "", ""])
    successful_frames = _overview_highlight_frames(fact_pack or {})
    dashboard = analysis.get("highlightDashboard")
    if not successful_frames:
        reason = _highlight_failure_reasons(fact_pack or {})
        lines.extend(["暂无可用高光帧。" + (f" 原因：{reason}。" if reason else ""), ""])
    elif not isinstance(dashboard, dict):
        lines.extend(["高光帧已生成，尚未完成视觉分类，因此不输出视觉洞察。", ""])
    else:
        frames_by_ref = {frame["frame_ref"]: frame for frame in successful_frames}
        markdown_groups = dashboard.get("groups")
        if not isinstance(markdown_groups, list):
            brand_scopes = dashboard.get("brands", [])
            markdown_groups = brand_scopes[0].get("groups", []) if brand_scopes else []
        for group in markdown_groups:
            category = {"scene": "other", "text_overlay": "other"}.get(group["category"], group["category"])
            lines.extend([f"### {HIGHLIGHT_CATEGORY_LABELS[category]}", "", "#### 共性洞察", ""])
            patterns = list(group["common_patterns"])
            directions = list(group["derivative_directions"])
            pair_count = min(len(patterns), len(directions))
            for pattern in patterns[:pair_count]:
                if isinstance(pattern, dict):
                    lines.extend([f"- {pattern.get('title', '共性观察')}：{pattern.get('body', '')}", ""])
                else:
                    lines.extend([f"- {pattern}", ""])
            for frame_ref in group["frame_refs"]:
                frame = frames_by_ref[frame_ref]
                frame_label = "封面画面" if frame["frame_type"] == "cover" else f"点击 Top{frame.get('peak_rank')} 波峰画面"
                value = "-" if frame.get("click_value") is None else str(frame["click_value"])
                lines.append(
                    f"- #{frame.get('rank', '-')}｜{frame.get('title', frame['material_id'])}｜{frame_label}｜{frame.get('second')}s｜点击指数 {value}"
                )
            lines.append("")
            lines.extend(["#### 裂变方向", ""])
            for direction in directions[:pair_count]:
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


def _is_placeholder_batch_category(value):
    compact = re.sub(r"[\s_-]+", "", str(value or "")).lower()
    return bool(re.fullmatch(r"(?:其他|other)\d+", compact))


def _require_frame_coverage(actual, expected, message):
    counts = Counter(actual)
    details = {"duplicates": sorted(ref for ref, count in counts.items() if count > 1),
               "missing": sorted(set(expected) - set(actual)),
               "unexpected": sorted(set(actual) - set(expected))}
    if any(details.values()):
        raise YuntuReportError(message + ": " + json.dumps(details, ensure_ascii=False))


def _validate_highlight_classification_groups(groups, known_refs, *, mode):
    if not isinstance(groups, list):
        raise YuntuReportError(f"{mode} groups must be a list")
    if mode == "batchClassification":
        if len(groups) < 2:
            raise YuntuReportError(f"{mode} must contain at least 2 semantic categories")
        if len(groups) > len(known_refs):
            raise YuntuReportError(f"{mode} cannot contain more categories than successful frames")
    actual_refs = []
    categories = []
    labels = []
    for group in groups:
        if not isinstance(group, dict):
            raise YuntuReportError(f"{mode} groups items must be objects")
        category = group.get("category")
        if not isinstance(category, str) or not category.strip():
            raise YuntuReportError(f"{mode} group category is required")
        if category in categories:
            raise YuntuReportError(f"{mode} group categories must be unique")
        categories.append(category)
        if mode == "batchClassification":
            for field in ("label", "rule"):
                if not isinstance(group.get(field), str) or not group[field].strip():
                    raise YuntuReportError(f"{mode} group {field} is required")
            if _is_placeholder_batch_category(category) or _is_placeholder_batch_category(group["label"]):
                raise YuntuReportError(f"{mode} group category and label must be semantic")
            if group["label"] in labels:
                raise YuntuReportError(f"{mode} group labels must be unique")
            labels.append(group["label"])
        elif category not in HIGHLIGHT_RENDER_CATEGORY_ORDER:
            raise YuntuReportError("standardClassification group category is invalid")
        refs = group.get("frame_refs")
        if not isinstance(refs, list) or not refs or not all(isinstance(ref, str) for ref in refs):
            raise YuntuReportError(f"{mode} groups require frame_refs")
        if not set(refs).issubset(known_refs):
            raise YuntuReportError(f"{mode} frame reference is invalid")
        if mode == "batchClassification":
            actual_refs.extend(refs)
            continue
        patterns = group.get("common_patterns")
        directions = group.get("derivative_directions")
        if not isinstance(patterns, list) or not all(isinstance(item, dict) for item in patterns):
            raise YuntuReportError(f"{mode} common_patterns must be structured objects")
        if not isinstance(directions, list) or len(patterns) != len(directions):
            raise YuntuReportError(f"{mode} common_patterns and derivative_directions must have matching counts")
        for pattern, direction in zip(patterns, directions):
            for item, label in ((pattern, "common pattern"), (direction, "derivative direction")):
                if not all(isinstance(item.get(key), str) and item[key].strip() for key in ("title", "body")):
                    raise YuntuReportError(f"{mode} {label} requires title and body")
                item_refs = item.get("frame_refs")
                if not isinstance(item_refs, list) or not item_refs or not set(item_refs).issubset(set(refs)):
                    raise YuntuReportError(f"{mode} {label} frame references are invalid")
                _validate_deep_dive_text(item["title"], f"{mode} {label} title")
                _validate_deep_dive_text(item["body"], f"{mode} {label} body")
        actual_refs.extend(refs)
    if mode == "standardClassification":
        _validate_highlight_insight_independence(groups, mode=mode)
    _require_frame_coverage(actual_refs, known_refs, f"{mode} must classify each successful frame exactly once")
    if mode == "standardClassification":
        expected_order = [category for category in HIGHLIGHT_RENDER_CATEGORY_ORDER if category in categories]
        if categories != expected_order:
            raise YuntuReportError("standardClassification groups must use portrait, product, other order")


def _validate_highlight_insight_independence(groups, *, mode):
    """Reject copied prose between standard visual categories in one scope."""
    for field, label in (("common_patterns", "common pattern"),
                         ("derivative_directions", "derivative direction")):
        seen = {}
        for group in groups:
            category = str(group.get("category") or "")
            for index, item in enumerate(group.get(field, [])):
                if not isinstance(item, dict):
                    continue
                semantic = _normalized_semantic_text(item.get("body"))
                if not semantic:
                    continue
                previous = seen.get(semantic)
                if previous is not None:
                    raise YuntuReportError(
                        f"{mode} {label} body must be independent across categories "
                        f"({previous[0]} vs {category})"
                    )
                seen[semantic] = (category, index)


def _validate_highlight_dual_classification(
    dashboard, successful_frames, *, strict_semantic_contract=False, require_classification=False
):
    fields = ("frameUnderstanding", "standardClassification", "batchClassification")
    present = [field for field in fields if field in dashboard]
    if not present and not require_classification:
        return
    if len(present) != len(fields):
        raise YuntuReportError("highlightDashboard must include frameUnderstanding, standardClassification, and batchClassification together")
    known_refs = {frame["frame_ref"] for frame in successful_frames}
    understanding = dashboard["frameUnderstanding"]
    if not isinstance(understanding, list):
        raise YuntuReportError("frameUnderstanding must be a list")
    understanding_refs = []
    understanding_texts = set()
    for item in understanding:
        if not isinstance(item, dict) or not isinstance(item.get("frame_ref"), str):
            raise YuntuReportError("frameUnderstanding items must include frame_ref")
        ref = item["frame_ref"]
        if ref not in known_refs:
            raise YuntuReportError("frameUnderstanding frame reference is invalid")
        if require_classification and (item.get("standard_category") not in HIGHLIGHT_RENDER_CATEGORY_ORDER or len(str(item.get("category_reason") or "").strip()) < 12):
            raise YuntuReportError("frameUnderstanding requires standard_category and category_reason")
        if item.get("status") not in {"complete", "unavailable"}:
            raise YuntuReportError("frameUnderstanding status is invalid")
        if item["status"] == "unavailable":
            if not isinstance(item.get("failure_reason"), str) or not item["failure_reason"].strip():
                raise YuntuReportError("frameUnderstanding unavailable items require failure_reason")
        else:
            required_fields = ("subject", "visual_focus", "human_product_relation", "action", "composition", "information_expression")
            if not all(isinstance(item.get(field), str) and item[field].strip() for field in required_fields):
                raise YuntuReportError("frameUnderstanding complete items require visual observations")
            if strict_semantic_contract:
                semantic = _normalized_semantic_text(" ".join(item.get(field, "") for field in required_fields))
                if semantic in understanding_texts:
                    raise YuntuReportError("frameUnderstanding observations must differ by frame")
                understanding_texts.add(semantic)
        understanding_refs.append(ref)
    _require_frame_coverage(understanding_refs, known_refs, "frameUnderstanding must cover each successful frame exactly once")

    for mode in ("standardClassification", "batchClassification"):
        classification = dashboard[mode]
        if not isinstance(classification, dict):
            raise YuntuReportError(f"{mode} must be an object")
        status = classification.get("status")
        if require_classification and mode == "standardClassification" and status != "complete":
            raise YuntuReportError("standardClassification must classify all successful frames")
        if status not in {"complete", "unavailable"}:
            raise YuntuReportError(f"{mode} status is invalid")
        reason = classification.get("missing_reason")
        if status == "unavailable" and (not isinstance(reason, str) or not reason.strip()):
            raise YuntuReportError(f"{mode} unavailable requires missing_reason")
        groups = classification.get("groups")
        if status == "unavailable":
            if groups not in ([], None):
                raise YuntuReportError(f"{mode} unavailable must not contain groups")
            continue
        _validate_highlight_classification_groups(groups, known_refs, mode=mode)
        if mode == "batchClassification" and (not isinstance(classification.get("rule"), str) or not classification["rule"].strip()):
            raise YuntuReportError("batchClassification complete requires rule")

    if require_classification:
        assignments = {item["frame_ref"]: item["standard_category"] for item in understanding}
        brands = dashboard.get("brands")
        if not isinstance(brands, list) or not brands:
            raise YuntuReportError("highlightDashboard.brands must be a non-empty list")
        scopes = [dashboard["standardClassification"], *brands]
        for scope in scopes:
            if not isinstance(scope, dict) or not isinstance(scope.get("groups"), list):
                raise YuntuReportError("highlightDashboard brand scopes require groups")
            for group in scope.get("groups", []):
                if not isinstance(group, dict) or not isinstance(group.get("frame_refs"), list):
                    raise YuntuReportError("highlightDashboard groups require frame_refs")
                if any(assignments.get(ref) != group.get("category") for ref in group.get("frame_refs", [])):
                    raise YuntuReportError("standard classification and brand groups must agree with frameUnderstanding.standard_category")


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
    _validate_highlight_dual_classification(
        dashboard, successful_frames,
        strict_semantic_contract=fact_pack.get("schemaVersion", 0) >= 8,
        require_classification=fact_pack.get("analysisQualityVersion", 0) >= 4,
    )
    scoped_brands = dashboard.get("brands")
    if scoped_brands is not None:
        if not isinstance(scoped_brands, list) or not scoped_brands:
            raise YuntuReportError("highlightDashboard.brands must be a non-empty list")
        known_refs = {frame["frame_ref"] for frame in successful_frames}
        brand_order = configured_brands(fact_pack.get("filters", {}))
        if quality_enabled(fact_pack) and [s.get("brand") for s in scoped_brands] != ["全品牌", *brand_order]:
            raise YuntuReportError("highlightDashboard.brands must cover every configured brand in order")
        seen_brands = set()
        for index, scope in enumerate(scoped_brands):
            if not isinstance(scope, dict) or not isinstance(scope.get("brand"), str):
                raise YuntuReportError("highlightDashboard brand scopes must be objects")
            brand = scope["brand"].strip()
            if not brand or brand in seen_brands:
                raise YuntuReportError("highlightDashboard brand scopes must be unique")
            if index == 0 and brand != "全品牌":
                raise YuntuReportError("highlightDashboard first brand scope must be 全品牌")
            groups = scope.get("groups")
            expected = known_refs if brand == "全品牌" else {f["frame_ref"] for f in successful_frames if brand in match_brands_from_title(f.get("title"), brand_order)}
            if not expected and groups == [] and str(scope.get("missing_reason") or "").strip():
                seen_brands.add(brand)
                continue
            if not isinstance(groups, list) or not groups:
                raise YuntuReportError("highlightDashboard brand scope groups must be a non-empty list")
            actual_refs = []
            categories = []
            for group in groups:
                if not isinstance(group, dict):
                    raise YuntuReportError("highlightDashboard groups items must be objects")
                category = group.get("category")
                if category not in HIGHLIGHT_RENDER_CATEGORY_ORDER:
                    raise YuntuReportError("highlightDashboard brand category is invalid")
                categories.append(category)
                frame_refs = group.get("frame_refs")
                if not isinstance(frame_refs, list) or not frame_refs or not all(isinstance(ref, str) for ref in frame_refs):
                    raise YuntuReportError("highlightDashboard groups require frame_refs")
                if not set(frame_refs).issubset(known_refs):
                    raise YuntuReportError("highlightDashboard brand frame reference is invalid")
                patterns = group.get("common_patterns")
                directions = group.get("derivative_directions")
                if not isinstance(patterns, list) or not patterns or not all(isinstance(item, dict) for item in patterns):
                    raise YuntuReportError("highlightDashboard brand groups require structured common_patterns")
                if not isinstance(directions, list) or len(patterns) != len(directions):
                    raise YuntuReportError("highlightDashboard common_patterns and derivative_directions must have matching counts")
                for pattern, direction in zip(patterns, directions):
                    for item, label in ((pattern, "common pattern"), (direction, "derivative direction")):
                        if not all(isinstance(item.get(key), str) and item[key].strip() for key in ("title", "body")):
                            raise YuntuReportError(f"highlightDashboard {label} requires title and body")
                        refs = item.get("frame_refs")
                        if not isinstance(refs, list) or not refs or not set(refs).issubset(set(frame_refs)):
                            raise YuntuReportError(f"highlightDashboard {label} frame references are invalid")
                        _validate_deep_dive_text(item["title"], f"highlightDashboard {label} title")
                        _validate_deep_dive_text(item["body"], f"highlightDashboard {label} body")
                actual_refs.extend(frame_refs)
            _validate_highlight_insight_independence(groups, mode="highlightDashboard brand scope")
            if categories != [category for category in HIGHLIGHT_RENDER_CATEGORY_ORDER if category in categories]:
                raise YuntuReportError("highlightDashboard brand groups must use portrait, product, other order")
            expected_refs = known_refs if brand == "全品牌" else {
                frame["frame_ref"]
                for frame in successful_frames
                if brand in match_brands_from_title(frame.get("title"), brand_order)
            }
            if len(actual_refs) != len(set(actual_refs)) or set(actual_refs) != expected_refs:
                raise YuntuReportError("highlightDashboard brand scope must classify its frames exactly once")
            seen_brands.add(brand)
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
            (isinstance(pattern, str) and pattern.strip())
            or (
                isinstance(pattern, dict)
                and isinstance(pattern.get("title"), str)
                and pattern["title"].strip()
                and isinstance(pattern.get("body"), str)
                and pattern["body"].strip()
                and isinstance(pattern.get("frame_refs"), list)
                and pattern["frame_refs"]
                and set(pattern["frame_refs"]).issubset(set(frame_refs))
            )
            for pattern in patterns
        ):
            raise YuntuReportError("highlightDashboard groups require common_patterns")
        for pattern in patterns:
            if isinstance(pattern, dict):
                _validate_deep_dive_text(
                    pattern["title"], "highlightDashboard common pattern title"
                )
                _validate_deep_dive_text(
                    pattern["body"], "highlightDashboard common pattern body"
                )
                continue
            _validate_deep_dive_text(
                pattern, "highlightDashboard groups common_patterns"
            )
        directions = group.get("derivative_directions")
        if not isinstance(directions, list):
            raise YuntuReportError("highlightDashboard groups require derivative_directions")
        if patterns and all(isinstance(pattern, dict) for pattern in patterns) and len(patterns) != len(directions):
            raise YuntuReportError("highlightDashboard common_patterns and derivative_directions must have matching counts")
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
        # Historical analysis files may still carry the retired AI index summaries.
        # Drop them from the normalized analysis before Presentation/report output.
        dive.pop("second_level_observations", None)
        frames = [
            frame for frame in facts[material_id].get("highlightFrames", [])
            if isinstance(frame, dict) and frame.get("available")
        ]
        known_refs = {frame.get("frame_ref") for frame in frames if isinstance(frame.get("frame_ref"), str)}
        observations = dive.get("frame_observations")
        if not isinstance(observations, list):
            raise YuntuReportError("materialDeepDives frame_observations must be a list")
        observation_refs = []
        strict_semantic_contract = fact_pack.get("schemaVersion", 0) >= 8
        observation_texts = set()
        for observation in observations:
            if not isinstance(observation, dict) or not isinstance(observation.get("frame_ref"), str):
                raise YuntuReportError("materialDeepDives frame_observations must include frame_ref")
            _validate_ai_text(
                observation.get("observation"),
                "materialDeepDives frame observation",
                "frame_observation",
            )
            if strict_semantic_contract:
                semantic = _normalized_semantic_text(observation.get("observation"))
                if semantic in observation_texts:
                    raise YuntuReportError("materialDeepDives frame observations must differ by frame")
                observation_texts.add(semantic)
            observation_refs.append(observation["frame_ref"])
        _require_frame_coverage(observation_refs, known_refs,
                                f"materialDeepDives must observe each successful frame exactly once ({material_id})")
        script_analysis = dive.get("scriptAnalysis")
        if script_analysis is None:
            if strict_semantic_contract:
                raise YuntuReportError("scriptAnalysis is required for every selected material")
            continue
        if not isinstance(script_analysis, dict) or set(script_analysis) - {"conclusion", "evidenceRefs", "availability"}:
            raise YuntuReportError("scriptAnalysis is invalid")
        availability = script_analysis.get("availability")
        if availability not in {"available", "unavailable"}:
            raise YuntuReportError("scriptAnalysis availability is invalid")
        evidence_refs = script_analysis.get("evidenceRefs")
        if not isinstance(evidence_refs, list) or any(not isinstance(ref, str) for ref in evidence_refs):
            raise YuntuReportError("scriptAnalysis evidenceRefs must be a list")
        fact = facts[material_id]
        index = fact.get("evidenceIndex", {}) if isinstance(fact.get("evidenceIndex"), dict) else {}
        known_script_refs = set(index.get("script", []))
        if not known_script_refs:
            known_script_refs = set(_chapter05_script_projection(fact, dive).get("evidenceRefs", []))
        if any(ref not in known_script_refs for ref in evidence_refs):
            raise YuntuReportError("scriptAnalysis evidenceRefs must belong to current material")
        conclusion = script_analysis.get("conclusion")
        script = fact.get("script", {}) if isinstance(fact.get("script"), dict) else {}
        has_script_text = bool(str(script.get("text") or fact.get("script_text") or "").strip())
        if availability == "available":
            if not has_script_text:
                raise YuntuReportError("scriptAnalysis must be unavailable when script text is absent")
            if not isinstance(conclusion, str) or not conclusion.strip():
                raise YuntuReportError(f"scriptAnalysis conclusion must be nonempty (material={material_id})")
            if not evidence_refs:
                raise YuntuReportError("scriptAnalysis evidenceRefs must not be empty when available")
            claim = SCRIPT_ANALYSIS_FORBIDDEN_CLAIM.search(conclusion)
            if claim:
                raise YuntuReportError(f"scriptAnalysis {material_id} conclusion contains unsupported claim: {claim.group(0)}")
        else:
            if not strict_semantic_contract:
                continue
            if has_script_text:
                raise YuntuReportError("scriptAnalysis must be available when script text exists")
            if evidence_refs:
                raise YuntuReportError("unavailable scriptAnalysis evidenceRefs must be empty")
            if not isinstance(conclusion, str) or not conclusion.strip():
                raise YuntuReportError("unavailable scriptAnalysis requires a reason")

    if set(dives_by_id) != set(selected_ids):
        raise YuntuReportError("materialDeepDives must cover every selected material")


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
                    source_root / target_rel,
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


def _copy_report_video_assets(fact_pack, output_dir, source_root=None):
    """Materialize only safe, persisted video files into the portable report."""
    output_dir = Path(output_dir)
    source_root = Path(source_root) if source_root is not None else output_dir.parent
    source_root = source_root.resolve()
    assets = {}
    for fact in fact_pack.get("materialFacts", []) if isinstance(fact_pack, dict) else []:
        if not isinstance(fact, dict):
            continue
        material_id = str(fact.get("material_id") or "")
        local_video = fact.get("localVideo") if isinstance(fact.get("localVideo"), dict) else {}
        relative_path = str(local_video.get("relative_path") or "").replace("\\", "/")
        if "localVideo" not in fact and re.fullmatch(r"[A-Za-z0-9_-]+", material_id):
            # Reports generated before video facts existed can still use retained assets.
            fallback_path = find_local_video_asset(source_root, material_id)
            if fallback_path is not None:
                local_video = {"available": True}
                relative_path = fallback_path.relative_to(source_root).as_posix()
        if not local_video.get("available") or not re.fullmatch(r"[A-Za-z0-9_-]+", material_id):
            assets[material_id] = {"available": False, "reason": "本批次未保存可交付的本地视频"}
            continue
        candidate = source_root / relative_path
        try:
            candidate.resolve().relative_to(source_root)
        except ValueError:
            assets[material_id] = {"available": False, "reason": "本地视频路径无效"}
            continue
        if (
            not relative_path
            or Path(relative_path).is_absolute()
            or ".." in Path(relative_path).parts
            or candidate.is_symlink()
            or not candidate.is_file()
            or candidate.stat().st_size <= 0
        ):
            assets[material_id] = {"available": False, "reason": "本地视频文件不可用"}
            continue
        target = output_dir / "assets" / "videos" / f"{material_id}.mp4"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(candidate, target)
        if target.is_symlink() or not target.is_file() or target.stat().st_size <= 0:
            raise YuntuReportError(f"report video asset is invalid: {material_id}")
        assets[material_id] = {
            "available": True,
            "src": f"assets/videos/{material_id}.mp4",
            "sizeBytes": target.stat().st_size,
        }
    return assets


def _validate_report_video_assets(video_assets, output_dir):
    output_dir = Path(output_dir)
    for material_id, asset in video_assets.items():
        if not isinstance(asset, dict) or asset.get("available") is not True:
            continue
        source = str(asset.get("src") or "")
        path = output_dir / source
        if not source.startswith("assets/videos/") or path.is_symlink() or not path.is_file() or path.stat().st_size <= 0:
            raise YuntuReportError(f"report video asset is missing: {material_id}")


def _generic_text(value):
    return str(value or "")


def _render_html(analysis, material_frames, fact_pack, presentation=None, highlight_workbook_href=None):
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

    highlight_export = ""
    if highlight_workbook_href:
        highlight_export = (
            '<div class="highlight-export-toolbar"><a class="highlight-export-button" href="'
            + html.escape(str(highlight_workbook_href), quote=True)
            + '" download>导出高光帧资产（Excel）</a></div>'
        )

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

    def section_scope(section_number, *scope_keys):
        badges = "".join(scope_badge(scope_key) for scope_key in scope_keys)
        if not badges:
            return ""
        return '<div class="report-scope-badges" aria-label="' + section_number + ' 章数据范围">' + badges + "</div>"

    def insight_cards(items):
        return "".join(
            f'<article class="insight-row"><p>{esc(_generic_text(item.get("summary", "")))}</p>'
            "</article>"
            for item in items
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
    frame_buttons = []
    for item in selected:
        material_id = str(item.get("material_id"))
        fact = facts.get(material_id, {})
        for frame in material_frames.get(material_id, []):
            if not frame.get("available") or not str(frame.get("relative_path", "")).endswith(".jpg"):
                continue
            label = "封面" if frame.get("is_cover") else f'{frame.get("second", 0)}s'
            reason = "/".join(str(value.get("trend_name") or value.get("type") or "") for value in frame.get("reasons", []) if isinstance(value, dict))
            rank = item.get("rank", "-")
            caption = f"#{rank} · {label} · {reason or '高光帧'}"
            frame_buttons.append(
                f'<button class="frame-button" type="button" data-material="{esc(material_id)}" data-frame="{html.escape(image_src(frame), quote=True)}" data-caption="{esc(caption)}" aria-label="查看 {esc(material_id)} {esc(label)} 高光帧"><img loading="lazy" src="{html.escape(image_src(frame), quote=True)}" alt="{esc(fact.get("title", material_id))} {esc(label)} 高光帧"><span>#{esc(rank)} · {esc(label)}</span></button>'
            )
    frame_options = "".join(f'<option value="{esc(str(item.get("material_id")))}">#{esc(item.get("rank", "-"))} {esc(facts.get(str(item.get("material_id")), {}).get("title", item.get("material_id"))[:18])}</option>' for item in selected)

    def highlight_frame_label(frame):
        if frame.get("frame_type") == "cover":
            return "封面画面"
        return f"点击 Top{frame.get('peak_rank')} 波峰画面"

    def highlight_material_title(frame):
        return str(frame.get("title", frame["material_id"])).removesuffix(".mp4")

    script_insights = render_script_insights(
        script_facts=fact_pack.get("scriptFacts"),
        script_insights=analysis.get("scriptInsights"),
        script_dashboard=((presentation or {}).get("chapters", {}).get("chapter03", {}).get("scriptDashboard") if isinstance(presentation, dict) else None),
        esc=esc,
    )
    highlight_insights = render_highlight_insights(
        successful_frames=_overview_highlight_frames(fact_pack),
        dashboard=analysis.get("highlightDashboard"),
        esc=esc,
        html_module=html,
        math_module=math,
        image_src=image_src,
        frame_label=highlight_frame_label,
        material_title=highlight_material_title,
        format_index_value=_format_index_value,
        failure_reason=_highlight_failure_reasons(fact_pack),
        category_order=HIGHLIGHT_RENDER_CATEGORY_ORDER,
        category_labels=HIGHLIGHT_CATEGORY_LABELS,
        presentation=(presentation or {}).get("chapters", {}).get("chapter04") if isinstance(presentation, dict) else None,
    )
    material_deep_dive = render_material_deep_dive(
        deep_dives=analysis.get("materialDeepDives"),
        selected_material_ids=_selected_material_ids(fact_pack),
        facts=facts,
        material_frames=material_frames,
        esc=esc,
        html_module=html,
        json_module=json,
        image_src=image_src,
        format_index_value=_format_index_value,
        format_metric=_format_metric,
        metric_labels=METRIC_LABELS,
        second_level_trends=SECOND_LEVEL_TRENDS,
        presentation=(presentation or {}).get("chapters", {}).get("chapter05") if isinstance(presentation, dict) else None,
    )

    top_material_combination = render_top_material_combination(
        analysis["topMaterialCombination"],
        esc=esc,
        generic_text=_generic_text,
        brand_order=configured_brands(fact_pack.get("filters", {})),
        presentation=(presentation or {}).get("chapters", {}).get("chapter01") if isinstance(presentation, dict) else None,
        jump_material_ids=_selected_material_ids(fact_pack),
    )
    audience_insights = render_audience_insights(
        fact_pack.get("audienceDashboard"),
        analysis=analysis,
        fact_pack=fact_pack,
        facts=facts,
        esc=esc,
        generic_text=_generic_text,
        insight_cards=insight_cards,
        dimension_labels=AUDIENCE_DIMENSION_LABELS,
        html_module=html,
        json_module=json,
        math_module=math,
        scope=section_scope("02", "ranking"),
        chapter02_facts=fact_pack.get("chapter02Facts"),
        presentation={**((presentation or {}).get("chapters", {}).get("chapter02") or {}), "scopeDefinitions": (presentation or {}).get("scopes", [])} if isinstance(presentation, dict) else None,
    )
    style = """
:root{--bg:#170d09;--paper:#fff8ec;--surface:#fffdf8;--ink:#2a170f;--muted:#705c50;--accent:#d79a4b;--accent-dark:#8e5528;--line:#dfcfbd;--line-dark:#4a2a1b;--positive:#406955;--focus:#f0bc64}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Segoe UI",sans-serif;font-size:16px;line-height:1.55}button,select,input{font:inherit}button,select{min-height:44px}.skip-link{position:fixed;left:12px;top:-60px;background:var(--paper);color:var(--ink);padding:10px;z-index:5}.skip-link:focus{top:12px}.page{width:min(1240px,calc(100% - 32px));margin:auto;padding:28px 0 72px}.report-cover{color:#fff;border-bottom:1px solid rgba(255,255,255,.24);padding:8px 0 28px}.report-cover p{max-width:68ch;color:#ead9c9;margin:0}.report-cover h1{font-size:2.6rem;line-height:1.1;margin:10px 0 12px;text-wrap:balance}.report-cover .cover-meta{display:flex;gap:8px;flex-wrap:wrap;margin-top:18px}.cover-meta span,.source-label{font-size:.75rem;font-weight:700}.cover-meta span{color:#f9d79b;border:1px solid rgba(249,215,155,.38);padding:4px 8px;border-radius:4px}.report-shell{display:grid;grid-template-columns:184px minmax(0,900px);gap:26px;align-items:start;margin-top:24px}.report-nav{position:sticky;top:18px;display:grid;gap:4px;padding:10px 0}.report-nav a{color:#dfc7ae;text-decoration:none;border-left:1px solid rgba(223,199,174,.35);padding:8px 10px;font-size:.875rem}.report-nav a:hover,.report-nav a:focus-visible,.report-nav a.active{color:#fff;background:#2a170f;border-left-color:var(--accent)}.report-nav small{color:#ac8970;padding:8px 10px}.report-content{min-width:0}.section{scroll-margin-top:18px;background:var(--paper);border:1px solid var(--line);border-radius:10px;padding:24px;margin-bottom:18px}.section-header{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;border-bottom:1px solid var(--line);padding-bottom:14px;margin-bottom:18px}.section-header h2{font-size:1.5rem;line-height:1.2;margin:0;text-wrap:balance}.section-header p{color:var(--muted);font-size:.875rem;margin:6px 0 0}.source-label{display:inline-block;color:var(--accent-dark);background:#f7e6cb;padding:4px 7px;border-radius:4px;white-space:nowrap}.insight-stack{display:grid;gap:0}.insight-row{padding:16px 0;border-bottom:1px solid var(--line)}.insight-row:last-child{border:0;padding-bottom:0}.insight-row p{margin:0;max-width:72ch}.material-references{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}.material-reference{color:var(--accent-dark);font-size:.8125rem;font-weight:700;text-decoration:none;border-bottom:1px solid currentColor}.evidence-details,.diagnosis details,.experiment details{margin-top:10px}.evidence-details summary,.diagnosis summary,.experiment summary{cursor:pointer;color:var(--accent-dark);font-weight:700}.evidence-details ul{padding-left:18px;color:var(--muted);font-size:.875rem}.baseline-strip{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-bottom:18px}.baseline{background:#f7ebd9;padding:10px;border-radius:6px}.baseline span,.baseline small{display:block;color:var(--muted);font-size:.75rem}.baseline b{display:block;font-size:1.05rem;font-variant-numeric:tabular-nums;margin:2px 0}.toolbar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:12px}.toolbar label{font-size:.8125rem;font-weight:700;color:var(--muted)}.toolbar select,.toolbar input{border:1px solid #ba9c7d;background:var(--surface);color:var(--ink);border-radius:5px;padding:6px 8px}.toolbar input{min-width:220px}.toolbar button{border:1px solid var(--accent-dark);background:transparent;color:var(--accent-dark);padding:6px 10px;border-radius:5px;cursor:pointer}.data-table{width:100%;border-collapse:collapse;font-size:.8125rem;overflow:hidden}.table-wrap{overflow:auto;border:1px solid var(--line);border-radius:6px}.data-table th{background:#f1dfc8;color:#5e3820;text-align:right;padding:9px 8px;white-space:nowrap}.data-table th:nth-child(2),.data-table td:nth-child(2){text-align:left}.data-table td{border-top:1px solid var(--line);padding:9px 8px;text-align:right;font-variant-numeric:tabular-nums}.data-table td small,.material-title span{display:block;color:var(--muted);font-size:.72rem;font-weight:400}.material-title{min-width:240px;max-width:360px}.rank{color:var(--accent-dark);font-weight:800}.tag-table td:first-child{text-align:left}.selection-bar{display:block;width:84px;height:6px;background:#ecd9c2;border-radius:99px;overflow:hidden}.selection-bar i{display:block;height:100%;background:var(--accent)}.trend-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px;margin-bottom:18px}.trend-summary{border-bottom:2px solid var(--accent);padding:8px 0}.trend-summary span,.trend-summary small{display:block;color:var(--muted);font-size:.72rem}.trend-summary b{font-size:1.125rem;font-variant-numeric:tabular-nums;margin-right:4px}.diagnosis{border-top:1px solid var(--line);padding:12px 0}.diagnosis summary{display:grid;grid-template-columns:52px 1fr auto;gap:10px;align-items:start;color:var(--ink)}.diagnosis summary span:last-child{color:var(--accent-dark);font-size:.8125rem}.diagnosis p{margin:12px 0 0;color:#483025}.frame-library{margin-top:26px;border-top:1px solid var(--line);padding-top:18px}.frame-library-head{display:flex;align-items:center;justify-content:space-between;gap:12px}.frame-library h3{margin:0;font-size:1.125rem}.frame-library select{border:1px solid #ba9c7d;background:var(--surface);padding:6px 8px;border-radius:5px}.highlight-gallery{display:grid;grid-template-columns:repeat(auto-fill,minmax(88px,1fr));gap:8px;margin-top:14px}.frame-button{border:1px solid var(--line);background:var(--surface);padding:4px;border-radius:6px;color:var(--muted);cursor:pointer;text-align:left;transition:border-color .18s ease,transform .18s ease}.frame-button img{display:block;width:100%;aspect-ratio:9/16;object-fit:cover;border-radius:3px}.frame-button span{display:block;font-size:.7rem;padding:4px 2px 1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.frame-button:hover{border-color:var(--accent-dark);transform:translateY(-1px)}.experiment{display:grid;grid-template-columns:48px 1fr;gap:12px;padding:16px 0;border-top:1px solid var(--line)}.experiment:first-of-type{border-top:0;padding-top:0}.experiment>span{color:var(--accent-dark);font-weight:800;font-size:.875rem}.experiment h3{font-size:1rem;line-height:1.45;margin:0}.experiment dl{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin:14px 0 0}.experiment dl div{border-top:1px solid var(--line);padding-top:7px}.experiment dt{color:var(--muted);font-size:.72rem}.experiment dd{margin:3px 0 0;font-size:.875rem}.data-note{color:var(--muted);font-size:.8125rem;margin:10px 0 0}.data-note strong{color:var(--ink)}dialog{border:0;padding:0;max-width:min(720px,92vw);background:transparent}dialog::backdrop{background:rgba(13,7,4,.88)}.lightbox{position:relative;background:#fff;padding:10px;border-radius:8px}.lightbox img{display:block;max-width:min(680px,88vw);max-height:82vh}.lightbox button{position:absolute;right:8px;top:8px;border:0;background:var(--ink);color:#fff;border-radius:5px;padding:6px 9px;cursor:pointer}.lightbox p{margin:7px 2px 0;font-size:.8125rem;color:var(--muted)}button:focus-visible,a:focus-visible,select:focus-visible,input:focus-visible,summary:focus-visible{outline:3px solid var(--focus);outline-offset:2px}@media(max-width:900px){.report-shell{grid-template-columns:1fr}.report-nav{position:sticky;top:0;z-index:2;background:var(--bg);grid-auto-flow:column;grid-auto-columns:max-content;overflow:auto;padding:8px 0}.report-nav small{display:none}.report-nav a{border-left:0;border-bottom:1px solid rgba(223,199,174,.35);white-space:nowrap}.report-nav a.active{border-bottom-color:var(--accent)}.section{padding:18px}.baseline-strip{grid-template-columns:repeat(2,minmax(0,1fr))}.trend-grid{grid-template-columns:repeat(3,minmax(0,1fr)}}@media(max-width:560px){.page{width:min(100% - 20px,1240px);padding-top:16px}.report-cover h1{font-size:2rem}.section-header{display:block}.source-label{margin-top:10px}.baseline-strip{grid-template-columns:1fr 1fr}.toolbar input{min-width:0;width:100%}.trend-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.diagnosis summary{grid-template-columns:42px 1fr}.diagnosis summary span:last-child{grid-column:2}.experiment dl{grid-template-columns:1fr}.highlight-gallery{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}.frame-button{transition:none}.frame-button:hover{transform:none}}
.performance-insights{margin-top:24px;border-top:1px solid var(--line);padding-top:18px}.performance-insights h3{margin:0;font-size:1.125rem}.performance-insights .insight-stack{margin-top:4px}.opportunity-charts{display:grid;gap:26px}.opportunity-charts article{min-width:0}.opportunity-charts h3{font-size:1.05rem;margin:0}.opportunity-charts p{color:var(--muted);font-size:.8125rem;margin:4px 0 12px}.chart-layout{min-width:0}.pie-layout{display:grid;grid-template-columns:180px minmax(0,1fr);gap:24px;align-items:center;min-height:180px}.pie-chart{border-radius:50%;display:grid;place-items:center;box-shadow:0 0 0 1px rgba(82,45,24,.12)}.pie-chart>span{display:grid;place-items:center;width:78px;height:78px;border-radius:50%;background:var(--paper);font-weight:800;font-variant-numeric:tabular-nums;text-align:center}.pie-chart small{color:var(--muted);font-size:.65rem;font-weight:400}.pie-legend{display:grid;gap:6px;padding:0;margin:0;list-style:none}.pie-legend li{display:grid;grid-template-columns:10px minmax(0,1fr) auto auto;gap:8px;align-items:center;font-size:.78rem;padding:3px 0;border-bottom:1px solid rgba(223,207,189,.7)}.pie-legend li:last-child{border-bottom:0}.pie-legend i{width:10px;height:10px;border-radius:2px}.pie-legend span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.pie-legend b{font-variant-numeric:tabular-nums}.pie-legend small{color:var(--muted);min-width:40px;text-align:right}.competitor-grid{display:grid;gap:0}.competitor-card{padding:16px 0;border-top:1px solid var(--line)}.competitor-card:first-child{padding-top:0;border-top:0}.competitor-card h3{font-size:1rem;margin:0 0 6px;color:var(--accent-dark)}.competitor-card p{margin:0;max-width:76ch}@media(max-width:700px){.pie-layout{grid-template-columns:140px minmax(0,1fr);gap:14px;min-height:140px}.pie-chart{width:140px!important;height:140px!important;flex-basis:140px!important}.pie-chart>span{width:64px;height:64px}.pie-legend li{font-size:.72rem;gap:6px}}@media(max-width:480px){.pie-layout{grid-template-columns:1fr}.pie-chart{justify-self:center}.pie-legend{width:100%}}
.top-material-overall h3,.top-material-brands h3{font-size:1.08rem;margin:0 0 12px}.top-material-overall>p,.brand-panel>p{margin:10px 0;max-width:76ch}.section-divider{height:0;border:0;border-top:1px solid var(--line);margin:30px 0}.brand-tabs{display:flex;gap:4px;overflow-x:auto;border-bottom:1px solid var(--line);padding:0 0 10px}.brand-tab{flex:0 0 auto;min-height:38px;border:0;border-bottom:2px solid transparent;border-radius:4px;background:transparent;color:var(--muted);padding:8px 12px;cursor:pointer;white-space:nowrap}.brand-tab:hover{color:var(--accent-dark);background:#f8ecd9}.brand-tab[aria-selected="true"]{border-bottom-color:var(--accent-dark);background:#f4e4ca;color:#5e3820;font-weight:700}.brand-panels{margin-top:16px;padding:18px 20px;background:#fbf0df;border-left:2px solid var(--accent)}.brand-panel[hidden]{display:none!important}.brand-panel{padding:0}.brand-panel-header{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;border-bottom:1px solid rgba(142,85,40,.2);padding-bottom:10px;margin-bottom:12px}.brand-current-brand{margin:0;color:#5e3820;font-weight:700}.brand-source{color:var(--muted);font-size:.75rem;margin:0!important}@media(max-width:560px){.brand-tabs{margin-right:-2px}.brand-tab{padding-inline:10px}.brand-panels{padding:16px}}
"""
    style = """
:root{--bg:#170d09;--paper:#fff8ec;--ink:#2a170f;--muted:#705c50;--accent:#d79a4b;--accent-dark:#8e5528;--line:#dfcfbd;--focus:#e8b85f}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Segoe UI",sans-serif;font-size:16px;line-height:1.65}button{font:inherit}.skip-link{position:fixed;left:12px;top:-60px;background:var(--paper);color:var(--ink);padding:10px;z-index:5}.skip-link:focus{top:12px}.page{width:min(1280px,calc(100% - 20px));margin:auto;padding:32px 0 72px}.report-cover{color:#fff;border-bottom:1px solid rgba(249,215,155,.32);padding:8px 0 28px}.report-cover p{max-width:68ch;color:#ead9c9;margin:0}.report-cover h1{font-size:2.5rem;line-height:1.15;margin:10px 0 12px;text-wrap:balance}.report-shell{display:grid;grid-template-columns:156px minmax(0,1fr);gap:18px;align-items:start;margin-top:24px}.report-nav{position:sticky;top:18px;display:grid;gap:5px;padding:10px 0}.report-nav small{color:#ac8970;padding:4px 10px;font-size:.75rem;font-weight:700}.report-nav a{border-left:1px solid rgba(223,199,174,.35);color:#dfc7ae;padding:8px 10px;font-size:.875rem;text-decoration:none}.report-nav a:hover,.report-nav a:focus-visible,.report-nav a[aria-current="location"]{border-left-color:var(--accent);background:#2a170f;color:#fff}.section{scroll-margin-top:18px;background:var(--paper);border:1px solid var(--line);border-radius:8px;padding:28px}.section-header{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;border-bottom:1px solid var(--line);padding-bottom:16px;margin-bottom:24px}.section-header h2{font-size:1.55rem;line-height:1.2;margin:0;text-wrap:balance}.section-header p{color:var(--muted);font-size:.875rem;margin:7px 0 0}.source-label{display:inline-block;color:var(--accent-dark);background:#f7e6cb;padding:4px 7px;border-radius:4px;font-size:.75rem;font-weight:700;white-space:nowrap}.top-material-overall h3,.top-material-brands h3{font-size:1.08rem;margin:0 0 12px}.top-material-overall>p,.brand-panel>p{margin:10px 0;max-width:76ch}.section-divider{height:0;border:0;border-top:1px solid var(--line);margin:32px 0}.brand-tabs{display:flex;gap:0;overflow-x:auto;border-bottom:1px solid var(--line);padding:0 2px}.brand-tab{position:relative;flex:0 0 auto;min-height:42px;border:0;border-radius:0;background:transparent;color:var(--muted);padding:8px 14px;cursor:pointer;white-space:nowrap}.brand-tab:hover{color:var(--accent-dark)}.brand-tab[aria-selected="true"]{color:#5e3820;font-weight:700}.brand-tab[aria-selected="true"]::after{position:absolute;right:12px;bottom:-1px;left:12px;height:2px;background:var(--accent-dark);content:""}.brand-tab:focus-visible{outline:2px solid var(--focus);outline-offset:-2px}.brand-panels{padding:18px 0 0}.brand-panel[hidden]{display:none!important}.brand-panel{border-left:2px solid var(--accent);padding:0 0 0 16px}@media(max-width:760px){.report-shell{grid-template-columns:1fr;gap:12px}.report-nav{position:static;display:flex;align-items:center;gap:8px;padding:0}.report-nav small{padding:0}.report-nav a{padding:5px 8px;border-left:0;border-bottom:1px solid rgba(223,199,174,.35)}}@media(max-width:560px){.page{width:min(100% - 20px,1280px);padding-top:18px}.report-cover h1{font-size:2rem}.section{padding:20px}.section-header{display:block}.source-label{margin-top:10px}.brand-tab{padding-inline:10px}.brand-panel{padding-left:12px}}
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
    style += """
.deep-visual-layout{display:grid;grid-template-columns:minmax(260px,0.8fr) minmax(300px,1fr);gap:16px;align-items:stretch}.deep-visual-layout>.material-video{display:block;width:100%;min-height:0;aspect-ratio:9/16;object-fit:contain;background:#1d120c;align-self:center}.deep-visual-layout>.material-video-unavailable{align-self:center;margin:0}.deep-visual-layout .deep-visual-strip{min-width:0;margin:0}.deep-frame-grid.fixed-six{grid-template-rows:repeat(2,minmax(0,auto));height:auto}.deep-frame-card{grid-template-rows:auto auto;overflow:visible}.deep-frame-card img{height:auto;aspect-ratio:9/16;object-fit:contain}@media(max-width:900px){.deep-visual-layout{grid-template-columns:1fr}.deep-visual-layout>.material-video{width:min(100%,640px)}}@media(max-width:560px){.deep-visual-layout .deep-frame-grid.fixed-six{grid-template-columns:repeat(2,minmax(0,1fr));grid-template-rows:repeat(3,minmax(0,auto));height:auto}}
    """
    style += '.highlight-export-toolbar{display:flex;justify-content:flex-end;margin:0 0 12px}.highlight-export-button{display:inline-flex;align-items:center;min-height:36px;border:1px solid var(--accent-dark);border-radius:999px;background:#2c1810;color:#fff8ec;padding:7px 14px;text-decoration:none;font-size:.8125rem;font-weight:800}.highlight-export-button:hover{background:var(--accent-dark)}.highlight-brand-tabs{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}.highlight-brand-tabs button{position:relative;min-height:40px;border:1px solid var(--line);border-radius:999px;background:#f7ead8;color:var(--muted);padding:8px 14px;cursor:pointer;white-space:nowrap}.highlight-brand-tabs button[aria-selected="true"]{border-color:var(--accent-dark);background:#2c1810;color:#fff;font-weight:800}.highlight-brand-panel[hidden]{display:none!important}.highlight-insight{margin:0 0 10px;padding:0;border-bottom:0}.highlight-insight:last-child{margin-bottom:0}.highlight-insight h5{margin:0 0 4px;font-size:.82rem}.highlight-insight p{margin:0;color:var(--muted);font-size:.82rem;line-height:1.55}'
    filters = fact_pack.get("filters", {}) if isinstance(fact_pack, dict) else {}
    industry = str(filters.get("industry") or "当前")
    brands = configured_brands(filters)
    brand_text = "、".join(brands) or aggregate_scope_label(fact_pack)
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
        top_material_scope=section_scope("01", "ranking"),
        highlight_scope=section_scope("04", "detail"),
        highlight_export=highlight_export,
        material_deep_dive_scope=section_scope("05", "detail"),
        top_material_combination=top_material_combination,
        audience_insights=audience_insights,
        script_insights=script_insights,
        highlight_insights=highlight_insights,
        material_deep_dive=material_deep_dive,
        baseline=baseline,
        material_tag_chart=material_tag_chart,
        people_tag_chart=people_tag_chart,
        trend_items=trend_items,
        frame_options=frame_options,
        frames="".join(frame_buttons),
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
    fact_pack = fact_pack or {}
    analysis = validate_analysis_input(
        analysis_json=analysis_json,
        fact_pack=fact_pack,
    )
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    report_video_assets = _copy_report_video_assets(
        fact_pack, output, highlight_asset_root
    )
    presentation = build_yuntu_presentation(
        analysis, fact_pack, report_video_assets=report_video_assets
    )
    data = {"status": "complete", "analysis": analysis, "presentation": presentation}
    if analysis_provenance is not None:
        data["analysisProvenance"] = analysis_provenance
    data["highlightFrames"] = {
        frame["frame_ref"]: frame for frame in _overview_highlight_frames(fact_pack)
    }
    if isinstance(fact_pack, dict) and isinstance(fact_pack.get("chapter02Facts"), dict):
        data["chapter02Facts"] = fact_pack["chapter02Facts"]
    audience_dashboard = fact_pack.get("audienceDashboard") if isinstance(fact_pack, dict) else None
    markdown = _render_markdown(analysis, audience_dashboard, fact_pack)
    _copy_highlight_assets(fact_pack, output, highlight_asset_root)
    export_path = export_highlight_workbook(
        fact_pack,
        (presentation or {}).get("chapters", {}).get("chapter04", {})
        if isinstance(presentation, dict)
        else {},
        output / "highlight-frames.xlsx",
        # Read the copied assets so the workbook embeds the same files shipped in the report.
        asset_root=output,
    )
    rendered_html = _render_html(
        analysis,
        _material_frames(fact_pack),
        fact_pack,
        presentation,
        highlight_workbook_href=export_path.name if export_path else None,
    )
    write_json_atomically(presentation, output / "presentation-report.json")
    write_json_atomically(data, output / "final-report-data.json")
    (output / "final-report.md").write_text(markdown, encoding="utf-8")
    (output / "final-report.html").write_text(rendered_html, encoding="utf-8")
    _validate_report_video_assets(report_video_assets, output)
    return 0
