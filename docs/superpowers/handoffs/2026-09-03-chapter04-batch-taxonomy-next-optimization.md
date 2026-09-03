# 第四部分本批次标准细分类与分布图交接摘要

## 1. 项目与当前执行状态

- 项目目录：`/Users/shuzida/Desktop/FDE客户/小仙炖/yuntu-industry-content-rankings-analysis`
- 当前分支：`codex/yuntu-rpa-parallelism`
- 指定继续执行任务：`codex://threads/01a060b8-16a9-7243-a2ab-a8bec2075f13`
- 该任务标题：`执行04｜高光帧标准分类与本批次分类切换`
- 当前状态：任务仍在执行中；最近一次执行包含分布图渲染提交及后续 tooltip/CSS 可用性收口，工作区有未提交修改，后续对话必须先检查并延续，不要覆盖或回退。
- 未跟踪目录 `.rpa-quarantine-qianchuan/` 属于用户数据，必须保留且不得加入提交。

## 2. 本轮用户需求

用户要求继续优化第四部分：

1. 本批次分类标准需要更细致、尽量多分一些类别，需修改高光分类提示词；
2. 在每个品牌 Tab 的“本批次标准”页签下增加类似八大人群分布的竖向柱状图，用于展示动态分类分布，必要时同步分类结果投影和前端渲染。

当前对话已完成设计文档和执行文档，并已将执行指令发送到指定 Luna 高思考强度任务。

## 3. 已完成的基础能力

### 第一部分

- 事实包已收敛为当前周期、环比周期、同周期全行业三批素材列表及确定性比较/爆款事实；不再把 RPA 详情数据放入第一部分事实包。
- Prompt 已拆分表现对比和爆款素材洞察，并要求全行业对比使用“与全行业大盘对比看”等明确句式。
- 前端已支持“所有指定品牌”、环比/全行业数据面板等交互。

### 第四部分双分类

- 已实现“标准分类 / 本批次标准”双模式。
- 标准分类保留人像、产品、其他三类，默认展示。
- 本批次分类先逐帧图片理解，再整批生成分类规则和分类组。
- 指定品牌 Tab 范围支持所有指定品牌及实际选定品牌；两种模式引用同一批成功高光帧。
- 每个分类组当前要求 3 条共性洞察 + 3 条裂变方向，并做唯一帧覆盖校验。

### 第四部分 Excel

- Excel 已从 `final-report` 预生成链路中剥离，报告目录及 ZIP 不再内置 `highlight-frames.xlsx`。
- 已增加独立按需导出入口；工作簿包含 `高光帧资产`、`标准分类`、`本批次标准` 三个 Sheet。
- 两张图片墙均按品牌一级、画面分类二级分组，图片下保留素材 ID，不显示视频标题；本批次分类不可用时明确降级。

### 第五部分

- 五类指数 AI 二次分析已移除，仅保留确定性曲线和交互。

## 4. 本轮文档

- 设计文档：[`docs/superpowers/specs/2026-09-03-chapter04-batch-taxonomy-granularity-distribution-design.md`](../specs/2026-09-03-chapter04-batch-taxonomy-granularity-distribution-design.md)
- 执行文档：[`docs/superpowers/plans/2026-09-03-chapter04-batch-taxonomy-granularity-distribution.md`](../plans/2026-09-03-chapter04-batch-taxonomy-granularity-distribution.md)
- 文档提交：`d593d1b docs: plan finer batch taxonomy distribution`

设计中的关键约定：

- 成功帧数 `n≤3` 目标 2–3 类，`4≤n≤7` 目标 3–6 类，`n≥8` 目标 6–10 类；类别数不得超过成功帧数；证据不足可少分，但至少形成两个有意义类别，否则批次分类不可用；
- 类别名称必须表达主体、动作、信息机制或构图角色，禁止“其他1/其他2”等占位名称；
- 分布由 Presentation 从品牌范围内的真实 `frame_refs` 确定性计算，不采信模型自行生成的 count/share；
- “本批次标准”面板顶部显示分类分布柱状图，标准分类面板不显示该图；长标签允许横向滚动，并提供帧数、占比和 aria 文本。

## 5. 当前代码/提交线索

与本轮需求直接相关的最新提交：

- `b538be0 feat: render batch taxonomy distribution`
  - 已修改提示词、分析 Schema/校验、Presentation 分布字段、报告渲染、CSS 与测试。
- 当前工作区在该提交之后有未提交修改，涉及：
  - `assets/report/unified-report.css`
  - `assets/report/unified-report.js`
  - `scripts/yuntu_report_sections.py`
  - `tests/test_yuntu_report.py`
  这些修改主要用于动态柱状图 tooltip 的 portal 定位、长标签/溢出处理及测试补充。执行任务结束前应完成测试并由任务统一提交，不要在新对话中擅自丢弃。

其他相关提交：

- `097c5ae 优化高光画面报告与导出体验`：按需 Excel 导出、双图片墙和报告包剥离；
- `d2a7db3 优化批量高光分类洞察`：批次分类 3+3 内容约束；
- `4946c42 重构：移除第五章 AI 指数分析`：移除第五部分指数 AI 文案；
- `966e7f8`、`9f06d09`、`d496dfc`、`ba210a1`、`ff787ad`：第四部分逐帧理解、批次分类和双模式切换基础实现。

## 6. 下一对话执行清单

进入新对话后，优先执行：

1. 读取本交接摘要、设计文档、执行文档及指定任务最新状态；
2. 检查 `git status` 和当前未提交 diff，确认是否仍为 tooltip/CSS 收口；
3. 在指定任务中继续，而不是新建重复实现：完成 TDD、Schema/Presentation/HTML/CSS 回归；
4. 确认真实新报告使用新的日期目录，不覆盖已有报告和 RPA 原始数据；
5. 回归按需 Excel 导出，确认三 Sheet、图片墙分层和报告 ZIP 不含 Excel；
6. 执行 `python -m compileall -q scripts tests`、全量 `unittest`、`git diff --check`，并做新 HTML 与分布图视觉检查；
7. 最终报告需记录：动态类别数量是否达到目标、每个品牌的 `totalFrames/count/share`、柱状图仅在本批次标准页签出现、测试数量、真实 HTML/ZIP/独立 Excel 绝对路径。

## 7. 验收口径

- 同一批次分类必须语义化、细粒度、无重复/空泛类别；每个成功帧恰好出现一次；每组 3+3 洞察保持不变。
- 全品牌与每个品牌 Tab 的分布分母分别是各自范围的成功高光帧总数；桶总数等于 `totalFrames`，占比总和约等于 100%。
- 图表应显示动态类别名称、帧数、占比、可访问 aria-label，并在类别较多或移动端保持可读。
- 标准分类、本批次分类切换、分页、图片预览、Excel 导出和第一/二/五部分不得回归。
