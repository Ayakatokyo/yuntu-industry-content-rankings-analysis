"""Read the same verified fact bundle for drafting, attestation and rendering."""
import copy
import json
from pathlib import Path

from rpa_io import file_sha256


class AnalysisBundleError(ValueError):
    pass


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise AnalysisBundleError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=unique)
    except (OSError, ValueError) as exc:
        raise AnalysisBundleError(f"invalid JSON {Path(path).name}: {exc}") from exc


def file_record(path, root):
    path, root = Path(path), Path(root)
    import os
    return {"path": os.path.relpath(path, root), "bytes": path.stat().st_size,
            "sha256": file_sha256(path)}


def verify_record(root, record, label):
    if not isinstance(record, dict) or not isinstance(record.get("path"), str):
        raise AnalysisBundleError(f"{label} is missing its file binding")
    path = Path(root) / record["path"]
    if (not path.is_file() or record.get("bytes") != path.stat().st_size
            or record.get("sha256") != file_sha256(path)):
        raise AnalysisBundleError(f"{label} does not match manifest: {record['path']}")
    return path


def load_analysis_bundle(manifest_path):
    manifest_path = Path(manifest_path).resolve()
    root = manifest_path.parent.parent
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict) or manifest.get("executionMode") != "single_model_call":
        raise AnalysisBundleError("analysis unit manifest executionMode is invalid")
    units = manifest.get("units")
    if not isinstance(units, list) or not units:
        raise AnalysisBundleError("analysis unit manifest is missing units")
    payloads = {}
    for index, unit in enumerate(units):
        path = verify_record(root, unit, "analysis unit")
        name = unit.get("unit", str(index))
        if name in payloads:
            raise AnalysisBundleError(f"duplicate analysis unit: {name}")
        payloads[name] = read_json(path)
    schema = {}
    if manifest.get("outputSchema"):
        schema = read_json(verify_record(root, manifest["outputSchema"], "output schema"))
    contract = manifest.get("analysisContract", {})
    if contract:
        if contract.get("version") != 1:
            raise AnalysisBundleError("unsupported analysis contract version")
        if set(payloads) != {"ranking_brand", "audience_marketing", "script_insights", "highlight", "material_deep_dive"} or not schema:
            raise AnalysisBundleError("analysis contract requires five units and an output schema")
        for label, filename in (("prompt", "yuntu-analysis-prompt.md"), ("reportData", "report-data.json")):
            if verify_record(root, contract.get(label), label).resolve() != (root / filename).resolve():
                raise AnalysisBundleError(f"{label} binding must point to {filename}")
        for asset in contract.get("visualAssets", []):
            path = verify_record(root, asset, f"visual asset {asset.get('frame_ref')}")
            try:
                from PIL import Image
                with Image.open(path) as image:
                    image.verify()
            except (OSError, ValueError) as exc:
                raise AnalysisBundleError(f"unreadable successful image: {asset.get('frame_ref')}") from exc
        for video in contract.get("videoAssets", []):
            path = verify_record(root, video, f"video asset {video.get('material_id')}")
            if path.stat().st_size == 0:
                raise AnalysisBundleError(f"empty successful video: {video.get('material_id')}")
    report_path = root / "report-data.json"
    facts = read_json(report_path)
    if not isinstance(facts, dict):
        raise AnalysisBundleError("report-data.json must be an object")
    # The front-end projection is intentionally compact. Restore validation
    # facts from their authoritative model inputs, never from chart scopes.
    facts = copy.deepcopy(facts)
    if contract:
        expected_refs = [x["frame_ref"] for f in facts.get("materialFacts", [])
                         for x in f.get("highlightFrames", []) if x.get("available")]
        bound_refs = [x.get("frame_ref") for x in contract.get("visualAssets", [])]
        if len(bound_refs) != len(set(bound_refs)) or set(expected_refs) != set(bound_refs):
            raise AnalysisBundleError("successful image bindings must cover report frames exactly once")
        if "videoAssets" in contract:
            expected_videos = {str(x["material_id"]) for x in facts.get("materialFacts", []) if x.get("localVideo", {}).get("available")}
            bound_videos = [x.get("material_id") for x in contract["videoAssets"]]
            if len(bound_videos) != len(set(bound_videos)) or set(bound_videos) != expected_videos:
                raise AnalysisBundleError("successful video bindings must cover available videos exactly once")
    audience = payloads.get("audience_marketing", {}).get("evidence", {})
    if "chapter02AiFacts" in audience:
        facts["chapter02AiFacts"] = audience["chapter02AiFacts"]
    script = payloads.get("script_insights", {}).get("evidence", {})
    if "scriptFacts" in script:
        facts["scriptFacts"] = script["scriptFacts"]
    materials = payloads.get("material_deep_dive", {}).get("evidence", {}).get("materialFacts", [])
    by_id = {str(x.get("material_id")): x for x in materials}
    if materials and set(by_id) != {str(x.get("material_id")) for x in facts.get("materialFacts", [])}:
        raise AnalysisBundleError("material facts and report projection have different material IDs")
    for fact in facts.get("materialFacts", []):
        canonical = by_id.get(str(fact.get("material_id")), {})
        for key in ("script", "evidenceIndex"):
            if key in canonical:
                fact[key] = copy.deepcopy(canonical[key])
    return {"manifest": manifest, "manifestPath": manifest_path, "root": root,
            "reportPath": report_path, "facts": facts, "units": payloads, "schema": schema}


def schema_errors(value, schema):
    try:
        from jsonschema import Draft202012Validator
    except ImportError as exc:
        raise AnalysisBundleError("jsonschema is required; install the skill requirements.txt") from exc
    Draft202012Validator.check_schema(schema)
    errors = []
    for error in Draft202012Validator(schema).iter_errors(value):
        # Reference enums can contain whole script sentences. Do not repeat
        # the entire fact pack in a diagnostic; the task file has the allowlist.
        if error.validator == "enum":
            message = "value is outside the allowed set; copy a value from this part's task JSON"
        elif error.validator in {"minLength", "maxLength", "minItems", "maxItems"}:
            message = f"{error.validator}={error.validator_value}, actual={len(error.instance)}"
        elif error.validator == "type":
            message = f"expected type {error.validator_value}"
        else:
            message = error.message
        errors.append({"path": "/" + "/".join(str(x) for x in error.absolute_path),
                       "message": message[:600], "code": f"schema.{error.validator}"})
    return errors
