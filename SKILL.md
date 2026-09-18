---
name: 云图行业素材全景分析
description: 适用于通过固定预策 RPA 连接器获取行业内容榜单与秒级详情，或复用已落盘的云图数据、高光帧和视频继续分析并生成全景内容策略报告的场景。
argument_hint: 输入行业、时间范围、榜单类型、品牌和人群筛选、素材列表本地筛选及详情素材数，生成云图行业素材全景分析报告。
metadata:
  pre_input: |
    请采集云图行业素材及相关数据。
    云图诊断授权账号：__field:rpa_shop__（必填）
    行业是 __field:industry__（必填，云图行业筛选）
    分析周期是 __field:date_range__
    截取方式是 __field:ranking_metric__
    品牌范围是 __field:brand_scope__；指定品牌是 __field:brands__（品牌数量范围3-10个）
    年龄筛选：__field:ages__；性别筛选：__field:genders__；八大人群筛选：__field:crowd_groups__（可选）
    素材筛选与排序：__field:material_list__ （可选，例如按“曝光量”>=1000000且“视频标题”包含“燕窝”，再按“互动率”降序）
    详情素材数 __field:detail_top_n__（包含秒级拆解和内容公式数据，默认10）
---

# 云图行业素材全景分析

统一精简分析，不设详细档位或切换参数。建议总览100–150字、经营/人群维度40–70字、两类脚本洞察每条50–80字、每张唯一画面观察25–60字、单素材核心结论80–120字；每个分类组默认一条共性判断和一个可测试方向。字数是表达预算，不是必须达到的门槛；保留事实、范围、引用及必要字段，不补字、不重复解释。

## 已落盘数据续跑

用户要求“用已落盘数据继续分析/重新生成报告”时直接进入本节；采集参数从原批次 manifest 读取，不重新索要账号凭证或启动 `fetch`。只有本地数据不足且用户明确要求补采时，才进入采集流程。

- 先定位用户指定批次及 `batch-manifest.json`，核对实际周期、筛选、选中素材 ID、规范化文件路径和本地资产。用户只说“最新”时核对清单内容和对话来源，不按目录名、mtime 或旧报告文件名猜测；有无法消除的多个候选时再询问。记录源清单/输入文件 SHA-256 和本轮独立输出路径。
- 先判断重分析还是仅重渲染。用户要求完整后续分析时，生成新 AI JSON，不把历史 JSON 改名或补字段冒充新分析。仅重渲染才考虑复用已通过校验、且事实包/提示词绑定未变化的历史分析。
- 保留源 CSV、normalized、旧 AI JSON、报告和 provenance。`prepare-analysis` 会检查高光帧并可能下载视频、截帧和回写资产清单；纯本地续跑前先检查资产完整性，并在独立批次副本运行，保持相对路径。本地续跑使用 `prepare-analysis --local-only`，已齐备资产直接复用；缺失资产若用户未授权补取，先报告具体缺口，不让准备步骤隐式联网。
- 区分 `source_empty`（源字段确实为空）、`parse_failed`（解码失败）和映射遗漏。仅在数据诊断阶段允许只读追溯 raw CSV → normalized → 章节事实包；业务分析仍只使用规范化后的章节事实。发现 CSV/normalized 有趋势而事实包称 `trend_not_returned`，先修复本地规范化或事实映射，不能靠提示词补造数据。字段存在不等于正文非空，创意标签不能代替完整脚本。
- 新事实包生成后核对素材集合、五类趋势点、脚本覆盖和成功帧集合。帧从旧数量变为新数量、脚本新增、素材范围或提示词改变时，旧分析需重新生成并重新 attest；不得删掉新增帧来迎合旧 JSON。阶段分别记为事实准备、模型分析、校验、渲染、交付，不用采集 `success` 代替分析完成。

## 先确认参数

云图没有独立的 API 报表店铺阶段。先选择 `rpa_shop`：榜单和素材详情均通过 `RPA_JULIANG_YT_ACCOUNT_PASSWORD` 获取，`rpa_shop.extra.shop_id` 是这两个步骤唯一使用的授权账号 ID，必须原样同时传入两步的 `--shop-id`；不得再手填、猜测或替换账号。执行每个阶段前查询当前授权列表：所选账号不在列表时以 `rpa_shop_not_authorized` 停止，不提交后续 RPA 任务，也不改用其他账号。

- 行业必填；指定品牌可选，填写时给 3–10 个品牌并使用 `SPECIFIED_BRANDS`。实时连接器的 `brands` 是 STRING：优先用英文逗号分隔品牌名；本地上下文校验也兼容斜杠分隔和 JSON 数组字符串，归一化后逐品牌比对页面实际 tag。连接器请求和 `run-summary.json` 保留该 STRING；写入 `batch-manifest.json.filters.brands` 后必须是规范化的品牌列表，供分析、草稿和报告逐品牌消费。年龄、性别、八大人群空缺时不传筛选参数（全选）。截取方式为曝光量TOP1000、CTRTOP1000、互动率TOP1000或完播率TOP1000。
- 秒级拆解素材数默认 10，由批参数 JSON 的 `target_top_n` 控制 RPA 详情实际拉取并做秒级拆解的目标素材数；第一部分品牌分析直接使用提取到的行业 TOP1000，并在其中按品牌匹配全部素材。启动前复述映射；未完成映射核对时不得启动 RPA 长任务。
- 榜单和素材详情必须使用同一分析周期：近7天=`LAST_7_DAYS`、近30天=`LAST_30_DAYS`，不换算为自定义日期，未填默认近七天。自定义日期两端均为 `CUSTOM` 且闭区间；云图界面日期只作展示核对，上一等长周期按实际日期前移，全行业固定 `ALL_INDUSTRY`。

## 采集

先读 `references/platforms/juliang-yt.md`、`references/connectors/juliang-yt/rpa_conn_juliang_yt_industry_content_rankings_list.md` 和 `references/connectors/juliang-yt/rpa_conn_juliang_yt_industry_content_rankings_details.md`。榜单与详情分别由 `scripts/rpa_dynamic_client.py` 和 `scripts/rpa_dynamic_detail_client.py` 固化唯一 connector code：`rpa.conn.juliang.yt.industry.content.rankings.list` 与 `rpa.conn.juliang.yt.industry.content.rankings.details`。平台、入参契约和出参说明每次都从 `/dcConnector/v3/listByConnectorCode` 实时读取。不得把详情返回的 `id` 当 connector code，不得固化 platform、复制 JSON Schema 或回退到逐字段 CLI。

仅使用平台运行时注入的 `ENV_BACKEND_HOST`、`YUCE_AUTHORIZATION`、`YUCE_SESSION_ID`（或 `YCSESSIONID`），凭证只留在环境变量。MCP 知识库地址不是 `ENV_BACKEND_HOST`；404 先核对网关基路径，504 视为网关超时并保留批次后用 `status` 排查。每次新采集固定按以下顺序，执行 `detail`、`schema`、`list-accounts`、`validate` 和真实 `fetch` 时，外层工具超时都显式设为 3600 秒：

```bash
python <skill-root>/scripts/rpa_dynamic_client.py detail
python <skill-root>/scripts/rpa_dynamic_detail_client.py detail
python <skill-root>/scripts/rpa_connector.py schema
python <skill-root>/scripts/rpa_dynamic_client.py list-accounts
python <skill-root>/scripts/rpa_dynamic_client.py validate --params-json '<按实时榜单契约生成的完整 JSON 对象>'
python <skill-root>/scripts/rpa_connector.py self-test
```

`inParamJsonSchemaText` 非空时只按其原文的 Draft 2020-12 契约校验；仅它为 `null` 时才使用 `inParamList`。未知 `shop_id` 先按详情返回的原始 `platformCode` 执行 `list-accounts`，不补 `_ACCOUNT_PASSWORD`。详情数组为空时停止，说明连接器不存在、未上线或不支持 `BIZ_EXPERT`。

将榜单和详情的动态业务参数合并成一个 JSON 文件；`target_top_n` 和 `candidate_top_n` 是本地批处理选材配置，不会透传给 connector。下例仅表示容器结构，`list`/`detail` 内的字段和枚举必须以本次 `schema` 输出为准：

```json
{
  "list": {"industry": "食品饮料", "date_type": "LAST_7_DAYS"},
  "detail": {"date_type": "LAST_7_DAYS"},
  "target_top_n": 10,
  "candidate_top_n": 20
}
```

```bash
python <skill-root>/scripts/rpa_connector.py fetch --shop-id "<shop_id>" --params-file "tmp/yuntu-rpa-params.json" --output-dir "云图数据资源/yuntu-rankings-analysis"
python <skill-root>/scripts/rpa_connector.py status --output-dir "云图数据资源/yuntu-rankings-analysis"
```

用 `--params-json` 可以传同样的完整对象。批处理 `fetch` 在每次榜单或详情任务下发前都会重新反查对应连接器详情并二次校验；失败时不下发该 RPA 任务。自定义日期、人群、品牌和榜单口径的业务映射仍遵守“先确认参数”，但实际字段名、类型、枚举与必填性不再由本文档固化。

固定顺序：三次列表（query、previous_period、industry）→ 验证 `list_context` 并选择唯一数字型 `material_id` → 详情 → 规范化 → 事实包 → 当前对话模型洞察 → 报告。RPA 优先 `files-envelope`/CSV：先落盘 `raw-csv/list.csv`、`raw-csv/details/<material_id>.csv`，再生成 `normalized/list-records.json`、`normalized/detail-records/<material_id>.json`；CSV 为主路径，兼容旧 `list-response.json`、`details/<material_id>.json`、`manifest.json`。

`fetch` 通过异步任务协议观察，单个远端任务最多轮询 3600 秒。`run-summary.json` 保存参数指纹和 `taskRuns` 汇总投影；`batch-manifest.json` 在提交后立即保存 `task_group_id`，并记录 `unresolvedMaterials`。同一输出目录恢复时只轮询已登记任务，不重复提交；没有可复用任务 ID 的失败项保持失败，不提供 RPA 重提命令。`status --output-dir` 同时核对摘要、manifest、规范化列表和详情。列表请求失败写清单并非零退出且不发详情；详情请求失败继续处理其余素材，最终非零但保留成功文件。

## 分析与交付

分析阶段只读 `normalized/` 与 `diagnostic-analysis/`，不读原始 CSV、RPA response 或临时 `fileUrl`。先运行 `prepare-analysis`；新批次不再生成 `yuntu-analysis-data.json`，生成 `report-data.json`、`diagnostic-analysis/yuntu-ai-analysis.schema.json`、`diagnostic-analysis/yuntu-analysis-prompt.md` 和五个章节事实包。历史批次缺少 `report-data.json` 时兼容渲染已有 `yuntu-analysis-data.json`；旧版完整 JSON 的额外字段忽略。渲染产物还包括 `final-report.md`。

当前对话模型直接完成一次分析任务：先读 manifest 和提示词一次，运行 `begin-analysis` 创建独立工作目录，再用 `read-analysis --workspace <目录> --part <key> --page 0` 读取任务页，按 scopedFacts、outputSkeleton、当前范围及引用清单填写 `*.json` 的 `content`。新任务内的事实视图已按章节、品牌、素材准备，不要求再全文读取五包、完整 Schema 或脚本；factInput 留作必要溯源。实际查看全部可用本地 JPEG，按素材同次完成第四章逐帧理解和第五章观察，再完成整批分类；第四章的 `viewedFrameRefs` 只记录实际查看过的成功 JPEG。四个章节草稿、第三章各品牌草稿及每个素材的草稿分别检查、保存和恢复，具体操作见 [分析草稿入口](references/analysis-drafts.md)。新批次 manifest 的 `analysisContract` 绑定五包、Schema、提示词、渲染事实和成功资产；恢复时由命令自动核对，变更后另建工作目录。`single_model_call` 保留为既有契约标识，不限制当前任务的读取或保存次数。

草稿写完立即保存，每完成一组相关草稿，用可重复的 `--part <key1> --part <key2>` 一次检查；单份报错只修受影响草稿。全部完成后直接运行 `assemble-analysis`，其内部完整检查通过才会组装，无需紧邻组装前再做一次全量检查。组装器只合并模型已写出的 JSON，保留按哈希命名的原始草稿快照和 assembly 收据，不生成、补齐或改写业务结论。新契约的 attest 必须验证草稿到最终 JSON 的无损对应。禁止程序化兜底，禁止新建承载业务结论的 Python/JS 生成脚本（包括沿用历史 `build_current_ai_analysis.py`），禁止 `codex exec`、子进程或外部模型服务调用模型。不得仅凭 `--generator` 认定模型；它和草稿来源都是调用者声明，哈希与收据不能证明模型身份、实际看图或业务判断正确。脚本和生成的提示词是 schema 权威，只生成当前报告实际展示的分析模块；固定规则负责统计，当前模型负责判断。

校验失败先读工作目录的 `validation.json`，按 `part/file/path` 修复受影响草稿。引用从该素材或 scope 的清单原样选择；帧覆盖报错列出重复、缺失和额外引用；`unsupported claim` 只核对具体句子中的跨事实源或指标因果断言。缺失事实保留不可用状态。不要删证据、关闭 provenance 或绕过 CLI；报告正文没有字数硬门槛，不为凑字数反复改写；输入未变化时不重复检查。仅报告生成任务中发现事实投影或校验器缺陷，应保留失败现场并报告具体契约问题，不以修改通用技能代码来放行；用户明确要求修复技能时可在该授权范围内修复并测试。

```bash
python <skill-root>/scripts/rpa_connector.py prepare-analysis --input-dir "云图数据资源/yuntu-rankings-analysis" --output-dir "云图数据资源/yuntu-rankings-analysis/diagnostic-analysis"
python <skill-root>/scripts/rpa_connector.py begin-analysis --fact-pack-json ".../diagnostic-analysis/analysis-units/analysis-unit-manifest.json" --workspace ".../diagnostic-analysis/model-drafts"
# 当前模型保存一组草稿后检查；--part 可重复。全部完成后 assemble 会执行全量检查。
python <skill-root>/scripts/rpa_connector.py check-analysis --workspace ".../diagnostic-analysis/model-drafts" --part ranking --part audience
python <skill-root>/scripts/rpa_connector.py assemble-analysis --workspace ".../diagnostic-analysis/model-drafts" --output ".../diagnostic-analysis/yuntu-ai-analysis.json"
python <skill-root>/scripts/rpa_connector.py attest-analysis --analysis-json ".../diagnostic-analysis/yuntu-ai-analysis.json" --fact-pack-json ".../diagnostic-analysis/analysis-units/analysis-unit-manifest.json" --prompt ".../diagnostic-analysis/yuntu-analysis-prompt.md" --source model_generated --generator "<模型或人工执行者>"
python <skill-root>/scripts/rpa_connector.py render-report --analysis-json ".../diagnostic-analysis/yuntu-ai-analysis.json" --output-dir ".../final-report"
```

报告只能由 `render-report` 渲染，使用 `assets/report/` 的离线资源并内联 CSS/JavaScript，不新增判断、不下载视频、不得手工修改 HTML。交付同级的 HTML 报告 `final-report/final-report.html` 和 `final-report.zip`；ZIP 仅含 `final-report/` 目录。报告验收只执行自动化产物校验：HTML、Markdown、报告数据、presentation JSON 与 `final-report/highlight-frames.xlsx` 非空，导航和本地帧引用有效，ZIP 含 Excel 且无占位符；不要启动实际浏览器，也不要把桌面端、移动端截图或人工视觉检查列为技能必经步骤。报告前确认 `status == success`、选中数量达标且无拒绝，否则按部分完成交付。

优化效果按 workspace.json 的 inputMetrics 与 validation.json 的 timingsSeconds 核对：字节量衡量模型读取体积，本地耗时衡量校验开销；实际模型耗时还需从执行日志单独计时，不用字节缩减率代替提速率。

新分析同时执行 `analysisQualityVersion=4` 的范围与证据契约：02、03 必须引用当前 scope 的事实，04 每个非空标准分类组默认输出一条共性结论与一个对应的裂变方向（结构兼容1–3条）。模型须核对具体观察、业务含义、建议与验证边界，禁止重复凑字；校验器不以字数或句数判定正文质量。03 和 04 必须覆盖全部指定品牌，缺失品牌保留入口并明确数据不足。品牌脚本在 `script-brand-<index>.json` 独立撰写；只引用同品牌原文。

有成功帧时，04 的逐帧理解、标准分类、本批次分类均为必填。逐帧记录 standard_category 与 category_reason，标准分类及各品牌分类必须与其一致；本批次确实无法分组时填写 unavailable 和具体原因，不得省略整个字段。
