# 第五章字段收敛设计

## 目标

清理 05｜单素材深度分析链路中的重复和不消费字段，同时保持合并事实包、第一/二/四章口径以及历史报告读取兼容。

## 范围与边界

- 只收窄第五章专用 `analysis-units/material-deep-dive-input.json` 的模型证据投影。
- `report-data.json` 继续保留跨章节共享的 `materialFacts`，不删除其历史兼容字段。
- `materialDeepDives` AI 输出契约保持不变：每项仅包含 `material_id`、`frame_observations`、`second_level_observations`。
- Presentation 第五章只保留 `chapters.chapter05` 作为素材面板唯一数据源；删除未被渲染器消费的顶层 `materials` 别名。
- 第五章帧卡只携带自身不可推导字段；素材 ID、排名、标题由 panel 继承，标题说明由渲染器按帧类型生成。

## 数据收敛

第五章模型输入每个素材保留：

- `material_id`
- `highlightFrames`：`frame_ref`、`second`、`frame_type`、`available`、`failure_reason`、`image_path`
- `secondLevelBreakdown.metrics`：趋势名、可用性、缺失原因、点序列、高点和流失点

删除第五章模型不消费的榜单指标、标签、可用性汇总和帧复制元数据，包括 `metricComparison`、`people_tags`、`material_tags`、`highlightFrameAvailability`、`listDataAvailability`、`rank`、`title` 及帧的 `is_cover`、`peak_rank`、`click_value`、`reasons`、`relative_path`、`frame_source`。

## Presentation 与渲染

- `_project_chapter05` 使用第五章专用帧投影，避免把 panel 级字段复制到每张帧卡。
- `materialTabs` 与 `interactions.chapter05-material-tabs` 继续保留稳定交互契约，但均由同一 `tabs` 对象生成。
- HTML 继续从 `chapters.chapter05.panels` 渲染，帧选择、观察和五类秒级趋势交互行为不变。

## 验证

- 单元测试断言第五章输入投影不含删除字段，且保留视觉图片与秒级事实。
- Presentation 测试断言不存在顶层 `materials`，帧卡不含 panel 可继承字段，chapter05 tabs 与交互声明一致。
- 报告渲染测试断言第五章帧、观察、秒级拆解和脚本不可用状态仍存在。
- 运行 `python -m unittest discover -s tests -q`、`python -m compileall -q scripts tests` 和 `git diff --check`。
