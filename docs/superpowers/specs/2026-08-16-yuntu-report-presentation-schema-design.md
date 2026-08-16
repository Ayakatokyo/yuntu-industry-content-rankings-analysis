# 云图报告 Presentation Schema 设计

## 目标

在不修改千川代码、不中断云图当前报告渲染的前提下，为云图建立显式、可校验、可独立演进的 `PresentationReport v1`。该模型承接已校验的云图事实包和 AI 分析结果，描述第 02、04、05 章所需的展示数据与交互契约，为后续统一千川与云图的图表、Tab、AI 文本、高光帧和单素材深度分析提供稳定边界。

## 设计原则

1. **展示对齐，数据独立**：复用千川已经验证的展示语义和交互模式，但不复制千川业务字段，也不导入千川专属假设。
2. **事实与解释分离**：图表、标签、趋势和帧元数据只来自事实包；AI 文本只来自已校验的 AI 分析 JSON；presentation 层不补写结论。
3. **双口径显式化**：第 02 章同时保留 `chapter02AiFacts` 与 `chapter02Facts` 的来源和用途，禁止通过同一字段隐式切换范围。
4. **声明展示，不执行交互**：schema 描述组件需要的输入、可用性和交互类型；当前阶段不改变 HTML 模板或 JavaScript 行为。
5. **可降级交付**：缺少图片、趋势或 AI 模块时，保留结构化不可用状态和原因，不生成替代事实或空洞结论。

## 范围

### 本阶段包含

- 新增 `presentationSchemaVersion: 1` 的云图 presentation 数据模型。
- 定义共享展示核心：报告元信息、章节、洞察块、图表、Tab、下钻、帧卡、素材深度分析和无障碍元数据。
- 定义云图扩展：第 02 章双事实口径、营销卖点二级标签、五类秒级指数、品牌/全量 scope 和 Top N 控制。
- 定义从现有 `analysis` 与 `fact_pack` 到 presentation 模型的纯函数适配边界。
- 定义验证规则和单元测试契约。

### 本阶段不包含

- 不修改 `/Users/shuzida/Desktop/FDE客户/小仙炖/qianchuan-video-peak-frames` 的任何文件。
- 不修改云图当前 `final-report-template.html`、CSS 或浏览器交互。
- 不改变第 01 章的分析口径或现有 `chapter02Facts` / `chapter02AiFacts` 数据生成逻辑。
- 不重跑 RPA，不改 AI 提示词，不重新分类营销标签。
- 不把 presentation 数据写入现有 `final-report-data.json`，除非后续迁移设计明确批准。

## 架构

```text
analysis.json + fact_pack.json
             │
             ▼
  build_yuntu_presentation(...)
             │
             ├── shared core
             ├── yuntu extensions
             └── validation metadata
             ▼
 presentation.json (PresentationReport v1)
```

presentation 层是一个只读投影。它不持有 RPA 调度状态，不重新聚合业务指标，不从文字推导图表数据，也不把 AI 结论转换成事实。适配器失败时应返回明确的校验错误，不能静默生成半成品 schema。

## 文件边界

### `scripts/yuntu_presentation.py`

新增模块，负责：

- `build_yuntu_presentation(analysis, fact_pack, *, report_meta=None)`：构建完整 presentation 对象。
- `validate_yuntu_presentation(payload)`：验证版本、章节、scope、图表、帧引用、素材引用和交互声明。
- 纯函数辅助器：scope 排序、图表 bucket 归一化、帧路径安全检查、AI 引用存在性检查。

该模块不得导入模板、CSS 或浏览器运行时代码。

### `tests/test_yuntu_presentation.py`

新增测试，先覆盖 schema 最小有效对象，再覆盖真实云图 fact pack 的双口径、营销下钻、帧覆盖、秒级趋势和缺失数据降级。

### 后续接入文件（本阶段只在计划中保留）

- `scripts/yuntu_report.py`：未来在写出最终报告时生成并保存 presentation JSON。
- `scripts/templates/final-report-template.html`：未来消费 presentation JSON，不在本阶段修改。
- `assets/report/unified-report.css`：未来按共享组件契约收敛样式，不在本阶段修改。

## Schema 总体结构

```json
{
  "presentationSchemaVersion": 1,
  "report": {
    "reportId": "yuntu-rankings-analysis-...",
    "title": "云图行业内容榜单分析",
    "period": {"startDate": "YYYY-MM-DD", "endDate": "YYYY-MM-DD"},
    "status": "complete",
    "sections": ["chapter01", "chapter02", "chapter03", "chapter04", "chapter05"]
  },
  "scopes": [],
  "chapters": {},
  "materials": [],
  "interactions": {},
  "extensions": {"yuntu": {}}
}
```

### `report`

只包含报告身份和展示状态，不包含 RPA 执行过程。`status` 只允许 `complete`、`partial`、`unavailable`。`sections` 使用稳定 ID，不直接使用中文标题作为程序键。

### `scopes`

```json
{
  "id": "all",
  "label": "全量",
  "kind": "industry|brand",
  "rankScope": "top1000|topN|all-materials",
  "topN": 30,
  "aiFactSource": "chapter02AiFacts",
  "chartFactSource": "chapter02Facts"
}
```

每个品牌 scope 必须明确 `topN`、`aiFactSource` 和 `chartFactSource`。全量 scope 的 AI 和图表范围均为 TOP1000；品牌 scope 的 AI 范围为用户输入 Top N，图表范围为该品牌全量素材。

## 共享展示核心

### 洞察块 `insight`

```json
{
  "id": "audience-click-pattern",
  "title": "标题",
  "text": "已校验的 AI 二次分析文本",
  "evidenceRefs": ["audience:CLICK_COUNT:age:..."] ,
  "parts": {
    "factAnchors": ["少量事实锚点"],
    "judgment": "分析判断",
    "validation": "下一步验证"
  }
}
```

`parts` 是展示结构，不要求重新切分 AI 原文；若 AI 输出没有结构化三段，则 `parts` 可为空，但 `text` 和 `evidenceRefs` 必须保留。presentation 层不得自己生成 `judgment` 或 `validation`。

### 图表 `chart`

```json
{
  "id": "marketing-level1",
  "type": "column|pie|table",
  "title": "营销卖点一级类别",
  "dataSource": "chapter02Facts",
  "scopeId": "brand-x",
  "value": {"field": "occurrenceCount", "unit": "count"},
  "buckets": [
    {"key": "产品利益", "label": "产品利益", "value": 120, "rank": 1}
  ],
  "interaction": {"type": "column-drilldown", "target": "marketing-level2"},
  "accessibility": {"label": "营销卖点一级类别柱状图"}
}
```

柱图必须提供稳定排序、单位和可访问名称。下钻目标必须是 schema 中已有的 chart 或 detail view，不能只依赖前端约定的 CSS class。

### Tab 与交互声明

```json
{
  "id": "chapter02-scope-tabs",
  "type": "tab-list",
  "items": [{"id": "all", "label": "全量", "panelId": "chapter02-all"}],
  "defaultItemId": "all",
  "keyboard": ["ArrowLeft", "ArrowRight", "Home", "End"]
}
```

当前阶段只验证声明完整性；实现仍由现有模板负责。

## 第 02 章模型

```json
{
  "chapter02": {
    "scopeTabs": {"interactionId": "chapter02-scope-tabs", "items": []},
    "panels": [{
      "scopeId": "all",
      "aiInsights": {
        "audience": [],
        "marketing": []
      },
      "charts": [],
      "topNControl": {
        "min": 1,
        "max": 30,
        "value": 30,
        "factSource": "chapter02Facts"
      }
    }]
  }
}
```

规则：

- `aiInsights` 只能引用 `chapter02AiFacts` 对应范围。
- `charts`、`topNControl` 和标签明细只能引用 `chapter02Facts`。
- `marketing` 图表使用原始标签归类结果，不允许 presentation 层重新分类。
- 一级类别柱点击后进入二级标签饼图和完整明细表；Top 10 聚合规则属于数据加工层，presentation 只消费已排序 bucket。

## 第 04 章模型

```json
{
  "chapter04": {
    "scopeId": "all",
    "categories": [{
      "id": "portrait",
      "label": "人物主视觉",
      "commonConclusion": "",
      "derivativeDirections": [],
      "frames": [{
        "frameRef": "highlight:material:peak_top_1",
        "available": true,
        "relativePath": "assets/highlight-frames/...jpg",
        "second": 12,
        "frameType": "peak",
        "caption": "点击 Top1 峰值帧"
      }]
    }]
  }
}
```

每个成功帧只能在一个分类出现一次。不可用帧保留在素材事实或限制字段中，但不能进入可视帧列表。分类枚举由云图 AI schema 定义，当前允许 `portrait`、`product`、`scene`、`text_overlay`、`other`。

## 第 05 章模型

```json
{
  "chapter05": {
    "materialTabs": [{"materialId": "m-1", "label": "#1 素材标题", "panelId": "material-m-1"}],
    "panels": [{
      "materialId": "m-1",
      "metrics": [],
      "frames": [],
      "frameObservations": [],
      "secondLevel": {
        "metrics": [
          {"id": "点赞指数", "available": true, "points": [], "highPoints": [], "lossPoints": []}
        ],
        "metricOrder": ["点赞指数", "流失指数", "点击指数", "互动指数", "评论指数"]
      },
      "aiAnalysis": {
        "visualSummary": "",
        "dataSummary": "",
        "audienceSummary": "",
        "marketingSummary": "",
        "replicationAdvice": "",
        "riskNotes": "",
        "doNotCopy": ""
      },
      "availability": {"status": "complete|partial|unavailable", "reasons": []}
    }]
  }
}
```

第 05 章的 `frames`、`secondLevel` 和 `aiAnalysis` 必须保持来源可区分：前两者是事实，后者是 AI 解释。脚本字段不在云图 schema 中伪造；没有脚本事实时由 `availability` 表达不可用。

## 云图扩展

`extensions.yuntu` 只承载无法放入共享核心、但对云图稳定展示必需的结构：

```json
{
  "extensions": {
    "yuntu": {
      "rankingMetric": "totalCost",
      "brandOrder": [],
      "marketingTagTaxonomyVersion": 1,
      "secondLevelMetricOrder": ["点赞指数", "流失指数", "点击指数", "互动指数", "评论指数"],
      "factSourceContract": {
        "chapter02AiFacts": "AI 二次分析唯一来源",
        "chapter02Facts": "真实汇总图表与 Top N 控制唯一来源"
      }
    }
  }
}
```

## 校验规则

`validate_yuntu_presentation` 至少验证：

1. `presentationSchemaVersion == 1`，报告状态和 section ID 合法。
2. scope ID 唯一；品牌 scope 的 AI/chart fact source 与 Top N 规则匹配。
3. 所有 chart bucket 数值有限、排序稳定、单位明确；下钻 target 存在。
4. 所有 AI insight、衍生方向和素材 AI 分析的 `evidenceRefs` 存在于原始 analysis/fact pack 的已知引用集合。
5. 第 04 章成功帧覆盖一次且仅一次；本地相对路径必须位于报告资产根目录内。
6. 第 05 章每个选中素材恰有一个 panel；帧观察不得引用不可用帧；秒级点的秒数必须存在于对应事实趋势。
7. 五类秒级指数顺序固定；缺失指标必须带 `available: false` 和原因，不得以空点数组冒充可用。
8. `topNControl` 只能引用 `chapter02Facts`，不能切换到 `chapter02AiFacts`。

## 测试设计

测试按 TDD 顺序实现：

1. 最小有效 presentation 对象通过验证。
2. 缺失版本、重复 scope、未知下钻 target 被拒绝。
3. 真实 fixture 生成全量和品牌 scope，验证 AI 与图表双口径不混用。
4. 营销标签一级/二级 chart、Top 10 聚合和完整明细保持排序与引用。
5. 第 04 章重复帧、漏帧、不可用帧引用分别失败或正确降级。
6. 第 05 章五类趋势顺序、真实秒数和缺失指标原因得到验证。
7. 适配器不修改输入对象，输出可 JSON 序列化，且不含视频 URL、RPA 执行字段或第 01 章重算结果。

## 后续迁移路径

本设计完成并验证后，下一阶段再单独制定迁移计划：

1. 让云图 `render_report` 同时输出 `presentation.json`，但继续使用现有 HTML。
2. 将现有模板的柱图、Tab、帧卡和素材工作区改为消费 presentation 数据。
3. 以真实严格批次做桌面端和移动端视觉验收。
4. 再将千川的隐式 `report_data_for_template()` 逐步整理成兼容的共享核心，不改变其业务扩展。
