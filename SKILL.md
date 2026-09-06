---
name: 云图行业内容榜单分析
description: 适用于通过固定预策 RPA 连接器获取行业内容榜单与秒级详情，并生成内容策略报告的场景。
argument_hint: 输入行业、分析周期（近7天、近30天或自定义起止日期）、指定品牌、截取方式、年龄、性别、八大人群和秒级拆解素材数，生成行业内容榜单分析报告。
metadata:
  pre_input: 帮我生成云图行业内容榜单分析报告，行业是 ____，分析周期是 ____（近7天、近30天或自定义起止日期；近7天/近30天直接使用云图周期定义，不换算为自定义日期），指定品牌是 ____（至少3个品牌），截取方式是 ____（曝光量TOP1000、CTRTOP1000、互动率TOP1000、完播率TOP1000），年龄是 ____（可选；不填写则不筛选，即全选），性别是 ____（可选；不填写则不筛选，即全选），八大人群是 ____（可选；不填写则不筛选，即全选），秒级拆解素材数是 ____（默认10）。
---

# 云图行业内容榜单分析

## 先确认参数

- 行业必填；指定品牌可选，填写时给 3–10 个品牌并使用 `SPECIFIED_BRANDS`。年龄、性别、八大人群空缺时不传筛选参数（全选）。截取方式为曝光量TOP1000、CTRTOP1000、互动率TOP1000或完播率TOP1000。
- 秒级拆解素材数默认 10，控制 RPA 详情实际拉取并做秒级拆解的目标素材数（`fetch --target-top-n`）；第一部分品牌分析直接使用提取到的行业 TOP1000，并在其中按品牌匹配全部素材。启动前复述映射；未完成映射核对时不得启动 RPA 长任务。
- 榜单和素材详情必须使用同一分析周期：近7天=`LAST_7_DAYS`、近30天=`LAST_30_DAYS`，不换算为自定义日期，未填默认近七天。自定义日期两端均为 `CUSTOM` 且闭区间；云图界面日期只作展示核对，上一等长周期按实际日期前移，全行业固定 `ALL_INDUSTRY`。

## 采集

先读 `references/platforms/juliang-yt.md`、`references/connectors/juliang-yt/rpa_conn_juliang_yt_industry_content_rankings_list.md` 和 `references/connectors/juliang-yt/rpa_conn_juliang_yt_industry_content_rankings_detail.md`。固定连接器为 `rpa.conn.juliang.yt.industry.content.rankings.list` 与 `rpa.conn.juliang.yt.industry.content.rankings.detail`；仅使用平台运行时注入的 `ENV_BACKEND_HOST`、`YUCE_AUTHORIZATION`、`YUCE_SESSION_ID`（或 `YCSESSIONID`），凭证只留在环境变量。未知 `shop_id` 先 `list-accounts`；404 查基路径，504 为网关超时，保留批次后用 `status` 排查。

```bash
python <skill-root>/scripts/rpa_connector.py list-accounts
python <skill-root>/scripts/rpa_connector.py schema
python <skill-root>/scripts/rpa_connector.py self-test
python <skill-root>/scripts/rpa_connector.py fetch --shop-id "<shop_id>" --industry "食品饮料" --time-range-type "LAST_7_DAYS" --detail-date-range-type "LAST_7_DAYS" --target-top-n 10 --candidate-top-n 20 --output-dir "RPA数据汇总/yuntu-rankings-analysis"
python <skill-root>/scripts/rpa_connector.py status --output-dir "RPA数据汇总/yuntu-rankings-analysis"
```

自定义范围时，两组日期类型都改 `CUSTOM` 并传 `--custom-start-date`、`--custom-end-date`、`--detail-custom-start-date`、`--detail-custom-end-date`；列表筛选还可传 `--ages`、`--genders`、`--crowd-groups`、`--brand-scope-type`、`--brands`、`--ranking-limit-type`。`--top-n` 仅兼容旧列表参数，不控制品牌分析范围。

固定顺序：三次列表（query、previous_period、industry）→ 选择唯一数字型 `material_id` → 详情 → 规范化 → 事实包 → 当前对话模型洞察 → 报告。RPA 优先 `files-envelope`/CSV：先落盘 `raw-csv/list.csv`、`raw-csv/details/<material_id>.csv`，再生成 `normalized/list-records.json`、`normalized/detail-records/<material_id>.json`；CSV 为主路径，兼容旧 `list-response.json`、`details/<material_id>.json`、`manifest.json`。

`fetch` 是长任务，以异步方式观察，单次最多等待 300 秒。`run-summary.json` 保存参数指纹；`batch-manifest.json` 保存 `rankingRuns`、`list_context`、候选与 `unresolvedMaterials`。已落盘详情不重复提交；`status --output-dir` 同时核对摘要、manifest、规范化列表和详情。列表请求失败写清单并非零退出且不发详情；详情请求失败继续处理其余素材，最终非零但保留成功文件。仅在用户确认可能重复请求后运行：

```bash
python <skill-root>/scripts/rpa_connector.py retry-failed --shop-id "<shop_id>" --output-dir "RPA数据汇总/yuntu-rankings-analysis"
python <skill-root>/scripts/rpa_connector.py retry-unresolved --shop-id "<shop_id>" --output-dir "RPA数据汇总/yuntu-rankings-analysis"
```

## 分析与交付

分析阶段只读 `normalized/` 与 `diagnostic-analysis/`，不读原始 CSV、RPA response 或临时 `fileUrl`。先运行 `prepare-analysis`；新批次不再生成 `yuntu-analysis-data.json`，生成 `report-data.json`、`diagnostic-analysis/yuntu-ai-analysis.schema.json`、`diagnostic-analysis/yuntu-analysis-prompt.md` 和五个章节事实包。历史批次缺少 `report-data.json` 时兼容渲染已有 `yuntu-analysis-data.json`；旧版完整 JSON 的额外字段忽略。渲染产物还包括 `final-report.md`。

当前对话模型直接完成一次分析：读取 manifest、五包和实际查看全部可用本地 JPEG，生成 `yuntu-ai-analysis.json`。禁止用 `codex exec`、子进程或外部模型服务，且不得仅凭 `--generator` 认定模型；固定规则只统计，禁止程序化兜底生成业务结论。脚本和生成的提示词是 schema 权威，只生成当前报告实际展示的分析模块。

```bash
python <skill-root>/scripts/rpa_connector.py prepare-analysis --input-dir "RPA数据汇总/yuntu-rankings-analysis" --output-dir "RPA数据汇总/yuntu-rankings-analysis/diagnostic-analysis"
python <skill-root>/scripts/rpa_connector.py attest-analysis --analysis-json ".../diagnostic-analysis/yuntu-ai-analysis.json" --fact-pack-json ".../diagnostic-analysis/analysis-units/analysis-unit-manifest.json" --prompt ".../diagnostic-analysis/yuntu-analysis-prompt.md" --source model_generated --generator "<模型或人工执行者>"
python <skill-root>/scripts/rpa_connector.py render-report --analysis-json ".../diagnostic-analysis/yuntu-ai-analysis.json" --output-dir ".../final-report"
```

报告只能由 `render-report` 渲染，使用 `assets/report/` 的离线资源并内联 CSS/JavaScript，不新增判断、不下载视频、不得手工修改 HTML。交付同级的 HTML 报告 `final-report/final-report.html` 和 `final-report.zip`；ZIP 仅含 `final-report/` 目录。报告验收只执行自动化产物校验：HTML、Markdown、报告数据、presentation JSON 与 `final-report/highlight-frames.xlsx` 非空，导航和本地帧引用有效，ZIP 含 Excel 且无占位符；不要启动实际浏览器，也不要把桌面端、移动端截图或人工视觉检查列为技能必经步骤。报告前确认 `status == success`、选中数量达标且无拒绝，否则按部分完成交付。
