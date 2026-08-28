"""Build report-aligned rows for the Chapter 04 highlight asset workbook."""

from collections import OrderedDict
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


HIGHLIGHT_CATEGORY_LABELS = {
    "portrait": "人像画面",
    "product": "产品画面",
    "other": "其他画面",
}
OTHER_BRAND = "其他品牌"


def match_brand_from_title(title, brands):
    """Return the first requested brand occurring in a material title."""
    text = str(title or "")
    for brand in brands or ():
        label = str(brand or "").strip()
        if label and label in text:
            return label
    return OTHER_BRAND


def _category_by_ref(presentation):
    mapping = {}
    chapter = presentation if isinstance(presentation, dict) else {}
    for category in chapter.get("categories", []):
        if not isinstance(category, dict):
            continue
        label = HIGHLIGHT_CATEGORY_LABELS.get(category.get("id"), category.get("id", ""))
        for frame in category.get("frames", []):
            if isinstance(frame, dict) and frame.get("frameRef"):
                mapping[str(frame["frameRef"])] = label
    for brand in chapter.get("brands", []):
        if not isinstance(brand, dict):
            continue
        for category in brand.get("categories", []):
            if not isinstance(category, dict):
                continue
            label = HIGHLIGHT_CATEGORY_LABELS.get(category.get("id"), category.get("id", ""))
            for frame in category.get("frames", []):
                if isinstance(frame, dict) and frame.get("frameRef"):
                    mapping[str(frame["frameRef"])] = label
    return mapping


def build_highlight_export_rows(fact_pack, presentation=None):
    """Return one Chinese-keyed row per available frame, matching report cards."""
    facts = fact_pack.get("materialFacts", []) if isinstance(fact_pack, dict) else []
    brands = (fact_pack.get("filters", {}) or {}).get("brands", []) if isinstance(fact_pack, dict) else []
    category_by_ref = _category_by_ref(presentation)
    rows = []
    for fact in facts:
        if not isinstance(fact, dict):
            continue
        material_id = str(fact.get("material_id") or "")
        title = str(fact.get("title") or material_id)
        brand = match_brand_from_title(title, brands)
        for frame in fact.get("highlightFrames", []):
            if not isinstance(frame, dict) or frame.get("available") is not True:
                continue
            frame_ref = str(frame.get("frame_ref") or "")
            frame_type = frame.get("frame_type") or ("cover" if frame.get("is_cover") else "click_peak")
            peak_rank = frame.get("peak_rank")
            frame_label = "封面画面" if frame_type == "cover" else f"点击 Top{peak_rank} 波峰画面"
            rows.append(OrderedDict([
                ("品牌", brand),
                ("视觉类型", category_by_ref.get(frame_ref, "其他画面")),
                ("素材排名", fact.get("rank")),
                ("素材 ID", material_id),
                ("素材标题", title),
                ("画面类型", frame_label),
                ("秒数", frame.get("second")),
                ("点击峰值排名", peak_rank if peak_rank is not None else "-"),
                ("点击指数", frame.get("click_value") if frame.get("click_value") is not None else "-"),
                ("frame_ref", frame_ref),
                ("本地图片路径", frame.get("relative_path") or frame.get("image_path") or ""),
            ]))
    return rows


def _resolve_frame_image_path(frame, asset_root=None):
    relative = str(frame.get("relative_path") or frame.get("image_path") or "").replace("\\", "/")
    if not relative:
        return ""
    path = Path(relative)
    candidates = [path] if path.is_absolute() else []
    if asset_root is not None and not path.is_absolute():
        root = Path(asset_root)
        candidates.extend((root / relative, root / "final-report" / "assets" / "highlight-frames" / path.relative_to("highlights") if relative.startswith("highlights/") else root / "final-report" / relative))
    return str(next((candidate.resolve() for candidate in candidates if candidate.is_file()), ""))


def export_highlight_workbook(fact_pack, presentation, output_path, asset_root=None):
    """Export report-aligned rows to a static XLSX workbook.

    The workbook is generated with the bundled artifact-tool runtime. If that
    runtime is unavailable, return ``None`` so HTML rendering remains usable.
    """
    rows = build_highlight_export_rows(fact_pack, presentation)
    for row in rows:
        material_id = row.get("素材 ID")
        frame = next((frame for fact in fact_pack.get("materialFacts", []) if str(fact.get("material_id")) == str(material_id) for frame in fact.get("highlightFrames", []) if str(frame.get("frame_ref")) == str(row.get("frame_ref"))), {})
        row["__image_path"] = _resolve_frame_image_path(frame, asset_root)
    if not rows:
        return None
    output_path = Path(output_path).resolve()
    node_path = os.environ.get("YUNTU_NODE_PATH") or shutil.which("node")
    bundled_node = Path("/Users/shuzida/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node")
    if bundled_node.is_file():
        node_path = str(bundled_node)
    configured_modules = os.environ.get("YUNTU_NODE_MODULES")
    module_root = Path(configured_modules) if configured_modules else Path()
    if not configured_modules or not module_root.is_dir():
        module_root = Path("/Users/shuzida/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules")
    builder = Path(__file__).with_name("build_highlight_workbook.mjs")
    if not node_path or not Path(node_path).is_file() or not module_root.is_dir() or not builder.is_file():
        return None
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="yuntu-highlight-xlsx-") as temp_dir:
        temp = Path(temp_dir)
        (temp / "node_modules").symlink_to(module_root, target_is_directory=True)
        temp_builder = temp / "build_highlight_workbook.mjs"
        temp_builder.write_text(builder.read_text(encoding="utf-8"), encoding="utf-8")
        input_path = temp / "highlight-rows.json"
        input_path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        result = subprocess.run(
            [str(node_path), str(temp_builder), str(input_path), str(output_path)],
            cwd=temp,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0 or not output_path.is_file():
            return None
        output_path.with_name(output_path.name + ".inspect.ndjson").unlink(missing_ok=True)
    return output_path
