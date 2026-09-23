# Yuntu Rankings Analysis Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a CSV-first RPA ingestion, normalization, analysis-fact, and report-rendering workflow for the 云图行业内容榜单分析 skill.

**Architecture:** Keep the existing fixed RPA connector identity in `scripts/rpa_connector.py`, but move new responsibilities into focused modules. RPA gateway results are unpacked into raw CSV or direct records, Yuntu-specific raw rows are normalized into stable JSON records, batch fetch writes manifest state, and later commands consume only normalized records.

**Tech Stack:** Python 3.9+ standard library, `requests>=2.31,<3`, `unittest`, JSON files, CSV parsing via `csv.DictReader`.

---

## File Structure

- Create `scripts/rpa_io.py`: gateway result unpacking, files-envelope validation, signed URL download, CSV parsing, JSON payload normalization, atomic JSON/file writing helpers.
- Create `scripts/yuntu_normalizer.py`: Yuntu list/detail record normalization from parsed CSV rows or direct JSON records into stable internal records.
- Create `scripts/yuntu_batch.py`: fetch orchestration for candidate pool, Top N selection, selected/rejected/cancelled manifest records, raw and normalized output paths.
- Create `scripts/yuntu_analysis.py`: build `yuntu-analysis-data.json` and `yuntu-analysis-prompt.md` from normalized records and manifest.
- Create `scripts/yuntu_report.py`: validate `yuntu-ai-analysis.json` and render `final-report-data.json`, `final-report.md`, and optional `final-report.html`.
- Modify `scripts/rpa_connector.py`: wire new `fetch`, `prepare-analysis`, and `render-report` CLI subcommands while preserving `list-accounts`, `schema`, `self-test`, and existing connector metadata.
- Modify `SKILL.md`: document CSV-first workflow, output directories, new commands, and failure behavior.
- Modify `agents/openai.yaml`: update prompt description only if the visible interface should mention report generation.
- Add tests:
  - `tests/test_rpa_io.py`
  - `tests/test_yuntu_normalizer.py`
  - `tests/test_yuntu_batch.py`
  - `tests/test_yuntu_analysis.py`
  - `tests/test_yuntu_report.py`
  - Extend `tests/test_skill_contract.py`

## Task 1: RPA Gateway Files and CSV IO

**Files:**
- Create: `scripts/rpa_io.py`
- Test: `tests/test_rpa_io.py`

- [ ] **Step 1: Write failing tests for files-envelope validation and payload compatibility**

Add `tests/test_rpa_io.py`:

```python
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "rpa_io.py"


def load_module():
    spec = importlib.util.spec_from_file_location("rpa_io", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeDownloadResponse:
    def __init__(self, chunks, status_error=None):
        self.chunks = chunks
        self.status_error = status_error

    def raise_for_status(self):
        if self.status_error:
            raise self.status_error

    def iter_content(self, chunk_size):
        return iter(self.chunks)


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.gets = []

    def get(self, url, **kwargs):
        self.gets.append((url, kwargs))
        return self.response


class RpaIoTests(unittest.TestCase):
    def test_unpack_gateway_result_accepts_files_envelope(self):
        io = load_module()
        result = {
            "success": True,
            "code": "200",
            "data": {
                "result_type": "files",
                "result_content": {
                    "status": "COMPLETED",
                    "failedInstances": 0,
                    "files": [{"fileUrl": "https://download.example/list.csv"}],
                },
            },
        }

        unpacked = io.unpack_gateway_result(result)

        self.assertEqual(unpacked.kind, "files")
        self.assertEqual(unpacked.file_url, "https://download.example/list.csv")

    def test_unpack_gateway_result_rejects_bad_files_envelopes(self):
        io = load_module()
        bad_cases = (
            ({"success": False, "code": "200", "data": {"result_type": "files"}}, "successful"),
            ({"success": True, "code": "500", "data": {"result_type": "files"}}, "successful"),
            ({"success": True, "code": "200", "data": {"result_type": "files", "result_content": {"status": "RUNNING", "failedInstances": 0, "files": [{"fileUrl": "https://x"}]}}}, "complete"),
            ({"success": True, "code": "200", "data": {"result_type": "files", "result_content": {"status": "COMPLETED", "failedInstances": 1, "files": [{"fileUrl": "https://x"}]}}}, "complete"),
            ({"success": True, "code": "200", "data": {"result_type": "files", "result_content": {"status": "COMPLETED", "failedInstances": 0, "files": []}}}, "fileUrl"),
        )
        for payload, message in bad_cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(io.RpaIoError, message):
                    io.unpack_gateway_result(payload)

    def test_unpack_gateway_result_accepts_direct_payload_records(self):
        io = load_module()
        self.assertEqual(
            io.unpack_gateway_result({"success": True, "data": [{"material_id": "1"}]}).records,
            [{"material_id": "1"}],
        )
        self.assertEqual(
            io.unpack_gateway_result({"success": True, "data": {"result_type": "payload", "payload": "[{\"material_id\":\"2\"}]"}}).records,
            [{"material_id": "2"}],
        )
        self.assertEqual(
            io.unpack_gateway_result([{"material_id": "3"}]).records,
            [{"material_id": "3"}],
        )

    def test_download_file_atomically_and_reject_empty_file(self):
        io = load_module()
        with tempfile.TemporaryDirectory() as temporary_directory:
            target = Path(temporary_directory) / "raw-csv" / "list.csv"
            session = FakeSession(FakeDownloadResponse([b"a,b\n1,2\n"]))
            path = io.download_file("https://download.example/list.csv", target, session=session)

            self.assertEqual(path, target)
            self.assertEqual(target.read_text(encoding="utf-8"), "a,b\n1,2\n")
            self.assertEqual(session.gets[0][0], "https://download.example/list.csv")
            self.assertFalse(list(target.parent.glob("*.tmp")))

            with self.assertRaisesRegex(io.RpaIoError, "empty"):
                io.download_file(
                    "https://download.example/empty.csv",
                    Path(temporary_directory) / "empty.csv",
                    session=FakeSession(FakeDownloadResponse([])),
                )

    def test_parse_csv_records_supports_common_delimiters_and_json_cells(self):
        io = load_module()
        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "list.csv"
            source.write_text(
                "material_id\x01object_index\x01tags\n"
                "101\x01{\"ctr\":0.5}\x01[\"轻食\",\"便携\"]\n",
                encoding="utf-8",
            )

            records = io.parse_csv_records(source)

            self.assertEqual(records[0]["material_id"], "101")
            self.assertEqual(records[0]["object_index"], {"ctr": 0.5})
            self.assertEqual(records[0]["tags"], ["轻食", "便携"])

    def test_parse_csv_records_rejects_bad_headers_and_empty_files(self):
        io = load_module()
        with tempfile.TemporaryDirectory() as temporary_directory:
            empty = Path(temporary_directory) / "empty.csv"
            empty.write_text("material_id,title\n", encoding="utf-8")
            with self.assertRaisesRegex(io.RpaIoError, "no records"):
                io.parse_csv_records(empty)

            duplicate = Path(temporary_directory) / "duplicate.csv"
            duplicate.write_text("material_id,material_id\n1,2\n", encoding="utf-8")
            with self.assertRaisesRegex(io.RpaIoError, "duplicate"):
                io.parse_csv_records(duplicate)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the new tests and verify they fail because the module is missing**

Run:

```bash
python -m unittest tests/test_rpa_io.py -v
```

Expected: FAIL or ERROR mentioning `scripts/rpa_io.py` is missing.

- [ ] **Step 3: Implement `scripts/rpa_io.py`**

Create `scripts/rpa_io.py`:

```python
"""RPA gateway result IO helpers for Yuntu analysis workflows."""

from dataclasses import dataclass
import csv
import io
import json
import os
from pathlib import Path
import tempfile

import requests


class RpaIoError(RuntimeError):
    """Raised when RPA gateway output cannot be materialized safely."""


@dataclass(frozen=True)
class GatewayResult:
    kind: str
    records: list | None = None
    file_url: str | None = None


def _decode_json_cell(value):
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return ""
    if text[0] not in "[{":
        return value
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return value


def _records_from_payload(payload):
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise RpaIoError("RPA payload string must contain valid JSON records") from exc
    if not isinstance(payload, list):
        raise RpaIoError("RPA gateway payload must be a record list")
    return payload


def _file_url_from_envelope(result):
    if result.get("success") is not True or result.get("code") not in (200, "200"):
        raise RpaIoError("RPA gateway files response was not successful")
    data = result.get("data")
    content = data.get("result_content") if isinstance(data, dict) else None
    if not isinstance(content, dict):
        raise RpaIoError("RPA gateway files response is missing result_content")
    if content.get("status") != "COMPLETED" or content.get("failedInstances") != 0:
        raise RpaIoError("RPA gateway files task did not complete successfully")
    files = content.get("files")
    if not isinstance(files, list) or not files or not isinstance(files[0], dict):
        raise RpaIoError("RPA gateway files response has no fileUrl")
    file_url = files[0].get("fileUrl")
    if not isinstance(file_url, str) or not file_url.strip():
        raise RpaIoError("RPA gateway files response fileUrl is missing")
    return file_url.strip()


def unpack_gateway_result(result):
    if isinstance(result, list):
        return GatewayResult(kind="records", records=result)
    if not isinstance(result, dict):
        raise RpaIoError("RPA gateway result must be a list or object")

    data = result.get("data")
    if isinstance(data, dict) and data.get("result_type") == "files":
        return GatewayResult(kind="files", file_url=_file_url_from_envelope(result))
    if isinstance(data, dict) and data.get("result_type") == "payload":
        return GatewayResult(kind="records", records=_records_from_payload(data.get("payload")))
    if isinstance(data, list):
        return GatewayResult(kind="records", records=data)
    if "payload" in result:
        return GatewayResult(kind="records", records=_records_from_payload(result.get("payload")))
    if result.get("success") is True:
        return GatewayResult(kind="records", records=[result])
    raise RpaIoError("RPA gateway result did not contain records or files")


def download_file(file_url, target_path, *, session=None, timeout=300):
    session = requests.Session() if session is None else session
    target = Path(target_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="wb",
        suffix=".tmp",
        dir=target.parent,
        delete=False,
    ) as staging_file:
        staging_path = Path(staging_file.name)
        try:
            response = session.get(file_url, stream=True, timeout=timeout)
            response.raise_for_status()
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    staging_file.write(chunk)
        except Exception as exc:
            try:
                staging_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise RpaIoError(f"unable to download RPA file: {exc}") from exc
    try:
        if staging_path.stat().st_size == 0:
            raise RpaIoError("downloaded RPA file is empty")
        os.replace(staging_path, target)
    except Exception:
        try:
            staging_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return target


def _detect_delimiter(header_line):
    for delimiter in ("\x01", ",", "\t"):
        if delimiter in header_line:
            return delimiter
    raise RpaIoError("RPA CSV header must use a supported delimiter")


def parse_csv_records(path):
    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise RpaIoError(f"unable to read RPA CSV {source}: {exc}") from exc
    first_line = text.partition("\n")[0]
    delimiter = _detect_delimiter(first_line)
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    headers = reader.fieldnames
    if not headers or any(not header for header in headers):
        raise RpaIoError(f"RPA CSV {source} has an invalid header")
    if len(headers) != len(set(headers)):
        raise RpaIoError(f"RPA CSV {source} has duplicate header names")

    records = []
    for row_number, row in enumerate(reader, start=2):
        if None in row:
            raise RpaIoError(f"RPA CSV {source} row {row_number} has too many fields")
        if not any(value not in (None, "") for value in row.values()):
            continue
        records.append({key: _decode_json_cell(value) for key, value in row.items()})
    if not records:
        raise RpaIoError(f"RPA CSV {source} has no records")
    return records


def write_json_atomically(result, output_path):
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".tmp",
        dir=target.parent,
        delete=False,
    ) as staging_file:
        staging_path = Path(staging_file.name)
        try:
            json.dump(result, staging_file, ensure_ascii=False, indent=2)
            staging_file.write("\n")
        except Exception:
            try:
                staging_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise
    try:
        os.replace(staging_path, target)
    except Exception:
        try:
            staging_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return target
```

- [ ] **Step 4: Run tests for Task 1**

Run:

```bash
python -m unittest tests/test_rpa_io.py -v
```

Expected: PASS, 6 tests.

- [ ] **Step 5: Commit Task 1**

```bash
git add scripts/rpa_io.py tests/test_rpa_io.py
git commit -m "feat: add RPA file output adapter"
```

## Task 2: Yuntu Record Normalization

**Files:**
- Create: `scripts/yuntu_normalizer.py`
- Test: `tests/test_yuntu_normalizer.py`

- [ ] **Step 1: Write failing tests for list and detail normalization**

Add `tests/test_yuntu_normalizer.py`:

```python
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "yuntu_normalizer.py"


def load_module():
    spec = importlib.util.spec_from_file_location("yuntu_normalizer", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class YuntuNormalizerTests(unittest.TestCase):
    def test_normalize_list_records_extracts_metrics_tags_and_rank(self):
        normalizer = load_module()
        raw = [
            {
                "title": "洽洽你也太卷了，这价拿到这么大一箱！#洽洽",
                "material_id": "7620993598538301494",
                "video_duration": "31",
                "object_index": {
                    "ctr": 0.664652568,
                    "show_cnt": "1655",
                    "cvr": 0.1709090909,
                    "pvr": 0.1135951662,
                    "play_over_rate": 0.239633818,
                    "play_duration_avg": 13.752265861,
                    "publish_time": "20260325",
                },
                "people_tag_entry": [
                    {"people_tag_type": 4, "tag_name_list": ["都市银发", "小镇中老年"]},
                    {"people_tag_type": 3, "tag_name_list": ["60+", "51-55"]},
                ],
                "material_tag_entry": [
                    {"material_tag_type": 52, "tag_name_list": ["包装_独立包装", "使用感受和服务体验_便携"]},
                    {"material_tag_type": 58, "tag_name_list": ["使用场景_健身"]},
                ],
            }
        ]

        records = normalizer.normalize_list_records(raw, source_path="raw-csv/list.csv")

        self.assertEqual(records[0]["material_id"], "7620993598538301494")
        self.assertEqual(records[0]["rank"], 1)
        self.assertEqual(records[0]["metrics"]["ctr"], 0.664652568)
        self.assertEqual(records[0]["metrics"]["show_cnt"], 1655)
        self.assertEqual(records[0]["people_tags"], ["都市银发", "小镇中老年", "60+", "51-55"])
        self.assertIn("包装_独立包装", records[0]["material_tags"])
        self.assertEqual(records[0]["source_paths"]["list"], "raw-csv/list.csv")

    def test_normalize_list_records_rejects_missing_numeric_material_id(self):
        normalizer = load_module()
        with self.assertRaisesRegex(normalizer.YuntuNormalizeError, "material_id"):
            normalizer.normalize_list_records([{"material_id": "abc"}], source_path="raw-csv/list.csv")

    def test_normalize_detail_records_extracts_trends(self):
        normalizer = load_module()
        raw = [
            {
                "materialId": "7648216411198554162",
                "startDate": "2026-06-23",
                "endDate": "2026-06-29",
                "dateRangeType": "LAST_7_DAYS",
                "videoUrl": "https://video.example/material.mp4",
                "trends": [
                    {
                        "trendName": "点击指数",
                        "trendType": 3,
                        "tendList": [{"x": 0, "y": 0.5}, {"x": 1, "y": 1}],
                        "highPoint": {"start_point": "1", "end_point": "2"},
                        "lossPoint": {"start_point": "0", "end_point": "1", "loss_percent": 0.5},
                    }
                ],
            }
        ]

        record = normalizer.normalize_detail_records(
            raw,
            material_id="7648216411198554162",
            source_path="raw-csv/details/7648216411198554162.csv",
        )

        self.assertEqual(record["material_id"], "7648216411198554162")
        self.assertEqual(record["date_range"]["type"], "LAST_7_DAYS")
        self.assertEqual(record["trend_series"][0]["trend_name"], "点击指数")
        self.assertEqual(record["high_points"][0]["start_sec"], 1)
        self.assertEqual(record["loss_points"][0]["loss_percent"], 0.5)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and verify they fail because the module is missing**

Run:

```bash
python -m unittest tests/test_yuntu_normalizer.py -v
```

Expected: FAIL or ERROR mentioning `scripts/yuntu_normalizer.py` is missing.

- [ ] **Step 3: Implement `scripts/yuntu_normalizer.py`**

Create `scripts/yuntu_normalizer.py`:

```python
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


def normalize_list_records(raw_records, *, source_path):
    if not isinstance(raw_records, list):
        raise YuntuNormalizeError("list records must be a list")
    normalized = []
    for rank, raw in enumerate(raw_records, start=1):
        if not isinstance(raw, dict):
            raise YuntuNormalizeError("list record must be an object")
        material_id = _require_material_id(raw.get("material_id") or raw.get("materialId"))
        object_index = raw.get("object_index")
        if not isinstance(object_index, dict):
            object_index = {}
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
                "video_duration": _number(raw.get("video_duration") or raw.get("videoDuration")),
                "publish_time": _text(object_index.get("publish_time") or raw.get("publish_time")),
                "metrics": metrics,
                "people_tags": _flatten_tag_entries(raw.get("people_tag_entry")),
                "material_tags": _flatten_tag_entries(raw.get("material_tag_entry")),
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
        "high_point": raw_trend.get("highPoint") if isinstance(raw_trend.get("highPoint"), dict) else None,
        "loss_point": raw_trend.get("lossPoint") if isinstance(raw_trend.get("lossPoint"), dict) else None,
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
    actual_material_id = _require_material_id(raw.get("materialId") or raw.get("material_id") or material_id)
    if actual_material_id != expected_material_id:
        raise YuntuNormalizeError("detail material_id does not match selected material")

    trend_series = []
    high_points = []
    loss_points = []
    trends = raw.get("trends")
    if not isinstance(trends, list):
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
        "source_paths": {"detail": source_path},
    }
```

- [ ] **Step 4: Run tests for Task 2**

Run:

```bash
python -m unittest tests/test_yuntu_normalizer.py -v
```

Expected: PASS, 3 tests.

- [ ] **Step 5: Commit Task 2**

```bash
git add scripts/yuntu_normalizer.py tests/test_yuntu_normalizer.py
git commit -m "feat: normalize Yuntu ranking records"
```

## Task 3: Batch Fetch Orchestration and Manifest

**Files:**
- Create: `scripts/yuntu_batch.py`
- Modify: `scripts/rpa_connector.py`
- Test: `tests/test_yuntu_batch.py`

- [ ] **Step 1: Write failing tests for CSV-first batch flow and JSON compatibility**

Add `tests/test_yuntu_batch.py`:

```python
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BATCH_PATH = ROOT / "scripts" / "yuntu_batch.py"


def load_batch():
    spec = importlib.util.spec_from_file_location("yuntu_batch", BATCH_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeInvoker:
    def __init__(self, list_result, detail_results):
        self.list_result = list_result
        self.detail_results = list(detail_results)
        self.list_calls = []
        self.detail_calls = []

    def invoke_list(self, shop_id, list_params):
        self.list_calls.append((shop_id, list_params))
        return self.list_result

    def invoke_detail(self, shop_id, detail_params):
        self.detail_calls.append((shop_id, detail_params))
        return self.detail_results.pop(0)


class FakeDownloader:
    def __init__(self, contents_by_url):
        self.contents_by_url = contents_by_url
        self.downloads = []

    def download_file(self, file_url, target_path):
        self.downloads.append((file_url, str(target_path)))
        target = Path(target_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.contents_by_url[file_url], encoding="utf-8")
        return target


class YuntuBatchTests(unittest.TestCase):
    def files_result(self, url):
        return {
            "success": True,
            "code": "200",
            "data": {
                "result_type": "files",
                "result_content": {
                    "status": "COMPLETED",
                    "failedInstances": 0,
                    "files": [{"fileUrl": url}],
                },
            },
        }

    def test_fetch_batch_downloads_csv_normalizes_and_writes_manifest(self):
        batch = load_batch()
        invoker = FakeInvoker(
            self.files_result("https://files.example/list.csv"),
            [
                self.files_result("https://files.example/101.csv"),
                self.files_result("https://files.example/202.csv"),
            ],
        )
        downloader = FakeDownloader(
            {
                "https://files.example/list.csv": (
                    "material_id\x01title\x01object_index\x01people_tag_entry\x01material_tag_entry\n"
                    "101\x01A\x01{\"ctr\":0.7}\x01[]\x01[]\n"
                    "202\x01B\x01{\"ctr\":0.4}\x01[]\x01[]\n"
                ),
                "https://files.example/101.csv": (
                    "materialId\x01dateRangeType\x01trends\n"
                    "101\x01LAST_7_DAYS\x01[{\"trendName\":\"点击指数\",\"tendList\":[{\"x\":1,\"y\":1}],\"highPoint\":{\"start_point\":\"1\",\"end_point\":\"2\"}}]\n"
                ),
                "https://files.example/202.csv": (
                    "materialId\x01dateRangeType\x01trends\n"
                    "202\x01LAST_7_DAYS\x01[]\n"
                ),
            }
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            status = batch.fetch_batch(
                shop_id="shop-42",
                list_params={"industry": "食品饮料"},
                detail_date_params={"date_range_type": "LAST_7_DAYS"},
                target_top_n=2,
                candidate_top_n=3,
                output_dir=temporary_directory,
                invoker=invoker,
                downloader=downloader,
            )
            root = Path(temporary_directory)
            manifest = json.loads((root / "batch-manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(status, 0)
        self.assertEqual([item["material_id"] for item in manifest["selectedMaterials"]], ["101", "202"])
        self.assertEqual(manifest["rejectedMaterials"], [])
        self.assertTrue((root / "normalized" / "list-records.json").exists())
        self.assertTrue((root / "normalized" / "detail-records" / "101.json").exists())
        self.assertTrue((root / "raw-csv" / "details" / "101.csv").exists())

    def test_fetch_batch_rejects_failed_details_and_continues_to_candidate_replacement(self):
        batch = load_batch()
        invoker = FakeInvoker(
            {"success": True, "data": [{"material_id": "101"}, {"material_id": "202"}, {"material_id": "303"}]},
            [
                {"success": False},
                {"success": True, "data": [{"materialId": "202", "dateRangeType": "LAST_7_DAYS", "trends": []}]},
                {"success": True, "data": [{"materialId": "303", "dateRangeType": "LAST_7_DAYS", "trends": []}]},
            ],
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            status = batch.fetch_batch(
                shop_id="shop-42",
                list_params={},
                detail_date_params={"date_range_type": "LAST_7_DAYS"},
                target_top_n=2,
                candidate_top_n=3,
                output_dir=temporary_directory,
                invoker=invoker,
            )
            manifest = json.loads((Path(temporary_directory) / "batch-manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(status, 1)
        self.assertEqual([item["material_id"] for item in manifest["selectedMaterials"]], ["202", "303"])
        self.assertEqual([item["material_id"] for item in manifest["rejectedMaterials"]], ["101"])
        self.assertEqual(len(invoker.detail_calls), 3)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and verify they fail because orchestration is missing**

Run:

```bash
python -m unittest tests/test_yuntu_batch.py -v
```

Expected: FAIL or ERROR mentioning `scripts/yuntu_batch.py` is missing.

- [ ] **Step 3: Implement `scripts/yuntu_batch.py`**

Create `scripts/yuntu_batch.py` with these interfaces:

```python
"""Batch fetch orchestration for Yuntu rankings analysis."""

from pathlib import Path
import time

from rpa_io import RpaIoError, download_file, parse_csv_records, unpack_gateway_result, write_json_atomically
from yuntu_normalizer import YuntuNormalizeError, normalize_detail_records, normalize_list_records


class YuntuBatchError(RuntimeError):
    """Raised when a Yuntu batch cannot be started."""


class ConnectorInvoker:
    def __init__(self, invoke_list, invoke_detail):
        self._invoke_list = invoke_list
        self._invoke_detail = invoke_detail

    def invoke_list(self, shop_id, list_params):
        return self._invoke_list(shop_id, list_params)

    def invoke_detail(self, shop_id, detail_params):
        return self._invoke_detail(shop_id, detail_params)


class FileDownloader:
    def download_file(self, file_url, target_path):
        return download_file(file_url, target_path)


def _elapsed(started_at):
    return round(time.monotonic() - started_at, 6)


def _validate_positive_int(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise YuntuBatchError(f"{name} must be a positive integer")
    return value


def _material_ids_from_list(records, candidate_top_n):
    selected = []
    seen = set()
    for record in records:
        material_id = record["material_id"]
        if material_id not in seen:
            seen.add(material_id)
            selected.append(material_id)
        if len(selected) >= candidate_top_n:
            break
    return selected


def _materialize_records(result, *, csv_path, json_path, downloader):
    unpacked = unpack_gateway_result(result)
    if unpacked.kind == "files":
        path = downloader.download_file(unpacked.file_url, csv_path)
        return parse_csv_records(path), str(path)
    write_json_atomically(unpacked.records, json_path)
    return unpacked.records, str(json_path)


def _new_manifest(*, list_params, detail_date_params, target_top_n, candidate_top_n):
    return {
        "schemaVersion": 1,
        "status": "running",
        "filters": list_params,
        "detailDateRange": detail_date_params,
        "targetTopN": target_top_n,
        "candidateTopN": candidate_top_n,
        "candidateMaterials": [],
        "submittedMaterials": [],
        "selectedMaterials": [],
        "rejectedMaterials": [],
        "cancelledMaterials": [],
        "timingsSec": {},
    }


def fetch_batch(*, shop_id, list_params, detail_date_params, target_top_n, candidate_top_n, output_dir, invoker, downloader=None):
    target_top_n = _validate_positive_int(target_top_n, "target_top_n")
    candidate_top_n = _validate_positive_int(candidate_top_n, "candidate_top_n")
    if candidate_top_n < target_top_n:
        raise YuntuBatchError("candidate_top_n cannot be smaller than target_top_n")
    if not isinstance(shop_id, str) or not shop_id.strip():
        raise YuntuBatchError("shop_id is required")
    downloader = FileDownloader() if downloader is None else downloader
    root = Path(output_dir)
    manifest_path = root / "batch-manifest.json"
    manifest = _new_manifest(
        list_params=list_params,
        detail_date_params=detail_date_params,
        target_top_n=target_top_n,
        candidate_top_n=candidate_top_n,
    )

    started = time.monotonic()
    try:
        raw_list, list_source = _materialize_records(
            invoker.invoke_list(shop_id, list_params),
            csv_path=root / "raw-csv" / "list.csv",
            json_path=root / "raw-json" / "list-response.json",
            downloader=downloader,
        )
        list_records = normalize_list_records(raw_list, source_path=_relative(root, list_source))
        write_json_atomically(list_records, root / "normalized" / "list-records.json")
    except Exception as exc:
        manifest["status"] = "list_failed"
        manifest["error"] = str(exc)
        manifest["timingsSec"]["totalSec"] = _elapsed(started)
        write_json_atomically(manifest, manifest_path)
        return 1

    candidate_ids = _material_ids_from_list(list_records, candidate_top_n)
    manifest["candidateMaterials"] = [{"rank": index, "material_id": material_id} for index, material_id in enumerate(candidate_ids, start=1)]
    list_by_id = {record["material_id"]: record for record in list_records}

    had_rejection = False
    for rank, material_id in enumerate(candidate_ids, start=1):
        if len(manifest["selectedMaterials"]) >= target_top_n:
            manifest["cancelledMaterials"].append({"rank": rank, "material_id": material_id, "reason": "target_satisfied"})
            continue
        detail_started = time.monotonic()
        submitted = {"rank": rank, "material_id": material_id}
        manifest["submittedMaterials"].append(submitted)
        try:
            raw_detail, detail_source = _materialize_records(
                invoker.invoke_detail(shop_id, {**detail_date_params, "material_id": material_id}),
                csv_path=root / "raw-csv" / "details" / f"{material_id}.csv",
                json_path=root / "raw-json" / "details" / f"{material_id}.json",
                downloader=downloader,
            )
            detail_record = normalize_detail_records(
                raw_detail,
                material_id=material_id,
                source_path=_relative(root, detail_source),
            )
            detail_output = root / "normalized" / "detail-records" / f"{material_id}.json"
            write_json_atomically(detail_record, detail_output)
            manifest["selectedMaterials"].append(
                {
                    "rank": rank,
                    "material_id": material_id,
                    "listRecordPath": "normalized/list-records.json",
                    "detailRecordPath": _relative(root, detail_output),
                    "rawDetailPath": _relative(root, detail_source),
                    "timingsSec": {"detailFetchSec": _elapsed(detail_started)},
                }
            )
        except Exception as exc:
            had_rejection = True
            manifest["rejectedMaterials"].append(
                {
                    "rank": rank,
                    "material_id": material_id,
                    "reason": exc.__class__.__name__,
                    "error": str(exc),
                    "timingsSec": {"detailFetchSec": _elapsed(detail_started)},
                }
            )

    ready_materials = [list_by_id[item["material_id"]] for item in manifest["selectedMaterials"]]
    write_json_atomically({"materials": ready_materials}, root / "normalized" / "top-materials-rpa-ready.json")
    manifest["status"] = "success" if len(manifest["selectedMaterials"]) >= target_top_n and not had_rejection else "partial"
    manifest["timingsSec"]["totalSec"] = _elapsed(started)
    write_json_atomically(manifest, manifest_path)
    return 0 if manifest["status"] == "success" else 1


def _relative(root, path):
    return str(Path(path).resolve().relative_to(Path(root).resolve()))
```

- [ ] **Step 4: Wire `scripts/rpa_connector.py` to call `fetch_batch`**

Modify imports near the top of `scripts/rpa_connector.py`:

```python
try:
    from yuntu_batch import ConnectorInvoker, fetch_batch
except ImportError:
    ConnectorInvoker = None
    fetch_batch = None
```

Modify `fetch_analysis` to remain available for old tests. Add a new wrapper:

```python
def fetch_batch_analysis(
    shop_id,
    raw_list_params,
    raw_detail_params,
    *,
    target_top_n=10,
    candidate_top_n=None,
    output_dir,
):
    if fetch_batch is None or ConnectorInvoker is None:
        raise RpaConnectorError("batch fetch support is unavailable")
    list_params = validate_list_business_params(raw_list_params)
    detail_date_params = _validate_detail_date_params(raw_detail_params)
    detail_date_range = {
        key: value for key, value in detail_date_params.items() if key != "material_id"
    }
    target_top_n = _validate_top_n(target_top_n)
    candidate_top_n = target_top_n * 3 if candidate_top_n is None else _validate_top_n(candidate_top_n)
    return fetch_batch(
        shop_id=shop_id,
        list_params=list_params,
        detail_date_params=detail_date_range,
        target_top_n=target_top_n,
        candidate_top_n=candidate_top_n,
        output_dir=output_dir,
        invoker=ConnectorInvoker(
            lambda sid, params: invoke_list(sid, params),
            lambda sid, params: invoke_detail(sid, params),
        ),
    )
```

Update `_parser()` fetch arguments:

```python
fetch_parser.add_argument("--target-top-n", type=_positive_int_argument)
fetch_parser.add_argument("--candidate-top-n", type=_positive_int_argument)
```

Update `main()` fetch branch:

```python
target_top_n = args.target_top_n or args.top_n
status = fetch_batch_analysis(
    args.shop_id,
    _list_params_from_args(args),
    {
        "date_range_type": args.detail_date_range_type,
        "custom_start_date": args.detail_custom_start_date,
        "custom_end_date": args.detail_custom_end_date,
    },
    target_top_n=target_top_n,
    candidate_top_n=args.candidate_top_n,
    output_dir=args.output_dir,
)
print(Path(args.output_dir) / "batch-manifest.json")
return status
```

- [ ] **Step 5: Run batch and connector regression tests**

Run:

```bash
python -m unittest tests/test_yuntu_batch.py tests/test_rpa_connector.py -v
```

Expected: PASS. Existing `fetch_analysis` unit tests remain green because the legacy function is preserved.

- [ ] **Step 6: Commit Task 3**

```bash
git add scripts/yuntu_batch.py scripts/rpa_connector.py tests/test_yuntu_batch.py
git commit -m "feat: add Yuntu batch fetch workflow"
```

## Task 4: Analysis Fact Pack Generation

**Files:**
- Create: `scripts/yuntu_analysis.py`
- Modify: `scripts/rpa_connector.py`
- Test: `tests/test_yuntu_analysis.py`

- [ ] **Step 1: Write failing tests for fact pack aggregation**

Add `tests/test_yuntu_analysis.py`:

```python
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "yuntu_analysis.py"


def load_module():
    spec = importlib.util.spec_from_file_location("yuntu_analysis", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class YuntuAnalysisTests(unittest.TestCase):
    def test_prepare_analysis_writes_fact_pack_and_prompt(self):
        analysis = load_module()
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "normalized" / "detail-records").mkdir(parents=True)
            (root / "batch-manifest.json").write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "filters": {"industry": "食品饮料"},
                        "selectedMaterials": [{"rank": 1, "material_id": "101", "detailRecordPath": "normalized/detail-records/101.json"}],
                        "rejectedMaterials": [{"rank": 2, "material_id": "202", "reason": "RpaIoError"}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (root / "normalized" / "list-records.json").write_text(
                json.dumps(
                    [
                        {
                            "material_id": "101",
                            "title": "高点击素材",
                            "rank": 1,
                            "metrics": {"ctr": 0.7, "cvr": 0.2},
                            "people_tags": ["都市银发"],
                            "material_tags": ["包装_独立包装"],
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (root / "normalized" / "detail-records" / "101.json").write_text(
                json.dumps(
                    {
                        "material_id": "101",
                        "high_points": [{"trend_name": "点击指数", "start_sec": 1, "end_sec": 2}],
                        "loss_points": [{"trend_name": "流失指数", "start_sec": 0, "end_sec": 1, "loss_percent": 0.5}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            status = analysis.prepare_analysis(input_dir=root, output_dir=root / "diagnostic-analysis")
            data = json.loads((root / "diagnostic-analysis" / "yuntu-analysis-data.json").read_text(encoding="utf-8"))
            prompt = (root / "diagnostic-analysis" / "yuntu-analysis-prompt.md").read_text(encoding="utf-8")

        self.assertEqual(status, 0)
        self.assertEqual(data["schemaVersion"], 1)
        self.assertEqual(data["filters"], {"industry": "食品饮料"})
        self.assertEqual(data["summaryMetrics"]["selectedCount"], 1)
        self.assertEqual(data["summaryMetrics"]["rejectedCount"], 1)
        self.assertEqual(data["audienceAggregations"]["都市银发"], 1)
        self.assertEqual(data["tagAggregations"]["包装_独立包装"], 1)
        self.assertIn("点击指数", data["trendHighlights"]["highPointNames"])
        self.assertIn("yuntu-ai-analysis.json", prompt)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and verify they fail because the module is missing**

Run:

```bash
python -m unittest tests/test_yuntu_analysis.py -v
```

Expected: FAIL or ERROR mentioning `scripts/yuntu_analysis.py` is missing.

- [ ] **Step 3: Implement `scripts/yuntu_analysis.py`**

Create `scripts/yuntu_analysis.py`:

```python
"""Build Yuntu analysis fact packs from normalized records."""

import json
from pathlib import Path

from rpa_io import write_json_atomically


class YuntuAnalysisError(RuntimeError):
    """Raised when analysis facts cannot be prepared."""


def _load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        raise YuntuAnalysisError(f"unable to read JSON {path}: {exc}") from exc


def _count_values(records, key):
    counts = {}
    for record in records:
        for value in record.get(key, []):
            counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _trend_highlights(details_by_id):
    high_names = []
    loss_names = []
    for detail in details_by_id.values():
        for point in detail.get("high_points", []):
            name = point.get("trend_name")
            if name and name not in high_names:
                high_names.append(name)
        for point in detail.get("loss_points", []):
            name = point.get("trend_name")
            if name and name not in loss_names:
                loss_names.append(name)
    return {"highPointNames": high_names, "lossPointNames": loss_names}


def _prompt_text():
    return (
        "# 云图行业内容榜单分析任务\n\n"
        "读取同目录的 `yuntu-analysis-data.json`，生成 `yuntu-ai-analysis.json`。\n\n"
        "输出必须包含：overallConclusion、rankingInsights、audienceInsights、tagInsights、"
        "trendInsights、materialAnalyses、creativePatterns、nextActions。\n\n"
        "所有结论必须引用素材 ID、指标、标签或秒级趋势作为证据。事实不足时写“数据不足以判断”。\n"
        "不得写执行过程、重跑、补位调度、代码状态或排障细节。\n"
    )


def prepare_analysis(*, input_dir, output_dir):
    root = Path(input_dir)
    output = Path(output_dir)
    manifest = _load_json(root / "batch-manifest.json")
    list_records = _load_json(root / "normalized" / "list-records.json")
    selected = manifest.get("selectedMaterials", [])
    rejected = manifest.get("rejectedMaterials", [])
    if not isinstance(selected, list) or not selected:
        raise YuntuAnalysisError("selectedMaterials must contain at least one material")

    list_by_id = {record.get("material_id"): record for record in list_records if isinstance(record, dict)}
    details_by_id = {}
    material_facts = []
    for item in selected:
        material_id = item.get("material_id")
        detail_path = item.get("detailRecordPath")
        if not material_id or not detail_path:
            raise YuntuAnalysisError("selected material is missing material_id or detailRecordPath")
        detail = _load_json(root / detail_path)
        details_by_id[material_id] = detail
        list_record = list_by_id.get(material_id, {})
        material_facts.append(
            {
                "material_id": material_id,
                "rank": item.get("rank"),
                "title": list_record.get("title", ""),
                "metrics": list_record.get("metrics", {}),
                "people_tags": list_record.get("people_tags", []),
                "material_tags": list_record.get("material_tags", []),
                "high_points": detail.get("high_points", []),
                "loss_points": detail.get("loss_points", []),
            }
        )

    fact_pack = {
        "schemaVersion": 1,
        "filters": manifest.get("filters", {}),
        "selectedMaterials": selected,
        "rejectedMaterials": rejected,
        "summaryMetrics": {
            "selectedCount": len(selected),
            "rejectedCount": len(rejected),
            "candidateCount": len(manifest.get("candidateMaterials", [])),
        },
        "audienceAggregations": _count_values(list_by_id.values(), "people_tags"),
        "tagAggregations": _count_values(list_by_id.values(), "material_tags"),
        "trendHighlights": _trend_highlights(details_by_id),
        "materialFacts": material_facts,
    }
    write_json_atomically(fact_pack, output / "yuntu-analysis-data.json")
    output.mkdir(parents=True, exist_ok=True)
    (output / "yuntu-analysis-prompt.md").write_text(_prompt_text(), encoding="utf-8")
    return 0
```

- [ ] **Step 4: Wire `prepare-analysis` into `scripts/rpa_connector.py`**

Add import:

```python
try:
    from yuntu_analysis import prepare_analysis
except ImportError:
    prepare_analysis = None
```

Add parser command in `_parser()`:

```python
prepare_parser = commands.add_parser("prepare-analysis", help="Prepare Yuntu analysis facts")
prepare_parser.add_argument("--input-dir", required=True)
prepare_parser.add_argument("--output-dir", required=True)
```

Add branch in `main()` before fetch:

```python
if args.command == "prepare-analysis":
    if prepare_analysis is None:
        raise RpaConnectorError("analysis preparation support is unavailable")
    return prepare_analysis(input_dir=args.input_dir, output_dir=args.output_dir)
```

- [ ] **Step 5: Run tests for Task 4**

Run:

```bash
python -m unittest tests/test_yuntu_analysis.py tests/test_rpa_connector.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit Task 4**

```bash
git add scripts/yuntu_analysis.py scripts/rpa_connector.py tests/test_yuntu_analysis.py
git commit -m "feat: prepare Yuntu analysis facts"
```

## Task 5: Report Rendering

**Files:**
- Create: `scripts/yuntu_report.py`
- Modify: `scripts/rpa_connector.py`
- Test: `tests/test_yuntu_report.py`

- [ ] **Step 1: Write failing tests for report validation and rendering**

Add `tests/test_yuntu_report.py`:

```python
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "yuntu_report.py"


def load_module():
    spec = importlib.util.spec_from_file_location("yuntu_report", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class YuntuReportTests(unittest.TestCase):
    def analysis_json(self):
        return {
            "overallConclusion": "本批次素材以价格钩子和独立包装卖点表现突出。",
            "rankingInsights": ["101 CTR 高于批次均值。"],
            "audienceInsights": ["都市银发标签出现 1 次。"],
            "tagInsights": ["包装_独立包装出现 1 次。"],
            "trendInsights": ["101 点击指数在 1-2 秒形成高点。"],
            "materialAnalyses": [{"material_id": "101", "summary": "首秒承接点击。"}],
            "creativePatterns": ["价格利益点前置。"],
            "nextActions": ["测试目标品牌礼盒装价格锚点表达。"],
        }

    def test_render_report_writes_data_markdown_and_html(self):
        report = load_module()
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            analysis_path = root / "diagnostic-analysis" / "yuntu-ai-analysis.json"
            analysis_path.parent.mkdir()
            analysis_path.write_text(json.dumps(self.analysis_json(), ensure_ascii=False), encoding="utf-8")
            status = report.render_report(
                analysis_json=analysis_path,
                output_dir=root / "final-report",
            )

            data = json.loads((root / "final-report" / "final-report-data.json").read_text(encoding="utf-8"))
            markdown = (root / "final-report" / "final-report.md").read_text(encoding="utf-8")
            html = (root / "final-report" / "final-report.html").read_text(encoding="utf-8")

        self.assertEqual(status, 0)
        self.assertEqual(data["status"], "complete")
        self.assertIn("行业榜单整体结论", markdown)
        self.assertIn("本批次素材以价格钩子", markdown)
        self.assertIn("<html", html)

    def test_render_report_rejects_missing_required_sections(self):
        report = load_module()
        with tempfile.TemporaryDirectory() as temporary_directory:
            analysis_path = Path(temporary_directory) / "analysis.json"
            analysis_path.write_text(json.dumps({"overallConclusion": "只有结论"}, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(report.YuntuReportError, "missing"):
                report.render_report(analysis_json=analysis_path, output_dir=Path(temporary_directory) / "report")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and verify they fail because the module is missing**

Run:

```bash
python -m unittest tests/test_yuntu_report.py -v
```

Expected: FAIL or ERROR mentioning `scripts/yuntu_report.py` is missing.

- [ ] **Step 3: Implement `scripts/yuntu_report.py`**

Create `scripts/yuntu_report.py`:

```python
"""Render final Yuntu analysis reports from model-authored JSON."""

import html
import json
from pathlib import Path

from rpa_io import write_json_atomically


class YuntuReportError(RuntimeError):
    """Raised when report inputs are invalid."""


REQUIRED_FIELDS = (
    "overallConclusion",
    "rankingInsights",
    "audienceInsights",
    "tagInsights",
    "trendInsights",
    "materialAnalyses",
    "creativePatterns",
    "nextActions",
)


SECTION_TITLES = (
    ("01｜行业榜单整体结论", "overallConclusion"),
    ("02｜Top 素材表现分层", "rankingInsights"),
    ("03｜人群与内容标签洞察", "audienceInsights"),
    ("04｜单素材秒级诊断", "materialAnalyses"),
    ("05｜高表现素材共性", "creativePatterns"),
    ("06｜目标品牌可借鉴创意方向", "tagInsights"),
    ("07｜下一轮素材建议", "nextActions"),
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
        raise YuntuReportError("analysis JSON is missing required fields: " + ", ".join(missing))
    return analysis


def _markdown_value(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, dict):
                text = item.get("summary") or item.get("body") or json.dumps(item, ensure_ascii=False, sort_keys=True)
            else:
                text = str(item)
            lines.append(f"- {text}")
        return "\n".join(lines)
    return json.dumps(value, ensure_ascii=False, indent=2)


def _render_markdown(analysis):
    lines = ["# 云图行业内容榜单分析报告", ""]
    for title, field in SECTION_TITLES:
        lines.extend([f"## {title}", "", _markdown_value(analysis[field]), ""])
    lines.extend(["## 附：秒级趋势洞察", "", _markdown_value(analysis["trendInsights"]), ""])
    return "\n".join(lines)


def _render_html(markdown):
    body = html.escape(markdown).replace("\n", "<br>\n")
    return "<!doctype html>\n<html lang=\"zh-CN\">\n<meta charset=\"utf-8\">\n<title>云图行业内容榜单分析报告</title>\n<body>\n" + body + "\n</body>\n</html>\n"


def render_report(*, analysis_json, output_dir):
    analysis = _load_analysis(analysis_json)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    data = {"status": "complete", "analysis": analysis}
    write_json_atomically(data, output / "final-report-data.json")
    markdown = _render_markdown(analysis)
    (output / "final-report.md").write_text(markdown, encoding="utf-8")
    (output / "final-report.html").write_text(_render_html(markdown), encoding="utf-8")
    return 0
```

- [ ] **Step 4: Wire `render-report` into `scripts/rpa_connector.py`**

Add import:

```python
try:
    from yuntu_report import render_report
except ImportError:
    render_report = None
```

Add parser command:

```python
report_parser = commands.add_parser("render-report", help="Render Yuntu final report")
report_parser.add_argument("--analysis-json", required=True)
report_parser.add_argument("--output-dir", required=True)
```

Add branch in `main()`:

```python
if args.command == "render-report":
    if render_report is None:
        raise RpaConnectorError("report rendering support is unavailable")
    return render_report(analysis_json=args.analysis_json, output_dir=args.output_dir)
```

- [ ] **Step 5: Run tests for Task 5**

Run:

```bash
python -m unittest tests/test_yuntu_report.py tests/test_rpa_connector.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit Task 5**

```bash
git add scripts/yuntu_report.py scripts/rpa_connector.py tests/test_yuntu_report.py
git commit -m "feat: render Yuntu analysis reports"
```

## Task 6: Skill Documentation and Contract Tests

**Files:**
- Modify: `SKILL.md`
- Modify: `agents/openai.yaml`
- Modify: `tests/test_skill_contract.py`

- [ ] **Step 1: Write failing contract tests for new workflow documentation**

Extend `tests/test_skill_contract.py` with:

```python
    def test_documents_csv_first_analysis_workflow(self):
        skill = self.read_skill()
        for phrase in (
            "files-envelope",
            "raw-csv/list.csv",
            "raw-csv/details/<material_id>.csv",
            "normalized/list-records.json",
            "normalized/detail-records/<material_id>.json",
            "batch-manifest.json",
            "prepare-analysis",
            "render-report",
            "yuntu-analysis-data.json",
            "yuntu-ai-analysis.json",
            "final-report.md",
        ):
            self.assertIn(phrase, skill)
        self.assertRegex(skill, r"(?s)CSV.{0,120}主路径")
        self.assertRegex(skill, r"(?s)分析.{0,120}normalized")
```

- [ ] **Step 2: Run contract test and verify it fails before docs are updated**

Run:

```bash
python -m unittest tests/test_skill_contract.py -v
```

Expected: FAIL in `test_documents_csv_first_analysis_workflow`.

- [ ] **Step 3: Update `SKILL.md` command and output documentation**

Modify `SKILL.md` to describe:

```markdown
## CSV 主路径与后续分析

RPA 大概率返回 `files-envelope`，脚本会校验 `success`、`code`、`result_type`、`status`、`failedInstances` 和 `files[0].fileUrl`，然后下载 CSV。`fileUrl` 只作为临时下载入口，不写入后续分析产物。

`fetch` 会写出：

- `raw-csv/list.csv`
- `raw-csv/details/<material_id>.csv`
- `normalized/list-records.json`
- `normalized/detail-records/<material_id>.json`
- `normalized/top-materials-rpa-ready.json`
- `batch-manifest.json`

分析阶段只读取 `normalized/`，不直接读取原始 CSV 或 RPA response。
```

Add command examples:

```bash
python yuntu-industry-content-rankings-analysis/scripts/rpa_connector.py fetch \
  --shop-id "<shop_id>" \
  --industry "食品饮料" \
  --time-range-type "LAST_7_DAYS" \
  --detail-date-range-type "LAST_7_DAYS" \
  --target-top-n 10 \
  --candidate-top-n 30 \
  --output-dir "RPA数据汇总/yuntu-rankings-analysis"
```

```bash
python yuntu-industry-content-rankings-analysis/scripts/rpa_connector.py prepare-analysis \
  --input-dir "RPA数据汇总/yuntu-rankings-analysis" \
  --output-dir "RPA数据汇总/yuntu-rankings-analysis/diagnostic-analysis"
```

```bash
python yuntu-industry-content-rankings-analysis/scripts/rpa_connector.py render-report \
  --analysis-json "RPA数据汇总/yuntu-rankings-analysis/diagnostic-analysis/yuntu-ai-analysis.json" \
  --output-dir "RPA数据汇总/yuntu-rankings-analysis/final-report"
```

- [ ] **Step 4: Run contract tests**

Run:

```bash
python -m unittest tests/test_skill_contract.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 6**

```bash
git add SKILL.md agents/openai.yaml tests/test_skill_contract.py
git commit -m "docs: document Yuntu analysis workflow"
```

## Task 7: Full Regression and Self-Test

**Files:**
- Modify only if regression reveals a defect in files already touched.

- [ ] **Step 1: Run the full test suite**

Run:

```bash
python -m unittest discover -s tests -v
```

Expected: PASS for all tests.

- [ ] **Step 2: Run CLI self-test**

Run:

```bash
python scripts/rpa_connector.py self-test
```

Expected output includes:

```text
self-test passed
```

- [ ] **Step 3: Check CLI help includes new commands**

Run:

```bash
python scripts/rpa_connector.py --help
python scripts/rpa_connector.py fetch --help
```

Expected:

- Root help lists `prepare-analysis` and `render-report`.
- Fetch help lists `--target-top-n` and `--candidate-top-n`.

- [ ] **Step 4: Inspect git status**

Run:

```bash
git status --short
```

Expected: clean working tree after all task commits.

## Self-Review

- Spec coverage: Tasks cover CSV files-envelope handling, raw CSV retention, normalized records, candidate replacement, batch manifest, fact pack, model analysis JSON expectations via prompt, report rendering, docs, and tests.
- Placeholder scan: Clean. Every task includes concrete files, commands, snippets, and expected results.
- Type consistency: Planned modules use `material_id`, `detailRecordPath`, `selectedMaterials`, `rejectedMaterials`, `cancelledMaterials`, `target_top_n`, and `candidate_top_n` consistently across tests and implementation snippets.
