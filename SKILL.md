---
name: 云图行业内容榜单分析
description: 适用于通过固定预策 RPA 连接器获取行业内容榜单与秒级详情，或复用已落盘的云图数据、高光帧和视频继续分析并生成内容策略报告的场景。
argument_hint: 输入行业、分析周期（近7天、近30天或自定义起止日期）、指定品牌、截取方式、年龄、性别、八大人群和秒级拆解素材数，生成行业内容榜单分析报告。
metadata:
  pre_input: 帮我生成云图行业内容榜单分析报告，行业是 ____，分析周期是 ____（近7天、近30天或自定义起止日期；近7天/近30天直接使用云图周期定义，不换算为自定义日期），指定品牌是 ____（至少3个品牌），截取方式是 ____（曝光量TOP1000、CTRTOP1000、互动率TOP1000、完播率TOP1000），年龄是 ____（可选；不填写则不筛选，即全选），性别是 ____（可选；不填写则不筛选，即全选），八大人群是 ____（可选；不填写则不筛选，即全选），秒级拆解素材数是 ____（默认10）。
---

# 云图行业内容榜单分析

## 已落盘数据续跑

用户要求“用已落盘数据继续分析/重新生成报告”时直接进入本节；采集参数从原批次 manifest 读取，不重新索要账号凭证或启动 `fetch`。只有本地数据不足且用户明确要求补采时，才进入采集流程。

- 先定位用户指定批次及 `batch-manifest.json`，核对实际周期、筛选、选中素材 ID、规范化文件路径和本地资产。用户只说“最新”时核对清单内容和对话来源，不按目录名、mtime 或旧报告文件名猜测；有无法消除的多个候选时再询问。记录源清单/输入文件 SHA-256 和本轮独立输出路径。
- 先判断重分析还是仅重渲染。用户要求完整后续分析时，生成新 AI JSON，不把历史 JSON 改名或补字段冒充新分析。仅重渲染才考虑复用已通过校验、且事实包/提示词绑定未变化的历史分析。
- 保留源 CSV、normalized、旧 AI JSON、报告和 provenance。`prepare-analysis` 会检查高光帧并可能下载视频、截帧和回写资产清单；纯本地续跑前先检查资产完整性，并在独立批次副本运行，保持相对路径。已齐备资产直接复用；缺失资产若用户未授权补取，先报告具体缺口，不让准备步骤隐式联网。
- 区分 `source_empty`（源字段确实为空）、`parse_failed`（解码失败）和映射遗漏。仅在数据诊断阶段允许只读追溯 raw CSV → normalized → 章节事实包；业务分析仍只使用规范化后的章节事实。发现 CSV/normalized 有趋势而事实包称 `trend_not_returned`，先修复本地规范化或事实映射，不能靠提示词补造数据。字段存在不等于正文非空，创意标签不能代替完整脚本。
- 新事实包生成后核对素材集合、五类趋势点、脚本覆盖和成功帧集合。帧从旧数量变为新数量、脚本新增、素材范围或提示词改变时，旧分析需重新生成并重新 attest；不得删掉新增帧来迎合旧 JSON。阶段分别记为事实准备、模型分析、校验、渲染、交付，不用采集 `success` 代替分析完成。

## 先确认参数

- 行业必填；指定品牌可选，填写时给 3–10 个品牌并使用 `SPECIFIED_BRANDS`。年龄、性别、八大人群空缺时不传筛选参数（全选）。截取方式为曝光量TOP1000、CTRTOP1000、互动率TOP1000或完播率TOP1000。
- 秒级拆解素材数默认 10，控制 RPA 详情实际拉取并做秒级拆解的目标素材数（`fetch --target-top-n`）；第一部分品牌分析直接使用提取到的行业 TOP1000，并在其中按品牌匹配全部素材。启动前复述映射；未完成映射核对时不得启动 RPA 长任务。
- 榜单和素材详情必须使用同一分析周期：近7天=`LAST_7_DAYS`、近30天=`LAST_30_DAYS`，不换算为自定义日期，未填默认近七天。自定义日期两端均为 `CUSTOM` 且闭区间；云图界面日期只作展示核对，上一等长周期按实际日期前移，全行业固定 `ALL_INDUSTRY`。

## 采集

先读 `references/platforms/juliang-yt.md`、`references/connectors/juliang-yt/rpa_conn_juliang_yt_industry_content_rankings_list.md` 和 `references/connectors/juliang-yt/rpa_conn_juliang_yt_industry_content_rankings_details.md`。固定连接器为 `rpa.conn.juliang.yt.industry.content.rankings.list` 与 `rpa.conn.juliang.yt.industry.content.rankings.details`；仅使用平台运行时注入的 `ENV_BACKEND_HOST`、`YUCE_AUTHORIZATION`、`YUCE_SESSION_ID`（或 `YCSESSIONID`），凭证只留在环境变量。MCP 知识库地址不是 `ENV_BACKEND_HOST`。未知 `shop_id` 先 `list-accounts`；404 查基路径，504 为网关超时，保留批次后用 `status` 排查。

```bash
python <skill-root>/scripts/rpa_connector.py list-accounts
python <skill-root>/scripts/rpa_connector.py schema
python <skill-root>/scripts/rpa_connector.py self-test
python <skill-root>/scripts/rpa_connector.py fetch --shop-id "<shop_id>" --industry "食品饮料" --time-range-type "LAST_7_DAYS" --detail-date-range-type "LAST_7_DAYS" --target-top-n 10 --candidate-top-n 20 --output-dir "RPA数据汇总/yuntu-rankings-analysis"
python <skill-root>/scripts/rpa_connector.py status --output-dir "RPA数据汇总/yuntu-rankings-analysis"
```

自定义范围时，两组日期类型都改 `CUSTOM` 并传 `--custom-start-date`、`--custom-end-date`、`--detail-custom-start-date`、`--detail-custom-end-date`；列表筛选还可传 `--ages`、`--genders`、`--crowd-groups`、`--brand-scope-type`、`--brands`、`--ranking-limit-type`。`--top-n` 仅兼容旧列表参数，不控制品牌分析范围。

固定顺序：三次列表（query、previous_period、industry）→ 验证 `list_context` 并选择唯一数字型 `material_id` → 详情 → 规范化 → 事实包 → 当前对话模型洞察 → 报告。RPA 优先 `files-envelope`/CSV：先落盘 `raw-csv/list.csv`、`raw-csv/details/<material_id>.csv`，再生成 `normalized/list-records.json`、`normalized/detail-records/<material_id>.json`；CSV 为主路径，兼容旧 `list-response.json`、`details/<material_id>.json`、`manifest.json`。

`fetch` 通过异步任务协议观察，单个远端任务最多轮询 3600 秒。`run-summary.json` 保存参数指纹和 `taskRuns` 汇总投影；`batch-manifest.json` 在提交后立即保存 `task_group_id`，并记录 `unresolvedMaterials`。同一输出目录恢复时只轮询已登记任务，不重复提交。`status --output-dir` 同时核对摘要、manifest、规范化列表和详情。列表请求失败写清单并非零退出且不发详情；详情请求失败继续处理其余素材，最终非零但保留成功文件。仅在用户确认可能重复请求后运行：

```bash
python <skill-root>/scripts/rpa_connector.py retry-failed --shop-id "<shop_id>" --output-dir "RPA数据汇总/yuntu-rankings-analysis"
python <skill-root>/scripts/rpa_connector.py retry-unresolved --shop-id "<shop_id>" --output-dir "RPA数据汇总/yuntu-rankings-analysis"
```

## 分析与交付

分析阶段只读 `normalized/` 与 `diagnostic-analysis/`，不读原始 CSV、RPA response 或临时 `fileUrl`。先运行 `prepare-analysis`；新批次不再生成 `yuntu-analysis-data.json`，生成 `report-data.json`、`diagnostic-analysis/yuntu-ai-analysis.schema.json`、`diagnostic-analysis/yuntu-analysis-prompt.md` 和五个章节事实包。历史批次缺少 `report-data.json` 时兼容渲染已有 `yuntu-analysis-data.json`；旧版完整 JSON 的额外字段忽略。渲染产物还包括 `final-report.md`。

当前对话模型直接完成一次分析任务：读取 manifest、五包和实际查看全部可用本地 JPEG，生成 `yuntu-ai-analysis.json`。允许在当前任务中按章节、素材或帧批次分步阅读并保存模型撰写的草稿；每次保存记录事实包/提示词哈希、已查看帧引用和待办，恢复时先核对绑定。manifest 的 `single_model_call` 保留为既有契约标识，不要求一次工具输出塞完所有图片和 JSON。禁止用 `codex exec`、子进程或外部模型服务调用模型，且不得仅凭 `--generator` 认定模型；脚本可无损组装模型已写出的 JSON 和检查覆盖，固定规则只统计，禁止程序化兜底或根据品牌、标题、帧序号套模板生成业务结论。脚本和生成的提示词是 schema 权威，只生成当前报告实际展示的分析模块。

校验失败后按报错字段修复：引用/素材/帧覆盖不符先查绑定与漏项；`unsupported claim` 核对具体句子和命中词，区别实际外推与否定性的范围限制；缺失事实保留不可用状态。不要为了通过门禁删证据、关闭 provenance、绕过 CLI 直接渲染或机械扩写凑字数。同一错误在未修改输入时不重复执行；修复受影响草稿后重新 attest，成功后继续 render 和打包，不把一次校验失败当成任务结束。

```bash
python <skill-root>/scripts/rpa_connector.py prepare-analysis --input-dir "RPA数据汇总/yuntu-rankings-analysis" --output-dir "RPA数据汇总/yuntu-rankings-analysis/diagnostic-analysis"
python <skill-root>/scripts/rpa_connector.py attest-analysis --analysis-json ".../diagnostic-analysis/yuntu-ai-analysis.json" --fact-pack-json ".../diagnostic-analysis/analysis-units/analysis-unit-manifest.json" --prompt ".../diagnostic-analysis/yuntu-analysis-prompt.md" --source model_generated --generator "<模型或人工执行者>"
python <skill-root>/scripts/rpa_connector.py render-report --analysis-json ".../diagnostic-analysis/yuntu-ai-analysis.json" --output-dir ".../final-report"
```

报告只能由 `render-report` 渲染，使用 `assets/report/` 的离线资源并内联 CSS/JavaScript，不新增判断、不下载视频、不得手工修改 HTML。交付同级的 HTML 报告 `final-report/final-report.html` 和 `final-report.zip`；ZIP 仅含 `final-report/` 目录。报告验收只执行自动化产物校验：HTML、Markdown、报告数据、presentation JSON 与 `final-report/highlight-frames.xlsx` 非空，导航和本地帧引用有效，ZIP 含 Excel 且无占位符；不要启动实际浏览器，也不要把桌面端、移动端截图或人工视觉检查列为技能必经步骤。报告前确认 `status == success`、选中数量达标且无拒绝，否则按部分完成交付。
