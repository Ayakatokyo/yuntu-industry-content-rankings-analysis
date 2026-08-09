"""Batch fetch orchestration for Yuntu rankings analysis."""

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
import yuntu_run_state as run_state


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
    result = {"rank": item["rank"], "material_id": item["material_id"]}
    if item["selectionGroupId"] != "default":
        result["selectionGroupId"] = item["selectionGroupId"]
        result["brandId"] = item["selectionGroup"]["brand_id"]
        result["brandName"] = item["selectionGroup"]["brand_name"]
        result["touchpointCode"] = item["selectionGroup"]["touchpoint_code"]
        result["touchpointName"] = item["selectionGroup"]["touchpoint_name"]
    return result


def _detail_request(item, detail_date_params):
    request = {"material_id": item["material_id"], **detail_date_params}
    if item["selectionGroupId"] != "default":
        request.update(
            {
                "selectionGroupId": item["selectionGroupId"],
                "brandId": item["selectionGroup"]["brand_id"],
                "brandName": item["selectionGroup"]["brand_name"],
                "touchpointCode": item["selectionGroup"]["touchpoint_code"],
                "touchpointName": item["selectionGroup"]["touchpoint_name"],
            }
        )
    return request


def _retry_detail_request(item, detail_date_params):
    request = {"material_id": item["material_id"], **detail_date_params}
    for key in (
        "selectionGroupId",
        "brandId",
        "brandName",
        "touchpointCode",
        "touchpointName",
    ):
        if key in item:
            request[key] = item[key]
    return request


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
        "schemaVersion": 2,
        "runId": summary["runId"],
        "parameterFingerprint": summary["parameterFingerprint"],
        "collectionContract": summary["collectionContract"],
        "status": "running",
        "filters": list_params,
        "detailDateRange": detail_date_params,
        "targetTopN": target_top_n,
        "candidateTopN": candidate_top_n,
        "candidateMaterials": [],
        "selectionGroups": [],
        "submittedMaterials": [],
        "selectedMaterials": [],
        "rejectedMaterials": [],
        "cancelledMaterials": [],
        "timingsSec": {},
    }


def _load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


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
            "cancelledCount": len(manifest.get("cancelledMaterials", [])),
        }
    )


def _brand_tokens(value):
    return {
        part.strip().casefold()
        for part in str(value or "").split("/")
        if part.strip()
    }


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
            f"{list_params['custom_start_date']} ~ {list_params['custom_end_date']}"
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
    manifest = _new_manifest(
        list_params=list_params,
        detail_date_params=detail_date_params,
        target_top_n=target_top_n,
        candidate_top_n=candidate_top_n,
        summary=summary,
    )
    write_json_atomically(manifest, manifest_path)

    started = time.monotonic()
    try:
        reusable_list = _reusable_list_artifact(root, list_params, detail_date_params)
        if reusable_list is not None:
            raw_list, list_source = parse_csv_records(reusable_list), str(reusable_list)
            summary["stages"]["list"]["requestStatus"] = "reused"
        else:
            summary["stages"]["list"]["requestStatus"] = "requested"
            _save_summary(root, summary)
            raw_list, list_source = _materialize_records(
                invoker.invoke_list(shop_id, list_params),
                csv_path=root / "raw-csv" / "list.csv",
                json_path=root / "raw-json" / "list-response.json",
                downloader=downloader,
            )
        list_records = normalize_list_records(raw_list, source_path=_relative(root, list_source))
        list_record_path = root / "normalized" / "list-records.json"
        write_json_atomically(list_records, list_record_path)
        _record_artifact(summary, root, "listRecords", list_record_path, "normalized_list")
        summary["stages"]["list"]["normalized"] = True
        context_verification = _validate_list_context(list_records, list_params)
        summary["stages"]["list"]["contextVerified"] = context_verification["valid"]
        summary["stages"]["list"]["contextIssues"] = context_verification["issues"]
        summary["stages"]["list"]["observedContext"] = context_verification["observed"]
        if not context_verification["valid"]:
            manifest["status"] = "list_context_mismatch"
            manifest["error"] = "list context does not match requested filters: " + ", ".join(
                context_verification["issues"]
            )
            manifest["timingsSec"]["totalSec"] = _elapsed(started)
            summary["status"] = "list_context_mismatch"
            _sync_stage_counts(summary, manifest, root)
            write_json_atomically(manifest, manifest_path)
            _save_summary(root, summary)
            return 1
    except Exception as exc:
        manifest["status"] = "list_failed"
        manifest["error"] = str(exc)
        manifest["timingsSec"]["totalSec"] = _elapsed(started)
        summary["status"] = "list_failed"
        summary["stages"]["list"]["requestStatus"] = "failed"
        _sync_stage_counts(summary, manifest, root)
        write_json_atomically(manifest, manifest_path)
        _save_summary(root, summary)
        return 1

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
    list_by_id = {record["material_id"]: record for record in list_records}

    had_rejection = False
    selected_by_group = {}
    for item in candidates:
        rank = item["rank"]
        material_id = item["material_id"]
        group_id = item["selectionGroupId"]
        if selected_by_group.get(group_id, 0) >= target_top_n:
            manifest["cancelledMaterials"].append(
                {**_manifest_material(item), "reason": "target_satisfied"}
            )
            continue
        detail_started = time.monotonic()
        manifest["submittedMaterials"].append(_manifest_material(item))
        _sync_stage_counts(summary, manifest, root)
        write_json_atomically(manifest, manifest_path)
        _save_summary(root, summary)
        try:
            raw_detail, detail_source = _materialize_records(
                invoker.invoke_detail(
                    shop_id, _detail_request(item, detail_date_params)
                ),
                csv_path=root / "raw-csv" / "details" / f"{material_id}.csv",
                json_path=root / "raw-json" / "details" / f"{material_id}.json",
                downloader=downloader,
            )
            detail_record = normalize_detail_records(
                raw_detail,
                material_id=material_id,
                source_path=_relative(root, detail_source),
                expected_selection_group=(
                    item["selectionGroup"] if group_id != "default" else None
                ),
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
            manifest["selectedMaterials"].append(
                {
                    **_manifest_material(item),
                    "listRecordPath": "normalized/list-records.json",
                    "detailRecordPath": _relative(root, detail_output),
                    "rawDetailPath": _relative(root, detail_source),
                    "timingsSec": {"detailFetchSec": _elapsed(detail_started)},
                }
            )
            selected_by_group[group_id] = selected_by_group.get(group_id, 0) + 1

        except Exception as exc:
            had_rejection = True
            manifest["rejectedMaterials"].append(
                {
                    **_manifest_material(item),
                    "reason": exc.__class__.__name__,
                    "error": str(exc),
                    "timingsSec": {"detailFetchSec": _elapsed(detail_started)},
                }
            )
        _sync_stage_counts(summary, manifest, root)
        write_json_atomically(manifest, manifest_path)
        _save_summary(root, summary)

    ready_materials = [
        list_by_id[item["material_id"]] for item in manifest["selectedMaterials"]
    ]
    write_json_atomically(
        {"materials": ready_materials},
        root / "normalized" / "top-materials-rpa-ready.json",
    )
    if _target_satisfied(manifest) and not had_rejection:
        manifest["status"] = "success"
    else:
        manifest["status"] = "partial"
    manifest["timingsSec"]["totalSec"] = _elapsed(started)
    summary["status"] = manifest["status"]
    summary["stages"]["details"]["requestStatus"] = (
        "completed" if manifest["status"] == "success" else "partial"
    )
    _sync_stage_counts(summary, manifest, root)
    write_json_atomically(manifest, manifest_path)
    _save_summary(root, summary)
    return 0 if manifest["status"] == "success" else 1


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


def retry_failed_batch(*, shop_id, output_dir, invoker, downloader=None):
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
    rejected = list(manifest.get("rejectedMaterials", []))
    if not rejected:
        _refresh_ready_materials(root, manifest)
        manifest["status"] = (
            "success"
            if _target_satisfied(manifest)
            else manifest.get("status", "partial")
        )
        summary["status"] = manifest["status"]
        summary["stages"]["details"]["requestStatus"] = "completed"
        _sync_stage_counts(summary, manifest, root)
        write_json_atomically(manifest, manifest_path)
        _save_summary(root, summary)
        return 0 if manifest["status"] == "success" else 1

    selected_ids = _selected_ids(manifest)
    still_rejected = []
    for item in rejected:
        material_id = item.get("material_id")
        if not isinstance(material_id, str) or not material_id.isdigit():
            still_rejected.append(item)
            continue
        rank = item.get("rank")
        detail_started = time.monotonic()
        try:
            raw_detail, detail_source = _materialize_records(
                invoker.invoke_detail(
                    shop_id, _retry_detail_request(item, detail_date_params)
                ),
                csv_path=root / "raw-csv" / "details" / f"{material_id}.csv",
                json_path=root / "raw-json" / "details" / f"{material_id}.json",
                downloader=downloader,
            )
            detail_record = normalize_detail_records(
                raw_detail,
                material_id=material_id,
                source_path=_relative(root, detail_source),
                expected_selection_group=(
                    {
                        "id": item.get("selectionGroupId"),
                        "brand_id": item.get("brandId"),
                        "brand_name": item.get("brandName"),
                        "touchpoint_code": item.get("touchpointCode"),
                        "touchpoint_name": item.get("touchpointName"),
                    }
                    if item.get("selectionGroupId")
                    else None
                ),
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
            if material_id not in selected_ids:
                manifest.setdefault("selectedMaterials", []).append(
                    {
                        "rank": rank,
                        "material_id": material_id,
                        **(
                            {key: item[key] for key in ("selectionGroupId", "brandId", "brandName", "touchpointCode", "touchpointName") if key in item}
                        ),
                        "listRecordPath": "normalized/list-records.json",
                        "detailRecordPath": _relative(root, detail_output),
                        "rawDetailPath": _relative(root, detail_source),
                        "timingsSec": {"detailFetchSec": _elapsed(detail_started)},
                    }
                )
                selected_ids.add(material_id)
        except Exception as exc:
            retry_count = int(item.get("retryCount", 0)) + 1
            updated = dict(item)
            updated["reason"] = exc.__class__.__name__
            updated["error"] = str(exc)
            updated["retryCount"] = retry_count
            updated["timingsSec"] = {"detailFetchSec": _elapsed(detail_started)}
            still_rejected.append(updated)

    manifest["selectedMaterials"] = sorted(
        manifest.get("selectedMaterials", []), key=lambda item: item.get("rank", 0)
    )
    manifest["rejectedMaterials"] = still_rejected
    _refresh_ready_materials(root, manifest)
    manifest["status"] = (
        "success"
        if not still_rejected and _target_satisfied(manifest)
        else "partial"
    )
    summary["status"] = manifest["status"]
    summary["stages"]["details"]["requestStatus"] = (
        "completed" if manifest["status"] == "success" else "partial"
    )
    _sync_stage_counts(summary, manifest, root)
    write_json_atomically(manifest, manifest_path)
    _save_summary(root, summary)
    return 0 if manifest["status"] == "success" else 1


def _relative(root, path):
    return str(Path(path).resolve().relative_to(Path(root).resolve()))
