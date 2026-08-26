"""Bind model-authored Yuntu analysis JSON to its facts and prompt."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from rpa_io import file_sha256, write_json_atomically
from yuntu_report import YuntuReportError, validate_analysis_input


class YuntuAnalysisProvenanceError(RuntimeError):
    """Raised when an analysis source receipt is absent or unverifiable."""


MODEL_SOURCES = {"model_generated", "manual_model_generated"}
PROGRAMMATIC_FALLBACK = "programmatic_fallback"
ALL_SOURCES = MODEL_SOURCES


def default_provenance_path(analysis_json):
    analysis_path = Path(analysis_json)
    return analysis_path.with_name(f"{analysis_path.stem}.provenance.json")


def _receipt_relative_path(path, receipt_path):
    return os.path.relpath(Path(path).resolve(), receipt_path.parent.resolve())


def _verify_analysis_unit_manifest(path):
    manifest_path = Path(path)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        if manifest_path.name == "analysis-unit-manifest.json":
            raise YuntuAnalysisProvenanceError(
                "analysis unit manifest must be valid JSON"
            ) from exc
        return
    if not isinstance(manifest, dict) or manifest.get("executionMode") != "single_model_call":
        return
    units = manifest.get("units")
    if not isinstance(units, list) or not units:
        raise YuntuAnalysisProvenanceError("analysis unit manifest is missing units")
    prompt_root = manifest_path.parent.parent
    for unit in units:
        unit_path = prompt_root / unit.get("path", "") if isinstance(unit, dict) else None
        if (
            unit_path is None
            or not unit_path.is_file()
            or unit.get("bytes") != unit_path.stat().st_size
            or unit.get("sha256") != file_sha256(unit_path)
        ):
            raise YuntuAnalysisProvenanceError(
                "analysis unit does not match manifest"
            )
    return manifest


def _validate_single_call_analysis(analysis_json, manifest_path):
    report_data_path = Path(manifest_path).parent.parent / "report-data.json"
    try:
        fact_pack = json.loads(report_data_path.read_text(encoding="utf-8"))
        if not isinstance(fact_pack, dict):
            raise ValueError("report-data.json must be an object")
        validate_analysis_input(
            analysis_json=analysis_json,
            fact_pack=fact_pack,
        )
    except (OSError, json.JSONDecodeError, ValueError, YuntuReportError) as exc:
        raise YuntuAnalysisProvenanceError(
            f"analysis validation failed: {exc}"
        ) from exc


def attest_analysis(
    *,
    analysis_json,
    fact_pack_json,
    prompt_path,
    source,
    generator,
    output_path=None,
    allow_programmatic_fallback=False,
):
    if source not in ALL_SOURCES:
        raise YuntuAnalysisProvenanceError("analysis source is not supported")
    if source == PROGRAMMATIC_FALLBACK or allow_programmatic_fallback:
        raise YuntuAnalysisProvenanceError(
            "programmatic fallback is disabled; generate analysis with an AI model"
        )
    paths = {
        "analysisJson": Path(analysis_json),
        "factPack": Path(fact_pack_json),
        "prompt": Path(prompt_path),
    }
    for label, path in paths.items():
        if not path.is_file() or not path.stat().st_size:
            raise YuntuAnalysisProvenanceError(f"{label} must be a nonempty file")
    manifest = _verify_analysis_unit_manifest(paths["factPack"])
    try:
        analysis = json.loads(paths["analysisJson"].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise YuntuAnalysisProvenanceError("analysis JSON must be valid JSON") from exc
    if not isinstance(analysis, dict):
        raise YuntuAnalysisProvenanceError("analysis JSON must be an object")
    if manifest is not None:
        _validate_single_call_analysis(paths["analysisJson"], paths["factPack"])
    target = Path(output_path) if output_path else default_provenance_path(analysis_json)
    receipt = {
        "schemaVersion": 1,
        "analysisSource": source,
        "generator": str(generator or "").strip() or "unspecified",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "artifacts": {
            label: {
                "path": _receipt_relative_path(path, target),
                "sha256": file_sha256(path),
            }
            for label, path in paths.items()
        },
    }
    write_json_atomically(receipt, target)
    return target


def load_verified_provenance(
    *, analysis_json, provenance_path, allow_programmatic_fallback=False
):
    source = Path(provenance_path)
    if not source.is_file():
        raise YuntuAnalysisProvenanceError("analysis provenance receipt is required")
    try:
        receipt = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise YuntuAnalysisProvenanceError("analysis provenance receipt is invalid") from exc
    if not isinstance(receipt, dict):
        raise YuntuAnalysisProvenanceError("analysis provenance receipt must be an object")
    analysis_source = receipt.get("analysisSource")
    if analysis_source not in ALL_SOURCES:
        raise YuntuAnalysisProvenanceError("analysis provenance source is invalid")
    if analysis_source == PROGRAMMATIC_FALLBACK or allow_programmatic_fallback:
        raise YuntuAnalysisProvenanceError(
            "programmatic fallback is disabled; generate analysis with an AI model"
        )
    artifacts = receipt.get("artifacts")
    analysis_artifact = artifacts.get("analysisJson") if isinstance(artifacts, dict) else None
    if not isinstance(analysis_artifact, dict):
        raise YuntuAnalysisProvenanceError("analysis provenance is missing analysis JSON")
    if analysis_artifact.get("sha256") != file_sha256(analysis_json):
        raise YuntuAnalysisProvenanceError("analysis JSON does not match provenance receipt")
    for label in ("factPack", "prompt"):
        artifact = artifacts.get(label)
        artifact_path = source.parent / artifact.get("path", "") if isinstance(artifact, dict) else None
        if (
            artifact_path is None
            or not artifact_path.is_file()
            or artifact.get("sha256") != file_sha256(artifact_path)
        ):
            raise YuntuAnalysisProvenanceError(
                f"analysis provenance {label} does not match receipt"
            )
        if label == "factPack":
            _verify_analysis_unit_manifest(artifact_path)
    return receipt
