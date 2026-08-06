"""Render final Yuntu analysis reports from model-authored JSON."""

import html
import json
from pathlib import Path

from rpa_io import write_json_atomically


class YuntuReportError(RuntimeError):
    """Raised when report inputs are invalid."""


REQUIRED_FIELDS = (
    "rankingOverview",
    "materialComparison",
    "materialDiagnoses",
    "competitorPatterns",
    "xiaoxianDunOpportunityMap",
    "experimentMatrix",
)

SECTION_TITLES = (
    ("01｜榜单机会总览", "rankingOverview"),
    ("02｜素材表现对比", "materialComparison"),
    ("03｜单素材秒级诊断", "materialDiagnoses"),
    ("04｜竞品创意模式", "competitorPatterns"),
    ("05｜小仙炖机会地图", "xiaoxianDunOpportunityMap"),
    ("06｜下一轮实验矩阵", "experimentMatrix"),
)

EVIDENCE_FIELDS = tuple(field for _, field in SECTION_TITLES[:-1])
EXPERIMENT_FIELDS = (
    "priority",
    "hypothesis",
    "creative_variable",
    "target_audience",
    "success_metric",
    "control",
    "review_action",
)


def _load_analysis(path):
    try:
        analysis = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        raise YuntuReportError(f"unable to read analysis JSON: {exc}") from exc
    if not isinstance(analysis, dict):
        raise YuntuReportError("analysis JSON must be an object")
    missing = [field for field in REQUIRED_FIELDS if field not in analysis]
    if missing:
        raise YuntuReportError(
            "analysis JSON is missing required fields: " + ", ".join(missing)
        )
    for field in EVIDENCE_FIELDS:
        _validate_evidence_section(analysis[field], field)
    _validate_experiments(analysis["experimentMatrix"])
    return analysis


def _validate_evidence_section(items, field):
    if not isinstance(items, list) or not items:
        raise YuntuReportError(f"{field} must be a nonempty list")
    for item in items:
        if not isinstance(item, dict):
            raise YuntuReportError(f"{field} items must be objects")
        evidence = item.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise YuntuReportError(f"{field} items must include evidence")
        material_id = item.get("material_id")
        material_ids = item.get("material_ids")
        if isinstance(material_id, str) and material_id.isdigit():
            continue
        if isinstance(material_ids, list) and material_ids and all(
            isinstance(value, str) and value.isdigit() for value in material_ids
        ):
            continue
        raise YuntuReportError(
            f"{field} items must include material_id or material_ids"
        )


def _validate_experiments(items):
    if not isinstance(items, list) or not items:
        raise YuntuReportError("experimentMatrix must be a nonempty list")
    for item in items:
        if not isinstance(item, dict):
            raise YuntuReportError("experimentMatrix items must be objects")
        for field in EXPERIMENT_FIELDS:
            if not isinstance(item.get(field), str) or not item[field].strip():
                raise YuntuReportError(
                    f"experimentMatrix items must include {field}"
                )


def _markdown_value(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, dict):
                if "hypothesis" in item:
                    text = (
                        f"{item['priority']}｜假设：{item['hypothesis']}；变量："
                        f"{item['creative_variable']}；目标人群：{item['target_audience']}；"
                        f"成功指标：{item['success_metric']}；对照：{item['control']}；"
                        f"复盘：{item['review_action']}"
                    )
                else:
                    material_ids = item.get("material_ids") or [item.get("material_id")]
                    material_text = "、".join(
                        str(material_id) for material_id in material_ids if material_id
                    )
                    evidence = json.dumps(
                        item.get("evidence", []), ensure_ascii=False, sort_keys=True
                    )
                    text = (
                        f"{item.get('summary') or item.get('body') or ''} "
                        f"素材：{material_text}；证据：{evidence}"
                    ).strip()
            else:
                text = str(item)
            lines.append(f"- {text}")
        return "\n".join(lines)
    return json.dumps(value, ensure_ascii=False, indent=2)


def _render_markdown(analysis):
    lines = ["# 云图行业内容榜单分析报告", ""]
    for title, field in SECTION_TITLES:
        lines.extend([f"## {title}", "", _markdown_value(analysis[field]), ""])
    return "\n".join(lines)


def _material_frames(fact_pack):
    frames = {}
    for fact in fact_pack.get("materialFacts", []) if isinstance(fact_pack, dict) else []:
        material_id = fact.get("material_id")
        if isinstance(material_id, str):
            frames[material_id] = fact.get("highlightFrames", [])
    return frames


def _render_html(analysis, material_frames, fact_pack):
    def esc(value):
        return html.escape(str(value))

    def image_src(frame):
        path = str(frame.get("relative_path", ""))
        return path if path.startswith("../") else "../" + path

    facts = {
        fact.get("material_id"): fact
        for fact in fact_pack.get("materialFacts", [])
        if isinstance(fact, dict) and fact.get("material_id")
    }
    selected = fact_pack.get("selectedMaterials", [])
    if not selected:
        selected = [{"material_id": material_id, "rank": "-"} for material_id in material_frames]
    metrics = (fact_pack.get("candidatePool") or {}).get("metrics", {})
    summary_metrics = fact_pack.get("summaryMetrics", {})
    overview = analysis.get("rankingOverview", [{}])[0].get("summary", "")
    materials = []
    for item in selected:
        material_id = str(item.get("material_id"))
        fact = facts.get(material_id, {})
        frame_list = [frame for frame in material_frames.get(material_id, []) if frame.get("available") and str(frame.get("relative_path", "")).endswith(".jpg")]
        metric_items = []
        for key in ("ctr", "play_3s_rate", "play_duration_avg", "interact_rate"):
            if key in fact.get("metrics", {}):
                value = fact["metrics"][key]
                label = {"ctr":"CTR", "play_3s_rate":"3秒播放率", "play_duration_avg":"平均播放时长", "interact_rate":"互动率"}[key]
                shown = f"{value * 100:.2f}%" if key != "play_duration_avg" else f"{value:.2f}s"
                metric_items.append(f'<div class="metric"><span>{label}</span><b>{shown}</b></div>')
        gallery = "".join(
            f'<button class="frame-button" type="button" data-frame="{html.escape(image_src(frame), quote=True)}" data-caption="{esc("封面" if frame.get("is_cover") else str(frame.get("second", 0)) + "s")}"><img src="{html.escape(image_src(frame), quote=True)}" alt="{esc(material_id)} {esc(frame.get("second", 0))}秒高光帧"><span>{esc("封面" if frame.get("is_cover") else str(frame.get("second", 0)) + "s")}</span></button>'
            for frame in frame_list
        )
        tags = "".join(f'<span class="tag">{esc(tag)}</span>' for tag in fact.get("material_tags", []))
        people = "".join(f'<span class="tag tag-person">{esc(tag)}</span>' for tag in fact.get("people_tags", []))
        materials.append(f'''<article class="material-card" id="material-{esc(material_id)}">
          <div class="material-head"><div><span class="rank">#{esc(item.get("rank"))}</span><h3>{esc(fact.get("title", material_id))}</h3><code>{esc(material_id)}</code></div><a class="jump" href="#material-{esc(material_id)}">查看素材</a></div>
          <div class="metric-grid">{"".join(metric_items)}</div>
          <div class="tag-row">{tags}{people}</div>
          <div class="highlight-gallery">{gallery or '<p class="muted">暂无可用高光帧</p>'}</div>
          <details><summary>查看该素材诊断与证据</summary><div class="detail-copy">{esc(next((x.get("summary", "") for x in analysis.get("materialDiagnoses", []) if x.get("material_id") == material_id), "数据不足以判断"))}</div></details>
        </article>''')

    sections = []
    for title, field in SECTION_TITLES:
        if field == "materialDiagnoses":
            continue
        cards = "".join(f'<article class="insight-card"><b>{esc(item.get("priority", ""))}</b><p>{esc(item.get("summary", item.get("hypothesis", "")))}</p><small>证据：{esc(json.dumps(item.get("evidence", []), ensure_ascii=False))}</small></article>' for item in analysis[field])
        sections.append(f'<section class="section"><p class="section-kicker">{esc(title.split("｜")[0])}</p><h2>{esc(title.split("｜", 1)[1])}</h2><div class="insight-stack">{cards}</div></section>')

    style = """
:root{--bg:#17100d;--paper:#fff8ed;--panel:#fffdf8;--ink:#2c1b13;--muted:#866e5d;--gold:#d79a4b;--line:#eadac5;--shadow:0 18px 55px rgba(58,31,15,.14)}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:linear-gradient(135deg,#17100d 0 23%,#342017 23%,#f7e5c9 75%,#fff8ed 100%);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}
main{width:min(1240px,calc(100% - 34px));margin:auto;padding:34px 0 76px}.hero,.report-cover{color:#fff;padding:26px 30px 34px;border-bottom:1px solid rgba(255,255,255,.2)}.eyebrow,.section-kicker{color:var(--gold);font-size:12px;font-weight:800;letter-spacing:.12em}
h1{font-size:clamp(36px,5vw,68px);line-height:1;margin:14px 0 18px}h2{font-size:30px;margin:0 0 16px}h3{font-size:20px;line-height:1.45;margin:7px 0 8px}p{line-height:1.75;margin:0}.subtitle{max-width:780px;color:rgba(255,255,255,.75);font-size:17px}
.dashboard{display:grid;grid-template-columns:1.5fr repeat(3,1fr);gap:12px;margin:24px 0}.dash-card,.section,.material-card{background:var(--panel);border:1px solid var(--line);box-shadow:var(--shadow);border-radius:18px}.dash-card{padding:18px}.dash-card b{display:block;font-size:24px;margin-top:6px}.dash-card p{font-size:13px;color:var(--muted)}
.section{padding:25px;margin:18px 0}.section-kicker{margin-bottom:7px}.insight-stack{display:grid;gap:12px}.insight-card{border:1px solid var(--line);border-radius:13px;padding:16px;background:#fff}.insight-card b{color:#9b6a37;font-size:13px}.insight-card small{display:block;color:var(--muted);margin-top:10px;line-height:1.6}
.material-nav{display:flex;gap:8px;overflow:auto;padding:2px 0 14px;position:sticky;top:0;background:rgba(247,229,201,.94);z-index:3}.material-nav a{white-space:nowrap;color:var(--ink);background:#fff;border:1px solid var(--line);border-radius:999px;padding:8px 12px;text-decoration:none;font-size:13px}
.material-card{padding:21px;margin:14px 0;scroll-margin-top:68px}.material-head{display:flex;justify-content:space-between;gap:16px;align-items:flex-start}.rank{color:#9b6a37;font-weight:800}code{color:var(--muted);font-size:12px}.jump{color:#9b6a37;font-size:13px;text-decoration:none;white-space:nowrap}
.metric-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:17px 0}.metric{background:#fff4e5;border-radius:11px;padding:11px}.metric span{display:block;color:var(--muted);font-size:12px}.metric b{display:block;font-size:18px;margin-top:4px}.tag-row{display:flex;flex-wrap:wrap;gap:6px;margin:12px 0}.tag{display:inline-block;background:#f5e7d3;color:#7b542e;border-radius:999px;padding:4px 8px;font-size:11px}.tag-person{background:#e8efe9;color:#49634e}
.frame-strip{display:grid;grid-template-columns:repeat(auto-fill,minmax(125px,1fr));gap:9px;margin-top:14px}.frame-button{border:1px solid var(--line);background:#fff;padding:5px;border-radius:10px;text-align:left;cursor:pointer;color:var(--muted)}.frame-button img{display:block;width:100%;aspect-ratio:9/16;object-fit:cover;border-radius:7px}.frame-button span{display:block;padding:5px 3px 2px;font-size:12px}
details{margin-top:14px;border-top:1px solid var(--line);padding-top:12px}summary{cursor:pointer;font-weight:700;color:#8d6035}.detail-copy{padding-top:10px;color:var(--muted)}.muted{color:var(--muted);padding:12px}#lightbox{position:fixed;inset:0;background:rgba(14,8,5,.82);display:none;place-items:center;z-index:10;padding:20px}#lightbox.open{display:grid}#lightbox img{max-height:86vh;max-width:min(90vw,620px);border-radius:12px}#lightbox button{position:fixed;top:18px;right:22px;border:0;background:#fff;color:var(--ink);border-radius:999px;padding:8px 13px;cursor:pointer}
@media(max-width:800px){.dashboard{grid-template-columns:repeat(2,1fr)}.dashboard .wide{grid-column:1/-1}.metric-grid{grid-template-columns:repeat(2,1fr)}}@media(max-width:560px){main{width:min(100% - 20px,1240px);padding-top:10px}.hero,.report-cover{padding:22px 18px 28px}h1{font-size:38px}.section{padding:19px}.material-head{display:block}.jump{display:inline-block;margin-top:8px}.frame-strip,.highlight-gallery{grid-template-columns:repeat(3,1fr)}}
"""
    filters = fact_pack.get("filters", {}) if isinstance(fact_pack, dict) else {}
    industry = str(filters.get("industry") or "食品饮料")
    brands = filters.get("brands") or []
    brand_text = "、".join(str(brand) for brand in brands if brand) or "指定品牌"
    date_text = ""
    if filters.get("custom_start_date") and filters.get("custom_end_date"):
        date_text = f"｜{filters['custom_start_date']} 至 {filters['custom_end_date']}"
    subtitle = f"{industry}行业｜{brand_text}{date_text}｜以素材表现、逐秒趋势和高光帧为证据的创意复盘"

    from string import Template
    template = Template("""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>云图行业内容榜单分析报告</title><style>$style</style></head><body><main><header class="report-cover"><div class="eyebrow">小仙炖｜云图行业内容策略</div><h1>云图行业内容榜单分析报告</h1><p class="subtitle">$subtitle</p></header><section class="dashboard"><div class="dash-card wide"><p>组合结论</p><b>$overview</b></div><div class="dash-card"><p>候选素材</p><b>$candidate_count</b></div><div class="dash-card"><p>入选素材</p><b>$selected_count</b></div><div class="dash-card"><p>高光帧</p><b>$frame_count</b></div></section><nav class="material-nav">$nav</nav>$sections<section class="section"><p class="section-kicker">03</p><h2>素材诊断与高光帧</h2><div>$materials</div></section></main><div id="lightbox" role="dialog" aria-modal="true"><button type="button" id="close-lightbox">关闭</button><img id="lightbox-image" alt="高光帧大图"></div><script>document.querySelectorAll('.frame-button').forEach(function(button){button.addEventListener('click',function(){document.getElementById('lightbox-image').src=button.dataset.frame;document.getElementById('lightbox').classList.add('open')})});function closeBox(){document.getElementById('lightbox').classList.remove('open');document.getElementById('lightbox-image').src=''}document.getElementById('close-lightbox').addEventListener('click',closeBox);document.getElementById('lightbox').addEventListener('click',function(e){if(e.target.id==='lightbox')closeBox()});document.addEventListener('keydown',function(e){if(e.key==='Escape')closeBox()});</script></body></html>""")
    return template.safe_substitute(style=style, overview=esc(overview), subtitle=esc(subtitle), candidate_count=esc(summary_metrics.get("candidateCount", "-")), selected_count=esc(summary_metrics.get("selectedCount", "-")), frame_count=str(sum(len([f for f in material_frames.get(str(item.get("material_id")), []) if f.get("available")]) for item in selected)), nav="".join(f'<a href="#material-{esc(item.get("material_id"))}">#{esc(item.get("rank"))} {esc(item.get("material_id"))}</a>' for item in selected), sections="".join(sections), materials="".join(materials))


def render_report(*, analysis_json, output_dir, fact_pack=None):
    analysis = _load_analysis(analysis_json)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    data = {"status": "complete", "analysis": analysis}
    write_json_atomically(data, output / "final-report-data.json")
    markdown = _render_markdown(analysis)
    (output / "final-report.md").write_text(markdown, encoding="utf-8")
    (output / "final-report.html").write_text(_render_html(analysis, _material_frames(fact_pack or {}), fact_pack or {}), encoding="utf-8")
    return 0
