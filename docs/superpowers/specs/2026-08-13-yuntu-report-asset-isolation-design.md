# 云图报告资源隔离设计

## 目标

在不改变云图报告的数据口径、章节顺序、已有 DOM 语义和用户可见交互的前提下，将报告渲染职责稳定拆分为数据与片段渲染、模板骨架、统一样式和统一交互四层。最终 HTML 只内联一份 CSS 和一份 JavaScript，避免模板、Python 与统一资产重复控制同一组件。

## 范围

本次处理 `scripts/yuntu_report.py`、`scripts/templates/final-report-template.html`、`assets/report/unified-report.css`、`assets/report/unified-report.js` 和对应测试。报告的业务分析、事实包 schema、章节内容、素材高光分类、页面文案和视觉设计保持云图现状，不迁移千川的页面结构或业务规则。

## 现状与根因

当前渲染器把大段 CSS 作为 `$style` 由 Python 生成，同时又把 `unified-report.css` 注入 `$unified_style`。模板还包含品牌 Tab、人群看板、高光分页、灯箱、折叠和素材跳转等交互脚本；`unified-report.js` 再次注册高光分页和灯箱事件。高光分页分别使用 `data-highlight-current-page` 和 `data-unified-highlight-page`，两套事件处理器竞争相同 DOM。

这种双样式源、双交互所有者会使选择器优先级、初始化顺序和事件捕获顺序影响最终报告行为，导致局部修改难以稳定生效。

## 目标架构

| 层级 | 文件 | 职责 | 禁止承担的职责 |
| --- | --- | --- | --- |
| 数据与渲染 | `scripts/yuntu_report.py` | 校验分析数据、生成云图业务 HTML 片段、读取资产、内联最终 HTML、输出产物 | 生成 CSS、定义浏览器事件 |
| 页面骨架 | `scripts/templates/final-report-template.html` | 章节顺序、语义容器、数据片段和唯一资源占位符 | 视觉规则、交互初始化 |
| 视觉样式 | `assets/report/unified-report.css` | 云图现有颜色、排版、布局、响应式和状态视觉 | 数据加工、事件绑定 |
| 浏览器交互 | `assets/report/unified-report.js` | Tab、折叠、人群钻取/图表、高光分页、灯箱、素材跳转 | 改写业务数据或生成业务结论 |

最终报告模板只保留 `$report_style` 和 `$report_script` 两个资产占位符。渲染前必须校验每个占位符在模板中恰好出现一次；渲染后不得保留未解析占位符或模板预览外链。

## DOM 与交互契约

云图现有 `data-*` 属性和 class 是迁移边界，不改变其语义。统一脚本成为下列行为的唯一所有者：

| 组件 | 入口属性 | 唯一状态/所有者 |
| --- | --- | --- |
| 品牌对比 | `data-brand-tab`、`data-brand-target` | 统一脚本通过 `aria-selected` 和 `hidden` 切换 |
| 人群饼图与钻取 | `data-audience-*` | 统一脚本读取渲染器提供的事实记录并更新看板 |
| 人群汇总折叠 | `data-collapsible-toggle` | 统一脚本通过 `aria-expanded` 和 `hidden` 切换 |
| 高光分类 | `data-highlight-category-tab`、`data-highlight-category-target` | 统一脚本通过 `aria-selected` 和 `hidden` 切换 |
| 高光分页 | `data-highlight-pagination`、`data-highlight-frame-card` | 统一脚本仅使用 `data-highlight-current-page` |
| 高光灯箱 | `data-highlight-src` | 统一脚本创建并管理唯一灯箱 |
| 单素材深度分析 | `data-material-tab`、`data-material-target`、`data-jump-material` | 统一脚本切换素材并定位章节 |

分页初始化、分类切换和分页点击都由同一模块调用同一个分页函数；禁止重新引入 `data-unified-highlight-page` 或第二个监听器。最终 HTML 也不再输出模板灯箱节点，因为灯箱由统一脚本按需创建。

## 样式迁移

将 `_render_html` 当前拼接的完整 CSS 迁入 `unified-report.css`，保留云图现有规则顺序与选择器，以维持当前视觉结果。合并时移除与既有统一 CSS 重复的规则，并为迁入的云图规则加 `body.unified-yuntu` 或 `.unified-yuntu` 作用域。`yuntu_report.py` 不再传递 `$style` 或读取第二份样式内容。

CSS 内的交互状态规则只消费上述稳定属性，例如 `[hidden]`、`[aria-selected="true"]` 和 `[aria-expanded="true"]`，不依赖模板内联脚本产生的专用状态属性。

## 验证策略

先以测试锁定迁移边界，再修改生产代码：

1. 模板契约：只有骨架和资源占位符，无内联可执行脚本、无 `$style`/`$unified_style` 双入口。
2. 渲染契约：最终 HTML 内联 CSS/JS 各一份、无未解析占位符、无模板预览链接。
3. 所有权契约：最终 HTML 仅含一次高光分页初始化，不含 `normalizeYuntuHighlightPagination`、`data-unified-highlight-page` 或模板分页函数。
4. 行为契约：在 DOM 测试环境中验证高光分类切换、分页、素材跳转、折叠和灯箱的唯一状态变化。
5. 现有报告数据契约：全量 Python 测试和真实输入报告生成继续通过。
6. 成品验收：生成报告后在浏览器以 1440x1000 与 390x844 检查页面没有横向溢出、异常空白或控制器失效；浏览器仅用于观察与验证。

## 风险与回退

该迁移不改变生成器的业务 HTML 字符串，因此可通过结构测试检测非预期 DOM 变动。每完成一个职责迁移即运行目标测试；任何视觉差异都先确认源 CSS、内联成品和浏览器加载文件是否一致。修改将在用户指定的当前 `main` 工作目录进行，不创建或切换 Git 分支；不会覆盖当前未跟踪的两份复盘文档。
