"""Persistent model drafts, scoped preflight and lossless assembly. No AI calls."""
import copy
import json
import os
import time
from pathlib import Path

from rpa_io import file_sha256, write_json_atomically
from yuntu_analysis_bundle import (
    AnalysisBundleError, file_record, load_analysis_bundle, read_json, schema_errors, verify_record,
)
import yuntu_report as report
from yuntu_analysis_quality import WRITING_RUBRIC, SCRIPT_FIELDS
from yuntu_analysis_inputs import READING_RULES, json_bytes, model_reading_view


def _binding(bundle):
    return {"manifestSha256": file_sha256(bundle["manifestPath"]),
            "promptSha256": file_sha256(bundle["root"] / "yuntu-analysis-prompt.md")}


def _parts(bundle):
    available = bundle["schema"].get("properties", {})
    parts = []
    for key, unit, fields in (
        ("ranking", "ranking_brand", ["topMaterialCombination"]),
        ("audience", "audience_marketing", ["chapter02Insights"]),
        ("script", "script_insights", ["scriptInsights", "keywordCloudReview", "keywordCloudInsight"]),
        ("highlight", "highlight", ["highlightDashboard"]),
    ):
        fields = [field for field in fields if field in available]
        if fields:
            parts.append({"key": key, "unit": unit, "path": f"{key}.json", "outputFields": fields})
    for index, brand in enumerate(bundle["facts"].get("scriptFacts", {}).get("brandScopeOrder", [])):
        if "scriptBrandInsights" in available:
            parts.append({"key": f"script-brand-{index}", "unit": "script_insights",
                          "path": f"script-brand-{index}.json", "brand": brand,
                          "outputFields": ["scriptBrandInsights"]})
    if "materialDeepDives" in available:
        for material in bundle["facts"].get("materialFacts", []):
            mid = str(material["material_id"])
            if not mid.isdigit():
                raise AnalysisBundleError("draft material_id must be numeric")
            parts.append({"key": f"material-{mid}", "unit": "material_deep_dive",
                          "path": f"material-{mid}.json", "materialId": mid,
                          "outputFields": ["materialDeepDives"]})
    return parts


def _part_schema(bundle, part):
    properties = bundle["schema"]["properties"]
    if "brand" in part:
        return copy.deepcopy(properties["scriptBrandInsights"]["properties"][part["brand"]])
    if "materialId" in part:
        schema = copy.deepcopy(properties["materialDeepDives"]["items"])
        fact = next(x for x in bundle["facts"]["materialFacts"] if str(x["material_id"]) == part["materialId"])
        schema["properties"]["material_id"] = {"const": part["materialId"]}
        script = schema["properties"]["scriptAnalysis"]["properties"]
        has_text = bool(fact.get("script", {}).get("text", "").strip())
        script["availability"] = {"const": "available" if has_text else "unavailable"}
        script["conclusion"] = {"type": "string", **({"minLength": 120, "maxLength": 220} if has_text else {})}
        refs = fact.get("evidenceIndex", {}).get("script", [])
        script["evidenceRefs"] = {"type": "array", "uniqueItems": True,
                                  "items": {"type": "string", "enum": refs} if refs else False,
                                  **({"minItems": 1} if has_text else {"maxItems": 0})}
        return schema
    return {"type": "object", "additionalProperties": False, "required": part["outputFields"],
            "properties": {key: properties[key] for key in part["outputFields"]}}


def _task(bundle, part):
    task = {"part": part["key"], "outputSchema": _part_schema(bundle, part),
            "factInput": next(x["path"] for x in bundle["manifest"]["units"] if x.get("unit") == part["unit"])}
    task["scopedFacts"] = model_reading_view(bundle, part)
    task["readingRule"] = READING_RULES[part["unit"]]
    task["factInputRole"] = "canonical_source_for_audit; read scopedFacts first, do not reread the full unit by default"
    task["imageRoot"] = str(bundle["root"])
    facts = bundle["facts"]
    task["writingRubric"] = WRITING_RUBRIC
    if part["key"] == "script" or "brand" in part:
        task["scope"] = part.get("brand", "所有指定品牌")
        task["evidenceFormat"] = "evidence 填本范围脚本文本或公式中的原文短语；material_ids 仅填本范围素材。正文缺失时 evidence=[]，明确数据不足以判断。"
    if "materialId" in part:
        fact = next(x for x in facts["materialFacts"] if str(x["material_id"]) == part["materialId"])
        task["scriptEvidenceRefs"] = fact.get("evidenceIndex", {}).get("script", [])
        task["requiredFrameRefs"] = [x["frame_ref"] for x in fact.get("highlightFrames", []) if x.get("available")]
        task["scriptTextAvailable"] = bool(fact.get("script", {}).get("text", "").strip())
        task["scriptForbiddenClaimPattern"] = report.SCRIPT_ANALYSIS_FORBIDDEN_CLAIM.pattern
        task["observationMinCharacters"] = report.AI_TEXT_MINIMUMS["frame_observation"]
    if part["key"] == "audience":
        scopes = facts["chapter02AiFacts"]
        task["scopes"] = {key: {"sampleCount": scopes[key].get("sampleCount"),
                                "availability": scopes[key].get("availability"),
                                "materialIds": [str(x["material_id"]) for x in scopes[key].get("topMaterials", [])]}
                          for key in scopes["scopeOrder"]}
    if part["key"] == "highlight":
        task["requiredFrameRefs"] = [x["frame_ref"] for x in report._overview_highlight_frames(facts)]
        task["classificationCoverage"] = "每套分类独立覆盖成功帧全集，每帧恰好一次；失败帧不分类。"
        if facts.get("analysisQualityVersion", 0) >= 4:
            task["classificationRequirements"] = "必须同时输出 frameUnderstanding、standardClassification、batchClassification 和 brands。逐帧填写 standard_category 与 category_reason；标准组及各品牌组必须与逐帧分类一致。人物作为讲解或操作主体归 portrait；手部辅助展示且产品为主体归 product；其余归 other 并写清理由。本批次分类按实际画面主题独立分组，不能以省略字段代替 unavailable。"
    return task


def begin_workspace(manifest_path, workspace):
    bundle = load_analysis_bundle(manifest_path)
    if not bundle["schema"]:
        raise AnalysisBundleError("drafting requires an output schema; prepare analysis first")
    workspace = Path(workspace).resolve()
    state_path = workspace / "workspace.json"
    if state_path.exists():
        state, _ = _load_workspace(workspace)
        if (workspace / state["manifest"]).resolve() != bundle["manifestPath"]:
            raise AnalysisBundleError("workspace belongs to another manifest")
        return state
    if workspace.exists() and any(workspace.iterdir()):
        raise AnalysisBundleError("new workspace must be empty")
    workspace.mkdir(parents=True, exist_ok=True)
    state = {"version": 1, "manifest": os.path.relpath(bundle["manifestPath"], workspace),
             "binding": _binding(bundle), "parts": _parts(bundle)}
    state["readingViewVersion"] = 1
    state["taskInputs"] = []
    state["inputMetrics"] = {"unitFileBytes": sum(x["bytes"] for x in bundle["manifest"]["units"]),
                             "scopedFactsBytes": 0, "taskFileBytes": 0,
                             "measurement": "UTF-8 bytes, not model tokens or elapsed model time"}
    for part in state["parts"]:
        write_json_atomically({"binding": state["binding"], "content": None,
                               "viewedFrameRefs": []}, workspace / part["path"])
        task = _task(bundle, part)
        task_path = workspace / f"{part['key']}.task.json"
        write_json_atomically(task, task_path, indent=None)
        state["taskInputs"].append(file_record(task_path, workspace))
        state["inputMetrics"]["scopedFactsBytes"] += json_bytes(task["scopedFacts"])
        state["inputMetrics"]["taskFileBytes"] += task_path.stat().st_size
    write_json_atomically(state, state_path)
    return state


def _load_workspace(workspace):
    workspace = Path(workspace)
    state = read_json(workspace / "workspace.json")
    bundle = load_analysis_bundle(workspace / state["manifest"])
    if state.get("version") != 1 or state.get("binding") != _binding(bundle) or state.get("parts") != _parts(bundle):
        raise AnalysisBundleError("workspace binding changed; start a new workspace for the new facts/prompt")
    if "readingViewVersion" in state:
        expected = [f"{part['key']}.task.json" for part in state["parts"]]
        records = state.get("taskInputs", [])
        if state["readingViewVersion"] != 1 or [x.get("path") for x in records] != expected:
            raise AnalysisBundleError("workspace reading view contract changed; start a new workspace")
        for record in records:
            verify_record(workspace, record, "model task input")
    return state, bundle


def _semantic_check(content, bundle, part):
    facts = copy.deepcopy(bundle["facts"])
    value = copy.deepcopy(content)
    if "brand" in part:
        facts["scriptFacts"] = facts["scriptFacts"]["brandScopes"][part["brand"]]
        facts["selectedMaterials"] = []
        report._validate_script_insights(value, facts)
    elif "materialId" in part:
        mid = part["materialId"]
        facts["selectedMaterials"] = [{"material_id": mid}]
        facts["materialFacts"] = [x for x in facts["materialFacts"] if str(x["material_id"]) == mid]
        report._validate_material_deep_dives({"materialDeepDives": [value]}, facts)
    elif part["key"] == "ranking":
        report._validate_top_material_combination(value["topMaterialCombination"], require_people_summary=False,
                                                   strict_contract=facts.get("schemaVersion", 0) >= 6)
        report._validate_ranking_scope_contract(value, facts)
        report._validate_period_and_hot_material_contract(value, facts)
    elif part["key"] == "audience":
        report._validate_chapter02_insights(value["chapter02Insights"], facts)
    elif part["key"] == "script":
        report._validate_script_insights(value, facts)
    elif part["key"] == "highlight":
        report._validate_highlight_dashboard(value, facts)


def _merge(parts, drafts):
    analysis = {}
    for part in parts:
        content = drafts[part["key"]]["content"]
        if "brand" in part:
            analysis.setdefault("scriptBrandInsights", {})[part["brand"]] = content
        elif "materialId" in part:
            analysis.setdefault("materialDeepDives", []).append(content)
        else:
            if set(analysis) & set(content):
                raise AnalysisBundleError("assembly contains duplicate output fields")
            analysis.update(content)
    return analysis


def _check(workspace, state, bundle, only_part=None):
    errors, drafts = [], {}
    selected = {only_part} if isinstance(only_part, str) else set(only_part or [])
    known = {part["key"] for part in state["parts"]}
    if only_part is not None and (not selected or selected - known):
        raise AnalysisBundleError(f"unknown draft part: {sorted(selected - known)}")
    parts = [x for x in state["parts"] if only_part is None or x["key"] in selected]
    for part in parts:
        def error(path, message):
            errors.append({"part": part["key"], "file": part["path"], "path": path, "message": message})
        try:
            draft = read_json(Path(workspace) / part["path"])
            if not isinstance(draft, dict) or draft.get("binding") != state["binding"]:
                raise AnalysisBundleError("draft binding does not match current facts/prompt")
            content = draft.get("content")
            if content is None:
                error("/content", "model draft is not written")
                continue
            found = schema_errors(content, _part_schema(bundle, part))
            for item in found:
                error("/content" + item["path"], item["message"])
            if found:
                continue
            if part["key"] == "highlight":
                expected = _task(bundle, part)["requiredFrameRefs"]
                viewed = draft.get("viewedFrameRefs")
                if not isinstance(viewed, list) or any(not isinstance(x, str) for x in viewed) or len(viewed) != len(set(viewed)) or set(viewed) != set(expected):
                    error("/viewedFrameRefs", "record each actually viewed successful JPEG exactly once")
            _semantic_check(content, bundle, part)
            drafts[part["key"]] = draft
        except (AnalysisBundleError, report.YuntuReportError) as exc:
            error("/content", str(exc))
    if only_part is None and not errors:
        try:
            report.validate_analysis_data(_merge(parts, drafts), bundle["facts"])
        except report.YuntuReportError as exc:
            errors.append({"part": "assembled", "file": "workspace.json", "path": "/content", "message": str(exc)})
    return {"valid": not errors, "checkedParts": [x["key"] for x in parts], "errors": errors}, drafts


def check_workspace(workspace, only_part=None):
    started = time.perf_counter()
    state, bundle = _load_workspace(workspace)
    loaded = time.perf_counter()
    result, _ = _check(workspace, state, bundle, only_part)
    result["timingsSeconds"] = {"loadAndVerifyInputs": round(loaded - started, 6),
                               "validateDrafts": round(time.perf_counter() - loaded, 6)}
    write_json_atomically(result, Path(workspace) / "validation.json")
    return result


def assembly_path(analysis_json):
    path = Path(analysis_json)
    return path.with_name(f"{path.stem}.assembly.json")


def assemble_workspace(workspace, output):
    started = time.perf_counter()
    state, bundle = _load_workspace(workspace)
    loaded = time.perf_counter()
    result, drafts = _check(workspace, state, bundle)
    result["timingsSeconds"] = {"loadAndVerifyInputs": round(loaded - started, 6),
                               "validateDrafts": round(time.perf_counter() - loaded, 6)}
    write_json_atomically(result, Path(workspace) / "validation.json")
    if not result["valid"]:
        raise AnalysisBundleError("assembly blocked; see workspace validation.json")
    analysis = _merge(state["parts"], drafts)
    output = Path(output).resolve()
    # Never overwrite an existing report input or a model draft implicitly.
    if output.exists() or assembly_path(output).exists():
        raise AnalysisBundleError("assembly output already exists; choose a new revision filename")
    output.parent.mkdir(parents=True, exist_ok=True)
    snapshot_dir = output.parent / f"{output.stem}.drafts"
    snapshot_dir.mkdir(exist_ok=True)
    snapshots = []
    for part in state["parts"]:
        raw = (Path(workspace) / part["path"]).read_bytes()
        # Recheck the bytes captured, not a later rewrite of the working draft.
        if json.loads(raw) != drafts[part["key"]]:
            raise AnalysisBundleError("draft changed during assembly; check again")
        import hashlib
        snapshot = snapshot_dir / f"{hashlib.sha256(raw).hexdigest()}.json"
        if snapshot.exists() and snapshot.read_bytes() != raw:
            raise AnalysisBundleError("draft snapshot hash mismatch")
        snapshot.write_bytes(raw)
        snapshots.append({"part": part, **file_record(snapshot, output.parent)})
    import tempfile
    with tempfile.TemporaryDirectory(dir=output.parent) as temporary:
        candidate = Path(temporary) / "analysis.json"
        write_json_atomically(analysis, candidate)
        report.validate_analysis_input(analysis_json=candidate, fact_pack=bundle["facts"])
        if schema_errors(analysis, bundle["schema"]):
            raise AnalysisBundleError("assembled output does not match schema")
        # Fact files and prompt must still be the versions used by the drafts.
        _load_workspace(workspace)
        write_json_atomically(analysis, output)
    receipt = {"version": 1, "assemblyMode": "lossless_model_drafts", "binding": state["binding"],
               "authorshipEvidence": "caller_declared_model_drafts; not proof of model identity or image viewing",
               "analysis": file_record(output, output.parent), "drafts": snapshots}
    write_json_atomically(receipt, assembly_path(output))
    return output


def verify_assembly(analysis_json, manifest_path):
    analysis_json = Path(analysis_json)
    bundle = load_analysis_bundle(manifest_path)
    receipt = read_json(assembly_path(analysis_json))
    if receipt.get("version") != 1 or receipt.get("binding") != _binding(bundle):
        raise AnalysisBundleError("assembly binding does not match facts/prompt")
    verify_record(analysis_json.parent, receipt.get("analysis"), "assembly analysis")
    if receipt["analysis"]["sha256"] != file_sha256(analysis_json):
        raise AnalysisBundleError("assembly does not match requested analysis")
    parts, drafts = [], {}
    for entry in receipt.get("drafts", []):
        draft = read_json(verify_record(analysis_json.parent, entry, "assembly draft snapshot"))
        if draft.get("binding") != receipt["binding"]:
            raise AnalysisBundleError("assembly draft binding mismatch")
        part = entry["part"]
        parts.append(part)
        drafts[part["key"]] = draft
    if parts != _parts(bundle) or _merge(parts, drafts) != read_json(analysis_json):
        raise AnalysisBundleError("assembly is not a lossless merge of model draft snapshots")
    return receipt
