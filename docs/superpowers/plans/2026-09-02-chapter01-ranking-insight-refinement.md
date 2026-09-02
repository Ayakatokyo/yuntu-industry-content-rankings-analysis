# 第一部分素材榜单洞察展示细化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 细化第一部分的行业对比语义、曝光口径、对比面板文案/布局与数值格式，同时保留已有爆款卡片实现。

**Architecture:** 在现有三批榜单列表和确定性比较事实之上做最小字段调整；提示词只强化环比与全行业分段语义；前端复用当前折叠组件，将确定性对比面板移动到两个洞察区块之间并统一数字格式化。

**Tech Stack:** Python、JSON Schema、HTML/CSS/JavaScript、unittest。

**Spec:** `docs/superpowers/specs/2026-09-02-chapter01-ranking-insight-refinement-design.md`

## Global Constraints

- 素材列表中的曝光只保留区间展示值，不保留素材级曝光确定值。
- 三组筛选条件的聚合比较事实继续保留，前端不得显示科学计数法。
- `dataSummary` 必须分别使用“环比看”和“与全行业大盘对比看”表达两种比较。
- 爆款素材事实卡片不新增、不改版、不改变字段与交互。
- 对比面板位于素材表现洞察和爆款素材洞察之间。

### Task 1: 移除素材级曝光确定值并保留区间

**Files:**
- Modify: `scripts/yuntu_analysis.py`
- Modify: `scripts/yuntu_top_materials.py`
- Test: `tests/test_yuntu_analysis.py`

**Interfaces:**
- Consumes: 三批榜单素材列表。
- Produces: 只含曝光区间展示值的素材行，以及可供比较面板使用的既有聚合事实。

- [ ] **Step 1: 添加失败测试，断言当前/环比/行业素材行不含确定曝光字段，只保留区间文本；同时断言四项指标仍存在。**
- [ ] **Step 2: 运行对应分析测试，确认新断言在旧结构上失败。**
- [ ] **Step 3: 调整素材行投影，删除素材级曝光数值及其别名，仅保留原始区间展示值；保持聚合比较事实兼容。**
- [ ] **Step 4: 对无法解析的区间写入不可用状态，不填充或推导确定值。**
- [ ] **Step 5: 运行 `python -m unittest tests.test_yuntu_analysis -v`。**
- [ ] **Step 6: 提交 `git add scripts/yuntu_analysis.py scripts/yuntu_top_materials.py tests/test_yuntu_analysis.py && git commit -m "fix: keep ranking exposure ranges only"`。**

### Task 2: 强化提示词中的两种比较语义

**Files:**
- Modify: `prompts/yuntu-analysis-prompt.md`
- Test: `tests/test_yuntu_analysis.py`

**Interfaces:**
- Consumes: Task 1 的比较事实。
- Produces: `dataSummary` 明确区分当前表现、环比和全行业对比；`hotMaterialInsight` 保持原语义。

- [ ] **Step 1: 添加失败测试，要求提示词包含“环比看”和“与全行业大盘对比看”，并禁止只使用模糊行业比较短语。**
- [ ] **Step 2: 运行提示词契约测试确认失败。**
- [ ] **Step 3: 修改第一章提示词，规定当前表现→环比看→与全行业大盘对比看的固定表达顺序，并明确不重新计算曝光。**
- [ ] **Step 4: 运行分析提示词和 Schema 定向测试。**
- [ ] **Step 5: 提交 `git add prompts/yuntu-analysis-prompt.md tests/test_yuntu_analysis.py && git commit -m "refine: distinguish chapter01 comparison narratives"`。**

### Task 3: 调整前端标题、面板顺序和曝光格式

**Files:**
- Modify: `scripts/yuntu_presentation.py`
- Modify: `scripts/yuntu_report_sections.py`
- Modify: `scripts/yuntu_report.py`
- Modify: `assets/report/unified-report.css`
- Test: `tests/test_yuntu_presentation.py`
- Test: `tests/test_yuntu_report.py`

**Interfaces:**
- Consumes: 既有比较事实与双段 AI 输出。
- Produces: “素材表现洞察”→“环比与全行业对比”→“爆款素材洞察”的章节一页面结构。

- [ ] **Step 1: 添加失败测试，断言新标题、按钮文案、面板 DOM 顺序和三组指标展示。**
- [ ] **Step 2: 添加失败测试，断言曝光总量/变化以中文单位渲染，禁止 `e+` 科学计数法。**
- [ ] **Step 3: 运行定向报告测试确认失败。**
- [ ] **Step 4: 修改渲染层标题和按钮文案，复用现有折叠控件，将比较面板移动到两个洞察区块之间。**
- [ ] **Step 5: 调整比较事实渲染为当前指标、环比变化、行业变化三段，并对曝光数值使用统一中文单位格式化。**
- [ ] **Step 6: 保持爆款卡片渲染函数、数据字段、排序和交互不变。**
- [ ] **Step 7: 运行 `python -m unittest tests.test_yuntu_presentation tests.test_yuntu_report -v`。**
- [ ] **Step 8: 提交 `git add scripts/yuntu_presentation.py scripts/yuntu_report_sections.py scripts/yuntu_report.py assets/report/unified-report.css tests/test_yuntu_presentation.py tests/test_yuntu_report.py && git commit -m "feat: refine chapter01 insight comparison panel"`。**

### Task 4: 真实报告与回归验收

**Files:**
- Create: `RPA数据汇总/yuntu-rankings-analysis-20260810-20260820-top6/final-report-latest-taxonomy-20260902-chapter01-insight-refinement/`

- [ ] **Step 1: 从现有真实分析输入生成新的独立报告目录和 ZIP，不覆盖历史产物。**
- [ ] **Step 2: 检查 ranking unit 的素材行曝光字段、三组比较事实和四项指标。**
- [ ] **Step 3: 检查 HTML/Markdown/Presentation 的标题、按钮、顺序、双段 AI 内容和科学计数法禁用。**
- [ ] **Step 4: 检查爆款素材卡片数量、素材 ID、区间字段和交互结构未变化。**
- [ ] **Step 5: 运行 `python -m compileall -q scripts tests`、`python -m unittest discover -s tests -p 'test_*.py'` 和 `git diff --check`，记录实际结果与环境限制。**
