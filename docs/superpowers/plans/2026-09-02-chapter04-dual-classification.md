# 第四部分高光帧双分类标准 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为第四部分指定品牌 Tab 增加“标准分类 / 本批次标准”切换，同时保留现有人像、产品、其他面板。

**Architecture:** 在现有高光帧事实源上增加逐帧图片理解和批次级分类结果，和标准分类并行存储。前端在指定品牌 Tab 的卡片区域增加模式切换，默认复用现有固定分类；动态模式只替换分类分组，不重建图片卡片交互。

**Tech Stack:** Python、JSON Schema、视觉模型提示词、HTML/CSS/JavaScript、unittest。

**Spec:** `docs/superpowers/specs/2026-09-02-chapter04-dual-classification-design.md`

## Global Constraints

- 标准分类人像/产品/其他必须保留且默认展示。
- 动态分类先逐帧理解，再按整批理解结果生成规则并归类。
- 切换只作用于指定品牌 Tab 的高光帧卡片区域。
- 两套分类引用同一批图片，不能重复或丢失帧。
- 分类不可用时必须安全降级并说明原因。

### Task 1: 增加逐帧图片理解事实

**Files:**
- Modify: `scripts/yuntu_analysis.py`
- Modify: `prompts/yuntu-analysis-prompt.md`
- Test: `tests/test_yuntu_analysis.py`

**Interfaces:**
- Produces: 每张成功高光帧的 `frameUnderstanding`，包含主体、视觉焦点、人物/产品关系、动作、构图和信息表达。

- [ ] **Step 1: 添加失败测试，断言可用高光帧具有逐帧理解结果，失败帧具有明确原因。**
- [ ] **Step 2: 运行定向分析测试确认失败。**
- [ ] **Step 3: 修改高光帧提示词，明确先理解画面、暂不套用人像/产品/其他固定分类。**
- [ ] **Step 4: 将理解结果写入高光事实包并保留来源帧引用。**
- [ ] **Step 5: 运行 `python -m unittest tests.test_yuntu_analysis -v`。**
- [ ] **Step 6: 提交 `git add scripts/yuntu_analysis.py prompts/yuntu-analysis-prompt.md tests/test_yuntu_analysis.py && git commit -m "feat: add highlight frame understanding"`。**

### Task 2: 生成并校验本批次分类结果

**Files:**
- Modify: `scripts/yuntu_analysis.py`
- Modify: `scripts/yuntu_report.py`
- Test: `tests/test_yuntu_analysis.py`
- Test: `tests/test_yuntu_report.py`

**Interfaces:**
- Consumes: Task 1 的整批 `frameUnderstanding`。
- Produces: `standardClassification` 与 `batchClassification` 双结果；动态分类包含规则、顺序、分组和 frame refs。

- [ ] **Step 1: 添加失败测试，断言批次分类覆盖全部成功帧且每帧只出现一次。**
- [ ] **Step 2: 添加失败测试，断言动态分类缺失或证据不足时输出不可用状态。**
- [ ] **Step 3: 修改提示词/Schema，要求模型先汇总整批理解再生成批次规则和分类结果。**
- [ ] **Step 4: 增加确定性校验，检查分类引用属于同一批次、无重复、无未知帧。**
- [ ] **Step 5: 运行分析与报告定向测试。**
- [ ] **Step 6: 提交 `git add scripts/yuntu_analysis.py scripts/yuntu_report.py tests/test_yuntu_analysis.py tests/test_yuntu_report.py && git commit -m "feat: add batch highlight classification"`。**

### Task 3: 实现指定品牌 Tab 的分类切换

**Files:**
- Modify: `scripts/yuntu_presentation.py`
- Modify: `scripts/yuntu_report_sections.py`
- Modify: `scripts/templates/final-report-template.html`
- Modify: `assets/report/unified-report.css`
- Test: `tests/test_yuntu_presentation.py`
- Test: `tests/test_yuntu_report.py`

**Interfaces:**
- Consumes: 双分类结果及指定品牌范围。
- Produces: 指定品牌 Tab 内的标准/本批次标准切换控件和对应卡片分组。

- [ ] **Step 1: 添加失败测试，断言六个指定品牌范围显示切换控件，非指定范围不显示。**
- [ ] **Step 2: 添加失败测试，断言默认标准分类包含人像、产品、其他，动态模式使用批次分类名称。**
- [ ] **Step 3: 在 Presentation 中投影双分类结果和分类可用状态。**
- [ ] **Step 4: 在报告渲染中增加可访问模式切换，复用现有高光帧卡片、分页和预览逻辑。**
- [ ] **Step 5: 增加 CSS，保持标准分类现有视觉，并让两种模式共享卡片样式。**
- [ ] **Step 6: 运行 `python -m unittest tests.test_yuntu_presentation tests.test_yuntu_report -v`。**
- [ ] **Step 7: 提交 `git add scripts/yuntu_presentation.py scripts/yuntu_report_sections.py scripts/templates/final-report-template.html assets/report/unified-report.css tests/test_yuntu_presentation.py tests/test_yuntu_report.py && git commit -m "feat: toggle highlight classification modes"`。**

### Task 4: 真实报告与回归验收

**Files:**
- Create: `RPA数据汇总/yuntu-rankings-analysis-20260810-20260820-top6/final-report-latest-taxonomy-20260902-chapter04-dual-classification/`

- [ ] **Step 1: 使用真实高光帧重新生成独立报告，不覆盖既有产物。**
- [ ] **Step 2: 校验每张成功帧均有理解结果或失败原因，双分类覆盖和唯一性成立。**
- [ ] **Step 3: 校验指定品牌 Tab 的默认标准分类、动态分类切换和不可用降级状态。**
- [ ] **Step 4: 运行 `python -m compileall -q scripts tests`、`python -m unittest discover -s tests -p 'test_*.py'` 和 `git diff --check`。**
- [ ] **Step 5: 检查新报告 HTML/ZIP 产物并提交最终实现。**
