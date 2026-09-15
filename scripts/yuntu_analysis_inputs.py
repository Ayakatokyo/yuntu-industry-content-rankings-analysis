"""Deterministic model reading views; canonical facts stay intact for validation.

No sampling, business conclusions, cross-chapter evidence or model calls.
"""
from copy import deepcopy
import json


def json_bytes(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _aggregate_view(value):
    result = deepcopy(value)
    # Chapter 01 explicitly disallows individual-material analysis. Preserve
    # every legal reference, metric, sample count, date and missing-data flag.
    if isinstance(result, dict) and "materials" in result:
        result["materialIds"] = [str(row["material_id"]) for row in result.pop("materials")]
    return result


def ranking_view(evidence):
    result = deepcopy(evidence)
    for key in ("current", "previousPeriod", "industryBenchmark", "industryTop1000Facts"):
        if key in result:
            result[key] = _aggregate_view(result[key])
    for scope in result.get("comparisonFacts", {}).get("scopes", {}).values():
        if "current" in scope:
            scope["current"] = _aggregate_view(scope["current"])
    for brand, scope in result.get("brandRankingFacts", {}).get("brands", {}).items():
        result["brandRankingFacts"]["brands"][brand] = _aggregate_view(scope)
    # hotMaterialFacts is intentionally untouched: threshold, all qualifying
    # materials, interval min/max/raw and auxiliary metrics are model evidence.
    return result


def audience_view(evidence):
    result = deepcopy(evidence)
    scopes = result["chapter02AiFacts"]
    materials = {}
    for name in scopes["scopeOrder"]:
        for row in scopes[name].get("topMaterials", []):
            mid = str(row["material_id"])
            # A different row with the same ID must not silently disappear.
            # Historical/nonstandard inputs fall back to their complete facts.
            if mid in materials and materials[mid] != row:
                return deepcopy(evidence)
            materials[mid] = row
    for name in scopes["scopeOrder"]:
        if "topMaterials" in scopes[name]:
            scopes[name]["topMaterialIds"] = [str(row["material_id"]) for row in scopes[name].pop("topMaterials")]
    result["materialsById"] = materials
    return result


def model_reading_view(bundle, part):
    evidence = bundle["units"][part["unit"]]["evidence"]
    unit = part["unit"]
    if unit == "ranking_brand":
        return ranking_view(evidence)
    if unit == "audience_marketing":
        return audience_view(evidence)
    if unit == "script_insights":
        facts = evidence["scriptFacts"]
        if "brand" in part:
            return deepcopy(facts["brandScopes"][part["brand"]])
        return {key: deepcopy(value) for key, value in facts.items()
                if key not in ("brandScopes", "brandScopeOrder")}
    if unit == "material_deep_dive":
        fact = next(row for row in evidence["materialFacts"]
                    if str(row["material_id"]) == part["materialId"])
        # Curves are displayed deterministically in chapter 05, never analyzed
        # by the model. Keep script and image evidence byte-for-byte in value.
        return {key: deepcopy(value) for key, value in fact.items()
                if key != "secondLevelBreakdown"}
    return deepcopy(evidence)


READING_RULES = {
    "ranking_brand": "scopedFacts 保留全范围聚合、比较、完整 materialIds 和完整爆款事实；仅省去禁止个案分析的聚合 materials 明细，不改变样本或统计。materialIds 仅用于引用。",
    "audience_marketing": "scopedFacts 的 chapter02AiFacts 保留全部范围、统计、标签及其顺序。若有 materialsById，各范围 topMaterialIds 按原顺序指向其中完整素材对象，等价于原 topMaterials；只能引用本范围 ID，不把 materialsById 全表当成品牌范围。",
    "script_insights": "scopedFacts 是本范围全部脚本、公式、关键词、覆盖率和证据；不需要再次读取包含其他品牌的 script-input.json。",
    "highlight": "scopedFacts 保留完整图片清单。按素材查看成功 JPEG，同次查看填写本章 frameUnderstanding 和对应 material 草稿的 frame_observations；完成全部理解后才做整批分类。",
    "material_deep_dive": "scopedFacts 只含当前素材完整脚本、引用和帧清单；secondLevelBreakdown 曲线仍在正式事实包供报告展示，不属于模型分析输入。不能从第三章借用脚本分析结论。",
}
