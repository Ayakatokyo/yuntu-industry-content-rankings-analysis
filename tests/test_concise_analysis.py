"""Model input usability and semantic checks, with scope gates intact."""
import copy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from test_analysis_stability import fixture
from test_analysis_brand_quality import script_facts
import yuntu_analysis_workspace as workspace
import yuntu_report as report


def test_new_draft_has_required_skeleton_but_cannot_pass_without_model_text(tmp_path):
    _, _, manifest = fixture(tmp_path / 'facts')
    root = tmp_path / 'drafts'
    workspace.begin_workspace(manifest, root)
    draft = json.loads((root / 'material-101.json').read_text())
    assert draft['content']['material_id'] == '101'
    assert draft['content']['scriptAnalysis']['conclusion'] is None
    assert draft['viewedFrameRefs'] == []
    result = workspace.check_workspace(root, 'material-101')
    assert result['valid'] is False


def test_task_read_is_bounded_reconstructable_and_bound(tmp_path):
    from analysis_task_io import restore_task_pages, pretty_json
    _, _, manifest = fixture(tmp_path / 'facts')
    root = tmp_path / 'drafts'
    workspace.begin_workspace(manifest, root)
    first = workspace.read_task(root, 'material-101', 0)
    pages = [first['records']]
    for page in range(1, first['pageCount']):
        response = workspace.read_task(root, 'material-101', page)
        assert len(pretty_json(response).encode()) < 12500
        pages.append(response['records'])
    task = restore_task_pages(pages)
    assert '早餐' in task['scopedFacts']['script']['text']
    assert task['outputSkeleton']['scriptAnalysis']['conclusion'] is None
    path = root / 'material-101.task.json'
    path.write_text(path.read_text() + ' ')
    with pytest.raises(ValueError, match='model task input'):
        workspace.read_task(root, 'material-101', 0)


def two_insights():
    return {'scriptInsights': [{'title': title, 'summary': '早餐表达适合测试。',
            'evidence': ['早餐'], 'material_ids': ['101']} for title in ('一二级内容公式：场景', '脚本文案：表达')]}


@pytest.mark.parametrize('limitation', ['尚不足以代表行业普遍规律。', '本批次样本尚不足以代表行业普遍规律。',
                                      '不能据此推断因果关系。'])
def test_explicit_negative_scope_clause_passes_without_exempting_neighbor_claims(limitation):
    facts = {'analysisQualityVersion': 4, 'scriptFacts': script_facts()}
    facts['scriptFacts'].pop('keywordCloud', None)
    analysis = two_insights()
    analysis['scriptInsights'][0]['summary'] = '早餐表达值得测试。' + limitation
    report._validate_script_insights(analysis, facts)
    analysis['scriptInsights'][0]['summary'] += '因此导致转化提升。'
    with pytest.raises(report.YuntuReportError, match='unsupported claim'):
        report._validate_script_insights(analysis, facts)


def test_script_check_returns_all_independent_quote_and_claim_errors():
    facts = {'analysisQualityVersion': 4, 'scriptFacts': script_facts()}
    facts['scriptFacts'].pop('keywordCloud', None)
    analysis = two_insights()
    analysis['scriptInsights'][0]['evidence'] = ['不存在的原文']
    analysis['scriptInsights'][0]['summary'] = '导致转化提升。'
    analysis['scriptInsights'][1]['evidence'] = ['另一句不存在']
    with pytest.raises(report.YuntuReportError) as error:
        report._validate_script_insights(analysis, facts)
    assert 'script insight 1.evidence' in str(error.value)
    assert 'script insight 1.summary' in str(error.value)
    assert 'script insight 2.evidence' in str(error.value)


def test_concise_audience_keeps_population_and_marks_omitted_tail():
    from yuntu_analysis_inputs import concise_reading_view
    rows = [{'material_id': str(i), 'title': str(i)} for i in range(12)]
    source = {'chapter02AiFacts': {'scopeOrder': ['all'], 'all': {
        'sampleCount': 1200, 'topMaterialIds': [str(i) for i in range(12)],
        'audienceDashboard': {'dimensions': {'age': {'buckets': [{'bucket': 'other', 'share': .2}]}}},
        'marketingDashboard': {'occurrenceCount': 100, 'categories': [
            {'category': '卖点', 'share': .4, 'occurrenceCount': 40, 'tags': [
                {'tag': str(i), 'count': 1} for i in range(20)]}]}}},
        'materialsById': {row['material_id']: row for row in rows}}
    before = copy.deepcopy(source)
    view = concise_reading_view(source)
    assert source == before
    scope = view['chapter02AiFacts']['all']
    assert scope['sampleCount'] == 1200
    assert scope['audienceDashboard'] == source['chapter02AiFacts']['all']['audienceDashboard']
    assert len(scope['topMaterialIds']) == 5
    assert scope['materialReadingCoverage'] == {'sourceCount': 12, 'includedCount': 5, 'omittedCount': 7, 'selection': 'original_order_first_5'}
    category = scope['marketingDashboard']['categories'][0]
    assert category['occurrenceCount'] == 40
    assert category['share'] == .4
    assert len(category['tags']) == 5
    assert category['tagReadingCoverage']['omittedCount'] == 15


def test_concise_rank_ids_do_not_change_aggregates_or_script_scope():
    from yuntu_analysis_inputs import concise_reading_view
    source = {'current': {'materialIds': [str(i) for i in range(1000)], 'sampleCount': 1000,
                          'metrics': {'ctr': {'median': .03}}}}
    view = concise_reading_view(source)
    assert view['current']['metrics'] == source['current']['metrics']
    assert view['current']['sampleCount'] == 1000
    assert len(view['current']['materialIds']) == 10
    assert view['current']['materialReadingCoverage']['omittedCount'] == 990
    scripts = {'materials': [{'text': '原文'}], 'keywordCloud': {'materialIds': list(range(100))}}
    assert concise_reading_view(scripts) == scripts


def test_ranking_trimming_never_trims_hot_material_evidence():
    from yuntu_analysis_inputs import concise_reading_view
    source = {'current': {'materialIds': [str(i) for i in range(30)]},
              'hotMaterialFacts': {'materialIds': [str(i) for i in range(30)], 'qualifyingCount': 30}}
    result = concise_reading_view(source)
    assert len(result['current']['materialIds']) == 10
    assert result['hotMaterialFacts'] == source['hotMaterialFacts']
