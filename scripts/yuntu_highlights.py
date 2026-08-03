"""Select and extract auditable highlight frames from normalized Yuntu details."""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

import requests


ALLOWED_HIGHLIGHT_TRENDS = (
    "点赞指数",
    "流失指数",
    "点击指数",
    "互动指数",
    "评论指数",
)

VIDEO_DOWNLOAD_TIMEOUT_SECONDS = 30
VIDEO_DOWNLOAD_MAX_BYTES = 200 * 1024 * 1024


class HighlightFrameError(Exception):
    """Raised when an individual video or frame cannot be processed."""


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


def download_video(
    url,
    destination,
    *,
    session=None,
    timeout=VIDEO_DOWNLOAD_TIMEOUT_SECONDS,
    max_bytes=VIDEO_DOWNLOAD_MAX_BYTES,
):
    """Download one HTTP(S) video while enforcing the configured byte limit."""
    parsed = urlsplit(url) if isinstance(url, str) else None
    if not parsed or parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HighlightFrameError("video URL must use HTTP(S)")

    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(f".{target.name}.part")
    response = None
    try:
        response = (session or requests).get(url, stream=True, timeout=timeout)
        response.raise_for_status()
        content_length = response.headers.get("Content-Length")
        if content_length is not None:
            try:
                if int(content_length) > max_bytes:
                    raise HighlightFrameError("video response exceeds maximum size")
            except ValueError:
                pass

        bytes_written = 0
        with partial.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                bytes_written += len(chunk)
                if bytes_written > max_bytes:
                    raise HighlightFrameError("video response exceeds maximum size")
                handle.write(chunk)
        if bytes_written == 0:
            raise HighlightFrameError("video response is empty")
        partial.replace(target)
        return target
    except HighlightFrameError:
        raise
    except Exception as error:
        raise HighlightFrameError(f"video download failed: {error}") from error
    finally:
        partial.unlink(missing_ok=True)
        if response is not None:
            response.close()


def _resolve_ffmpeg(ffmpeg_bin=None):
    candidate = ffmpeg_bin or os.environ.get("IMAGEIO_FFMPEG_EXE") or shutil.which("ffmpeg")
    if not candidate:
        raise HighlightFrameError("ffmpeg executable was not found")
    return candidate


def extract_frame(video_path, second, destination, *, ffmpeg_bin=None):
    """Use FFmpeg to produce one non-empty JPEG, publishing it atomically."""
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(f".{target.name}.part")
    command = [
        _resolve_ffmpeg(ffmpeg_bin),
        "-y",
        "-ss",
        str(second),
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(partial),
    ]
    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=VIDEO_DOWNLOAD_TIMEOUT_SECONDS,
            check=False,
        )
        if completed.returncode != 0 or not partial.is_file() or partial.stat().st_size == 0:
            raise HighlightFrameError("ffmpeg frame extraction failed")
        partial.replace(target)
        return target
    except HighlightFrameError:
        raise
    except (OSError, subprocess.SubprocessError) as error:
        raise HighlightFrameError(f"ffmpeg frame extraction failed: {error}") from error
    finally:
        partial.unlink(missing_ok=True)


def _write_json_atomically(payload, destination):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(f".{destination.name}.part")
    try:
        partial.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        partial.replace(destination)
    finally:
        partial.unlink(missing_ok=True)


def _frame_record(candidate, *, available, relative_path=None, failure_reason=None):
    frame = {**candidate, "available": available}
    if relative_path is not None:
        frame["relative_path"] = relative_path
    if failure_reason is not None:
        frame["failure_reason"] = failure_reason
    return frame


def _material_frames(detail, trend_names, root, downloader, frame_extractor, ffmpeg_bin):
    candidates = select_highlight_candidates(detail, trend_names)
    material_id = str(detail.get("material_id") or "")
    video_url = detail.get("video_url")
    if not isinstance(video_url, str) or not video_url.strip():
        return [
            _frame_record(candidate, available=False, failure_reason="missing_video_url")
            for candidate in candidates
        ]

    material_root = root / "highlights" / material_id
    try:
        with tempfile.TemporaryDirectory(prefix="yuntu-highlight-") as temporary_directory:
            video_path = Path(temporary_directory) / "source-video"
            downloader(video_url, video_path)
            material_root.mkdir(parents=True, exist_ok=True)
            frames = []
            for index, candidate in enumerate(candidates, start=1):
                filename = f"{index:02d}-{candidate['second']:03d}s.jpg"
                target = material_root / filename
                relative_path = str(target.relative_to(root))
                try:
                    frame_extractor(video_path, candidate["second"], target, ffmpeg_bin=ffmpeg_bin)
                    frames.append(
                        _frame_record(
                            candidate,
                            available=True,
                            relative_path=relative_path,
                        )
                    )
                except Exception:
                    target.unlink(missing_ok=True)
                    frames.append(
                        _frame_record(candidate, available=False, failure_reason="extract_failed")
                    )
            return frames
    except Exception:
        return [
            _frame_record(candidate, available=False, failure_reason="download_failed")
            for candidate in candidates
        ]


def generate_highlights(
    details,
    trend_names,
    output_dir,
    *,
    downloader=download_video,
    frame_extractor=extract_frame,
    ffmpeg_bin=None,
):
    """Create non-blocking highlight JPEGs and return their manifest frame records."""
    selected_trends = normalize_highlight_trends(trend_names)
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    results = {}
    materials = []
    for detail in details:
        material_id = str(detail.get("material_id") or "")
        frames = _material_frames(
            detail,
            selected_trends,
            root,
            downloader,
            frame_extractor,
            ffmpeg_bin,
        )
        results[material_id] = frames
        materials.append(
            {
                "material_id": material_id,
                "video_url": detail.get("video_url") if isinstance(detail.get("video_url"), str) else "",
                "frames": frames,
            }
        )
    _write_json_atomically(
        {"schemaVersion": 1, "materials": materials}, root / "highlights-manifest.json"
    )
    return results
