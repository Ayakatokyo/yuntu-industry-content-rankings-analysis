"""Batch fetch orchestration for Yuntu rankings analysis."""

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timedelta
import json
from pathlib import Path
import time

from rpa_io import (
    download_file,
    parse_csv_records,
    unpack_gateway_result,
    write_json_atomically,
)
from yuntu_normalizer import normalize_detail_records, normalize_list_records
from yuntu_highlights import (
    details_missing_standard_highlights,
    generate_standard_highlights_for_detail,
    load_highlights_manifest,
    write_highlights_manifest,
)
import yuntu_run_state as run_state


class YuntuBatchError(RuntimeError):
    """Raised when a Yuntu batch cannot be started."""


DETAIL_WAVE_CONCURRENCY = 3
HIGHLIGHT_CONCURRENCY = 3
RANKING_RUN_ORDER = ("query", "previous_period", "industry")
SELECTION_GROUP_FIELDS = {
    "selectionGroupId": "id",
    "brandId": "brand_id",
    "brandName": "brand_name",
    "touchpointCode": "touchpoint_code",
    "touchpointName": "touchpoint_name",
}


class ConnectorInvoker:
    def __init__(self, invoke_list, invoke_detail):
        self._invoke_list = invoke_list
        self._invoke_detail = invoke_detail

    def invoke_list(self, shop_id, list_params):
        return self._invoke_list(shop_id, list_params)

    def invoke_detail(self, shop_id, detail_params):
        return self._invoke_detail(shop_id, detail_params)


def _parse_period_date(value):
    text = str(value or "")
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _iso_date_range(start, end):
    if not start or not end:
        return None
    return {"startDate": start.isoformat(), "endDate": end.isoformat()}


def _compact_date(value):
    return value.strftime("%Y%m%d")


def build_ranking_run_specs(list_params, *, resolved_date_range=None):
    """Build immutable query, previous-period, and industry list request specs."""
    if not isinstance(list_params, dict):
        raise YuntuBatchError("list_params must be an object")
    query_params = dict(list_params)
    start = end = None
    if query_params.get("time_range_type") == "CUSTOM":
        start = _parse_period_date(query_params.get("custom_start_date"))
        end = _parse_period_date(query_params.get("custom_end_date"))
    elif isinstance(resolved_date_range, dict):
        start = _parse_period_date(resolved_date_range.get("startDate"))
        end = _parse_period_date(resolved_date_range.get("endDate"))

    query_range = _iso_date_range(start, end)
    previous_params = None
    previous_range = None
    if start and end:
        period_days = (end - start).days + 1
        previous_end = start - timedelta(days=1)
        previous_start = previous_end - timedelta(days=period_days - 1)
        previous_params = {
            **query_params,
            "time_range_type": "CUSTOM",
            "custom_start_date": _compact_date(previous_start),
            "custom_end_date": _compact_date(previous_end),
        }
        previous_range = _iso_date_range(previous_start, previous_end)

    industry_params = {
        key: value
        for key, value in query_params.items()
        if key not in {"brand_scope_type", "brands"}
    }
    industry_params["brand_scope_type"] = "ALL_INDUSTRY"
    return {
        "query": {"params": query_params, "resolvedDateRange": query_range},
        "previous_period": {
            "params": previous_params,
            "resolvedDateRange": previous_range,
            "unavailableReason": (
                "query actual date range is unavailable; previous period cannot be derived"
                if previous_params is None
                else ""
            ),
        },
        "industry": {"params": industry_params, "resolvedDateRange": query_range},
    }


class FileDownloader:
    def download_file(self, file_url, target_path):
        return download_file(file_url, target_path)


def _elapsed(started_at):
    return round(time.monotonic() - started_at, 6)


def _validate_positive_int(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise YuntuBatchError(f"{name} must be a positive integer")
    return value


def _selection_group(record):
    group = record.get("selection_group")
    if not isinstance(group, dict):
        group = {}
    return {
        "id": group.get("id") or "default",
        "brand_id": group.get("brand_id") or "",
        "brand_name": group.get("brand_name") or "",
        "touchpoint_code": group.get("touchpoint_code") or "",
        "touchpoint_name": group.get("touchpoint_name") or "",
    }


def _candidate_materials_from_list(records, candidate_top_n):
    selected = []
    seen = set()
    for record in records:
        material_id = record["material_id"]
        if material_id in seen:
            continue
        group = _selection_group(record)
        group_count = sum(
            item["selectionGroupId"] == group["id"] for item in selected
        )
        if group_count >= candidate_top_n:
            continue
        seen.add(material_id)
        selected.append(
            {
                "rank": record["rank"],
                "material_id": material_id,
                "selectionGroupId": group["id"],
                "selectionGroup": group,
            }
        )
    return selected


def _manifest_material(item):
    return {
        "rank": item["rank"],
        "material_id": item["material_id"],
        **_selection_group_fields(item),
    }


def _selection_group_fields(item):
    """Return the durable manifest shape for an optional selection group."""
    group_id = item.get("selectionGroupId")
    if not group_id or group_id == "default":
        return {}
    group = item.get("selectionGroup")
    if isinstance(group, dict):
        return {
            field: group.get(key, "")
            for field, key in SELECTION_GROUP_FIELDS.items()
        }
    return {
        field: item.get(field, "")
        for field in SELECTION_GROUP_FIELDS
    }


def _expected_selection_group(item):
    fields = _selection_group_fields(item)
    if not fields:
        return None
    return {key: fields[field] for field, key in SELECTION_GROUP_FIELDS.items()}


def _detail_request(item, detail_date_params):
    return {
        "material_id": item["material_id"],
        **detail_date_params,
        **_selection_group_fields(item),
    }


def _target_satisfied(manifest):
    groups = manifest.get("selectionGroups")
    if not isinstance(groups, list) or not groups:
        return len(manifest.get("selectedMaterials", [])) >= manifest.get("targetTopN", 0)
    selected_by_group = {}
    for item in manifest.get("selectedMaterials", []):
        group_id = item.get("selectionGroupId", "default")
        selected_by_group[group_id] = selected_by_group.get(group_id, 0) + 1
    return all(
        selected_by_group.get(group.get("selectionGroupId"), 0)
        >= group.get("targetTopN", 0)
        for group in groups
    )


def _materialize_records(result, *, csv_path, json_path, downloader):
    unpacked = unpack_gateway_result(result)
    if unpacked.kind == "files":
        path = downloader.download_file(unpacked.file_url, csv_path)
        return parse_csv_records(path), str(path)
    write_json_atomically(unpacked.records, json_path)
    return unpacked.records, str(json_path)


def _new_manifest(
    *,
    list_params,
    detail_date_params,
    target_top_n,
    candidate_top_n,
    summary,
):
    return {
        "schemaVersion": 3,
        "runId": summary["runId"],
        "parameterFingerprint": summary["parameterFingerprint"],
        "collectionContract": summary["collectionContract"],
        "status": "running",
        "rankingRuns": {},
        "filters": list_params,
        "detailDateRange": detail_date_params,
        "targetTopN": target_top_n,
        "candidateTopN": candidate_top_n,
        "candidateMaterials": [],
        "selectionGroups": [],
        "submittedMaterials": [],
        "selectedMaterials": [],
        "rejectedMaterials": [],
        "unresolvedMaterials": [],
        "cancelledMaterials": [],
        "timingsSec": {},
    }


def _load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _open_or_new_manifest(
    *,
    manifest_path,
    list_params,
    detail_date_params,
    target_top_n,
    candidate_top_n,
    summary,
):
    if not manifest_path.is_file():
        return _new_manifest(
            list_params=list_params,
            detail_date_params=detail_date_params,
            target_top_n=target_top_n,
            candidate_top_n=candidate_top_n,
            summary=summary,
        )
    try:
        manifest = _load_json(manifest_path)
    except (OSError, ValueError) as exc:
        raise YuntuBatchError("existing batch manifest is unreadable") from exc
    if (
        manifest.get("filters") != list_params
        or manifest.get("detailDateRange") != detail_date_params
        or manifest.get("targetTopN") != target_top_n
        or manifest.get("candidateTopN") != candidate_top_n
    ):
        raise YuntuBatchError(
            "output directory belongs to a different collection contract; choose a new output directory"
        )
    manifest.update(
        {
            "schemaVersion": 3,
            "runId": summary["runId"],
            "parameterFingerprint": summary["parameterFingerprint"],
            "collectionContract": summary["collectionContract"],
            "status": "running",
        }
    )
    for key in (
        "rankingRuns",
        "candidateMaterials",
        "selectionGroups",
        "submittedMaterials",
        "selectedMaterials",
        "rejectedMaterials",
        "unresolvedMaterials",
        "cancelledMaterials",
    ):
        manifest.setdefault(key, [])
    manifest.setdefault("timingsSec", {})
    if not isinstance(manifest.get("rankingRuns"), dict):
        manifest["rankingRuns"] = {}
    return manifest


def _detail_source_path(root, material_id):
    csv_path = root / "raw-csv" / "details" / f"{material_id}.csv"
    json_path = root / "raw-json" / "details" / f"{material_id}.json"
    if csv_path.is_file():
        return _relative(root, csv_path)
    if json_path.is_file():
        return _relative(root, json_path)
    return None


def _restore_persisted_details(root, manifest, candidates):
    """Rebuild successful manifest entries from durable normalized detail files."""
    candidate_by_id = {item["material_id"]: item for item in candidates}
    existing = {
        item.get("material_id"): item
        for item in manifest.get("selectedMaterials", [])
        if isinstance(item, dict) and isinstance(item.get("material_id"), str)
    }
    restored = []
    detail_dir = root / "normalized" / "detail-records"
    for material_id, item in candidate_by_id.items():
        detail_path = detail_dir / f"{material_id}.json"
        if not detail_path.is_file():
            continue
        try:
            detail = _load_json(detail_path)
        except (OSError, ValueError):
            continue
        if detail.get("material_id") != material_id:
            continue
        previous = existing.get(material_id, {})
        restored.append(
            {
                **_manifest_material(item),
                "listRecordPath": "normalized/list-records.json",
                "detailRecordPath": _relative(root, detail_path),
                "rawDetailPath": previous.get("rawDetailPath")
                or _detail_source_path(root, material_id),
                "timingsSec": previous.get("timingsSec", {}),
            }
        )
    manifest["selectedMaterials"] = sorted(restored, key=lambda entry: entry["rank"])


def _mark_unresolved_submissions(manifest, candidates):
    """Keep interrupted detail requests visible without silently retrying them."""
    candidate_by_id = {item["material_id"]: item for item in candidates}
    terminal_ids = _selected_ids(manifest)
    for key in ("rejectedMaterials", "cancelledMaterials", "unresolvedMaterials"):
        terminal_ids.update(
            item.get("material_id")
            for item in manifest.get(key, [])
            if isinstance(item, dict) and isinstance(item.get("material_id"), str)
        )
    unresolved = list(manifest.get("unresolvedMaterials", []))
    for submitted in manifest.get("submittedMaterials", []):
        if not isinstance(submitted, dict):
            continue
        material_id = submitted.get("material_id")
        item = candidate_by_id.get(material_id)
        if item is None or material_id in terminal_ids:
            continue
        unresolved.append(
            {
                **_manifest_material(item),
                "reason": "interrupted_before_persistence",
            }
        )
        terminal_ids.add(material_id)
    manifest["unresolvedMaterials"] = unresolved


def _has_existing_collection_artifacts(root):
    return any(
        path.exists()
        for path in (
            root / run_state.RUN_SUMMARY_NAME,
            root / "batch-manifest.json",
            root / "raw-csv" / "list.csv",
            root / "raw-json" / "list-response.json",
            root / "normalized" / "list-records.json",
        )
    )


def _open_collection_summary(root, contract):
    summary_path = root / run_state.RUN_SUMMARY_NAME
    if _has_existing_collection_artifacts(root):
        if not summary_path.is_file():
            raise YuntuBatchError(
                "output directory contains an unverifiable existing batch; choose a new output directory"
            )
        try:
            summary = run_state.load_run_state(summary_path)
        except run_state.YuntuRunStateError as exc:
            raise YuntuBatchError(
                "output directory contains an unverifiable existing batch; choose a new output directory"
            ) from exc
        if not run_state.collection_contract_matches(summary, contract):
            raise YuntuBatchError(
                "output directory belongs to a different collection contract; choose a new output directory"
            )
        return summary
    summary = run_state.new_collection_summary(contract)
    run_state.save_run_state(summary, summary_path)
    return summary


def _save_summary(root, summary):
    run_state.save_run_state(summary, root / run_state.RUN_SUMMARY_NAME)


def _record_artifact(summary, root, key, path, source):
    try:
        run_state.register_artifact(summary, root, key, path, source)
    except run_state.YuntuRunStateError:
        # State remains useful even when an optional raw artifact is not available.
        pass


def _sync_stage_counts(summary, manifest, root):
    details_dir = root / "normalized" / "detail-records"
    persisted_count = len(list(details_dir.glob("*.json"))) if details_dir.is_dir() else 0
    counts = summary["stageCounts"]
    counts.update(
        {
            "candidateCount": len(manifest.get("candidateMaterials", [])),
            "detailSubmittedCount": len(manifest.get("submittedMaterials", [])),
            "detailRecordsPersistedCount": persisted_count,
            "selectedCount": len(manifest.get("selectedMaterials", [])),
            "rejectedCount": len(manifest.get("rejectedMaterials", [])),
            "unresolvedCount": len(manifest.get("unresolvedMaterials", [])),
            "cancelledCount": len(manifest.get("cancelledMaterials", [])),
        }
    )


def _brand_tokens(value):
    return {
        part.strip().casefold()
        for part in str(value or "").split("/")
        if part.strip()
    }


def _display_date(value):
    text = str(value or "")
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text


def _validate_list_context(list_records, list_params):
    if not list_records:
        return {"valid": False, "issues": ["list records are empty"], "observed": {}}
    context = list_records[0].get("list_context")
    context = context if isinstance(context, dict) else {}
    issues = []
    if "industry" in list_params and context.get("industry") != list_params["industry"]:
        issues.append("industry")
    if list_params.get("time_range_type") == "CUSTOM":
        expected = (
            f"{_display_date(list_params['custom_start_date'])} ~ "
            f"{_display_date(list_params['custom_end_date'])}"
        )
        if context.get("custom_date_range") != expected:
            issues.append("custom_date_range")
    if list_params.get("brand_scope_type") == "SPECIFIED_BRANDS":
        if context.get("brand_scope") not in {"指定品牌", "SPECIFIED_BRANDS"}:
            issues.append("brand_scope")
        actual_brands = context.get("brands")
        if not isinstance(actual_brands, list):
            actual_brands = []
        actual_tokens = [_brand_tokens(brand) for brand in actual_brands]
        for brand in list_params.get("brands", []):
            if not any(_brand_tokens(brand) & tokens for tokens in actual_tokens):
                issues.append("brands")
                break
    if "ranking_limit_type" in list_params:
        expected_labels = {
            "EXPOSURE_TOP1000": {"曝光量TOP1000", "EXPOSURE_TOP1000"},
            "CTR_TOP1000": {"点击率TOP1000", "CTR_TOP1000"},
            "INTERACTION_RATE_TOP1000": {"互动率TOP1000", "INTERACTION_RATE_TOP1000"},
            "COMPLETION_RATE_TOP1000": {"完播率TOP1000", "COMPLETION_RATE_TOP1000"},
        }
        if context.get("ranking_limit") not in expected_labels[list_params["ranking_limit_type"]]:
            issues.append("ranking_limit")
    return {"valid": not issues, "issues": issues, "observed": context}


def _reusable_list_artifact(root, list_params, detail_date_params):
    """Return a completed list CSV from the same run, if one is available."""
    manifest_path = root / "batch-manifest.json"
    list_path = root / "raw-csv" / "list.csv"
    if not manifest_path.is_file() or not list_path.is_file() or not list_path.stat().st_size:
        return None
    try:
        previous = _load_json(manifest_path)
    except (OSError, ValueError):
        return None
    if (
        previous.get("filters") != list_params
        or previous.get("detailDateRange") != detail_date_params
    ):
        return None
    return list_path


def _ranking_list_paths(root, run_key):
    if run_key == "query":
        return (
            root / "raw-csv" / "list.csv",
            root / "raw-json" / "list-response.json",
            root / "normalized" / "list-records.json",
        )
    suffix = "previous-period" if run_key == "previous_period" else "industry"
    return (
        root / "raw-csv" / f"list-{suffix}.csv",
        root / "raw-json" / f"list-response-{suffix}.json",
        root / "normalized" / f"list-records-{suffix}.json",
    )


def _ranking_run_snapshot(*, root, run_key, spec, status="pending"):
    raw_csv, raw_json, normalized = _ranking_list_paths(root, run_key)
    return {
        "runKey": run_key,
        "requestParams": spec.get("params"),
        "actualDateRange": spec.get("resolvedDateRange"),
        "status": status,
        "rawPath": _relative(root, raw_csv),
        "rawJsonPath": _relative(root, raw_json),
        "normalizedPath": _relative(root, normalized),
        "sampleCount": 0,
        "contextVerification": {"valid": False, "issues": [], "observed": {}},
    }


def _invoke_ranking_result(*, run_key, shop_id, spec, invoker):
    """Run only one ranking gateway request in a worker thread."""
    started = time.monotonic()
    try:
        return {
            "runKey": run_key,
            "result": invoker.invoke_list(shop_id, spec["params"]),
            "duration": _elapsed(started),
            "error": None,
        }
    except Exception as exc:
        return {
            "runKey": run_key,
            "result": None,
            "duration": _elapsed(started),
            "error": exc,
        }


def _persist_ranking_response(
    *, root, manifest, summary, run_key, spec, response, downloader
):
    """Materialize and normalize one worker response on the main thread."""
    entry = manifest["rankingRuns"][run_key]
    if response["error"] is not None:
        entry.update(
            {
                "status": "failed",
                "error": str(response["error"]),
                "timingsSec": {"listFetchSec": response["duration"]},
            }
        )
        return None, entry

    raw_csv, raw_json, normalized_path = _ranking_list_paths(root, run_key)
    try:
        raw_list, list_source = _materialize_records(
            response["result"],
            csv_path=raw_csv,
            json_path=raw_json,
            downloader=downloader,
        )
        list_records = normalize_list_records(
            raw_list, source_path=_relative(root, list_source)
        )
        write_json_atomically(list_records, normalized_path)
        verification = _validate_list_context(list_records, spec["params"])
        entry.update(
            {
                "status": "success" if verification["valid"] else "context_mismatch",
                "sampleCount": len(list_records),
                "contextVerification": verification,
                "actualDateRange": _actual_date_range_from_records(list_records)
                or spec.get("resolvedDateRange"),
                "timingsSec": {"listFetchSec": response["duration"]},
            }
        )
        _record_artifact(
            summary,
            root,
            f"rankingList:{run_key}",
            normalized_path,
            f"normalized_ranking_{run_key}",
        )
        return list_records, entry
    except Exception as exc:
        entry.update({"status": "failed", "error": str(exc)})
        return None, entry


def _reusable_ranking_records(root, manifest, run_key):
    """Return a verified normalized ranking list from a previous checkpoint."""
    entry = manifest.get("rankingRuns", {}).get(run_key)
    if not isinstance(entry, dict) or entry.get("status") != "success":
        return None
    relative_path = entry.get("normalizedPath")
    if not isinstance(relative_path, str) or not relative_path:
        return None
    path = root / relative_path
    try:
        records = _load_json(path)
    except (OSError, ValueError):
        return None
    if not isinstance(records, list) or not records:
        return None
    return records


def _persist_ranking_run(
    *, root, manifest, summary, run_key, shop_id, spec, invoker, downloader
):
    entry = _ranking_run_snapshot(root=root, run_key=run_key, spec=spec)
    manifest["rankingRuns"][run_key] = entry
    summary["rankingRuns"] = manifest["rankingRuns"]
    summary["stages"]["list"].setdefault("runs", {})[run_key] = entry
    _save_summary(root, summary)
    response = _invoke_ranking_result(
        run_key=run_key, shop_id=shop_id, spec=spec, invoker=invoker
    )
    return _persist_ranking_response(
        root=root,
        manifest=manifest,
        summary=summary,
        run_key=run_key,
        spec=spec,
        response=response,
        downloader=downloader,
    )


def _actual_date_range_from_records(records):
    if not records:
        return None
    context = records[0].get("list_context", {})
    if not isinstance(context, dict):
        return None
    start = _parse_period_date(context.get("actual_start_date"))
    end = _parse_period_date(context.get("actual_end_date"))
    return _iso_date_range(start, end)


def _selected_ids(manifest):
    return {item["material_id"] for item in manifest.get("selectedMaterials", [])}


def _refresh_ready_materials(root, manifest):
    list_records = _load_json(root / "normalized" / "list-records.json")
    list_by_id = {
        record["material_id"]: record
        for record in list_records
        if isinstance(record, dict) and "material_id" in record
    }
    selected_materials = sorted(
        manifest.get("selectedMaterials", []), key=lambda item: item.get("rank", 0)
    )
    ready_materials = [
        list_by_id[item["material_id"]]
        for item in selected_materials
        if item["material_id"] in list_by_id
    ]
    write_json_atomically(
        {"materials": ready_materials},
        root / "normalized" / "top-materials-rpa-ready.json",
    )


def _finalize_details(
    root,
    manifest,
    summary,
    manifest_path,
    *,
    incomplete_status="partial",
    require_no_unresolved=True,
):
    """Write the shared collection handoff after fetch or either retry path."""
    _refresh_ready_materials(root, manifest)
    succeeded = (
        not manifest.get("rejectedMaterials")
        and (not require_no_unresolved or not manifest.get("unresolvedMaterials"))
        and _target_satisfied(manifest)
        and (
            not manifest.get("rankingRuns")
            or all(
                isinstance(run, dict) and run.get("status") == "success"
                for run in manifest["rankingRuns"].values()
            )
        )
    )
    manifest["status"] = "success" if succeeded else incomplete_status
    summary["status"] = manifest["status"]
    summary["stages"]["details"]["requestStatus"] = (
        "completed" if succeeded else "partial"
    )
    _sync_stage_counts(summary, manifest, root)
    write_json_atomically(manifest, manifest_path)
    _save_summary(root, summary)
    return 0 if succeeded else 1


def _invoke_detail_result(*, item, shop_id, detail_date_params, invoker):
    """Run only the gateway call in a worker; the scheduler owns all writes."""
    started = time.monotonic()
    try:
        return {
            "item": item,
            "result": invoker.invoke_detail(
                shop_id, _detail_request(item, detail_date_params)
            ),
            "started": started,
            "error": None,
        }
    except Exception as exc:
        return {"item": item, "result": None, "started": started, "error": exc}


def _persist_detail(*, root, summary, item, gateway_result, downloader, detail_fetch_sec):
    """Normalize a successful detail response and build its durable manifest entry."""
    material_id = item["material_id"]
    raw_detail, detail_source = _materialize_records(
        gateway_result,
        csv_path=root / "raw-csv" / "details" / f"{material_id}.csv",
        json_path=root / "raw-json" / "details" / f"{material_id}.json",
        downloader=downloader,
    )
    detail_record = normalize_detail_records(
        raw_detail,
        material_id=material_id,
        source_path=_relative(root, detail_source),
        expected_selection_group=_expected_selection_group(item),
    )
    detail_output = root / "normalized" / "detail-records" / f"{material_id}.json"
    write_json_atomically(detail_record, detail_output)
    _record_artifact(
        summary,
        root,
        f"detailRecord:{material_id}",
        detail_output,
        "normalized_detail",
    )
    return detail_record, {
        **_manifest_material(item),
        "listRecordPath": "normalized/list-records.json",
        "detailRecordPath": _relative(root, detail_output),
        "rawDetailPath": _relative(root, detail_source),
        "timingsSec": {"detailFetchSec": detail_fetch_sec},
    }


def _generate_highlight_result(detail, root):
    """Run a material's video download and frame extraction in a worker."""
    started = time.monotonic()
    try:
        return {
            "material_id": detail["material_id"],
            "frames": generate_standard_highlights_for_detail(detail, root),
            "duration": _elapsed(started),
            "error": None,
        }
    except Exception as exc:
        return {
            "material_id": detail["material_id"],
            "frames": [],
            "duration": _elapsed(started),
            "error": exc,
        }


def _next_detail_wave(
    candidates,
    next_index,
    *,
    selected_ids,
    rejected_ids,
    unresolved_ids,
    selected_by_group,
    target_top_n,
    manifest,
):
    """Select the next bounded wave while preserving original candidate order."""
    wave = []
    known_ids = selected_ids | rejected_ids | unresolved_ids
    remaining_required = sum(
        max(
            group.get("targetTopN", target_top_n)
            - selected_by_group.get(group["selectionGroupId"], 0),
            0,
        )
        for group in manifest.get("selectionGroups", [])
    )
    wave_limit = min(DETAIL_WAVE_CONCURRENCY, remaining_required)
    if wave_limit == 0:
        while next_index < len(candidates):
            item = candidates[next_index]
            next_index += 1
            material_id = item["material_id"]
            group_id = item["selectionGroupId"]
            if material_id in known_ids:
                continue
            if selected_by_group.get(group_id, 0) >= target_top_n:
                manifest["cancelledMaterials"].append(
                    {**_manifest_material(item), "reason": "target_satisfied"}
                )
        return wave, next_index
    while next_index < len(candidates) and len(wave) < wave_limit:
        item = candidates[next_index]
        next_index += 1
        material_id = item["material_id"]
        group_id = item["selectionGroupId"]
        if material_id in known_ids:
            continue
        if selected_by_group.get(group_id, 0) >= target_top_n:
            manifest["cancelledMaterials"].append(
                {**_manifest_material(item), "reason": "target_satisfied"}
            )
            known_ids.add(material_id)
            continue
        wave.append(item)
        known_ids.add(material_id)
    return wave, next_index


def _selected_entry(manifest, material_id):
    return next(
        (
            item
            for item in manifest["selectedMaterials"]
            if item.get("material_id") == material_id
        ),
        None,
    )


def fetch_batch(
    *,
    shop_id,
    list_params,
    detail_date_params,
    target_top_n,
    candidate_top_n,
    output_dir,
    invoker,
    downloader=None,
):
    target_top_n = _validate_positive_int(target_top_n, "target_top_n")
    candidate_top_n = _validate_positive_int(candidate_top_n, "candidate_top_n")
    if candidate_top_n < target_top_n:
        raise YuntuBatchError("candidate_top_n cannot be smaller than target_top_n")
    if not isinstance(shop_id, str) or not shop_id.strip():
        raise YuntuBatchError("shop_id is required")
    downloader = FileDownloader() if downloader is None else downloader
    root = Path(output_dir)
    manifest_path = root / "batch-manifest.json"
    contract = run_state.collection_contract(
        shop_id=shop_id,
        list_params=list_params,
        detail_date_params=detail_date_params,
        target_top_n=target_top_n,
        candidate_top_n=candidate_top_n,
    )
    try:
        summary = _open_collection_summary(root, contract)
    except run_state.YuntuRunStateError as exc:
        raise YuntuBatchError(str(exc)) from exc
    manifest = _open_or_new_manifest(
        manifest_path=manifest_path,
        list_params=list_params,
        detail_date_params=detail_date_params,
        target_top_n=target_top_n,
        candidate_top_n=candidate_top_n,
        summary=summary,
    )
    write_json_atomically(manifest, manifest_path)

    started = time.monotonic()
    legacy_single_run = (
        "time_range_type" not in list_params
        or
        summary.get("schemaVersion", 0) < 3
        and _reusable_list_artifact(root, list_params, detail_date_params) is not None
    )
    if legacy_single_run:
        try:
            reusable_list = _reusable_list_artifact(root, list_params, detail_date_params)
            if reusable_list is not None:
                raw_list = parse_csv_records(reusable_list)
                list_source = reusable_list
                request_status = "reused"
            else:
                raw_list, list_source = _materialize_records(
                    invoker.invoke_list(shop_id, list_params),
                    csv_path=root / "raw-csv" / "list.csv",
                    json_path=root / "raw-json" / "list-response.json",
                    downloader=downloader,
                )
                request_status = "requested"
            list_records = normalize_list_records(
                raw_list, source_path=_relative(root, list_source)
            )
            write_json_atomically(list_records, root / "normalized" / "list-records.json")
            context_verification = _validate_list_context(list_records, list_params)
            summary["stages"]["list"].update(
                {
                    "requestStatus": request_status,
                    "normalized": True,
                    "contextVerified": context_verification["valid"],
                    "contextIssues": context_verification["issues"],
                    "observedContext": context_verification["observed"],
                }
            )
            if not context_verification["valid"]:
                manifest["status"] = "list_context_mismatch"
                manifest["error"] = "list context does not match requested filters: " + ", ".join(
                    context_verification["issues"]
                )
                summary["status"] = manifest["status"]
                _sync_stage_counts(summary, manifest, root)
                write_json_atomically(manifest, manifest_path)
                _save_summary(root, summary)
                return 1
        except Exception as exc:
            manifest["status"] = "list_failed"
            manifest["error"] = str(exc)
            summary["status"] = "list_failed"
            summary["stages"]["list"]["requestStatus"] = "failed"
            _sync_stage_counts(summary, manifest, root)
            write_json_atomically(manifest, manifest_path)
            _save_summary(root, summary)
            return 1
    else:
        specs = build_ranking_run_specs(list_params)
        ranking_records = {}
        existing_ranking_runs = manifest.get("rankingRuns", {})
        manifest["rankingRuns"] = {}
        pending_specs = {}
        reused_records = {}
        for run_key in RANKING_RUN_ORDER:
            spec = specs[run_key]
            reusable = _reusable_ranking_records(
                root, {"rankingRuns": existing_ranking_runs}, run_key
            )
            if reusable is not None:
                entry = dict(existing_ranking_runs[run_key])
                entry["requestStatus"] = "reused"
                manifest["rankingRuns"][run_key] = entry
                reused_records[run_key] = reusable
            elif not spec.get("params"):
                entry = _ranking_run_snapshot(
                    root=root, run_key=run_key, spec=spec, status="unavailable"
                )
                entry["error"] = spec.get("unavailableReason") or "actual date range unavailable"
                manifest["rankingRuns"][run_key] = entry
            else:
                entry = _ranking_run_snapshot(
                    root=root, run_key=run_key, spec=spec, status="running"
                )
                entry["requestStatus"] = "requested"
                manifest["rankingRuns"][run_key] = entry
                pending_specs[run_key] = spec

        summary["rankingRuns"] = manifest["rankingRuns"]
        summary["stages"]["list"]["runs"] = manifest["rankingRuns"]
        write_json_atomically(manifest, manifest_path)
        _save_summary(root, summary)

        def persist_ranking_result(run_key, spec, response):
            records, entry = _persist_ranking_response(
                root=root,
                manifest=manifest,
                summary=summary,
                run_key=run_key,
                spec=spec,
                response=response,
                downloader=downloader,
            )
            if records is not None and entry["status"] == "success":
                ranking_records[run_key] = records
            write_json_atomically(manifest, manifest_path)
            _save_summary(root, summary)
            return records, entry

        for run_key, records in reused_records.items():
            ranking_records[run_key] = records

        # Relative periods cannot be derived until the query response exposes
        # its actual closed date range. Query and industry still run together;
        # the previous-period request is submitted as soon as that range is
        # available, without moving any persistence into a worker.
        if (
            not specs["previous_period"].get("params")
            and "query" in reused_records
            and manifest["rankingRuns"]["query"].get("actualDateRange")
        ):
            specs = build_ranking_run_specs(
                list_params,
                resolved_date_range=manifest["rankingRuns"]["query"]["actualDateRange"],
            )
            previous_spec = specs["previous_period"]
            entry = _ranking_run_snapshot(
                root=root, run_key="previous_period", spec=previous_spec, status="running"
            )
            entry["requestStatus"] = "requested"
            manifest["rankingRuns"]["previous_period"] = entry
            pending_specs["previous_period"] = previous_spec

        with ThreadPoolExecutor(max_workers=3) as ranking_executor:
            pending = {
                ranking_executor.submit(
                    _invoke_ranking_result,
                    run_key=run_key,
                    shop_id=shop_id,
                    spec=spec,
                    invoker=invoker,
                ): run_key
                for run_key, spec in pending_specs.items()
            }
            while pending:
                done, _ = wait(set(pending), return_when=FIRST_COMPLETED)
                for future in sorted(
                    done, key=lambda item: RANKING_RUN_ORDER.index(pending[item])
                ):
                    run_key = pending.pop(future)
                    response = future.result()
                    records, entry = persist_ranking_result(
                        run_key, pending_specs[run_key], response
                    )
                    if (
                        run_key == "query"
                        and records is not None
                        and entry["status"] == "success"
                        and not specs["previous_period"].get("params")
                    ):
                        query_range = entry.get("actualDateRange")
                        if query_range:
                            specs = build_ranking_run_specs(
                                list_params, resolved_date_range=query_range
                            )
                            previous_spec = specs["previous_period"]
                            previous_entry = _ranking_run_snapshot(
                                root=root,
                                run_key="previous_period",
                                spec=previous_spec,
                                status="running",
                            )
                            previous_entry["requestStatus"] = "requested"
                            manifest["rankingRuns"]["previous_period"] = previous_entry
                            pending_specs["previous_period"] = previous_spec
                            pending[
                                ranking_executor.submit(
                                    _invoke_ranking_result,
                                    run_key="previous_period",
                                    shop_id=shop_id,
                                    spec=previous_spec,
                                    invoker=invoker,
                                )
                            ] = "previous_period"

        list_records = ranking_records.get("query")
        query_entry = manifest["rankingRuns"]["query"]
        if list_records is None or query_entry["status"] != "success":
            manifest["status"] = (
                "list_context_mismatch"
                if query_entry["status"] == "context_mismatch"
                else "list_failed"
            )
            manifest["error"] = query_entry.get("error") or (
                "query list context does not match requested filters"
            )
            manifest["timingsSec"]["totalSec"] = _elapsed(started)
            summary["status"] = manifest["status"]
            summary["stages"]["list"]["requestStatus"] = "failed"
            _sync_stage_counts(summary, manifest, root)
            write_json_atomically(manifest, manifest_path)
            _save_summary(root, summary)
            return 1
        summary["stages"]["list"].update(
            {
                "requestStatus": "completed"
                if all(
                    item.get("status") == "success"
                    for item in manifest["rankingRuns"].values()
                )
                else "partial",
                "normalized": True,
                "contextVerified": True,
                "runs": manifest["rankingRuns"],
            }
        )
        _save_summary(root, summary)

    candidates = _candidate_materials_from_list(list_records, candidate_top_n)
    manifest["candidateMaterials"] = [_manifest_material(item) for item in candidates]
    groups = {}
    for item in candidates:
        group = groups.setdefault(
            item["selectionGroupId"],
            {
                "selectionGroupId": item["selectionGroupId"],
                "brandId": item["selectionGroup"]["brand_id"],
                "brandName": item["selectionGroup"]["brand_name"],
                "touchpointCode": item["selectionGroup"]["touchpoint_code"],
                "touchpointName": item["selectionGroup"]["touchpoint_name"],
                "targetTopN": target_top_n,
                "candidateCount": 0,
            },
        )
        group["candidateCount"] += 1
    manifest["selectionGroups"] = list(groups.values())
    _restore_persisted_details(root, manifest, candidates)
    _mark_unresolved_submissions(manifest, candidates)
    detail_requests = [
        _detail_request(item, detail_date_params)
        for item in candidates
    ]
    detail_request_path = root / "normalized" / "detail-request-params.json"
    write_json_atomically(detail_requests, detail_request_path)
    manifest["detailRequestPath"] = _relative(root, detail_request_path)
    _record_artifact(summary, root, "detailRequests", detail_request_path, "detail_request_params")
    summary["stages"]["details"]["requestStatus"] = "running"
    _sync_stage_counts(summary, manifest, root)
    _save_summary(root, summary)
    selected_by_group = {}
    selected_ids = _selected_ids(manifest)
    rejected_ids = {
        item.get("material_id")
        for item in manifest["rejectedMaterials"]
        if isinstance(item, dict) and isinstance(item.get("material_id"), str)
    }
    unresolved_ids = {
        item.get("material_id")
        for item in manifest["unresolvedMaterials"]
        if isinstance(item, dict) and isinstance(item.get("material_id"), str)
    }
    for selected in manifest["selectedMaterials"]:
        group_id = selected.get("selectionGroupId", "default")
        selected_by_group[group_id] = selected_by_group.get(group_id, 0) + 1
    frames_by_material = load_highlights_manifest(root)
    pending_details = {}
    pending_highlights = {}
    next_index = 0

    def checkpoint():
        write_highlights_manifest(root, frames_by_material)
        detail_stage = summary["stages"]["details"]
        detail_stage["postprocessSubmittedCount"] = sum(
            item.get("postprocessStatus") in {"running", "succeeded", "failed", "reused"}
            for item in manifest["selectedMaterials"]
        )
        detail_stage["postprocessSucceededCount"] = sum(
            item.get("postprocessStatus") in {"succeeded", "reused"}
            for item in manifest["selectedMaterials"]
        )
        detail_stage["postprocessFailedCount"] = sum(
            item.get("postprocessStatus") == "failed"
            for item in manifest["selectedMaterials"]
        )
        _sync_stage_counts(summary, manifest, root)
        write_json_atomically(manifest, manifest_path)
        _save_summary(root, summary)

    def submit_highlight(executor, detail):
        material_id = detail["material_id"]
        entry = _selected_entry(manifest, material_id)
        if entry is not None:
            entry["postprocessStatus"] = "running"
        future = executor.submit(_generate_highlight_result, detail, root)
        pending_highlights[future] = material_id

    # Resume never repeats a persisted detail. Missing frames are a separate job.
    restored_details = []
    for selected in manifest["selectedMaterials"]:
        path = selected.get("detailRecordPath")
        if not isinstance(path, str):
            continue
        try:
            restored_details.append(_load_json(root / path))
        except (OSError, ValueError):
            continue

    with ThreadPoolExecutor(max_workers=DETAIL_WAVE_CONCURRENCY) as detail_executor, ThreadPoolExecutor(
        max_workers=HIGHLIGHT_CONCURRENCY
    ) as highlight_executor:
        for detail in details_missing_standard_highlights(restored_details, root):
            submit_highlight(highlight_executor, detail)

        while True:
            if not pending_details and not pending_highlights:
                wave, next_index = _next_detail_wave(
                    candidates,
                    next_index,
                    selected_ids=selected_ids,
                    rejected_ids=rejected_ids,
                    unresolved_ids=unresolved_ids,
                    selected_by_group=selected_by_group,
                    target_top_n=target_top_n,
                    manifest=manifest,
                )
                if not wave:
                    break
                for item in wave:
                    manifest["submittedMaterials"].append(_manifest_material(item))
                    future = detail_executor.submit(
                        _invoke_detail_result,
                        item=item,
                        shop_id=shop_id,
                        detail_date_params=detail_date_params,
                        invoker=invoker,
                    )
                    pending_details[future] = item["material_id"]
                checkpoint()

            done, _ = wait(
                set(pending_details) | set(pending_highlights),
                return_when=FIRST_COMPLETED,
            )
            for future in done:
                if future in pending_details:
                    result = future.result()
                    pending_details.pop(future)
                    item = result["item"]
                    material_id = item["material_id"]
                    try:
                        if result["error"] is not None:
                            raise result["error"]
                        detail_record, selected_entry = _persist_detail(
                            root=root,
                            summary=summary,
                            item=item,
                            gateway_result=result["result"],
                            downloader=downloader,
                            detail_fetch_sec=_elapsed(result["started"]),
                        )
                        selected_entry["postprocessStatus"] = "pending"
                        manifest["selectedMaterials"].append(selected_entry)
                        selected_ids.add(material_id)
                        selected_by_group[item["selectionGroupId"]] = (
                            selected_by_group.get(item["selectionGroupId"], 0) + 1
                        )
                        submit_highlight(highlight_executor, detail_record)
                    except Exception as exc:
                        rejected_ids.add(material_id)
                        manifest["rejectedMaterials"].append(
                            {
                                **_manifest_material(item),
                                "reason": exc.__class__.__name__,
                                "error": str(exc),
                                "timingsSec": {"detailFetchSec": _elapsed(result["started"])},
                            }
                        )
                else:
                    result = future.result()
                    pending_highlights.pop(future)
                    material_id = result["material_id"]
                    entry = _selected_entry(manifest, material_id)
                    if entry is not None:
                        entry["postprocessTimingsSec"] = {
                            "highlightSec": result["duration"]
                        }
                        if result["error"] is None:
                            entry["postprocessStatus"] = "succeeded"
                            frames_by_material[material_id] = result["frames"]
                        else:
                            entry["postprocessStatus"] = "failed"
                            entry["postprocessError"] = str(result["error"])
            checkpoint()

    manifest["selectedMaterials"] = sorted(
        manifest["selectedMaterials"], key=lambda item: item.get("rank", 0)
    )
    manifest["timingsSec"]["totalSec"] = _elapsed(started)
    return _finalize_details(
        root,
        manifest,
        summary,
        manifest_path,
        require_no_unresolved=False,
    )


def collection_status(*, output_dir):
    """Read collection progress from state and landed artifacts without mutating them."""
    root = Path(output_dir)
    summary_path = root / run_state.RUN_SUMMARY_NAME
    manifest_path = root / "batch-manifest.json"
    try:
        summary = run_state.load_run_state(summary_path) if summary_path.is_file() else {}
    except run_state.YuntuRunStateError:
        summary = {"status": "state_unreadable"}
    try:
        manifest = _load_json(manifest_path) if manifest_path.is_file() else {}
    except (OSError, ValueError):
        manifest = {"status": "manifest_unreadable"}

    def _records(path):
        try:
            records = _load_json(path)
        except (OSError, ValueError):
            return []
        return records if isinstance(records, list) else []

    list_records = _records(root / "normalized" / "list-records.json")
    detail_requests = _records(root / "normalized" / "detail-request-params.json")
    detail_dir = root / "normalized" / "detail-records"
    persisted_details = len(list(detail_dir.glob("*.json"))) if detail_dir.is_dir() else 0
    stages = summary.get("stages") if isinstance(summary.get("stages"), dict) else {}
    list_stage = stages.get("list") if isinstance(stages.get("list"), dict) else {}
    detail_stage = stages.get("details") if isinstance(stages.get("details"), dict) else {}
    return {
        "status": summary.get("status") or manifest.get("status") or "not_started",
        "runId": summary.get("runId") or manifest.get("runId"),
        "parameterFingerprint": summary.get("parameterFingerprint"),
        "collectionContract": summary.get("collectionContract"),
        "rankingRuns": summary.get("rankingRuns") or manifest.get("rankingRuns", {}),
        "stages": {
            "list": {
                "requestStatus": list_stage.get("requestStatus", "unknown"),
                "normalizedRecordCount": len(list_records),
                "contextVerified": list_stage.get("contextVerified"),
                "contextIssues": list_stage.get("contextIssues", []),
            },
            "details": {
                "requestStatus": detail_stage.get("requestStatus", "unknown"),
                "requestParamCount": len(detail_requests),
                "submittedCount": len(manifest.get("submittedMaterials", [])),
                "persistedRecordCount": persisted_details,
                "selectedCount": len(manifest.get("selectedMaterials", [])),
                "rejectedCount": len(manifest.get("rejectedMaterials", [])),
                "unresolvedCount": len(manifest.get("unresolvedMaterials", [])),
                "cancelledCount": len(manifest.get("cancelledMaterials", [])),
            },
        },
        "evidencePaths": {
            "runSummary": str(summary_path) if summary_path.is_file() else None,
            "batchManifest": str(manifest_path) if manifest_path.is_file() else None,
            "listRecords": str(root / "normalized" / "list-records.json")
            if list_records
            else None,
            "detailRequests": str(root / "normalized" / "detail-request-params.json")
            if detail_requests
            else None,
            "detailRecordsDir": str(detail_dir) if detail_dir.is_dir() else None,
        },
    }


def _retry_batch_items(*, shop_id, output_dir, invoker, item_key, downloader=None):
    if not isinstance(shop_id, str) or not shop_id.strip():
        raise YuntuBatchError("shop_id is required")
    downloader = FileDownloader() if downloader is None else downloader
    root = Path(output_dir)
    manifest_path = root / "batch-manifest.json"
    summary_path = root / run_state.RUN_SUMMARY_NAME
    if not summary_path.is_file():
        raise YuntuBatchError(
            "output directory contains an unverifiable existing batch; choose a new output directory"
        )
    try:
        summary = run_state.load_run_state(summary_path)
    except run_state.YuntuRunStateError as exc:
        raise YuntuBatchError(
            "output directory contains an unverifiable existing batch; choose a new output directory"
        ) from exc
    contract = summary.get("collectionContract")
    if not isinstance(contract, dict) or not run_state.collection_contract_matches(
        summary, contract
    ):
        raise YuntuBatchError(
            "output directory contains an unverifiable existing batch; choose a new output directory"
        )
    if contract.get("shopId") != shop_id.strip():
        raise YuntuBatchError(
            "output directory belongs to a different collection contract; choose a new output directory"
        )
    manifest = _load_json(manifest_path)
    detail_date_params = contract["detailDateRange"]
    if manifest.get("detailDateRange") != detail_date_params:
        raise YuntuBatchError("batch manifest detailDateRange does not match collection contract")
    retry_items = list(manifest.get(item_key, []))
    if not retry_items:
        return _finalize_details(
            root,
            manifest,
            summary,
            manifest_path,
            incomplete_status=manifest.get("status", "partial"),
        )

    selected_ids = _selected_ids(manifest)
    still_retry_items = []
    for item in retry_items:
        material_id = item.get("material_id")
        if not isinstance(material_id, str) or not material_id.isdigit():
            still_retry_items.append(item)
            continue
        detail_started = time.monotonic()
        try:
            _, selected_entry = _persist_detail(
                root=root,
                summary=summary,
                item=item,
                gateway_result=invoker.invoke_detail(
                    shop_id, _detail_request(item, detail_date_params)
                ),
                downloader=downloader,
                detail_fetch_sec=_elapsed(detail_started),
            )
            if material_id not in selected_ids:
                manifest.setdefault("selectedMaterials", []).append(selected_entry)
                selected_ids.add(material_id)
        except Exception as exc:
            retry_count = int(item.get("retryCount", 0)) + 1
            updated = dict(item)
            updated["reason"] = exc.__class__.__name__
            updated["error"] = str(exc)
            updated["retryCount"] = retry_count
            updated["timingsSec"] = {"detailFetchSec": _elapsed(detail_started)}
            still_retry_items.append(updated)

    manifest["selectedMaterials"] = sorted(
        manifest.get("selectedMaterials", []), key=lambda item: item.get("rank", 0)
    )
    manifest[item_key] = still_retry_items
    return _finalize_details(root, manifest, summary, manifest_path)


def retry_failed_batch(*, shop_id, output_dir, invoker, downloader=None):
    return _retry_batch_items(
        shop_id=shop_id,
        output_dir=output_dir,
        invoker=invoker,
        item_key="rejectedMaterials",
        downloader=downloader,
    )


def retry_unresolved_batch(*, shop_id, output_dir, invoker, downloader=None):
    return _retry_batch_items(
        shop_id=shop_id,
        output_dir=output_dir,
        invoker=invoker,
        item_key="unresolvedMaterials",
        downloader=downloader,
    )


def _relative(root, path):
    return str(Path(path).resolve().relative_to(Path(root).resolve()))
