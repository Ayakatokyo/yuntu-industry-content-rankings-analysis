# 云图完整事实快照渐进移除设计

## 目标

新执行的 `prepare-analysis` 不再生成 `yuntu-analysis-data.json`。模型分析继续读取四个章节事实包，报告渲染继续读取 `report-data.json`，历史批次仍可通过已有完整快照重新渲染。

## 边界

- 不删除或改写任何已有真实批次产物。
- 不修改 RPA、`normalized/` 或 `highlights/` 处理。
- 不改变四个章节事实包、统一输出 Schema 或报告结构。
- 不移除 `render-report` 对历史 `yuntu-analysis-data.json` 的回退读取。

## 新批次数据流

`prepare-analysis` 在内存中构造完整派生事实对象，以此生成：

- `report-data.json`：报告渲染、attest 前统一校验所需事实。
- `analysis-units/analysis-unit-manifest.json`：单次模型调用入口。
- 四个 `analysis-units/*-input.json`：章节隔离的模型证据。
- `yuntu-ai-analysis.schema.json` 与 `yuntu-analysis-prompt.md`。

完整派生对象只作为一次执行中的内部中间值，不再落盘为 `yuntu-analysis-data.json`。

## 兼容策略

`render-report` 的默认事实文件解析顺序保持：优先同目录 `report-data.json`，缺失时回退同目录 `yuntu-analysis-data.json`。显式 `--fact-pack-json` 行为不变。旧式 provenance 和历史 AI JSON 兼容行为不变。

## 验收

1. 新 `prepare-analysis` 成功后不存在 `yuntu-analysis-data.json`。
2. `report-data.json`、四包、manifest、Schema 和 Prompt 均存在。
3. 新批次可完成 `attest-analysis` 与 `render-report`。
4. 仅有旧完整快照的历史渲染回退测试继续通过。
5. 固定真实批次在临时目录重新准备；当前对话模型读取四包并实际查看全部可用 JPEG 后生成四字段分析。
6. 分析通过结构、证据和质量校验，报告包含预期素材与高光帧引用。
