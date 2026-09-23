# 第一部分周期对比与爆款素材 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为第一章接入三次榜单采集、环比/大盘比较和曝光区间爆款素材分析。

**Architecture:** 在现有批次中增加带日期与口径标识的 `rankingRuns`，当前查询周期继续驱动详情采集；分析层分别生成比较事实和确定性 `hotMaterialFacts`，模型在同一品牌结论中整体解释已计算事实，Presentation 再投影为第一章稳定展示结构。

**Tech Stack:** Python 3、现有 RPA connector、JSON Schema、unittest、现有 HTML/Markdown 报告渲染。

**Spec:** `docs/superpowers/specs/2026-08-31-yuntu-chapter01-period-benchmark-hot-material-design.md`

## Global Constraints

- 爆款规则是项目级配置，不做账号配置；默认从 `config/hot-material-rules.json` 读取曝光量区间最小值 `>= 200000`，实际指标、比较关系和阈值以配置为准。
- 三次列表采集分别为 query、previous_period、industry；详情只采集 query 周期。
- AI 不计算事实、不补造曝光、不写跨章节证据或因果结论。
- 历史单周期报告保持只读兼容。

### Task 1: 三口径列表采集与批次 manifest

**Files:**
- Modify: `scripts/rpa_connector.py`
- Modify: `scripts/yuntu_batch.py`
- Modify: `scripts/yuntu_run_state.py`
- Test: `tests/test_rpa_connector.py`, `tests/test_yuntu_batch.py`, `tests/test_yuntu_run_state.py`

**Interfaces:**
- Produce `rankingRuns.query`, `rankingRuns.previous_period`, `rankingRuns.industry` with request parameters, resolved dates, source paths and status.
- Preserve current `normalized/list-records.json` semantics for query data and add explicit paths for comparison lists.

- [x] 写失败测试：验证自定义周期会生成上一等长周期、全行业请求强制 `ALL_INDUSTRY`，并记录三次请求。
- [x] 运行聚焦测试确认当前实现失败。
- [x] 实现三次列表编排、日期平移、状态持久化和中断恢复；详情候选只来自 query。
- [x] 运行 connector/batch/run-state 聚焦测试并确认通过。

### Task 2: 曝光区间标准化与比较事实

**Files:**
- Modify: `scripts/yuntu_normalizer.py`
- Modify: `scripts/yuntu_analysis.py`
- Test: `tests/test_yuntu_normalizer.py`, `tests/test_yuntu_analysis.py`

**Interfaces:**
- Add normalized exposure interval `{min, max, raw}` with legacy numeric compatibility.
- Add comparison facts containing current/previous/industry aggregates, deltas, rates and availability reasons.

- [x] 写边界测试：`199999` 不入选、`200000` 入选、区间下限决定资格、不可解析值不计数。
- [x] 运行测试确认失败。
- [x] 实现区间解析、三口径聚合和零值/缺失保护。
- [x] 运行分析与标准化测试确认通过。

### Task 3: 爆款事实与模型输出契约

**Files:**
- Modify: `scripts/yuntu_analysis.py`
- Modify: `prompts/yuntu-analysis-prompt.md`
- Modify: `scripts/yuntu_report.py`
- Modify: `scripts/yuntu_analysis_provenance.py`
- Test: `tests/test_yuntu_analysis.py`, `tests/test_yuntu_report.py`, `tests/test_skill_contract.py`

**Interfaces:**
- Add `hotMaterialFacts` to `ranking-brand-input.json`.
- Keep one `dataSummary` per first-chapter conclusion, covering current data, period comparison, industry benchmark, and hot-material facts.

- [x] 写失败测试：缺少爆款证据、错误 scope、虚构 material ID、错误数量和缺少独立 AI 字段都必须拒绝。
- [x] 运行测试确认失败。
- [x] 实现确定性命中清单、Schema 动态引用、Prompt 约束和 provenance 门禁。
- [x] 运行分析/报告/技能契约测试确认通过。

### Task 4: Presentation 与 HTML/Markdown 爆款面板

**Files:**
- Modify: `scripts/yuntu_presentation.py`
- Modify: `scripts/yuntu_report_sections.py`
- Modify: `scripts/yuntu_report.py`
- Modify: `scripts/templates/final-report-template.html`
- Modify: `assets/report/unified-report.css`
- Test: `tests/test_yuntu_presentation.py`, `tests/test_yuntu_report.py`

**Interfaces:**
- Produce `chapter01.comparison` and `chapter01.hotMaterialPanel`.
- Render per-scope rule label, count, names, exposure interval, auxiliary metrics and unavailable state.

- [x] 写失败测试：面板显示 20 万规则、命中数量、素材名称与不可用状态；旧报告仍可渲染。
- [x] 运行测试确认失败。
- [x] 实现稳定投影和报告布局，不把原始三份列表复制到 Presentation。
- [x] 运行展示聚焦测试确认通过。

### Task 5: 真实回归与收口

**Files:**
- Modify: `SKILL.md`
- Test: full `tests/` suite and fixed real batch under a new temporary output directory

- [x] 更新技能说明，明确三次榜单采集、上一周期定义和曝光区间爆款规则。
- [x] 用固定真实批次执行三次列表采集、`prepare-analysis`、当前模型生成、`attest-analysis` 和 `render-report`；三次列表均成功返回 1000 条，4 条秒级详情全部成功，报告已生成。
- [x] 核对真实批次的样本、上一周期比较事实与曝光区间命中清单；仅解析顶层 `show_cnt` 的区间展示值，不将嵌套精确 `show_cnt` 替代为曝光区间。
- [x] 运行 `python -m unittest discover -s tests -p 'test_*.py'`、`python -m compileall -q scripts tests` 和 `git diff --check`。
