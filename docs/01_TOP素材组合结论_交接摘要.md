# 第一部分交接摘要：TOP 素材组合结论

## 交接目的

第一部分 `01｜TOP 素材组合结论` 已完成。新的对话应从第二部分的设计确认和实现开始，不应回退、重做或破坏第一部分，也不得修改 RPA 的既有能力。

## 当前工作区

- 仓库：`/Users/shuzida/Desktop/FDE客户/目标品牌/yuntu-industry-content-rankings-analysis`
- 当前分支：`main`
- 最近与第一部分相关的提交：
  - `32905d8 fix: restore report sidebar navigation`
  - `847fedb refactor: focus report on top material conclusions`
  - `7b3496f fix: make top material brand tabs functional`
  - `c448e89 refine: add brand tabs to top material report`
- `main` 已包含尚未推送到 `origin/main` 的本地提交。
- 存在用户未提交的 `.gitignore` 修改。后续操作必须保留，不得暂存、覆盖或回退。
- 用户明确要求不使用浏览器工具。后续仍以代码、测试和静态产物验证为主。

## RPA 边界

本次改造仅覆盖 RPA 执行完成后的数据提取、商业分析和报告呈现。以下路径不得修改，必须保留现有 RPA 能力：

- `scripts/rpa_connector.py`
- `scripts/yuntu_batch.py`
- `references/connectors/**`
- 网关调用、重试、CSV 下载、CSV 规范化与详情抓取主路径

第一部分全部改动均位于 RPA 后处理、报告模板和测试，RPA 自检持续通过。

## 第一部分已实现的业务口径

### 分析对象

1. 品牌筛选条件下按曝光量排序的 TOP30。
2. 标题匹配识别后的各品牌曝光 TOP30。

品牌识别为业务规则，不是 RPA 原生品牌字段：

- `万益蓝/WONDERLAB`：标题命中 `万益蓝` 或 `wonderlab`
- `五个女博士`：标题命中 `五个女博士`
- `燕之屋`：标题命中 `燕之屋`
- 未命中归为未知品牌，只进入整体 TOP30；命中多个品牌归为歧义品牌，不进入单品牌对比。

### 结论结构

整体 TOP30 与每个品牌 TOP30 都按三条固定展开线输出：

- 从数据维度看
- 从人群维度看
- 从营销卖点维度看

整体人群结论会强制补充以下说明：

> 人群标签是重叠标签，不是真实人群分布，不能相加为 100%。

整体与品牌结论中使用的核心数据包括曝光、CTR、CVR、PVR、3S/5S/完播、互动率、组件点击率和平均播放时长；CPM 未由 RPA 提供时必须写为不可用，禁止推算。人群同时保存素材数量占比与曝光加权覆盖率。卖点只允许描述共现或相关表现，不得写成因果。

## 已实现的后处理模块

### 数据事实

[scripts/yuntu_top_materials.py](/Users/shuzida/Desktop/FDE客户/目标品牌/yuntu-industry-content-rankings-analysis/scripts/yuntu_top_materials.py) 是纯后处理模块，负责：

- 以曝光量、排名、素材 ID 的稳定顺序选取 TOP30。
- 汇总整体和品牌 TOP30 的曝光结构、指标均值/中位数、TOP3 集中度。
- 汇总年龄、性别、八大画像的素材数量占比和曝光加权覆盖率。
- 按成分/原料、功效、痛点、使用场景、内容形式、促销利益汇总营销卖点。
- 产出标签与 CTR/CVR/3S 完播率的有无标签中位数对照；任一组样本少于 3 条则不作比较结论。

### 分析输入与校验

[scripts/yuntu_analysis.py](/Users/shuzida/Desktop/FDE客户/目标品牌/yuntu-industry-content-rankings-analysis/scripts/yuntu_analysis.py) 将第一部分事实写入分析包和模型提示。

[scripts/yuntu_report.py](/Users/shuzida/Desktop/FDE客户/目标品牌/yuntu-industry-content-rankings-analysis/scripts/yuntu_report.py) 强制以下合同：

- `topMaterialCombination.overallConclusions` 必须且只能有 `data`、`people`、`marketing` 三项。
- 每个 `brandConclusions` 项必须有 `dataSummary`、`peopleSummary`、`marketingSummary`。
- `brandComparisonConclusion` 必须包含覆盖每个参与品牌且带指标字段的证据。
- 用户可读 `summary` 禁止出现“查看数据依据”、`证据：` 或审计 JSON 片段。

结构化 `evidence` 继续保留在 `final-report-data.json`，但不进入 HTML 或 Markdown 正文。

## 当前报告呈现

用户可读报告当前被刻意收敛为单章节：

```text
01｜TOP 素材组合结论

品牌筛选条件下 TOP30 整体分析
从数据维度看，……
从人群维度看，……
从营销卖点维度看，……

────────────────

各品牌 TOP30 对比分析
[万益蓝/WONDERLAB] [五个女博士] [燕之屋]

当前选中品牌的三维结论

────────────────

品牌间差异总结
```

HTML 具体行为：

- 侧边目录功能已保留，但目录当前只显示 `01｜TOP 素材组合结论`。
- 桌面端目录固定在左侧；移动端变为正文上方的单行目录。
- 品牌 Tab 默认选中 `五个女博士`，初始只展示该品牌；其余品牌面板带 `hidden`，不占页面高度。
- Tab 支持点击和 `ArrowLeft`、`ArrowRight`、`ArrowUp`、`ArrowDown`、`Home`、`End` 键盘切换。
- Tab 使用报告内导航样式：文字加暖棕色底部强调线，不再使用表单式边框按钮。
- 可见正文不再显示“当前品牌”或“标题匹配归属”提示行；该归属信息保留在 panel 的无障碍标签中。
- 无 JavaScript 时，`noscript` 会顺序展示全部品牌面板。

Markdown 不支持真实 Tab，因此按品牌顺序展示，品牌之间使用 `---` 分隔。

模板与报告渲染的关键文件：

- [scripts/templates/final-report-template.html](/Users/shuzida/Desktop/FDE客户/目标品牌/yuntu-industry-content-rankings-analysis/scripts/templates/final-report-template.html)
- [scripts/yuntu_report.py](/Users/shuzida/Desktop/FDE客户/目标品牌/yuntu-industry-content-rankings-analysis/scripts/yuntu_report.py)
- [tests/test_yuntu_report.py](/Users/shuzida/Desktop/FDE客户/目标品牌/yuntu-industry-content-rankings-analysis/tests/test_yuntu_report.py)

## 已修复的结构问题

`topMaterialCombination` 过去在结尾多输出了一个 `</div>`，会提前关闭报告内容容器，导致后续章节可能脱离布局网格。该问题已修复，并有测试断言防止 `</article></div></section>` 再次出现。

## 当前报告范围的注意事项

- HTML 和 Markdown 暂时只渲染第一部分；`02` 至 `07` 不进入用户可读报告。
- 为保持既有分析接口兼容，`yuntu-ai-analysis.json` 仍需包含七个原有顶层键，报告渲染器也仍会校验这些字段和证据。它们只是暂不展示，不是被删除。
- `final-report-data.json` 继续完整保留分析 JSON，供审计与后续章节开发使用。
- `scripts/yuntu_report.py` 中仍保留部分旧章节的内部计算和历史样式文本，以保留数据合同和将来逐章恢复的基础；当前模板不会输出它们。

## 验证基线

最近一次完成的验证：

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
python scripts/rpa_connector.py self-test
git diff --check
```

结果：

- 93 项测试通过。
- RPA connector 自检通过。
- 未修改 RPA 相关文件。

## 第二部分开始建议

第二部分尚未定义具体的章节目标、分析口径和最终呈现。新对话应先做以下确认，再开始实现：

1. 明确第二部分的章节名称、分析对象、使用的 RPA 后处理事实、结论维度和指标口径。
2. 确认第二部分是否重新进入单章节报告，或作为 `01` 后的新可读章节恢复到 HTML/Markdown。
3. 为第二部分单独编写设计方案，避免与第一部分设计文档混写。
4. 先补测试，再改 `scripts/yuntu_analysis.py`、`scripts/yuntu_report.py` 和模板；仅在必要时新增纯后处理模块。
5. 继续保持 RPA 边界、证据不进入用户正文、人群标签重叠口径和不使用浏览器工具的约束。
