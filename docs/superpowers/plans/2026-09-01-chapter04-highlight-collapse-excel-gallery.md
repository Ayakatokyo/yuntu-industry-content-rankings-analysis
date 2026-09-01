# 第四部分高光帧折叠与 Excel 图片墙 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (or superpowers:subagent-driven-development) to implement this plan task-by-task.

**Goal:** 为第四部分高光帧面板增加卡片折叠，并优化高光帧 Excel 图片显示与分类图片墙。

**Architecture:** 报告渲染器输出每个分类面板的独立折叠控件，浏览器端复用现有折叠行为；导出器以同一份高光帧 rows 事实源生成明细 Sheet 和图片墙 Sheet，使用 openpyxl/Pillow 处理图片尺寸和工作簿内部链接。

**Tech Stack:** Python、HTML/CSS/JavaScript、openpyxl、Pillow、unittest。

**Spec:** `docs/superpowers/specs/2026-09-01-chapter04-highlight-collapse-excel-gallery-design.md`

## Global Constraints

- 折叠只隐藏高光帧卡片网格与分页，共性结论和裂变方向始终可见。
- 图片按原始比例缩放，不裁切、不拉伸。
- 图片墙不展示排名、点击指数等业务指标，不使用 VBA。
- 不覆盖既有报告和原始 RPA 数据。

### Task 1: 高光帧卡片折叠

**Files:**
- Modify: `scripts/yuntu_report_sections.py`
- Modify: `scripts/templates/final-report-template.html`
- Modify: `assets/report/unified-report.css`
- Test: `tests/test_yuntu_report.py`

- [ ] 添加失败测试，断言每个高光分类面板包含 `aria-expanded` 折叠按钮，按钮位于分析文字之后、图片网格之前。
- [ ] 为高光卡片网格和分页包裹稳定的 `id`/`data` 标记，按钮默认展开并关联该区域。
- [ ] 复用现有折叠初始化逻辑：切换按钮只设置卡片区域 `hidden`，不改变共性结论或裂变方向节点。
- [ ] 增加按钮状态样式和窄屏规则，保持键盘可操作。
- [ ] 运行 `python -m unittest tests.test_yuntu_report`，确认新增结构测试通过。
- [ ] 提交：`git add scripts/yuntu_report_sections.py scripts/templates/final-report-template.html assets/report/unified-report.css tests/test_yuntu_report.py && git commit -m "feat: collapse yuntu highlight cards"`

### Task 2: 优化明细 Sheet 图片

**Files:**
- Modify: `scripts/yuntu_highlight_export.py`
- Test: `tests/test_yuntu_highlight_export.py`

- [ ] 添加测试验证图片列存在图片、图片尺寸保持比例、行高覆盖图片高度。
- [ ] 将 openpyxl/Pillow 导出作为统一实现路径，读取图片原始尺寸并按最大宽高等比缩放。
- [ ] 设置图片列宽、数据行高、图片锚点和冻结窗格，避免图片截断或跨行遮挡。
- [ ] 保留现有列和筛选字段，并验证每个可用高光帧均写入一次。
- [ ] 运行 `python -m unittest tests.test_yuntu_highlight_export`。
- [ ] 提交：`git add scripts/yuntu_highlight_export.py tests/test_yuntu_highlight_export.py && git commit -m "feat: improve yuntu highlight image export"`

### Task 3: 新增图片墙 Sheet

**Files:**
- Modify: `scripts/yuntu_highlight_export.py`
- Test: `tests/test_yuntu_highlight_export.py`

- [ ] 添加测试验证工作簿包含 `高光帧图片墙`，四个范围入口及全量/分类图片数量正确。
- [ ] 按 `视觉类型` 将同一 rows 分为全量、人像画面、产品画面、其他画面四个分区。
- [ ] 写入只包含图片和最小识别信息的画廊布局，并设置统一卡片宽高、等比缩放、行高和列宽。
- [ ] 为四个入口写入工作簿内部 `location` 超链接，避免外部链接或 VBA 依赖。
- [ ] 运行导出专项测试并检查 XLSX XML 中图片锚点数与事实源图片数一致。
- [ ] 提交：`git add scripts/yuntu_highlight_export.py tests/test_yuntu_highlight_export.py && git commit -m "feat: add yuntu highlight gallery sheet"`

### Task 4: 真实报告与回归验证

**Files:**
- Create: `RPA数据汇总/yuntu-rankings-analysis-20260810-20260820-top6/final-report-latest-taxonomy-20260901/`（新产物目录）

- [ ] 使用现有真实事实包和已验证分析结果重新渲染 HTML 与 Excel。
- [ ] 检查三类高光面板的折叠 DOM 顺序、默认状态和图片数量。
- [ ] 检查 Excel 两个 Sheet、图片比例/锚点、四个范围入口和 ZIP 打包结果。
- [ ] 运行 `python -m compileall -q scripts tests`。
- [ ] 运行 `python -m unittest discover -s tests -p 'test_*.py'` 并记录完整结果。
- [ ] 使用浏览器检查展开/收起、分类切换和图片预览，保留旧产物不变。
