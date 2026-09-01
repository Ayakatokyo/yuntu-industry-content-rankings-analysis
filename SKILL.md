---
name: 云图行业内容榜单分析
description: 适用于通过固定预策 RPA 连接器获取行业内容榜单与秒级详情，并生成内容策略报告的场景。
argument_hint: 输入行业、分析周期（近7天、近30天或自定义起止日期）、指定品牌、截取方式、年龄、性别、八大人群和秒级拆解素材数，生成行业内容榜单分析报告。
metadata:
  pre_input: 帮我生成云图行业内容榜单分析报告，行业是 ____，分析周期是 ____（近7天、近30天或自定义起止日期；近7天/近30天直接使用云图周期定义，不换算为自定义日期），指定品牌是 ____（至少3个品牌），截取方式是 ____（曝光量TOP1000、CTRTOP1000、互动率TOP1000、完播率TOP1000），年龄是 ____（可选；不填写则不筛选，即全选），性别是 ____（可选；不填写则不筛选，即全选），八大人群是 ____（可选；不填写则不筛选，即全选），秒级拆解素材数是 ____（默认10）。
---

# 云图行业内容榜单分析

## 输入与时间

- `行业`必填；`指定品牌`可选，填写时提供 3 至 10 个品牌并使用 `SPECIFIED_BRANDS`。
- `截取方式`支持曝光量TOP1000、CTRTOP1000、互动率TOP1000、完播率TOP1000；年龄、性别、八大人群不填写时不传筛选参数（全选）。第一部分品牌分析直接使用提取到的行业 TOP1000，并在其中按品牌匹配全部素材；秒级拆解素材数默认 10，控制 RPA 详情实际拉取并做秒级拆解的目标素材数（`fetch --target-top-n`）。
- 榜单和素材详情必须使用同一分析周期（查询周期）：近7天=`LAST_7_DAYS`，近30天=`LAST_30_DAYS`，不换算为自定义日期；未填写时默认近七天。明确起止日时，两端均使用 `CUSTOM` 和相同闭区间（首尾包含）。云图界面日期只作展示核对；上一等长周期由已解析实际日期向前平移，全行业对比固定使用 `ALL_INDUSTRY`。

## 连接器与安全边界

固定连接器：`rpa.conn.juliang.yt.industry.content.rankings.list`、`rpa.conn.juliang.yt.industry.content.rankings.detail`。元数据由脚本固化，不接受覆盖。运行前阅读：

- `references/platforms/juliang-yt.md`
- `references/connectors/juliang-yt/rpa_conn_juliang_yt_industry_content_rankings_list.md`
- `references/connectors/juliang-yt/rpa_conn_juliang_yt_industry_content_rankings_detail.md`

网关使用平台运行时注入的 `ENV_BACKEND_HOST`、`YUCE_AUTHORIZATION`，以及 `YUCE_SESSION_ID` 或 `YCSESSIONID` 会话变量；显式 `YCSESSIONID` 优先作为 cookie，缺少 agent session 时可用它作为兼容回退。凭证保留在环境变量，不写入命令、JSON 或输出路径，也不要用 `.env` 覆盖网关地址。未知 `shop_id` 先运行 `list-accounts`。404 检查基路径，504 网关超时则保留批次证据后用 `status` 排查。

## 采集与观察

流程固定为：三次列表（`query`、`previous_period`、`industry`） -> 从 query 选择唯一数字型 `material_id` -> 详情 -> 规范化 -> 事实包 -> 模型洞察 -> 报告。RPA 优先走 `files-envelope`/CSV，先落盘原始文件，再生成 `normalized` records。

```bash
python <skill-root>/scripts/rpa_connector.py list-accounts
python <skill-root>/scripts/rpa_connector.py schema
python <skill-root>/scripts/rpa_connector.py self-test
python <skill-root>/scripts/rpa_connector.py status --output-dir "RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-top5"
```

```bash
python <skill-root>/scripts/rpa_connector.py fetch \
  --shop-id "<shop_id>" --industry "食品饮料" \
  --time-range-type "LAST_7_DAYS" --detail-date-range-type "LAST_7_DAYS" \
  --target-top-n 10 --candidate-top-n 20 \
  --output-dir "RPA数据汇总/yuntu-rankings-analysis"
```

自定义范围时，两端改为 `CUSTOM` 并传入 `--custom-start-date`、`--custom-end-date`、`--detail-custom-start-date`、`--detail-custom-end-date`。上例中的 `--target-top-n 10` 表示秒级拆解素材数为 10；`--candidate-top-n` 是候选池数量，默认是目标数的 2 倍；`--top-n` 仅为旧版列表参数兼容，不控制第一部分品牌分析范围。列表筛选使用 `--industry`、时间范围、`--ages`、`--genders`、`--crowd-groups`、`--brand-scope-type`、`--brands`、`--ranking-limit-type`。

`fetch` 是长任务：通过异步会话和 `status` 观察落盘，单次 RPA 最多等待 300 秒。新批次列表调用三次并分别写入 `rankingRuns` 与独立路径；三个已确定参数的榜单请求（`query`、`previous_period`、`industry`）并行执行，工作线程只负责请求和返回响应，主线程统一规范化、原子落盘并更新 manifest/run-summary，最终输出顺序固定。相对周期的上一周期须等 query 返回实际日期后再提交；query 完成后选择 `material_id` 才发详情，详情只消费 query 的 `normalized/detail-request-params.json`。上一周期使用当前实际闭区间向前平移等长天数，industry 请求强制 `ALL_INDUSTRY`。详情每波最多并行 3 个素材；本波详情与高光任务全部终态后才启动下一波。高光处理失败只记录原因，不补拉详情；已成功榜单和已落盘详情在恢复时不重复请求。

## 批次门禁与恢复

- 业务条件变化必须新建带日期和 TopN 的输出目录；指定品牌必须成对传入 `--brand-scope-type SPECIFIED_BRANDS` 与单个逗号分隔的 `--brands`。
- 启动 `fetch` 前必须先复述参数映射并核对：`fetch --target-top-n = 秒级拆解素材数`；第一部分品牌分析不再单独传入品牌 Top N。未完成映射核对时不得启动 RPA 长任务。
- `run-summary.json` 保存运行 ID、参数指纹、不可变契约和阶段计数；`batch-manifest.json` 保存候选、提交、选中、拒绝、`unresolvedMaterials` 和取消项，并逐项保存 `rankingRuns.query`、`rankingRuns.previous_period`、`rankingRuns.industry` 的请求参数、实际日期、状态和路径。续跑契约包含 `shop_id`、全部列表筛选、详情日期、`targetTopN`、`candidateTopN`；不一致或缺少可验证摘要就新建目录。
- `status --output-dir` 同时核对摘要、manifest、规范化列表、详情请求和详情文件。已落盘详情不重复提交；manifest 仍为 running 但文件已落盘时不重跑或覆盖。
- 中断且无本地详情的项目进入 `unresolvedMaterials`，不等同于 RPA 失败；用户确认可能重复请求后才运行 `retry-unresolved`。`retry-failed` 只重试 `rejectedMaterials`。
- 规范化后校验每个 `rankingRuns` 的 `list_context` 与请求一致；失败停止在 `list_context_mismatch`。报告前确认 `status == success`、`selectedCount == targetTopN`、`rejectedCount == 0`，否则按部分完成交付。历史单周期目录仍按旧路径只读兼容。
- 若存在 `selectionGroupId`，每个“品牌 × 触点”为隔离组，失败只在同组候选补位，禁止跨组借用。不得从标题、趋势或其他字段推造脚本、公式或时间戳。

## 分析与报告

### 品牌标题匹配规则

品牌范围严格取本轮 `pre_input` 的 `brands`，不扩展未输入品牌；含 `/` 的规范名拆分为中英文组成项，统一 Unicode、大小写、空格和标点后匹配，允许品牌词作为产品/营销短语子串及中英文连续混写，完整标签不是必需条件。按最长词优先并保留 `matchedBrands` 证据；命中多个品牌时同时进入多个分组。短子字段仅限受控别名或已观测上下文（如 `九阳豆浆` → `九阳自律豆浆`），不把单独 `九阳` 无条件视为命中；无有效词则为“未知品牌”，不得凭品类、功效或画面覆盖标题结果。

先运行 `prepare-analysis`。新批次不再生成 `yuntu-analysis-data.json`，只生成精简的 `report-data.json` 和 `analysis-units/` 下的榜单品牌、人群卖点、视觉高光、单素材秒级四个章节事实包。第一章的 `hotMaterialFacts` 使用 `config/hot-material-rules.json` 中的 `hotMaterialRule` 确定性计算；默认规则是曝光量区间下限 `>= 200000`，但实际生效阈值、指标和比较关系以配置为准，保留 `min`/`max`/`raw`；云图顶层 `show_cnt` 返回带范围或单位的展示字符串（如 `200-300w`）时按曝光区间解析，嵌套精确 `object_index.show_cnt` 只作为指标，不得互相替代。数据和高光帧的分析理解必须由当前对话模型直接完成：在同一次调用中读取 manifest 与四包，实际查看全部可用本地 JPEG，再生成一份 `yuntu-ai-analysis.json`；不得通过 `codex exec`、子进程或外部模型服务代替当前对话模型，不得仅凭 `--generator` 文本认定模型身份。不拆成四次模型调用。固定规则只做统计、归类、聚合和图表数据，不生成业务结论。第一章每个品牌（含全品牌）只输出一个 `dataSummary`，整体分析当前数据、环比、行业大盘和爆款事实；爆款清单仍由确定性事实面板展示。前端不再增加“AI二次分析”标题或独立底色卡片。新模型输出只生成当前报告实际展示的分析模块；旧版完整 JSON 中的额外字段会被忽略并继续兼容渲染。历史批次缺少 `report-data.json` 时，`render-report` 仍可回退读取已有 `yuntu-analysis-data.json`。脚本和生成的提示词是 schema 权威，入口不重复维护字段枚举。完成后登记来源回执：

```bash
python <skill-root>/scripts/rpa_connector.py prepare-analysis \
  --input-dir "RPA数据汇总/yuntu-rankings-analysis" \
  --output-dir "RPA数据汇总/yuntu-rankings-analysis/diagnostic-analysis"
python <skill-root>/scripts/rpa_connector.py attest-analysis \
  --analysis-json ".../diagnostic-analysis/yuntu-ai-analysis.json" \
  --fact-pack-json ".../diagnostic-analysis/analysis-units/analysis-unit-manifest.json" \
  --prompt ".../diagnostic-analysis/yuntu-analysis-prompt.md" \
  --source model_generated --generator "<模型或人工执行者>"
```

`--source` 只能为 `model_generated` 或 `manual_model_generated`，禁止程序化兜底。报告必须使用 `render-report`，它只渲染已验证洞察，不新增判断，不下载视频、不调用外部模型，也不得手工修改成品 HTML 绕过渲染器；成品使用 `assets/report/` 离线资源并内联 CSS/JavaScript。

```bash
python <skill-root>/scripts/rpa_connector.py render-report \
  --analysis-json "RPA数据汇总/yuntu-rankings-analysis/diagnostic-analysis/yuntu-ai-analysis.json" \
  --output-dir "RPA数据汇总/yuntu-rankings-analysis/final-report"
```

`render-report` 完成后交付两个文件：可直接打开的 HTML 报告 `final-report/final-report.html`，以及与 `final-report/` 目录同级的 `final-report.zip`；ZIP 只包含 `final-report/` 目录及其内部文件，不包含批次根目录其他产物。

报告验收只执行自动化产物校验：确认 HTML、Markdown、报告数据和 presentation JSON 均已生成；章节 ID 与导航目标完整且唯一；本地高光帧存在、非空且引用可解析；04 章节存在“导出高光帧资产（Excel）”按钮且 `final-report/highlight-frames.xlsx` 存在、非空（使用 `openpyxl` 与 Pillow 生成图片列和图片墙；依赖不可用时必须在 stderr 明确告警并将该批次标记为部分完成）；成品不含未替换占位符，也不把 `undefined` 或 `None` 作为报告数据值输出；ZIP 仅包含 `final-report/`；presentation JSON 通过 schema 校验。不要启动实际浏览器，也不要把桌面端、移动端截图或人工视觉检查列为技能必经步骤。

## 产物与失败处理

主要产物：`raw-csv/list.csv`、`raw-csv/list-previous-period.csv`、`raw-csv/list-industry.csv`、`raw-csv/details/<material_id>.csv`、`normalized/list-records.json`、`normalized/list-previous-period-records.json`、`normalized/list-industry-records.json`、`normalized/detail-records/<material_id>.json`、`batch-manifest.json`、`run-summary.json`、`diagnostic-analysis/report-data.json`（含比较与 `hotMaterialFacts`）、`diagnostic-analysis/analysis-units/analysis-unit-manifest.json`、四个 `analysis-units/*-input.json`、`diagnostic-analysis/yuntu-ai-analysis.schema.json`、`diagnostic-analysis/yuntu-analysis-prompt.md`、`diagnostic-analysis/yuntu-ai-analysis.json`、`final-report/final-report-data.json`、`final-report/final-report.md`、`final-report/final-report.html`、`final-report/highlight-frames.xlsx`、同级 `final-report.zip`。兼容路径可保留历史批次的 `diagnostic-analysis/yuntu-analysis-data.json`，以及旧版 `list-response.json`、`details/<material_id>.json`、`manifest.json`；CSV 为主路径，兼容 JSON 与安全的 Python 字面量。

分析阶段只读 `normalized/` 和 `diagnostic-analysis/`，不读原始 CSV、RPA response 或临时 `fileUrl`。`files-envelope` 校验成功后才下载 CSV；解析失败的嵌套字段保留原文并标记缺失。列表请求失败或无有效素材时写清单、非零退出且不发详情；详情请求失败记录后继续，最终非零但保留成功文件。报告前确认 `status == success`、`selectedCount == targetTopN`、`rejectedCount == 0`，否则按部分完成交付。

```bash
python <skill-root>/scripts/rpa_connector.py retry-failed --shop-id "<shop_id>" --output-dir "RPA数据汇总/yuntu-rankings-analysis"
python <skill-root>/scripts/rpa_connector.py retry-unresolved --shop-id "<shop_id>" --output-dir "RPA数据汇总/yuntu-rankings-analysis"
```
