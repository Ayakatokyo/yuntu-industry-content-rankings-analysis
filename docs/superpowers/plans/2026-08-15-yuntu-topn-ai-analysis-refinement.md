# 云图 Top N 标题与 AI 分析优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让报告标题显示用户输入的 Top N，并让 AI 二次分析采用千川风格的“少量事实锚点 + 判断 + 下一步验证”短段落。

**Architecture:** 事实包继续保存 `requested_top_n`，报告渲染器从事实包读取该参数并传入章节组件。AI 提示词保持固定模板，但在每次生成时注入本次 Top N 和分析范围，并强化各维度的分析动作约束；不引入随机提示词生成。

**Tech Stack:** Python 3、stdlib `json`、现有 Markdown/HTML 渲染器、unittest。

---

### Task 1: 固化动态 Top N 标题契约

**Files:**
- Modify: `scripts/yuntu_report.py`
- Modify: `scripts/yuntu_report_sections.py`
- Test: `tests/test_yuntu_report.py`

- [ ] **Step 1: Write failing tests**

增加事实包 `requested_top_n=30` 时 HTML 和 Markdown 必须出现“各品牌榜单 Top 30 分析”，并禁止旧的“Top N”标题；同时验证不同 Top N 会随事实包变化。

- [ ] **Step 2: Run focused report tests and verify failure**

Run: `python -m unittest tests.test_yuntu_report -v`

Expected: 新增动态标题断言失败，当前渲染器仍输出固定“Top N”。

- [ ] **Step 3: Implement dynamic title propagation**

从 `fact_pack.brandTopNFacts.requested_top_n` 读取正整数，传给 HTML/Markdown 渲染函数；无事实包时保留 `Top N` 兼容回退。章节标题、tablist aria-label 和品牌范围说明统一使用该数字。

- [ ] **Step 4: Run focused tests and verify pass**

Run: `python -m unittest tests.test_yuntu_report -v`

Expected: 全部报告测试通过。

### Task 2: 按千川风格增强 AI 提示词

**Files:**
- Modify: `scripts/yuntu_analysis.py`
- Modify: `SKILL.md`
- Test: `tests/test_yuntu_analysis.py`
- Test: `tests/test_skill_contract.py`

- [ ] **Step 1: Write failing prompt contract tests**

要求生成的 prompt 明确包含“少量关键事实锚点 + 多句分析判断”、保留判断、改写判断、下一步验证、行业基线比较和 Top N 动态范围，并明确提示词模板固定、运行参数动态注入。

- [ ] **Step 2: Run focused tests and verify failure**

Run: `python -m unittest tests.test_yuntu_analysis tests.test_skill_contract -v`

Expected: 新增提示词契约断言失败。

- [ ] **Step 3: Implement a fixed template with runtime metadata**

将 `_prompt_text(brand_top_n, filters)` 改为固定模板加运行参数注入。各结论要求使用少量事实锚点，补充“事实意味着什么、保留/改写判断、下一步如何验证”；对数据、人群、营销卖点和品牌对比分别给出简短分析要求，禁止只罗列指标或标签。

- [ ] **Step 4: Run focused tests and verify pass**

Run: `python -m unittest tests.test_yuntu_analysis tests.test_skill_contract -v`

Expected: 全部通过，且生成的 prompt 包含本次 Top N。

### Task 3: 使用现有真实批次重新生成并验证

**Files:**
- Regenerate: `RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict/diagnostic-analysis/yuntu-analysis-prompt.md`
- Regenerate: `RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict/final-report/`

- [ ] **Step 1: Regenerate prompt and facts without RPA**

使用已有批次执行 `prepare-analysis --brand-top-n 30`，不重新调用 RPA；保留已有 AI JSON，除非提示词契约要求重新生成模型内容。

- [ ] **Step 2: Render final report from existing attested AI JSON**

使用现有 `yuntu-ai-analysis.json`、事实包和 provenance 重新渲染最终报告。

- [ ] **Step 3: Run full verification**

Run: `python -m unittest discover -s tests -v` and `python -m py_compile scripts/*.py`。

另外检查真实 HTML/Markdown 中出现“各品牌榜单 Top 30 分析”，Tab 保留完整品牌名，01 章不出现秒级范围。
