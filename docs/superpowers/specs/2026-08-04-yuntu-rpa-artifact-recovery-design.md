# 云图 RPA 产物接收与可恢复执行设计

## 目标

将云图行业内容榜单分析从命令顺序驱动改为产物驱动：RPA 的成功结果必须被接收、校验并物化到运行目录，之后的分析、渲染和验收只读取本地运行产物，不得重复调用 RPA。

## 问题证据

真实执行日志显示：RPA 抓取超时后仍有部分 CSV 已生成；执行者随后反复查找文件并再次调用抓取。由于当前流程没有一个明确的运行状态文件来声明“哪些响应文件已接收、哪些待恢复、下一步无需 RPA”，RPA 结果、临时附件和本地落盘之间的边界不清晰。分析 JSON 的结构错误又会诱发不必要的重新抓取。

## 设计

### 运行目录与唯一状态

每次 `fetch` 以规范化的业务参数生成参数指纹，并在输出目录写入 `run-summary.json`。该文件是恢复、分析和报告阶段的唯一入口，包含：

- `schemaVersion`、`runId`、`parameterFingerprint` 和过滤条件；
- 阶段状态：`collecting`、`analysis_pending`、`report_pending`、`complete` 或带失败原因的可恢复状态；
- `artifacts`：每个 RPA 响应、附件和已物化文件的相对路径、来源、大小、SHA-256、解析状态；
- `nextAction`：可执行的本地命令及其是否允许调用 RPA。

`batch-manifest.json` 保留为选材与详情调度明细；`run-summary.json` 聚合它并对执行者给出恢复结论。

### 文件接收与物化

RPA 结果接收顺序固定如下：

1. 原子保存脱敏后的网关响应到 `raw-responses/`。
2. 若返回 files-envelope，先检查 `fileUrl`；若该 URL 下载失败或已经过期，则在受限的 `artifact-input-dir` 中按允许扩展名和本次请求的文件名线索查找新产生的附件。
3. 将唯一候选文件原子复制到 `raw-csv/`，记录来源为 `download` 或 `local_artifact`，并校验非空、SHA-256 与 CSV 可解析性。
4. 只有文件物化和解析均成功，才写入 `normalized/`、更新 `batch-manifest.json`，并将该 RPA 阶段标记为完成。

不会扫描用户的整个下载目录，也不会接受多个候选文件。找不到或有歧义时写入 `artifact_unavailable`，保留已落盘文件并退出；恢复只能补接收该文件或重试缺失详情。

### 幂等与恢复规则

`fetch` 在输出目录已有同一参数指纹且 `run-summary.json` 声明已接收的榜单和详情文件时，不再调用列表或已成功详情 RPA。它刷新状态并返回本地恢复动作。仅以下情况允许新的 RPA 调用：参数指纹变化、用户传入明确的 `--refresh`，或状态文件将某详情显式标记为 `retryable_rpa`。

`prepare-analysis` 和 `render-report` 只接受有效的本地运行目录。它们把阶段状态分别推进为 `analysis_pending`、`report_pending` 或 `complete`，任何失败只更新状态和 `nextAction`，不得调用 RPA。

### 验收

每个阶段完成后校验其声明的本地文件存在、非空且哈希匹配。最终验收同时要求：已选素材数等于可用详情数、分析六章满足渲染器结构契约、三份最终报告产物存在且非空。验收失败必须指向本地修复命令，禁止推荐重新抓取。

## 兼容性

保持现有 `fetch`、`retry-failed`、`prepare-analysis` 与 `render-report` 命令可用；新增可选的 `--artifact-input-dir` 和明确的 `--refresh`。既有 `batch-manifest.json` 保持可读取；新 `run-summary.json` 补充而非替换其选材字段。
