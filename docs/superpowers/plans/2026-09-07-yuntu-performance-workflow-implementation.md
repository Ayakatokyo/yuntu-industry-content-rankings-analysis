# 云图取数后处理与分析工作流实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将云图技能改造为“采集后明确处理并封存快照、问题驱动地选择事实、可恢复分析和按需交付”的工作流，且不改变客户商业分析逻辑和现有完整报告交付。

**Architecture:** 保持 M0 连接器迁移、规范化和报告渲染为现有边界；新增后处理、快照和分析编排三个小模块。所有分析从经验证快照读取，模型只消费 `analysis-input.json` 中被允许的事实，报告只消费已验证的分析 attempt。

**Tech Stack:** Python 3、标准库 `dataclasses/json/hashlib/pathlib`、现有 `requests`、`unittest`、现有 `write_json_atomically`/`yuntu_run_state`/报告渲染器；不增加服务、数据库、队列或外部模型运行依赖。

**Spec:** [云图取数后处理与分析工作流实施契约](../specs/2026-09-07-yuntu-workflow-implementation-contract.md)

## Global Constraints

- 本计划在 M0 新连接器迁移验收后执行；M1 的离线测试可先开发，但不得替换线上连接器或请求旧详情连接器。
- 保留客户输入的业务分析方法、现有五章 JSON schema、Excel、离线 HTML/ZIP；不新增默认商业诊断、阈值或评分。
- `prepare-analysis`、对话分析和渲染均不得 RPA、下载视频、FFmpeg 或改写源 run。
- 历史数据只读；测试只使用 fixture、临时目录或独立新 run，绝不覆盖历史 RPA 数据、报告、ZIP、执行日志。
- 快照与分析仅允许 root-contained、非空、SHA-256 匹配的 artifact；不能按 mtime 推断“最新批次”。
- 只有当前宿主对话模型生成商业结论；禁止外部模型子进程及程序化结论兜底。
- 每个任务独立提交前须通过其列出的测试；提交、推送、上线需届时另行授权。

## 0. 开工顺序和文件地图

实施者先读本计划、实施契约、M0 迁移设计和 `SKILL.md`。按 Task 1–8 顺序执行；Task 9/10 仅在 M1–M3 稳定后执行。不要把 M4 并发实验混入 M1 的功能提交。

| 任务 | 创建/修改文件 | 独立产出 |
| --- | --- | --- |
| 1 | `yuntu_workflow_common.py`、run-state、测试 | 哈希、根路径、锁、阶段计时基础能力 |
| 2 | `yuntu_postprocess.py`、batch、analysis、测试 | 显式后处理和纯读分析准备 |
| 3 | `yuntu_snapshot.py`、run-state、测试 | 可验证快照、目录、交接卡 |
| 4 | `yuntu_analysis_workflow.py`、测试 | 请求、catalog、受限 SelectionSpec |
| 5 | 同上、provenance、测试 | 事实切片、引用校验、attempt 持久化 |
| 6 | analysis/provenance、测试 | staged unit 与局部恢复，兼容旧单调用 |
| 7 | connector/report、测试、SKILL | collect-only、按需回答、全报告交付恢复 |
| 8 | CLI/状态/文档、测试 | 用户可执行命令和交接体验 |
| 9 | highlights/telemetry、测试 | 内容身份缓存和可测量后处理 |
| 10 | 独立实验代码/记录 | 波次屏障的受控性能实验 |

### Task 1：基础不变性、锁与阶段计时

**Files:**
- Create: `scripts/yuntu_workflow_common.py`
- Modify: `scripts/yuntu_run_state.py`
- Create: `tests/test_yuntu_workflow_common.py`
- Modify: `tests/test_yuntu_run_state.py`

**Interfaces:**
- Produces `stable_id(prefix: str, payload: dict) -> str`、`validate_rooted_file(root: Path, path: Path) -> Path`、`WorkflowLock`、`record_timing(...) -> dict`。
- Consumed by Tasks 2–10; all paths passed as `Path`, all errors subclass `YuntuWorkflowError`.

- [ ] **1.1 写稳定 ID 和路径越界的失败测试。**

```python
def test_stable_id_ignores_mapping_order_and_path_must_stay_under_root(self):
    common = load_module()
    self.assertEqual(
        common.stable_id("snapshot", {"b": 2, "a": 1}),
        common.stable_id("snapshot", {"a": 1, "b": 2}),
    )
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory) / "run"; root.mkdir()
        outside = Path(directory) / "outside.json"; outside.write_text("{}")
        with self.assertRaisesRegex(common.YuntuWorkflowError, "outside root"):
            common.validate_rooted_file(root, outside)
```

- [ ] **1.2 运行失败测试。**

Run: `python -m unittest tests.test_yuntu_workflow_common -v`
Expected: import failure until Task 1 implementation exists.

- [ ] **1.3 实现基础模块。** `stable_id` 使用契约 §3.1 的 canonical JSON。`validate_rooted_file` resolve 后验证 `is_file`、`st_size > 0`、`relative_to(root.resolve())`；返回绝对 path。`WorkflowLock.acquire()` 原子创建 `.workflow.lock`，已有锁抛 `lock_held`；`release()` 仅删除自己 ownerId 的锁。`record_timing` 只追加 JSONL 记录，不吞异常。

- [ ] **1.4 增加锁竞争与 timing schema 测试。** 两个 lock 对同一 root，第二个应 `lock_held`；释放后可获取。断言记录含 stage/outcome/wallTimeSec 且 stage 不在固定集合时被拒绝。

- [ ] **1.5 运行任务测试。**

Run: `python -m unittest tests.test_yuntu_workflow_common tests.test_yuntu_run_state -v`
Expected: PASS；没有创建 workspace 外文件。

### Task 2：把后处理移出分析准备

**Files:**
- Create: `scripts/yuntu_postprocess.py`
- Modify: `scripts/yuntu_batch.py`
- Modify: `scripts/yuntu_analysis.py`
- Modify: `tests/test_yuntu_batch.py`, `tests/test_yuntu_analysis.py`
- Create: `tests/test_yuntu_postprocess.py`

**Interfaces:**
- Consumes Task 1 的 lock/timing 和既有 `yuntu_highlights` 选点/下载/抽帧函数。
- Produces `PostprocessRequest`、`PostprocessResult`、`postprocess_run`、`retry_postprocess`（契约 §4.1）。

- [ ] **2.1 为纯读 `prepare_analysis` 写失败测试。** 在可用 fixture 中 monkeypatch `yuntu_analysis.generate_standard_highlights_for_detail`、`download_video`、`extract_frames_batch` 为抛错函数；调用 `prepare_analysis` 后断言成功、源 `highlights-manifest.json` 的 SHA-256 不变。
- [ ] **2.2 为 data-only 写失败测试。** 传入两个 selected detail 和记录调用的 downloader/extractor，断言两个调用列表为空，结果的 video/frames 状态均为 `not_requested`。
- [ ] **2.3 为按素材恢复写失败测试。** 一个素材已有相同 source/spec 成功记录，另一个 `frames.status=failed`；调用 retry，断言只对失败素材调用 extractor，且 RPA invoker 调用数为 0。
- [ ] **2.4 实现协调器。** 从 `prepare_analysis` 删除高光生成和 manifest 写入段；让 `fetch_batch_analysis` 在所有 selected detail 规范化成功后以 `standard_report` 调用 `postprocess_run`。保持 M0 的详情/高光波次屏障；不把 postprocess 放到 worker 直接写共享 manifest。将 per-material 状态按契约字段写入 manifest，最后一次性 checkpoint。
- [ ] **2.5 保持批量抽帧和回退行为。** 调用既有 `extract_frames_batch`，批次失败才调用既有逐帧提取；捕获处记录 `batch_extract_failed`、`frame_extract_failed` 等精确错误码。不要重新实现 FFmpeg。
- [ ] **2.6 运行任务测试。**

Run: `python -m unittest tests.test_yuntu_postprocess tests.test_yuntu_analysis tests.test_yuntu_batch -v`
Expected: PASS；prepare-analysis 无网络、无 FFmpeg、无源写入。

### Task 3：封存快照、目录和交接卡

**Files:**
- Create: `scripts/yuntu_snapshot.py`
- Modify: `scripts/yuntu_run_state.py`
- Create: `tests/test_yuntu_snapshot.py`

**Interfaces:**
- Consumes verified M0 manifest、normalized artifacts、Task 2 postprocess statuses。
- Produces `seal_snapshot`、`load_verified_snapshot`、`build_fact_catalog`、`build_handoff` 及契约 §4.2 的四个文件。

- [ ] **3.1 写混合目录拒绝测试。** 构造 summary 表示 12 条、manifest 只选 5 条且 detail artifact 目录另有 17 条；`seal_snapshot(required_capabilities={"detail"})` 只允许 manifest 的 5 条。令其中一条 hash 被篡改，断言抛 `source_hash_mismatch` 且不发布 snapshot 目录。
- [ ] **3.2 写能力门槛测试。** data-only run 使用 `{ranking, detail}` 成功封存且 visual 是 `not_requested`；请求 `{standard_report}` 时抛 `capability_missing` 并列出 materialId。
- [ ] **3.3 实现 artifact 收集和 ID。** 只从 `selectedMaterials` 的 `detailRecordPath`、已验证 ranking run 与 Task 2 records 收集 artifact；验证 root containment、size、hash、周期/上下文。以排序后的 artifacts 和 collection contract hash 计算 snapshotId。先在 `snapshots/.<id>.staging` 写入，再校验四个文件后发布。
- [ ] **3.4 实现 catalog/handoff。** catalog 的字段、availability、allowed operations 固定为契约 §4.3；handoff 不含 CSV/URL/凭证，`resumePrompt` 只引用 snapshotId 与可用能力。用 Markdown 交接卡明确脚本、视觉和周期缺口。
- [ ] **3.5 写加载校验测试。** 修改已封存 artifact 后 `load_verified_snapshot` 必须在返回 manifest 前抛 `source_hash_mismatch`；将 manifest path 改为 `../x` 必须抛 `source_outside_root`。
- [ ] **3.6 运行任务测试。**

Run: `python -m unittest tests.test_yuntu_snapshot tests.test_yuntu_run_state -v`
Expected: PASS；每个 ready snapshot 的四个文件存在且 JSON 可解析。

### Task 4：分析请求、catalog 和 SelectionSpec

**Files:**
- Create: `scripts/yuntu_analysis_workflow.py`
- Create: `tests/test_yuntu_analysis_workflow.py`

**Interfaces:**
- Consumes Task 3 `load_verified_snapshot` 和 fact catalog。
- Produces `create_analysis_request`、`validate_selection_spec`；输入/输出字段严格遵守契约 §5.1。

- [ ] **4.1 写请求 identity 测试。** 相同 snapshot 上两个不同问题产生不同 UUID `analysisId`、不同 intentHash；相同语义字段但 dict key 顺序不同的 userRules 得同一 intentHash。
- [ ] **4.2 写非法选择测试。** 对未知 dataset、`../` path、`operator="sql"`、投影不存在字段、文本字段 gte、未知顶层 key 分别断言 `selection_invalid`。
- [ ] **4.3 实现 request。** 验证 snapshot ready 和 requestedOutput；从用户显式问题/规则识别所需能力，但不写回 collection contract。能力不足时创建 request 并标 `awaiting_selection`，写 `gaps`，不触发采集。
- [ ] **4.4 实现封闭 spec validator。** 使用显式 dict schema 检查，不接受 callable/string 表达式。字段只从 catalog fields 解析，filter/sort/aggregate 仅使用契约枚举。
- [ ] **4.5 运行任务测试。**

Run: `python -m unittest tests.test_yuntu_analysis_workflow -v`
Expected: PASS；无 `requests`、下载器、FFmpeg mock 调用。

### Task 5：本地选择、引用和分析 attempt

**Files:**
- Modify: `scripts/yuntu_analysis_workflow.py`
- Modify: `scripts/yuntu_analysis_provenance.py`
- Modify: `tests/test_yuntu_analysis_workflow.py`
- Create: `tests/test_yuntu_analysis_references.py`

**Interfaces:**
- Produces `execute_selection`、`validate_analysis_references`、`analysis-input.json`、attempt receipt。
- Consumed by Task 6 staged units and Task 7 delivery router。

- [ ] **5.1 写脚本最小投影测试。** 对只问指定素材话术的问题，执行 selection 后断言 `facts` 不含 `industryTop1000Facts`、`audienceDashboard`、`visualAssets`，allowedFactRefs 均指向该素材 script 路径。
- [ ] **5.2 写全量聚合测试。** 对 1,000 条榜单 fixture 执行 `count`/`median`，断言 aggregate 的 sourceRefs 覆盖全部参与记录；不能以 selected detail 数替代全量范围。
- [ ] **5.3 写引用拒绝测试。** 输出引用不存在 pointer、快照外 path、切片局部数组索引但非原源 pointer 时，`validate_analysis_references` 返回 `reference_invalid`；有效 aggregateRef 通过。
- [ ] **5.4 实现 selection executor。** 依序 load verified artifact → filter → project → sort → aggregate；保存 sourceRecordCount/selectedCount/selectionHash/inputSnapshotHash/截断原因。零匹配创建可读 `selection_empty` gap，不抛无上下文异常。只允许在 facts 中存 projection 与聚合。
- [ ] **5.5 实现 attempt 文件。** 每次尝试先写 immutable `attempts/<uuid>/request.json`；模型输出通过 schema+引用后原子写 output/receipt，失败写 validation.json。不得覆盖既有成功 output。
- [ ] **5.6 运行任务测试。**

Run: `python -m unittest tests.test_yuntu_analysis_workflow tests.test_yuntu_analysis_references tests.test_yuntu_analysis_provenance -v`
Expected: PASS；同快照文本再分析的采集、下载、FFmpeg 调用均为 0。

### Task 6：staged model manifest 与局部恢复

**Files:**
- Modify: `scripts/yuntu_analysis.py`
- Modify: `scripts/yuntu_analysis_provenance.py`
- Modify: `tests/test_yuntu_analysis.py`, `tests/test_yuntu_report.py`
- Create: `tests/test_yuntu_staged_analysis.py`

**Interfaces:**
- Consumes Task 5 analysis input/attempt contract。
- Produces staged manifest and provenance validation specified in contract §6.

- [ ] **6.1 写旧模式兼容测试。** 已有 `executionMode=single_model_call` fixture 继续通过 `_verify_analysis_unit_manifest` 和 `load_verified_provenance`。
- [ ] **6.2 写新模式 hash/依赖测试。** 一个 `material_script` unit 成功、另一个失败；retry 后只失败 unit 获取新 attemptId，章节 synthesis 在任一依赖失败时为 pending/partial，不被标 success。
- [ ] **6.3 写视觉缓存身份测试。** 相同 JPEG hash 但不同 promptHash 或 schemaHash 为 cache miss；完全相同 key 为 hit，并且返回记录 type 为 `model_observation`、含 frameRef/source ref。
- [ ] **6.4 实现 mode 分支。** 旧函数保持单次模式行为；为 staged mode 建立单位及依赖哈希、状态和 validation error。不要把多个调用继续记录为 single_model_call。
- [ ] **6.5 实现局部失效。** 仅当输入/schema/依赖 hash 变化时删除该 unit 及下游可再生结果；成功的无关素材 unit 保留。报告组装对缺失 unit 写 gaps，禁止伪造完成章节。
- [ ] **6.6 运行任务测试。**

Run: `python -m unittest tests.test_yuntu_staged_analysis tests.test_yuntu_analysis tests.test_yuntu_report -v`
Expected: PASS；五章既有 schema 与删除的指数解释不回归。

### Task 7：按需回答、完整报告与渲染恢复

**Files:**
- Modify: `scripts/rpa_connector.py`
- Modify: `scripts/yuntu_report.py`
- Modify: `tests/test_rpa_connector.py`, `tests/test_yuntu_report.py`

**Interfaces:**
- Produces `analyze`/`render-report` command边界、report receipt，消费 Task 5/6 verified analysis。

- [ ] **7.1 写 answer 分流测试。** `requestedOutput="answer"` 返回 answer artifact 和 receipt，mock `render_report` 断言未调用；RPA/后处理 mock 亦未调用。
- [ ] **7.2 写全报告 staging 测试。** 在 staging 中让 Excel 导出抛错，断言 final report 目录不存在且 analysis attempt 不变；修复导出后重试仅运行 render/excel/zip，RPA/model mock 调用数为 0。
- [ ] **7.3 实现显式 CLI。** 添加 `postprocess`、`seal-snapshot`、`create-analysis`、`prepare-selection`、`analyze`、`render-analysis` 子命令。命令参数必须是明确路径/ID，所有路径经 root 验证；保留已有 `prepare-analysis` 和 `render-report` 兼容入口。
- [ ] **7.4 实现交付 staging 与 receipt。** 调整报告输出为 `<reportId>/.staging` 完整校验后发布；receipt 记录 analysis/fact/render hash 及各产物 hash。现有 Excel 与 ZIP 校验保持。
- [ ] **7.5 运行任务测试。**

Run: `python -m unittest tests.test_rpa_connector tests.test_yuntu_report -v`
Expected: PASS；失败恢复不触发模型或 RPA。

### Task 8：技能说明、状态输出和端到端离线回放

**Files:**
- Modify: `SKILL.md`
- Modify: `scripts/rpa_connector.py`
- Create: `tests/test_yuntu_workflow_e2e.py`
- Create: `docs/handoffs/2026-09-07-yuntu-workflow-implementation-execution.md`（执行时）

**Interfaces:** 用户可见命令只引用 Task 2–7 已实现的接口；`status` 是纯本地读取。

- [ ] **8.1 写 collect-only 回放测试。** 从合成已完成 run 创建 data-only 快照，断言得到 handoff；流程到此停止且没有 analysis/report 目录。
- [ ] **8.2 写完整报告连续回放测试。** 从标准后处理 fixture 依次 postprocess → seal → request → selection → 注入合格模型输出 → attest → render；断言 report 有 HTML、Markdown、presentation JSON、Excel、ZIP，且所有 upstream 调用各一次。
- [ ] **8.3 更新 SKILL.md。** 描述两种用户范围、交接卡、跨对话 snapshotId 选择和缺口反馈。原 `fetch`、历史 `prepare-analysis`、`attest-analysis`、`render-report` 指令保留为兼容说明；明确分析阶段不做 I/O 副作用。
- [ ] **8.4 增强 status。** 输出 runId、可用 snapshot 列表（ID/状态/范围/创建时间）、active lock、capabilities 和 gaps；不得扫描/修改历史 CSV 来猜测最新批次。
- [ ] **8.5 运行离线回放和契约检查。**

Run: `python -m unittest tests.test_yuntu_workflow_e2e tests.test_skill_contract -v`
Expected: PASS；保留数据/文本报告交接边界。

### Task 9：后处理缓存身份和遥测

**Files:**
- Modify: `scripts/yuntu_highlights.py`, `scripts/yuntu_postprocess.py`
- Modify: `tests/test_yuntu_highlights.py`, `tests/test_yuntu_postprocess.py`

**Interfaces:** 消费 Task 1 timing；实现契约 §7 的 video/frame cache key 和 `workflow-timings.json`。

- [ ] **9.1 写缓存命中/失效测试。** 相同 materialId 但 sourceHash 或 processingSpecHash 改变时必须重新提取；相同完整键且 JPEG 有效时不调用 extractor。
- [ ] **9.2 实现逐帧缓存。** 不因一帧缺失而删除完整集合；只将无效帧加入 request。保留既有批量抽帧与逐帧 fallback。
- [ ] **9.3 写 timing 完整性测试。** download/extract/validate 各产生独立 timing；批量失败且回退时记录 fallback 次数和额外进程数。
- [ ] **9.4 运行任务测试。**

Run: `python -m unittest tests.test_yuntu_highlights tests.test_yuntu_postprocess tests.test_yuntu_workflow_common -v`
Expected: PASS；缓存不误命中且每阶段可测。

### Task 10：波次屏障的隔离性能实验

**Files:**
- Create: `scripts/experiments/yuntu_bounded_pipeline.py`
- Create: `tests/test_yuntu_bounded_pipeline.py`
- Create: `docs/handoffs/2026-09-07-yuntu-pipeline-experiment.md`

**Interfaces:** 实验只读取冻结 fixture 或独立新 run；不得替换默认 `yuntu_batch` 调度。

- [ ] **10.1 写背压/取消测试。** 有界队列满时详情提交暂停；取消后不发布 snapshot、manifest 不含半完成 selected entry。
- [ ] **10.2 实现实验配置。** 显式参数 `--max-rpa-inflight`、`--max-postprocess-queue`、`--max-downloads`、`--max-decodes`；默认值不得被正式命令使用。
- [ ] **10.3 执行可比基线。** 同一冻结样本分别运行屏障模式和实验模式，记录 output/frame manifest hash、wall time、最大在途、内存/磁盘、retry/fallback 数。
- [ ] **10.4 写实验结论。** 只有结果 hash 一致、资源不超过配置、失败/取消无半成品时，才能提交是否把实现推广为正式设计的建议；否则删除实验运行目录，保留记录。
- [ ] **10.5 运行实验单测。**

Run: `python -m unittest tests.test_yuntu_bounded_pipeline -v`
Expected: PASS；默认调度测试仍保持原屏障。

## 执行前后检查

执行前记录 `git status --short`、`git rev-parse HEAD`、fixture/历史基线 hash。每一 Task 完成后运行其定向测试；Task 8 完成后再运行：

```bash
python -m unittest discover -s tests -v
python scripts/rpa_connector.py self-test
git diff --check
```

预期为全部通过、无空白错误和无历史数据改写。若已有与本任务无关的工作区变更，只报告并隔离，不清理或合并。真实新连接器调用、发布、提交和推送不由本计划自动执行，执行记录必须填写实际命令、测试、run/snapshot/analysis/report ID、产物 hash 和剩余 gaps。

## 给后续执行模型的起始提示词

```text
请在 yuntu-industry-content-rankings-analysis 仓库执行 docs/superpowers/plans/2026-09-07-yuntu-performance-workflow-implementation.md 的 Task <编号>。先读对应实施契约和现有代码/测试，再严格按该 Task 的失败测试→最小实现→定向测试步骤工作。不要改动其他 Task，不要切换或调用旧详情连接器，不要重写历史数据或客户商业分析逻辑。完成后报告改动文件、测试命令与结果、未满足的前置条件；不要提交或推送。
```

## 自检结果

本计划覆盖实施契约的 M1（Task 1–3）、M2（Task 4–5）、M3（Task 6）、M5（Task 7–8）和 M4（Task 9–10）。接口名称、状态、路径、引用格式和验收项均在任务中给出；M4 的默认调度变更没有被提前授权为实现。计划只描述未来代码变更，当前未执行任何代码、RPA、FFmpeg、模型生成、提交或推送。
