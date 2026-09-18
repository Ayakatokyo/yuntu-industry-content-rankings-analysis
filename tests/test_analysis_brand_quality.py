"""Regression tests for the four issues observed in the fresh September 12 run."""
import copy
import html
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from jsonschema import Draft202012Validator
import yuntu_analysis as preparation
import yuntu_analysis_quality as quality
import yuntu_presentation as presentation
import yuntu_report as report
from yuntu_report_sections import render_script_insights
from yuntu_analysis_workspace import _merge, _part_schema, _parts


def script_facts(mid="101", text="早餐喝豆浆，配方有红豆，口感软糯。"):
    return preparation.build_script_facts(
        [{"material_id": mid, "script_text": text}], [{"material_id": mid}]) if mid else preparation.build_script_facts([], [])


def script_output(ids=None, available=True):
    return {"scriptInsights": [
        {"title": title, "summary": "早餐喝豆浆，配方有红豆，口感软糯。" * 12 if available else "本品牌未获取脚本文本，数据不足以判断。",
         "evidence": ["红豆"] if available else [], "material_ids": ids or []}
        for title in ("一二级内容公式：表达结构", "脚本文案：场景承接")],
        "keywordCloudReview": [], "keywordCloudInsight": {
            "oneSentenceConclusion": "脚本文本中以早餐承接豆浆。" if available else "本品牌缺少脚本文本，数据不足以判断。",
            "summary": "建议比较早餐先行与配方先行的版本，观察卖点是否易于复述。" * 5 if available else "本品牌缺少脚本文本，不能提炼关键词或卖点。",
            "sellingPoints": []}}


class BrandQualityTests(unittest.TestCase):
    def test_v4_requires_all_classification_fields_before_drafting(self):
        facts = self.quality_facts()
        facts["analysisQualityVersion"] = 4
        schema = preparation._analysis_output_schema(facts)["properties"]["highlightDashboard"]
        self.assertEqual(set(schema["required"]), {"brands", "frameUnderstanding", "standardClassification", "batchClassification"})
        frame_schema = schema["properties"]["frameUnderstanding"]["items"]
        self.assertIn("standard_category", frame_schema["required"])
        self.assertIn("category_reason", frame_schema["required"])
        self.assertEqual(schema["properties"]["standardClassification"]["properties"]["status"], {"const": "complete"})

    def test_v3_highlights_allow_one_to_three_distinct_items(self):
        facts = self.quality_facts()
        facts["analysisQualityVersion"] = 3
        brands = preparation._analysis_output_schema(facts)["properties"]["highlightDashboard"]["properties"]["brands"]
        for scope in brands["prefixItems"][:2]:
            fields = scope["properties"]["groups"]["items"]["properties"]
            for field in ("common_patterns", "derivative_directions"):
                validator = Draft202012Validator(fields[field])
                items = [{"title": f"观察角度{i}", "body": "用于校验结构要求的充分长度正文。" * 10,
                          "frame_refs": ["highlight:101:cover:0"]} for i in range(4)]
                for count in (1, 2, 3):
                    self.assertEqual(list(validator.iter_errors(items[:count])), [])
                for count in (0, 4):
                    self.assertTrue(list(validator.iter_errors(items[:count])))
                self.assertTrue(list(validator.iter_errors([items[0], items[0]])))
        empty = brands["prefixItems"][2]
        self.assertEqual(list(Draft202012Validator(empty).iter_errors({
            "brand": "无样本", "groups": [], "missing_reason": "该品牌未获取成功画面，数据不足以判断。"})), [])

    def test_v2_highlights_keep_their_original_count_contract(self):
        schema = preparation._analysis_output_schema(self.quality_facts())
        groups = schema["properties"]["highlightDashboard"]["properties"]["brands"]["prefixItems"][0]["properties"]["groups"]
        for field in ("common_patterns", "derivative_directions"):
            self.assertEqual(groups["items"]["properties"][field]["minItems"], 1)
            self.assertNotIn("maxItems", groups["items"]["properties"][field])

    def quality_facts(self):
        sf = script_facts()
        sf.update(brandScopeOrder=["豆浆", "无样本"], brandScopes={"豆浆": script_facts(), "无样本": script_facts(mid=None)})
        return {"analysisQualityVersion": 2, "filters": {"brands": ["豆浆", "无样本"]},
                "chapter02AiFacts": {"scopeOrder": ["all"], "all": {"sampleCount": 1}},
                "scriptFacts": sf, "materialFacts": [{"material_id": "101", "title": "豆浆",
                "highlightFrames": [{"frame_ref": "highlight:101:cover:0", "frame_type": "cover", "second": 0, "available": True}]}]}

    def test_render_projection_retains_the_same_quality_schema(self):
        facts = self.quality_facts()
        without_assets = preparation._analysis_output_schema(facts)
        facts["visualAssets"] = [{"available": True}]
        self.assertEqual(without_assets, preparation._analysis_output_schema(facts))
        self.assertIn("highlightDashboard", without_assets["required"])

    def test_highlight_schema_requires_all_brands_and_explicit_empty_reason(self):
        schema = preparation._analysis_output_schema(self.quality_facts())["properties"]["highlightDashboard"]["properties"]["brands"]
        item = {"title": "主体识别", "body": "这是用于验证长度的画面分析。" * 10, "frame_refs": ["highlight:101:cover:0"]}
        group = {"category": "product", "frame_refs": ["highlight:101:cover:0"], "common_patterns": [item], "derivative_directions": [item]}
        values = [{"brand": "全品牌", "groups": [group]}, {"brand": "豆浆", "groups": [group]},
                  {"brand": "无样本", "groups": [], "missing_reason": "该品牌未获取成功画面，数据不足以判断。"}]
        validator = Draft202012Validator(schema)
        self.assertEqual(list(validator.iter_errors(values)), [])
        self.assertTrue(list(validator.iter_errors(values[:1])))
        values[-1].pop("missing_reason")
        self.assertTrue(list(validator.iter_errors(values)))

    def test_audience_concise_summaries_are_accepted_but_missing_script_brands_are_rejected(self):
        schema = preparation._analysis_output_schema(self.quality_facts())
        audience = schema["properties"]["chapter02Insights"]
        value = {"scopeOrder": ["all"], "scopes": {"all": {key: {
            "title": "观察", "summary": "只描述标签。", "evidence": ["早餐"], "material_ids": ["101"]}
            for key in ("audienceSummary", "marketingSummary")}}}
        self.assertEqual(list(Draft202012Validator(audience).iter_errors(value)), [])
        self.assertTrue(list(Draft202012Validator(schema["properties"]["scriptBrandInsights"]).iter_errors({})))

    def test_all_industry_schema_does_not_require_brand_script_output(self):
        facts = self.quality_facts()
        facts["filters"]["brands"] = []
        facts["scriptFacts"]["brandScopeOrder"] = []
        facts["scriptFacts"]["brandScopes"] = {}

        schema = preparation._analysis_output_schema(facts)

        self.assertNotIn("scriptBrandInsights", schema["required"])
        self.assertNotIn("scriptBrandInsights", schema["properties"])
        self.assertFalse(any("brand" in part for part in _parts({"schema": schema, "facts": facts})))

    def test_script_evidence_never_quotes_visual_or_title_only_text(self):
        facts = {"analysisQualityVersion": 2, "scriptFacts": script_facts()}
        facts["scriptFacts"]["materials"][0]["content_formula"] = {"sources": {"title": {"text": "仅标题证据"}, "visual": {"text": "仅画面证据"}}}
        for quote in ("仅标题证据", "仅画面证据"):
            value = script_output(["101"])
            value["scriptInsights"][0]["evidence"] = [quote]
            with self.assertRaises(report.YuntuReportError):
                report._validate_script_insights(value, facts)

    def test_generated_sentences_have_no_invented_formula_membership(self):
        evidence = preparation._script_evidence_projection("101", "早餐喝豆浆。配方有红豆。", [{"level2": "使用场景"}])
        self.assertTrue(all(not item["level2"] for item in evidence))

    def test_nested_script_terms_override_old_whole_sentence_targets(self):
        fact = {"material_id": "101", "script": {
            "text": "早餐喝豆浆，配方有红豆，口感软糯。",
            "formula": [{"level1": "商品卖点", "level2": "成分配方原料"}, {"level1": "商品卖点", "level2": "使用感受和服务体验"}],
            "evidence": [{"level2": "成分配方原料", "sentence": "早餐喝豆浆，配方有红豆，口感软糯。", "evidenceRef": "script:101:text:whole"}]},
            "content_formula": {"sources": {"script": {"detail": {"42": ["红豆"], "39": ["软糯"]}}, "title": {"detail": {"42": ["早餐"]}}}}}
        result = presentation._chapter05_script_projection(fact, {})
        self.assertEqual([e["sentence"] for e in result["evidence"]], ["红豆", "软糯"])
        self.assertEqual(result["formula"][0]["evidenceRefs"], ["script:101:text:红豆"])
        self.assertEqual(result["formula"][1]["evidenceRefs"], ["script:101:text:软糯"])
        self.assertTrue(set(e["evidenceRef"] for e in result["evidence"]).issubset(result["evidenceRefs"]))

    def test_formula_without_source_terms_never_targets_whole_script(self):
        result = presentation._chapter05_script_projection({"material_id": "101", "script": {
            "text": "使用场景，商品卖点。", "formula": [{"level1": "商品卖点", "level2": "使用场景"}],
            "evidence": [{"sentence": "使用场景，商品卖点。", "level2": "使用场景", "evidenceRef": "script:101:text:whole"}]}}, {})
        self.assertEqual(result["evidence"], [])
        self.assertFalse(result["formula"][0].get("evidenceRefs"))

    def test_schema_accepts_concise_analysis_without_character_quotas(self):
        props = {"scriptInsights": {"type": "array", "minItems": 2, "maxItems": 2, "items": preparation._analysis_insight_schema()},
                 "keywordCloudReview": {"type": "array", "items": preparation._keyword_cloud_review_schema()},
                 "keywordCloudInsight": preparation._keyword_cloud_insight_schema()}
        schema = quality.script_scope_schema(props, script_facts())
        value = script_output(["101"])
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(value)), [])
        value["scriptInsights"][0]["summary"] = "早餐场景连接配方卖点。"
        value["keywordCloudInsight"]["summary"] = "品质词更集中。"
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(value)), [])

    def test_highlight_schema_keeps_prose_nonempty_without_length_or_item_quotas(self):
        facts = self.quality_facts()
        facts["analysisQualityVersion"] = 4
        dashboard = preparation._analysis_output_schema(facts)["properties"]["highlightDashboard"]["properties"]
        groups = dashboard["brands"]["prefixItems"][0]["properties"]["groups"]
        fields = groups["items"]["properties"]

        for name in ("common_patterns", "derivative_directions"):
            self.assertEqual(fields[name]["minItems"], 1)
            self.assertNotIn("minLength", fields[name]["items"]["properties"]["body"])

    def test_brand_script_rejects_foreign_ids_and_unquoted_evidence(self):
        facts = {"analysisQualityVersion": 2, "scriptFacts": script_facts()}
        for ids, evidence in ((["999"], ["红豆"]), (["101"], ["脚本事实包"]), (["101"], ["另一品牌"] )):
            value = script_output(ids)
            value["scriptInsights"][0]["evidence"] = evidence
            with self.assertRaises(report.YuntuReportError):
                report._validate_script_insights(value, facts)

    def test_empty_brand_uses_no_aggregate_evidence(self):
        facts = {"analysisQualityVersion": 2, "scriptFacts": script_facts(mid=None), "selectedMaterials": [{"material_id": "999"}]}
        value = script_output(available=False)
        for insight in value["scriptInsights"]:
            insight["summary"] = "本品牌没有可用脚本文本。"
        value["keywordCloudInsight"]["summary"] = "本品牌没有可用关键词。"
        report._validate_script_insights(value, facts)
        value["scriptInsights"][0]["material_ids"] = ["999"]
        with self.assertRaises(report.YuntuReportError):
            report._validate_script_insights(value, facts)

    def test_brand_panels_have_unique_controls_and_scoped_content(self):
        facts = script_facts()
        facts.update(brandScopeOrder=["豆浆", "无样本"], brandScopes={"豆浆": script_facts(), "无样本": script_facts(mid=None)})
        value = script_output(["101"])
        value["scriptBrandInsights"] = {"豆浆": script_output(["101"]), "无样本": script_output(available=False)}
        result = presentation._project_chapter03(value, {"scriptFacts": facts})
        json.dumps(result)  # no circular aggregate object
        panels = result["scriptDashboard"]["brandPanels"]
        self.assertEqual(panels[-1]["scriptDashboard"]["materials"], [])
        self.assertEqual(panels[-1]["scriptDashboard"]["keywordCloudPanel"]["keywords"], [])
        markup = render_script_insights(script_facts=facts, script_dashboard=result["scriptDashboard"], esc=lambda v: html.escape(str(v), quote=True))
        from html.parser import HTMLParser
        class Tags(HTMLParser):
            def __init__(self):
                super().__init__(); self.ids=[]; self.controls=[]
            def handle_starttag(self, tag, attrs):
                attrs=dict(attrs)
                if "id" in attrs: self.ids.append(attrs["id"])
                if "aria-controls" in attrs: self.controls.append(attrs["aria-controls"])
        tags=Tags(); tags.feed(markup)
        self.assertEqual(len(tags.ids),len(set(tags.ids)))
        self.assertTrue(set(tags.controls).issubset(tags.ids))
        self.assertIn("无样本",markup)
        self.assertIn("数据不足以判断",markup)

    def test_brand_drafts_assemble_without_rewriting(self):
        parts=[{"key":"script", "outputFields":list(quality.SCRIPT_FIELDS)}, {"key":"script-brand-0", "brand":"豆浆"}]
        value=script_output(["101"])
        drafts={key:{"content":copy.deepcopy(value)} for key in ("script", "script-brand-0")}
        combined=_merge(parts,drafts)
        self.assertEqual(combined["scriptBrandInsights"]["豆浆"],value)
        self.assertEqual(combined["scriptInsights"],value["scriptInsights"])


if __name__ == "__main__":
    unittest.main()
