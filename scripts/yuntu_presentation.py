"""Build a stable presentation projection from validated Yuntu report inputs."""

from copy import deepcopy
import math
from pathlib import PurePosixPath


PRESENTATION_SCHEMA_VERSION = 1
REPORT_TITLE = "云图行业内容榜单分析"
SECTION_IDS = ("chapter02", "chapter04", "chapter05")
REPORT_STATUSES = {"complete", "partial", "unavailable"}
HIGHLIGHT_CATEGORIES = ("portrait", "product", "scene", "text_overlay", "other")
SECOND_LEVEL_METRIC_ORDER = ("点赞指数", "流失指数", "点击指数", "互动指数", "评论指数")


class YuntuPresentationError(ValueError):
    """Raised when the report inputs cannot form a safe presentation projection."""


def _text(value):
    return str(value or "").strip()


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
            "title": _text(item.get("dimension")),
            "text": summary,
            "evidence": deepcopy(item.get("evidence", [])),
            "materialIds": [str(value) for value in item.get("material_ids", []) if _text(value)],
            "materialId": _text(item.get("material_id")),
            "parts": {},
        })
    return result


def _chapter02_sources(fact_pack):
    chart_facts = fact_pack.get("chapter02Facts", {})
    ai_facts = fact_pack.get("chapter02AiFacts", {})
    if not chart_facts and not ai_facts:
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


def _chart_bucket(key, label, value, rank):
    return {
        "key": _text(key),
        "label": _text(label),
        "value": _finite_number(value, "chart value"),
        "rank": rank,
    }


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
            tag_buckets.append(_chart_bucket(tag["tag"], tag["tag"], tag.get("count", 0), tag_index))
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
        "title": "营销卖点一级类别",
        "dataSource": "chapter02Facts",
        "scopeId": scope_id,
        "value": {"field": "occurrenceCount", "unit": "count"},
        "buckets": primary_buckets,
        "interaction": {"type": "column-drilldown", "target": f"{scope_id}-marketing-level2"},
        "accessibility": {"label": "营销卖点一级类别柱状图"},
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
    top_n = (fact_pack.get("brandTopNFacts") or {}).get("requested_top_n")
    top_n = top_n if isinstance(top_n, int) and top_n > 0 else None
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
            "label": _text(scope_fact.get("label")) or scope_key,
            "kind": "industry" if scope_key == "all" else "brand",
            "rankScope": "top1000" if scope_key == "all" else "all-materials",
            "topN": None if scope_key == "all" else top_n,
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
                "audience": _copy_insights(scope_insights.get("audienceInsights", [])),
                "marketing": _copy_insights(scope_insights.get("marketingInsights", [])),
            },
            "charts": charts,
            "detailViews": detail_views,
            "topNControl": {
                "min": 1,
                "max": top_n or 1,
                "value": top_n or 1,
                "factSource": "chapter02Facts",
            },
        })
        tab_items.append({"id": scope_id, "label": scopes[-1]["label"], "panelId": panels[-1]["id"]})
    return scopes, {
        "scopeTabs": {"interactionId": "chapter02-scope-tabs", "items": tab_items},
        "panels": panels,
    }, {
        "chapter02-scope-tabs": {"id": "chapter02-scope-tabs", "type": "tab-list", "items": tab_items, "defaultItemId": tab_items[0]["id"], "keyboard": ["ArrowLeft", "ArrowRight", "Home", "End"]},
        **{target: {"id": target, "type": "column-drilldown", "targets": values} for target, values in interaction_targets.items()},
    }


def _available_frames(fact_pack):
    frames = {}
    for fact in fact_pack.get("materialFacts", []) if isinstance(fact_pack, dict) else []:
        if not isinstance(fact, dict):
            continue
        for frame in fact.get("highlightFrames", []):
            if not isinstance(frame, dict) or frame.get("available") is not True:
                continue
            ref = _text(frame.get("frame_ref"))
            if not ref or ref in frames:
                raise YuntuPresentationError("highlight frame reference is invalid")
            copied = deepcopy(frame)
            copied["relative_path"] = _safe_relative_frame_path(copied.get("relative_path"))
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
        "caption": caption,
    }


def _project_chapter04(analysis, fact_pack):
    available = _available_frames(fact_pack)
    dashboard = analysis.get("highlightDashboard", {}) if isinstance(analysis, dict) else {}
    groups = dashboard.get("groups", []) if isinstance(dashboard, dict) else []
    if not available:
        return {"scopeId": "all", "categories": [], "availability": {"status": "unavailable", "reasons": ["暂无可用高光帧"]}}
    if not isinstance(groups, list) or not groups:
        raise YuntuPresentationError("highlight dashboard is required")
    seen, categories, previous_index = [], [], -1
    for group in groups:
        if not isinstance(group, dict) or group.get("category") not in HIGHLIGHT_CATEGORIES:
            raise YuntuPresentationError("highlight category is invalid")
        category = group["category"]
        category_index = HIGHLIGHT_CATEGORIES.index(category)
        if category_index <= previous_index:
            raise YuntuPresentationError("highlight category order is invalid")
        previous_index = category_index
        refs = group.get("frame_refs", [])
        if not isinstance(refs, list) or any(_text(ref) not in available for ref in refs):
            raise YuntuPresentationError("highlight frame reference is invalid")
        seen.extend(refs)
        categories.append({
            "id": category,
            "label": category,
            "commonConclusion": list(deepcopy(group.get("common_patterns", []))),
            "derivativeDirections": deepcopy(group.get("derivative_directions", [])),
            "frames": [_frame_card(available[ref]) for ref in refs],
        })
    if set(seen) != set(available) or len(seen) != len(set(seen)):
        raise YuntuPresentationError("highlight frame coverage is invalid")
    return {"scopeId": "all", "categories": categories, "availability": {"status": "complete", "reasons": []}}


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


def _project_chapter05(analysis, fact_pack):
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
    if selected_ids and set(dives_by_id) != set(selected_ids):
        raise YuntuPresentationError("material deep dives must cover selected materials")
    tabs, panels = [], []
    for material_id in selected_ids:
        fact = facts.get(material_id)
        if not isinstance(fact, dict):
            raise YuntuPresentationError("selected material fact is missing")
        dive = dives_by_id[material_id]
        frames = []
        for frame in fact.get("highlightFrames", []):
            if isinstance(frame, dict) and frame.get("available") is True:
                copied = deepcopy(frame)
                copied["relative_path"] = _safe_relative_frame_path(copied.get("relative_path"))
                frames.append(_frame_card(copied))
        observations = dive.get("frame_observations", [])
        observations_by_ref = {item.get("frame_ref"): deepcopy(item) for item in observations if isinstance(item, dict)}
        frame_refs = {frame["frameRef"] for frame in frames}
        if set(observations_by_ref) != frame_refs or len(observations_by_ref) != len(observations):
            raise YuntuPresentationError("material deep dive frame coverage is invalid")
        second_level = _project_second_level((fact.get("secondLevelBreakdown") or {}).get("metrics", []))
        seconds_by_metric = {item["id"]: {point["second"] for point in item["points"]} for item in second_level["metrics"]}
        second_observations = dive.get("second_level_observations", [])
        for observation in second_observations:
            if not isinstance(observation, dict):
                raise YuntuPresentationError("second level observation is invalid")
            name = observation.get("trend_name")
            seconds = observation.get("evidence_seconds", [])
            if name not in seconds_by_metric or not isinstance(seconds, list) or not set(seconds).issubset(seconds_by_metric[name]):
                raise YuntuPresentationError("second level observation seconds are invalid")
        status = "complete" if frames and all(item["available"] for item in second_level["metrics"]) else "partial"
        panel_id = f"material-{material_id}"
        tabs.append({"materialId": material_id, "label": f"#{fact.get('rank', '-')} {fact.get('title') or material_id}", "panelId": panel_id})
        panels.append({
            "id": panel_id,
            "materialId": material_id,
            "rank": fact.get("rank"),
            "title": _text(fact.get("title")),
            "metrics": deepcopy(fact.get("metrics", {})),
            "frames": frames,
            "frameObservations": [observations_by_ref[frame["frameRef"]] for frame in frames],
            "secondLevel": second_level,
            "secondLevelObservations": deepcopy(second_observations),
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
    return payload


def build_yuntu_presentation(analysis, fact_pack, *, report_meta=None):
    if not isinstance(analysis, dict) or not isinstance(fact_pack, dict):
        raise YuntuPresentationError("analysis and fact pack must be objects")
    scopes, chapter02, chapter02_interactions = _project_chapter02(analysis, fact_pack)
    chapter04 = _project_chapter04(analysis, fact_pack)
    chapter05, chapter05_interactions = _project_chapter05(analysis, fact_pack)
    payload = {
        "presentationSchemaVersion": PRESENTATION_SCHEMA_VERSION,
        "report": _report_metadata(fact_pack, report_meta),
        "scopes": scopes,
        "chapters": {"chapter02": chapter02, "chapter04": chapter04, "chapter05": chapter05},
        "materials": deepcopy(chapter05["panels"]),
        "interactions": {**chapter02_interactions, "chapter04-frame-lightbox": {"id": "chapter04-frame-lightbox", "type": "frame-lightbox"}, **chapter05_interactions},
        "extensions": {
            "yuntu": {
                "rankingMetric": "totalCost",
                "brandOrder": [scope["label"] for scope in scopes if scope["kind"] == "brand"],
                "marketingTagTaxonomyVersion": 1,
                "secondLevelMetricOrder": list(SECOND_LEVEL_METRIC_ORDER),
                "factSourceContract": {
                    "chapter02AiFacts": "AI 二次分析唯一来源",
                    "chapter02Facts": "真实汇总图表与 Top N 控制唯一来源",
                },
            }
        },
    }
    return validate_yuntu_presentation(payload)
