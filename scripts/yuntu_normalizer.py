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


def _detail_availability(trends, trend_series, high_points, loss_points):
    return {
        "trends": _availability(trends, has_values=bool(trend_series)),
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


def normalize_detail_records(
    raw_records, *, material_id, source_path, expected_selection_group=None
):
    if isinstance(raw_records, list) and raw_records:
        raw = raw_records[0]
    elif isinstance(raw_records, dict):
        raw = raw_records
    else:
        raise YuntuNormalizeError("detail records must contain one detail object")
    if not isinstance(raw, dict):
        raise YuntuNormalizeError("detail record must be an object")

    expected_material_id = _require_material_id(material_id)
    actual_material_id = _require_material_id(
        raw.get("materialId") or raw.get("material_id") or material_id
    )
    if actual_material_id != expected_material_id:
        raise YuntuNormalizeError("detail material_id does not match selected material")

    selection_group = _selection_group(raw)
    if expected_selection_group is not None:
        expected_id = _text(expected_selection_group.get("id"))
        if expected_id and expected_id != "default":
            if selection_group["id"] == "default":
                raise YuntuNormalizeError("detail response is missing selection group echo")
            if selection_group["id"] != expected_id:
                raise YuntuNormalizeError("detail selection group does not match selected material")
            selection_group = {
                key: _text(expected_selection_group.get(key)) or selection_group[key]
                for key in selection_group
            }

    trend_series = []
    high_points = []
    loss_points = []
    trends_value = raw.get("trends")
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
    script_text_value = raw.get("scriptText") or raw.get("script_text")
    content_formula = raw.get("contentFormula") or raw.get("content_formula")
    if not isinstance(content_formula, (str, dict, list)):
        content_formula = None
    script_segments, script_segments_availability = _script_segments(
        raw.get("scriptSegments") or raw.get("script_segments")
    )
    return {
        "material_id": expected_material_id,
        "date_range": {
            "type": _text(raw.get("dateRangeType") or raw.get("date_range_type")),
            "start_date": _text(raw.get("startDate") or raw.get("start_date")),
            "end_date": _text(raw.get("endDate") or raw.get("end_date")),
        },
        "video_url": _text(raw.get("videoUrl") or raw.get("video_url")),
        "selection_group": selection_group,
        "script_text": _text(script_text_value),
        "content_formula": content_formula,
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
            ),
            "selection_group": {
                "available": selection_group["id"] != "default",
                "missing_reason": "" if selection_group["id"] != "default" else "source_empty",
            },
            "script_text": _availability(script_text_value, has_values=bool(_text(script_text_value))),
            "content_formula": _availability(content_formula, has_values=content_formula is not None),
            "script_segments": script_segments_availability,
        },
        "source_paths": {"detail": source_path},
    }
