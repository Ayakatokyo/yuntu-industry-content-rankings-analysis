# 云图行业内容榜单报告执行日志摘要

## 日志口径

这是对本次执行及其直接相关历史对话的摘要，不是完整聊天转储。原始历史提取结果保留在 `work/codex-review-20260909/source.json`，历史复盘覆盖索引保留在 `docs/reviews/2026-09-08-yuntu-landed-analysis-coverage.json`。摘要已删除授权值、Cookie、token 和完整请求头。

## 本次执行时间线

| 阶段 | 事件 | 结果/证据 |
|---|---|---|
| 采集初次尝试 | 三组列表请求使用旧运行时地址 | HTTP 401，未将凭证写入产物 |
| 授权恢复 | 用户提供新的运行时环境配置 | 上下文确认成功，发现账号与 shop 上下文 |
| 列表采集 | 当前周期、上一周期、同周期全行业 | 三组均 1000 条，口径校验通过 |
| 详情采集 | 20 个候选，异步详情任务分批提交 | 10/10 成功，0 失败，0 拒绝，0 未解析 |
| 高光资源 | 对 10 个成功详情素材生成本地高光帧 | 50 张高光帧落盘 |
| 事实准备 | 生成 5 个分析输入单元 | 榜单、人群营销、脚本、视觉高光、单素材深度分析输入均存在 |
| AI 分析 | 生成 `yuntu-ai-analysis.json` | Schema 结构可读，但存在模板复用、卖点为空、逐帧不具体等问题 |
| 门禁恢复 | 处理零样本、禁词、状态枚举、分类 rule 等错误 | 最终通过，但部分修复是兼容性兜底，未解决语义质量 |
| 渲染 | 生成 HTML、Markdown、Excel、JSON | 文件均存在，报告可打开 |
| 交付验收 | ZIP 完整性与工作区检查 | `unzip -t`、`git diff --check` 通过；不代表 AI 分析正确 |

## 当前批次关键输出

- `run-summary.json`：三组列表均为 `success`，详情 postprocess 成功数为 10。
- `batch-manifest.json`：记录详情任务组、业务参数、提交/完成时间和归一化产物路径。
- `normalized/list-records*.json`：当前、上一周期、全行业榜单归一化记录。
- `normalized/detail-records/*.json`：10 个成功详情素材的归一化记录。
- `diagnostic-analysis/analysis-units/*.json`：AI 分析输入事实单元。
- `diagnostic-analysis/yuntu-analysis-prompt.md`：当前提示词及事实域约束。
- `diagnostic-analysis/yuntu-ai-analysis.json`：本次 AI 二次分析结果。
- `diagnostic-analysis/yuntu-ai-analysis.provenance.json`：分析 JSON、事实包和提示词的哈希绑定。
- `final-report/final-report.html`：用户批注对应的最终报告页面。
- `final-report/highlight-frames.xlsx`：高光帧导出表。
- `final-report.zip`：最终交付包。

## 已确认的异常日志

1. 高光帧图片墙曾遇到部分临时副本 JPEG 无法识别的日志；该日志来自验证临时副本路径，不能与当前 50 张已落盘高光帧的 AI 语义质量混为一谈。后续应在事实准备阶段明确 `available` 和 `failure_reason`，并让不可读图片从“成功帧覆盖门禁”中剔除。
2. `missing processed brand facts for 孕味食足`：零样本品牌事实没有正式生成，渲染器后来跳过 `sampleCount=0` scope。
3. `script insight 1.summary contains unsupported claim: 行业普遍`：禁词正则误读了否定语境，后来增加有限否定范围处理。
4. `script insight 2.summary contains unsupported claim: 导致`：模型用了因果禁词，执行时改写了输出文本；后续应从提示词和语义校验上约束为相关性表达。
5. `frameUnderstanding status is invalid`：曾输出 `available`，Schema 只接受 `complete` 或 `unavailable`，后改为 `complete`。
6. `batchClassification complete requires rule`：批次分类缺少顶层 `rule`，后补齐。

## AI 输出审计摘要

| 检查项 | 结果 |
|---|---|
| Chapter 02 非空 scope | 7 个 |
| Chapter 02 人群摘要唯一文本数 | 1 |
| Chapter 02 营销摘要唯一文本数 | 1 |
| 有完整脚本文案素材 | 4/10 |
| 关键词事实候选 | 存在，含频次、素材 ID 和证据引用 |
| sellingPoints | 0 条 |
| 高光帧理解 | 50 条结构记录 |
| 高光帧观察 | 50 条，29 条唯一文本 |
| 标准分类 | 2 组，未显式保留 other 组 |
| 本批次分类 | 2 组，未达到 50 帧证据允许时的细分目标 |
| 分类组共性/裂变字段 | 数量满足，但大量模板复用 |
| 最终文件 | HTML/Markdown/JSON/Excel/ZIP 均存在 |

## 历史执行链的相关证据

此前已落地的复盘表明，同一项目曾出现三条连续问题链：

- CSV 与 normalized 中存在 `secondTrend` 和部分脚本文案，但事实包曾错误标记为未返回；
- 新事实包与旧 AI JSON 不匹配时，`attest-analysis` 正确拒绝了高光帧未完整分类的 JSON；
- 禁词规则曾错误拒绝明确的“不能外推行业普遍”否定句，同时对帧覆盖不足的拒绝是正确的。

这说明项目风险不是单一的“门禁过严”，而是事实映射、AI 取证、旧分析复用、门禁语义和恢复流程共同作用。相关历史复盘见 `docs/reviews/2026-09-08-yuntu-landed-analysis-review.md`。

## 执行任务交接摘要

新任务必须读取：

1. `docs/reviews/2026-09-09-yuntu-report-execution-postmortem.md`
2. `docs/reviews/2026-09-09-yuntu-report-execution-log-summary.md`

建议第一步：只读检查当前分支、未提交 diff、上述批次 manifest/事实包/AI JSON、提示词和 CSS/渲染函数；不要重新采集，也不要直接修改最终 HTML。

建议实施顺序：

1. 先为零样本、脚本可用性、图片可读性和逐帧引用建立正式事实状态；
2. 再改提示词/分析执行与 AI JSON 语义门禁；
3. 再修复 Tab、对比卡片和词云布局；
4. 最后用当前批次做离线回放、报告生成和 ZIP 验收。

授权范围：允许在当前仓库内修复技能、增加测试并生成离线验证产物；不允许提交、合并、推送或重新调用 RPA，除非用户另行授权。
