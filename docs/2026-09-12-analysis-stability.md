# 云图分析链路稳定性优化与验证

本次针对事实包 → 当前模型撰写分析 → attest → 前端渲染的链路修复。依据为用户提供的复盘、粘贴补充和真实执行任务 `01a0906a-ee9d-7571-a7a2-902a97a8e4bd` 的日志。日志中的 prepare、四批看图、临时脚本写出 JSON、逐次 attest 错误及 render 调用均已核对。没有重新采集、调用外部模型或覆盖历史报告。

## 已落地的变化

| 复盘中暴露的问题 | 本次处理 |
|---|---|
| 校验从空的 `chapter02AiFacts` 报告投影读范围，临时改读图表范围才通过 | `yuntu_analysis_bundle.py` 从 manifest 验证并读取五包；第二章恢复正式 AI 范围，第五章恢复本素材 `script/evidenceIndex`。attest 与 render 共用该加载器；空投影直接调用校验器时提示缺少 canonical 事实，不能借用图表范围。 |
| 零样本品牌在无事实的前置检查中被当成缺少引用 | 去掉无事实的重复校验，按本 scope 的实际可用性检查；零样本保留空引用及数据不足。scope 顺序必须与事实完全一致。 |
| 模型以临时 Python 常量拼装整份业务 JSON | 新增 `begin-analysis`、`check-analysis`、`assemble-analysis`。模型直接写四份章节草稿与逐素材草稿，固定程序只做校验、保存原始快照和无损合并。 |
| 引用、字数、帧集合直到 attest 才发现有误 | 每份草稿配 `.task.json`，提前提供字段 Schema、scope 素材、当前素材脚本引用、成功帧全集、可用性及脚本文案长度。可单份检查或集中检查，失败返回非零并保存 `validation.json`。 |
| 多类错误串行暴露，错误又迫使模型阅读脚本排障 | 独立草稿错误合并报告；帧覆盖列明重复、缺失和额外引用，长度错误给出实际长度，禁用声明提示命中词。Schema 错误不再重复输出整段脚本引用清单。 |
| Schema 要求批次分类至少两个组，与 unavailable 的空数组规则冲突 | 改为根据 status 条件校验；complete 至少两组，unavailable 为空。新版第五章 Schema 明确要求 `scriptAnalysis`。 |
| provenance 只绑定最终 JSON，无法核对原始模型草稿 | 新契约强制 assembly 收据，逐份保存按 SHA256 命名的原始草稿；校验最终 JSON 是这些快照的无损合并。修改工作草稿不影响此前快照，修改快照或最终文件会失效。 |
| 事实、Schema、报告数据或本地资产变化后仍可能混用 | 新 manifest 绑定提示词、Schema、五包、报告数据及成功 JPEG/MP4；入口检查哈希，JPEG 还验证可解码。恢复时拒绝改变过的绑定；render 拒绝不同的显式事实或资产根目录。 |
| 视频事实明确不可用，渲染却可能捡到后来出现的 MP4 | 只有缺少 `localVideo` 字段的旧事实可兼容查找视频；显式 unavailable 保持原事实状态。 |

新流程：

```text
prepare-analysis → begin-analysis
  → 模型直接撰写章节／单素材 JSON，并实际看图
  → check-analysis（按草稿定位错误）
  → assemble-analysis（原始草稿快照＋无损合并收据）
  → attest-analysis → render-report
```

入口和提示词已更新；详细操作见 `references/analysis-drafts.md`。运行环境需安装 `requirements.txt`，其中新增 `jsonschema>=4.18,<5`。`single_model_call` 仍是历史契约标识，不代表一次模型 API 调用；没有引入新的模型调用服务。

## 验证结果

- 新增 15 项回归全部通过，覆盖规范事实恢复、零样本、scope 顺序、图表范围隔离、草稿无损组装与修改检测、prompt/schema/report 哈希、断点恢复、重复 JSON 键、成功图片检查、不可用视频、分类覆盖诊断、Schema 与 unavailable 一致性、短诊断及缺少 assembly 的拒绝行为。
- 全量 `python -m unittest discover -s tests -q`：370 项，368 通过、1 跳过、1 失败。唯一失败 `test_shared_style_defines_text_card_and_control_contract` 与修改前 355 项基线相同：断言 CSS 必须含 `minmax(112px, 1fr)`，当前 CSS 不含。此次未修改 CSS，也未修改该测试。
- 连接器 `self-test`、Python 编译、JavaScript 语法和 `git diff --check` 通过。
- 系统 `skill-creator` 的 quick_validate 在修改前后均因既有 `argument_hint` 元数据被拒绝；项目自己的 20 项 Skill 契约测试通过。保留现有技能名称及平台元数据，没有为通过通用检查而改变平台接口。

真实批次离线回放使用 `20260911-food-beverage-0901-0907-exposure-top1000` 的已有最终分析 JSON，作为回归输入拆成 14 份草稿。没有把这次回放称为新模型分析。全部草稿经一次完整检查通过后，由正式 CLI 完成组装、attest 和渲染；组装前后的分析对象完全相等。

产物包含 37 张 JPEG、8 个 MP4、3 个工作表的 Excel、HTML、Markdown、presentation JSON、报告数据及 ZIP。ZIP 内共 50 项，均在 `final-report/` 下；HTML 本地资源和锚点检查无缺失。原批次 138 个文件逐一核对 SHA256，全部未变。

另在回放草稿中同时注入四种复盘错误：scope 越界、重复帧分类、跨素材脚本引用、过短脚本结论。一次 `check-analysis` 同时定位四份错误草稿；恢复原始字节后完整检查再次通过。提示词改动后，旧草稿目录恢复被拒绝。

执行证据均在 `work/stability-review/`：

- `baseline-tests.log`、`final-tests.log`：修改前后全量测试。
- `*-red-tests.log`：新增行为修复前失败记录。
- `preexisting-report.patch`：开始前工作区的临时校验器补丁。
- `skill-validator.json`：通用 Skill 检查的前后结果。
- `replay/injected-errors.json`：四类错误的一次预检结果。
- `replay/verification.json`：产物数量、资源校验及 SHA256。
- `replay/diagnostic-analysis/replayed-analysis.*`：回放 JSON、assembly、provenance 与原始草稿快照。
- `replay/final-report/`、`replay/final-report.zip`：独立回放产物。

## 证据边界与保留问题

本次证明了事实来源一致、草稿可恢复、结构错误提前定位和现有报告可离线复现，尚未用多次全新模型分析测量首次通过率。`model_generated`、generator 和已看帧清单仍是执行者声明；收据能证明字节及合并关系，不能证明模型身份、实际看图或业务结论正确。独立草稿错误会汇总，同一段内的语义规则仍可能先报告最先命中的一项。

此次没有修复采集端 CDN 403、下载异常详情丢失或 batch 的后处理 success 统计；它们属于事实准备上游问题。两个失败素材仍保持缺失状态，未伪装成成功。本次修复保证已声明成功的资产损坏或缺失时不能继续进入新分析链路。

所有改动留在当前工作区，未提交或推送 Git。历史 `scripts/build_current_ai_analysis.py` 保留作执行证据，新流程不引用或执行它；原先的图表范围回退补丁已由规范事实加载替代。
