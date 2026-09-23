# 第四部分分类与高光帧特征分析 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重构第四部分分类 Tab，移除本批次洞察内容，并新增基于图片可观察特征的占比柱状图。

**Architecture:** 提示词为每个成功高光帧输出五个静态可观察维度；分析校验保证每帧每维度单一类别。Presentation 以真实 frame_refs 和素材 ID 确定性计算类别帧数、去重素材数和占比，报告渲染器只消费该投影，不让模型提供统计数字。

**Tech Stack:** Python、JSON Schema/分析校验、HTML/CSS/JavaScript、unittest、openpyxl（既有按需导出）。

**Spec:** `docs/superpowers/specs/2026-09-03-chapter04-feature-analysis-design.md`

## Global Constraints

- 标准模式 Tab 必须为“产品”“人像”“其他”，不得出现固定分类规则说明。
- 本批次模式 Tab 必须为“本批次视觉主题”，不渲染共性洞察和裂变方向。
- 新增 Tab 必须为“高光帧特征分析”，仅分析图片可观察事实；剪辑仅限静态画面结构。
- 图表占比按去重素材数计算，Tooltip 同时显示帧数和去重素材数。
- 不覆盖历史报告、原始 RPA 数据或未跟踪目录 `.rpa-quarantine-qianchuan/`。

### Task 1: 收敛提示词、Schema 与分析校验

**Files:**
- Modify: `prompts/yuntu-analysis-prompt.md`
- Modify: `scripts/yuntu_analysis.py`
- Modify: `scripts/yuntu_report.py`
- Test: `tests/test_yuntu_analysis.py`

**Interfaces:**
- Consumes: 逐帧 `frameUnderstanding` 与成功高光帧事实。
- Produces: 不再要求批次分类组输出 `common_patterns`/`derivative_directions`；每帧输出 `featureAnalysis.dimensions` 五个单值维度。

- [ ] **Step 1: 写失败测试，断言提示词要求“本批次视觉主题”且删除 3+3 洞察要求，同时包含五个图片可观察维度和静态画面结构限制。**
- [ ] **Step 2: 运行 `python -m unittest tests.test_yuntu_analysis -v` 中相关测试，确认旧提示词导致失败。**
- [ ] **Step 3: 修改提示词，明确标准分类标签、动态主题标签、五维类别格式、“无法判断”策略和不得推断动态剪辑的边界。**
- [ ] **Step 4: 扩展分析输出校验，要求每个成功 frame_ref 至多一个维度类别，拒绝空类别和动态剪辑断言；历史字段只读兼容。**
- [ ] **Step 5: 运行 `python -m unittest tests.test_yuntu_analysis -v`，确认提示词和校验通过。**
- [ ] **Step 6: 提交：`git add prompts/yuntu-analysis-prompt.md scripts/yuntu_analysis.py schemas tests/test_yuntu_analysis.py && git commit -m "feat: add highlight frame feature taxonomy contract"`。**

### Task 2: Presentation 投影与确定性统计

**Files:**
- Modify: `scripts/yuntu_presentation.py`
- Test: `tests/test_yuntu_presentation.py`

**Interfaces:**
- Consumes: Task 1 的逐帧特征分类、事实包素材 ID、现有双分类结果。
- Produces: `chapters.chapter04.brands[].featureAnalysis`，含维度、桶、frameCount、materialCount、share；分类模式 label 为新的中文名称。

- [ ] **Step 1: 写失败测试，断言本批次分类组不再投影共性/裂变字段，标准/本批次 label 使用新名称，并生成五维统计。**
- [ ] **Step 2: 写失败测试，给同一素材多张同类高光帧，断言 `materialCount` 只计 1，share 使用去重素材分母。**
- [ ] **Step 3: 实现维度归一化和主类别选择：同一素材同一维度按帧数优先、并列时按最高可用置信度和原始帧顺序择一。**
- [ ] **Step 4: 实现 `featureAnalysis` 投影，按真实 refs 计算 frameCount/materialCount/share，空数据输出不可用状态。**
- [ ] **Step 5: 删除批次组的 `common_patterns`/`derivative_directions` 投影，但兼容读取历史字段。**
- [ ] **Step 6: 运行 `python -m unittest tests.test_yuntu_presentation -v`。**
- [ ] **Step 7: 提交：`git add scripts/yuntu_presentation.py tests/test_yuntu_presentation.py && git commit -m "feat: project deterministic highlight feature analysis"`。**

### Task 3: HTML/Markdown 分类页面与新图表

**Files:**
- Modify: `scripts/yuntu_report_sections.py`
- Modify: `scripts/yuntu_report.py`
- Modify: `assets/report/unified-report.css`
- Modify: `assets/report/unified-report.js`
- Test: `tests/test_yuntu_report.py`

**Interfaces:**
- Consumes: Task 2 的 `classificationModes` 和 `featureAnalysis`。
- Produces: 新分类 Tab、无“分类标准：”说明、无批次 3+3 洞察，以及可访问的占比柱状图。

- [ ] **Step 1: 写失败测试，断言标准 Tab 为“产品/人像/其他”、本批次 Tab 为“本批次视觉主题”，HTML 不含规则说明或共性/裂变标题。**
- [ ] **Step 2: 写失败测试，断言“高光帧特征分析”Tab 的柱状图横轴含 `维度：类别`，纵轴为百分比，Tooltip/aria-label 含帧数和去重素材数。**
- [ ] **Step 3: 修改 `render_highlight_insights()`：模式 Tab 顺序为三个标准分类、本批次视觉主题、特征分析；批次模式只渲染分布、卡片和分页。**
- [ ] **Step 4: 增加特征图表渲染器，支持全部/单维度筛选、长标签横向滚动、无数据提示和可访问文本；复用现有竖柱 CSS。**
- [ ] **Step 5: 删除 `分类标准：`、分类规则段落和批次共性/裂变 HTML/Markdown 入口，保留历史数据兼容读取。**
- [ ] **Step 6: 更新 JavaScript Tab 初始化和维度筛选交互，确保品牌切换、模式切换、分页、tooltip、图片预览互不干扰。**
- [ ] **Step 7: 运行 `python -m unittest tests.test_yuntu_report -v`、`node --check assets/report/unified-report.js`。**
- [ ] **Step 8: 提交：`git add scripts/yuntu_report_sections.py scripts/yuntu_report.py assets/report/unified-report.css assets/report/unified-report.js tests/test_yuntu_report.py && git commit -m "feat: render highlight feature analysis tabs"`。**

### Task 4: 真实报告、Excel 回归与全量验收

**Files:**
- Create: `RPA数据汇总/<当前批次>/final-report-latest-taxonomy-20260903-feature-analysis/`
- Create: `RPA数据汇总/<当前批次>/exports/highlight-frames-chapter04-20260903-feature-analysis.xlsx`
- Create: 同名 ZIP 归档

- [ ] **Step 1: 使用现有真实事实包生成新的独立报告目录，不覆盖已有报告或 RPA 原始数据。**
- [ ] **Step 2: 校验 Presentation：标准 label、本批次 label、五维 featureAnalysis、每维度 materialCount 去重和 share 合计。**
- [ ] **Step 3: 校验 HTML/Markdown：无“分类标准：”、无本批次共性/裂变内容；特征 Tab、柱状图、帧数和素材数存在。**
- [ ] **Step 4: 回归独立 Excel 导出，确认三 Sheet 顺序和报告 ZIP 不含 Excel。**
- [ ] **Step 5: 执行 `python -m compileall -q scripts tests`、`python -m unittest discover -s tests -p 'test_*.py'`、`git diff --check`。**
- [ ] **Step 6: 打开新 HTML 检查品牌/分类/特征 Tab、长标签、tooltip 和移动端横向滚动；记录测试数量、报告/ZIP/XLSX 绝对路径及环境限制。**
- [ ] **Step 7: 提交验收产物和必要文档，不加入 `.rpa-quarantine-qianchuan/`。**
