# 第五部分删除五类指数 AI 二次分析设计方案

## 目标

删除第五部分对点赞指数、流失指数、点击指数、互动指数和评论指数的 AI 二次分析文案及其展示链路，保留五类指数的确定性秒级数据、峰值/流失点、指标切换和时长滑杆等原始数据交互。

## 问题与边界

当前 AI 文案位于 `materialDeepDives[].second_level_observations[]`，Presentation 投影为 `chapters.chapter05.panels[].secondLevelObservations[]`。这些文案的 `evidence_seconds` 只校验是否存在于对应指标的秒级曲线，并未绑定实际图片引用；而现有标准高光帧主要按点击指数提取，因此非点击指标的画面归因缺少可靠证据。

本次只删除 AI 解释层，不删除指标事实层。删除范围包括：五类指数 AI 洞察对象、其输入/输出契约、Presentation 投影和 Markdown/HTML 用户可见文案。保留范围包括：`secondLevelBreakdown.metrics`、每个指标的秒级 `points`、`high_points`、`loss_points`、指标切换控件、时长滑杆、确定性曲线和原始证据数据。

## 数据流调整

```text
RPA/榜单素材详情
        ↓
secondLevelBreakdown.metrics
        ├─ 秒级 points
        ├─ high_points / loss_points
        └─ 指标切换与时长滑杆

materialDeepDives.second_level_observations
        ✕ 删除 AI 二次分析文案
```

第五部分不再要求模型读取或生成五类指数的自然语言解释，也不再把 `evidence_seconds` 当作画面归因依据。确定性曲线仍可展示指标随时间变化，但页面不再声称某个具体画面导致指标变化。

## 兼容策略

- 新生成报告不输出 `second_level_observations` 和 `secondLevelObservations`。
- 历史分析 JSON 和历史报告目录不改写、不覆盖。
- 读取历史分析时允许旧字段存在，但在新 Presentation 和 HTML/Markdown 渲染中忽略这些字段；历史确定性 `secondLevelBreakdown` 继续可用。
- Schema/校验区分新输出和历史输入：新输出禁止死字段，兼容读取不因旧字段直接崩溃。

## 验收标准

- 新模型输入、输出 Schema、Presentation 和报告渲染链路无五类指数 AI 文案字段。
- `secondLevelBreakdown.metrics`、秒级点、峰值/流失点、指标切换和时长滑杆全部保留。
- HTML 和 Markdown 不出现五类指数 AI 洞察标题、摘要或证据秒文案。
- 历史报告和旧 JSON 不被修改，新渲染可安全忽略旧 AI 字段。
- 定向测试、全量测试、编译检查和真实报告产物验证完成。
