# 云图 AI 二次分析契约升级设计

## 目标

将云图报告的新增视觉和秒级模块纳入当前对话模型的正式二次分析范围。流程仍为：

```text
fetch -> prepare-analysis -> 当前对话模型生成 yuntu-ai-analysis.json
      -> attest-analysis -> render-report
```

脚本不新增模型 API 调用。`prepare-analysis` 只计算、整理并输出可审计事实和本地帧资产；当前对话模型读取事实包、提示词及成功帧后生成业务判断；渲染器只校验和展示模型结论。

## 范围与边界

- 不调整 RPA 连接器、榜单筛选、秒级指标计算或高光帧选择规则。
- 高光帧仍为 0s 封面帧和点击指数 Top 5 局部峰值帧；本地帧可在视频 URL 过期后复用。
- `03｜脚本洞察` 继续是无脚本数据的固定占位，不引入脚本、话术或帧-话术推断。
- `04｜高光画面洞察` 和 `05｜单素材深度分析` 不再允许报告渲染器生成业务判断兜底文本。
- 解释只能描述事实共现或可能关系，不得归因于点击、转化或指标提升；不得输出未经确认的健康、滋补或孕期功效主张。

## 事实包契约

`yuntu-analysis-data.json` 升级为 schema v4，并保留 `materialFacts`、`candidatePool`、`topMaterialCombination` 等现有字段以兼容既有统计与报告代码。新增面向模型的分层事实输入：

| 字段 | 内容 | 规则 |
| --- | --- | --- |
| `rankingFacts` | 排名和榜单指标 | 只包含已采集指标；CPM 缺失须显式标记不可用。 |
| `audienceFacts` | 年龄、性别、八大人群标签 | 标明标签可重叠，不可相加为真实人群占比。 |
| `marketingFacts` | 素材标签、产品卖点、场景及促销利益 | 仅为标签事实，不构成营销效果因果。 |
| `secondLevelFacts` | 每条素材的五类秒级趋势 | 仅包含点赞、流失、点击、互动、评论指数及真实秒数。 |
| `highlightFrameFacts` | 每条高光帧的元数据 | 包含 `frame_ref`、秒数、帧类型、峰值排序和值及可用状态。 |
| `visualAssets` | 可由当前对话模型读取的图片清单 | 每项包含素材 ID、本地相对路径、`frame_ref`、秒数、类型、可用状态和失败原因。 |
| `dataLimitations` | 数据缺失、帧失败、URL 过期和样本限制 | 仅记录事实限制，不代写商业结论。 |

同一成功帧在 `highlightFrameFacts` 与 `visualAssets` 使用一致的 `frame_ref`。不可用帧保留失败原因，但不进入视觉分类和逐帧观察的覆盖范围。

## 当前对话模型输入与输出

`yuntu-analysis-prompt.md` 明确要求当前对话模型读取事实包和 `visualAssets` 的每张成功本地 JPEG 后，输出完整 JSON。提示词禁止模型编造真实点击次数、转化原因、脚本内容、互动计数或因果结论。

输出的既有章节继续保留；其中新增或强化的字段如下：

### `audienceInsights`

必填，作为 `02｜人群洞察` 的文字判断来源。每项包含 `summary`、`evidence` 和 `material_id` 或 `material_ids`，且必须说明人群标签可重叠、不能相加为真实人群比例。年龄、性别和八大人群的图表仍由事实包渲染；渲染器不得从图表数据代写其商业解释。

### `highlightDashboard`

有成功高光帧时必填。`groups` 中每个成功 `frame_ref` 必须且只能出现一次，按以下顺序使用非空分类：`portrait`、`product`、`scene`、`text_overlay`、`other`。分类为单一主视觉类别，不表示画面不含其他元素。

每个分类包含：

- `frame_refs`
- `common_patterns`
- `derivative_directions`，每条方向只能引用同组帧

每项观察只能说明肉眼可见的主体、构图、场景、字幕或动作，并可说明其“处于点击指数峰值秒点”；不得说明它造成点击、转化或效果提升。

### `materialDeepDives`

每个入选素材恰有一项，并包含：

- `material_id`
- `frame_observations`：每张成功帧恰被引用一次
- `second_level_observations`：仅五类云图指数，证据秒数必须真实存在
- `visual_summary`
- `data_summary`
- `audience_summary`
- `marketing_summary`
- `replication_advice`
- `risk_notes`
- `opening_judgment`
- `visual_rhythm`
- `peak_frame_reading`
- `second_level_reading`
- `audience_fit`
- `replication_advice`
- `do_not_copy`

上述所有摘要均由模型输出。`risk_notes` 应覆盖数据不足、视觉复用边界和潜在合规复核，不能将合规风险写成未经验证的结论；`do_not_copy` 说明不宜照搬的表达、画面或宣称，不得根据标题和趋势补造脚本内容。

### `experimentMatrix`

每个实验在既有字段外必须引用至少一项真实证据：`material_id`、`metric`、`frame_ref` 或秒级趋势及秒数。引用必须可以回溯到事实包；实验是待验证假设，不是效果承诺。

## 校验与渲染

渲染前校验以下条件：

1. 成功高光帧存在时，必须有 `highlightDashboard`，且全量唯一分类。
2. `audienceInsights` 必须存在且每项带素材和事实证据；图表保持事实展示，不为其生成规则结论。
3. 每个选中素材必须有一条 `materialDeepDives`，所有新增摘要字段非空。
4. 每条逐帧观察引用该素材真实可用 `frame_ref`；每条秒级观察引用该趋势的真实秒数。
5. 每个实验矩阵项至少引用一个真实素材、指标、帧或秒级证据。
6. AI 可见及报告可见字段均拒绝禁用因果和未证实健康功效措辞。

`render-report` 不补写视觉观察、深度总结、受众和营销判断、复用建议、风险提示或实验假设。所有结论保留在 `final-report-data.json`，可见 HTML 仅展示经过校验的结论与必要图表数据。

## 失败处理与可审计性

- 视频 URL 到期不影响已落盘成功帧；事实包在 `visualAssets` 中保留其本地来源和可用状态。
- 没有成功帧时不要求视觉分类，报告显示数据不可用状态，不生成替代视觉洞察。
- 缺少必填 AI 模块、引用不存在的证据或命中禁止语言时，渲染命令非零失败，不降级为规则拼接分析。
- `attest-analysis` 继续记录事实包哈希、提示词哈希、来源和生成者；`programmatic_fallback` 继续被拒绝。

## 测试策略

单元测试先验证 schema v4 的分层事实包、成功帧唯一分类、新增深度分析字段、实验引用与禁止语言。随后验证完整渲染：报告应消费模型结论，`final-report-data.json` 保留帧和证据引用，而 HTML 不出现审计 JSON 或旧的规则兜底句。
