# 云图技能简化交接摘要

## 当前结论

可以继续下一阶段的保守简化。三阶段变更均已通过自动回归与真实 RPA 验证；近期观察到的前台命令约 30 秒后无输出是异步 RPA 的展示现象，不是任务中止，也不是简化回归。

## 当前基线

- 仓库：`/Users/shuzida/Desktop/FDE客户/小仙炖/yuntu-industry-content-rankings-analysis`
- 分支：`codex/yuntu-presentation-schema`
- 工作区：干净。
- 阶段一提交：`b4bc088 精简云图技能说明并清理旧流程`
  - 删除旧的串行拉取路径、v1 运行状态构造和过时辅助函数。
  - `SKILL.md` 从 248 行收敛到 97 行。
  - 修复自定义日期展示格式与请求格式不一致的校验问题。
- 阶段二提交：`2cfb255 优化批次重试与素材分组处理`
  - 统一 selection group 的 manifest 与详情请求映射。
  - 统一首次采集与重试路径的收尾状态写入。
- 阶段三提交：`029194e refactor: share yuntu detail persistence`
  - 提取 `_persist_detail()`，由首次 `fetch_batch()` 与两类重试共用。
  - 保持首次路径的波次并发、高光提交与分组计数；保持重试路径的串行账本处理。
  - 新增 `_persist_detail()` 契约测试。

设计与实施记录：

- `docs/superpowers/specs/2026-08-20-yuntu-batch-phase3-design.md`
- `docs/superpowers/plans/2026-08-20-yuntu-batch-phase3-implementation.md`

## 不可改变的契约

- 不修改 CLI 参数、`batch-manifest.json`、`run-summary.json`、规范化记录和报告 schema。
- 不修改 RPA function code、超时策略、详情波次并发（2）、高光并发（3）和“本波详情与高光全部终态后再开下一波”的顺序。
- 不改变候选补位、按品牌 × 触点分组、`rejectedMaterials`/`unresolvedMaterials` 语义和已落盘详情恢复。
- 不用程序化兜底生成业务分析。报告必须先 `prepare-analysis`，再基于当前事实包与全部成功 JPEG 生成新的模型分析 JSON，之后 `attest-analysis` 和 `render-report`。

## 最新真实回归

运行目录：

`RPA数据汇总/yuntu-rankings-analysis-last7days-top2-real-run-phase3`

请求参数：

- 行业：食品饮料
- 周期：`LAST_7_DAYS`，未转换为自定义日期
- 品牌：小仙炖、五个女博士、燕之屋
- 榜单：`EXPOSURE_TOP1000`
- 年龄、性别、八大人群：未传，即全选
- 品牌报告范围：每品牌 Top30
- 秒级拆解目标：2；候选池：4

验证证据：

- 自动测试：`python -m pytest -q`，结果 `200 passed, 40 subtests passed`。
- 连接器：`self-test passed`；账号发现成功后使用既有 `shop_id` 运行。
- `status`：`success`；列表 1000 条、筛选上下文校验通过、详情请求 4 条、提交 2 条、持久化 2 条、选中 2 条、拒绝 0、未解析 0、取消候选 2 条。
- 两条详情的高光后处理均成功，生成 11 张 JPEG。
- `prepare-analysis --brand-top-n 30` 成功；新模型分析已完成 provenance 登记；`render-report` 输出 `final-report-data.json.status == complete`。
- 静态检查确认 HTML、Markdown、结构化数据均非空，11 张帧和 2 条深度拆解齐全，未发现空图片路径或 `NaN`。
- 本地 `file://` 报告预览被浏览器策略拒绝，未通过替代浏览器绕过；因此没有本轮 1440x1000/390x844 截图证据。

关键产物：

- `RPA数据汇总/yuntu-rankings-analysis-last7days-top2-real-run-phase3/run-summary.json`
- `RPA数据汇总/yuntu-rankings-analysis-last7days-top2-real-run-phase3/batch-manifest.json`
- `RPA数据汇总/yuntu-rankings-analysis-last7days-top2-real-run-phase3/diagnostic-analysis/yuntu-analysis-data.json`
- `RPA数据汇总/yuntu-rankings-analysis-last7days-top2-real-run-phase3/diagnostic-analysis/yuntu-ai-analysis.json`
- `RPA数据汇总/yuntu-rankings-analysis-last7days-top2-real-run-phase3/final-report/final-report.html`
- `RPA数据汇总/yuntu-rankings-analysis-last7days-top2-real-run-phase3/final-report/final-report.md`

## 新对话的建议入口

以当前 `029194e` 为代码基线，先执行：

```bash
git status --short
python -m pytest -q
```

随后只读审查 `scripts/yuntu_batch.py`、`scripts/rpa_connector.py`、`scripts/yuntu_report.py` 与其测试，优先寻找以下低风险目标：明确未使用的私有函数、完全重复的内部状态转换、或只承载一次的中间变量。每一项都应先写会失败的行为测试，再做最小抽取；不要将异步状态观察、报告 schema 或 RPA 调度混入“简化”阶段。

再次执行真实回归时，显式注入 `ENV_BACKEND_HOST`、`YUCE_AUTHORIZATION`、`YUCE_SESSION_ID`、`YCSESSIONID`；认证值沿用用户当前授权提供的值，但不得写入文档、命令记录、JSON 或报告。
