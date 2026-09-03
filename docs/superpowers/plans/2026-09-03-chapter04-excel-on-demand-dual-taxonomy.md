# 第四部分高光帧按需 Excel 导出与双分类图片墙 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将第四部分 XLSX 从报告包中剥离为独立按需导出，并将图片墙重构为品牌一级、分类二级的“标准分类 / 本批次标准”双 Sheet。

**Architecture:** `render_report()` 只构建可离线阅读的报告与图片资产，不预生成 XLSX。`rpa_connector.py` 增加显式 `export-highlight-workbook` 命令，读取同版本事实包、Presentation 和高光图片资产来创建独立工作簿。导出器将标准及批次分类分别按 `frame_ref` 映射，再由通用图片墙构造器按照品牌 → 分类生成两个 Sheet。

**Tech Stack:** Python、argparse、openpyxl、Pillow、unittest。

**Spec:** `docs/superpowers/specs/2026-09-03-chapter04-excel-on-demand-dual-taxonomy-design.md`

## Global Constraints

- 不得重新获取 RPA、重跑图片理解或重跑批次分类；导出只消费已落盘事实与 Presentation。
- `final-report/` 和它的 ZIP 绝不包含 `highlight-frames.xlsx`。
- 报告目录内不得保留指向已移除 XLSX 的静态下载链接。
- 图片墙一级分类为品牌、二级分类为画面分类；图片卡片仅显示图片和素材 ID。
- 标准分类固定为人像画面、产品画面、其他画面；本批次标准必须使用动态分类或明确不可用原因，不能伪造回退。
- 只在新的独立输出目录生成验证报告和导出文件，不覆盖历史报告或 RPA 原始数据。

---

## 文件职责

- `scripts/yuntu_highlight_export.py`：构建高光帧导出行、读取双分类映射、生成资产明细与两个图片墙 Sheet。
- `scripts/yuntu_report.py`：移除渲染期的 XLSX 写入与报告内静态下载链接。
- `scripts/rpa_connector.py`：提供按需导出 CLI，解析并验证事实包、Presentation、图片根目录和独立输出路径。
- `tests/test_yuntu_highlight_export.py`：验证工作簿布局、Sheet 语义、分类覆盖、图片/ID内容和不可用降级。
- `tests/test_yuntu_report.py`：验证报告目录和 ZIP 都不包含 XLSX，HTML 不渲染失效链接。
- `tests/test_rpa_connector.py`：验证新 CLI 的参数和分派行为。

### Task 1: 用失败测试锁定“报告包不包含 Excel”的契约

**Files:**
- Modify: `tests/test_yuntu_report.py`
- Modify: `scripts/yuntu_report.py`

**Interfaces:**
- Produces: `render_report(...) -> 0` 只输出报告原生文件与资源，不调用 `export_highlight_workbook`。

- [ ] **Step 1: 编写失败测试，渲染临时报告后断言 `final-report/highlight-frames.xlsx` 不存在，ZIP 条目不含该路径。**

```python
with zipfile.ZipFile(root / "final-report.zip") as archive:
    self.assertNotIn("final-report/highlight-frames.xlsx", archive.namelist())
self.assertFalse((root / "final-report" / "highlight-frames.xlsx").exists())
```

- [ ] **Step 2: 编写失败测试，断言报告 HTML 不含 `highlight-export-toolbar`、`highlight-frames.xlsx` 或同目录下载锚点。**
- [ ] **Step 3: 运行 `python -m unittest tests.test_yuntu_report.YuntuReportTests.test_render_report_creates_sibling_zip_with_final_report_directory -v`，确认新断言在旧实现失败。**
- [ ] **Step 4: 删除 `yuntu_report.py` 对 `export_highlight_workbook` 的导入与渲染期调用；停止传入 `highlight_export_href`，并删除只服务该链接的 HTML/CSS 生成分支。高光图片复制与 JSON 写入保持不变。**
- [ ] **Step 5: 运行 `python -m unittest tests.test_yuntu_report -v`，确认报告/ZIP 契约及其他渲染测试通过。**
- [ ] **Step 6: 提交：`git add scripts/yuntu_report.py tests/test_yuntu_report.py && git commit -m "refactor: remove excel from report package"`。**

### Task 2: 将导出行扩展为双分类可追溯数据

**Files:**
- Modify: `scripts/yuntu_highlight_export.py`
- Modify: `tests/test_yuntu_highlight_export.py`

**Interfaces:**
- Consumes: `fact_pack`, `presentation["chapters"]["chapter04"]`。
- Produces: `build_highlight_export_rows(fact_pack, chapter04) -> list[OrderedDict]`，每行至少含 `品牌`、`视觉类型`、`本批次标准分类`、`素材 ID`、`frame_ref` 和本地图片路径。

- [ ] **Step 1: 添加失败测试，构造同一素材下三张可用高光帧与 `classificationModes`，断言行分别拥有固定分类与动态批次分类。**
- [ ] **Step 2: 添加失败测试，断言批次分类不可用时每行的“本批次标准分类”为“本批次标准不可用”，并保留不可用原因供图片墙使用。**
- [ ] **Step 3: 运行 `python -m unittest tests.test_yuntu_highlight_export.HighlightExportTests -v`，确认新断言失败。**
- [ ] **Step 4: 抽取按 `frameRef` 收集分类标签的 helper。它读取 all-brand scope 的 `classificationModes`；标准分类兼容旧 `categories` 结构，批次分类只在 `available == true` 时映射。**
- [ ] **Step 5: 在 `build_highlight_export_rows` 中写入“本批次标准分类”和内部批次状态/原因；保持既有字段兼容，并按品牌、标准分类、素材排名、秒数、峰值排序。**
- [ ] **Step 6: 运行 `python -m unittest tests.test_yuntu_highlight_export -v`。**
- [ ] **Step 7: 提交：`git add scripts/yuntu_highlight_export.py tests/test_yuntu_highlight_export.py && git commit -m "feat: map dual highlight taxonomies for export"`。**

### Task 3: 重建明细与双分类图片墙工作簿

**Files:**
- Modify: `scripts/yuntu_highlight_export.py`
- Modify: `tests/test_yuntu_highlight_export.py`

**Interfaces:**
- Consumes: Task 2 的导出行和本地 `__image_path`。
- Produces: `export_highlight_workbook(...) -> Path | None`，Sheet 顺序固定为 `高光帧资产`、`标准分类`、`本批次标准`。

- [ ] **Step 1: 添加失败测试，断言资产 Sheet 包含“本批次标准分类”列，且表头、筛选范围和图片锚点与实际列一致。**
- [ ] **Step 2: 添加失败测试，断言工作簿 Sheet 顺序精确为 `['高光帧资产', '标准分类', '本批次标准']`。**
- [ ] **Step 3: 添加失败测试，检查两个图片墙的文本：含品牌分区、固定/动态二级分类、素材 ID；不含素材标题；每个可用帧仅在各自 Sheet 中出现一次。**
- [ ] **Step 4: 添加失败测试，覆盖本批次分类不可用：`本批次标准` Sheet 存在且展示不可用原因，且没有把标准分类图片复制进去。**
- [ ] **Step 5: 实现通用 `_build_gallery_sheet(workbook, title, rows, category_key, category_order, unavailable_reason='')`。先生成品牌导航与品牌标题，再为每个品牌生成分类标题、四列图片区和仅带“素材 ID：...”的标识行。移除素材/视频标题行。**
- [ ] **Step 6: 将旧 `高光帧图片墙` 改为调用通用构造器生成 `标准分类`；从批次分类标签/顺序生成 `本批次标准`。更新 `高光帧资产` 的列和 Excel 表范围。**
- [ ] **Step 7: 运行 `python -m unittest tests.test_yuntu_highlight_export -v`，并用 `openpyxl.load_workbook()` 检查三个 Sheet、图片锚点和表头。**
- [ ] **Step 8: 对本轮生成的工作簿逐 Sheet 做一次视觉验证，确认图片未拉伸、ID 未裁切、品牌/分类标题可读。**
- [ ] **Step 9: 提交：`git add scripts/yuntu_highlight_export.py tests/test_yuntu_highlight_export.py && git commit -m "feat: export dual taxonomy highlight galleries"`。**

### Task 4: 新增独立按需导出 CLI

**Files:**
- Modify: `scripts/rpa_connector.py`
- Modify: `tests/test_rpa_connector.py`
- Modify: `tests/test_yuntu_highlight_export.py`

**Interfaces:**
- Produces: `python scripts/rpa_connector.py export-highlight-workbook --fact-pack-json <facts.json> --presentation-json <presentation-report.json> --asset-root <root> --output <exports/highlight-frames.xlsx>`。
- Exit codes: `0` 表示已生成非空工作簿；输入不可读、无可导出帧或写入失败时为非零。

- [ ] **Step 1: 添加失败测试，mock `export_highlight_workbook` 并断言 CLI 将四个参数正确传递，返回成功状态且打印实际输出路径。**
- [ ] **Step 2: 添加失败测试，断言缺少事实包/Presentation、无效 JSON 和导出器返回 `None` 时抛出可读的 `RpaConnectorError`。**
- [ ] **Step 3: 运行 `python -m unittest tests.test_rpa_connector -v`，确认新 CLI 测试失败。**
- [ ] **Step 4: 在 parser 中注册 `export-highlight-workbook` 及四个必填参数；在 `main()` 中加载 JSON、提取 `presentation['chapters']['chapter04']`、调用导出器并打印已生成路径。输出路径不得解析为 `final-report/highlight-frames.xlsx`；若目标在报告目录内，拒绝并提示使用同批次 `exports/` 目录。**
- [ ] **Step 5: 用 Task 3 的临时事实包、Presentation 和图片资源进行 CLI 端到端测试；确认产物独立于 `final-report` 目录。**
- [ ] **Step 6: 运行 `python -m unittest tests.test_rpa_connector tests.test_yuntu_highlight_export -v`。**
- [ ] **Step 7: 提交：`git add scripts/rpa_connector.py tests/test_rpa_connector.py tests/test_yuntu_highlight_export.py && git commit -m "feat: add on-demand highlight workbook export"`。**

### Task 5: 真实报告回归与交付校验

**Files:**
- Create: `RPA数据汇总/<当前批次>/final-report-chapter04-on-demand-excel-20260903/`
- Create: `RPA数据汇总/<当前批次>/exports/highlight-frames-chapter04-20260903.xlsx`

- [ ] **Step 1: 使用已有、已实现双分类的同一批真实事实包和 AI 分析/provenance，生成一个日期命名的新报告目录；不得覆盖现有 `final-report`。**
- [ ] **Step 2: 检查新目录及其 ZIP：存在 HTML、Markdown、两个 JSON 和高光图片资产；不存在 `highlight-frames.xlsx`；HTML 不含报告内 XLSX 链接。**
- [ ] **Step 3: 使用新 CLI 从该报告的同版本事实包、`presentation-report.json` 和高光资源生成 `exports/` 下的独立工作簿。**
- [ ] **Step 4: 打开工作簿验证 Sheet 顺序、资产 Sheet 的双分类列、两张图片墙的品牌 → 分类层级、仅素材 ID 标识、图片数量和本批次不可用降级（如该真实批次适用）。**
- [ ] **Step 5: 运行 `python -m compileall -q scripts tests`、`python -m unittest discover -s tests -p 'test_*.py'` 和 `git diff --check`。**
- [ ] **Step 6: 确认没有暂存或提交 `.rpa-quarantine-qianchuan/` 等无关用户文件，仅提交本方案涉及的源代码、测试与文档。**
- [ ] **Step 7: 提交最终实现并记录新报告及独立 Excel 的绝对路径。**
