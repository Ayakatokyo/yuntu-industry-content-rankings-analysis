"""Versioned, scope-aware writing requirements shared by tasks and validators.

These are structural floors, not a claim that length proves analytical quality.
"""
from copy import deepcopy
from yuntu_highlight_export import match_brands_from_title

QUALITY_VERSION = 4
SCRIPT_FIELDS = ("scriptInsights", "keywordCloudReview", "keywordCloudInsight")
WRITING_RUBRIC = "有事实的分析须说明具体观察、业务含义、可执行建议及验证边界；不得重复填充。无事实时明确缺口，不借用其他品牌结论。"


def enabled(facts):
    return facts.get("analysisQualityVersion", 0) >= 2


def script_scope_schema(properties, facts):
    result = {"type": "object", "additionalProperties": False,
              "required": list(SCRIPT_FIELDS),
              "properties": {k: deepcopy(properties[k]) for k in SCRIPT_FIELDS}}
    props = result["properties"]
    available = bool(facts.get("coverage", {}).get("script"))
    props["scriptInsights"]["items"]["properties"]["summary"]["minLength"] = 180 if available else 12
    ids = [str(m["material_id"]) for m in facts.get("materials", [])]
    props["scriptInsights"]["items"]["properties"]["material_ids"] = {
        "type": "array", "uniqueItems": True, "items": {"enum": ids} if ids else False,
        **({"minItems": 1} if available else {})}
    if not available:
        props["scriptInsights"]["items"]["properties"]["evidence"]["maxItems"] = 0
    props["keywordCloudInsight"]["properties"]["summary"]["minLength"] = 100 if available else 12
    props["keywordCloudInsight"]["properties"]["sellingPoints"]["items"]["properties"]["description"]["minLength"] = 60
    return result


def apply_schema(schema, facts):
    if not enabled(facts):
        return schema
    props = schema["properties"]
    scopes = props["chapter02Insights"]["properties"]["scopes"]["properties"]
    for key in list(scopes):
        scopes[key] = deepcopy(scopes[key])
        available = bool(facts["chapter02AiFacts"][key].get("sampleCount"))
        for item in scopes[key]["properties"].values():
            item["properties"]["summary"]["minLength"] = 180 if available else 12
    script_facts = facts.get("scriptFacts", {})
    if "scriptInsights" in props:
        base = deepcopy(props)
        props.update(script_scope_schema(base, script_facts)["properties"])
        order = script_facts.get("brandScopeOrder", [])
        props["scriptBrandInsights"] = {
            "type": "object", "additionalProperties": False, "required": order,
            "properties": {b: script_scope_schema(base, script_facts["brandScopes"][b]) for b in order}}
        schema["required"].append("scriptBrandInsights")
    if "highlightDashboard" in props:
        dashboard = props["highlightDashboard"]["properties"]
        if facts.get("analysisQualityVersion", 0) >= 4:
            props["highlightDashboard"]["required"] = ["brands", "frameUnderstanding", "standardClassification", "batchClassification"]
            understanding = dashboard["frameUnderstanding"]["items"]
            understanding["required"] += ["standard_category", "category_reason"]
            understanding["properties"].update(
                standard_category={"enum": ["portrait", "product", "other"]},
                category_reason={"type": "string", "minLength": 12})
            dashboard["standardClassification"]["properties"]["status"] = {"const": "complete"}
        original = dashboard["brands"]["items"]
        brands = ["全品牌", *facts.get("filters", {}).get("brands", [])]
        scopes = []
        for brand in brands:
            item = deepcopy(original)
            item["properties"]["brand"] = {"const": brand}
            refs = [f.get("frame_ref") or f"highlight:{m['material_id']}:{f.get('frame_type', 'click_peak')}:{f.get('second', 0)}" for m in facts.get("materialFacts", [])
                    if brand == "全品牌" or brand in match_brands_from_title(m.get("title"), brands[1:])
                    for f in m.get("highlightFrames", []) if f.get("available")]
            item["properties"]["missing_reason"] = {"type": "string"}
            groups = item["properties"]["groups"]
            if not refs:
                groups.update(minItems=0, maxItems=0)
                item["required"].append("missing_reason")
                item["properties"]["missing_reason"]["minLength"] = 12
            else:
                gp = groups["items"]["properties"]
                gp["frame_refs"]["items"] = {"enum": refs}
                for key in ("common_patterns", "derivative_directions"):
                    gp[key]["minItems"] = 2 if facts.get("analysisQualityVersion", 0) >= 3 else 1
                    if facts.get("analysisQualityVersion", 0) >= 3:
                        gp[key].update(maxItems=3, uniqueItems=True)
                    gp[key]["items"]["properties"]["body"]["minLength"] = 100
            scopes.append(item)
        dashboard["brands"] = {"type": "array", "prefixItems": scopes,
                               "items": False, "minItems": len(scopes), "maxItems": len(scopes)}
        if facts.get("analysisQualityVersion", 0) >= 4:
            dashboard["standardClassification"]["properties"]["groups"] = deepcopy(scopes[0]["properties"]["groups"])
    return schema
