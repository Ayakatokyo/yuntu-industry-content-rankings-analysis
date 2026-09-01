# 第二部分图表提示与横向滚动 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (or superpowers:subagent-driven-development) to implement this plan task-by-task.

**Goal:** 调整第二部分报告的图表提示布局、分类规则说明文案，并将营销卖点一级分类柱状图改为单行横向滚动。

**Architecture:** 在 Python 报告片段渲染器中调整标题与提示的语义结构，在统一报告 CSS 中集中定义标题行和滚动容器样式；浏览器端仅消费现有 data 属性，不新增数据接口。

**Tech Stack:** Python、HTML 模板、CSS、unittest。

**Spec:** `docs/superpowers/specs/2026-09-01-chapter02-chart-hints-horizontal-scroll-design.md`

## Global Constraints

- 不修改 RPA、事实包字段或营销标签解析逻辑。
- 营销卖点提示必须使用：`点击一级标签柱状图可查看二级标签分布`。
- 营销卖点图表必须单行排列并通过横向滚动访问溢出分类。
- 保留现有点击下钻、键盘焦点和无数据分支。

### Task 1: 更新报告片段语义结构与文案

**Files:**
- Modify: `scripts/yuntu_report_sections.py`（八大人群与营销卖点标题/提示渲染）
- Test: `tests/test_yuntu_report.py`

- [ ] 添加断言：生成 HTML 包含八大人群标题行提示、营销卖点新提示、规则说明完整文案。
- [ ] 调整八大人群图表标题区域，将现有 `audience-crowd-hint` 放入标题行右侧。
- [ ] 调整营销卖点标题区域，输出新提示与规则说明段，并保持 `data-marketing-view` 及柱点击标记不变。
- [ ] 运行 `python -m unittest tests.test_yuntu_report`，确认新增断言先失败后通过。
- [ ] 提交：`git add scripts/yuntu_report_sections.py tests/test_yuntu_report.py && git commit -m "feat: refine chapter02 chart hints"`

### Task 2: 实现单行横向滚动样式

**Files:**
- Modify: `assets/report/unified-report.css`
- Test: `tests/test_yuntu_report.py`

- [ ] 添加 CSS 断言，检查营销柱状图包含 `flex-wrap:nowrap`、`overflow-x:auto` 和分类柱不可压缩规则。
- [ ] 将 `.unified-yuntu .marketing-column-chart` 改为单行横向滚动容器，桌面分类柱基础宽度 86px，移动端 68px。
- [ ] 为滚动容器补充 `tabindex="0"`、`role="region"`、`aria-label`（在渲染片段中输出）对应的可访问性样式，不隐藏滚动条功能。
- [ ] 保持八大人群柱状图当前布局，仅复用不影响其网格结构的通用变量。
- [ ] 运行 `python -m unittest tests.test_yuntu_report`，确认 CSS 断言通过。
- [ ] 提交：`git add assets/report/unified-report.css scripts/yuntu_report_sections.py tests/test_yuntu_report.py && git commit -m "feat: make marketing chart horizontally scrollable"`

### Task 3: 真实报告渲染与回归验证

**Files:**
- Create: `RPA数据汇总/yuntu-rankings-analysis-20260810-20260820-top6/final-report-latest-taxonomy-20260901/`（生成产物，不覆盖旧报告）

- [ ] 使用最新事实包与已验证分析结果重新执行 `render-report`。
- [ ] 检查 HTML 中标题行、三段文案、`overflow-x:auto` 和 16 个一级分类柱均存在。
- [ ] 运行 `python -m compileall -q scripts tests`。
- [ ] 运行 `python -m unittest discover -s tests -p 'test_*.py'`，记录完整通过结果。
- [ ] 使用浏览器检查桌面与窄屏：分类柱无第二行，横向滚动可拖动/键盘访问，标题提示不遮挡。
