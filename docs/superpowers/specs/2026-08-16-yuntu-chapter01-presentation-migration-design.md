# 云图第 01 章 Presentation Migration 设计

## 目标

将第 01 章 `TOP 素材组合结论` 纳入 `PresentationReport v1`，让最终 HTML 与第 02、04、05 章一样优先消费展示投影，同时保持当前的分析口径、品牌 Top N 参数、品牌 Tab 和无障碍交互不变。

## 边界

- 不修改千川项目、RPA、AI 提示词或第 01 章的事实加工逻辑。
- 不重写第 01 章 HTML 组件和 CSS。
- 旧的 `analysis + fact_pack` 调用保留为兼容回退。
- presentation 只复制已校验的 AI 结论和范围元数据，不生成或改写结论。

## 数据模型

`chapters.chapter01` 包含：

- `executiveInsight`：综合结论。
- `overallInsights`：TOP1000 整体结论，按现有维度保留。
- `brandTabs`：品牌排序、默认项和键盘导航声明。
- `brandPanels`：每个品牌的当前 Top N 结论、标题匹配归属说明和范围。
- `brandComparisonInsight`：品牌间差异总结。

每个 insight 保留 `text`、`dimension`、`evidence` 和素材引用。第 01 章品牌范围来自已加工 fact pack 中的用户请求 Top N；不会用第 02 章的全量品牌图表口径替代它。

## 渲染路径

```text
analysis.topMaterialCombination + fact_pack.brandTopNFacts
                         ↓
        presentation.chapters.chapter01
                         ↓
   render_top_material_combination(presentation=...)
                         ↓
                 现有 HTML / JS / CSS
```

渲染器在存在完整 `chapter01` presentation 时仅从该对象构造当前组件的内部值；否则沿用原有输入。这样可让新报告走 schema，也不破坏历史不完整输入。

## 验证

- schema 单元测试覆盖结论、品牌排序、Top N、证据和交互声明。
- 报告测试覆盖 HTML 从 schema 分支生成现有品牌 Tab 和结论区。
- 完整单测、编译检查、`git diff --check`。
- 用真实严格批次重渲染，不重跑 RPA。
