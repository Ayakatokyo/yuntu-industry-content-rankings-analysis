# 云图脚本分析与千川报告对齐 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline execution is selected for this task).

**Goal:** 使用云图真实脚本事实重新生成结构化 AI 二次分析，并让第三章按千川报告的洞察、关键词和内容公式层级完整呈现。

**Architecture:** 保持现有事实包和 `scriptInsights` 输出契约不变，在 Prompt 中约束固定的脚本洞察顺序；Presentation 透传全部已校验洞察；报告 Sections 将洞察、关键词三列和公式 dashboard 按千川 DOM 顺序渲染。真实批次通过现有截帧、图片理解、provenance 校验和报告生成链路落盘。

**Tech Stack:** Python 3、unittest/pytest、JSON facts、HTML/CSS/vanilla JavaScript、现有 RPA/highlight pipeline。

**Spec:** `docs/superpowers/specs/2026-09-04-yuntu-script-insights-report-ui-polish-design.md` 与本轮已确认的 Prompt/真实链路对齐方案。

## Global Constraints

- 只使用 `selected_detail_materials` 中真实存在的素材、脚本和公式证据。
- 不修改 CSV 解析、RPA 连接器、事实语义或第五章秒级拆解契约。
- 不生成帧-话术、秒点-话术对应，不把内容公式或脚本样本写成因果结论。
- `scriptInsights[*]` 必须包含非空 `title`、`summary`、`evidence` 和合法 `material_ids`。
- AI 缺失时关键词、公式图表和真实空状态仍须可渲染。

### Task 1: 固定脚本洞察组织并补充回归测试

**Files:**
- Modify: `prompts/yuntu-analysis-prompt.md`
- Test: `tests/test_yuntu_analysis.py`
- Test: `tests/test_yuntu_presentation.py`

**Interfaces:**
- Consumes: `analysis-units/script-input.json` 的真实脚本事实。
- Produces: 仍为 `scriptInsights[]`，每项使用现有 `title`、`summary`、`evidence`、`material_ids` 字段。

- [ ] 写测试，验证 Prompt 明确要求固定顺序的脚本洞察，并要求每条洞察绑定素材证据。
- [ ] 运行该测试确认当前 Prompt 不满足断言。
- [ ] 修改 Prompt：要求按开场/问题引入、信任/证明、卖点/场景/促销组合、结构复用与改写、可验证变量等固定内容组织；没有事实时输出“数据不足以判断”；禁止因果和帧-话术推断。
- [ ] 运行 Prompt 相关测试及静态重复规则扫描。

### Task 2: 让 Presentation 和报告 Sections 展示全部洞察

**Files:**
- Modify: `scripts/yuntu_presentation.py`
- Modify: `scripts/yuntu_report_sections.py`
- Test: `tests/test_yuntu_presentation.py`
- Test: `tests/test_yuntu_report.py`

**Interfaces:**
- Consumes: 已校验的 `analysis.scriptInsights` 和 `scriptDashboard`。
- Produces: `chapter03.scriptInsights` 的全量投影，以及千川顺序的 HTML：AI 洞察 → 关键词三列 → 公式汇总/钻取。

- [ ] 写失败测试，使用超过两条真实契约合法的洞察，断言第三章全部展示且第一条不再重复充当唯一关键词结论。
- [ ] 运行测试确认当前实现只展示两条或存在重复投影问题。
- [ ] 修改投影/渲染：保留全部洞察；按维度标题识别公式/脚本文案卡片，其余合法洞察按同一 insight-card 继续展示；关键词结论只读取 dashboard conclusion；卖点和频次只读取确定性事实。
- [ ] 运行 Chapter 03 回归测试并确认 HTML 没有把脚本文案、创意拆解复制到第五章之外。

### Task 3: 严格收敛第三章千川视觉细节

**Files:**
- Modify: `assets/report/unified-report.css`
- Modify: `scripts/templates/final-report-template.html`（仅在公式交互或焦点恢复仍与千川结构不一致时修改）
- Test: `tests/test_yuntu_report.py`

**Interfaces:**
- Consumes: Task 2 输出的 HTML mount 点和 `data-script-formula`。
- Produces: 桌面端 AI/关键词布局、折叠公式区、键盘钻取和移动端降级。

- [ ] 写结构断言，覆盖千川 class 层级、三列最小宽度、正文字号行高、折叠按钮和公式 drilldown。
- [ ] 运行测试确认差异后再做最小 CSS/模板调整。
- [ ] 以千川参考 HTML/CSS 的计算关系校准卡片内边距、圆角、关键词三列比例、图表容器和断点，不引入无关色板。
- [ ] 运行 Python/JS 语法检查、`git diff --check` 和报告结构测试。

### Task 4: 用真实云图批次重新执行完整链路

**Files:**
- Read: `RPA数据汇总/yuntu-rankings-analysis-20260810-20260820-top12/analysis-units/script-input.json`
- Read: `RPA数据汇总/yuntu-rankings-analysis-20260810-20260820-top12/analysis-units/visual-assets.json`
- Create: `RPA数据汇总/yuntu-rankings-analysis-20260810-20260820-top12/diagnostic-analysis/yuntu-ai-analysis-qianchuan-aligned.json`
- Create: `RPA数据汇总/yuntu-rankings-analysis-20260810-20260820-top12/final-report-qianchuan-aligned-20260904/final-report.html`

**Interfaces:**
- Consumes: 真实 CSV 详情、临时视频 URL/已落盘视频、成功高光帧和图片理解输入。
- Produces: 带 provenance 的真实 AI 分析 JSON、最终 HTML 和 ZIP。

- [ ] 校验批次素材 ID、脚本覆盖数和 visual assets 清单，确认不重复使用旧分析结果。
- [ ] 对真实成功视频执行下载/截帧，逐张执行图片理解；临时 URL 失败时使用已落盘帧并记录失败原因。
- [ ] 基于真实 `script-input.json` 生成千川结构化 `scriptInsights`，其余顶层分析字段沿用同一批次已验证事实，不补造业务指标。
- [ ] 通过现有 `validate_analysis_input`、provenance/attest 校验后渲染报告并生成 ZIP。
- [ ] 检查报告中 5 个素材 ID、脚本洞察条数、关键词/公式统计、成功高光帧引用和第五章图片理解结果均来自真实文件。

### Task 5: 全量验证与交付

**Files:**
- Test: `tests/` 全量测试
- Verify: 真实批次最终 HTML、JSON provenance 和 ZIP

- [ ] 运行 `pytest -q`，确认全量测试通过。
- [ ] 运行 Python 编译检查、模板 JavaScript 语法检查和 `git diff --check`。
- [ ] 对比千川参考报告的第三章 DOM 顺序、卡片结构、关键词三列和公式折叠区。
- [ ] 交付最终报告、ZIP、分析 JSON 和真实链路执行摘要，明确列出素材 ID 与高光帧/图片理解结果。
