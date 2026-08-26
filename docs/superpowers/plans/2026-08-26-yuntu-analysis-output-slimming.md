# 云图 AI 分析输出精简 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 删除当前 HTML 未展示的 AI 输出要求和渲染校验，同时保持新版精简 JSON 与旧版完整 JSON 均可生成现有五章报告。

**Architecture:** 将模型输出契约收敛到四个实际展示模块。报告加载、展示投影和 Prompt 使用同一精简契约；旧字段作为可选额外属性被忽略。真实批次回归通过临时精简副本执行，不修改落盘原始产物。

**Tech Stack:** Python 3、`unittest`、JSON、Markdown Prompt、现有离线 HTML 渲染器。

---

### Task 1: 锁定精简 JSON 渲染行为

**Files:**
- Modify: `tests/test_yuntu_report.py`
- Modify: `tests/test_yuntu_presentation.py`

- [ ] 新增测试：删除 7 个旧顶层字段和 `overallConclusions` 后仍生成 01 至 05 章。
- [ ] 新增测试：保留旧字段时仍可渲染，证明向后兼容。
- [ ] 运行新增测试并确认因当前必填校验失败。

### Task 2: 收敛报告与展示投影契约

**Files:**
- Modify: `scripts/yuntu_report.py`
- Modify: `scripts/yuntu_presentation.py`

- [ ] 将报告必填字段收敛为 `topMaterialCombination` 和 `chapter02Insights`，视觉及秒级字段继续按事实包条件校验。
- [ ] 删除旧字段的证据、实验和事实引用校验调用。
- [ ] 允许 `topMaterialCombination` 缺少 `overallConclusions`。
- [ ] 删除 `_render_html` 中未进入当前模板的旧字段中间渲染。
- [ ] 运行报告与展示投影测试并确认通过。

### Task 3: 收敛模型 Prompt 与技能说明

**Files:**
- Modify: `prompts/yuntu-analysis-prompt.md`
- Modify: `SKILL.md`
- Modify: `tests/test_yuntu_analysis.py`
- Modify: `tests/test_skill_contract.py`

- [ ] 先修改测试，要求 Prompt 只声明当前四个展示模块。
- [ ] 运行测试并确认因旧 Prompt 仍包含删除字段而失败。
- [ ] 删除旧章节、实验矩阵和 `overallConclusions` 的生成要求。
- [ ] 在技能分析流程中说明精简输出和旧版兼容边界。
- [ ] 运行分析与技能契约测试并确认通过。

### Task 4: 真实批次兼容回归

**Files:**
- Read: `RPA数据汇总/*/diagnostic-analysis/yuntu-analysis-data.json`
- Read: `RPA数据汇总/*/diagnostic-analysis/yuntu-ai-analysis.json`
- Create only under a temporary directory: 精简分析副本与重渲染产物

- [ ] 对两个完整批次生成删除旧字段后的临时 AI JSON。
- [ ] 用原事实包和临时 AI JSON 调用 `render_report`。
- [ ] 比较原报告与新报告的五个章节 ID、导航目标及所有当前展示 AI 文本。
- [ ] 确认两个临时报告均生成 HTML、Markdown、展示投影和 ZIP。

### Task 5: 全量验证

**Files:**
- Verify only

- [ ] 运行 `python -m unittest discover -s tests -v`，要求 0 失败。
- [ ] 运行 `python -m py_compile scripts/yuntu_report.py scripts/yuntu_presentation.py scripts/yuntu_analysis.py`。
- [ ] 运行技能 `quick_validate.py`。
- [ ] 运行 `git diff --check` 并审查最终 diff。
