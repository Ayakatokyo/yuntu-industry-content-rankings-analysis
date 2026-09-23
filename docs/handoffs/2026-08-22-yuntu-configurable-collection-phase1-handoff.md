# 云图可配置采集元技能阶段一交接摘要

## 交接目的

当前对话已完成“可配置云图采集与高光帧基础技能”的第一阶段。后续优化、缺陷修复和功能扩展请在新对话中继续，优先读取本摘要和独立技能仓库，不要重新从原始技能推导已确认的设计。

## 用户目标与范围决策

用户希望从原“云图行业内容榜单分析”技能中抽取 A-F 能力，形成元技能底座，并分阶段演进：

1. 迁移采集和高光帧能力。
2. 支持自定义查询条件和自定义高光帧标准。
3. 将用户口语化商业分析思路转换为格式化 Prompt。
4. 引导用户基于底座生成属于自己的高光帧分析技能并最终生成报告。

当前只完成第 1、2 项的基础实现。商业分析 Prompt、模型洞察和报告生成明确暂缓。

已确认的边界：

- 新技能独立创建文件夹和独立 Git 仓库，当前原技能保持不变。
- 对话输入必须先转换为 JSON 配置，回显并确认后再执行；文件入口直接读取同一配置格式。
- 第一阶段只输出原始/规范化数据、批次状态和高光帧资产，不输出商业结论或报告。

## 原技能 B 能力评估

原技能已经支持固定字段的组合查询：行业、`LAST_7_DAYS`、`LAST_30_DAYS` 或 `CUSTOM` 日期、年龄、性别、八大人群、品牌范围、指定品牌和四类榜单指标。

但原技能不是公开的版本化 QuerySpec：CLI 是扁平参数，未知字段会被拒绝，自定义日期有平台日期和跨度限制，指定品牌要求 3 至 10 个。因此第一阶段将其包装为稳定的嵌套配置契约，而不是开放任意字段透传。

## 独立技能位置

独立技能仓库：

`/Users/shuzida/Desktop/FDE客户/小仙炖/yuntu-configurable-collection`

当前仓库工作区干净，主要提交如下：

- `18a484d`：迁移 A-F 稳定模块和基础回归测试。
- `b89447c`：修复失败详情重试后未触发高光帧后处理；增加 `scripts` 包导入支持。
- `aac3cfb`：增加 QuerySpec / HighlightSpec 解析、默认值、校验、转换和指纹。
- `245a095`：增加按策略选择高光帧的实现和测试。
- `ba7ba5d`：将高光策略接入批次首次执行、恢复和重试，并把配置指纹纳入批次契约。
- `54c6f4c`：增加 collection-only CLI、技能说明、UI metadata 和配置样例。
- `92f7e6f`：清理入口中分析/报告命令和无关包装逻辑。
- `b15bbfa`：增加入口级筛选参数转换测试。
- `fab29a6`：兼容真实云图返回的 `CTRTOP1000` 上下文别名。

原技能仓库：

`/Users/shuzida/Desktop/FDE客户/小仙炖/yuntu-industry-content-rankings-analysis`

本轮未修改原技能实现；只新增了设计、计划和本交接文档。

## 已实现能力

### QuerySpec

入口文件：`scripts/config_specs.py`

配置包含：

- `schema_version`、固定 `source`、`industry`。
- `period.type`：`LAST_7_DAYS`、`LAST_30_DAYS`、`CUSTOM`。
- `filters.ages`、`filters.genders`、`filters.crowd_groups`。
- `filters.brand_scope.type`：`ALL_INDUSTRY` 或 `SPECIFIED_BRANDS`。
- `filters.brand_scope.brands`：指定品牌时 3 至 10 个。
- `ranking.metric`：曝光、CTR、互动率、完播率四类 TOP1000。
- `collection.target_top_n` 和 `candidate_top_n`，默认 10 和 20。

解析后转换为当前固定 RPA 连接器所需的扁平参数，并生成 SHA-256 配置指纹。未知字段、无效枚举、冲突日期、品牌范围和非正 TopN 会拒绝执行。

### HighlightSpec

支持五个指标：点赞、流失、点击、互动、评论指数。

每个指标可以独立配置：

- `local_peaks`：局部波峰。
- `absolute_max`：绝对最高值；并列时取最早秒点。
- `limit`：正整数；当前 `absolute_max` 实际选取一个最高点。

支持是否包含封面。不同指标命中同一秒时只抽取一张 JPEG，但 manifest 会保留所有命中指标、策略、值和排序原因。

### 批次与资产

保留并迁移：

- 固定云图列表/详情连接器。
- CSV 优先落盘和规范化榜单/详情记录。
- 候选补位、品牌乘触点隔离、详情两条一波并发。
- 已落盘详情恢复、`retry-failed`、`retry-unresolved`。
- 视频下载、FFmpeg 帧抽取、本地帧复用和高光 manifest。

运行目录会写入：

- `resolved-query-spec.json`
- `resolved-highlight-spec.json`
- `raw-csv/`
- `normalized/`
- `batch-manifest.json`
- `run-summary.json`
- `highlights-manifest.json`
- `highlights/` JPEG 文件

## 公共 CLI

在独立技能目录执行：

```bash
python scripts/collector.py list-accounts
python scripts/collector.py validate --query-spec query.json --highlight-spec highlights.json
python scripts/collector.py collect --shop-id "<shop_id>" --query-spec query.json --highlight-spec highlights.json --output-dir runs/example
python scripts/collector.py status --output-dir runs/example
python scripts/collector.py retry-failed --shop-id "<shop_id>" --output-dir runs/example
python scripts/collector.py retry-unresolved --shop-id "<shop_id>" --output-dir runs/example
```

凭证必须通过平台注入的环境变量提供，不能写入配置、命令记录或产物。支持的运行时变量为 `ENV_BACKEND_HOST`、`YUCE_AUTHORIZATION`、`YUCE_SESSION_ID` 或兼容回退的 `YCSESSIONID`。

## 测试证据

当前独立技能最新离线回归：

```text
python -m unittest discover -s tests -q
Ran 59 tests
OK
```

另已执行 `python -m compileall -q scripts`、`python scripts/collector.py self-test` 和 `git diff --check`，均通过。

覆盖重点：

- QuerySpec 默认值、字段转换、日期/品牌/枚举校验。
- HighlightSpec 五维策略、局部波峰、绝对最高点、同秒合并。
- collector 入口将配置转换为批次和 RPA 参数。
- 批次重试成功后仍触发高光帧后处理。
- 原技能分析/报告模块没有被迁移到新技能。

## 真实 RPA 验证

真实运行目录：

`/Users/shuzida/Desktop/FDE客户/小仙炖/yuntu-configurable-collection/runs/real-e2e-20260822-top2`

实际验证过程：

1. `list-accounts` 成功发现一个可用 `shop_id`。
2. 首次 `collect` 成功请求列表，但由于平台返回上下文为 `CTRTOP1000`，原门禁只识别 `CTR_TOP1000`，安全停止在 `list_context_mismatch`，未发详情。
3. 增加严格别名 `CTRTOP1000` 并增加回归测试。
4. 续跑复用已落盘列表，列表上下文验证通过并进入详情阶段。

最终结果：

- 列表：1000 条，`contextVerified=true`。
- 详情请求：4 条候选，3 条提交，2 条成功持久化，1 条被拒绝，1 条取消。
- 失败详情原因：RPA 网关返回内容无法解析为记录列表，错误为 `RPA gateway payload must be a record list`。
- 高光：2 条成功素材均 `postprocessStatus=succeeded`，共 9 张可用 JPEG。
- 批次最终状态：`partial`，不是完整成功。
- 可使用 `retry-failed` 重试被拒绝详情；本轮尚未继续重试。

真实运行证明了筛选条件转换、列表连接器、上下文门禁、详情调度和高光资产链路均能实际运行；但详情连接器存在一次真实返回格式异常，因此不能把本轮标为真实 E2E 全通过。

## 当前已知问题与风险

- 真实详情请求有一条返回非记录列表，需要使用 `retry-failed` 继续验证是否为临时网关问题或特定素材响应问题。
- `collector.py` 的真实 RPA 入口已验证，但还没有把“口语化对话 -> QuerySpec”做成独立自动化引导流程；目前该转换由对话模型按技能说明完成。
- 当前技能只生成数据和帧资产，没有商业分析 Prompt、模型洞察、报告 schema 或 HTML/Markdown 报告。
- 暂未安装到用户技能目录；当前先以独立仓库方式开发和验证。
- 当前没有真实视频内容人工检查记录，只验证了 JPEG 文件、数量、可用状态和 manifest 原因。

## 新对话建议入口

新对话开始时先执行：

```bash
cd "/Users/shuzida/Desktop/FDE客户/小仙炖/yuntu-configurable-collection"
git status --short
python -m unittest discover -s tests -q
```

建议后续顺序：

1. 先对 `runs/real-e2e-20260822-top2` 执行 `retry-failed`，确认详情网关异常能否恢复。
2. 增加真实/模拟的 `CUSTOM` 日期、指定品牌、年龄、性别和八大人群组合验证。
3. 增加不同五维高光策略的真实运行验证，并人工抽查 JPEG 秒点与趋势值对应关系。
4. 再设计“口语化商业分析思路 -> 标准化 Prompt”契约，不要把分析和报告代码提前混入当前采集底座。
5. 最后实现引导式元技能：询问数据源、查询条件、高光策略、商业分析框架和报告需求，生成一个依赖本底座的新技能。

## 结论

阶段一“独立、配置驱动的云图榜单/详情/高光帧采集底座”已完成离线实现并通过 59 项测试；真实 RPA 已跑通列表、详情和高光链路，但当前批次为 `partial`，仍有一条详情响应需要重试或归因。后续对话应以“验证和增量完善”为起点，不应重新设计已经确认的独立仓库和 QuerySpec / HighlightSpec 边界。
