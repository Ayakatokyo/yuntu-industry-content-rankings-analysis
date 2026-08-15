# 云图 TOP1000 与品牌 Top N 分析重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 01 章分别分析完整行业 TOP1000 与同一榜单池筛出的品牌 Top N，并将秒级详情排除在 01 章之外。

**Architecture:** `yuntu_normalizer.py` 负责把榜单原始指标规范化；`yuntu_analysis.py` 负责从完整榜单池生成 `industryTop1000Facts` 和 `brandTopNFacts`，从成功详情生成独立秒级事实；AI prompt 与 `yuntu_report.py`/章节渲染器只消费对应事实范围。RPA 取数流程不变。

**Tech Stack:** Python 3、stdlib `json/csv/unittest`、现有 HTML/Markdown 渲染器。

---

### Task 1: 固化榜单事实范围和指标契约

**Files:**
- Modify: `scripts/yuntu_normalizer.py`
- Modify: `scripts/yuntu_top_materials.py`
- Modify: `scripts/yuntu_analysis.py`
- Test: `tests/test_yuntu_normalizer.py`
- Test: `tests/test_yuntu_analysis.py`

- [ ] **Step 1: Add failing tests for preserved metrics and full-pool facts**

覆盖 `interact_cnt` 等非 01 章指标不得误进 01 章、五项目标指标保留、`prepare_analysis` 的行业候选数等于完整榜单数，以及品牌 facts 不以 `selectedMaterials` 数量为池。

- [ ] **Step 2: Run focused tests and verify failure**

Run: `python -m unittest tests/test_yuntu_normalizer.py tests/test_yuntu_analysis.py -v`

Expected: 新增断言失败，现有实现仍从成功详情集合构建 `topMaterialCombination`。

- [ ] **Step 3: Extend normalized metric whitelist and availability**

保留 `show_cnt`、`ctr`、`cvr`、`play_3s_rate`、`cpm` 的结构化状态；CPM 不从任何字段计算，统一写 `available=false` 与 `rpa_not_provided`。不把原始 `object_index` 传入模型输入。

- [ ] **Step 4: Build full-pool industry and brand Top N groups**

将事实生成入口改为完整 `pool_records`；品牌分组沿用当前运行的用户筛选上下文与现有可审计归属结果，输出 `industryTop1000Facts`、`brandTopNFacts`，同时保留未归属/歧义数量和 Top N 实际样本数。

- [ ] **Step 5: Run focused tests and verify pass**

Run: `python -m unittest tests/test_yuntu_normalizer.py tests/test_yuntu_analysis.py -v`

Expected: PASS。

### Task 2: 重构 AI 输入和 01 章校验/渲染

**Files:**
- Modify: `scripts/yuntu_analysis.py`
- Modify: `scripts/yuntu_report.py`
- Modify: `scripts/yuntu_report_sections.py`
- Test: `tests/test_yuntu_report.py`
- Test: `tests/test_yuntu_analysis.py`

- [ ] **Step 1: Add failing contract tests**

断言 prompt 要求 AI 只引用两套榜单 facts；报告 HTML 包含行业 TOP1000 与品牌 Top N；旧的“成功秒级拆解素材”文本和秒级证据不能出现在 01 章。

- [ ] **Step 2: Run focused report tests and verify failure**

Run: `python -m unittest tests/test_yuntu_report.py tests/test_yuntu_analysis.py -v`

Expected: 新契约断言失败。

- [ ] **Step 3: Update prompt and analysis validation**

修改 `topMaterialCombination` 合同，要求行业/品牌 summary 分别引用各自 facts 的素材 ID、指标和样本范围；删除品牌结论只能引用成功秒级素材的约束。

- [ ] **Step 4: Render only the two ranking scopes in section 01**

将行业整体分析和品牌 Top N tabs 的标题、样本数、五项指标和三类标签接入渲染；保留 04/05 的秒级渲染路径不变。

- [ ] **Step 5: Run focused tests and verify pass**

Run: `python -m unittest tests/test_yuntu_report.py tests/test_yuntu_analysis.py -v`

Expected: PASS。

### Task 3: 更新技能输入契约和文档

**Files:**
- Modify: `SKILL.md`
- Test: `tests/test_skill_contract.py`

- [ ] **Step 1: Add failing contract assertions**

要求 `pre_input` 同时包含“品牌榜单 Top 素材数”和“秒级拆解素材数”，并声明品牌 Top N 从已获取 TOP1000 中筛选，秒级素材数只控制 04/05。

- [ ] **Step 2: Update `SKILL.md`**

删除单一 `Top素材数量` 的歧义，写明 RPA 取数仍只获取合并 TOP1000，01 章不消费详情，CPM 未提供时不可推算。

- [ ] **Step 3: Run skill contract tests**

Run: `python -m unittest tests/test_skill_contract.py -v`

Expected: PASS。

### Task 4: Real-batch regeneration and verification

**Files:**
- Read/Regenerate: `RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict/diagnostic-analysis/`
- Render: `RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict/final-report/`

- [ ] **Step 1: Run full unit suite**

Run: `python -m unittest discover -s tests -v`

Expected: all tests pass。

- [ ] **Step 2: Rebuild analysis facts from existing normalized data**

Run: `python scripts/rpa_connector.py prepare-analysis --input-dir 'RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict' --output-dir 'RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict/diagnostic-analysis'`

Expected: fact pack reports industry count 1000 and preserves detail success count 5 / failure count 1。

- [ ] **Step 3: Re-attest existing model JSON only if contract-compatible**

Do not rerun RPA. If the existing model JSON violates the new 01 contract, update the model-authored JSON from the regenerated facts and then run `attest-analysis`。

- [ ] **Step 4: Render final report and inspect scope strings**

Run `render-report` with the existing batch analysis inputs. Assert HTML/Markdown contain industry TOP1000 and brand Top N, and 01 章 contains no second-level scope text。

- [ ] **Step 5: Run final verification**

Run: `python -m unittest discover -s tests -v` and `python -m py_compile scripts/*.py`

Expected: all tests and compilation pass; final report artifacts are non-empty。
