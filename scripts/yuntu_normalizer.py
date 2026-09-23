"""Normalize Yuntu ranking and material-detail RPA records."""

import re


class YuntuNormalizeError(RuntimeError):
    """Raised when raw Yuntu records cannot be normalized."""


METRIC_FIELDS = (
    "ctr",
    "cvr",
    "pvr",
    "play_3s_rate",
    "play_5s_rate",
    "play_over_rate",
    "play_duration_avg",
    "show_cnt",
    "interact_rate",
    "component_click_rate",
)

SECOND_TREND_ALIASES = {
    "likeIndex": "点赞指数",
    "lossIndex": "流失指数",
    "clickIndex": "点击指数",
    "interactIndex": "互动指数",
    "commentIndex": "评论指数",
}


def _text(value):
    if value is None:
        return ""
    return str(value).strip()


def _number(value):
    if value in (None, ""):
        return None
    try:
        if isinstance(value, str) and value.isdigit():
            return int(value)
        return float(value)
    except (TypeError, ValueError):
        return None


_EXPOSURE_RANGE_RE = re.compile(
    r"(?P<left>\d+(?:\.\d+)?)\s*(?P<left_unit>万|w|W|千|k|K)?\s*"
    r"(?:-|–|—|~|至|到)\s*"
    r"(?P<right>\d+(?:\.\d+)?)\s*(?P<right_unit>万|w|W|千|k|K)?"
)
_EXPOSURE_SINGLE_RE = re.compile(r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>万|w|W|千|k|K)?")


def _exposure_number(value, unit=""):
    multiplier = {"万": 10000, "w": 10000, "W": 10000, "千": 1000, "k": 1000, "K": 1000}.get(unit, 1)
    return int(round(float(value) * multiplier))


def parse_exposure_interval(value):
    """Parse a Yuntu exposure display value without substituting another metric."""
    if isinstance(value, dict):
        raw = value.get("raw", value.get("text", ""))
        minimum = _number(value.get("min"))
        maximum = _number(value.get("max"))
        return {
            "min": int(minimum) if minimum is not None else None,
            "max": int(maximum) if maximum is not None else None,
            "raw": _text(raw),
        }
    raw = _text(value)
    if not raw:
        return {"min": None, "max": None, "raw": raw}
    compact = raw.replace(",", "").replace("，", "").strip()
    range_match = _EXPOSURE_RANGE_RE.search(compact)
    if range_match:
        left_unit = range_match.group("left_unit") or range_match.group("right_unit") or ""
        right_unit = range_match.group("right_unit") or range_match.group("left_unit") or ""
        return {
            "min": _exposure_number(range_match.group("left"), left_unit),
            "max": _exposure_number(range_match.group("right"), right_unit),
            "raw": raw,
        }
    single_match = _EXPOSURE_SINGLE_RE.fullmatch(compact)
    if single_match:
        parsed = _exposure_number(single_match.group("value"), single_match.group("unit") or "")
        return {"min": parsed, "max": parsed, "raw": raw}
    greater_match = re.search(r"(\d+(?:\.\d+)?)\s*(万|w|W|千|k|K)?\s*(?:以上|起)", compact)
    if greater_match:
        return {
            "min": _exposure_number(greater_match.group(1), greater_match.group(2) or ""),
            "max": None,
            "raw": raw,
        }
    return {"min": None, "max": None, "raw": raw}


def _raw_exposure_value(raw, object_index):
    for key in ("exposure", "exposure_range", "exposureRange"):
        if key in raw and raw.get(key) not in (None, ""):
            return raw.get(key)
    for key in ("exposure", "exposure_range", "exposureRange"):
        if key in object_index and object_index.get(key) not in (None, ""):
            return object_index.get(key)
    # The live Yuntu list response stores the display bucket in the top-level
    # show_cnt column (for example, ``200-300w``), while object_index.show_cnt
    # remains the exact numeric metric. Only accept an unmistakable display
    # bucket here; never reinterpret a numeric show count as an exposure range.
    show_cnt = raw.get("show_cnt")
    if isinstance(show_cnt, str) and (
        _EXPOSURE_RANGE_RE.search(show_cnt)
        or re.search(r"(?:万|w|W|千|k|K|以上|起)", show_cnt)
    ):
        return show_cnt
    return None


def _require_material_id(value):
    material_id = _text(value)
    if not material_id.isdigit():
        raise YuntuNormalizeError("material_id must contain digits only")
    return material_id


def _flatten_tag_entries(value):
    tags = []
    if not isinstance(value, list):
        return tags
    for entry in value:
        if not isinstance(entry, dict):
            continue
        names = entry.get("tag_name_list")
        if not isinstance(names, list):
            continue
        for name in names:
            text = _text(name)
            if text and text not in tags:
                tags.append(text)
    return tags


def _availability(value, *, has_values):
    if has_values:
        return {"available": True, "missing_reason": ""}
    if value in (None, "") or value == []:
        return {"available": False, "missing_reason": "source_empty"}
    if isinstance(value, str):
        return {"available": False, "missing_reason": "unparsed_source_value"}
    return {"available": False, "missing_reason": "no_usable_values"}


def _availability_with_parse_state(value, *, has_values, parse_failed):
    if parse_failed:
        return {"available": False, "missing_reason": "parse_failed"}
    return _availability(value, has_values=has_values)


def _detail_availability(trends, trend_series, high_points, loss_points, *, parse_failed=False):
    return {
        "trends": _availability_with_parse_state(
            trends, has_values=bool(trend_series), parse_failed=parse_failed
        ),
        "high_points": _availability(trends, has_values=bool(high_points)),
        "loss_points": _availability(trends, has_values=bool(loss_points)),
    }


def _selection_group(raw):
    brand_id = _text(raw.get("brandId") or raw.get("brand_id"))
    brand_name = _text(raw.get("brandName") or raw.get("brand_name"))
    touchpoint_code = _text(raw.get("touchpointCode") or raw.get("touchpoint_code"))
    touchpoint_name = _text(raw.get("touchpointName") or raw.get("touchpoint_name"))
    group_id = _text(raw.get("selectionGroupId") or raw.get("selection_group_id"))
    if not group_id and (brand_id or brand_name or touchpoint_code or touchpoint_name):
        group_id = f"{brand_id or brand_name}:{touchpoint_code or touchpoint_name}"
    return {
        "id": group_id or "default",
        "brand_id": brand_id,
        "brand_name": brand_name,
        "touchpoint_code": touchpoint_code,
        "touchpoint_name": touchpoint_name,
    }


def _script_segments(value):
    if not isinstance(value, list):
        return [], _availability(value, has_values=False)
    segments = []
    previous_end = -1
    for item in value:
        if not isinstance(item, dict):
            return [], {"available": False, "missing_reason": "invalid_timestamped_segments"}
        start_ms = _number(
            item["startMs"] if "startMs" in item else item.get("start_ms")
        )
        end_ms = _number(item["endMs"] if "endMs" in item else item.get("end_ms"))
        text = _text(item.get("text") or item.get("scriptText") or item.get("script_text"))
        if (
            start_ms is None
            or end_ms is None
            or start_ms < 0
            or end_ms <= start_ms
            or start_ms < previous_end
            or not text
        ):
            return [], {"available": False, "missing_reason": "invalid_timestamped_segments"}
        normalized = {"start_ms": int(start_ms), "end_ms": int(end_ms), "text": text}
        segments.append(normalized)
        previous_end = normalized["end_ms"]
    return segments, _availability(value, has_values=bool(segments))


def normalize_list_records(raw_records, *, source_path):
    if not isinstance(raw_records, list):
        raise YuntuNormalizeError("list records must be a list")
    normalized = []
    for rank, raw in enumerate(raw_records, start=1):
        if not isinstance(raw, dict):
            raise YuntuNormalizeError("list record must be an object")
        material_id = _require_material_id(raw.get("material_id") or raw.get("materialId"))
        object_index_value = raw.get("object_index")
        object_index = object_index_value
        if not isinstance(object_index_value, dict):
            object_index = {}
        raw_exposure_value = _raw_exposure_value(raw, object_index)
        exposure = parse_exposure_interval(raw_exposure_value)
        people_tag_entry = raw.get("people_tag_entry")
        material_tag_entry = raw.get("material_tag_entry")
        metrics = {}
        for field in METRIC_FIELDS:
            metric_value = _number(object_index.get(field, raw.get(field)))
            if metric_value is not None:
                metrics[field] = metric_value
        normalized.append(
            {
                "material_id": material_id,
                "item_id": _text(raw.get("item_id") or raw.get("itemId")),
                "object_type": _text(raw.get("object_type") or raw.get("objectType")),
                "material_uri": _text(raw.get("material_uri") or raw.get("materialUri")),
                "account_id": _text(raw.get("accountId") or raw.get("account_id")),
                "business_date": _text(raw.get("bizDate") or raw.get("business_date")),
                "list_context": {
                    "industry": _text(raw.get("page_industry") or raw.get("industry")),
                    "time_range": _text(raw.get("page_time_range") or raw.get("time_range")),
                    "custom_date_range": _text(raw.get("page_custom_date_range")),
                    "brand_scope": _text(raw.get("page_brand_scope")),
                    "brands": raw.get("page_brands") if isinstance(raw.get("page_brands"), list) else [],
                    "ranking_limit": _text(raw.get("page_ranking_limit")),
                    "actual_start_date": _text(
                        raw.get("page_actual_start_date")
                        or raw.get("actual_start_date")
                        or raw.get("start_date")
                    ),
                    "actual_end_date": _text(
                        raw.get("page_actual_end_date")
                        or raw.get("actual_end_date")
                        or raw.get("end_date")
                    ),
                },
                "selection_group": _selection_group(raw),
                "title": _text(raw.get("title")),
                "rank": rank,
                "video_duration": _number(
                    raw.get("video_duration") or raw.get("videoDuration")
                ),
                "publish_time": _text(
                    object_index.get("publish_time") or raw.get("publish_time")
                ),
                "metrics": metrics,
                "exposure": exposure,
                "people_tags": _flatten_tag_entries(people_tag_entry),
                "material_tags": _flatten_tag_entries(material_tag_entry),
                "data_availability": {
                    "metrics": _availability(
                        object_index_value if object_index_value is not None else raw,
                        has_values=bool(metrics),
                    ),
                    **(
                        {
                            "exposure": _availability(
                                raw_exposure_value,
                                has_values=exposure["min"] is not None,
                            )
                        }
                        if raw_exposure_value not in (None, "")
                        else {}
                    ),
                    "people_tags": _availability(
                        people_tag_entry,
                        has_values=bool(_flatten_tag_entries(people_tag_entry)),
                    ),
                    "material_tags": _availability(
                        material_tag_entry,
                        has_values=bool(_flatten_tag_entries(material_tag_entry)),
                    ),
                },
                "source_paths": {"list": source_path},
            }
        )
    return normalized


def _point_seconds(value):
    seconds = _number(value)
    if seconds is None:
        return None
    return int(seconds)


def _normalize_trend(raw_trend):
    trend_name = _text(raw_trend.get("trendName") or raw_trend.get("trend_name"))
    series = []
    for point in raw_trend.get("tendList", []):
        if not isinstance(point, dict):
            continue
        x_value = _number(point.get("x"))
        y_value = _number(point.get("y"))
        if x_value is not None and y_value is not None:
            series.append({"second": int(x_value), "value": y_value})
    return {
        "trend_name": trend_name,
        "trend_type": _number(raw_trend.get("trendType") or raw_trend.get("trend_type")),
        "series": series,
        "high_point": raw_trend.get("highPoint")
        if isinstance(raw_trend.get("highPoint"), dict)
        else None,
        "loss_point": raw_trend.get("lossPoint")
        if isinstance(raw_trend.get("lossPoint"), dict)
        else None,
    }


def _flat_detail_value(raw, name):
    """Read a scalar from either the flat coreData prefix or legacy aliases."""
    for key in (name, f"coreData.{name}", f"core_data.{name}"):
        if key in raw and raw[key] not in (None, ""):
            return raw[key]
    return None


def _flat_point(raw, prefix):
    value = raw.get(prefix)
    if isinstance(value, dict):
        return value
    point = {}
    for source_name, output_name in (
        ("start_point", "start_point"),
        ("end_point", "end_point"),
        ("startPoint", "start_point"),
        ("endPoint", "end_point"),
        ("loss_percent", "loss_percent"),
        ("lossPercent", "loss_percent"),
    ):
        if f"{prefix}.{source_name}" in raw:
            point[output_name] = raw[f"{prefix}.{source_name}"]
    return point or None


def _detail_material_identity(raw, core_data, fallback):
    """Reject conflicting root/core identities before choosing a detail row."""
    values = []
    for value in (
        raw.get("materialId"), raw.get("material_id"), raw.get("coreData.materialId"),
        raw.get("core_data.material_id"), core_data.get("objectId"),
        core_data.get("materialId"),
    ):
        if value not in (None, ""):
            values.append(_require_material_id(value))
    if len(set(values)) > 1:
        raise YuntuNormalizeError("detail root materialId conflicts with coreData objectId")
    return values[0] if values else _require_material_id(fallback)


def _canonical_period_date(value):
    text = _text(value).replace("-", "")
    return text if len(text) == 8 and text.isdigit() else ""


def _verify_detail_context(*, date_type, start_date, end_date, expected_context):
    if not expected_context:
        return {"valid": True, "mode": "not_requested", "issues": []}
    expected_type = _text(
        expected_context.get("date_type") or expected_context.get("date_range_type")
    )
    if not expected_type:
        return {"valid": True, "mode": "not_requested", "issues": []}
    issues = []
    if _text(date_type) != expected_type:
        issues.append("date_type")
    if expected_type == "CUSTOM":
        if _canonical_period_date(start_date) != _canonical_period_date(
            expected_context.get("custom_start_date")
        ):
            issues.append("custom_start_date")
        if _canonical_period_date(end_date) != _canonical_period_date(
            expected_context.get("custom_end_date")
        ):
            issues.append("custom_end_date")
        mode = "custom_dates"
    else:
        # Relative periods are connector-defined.  A directory name or local
        # clock must never be promoted into an asserted server date range.
        mode = "relative_type_only"
    if issues:
        raise YuntuNormalizeError(
            "detail response period does not match request: " + ", ".join(issues)
        )
    return {"valid": True, "mode": mode, "issues": []}


def _flat_detail_trends(raw):
    """Convert secondTrend.<name>.* CSV columns to the legacy trend shape."""
    prefix = "secondTrend."
    names = []
    for key in raw:
        if not key.startswith(prefix):
            continue
        remainder = key[len(prefix):]
        name = remainder.split(".", 1)[0]
        if name and name not in names:
            names.append(name)
    trends = []
    for name in names:
        base = f"{prefix}{name}."
        trend = {
            "trendName": raw.get(f"{base}trendName") or raw.get(f"{base}trend_name") or name,
            "trendType": raw.get(f"{base}trendType") or raw.get(f"{base}trend_type"),
            "tendList": raw.get(f"{base}tendList") or raw.get(f"{base}tend_list") or [],
            "highPoint": _flat_point(raw, f"{base}highPoint"),
            "lossPoint": _flat_point(raw, f"{base}lossPoint"),
        }
        if any(value not in (None, "", [], {}) for value in trend.values()):
            trends.append(trend)
    return trends


def _flat_content_formula(raw):
    """Preserve formula source domains from flat CSV columns."""
    prefix = "contentFormula."
    values = {}
    sources = {"title": {}, "visual": {}, "script": {}}
    source_names = {"视频标题": "title", "视频画面": "visual", "视频脚本": "script"}
    for key, value in raw.items():
        if not key.startswith(prefix):
            continue
        path = key[len(prefix):]
        if value in (None, "", []):
            continue
        if path.endswith(".labels") or path == "labels":
            values["labels"] = value
        else:
            source_name, separator, source_path = path.partition(".")
            target = source_names.get(source_name)
            if target and separator:
                sources[target][source_path] = value
            else:
                values[path] = value
    normalized_sources = {
        name: source for name, source in sources.items() if source
    }
    if normalized_sources:
        values["sources"] = normalized_sources
    return values or None


def _nested_detail_trends(raw):
    second_trend = raw.get("secondTrend")
    if not isinstance(second_trend, dict):
        return []
    trends = []
    for name, value in second_trend.items():
        if not isinstance(value, dict):
            continue
        trends.append(
            {
                "trendName": value.get("trendName") or SECOND_TREND_ALIASES.get(name) or name,
                "trendType": value.get("trendType") or value.get("trend_type"),
                "tendList": value.get("tendList") or value.get("tend_list") or [],
                "highPoint": value.get("highPoint"),
                "lossPoint": value.get("lossPoint"),
            }
        )
    return trends


def _nested_content_formula(value):
    if not isinstance(value, dict):
        return value
    formula = value.get("本视频内容公式") or value.get("videoContentFormula")
    labels = formula.get("labels") if isinstance(formula, dict) else value.get("labels")
    result = {"labels": labels} if labels is not None else {}
    sources = {}
    for raw_name, source_name in (
        ("视频标题", "title"), ("videoTitle", "title"),
        ("视频画面", "visual"), ("videoVisual", "visual"),
        ("视频脚本", "script"), ("videoScript", "script"),
    ):
        source = value.get(raw_name)
        if not isinstance(source, dict):
            continue
        normalized = {}
        if source.get("text") not in (None, ""):
            normalized["text"] = source.get("text")
        if isinstance(source.get("detail"), dict):
            normalized["detail"] = source["detail"]
        if normalized:
            sources[source_name] = normalized
    if sources:
        result["sources"] = sources
    return result or None


def _nested_core_metrics(core_data):
    if not isinstance(core_data, dict):
        return {}
    excluded = {
        "objectId", "materialId", "title", "videoDuration", "videoDurationType",
        "dateType", "customStartDate", "customEndDate", "videoUrl",
    }
    return {
        name: parsed
        for name, value in core_data.items()
        if name not in excluded and (parsed := _number(value)) is not None
    }


def _normalized_creative_breakdown(value):
    if not isinstance(value, dict):
        return value
    tags = []
    for raw_value in value.values():
        for item in raw_value if isinstance(raw_value, list) else [raw_value]:
            for tag in re.split(r"[、，,；;\\n]+", _text(item)):
                if tag and tag not in tags:
                    tags.append(tag)
    return {"raw": value, "tags": tags}


def _flat_creative_breakdown(raw):
    """Preserve raw creative columns and provide deterministic analyzable tags."""
    prefix = "creativeBreakdown."
    raw_values = {
        key[len(prefix):]: value
        for key, value in raw.items()
        if key.startswith(prefix) and value not in (None, "")
    }
    if not raw_values:
        return None
    tags = []
    for value in raw_values.values():
        values = value if isinstance(value, list) else [value]
        for item in values:
            for tag in re.split(r"[、，,；;\\n]+", _text(item)):
                tag = tag.strip()
                if tag and tag not in tags:
                    tags.append(tag)
    return {"raw": raw_values, "tags": tags}


def _flat_core_metrics(raw):
    metrics = {}
    for key, value in raw.items():
        if not key.startswith("coreData."):
            continue
        name = key[len("coreData."):]
        if name in {"materialId", "dateType", "customStartDate", "customEndDate", "videoUrl"}:
            continue
        parsed = _number(value)
        if parsed is not None:
            metrics[name] = parsed
    return metrics


def normalize_detail_records(
    raw_records,
    *,
    material_id,
    source_path,
    source_hash=None,
    expected_selection_group=None,
    expected_context=None,
):
    if isinstance(raw_records, list) and raw_records:
        raw = raw_records[0]
    elif isinstance(raw_records, dict):
        raw = raw_records
    else:
        raise YuntuNormalizeError("detail records must contain one detail object")
    if not isinstance(raw, dict):
        raise YuntuNormalizeError("detail record must be an object")

    parse_failed_fields = raw.get("__parse_failed_fields__", [])
    if not isinstance(parse_failed_fields, list):
        parse_failed_fields = []

    expected_material_id = _require_material_id(material_id)
    core_data = raw.get("coreData") if isinstance(raw.get("coreData"), dict) else {}
    actual_material_id = _detail_material_identity(raw, core_data, material_id)
    if actual_material_id != expected_material_id:
        raise YuntuNormalizeError("detail material_id does not match selected material")

    new_detail_schema = any(
        isinstance(raw.get(key), dict)
        for key in ("coreData", "audiencePortrait", "secondTrend")
    )
    selection_group = _selection_group(raw)
    if expected_selection_group is not None:
        expected_id = _text(expected_selection_group.get("id"))
        if expected_id and expected_id != "default":
            if selection_group["id"] == "default":
                if not new_detail_schema:
                    raise YuntuNormalizeError("detail response is missing selection group echo")
                # The new details connector only receives material/date fields.
                # Keep the grouping chosen from the verified list response rather
                # than requiring an echo that is not part of its contract.
                selection_group = {
                    key: _text(expected_selection_group.get(key))
                    for key in selection_group
                }
            if selection_group["id"] != expected_id:
                raise YuntuNormalizeError("detail selection group does not match selected material")
            selection_group = {
                key: _text(expected_selection_group.get(key)) or selection_group[key]
                for key in selection_group
            }

    nested_schema = new_detail_schema
    trend_series = []
    high_points = []
    loss_points = []
    flat_schema = any(
        key.startswith(("coreData.", "core_data.", "secondTrend.", "contentFormula.", "creativeBreakdown."))
        for key in raw
    )
    flat_trends = _flat_detail_trends(raw) if flat_schema else []
    nested_trends = _nested_detail_trends(raw) if nested_schema else []
    trends_value = raw.get("trends") if "trends" in raw else (
        flat_trends if flat_schema else (nested_trends if nested_schema else None)
    )
    trends = trends_value
    if not isinstance(trends_value, list):
        trends = []
    for raw_trend in trends:
        if not isinstance(raw_trend, dict):
            continue
        trend = _normalize_trend(raw_trend)
        trend_series.append(trend)
        high = trend["high_point"]
        if high:
            high_points.append(
                {
                    "trend_name": trend["trend_name"],
                    "start_sec": _point_seconds(high.get("start_point")),
                    "end_sec": _point_seconds(high.get("end_point")),
                }
            )
        loss = trend["loss_point"]
        if loss:
            loss_points.append(
                {
                    "trend_name": trend["trend_name"],
                    "start_sec": _point_seconds(loss.get("start_point")),
                    "end_sec": _point_seconds(loss.get("end_point")),
                    "loss_percent": _number(loss.get("loss_percent")),
                }
            )
    flat_script_text = raw.get("contentFormula.视频脚本.text")
    nested_formula = _nested_content_formula(raw.get("contentFormula")) if nested_schema else None
    nested_script = (
        nested_formula.get("sources", {}).get("script", {}).get("text")
        if isinstance(nested_formula, dict)
        else None
    )
    script_text_value = raw.get("scriptText") or raw.get("script_text") or flat_script_text or nested_script
    content_formula = raw.get("contentFormula") or raw.get("content_formula")
    if nested_schema:
        content_formula = nested_formula
    elif content_formula is None and flat_schema:
        content_formula = _flat_content_formula(raw)
    if not isinstance(content_formula, (str, dict, list)):
        content_formula = None
    creative_breakdown = raw.get("creativeBreakdown") or raw.get("creative_breakdown")
    if nested_schema:
        creative_breakdown = _normalized_creative_breakdown(creative_breakdown)
    elif creative_breakdown is None and flat_schema:
        creative_breakdown = _flat_creative_breakdown(raw)
    script_segments, script_segments_availability = _script_segments(
        raw.get("scriptSegments") or raw.get("script_segments")
    )
    date_type = _flat_detail_value(raw, "dateType") or raw.get("dateType") or raw.get("dateRangeType") or raw.get("date_range_type") or core_data.get("dateType")
    start_date = _flat_detail_value(raw, "customStartDate") or raw.get("customStartDate") or raw.get("startDate") or raw.get("start_date") or core_data.get("customStartDate")
    end_date = _flat_detail_value(raw, "customEndDate") or raw.get("customEndDate") or raw.get("endDate") or raw.get("end_date") or core_data.get("customEndDate")
    video_duration = _flat_detail_value(raw, "videoDuration") or raw.get("videoDuration") or raw.get("video_duration") or core_data.get("videoDuration")
    core_metrics = _flat_core_metrics(raw) if flat_schema else _nested_core_metrics(core_data)
    title = _flat_detail_value(raw, "title") or raw.get("title") or core_data.get("title")
    video_url = _flat_detail_value(raw, "videoUrl") or raw.get("videoUrl") or raw.get("video_url") or core_data.get("videoUrl")
    audience_portrait = raw.get("audiencePortrait") if isinstance(raw.get("audiencePortrait"), dict) else {}
    source_hashes = {"detail": _text(source_hash)} if source_hash else {}
    period_verification = _verify_detail_context(
        date_type=date_type,
        start_date=start_date,
        end_date=end_date,
        expected_context=expected_context,
    )
    return {
        "material_id": expected_material_id,
        "normalization_version": 3 if flat_schema or nested_schema else 1,
        "source_schema": "flat_detail_csv" if flat_schema else ("new_nested_detail" if nested_schema else "legacy_detail"),
        "date_range": {
            "type": _text(date_type),
            "start_date": _text(start_date),
            "end_date": _text(end_date),
        },
        "period_verification": period_verification,
        "title": _text(title),
        "video_url": _text(video_url),
        "video_duration": _number(video_duration),
        "core_data": core_data,
        "audience_portrait": audience_portrait,
        "business_date": _text(raw.get("bizDate") or raw.get("business_date")),
        "account_id": _text(raw.get("accountId") or raw.get("account_id")),
        "selection_group": selection_group,
        "script_text": _text(script_text_value),
        "content_formula": content_formula,
        "creative_breakdown": creative_breakdown,
        "metrics": core_metrics,
        "script_segments": script_segments,
        "trend_series": trend_series,
        "high_points": high_points,
        "loss_points": loss_points,
        "data_availability": {
            **_detail_availability(
                trends_value,
                trend_series,
                high_points,
                loss_points,
                parse_failed="secondTrend" in parse_failed_fields or "trends" in parse_failed_fields,
            ),
            "selection_group": {
                "available": selection_group["id"] != "default",
                "missing_reason": "" if selection_group["id"] != "default" else "source_empty",
            },
            "script_text": _availability_with_parse_state(
                script_text_value, has_values=bool(_text(script_text_value)),
                parse_failed="scriptText" in parse_failed_fields or "script_text" in parse_failed_fields,
            ),
            "content_formula": _availability_with_parse_state(
                content_formula, has_values=content_formula is not None,
                parse_failed="contentFormula" in parse_failed_fields or "content_formula" in parse_failed_fields,
            ),
            "creative_breakdown": _availability_with_parse_state(
                creative_breakdown, has_values=creative_breakdown is not None,
                parse_failed="creativeBreakdown" in parse_failed_fields or "creative_breakdown" in parse_failed_fields,
            ),
            "audience_portrait": _availability(audience_portrait, has_values=bool(audience_portrait)),
            "script_segments": script_segments_availability,
        },
        "source_paths": {"detail": source_path},
        "source_hashes": source_hashes,
    }
