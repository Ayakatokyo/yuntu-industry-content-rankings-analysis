# 第一部分素材榜单事实包、提示词与报告渲染 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 收敛第一部分榜单事实包，拆分表现/爆款 AI 分析，并统一“所有指定品牌”报告展示与确定性事实面板交互。

**Architecture:** 保留现有榜单事实字段、爆款事实卡片和章节一投影结构；在模型输入投影阶段移除 RPA 详情相关字段，在事实层明确三批榜单素材列表及确定性比较事实。提示词继续使用 `dataSummary` 与 `hotMaterialInsight`，渲染层分别输出两个段落，并让环比/行业面板复用现有展开/收起组件。

**Tech Stack:** Python、JSON Schema、HTML/CSS/JavaScript、unittest。

**Spec:** `docs/superpowers/specs/2026-09-01-chapter01-ranking-facts-prompt-render-design.md`

## Global Constraints

- 第一部分事实包不得包含 RPA 详情、高光帧、秒级数据、视觉分类或深度分析结果。
- 三批素材列表必须包含曝光数据、点击率、转化率和 3 秒完播。
- 行业基准列表同周期但不筛选品牌；品牌行业对比始终引用该未筛选范围。
- 现有爆款素材事实卡片保留，不新增卡片设计。
- 环比/全行业事实面板复用现有爆款素材汇总面板的展开/收起交互。

### Task 1: 收敛第一部分事实包

**Files:**
- Modify: `scripts/yuntu_analysis.py`
- Modify: `scripts/yuntu_top_materials.py`
- Test: `tests/test_yuntu_analysis.py`

**Interfaces:**
- Produces: `ranking-brand-input.json` with `current`, `previousPeriod`, `industryBenchmark`, `comparisonFacts`, `hotMaterialFacts`, and list rows limited to ranking fields.

- [ ] **Step 1: Write failing tests** asserting ranking input excludes `visualAssets`, `highlightFrames`, `secondLevelBreakdown`, and RPA detail keys while each of `current`, `previousPeriod`, and `industryBenchmark` rows contains exposure, CTR, CVR, and 3-second completion metrics.
- [ ] **Step 2: Run `python -m unittest tests.test_yuntu_analysis -v` and verify the new boundary assertions fail against the current projection.
- [ ] **Step 3: Update the ranking-unit projection so only the three ranking lists, deterministic comparison facts, and existing hot-material facts are emitted; keep the full multi-chapter fact pack available to the other analysis units.
- [ ] **Step 4: Ensure industry comparison aggregation consumes the unfiltered same-period industry list, while brand scopes filter only current and previous lists by runtime title matching.
- [ ] **Step 5: Run the focused analysis tests and verify all boundary and metric assertions pass.
- [ ] **Step 6: Commit with `git add scripts/yuntu_analysis.py scripts/yuntu_top_materials.py tests/test_yuntu_analysis.py && git commit -m "refactor: narrow chapter01 ranking fact package"`.

### Task 2: Split first-chapter prompt output into two analyses

**Files:**
- Modify: `prompts/yuntu-analysis-prompt.md`
- Modify: `scripts/yuntu_analysis.py`
- Modify: `scripts/yuntu_report.py`
- Test: `tests/test_yuntu_analysis.py`

**Interfaces:**
- Consumes: Task 1 ranking fact package.
- Produces: each `brandConclusions` item and `allBrandsConclusion` with `dataSummary` for period/industry comparison and `hotMaterialInsight` for aggregate hot-material analysis.

- [ ] **Step 1: Add failing prompt/schema tests requiring `dataSummary` and `hotMaterialInsight` to be semantically separate and rejecting RPA/highlight references in the ranking unit.
- [ ] **Step 2: Run the focused prompt/schema tests and confirm they fail before the prompt contract changes.
- [ ] **Step 3: Rewrite only the first-chapter prompt clauses: `dataSummary` covers current vs previous vs industry; `hotMaterialInsight` covers only hot-material patterns; both remain scoped to the same all-brand or brand range.
- [ ] **Step 4: Update validation to accept the retained fields, enforce the two scopes, preserve existing evidence/material ID rules, and prohibit additional cross-range fields.
- [ ] **Step 5: Run `python -m unittest tests.test_yuntu_analysis tests.test_yuntu_report -v` and verify the prompt and contract tests pass.
- [ ] **Step 6: Commit with `git add prompts/yuntu-analysis-prompt.md scripts/yuntu_analysis.py scripts/yuntu_report.py tests/test_yuntu_analysis.py && git commit -m "feat: split chapter01 ranking insights"`.

### Task 3: Render renamed Tab and collapsible deterministic comparison panel

**Files:**
- Modify: `scripts/yuntu_presentation.py`
- Modify: `scripts/yuntu_report_sections.py`
- Modify: `scripts/templates/final-report-template.html`
- Modify: `assets/report/unified-report.css`
- Test: `tests/test_yuntu_presentation.py`
- Test: `tests/test_yuntu_report.py`

**Interfaces:**
- Consumes: Task 2 analysis output and Task 1 deterministic comparison facts.
- Produces: chapter01 Presentation/report with `label="所有指定品牌"`, separate AI blocks, and a comparison panel using the existing collapse-toggle contract.

- [ ] **Step 1: Add failing renderer tests for the “所有指定品牌” label, separate `dataSummary`/`hotMaterialInsight` blocks, and `aria-expanded`/`aria-controls` comparison toggle placement.
- [ ] **Step 2: Run the focused presentation/report tests and verify the new assertions fail.
- [ ] **Step 3: Change only the displayed aggregate label; retain internal all-brand IDs and existing brand matching behavior.
- [ ] **Step 4: Project the two AI fields separately and wrap only the deterministic comparison facts in the same toggle pattern used by the existing hot-material summary panel.
- [ ] **Step 5: Leave the existing hot-material fact cards, fields, sorting, and interactions unchanged; add regression assertions for card identity and count.
- [ ] **Step 6: Run `python -m unittest tests.test_yuntu_presentation tests.test_yuntu_report -v` and verify all focused tests pass.
- [ ] **Step 7: Commit with `git add scripts/yuntu_presentation.py scripts/yuntu_report_sections.py scripts/templates/final-report-template.html assets/report/unified-report.css tests/test_yuntu_presentation.py tests/test_yuntu_report.py && git commit -m "feat: render chapter01 comparison collapse panel"`.

### Task 4: Real-data regeneration and full regression

**Files:**
- Create: `RPA数据汇总/yuntu-rankings-analysis-20260810-20260820-top6/final-report-latest-taxonomy-20260901-chapter01-ranking-facts/`
- Create: `RPA数据汇总/yuntu-rankings-analysis-20260810-20260820-top6/final-report-latest-taxonomy-20260901-chapter01-ranking-facts.zip`

- [ ] **Step 1: Render a new report directory from the existing real analysis/fact inputs without overwriting prior report directories or RPA source data.
- [ ] **Step 2: Assert the ranking input contains only the three list scopes and required metrics, and contains no RPA/highlight fields.
- [ ] **Step 3: Assert HTML, Markdown, and Presentation use “所有指定品牌”, contain two distinct AI sections per scope, and expose the comparison collapse control.
- [ ] **Step 4: Assert existing hot-material card count, IDs, and exposure fields match the deterministic hot-material facts.
- [ ] **Step 5: Run `python -m compileall -q scripts tests`, `python -m unittest discover -s tests -p 'test_*.py'`, and `git diff --check`.
- [ ] **Step 6: Inspect the generated ZIP contents and record artifact paths and test totals in the execution report.
- [ ] **Step 7: Commit only source/test/documentation changes; keep generated real-data artifacts uncommitted unless the repository’s existing artifact policy requires tracking them.
