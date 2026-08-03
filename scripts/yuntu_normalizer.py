"""Normalize Yuntu ranking and material-detail RPA records."""


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
                "title": _text(raw.get("title")),
                "rank": rank,
                "video_duration": _number(
                    raw.get("video_duration") or raw.get("videoDuration")
                ),
                "publish_time": _text(
                    object_index.get("publish_time") or raw.get("publish_time")
                ),
                "metrics": metrics,
                "people_tags": _flatten_tag_entries(people_tag_entry),
                "material_tags": _flatten_tag_entries(material_tag_entry),
                "data_availability": {
                    "metrics": _availability(
                        object_index_value if object_index_value is not None else raw,
                        has_values=bool(metrics),
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


def normalize_detail_records(raw_records, *, material_id, source_path):
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
    return {
        "material_id": expected_material_id,
        "date_range": {
            "type": _text(raw.get("dateRangeType") or raw.get("date_range_type")),
            "start_date": _text(raw.get("startDate") or raw.get("start_date")),
            "end_date": _text(raw.get("endDate") or raw.get("end_date")),
        },
        "video_url": _text(raw.get("videoUrl") or raw.get("video_url")),
        "trend_series": trend_series,
        "high_points": high_points,
        "loss_points": loss_points,
        "data_availability": _detail_availability(
            trends_value,
            trend_series,
            high_points,
            loss_points,
        ),
        "source_paths": {"detail": source_path},
    }
