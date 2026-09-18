"""Deterministic model reading views; canonical facts stay intact for validation.

Full source facts stay unchanged; concise views disclose omitted display tails.
No business conclusions, cross-chapter evidence or model calls.
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


def concise_reading_view(source):
    """Preserve population statistics, disclose every trimmed display-only tail."""
    result = deepcopy(source)
    def trim_ranking_ids(value):
        if isinstance(value, dict):
            if 'materialIds' in value:
                ids = value['materialIds']
                value['materialReadingCoverage'] = {'sourceCount': len(ids), 'includedCount': min(10, len(ids)),
                    'omittedCount': max(0, len(ids) - 10), 'selection': 'original_order_first_10'}
                value['materialIds'] = ids[:10]
            for key, child in list(value.items()):
                if key not in {'hotMaterialFacts', 'hotMaterialRule'}:
                    trim_ranking_ids(child)
        elif isinstance(value, list):
            for child in value:
                trim_ranking_ids(child)
    if 'current' in result or 'comparisonFacts' in result:
        trim_ranking_ids(result)
    scopes = result.get('chapter02AiFacts', {})
    used_ids = set()
    for name in scopes.get('scopeOrder', []):
        scope = scopes[name]
        if 'topMaterialIds' in scope:
            ids = scope['topMaterialIds']
            scope['materialReadingCoverage'] = {'sourceCount': len(ids), 'includedCount': min(5, len(ids)),
                'omittedCount': max(0, len(ids) - 5), 'selection': 'original_order_first_5'}
            scope['topMaterialIds'] = ids[:5]
            used_ids.update(ids[:5])
        for category in scope.get('marketingDashboard', {}).get('categories', []):
            if 'tags' in category:
                tags = category['tags']
                category['tagReadingCoverage'] = {'sourceCount': len(tags), 'includedCount': min(5, len(tags)),
                    'omittedCount': max(0, len(tags) - 5), 'selection': 'original_order_first_5'}
                category['tags'] = tags[:5]
    if 'materialsById' in result:
        result['materialsById'] = {mid: row for mid, row in result['materialsById'].items() if mid in used_ids}
    return result


READING_RULES = {
    "ranking_brand": "scopedFacts 保留全范围聚合、比较和完整爆款事实。聚合materialIds仅给原顺序前10项并附materialReadingCoverage，不改变样本或统计；这些ID仅供引用，不代表总体特征。完整索引留在factInput供定向溯源。",
    "audience_marketing": "scopedFacts 保留全部范围、原统计和全部人群桶。各范围素材与营销类别tags默认只读原顺序前5项，ReadingCoverage标明省略量；分母和类别share仍是全量统计，不能用读取子集重新求占比。需要长尾证据时定向读取factInput，只引用本范围素材。",
    "script_insights": "scopedFacts 是本范围全部脚本、公式、关键词、覆盖率和证据；不需要再次读取包含其他品牌的 script-input.json。",
    "highlight": "scopedFacts 保留完整图片清单。按素材查看成功 JPEG，同次查看填写本章 frameUnderstanding 和对应 material 草稿的 frame_observations；完成全部理解后才做整批分类。",
    "material_deep_dive": "scopedFacts 只含当前素材完整脚本、引用和帧清单；secondLevelBreakdown 曲线仍在正式事实包供报告展示，不属于模型分析输入。不能从第三章借用脚本分析结论。",
}
