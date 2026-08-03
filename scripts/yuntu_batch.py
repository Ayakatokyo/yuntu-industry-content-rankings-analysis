"""Batch fetch orchestration for Yuntu rankings analysis."""

from pathlib import Path
import time

from rpa_io import (
    download_file,
    parse_csv_records,
    unpack_gateway_result,
    write_json_atomically,
)
from yuntu_normalizer import normalize_detail_records, normalize_list_records


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


def _load_json(path):
    import json

    return json.loads(Path(path).read_text(encoding="utf-8"))


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
    manifest["candidateMaterials"] = [
        {"rank": index, "material_id": material_id}
        for index, material_id in enumerate(candidate_ids, start=1)
    ]
    list_by_id = {record["material_id"]: record for record in list_records}

    had_rejection = False
    for rank, material_id in enumerate(candidate_ids, start=1):
        if len(manifest["selectedMaterials"]) >= target_top_n:
            manifest["cancelledMaterials"].append(
                {"rank": rank, "material_id": material_id, "reason": "target_satisfied"}
            )
            continue
        detail_started = time.monotonic()
        manifest["submittedMaterials"].append({"rank": rank, "material_id": material_id})
        try:
            raw_detail, detail_source = _materialize_records(
                invoker.invoke_detail(
                    shop_id, {**detail_date_params, "material_id": material_id}
                ),
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

    ready_materials = [
        list_by_id[item["material_id"]] for item in manifest["selectedMaterials"]
    ]
    write_json_atomically(
        {"materials": ready_materials},
        root / "normalized" / "top-materials-rpa-ready.json",
    )
    if len(manifest["selectedMaterials"]) >= target_top_n and not had_rejection:
        manifest["status"] = "success"
    else:
        manifest["status"] = "partial"
    manifest["timingsSec"]["totalSec"] = _elapsed(started)
    write_json_atomically(manifest, manifest_path)
    return 0 if manifest["status"] == "success" else 1


def retry_failed_batch(*, shop_id, output_dir, invoker, downloader=None):
    if not isinstance(shop_id, str) or not shop_id.strip():
        raise YuntuBatchError("shop_id is required")
    downloader = FileDownloader() if downloader is None else downloader
    root = Path(output_dir)
    manifest_path = root / "batch-manifest.json"
    manifest = _load_json(manifest_path)
    detail_date_params = manifest.get("detailDateRange")
    if not isinstance(detail_date_params, dict):
        raise YuntuBatchError("batch manifest is missing detailDateRange")
    rejected = list(manifest.get("rejectedMaterials", []))
    if not rejected:
        _refresh_ready_materials(root, manifest)
        manifest["status"] = (
            "success"
            if len(manifest.get("selectedMaterials", [])) >= manifest.get("targetTopN", 0)
            else manifest.get("status", "partial")
        )
        write_json_atomically(manifest, manifest_path)
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
                    shop_id, {**detail_date_params, "material_id": material_id}
                ),
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
            if material_id not in selected_ids:
                manifest.setdefault("selectedMaterials", []).append(
                    {
                        "rank": rank,
                        "material_id": material_id,
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
    target = manifest.get("targetTopN", 0)
    manifest["status"] = (
        "success"
        if not still_rejected and len(manifest.get("selectedMaterials", [])) >= target
        else "partial"
    )
    write_json_atomically(manifest, manifest_path)
    return 0 if manifest["status"] == "success" else 1


def _relative(root, path):
    return str(Path(path).resolve().relative_to(Path(root).resolve()))
