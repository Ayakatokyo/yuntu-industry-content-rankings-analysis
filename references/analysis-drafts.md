# 从事实包到模型草稿再到报告

统一精简分析，不设详细档位或切换参数。建议总览100–150字、经营/人群维度40–70字、两类脚本洞察每条50–80字、每张唯一画面观察25–60字、单素材核心结论80–120字；每个分类组默认一条共性判断和一个可测试方向。字数是表达预算，不是必须达到的门槛；保留事实、范围、引用及必要字段，不补字、不重复解释。

在安装了技能 `requirements.txt` 的 Python 环境运行。全部命令都是本地文件操作，不调用模型或下载资产。

1. `begin-analysis --fact-pack-json <analysis-unit-manifest.json> --workspace <新目录>` 验证事实、提示词、Schema 和成功资产，创建 `workspace.json`、四个章节草稿、各品牌脚本草稿及每个素材的草稿。再次运行同目录只验证恢复，不覆盖已有草稿。
2. 模型先读提示词一次，再运行 `read-analysis --workspace <目录> --part <key> --page 0`，按 nextPage 读到 null；有界多行records可按path/value及container/start/text还原同名task。读取scopedFacts、readingRule、outputSkeleton与outputSchema，不再反复jq探层。scopedFacts 来自已验证的对应章节事实，不含业务答案；factInput 相对于 manifest 所在 `analysis-units` 的上一级目录，保留正式来源供必要溯源，不要求重复全文读取。image_path 相对于 task.imageRoot。旧工作目录没有 scopedFacts 时才读对应原包。新 task 文件有哈希绑定，不要编辑 task；绑定改变后另建工作目录。
3. 模型直接编辑草稿的 `content`，保持 `binding` 原样。章节 content 是顶层字段对象，例如 `{"chapter02Insights": {...}}`；单素材 content 是 `{"material_id": "...", "scriptAnalysis": {...}, "frame_observations": [...]}`。初始骨架保留常量与必填字段，正文 `null` 表示未完成，不能交付。可多次保存；不要把文字先写入 Python 常量或用品牌/帧序号模板生产正文。
4. 按素材实际逐张看图，同次完成第四章逐帧理解与第五章对应观察，及时保存；全部理解完成后做第四章整批分类。无疑点时不重复看同一原图，不把两章的业务结论互相当成证据。看图后记录 `highlight.json.viewedFrameRefs`。即使图片无法可靠理解，也记录已查看引用并在理解结果中写 unavailable 和原因；未成功落盘的图片不进入此清单。两套分类各自独立覆盖成功帧，每帧一次。
5. `check-analysis --workspace <目录> --part material-<ID1> --part material-<ID2>` 可一次检查一组，共享一次完整事实和资产验证；单个 --part 仍可单独检查。不带 `--part` 汇总所有草稿错误，通过后同时检查完整组装值。推荐第一、二章一组，第三章及品牌一组，单素材每 3–5 份一组；第四章整批完成后检查。结果写入 `validation.json`，失败返回非零退出码。结果包含草稿、字段路径、结构错误及章节语义门禁错误；同一段的语义门禁仍可能先报告最先命中的规则，结构和独立草稿错误会合并呈现。
6. 各组草稿完成后直接运行 `assemble-analysis --workspace <目录> --output <新JSON文件>`。程序内部先执行完整检查（失败仍写 validation.json 并拒绝输出），通过后复制原始草稿到 `<文件名>.drafts/<SHA256>.json`，无损合并，复用报告校验并生成 `<文件名>.assembly.json`。已有输出不覆盖；修改草稿后使用新的输出文件名。快照保留原始字节，后续修改工作草稿不影响此前快照；改写快照会导致验证失败。
7. 按 SKILL.md 的命令 attest，再 render。两者都加载相同的 manifest 绑定事实；第二章范围来自 `audience-marketing-input.json`，第五章脚本引用来自 `material-deep-dive-input.json`，不会从图表范围或另一章拼凑引用。render 的显式事实路径必须与已证明的渲染事实一致。

新 `analysisContract` 批次要求组装收据；没有该字段的历史批次仍支持原来已签名 JSON 的重渲染，并回填正式章节事实进行校验。历史 JSON 可用于离线回归，但不能改称本轮重新分析。重新准备事实或修改提示词后需新建草稿目录，不能迁移旧绑定。

`model_generated`、`generator`、`viewedFrameRefs` 是执行者声明。收据可验证文件未变及正文无损组装，不能证明模型身份、真实看图或每条业务判断正确；模型调用或看图行为仍需对话执行日志佐证。

第三章品牌草稿的 key 为 `script-brand-<index>`，对应品牌由 task 明确给出。content 与全量脚本一样包含 scriptInsights、keywordCloudReview、keywordCloudInsight，由组装器无损收进 scriptBrandInsights[品牌]。task 提供该品牌独立统计的正文、公式和关键词；正文缺失时保持证据为空并说明数据不足，不能套用全量分析。

## 模型输入视图与计量

- 第一章省去聚合对象中禁止个案分析的逐素材明细，仅给出materialIds的前10项及省略量；四项指标、周期、环比、行业比较和缺失状态保持原值。完整 hotMaterialFacts（含区间、名称、辅助指标）保留。正式五包和报告事实不修改。
- 第二章把各范围重复的 topMaterials 提取为 materialsById，scope 的 topMaterialIds 保留原顺序；按 ID 可获取本任务保留的完整素材对象。所有人群桶、营销类别和原统计保留；各scope默认读取原顺序前5素材与每类别前5个tags，ReadingCoverage记录省略量，不从子集重新计算统计。遇到同 ID 不同事实则保留完整原结构，不静默合并。
- 第三章只带当前全量或品牌 scope；第五章只带当前素材的完整 script/evidenceIndex/highlightFrames，秒级曲线交给报告。所有成功 JPEG 仍需逐张查看。
- workspace.json.inputMetrics 包含原五包总字节、投影事实总字节、全部 task 文件字节；后者包含 Schema 等开销。validation.json.timingsSeconds 分别记录验证输入与检查草稿耗时。比较时说明同一批次与口径；模型读写时长、重试次数需另从实际执行日志测量。
- 旧 workspace 可继续恢复但不会被自动改写为新视图；要使用优化路径，基于未变化的 manifest 新建独立 workspace。历史分析用于回归时明确标记回放，不冒充新分析。
