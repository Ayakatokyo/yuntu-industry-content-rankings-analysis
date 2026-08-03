"""Select auditable highlight-frame candidates from normalized Yuntu details."""


ALLOWED_HIGHLIGHT_TRENDS = (
    "点赞指数",
    "流失指数",
    "点击指数",
    "互动指数",
    "评论指数",
)


def normalize_highlight_trends(trend_names):
    """Validate configured highlight metrics and preserve their first occurrence."""
    normalized = []
    for trend_name in trend_names:
        if trend_name not in ALLOWED_HIGHLIGHT_TRENDS:
            raise ValueError(f"未知的高光趋势指标: {trend_name}")
        if trend_name not in normalized:
            normalized.append(trend_name)
    return normalized


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _normalized_points(series):
    by_second = {}
    for point in series:
        if not isinstance(point, dict):
            continue
        second = point.get("second")
        value = point.get("value")
        if not isinstance(second, int) or isinstance(second, bool) or not _is_number(value):
            continue
        previous = by_second.get(second)
        if previous is None or value > previous:
            by_second[second] = value
    return sorted(by_second.items())


def _collapse_plateaus(points):
    """Keep the earliest second of every continuous equal-value plateau."""
    collapsed = []
    for second, value in points:
        if (
            collapsed
            and second == collapsed[-1][0] + 1
            and value == collapsed[-1][1]
        ):
            continue
        collapsed.append((second, value))
    return collapsed


def _local_peaks(series):
    points = _collapse_plateaus(_normalized_points(series))
    if len(points) < 2:
        return []

    peaks = []
    for index, (second, value) in enumerate(points):
        if index == 0:
            is_peak = value > points[1][1]
        elif index == len(points) - 1:
            is_peak = value > points[index - 1][1]
        else:
            is_peak = value > points[index - 1][1] and value > points[index + 1][1]
        if is_peak:
            peaks.append((second, value))
    return sorted(peaks, key=lambda point: (-point[1], point[0]))[:3]


def _within_high_point(detail, trend_name, second):
    for high_point in detail.get("high_points", []):
        if not isinstance(high_point, dict) or high_point.get("trend_name") != trend_name:
            continue
        start_sec = high_point.get("start_sec")
        end_sec = high_point.get("end_sec")
        if (
            isinstance(start_sec, int)
            and not isinstance(start_sec, bool)
            and isinstance(end_sec, int)
            and not isinstance(end_sec, bool)
            and start_sec <= second <= end_sec
        ):
            return True
    return False


def _series_for_trend(detail, trend_name):
    points = []
    for trend in detail.get("trend_series", []):
        if isinstance(trend, dict) and trend.get("trend_name") == trend_name:
            series = trend.get("series")
            if isinstance(series, list):
                points.extend(series)
    return points


def select_highlight_candidates(detail, trend_names):
    """Return a cover frame plus up to three ranked peaks for each selected metric."""
    trend_names = normalize_highlight_trends(trend_names)
    candidates = {0: {"second": 0, "is_cover": True, "reasons": [{"type": "cover"}]}}

    for trend_name in trend_names:
        for rank, (second, value) in enumerate(
            _local_peaks(_series_for_trend(detail, trend_name)), start=1
        ):
            candidate = candidates.setdefault(
                second, {"second": second, "is_cover": False, "reasons": []}
            )
            candidate["reasons"].append(
                {
                    "type": "local_peak",
                    "trend_name": trend_name,
                    "value": value,
                    "rank": rank,
                    "within_high_point": _within_high_point(detail, trend_name, second),
                }
            )

    return [candidates[second] for second in sorted(candidates)]
