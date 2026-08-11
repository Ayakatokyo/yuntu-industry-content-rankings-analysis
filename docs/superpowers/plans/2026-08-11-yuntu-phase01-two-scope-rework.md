# 云图 01 章两套数据口径返工 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 将 `01｜TOP 素材组合结论` 收敛为 TOP1000 全局分析与成功秒级拆解素材集合两套口径，删除品牌筛选 TOP30 整体分析，并重新生成可验收的离线报告。

**Architecture:** `scripts/yuntu_analysis.py` 只输出 `ranking` 和 `detail` 读者可见范围，并把实际成功秒级拆解的素材对应榜单记录传给 `build_top_material_combination()` 生成各品牌 TOP 对比事实。`scripts/yuntu_report.py` 只渲染这两种范围：全局结论区标注 TOP1000，品牌 Tab 和品牌差异区标注成功秒级拆解素材集合；HTML 与 Markdown 均不保留 TOP30 文案。

**Tech Stack:** Python 3、`unittest`、静态 HTML/Markdown 报告、JSON 事实包。

---

### Task 1: 用测试定义两套范围和品牌对比样本

**Files:**
- Modify: `tests/test_yuntu_analysis.py:143-179, 288-350`
- Modify: `tests/test_yuntu_report.py:44-113, 298-332`

- [x] **Step 1: 写入失败测试，要求事实包没有 `brand_top30`，且详情层的样本数只计算成功详情**

```python
self.assertEqual(set(data["reportScopes"]), {"ranking", "detail"})
self.assertEqual(data["reportScopes"]["detail"]["sample_count"], 1)
self.assertEqual(data["reportScopes"]["detail"]["success_count"], 1)
self.assertEqual(data["reportScopes"]["detail"]["failed_count"], 1)
```

将测试名改为 `test_prepare_analysis_emits_report_scopes_for_ranking_and_successful_detail`，并删除旧的 `brand_top30` 断言。

- [x] **Step 2: 写入失败测试，要求 01 章事实中的品牌对比只包含已成功拆解的素材**

在 `test_prepare_analysis_writes_top_material_combination_and_prompt_contract` 中增加一条未入选、标题为“万益蓝”的榜单记录。保留“五个女博士”素材为唯一 `selectedMaterials` 项，并断言：

```python
combination = data["topMaterialCombination"]
self.assertEqual(
    [item["material_id"] for item in combination["overall"]["topMaterials"]],
    ["1"],
)
self.assertEqual(set(combination["brands"]), {"五个女博士"})
self.assertIn("成功秒级拆解素材集合", prompt)
self.assertNotIn("品牌筛选 TOP30", prompt)
```

- [x] **Step 3: 写入失败测试，要求 HTML 和 Markdown 只出现两种范围且没有 TOP30 章节**

将报告夹具的 `executiveSummary.evidence` 改为 `ranking` 与 `detail`，事实包改为：

```python
"reportScopes": {
    "ranking": {"source_name": "TOP1000 榜单素材", "sample_count": 1000},
    "detail": {
        "source_name": "成功秒级拆解素材",
        "sample_count": 5,
        "success_count": 5,
        "failed_count": 1,
    },
},
```

渲染后断言：

```python
self.assertIn("TOP1000 榜单素材：1000 条", rendered)
self.assertIn("成功秒级拆解素材：5 条", rendered)
self.assertIn("TOP1000 整体分析", rendered)
self.assertIn("各品牌 TOP 对比分析（成功秒级拆解素材）", rendered)
self.assertNotIn("品牌筛选 TOP30", rendered)
self.assertNotIn("各品牌 TOP30", rendered)
self.assertNotIn("TOP30", markdown)
```

- [x] **Step 4: 执行定向测试，确认因旧口径失败**

Run: `python3 -m unittest tests.test_yuntu_analysis.YuntuAnalysisTests.test_prepare_analysis_emits_report_scopes_for_ranking_and_successful_detail tests.test_yuntu_analysis.YuntuAnalysisTests.test_prepare_analysis_writes_top_material_combination_and_prompt_contract tests.test_yuntu_report.YuntuReportTests.test_render_report_shows_top_material_scope_and_executive_summary -v`

Expected: `FAIL`，原因是仍输出 `brand_top30`、详情样本数包含失败记录或报告仍渲染 TOP30 文案。

### Task 2: 生成与成功秒级拆解一致的事实包

**Files:**
- Modify: `scripts/yuntu_analysis.py:66-98, 417, 440-488`
- Test: `tests/test_yuntu_analysis.py`

- [x] **Step 1: 仅保留 `ranking` 与 `detail` 范围**

将 `_report_scopes()` 的详情范围改为：

```python
"detail": {
    "source_name": "成功秒级拆解素材",
    "sample_count": len(selected),
    "success_count": len(selected),
    "failed_count": len(rejected),
    "selection_rule": "实际成功取得秒级详情的素材；各品牌 TOP 对比仅使用此集合",
    "limitations": ["执行失败素材不纳入秒级分析或各品牌 TOP 对比"],
},
```

删除 `brand_top30` 对象。

- [x] **Step 2: 让组合事实只从已成功详情的榜单记录构建**

在 `prepare_analysis()` 构造 `selected_pool_records`，并替换事实包中的调用：

```python
selected_pool_records = [
    record for record in pool_records
    if record.get("material_id") in selected_ids
]
...
"topMaterialCombination": build_top_material_combination(selected_pool_records),
```

保留 `candidatePool`、`audienceDashboard` 和全局标签统计从 `pool_records` 生成，避免把 TOP1000 全局分析缩小为秒级样本。

- [x] **Step 3: 更新模型提示的口径约束**

将 `topMaterialCombination` 契约改为：`overallConclusions` 只能描述 `ranking` 的全局事实；`brandConclusions` 与 `brandComparisonConclusion` 只能引用 `detail` 成功素材，并明确无品牌命中时必须写“数据不足以判断”，不得借用 TOP1000 中未成功拆解的品牌素材。

- [x] **Step 4: 运行 Task 1 的两个分析测试，确认通过**

Run: `python3 -m unittest tests.test_yuntu_analysis.YuntuAnalysisTests.test_prepare_analysis_emits_report_scopes_for_ranking_and_successful_detail tests.test_yuntu_analysis.YuntuAnalysisTests.test_prepare_analysis_writes_top_material_combination_and_prompt_contract -v`

Expected: `OK`。

### Task 3: 删除 01 章 TOP30 呈现并标注正确范围

**Files:**
- Modify: `scripts/yuntu_report.py:358-400, 890-990`
- Test: `tests/test_yuntu_report.py`

- [x] **Step 1: 改写 Markdown 的章节标题**

将全局三维结论标题从 `品牌筛选条件下 TOP30 整体分析` 改为 `TOP1000 整体分析`，将品牌段落标题从 `各品牌 TOP30 对比分析` 改为 `各品牌 TOP 对比分析（成功秒级拆解素材）`。

- [x] **Step 2: 改写 HTML 范围标签和区块标题**

在 `top_material_combination_cards()` 中只遍历：

```python
for scope_key in ("ranking", "detail")
```

详情标签使用 `sample_count` 作为主计数：`成功秒级拆解素材：5 条`。全局区块标题改为 `TOP1000 整体分析`；品牌区块和 Tab 的可访问名称改为 `各品牌 TOP 对比分析（成功秒级拆解素材）`，并在品牌面板的可见说明中保留标题规则归属与“仅含成功秒级拆解素材”的边界。

- [x] **Step 3: 运行报告定向测试，确认通过**

Run: `python3 -m unittest tests.test_yuntu_report.YuntuReportTests.test_render_report_shows_top_material_scope_and_executive_summary -v`

Expected: `OK`。

### Task 4: 回归验证并生成新验收报告

**Files:**
- Read: `RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-top5-real-e2e-20260809-203000/batch-manifest.json`
- Read: `RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-top5-real-e2e-20260809-203000/normalized/list-records.json`
- Read: `RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-top5-real-e2e-20260809-203000/generated-report-latest-code-20260810-180515/diagnostic-analysis/yuntu-ai-analysis.json`
- Create: `RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-top5-real-e2e-20260809-203000/generated-report-latest-code-20260810-final/phase01-two-scope-rework-20260811/`

- [x] **Step 1: 运行完整回归**

Run: `python3 -m unittest tests.test_yuntu_top_materials tests.test_yuntu_analysis tests.test_yuntu_report -v`

Expected: `OK`。

- [x] **Step 2: 基于原始 RPA 数据和兼容分析创建新阶段输入**

对原始 RPA 根目录执行 `scripts/yuntu_analysis.py`，将新事实包写入新阶段目录的 `diagnostic-analysis/`。从 `generated-report-latest-code-20260810-180515` 复制与高光帧匹配的模型分析 JSON 到新阶段目录，并将模型分析的 `executiveSummary` 与品牌结论限制为实际 5 条成功秒级素材；保留 AI 输出其余经现有校验的章节。不得覆盖原始 `final-report` 或 Phase 01 预览。

- [x] **Step 3: 渲染并检查产物**

Run: `python3 scripts/yuntu_report.py --analysis-json '<新阶段分析 JSON>' --fact-pack '<新阶段事实包 JSON>' --output-dir '<新阶段/final-report>'`

Run: `rg -n 'TOP1000 榜单素材|成功秒级拆解素材|TOP1000 整体分析|各品牌 TOP 对比分析|品牌筛选 TOP30|各品牌 TOP30' '<新阶段/final-report/final-report.html>' '<新阶段/final-report/final-report.md>'`

Expected: 前四项出现；后两项不出现；输出包含 `final-report.html`、`final-report.md`、`final-report-data.json` 和 30 个可用高光帧资产。

- [x] **Step 4: 执行静态检查**

Run: `git diff --check`

Expected: 无输出、退出码 0。
