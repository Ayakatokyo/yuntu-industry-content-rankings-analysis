# 云图第五部分单素材脚本分析完善设计方案

## 1. 背景

云图第三章已经具备批量脚本洞察、关键词云和内容公式分布。第五章“单素材深度分析”当前以高光帧和秒级拆解为主，脚本 Tab 仅把 `script_text`、`content_formula` 和 `creative_breakdown` 直接拼成一块文本，缺少针对当前素材的 AI 结论、内容公式结构化展示、原始脚本阅读和证据句联动，导致每个素材工作区的信息层级混乱。

本 feature 的主对象是第五章单个素材工作区中的“脚本分析”板块。事实输入继续来自云图现有 `materialFacts`/`material-deep-dive-input.json`；不复用第三章批量脚本事实，不接入新连接器，不创建独立 CSV 导入适配层。千川参考页面与视觉基线为：

`/Users/shuzida/Desktop/FDE客户/小仙炖/qianchuan-video-peak-frames/runs/qianchuan-20260905-0830-0904-top15-persistent-mp4/final-report-compressed/final-report.html`

## 2. 目标行为

用户在第五章选择任意素材并打开“脚本分析”Tab 时，应按以下顺序阅读：

1. **AI 脚本结论**：只针对当前素材的脚本文案、内容公式一/二级标签和证据句，说明利益点、表达方式、场景承接、可能的保留/改写方向；不引用其他素材或其他章节事实。
2. **本视频内容公式**：以一级→二级链路/标签胶囊展示当前素材的公式组合；点击标签可定位对应证据句。
3. **本视频脚本**：以可读的原始脚本文案展示，证据句在原文中高亮；点击公式标签时滚动并高亮对应证据。
4. **证据与边界**：显示当前素材允许的 `evidenceRefs`，缺失时显示“数据不足以判断”；没有脚本时间戳时不建立帧—话术对应。

高光帧观察、秒级拆解、人群标签和综合判断仍由各自 Tab/面板负责，不在脚本 Tab 重复展示。

## 3. 事实包设计（保持云图数据结构）

### 3.1 输入单元

继续使用 `scripts/yuntu_analysis.py::_write_analysis_units()` 生成的：

`analysis-units/material-deep-dive-input.json`

在现有 `evidence.materialFacts[*]` 中为每个素材补充 `script` 投影，不新建千川式独立适配层：

```json
{
  "material_id": "m-001",
  "script": {
    "text": "早餐可以不碰碳水，但鲜炖燕窝一定要坚持吃。",
    "labels": [
      {
        "level1": "商品卖点",
        "level2": "品质功效",
        "evidenceRef": "script:m-001:商品卖点:品质功效"
      }
    ],
    "formula": [
      {"level1": "商品卖点", "level2": "品质功效"}
    ],
    "evidence": [
      {
        "level2": "品质功效",
        "sentence": "鲜炖燕窝一定要坚持吃。",
        "evidenceRef": "script:m-001:text:鲜炖燕窝"
      }
    ],
    "availability": {
      "text": {"available": true, "missing_reason": ""},
      "formula": {"available": true, "missing_reason": ""},
      "evidence": {"available": true, "missing_reason": ""}
    }
  },
  "evidenceIndex": {
    "script": [
      "script:m-001:商品卖点:品质功效",
      "script:m-001:text:鲜炖燕窝"
    ]
  },
  "highlightFrames": [],
  "secondLevelBreakdown": {"metrics": []}
}
```

`script.text`、`script.labels`、`script.formula`、`script.evidence` 都从当前素材已有的 `script_text`、`content_formula`、规范化证据句映射而来；缺失字段保持空数组/空字符串并填充 `missing_reason`。`evidenceIndex.script` 是模型和前端共同使用的引用白名单，引用必须逐字存在。

### 3.2 事实边界

- 模型只读取当前 `materialFacts[*]` 对象内的 `script` 与 `evidenceIndex.script`，不得从 Chapter 03 重新拼接，也不得跨素材复制结论。
- 标题、视频画面文本、榜单指标、高光帧和秒级曲线不是第五章脚本 AI 的输入；脚本 Tab 可显示当前素材脚本事实，但不把标题/画面当作脚本证据。
- 没有脚本分段时间戳时，`script.evidence` 只能定位到文本/公式引用，不产生秒点、帧—话术或因果归因。
- `convertCnt`、互动指数或曝光等指标不写进脚本结论，除非该素材的既有 AI 契约明确允许；本轮默认不允许。

## 4. AI 提示词与输出契约

在 `prompts/yuntu-analysis-prompt.md` 的 Chapter 05 规则中补充“单素材脚本分析”段落：

- 遍历 `material-deep-dive-input.json` 中每个素材，使用当前素材 `script` 和 `evidenceIndex.script`。
- 输出 `materialDeepDives[*].scriptAnalysis`，不改变既有 `frame_observations` 结构。
- `scriptAnalysis.conclusion` 控制 120–220 个中文字符，包含少量事实锚点、利益点/表达方式/场景承接、保留与改写方向和下一步验证；事实不足时写“数据不足以判断”。
- `scriptAnalysis.evidenceRefs` 至少一个且全部属于当前素材 `evidenceIndex.script`；无脚本事实时允许为空数组并明确不可用状态。
- 不得将脚本句子与高光帧或秒级指标做无依据对齐，不得把脚本结构写成点击/转化因果，不得使用其他素材证据。

目标输出形态：

```json
{
  "materialDeepDives": [
    {
      "material_id": "m-001",
      "scriptAnalysis": {
        "conclusion": "该素材先用早餐场景建立日常代入，再以鲜炖燕窝和坚持食用承接品质价值，表达生活化且利益点明确，适合保留“具体场景+产品价值”的结构。下一轮可分别测试品质卖点前置与场景前置，观察首屏停留、点击率和成交变化，不把结构差异直接写成因果。",
        "evidenceRefs": [
          "script:m-001:商品卖点:品质功效",
          "script:m-001:text:鲜炖燕窝"
        ],
        "availability": "available"
      },
      "frame_observations": []
    }
  ]
}
```

Schema 仍由 `_material_deep_dive_output_schema()` 统一生成：`material_id` 与既有 frame observation 同级，新增 `scriptAnalysis` 为可选对象；当事实包包含脚本时设为必填，当脚本整体缺失时保留对象并将 `availability` 标为 `unavailable`。旧的仅含 `frame_observations` 的历史 AI 结果可被归一化为“脚本分析不可用”，不阻断报告生成。

## 5. Presentation 投影

修改 `scripts/yuntu_presentation.py::_project_chapter05()`：

- 从 `materialFacts[material_id].script` 读取原始脚本、公式、证据和可用性。
- 从 `materialDeepDives[material_id].scriptAnalysis` 读取 AI 结论，并过滤越界 `evidenceRefs`。
- 在每个 `panels[*]` 增加：

```json
{
  "script": {
    "text": "…",
    "formula": [{"level1": "商品卖点", "level2": "品质功效"}],
    "evidence": [{"level2": "品质功效", "sentence": "…", "evidenceRef": "…"}],
    "evidenceRefs": ["…"],
    "analysis": {
      "conclusion": "…",
      "evidenceRefs": ["…"],
      "availability": "available"
    },
    "availability": "available"
  }
}
```

投影层不复制第三章批量事实，不把原始标题/画面文本注入 `script`，并保持第五章素材 Tab、帧观察和秒级交互契约不变。

## 6. 前端展示设计

### 6.1 HTML 语义层

第五章每个素材面板保留现有三 Tab，在 `material-detail-script-*` 中输出：

```text
脚本分析
├─ AI 脚本结论（.material-script-ai）
├─ 本视频内容公式（.material-script-formula）
├─ 本视频脚本（.material-script-transcript）
│  └─ 证据句高亮（.script-evidence-highlight）
└─ 数据状态/边界提示
```

AI 结论是第一视觉层，公式使用横向链路胶囊（一级标签 → 二级标签），脚本文案使用高可读行宽和自然换行；证据句采用同一高亮色，并附 `data-evidence-ref`，供公式点击联动。

### 6.2 JavaScript 交互

在 `scripts/templates/final-report-template.html` 的第五章脚本中新增 `renderMaterialScriptAnalysis(panel)`：

1. 读取当前 panel 的 `script` 对象；不存在时渲染空状态。
2. 将公式胶囊绑定到证据引用集合；点击后为对应文本节点添加 `.is-evidence-active` 并滚动到首个匹配证据。
3. 支持键盘 Enter/Space、`aria-controls`、`aria-live` 和 reduced-motion。
4. 切换素材 Tab 时清理旧高亮，切换回脚本 Tab 时不改变其他 Tab 的状态。

证据高亮必须基于 `evidenceRefs`/`sentence` 的确定性匹配；找不到句子时只显示引用标签，不用模糊替换或猜测文本。

### 6.3 CSS 视觉规范

参考千川单素材工作区：AI 结论使用主卡片，公式使用浅色标签链路，原始脚本使用纸张式文本卡，证据高亮使用暖色背景和左侧标记。脚本 Tab 与高光帧/秒级 Tab 保持相同的 `material-card`、内边距、圆角和标题层级；桌面端正文最大宽度 72ch，移动端单列且不横向溢出。

## 7. 异常、兼容与回滚

- 脚本缺失：保留 Tab，显示“脚本分析数据不足”，不隐藏整个素材面板。
- AI 缺失或引用越界：显示确定性公式/脚本文本，AI 卡显示“暂无 AI 二次分析结果”，越界引用被过滤并记录校验错误。
- 证据句不在原文：不进行高亮，不生成替代句；显示“证据句无法在当前脚本中定位”。
- 旧历史结果没有 `scriptAnalysis`：只降级 AI 区，不影响高光帧和秒级拆解。
- 本轮不保留新的双写或长期兼容层；完成验证后以当前最终 payload 为唯一口径。

## 8. 验收条件

- [ ] `material-deep-dive-input.json` 每个素材可提供脚本文本、公式、证据和证据白名单，且不混入其他素材或章节事实。
- [ ] AI 输出每个素材一个 `scriptAnalysis`，结论 120–220 个中文字符，引用全部来自当前素材白名单；脚本缺失时明确不可用。
- [ ] Presentation 的第五章 panel 同时包含 `script.text`、`script.formula`、`script.evidence` 和 `script.analysis`，且不破坏既有帧/秒级字段。
- [ ] 脚本 Tab 展示顺序固定为 AI 结论 → 内容公式 → 原始脚本 → 证据高亮/边界提示。
- [ ] 点击内容公式标签能定位并高亮对应证据句，键盘操作和 reduced-motion 可用。
- [ ] 第五章脚本分析不引用标题、画面文本、高光帧或秒级指标作自然语言证据，不生成因果归因。
- [ ] 桌面和移动端均无文本溢出；无脚本、无 AI、证据无法定位三种空状态可读。
- [ ] 现有全量 pytest 与第五章报告生成回归全部通过，第四章和第三章输出保持不变。

## 9. 详细设计判定

需要 `/detail-design` 级别核对：字段级脚本 payload、`evidenceRef` 白名单、文本高亮算法、Tab 生命周期和历史 AI 结果降级均会影响跨模块契约。实现阶段应先锁定这些细节，再进入模板与样式修改。
