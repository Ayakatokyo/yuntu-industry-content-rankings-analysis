# 云图 RPA 适配性优化设计

## 目标

在不改变现有“榜单取数 -> 详情取数 -> 规范化 -> 分析 -> 报告”主链路的前提下，把当前技能与平台 `预策RPA连接器取数` 的契约对齐，减少文档漂移和运行时误拒绝。

## 范围

- 放宽 `ages`、`genders`、`crowd_groups` 的枚举阻断，只保留格式级校验。
- 增加失败详情的定向恢复能力，支持基于 `batch-manifest.json` 重试 rejected 素材。
- 将技能文档改成 `<skill-root>` 命令路径，并显式引用平台式 `references/` 路由结构。
- 补齐本地 `references/platforms` 与 `references/connectors` 文档，使技能结构与平台知识库一致。

## 非目标

- 不改动固定 `function_code`、`platform`、`data_source_type`。
- 不重写现有批次拉取、规范化、分析和渲染逻辑。
- 不引入视频下载、抽帧、断点续跑全量恢复。

## 方案

### 1. 入参兼容

当前脚本对白名单之外的 `ages`、`genders`、`crowd_groups` 值直接报错，这会让自定义技能比平台知识条目更严格。优化后：

- `ages`、`genders`、`crowd_groups` 继续要求是逗号分隔字符串或字符串数组。
- 仍拒绝空值、重复值、非字符串值。
- 不再要求必须命中内置英文枚举。

这样可以兼容中文标签、平台未来新增值和尚未固化到脚本内的编码。

### 2. 失败详情重试

在 `scripts/yuntu_batch.py` 增加 `retry_failed_batch()`：

- 读取已有 `batch-manifest.json`。
- 仅重试 `rejectedMaterials` 中的素材详情请求。
- 成功后回填 `normalized/detail-records/*.json`、`selectedMaterials` 和 `top-materials-rpa-ready.json`。
- 全部 rejected 清空且达到目标数量时，将状态更新为 `success`。

在 CLI 增加 `retry-failed` 子命令，参数最小化为：

- `--shop-id`
- `--output-dir`

详情日期范围继续从现有 manifest 的 `detailDateRange` 读取。

### 3. 技能结构与文档

保留根 `SKILL.md` 作为总入口，但增加：

- `references/platforms/juliang-yt.md`
- `references/connectors/juliang-yt/rpa_conn_juliang_yt_industry_content_rankings_list.md`
- `references/connectors/juliang-yt/rpa_conn_juliang_yt_industry_content_rankings_detail.md`

`SKILL.md` 统一用 `python <skill-root>/scripts/rpa_connector.py ...` 表达命令，并在正文显式指向上述 `references/` 文档。

## 验收标准

- 多选筛选字段接受合法但未收录在本地白名单内的值。
- `retry-failed` 只重试 rejected 素材，不重复请求成功详情。
- `SKILL.md` 出现 `<skill-root>` 命令路径和平台式 `references/` 文档引用。
- 现有测试与新增测试全部通过。
