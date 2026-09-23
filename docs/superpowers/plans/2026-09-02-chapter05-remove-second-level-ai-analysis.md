# 第五部分删除五类指数 AI 二次分析 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 移除第五部分五类指数 AI 二次分析文案，保留确定性秒级曲线和全部原始数据交互。

**Architecture:** 在分析输入/输出边界移除 `second_level_observations`，让第五部分只消费 `secondLevelBreakdown.metrics` 等确定性事实。Presentation、HTML 和 Markdown 删除 AI 洞察投影与渲染，但保留指标曲线、峰值/流失点、指标切换和时长滑杆；历史报告读取采用忽略旧字段的兼容策略。

**Tech Stack:** Python、JSON Schema、HTML/CSS/JavaScript、unittest。

**Spec:** `docs/superpowers/specs/2026-09-02-chapter05-remove-second-level-ai-analysis-design.md`

## Global Constraints

- 删除点赞、流失、点击、互动、评论五类指数的 AI 二次分析文案。
- 保留 `secondLevelBreakdown.metrics`、秒级 points、high_points、loss_points 和全部交互。
- 新输出不得产生 `materialDeepDives[].second_level_observations[]` 或 `chapters.chapter05.panels[].secondLevelObservations[]`。
- 历史报告与历史 JSON 不覆盖；新渲染忽略历史 AI 字段。

### Task 1: 收敛第五部分输入与输出契约

**Files:**
- Modify: `prompts/yuntu-analysis-prompt.md`
- Modify: `scripts/yuntu_analysis.py`
- Modify: `scripts/yuntu_report.py`
- Test: `tests/test_yuntu_analysis.py`
- Test: `tests/test_yuntu_report.py`

**Interfaces:**
- Consumes: `material-deep-dive-input.json` 中的确定性 `secondLevelBreakdown`。
- Produces: 不含 `second_level_observations` 的 `materialDeepDives`，保留确定性指标结构。

- [x] **Step 1: 添加失败测试，断言新第五部分模型输入/输出禁止五类指数 AI 洞察字段，同时保留 `secondLevelBreakdown.metrics`。**
- [x] **Step 2: 运行第五部分分析与报告定向测试，确认新边界断言失败。**
- [x] **Step 3: 修改提示词，删除五类指数自然语言分析要求及 `evidence_seconds` 画面归因要求，明确只保留确定性指标事实。**
- [x] **Step 4: 修改输入投影、输出 Schema 和校验逻辑，禁止新输出生成死字段；历史输入存在旧字段时只忽略不报错。**
- [x] **Step 5: 运行定向分析、Presentation 与报告测试，128/128 通过。**
- [x] **Step 6: 已完成实现变更提交（合并提交见最终回执）。**

### Task 2: 删除 Presentation 与报告中的 AI 洞察渲染

**Files:**
- Modify: `scripts/yuntu_presentation.py`
- Modify: `scripts/yuntu_report_sections.py`
- Modify: `scripts/yuntu_report.py`
- Modify: `scripts/templates/final-report-template.html`
- Modify: `assets/report/unified-report.css`
- Test: `tests/test_yuntu_presentation.py`
- Test: `tests/test_yuntu_report.py`

**Interfaces:**
- Consumes: Task 1 的确定性第五部分事实。
- Produces: `chapters.chapter05.panels[]` 仅含曲线事实与交互所需数据，不含 `secondLevelObservations`。

- [x] **Step 1: 添加失败测试，断言 Presentation 不投影 `secondLevelObservations`，HTML/Markdown 不渲染五类指数 AI 文案。**
- [x] **Step 2: 添加回归测试，断言五类指标曲线、峰值/流失点、指标切换和时长滑杆仍存在。**
- [x] **Step 3: 删除 Presentation 的 AI 洞察投影和报告渲染入口，保留确定性指标投影。**
- [x] **Step 4: 核对模板、样式和测试中的死字段/死文案；报告实际使用的内嵌样式无需改动，曲线交互结构保持不变。**
- [x] **Step 5: 对历史分析对象保留忽略式兼容读取。**
- [x] **Step 6: 运行定向 Presentation 与报告测试，128/128 定向总测试通过。**
- [x] **Step 7: 实现变更已纳入当前工作区提交。**

### Task 3: 文档、Schema 和历史兼容回归

**Files:**
- Modify: `docs/mermaid/chapter05-material-deep-dive-data-flow.md`
- Modify: 相关 `schemas/` 或 `analysis-units/` Schema 文件（以仓库实际路径为准）
- Test: `tests/test_yuntu_analysis.py`
- Test: `tests/test_yuntu_presentation.py`
- Test: `tests/test_yuntu_report.py`

- [x] **Step 1: 更新第五部分 Mermaid 链路图，标注确定性指标保留、AI 指数分析删除和历史字段兼容边界。**
- [x] **Step 2: 增加旧分析 JSON 夹具，验证新渲染忽略 `second_level_observations` 但正常显示曲线交互。**
- [x] **Step 3: 运行第五部分全部定向测试并检查无死字段引用。**
- [x] **Step 4: 文档、Schema 约束和兼容测试已纳入当前工作区提交。**

### Task 4: 真实报告重渲染与全量验收

**Files:**
- Create: `RPA数据汇总/yuntu-rankings-analysis-20260810-20260820-top6/final-report-latest-taxonomy-20260902-chapter05-no-ai-index-observations/`
- Create: 同名 `.zip` 归档

- [x] **Step 1: 使用现有真实事实包和分析输入生成新的独立报告目录，不覆盖旧报告或 RPA 数据。**
- [x] **Step 2: 校验新报告 JSON/Presentation 不含五类指数 AI 字段，仍含秒级 metrics、high_points、loss_points 和交互配置。**
- [x] **Step 3: 校验 HTML/Markdown 不出现五类指数 AI 文案或 evidence_seconds 画面归因，但曲线和指标切换仍存在。**
- [x] **Step 4: 已运行 `compileall`、全量 unittest 和 `git diff --check`。全量测试 284/284 通过。**
- [x] **Step 5: 已检查 ZIP 条目，旧报告未覆盖；Pillow 使用临时隔离 venv 补齐，未生成 `highlight-frames.xlsx` 的限制已解除。**

## Execution record

- 定向测试：`python -m unittest tests.test_yuntu_analysis tests.test_yuntu_presentation tests.test_yuntu_report -q`，128/128 通过。
- 全量测试：`python -m unittest discover -s tests -p 'test_*.py'`，284/284 通过。
- 编译检查：`python -m compileall -q scripts tests`，通过。
- 真实报告：`final-report-latest-taxonomy-20260902-chapter05-no-ai-index-observations/`，18 个素材面板、90 个指标控件；旧报告未覆盖。
