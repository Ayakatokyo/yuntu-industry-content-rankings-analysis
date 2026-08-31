"""Stable HTML renderers for independently migrated Yuntu report sections."""


def render_script_insights():
    return (
        '<div class="data-state"><span>脚本数据：未接入</span><p>'
        '本次云图 RPA 未提供可用于汇总的脚本正文与时间戳段落；本部分暂不输出话术、内容公式或帧-话术对应关系。'
        "</p></div>"
    )


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
            value["brandConclusions"].append({
                "brand": panel.get("brand", ""),
                "dataSummary": summaries.get("data", ""),
            })
        brand_order = [panel.get("brand", "") for panel in presentation["brandPanels"]]
    brand_conclusions = {item["brand"]: item for item in value["brandConclusions"]}
    ordered_brands = [
        brand_conclusions[brand] for brand in brand_order if brand in brand_conclusions
    ]
    ordered_brands.extend(
        item for item in value["brandConclusions"] if item not in ordered_brands
    )
    default_brand = next(
        (item["brand"] for item in ordered_brands if item["brand"] == "全品牌"),
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
    if comparison is not None and not merge_ai:
        summary = comparison.get("summary")
        if summary:
            chunks.append(
                '<section class="chapter01-comparison"><h4>环比与大盘比较</h4><p>'
                + esc(summary)
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
                    "show_cnt": "曝光量",
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
                    if key == "show_cnt":
                        return f"{value / 10000:.1f} 万" if value >= 10000 else f"{value:,.0f}"
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
                tags = [{"tag": item.get("label"), "count": item.get("value", 0)} for item in (detail.get("pie", {}).get("buckets", []))]
                categories.append({"category": bucket.get("label"), "occurrenceCount": bucket.get("value", 0), "tagCount": len(tags), "tags": tags})
            converted_facts[scope_key] = {"label": (scope_definition or {}).get("label", scope_key), "audienceDashboard": panel.get("audienceDashboard", {}), "topMaterials": panel.get("topMaterials", []), "marketingDashboard": {"categories": categories, "tagCount": sum(item.get("tagCount", 0) for item in categories), "occurrenceCount": sum(item.get("occurrenceCount", 0) for item in categories)}}
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
        if not categories:
            return '<div class="marketing-dashboard"><h3>营销卖点汇总</h3><p class="data-note">暂无营销卖点汇总数据。</p></div>'
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
        return '<div class="marketing-dashboard marketing-dashboard-card chart-card" data-marketing-categories="' + payload + '"><h3>营销卖点汇总</h3><p class="script-dashboard-hint">共 ' \
            + esc(dashboard.get("tagCount", 0)) + ' 个标签，' + esc(dashboard.get("occurrenceCount", 0)) \
            + ' 次命中；点击类别柱查看该类别的标签比例。</p><div data-marketing-view><div class="chart-grid script-dashboard-overview marketing-column-chart" role="group" aria-label="营销卖点一级类别柱状图">' \
            + "".join(columns) + '</div></div></div>'

    tabs, panels = [], []
    for index, scope_key in enumerate(chapter02_facts["scopeOrder"]):
        scope_fact = chapter02_facts.get(scope_key, {})
        selected = index == 0
        tab_id, panel_id = f"chapter02-tab-{index}", f"chapter02-panel-{index}"
        label = "全品牌" if scope_key == "all" else scope_fact.get("label", scope_key)
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
    export_href=None,
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
            brand_views.append({"brand": brand.get("brand", ""), "id": brand.get("id", ""), "frames": brand_frames, "dashboard": brand_dashboard})
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

    def render_groups(groups, frames, *, id_prefix="highlight"):
        normalized_groups = {}
        for raw_group in groups:
            if not isinstance(raw_group, dict):
                continue
            category = category_aliases.get(raw_group.get("category"), raw_group.get("category"))
            target = normalized_groups.setdefault(category, {"category": category, "frame_refs": [], "common_patterns": [], "derivative_directions": []})
            target["frame_refs"].extend(raw_group.get("frame_refs", []))
            target["common_patterns"].extend(raw_group.get("common_patterns", []))
            target["derivative_directions"].extend(raw_group.get("derivative_directions", []))
        normalized = {"groups": [normalized_groups[key] for key in ("portrait", "product", "other") if key in normalized_groups]}
        frames_by_ref = {frame["frame_ref"]: frame for frame in frames}
        groups_to_render = [group for category in category_order for group in normalized["groups"] if group["category"] == category]
        tabs, panels = [], []
        for index, group in enumerate(groups_to_render):
            category = group["category"]
            selected = index == 0
            panel_id, tab_id = f"{id_prefix}-panel-{category}", f"{id_prefix}-tab-{category}"
            refs = group["frame_refs"]
            tabs.append('<button type="button" role="tab" id="' + esc(tab_id) + '" aria-controls="' + esc(panel_id) + '" aria-selected="' + str(selected).lower() + '" tabindex="' + ("0" if selected else "-1") + '" data-highlight-category-tab data-highlight-category-target="' + esc(panel_id) + '">' + esc(category_labels[category]) + " · " + esc(len(refs)) + " 帧</button>")
            cards = []
            for ref in refs:
                frame = frames_by_ref[ref]
                material_id = str(frame.get("material_id", ""))
                click_text = f"点击指数 {format_index_value(frame.get('click_value'))}"
                caption = f"#{esc(frame.get('rank', '-'))} · {esc(material_title(frame))} · {esc(frame_label(frame))} · {esc(frame.get('second'))}s · {click_text}"
                cards.append('<article class="highlight-frame-card" data-highlight-frame-card data-highlight-material-id="' + esc(material_id) + '"><figure><button class="highlight-frame-preview highlight-frame-button" type="button" data-highlight-src="' + html_module.escape(image_src(frame), quote=True) + '" data-highlight-caption="' + html_module.escape(caption, quote=True) + '" aria-label="查看高光帧大图"><img loading="lazy" src="' + html_module.escape(image_src(frame), quote=True) + '" alt="' + esc(caption) + '"></button></figure><div class="highlight-frame-meta"><small class="highlight-frame-kind">' + esc(frame_label(frame)) + '</small><span class="highlight-frame-metric">' + esc(frame.get("second")) + 's · ' + esc(click_text) + '</span><button class="highlight-material-title" type="button" data-jump-material="' + esc(material_id) + '">' + esc(material_title(frame)) + '</button></div></article>')
            pattern_items = []
            for item in group["common_patterns"]:
                if isinstance(item, dict):
                    pattern_items.append('<article class="highlight-insight"><h5>' + esc(item.get("title", "")) + '</h5><p>' + esc(item.get("body", "")) + '</p></article>')
                else:
                    pattern_items.append('<article class="highlight-insight"><p>' + esc(item) + '</p></article>')
            patterns = "".join(pattern_items)
            directions_data = list(group["derivative_directions"])
            if len(pattern_items) != len(directions_data):
                # Keep the two columns strictly paired in the rendered report.
                # Legacy model outputs may contain one-sided entries; trim to
                # the shared prefix rather than showing unmatched insights.
                pair_count = min(len(pattern_items), len(directions_data))
                pattern_items = pattern_items[:pair_count]
                patterns = "".join(pattern_items)
                directions_data = directions_data[:pair_count]
            directions = "<h4>裂变方向</h4>" + "".join(f'<article class="highlight-direction"><h5>{esc(item["title"])}</h5><p>{esc(item["body"])}</p></article>' for item in directions_data)
            page_count = max(1, math_module.ceil(len(refs) / 12))
            panels.append('<article class="highlight-category highlight-category-panel" role="tabpanel" id="' + esc(panel_id) + '" aria-labelledby="' + esc(tab_id) + '"' + (" hidden" if not selected else "") + ' data-highlight-page-size="12" data-highlight-frame-count="' + esc(len(refs)) + '"><div class="highlight-analysis-pair"><div class="highlight-summary"><h4>共性洞察</h4><div class="highlight-patterns">' + patterns + '</div></div><div class="highlight-directions">' + directions + '</div></div><div class="highlight-frame-grid">' + "".join(cards) + '</div><div class="highlight-pagination" data-highlight-pagination><button type="button" data-highlight-page="previous">上一页</button><span data-highlight-page-status>1 / ' + esc(page_count) + '</span><button type="button" data-highlight-page="next">下一页</button></div></article>')
        return '<div class="highlight-dashboard-tabs" role="tablist" aria-label="高光画面分类">' + "".join(tabs) + '</div><div class="highlight-dashboard-panels">' + "".join(panels) + '</div>'

    def with_export_link(content):
        if not export_href:
            return content
        link = '<a class="highlight-export-button" href="' + html_module.escape(str(export_href), quote=True) + '" download>导出高光帧资产（Excel）</a>'
        return '<div class="highlight-export-toolbar">' + link + '</div>' + content

    if brand_views:
        brand_tabs = []
        brand_panels = []
        for index, view in enumerate(brand_views):
            selected = index == 0
            brand_id = str(view["id"] or f"highlight-brand-{index}")
            panel_id = f"highlight-brand-panel-{brand_id}"
            tab_id = f"highlight-brand-tab-{brand_id}"
            brand_tabs.append('<button type="button" role="tab" id="' + esc(tab_id) + '" aria-controls="' + esc(panel_id) + '" aria-selected="' + str(selected).lower() + '" tabindex="' + ("0" if selected else "-1") + '" data-highlight-brand-tab data-highlight-brand-target="' + esc(panel_id) + '">' + esc(view["brand"]) + '</button>')
            category_html = render_groups(view["dashboard"]["groups"], view["frames"], id_prefix=f"highlight-{brand_id}")
            brand_panels.append('<section class="highlight-brand-panel" role="tabpanel" id="' + esc(panel_id) + '" aria-labelledby="' + esc(tab_id) + '"' + (" hidden" if not selected else "") + ' data-highlight-brand-panel>' + category_html + '</section>')
        return with_export_link('<div class="highlight-brand-tabs" role="tablist" aria-label="高光画面品牌分类">' + "".join(brand_tabs) + '</div><div class="highlight-brand-panels">' + "".join(brand_panels) + '</div>')

    if dashboard is None:
        dashboard = {"groups": []}
    return with_export_link(render_groups(dashboard.get("groups", []), successful_frames))


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
            facts[material_id] = {"material_id": material_id, "rank": panel.get("rank", "-"), "title": panel.get("title", ""), "metrics": panel.get("metrics", {}), "people_tags": panel.get("peopleTags", []), "material_tags": panel.get("materialTags", []), "listDataAvailability": panel.get("listDataAvailability", {}), "secondLevelBreakdown": {"metrics": [{"trend_name": metric.get("id"), "available": metric.get("available"), "missing_reason": metric.get("reason", ""), "points": metric.get("points", []), "high_points": metric.get("highPoints", []), "loss_points": metric.get("lossPoints", [])} for metric in panel.get("secondLevel", {}).get("metrics", [])]}}
            material_frames[material_id] = [{"frame_ref": frame.get("frameRef"), "available": True, "relative_path": frame.get("relativePath"), "second": frame.get("second"), "frame_type": frame.get("frameType"), "peak_rank": frame.get("peakRank"), "click_value": frame.get("clickValue")} for frame in panel.get("frames", [])] + [{"available": False, "failure_reason": reason} for reason in panel.get("frameFailures", [])]
            deep_dives.append({"material_id": material_id, "frame_observations": panel.get("frameObservations", []), "second_level_observations": panel.get("secondLevelObservations", [])})
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
        metric_summary = "".join('<li><span>' + esc(metric_labels[key]) + '</span><b>' + esc(format_metric(fact.get("metrics", {}).get(key), key)) + "</b></li>" for key in ("show_cnt", "ctr", "cvr", "play_3s_rate", "interact_rate") if key in fact.get("metrics", {}))
        panels.append('<article class="material-deep-panel material-card" role="tabpanel" id="material-deep-panel-' + str(index) + '" aria-labelledby="material-deep-tab-' + str(index) + '"' + ("" if selected_tab else " hidden") + '><header class="material-deep-header material-head"><span>#' + esc(fact.get("rank", "-")) + '</span><h3>' + esc(title) + '</h3><p class="material-deep-id">素材 ID：' + esc(material_id) + '</p></header><ul class="material-deep-metrics">' + metric_summary + '</ul><dl class="material-fact-tags">' + source_tags(fact, "people_tags", "核心人群标签") + source_tags(fact, "material_tags", "营销卖点标签") + '</dl><div class="material-detail-tabs" role="tablist" aria-label="' + esc(title) + '分析视图">' + '<button type="button" role="tab" id="material-detail-tab-visual-' + str(index) + '" aria-controls="material-detail-visual-' + str(index) + '" aria-selected="true" data-material-detail-tab="visual" data-material-detail-target="material-detail-visual-' + str(index) + '">高光帧观察</button>' + '<button type="button" role="tab" id="material-detail-tab-timeline-' + str(index) + '" aria-controls="material-detail-timeline-' + str(index) + '" aria-selected="false" tabindex="-1" data-material-detail-tab="timeline" data-material-detail-target="material-detail-timeline-' + str(index) + '">秒级拆解</button>' + '<button type="button" role="tab" id="material-detail-tab-script-' + str(index) + '" aria-controls="material-detail-script-' + str(index) + '" aria-selected="false" tabindex="-1" data-material-detail-tab="script" data-material-detail-target="material-detail-script-' + str(index) + '">脚本分析</button></div>' + '<div class="material-detail-panel" id="material-detail-visual-' + str(index) + '" role="tabpanel" aria-labelledby="material-detail-tab-visual-' + str(index) + '"><div class="deep-visual-strip"><div class="deep-frame-selection-controls">' + '<button type="button" data-deep-frame-select-all>全选高光帧</button><button type="button" data-deep-frame-clear>全不选高光帧</button></div><div class="deep-frame-grid fixed-six">' + "".join(frame_cards) + '</div>' + frame_state + '</div><div class="deep-frame-observations"><h4>高光帧观察</h4><p class="deep-frame-observation-empty" data-deep-frame-observation-empty hidden aria-live="polite">尚未选择高光帧，请选择至少一帧查看观察内容。</p><ul data-deep-frame-observations>' + frame_observations + '</ul></div></div><div class="material-detail-panel" id="material-detail-timeline-' + str(index) + '" role="tabpanel" aria-labelledby="material-detail-tab-timeline-' + str(index) + '" hidden><div class="second-level-section">' + second_level_timeline(metrics, index) + '</div></div><div class="material-detail-panel data-state" id="material-detail-script-' + str(index) + '" role="tabpanel" aria-labelledby="material-detail-tab-script-' + str(index) + '" hidden><span>脚本数据：未接入</span><p>当前未提供脚本正文与时间戳段落，暂不输出内容公式、话术结论和帧-话术对应关系。</p></div></article>')
    return '<div class="material-deep-layout side-tabs"><div class="material-deep-tab-list" role="tablist" aria-label="单素材深度分析">' + "".join(tabs) + '</div><div class="material-deep-panels">' + "".join(panels) + "</div></div>"
