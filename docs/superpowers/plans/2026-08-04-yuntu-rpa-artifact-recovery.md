# 云图 RPA 产物接收与可恢复执行 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every successful Yuntu RPA result materialize into a verified run directory and ensure later stages reuse local artifacts instead of invoking RPA again.

**Architecture:** Add a focused run-state module for fingerprints, artifact records, checksums, and `run-summary.json`. Extend the existing RPA IO/batch layers to recover a CSV from an explicitly scoped attachment directory only when direct download fails. The connector becomes the state-transition boundary: fetch creates or resumes a run, while analysis and rendering advance only local stages.

**Tech Stack:** Python 3.9+, standard library (`hashlib`, `shutil`, `json`), `requests`, `unittest`.

---

### Task 1: Run State and Artifact Contract

**Files:**
- Create: `scripts/yuntu_run_state.py`
- Create: `tests/test_yuntu_run_state.py`

- [ ] **Step 1: Write failing tests for a stable parameter fingerprint and verified artifact record.**

```python
def test_register_artifact_writes_relative_path_checksum_and_size(self):
    state = load_run_state()
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "raw-csv" / "list.csv"
        source.parent.mkdir()
        source.write_text("material_id\n101\n", encoding="utf-8")
        summary = state.new_run_summary(root, {"industry": "食品饮料"})

        state.register_artifact(summary, root, "ranking_list", source, "local_artifact")

        artifact = summary["artifacts"]["ranking_list"]
        self.assertEqual(artifact["path"], "raw-csv/list.csv")
        self.assertEqual(artifact["sizeBytes"], source.stat().st_size)
        self.assertEqual(len(artifact["sha256"]), 64)
```

- [ ] **Step 2: Run the test and verify RED.**

Run: `python -m unittest tests/test_yuntu_run_state.py -v`

Expected: ERROR because `scripts/yuntu_run_state.py` does not exist.

- [ ] **Step 3: Implement the minimal run-state API.**

```python
def parameter_fingerprint(filters):
    encoded = json.dumps(filters, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

def new_run_summary(root, filters):
    return {"schemaVersion": 1, "runId": uuid.uuid4().hex,
            "parameterFingerprint": parameter_fingerprint(filters),
            "filters": filters, "status": "collecting", "artifacts": {},
            "nextAction": {"command": "fetch", "allowsRpa": True}}

def register_artifact(summary, root, key, path, source):
    source_path = Path(path)
    if not source_path.is_file() or source_path.stat().st_size == 0:
        raise YuntuRunStateError("artifact must be a nonempty file")
    summary["artifacts"][key] = {"path": str(source_path.relative_to(root)),
        "source": source, "sizeBytes": source_path.stat().st_size,
        "sha256": sha256_file(source_path), "parseStatus": "pending"}
```

- [ ] **Step 4: Run the module test and verify GREEN.**

Run: `python -m unittest tests/test_yuntu_run_state.py -v`

Expected: PASS.

### Task 2: Scoped Local-Artifact Materialization

**Files:**
- Modify: `scripts/rpa_io.py`
- Modify: `scripts/yuntu_batch.py`
- Modify: `tests/test_rpa_io.py`
- Modify: `tests/test_yuntu_batch.py`

- [ ] **Step 1: Write failing tests for exact, unambiguous local artifact recovery.**

```python
def test_copy_local_artifact_rejects_missing_and_ambiguous_candidates(self):
    io = load_io()
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        incoming = root / "incoming"; incoming.mkdir()
        (incoming / "list-a.csv").write_text("x\n1\n", encoding="utf-8")
        (incoming / "list-b.csv").write_text("x\n2\n", encoding="utf-8")
        with self.assertRaisesRegex(io.RpaIoError, "ambiguous"):
            io.materialize_local_artifact(incoming, root / "out.csv", suffix=".csv")
```

- [ ] **Step 2: Run these tests and verify RED.**

Run: `python -m unittest tests/test_rpa_io.py tests/test_yuntu_batch.py -v`

Expected: ERROR because `materialize_local_artifact` is undefined.

- [ ] **Step 3: Implement bounded artifact selection, atomic copy, and batch fallback.**

```python
def materialize_local_artifact(input_dir, target_path, *, suffix):
    candidates = sorted(path for path in Path(input_dir).iterdir()
                        if path.is_file() and path.suffix.lower() == suffix)
    if len(candidates) != 1:
        raise RpaIoError("local RPA artifact is missing or ambiguous")
    return copy_file_atomically(candidates[0], target_path)
```

`_materialize_records` must try the signed URL first. On download failure it may call this helper only when `artifact_input_dir` is explicitly supplied. It must parse the copied CSV before returning, and report whether the source was `download` or `local_artifact` to the caller.

- [ ] **Step 4: Run targeted tests and verify GREEN.**

Run: `python -m unittest tests/test_rpa_io.py tests/test_yuntu_batch.py -v`

Expected: PASS, including a test proving the batch uses a scoped local CSV without making another RPA invocation.

### Task 3: Idempotent Fetch and Summary State Transitions

**Files:**
- Modify: `scripts/yuntu_batch.py`
- Modify: `scripts/rpa_connector.py`
- Modify: `tests/test_yuntu_batch.py`
- Modify: `tests/test_rpa_connector.py`

- [ ] **Step 1: Write failing tests for same-fingerprint reuse and explicit refresh.**

```python
def test_fetch_reuses_complete_local_run_without_invoking_rpa(self):
    batch = load_batch()
    invoker = FakeInvoker(self.files_result("https://unused/list.csv"), [])
    with prepared_complete_run() as root:
        status = batch.fetch_batch(..., output_dir=root, invoker=invoker)
    self.assertEqual(status, 0)
    self.assertEqual(invoker.list_calls, [])
    self.assertEqual(invoker.detail_calls, [])
```

- [ ] **Step 2: Run the tests and verify RED.**

Run: `python -m unittest tests/test_yuntu_batch.py tests/test_rpa_connector.py -v`

Expected: FAIL because fetch currently always invokes the ranking-list RPA.

- [ ] **Step 3: Implement resume-or-refresh behavior and CLI flags.**

`fetch_batch` must load `run-summary.json` before invoking RPA. If its fingerprint matches and its registered list/detail artifacts pass checksum and parse checks, refresh `nextAction` to local analysis and return without invoking `invoker`. Add `--artifact-input-dir` and `--refresh` to the `fetch` parser; `--refresh` is the only way to replace a matching complete run.

- [ ] **Step 4: Run the tests and verify GREEN.**

Run: `python -m unittest tests/test_yuntu_batch.py tests/test_rpa_connector.py -v`

Expected: PASS.

### Task 4: Local-Only Analysis, Rendering, and Operator Contract

**Files:**
- Modify: `scripts/rpa_connector.py`
- Modify: `scripts/yuntu_analysis.py`
- Modify: `scripts/yuntu_report.py`
- Modify: `SKILL.md`
- Modify: `tests/test_yuntu_analysis.py`
- Modify: `tests/test_yuntu_report.py`
- Modify: `tests/test_skill_contract.py`

- [ ] **Step 1: Write failing tests for local stage transitions.**

```python
def test_render_failure_marks_report_pending_without_rpa_retry(self):
    with prepared_analysis_run() as root:
        with self.assertRaises(YuntuReportError):
            render_report(root / "diagnostic-analysis" / "invalid.json", root / "final-report")
        summary = load_summary(root)
    self.assertEqual(summary["status"], "report_pending")
    self.assertFalse(summary["nextAction"]["allowsRpa"])
```

- [ ] **Step 2: Run the tests and verify RED.**

Run: `python -m unittest tests/test_yuntu_analysis.py tests/test_yuntu_report.py tests/test_skill_contract.py -v`

Expected: FAIL because local stages do not update `run-summary.json`.

- [ ] **Step 3: Implement state transitions and document the single standard workflow.**

`prepare-analysis` must require a valid materialized run and set `analysis_pending`; `render-report` must record `report_pending` on contract errors and `complete` only after all three final artifacts are nonempty. Rewrite `SKILL.md` so operators run `fetch`, read `run-summary.json`, then run only the stated local next action. The skill must explicitly prohibit rerunning RPA for analysis/report failures and show `--refresh` as the sole opt-in exception.

- [ ] **Step 4: Run targeted tests and verify GREEN.**

Run: `python -m unittest tests/test_yuntu_analysis.py tests/test_yuntu_report.py tests/test_skill_contract.py -v`

Expected: PASS.

### Task 5: Full Regression and Documentation Verification

**Files:**
- Modify only if verification exposes an issue: files from Tasks 1-4

- [ ] **Step 1: Run the complete suite.**

Run: `python -m unittest discover -s tests -v`

Expected: PASS with zero failures and errors.

- [ ] **Step 2: Inspect the CLI and operator instructions.**

Run: `python scripts/rpa_connector.py fetch --help && python scripts/rpa_connector.py prepare-analysis --help && python scripts/rpa_connector.py render-report --help`

Expected: `fetch` exposes `--artifact-input-dir` and `--refresh`; local-stage commands require no RPA input.

- [ ] **Step 3: Verify the changed-file set.**

Run: `git diff --check && git status --short`

Expected: no whitespace errors; only the planned implementation, tests, skill, design, and plan files are modified.
