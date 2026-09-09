"""Stable HTML renderers for independently migrated Yuntu report sections."""

import json

from yuntu_presentation import content_formula_label


def _format_chapter01_exposure(value, *, signed=False):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return "不可用"
    value = float(value)
    if signed:
        if value == 0:
            return "0 次"
        prefix = "增加" if value > 0 else "减少"
        return f"{prefix} {_format_chapter01_exposure(abs(value))}"
    absolute = abs(value)
    if absolute >= 100000000:
        number, unit = absolute / 100000000, "亿"
    elif absolute >= 10000:
        number, unit = absolute / 10000, "万"
    elif absolute >= 1000:
        number, unit = absolute / 1000, "千"
    else:
        return f"{value:,.0f} 次"
    return f"{number:.1f} {unit}次"


def _format_chapter01_percentage(value, *, signed=False):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return "不可用"
    if signed and value > 0:
        return f"+{value:.2%}"
    return f"{value:.2%}"


def _chapter01_current_metric_value(fact, key):
    metrics = fact.get("metrics", {}) if isinstance(fact, dict) else {}
    metric = metrics.get(key, {}) if isinstance(metrics, dict) else {}
    if not isinstance(metric, dict):
        return None
    return metric.get("total" if key == "show_cnt" else "median")


def _chapter01_baseline_metric_value(fact, key):
    metrics = fact.get("metrics", {}) if isinstance(fact, dict) else {}
    metric = metrics.get(key, {}) if isinstance(metrics, dict) else {}
    if not isinstance(metric, dict):
        return None
    return metric.get("baseline")


def _chapter01_rate_against_current(current_fact, baseline_fact, key):
    current = _chapter01_current_metric_value(current_fact, key)
    baseline = _chapter01_baseline_metric_value(baseline_fact, key)
    if (
        not isinstance(current, (int, float))
        or isinstance(current, bool)
        or not isinstance(baseline, (int, float))
        or isinstance(baseline, bool)
        or current == 0
    ):
        return None
    return (baseline - current) / current


def _render_chapter01_metric_values(fact, *, esc, source="current", comparison_reference=None):
    if not isinstance(fact, dict):
        return ""
    labels = (
        ("show_cnt", "曝光总量", _format_chapter01_exposure),
        ("ctr", "CTR", _format_chapter01_percentage),
        ("cvr", "CVR", _format_chapter01_percentage),
        ("play_3s_rate", "3 秒完播率", _format_chapter01_percentage),
    )
    items = []
    for key, label, formatter in labels:
        value = (
            _chapter01_current_metric_value(fact, key)
            if source == "current"
            else _chapter01_baseline_metric_value(fact, key)
        )
        value_text = formatter(value)
        if source != "current" and isinstance(comparison_reference, dict):
            rate = _chapter01_rate_against_current(comparison_reference, fact, key)
            if rate is not None:
                value_text += f"（变化率 {_format_chapter01_percentage(rate, signed=True)}）"
        items.append(
            "<li><strong>"
            + esc(label)
            + "</strong>："
            + esc(value_text)
            + "</li>"
        )
    return "".join(items)


def _render_chapter01_current_metrics(fact, *, esc):
    return _render_chapter01_metric_values(fact, esc=esc, source="current")


def _render_chapter01_comparison_card(fact, *, title, esc, source, comparison_reference=None):
    if not isinstance(fact, dict):
        return ""
    return (
        '<section class="chapter01-comparison-group chapter01-comparison-card">'
        + "<h5>"
        + esc(title)
        + '</h5><div class="chapter01-comparison-card-values"><h6>真实值</h6><ul class="chapter01-comparison-facts">'
        + _render_chapter01_metric_values(
            fact,
            esc=esc,
            source=source,
            comparison_reference=comparison_reference,
        )
        + "</ul></div></section>"
    )


def _script_formula_labels(formula):
    labels = formula.get("labels") if isinstance(formula, dict) else None
    if not isinstance(labels, list):
        return []
    result = []
    for item in labels:
        if not isinstance(item, dict):
            continue
        primary = str(item.get("level_1_label") or item.get("level1_label") or "").strip()
        secondary = item.get("level_2_labels") or item.get("level2_labels") or []
        if not isinstance(secondary, list):
            secondary = [secondary]
        if primary:
            result.append({"primary": primary, "secondary": [str(value).strip() for value in secondary if str(value).strip()]})
    return result


def _script_formula_evidence(formula):
    labels = _script_formula_labels(formula)
    if labels:
        return "；".join(item["primary"] + ("（" + "、".join(item["secondary"]) + "）" if item["secondary"] else "") for item in labels)
    return "未返回"


def _script_formula_detail_tokens(item):
    """Return readable, de-duplicated secondary formula text for display."""
    if not isinstance(item, dict):
        return []
    raw_values = item.get("detailLabels", [])
    if isinstance(raw_values, str):
        raw_values = [raw_values]
    if not isinstance(raw_values, list):
        raw_values = []
    tokens = []
    for raw_value in raw_values:
        for value in str(raw_value).replace("，", "、").split("、"):
            value = value.strip()
            if value and value not in tokens:
                tokens.append(value)
    return tokens


def _script_formula_display_label(item, secondary):
    """Return the semantic YunTu primary formula category for a chart label."""
    if not isinstance(item, dict):
        return "未命名公式"
    identifier = str(item.get("id") or "").strip()
    label = content_formula_label("primary", identifier, item.get("label"))
    if label:
        return label
    fallback = str(item.get("displayLabel") or item.get("label") or "").strip()
    return fallback if fallback and not fallback.isdigit() else "内容公式不可用"


def _script_formula_semantic_label(item):
    if not isinstance(item, dict):
        return ""
    identifier = str(item.get("id") or "").strip()
    return content_formula_label("secondary", identifier, item.get("label"))


def render_script_insights(*, script_facts=None, script_insights=None, script_dashboard=None, esc=str):
    if not isinstance(script_facts, dict) or not script_facts.get("materials"):
        return '<div class="data-state"><span>脚本数据：不可用</span><p>当前未提供脚本事实，数据不足以判断。</p></div>'
    dashboard = script_dashboard if isinstance(script_dashboard, dict) else {}
    coverage = script_facts.get("coverage", {})
    total = coverage.get("total", len(script_facts.get("materials", [])))
    script_count = coverage.get("script", 0)
    rate = coverage.get("rate", 0)
    try:
        rate_text = f"{float(rate):.0%}"
    except (TypeError, ValueError):
        rate_text = "不可用"
    dimensions = dashboard.get("dimensions", {}) if isinstance(dashboard.get("dimensions"), dict) else {}
    formula_dimension = dimensions.get("contentFormula", {}) if isinstance(dimensions.get("contentFormula"), dict) else {}
    primary = formula_dimension.get("primary", []) if isinstance(formula_dimension.get("primary"), list) else []
    secondary = formula_dimension.get("secondary", {}) if isinstance(formula_dimension.get("secondary"), dict) else {}
    formula_secondary = {}
    for primary_id, raw_children in secondary.items():
        children = []
        if not isinstance(raw_children, list):
            continue
        for raw_child in raw_children:
            if not isinstance(raw_child, dict):
                continue
            child = dict(raw_child)
            semantic_label = _script_formula_semantic_label(child)
            if semantic_label:
                child["label"] = semantic_label
            children.append(child)
        formula_secondary[str(primary_id)] = children
    formula_primary = []
    for raw_item in primary:
        if not isinstance(raw_item, dict):
            continue
        item = dict(raw_item)
        item["displayLabel"] = _script_formula_display_label(item, secondary)
        formula_primary.append(item)
    formula_data = {"primary": formula_primary, "secondary": formula_secondary}
    maximum = max([item.get("count", 0) for item in formula_primary] or [1])
    formula_columns = "".join(
        '<button class="script-formula-primary-column" type="button" data-script-formula-primary data-primary-id="' + esc(item.get("id")) + '" aria-controls="script-formula-view" aria-label="查看' + esc(item.get("displayLabel")) + '的二级内容公式占比"><span class="script-formula-column-plot"><i style="height:' + str(round(float(item.get("count", 0)) / maximum * 100, 2)) + '%"></i></span><strong class="script-formula-display-label">' + esc(item.get("displayLabel")) + '</strong><small>' + esc(item.get("count", 0)) + ' 个素材</small></button>'
        for item in formula_primary
    )
    if not formula_columns:
        formula_columns = '<div class="data-state"><span>内容公式：不可用</span><p>未提供可用的一二级内容公式标签，数据不足以判断。</p></div>'
    formula_markup = '<section class="script-formula-dimension"><div class="collapsible-head"><button class="collapsible-toggle" type="button" data-collapsible-toggle data-collapsible-expanded-label="收起脚本汇总数据" data-collapsible-collapsed-label="展开脚本汇总数据" aria-expanded="true" aria-controls="script-formula-body"><span class="collapsible-toggle-action">收起脚本汇总数据</span></button></div><div class="collapsible-body" id="script-formula-body"><div class="script-formula-head"><h3>一二级内容公式分布</h3><p class="script-dashboard-hint">点击一级公式柱状图可查看二级内容公式占比</p></div><div class="script-formula-dashboard"><div class="data-dashboard" data-script-formula="' + esc(json.dumps(formula_data, ensure_ascii=False)) + '"><div id="script-formula-view" data-script-formula-view aria-live="polite"><div class="script-formula-overview" role="region" aria-label="一级内容公式柱状图">' + formula_columns + '</div></div></div></div></div></section>'

    projected_insights = dashboard.get("insights") if isinstance(dashboard.get("insights"), list) else script_insights
    if not isinstance(projected_insights, list):
        projected_insights = []
    dimension_items = {"一二级内容公式": None, "脚本文案": None}
    unassigned = []
    for raw_item in projected_insights:
        item = raw_item if isinstance(raw_item, dict) else {}
        title_text = str(item.get("title") or item.get("text") or "")
        if "一二级内容公式" in title_text or "内容公式" in title_text or "公式" in title_text:
            dimension_items["一二级内容公式"] = item
        elif "脚本文案" in title_text or "脚本" in title_text:
            dimension_items["脚本文案"] = item
        else:
            unassigned.append(item)
    for label in ("一二级内容公式", "脚本文案"):
        if dimension_items[label] is None and unassigned:
            dimension_items[label] = unassigned.pop(0)

    def render_dimension_block(label, item):
        item = item if isinstance(item, dict) else {}
        raw_title = str(item.get("title") or item.get("text") or "数据不足以判断。")
        title = raw_title
        for prefix in (label + "：", label + ":"):
            if title.startswith(prefix):
                title = title[len(prefix):].strip() or "数据不足以判断。"
                break
        summary = str(item.get("summary") or item.get("text") or "数据不足以判断。")
        return '<section class="script-insight-dimension-block"><div class="script-insight-dimension-content"><p class="script-insight-dimension-lead"><strong>' + esc(label) + '</strong><span>：' + esc(title) + '</span></p><p class="script-insight-detail">' + esc(summary) + '</p></div></section>'

    ai_markup = '<div class="primary-summary" id="script-primary"><section class="script-ai-insights script-ai-insights-layout">' + render_dimension_block("一二级内容公式", dimension_items["一二级内容公式"]) + render_dimension_block("脚本文案", dimension_items["脚本文案"]) + '</section></div>'

    keyword_panel = dashboard.get("keywordCloudPanel", {}) if isinstance(dashboard.get("keywordCloudPanel"), dict) else {}
    conclusion = dashboard.get("conclusion", {}) if isinstance(dashboard.get("conclusion"), dict) else {}
    conclusion_text = keyword_panel.get("oneSentenceConclusion") or conclusion.get("text") or ("脚本文本覆盖 " + str(script_count) + "/" + str(total) + " 个素材；数据不足以判断脚本文案结构。")
    summary_text = keyword_panel.get("summary") or ("脚本文本覆盖 " + str(script_count) + "/" + str(total) + " 个已获取详情素材（" + str(rate_text) + "）。")
    keywords = keyword_panel.get("keywords", []) if isinstance(keyword_panel.get("keywords"), list) else dashboard.get("keywords", [])
    keywords = [item for item in keywords[:24] if isinstance(item, dict)]
    keyword_maximum = max([item.get("frequency", item.get("count", 0)) for item in keywords] or [1])
    keyword_markup = "".join(
        '<span class="keyword-cloud-word keyword-cloud-tone-' + str(index % 6) + ' script-keyword" style="--keyword-weight:' + str(round(1 + float(item.get("frequency", item.get("count", 0))) / keyword_maximum * 1.35, 2)) + '" title="' + esc(str(item.get("frequency", item.get("count", 0))) + ' 次出现') + '">' + esc(item.get("keyword") or item.get("label")) + '</span>'
        for index, item in enumerate(keywords)
    ) or '<span class="data-note">暂无可用关键词，数据不足以判断。</span>'
    selling_points = keyword_panel.get("sellingPoints", []) if isinstance(keyword_panel.get("sellingPoints"), list) else dashboard.get("sellingPoints", [])
    selling_points = [item for item in selling_points[:4] if isinstance(item, dict)]
    selling_markup = "".join('<div class="keyword-selling-card"><b>' + esc(str(index + 1) + '｜' + str(item.get("title") or item.get("label") or "卖点")) + '</b><p>' + esc(str(item.get("description") or (str(item.get("count", 0)) + " 个素材覆盖"))) + '</p></div>' for index, item in enumerate(selling_points)) or '<p class="muted data-note">暂无可用卖点，数据不足以判断。</p>'
    triad_markup = '<div class="keyword-cloud-panel" id="keyword-cloud-panel"><section class="script-keyword-triad"><div class="keyword-cloud-layout script-keyword-triad-grid"><article class="keyword-cloud-conclusion script-keyword-conclusion"><small class="keyword-cloud-kicker script-keyword-kicker">一句话结论</small><h3>' + esc(conclusion_text) + '</h3><p>' + esc(summary_text) + '</p></article><article class="keyword-cloud-summary script-keyword-cloud-panel"><small class="keyword-cloud-kicker script-keyword-kicker">高频关键词云</small><div class="keyword-cloud-words">' + keyword_markup + '</div></article><article class="keyword-cloud-selling script-keyword-selling-panel"><small class="keyword-cloud-kicker script-keyword-kicker">从关键词云提炼的卖点</small><div class="script-selling-points">' + selling_markup + '</div></article></div></section></div>'
    dashboard_markup = '<div class="raw-fact-card dashboard-data-card script-dashboard" id="script-dashboard">' + formula_markup + '</div>'
    return '<div class="script-insights-sections">' + ai_markup + triad_markup + dashboard_markup + '</div>'


def render_top_material_combination(
    value,
    *,
    esc,
    generic_text,
    brand_order,
    presentation=None,
    jump_material_ids=None,
):
    jump_material_ids = {str(value) for value in (jump_material_ids or [])}
    presentation_panels = None
    if isinstance(presentation, dict) and presentation.get("brandPanels"):
        presentation_panels = {
            panel.get("brand"): panel
            for panel in presentation["brandPanels"]
            if isinstance(panel, dict)
        }
        value = {"brandConclusions": []}
        for panel in presentation["brandPanels"]:
            summaries = {item.get("dimension"): item.get("text", "") for item in panel.get("insights", [])}
            ai_analysis = panel.get("aiAnalysis") if isinstance(panel.get("aiAnalysis"), dict) else {}
            conclusion = {
                "brand": panel.get("brand", ""),
                "dataSummary": ai_analysis.get("dataSummary") or summaries.get("data", ""),
            }
            if isinstance(ai_analysis.get("hotMaterialInsight"), dict):
                conclusion["hotMaterialInsight"] = ai_analysis["hotMaterialInsight"]
            value["brandConclusions"].append(conclusion)
        brand_order = [panel.get("brand", "") for panel in presentation["brandPanels"]]
    brand_conclusions = {item["brand"]: item for item in value["brandConclusions"]}
    ordered_brands = [
        brand_conclusions[brand] for brand in brand_order if brand in brand_conclusions
    ]
    ordered_brands.extend(
        item for item in value["brandConclusions"] if item not in ordered_brands
    )
    default_brand = next(
        (item["brand"] for item in ordered_brands if item["brand"] in {"全品牌", "所有指定品牌"}),
        ordered_brands[0]["brand"],
    )
    tabs = "".join(
        '<button class="brand-tab" type="button" role="tab" '
        + f'id="brand-tab-{index}" aria-controls="brand-panel-{index}" '
        + f'aria-selected="{str(item["brand"] == default_brand).lower()}" '
        + f'tabindex="{0 if item["brand"] == default_brand else -1}" '
        + f'data-brand-tab="{esc(item["brand"])}" data-brand-target="brand-panel-{index}">'
        + esc(item["brand"])
        + "</button>"
        for index, item in enumerate(ordered_brands)
    )
    panels = "".join(
        '<article class="brand-panel" role="tabpanel" '
        + f'id="brand-panel-{index}" aria-labelledby="brand-tab-{index}" '
        + ("hidden " if item["brand"] != default_brand else "")
        + f'aria-label="{esc(item["brand"])}，标题匹配归属" '
        + f'data-brand-panel="{esc(item["brand"])}">'
        + '<p class="brand-classification-note">品牌归属：本次榜单标题匹配；分析范围：行业 TOP1000 内该品牌全部匹配素材</p>'
        + (
            _render_chapter01_ai_analysis(
                presentation_panels.get(item["brand"], {}).get("aiAnalysis"),
                esc=esc,
            )
            if presentation_panels
            and isinstance(presentation_panels.get(item["brand"]), dict)
            and presentation_panels.get(item["brand"]).get("aiAnalysis")
            else (
                '<p class="brand-summary brand-summary-data">'
                + esc(generic_text(item.get("dataSummary")))
                + "</p>"
                if generic_text(item.get("dataSummary"))
                else ""
            )
        )
        + _render_chapter01_period_panel(
            presentation_panels.get(item["brand"]) if presentation_panels else None,
            esc=esc,
            merge_ai=bool(
                presentation_panels
                and isinstance(presentation_panels.get(item["brand"]), dict)
                and presentation_panels.get(item["brand"]).get("aiAnalysis")
            ),
            jump_material_ids=jump_material_ids,
        )
        + "</article>"
        for index, item in enumerate(ordered_brands)
    )

    return (
        '<div class="top-material-brands yuntu-content-card">'
        + '<div class="brand-tabs" role="tablist" aria-label="各品牌榜单分析">'
        + tabs
        + '</div><div class="brand-panels">'
        + panels
        + "</div></div>"
    )


def _render_chapter01_ai_analysis(value, *, esc):
    if not isinstance(value, dict):
        return ""
    data_summary = value.get("dataSummary")
    if isinstance(data_summary, str) and data_summary.strip():
        return (
            '<section class="chapter01-ai-block chapter01-data-summary"><h4>素材表现洞察</h4><p>'
            + esc(data_summary)
            + "</p></section>"
        )
    summary = value.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        return ""
    return '<p class="chapter01-ai-summary">' + esc(summary) + "</p>"


def _render_chapter01_period_panel(panel, *, esc, merge_ai=False, jump_material_ids=None):
    if not isinstance(panel, dict):
        return ""
    comparison = panel.get("comparison") if isinstance(panel.get("comparison"), dict) else None
    hot = panel.get("hotMaterialPanel") if isinstance(panel.get("hotMaterialPanel"), dict) else None
    chunks = []
    if comparison is not None:
        comparison_facts = comparison.get("facts") if isinstance(comparison.get("facts"), dict) else {}
        comparison_cards = []
        current = comparison_facts.get("current")
        if isinstance(current, dict):
            comparison_cards.append(
                _render_chapter01_comparison_card(
                    current,
                    title="当前默认筛选条件",
                    esc=esc,
                    source="current",
                )
            )
        for baseline_key, baseline_label in (("previousPeriod", "环比周期"), ("industryBenchmark", "同周期全行业")):
            fact = comparison_facts.get(baseline_key)
            if not isinstance(fact, dict):
                continue
            comparison_cards.append(
                _render_chapter01_comparison_card(
                    fact,
                    title=baseline_label,
                    esc=esc,
                    source="baseline",
                    comparison_reference=current,
                )
            )
        if comparison_cards or comparison.get("summary"):
            if comparison_cards:
                comparison_body = '<div class="chapter01-comparison-grid">' + "".join(comparison_cards) + "</div>"
            else:
                comparison_body = "<p>" + esc(comparison["summary"]) + "</p>"
            comparison_section = (
                '<section class="chapter01-comparison"><div class="collapsible-head"><button class="collapsible-toggle comparison-toggle" type="button" data-collapsible-toggle data-collapsible-expanded-label="收起环比与全行业对比数据" data-collapsible-collapsed-label="展开环比与全行业对比数据" aria-expanded="true" aria-controls="'
                + esc("chapter01-comparison-details-" + str(panel.get("id") or panel.get("brand") or "scope").replace(" ", "-"))
                + '"><span class="collapsible-toggle-action">收起环比与全行业对比数据</span></button></div><h4>环比与全行业对比</h4><div class="collapsible-body" id="'
                + esc("chapter01-comparison-details-" + str(panel.get("id") or panel.get("brand") or "scope").replace(" ", "-"))
                + '">' + comparison_body + "</div></section>"
            )
            chunks = [comparison_section]
    hot_insight = panel.get("aiAnalysis", {}).get("hotMaterialInsight") if isinstance(panel.get("aiAnalysis"), dict) else None
    if isinstance(hot_insight, dict) and isinstance(hot_insight.get("summary"), str) and hot_insight["summary"].strip():
        chunks.append(
            '<section class="chapter01-ai-block chapter01-hot-insight"><h4>爆款素材洞察</h4><p>'
            + esc(hot_insight["summary"])
            + "</p></section>"
        )
    if hot is not None:
        if hot.get("available"):
            cards = []
            for material in hot.get("materials", []):
                exposure = material.get("exposure", {}) if isinstance(material, dict) else {}
                interval = exposure.get("raw") or (
                    f"{exposure.get('min')} - {exposure.get('max')}"
                    if exposure.get("min") is not None else "不可用"
                )
                metrics = material.get("metrics", {}) if isinstance(material, dict) else {}
                material_id = material.get("material_id") if isinstance(material, dict) else None
                title = material.get("title") or material.get("material_id", "")
                title_html = esc(title)
                if material_id and str(material_id) in jump_material_ids:
                    title_html = (
                        '<button type="button" class="hot-material-title" data-jump-material="'
                        + esc(material_id)
                        + '" title="跳转到第五部分单素材深度分析">'
                        + esc(title)
                        + "</button>"
                    )
                metric_labels = {
                    "ctr": "CTR",
                    "cvr": "CVR",
                    "play_3s_rate": "3 秒播放率",
                    "interact_rate": "互动率",
                    "play_5s_rate": "5 秒播放率",
                    "play_over_rate": "完播率",
                }
                def format_metric(key, value):
                    if not isinstance(value, (int, float)):
                        return "-"
                    return f"{value * 100:.2f}%"
                metric_text = "、".join(
                    f"{metric_labels.get(key, key)} {format_metric(key, metrics[key])}"
                    for key in metric_labels
                    if key in metrics and metrics[key] is not None
                )
                cards.append(
                    '<article class="hot-material-card"><h5>'
                    + title_html
                    + '</h5>'
                    + ('<p>素材 ID：' + esc(material_id) + '</p>' if material_id else '')
                    + '<p>曝光区间：'
                    + esc(interval)
                    + '</p><small>'
                    + esc(metric_text or "辅助指标不可用")
                    + "</small></article>"
                )
            chunks.append(
                '<section class="hot-material-panel">'
                + '<div class="collapsible-head"><button class="collapsible-toggle hot-material-toggle" type="button" data-collapsible-toggle data-collapsible-expanded-label="收起爆款素材汇总数据" data-collapsible-collapsed-label="展开爆款素材汇总数据" aria-expanded="true" aria-controls="'
                + esc("hot-material-details-" + str(panel.get("id") or panel.get("brand") or "scope").replace(" ", "-"))
                + '"><span class="collapsible-toggle-action">收起爆款素材汇总数据</span></button></div>'
                + '<h4>爆款素材面板</h4>'
                + '<div class="collapsible-body" id="'
                + esc("hot-material-details-" + str(panel.get("id") or panel.get("brand") or "scope").replace(" ", "-"))
                + '"><p class="hot-material-rule">曝光量区间下限 ≥ '
                + esc(hot.get("thresholdExposureMin"))
                + '｜命中 '
                + esc(hot.get("qualifyingCount", 0))
                + " 条素材</p>"
                + '<div class="hot-material-scroll"><div class="hot-material-grid">'
                + "".join(cards)
                + "</div></div></div></section>"
            )
        else:
            chunks.append(
                '<section class="hot-material-panel data-state"><h4>爆款素材面板</h4><p>曝光区间事实不可用。'
                + esc(hot.get("missingReason") or "数据不足")
                + "</p></section>"
            )
    return "".join(chunks)


def _render_audience_scope(
    value,
    *,
    analysis,
    fact_pack,
    facts,
    esc,
    generic_text,
    insight_cards,
    dimension_labels,
    html_module,
    json_module,
    math_module,
    scope,
    insights=None,
    dashboard_id="audience-dashboard-body",
    extra_dashboard_html="",
    topn_records=None,
):
    def audience_dimension_chart(key, dimension):
        label = dimension_labels[key]
        record_count = dimension.get("recordCount", 0)
        buckets = dimension.get("buckets", [])
        unlabeled_count = dimension.get("unlabeledRecordCount", 0)
        if not buckets:
            unlabeled_note = (
                f'<p class="data-note">未识别到该维度标签：{esc(unlabeled_count)} 条素材。</p>'
                if unlabeled_count else ""
            )
            return (
                f'<article class="chart-card audience-chart"><h3>{esc(label)}分布</h3>'
                + '<p class="data-note">暂无可视化数据。</p>' + unlabeled_note + '</article>'
            )
        if dimension.get("labelMode") == "normalized_tag_share" and key == "crowd":
            max_share = max(bucket["chartShare"] for bucket in buckets)
            axis_max = max(10, math_module.ceil(max_share * 100 / 10) * 10)
            axis_ticks = (axis_max, axis_max * 0.75, axis_max * 0.5, axis_max * 0.25, 0)
            colors = ("#9b6a37", "#d79a4b", "#b77d54", "#c7a36a", "#a14f38", "#958268", "#ab8068", "#6d5d4d")
            columns = []
            for index, bucket in enumerate(buckets):
                chart_share = bucket["chartShare"] * 100
                tooltip = (
                    '<div class="chart-tooltip" role="tooltip"><b>' + esc(bucket["label"]) + '</b>'
                    + '<span>命中素材数：' + esc(bucket["materialCount"]) + '条</span>'
                    + '<span>占比：' + f"{chart_share:.1f}%" + '</span></div>'
                )
                columns.append(
                    '<div class="audience-column-item" role="img" tabindex="0" aria-label="'
                    + esc(bucket["label"]) + '，素材数 ' + esc(bucket["materialCount"])
                    + ' 条，占比 ' + f"{chart_share:.1f}%"
                    + '"><div class="audience-column-bar" style="height:'
                    + f"{max(2, chart_share / axis_max * 100):.2f}%" + ';background:'
                    + colors[index % len(colors)] + '"></div><span class="audience-column-label">'
                    + esc(bucket["label"]) + '</span>' + tooltip + '</div>'
                )
            return (
                '<article class="chart-card audience-chart audience-chart-crowd"><h3>' + esc(label)
                + '分布</h3><div class="audience-column-chart" data-audience-column role="group" aria-label="'
                + esc(label) + '标签占比柱状图，素材样本共 ' + esc(record_count) + ' 条">'
                + '<div class="audience-column-y-axis">'
                + ''.join('<span>' + f"{value:.0f}%" + '</span>' for value in axis_ticks)
                + '</div><div class="audience-column-plot" style="grid-template-columns:repeat('
                + esc(len(columns)) + ',minmax(0,1fr))">' + ''.join(columns) + '</div></div></article>'
            )
        if dimension.get("labelMode") == "normalized_tag_share":
            colors = ("#9b6a37", "#d79a4b", "#6f7f5f", "#a14f38", "#6d5d4d", "#c7a36a", "#7d8f9a", "#b77d54", "#958268", "#ab8068", "#8d9a7b")
            items = [(bucket["label"], bucket["materialCount"], bucket["materialShare"], bucket["chartShare"]) for bucket in buckets]
            visual_items = sorted(items, key=lambda item: (-item[3], str(item[0]))) if key == "age" else items
            cursor = 0.0
            stops, slices, legend = [], [], []
            colors_by_label = {}
            for index, (item_label, count, material_share, chart_share) in enumerate(visual_items):
                color = colors[index % len(colors)]
                colors_by_label[item_label] = color
                next_cursor = cursor + chart_share * 100
                stops.append(f"{color} {cursor:.4f}% {next_cursor:.4f}%")
                slices.append({"label": item_label, "count": count, "materialShare": round(material_share * 100, 1), "share": round(chart_share * 100, 1), "start": cursor * 3.6, "end": next_cursor * 3.6})
                cursor = next_cursor
            for item_label, count, material_share, chart_share in visual_items:
                legend.append(
                    '<li class="legend-item" title="' + esc(item_label) + '：命中素材数：' + esc(count) + '条 占比：' + f"{chart_share * 100:.1f}%" + '">'
                    + '<span class="legend-label"><i class="legend-swatch" style="background:' + colors_by_label[item_label] + '"></i>'
                    + esc(item_label) + '</span><span class="legend-count">' + esc(count) + ' 条</span><span class="legend-share">' + f"{chart_share * 100:.1f}%" + '</span></li>'
                )
            return (
                f'<article class="chart-card audience-chart audience-chart-{esc(key)}"><h3>{esc(label)}分布</h3><div class="audience-pie-layout">'
                + f'<div class="pie-chart" data-audience-pie role="img" tabindex="0" aria-label="{esc(label)}标签占比饼图，素材样本共 {esc(record_count)} 条" data-pie-slices="{esc(json_module.dumps(slices, ensure_ascii=False))}" style="background:conic-gradient({", ".join(stops)})">'
                + '<div class="chart-tooltip" role="tooltip"></div></div>'
                + '<ul class="pie-legend">' + "".join(legend) + '</ul></div></article>'
            )
        return f'<article class="chart-card audience-chart"><h3>{esc(label)}分布</h3><p class="data-note">暂无可视化数据。</p></article>'

    ai_insights = insight_cards(
        insights if isinstance(insights, list) else (analysis.get("audienceInsights") or [])
    )
    if not isinstance(value, dict):
        return ('<section class="section" id="audience-insights"><header class="section-header">'
                '<h2>02｜人群洞察</h2>' + scope + '</header>' + ai_insights + '<p class="data-note">暂无人群汇总数据。</p></section>')
    dimensions = value.get("dimensions", {})
    if not isinstance(dimensions, dict):
        return ""
    dimension_order = ("crowd", "age", "gender")
    charts = "".join(audience_dimension_chart(key, dimensions[key]) for key in dimension_order if key in dimensions and isinstance(dimensions[key], dict))
    charts += "".join(audience_dimension_chart(key, dimension) for key, dimension in dimensions.items() if key not in dimension_order and key in dimension_labels and isinstance(dimension, dict))
    if not charts:
        charts = '<p class="data-note">暂无人群汇总数据。</p>'
    if topn_records is None:
        # Historical reports may still carry either legacy top-N field. New
        # chapter02 rendering passes scope_fact.topMaterials explicitly.
        topn_records = fact_pack.get("audienceRankRecords")
        if topn_records is None:
            topn_records = fact_pack.get("audienceTopNRecords", [])
    topn_records_json = ""
    topn_controls = ""
    if isinstance(topn_records, list) and topn_records:
        topn_records = [{**record, "title": facts.get(str(record.get("material_id")), {}).get("title", str(record.get("material_id", "")))} for record in topn_records if isinstance(record, dict)]
        topn_records_json = html_module.escape(json_module.dumps(topn_records, ensure_ascii=False, separators=(",", ":")), quote=True)
        max_topn = len(topn_records)
        topn_controls = ('<div class="audience-topn-controls" aria-label="人群分析素材范围">'
            '<label>分析 TOP <input type="number" min="1" max="' + esc(max_topn) + '" value="' + esc(max_topn) + '" step="1" inputmode="numeric" data-audience-topn-input></label>'
            '<input type="range" min="1" max="' + esc(max_topn) + '" value="' + esc(max_topn) + '" step="1" data-audience-topn-range>'
            '<span data-audience-topn-label>当前 TOP' + esc(max_topn) + ' / ' + esc(max_topn) + '</span></div>')
    dashboard_attrs = ' class="audience-dashboard"'
    if topn_records_json:
        dashboard_attrs += ' data-audience-records="' + topn_records_json + '"'
    return ('<section class="section" id="audience-insights"><header class="section-header">'
        '<h2>02｜人群洞察</h2>' + scope + '</header><div class="audience-ai-insights">' + ai_insights
        + '</div><div' + dashboard_attrs + '><div class="audience-data-card raw-fact-card">'
        + '<div class="collapsible-head"><button class="collapsible-toggle" type="button" data-collapsible-toggle data-collapsible-expanded-label="收起人群及营销卖点汇总数据" data-collapsible-collapsed-label="展开人群及营销卖点汇总数据" aria-expanded="true" aria-controls="' + dashboard_id + '"><span class="collapsible-toggle-action">收起人群及营销卖点汇总数据</span></button></div>'
        + '<div class="collapsible-body" id="' + dashboard_id + '">' + topn_controls
        + '<div class="audience-chart-grid" data-audience-chart-grid>' + charts + '</div>' + extra_dashboard_html + '</div></div></div></section>')


def render_audience_insights(
    value,
    *,
    analysis,
    fact_pack,
    facts,
    esc,
    generic_text,
    insight_cards,
    dimension_labels,
    html_module,
    json_module,
    math_module,
    scope,
    chapter02_facts=None,
    presentation=None,
):
    """Render all-data and brand audience/marketing panels with one tab contract."""
    if isinstance(presentation, dict) and presentation.get("panels"):
        panels = presentation.get("panels", [])
        converted_facts = {"scopeOrder": []}
        converted_insights = {"scopeOrder": [], "scopes": {}}
        for panel in panels:
            scope_id = panel.get("scopeId", "")
            scope_definition = next((item for item in presentation.get("scopeDefinitions", []) if item.get("id") == scope_id), None)
            scope_key = (scope_definition or {}).get("sourceKey", scope_id)
            converted_facts["scopeOrder"].append(scope_key)
            chart = (panel.get("charts") or [{}])[0]
            categories = []
            details = {item.get("category"): item for item in panel.get("detailViews", [])}
            for bucket in chart.get("buckets", []):
                detail = details.get(bucket.get("label"), {})
                tags = [{"tag": item.get("label"), "rawTag": item.get("rawTag"), "count": item.get("value", 0)} for item in (detail.get("pie", {}).get("buckets", []))]
                categories.append({"category": bucket.get("label"), "occurrenceCount": bucket.get("value", 0), "tagCount": len(tags), "tags": tags})
            converted_facts[scope_key] = {"label": (scope_definition or {}).get("label", scope_key), "audienceDashboard": panel.get("audienceDashboard", {}), "topMaterials": panel.get("topMaterials", []), "marketingDashboard": {"categories": categories, "tagCount": sum(item.get("tagCount", 0) for item in categories), "occurrenceCount": sum(item.get("occurrenceCount", 0) for item in categories)}}
            if panel.get("marketingTagTaxonomyVersion") is not None:
                converted_facts[scope_key]["marketingDashboard"]["taxonomyVersion"] = panel["marketingTagTaxonomyVersion"]
            ai_insights = panel.get("aiInsights", {})
            converted_insights["scopes"][scope_key] = {
                "audienceSummary": {"title": (ai_insights.get("audienceSummary") or {}).get("title", ""), "summary": (ai_insights.get("audienceSummary") or {}).get("text", "")},
                "marketingSummary": {"title": (ai_insights.get("marketingSummary") or {}).get("title", ""), "summary": (ai_insights.get("marketingSummary") or {}).get("text", "")},
            }
        converted_insights["scopeOrder"] = converted_facts["scopeOrder"]
        analysis = {**analysis, "chapter02Insights": converted_insights}
        chapter02_facts = converted_facts
    if not isinstance(chapter02_facts, dict) or not chapter02_facts.get("scopeOrder"):
        return _render_audience_scope(
            value, analysis=analysis, fact_pack=fact_pack, facts=facts, esc=esc,
            generic_text=generic_text, insight_cards=insight_cards,
            dimension_labels=dimension_labels, html_module=html_module,
            json_module=json_module, math_module=math_module, scope=scope,
        )

    insight_bundle = analysis.get("chapter02Insights", {})
    insight_scopes = insight_bundle.get("scopes", {}) if isinstance(insight_bundle, dict) else {}
    if not insight_scopes:
        legacy_audience = analysis.get("audienceInsights", [])
        combination = analysis.get("topMaterialCombination", {})
        legacy_brands = {
            item.get("brand"): item
            for item in combination.get("brandConclusions", [])
            if isinstance(item, dict)
        }
        overall_marketing = next(
            (item.get("summary", "") for item in combination.get("overallConclusions", [])
             if isinstance(item, dict) and item.get("dimension") == "marketing"),
            "",
        )
        insight_scopes = {"all": {"audienceInsights": legacy_audience, "marketingInsights": [{"summary": overall_marketing}]}}
        for brand, item in legacy_brands.items():
            insight_scopes[brand] = {
                "audienceInsights": [{"summary": item.get("peopleSummary", "")}],
                "marketingInsights": [{"summary": item.get("marketingSummary", "")}],
            }

    def marketing_html(dashboard):
        categories = dashboard.get("categories", []) if isinstance(dashboard, dict) else []
        payload = html_module.escape(json_module.dumps(categories, ensure_ascii=False, separators=(",", ":")), quote=True)
        interaction_hint = "点击一级标签柱状图可查看二级标签分布"
        taxonomy_note = (
            "营销卖点标签分类规则以完整营销卖点中括号里的内容为一级标签。"
        )
        taxonomy_version = dashboard.get("taxonomyVersion") if isinstance(dashboard, dict) else None
        taxonomy_attr = (
            ' data-marketing-taxonomy-version="' + esc(taxonomy_version) + '"'
            if taxonomy_version is not None else ""
        )
        if not categories:
            return (
                '<div class="marketing-dashboard"><div class="section-title-row"><h3>营销卖点汇总</h3>'
                '<p class="script-dashboard-hint chart-interaction-hint">' + interaction_hint + '</p></div>'
                '<p class="marketing-taxonomy-note">' + taxonomy_note + '</p>'
                '<p class="data-note">暂无营销卖点汇总数据。</p></div>'
            )
        maximum = max((item.get("occurrenceCount", 0) for item in categories), default=1) or 1
        columns = []
        for item in categories:
            count = item.get("occurrenceCount", 0)
            columns.append(
                '<button class="marketing-category-column" type="button" data-marketing-category-column data-marketing-category="'
                + esc(item.get("category", "")) + '" aria-label="查看' + esc(item.get("category", ""))
                + '标签比例"><span class="marketing-category-column-plot"><i style="height:'
                + f'{count / maximum * 100:.2f}%' + '"></i></span><strong>' + esc(item.get("category", ""))
                + '</strong><span>' + esc(count) + ' 次</span></button>'
            )
        return (
            '<div class="marketing-dashboard marketing-dashboard-card chart-card"' + taxonomy_attr
            + ' data-marketing-categories="' + payload + '"><div class="section-title-row"><h3>营销卖点汇总</h3>'
            + '<p class="script-dashboard-hint chart-interaction-hint">' + interaction_hint + '</p></div>'
            + '<p class="marketing-taxonomy-note">' + taxonomy_note + '</p><div data-marketing-view>'
            + '<div class="chart-grid script-dashboard-overview marketing-column-chart" role="region" tabindex="0" aria-label="营销卖点汇总柱状图">'
            + "".join(columns) + '</div></div></div>'
        )

    tabs, panels = [], []
    for index, scope_key in enumerate(chapter02_facts["scopeOrder"]):
        scope_fact = chapter02_facts.get(scope_key, {})
        selected = index == 0
        tab_id, panel_id = f"chapter02-tab-{index}", f"chapter02-panel-{index}"
        label = "所有指定品牌" if scope_key == "all" else scope_fact.get("label", scope_key)
        tabs.append(
            '<button type="button" role="tab" id="' + tab_id + '" aria-controls="' + panel_id
            + '" aria-selected="' + str(selected).lower() + '" tabindex="' + ("0" if selected else "-1")
            + '" data-chapter02-tab="' + esc(scope_key) + '" data-chapter02-target="' + panel_id + '">' + esc(label) + '</button>'
        )
        scope_insights = insight_scopes.get(scope_key, {}) if isinstance(insight_scopes, dict) else {}
        def dimension_block(label, summary):
            summary = summary if isinstance(summary, dict) else {}
            blocks = []
            title = summary.get("title")
            text = summary.get("summary")
            if title:
                blocks.append('<p class="chapter02-dimension-lead"><strong>' + esc(label) + '</strong><span>：' + esc(title) + '</span></p>')
            if text:
                blocks.append('<p class="chapter02-detail-insight">' + esc(text) + '</p>')
            if not blocks:
                return ''
            return '<section class="chapter02-dimension-block"><div class="chapter02-dimension-content">' + ''.join(blocks) + '</div></section>'

        ai_html = ''
        if isinstance(scope_insights, dict):
            ai_html = dimension_block("人群", scope_insights.get("audienceSummary"))
            ai_html += dimension_block("营销卖点", scope_insights.get("marketingSummary"))
        ai_html = ai_html or '<p class="data-note">暂无该范围 AI 二次分析。</p>'
        rendered_scope = _render_audience_scope(
            scope_fact.get("audienceDashboard", {}), analysis=analysis,
            fact_pack=fact_pack, facts=facts, esc=esc,
            generic_text=generic_text, insight_cards=insight_cards, dimension_labels=dimension_labels,
            html_module=html_module, json_module=json_module, math_module=math_module,
            scope="", insights=[], dashboard_id="chapter02-audience-dashboard-body-" + str(index),
            extra_dashboard_html=marketing_html(scope_fact.get("marketingDashboard", {})),
            topn_records=scope_fact.get("topMaterials", []),
        )
        dashboard_start = rendered_scope.find('<div class="audience-dashboard"')
        dashboard_html = rendered_scope[dashboard_start:].rsplit("</section>", 1)[0] if dashboard_start >= 0 else '<p class="data-note">暂无人群汇总数据。</p>'
        panels.append(
            '<section class="chapter02-panel" role="tabpanel" id="' + panel_id + '" aria-labelledby="' + tab_id + '"'
            + (" hidden" if not selected else "") + ' data-chapter02-panel="' + esc(scope_key) + '">'
            + '<div class="chapter02-ai-insights">'
            + ai_html + '</div><div class="chapter02-audience-summary">' + dashboard_html + '</div></section>'
        )
    return '<section class="section" id="audience-insights"><header class="section-header"><h2>02｜人群及营销卖点洞察</h2>' \
        + scope + '</header><div class="chapter02-tabs" role="tablist" aria-label="人群及营销卖点洞察范围">' \
        + "".join(tabs) + '</div><div class="chapter02-panels">' + "".join(panels) + '</div></section>'


def render_highlight_insights(
    *, successful_frames, dashboard, esc, html_module, math_module,
    image_src, frame_label, material_title, format_index_value, failure_reason,
    category_order, category_labels,
    presentation=None,
):
    def convert_groups(category_groups):
        converted_frames = []
        converted_groups = []
        pattern_titles = ("画面主体与构图", "信息层与动作机制", "可迁移机会")
        for category in category_groups:
            refs = []
            for frame in category.get("frames", []):
                converted = {
                    "frame_ref": frame.get("frameRef"),
                    "available": True,
                    "relative_path": frame.get("relativePath"),
                    "second": frame.get("second"),
                    "frame_type": frame.get("frameType"),
                    "peak_rank": frame.get("peakRank"),
                    "click_value": frame.get("clickValue"),
                    "material_id": frame.get("materialId", ""),
                    "rank": frame.get("rank", "-"),
                    "title": frame.get("title", ""),
                    "brand": frame.get("brand", ""),
                }
                converted_frames.append(converted)
                refs.append(converted["frame_ref"])
            patterns = []
            for index, pattern in enumerate(category.get("commonConclusion", [])):
                if isinstance(pattern, dict):
                    normalized = dict(pattern)
                    normalized["frame_refs"] = [ref for ref in normalized.get("frame_refs", refs) if ref in refs] or refs
                else:
                    normalized = {"title": pattern_titles[index] if index < len(pattern_titles) else "共性观察", "body": str(pattern), "frame_refs": refs}
                patterns.append(normalized)
            converted_groups.append({
                "category": category.get("id"),
                "label": category.get("label", category.get("id")),
                "frame_refs": refs,
                "common_patterns": patterns,
                "derivative_directions": category.get("derivativeDirections", []),
            })
        return converted_frames, {"groups": converted_groups}

    brand_views = []
    if isinstance(presentation, dict) and presentation.get("brands"):
        for brand in presentation.get("brands", []):
            if not isinstance(brand, dict):
                continue
            brand_frames, brand_dashboard = convert_groups(brand.get("categories", []))
            modes = []
            for mode in brand.get("classificationModes", []):
                if not isinstance(mode, dict):
                    continue
                mode_frames, mode_dashboard = convert_groups(mode.get("categories", []))
                modes.append({
                    "id": mode.get("id", ""),
                    "label": mode.get("label", ""),
                    "available": mode.get("available") is True,
                    "reason": mode.get("reason", ""),
                    "rule": mode.get("rule", ""),
                    "frames": mode_frames,
                    "dashboard": mode_dashboard,
                    "distribution": mode.get("distribution"),
                })
            brand_views.append({"brand": brand.get("brand", ""), "id": brand.get("id", ""), "frames": brand_frames, "dashboard": brand_dashboard, "modes": modes})
        successful_frames = [frame for view in brand_views for frame in view["frames"]]
        dashboard = None
    elif isinstance(presentation, dict) and presentation.get("categories"):
        successful_frames, dashboard = convert_groups(presentation.get("categories", []))
    if not successful_frames:
        detail = f"（{esc(failure_reason)}）" if failure_reason else ""
        return '<p class="data-note">暂无可用高光帧' + detail + "。</p>"
    if not brand_views and not isinstance(dashboard, dict):
        return '<p class="data-note">高光帧已生成，尚未完成视觉分类，因此不输出视觉洞察。</p>'
    category_aliases = {"scene": "other", "text_overlay": "other"}

    def render_batch_distribution(distribution):
        if not isinstance(distribution, dict):
            return ""
        total_frames = distribution.get("totalFrames")
        buckets = distribution.get("buckets")
        if not isinstance(total_frames, int) or total_frames <= 0 or not isinstance(buckets, list) or not buckets:
            return ""
        valid_buckets = [
            bucket for bucket in buckets
            if isinstance(bucket, dict)
            and isinstance(bucket.get("count"), int)
            and isinstance(bucket.get("share"), (int, float))
            and not isinstance(bucket.get("share"), bool)
        ]
        if len(valid_buckets) != len(buckets):
            return ""
        axis_max = max(10, math_module.ceil(max(bucket["share"] * 100 for bucket in buckets) / 10) * 10)
        colors = ("#9b6a37", "#d79a4b", "#b77d54", "#c7a36a", "#a14f38", "#958268", "#ab8068", "#6d5d4d")
        columns = []
        for index, bucket in enumerate(buckets):
            label = bucket.get("label") or bucket.get("category")
            count = bucket["count"]
            share = bucket["share"] * 100
            tooltip = (
                '<div class="chart-tooltip" role="tooltip"><b>' + esc(label) + '</b>'
                + '<span>帧数：' + esc(count) + ' 帧</span>'
                + '<span>占比：' + f"{share:.1f}%" + '</span></div>'
            )
            columns.append(
                '<div class="audience-column-item" role="img" tabindex="0" aria-label="'
                + esc(label) + '，' + esc(count) + ' 帧，占比 ' + f"{share:.1f}%"
                + '" data-highlight-batch-tooltip="true" data-tooltip-label="'
                + esc(label) + '" data-tooltip-count="' + esc(count)
                + '" data-tooltip-share="' + f"{share:.1f}%"
                + '"><div class="audience-column-bar" style="height:'
                + f"{max(2, share / axis_max * 100):.2f}%" + ';background:'
                + colors[index % len(colors)] + '"></div><span class="audience-column-label">'
                + esc(label) + '</span>' + tooltip + '</div>'
            )
        return (
            '<article class="chart-card audience-chart highlight-batch-distribution" data-highlight-batch-distribution>'
            '<h3>本批次视觉主题分布</h3>'
            '<div class="highlight-batch-distribution-scroll"><div class="audience-column-chart" role="group" aria-label="本批次视觉主题分布柱状图，样本总数 '
            + esc(total_frames) + ' 帧">'
            + '<div class="audience-column-y-axis">'
            + ''.join('<span>' + f"{value:.0f}%" + '</span>' for value in (axis_max, axis_max * 0.75, axis_max * 0.5, axis_max * 0.25, 0))
            + '</div><div class="audience-column-plot" style="grid-template-columns:repeat('
            + esc(len(columns)) + ',minmax(96px,1fr));min-width:' + esc(max(100, len(columns) * 96)) + 'px">'
            + ''.join(columns) + '</div></div></div>'
            '<p class="data-note">样本总数：' + esc(total_frames) + ' 帧</p></article>'
        )

    def render_groups(groups, frames, *, id_prefix="highlight", show_insights=True):
        normalized_groups = {}
        for raw_group in groups:
            if not isinstance(raw_group, dict):
                continue
            category = category_aliases.get(raw_group.get("category"), raw_group.get("category"))
            target = normalized_groups.setdefault(category, {"category": category, "label": raw_group.get("label", category), "frame_refs": [], "common_patterns": [], "derivative_directions": []})
            target["frame_refs"].extend(raw_group.get("frame_refs", []))
            target["common_patterns"].extend(raw_group.get("common_patterns", []))
            target["derivative_directions"].extend(raw_group.get("derivative_directions", []))
        normalized = {"groups": list(normalized_groups.values())}
        frames_by_ref = {frame["frame_ref"]: frame for frame in frames}
        groups_to_render = normalized["groups"]
        tabs, panels = [], []
        for index, group in enumerate(groups_to_render):
            category = group["category"]
            selected = index == 0
            panel_id, tab_id = f"{id_prefix}-panel-{category}", f"{id_prefix}-tab-{category}"
            refs = group["frame_refs"]
            category_label = category_labels.get(category) or group.get("label") or category
            tabs.append('<button type="button" role="tab" id="' + esc(tab_id) + '" aria-controls="' + esc(panel_id) + '" aria-selected="' + str(selected).lower() + '" tabindex="' + ("0" if selected else "-1") + '" data-highlight-category-tab data-highlight-category-target="' + esc(panel_id) + '">' + esc(category_label) + " · " + esc(len(refs)) + " 帧</button>")
            cards = []
            for ref in refs:
                frame = frames_by_ref[ref]
                material_id = str(frame.get("material_id", ""))
                click_text = f"点击指数 {format_index_value(frame.get('click_value'))}"
                caption = f"#{esc(frame.get('rank', '-'))} · {esc(material_title(frame))} · {esc(frame_label(frame))} · {esc(frame.get('second'))}s · {click_text}"
                cards.append('<article class="highlight-frame-card" data-highlight-frame-card data-highlight-material-id="' + esc(material_id) + '"><figure><button class="highlight-frame-preview highlight-frame-button" type="button" data-highlight-src="' + html_module.escape(image_src(frame), quote=True) + '" data-highlight-caption="' + html_module.escape(caption, quote=True) + '" aria-label="查看高光帧大图"><img loading="lazy" src="' + html_module.escape(image_src(frame), quote=True) + '" alt="' + esc(caption) + '"></button></figure><div class="highlight-frame-meta"><small class="highlight-frame-kind">' + esc(frame_label(frame)) + '</small><span class="highlight-frame-metric">' + esc(frame.get("second")) + 's · ' + esc(click_text) + '</span><button class="highlight-material-title" type="button" data-jump-material="' + esc(material_id) + '">' + esc(material_title(frame)) + '</button></div></article>')
            insight_html = ""
            if show_insights:
                pattern_items = []
                for item in group["common_patterns"]:
                    if isinstance(item, dict):
                        pattern_items.append('<article class="highlight-insight"><h5>' + esc(item.get("title", "")) + '</h5><p>' + esc(item.get("body", "")) + '</p></article>')
                    else:
                        pattern_items.append('<article class="highlight-insight"><p>' + esc(item) + '</p></article>')
                patterns = "".join(pattern_items)
                directions_data = list(group["derivative_directions"])
                if len(pattern_items) != len(directions_data):
                    pair_count = min(len(pattern_items), len(directions_data))
                    pattern_items = pattern_items[:pair_count]
                    patterns = "".join(pattern_items)
                    directions_data = directions_data[:pair_count]
                directions = "<h4>裂变方向</h4>" + "".join(f'<article class="highlight-direction"><h5>{esc(item["title"])}</h5><p>{esc(item["body"])}</p></article>' for item in directions_data)
                insight_html = '<div class="highlight-analysis-pair"><div class="highlight-summary"><h4>共性洞察</h4><div class="highlight-patterns">' + patterns + '</div></div><div class="highlight-directions">' + directions + '</div></div>'
            page_count = max(1, math_module.ceil(len(refs) / 12))
            cards_panel_id = f"{id_prefix}-cards-{category}"
            highlight_data_card = (
                '<div class="highlight-data-card raw-fact-card">'
                '<div class="collapsible-head highlight-collapse-head">'
                '<button class="collapsible-toggle highlight-collapse-toggle" type="button" data-collapsible-toggle data-highlight-collapse-toggle data-collapsible-expanded-label="收起高光画面数据" data-collapsible-collapsed-label="展开高光画面数据" aria-expanded="true" aria-controls="'
                + esc(cards_panel_id)
                + '"><span class="collapsible-toggle-action">收起高光画面数据</span></button></div>'
                '<div class="highlight-cards-panel" id="'
                + esc(cards_panel_id)
                + '" data-highlight-cards-panel><div class="highlight-frame-grid">'
                + "".join(cards)
                + '</div><div class="highlight-pagination" data-highlight-pagination><button type="button" data-highlight-page="previous">上一页</button><span data-highlight-page-status>1 / '
                + esc(page_count)
                + '</span><button type="button" data-highlight-page="next">下一页</button></div></div></div>'
            )
            panels.append(
                '<article class="highlight-category highlight-category-panel" role="tabpanel" id="'
                + esc(panel_id)
                + '" aria-labelledby="'
                + esc(tab_id)
                + '"'
                + (" hidden" if not selected else "")
                + ' data-highlight-page-size="12" data-highlight-frame-count="'
                + esc(len(refs))
                + '">'
                + insight_html
                + highlight_data_card
                + '</article>'
            )
        return '<div class="highlight-dashboard-tabs" role="tablist" aria-label="高光画面分类">' + "".join(tabs) + '</div><div class="highlight-dashboard-panels">' + "".join(panels) + '</div>'

    if brand_views:
        brand_tabs = []
        brand_panels = []
        for index, view in enumerate(brand_views):
            selected = index == 0
            brand_id = str(view["id"] or f"highlight-brand-{index}")
            panel_id = f"highlight-brand-panel-{brand_id}"
            tab_id = f"highlight-brand-tab-{brand_id}"
            display_brand = "所有指定品牌" if view["brand"] == "全品牌" else view["brand"]
            brand_tabs.append('<button type="button" role="tab" id="' + esc(tab_id) + '" aria-controls="' + esc(panel_id) + '" aria-selected="' + str(selected).lower() + '" tabindex="' + ("0" if selected else "-1") + '" data-highlight-brand-tab data-highlight-brand-target="' + esc(panel_id) + '">' + esc(display_brand) + '</button>')
            modes = view.get("modes", [])
            if modes:
                mode_tabs = []
                mode_panels = []
                for mode_index, mode in enumerate(modes):
                    mode_selected = mode_index == 0
                    mode_id = f"highlight-{brand_id}-mode-{mode['id']}"
                    mode_panel_id = f"{mode_id}-panel"
                    disabled = " disabled aria-disabled=\"true\"" if not mode["available"] else ""
                    title = f' title="{esc(mode["reason"])}"' if mode["reason"] else ""
                    mode_tabs.append('<button type="button" role="tab" id="' + esc(mode_id) + '" aria-controls="' + esc(mode_panel_id) + '" aria-selected="' + str(mode_selected).lower() + '" tabindex="' + ("0" if mode_selected else "-1") + '" data-highlight-classification-tab data-highlight-classification-target="' + esc(mode_panel_id) + '"' + disabled + title + '>' + esc(mode["label"]) + '</button>')
                    if mode["available"]:
                        mode_content = render_batch_distribution(mode.get("distribution")) if mode.get("id") == "batch" else ""
                        mode_content += render_groups(mode["dashboard"]["groups"], mode["frames"], id_prefix=mode_id, show_insights=mode.get("id") != "batch")
                        if mode["rule"] and mode.get("id") != "batch":
                            mode_content = '<p class="highlight-classification-rule">分类规则：' + esc(mode["rule"]) + '</p>' + mode_content
                    else:
                        mode_content = '<p class="data-note">本批次标准不可用' + ("：" + esc(mode["reason"]) if mode["reason"] else "") + '。</p>'
                    mode_panels.append('<div class="highlight-classification-panel" role="tabpanel" id="' + esc(mode_panel_id) + '" aria-labelledby="' + esc(mode_id) + '"' + (" hidden" if not mode_selected else "") + ' data-highlight-classification-panel>' + mode_content + '</div>')
                classification_html = '<div class="highlight-classification-tabs" role="tablist" aria-label="分类标准">' + "".join(mode_tabs) + '</div><div class="highlight-classification-panels">' + "".join(mode_panels) + '</div>'
            else:
                classification_html = render_groups(view["dashboard"]["groups"], view["frames"], id_prefix=f"highlight-{brand_id}")
            brand_panels.append('<section class="highlight-brand-panel" role="tabpanel" id="' + esc(panel_id) + '" aria-labelledby="' + esc(tab_id) + '"' + (" hidden" if not selected else "") + ' data-highlight-brand-panel>' + classification_html + '</section>')
        return '<div class="highlight-brand-tabs" role="tablist" aria-label="高光画面品牌分类">' + "".join(brand_tabs) + '</div><div class="highlight-brand-panels">' + "".join(brand_panels) + '</div>'

    if dashboard is None:
        dashboard = {"groups": []}
    return render_groups(dashboard.get("groups", []), successful_frames)


def render_material_deep_dive(
    *,
    deep_dives,
    selected_material_ids,
    facts,
    material_frames,
    esc,
    html_module,
    json_module,
    image_src,
    format_index_value,
    format_metric,
    metric_labels,
    second_level_trends,
    presentation=None,
):
    if isinstance(presentation, dict) and presentation.get("panels"):
        deep_dives = []
        selected_material_ids = []
        facts = {}
        material_frames = {}
        for panel in presentation.get("panels", []):
            material_id = str(panel.get("materialId", "")); selected_material_ids.append(material_id)
            panel_script = panel.get("script") if isinstance(panel.get("script"), dict) else {}
            facts[material_id] = {"material_id": material_id, "rank": panel.get("rank", "-"), "title": panel.get("title", ""), "exposure": panel.get("exposure", {}), "metrics": panel.get("metrics", {}), "script_text": panel.get("scriptText", ""), "script_segments": panel.get("scriptSegments", []), "content_formula": panel.get("contentFormula"), "creative_breakdown": panel.get("creativeBreakdown"), "script": panel_script, "evidenceIndex": {"script": panel_script.get("evidenceRefs", [])}, "detailMetrics": panel.get("scriptMetrics", {}), "detailDataAvailability": panel.get("scriptDataAvailability", {}), "people_tags": panel.get("peopleTags", []), "material_tags": panel.get("materialTags", []), "listDataAvailability": panel.get("listDataAvailability", {}), "video": panel.get("video", {}), "secondLevelBreakdown": {"metrics": [{"trend_name": metric.get("id"), "available": metric.get("available"), "missing_reason": metric.get("reason", ""), "points": metric.get("points", []), "high_points": metric.get("highPoints", []), "loss_points": metric.get("lossPoints", [])} for metric in panel.get("secondLevel", {}).get("metrics", [])]}}
            material_frames[material_id] = [{"frame_ref": frame.get("frameRef"), "available": True, "relative_path": frame.get("relativePath"), "second": frame.get("second"), "frame_type": frame.get("frameType"), "peak_rank": frame.get("peakRank"), "click_value": frame.get("clickValue")} for frame in panel.get("frames", [])] + [{"available": False, "failure_reason": reason} for reason in panel.get("frameFailures", [])]
            deep_dives.append({"material_id": material_id, "frame_observations": panel.get("frameObservations", []), "scriptAnalysis": panel_script.get("analysis")})
    if not isinstance(deep_dives, list) or not deep_dives:
        return '<p class="data-note">暂无单素材深度分析数据。</p>'
    dives_by_id = {str(dive.get("material_id")): dive for dive in deep_dives}
    ordered_ids = [material_id for material_id in selected_material_ids if material_id in dives_by_id]
    default_id = ordered_ids[0] if ordered_ids else str(deep_dives[0].get("material_id"))
    tabs, panels = [], []

    def second_level_timeline(metrics, material_index):
        metrics_by_name = {metric.get("trend_name"): metric for metric in metrics if isinstance(metric, dict)}
        ordered_metrics = []
        for trend_name in second_level_trends:
            metric = metrics_by_name.get(trend_name, {"trend_name": trend_name, "available": False, "missing_reason": "趋势未返回"})
            ordered_metrics.append({
                "trend_name": trend_name,
                "available": bool(metric.get("available")),
                "missing_reason": str(metric.get("missing_reason") or "该指标暂无可用秒级数据"),
                "points": [{"second": point.get("second"), "value": point.get("value")} for point in metric.get("points", []) if isinstance(point, dict) and isinstance(point.get("second"), int) and isinstance(point.get("value"), (int, float))],
                "high_points": [item for item in metric.get("high_points", []) if isinstance(item, dict)],
                "loss_points": [item for item in metric.get("loss_points", []) if isinstance(item, dict)],
            })
        buttons = "".join('<button type="button" data-second-level-metric="' + esc(metric["trend_name"]) + '" aria-pressed="false">' + esc(metric["trend_name"]) + "</button>" for metric in ordered_metrics)
        payload = html_module.escape(json_module.dumps(ordered_metrics, ensure_ascii=False), quote=True)
        body_id = "second-level-body-" + str(material_index)
        return ('<div class="second-level-timeline raw-fact-card" data-second-level-timeline data-second-level-metrics="' + payload + '">'
            + '<div class="collapsible-head"><button class="collapsible-toggle" type="button" data-collapsible-toggle data-collapsible-expanded-label="收起秒级拆解数据" data-collapsible-collapsed-label="展开秒级拆解数据" aria-expanded="true" aria-controls="' + esc(body_id) + '"><span class="collapsible-toggle-action">收起秒级拆解数据</span></button></div>'
            + '<div class="collapsible-body" id="' + esc(body_id) + '"><b class="collapsible-body-title">秒级拆解</b>'
            + '<div class="second-level-switcher metric-switch" role="group" aria-label="秒级拆解指标">' + buttons + "</div>"
            + '<div class="second-level-chart-mount" aria-live="polite"></div>'
            + '<label class="second-level-range-control">查看时长 <input type="range" min="20" max="100" value="100" step="10" data-second-level-range></label>'
            + '<p class="second-level-peak-note" data-second-level-peak></p></div></div>')

    def source_tags(fact, field, label):
        availability = (fact.get("listDataAvailability") or {}).get(field, {})
        values = fact.get(field, [])
        if not availability.get("available") or not isinstance(values, list) or not values:
            return '<dt>' + esc(label) + '</dt><dd>未返回</dd>'
        return '<dt>' + esc(label) + '</dt><dd>' + "".join('<span class="material-fact-tag">' + esc(value) + '</span>' for value in values if isinstance(value, str) and value) + '</dd>'

    def render_script_panel(fact, dive, material_index):
        raw_script = fact.get("script") if isinstance(fact.get("script"), dict) else {}
        script_text = str(raw_script.get("text") or fact.get("script_text") or "").strip()
        formula = raw_script.get("formula") if isinstance(raw_script.get("formula"), list) else []
        evidence = raw_script.get("evidence") if isinstance(raw_script.get("evidence"), list) else []
        copy_blocks = raw_script.get("copyBlocks") if isinstance(raw_script.get("copyBlocks"), list) else []
        has_script_data = bool(script_text or formula or evidence or copy_blocks)
        empty_card = '<div class="raw-fact-card material-script-analysis"><b class="collapsible-body-title">脚本分析数据</b><p class="data-note">暂无脚本分析数据</p></div>'
        if not has_script_data:
            return empty_card
        allowed_refs = set(str(ref) for ref in raw_script.get("evidenceRefs", []) if ref)
        if not allowed_refs:
            allowed_refs = {
                str(item.get("evidenceRef")) for item in evidence
                if isinstance(item, dict) and item.get("evidenceRef")
            }
        formula_palette = ("#2f8f5b", "#d5543f", "#d98324", "#3478c7", "#169a9a", "#c4477e", "#7157c8", "#6f7f2f")
        formula_level_colors = {
            "人群": "#ef6b53",
            "适用人群": "#ef6b53",
            "品牌印象": "#7c5cff",
            "商品卖点": "#25b56b",
            "使用场景": "#2f8ff7",
        }
        formula_colors = {
            index: formula_level_colors.get(str(item.get("level1") or "").strip(), formula_palette[index % len(formula_palette)])
            for index, item in enumerate(formula) if isinstance(item, dict)
        }

        def evidence_refs_for_formula(item, formula_index):
            refs = [str(ref) for ref in item.get("evidenceRefs", []) if ref] if isinstance(item, dict) else []
            level1 = str(item.get("level1") or "").strip() if isinstance(item, dict) else ""
            level2 = str(item.get("level2") or "").strip() if isinstance(item, dict) else ""
            for candidate in evidence:
                if not isinstance(candidate, dict):
                    continue
                candidate_formula_index = candidate.get("formulaIndex")
                if candidate_formula_index == formula_index or (
                    candidate_formula_index is None and (
                        str(candidate.get("level2") or "").strip() == level2
                        or str(candidate.get("level1") or "").strip() == level1
                    )
                ):
                    refs.append(str(candidate.get("evidenceRef")))
            for block in copy_blocks:
                for candidate in block.get("evidence", []) if isinstance(block, dict) else []:
                    if isinstance(candidate, dict) and candidate.get("formulaIndex") == formula_index:
                        refs.append(str(candidate.get("evidenceRef")))
            return list(dict.fromkeys(ref for ref in refs if ref in allowed_refs))

        def render_copy_text(copy_text, copy_evidence):
            text = str(copy_text or "")
            ranges = []
            for item in copy_evidence:
                if not isinstance(item, dict):
                    continue
                sentence = str(item.get("sentence") or "").strip()
                ref = str(item.get("evidenceRef") or "").strip()
                if not sentence or ref not in allowed_refs:
                    continue
                cursor = 0
                while cursor < len(text):
                    start = text.find(sentence, cursor)
                    if start < 0:
                        break
                    ranges.append({"start": start, "end": start + len(sentence), "sentence": sentence, "ref": ref, "level2": str(item.get("level2") or ""), "detail": str(item.get("detail") or ""), "formulaIndex": item.get("formulaIndex")})
                    cursor = start + len(sentence)
            ranges.sort(key=lambda item: (item["start"], -(item["end"] - item["start"])))
            located = []
            for item in ranges:
                if not located or item["start"] >= located[-1]["end"]:
                    located.append(item)
            parts, cursor = [], 0
            for item in located:
                if item["start"] > cursor:
                    parts.append(esc(text[cursor:item["start"]]))
                color = formula_colors.get(item.get("formulaIndex"), "#d79a4b")
                title = item["detail"] or item["level2"] or "证据文字"
                parts.append('<span class="script-evidence-highlight" data-script-evidence-ref="' + html_module.escape(item["ref"], quote=True) + '" data-script-formula-index="' + str(item.get("formulaIndex", "")) + '" tabindex="0" role="button" aria-pressed="false" title="' + esc(title) + '" style="--script-color:' + color + '">' + esc(item["sentence"]) + '</span>')
                cursor = item["end"]
            if cursor < len(text):
                parts.append(esc(text[cursor:]))
            return "".join(parts) or esc(text)

        sections = []
        formula_copy_values = []

        if formula:
            chips = []
            for formula_index, item in enumerate(formula):
                if not isinstance(item, dict):
                    continue
                level1 = str(item.get("level1") or "").strip()
                level2 = str(item.get("level2") or "").strip()
                if not level1 and not level2:
                    continue
                targets = evidence_refs_for_formula(item, formula_index)
                target_payload = html_module.escape(json_module.dumps(targets, ensure_ascii=False), quote=True)
                detail = str(item.get("detail") or "").strip()
                display_level1 = level1 or "一级标签"
                display_level2 = level2 or "二级标签"
                color = formula_colors.get(formula_index, formula_palette[formula_index % len(formula_palette)])
                copy_label = display_level1 + ("-" + display_level2 if display_level2 else "")
                if detail:
                    copy_label += "（" + detail + "）"
                formula_copy_values.append(copy_label)
                chip_body = '<span class="script-formula-title-label"><span class="script-formula-label"></span><span class="script-formula-title script-formula-level1">' + esc(display_level1) + '</span></span><span class="script-formula-token script-formula-level2" style="--script-color:' + color + '">' + esc(display_level2)
                if detail:
                    chip_body += '<span class="script-formula-detail">' + esc(detail) + '</span>'
                chip_body += '</span>'
                chips.append('<button type="button" class="script-formula-item script-formula-token" data-script-formula data-script-evidence-refs="' + target_payload + '" aria-controls="material-script-transcript-' + str(material_index) + '" aria-pressed="false" style="--script-color:' + color + '">' + chip_body + '</button>')
            if chips:
                formula_copy = html_module.escape(" + ".join(formula_copy_values), quote=True)
                sections.append('<section class="script-analysis-section"><div class="script-analysis-section-header"><b>本视频内容公式</b><button type="button" class="copy-button" data-script-copy="' + formula_copy + '">复制内容公式</button></div><div class="script-formula-chain script-formula-text" role="group" aria-label="本视频内容公式">' + '<span class="script-formula-connector">+</span>'.join(chips) + '</div></section>')

        transcript_parts = []
        script_copy_parts = []
        for block in copy_blocks:
            if not isinstance(block, dict) or not str(block.get("text") or "").strip():
                continue
            block_label = str(block.get("label") or "视频文字")
            block_text = str(block.get("text") or "").strip()
            block_evidence = block.get("evidence") if isinstance(block.get("evidence"), list) else []
            transcript_parts.append('<p class="script-copy-source"><strong>' + esc(block_label) + '</strong><span>' + render_copy_text(block_text, block_evidence) + '</span></p>')
            script_copy_parts.append(block_label + "：" + block_text)
        if script_text:
            transcript_parts.append('<p class="script-copy-source"><strong>脚本文案</strong><span>' + render_copy_text(script_text, evidence) + '</span></p>')
            script_copy_parts.append("脚本文案：" + script_text)
        if transcript_parts:
            script_copy_value = html_module.escape("\n".join(script_copy_parts), quote=True)
            sections.append('<section class="script-analysis-section"><div class="script-analysis-section-header"><b>本视频脚本</b><button type="button" class="copy-button" data-script-copy="' + script_copy_value + '">复制脚本</button></div><div id="material-script-transcript-' + str(material_index) + '" class="transcript script-text-body script-transcript">' + "".join(transcript_parts) + '</div></section>')

        return '<div class="raw-fact-card material-script-analysis"><b class="collapsible-body-title">脚本分析数据</b><div class="script-analysis-panel">' + "".join(sections) + '</div></div>'

    for index, material_id in enumerate(ordered_ids):
        fact = facts.get(material_id, {})
        dive = dives_by_id[material_id]
        title = fact.get("title") or material_id
        selected_tab = material_id == default_id
        tabs.append('<button class="material-deep-tab" type="button" role="tab" id="material-deep-tab-' + str(index) + '" aria-controls="material-deep-panel-' + str(index) + '" aria-selected="' + str(selected_tab).lower() + '" tabindex="' + ("0" if selected_tab else "-1") + '" data-material-tab data-material-target="material-deep-panel-' + str(index) + '" data-material-id="' + esc(material_id) + '">#' + esc(fact.get("rank", "-")) + " " + esc(title) + "</button>")
        observations = {item.get("frame_ref"): item.get("observation") for item in dive.get("frame_observations", []) if isinstance(item, dict)}
        all_frames = [frame for frame in material_frames.get(material_id, []) if isinstance(frame, dict)]
        frames = sorted([frame for frame in all_frames if frame.get("available") and str(frame.get("relative_path", "")).endswith(".jpg")], key=lambda frame: (frame.get("second", 0), 0 if frame.get("frame_type") == "cover" else 1))
        frame_cards = []
        for frame in frames:
            click_value = "-" if frame.get("click_value") is None else format_index_value(frame["click_value"])
            caption = f"{frame.get('second')}s · 点击指数 {click_value}"
            frame_cards.append('<figure class="deep-frame-card" data-deep-frame-card><label class="deep-frame-select-label"><input type="checkbox" data-deep-frame-checkbox data-frame-ref="' + esc(frame.get("frame_ref")) + '" checked aria-label="选择 ' + esc(caption) + '">选择</label><button class="highlight-frame-button" type="button" data-highlight-src="' + html_module.escape(image_src(frame), quote=True) + '" data-highlight-caption="' + html_module.escape(caption, quote=True) + '" aria-label="查看 ' + esc(caption) + '"><img loading="lazy" src="' + html_module.escape(image_src(frame), quote=True) + '" alt="' + esc(title + " " + caption) + '"></button><figcaption>' + esc(caption) + "</figcaption></figure>")
        breakdown = fact.get("secondLevelBreakdown", {})
        metrics = breakdown.get("metrics", []) if isinstance(breakdown, dict) else []
        failed_reasons = []
        for frame in all_frames:
            if frame.get("available"):
                continue
            reason = frame.get("failure_reason") or frame.get("missing_reason") or frame.get("reason")
            if reason and str(reason) not in failed_reasons:
                failed_reasons.append(str(reason))
        frame_state = ""
        if not frames:
            reason_text = "；".join(failed_reasons)
            frame_state = '<p class="data-note">暂无可用于观察的高光帧。' + (esc(reason_text) if reason_text else "") + "</p>"
        frame_observations = "".join('<li data-deep-frame-observation data-frame-ref="' + esc(frame.get("frame_ref")) + '"><strong>' + esc(str(frame.get("second")) + "s · 点击指数 " + ("-" if frame.get("click_value") is None else format_index_value(frame["click_value"]))) + "：</strong>" + esc(observations.get(frame.get("frame_ref"), "")) + "</li>" for frame in frames) or "<li>暂无可用于观察的高光帧。</li>"
        exposure = fact.get("exposure") if isinstance(fact.get("exposure"), dict) else {}
        exposure_interval = exposure.get("raw")
        if not exposure_interval and (exposure.get("min") is not None or exposure.get("max") is not None):
            exposure_interval = " - ".join(str(value) for value in (exposure.get("min"), exposure.get("max")) if value is not None)
        metric_items = []
        for key in ("show_cnt", "ctr", "cvr", "play_3s_rate", "interact_rate"):
            if key not in fact.get("metrics", {}):
                continue
            value = exposure_interval if key == "show_cnt" and exposure_interval else format_metric(fact.get("metrics", {}).get(key), key)
            metric_items.append('<li><span>' + esc(metric_labels[key]) + '</span><b>' + esc(value) + "</b></li>")
        metric_summary = "".join(metric_items)
        script_panel = render_script_panel(fact, dive, index)
        video = fact.get("video") if isinstance(fact.get("video"), dict) else {}
        video_src = str(video.get("src") or "")
        if video.get("available") is True and video_src.startswith("assets/videos/"):
            video_panel = '<video class="material-video" controls preload="metadata" src="' + html_module.escape(video_src, quote=True) + '">当前浏览器不支持本地视频播放。</video>'
        else:
            video_panel = '<p class="material-video-unavailable data-note">' + esc(video.get("reason") or "本批次未保存可交付的本地视频") + '</p>'
        visual_panel = '<div class="deep-visual-layout">' + video_panel + '<div class="deep-visual-strip"><div class="deep-frame-selection-controls">' + '<button type="button" data-deep-frame-select-all>全选高光帧</button><button type="button" data-deep-frame-clear>全不选高光帧</button></div><div class="deep-frame-grid fixed-six">' + "".join(frame_cards) + '</div>' + frame_state + '</div></div><div class="deep-frame-observations"><h4>高光帧观察</h4><p class="deep-frame-observation-empty" data-deep-frame-observation-empty hidden aria-live="polite">尚未选择高光帧，请选择至少一帧查看观察内容。</p><ul data-deep-frame-observations>' + frame_observations + '</ul></div>'
        panels.append('<article class="material-deep-panel material-card" role="tabpanel" id="material-deep-panel-' + str(index) + '" aria-labelledby="material-deep-tab-' + str(index) + '"' + ("" if selected_tab else " hidden") + '><header class="material-deep-header material-head"><span>#' + esc(fact.get("rank", "-")) + '</span><h3>' + esc(title) + '</h3><p class="material-deep-id">素材 ID：' + esc(material_id) + '</p></header><ul class="material-deep-metrics">' + metric_summary + '</ul><dl class="material-fact-tags">' + source_tags(fact, "people_tags", "核心人群标签") + source_tags(fact, "material_tags", "营销卖点标签") + '</dl><div class="material-detail-tabs" role="tablist" aria-label="' + esc(title) + '分析视图">' + '<button type="button" role="tab" id="material-detail-tab-visual-' + str(index) + '" aria-controls="material-detail-visual-' + str(index) + '" aria-selected="true" data-material-detail-tab="visual" data-material-detail-target="material-detail-visual-' + str(index) + '">高光帧观察</button>' + '<button type="button" role="tab" id="material-detail-tab-timeline-' + str(index) + '" aria-controls="material-detail-timeline-' + str(index) + '" aria-selected="false" tabindex="-1" data-material-detail-tab="timeline" data-material-detail-target="material-detail-timeline-' + str(index) + '">秒级拆解</button>' + '<button type="button" role="tab" id="material-detail-tab-script-' + str(index) + '" aria-controls="material-detail-script-' + str(index) + '" aria-selected="false" tabindex="-1" data-material-detail-tab="script" data-material-detail-target="material-detail-script-' + str(index) + '">脚本分析</button></div>' + '<div class="material-detail-panel" id="material-detail-visual-' + str(index) + '" role="tabpanel" aria-labelledby="material-detail-tab-visual-' + str(index) + '">' + visual_panel + '</div><div class="material-detail-panel" id="material-detail-timeline-' + str(index) + '" role="tabpanel" aria-labelledby="material-detail-tab-timeline-' + str(index) + '" hidden><div class="second-level-section">' + second_level_timeline(metrics, index) + '</div></div><div class="material-detail-panel" id="material-detail-script-' + str(index) + '" role="tabpanel" aria-labelledby="material-detail-tab-script-' + str(index) + '" hidden>' + script_panel + '</div></article>')
    return '<div class="material-deep-layout side-tabs"><div class="material-deep-tab-list" role="tablist" aria-label="单素材深度分析">' + "".join(tabs) + '</div><div class="material-deep-panels">' + "".join(panels) + "</div></div>"
