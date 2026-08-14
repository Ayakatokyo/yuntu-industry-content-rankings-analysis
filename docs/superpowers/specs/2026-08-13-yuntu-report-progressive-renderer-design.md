# 云图报告渐进式渲染器拆分设计

## 目标

在不改变报告最终 HTML、视觉样式、浏览器交互和数据口径的前提下，先将 `scripts/yuntu_report.py` 中 `_render_html()` 的五个业务章节拆成可定位的内部渲染函数，为后续资源隔离建立安全边界。

## 第一阶段范围

仅修改 `scripts/yuntu_report.py` 与对应测试。以下内容冻结不动：

- `scripts/templates/final-report-template.html`
- `assets/report/unified-report.css`
- `assets/report/unified-report.js`
- 分析 JSON、Fact Pack、高光帧和输出目录契约
- 报告中的 class、`data-*` 属性、章节顺序、文案和 CSS 拼接顺序

## 目标结构

保留 `_render_html()` 作为编排入口，提取五个纯 Python 内部渲染函数：

1. `render_top_material_combination(...)`
2. `render_audience_insights(...)`
3. `render_script_insights(...)`
4. `render_highlight_insights(...)`
5. `render_material_deep_dive(...)`

函数接收当前 `_render_html()` 已准备好的局部数据和闭包工具，返回与现有变量完全相同的 HTML 片段。第一阶段允许函数位于同一模块内，不新增跨文件抽象，避免改变导入和运行时行为。

## 等价性门禁

在拆分前使用当前 `main` 生成固定 fixture 和用户指定真实数据报告，保存 HTML SHA-256。每次提取一个章节后：

- `python -m unittest tests.test_yuntu_report -v` 全部通过；
- 同一输入生成的 `final-report.html` SHA-256 与拆分前完全一致；
- `git diff --check` 通过；
- 浏览器仅观察桌面端成品，确认五章存在、无横向溢出，且人群左右布局和单素材 grid 布局未变。

若字节级结果变化，立即停止该步并回退该步，不继续拆下一章。

## 明确不做

本阶段不删除 Python 内联 CSS，不移动模板脚本，不合并 `unified-report.css/js`，不改分页状态、不新增资源 manifest，也不做移动端/平板验收。
