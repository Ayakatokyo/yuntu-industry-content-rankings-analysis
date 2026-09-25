"""Model navigation preserves every bound fact and successful image."""
import json
from pathlib import Path
import sys

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from test_analysis_stability import fixture
import yuntu_analysis as preparation
import yuntu_analysis_workspace as workspace
from analysis_task_io import pretty_json, restore_task_pages
from rpa_io import write_json_atomically
from yuntu_analysis_bundle import AnalysisBundleError


def image_fixture(root, count=43):
    facts, _, manifest = fixture(root)
    facts["analysisQualityVersion"] = 4
    facts["scriptFacts"] = preparation.build_script_facts(facts["materialFacts"], facts["selectedMaterials"])
    facts["materialFacts"][0]["title"] = "早餐豆浆"
    facts["materialFacts"][1]["title"] = "另一素材"
    for index in range(count):
        mid = "101" if index < 23 else "102"
        path = root.parent / f"frame-{index}.jpg"
        Image.new("RGB", (2, 2), (index, 0, 0)).save(path)
        frame = {"frame_ref": f"highlight:{mid}:click_peak:{index}", "frame_type": "click_peak",
                 "second": index, "available": True, "image_path": path.name}
        facts["materialFacts"][0 if mid == "101" else 1]["highlightFrames"].append(frame)
        facts["visualAssets"].append({**frame, "material_id": mid})
    facts["materialFacts"][0]["highlightFrames"].insert(0, {
        "frame_ref": "highlight:101:click_peak:failed", "available": False, "failure_reason": "not downloaded"})
    write_json_atomically(preparation._report_data(facts), root / "report-data.json")
    preparation._write_analysis_units(facts, root)
    return facts, manifest


def read_section(root, part, section):
    first = workspace.read_task(root, part, section=section)
    pages = [first["records"]]
    for page in range(1, first["pageCount"]):
        result = workspace.read_task(root, part, page, section=section)
        assert len(pretty_json(result).encode()) < 12500
        pages.append(result["records"])
    return restore_task_pages(pages)


def test_navigation_exposes_scopes_sections_and_canonical_source_without_prose(tmp_path):
    _, _, manifest = fixture(tmp_path / "facts")
    root = tmp_path / "drafts"
    workspace.begin_workspace(manifest, root)
    navigation = workspace.read_workspace_navigation(root)
    parts = {part["part"]: part for part in navigation["parts"]}
    assert parts["material-101"]["draft"] == "material-101.json"
    assert parts["material-101"]["materialId"] == "101"
    assert parts["material-101"]["scriptTextAvailable"] is True
    assert parts["material-102"]["scriptTextAvailable"] is False
    assert parts["audience"]["scopes"] == ["all", "空品牌"]
    assert parts["material-101"]["sectionPages"]["facts"] >= 1
    assert parts["material-101"]["sectionPages"]["skeleton"] >= 1
    assert Path(navigation["promptPath"]).is_file()
    assert navigation["frames"]["successfulCount"] == 0
    assert navigation["frames"]["batchCount"] == 0
    assert "早餐可选豆浆" not in json.dumps(navigation, ensure_ascii=False)


def test_section_read_is_lossless_smaller_and_keeps_binding_checks(tmp_path):
    _, _, manifest = fixture(tmp_path / "facts")
    root = tmp_path / "drafts"
    workspace.begin_workspace(manifest, root)
    original = json.loads((root / "material-101.task.json").read_text())
    facts = read_section(root, "material-101", "facts")
    assert facts == {"scopedFacts": original["scopedFacts"]}
    assert read_section(root, "material-101", "schema") == {"outputSchema": original["outputSchema"]}
    assert read_section(root, "material-101", "skeleton") == {"outputSkeleton": original["outputSkeleton"]}
    assert len(pretty_json(facts).encode()) < len(pretty_json(original).encode()) / 2
    assert "scopedFacts" not in read_section(root, "material-101", "guidance")
    with pytest.raises(AnalysisBundleError, match="section"):
        workspace.read_task(root, "material-101", section="unknown")
    source = root / "material-101.task.json"
    source.write_text(source.read_text() + " ")
    with pytest.raises(AnalysisBundleError, match="model task input"):
        workspace.read_task(root, "material-101", section="facts")


def test_frame_batches_cover_all_successes_once_and_map_both_drafts(tmp_path):
    _, manifest = image_fixture(tmp_path / "facts")
    root = tmp_path / "drafts"
    workspace.begin_workspace(manifest, root)
    batches = [workspace.read_frame_batch(root, batch=i) for i in range(3)]
    assert [len(batch["frames"]) for batch in batches] == [20, 20, 3]
    assert [batch["nextBatch"] for batch in batches] == [1, 2, None]
    frames = [frame for batch in batches for frame in batch["frames"]]
    assert [frame["frame_ref"] for frame in frames] == [
        f"highlight:{'101' if i < 23 else '102'}:click_peak:{i}" for i in range(43)]
    assert frames[0]["highlightIndex"] == 0
    assert frames[0]["materialObservationIndex"] == 0
    assert frames[23]["materialPart"] == "material-102"
    assert frames[23]["materialObservationIndex"] == 0
    for frame in frames:
        assert Path(frame["image_path"]).is_file()
        material = json.loads((root / f"{frame['materialPart']}.json").read_text())
        assert material["content"]["frame_observations"][frame["materialObservationIndex"]]["frame_ref"] == frame["frame_ref"]
    highlight = json.loads((root / "highlight.json").read_text())
    assert highlight["viewedFrameRefs"] == []
    assert highlight["content"]["highlightDashboard"]["frameUnderstanding"][42]["subject"] is None
    assert batches[0]["writeTargets"]["understanding"] == "highlight.json#/content/highlightDashboard/frameUnderstanding"
    assert "standard_category" in batches[0]["understandingSchema"]["required"]
    assert all(len(pretty_json(batch).encode()) < 16000 for batch in batches)
    assert workspace.read_workspace_navigation(root)["frames"]["batchCount"] == 3


@pytest.mark.parametrize("batch,size", [(-1, 20), (3, 20), (0, 0), (0, 21), (True, 20), (0, True)])
def test_frame_batch_rejects_invalid_bounds(tmp_path, batch, size):
    _, manifest = image_fixture(tmp_path / "facts")
    root = tmp_path / "drafts"
    workspace.begin_workspace(manifest, root)
    with pytest.raises(AnalysisBundleError):
        workspace.read_frame_batch(root, batch=batch, batch_size=size)


def test_frame_read_still_rejects_changed_successful_image(tmp_path):
    _, manifest = image_fixture(tmp_path / "facts", count=1)
    root = tmp_path / "drafts"
    workspace.begin_workspace(manifest, root)
    (tmp_path / "frame-0.jpg").write_bytes(b"changed")
    with pytest.raises(AnalysisBundleError, match="visual asset"):
        workspace.read_frame_batch(root)


def test_script_guidance_explains_cited_material_scope_and_original_sources(tmp_path):
    facts, _, manifest = fixture(tmp_path / "facts")
    facts["brandScope"] = {"version": 1, "mode": "all_industry", "brands": [], "aggregateLabel": "全行业"}
    write_json_atomically(preparation._report_data(facts), tmp_path / "facts" / "report-data.json")
    preparation._write_analysis_units(facts, tmp_path / "facts")
    root = tmp_path / "drafts"
    workspace.begin_workspace(manifest, root)
    guidance = read_section(root, "script", "guidance")
    assert guidance["scope"] == "全行业"
    ranking = json.loads((root / "ranking.json").read_text())["content"]["topMaterialCombination"]
    assert ranking["brandConclusions"] == []
    assert ranking["allBrandsConclusion"]["classificationSource"] == "scope_aggregate"
    assert guidance["quoteSourcePaths"] == [
        "scopedFacts.materials[].script_text", "scopedFacts.materials[].content_formula.labels",
        "scopedFacts.materials[].content_formula.sources.script.detail"]
    assert "material_ids" in guidance["evidenceFormat"]
