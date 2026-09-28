# 从事实包到模型草稿再到报告

统一精简分析，不设详细档位或切换参数。建议总览100–150字、经营/人群维度40–70字、两类脚本洞察每条50–80字、每张唯一画面观察25–60字、单素材核心结论80–120字；每个分类组默认一条共性判断和一个可测试方向。字数是表达预算，不是必须达到的门槛；保留事实、范围、引用及必要字段，不补字、不重复解释。

在安装了技能 `requirements.txt` 的 Python 环境运行。草稿、导航、校验、组装、认证、渲染和验收命令只操作本地文件，不调用模型或下载资产。`prepare-analysis` 可能补取资产；纯本地续跑须在独立批次副本加 `--local-only`。

`brandScope` 是新事实包的统一范围说明；全品牌聚合结论的 `classificationSource` 固定为 `scope_aggregate`，单品牌标题匹配为 `runtime_title_rule`。这表示来源与范围，不表示品牌归属经过平台认证。旧批次要应用新口径时，重新准备事实并新建分析工作目录。

## 一次定位后按需读取

创建工作目录后运行 `analysis-overview --workspace <目录>`。返回每个 part 的草稿路径、scope/materialId、脚本是否可用及 `sectionPages`，并给出成功帧数与默认 20 张的批次数。不必重新读取完整 Schema 来查字段，也不根据旧报告猜 `audienceDashboard` 的层级。

首轮使用默认 `all` 按 nextPage 完整读取；修复或重读时，`read-analysis --workspace <目录> --part <key> --section facts --page 0` 只读事实；`schema` 读输出契约、`skeleton` 读骨架、`guidance` 读范围与引用规则；默认 `all` 保留旧用法。各 section 按 nextPage 读完，仍自动核验原始绑定，不能修改 task 文件。

`read-frame-batch --workspace <目录> --batch 0` 返回最多 20 张成功帧的绝对路径、frame_ref、`materialPart`、两章写入索引、共享字段 Schema 和 nextBatch。按批次实际看完，填写第四章理解与第五章对应观察；索引指初始骨架，若手工调整顺序按 frame_ref 定位。建议每字段 40 字内的短记录、避免分节长文；不得省字段或省帧。截断后缩小 batch-size 时，批号也按新大小重新计算（原 20 张的第 b 批对应 10 张的第 2b、2b+1 批），按 frame_ref 补齐，不直接沿用旧 nextBatch。全批完成后再汇总分类。工具不记录“已看过”，只有执行者看图后才能写 viewedFrameRefs。

第三章先选 material_ids，再从 `guidance.quoteSourcePaths` 指向的同素材正文/公式逐字选 `evidence`。证据不写改述句，不把 frame_ref 或脚本 ref 当原文；第五章 `evidenceRefs` 仍使用该素材的引用清单，两种证据格式不同。

## 保存、检查与交付

1. `begin-analysis --fact-pack-json <analysis-unit-manifest.json> --workspace <新目录>` 验证事实、提示词、Schema 和成功资产，创建 `workspace.json`、四个章节草稿、各品牌脚本草稿及每个素材的草稿。再次运行同目录只验证恢复，不覆盖已有草稿。
2. 模型先读提示词一次，再运行 `read-analysis --workspace <目录> --part <key> --page 0`，按 nextPage 读到 null；有界多行records可按path/value及container/start/text还原同名task。读取scopedFacts、readingRule、outputSkeleton与outputSchema，不再反复jq探层。scopedFacts 来自已验证的对应章节事实，不含业务答案；factInput 相对于 manifest 所在 `analysis-units` 的上一级目录，保留正式来源供必要溯源，不要求重复全文读取。image_path 相对于 task.imageRoot。旧工作目录没有 scopedFacts 时才读对应原包。新 task 文件有哈希绑定，不要编辑 task；绑定改变后另建工作目录。
3. 模型直接编辑草稿的 `content`，保持 `binding` 原样。章节 content 是顶层字段对象，例如 `{"chapter02Insights": {...}}`；单素材 content 是 `{"material_id": "...", "scriptAnalysis": {...}, "frame_observations": [...]}`。初始骨架保留常量与必填字段，正文 `null` 表示未完成，不能交付。可多次保存；不要把文字先写入 Python 常量或用品牌/帧序号模板生产正文。
4. 按素材实际逐张看图，同次完成第四章逐帧理解与第五章对应观察，及时保存；全部理解完成后做第四章整批分类。无疑点时不重复看同一原图，不把两章的业务结论互相当成证据。看图后记录 `highlight.json.viewedFrameRefs`。即使图片无法可靠理解，也记录已查看引用并在理解结果中写 unavailable 和原因；未成功落盘的图片不进入此清单。两套分类各自独立覆盖成功帧，每帧一次。
5. `check-analysis --workspace <目录> --part material-<ID1> --part material-<ID2>` 可一次检查一组，共享一次完整事实和资产验证；单个 --part 仍可单独检查。不带 `--part` 汇总所有草稿错误，通过后同时检查完整组装值。推荐第一、二章一组，第三章及品牌一组，单素材每 3–5 份一组；第四章整批完成后检查。结果写入 `validation.json`，失败返回非零退出码。结果包含草稿、字段路径、结构错误及章节语义门禁错误；同一段的语义门禁仍可能先报告最先命中的规则，结构和独立草稿错误会合并呈现。
6. 各组草稿完成后直接运行 `assemble-analysis --workspace <目录> --output <新JSON文件>`。程序内部先执行完整检查（失败仍写 validation.json 并拒绝输出），通过后复制原始草稿到 `<文件名>.drafts/<SHA256>.json`，无损合并，复用报告校验并生成 `<文件名>.assembly.json`。已有输出不覆盖；修改草稿后使用新的输出文件名。快照保留原始字节，后续修改工作草稿不影响此前快照；改写快照会导致验证失败。
7. 按 SKILL.md 的命令 attest，再 render。两者都加载相同的 manifest 绑定事实；第二章范围来自 `audience-marketing-input.json`，第五章脚本引用来自 `material-deep-dive-input.json`，不会从图表范围或另一章拼凑引用。render 的显式事实路径必须与已证明的渲染事实一致。

8. `verify-report --output-dir <final-report>` 一次核查 HTML/Markdown/JSON、导航、图片/视频引用及 Excel 内部 CRC 和嵌图数量。最终只提供 `final-report/final-report.html` 报告入口，不生成或交付报告 ZIP；保留完整报告目录和相对路径，包括原图、视频、Excel 及配套 JSON/Markdown。无成功帧时不强求空 Excel；有成功帧却缺 Excel 必须修复导出。超过 200 MiB 的提醒不代表验证失败，不能为减小体积删除报告依赖。历史同级 ZIP 原样保留，验收不依赖也不返回它。

新 `analysisContract` 批次要求组装收据；没有该字段的历史批次仍支持原来已签名 JSON 的重渲染，并回填正式章节事实进行校验。历史 JSON 可用于离线回归，但不能改称本轮重新分析。重新准备事实或修改提示词后需新建草稿目录，不能迁移旧绑定。

`model_generated`、`generator`、`viewedFrameRefs` 是执行者声明。收据可验证文件未变及正文无损组装，不能证明模型身份、真实看图或每条业务判断正确；模型调用或看图行为仍需对话执行日志佐证。

第三章品牌草稿的 key 为 `script-brand-<index>`，对应品牌由 task 明确给出。content 与全量脚本一样包含 scriptInsights、keywordCloudReview、keywordCloudInsight，由组装器无损收进 scriptBrandInsights[品牌]。task 提供该品牌独立统计的正文、公式和关键词；正文缺失时保持证据为空并说明数据不足，不能套用全量分析。

## 模型输入视图与计量

- 第一章省去聚合对象中禁止个案分析的逐素材明细，仅给出materialIds的前10项及省略量；四项指标、周期、环比、行业比较和缺失状态保持原值。完整 hotMaterialFacts（含区间、名称、辅助指标）保留。正式五包和报告事实不修改。
- 第二章把各范围重复的 topMaterials 提取为 materialsById，scope 的 topMaterialIds 保留原顺序；按 ID 可获取本任务保留的完整素材对象。所有人群桶、营销类别和原统计保留；各scope默认读取原顺序前5素材与每类别前5个tags，ReadingCoverage记录省略量，不从子集重新计算统计。遇到同 ID 不同事实则保留完整原结构，不静默合并。
- 第三章只带当前全量或品牌 scope；第五章只带当前素材的完整 script/evidenceIndex/highlightFrames，秒级曲线交给报告。所有成功 JPEG 仍需逐张查看。
- workspace.json.inputMetrics 包含原五包总字节、投影事实总字节、全部 task 文件字节；后者包含 Schema 等开销。validation.json.timingsSeconds 分别记录验证输入与检查草稿耗时。比较时说明同一批次与口径；模型读写时长、重试次数需另从实际执行日志测量。
- 旧 workspace 可继续恢复但不会被自动改写为新视图；要使用优化路径，基于未变化的 manifest 新建独立 workspace。历史分析用于回归时明确标记回放，不冒充新分析。

## 完整命令示例

```bash
python <skill-root>/scripts/rpa_connector.py prepare-analysis --input-dir "云图数据资源/yuntu-rankings-analysis" --output-dir "云图数据资源/yuntu-rankings-analysis/diagnostic-analysis"
python <skill-root>/scripts/rpa_connector.py begin-analysis --fact-pack-json ".../diagnostic-analysis/analysis-units/analysis-unit-manifest.json" --workspace ".../diagnostic-analysis/model-drafts"
python <skill-root>/scripts/rpa_connector.py analysis-overview --workspace ".../diagnostic-analysis/model-drafts"
python <skill-root>/scripts/rpa_connector.py read-frame-batch --workspace ".../diagnostic-analysis/model-drafts" --batch 0
# 当前模型保存一组草稿后检查；--part 可重复。全部完成后 assemble 会执行全量检查。
python <skill-root>/scripts/rpa_connector.py check-analysis --workspace ".../diagnostic-analysis/model-drafts" --part ranking --part audience
python <skill-root>/scripts/rpa_connector.py assemble-analysis --workspace ".../diagnostic-analysis/model-drafts" --output ".../diagnostic-analysis/yuntu-ai-analysis.json"
python <skill-root>/scripts/rpa_connector.py attest-analysis --analysis-json ".../diagnostic-analysis/yuntu-ai-analysis.json" --fact-pack-json ".../diagnostic-analysis/analysis-units/analysis-unit-manifest.json" --prompt ".../diagnostic-analysis/yuntu-analysis-prompt.md" --source model_generated --generator "<模型或人工执行者>"
python <skill-root>/scripts/rpa_connector.py render-report --analysis-json ".../diagnostic-analysis/yuntu-ai-analysis.json" --output-dir ".../final-report"
python <skill-root>/scripts/rpa_connector.py verify-report --output-dir ".../final-report"
```
