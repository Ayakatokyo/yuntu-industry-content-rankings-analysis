# 云图报告优化交接摘要：Phase 01 已完成

**交接日期：** 2026-08-11  
**当前分支：** `main`  
**最新提交：** `1f694ce 修正报告首章数据口径`  
**本阶段状态：** `01｜TOP 素材组合结论` 已完成，等待用户审阅验收报告后再继续第 02 部分。

## 本阶段完成内容

第一部分已按新数据口径返工，不再使用“品牌筛选 TOP30”作为报告分析范围。

报告现在只保留两套读者可见数据口径：

1. **TOP1000 榜单素材**：用于全局排名、人群、卖点等整体结论。
2. **成功秒级拆解素材**：用于秒级指标、高光画面、单素材深度分析，以及各品牌 TOP 对比。

`01｜TOP 素材组合结论` 已调整为：

- `TOP1000 整体分析`：三维整体结论只描述 TOP1000 榜单数据。
- `各品牌 TOP 对比分析（成功秒级拆解素材）`：只基于实际成功取得秒级详情的素材，不再使用品牌筛选后的 TOP30。
- 品牌归属明确标注为“标题匹配归属”，不是 RPA 原生品牌字段。
- 当品牌没有成功秒级拆解素材时，不借用 TOP1000 中的其他素材做品牌结论；报告应说明数据不足。

## 关键实现位置

- `scripts/yuntu_analysis.py`
  - `_report_scopes()` 仅输出 `ranking` 与 `detail`。
  - `detail.sample_count` 仅统计成功秒级拆解素材；失败素材仅保留在 `failed_count`。
  - `topMaterialCombination` 的品牌对比事实只由成功详情对应的榜单记录生成。
  - AI 分析提示词限制：全局结论使用 TOP1000，品牌结论及品牌差异只使用成功秒级拆解素材。

- `scripts/yuntu_report.py`
  - HTML 和 Markdown 的第一部分仅渲染上述两种范围。
  - 删除“品牌筛选 TOP30 整体分析”“各品牌 TOP30”等标题、范围标签和文案。
  - 品牌面板展示“品牌归属：标题匹配归属；对比样本：成功秒级拆解素材”。

- `tests/test_yuntu_analysis.py`
  - 覆盖两套范围、成功详情计数和品牌事实仅来自成功拆解素材。

- `tests/test_yuntu_report.py`
  - 覆盖 HTML/Markdown 的范围标签、第一部分标题及 TOP30 文案不再出现。

## 验收产物

最新报告：

`/Users/shuzida/Desktop/FDE客户/小仙炖/yuntu-industry-content-rankings-analysis/RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-top5-real-e2e-20260809-203000/generated-report-latest-code-20260810-final/phase01-two-scope-rework-20260811/final-report/final-report.html`

对应产物：

- 事实包：`.../phase01-two-scope-rework-20260811/yuntu-analysis-data-phase01-two-scope.json`
- AI 分析：`.../phase01-two-scope-rework-20260811/yuntu-ai-analysis-phase01-two-scope.json`
- Markdown 报告：`.../phase01-two-scope-rework-20260811/final-report/final-report.md`

本次真实数据：

| 数据范围 | 数量 | 当前品牌覆盖 |
| --- | ---: | --- |
| TOP1000 榜单素材 | 1000 条 | 全部榜单样本 |
| 成功秒级拆解素材 | 5 条 | 均为“五个女博士” |

因此，报告第一部分当前只展示“五个女博士”的品牌面板；万益蓝、燕之屋没有成功秒级详情，无法形成三品牌秒级横向比较。这是数据事实，不应以 TOP1000 中未拆解素材补齐。

## 验证记录

已通过：

```bash
python3 -m unittest tests.test_yuntu_top_materials tests.test_yuntu_analysis tests.test_yuntu_report -q
```

结果：`Ran 54 tests ... OK`。

同时已执行 `git diff --check`，无格式错误。验收报告的静态检查确认：TOP30 禁止文案为 0，并包含 30 张可用高光帧资产。

## 数据兼容性限制

原始根目录的事实包与旧 AI 分析存在高光帧版本不匹配，不能直接混用：

- 不兼容组合：
  - `RPA数据汇总/.../diagnostic-analysis/yuntu-analysis-data.json`
  - `RPA数据汇总/.../diagnostic-analysis/yuntu-ai-analysis.json`

- 可兼容的历史帧/分析来源：
  - `RPA数据汇总/.../generated-report-latest-code-20260810-180515/diagnostic-analysis/yuntu-analysis-data.json`
  - `RPA数据汇总/.../generated-report-latest-code-20260810-180515/diagnostic-analysis/yuntu-ai-analysis.json`

Phase 01 已用新脚本重建范围与组合事实，并沿用兼容历史事实包中的真实高光帧资产。后续重新生成报告时，必须继续校验事实包、AI 分析及高光帧资源属于同一兼容版本，避免高光画面变为 0 帧或深度分析校验失败。

## 后续工作入口

用户已要求按整体方案逐项优化。下一步是 **`02｜人群洞察`**，但只有在用户确认可以继续后才开始。

开始第二部分前，应先明确告知用户：

> 现在开始优化第二部分 `02｜人群洞察`，重点是统一人群数据展示和悬浮提示文案，删除展开区重复标题，并保持 TOP1000 榜单口径一致。

已规划的第二部分改动：

1. 收起/展开按钮改为“收起人群汇总数据 / 展开人群汇总数据”。
2. 删除展开区域内重复的“人群数据”标题。
3. 八大人群、年龄、性别图表的悬浮文案统一为“命中素材数：n条”“占比：n%”。
4. 同步模板中 TOP N 动态图表文案，避免静态与动态图表口径、措辞不一致。

相关整体方案：

`docs/superpowers/specs/2026-08-11-yuntu-report-overall-optimization-design.md`

Phase 01 实施计划：

`docs/superpowers/plans/2026-08-11-yuntu-phase01-two-scope-rework.md`
