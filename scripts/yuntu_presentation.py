"""Build a stable presentation projection from validated Yuntu report inputs."""

from copy import deepcopy
import math
import re
from pathlib import PurePosixPath

from yuntu_highlight_export import match_brands_from_title


PRESENTATION_SCHEMA_VERSION = 3
REPORT_TITLE = "云图行业内容榜单分析"
SECTION_IDS = ("chapter01", "chapter02", "chapter03", "chapter04", "chapter05")
REPORT_STATUSES = {"complete", "partial", "unavailable"}
HIGHLIGHT_CATEGORIES = ("portrait", "product", "scene", "text_overlay", "other")
SECOND_LEVEL_METRIC_ORDER = ("点赞指数", "流失指数", "点击指数", "互动指数", "评论指数")

# 云图内容公式接口返回数字 ID；detail.* 只保存某条素材命中的具体词，
# 不能用具体词反向充当一级/二级公式类别。
CONTENT_FORMULA_PRIMARY_LABELS = {
    "9": "商品卖点",
    "10": "品牌印象",
    "13": "人群",
    "15": "使用场景",
}
CONTENT_FORMULA_SECONDARY_LABELS = {
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


class YuntuPresentationError(ValueError):
    """Raised when the report inputs cannot form a safe presentation projection."""


def _text(value):
    return str(value or "").strip()


def _normalize_script_formula_text(value):
    """Replace legacy numeric formula references with YunTu semantic labels."""
    text = _text(value)
    if not text:
        return text

    def replace_sequence(match, level, prefix):
        body = match.group(1)
        parts = re.split(r"(\s*(?:和|、|/)\s*)", body)
        rendered = []
        for part in parts:
            identifier = re.search(r"\d+", part)
            if identifier:
                label = content_formula_label(level, identifier.group(0))
                rendered.append(f'“{label}”' if label else part)
            else:
                rendered.append(part)
        return prefix + "".join(rendered)

    sequence_patterns = (
        ("primary", "一级公式", r"一级标签\s*(\d+(?:\s*[“\"][^”\"]+[”\"])?(?:\s*(?:和|、|/)\s*\d+(?:\s*[“\"][^”\"]+[”\"])?)+)"),
        ("secondary", "二级公式", r"二级标签\s*(\d+(?:\s*[“\"][^”\"]+[”\"])?(?:\s*(?:和|、|/)\s*\d+(?:\s*[“\"][^”\"]+[”\"])?)+)"),
    )
    for level, prefix, pattern in sequence_patterns:
        text = re.sub(
            pattern,
            lambda match: replace_sequence(match, level, prefix),
            text,
        )

    def replace_single(match):
        level = "primary" if match.group(1) == "一级" else "secondary"
        label = content_formula_label(level, match.group(2))
        return f'{match.group(1)}公式“{label}”' if label else match.group(0)

    text = re.sub(r"(一级|二级)标签\s*(\d+)(?:\s*[“\"][^”\"]+[”\"])?", replace_single, text)
    text = re.sub(
        r"(?<!\d)10\s*/\s*9(?=\s*对应)",
        '“品牌印象”/“商品卖点”',
        text,
    )
    return text


def content_formula_label(level, value, explicit_label=None):
    """Resolve a YunTu formula ID to its semantic category label."""
    labels = (
        CONTENT_FORMULA_PRIMARY_LABELS
        if level == "primary"
        else CONTENT_FORMULA_SECONDARY_LABELS
    )
    raw_value = value
    if isinstance(value, dict):
        raw_value = value.get("value") or value.get("id")
        explicit_label = explicit_label or value.get("label")
    identifier = _text(raw_value)
    if identifier in labels:
        return labels[identifier]
    label = _text(explicit_label)
    return label if label and not label.isdigit() else ""


def _formula_value_and_label(value):
    if isinstance(value, dict):
        return _text(value.get("value") or value.get("id")), _text(value.get("label"))
    return _text(value), ""


def _safe_relative_frame_path(value):
    raw = _text(value).replace("\\", "/")
    path = PurePosixPath(raw)
    if not raw or path.is_absolute() or ".." in path.parts:
        raise YuntuPresentationError("relative frame path is invalid")
    return path.as_posix()


def _finite_number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise YuntuPresentationError(f"{label} is invalid")
    return value


def _scope_id(scope_key):
    if scope_key == "all":
        return "all"
    tokens = []
    current = []
    for character in _text(scope_key).lower():
        if character.isascii() and character.isalnum():
            current.append(character)
        elif not character.isascii():
            if current:
                tokens.append("".join(current))
                current = []
            tokens.append(f"u{ord(character):x}")
        elif current:
            tokens.append("".join(current))
            current = []
    if current:
        tokens.append("".join(current))
    return "brand-" + "-".join(tokens or ["unknown"])


def _report_metadata(fact_pack, report_meta):
    filters = fact_pack.get("filters", {}) if isinstance(fact_pack, dict) else {}
    metadata = report_meta if isinstance(report_meta, dict) else {}
    status = _text(metadata.get("status")) or "complete"
    if status not in REPORT_STATUSES:
        raise YuntuPresentationError("report status is invalid")
    return {
        "reportId": _text(metadata.get("reportId")),
        "title": _text(metadata.get("title")) or REPORT_TITLE,
        "period": {
            "startDate": _text(metadata.get("startDate") or filters.get("startDate") or filters.get("start_date")),
            "endDate": _text(metadata.get("endDate") or filters.get("endDate") or filters.get("end_date")),
        },
        "status": status,
        "sections": list(SECTION_IDS),
    }


def _copy_insights(items):
    if not isinstance(items, list):
        return []
    result = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise YuntuPresentationError("chapter02 insight is invalid")
        summary = _text(item.get("summary"))
        if not summary:
            raise YuntuPresentationError("chapter02 insight summary is required")
        result.append({
            "id": f"insight-{index}",
            "title": _text(item.get("title") or item.get("dimension")),
            "text": summary,
            "evidence": deepcopy(item.get("evidence", [])),
            "materialIds": [str(value) for value in item.get("material_ids", []) if _text(value)],
            "materialId": _text(item.get("material_id")),
            "parts": {},
        })
    return result


def _copy_insight(item):
    if item is None:
        return None
    if not isinstance(item, dict):
        raise YuntuPresentationError("chapter02 dimension summary is invalid")
    return {
        "title": _text(item.get("title")),
        "text": _text(item.get("summary")),
        "evidence": deepcopy(item.get("evidence", [])),
        "materialIds": [str(value) for value in item.get("material_ids", []) if _text(value)],
        "materialId": _text(item.get("material_id")),
    }


def _chapter02_sources(fact_pack):
    chart_facts = fact_pack.get("chapter02Facts", {})
    ai_facts = fact_pack.get("chapter02AiFacts", {})
    if not chart_facts or not ai_facts:
        return {}, {}, []
    if not isinstance(chart_facts, dict) or not isinstance(ai_facts, dict):
        raise YuntuPresentationError("chapter02 facts are invalid")
    chart_order = chart_facts.get("scopeOrder")
    ai_order = ai_facts.get("scopeOrder")
    if not isinstance(chart_order, list) or chart_order != ai_order or not chart_order or chart_order[0] != "all":
        raise YuntuPresentationError("chapter02 scope order is invalid")
    if any(_text(scope) not in chart_facts or _text(scope) not in ai_facts for scope in chart_order):
        raise YuntuPresentationError("chapter02 scope facts are incomplete")
    return chart_facts, ai_facts, chart_order


def _chart_bucket(key, label, value, rank, *, raw_tag=None):
    bucket = {
        "key": _text(key),
        "label": _text(label),
        "value": _finite_number(value, "chart value"),
        "rank": rank,
    }
    if _text(raw_tag):
        bucket["rawTag"] = _text(raw_tag)
    return bucket


def _marketing_charts(scope_id, scope_fact):
    dashboard = scope_fact.get("marketingDashboard", {}) if isinstance(scope_fact, dict) else {}
    categories = dashboard.get("categories", []) if isinstance(dashboard, dict) else []
    if not isinstance(categories, list):
        raise YuntuPresentationError("marketing categories are invalid")
    primary_buckets = []
    detail_views = []
    for index, category in enumerate(categories, start=1):
        if not isinstance(category, dict):
            raise YuntuPresentationError("marketing category is invalid")
        name = _text(category.get("category"))
        if not name:
            raise YuntuPresentationError("marketing category name is required")
        primary_buckets.append(_chart_bucket(name, name, category.get("occurrenceCount", 0), index))
        tags = category.get("tags", [])
        if not isinstance(tags, list):
            raise YuntuPresentationError("marketing tags are invalid")
        tag_buckets = []
        for tag_index, tag in enumerate(tags, start=1):
            if not isinstance(tag, dict) or not _text(tag.get("tag")):
                raise YuntuPresentationError("marketing tag is invalid")
            tag_buckets.append(
                _chart_bucket(
                    tag["tag"],
                    tag["tag"],
                    tag.get("count", 0),
                    tag_index,
                    raw_tag=tag.get("rawTag"),
                )
            )
        detail_views.append({
            "id": f"{scope_id}-marketing-level2-{index}",
            "category": name,
            "pie": {
                "id": f"{scope_id}-marketing-level2-pie-{index}",
                "type": "pie",
                "title": f"{name}二级标签",
                "dataSource": "chapter02Facts",
                "scopeId": scope_id,
                "value": {"field": "count", "unit": "count"},
                "buckets": tag_buckets,
                "interaction": {"type": "none"},
                "accessibility": {"label": f"{name}二级标签饼图"},
            },
            "table": {
                "id": f"{scope_id}-marketing-level2-table-{index}",
                "type": "table",
                "title": f"{name}全部标签明细",
                "dataSource": "chapter02Facts",
                "scopeId": scope_id,
                "value": {"field": "count", "unit": "count"},
                "buckets": tag_buckets,
                "interaction": {"type": "expand"},
                "accessibility": {"label": f"{name}全部标签明细表"},
            },
        })
    primary_id = f"{scope_id}-marketing-level1"
    return [{
        "id": primary_id,
        "type": "column",
        "title": "营销卖点汇总",
        "dataSource": "chapter02Facts",
        "scopeId": scope_id,
        "value": {"field": "occurrenceCount", "unit": "count"},
        "buckets": primary_buckets,
        "interaction": {"type": "column-drilldown", "target": f"{scope_id}-marketing-level2"},
        "accessibility": {"label": "营销卖点汇总柱状图"},
    }], detail_views


def _project_chapter02(analysis, fact_pack):
    chart_facts, _ai_facts, scope_order = _chapter02_sources(fact_pack)
    if not scope_order:
        return [], {"scopeTabs": {"interactionId": "chapter02-scope-tabs", "items": []}, "panels": []}, {}
    insights = analysis.get("chapter02Insights", {}) if isinstance(analysis, dict) else {}
    insight_order = insights.get("scopeOrder", scope_order) if isinstance(insights, dict) else scope_order
    insight_scopes = insights.get("scopes", {}) if isinstance(insights, dict) else {}
    if insight_order != scope_order or (insight_scopes and set(insight_scopes) != set(scope_order)):
        raise YuntuPresentationError("chapter02 analysis scope order is invalid")
    scopes, panels, tab_items = [], [], []
    interaction_targets = {}
    for index, scope_key in enumerate(scope_order):
        scope_key = _text(scope_key)
        scope_id = _scope_id(scope_key)
        scope_fact = chart_facts[scope_key]
        if not isinstance(scope_fact, dict):
            raise YuntuPresentationError("chapter02 scope fact is invalid")
        scopes.append({
            "id": scope_id,
            "sourceKey": scope_key,
            "label": _text(scope_fact.get("label")) or scope_key,
            "kind": "industry" if scope_key == "all" else "brand",
            "rankScope": "top1000" if scope_key == "all" else "all-materials",
            "aiFactSource": "chapter02AiFacts",
            "chartFactSource": "chapter02Facts",
        })
        scope_insights = insight_scopes.get(scope_key, {}) if isinstance(insight_scopes, dict) else {}
        charts, detail_views = _marketing_charts(scope_id, scope_fact)
        target_id = f"{scope_id}-marketing-level2"
        interaction_targets[target_id] = [item["id"] for item in detail_views]
        panels.append({
            "id": f"chapter02-{scope_id}",
            "scopeId": scope_id,
            "aiFactSource": "chapter02AiFacts",
            "chartFactSource": "chapter02Facts",
            "aiInsights": {
                "audienceSummary": _copy_insight(scope_insights.get("audienceSummary")),
                "marketingSummary": _copy_insight(scope_insights.get("marketingSummary")),
            },
            "audienceDashboard": deepcopy(scope_fact.get("audienceDashboard", {})),
            "topMaterials": deepcopy(scope_fact.get("topMaterials", [])),
            "charts": charts,
            "detailViews": detail_views,
            **(
                {"marketingTagTaxonomyVersion": scope_fact["marketingDashboard"]["taxonomyVersion"]}
                if isinstance(scope_fact.get("marketingDashboard"), dict)
                and scope_fact["marketingDashboard"].get("taxonomyVersion") is not None
                else {}
            ),
        })
        tab_items.append({"id": scope_id, "label": scopes[-1]["label"], "panelId": panels[-1]["id"]})
    return scopes, {
        "scopeTabs": {"interactionId": "chapter02-scope-tabs", "items": tab_items},
        "panels": panels,
    }, {
        "chapter02-scope-tabs": {"id": "chapter02-scope-tabs", "type": "tab-list", "items": tab_items, "defaultItemId": tab_items[0]["id"], "keyboard": ["ArrowLeft", "ArrowRight", "Home", "End"]},
        **{target: {"id": target, "type": "column-drilldown", "targets": values} for target, values in interaction_targets.items()},
    }


def _script_insights(analysis, material_ids):
    insights = analysis.get("scriptInsights", []) if isinstance(analysis, dict) else []
    if insights in (None, []):
        return []
    if not isinstance(insights, list):
        raise YuntuPresentationError("scriptInsights must be a list")
    allowed = set(material_ids)
    projected = []
    for index, item in enumerate(insights, start=1):
        if not isinstance(item, dict):
            raise YuntuPresentationError("script insight is invalid")
        title = _text(item.get("title"))
        summary = _text(item.get("summary"))
        if "公式" in title or "公式" in summary:
            title = _normalize_script_formula_text(title)
            summary = _normalize_script_formula_text(summary)
        evidence = deepcopy(item.get("evidence", []))
        ids = [str(value) for value in item.get("material_ids", []) if _text(value)]
        if not title or not summary or not ids or not set(ids).issubset(allowed):
            raise YuntuPresentationError("script insight evidence is invalid")
        projected.append({
            "id": f"script-insight-{index}",
            "title": title,
            "text": summary,
            "evidence": evidence,
            "materialIds": ids,
        })
    return projected


def _script_frequency_items(frequencies, dimension):
    values = frequencies.get(dimension, {}) if isinstance(frequencies, dict) else {}
    if not isinstance(values, dict):
        return []
    items = []
    for label, value in values.items():
        if not isinstance(value, dict) or not _text(label):
            continue
        material_ids = [str(item) for item in value.get("material_ids", []) if _text(item)]
        count = value.get("count", len(material_ids))
        if isinstance(count, bool) or not isinstance(count, (int, float)):
            count = len(material_ids)
        items.append({
            "label": _text(label),
            "count": count,
            "materialIds": material_ids,
            "dimension": dimension,
        })
    return sorted(items, key=lambda item: (-item["count"], item["label"]))


def _script_keywords(frequencies):
    merged = {}
    for dimension in ("selling_points", "scenes", "promotions", "marketing_formats"):
        for item in _script_frequency_items(frequencies, dimension):
            entry = merged.setdefault(item["label"], {"label": item["label"], "materialIds": [], "dimensions": []})
            for material_id in item["materialIds"]:
                if material_id not in entry["materialIds"]:
                    entry["materialIds"].append(material_id)
            if dimension not in entry["dimensions"]:
                entry["dimensions"].append(dimension)
    for item in merged.values():
        item["count"] = len(item["materialIds"])
    return sorted(merged.values(), key=lambda item: (-item["count"], item["label"]))


def _formula_hierarchy(materials):
    primary = {}
    secondary = {}
    for material in materials:
        if not isinstance(material, dict):
            continue
        formula = material.get("content_formula")
        labels = formula.get("labels") if isinstance(formula, dict) else None
        if not isinstance(labels, list):
            continue
        detail_labels = {
            _text(str(key)[len("detail."):]): [_text(value)]
            for key, value in formula.items()
            if str(key).startswith("detail.") and _text(str(key)[len("detail."):]) and _text(value)
        }
        material_id = _text(material.get("material_id"))
        seen_primary = set()
        seen_secondary = set()
        for item in labels:
            if not isinstance(item, dict):
                continue
            primary_id, primary_explicit_label = _formula_value_and_label(
                item.get("level_1_label") or item.get("level1_label")
            )
            if not primary_id:
                continue
            primary_label = content_formula_label("primary", primary_id, primary_explicit_label) or primary_id
            primary_entry = primary.setdefault(primary_id, {"id": primary_id, "label": primary_label, "count": 0, "materialIds": []})
            if primary_id not in seen_primary:
                primary_entry["count"] += 1
                if material_id and material_id not in primary_entry["materialIds"]:
                    primary_entry["materialIds"].append(material_id)
                seen_primary.add(primary_id)
            values = item.get("level_2_labels") or item.get("level2_labels") or []
            if not isinstance(values, list):
                values = [values]
            children = secondary.setdefault(primary_id, {})
            for value in values:
                secondary_id, secondary_explicit_label = _formula_value_and_label(value)
                if not secondary_id:
                    continue
                pair = (primary_id, secondary_id)
                secondary_label = content_formula_label("secondary", secondary_id, secondary_explicit_label) or secondary_id
                child = children.setdefault(secondary_id, {"id": secondary_id, "label": secondary_label, "count": 0, "materialIds": [], "detailLabels": []})
                if pair in seen_secondary:
                    continue
                child["count"] += 1
                if material_id and material_id not in child["materialIds"]:
                    child["materialIds"].append(material_id)
                for detail in detail_labels.get(secondary_id, []):
                    if detail not in child["detailLabels"]:
                        child["detailLabels"].append(detail)
                seen_secondary.add(pair)
    return {
        "primary": sorted(primary.values(), key=lambda item: (-item["count"], item["label"])),
        "secondary": {
            primary_id: sorted(children.values(), key=lambda item: (-item["count"], item["label"]))
            for primary_id, children in secondary.items()
        },
    }


def _content_formula_text(content_formula, key):
    if not isinstance(content_formula, dict):
        return ""
    return _text(content_formula.get(key))


def _content_formula_detail(content_formula, value):
    if not isinstance(content_formula, dict):
        return ""
    raw_value = value.get("value") or value.get("id") if isinstance(value, dict) else value
    detail = _text(content_formula.get(f"detail.{_text(raw_value)}"))
    if detail:
        return detail
    target_label = content_formula_label("secondary", raw_value) or _text(raw_value)
    for item in content_formula.get("labels", []) if isinstance(content_formula.get("labels"), list) else []:
        if not isinstance(item, dict):
            continue
        values = item.get("level_2_labels") or item.get("level2_labels") or []
        if not isinstance(values, list):
            values = [values]
        for candidate in values:
            if content_formula_label("secondary", candidate) == target_label or _text(candidate) == target_label:
                detail = _text(content_formula.get(f"detail.{_text(candidate.get('value') or candidate.get('id') if isinstance(candidate, dict) else candidate)}"))
                if detail:
                    return detail
    return ""


def _chapter05_formula_items(raw_script, content_formula):
    source_formula = raw_script.get("formula") if isinstance(raw_script, dict) else None
    formula = []
    if isinstance(source_formula, list) and source_formula:
        for item in source_formula:
            if not isinstance(item, dict):
                continue
            level1 = _text(item.get("level1") or item.get("level_1") or item.get("level1_label") or item.get("level_1_label"))
            level2 = _text(item.get("level2") or item.get("level_2") or item.get("level2_label") or item.get("level_2_label"))
            if not level1 and not level2:
                continue
            normalized = {"level1": level1, "level2": level2}
            detail = _text(item.get("detail") or item.get("detailLabel") or item.get("detail_label")) or _content_formula_detail(content_formula, level2)
            if detail:
                normalized["detail"] = detail
            formula.append(normalized)
        return formula

    labels = content_formula.get("labels") if isinstance(content_formula, dict) else []
    if not isinstance(labels, list):
        return formula
    for item in labels:
        if not isinstance(item, dict):
            continue
        primary_value = item.get("level_1_label") or item.get("level1_label") or item.get("level1")
        primary = content_formula_label("primary", primary_value) or _text(primary_value)
        secondary_values = item.get("level_2_labels") or item.get("level2_labels") or item.get("level2") or []
        if not isinstance(secondary_values, list):
            secondary_values = [secondary_values]
        for secondary_value in secondary_values:
            secondary = content_formula_label("secondary", secondary_value) or _text(secondary_value)
            if not primary and not secondary:
                continue
            normalized = {"level1": primary, "level2": secondary}
            detail = _content_formula_detail(content_formula, secondary_value)
            if detail:
                normalized["detail"] = detail
            formula.append(normalized)
    return formula


def _chapter05_copy_blocks(material_id, content_formula, formula):
    sources = (
        ("video_title", "视频标题", "视频标题.text"),
        ("video_frame", "视频画面", "视频画面.text"),
    )
    blocks = []
    for source_id, label, source_key in sources:
        text = _content_formula_text(content_formula, source_key)
        if not text:
            continue
        evidence = []
        used_refs = set()
        for formula_index, item in enumerate(formula):
            for term in _chapter05_formula_terms(item):
                if term not in text:
                    continue
                reference = f"script:{material_id}:{source_id}:{term}"
                if reference in used_refs:
                    reference += f":formula:{formula_index}"
                used_refs.add(reference)
                evidence.append({
                    "formulaIndex": formula_index,
                    "level1": _text(item.get("level1")),
                    "level2": _text(item.get("level2")),
                    "detail": _text(item.get("detail")),
                    "sentence": term,
                    "evidenceRef": reference,
                })
        blocks.append({"id": source_id, "label": label, "text": text, "evidence": evidence})
    return blocks


def _chapter05_formula_terms(item):
    """Return the concrete, non-overlapping terms that may be located in copy."""
    values = (_text(item.get("detail")), _text(item.get("level2")), _text(item.get("level1")))
    terms = []
    for value in values:
        for term in re.split(r"[、，,/／]+", value):
            term = term.strip()
            if term and term not in terms:
                terms.append(term)
    return sorted(terms, key=len, reverse=True)


def _chapter05_script_projection(fact, dive):
    """Project selected material script facts and deterministic copy evidence."""
    material_id = _text(fact.get("material_id"))
    raw_script = fact.get("script") if isinstance(fact.get("script"), dict) else {}
    script_text = _text(raw_script.get("text") or fact.get("script_text"))
    content_formula = fact.get("content_formula") if isinstance(fact.get("content_formula"), dict) else {}
    formula = _chapter05_formula_items(raw_script, content_formula)
    if not formula:
        formula = []
    evidence = deepcopy(raw_script.get("evidence")) if isinstance(raw_script.get("evidence"), list) else []
    if not evidence and script_text:
        used_refs = set()
        for formula_index, item in enumerate(formula):
            for term in _chapter05_formula_terms(item):
                if term not in script_text:
                    continue
                reference = f"script:{material_id}:text:{term}"
                if reference in used_refs:
                    reference += f":formula:{formula_index}"
                used_refs.add(reference)
                evidence.append({
                    "formulaIndex": formula_index,
                    "level1": _text(item.get("level1")),
                    "level2": _text(item.get("level2")),
                    "detail": _text(item.get("detail")),
                    "sentence": term,
                    "evidenceRef": reference,
                })
    evidence = [item for item in evidence if isinstance(item, dict) and _text(item.get("sentence")) and _text(item.get("evidenceRef"))]
    copy_blocks = _chapter05_copy_blocks(material_id, content_formula, formula)
    index = fact.get("evidenceIndex") if isinstance(fact.get("evidenceIndex"), dict) else {}
    evidence_refs = [str(ref) for ref in index.get("script", []) if _text(ref)]
    if not evidence_refs:
        evidence_refs = [
            f"script:{material_id}:{item.get('level1')}:{item.get('level2')}"
            for item in formula
            if isinstance(item, dict) and _text(item.get("level1"))
        ]
        evidence_refs.extend(
            str(item.get("evidenceRef")) for item in evidence
            if isinstance(item, dict) and item.get("evidenceRef")
        )
    for block in copy_blocks:
        evidence_refs.extend(
            str(item.get("evidenceRef")) for item in block.get("evidence", [])
            if isinstance(item, dict) and item.get("evidenceRef")
        )
    evidence_refs = list(dict.fromkeys(ref for ref in evidence_refs if ref.startswith(f"script:{material_id}:")))
    for formula_index, item in enumerate(formula):
        refs = []
        for candidate in evidence:
            if not isinstance(candidate, dict):
                continue
            if candidate.get("formulaIndex") == formula_index or (
                candidate.get("formulaIndex") is None and (
                    _text(candidate.get("level2")) == _text(item.get("level2"))
                    or _text(candidate.get("level1")) == _text(item.get("level1"))
                )
            ):
                refs.append(_text(candidate.get("evidenceRef")))
        for block in copy_blocks:
            refs.extend(
                _text(candidate.get("evidenceRef"))
                for candidate in block.get("evidence", [])
                if isinstance(candidate, dict) and candidate.get("formulaIndex") == formula_index
            )
        refs = list(dict.fromkeys(ref for ref in refs if ref))
        if refs:
            item["evidenceRefs"] = refs
    script_available = bool(script_text or formula or evidence or copy_blocks)
    return {
        "text": script_text,
        "formula": formula,
        "evidence": evidence,
        "copyBlocks": copy_blocks,
        "evidenceRefs": evidence_refs,
        "availability": _text(raw_script.get("availability")) if _text(raw_script.get("availability")) in {"available", "unavailable"} else ("available" if script_available else "unavailable"),
    }


def _project_keyword_cloud(facts, analysis, material_ids):
    """Apply the AI review to deterministic keyword facts without re-counting text."""
    raw_cloud = facts.get("keywordCloud", {}) if isinstance(facts, dict) else {}
    raw_keywords = raw_cloud.get("keywords", []) if isinstance(raw_cloud, dict) else []
    if not isinstance(raw_keywords, list):
        raw_keywords = []

    ai_source = analysis if isinstance(analysis, dict) else {}
    review_items = ai_source.get("keywordCloudReview", [])
    if not isinstance(review_items, list):
        review_items = []
    review = {
        _text(item.get("keyword")): {
            "decision": _text(item.get("decision")),
            "target": _text(item.get("target")),
        }
        for item in review_items
        if isinstance(item, dict) and _text(item.get("keyword"))
    }
    allowed_material_ids = {str(value) for value in material_ids}
    merged = {}
    for raw in raw_keywords:
        if not isinstance(raw, dict) or not _text(raw.get("keyword")):
            continue
        keyword = _text(raw.get("keyword"))
        decision = review.get(keyword, {}).get("decision", "accept")
        if decision == "exclude":
            continue
        target = review.get(keyword, {}).get("target", "") if decision == "merge" else ""
        projected_keyword = target or keyword
        item = merged.setdefault(projected_keyword, {
            "keyword": projected_keyword,
            "frequency": 0,
            "materialIds": [],
            "evidenceRefs": [],
        })
        frequency = raw.get("frequency", 0)
        if isinstance(frequency, bool) or not isinstance(frequency, (int, float)):
            frequency = 0
        item["frequency"] += frequency
        for value in raw.get("materialIds", []):
            value = str(value)
            if value in allowed_material_ids and value not in item["materialIds"]:
                item["materialIds"].append(value)
        for ref in raw.get("evidenceRefs", []):
            ref = _text(ref)
            if ref and ref not in item["evidenceRefs"]:
                item["evidenceRefs"].append(ref)

    keywords = sorted(merged.values(), key=lambda item: (-item["frequency"], item["keyword"]))
    ai_cloud = ai_source.get("keywordCloudInsight", {})
    if not isinstance(ai_cloud, dict):
        ai_cloud = {}
    valid_keywords = {item["keyword"] for item in keywords}
    valid_refs = {ref for item in keywords for ref in item["evidenceRefs"]}
    selling_points = []
    raw_selling_points = ai_cloud.get("sellingPoints", [])
    if not isinstance(raw_selling_points, list):
        raw_selling_points = []
    for raw in raw_selling_points[:4]:
        if not isinstance(raw, dict):
            continue
        keyword_refs = [
            _text(ref) for ref in raw.get("keywordRefs", [])
            if _text(ref) in valid_keywords
        ]
        evidence_refs = [
            _text(ref) for ref in raw.get("evidenceRefs", [])
            if _text(ref) in valid_refs
        ]
        title = _text(raw.get("title"))
        description = _text(raw.get("description"))
        if title and description and keyword_refs and evidence_refs:
            selling_points.append({
                "title": title,
                "description": description,
                "keywordRefs": keyword_refs,
                "evidenceRefs": evidence_refs,
            })
    return {
        "oneSentenceConclusion": _text(ai_cloud.get("oneSentenceConclusion")),
        "summary": _text(ai_cloud.get("summary")),
        "keywords": keywords,
        "sellingPoints": selling_points,
        "source": "facts.scriptFacts.keywordCloud + ai.keywordCloudInsight",
        "evidenceRefs": list(dict.fromkeys(
            ref for item in keywords for ref in item["evidenceRefs"]
        )),
        "availability": "available" if keywords else "unavailable",
    }


def _project_chapter03(analysis, fact_pack):
    facts = fact_pack.get("scriptFacts") if isinstance(fact_pack, dict) else None
    if not isinstance(facts, dict):
        facts = {
            "scope": "selected_detail_materials",
            "coverage": {"total": 0, "script": 0, "rate": 0},
            "frequencies": {},
            "materials": [],
            "limitations": ["未提供脚本事实，数据不足以判断。"],
        }
    materials = []
    material_ids = []
    for item in facts.get("materials", []):
        if not isinstance(item, dict):
            continue
        material_id = _text(item.get("material_id"))
        if not material_id:
            continue
        material_ids.append(material_id)
        availability = item.get("data_availability", {})
        script_state = availability.get("script_text", {}) if isinstance(availability, dict) else {}
        segments_state = availability.get("script_segments", {}) if isinstance(availability, dict) else {}
        materials.append({
            "materialId": material_id,
            "rank": item.get("rank"),
            "scriptText": _text(item.get("script_text")),
            "scriptSegments": deepcopy(item.get("script_segments", [])),
            "scriptSegmentsAvailable": bool(segments_state.get("available")),
            "contentFormula": deepcopy(item.get("content_formula")),
            "creativeBreakdown": deepcopy(item.get("creative_breakdown")),
            "metrics": deepcopy(item.get("metrics", {})),
            "availability": _text(script_state.get("missing_reason")) if not script_state.get("available") else "available",
        })
    insights = _script_insights(analysis, material_ids)[:2]
    frequencies = facts.get("frequencies", {}) if isinstance(facts.get("frequencies"), dict) else {}
    coverage = deepcopy(facts.get("coverage", {"total": len(materials), "script": 0, "rate": 0}))
    if insights:
        conclusion = {
            "text": insights[0]["text"],
            "materialIds": deepcopy(insights[0]["materialIds"]),
            "source": "scriptInsights",
        }
    else:
        conclusion = {
            "text": f"已获取详情素材中脚本文本覆盖 {coverage.get('script', 0)}/{coverage.get('total', len(materials))} 个素材；当前数据不足以判断脚本文案结构。",
            "materialIds": [],
            "source": "coverage",
        }
    content_formula = _formula_hierarchy(facts.get("materials", []))
    keyword_cloud_panel = _project_keyword_cloud(facts, analysis, material_ids)
    dashboard = {
        "scope": _text(facts.get("scope")) or "selected_detail_materials",
        "scopeLabel": "已获取详情素材",
        "coverage": coverage,
        "conclusion": conclusion,
        "keywords": _script_keywords(frequencies),
        "sellingPoints": _script_frequency_items(frequencies, "selling_points"),
        "keywordCloudPanel": keyword_cloud_panel,
        "frequencies": deepcopy(frequencies),
        "dimensions": {
            "contentFormula": {
                "label": "一二级内容公式",
                **content_formula,
            },
            "scriptCopy": {
                "label": "脚本文案",
                "coverage": deepcopy(coverage),
                "materials": deepcopy(materials),
            },
        },
        "materials": materials,
        "insights": insights,
        "limitations": deepcopy(facts.get("limitations", [])),
    }
    return {"scriptDashboard": dashboard}


def _project_chapter01(analysis, fact_pack):
    combination = analysis.get("topMaterialCombination", {}) if isinstance(analysis, dict) else {}
    if not combination:
        return {"brandTabs": [], "brandPanels": []}
    if not isinstance(combination, dict):
        raise YuntuPresentationError("chapter01 combination is invalid")
    brands = combination.get("brandConclusions", [])
    if not isinstance(brands, list):
        raise YuntuPresentationError("chapter01 brand conclusions are invalid")
    panels = []
    aggregate = combination.get("allBrandsConclusion")
    if isinstance(aggregate, dict) and _text(aggregate.get("dataSummary")):
        panels.append({
            "id": "all-brands",
            "brand": "所有指定品牌",
            "insights": [{"text": _text(aggregate.get("dataSummary")), "dimension": "data"}],
        })
        _attach_chapter01_period_panels(panels[-1], aggregate, "all", fact_pack)
    else:
        facts = fact_pack.get("industryTop1000Facts")
        # Older persisted reports carried the same aggregate metrics under
        # allBrandsRankingFacts; keep this read-only fallback for migration.
        if (
            not isinstance(facts, dict)
            or not facts.get("metrics")
        ) and isinstance(fact_pack.get("allBrandsRankingFacts"), dict):
            facts = fact_pack["allBrandsRankingFacts"]
        if not isinstance(facts, dict):
            facts = None
        if facts is not None:
            panels.append({
                "id": "all-brands",
                "brand": "所有指定品牌",
                "insights": [{"text": _ranking_scope_fallback_summary(facts), "dimension": "data"}],
            })
            _attach_chapter01_period_panels(panels[-1], {}, "all", fact_pack)
    for item in brands:
        if not isinstance(item, dict) or not _text(item.get("brand")):
            raise YuntuPresentationError("chapter01 brand conclusion is invalid")
        brand = _text(item.get("brand"))
        panels.append({
            "id": _scope_id(brand),
            "brand": brand,
            "insights": ([
                {"text": _text(item.get("dataSummary")), "dimension": "data"}
            ] if _text(item.get("dataSummary")) else []),
        })
        _attach_chapter01_period_panels(panels[-1], item, brand, fact_pack)
        ai_analysis = _chapter01_ai_analysis(item)
        if ai_analysis is not None:
            panels[-1]["aiAnalysis"] = ai_analysis
    if panels:
        aggregate_panel = panels[0]
        aggregate_conclusion = aggregate if isinstance(aggregate, dict) else {}
        ai_analysis = _chapter01_ai_analysis(aggregate_conclusion)
        if ai_analysis is not None:
            aggregate_panel["aiAnalysis"] = ai_analysis
    if not panels:
        raise YuntuPresentationError("chapter01 brand conclusions are required")
    tabs = [{"id": panel["id"], "label": panel["brand"], "panelId": panel["id"]} for panel in panels]
    return {
        "brandTabs": tabs,
        "brandPanels": panels,
    }


def _chapter01_ai_analysis(conclusion):
    """Project first-chapter AI fields without merging the two user-facing sections."""
    if not isinstance(conclusion, dict):
        return None
    data_summary = _text(conclusion.get("dataSummary"))
    hot_insight = _copy_chapter01_insight(conclusion.get("hotMaterialInsight"))
    if hot_insight is not None and not conclusion.get("comparisonSummary"):
        if not data_summary and not hot_insight.get("summary"):
            return None
        return {
            "dataSummary": data_summary,
            "hotMaterialInsight": hot_insight,
        }

    # Historical schema-v7 reports used comparisonSummary and hotMaterialInsight
    # as additions to one paragraph. Keep that read-only compatibility path.
    summary_parts = [data_summary, _text(conclusion.get("comparisonSummary"))]
    if hot_insight is not None:
        summary_parts.append(hot_insight.get("summary"))
    summary = " ".join(part for part in summary_parts if part)
    if not summary:
        return None
    return {"summary": summary}


def _attach_chapter01_period_panels(panel, conclusion, scope_key, fact_pack):
    comparison_facts = fact_pack.get("comparisonFacts") if isinstance(fact_pack, dict) else None
    hot_facts = fact_pack.get("hotMaterialFacts") if isinstance(fact_pack, dict) else None
    if not isinstance(comparison_facts, dict) or not isinstance(hot_facts, dict):
        return
    scoped_comparison = comparison_facts.get("scopes", {}).get(scope_key)
    if not isinstance(scoped_comparison, dict):
        legacy_brand_comparison = comparison_facts.get("brand")
        if scope_key != "all" and isinstance(legacy_brand_comparison, dict):
            scoped_comparison = legacy_brand_comparison
    if not isinstance(scoped_comparison, dict):
        scoped_comparison = {
            key: value
            for key, value in comparison_facts.items()
            if key in {"previousPeriod", "industryBenchmark"}
        }
    panel["comparison"] = {
        "summary": _text(conclusion.get("comparisonSummary")),
        "facts": deepcopy(scoped_comparison),
    }
    hot_key = "all" if scope_key == "all" else panel["brand"]
    hot = hot_facts.get(hot_key)
    if not isinstance(hot, dict):
        raise YuntuPresentationError(f"chapter01 hot material facts are missing for {panel['brand']}")
    panel["hotMaterialPanel"] = {
        "thresholdExposureMin": hot.get("thresholdExposureMin"),
        "qualifyingCount": hot.get("qualifyingCount", 0),
        "materials": deepcopy(hot.get("materials", [])),
        "sortRule": hot.get("sortRule", "exposure.min descending"),
        "available": bool(hot.get("available")),
        "missingReason": _text(hot.get("missing_reason")),
        "insight": _copy_chapter01_insight(conclusion.get("hotMaterialInsight")),
    }


def _copy_chapter01_insight(value):
    if not isinstance(value, dict):
        return None
    return {
        "title": _text(value.get("title")),
        "summary": _text(value.get("summary")),
        "evidence": deepcopy(value.get("evidence", {})),
    }


def _ranking_scope_fallback_summary(facts):
    metrics = facts.get("metrics", {}) if isinstance(facts, dict) else {}
    sample = facts.get("sample_count", 0)
    show = metrics.get("show_cnt", {}).get("total", 0)
    ctr = metrics.get("ctr", {}).get("median")
    cvr = metrics.get("cvr", {}).get("median")
    play = metrics.get("play_3s_rate", {}).get("median")
    def fmt(value, suffix=""):
        return "数据不足" if value is None else f"{value:.2%}" if suffix == "%" else f"{value:,.0f}"
    return f"全品牌范围覆盖 {sample} 条素材，累计曝光 {fmt(show)}；CTR 中位数 {fmt(ctr, '%')}、CVR 中位数 {fmt(cvr, '%')}、3 秒播放率中位数 {fmt(play, '%')}。该汇总用于观察多品牌素材池的整体表现，后续可结合各品牌 Tab 对比指标组合与标题主题。"


def _available_frames(fact_pack):
    frames = {}
    for fact in fact_pack.get("materialFacts", []) if isinstance(fact_pack, dict) else []:
        if not isinstance(fact, dict):
            continue
        for frame in fact.get("highlightFrames", []):
            if not isinstance(frame, dict) or frame.get("available") is not True:
                continue
            ref = _text(frame.get("frame_ref"))
            if not ref:
                continue
            if ref in frames:
                raise YuntuPresentationError("highlight frame reference is invalid")
            copied = deepcopy(frame)
            copied["relative_path"] = _safe_relative_frame_path(copied.get("relative_path"))
            copied["material_id"] = _text(fact.get("material_id"))
            copied["rank"] = fact.get("rank", "-")
            copied["title"] = _text(fact.get("title"))
            frames[ref] = copied
    return frames


def _frame_card(frame):
    frame_type = _text(frame.get("frame_type"))
    rank = frame.get("peak_rank")
    caption = "封面帧" if frame_type == "cover" else f"点击 Top{rank} 峰值帧"
    return {
        "frameRef": frame["frame_ref"],
        "available": True,
        "relativePath": frame["relative_path"],
        "second": frame.get("second"),
        "frameType": frame_type,
        "peakRank": rank,
        "clickValue": frame.get("click_value"),
        "materialId": _text(frame.get("material_id")),
        "rank": frame.get("rank", "-"),
        "title": _text(frame.get("title")),
        "caption": caption,
    }


def _chapter05_frame_card(frame):
    """Project only frame facts that cannot be inherited from its material panel."""
    return {
        "frameRef": frame["frame_ref"],
        "available": True,
        "relativePath": frame["relative_path"],
        "second": frame.get("second"),
        "frameType": _text(frame.get("frame_type")),
        "peakRank": frame.get("peak_rank"),
        "clickValue": frame.get("click_value"),
    }


def _project_scoped_highlight_brands(scoped_brands, available, brand_order):
    """Project model-authored brand-scoped highlight groups without copying conclusions."""
    if not isinstance(scoped_brands, list) or not scoped_brands:
        raise YuntuPresentationError("highlight dashboard brands are required")
    projected = []
    seen_brands = set()
    all_refs = set(available)
    for scope in scoped_brands:
        if not isinstance(scope, dict):
            raise YuntuPresentationError("highlight brand scope is invalid")
        brand = _text(scope.get("brand"))
        groups = scope.get("groups")
        if not brand or brand in seen_brands or not isinstance(groups, list) or not groups:
            raise YuntuPresentationError("highlight brand scope is invalid")
        seen_brands.add(brand)
        merged = {}
        scope_refs = []
        for group in groups:
            if not isinstance(group, dict) or group.get("category") not in HIGHLIGHT_CATEGORIES:
                raise YuntuPresentationError("highlight category is invalid")
            category = {"scene": "other", "text_overlay": "other"}.get(group["category"], group["category"])
            refs = group.get("frame_refs", [])
            if not isinstance(refs, list) or not refs or any(_text(ref) not in available for ref in refs):
                raise YuntuPresentationError("highlight frame reference is invalid")
            scope_refs.extend(refs)
            target = merged.setdefault(category, {"id": category, "label": category, "commonConclusion": [], "derivativeDirections": [], "frames": []})
            target["commonConclusion"].extend(deepcopy(group.get("common_patterns", [])))
            target["derivativeDirections"].extend(deepcopy(group.get("derivative_directions", [])))
            for ref in refs:
                frame_card = _frame_card(available[ref])
                frame_card["brand"] = "、".join(match_brands_from_title(frame_card.get("title"), brand_order)) or "其他品牌"
                target["frames"].append(frame_card)
        if len(scope_refs) != len(set(scope_refs)):
            raise YuntuPresentationError("highlight frame coverage is invalid")
        categories = [merged[key] for key in ("portrait", "product", "other") if key in merged]
        projected.append({
            "id": "all-brands" if brand == "全品牌" else _scope_id(brand),
            "brand": brand,
            "categories": categories,
            "_refs": set(scope_refs),
        })
    if projected[0]["brand"] != "全品牌" or projected[0]["_refs"] != all_refs:
        raise YuntuPresentationError("all-brand highlight scope must cover every available frame")
    for scope in projected[1:]:
        expected = {
            ref for ref, frame in available.items()
            if scope["brand"] in match_brands_from_title(frame.get("title"), brand_order)
        }
        if scope["_refs"] != expected:
            raise YuntuPresentationError("brand highlight scope frame coverage is invalid")
    for scope in projected:
        scope.pop("_refs", None)
    return {"scopeId": "all", "brands": projected, "availability": {"status": "complete", "reasons": []}}


def _is_designated_highlight_mode_brand(brand, brand_order):
    """Enable modes for the current run's selected brands, not a global allowlist."""
    normalized = _text(brand).replace(" ", "").lower()
    if normalized in {"所有指定品牌", "全品牌"}:
        return True
    return any(
        normalized == _text(selected).replace(" ", "").lower()
        for selected in brand_order
    )


def _classification_mode_categories(classification, available, brand, brand_order):
    status = classification.get("status") if isinstance(classification, dict) else None
    reason = _text(classification.get("missing_reason")) if isinstance(classification, dict) else ""
    mode = {
        "id": "batch",
        "label": "本批次视觉主题",
        "available": status == "complete",
        "reason": reason,
        "rule": _text(classification.get("rule")) if isinstance(classification, dict) else "",
        "categories": [],
    }
    if status != "complete":
        return mode
    scope_refs = set(available)
    if brand not in {"全品牌", "所有指定品牌"}:
        scope_refs = {
            ref for ref, frame in available.items()
            if brand in match_brands_from_title(frame.get("title"), brand_order)
        }
    merged = {}
    covered_refs = []
    for group in classification.get("groups", []):
        if not isinstance(group, dict):
            continue
        refs = [ref for ref in group.get("frame_refs", []) if ref in scope_refs]
        if not refs:
            continue
        if len(refs) != len(set(refs)) or any(ref in covered_refs for ref in refs):
            raise YuntuPresentationError("batch highlight frame coverage is invalid")
        covered_refs.extend(refs)
        category_id = _text(group.get("category"))
        if not category_id:
            continue
        target = merged.setdefault(category_id, {
            "id": category_id,
            "label": _text(group.get("label")) or category_id,
            "rule": _text(group.get("rule")) or mode["rule"],
            "frames": [],
        })
        for ref in refs:
            frame_card = _frame_card(available[ref])
            frame_card["brand"] = "、".join(match_brands_from_title(frame_card.get("title"), brand_order)) or "其他品牌"
            target["frames"].append(frame_card)
    if set(covered_refs) != scope_refs or len(covered_refs) != len(scope_refs):
        raise YuntuPresentationError("batch highlight frame coverage is invalid")
    mode["categories"] = list(merged.values())
    buckets = [
        {
            "category": category["id"],
            "label": category["label"],
            "count": len(category["frames"]),
            "share": len(category["frames"]) / len(scope_refs),
        }
        for category in mode["categories"]
    ]
    mode["distribution"] = {"totalFrames": len(scope_refs), "buckets": buckets}
    return mode


def _attach_highlight_classification_modes(chapter, dashboard, available, brand_order):
    if not isinstance(dashboard, dict) or not all(
        field in dashboard for field in ("standardClassification", "batchClassification")
    ):
        return chapter
    for brand in chapter.get("brands", []):
        if not isinstance(brand, dict) or not _is_designated_highlight_mode_brand(brand.get("brand"), brand_order):
            continue
        standard_categories = deepcopy(brand.get("categories", []))
        for category in standard_categories:
            category.setdefault("rule", "人物 / 产品 / 其他的固定视觉主体分类")
        batch_mode = _classification_mode_categories(
            dashboard["batchClassification"], available, brand.get("brand"), brand_order
        )
        brand["classificationModes"] = [
            {
                "id": "standard",
                "label": "标准分类",
                "available": True,
                "reason": "",
                "rule": "人物 / 产品 / 其他的固定视觉主体分类",
                "categories": standard_categories,
            },
            batch_mode,
        ]
    if any("classificationModes" in brand for brand in chapter.get("brands", [])):
        chapter["defaultClassificationMode"] = "standard"
    return chapter


def _project_chapter04(analysis, fact_pack):
    available = _available_frames(fact_pack)
    dashboard = analysis.get("highlightDashboard", {}) if isinstance(analysis, dict) else {}
    groups = dashboard.get("groups", []) if isinstance(dashboard, dict) else []
    if not available:
        return {"scopeId": "all", "brands": [], "availability": {"status": "unavailable", "reasons": ["暂无可用高光帧"]}}
    if not isinstance(groups, list) or not groups:
        scoped_brands = dashboard.get("brands") if isinstance(dashboard, dict) else None
        if scoped_brands is not None:
            brand_order = [str(brand).strip() for brand in (fact_pack.get("filters", {}) or {}).get("brands", []) if str(brand).strip()]
            chapter = _project_scoped_highlight_brands(scoped_brands, available, brand_order)
            return _attach_highlight_classification_modes(chapter, dashboard, available, brand_order)
        raise YuntuPresentationError("highlight dashboard is required")
    seen, categories, previous_index = [], [], -1
    merged = {}
    brand_order = [str(brand).strip() for brand in (fact_pack.get("filters", {}) or {}).get("brands", []) if str(brand).strip()]
    brand_merged = {}
    category_aliases = {"scene": "other", "text_overlay": "other"}
    for group in groups:
        if not isinstance(group, dict) or group.get("category") not in HIGHLIGHT_CATEGORIES:
            raise YuntuPresentationError("highlight category is invalid")
        category = category_aliases.get(group["category"], group["category"])
        refs = group.get("frame_refs", [])
        if not isinstance(refs, list) or any(_text(ref) not in available for ref in refs):
            raise YuntuPresentationError("highlight frame reference is invalid")
        seen.extend(refs)
        target = merged.setdefault(category, {"id": category, "label": category, "commonConclusion": [], "derivativeDirections": [], "frames": []})
        target["commonConclusion"].extend(deepcopy(group.get("common_patterns", [])))
        target["derivativeDirections"].extend(deepcopy(group.get("derivative_directions", [])))
        for ref in refs:
            frame_card = _frame_card(available[ref])
            matched_brands = match_brands_from_title(frame_card.get("title"), brand_order)
            frame_card["brand"] = "、".join(matched_brands) or "其他品牌"
            target["frames"].append(frame_card)
            for matched_brand in matched_brands or ["其他品牌"]:
                brand_target = brand_merged.setdefault(matched_brand, {})
                brand_category = brand_target.setdefault(category, {"id": category, "label": category, "commonConclusion": [], "derivativeDirections": [], "frames": []})
                brand_category["frames"].append(frame_card)
        for brand in list(brand_merged):
            if category not in brand_merged[brand]:
                continue
            brand_category = brand_merged[brand][category]
            if not brand_category["commonConclusion"]:
                brand_category["commonConclusion"].extend(deepcopy(group.get("common_patterns", [])))
            brand_refs = {frame["frameRef"] for frame in brand_category["frames"]}
            for direction in group.get("derivative_directions", []):
                if not isinstance(direction, dict):
                    continue
                direction_refs = [ref for ref in direction.get("frame_refs", []) if ref in brand_refs]
                if direction_refs:
                    copied = deepcopy(direction)
                    copied["frame_refs"] = direction_refs
                    brand_category["derivativeDirections"].append(copied)
    for category in ("portrait", "product", "other"):
        if category in merged:
            categories.append(merged[category])
    if set(seen) != set(available) or len(seen) != len(set(seen)):
        raise YuntuPresentationError("highlight frame coverage is invalid")
    ordered_brands = []
    if categories:
        ordered_brands.append({"id": "all-brands", "brand": "全品牌", "categories": deepcopy(categories)})
    for brand in brand_order + [brand for brand in brand_merged if brand not in brand_order]:
        if brand not in brand_merged:
            continue
        brand_categories = [brand_merged[brand][category] for category in ("portrait", "product", "other") if category in brand_merged[brand]]
        ordered_brands.append({"id": _scope_id(brand), "brand": brand, "categories": brand_categories})
    # New projections use the all-brand tab as the single chapter-level source.
    # The renderer still accepts historical payloads that contain top-level
    # ``categories`` as a read-only compatibility fallback.
    chapter = {"scopeId": "all", "brands": ordered_brands, "availability": {"status": "complete", "reasons": []}}
    return _attach_highlight_classification_modes(chapter, dashboard, available, brand_order)


def _project_second_level(metrics):
    indexed = {item.get("trend_name"): item for item in metrics if isinstance(item, dict)}
    projected = []
    for name in SECOND_LEVEL_METRIC_ORDER:
        source = indexed.get(name, {"trend_name": name, "available": False, "missing_reason": "趋势未返回", "points": []})
        available = source.get("available") is True
        reason = _text(source.get("missing_reason"))
        if not available and not reason:
            raise YuntuPresentationError("unavailable trend missing reason")
        points = deepcopy(source.get("points", []))
        if not isinstance(points, list) or any(not isinstance(point, dict) or not isinstance(point.get("second"), int) for point in points):
            raise YuntuPresentationError("second level points are invalid")
        projected.append({
            "id": name,
            "available": available,
            "reason": reason,
            "points": points,
            "highPoints": deepcopy(source.get("high_points", [])),
            "lossPoints": deepcopy(source.get("loss_points", [])),
        })
    return {"metricOrder": list(SECOND_LEVEL_METRIC_ORDER), "metrics": projected}


def _project_chapter05(analysis, fact_pack, *, report_video_assets=None):
    facts = {
        _text(fact.get("material_id")): fact
        for fact in fact_pack.get("materialFacts", []) if isinstance(fact, dict) and _text(fact.get("material_id"))
    }
    selected = fact_pack.get("selectedMaterials", []) if isinstance(fact_pack, dict) else []
    selected_ids = [_text(item.get("material_id")) for item in selected if isinstance(item, dict) and _text(item.get("material_id"))]
    if not selected_ids:
        selected_ids = list(facts)
    dives = analysis.get("materialDeepDives", []) if isinstance(analysis, dict) else []
    dives_by_id = {_text(dive.get("material_id")): dive for dive in dives if isinstance(dive, dict) and _text(dive.get("material_id"))}
    if not selected_ids or not dives_by_id:
        return {"materialTabs": [], "panels": []}, {
            "chapter05-material-tabs": {"id": "chapter05-material-tabs", "type": "tab-list", "items": [], "defaultItemId": "", "keyboard": ["ArrowLeft", "ArrowRight", "Home", "End"]},
            "chapter05-second-level": {"id": "chapter05-second-level", "type": "timeline-metric-switch", "metricOrder": list(SECOND_LEVEL_METRIC_ORDER)},
        }
    if selected_ids and set(dives_by_id) != set(selected_ids):
        raise YuntuPresentationError("material deep dives must cover selected materials")
    report_video_assets = report_video_assets if isinstance(report_video_assets, dict) else {}
    tabs, panels = [], []
    for material_id in selected_ids:
        fact = facts.get(material_id)
        if not isinstance(fact, dict):
            raise YuntuPresentationError("selected material fact is missing")
        dive = dives_by_id[material_id]
        frames = []
        frame_failures = []
        for frame in fact.get("highlightFrames", []):
            if isinstance(frame, dict) and frame.get("available") is True:
                copied = deepcopy(frame)
                copied["relative_path"] = _safe_relative_frame_path(copied.get("relative_path"))
                copied["material_id"] = material_id
                frames.append(_chapter05_frame_card(copied))
            elif isinstance(frame, dict):
                reason = _text(frame.get("failure_reason") or frame.get("missing_reason") or frame.get("reason"))
                if reason and reason not in frame_failures:
                    frame_failures.append(reason)
        observations = dive.get("frame_observations", [])
        observations_by_ref = {item.get("frame_ref"): deepcopy(item) for item in observations if isinstance(item, dict)}
        frame_refs = {frame["frameRef"] for frame in frames}
        if set(observations_by_ref) != frame_refs or len(observations_by_ref) != len(observations):
            raise YuntuPresentationError("material deep dive frame coverage is invalid")
        second_level = _project_second_level((fact.get("secondLevelBreakdown") or {}).get("metrics", []))
        status = "complete" if frames and all(item["available"] for item in second_level["metrics"]) else "partial"
        panel_id = f"material-{material_id}"
        tabs.append({"materialId": material_id, "label": f"#{fact.get('rank', '-')} {fact.get('title') or material_id}", "panelId": panel_id})
        panels.append({
            "id": panel_id,
            "materialId": material_id,
            "rank": fact.get("rank"),
            "title": _text(fact.get("title")),
            "videoTitleText": _content_formula_text(fact.get("content_formula"), "视频标题.text"),
            "videoFrameText": _content_formula_text(fact.get("content_formula"), "视频画面.text"),
            "exposure": deepcopy(fact.get("exposure", {})),
            "metrics": deepcopy(fact.get("metrics", {})),
            "scriptText": _text(fact.get("script_text")),
            "scriptSegments": deepcopy(fact.get("script_segments", [])),
            "scriptSegmentsAvailable": any(
                isinstance(segment, dict) for segment in fact.get("script_segments", [])
            ),
            "contentFormula": deepcopy(fact.get("content_formula")),
            "script": _chapter05_script_projection(fact, dive),
            "creativeBreakdown": deepcopy(fact.get("creative_breakdown")),
            "scriptMetrics": deepcopy(fact.get("detailMetrics", {})),
            "scriptDataAvailability": deepcopy(fact.get("detailDataAvailability", {})),
            "peopleTags": deepcopy(fact.get("people_tags", [])),
            "materialTags": deepcopy(fact.get("material_tags", [])),
            "listDataAvailability": deepcopy(fact.get("listDataAvailability", {})),
            "video": deepcopy(report_video_assets.get(material_id, {
                "available": False,
                "reason": "本批次未保存可交付的本地视频",
            })),
            "frames": frames,
            "frameFailures": frame_failures,
            "frameObservations": [observations_by_ref[frame["frameRef"]] for frame in frames],
            "secondLevel": second_level,
            "availability": {"status": status, "reasons": []},
        })
    return {"materialTabs": tabs, "panels": panels}, {
        "chapter05-material-tabs": {"id": "chapter05-material-tabs", "type": "tab-list", "items": tabs, "defaultItemId": tabs[0]["materialId"] if tabs else "", "keyboard": ["ArrowLeft", "ArrowRight", "Home", "End"]},
        "chapter05-second-level": {"id": "chapter05-second-level", "type": "timeline-metric-switch", "metricOrder": list(SECOND_LEVEL_METRIC_ORDER)},
    }


def validate_yuntu_presentation(payload):
    if not isinstance(payload, dict):
        raise YuntuPresentationError("presentation must be an object")
    if payload.get("presentationSchemaVersion") != PRESENTATION_SCHEMA_VERSION:
        raise YuntuPresentationError("unsupported presentation schema version")
    report = payload.get("report")
    if not isinstance(report, dict) or report.get("sections") != list(SECTION_IDS) or report.get("status") not in REPORT_STATUSES:
        raise YuntuPresentationError("presentation report is invalid")
    scopes = payload.get("scopes")
    if not isinstance(scopes, list) or len({item.get("id") for item in scopes if isinstance(item, dict)}) != len(scopes):
        raise YuntuPresentationError("presentation scopes are invalid")
    if not isinstance(payload.get("chapters"), dict) or not isinstance(payload.get("interactions"), dict):
        raise YuntuPresentationError("presentation sections are invalid")
    chapter04 = payload["chapters"].get("chapter04", {})
    for brand in chapter04.get("brands", []) if isinstance(chapter04, dict) else []:
        if not isinstance(brand, dict):
            continue
        for mode in brand.get("classificationModes", []):
            if not isinstance(mode, dict) or mode.get("id") != "batch" or mode.get("available") is not True:
                continue
            distribution = mode.get("distribution")
            if not isinstance(distribution, dict):
                raise YuntuPresentationError("batch distribution is required")
            total_frames = distribution.get("totalFrames")
            buckets = distribution.get("buckets")
            if isinstance(total_frames, bool) or not isinstance(total_frames, int) or total_frames < 0:
                raise YuntuPresentationError("batch distribution totalFrames is invalid")
            if not isinstance(buckets, list):
                raise YuntuPresentationError("batch distribution buckets are invalid")
            category_ids = [bucket.get("category") for bucket in buckets if isinstance(bucket, dict)]
            if len(category_ids) != len(buckets) or any(not _text(category) for category in category_ids):
                raise YuntuPresentationError("batch distribution category is invalid")
            if len(category_ids) != len(set(category_ids)):
                raise YuntuPresentationError("batch distribution category is duplicated")
            category_map = {
                category.get("id"): category
                for category in mode.get("categories", [])
                if isinstance(category, dict)
            }
            if set(category_ids) != set(category_map):
                raise YuntuPresentationError("batch distribution category coverage is invalid")
            count_total = 0
            share_total = 0.0
            for bucket in buckets:
                if not isinstance(bucket.get("count"), int) or isinstance(bucket.get("count"), bool) or bucket["count"] < 0:
                    raise YuntuPresentationError("batch distribution count is invalid")
                share = _finite_number(bucket.get("share"), "batch distribution share")
                if share < 0 or share > 1:
                    raise YuntuPresentationError("batch distribution share is invalid")
                expected_count = len(category_map[bucket["category"]].get("frames", []))
                if bucket["count"] != expected_count:
                    raise YuntuPresentationError("batch distribution count is inconsistent")
                count_total += bucket["count"]
                share_total += share
            if count_total != total_frames:
                raise YuntuPresentationError("batch distribution count total is inconsistent")
            if total_frames == 0:
                if buckets:
                    raise YuntuPresentationError("batch distribution buckets must be empty")
            elif not math.isclose(share_total, 1.0, rel_tol=0.0, abs_tol=1e-6):
                raise YuntuPresentationError("batch distribution share total is inconsistent")
    return payload


def build_yuntu_presentation(analysis, fact_pack, *, report_meta=None, report_video_assets=None):
    if not isinstance(analysis, dict) or not isinstance(fact_pack, dict):
        raise YuntuPresentationError("analysis and fact pack must be objects")
    chapter01 = _project_chapter01(analysis, fact_pack)
    scopes, chapter02, chapter02_interactions = _project_chapter02(analysis, fact_pack)
    chapter03 = _project_chapter03(analysis, fact_pack)
    chapter04 = _project_chapter04(analysis, fact_pack)
    chapter05, chapter05_interactions = _project_chapter05(
        analysis, fact_pack, report_video_assets=report_video_assets
    )
    payload = {
        "presentationSchemaVersion": PRESENTATION_SCHEMA_VERSION,
        "report": _report_metadata(fact_pack, report_meta),
        "scopes": scopes,
        "chapters": {"chapter01": chapter01, "chapter02": chapter02, "chapter03": chapter03, "chapter04": chapter04, "chapter05": chapter05},
        "interactions": {"chapter01-brand-tabs": {"id": "chapter01-brand-tabs", "type": "tab-list", "items": chapter01["brandTabs"], "defaultItemId": chapter01["brandTabs"][0]["id"] if chapter01["brandTabs"] else "", "keyboard": ["ArrowLeft", "ArrowRight", "Home", "End"]}, **chapter02_interactions, "chapter04-frame-lightbox": {"id": "chapter04-frame-lightbox", "type": "frame-lightbox"}, **chapter05_interactions},
        "extensions": {
            "yuntu": {
                "rankingMetric": "totalCost",
                "brandOrder": [scope["label"] for scope in scopes if scope["kind"] == "brand"],
                "marketingTagTaxonomyVersion": 2,
                "secondLevelMetricOrder": list(SECOND_LEVEL_METRIC_ORDER),
                "factSourceContract": {
                    "chapter02AiFacts": "AI 二次分析唯一来源",
                    "chapter02Facts": "真实汇总图表与范围 Tab 唯一来源",
                },
            }
        },
    }
    return validate_yuntu_presentation(payload)
