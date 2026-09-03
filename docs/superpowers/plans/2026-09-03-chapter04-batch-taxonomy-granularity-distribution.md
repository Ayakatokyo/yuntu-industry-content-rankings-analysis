# 第四部分本批次标准细分类与分布图 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让第四部分本批次标准分类更细且有语义，并在每个品牌的本批次标准面板增加确定性分类分布柱状图。

**Architecture:** 提示词负责定义基于逐帧理解的细分类策略，分析校验负责约束类别数量、唯一覆盖和语义字段。Presentation 在品牌范围投影之后从真实分类帧引用计算 distribution，报告渲染器只把该确定性数据绘制为复用八大人群视觉语言的柱状图。

**Tech Stack:** Python、JSON Schema、HTML/CSS、unittest。

**Spec:** `docs/superpowers/specs/2026-09-03-chapter04-batch-taxonomy-granularity-distribution-design.md`

## Global Constraints

- 本批次分类必须先逐帧理解再整批归类，类别名称需要表达可观察的视觉角色或信息机制。
- 目标分类数量：`n≤3` 为 2–3 类，`4≤n≤7` 为 3–6 类，`n≥8` 为 6–10 类；不得超过成功帧数，证据不足时允许更少但至少两类。
- 每个分类组保持严格 3 条共性洞察 + 3 条裂变方向；每帧只能归入一个分类。
- 分布由 Presentation 从 frame_refs 确定性计算，不读取模型提供的占比。
- 图表只在品牌 Tab 的“本批次标准”面板显示，标准分类和其他章节不显示。
- 不覆盖历史报告、RPA 原始数据或 `.rpa-quarantine-qianchuan/`，真实报告写入新的日期目录。

---

## 文件职责

- `prompts/yuntu-analysis-prompt.md`：增加细分类目标、语义命名、拆分/合并边界和不可用条件。
- `scripts/yuntu_analysis.py`：同步高光输出 Schema/必要校验字段，确保分类粒度契约可验证。
- `scripts/yuntu_presentation.py`：为每个批次模式计算品牌范围 distribution，并验证其计数。
- `scripts/yuntu_report_sections.py`：渲染批次模式分布图的 HTML 结构和无数据状态。
- `assets/report/unified-report.css`：复用八大人群柱状图变量，补充动态类别横向滚动与图表卡片样式。
- `tests/test_yuntu_analysis.py`、`tests/test_yuntu_presentation.py`、`tests/test_yuntu_report.py`：覆盖提示词/Schema、分布投影、HTML 可访问性和回归。

### Task 1: 收紧提示词与 Schema 的细分类契约

**Files:**
- Modify: `prompts/yuntu-analysis-prompt.md`
- Modify: `scripts/yuntu_analysis.py`
- Modify: `tests/test_yuntu_analysis.py`

**Interfaces:**
- Produces: `batchClassification.groups` with semantic `label`/`rule`, evidence-backed fine-grained categories, and unchanged 3+3 insight structure.

- [ ] **Step 1: 添加失败测试，断言高光提示词包含 2–3 / 3–6 / 6–10 粒度目标、语义命名和禁止“其他 1/其他 2”占位类别的规则。**
- [ ] **Step 2: 添加失败测试，断言 Schema 要求批次组的 `label`、`rule`、`frame_refs` 和 3+3 洞察字段。**
- [ ] **Step 3: 运行 `python -m unittest tests.test_yuntu_analysis.YuntuAnalysisTests.test_highlight_prompt_requires_fine_grained_batch_taxonomy -v`，确认旧提示词失败。**
- [ ] **Step 4: 修改 `prompts/yuntu-analysis-prompt.md`，加入按成功帧数分档的类别目标、主体/动作/信息机制拆分边界、语义命名和至少两类不可用条件。**
- [ ] **Step 5: 在 `_highlight_output_schema()` 中补充批次组字段的非空约束；在已有结构校验中拒绝空 label/rule、重复类别和超过成功帧数的 frame_refs。**
- [ ] **Step 6: 运行 `python -m unittest tests.test_yuntu_analysis -v` 并提交：`git add prompts/yuntu-analysis-prompt.md scripts/yuntu_analysis.py tests/test_yuntu_analysis.py && git commit -m "feat: require finer batch highlight taxonomy"`。**

### Task 2: 计算并校验品牌范围的批次分布

**Files:**
- Modify: `scripts/yuntu_presentation.py`
- Modify: `tests/test_yuntu_presentation.py`

**Interfaces:**
- Consumes: `_classification_mode_categories()` 返回的批次 categories。
- Produces: `classificationModes[*]` 的 batch mode 增加：

```python
{"distribution": {"totalFrames": int, "buckets": [{"category": str, "label": str, "count": int, "share": float}]}}
```

- [ ] **Step 1: 添加失败测试，构造三类批次分类和品牌范围，断言全品牌及品牌 Tab 的 totalFrames、count、share 分母分别正确。**
- [ ] **Step 2: 添加失败测试，断言类别帧重复/遗漏或 distribution 计数不一致时抛出 `YuntuPresentationError`。**
- [ ] **Step 3: 运行 `python -m unittest tests.test_yuntu_presentation -v`，确认旧 Presentation 没有 distribution 字段。**
- [ ] **Step 4: 在 `_classification_mode_categories()` 完成 categories 后，以每个 category 的唯一 frame 数计算 distribution；不读取模型 count/share，保留 category 原始顺序，空批次返回 `totalFrames: 0, buckets: []`。**
- [ ] **Step 5: 在 `validate_yuntu_presentation()` 或对应投影校验中验证 count 总和、share 范围和总和容差，并确保 brand 过滤后的帧总数等于 totalFrames。**
- [ ] **Step 6: 运行 `python -m unittest tests.test_yuntu_presentation -v` 并提交：`git add scripts/yuntu_presentation.py tests/test_yuntu_presentation.py && git commit -m "feat: project batch taxonomy distribution"`。**

### Task 3: 在“本批次标准”面板渲染柱状图

**Files:**
- Modify: `scripts/yuntu_report_sections.py`
- Modify: `assets/report/unified-report.css`
- Modify: `tests/test_yuntu_report.py`

**Interfaces:**
- Consumes: `mode["distribution"]` 与现有 `mode["dashboard"]`。
- Produces: 带 `data-highlight-batch-distribution` 的图表卡片，包含 `aria-label`、类别标签、帧数和占比；批次不可用时不生成空图表。

- [ ] **Step 1: 添加失败测试，断言 HTML 在本批次标准模式出现“本批次标准分类分布”、`audience-column-chart`/等价竖柱结构、动态类别与帧数/占比。**
- [ ] **Step 2: 添加失败测试，断言标准分类模式不含该图表，批次不可用时只显示不可用原因。**
- [ ] **Step 3: 运行 `python -m unittest tests.test_yuntu_report.YuntuReportTests.test_renders_batch_classification_distribution_chart -v`，确认旧渲染失败。**
- [ ] **Step 4: 在 `render_highlight_insights()` 中增加 `render_batch_distribution(distribution, ...)`，按桶 count 归一化柱高，生成网格线、tooltip、样本总数和可访问标签；将其插入批次模式分类 Tab 之前。**
- [ ] **Step 5: 复用 `.audience-column-chart` 的布局变量，在统一 CSS 中为动态类别设置最小宽度、横向滚动、长标签换行和移动端可读性。**
- [ ] **Step 6: 运行 `python -m unittest tests.test_yuntu_report -v`、`node --check assets/report/unified-report.js`，并提交：`git add scripts/yuntu_report_sections.py assets/report/unified-report.css tests/test_yuntu_report.py && git commit -m "feat: render batch taxonomy distribution chart"`。**

### Task 4: 真实报告与全量回归

**Files:**
- Create: `RPA数据汇总/<当前批次>/final-report-latest-taxonomy-20260903-batch-distribution/`

- [ ] **Step 1: 使用最新双分类分析输入生成新的独立报告，不覆盖既有报告；若模型输入需要重生成，按 Task 1 的新提示词重新生成并保存到新的 diagnostic 目录。**
- [ ] **Step 2: 检查每个批次类别的语义名称、类别数量、每帧唯一覆盖和 3+3 洞察结构；记录各品牌的 distribution 桶和总数。**
- [ ] **Step 3: 打开新 HTML，确认各品牌 Tab 的“本批次标准”出现分类分布柱状图，标准分类不出现；确认长类别名称、tooltip 和无数据状态可读。**
- [ ] **Step 4: 回归上一轮独立 Excel 导出：工作簿仍为 `高光帧资产`、`标准分类`、`本批次标准`，导出不把 Excel 放回报告目录。**
- [ ] **Step 5: 运行 `python -m compileall -q scripts tests`、`python -m unittest discover -s tests -p 'test_*.py'`、`git diff --check`，并检查报告 ZIP 无 Excel。**
- [ ] **Step 6: 提交实现并记录新 HTML/ZIP/独立 Excel 的绝对路径和测试数量。**
