# 可配置云图采集与高光帧基础技能设计

## 目标

从现有“云图行业内容榜单分析”技能中独立出可安装、可复跑的采集底座。该底座只负责固定云图 RPA 的榜单和素材详情采集、标准化、批次恢复与可配置高光帧提取，不包含事实包、商业分析 Prompt、模型洞察来源登记或报告渲染。

后续的商业分析标准化 Prompt 和引导式元技能均以此底座为唯一数据与素材入口。

## 边界

新技能名称暂定为 `yuntu-configurable-collection`，位于独立技能文件夹和独立 Git 仓库中。当前 `yuntu-industry-content-rankings-analysis` 技能保持不变。

新技能保留：

- 固定云图账号发现、认证读取、连接器调用与参数校验。
- 榜单列表和入选素材的秒级详情采集。
- CSV 优先落盘、网关结果解析和规范化记录。
- 候选补位、品牌乘触点分组、批次账本、续跑、状态查询和两类重试。
- 视频下载、可配置高光秒点选择、JPEG 提取和高光帧清单。

新技能不包含：

- 统计事实包、品牌/人群/营销分析。
- 商业分析 Prompt、模型调用或模型结果来源校验。
- Markdown、HTML、JSON 报告投影或渲染资源。

## 架构

```text
对话输入 / query-spec.json / highlight-spec.json
  -> 配置解析、默认值补齐与校验
  -> 固定云图列表 RPA
  -> CSV 落盘与榜单规范化
  -> 候选筛选、详情 RPA、批次恢复和失败补位
  -> 详情规范化
  -> HighlightSpec 选点、视频下载和 JPEG 抽取
  -> 结构化数据、帧资产与可审计清单
```

迁移 `rpa_connector.py`、`rpa_io.py`、`yuntu_normalizer.py`、`yuntu_run_state.py`、`yuntu_batch.py` 与 `yuntu_highlights.py` 中的相关实现。新 CLI 入口为 `scripts/collector.py`。迁移后仅以新配置契约调用这些模块，不能反向依赖原技能的分析或报告模块。

## QuerySpec

`query-spec.json` 规定用户要采集的数据。用户以对话输入时，代理先生成该文件、向用户回显已解析条件并确认；自动化和续跑直接提供该文件。两条入口必须生成完全相同的已解析配置。

```json
{
  "schema_version": 1,
  "source": "juliang_yuntu_industry_content_rankings",
  "industry": "食品饮料",
  "period": { "type": "LAST_7_DAYS" },
  "filters": {
    "ages": [],
    "genders": [],
    "crowd_groups": [],
    "brand_scope": { "type": "ALL_INDUSTRY", "brands": [] }
  },
  "ranking": { "metric": "CTR_TOP1000" },
  "collection": { "target_top_n": 10, "candidate_top_n": 20 }
}
```

支持的筛选条件保持当前连接器范围：行业、近 7 天/近 30 天/自定义日期、年龄、性别、八大人群、品牌范围和四类榜单指标。`CUSTOM` 期间必须带闭区间起止日期，并复用现有时间跨度和可用日期校验。未知字段、冲突字段和不受支持的枚举必须报错，不能透传到 RPA。

解析器必须写出 `resolved-query-spec.json`。其中填入所有默认值，并将其指纹计入运行契约。`shop_id`、已解析查询和已解析高光策略不一致时，已有运行目录禁止续跑。

## HighlightSpec

`highlight-spec.json` 规定每个素材如何选择和抽取高光帧。

```json
{
  "schema_version": 1,
  "include_cover": true,
  "metrics": {
    "点赞指数": { "strategy": "local_peaks", "limit": 3 },
    "流失指数": { "strategy": "absolute_max", "limit": 1 },
    "点击指数": { "strategy": "local_peaks", "limit": 3 },
    "互动指数": { "strategy": "absolute_max", "limit": 1 },
    "评论指数": { "strategy": "local_peaks", "limit": 2 }
  }
}
```

第一版只支持五项指标：点赞、流失、点击、互动和评论指数；每个指标可独立指定：

- `local_peaks`：按趋势选择局部波峰。
- `absolute_max`：选择整条趋势中的绝对最高点。

`limit` 必须为正整数。相同秒点被多个指标命中时只能生成一张 JPEG，但清单必须保存全部指标、策略和命中原因。缺失趋势或视频不可用时，写出明确的不可用或失败状态，不能伪造帧，也不能阻断其他指标的处理。

解析器必须写出 `resolved-highlight-spec.json`。策略字段预留扩展空间，但第一版遇到未知策略立即报错。

## 执行接口与产物

```bash
python scripts/collector.py list-accounts
python scripts/collector.py validate --query-spec query.json --highlight-spec highlights.json
python scripts/collector.py collect --shop-id "<shop_id>" --query-spec query.json --highlight-spec highlights.json --output-dir runs/example
python scripts/collector.py status --output-dir runs/example
python scripts/collector.py retry-failed --shop-id "<shop_id>" --output-dir runs/example
python scripts/collector.py retry-unresolved --shop-id "<shop_id>" --output-dir runs/example
```

每次运行至少输出：

- `resolved-query-spec.json` 和 `resolved-highlight-spec.json`。
- `raw-csv/list.csv` 与 `raw-csv/details/<material_id>.csv`。
- `normalized/list-records.json` 与 `normalized/detail-records/<material_id>.json`。
- `batch-manifest.json`、`run-summary.json` 与 `highlights-manifest.json`。
- `highlights/<material_id>/` 下的 JPEG 帧。

保留固定连接器、环境凭证边界、CSV 优先路径、两条详情一波的并发、候选补位、同组补位、已落盘详情恢复和两类重试的现有行为。高光帧选择从固定“封面加点击峰值”替换为 HighlightSpec 驱动。

## 错误处理

- 解析配置前拒绝未知字段、无效枚举、空值和不一致的日期或品牌范围。
- 列表失败或列表上下文与已解析 QuerySpec 不一致时，停止详情采集并保存状态。
- 单条详情失败进入 `rejectedMaterials`；进程中断但未持久化的详情进入 `unresolvedMaterials`。
- `retry-failed` 只处理拒绝条目；`retry-unresolved` 只处理明确确认可重发的未解析条目。
- 视频下载或帧提取失败仅影响对应帧记录；已成功的详情和其他帧保持可交付。

## 验证

- 对话生成配置和直接加载等价 JSON 必须产生相同的已解析配置和 RPA 参数。
- 覆盖 QuerySpec 的默认值、每个支持字段、冲突、未知字段和日期边界。
- 覆盖五项指标各自的 `local_peaks` 与 `absolute_max` 选择。
- 覆盖跨指标同秒去重与命中来源保留。
- 覆盖缺失趋势、视频不可下载、单帧失败、详情失败、候选补位、状态查询、同配置续跑与配置不一致拒绝续跑。
- 覆盖迁移边界，确保新技能不导入分析、商业 Prompt、模型来源校验或报告渲染模块。

## 分阶段路线

1. 创建独立技能目录，迁移 A-F 的稳定能力，并建立上述 CLI 与产物边界。
2. 实现 QuerySpec 和 HighlightSpec，替换现有扁平 CLI 入参与固定高光策略。
3. 在基础技能的事实和帧资产之上，实现将口语化商业分析思路标准化为可验证 Prompt 的能力。
4. 实现引导式元技能：询问数据源、取数口径、高光策略、商业分析框架和报告需求，生成一个依赖该底座的新技能。
