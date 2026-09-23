# 可配置云图采集基础技能 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an independently installable Yuntu skill that collects configured ranking and detail data, persists normalized artifacts, and extracts configured highlight frames.

**Architecture:** Create a sibling skill repository at `../yuntu-configurable-collection`. Copy the proven RPA, CSV IO, normalization, run-state, batch, and frame-extraction modules, then add a configuration layer that resolves `QuerySpec` and `HighlightSpec` before the batch orchestrator runs. The collector CLI is the only public execution entry point; it saves resolved configurations in the output directory and supplies them to the batch contract.

**Tech Stack:** Python 3.13, `requests`, `imageio-ffmpeg`, `unittest`, fixed Yuce RPA gateway connectors, ffmpeg.

---

## File Structure

```text
../yuntu-configurable-collection/
  SKILL.md                         # Skill trigger, two input modes, collection-only boundary
  agents/openai.yaml               # Codex UI metadata
  requirements.txt                 # requests and imageio-ffmpeg
  references/                      # Copied fixed platform and connector contracts
  scripts/
    collector.py                   # Public CLI and RPA transport wrappers
    config_specs.py                # QuerySpec / HighlightSpec parse, resolution, conversion and persistence
    rpa_io.py                      # Copied gateway and CSV helpers
    yuntu_normalizer.py            # Copied normalized list/detail schema
    yuntu_run_state.py             # Copied persistent contract and artifact helpers
    yuntu_batch.py                 # Batch orchestration accepting HighlightSpec
    yuntu_highlights.py            # Configured candidate selection and non-blocking JPEG extraction
  tests/
    test_config_specs.py           # Spec resolution and error cases
    test_collector.py              # Configured CLI argument wiring
    test_yuntu_highlights.py       # Strategy selection and same-second merge
    test_yuntu_batch.py            # Resolved configuration persistence and configured highlighter integration
    test_migration_boundary.py     # No analysis/report dependency is present
```

### Task 1: Bootstrap the independent skill skeleton

**Files:**
- Create: `../yuntu-configurable-collection/{SKILL.md,agents/openai.yaml,requirements.txt}`
- Create: `../yuntu-configurable-collection/references/platforms/juliang-yt.md`
- Create: `../yuntu-configurable-collection/references/connectors/juliang-yt/rpa_conn_juliang_yt_industry_content_rankings_{list,detail}.md`
- Create: `../yuntu-configurable-collection/scripts/{rpa_io.py,yuntu_normalizer.py,yuntu_run_state.py,yuntu_batch.py,yuntu_highlights.py}`
- Create: `../yuntu-configurable-collection/tests/{test_rpa_io.py,test_yuntu_normalizer.py,test_yuntu_run_state.py}`

- [ ] **Step 1: Create the sibling repository and its Git ignore rules**

Run:

```bash
mkdir -p ../yuntu-configurable-collection
mkdir -p ../yuntu-configurable-collection/{agents,references,scripts,tests}
git -C ../yuntu-configurable-collection init -b main
printf '__pycache__/\n*.py[cod]\nruns/\n' > ../yuntu-configurable-collection/.gitignore
```

- [ ] **Step 2: Copy only A-F dependencies and their direct regression tests**

Run:

```bash
cp requirements.txt ../yuntu-configurable-collection/
cp -R references ../yuntu-configurable-collection/
cp scripts/rpa_io.py scripts/yuntu_normalizer.py scripts/yuntu_run_state.py scripts/yuntu_batch.py scripts/yuntu_highlights.py ../yuntu-configurable-collection/scripts/
cp tests/test_rpa_io.py tests/test_yuntu_normalizer.py tests/test_yuntu_run_state.py ../yuntu-configurable-collection/tests/
```

- [ ] **Step 3: Run the copied unit tests to establish the migration baseline**

Run: `python -m unittest discover -s tests -p 'test_rpa_io.py' -v && python -m unittest discover -s tests -p 'test_yuntu_normalizer.py' -v && python -m unittest discover -s tests -p 'test_yuntu_run_state.py' -v`

Expected: all copied tests pass; imports must not refer to the original repository path.

- [ ] **Step 4: Commit the independent skeleton**

```bash
git -C ../yuntu-configurable-collection add .
git -C ../yuntu-configurable-collection commit -m "chore: bootstrap configurable yuntu collection skill"
```

### Task 2: Add resolved configuration contracts

**Files:**
- Create: `../yuntu-configurable-collection/scripts/config_specs.py`
- Create: `../yuntu-configurable-collection/tests/test_config_specs.py`

- [ ] **Step 1: Write the failing QuerySpec resolution tests**

```python
def test_resolve_query_spec_applies_defaults_and_translates_to_rpa_params():
    resolved = resolve_query_spec({
        "schema_version": 1,
        "source": "juliang_yuntu_industry_content_rankings",
        "industry": "食品饮料",
        "period": {"type": "LAST_7_DAYS"},
        "ranking": {"metric": "CTR_TOP1000"},
    })
    assert resolved["collection"] == {"target_top_n": 10, "candidate_top_n": 20}
    assert query_to_rpa_params(resolved)["ranking_limit_type"] == "CTR_TOP1000"
    assert detail_to_rpa_params(resolved) == {"date_range_type": "LAST_7_DAYS"}

def test_resolve_query_spec_rejects_unknown_field_and_invalid_brand_scope():
    with pytest.raises(ConfigSpecError, match="unknown QuerySpec fields"):
        resolve_query_spec(valid_query(extra=True))
    with pytest.raises(ConfigSpecError, match="SPECIFIED_BRANDS"):
        resolve_query_spec(valid_query(filters={"brand_scope": {"type": "SPECIFIED_BRANDS", "brands": []}}))
```

- [ ] **Step 2: Run the tests to verify failure**

Run: `python -m pytest tests/test_config_specs.py -q`

Expected: FAIL because `config_specs` does not exist.

- [ ] **Step 3: Implement strict QuerySpec resolution**

Implement these public functions in `scripts/config_specs.py`:

Public API: `ConfigSpecError`, `resolve_query_spec(payload)`, `query_to_rpa_params(resolved)`, `detail_to_rpa_params(resolved)`, `resolve_highlight_spec(payload)`, `spec_fingerprint(query, highlights)`, and `write_resolved_specs(output_dir, query, highlights)`.

Require top-level `schema_version`, `source`, `industry`, `period`, and `ranking`; fill omitted `filters` with empty filter lists and `ALL_INDUSTRY`, and fill omitted `collection` with `target_top_n=10` and `candidate_top_n=target_top_n * 2`. Reproduce the current connector's date, ranking, brand, and demographic validation in the resolver. Translate the nested schema to the existing flat `list_params` and detail date parameters before returning.

- [ ] **Step 4: Write failing HighlightSpec resolution tests**

```python
def test_resolve_highlight_spec_defaults_all_five_metrics():
    resolved = resolve_highlight_spec({"schema_version": 1})
    assert resolved["include_cover"] is True
    assert set(resolved["metrics"]) == {"点赞指数", "流失指数", "点击指数", "互动指数", "评论指数"}

def test_resolve_highlight_spec_rejects_unknown_strategy_and_nonpositive_limit():
    with pytest.raises(ConfigSpecError, match="strategy"):
        resolve_highlight_spec({"schema_version": 1, "metrics": {"点击指数": {"strategy": "median", "limit": 1}}})
    with pytest.raises(ConfigSpecError, match="limit"):
        resolve_highlight_spec({"schema_version": 1, "metrics": {"点击指数": {"strategy": "absolute_max", "limit": 0}}})
```

- [ ] **Step 5: Implement HighlightSpec resolution and atomic persistence**

Implement `resolve_highlight_spec(payload: dict) -> dict`. Allow only the five specified metrics and strategies `local_peaks` and `absolute_max`; default unspecified metrics to `{strategy: "local_peaks", limit: 3}` and `include_cover=True`. Reuse `write_json_atomically` to write `resolved-query-spec.json` and `resolved-highlight-spec.json`, and fingerprint canonical JSON with sorted keys and SHA-256.

- [ ] **Step 6: Run configuration tests and commit**

Run: `python -m pytest tests/test_config_specs.py -q`

Expected: PASS.

```bash
git -C ../yuntu-configurable-collection add scripts/config_specs.py tests/test_config_specs.py
git -C ../yuntu-configurable-collection commit -m "feat: add resolved collection specifications"
```

### Task 3: Make highlighter selection policy-driven

**Files:**
- Modify: `../yuntu-configurable-collection/scripts/yuntu_highlights.py`
- Create: `../yuntu-configurable-collection/tests/test_yuntu_highlights.py`

- [ ] **Step 1: Write failing candidate-selection tests**

```python
def test_select_candidates_uses_per_metric_peak_and_absolute_max_rules():
    candidates = select_highlight_candidates_by_spec(detail_with_click_and_like(), {
        "include_cover": True,
        "metrics": {
            "点击指数": {"strategy": "local_peaks", "limit": 2},
            "点赞指数": {"strategy": "absolute_max", "limit": 1},
        },
    })
    assert [candidate["second"] for candidate in candidates] == [0, 1, 3, 4]
    assert candidates[-1]["reasons"] == [{"type": "absolute_max", "trend_name": "点赞指数", "value": 12, "rank": 1, "within_high_point": False}]

def test_select_candidates_merges_same_second_and_retains_all_reasons():
    candidates = select_highlight_candidates_by_spec(detail_with_shared_second(), spec_for_click_and_like())
    shared = next(item for item in candidates if item["second"] == 5)
    assert {reason["trend_name"] for reason in shared["reasons"]} == {"点击指数", "点赞指数"}
```

- [ ] **Step 2: Run the tests to verify failure**

Run: `python -m pytest tests/test_yuntu_highlights.py -q`

Expected: FAIL because `select_highlight_candidates_by_spec` does not exist.

- [ ] **Step 3: Implement policy selection and per-detail frame generation**

Add:

Public API: `select_highlight_candidates_by_spec(detail, highlight_spec)`, `generate_highlights_for_detail(detail, output_dir, highlight_spec, *, downloader, frame_extractor, batch_extractor, ffmpeg_bin)`, and `details_missing_highlights_by_spec(details, output_dir, highlight_spec)`.

For `absolute_max`, normalize the source series, select the largest value, use the earliest second for ties, and return one reason with `type="absolute_max"`. For `local_peaks`, reuse `_local_peaks(series, limit=limit)`. Add a cover candidate only when `include_cover` is true. Merge candidates by second, append all reasons, and sort cover first then non-cover by second. Write the resolved policy fingerprint into `highlights-manifest.json` so old frames are reusable only for the same policy.

- [ ] **Step 4: Run highlighter tests and commit**

Run: `python -m pytest tests/test_yuntu_highlights.py -q`

Expected: PASS.

```bash
git -C ../yuntu-configurable-collection add scripts/yuntu_highlights.py tests/test_yuntu_highlights.py
git -C ../yuntu-configurable-collection commit -m "feat: support configured highlight policies"
```

### Task 4: Integrate configurations with batch collection

**Files:**
- Modify: `../yuntu-configurable-collection/scripts/yuntu_run_state.py`
- Modify: `../yuntu-configurable-collection/scripts/yuntu_batch.py`
- Create: `../yuntu-configurable-collection/tests/test_yuntu_batch.py`

- [ ] **Step 1: Write failing contract and orchestration tests**

```python
def test_collection_contract_changes_when_resolved_highlight_spec_changes():
    first = collection_contract(
        shop_id="shop", list_params={"industry": "食品饮料"},
        detail_date_params={"date_range_type": "LAST_7_DAYS"},
        target_top_n=1, candidate_top_n=2, configuration_fingerprint="a" * 64,
    )
    second = collection_contract(
        shop_id="shop", list_params={"industry": "食品饮料"},
        detail_date_params={"date_range_type": "LAST_7_DAYS"},
        target_top_n=1, candidate_top_n=2, configuration_fingerprint="b" * 64,
    )
    assert not collection_contract_matches(new_collection_summary(first), second)

def test_fetch_batch_passes_highlight_spec_to_postprocess(tmp_path):
    status = fetch_batch(
        shop_id="shop", list_params={"industry": "食品饮料"},
        detail_date_params={"date_range_type": "LAST_7_DAYS"}, target_top_n=1,
        candidate_top_n=1, output_dir=tmp_path, invoker=FakeInvoker(list_result(), detail_results()),
        highlight_spec=resolved_highlights(), configuration_fingerprint="a" * 64,
    )
    assert status == 0
    manifest = json.loads((tmp_path / "highlights-manifest.json").read_text())
    assert manifest["highlightSpecFingerprint"] == fingerprint(resolved_highlights())
```

- [ ] **Step 2: Run batch tests to verify failure**

Run: `python -m pytest tests/test_yuntu_batch.py -q`

Expected: FAIL because the batch API has no `highlight_spec` or configuration fingerprint.

- [ ] **Step 3: Extend the contract and batch API without changing scheduling behavior**

Add `configuration_fingerprint` to `collection_contract()` and preserve it in `run-summary.json`. Add `highlight_spec` and `configuration_fingerprint` keyword-only arguments to `fetch_batch()`, `retry_failed_batch()`, and `retry_unresolved_batch()`. Replace fixed standard-highlighter calls with `generate_highlights_for_detail()` and policy-aware missing-frame checks. Preserve all current detail-wave concurrency, highlighter concurrency, candidate replacement, status, manifest, and retry semantics.

- [ ] **Step 4: Run batch and copied regression tests and commit**

Run: `python -m pytest tests/test_yuntu_batch.py tests/test_rpa_io.py tests/test_yuntu_normalizer.py tests/test_yuntu_run_state.py -q`

Expected: PASS.

```bash
git -C ../yuntu-configurable-collection add scripts/yuntu_batch.py scripts/yuntu_run_state.py tests/test_yuntu_batch.py
git -C ../yuntu-configurable-collection commit -m "feat: bind batch collection to resolved highlight policy"
```

### Task 5: Build the collector CLI and skill instructions

**Files:**
- Create: `../yuntu-configurable-collection/scripts/collector.py`
- Create: `../yuntu-configurable-collection/tests/test_collector.py`
- Create: `../yuntu-configurable-collection/tests/test_migration_boundary.py`
- Create: `../yuntu-configurable-collection/SKILL.md`
- Create: `../yuntu-configurable-collection/agents/openai.yaml`

- [ ] **Step 1: Write failing collector tests**

```python
def test_validate_writes_no_output_and_prints_resolved_specs(tmp_path, capsys):
    status = main(["validate", "--query-spec", str(query_path), "--highlight-spec", str(highlight_path)])
    assert status == 0
    assert '"schema_version": 1' in capsys.readouterr().out

def test_collect_writes_resolved_specs_before_calling_batch(tmp_path, monkeypatch):
    monkeypatch.setattr(collector, "fetch_batch", fake_fetch)
    assert main(["collect", "--shop-id", "shop", "--query-spec", str(query_path), "--highlight-spec", str(highlight_path), "--output-dir", str(tmp_path)]) == 0
    assert (tmp_path / "resolved-query-spec.json").exists()
    assert (tmp_path / "resolved-highlight-spec.json").exists()
```

- [ ] **Step 2: Run collector tests to verify failure**

Run: `python -m pytest tests/test_collector.py -q`

Expected: FAIL because `collector.py` does not exist.

- [ ] **Step 3: Implement the public CLI**

Provide `list-accounts`, `validate`, `collect`, `status`, `retry-failed`, and `retry-unresolved`. `collect` must load and resolve both JSON files, write them before RPA invocation, build a `ConnectorInvoker` from fixed `invoke_list` and `invoke_detail`, then call `fetch_batch` with converted RPA parameters and the configuration fingerprint. The retry commands must read saved resolved specs, reject missing files, and pass their fingerprint and policy back to the batch API. Do not expose function codes, raw arbitrary RPA fields, or analysis/report commands.

- [ ] **Step 4: Write and run the migration-boundary test**

```python
def test_skill_does_not_ship_or_import_analysis_and_reporting_code():
    script_names = {path.name for path in (ROOT / "scripts").glob("*.py")}
    assert not {"yuntu_analysis.py", "yuntu_report.py", "yuntu_presentation.py"} & script_names
    source = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "scripts").glob("*.py"))
    assert "yuntu_analysis" not in source
    assert "yuntu_report" not in source
```

Run: `python -m pytest tests/test_collector.py tests/test_migration_boundary.py -q`

Expected: PASS.

- [ ] **Step 5: Write concise skill instructions and UI metadata**

Document the two input modes: convert user language into a JSON configuration, show it for confirmation, save it, then invoke `collect`; or directly use user-supplied JSON files. Document only collection outputs, fixed connector credential boundaries, supported fields, policies, commands, retry requirements, and the explicit exclusion of business analysis/reporting.

- [ ] **Step 6: Run full regression and commit the completed base skill**

Run: `python -m pytest -q`

Expected: PASS.

```bash
git -C ../yuntu-configurable-collection add .
git -C ../yuntu-configurable-collection commit -m "feat: add configurable yuntu collection skill"
```

### Task 6: Run a controlled verification pass

**Files:**
- Create: `../yuntu-configurable-collection/tests/fixtures/query-spec.json`
- Create: `../yuntu-configurable-collection/tests/fixtures/highlight-spec.json`

- [ ] **Step 1: Add representative configuration fixtures**

Use a `CUSTOM` period, three brands, one demographic filter, a `CTR_TOP1000` ranking, and a mix of both supported frame-selection strategies.

- [ ] **Step 2: Verify offline configuration and CLI behavior**

Run:

```bash
python scripts/collector.py validate --query-spec tests/fixtures/query-spec.json --highlight-spec tests/fixtures/highlight-spec.json
python -m pytest -q
```

Expected: validation prints resolved configurations without credentials or RPA traffic; all tests pass.

- [ ] **Step 3: Record the verification boundary**

Do not run live RPA without the platform-provided credentials and an explicit collection request. Verify that test output, fixtures, manifests, and Git history contain no credential values.
