# Yuntu Batch Phase 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove duplicate successful-detail persistence from the initial fetch and retry paths without changing collection behavior or artifacts.

**Architecture:** Add one private persistence helper in `yuntu_batch.py`. It will materialize gateway output, normalize and persist the detail record, register its artifact, and return the canonical selected-material entry. `fetch_batch()` will retain wave scheduling and highlighter submission; `_retry_batch_items()` will retain retry bookkeeping.

**Tech Stack:** Python 3, `unittest`, existing RPA I/O and Yuntu normalizer modules.

---

### Task 1: Share successful-detail persistence

**Files:**
- Modify: `tests/test_yuntu_batch.py`
- Modify: `scripts/yuntu_batch.py`

- [ ] **Step 1: Write the failing test**

Add a test that calls the planned `_persist_detail()` helper with a JSON gateway result and asserts the helper creates the normalized record, registers its checksum artifact, and returns the manifest entry common to both paths:

```python
def test_persist_detail_returns_common_selected_material_entry(self):
    batch = load_batch()
    item = {"rank": 1, "material_id": "101", "selectionGroupId": "default"}
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        contract = batch.run_state.collection_contract(
            shop_id="shop-42", list_params={},
            detail_date_params={"date_range_type": "LAST_7_DAYS"},
            target_top_n=1, candidate_top_n=1,
        )
        summary = batch.run_state.new_collection_summary(contract)
        detail, entry = batch._persist_detail(
            root=root, summary=summary, item=item,
            gateway_result=detail_result("101"), downloader=FakeDownloader({}),
            detail_fetch_sec=0.25,
        )

        self.assertEqual(detail["material_id"], "101")
        self.assertEqual(entry["material_id"], "101")
        self.assertEqual(entry["detailRecordPath"], "normalized/detail-records/101.json")
        self.assertEqual(entry["rawDetailPath"], "raw-json/details/101.json")
        self.assertEqual(entry["timingsSec"], {"detailFetchSec": 0.25})
        self.assertIn("detailRecord:101", summary["artifacts"])
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `python -m pytest tests/test_yuntu_batch.py::YuntuBatchTests::test_persist_detail_returns_common_selected_material_entry -q`

Expected: failure because `_persist_detail` is not defined.

- [ ] **Step 3: Implement the minimal persistence helper**

Add this private helper near `_invoke_detail_result`:

```python
def _persist_detail(*, root, summary, item, gateway_result, downloader, detail_fetch_sec):
    material_id = item["material_id"]
    raw_detail, detail_source = _materialize_records(
        gateway_result,
        csv_path=root / "raw-csv" / "details" / f"{material_id}.csv",
        json_path=root / "raw-json" / "details" / f"{material_id}.json",
        downloader=downloader,
    )
    detail = normalize_detail_records(
        raw_detail, material_id=material_id,
        source_path=_relative(root, detail_source),
        expected_selection_group=_expected_selection_group(item),
    )
    detail_path = root / "normalized" / "detail-records" / f"{material_id}.json"
    write_json_atomically(detail, detail_path)
    _record_artifact(summary, root, f"detailRecord:{material_id}", detail_path, "normalized_detail")
    return detail, {
        **_manifest_material(item),
        "listRecordPath": "normalized/list-records.json",
        "detailRecordPath": _relative(root, detail_path),
        "rawDetailPath": _relative(root, detail_source),
        "timingsSec": {"detailFetchSec": detail_fetch_sec},
    }
```

Replace the two duplicated materialize/normalize/write/register blocks. In `fetch_batch()`, add `postprocessStatus: "pending"` to the returned entry before append, update group counts, and submit the returned detail to its existing highlighter. In `_retry_batch_items()`, append the returned entry only when its material ID is not already selected.

- [ ] **Step 4: Run the focused test and verify GREEN**

Run: `python -m pytest tests/test_yuntu_batch.py::YuntuBatchTests::test_persist_detail_returns_common_selected_material_entry -q`

Expected: `1 passed`.

- [ ] **Step 5: Run affected and full regression suites**

Run:

```bash
python -m pytest tests/test_yuntu_batch.py -q
python -m pytest -q
```

Expected: both commands exit 0 with no test failures.

- [ ] **Step 6: Validate the existing real batch read-only**

Run:

```bash
python scripts/rpa_connector.py status \
  --output-dir "RPA数据汇总/yuntu-rankings-analysis-20260730-20260804-top2-real-run-phase2"
```

Expected: `status` remains `success`, with two persisted and two selected detail records.

- [ ] **Step 7: Commit implementation**

```bash
git add scripts/yuntu_batch.py tests/test_yuntu_batch.py \
  docs/superpowers/plans/2026-08-20-yuntu-batch-phase3-implementation.md
git commit -m "refactor: share yuntu detail persistence"
```
