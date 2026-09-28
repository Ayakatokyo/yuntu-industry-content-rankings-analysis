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
from yuntu_analysis_inputs import READING_RULES, json_bytes, model_reading_view, concise_reading_view
from analysis_task_io import TASK_SECTIONS, task_pages, task_section


def _skeleton(schema):
    """Only structural constants; null prose must be authored by the model."""
    if 'const' in schema:
        return copy.deepcopy(schema['const'])
    if schema.get('type') == 'object':
        return {key: _skeleton(schema.get('properties', {}).get(key, {})) for key in schema.get('required', [])}
    if schema.get('type') == 'array':
        if 'prefixItems' in schema:
            return [_skeleton(item) for item in schema['prefixItems']]
        return [_skeleton(schema.get('items', {})) for _ in range(schema.get('minItems', 0))]
    return None


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
        script["conclusion"] = {"type": "string", "minLength": 1}
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
    task["scopedFacts"] = concise_reading_view(model_reading_view(bundle, part))
    task['outputSkeleton'] = _skeleton(task['outputSchema'])
    task['writingBudget'] = '统一精简：总览100–150字，维度40–70字，脚本50–80字，唯一画面观察25–60字，素材核心判断80–120字；每组一条判断和一个方向。字数不作通过门槛。'
    task["readingRule"] = READING_RULES[part["unit"]]
    task["factInputRole"] = "canonical_source_for_audit; read scopedFacts first, do not reread the full unit by default"
    task["imageRoot"] = str(bundle["root"])
    facts = bundle["facts"]
    task["writingRubric"] = WRITING_RUBRIC
    if part["key"] == "script" or "brand" in part:
        task["scope"] = part.get("brand", facts.get("brandScope", {}).get("aggregateLabel") or
                                 ("所有指定品牌" if facts.get("scriptFacts", {}).get("brandScopeOrder") else "全品牌"))
        task["evidenceFormat"] = "先选择本范围 material_ids，再从这些素材的 quoteSourcePaths 中逐字引用连续原文短语到 evidence；概括词、标题、画面、关键词统计不是可替代原文。正文缺失时 evidence=[]，明确数据不足以判断。"
        task["quoteSourcePaths"] = ["scopedFacts.materials[].script_text", "scopedFacts.materials[].content_formula.labels",
                                    "scopedFacts.materials[].content_formula.sources.script.detail"]
        task['requiredScriptTitles'] = ['一二级内容公式：', '脚本文案：']
        task['scopeLimitationExample'] = '本批次样本尚不足以代表行业普遍规律。'
    if "materialId" in part:
        fact = next(x for x in facts["materialFacts"] if str(x["material_id"]) == part["materialId"])
        task["scriptEvidenceRefs"] = fact.get("evidenceIndex", {}).get("script", [])
        task["requiredFrameRefs"] = [x["frame_ref"] for x in fact.get("highlightFrames", []) if x.get("available")]
        task["scriptTextAvailable"] = bool(fact.get("script", {}).get("text", "").strip())
        task["scriptForbiddenClaimPattern"] = report.SCRIPT_ANALYSIS_FORBIDDEN_CLAIM.pattern
        task['outputSkeleton']['frame_observations'] = [
            {'frame_ref': ref, 'observation': None} for ref in task['requiredFrameRefs']]
    if part["key"] == "audience":
        scopes = facts["chapter02AiFacts"]
        task["scopes"] = {key: {"sampleCount": scopes[key].get("sampleCount"),
                                "availability": scopes[key].get("availability"),
                                "materialIds": task['scopedFacts']['chapter02AiFacts'][key].get('topMaterialIds',
                                    [str(x["material_id"]) for x in scopes[key].get("topMaterials", [])])}
                          for key in scopes["scopeOrder"]}
    if part["key"] == "highlight":
        task["requiredFrameRefs"] = [x["frame_ref"] for x in report._overview_highlight_frames(facts)]
        task["classificationCoverage"] = "每套分类独立覆盖成功帧全集，每帧恰好一次；失败帧不分类。"
        frame_schema = task['outputSchema']['properties']['highlightDashboard']['properties']['frameUnderstanding']['items']
        task['outputSkeleton']['highlightDashboard']['frameUnderstanding'] = [
            {**_skeleton(frame_schema), 'frame_ref': ref} for ref in task['requiredFrameRefs']]
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
        task = _task(bundle, part)
        write_json_atomically({"binding": state["binding"], "content": task['outputSkeleton'],
                               "viewedFrameRefs": []}, workspace / part["path"])
        task_path = workspace / f"{part['key']}.task.json"
        write_json_atomically(task, task_path, indent=None)
        state["taskInputs"].append(file_record(task_path, workspace))
        state["inputMetrics"]["scopedFactsBytes"] += json_bytes(task["scopedFacts"])
        state["inputMetrics"]["taskFileBytes"] += task_path.stat().st_size
    write_json_atomically(state, state_path)
    return state


def _workspace_task(workspace, state, bundle, part_key):
    part = next((part for part in state['parts'] if part['key'] == part_key), None)
    if part is None:
        raise AnalysisBundleError('unknown draft part')
    # Persisted task is hash-verified by _load_workspace. Do not silently replace it.
    return read_json(Path(workspace) / f'{part_key}.task.json') if 'readingViewVersion' in state else _task(bundle, part)


def read_task(workspace, part_key, page=0, section="all"):
    if section not in TASK_SECTIONS:
        raise AnalysisBundleError(f"unknown analysis section: {section}")
    state, bundle = _load_workspace(workspace)
    task = _workspace_task(workspace, state, bundle, part_key)
    pages = task_pages(task_section(task, section))
    if type(page) is not int or not 0 <= page < len(pages):
        raise AnalysisBundleError('analysis page is out of range')
    return {'part': part_key, 'binding': state['binding'], 'section': section, 'page': page, 'pageCount': len(pages),
            'nextPage': page + 1 if page + 1 < len(pages) else None, 'records': pages[page]}


def read_workspace_navigation(workspace):
    """Describe every task and read section without replaying facts or schemas."""
    state, bundle = _load_workspace(workspace)
    parts = []
    for part in state["parts"]:
        task = _workspace_task(workspace, state, bundle, part["key"])
        entry = {"part": part["key"], "draft": part["path"], "writeField": "content",
                 "outputFields": part["outputFields"],
                 "sectionPages": {section: len(task_pages(task_section(task, section))) for section in TASK_SECTIONS}}
        for key in ("materialId", "brand"):
            if key in part:
                entry[key] = part[key]
        for key in ("scope", "scriptTextAvailable"):
            if key in task:
                entry[key] = task[key]
        if "scopes" in task:
            entry["scopes"] = list(task["scopes"])
        if "requiredFrameRefs" in task:
            entry["successfulFrameCount"] = len(task["requiredFrameRefs"])
        parts.append(entry)
    frames = report._overview_highlight_frames(bundle["facts"])
    return {"binding": state["binding"], "workspace": str(Path(workspace).resolve()),
            "promptPath": str(bundle["root"] / "yuntu-analysis-prompt.md"), "parts": parts,
            "frames": {"successfulCount": len(frames), "maxBatchSize": 20, "batchCount": (len(frames) + 19) // 20},
            "workflow": ["读取提示词一次；首次按 part 读取默认 all 并沿 nextPage 读完；修复时仅按需重读 facts、guidance、skeleton 或 schema 分区。",
                         "read-frame-batch 按素材顺序读取全部批次；每张成功 JPEG 同次填写第四章理解与第五章观察，及时保存。",
                         "全部逐帧理解保存后完成第四章两套分类及品牌分析；每套分类仍须各自覆盖全部成功帧。",
                         "每组草稿保存后 check-analysis --part 可重复；全部完成后 assemble-analysis 内部执行完整检查。"],
            "readingMetrics": state.get("inputMetrics", {}),
            "note": "导航和图片批次不会生成分析正文或声明已看图；每次读取仍核对完整事实、任务和成功资产绑定。"}


def read_frame_batch(workspace, batch=0, batch_size=20):
    """One viewing queue for both chapters, with every successful frame retained."""
    if type(batch_size) is not int or not 1 <= batch_size <= 20:
        raise AnalysisBundleError("frame batch size must be an integer from 1 to 20")
    if type(batch) is not int or batch < 0:
        raise AnalysisBundleError("frame batch is out of range")
    state, bundle = _load_workspace(workspace)
    frames = report._overview_highlight_frames(bundle["facts"])
    batch_count = (len(frames) + batch_size - 1) // batch_size
    if batch >= max(1, batch_count):
        raise AnalysisBundleError("frame batch is out of range")
    # Manifest paths are the verified images, not a guessed report-relative path.
    paths = {asset["frame_ref"]: asset["path"] for asset in
             bundle["manifest"].get("analysisContract", {}).get("visualAssets", [])}
    if not paths:
        paths = {frame["frame_ref"]: frame.get("image_path", "")
                 for material in bundle["units"].get("material_deep_dive", {}).get("evidence", {}).get("materialFacts", [])
                 for frame in material.get("highlightFrames", []) if frame.get("available")}
    rows, material_offsets = [], {}
    for index, frame in enumerate(frames):
        mid = frame["material_id"]
        offset = material_offsets.get(mid, 0)
        material_offsets[mid] = offset + 1
        if not batch * batch_size <= index < (batch + 1) * batch_size:
            continue
        image_path = paths.get(frame["frame_ref"])
        if not image_path:
            raise AnalysisBundleError(f"successful image has no bound path: {frame['frame_ref']}")
        rows.append({"frame_ref": frame["frame_ref"], "materialPart": f"material-{mid}",
                     "image_path": str((bundle["root"] / image_path).resolve()),
                     "frame_type": frame["frame_type"], "second": frame.get("second"),
                     "highlightIndex": index, "materialObservationIndex": offset})
    highlight = _workspace_task(workspace, state, bundle, "highlight") if frames else {}
    schema = highlight.get("outputSchema", {}).get("properties", {}).get("highlightDashboard", {}).get("properties", {}).get("frameUnderstanding", {}).get("items", {})
    return {"binding": state["binding"], "batch": batch, "batchSize": batch_size,
            "batchCount": batch_count, "totalSuccessfulFrames": len(frames),
            "nextBatch": batch + 1 if batch + 1 < batch_count else None,
            "frames": rows, "understandingSchema": schema,
            "writeTargets": {"understanding": "highlight.json#/content/highlightDashboard/frameUnderstanding",
                             "observation": "<materialPart>.json#/content/frame_observations",
                             "viewedDeclaration": "highlight.json#/viewedFrameRefs"},
            "readingRule": "逐张查看本批全部原图，同次独立完成两章对应观察；按 frame_ref 定位草稿，索引只对应初始骨架，编辑重排后以引用为准。",
            "responseRule": "每图保留 frame_ref，直接给必填字段；短句、不另写章节总结，单个画面描述约25–40字。不得因回复预算省略成功帧或必填字段；输出截断时减小 batch-size 并补齐未返回帧。",
            "completionRule": "实际看图后才追加 viewedFrameRefs；无法理解仍记录已查看并写 unavailable 与原因。全部批次完成后再做整批分类；两套分类各自覆盖成功帧全集。"}


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
