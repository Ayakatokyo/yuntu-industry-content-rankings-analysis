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
    dimension_labels,
    dimensions,
    brand_summary_fields,
    brand_order,
):
    overall_by_dimension = {
        item["dimension"]: item for item in value["overallConclusions"]
    }
    overall = "".join(
        '<p><strong>'
        + dimension_labels[dimension]
        + "，</strong>"
        + esc(generic_text(overall_by_dimension[dimension]["summary"]))
        + "</p>"
        for dimension in dimensions
    )
    brand_conclusions = {item["brand"]: item for item in value["brandConclusions"]}
    ordered_brands = [
        brand_conclusions[brand] for brand in brand_order if brand in brand_conclusions
    ]
    ordered_brands.extend(
        item for item in value["brandConclusions"] if item not in ordered_brands
    )
    default_brand = next(
        (item["brand"] for item in ordered_brands if item["brand"] == "五个女博士"),
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
        + '<p class="brand-classification-note">品牌归属：标题匹配归属；对比样本：成功秒级拆解素材</p>'
        + "".join(
            '<p><strong>'
            + dimension_labels[dimension]
            + "，</strong>"
            + esc(generic_text(item[brand_summary_fields[dimension]]))
            + "</p>"
            for dimension in dimensions
        )
        + "</article>"
        for index, item in enumerate(ordered_brands)
    )
    return (
        '<article class="top-material-executive yuntu-content-card"><h3>综合结论</h3><p>'
        + esc(generic_text(value["executiveSummary"]["summary"]))
        + "</p></article>"
        + '<div class="top-material-overall yuntu-content-card"><h3>TOP1000 整体分析</h3>'
        + overall
        + "</div>"
        + '<div class="top-material-brands yuntu-content-card"><h3>各品牌 TOP 对比分析（成功秒级拆解素材）</h3>'
        + '<div class="brand-tabs" role="tablist" aria-label="各品牌 TOP 对比分析（成功秒级拆解素材）">'
        + tabs
        + '</div><div class="brand-panels">'
        + panels
        + "</div></div>"
        + '<article class="brand-difference yuntu-content-card"><h3>品牌间差异总结</h3><p>'
        + esc(generic_text(value["brandComparisonConclusion"]["summary"]))
        + "</p></article>"
    )


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

    ai_insights = insight_cards(analysis["audienceInsights"])
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
        + '<div class="collapsible-head"><button class="collapsible-toggle" type="button" data-collapsible-toggle data-collapsible-expanded-label="收起人群汇总数据" data-collapsible-collapsed-label="展开人群汇总数据" aria-expanded="true" aria-controls="audience-dashboard-body"><span class="collapsible-toggle-action">收起人群汇总数据</span></button></div>'
        + '<div class="collapsible-body" id="audience-dashboard-body">' + topn_controls
        + '<div class="audience-chart-grid" data-audience-chart-grid>' + charts + '</div></div></div></div></section>')


def render_highlight_insights(
    *, successful_frames, dashboard, esc, html_module, math_module,
    image_src, frame_label, material_title, format_index_value, failure_reason,
    category_order, category_labels,
):
    if not successful_frames:
        detail = f"（{esc(failure_reason)}）" if failure_reason else ""
        return '<p class="data-note">暂无可用高光帧' + detail + "。</p>"
    if not isinstance(dashboard, dict):
        return '<p class="data-note">高光帧已生成，尚未完成视觉分类，因此不输出视觉洞察。</p>'
    frames_by_ref = {frame["frame_ref"]: frame for frame in successful_frames}
    groups = [group for category in category_order for group in dashboard["groups"] if group["category"] == category]
    tabs, panels = [], []
    for index, group in enumerate(groups):
        category = group["category"]
        selected = index == 0
        panel_id, tab_id = f"highlight-panel-{category}", f"highlight-tab-{category}"
        refs = group["frame_refs"]
        tabs.append('<button type="button" role="tab" id="' + esc(tab_id) + '" aria-controls="' + esc(panel_id) + '" aria-selected="' + str(selected).lower() + '" tabindex="' + ("0" if selected else "-1") + '" data-highlight-category-tab data-highlight-category-target="' + esc(panel_id) + '">' + esc(category_labels[category]) + " · " + esc(len(refs)) + " 帧</button>")
        cards = []
        for ref in refs:
            frame = frames_by_ref[ref]
            material_id = str(frame.get("material_id", ""))
            click_text = f"点击指数 {format_index_value(frame.get('click_value'))}"
            caption = f"#{esc(frame.get('rank', '-'))} · {esc(material_title(frame))} · {esc(frame_label(frame))} · {esc(frame.get('second'))}s · {click_text}"
            cards.append('<article class="highlight-frame-card" data-highlight-frame-card data-highlight-material-id="' + esc(material_id) + '"><figure><button class="highlight-frame-preview highlight-frame-button" type="button" data-highlight-src="' + html_module.escape(image_src(frame), quote=True) + '" data-highlight-caption="' + html_module.escape(caption, quote=True) + '" aria-label="查看高光帧大图"><img loading="lazy" src="' + html_module.escape(image_src(frame), quote=True) + '" alt="' + esc(caption) + '"></button></figure><div class="highlight-frame-meta"><strong>' + esc(material_title(frame)) + '</strong><small>' + esc(frame_label(frame)) + '</small><span>' + esc(frame.get("second")) + 's · ' + esc(click_text) + '</span><button class="highlight-source-link" type="button" data-jump-material="' + esc(material_id) + '">查看素材：#' + esc(frame.get("rank", "-")) + '</button></div></article>')
        patterns = "".join(f"<li>{esc(item)}</li>" for item in group["common_patterns"])
        directions = "".join(f'<article class="highlight-direction"><h4>{esc(item["title"])}</h4><p>{esc(item["body"])}</p></article>' for item in group["derivative_directions"])
        page_count = max(1, math_module.ceil(len(refs) / 12))
        panels.append('<article class="highlight-category highlight-category-panel" role="tabpanel" id="' + esc(panel_id) + '" aria-labelledby="' + esc(tab_id) + '"' + (" hidden" if not selected else "") + ' data-highlight-page-size="12" data-highlight-frame-count="' + esc(len(refs)) + '"><div class="highlight-analysis-pair"><div class="highlight-summary"><h4>共性洞察</h4><ul>' + patterns + '</ul></div><div class="highlight-directions">' + directions + '</div></div><div class="highlight-frame-grid">' + "".join(cards) + '</div><div class="highlight-pagination" data-highlight-pagination><button type="button" data-highlight-page="previous">上一页</button><span data-highlight-page-status>1 / ' + esc(page_count) + '</span><button type="button" data-highlight-page="next">下一页</button></div></article>')
    return '<p class="data-note">每条素材保留封面画面，并从点击指数局部峰值中按点击值降序、秒数升序取最多 5 帧。</p><div class="highlight-dashboard-tabs" role="tablist" aria-label="高光画面分类">' + "".join(tabs) + '</div><div class="highlight-dashboard-panels">' + "".join(panels) + '</div>'


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
):
    if not isinstance(deep_dives, list) or not deep_dives:
        return '<p class="data-note">暂无单素材深度分析数据。</p>'
    dives_by_id = {str(dive.get("material_id")): dive for dive in deep_dives}
    ordered_ids = [material_id for material_id in selected_material_ids if material_id in dives_by_id]
    default_id = ordered_ids[0] if ordered_ids else str(deep_dives[0].get("material_id"))
    tabs, panels = [], []

    def deep_frame_label(frame):
        labels = ["封面帧" if frame.get("frame_type") == "cover" else f"点击 Top{frame.get('peak_rank')} 峰值帧"]
        if frame.get("frame_type") == "cover" and frame.get("peak_rank"):
            labels.append(f"点击 Top{frame['peak_rank']} 峰值")
        return "｜".join(labels)

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
            + '<div class="collapsible-head"><button class="collapsible-toggle" type="button" data-collapsible-toggle aria-expanded="true" aria-controls="' + esc(body_id) + '"><span class="collapsible-toggle-action">收起数据</span></button></div>'
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
            caption = f"{deep_frame_label(frame)}｜{frame.get('second')}s"
            if frame.get("click_value") is not None:
                caption += f"｜点击指数 {format_index_value(frame['click_value'])}"
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
        frame_observations = "".join('<li data-deep-frame-observation data-frame-ref="' + esc(frame.get("frame_ref")) + '"><strong>' + esc(deep_frame_label(frame)) + "｜" + esc(frame.get("second")) + "s：</strong>" + esc(observations.get(frame.get("frame_ref"), "")) + "</li>" for frame in frames) or "<li>暂无可用于观察的高光帧。</li>"
        metric_summary = "".join('<li><span>' + esc(metric_labels[key]) + '</span><b>' + esc(format_metric(fact.get("metrics", {}).get(key), key)) + "</b></li>" for key in ("show_cnt", "ctr", "cvr", "play_3s_rate", "interact_rate") if key in fact.get("metrics", {}))
        panels.append('<article class="material-deep-panel material-card" role="tabpanel" id="material-deep-panel-' + str(index) + '" aria-labelledby="material-deep-tab-' + str(index) + '"' + ("" if selected_tab else " hidden") + '><header class="material-deep-header material-head"><span>#' + esc(fact.get("rank", "-")) + '</span><h3>' + esc(title) + '</h3><p class="material-deep-id">素材 ID：' + esc(material_id) + '</p></header><ul class="material-deep-metrics">' + metric_summary + '</ul><dl class="material-fact-tags">' + source_tags(fact, "people_tags", "核心人群标签") + source_tags(fact, "material_tags", "营销卖点标签") + '</dl><div class="material-detail-tabs" role="tablist" aria-label="' + esc(title) + '分析视图">' + '<button type="button" role="tab" aria-selected="true" data-material-detail-tab="visual" data-material-detail-target="material-detail-visual-' + str(index) + '">高光帧观察</button>' + '<button type="button" role="tab" aria-selected="false" tabindex="-1" data-material-detail-tab="timeline" data-material-detail-target="material-detail-timeline-' + str(index) + '">秒级拆解</button>' + '<button type="button" role="tab" aria-selected="false" tabindex="-1" data-material-detail-tab="script" data-material-detail-target="material-detail-script-' + str(index) + '">脚本分析</button></div>' + '<div class="material-detail-panel" id="material-detail-visual-' + str(index) + '" role="tabpanel"><div class="deep-visual-strip"><div class="deep-frame-selection-controls">' + '<button type="button" data-deep-frame-select-all>全选</button><button type="button" data-deep-frame-clear>清空</button></div><div class="deep-frame-grid fixed-six">' + "".join(frame_cards) + '</div>' + frame_state + '</div><div class="deep-frame-observations"><h4>高光帧观察</h4><ul data-deep-frame-observations>' + frame_observations + '</ul></div></div><div class="material-detail-panel" id="material-detail-timeline-' + str(index) + '" role="tabpanel" hidden><div class="second-level-section">' + second_level_timeline(metrics, index) + '</div></div><div class="material-detail-panel data-state" id="material-detail-script-' + str(index) + '" role="tabpanel" hidden><span>脚本数据：未接入</span><p>当前未提供脚本正文与时间戳段落，暂不输出内容公式、话术结论和帧-话术对应关系。</p></div></article>')
    return '<div class="material-deep-layout side-tabs"><div class="material-deep-tab-list" role="tablist" aria-label="单素材深度分析">' + "".join(tabs) + '</div><div class="material-deep-panels">' + "".join(panels) + "</div></div>"
