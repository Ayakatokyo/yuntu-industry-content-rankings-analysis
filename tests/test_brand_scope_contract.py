"""All chapters use the same explicit, run-local brand scope."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from jsonschema import Draft202012Validator
from PIL import Image
import yuntu_analysis as preparation
import yuntu_report as report
import yuntu_presentation as presentation
import yuntu_top_materials as top


class BrandScopeContractTests(unittest.TestCase):
    def prepare(self, root, filters):
        records = [
            {'material_id': '101', 'rank': 1, 'title': '万益蓝与镜头牌相机联名',
             'metrics': {'show_cnt': 200, 'ctr': .1, 'cvr': .03, 'play_3s_rate': .5}},
            {'material_id': '102', 'rank': 2, 'title': '五个女博士',
             'metrics': {'show_cnt': 100, 'ctr': .2, 'cvr': .02, 'play_3s_rate': .4}},
        ]
        details = root / 'normalized/detail-records'
        details.mkdir(parents=True)
        (root / 'normalized/list-records.json').write_text(json.dumps(records))
        (details / '101.json').write_text(json.dumps({'material_id': '101', 'script_text': '相机画面清晰。'}))
        (root / 'batch-manifest.json').write_text(json.dumps({
            'filters': filters, 'selectedMaterials': [{'material_id': '101', 'rank': 1,
            'detailRecordPath': 'normalized/detail-records/101.json'}],
            'rankingRuns': {'query': {'normalizedPath': 'normalized/list-records.json'}}}))
        image = root / 'highlights/101/01-000s.jpg'
        image.parent.mkdir(parents=True)
        Image.new('RGB', (8, 8), 'white').save(image, 'JPEG')
        preparation.write_highlights_manifest(root, {'101': [{
            'frame_ref': 'highlight:101:cover:0', 'frame_type': 'cover', 'second': 0,
            'is_cover': True, 'available': True, 'relative_path': 'highlights/101/01-000s.jpg'}]})
        output = root / 'analysis' 
        preparation.prepare_analysis(input_dir=root, output_dir=output, local_only=True)
        return (json.loads((output / 'report-data.json').read_text()),
                json.loads((output / 'yuntu-ai-analysis.schema.json').read_text()))

    def test_missing_brand_configuration_never_uses_food_brand_defaults(self):
        for brands in (None, []):
            with self.subTest(brands=brands):
                result = top.build_top_material_combination([
                    {'material_id': '1', 'title': '万益蓝五个女博士燕之屋',
                     'metrics': {'show_cnt': 100}}], brands=brands)
                self.assertEqual(result['brands'], {})
                self.assertEqual(result['classificationRules'], [])
                self.assertEqual(result['overall']['candidateCount'], 1)
                self.assertEqual(top.classify_brand('万益蓝', brands=brands)['source'], 'not_configured')

    def test_all_industry_has_only_aggregate_in_every_chapter(self):
        with tempfile.TemporaryDirectory() as directory:
            facts, schema = self.prepare(Path(directory), {'industry': '3C', 'brand_scope_type': 'ALL_INDUSTRY'})
        self.assertEqual(facts['brandRankingFacts']['brands'], {})
        self.assertEqual(facts['chapter02Facts']['scopeOrder'], ['all'])
        self.assertEqual(facts['chapter02AiFacts']['scopeOrder'], ['all'])
        self.assertEqual(facts['scriptFacts']['brandScopeOrder'], [])
        self.assertEqual(list(facts['comparisonFacts']['scopes']), ['all'])
        self.assertEqual(list(facts['hotMaterialFacts']), ['all'])
        self.assertEqual(facts['brandScope']['missingReason'], 'brands_not_specified')
        self.assertEqual(facts['summaryMetrics']['candidateCount'], 2)
        self.assertEqual(facts['chapter02Facts']['all']['sampleCount'], 2)
        highlight = schema['properties']['highlightDashboard']['properties']['brands']['prefixItems']
        self.assertEqual([x['properties']['brand']['const'] for x in highlight], ['全品牌'])
        self.assertEqual(highlight[0]['properties']['groups']['items']['properties']['frame_refs']['items']['enum'],
                         ['highlight:101:cover:0'])
        Draft202012Validator.check_schema(schema)
        ranking = schema['properties']['topMaterialCombination']
        self.assertFalse(list(Draft202012Validator(ranking['properties']['brandConclusions']).iter_errors([])))
        self.assertTrue(list(Draft202012Validator(ranking['properties']['brandConclusions']).iter_errors([{'brand': '万益蓝'}])))
        self.assertEqual(ranking['properties']['allBrandsConclusion']['properties']['classificationSource'], {'const': 'scope_aggregate'})

    def test_specified_brand_names_are_deduplicated_and_empty_scopes_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            facts, schema = self.prepare(Path(directory), {'brand_scope_type': 'SPECIFIED_BRANDS',
                'brands': [' 万益蓝 ', '镜头牌', '', '万益蓝', '无样本', None]})
        self.assertEqual(facts['filters']['brands'], ['万益蓝', '镜头牌', '无样本'])
        self.assertEqual(facts['chapter02AiFacts']['scopeOrder'], ['all', '万益蓝', '镜头牌', '无样本'])
        self.assertEqual(facts['scriptFacts']['brandScopeOrder'], ['万益蓝', '镜头牌', '无样本'])
        self.assertEqual(facts['brandRankingFacts']['brands']['无样本']['missingReason'], 'no_matching_material_in_scope')
        self.assertEqual(facts['chapter02Facts']['无样本']['sampleCount'], 0)
        self.assertEqual(facts['brandRankingFacts']['brands']['万益蓝']['materials'], [{'material_id': '101'}])
        self.assertEqual(facts['brandRankingFacts']['brands']['镜头牌']['materials'], [{'material_id': '101'}])
        items = schema['properties']['topMaterialCombination']['properties']['brandConclusions']['prefixItems']
        self.assertEqual([x['properties']['brand']['const'] for x in items], ['万益蓝', '镜头牌', '无样本'])
        highlight = schema['properties']['highlightDashboard']['properties']['brands']['prefixItems']
        self.assertEqual([x['properties']['brand']['const'] for x in highlight], ['全品牌', '万益蓝', '镜头牌', '无样本'])
        self.assertEqual(highlight[-1]['properties']['groups']['maxItems'], 0)
        self.assertIn('missing_reason', highlight[-1]['required'])
        Draft202012Validator.check_schema(schema)

    def test_all_industry_discards_stale_specified_brands(self):
        with tempfile.TemporaryDirectory() as directory:
            facts, _ = self.prepare(Path(directory), {'brand_scope_type': 'ALL_INDUSTRY', 'brands': ['万益蓝']})
        self.assertEqual(facts['filters']['brands'], [])
        self.assertEqual(facts['chapter02AiFacts']['scopeOrder'], ['all'])

    def test_new_contract_rejects_extra_brand_conclusion_and_wrong_aggregate_source(self):
        facts = {'brandScope': {'version': 1, 'mode': 'all_industry', 'brands': []},
                 'filters': {'brands': []}, 'industryTop1000Facts': {'source_scope': 'industry_top1000'}}
        extra = {'topMaterialCombination': {'brandConclusions': [{'brand': '万益蓝'}]}}
        with self.assertRaisesRegex(report.YuntuReportError, 'brand'):
            report._validate_ranking_scope_contract(extra, facts)
        value = {'topMaterialCombination': {'brandConclusions': [], 'allBrandsConclusion': {
            'brand': '全品牌', 'classificationSource': 'runtime_title_rule'}}}
        with self.assertRaisesRegex(report.YuntuReportError, 'scope_aggregate'):
            report._validate_ranking_scope_contract(value, facts)

    def test_rendered_all_industry_report_uses_no_specified_brand_tabs(self):
        import test_yuntu_report
        analysis = test_yuntu_report.YuntuReportTests().analysis_json()
        combination = analysis['topMaterialCombination']
        aggregate = dict(combination['brandConclusions'][0])
        aggregate.update(brand='全品牌', classificationSource='scope_aggregate')
        combination['brandConclusions'] = []
        combination['allBrandsConclusion'] = aggregate
        facts = {'brandScope': {'version': 1, 'mode': 'all_industry', 'brands': []},
                 'filters': {'industry': '3C', 'brand_scope_type': 'ALL_INDUSTRY', 'brands': []}}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'analysis.json'
            path.write_text(json.dumps(analysis))
            report.render_report(analysis_json=path, output_dir=root / 'report', fact_pack=facts)
            rendered = (root / 'report/final-report.html').read_text()
            markdown = (root / 'report/final-report.md').read_text()
        self.assertIn('3C行业｜全行业', rendered)
        self.assertIn('data-brand-tab="全行业"', rendered)
        self.assertNotIn('data-brand-tab="五个女博士"', rendered)
        self.assertNotIn('data-brand-tab="万益蓝/WONDERLAB"', rendered)
        self.assertIn('### 全行业', markdown)

    def test_presentation_labels_aggregate_as_all_industry(self):
        facts = {'brandScope': {'version': 1, 'mode': 'all_industry', 'brands': [], 'aggregateLabel': '全行业'}}
        analysis = {'topMaterialCombination': {'brandConclusions': [], 'allBrandsConclusion': {'brand': '全品牌', 'dataSummary': '本行业汇总'}}}
        chapter = presentation._project_chapter01(analysis, facts)
        self.assertEqual(chapter['brandPanels'][0]['brand'], '全行业')


if __name__ == '__main__':
    unittest.main()
