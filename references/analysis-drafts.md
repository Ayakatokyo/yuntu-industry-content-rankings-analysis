# 从事实包到模型草稿再到报告

在安装了技能 `requirements.txt` 的 Python 环境运行。全部命令都是本地文件操作，不调用模型或下载资产。

1. `begin-analysis --fact-pack-json <analysis-unit-manifest.json> --workspace <新目录>` 验证事实、提示词、Schema 和成功资产，创建 `workspace.json`、四个章节草稿、各品牌脚本草稿及每个素材的草稿。再次运行同目录只验证恢复，不覆盖已有草稿。
2. 模型先读提示词和对应章节事实，再读同名 `.task.json`。task 中的 `factInput` 相对于 manifest 所在 `analysis-units` 的上一级目录；它是正式事实来源。task 只含确定性的结构、合法引用与约束，不含业务答案。
3. 模型直接编辑草稿的 `content`，保持 `binding` 原样。章节 content 是顶层字段对象，例如 `{"chapter02Insights": {...}}`；单素材 content 是 `{"material_id": "...", "scriptAnalysis": {...}, "frame_observations": [...]}`。初始 `null` 表示未完成，不是可交付内容。可多次保存；不要把文字先写入 Python 常量或用品牌/帧序号模板生产正文。
4. 实际逐张看图后，记录 `highlight.json.viewedFrameRefs`。即使图片无法可靠理解，也记录已查看引用并在理解结果中写 unavailable 和原因；未成功落盘的图片不进入此清单。两套分类各自独立覆盖成功帧，每帧一次。
5. `check-analysis --workspace <目录> --part material-<ID>` 可检查刚写完的一份；不带 `--part` 汇总所有草稿的错误；各部分通过后会同时检查完整组装值，提前发现跨部分契约问题。结果写入 `validation.json`，失败返回非零退出码。结果包含草稿、字段路径、结构错误及章节语义门禁错误；同一段的语义门禁仍可能先报告最先命中的规则，结构和独立草稿错误会合并呈现。
6. 完整检查通过后运行 `assemble-analysis --workspace <目录> --output <新JSON文件>`。程序复制原始草稿到 `<文件名>.drafts/<SHA256>.json`，无损合并，复用报告校验并生成 `<文件名>.assembly.json`。已有输出不覆盖；修改草稿后使用新的输出文件名。快照保留原始字节，后续修改工作草稿不影响此前快照；改写快照会导致验证失败。
7. 按 SKILL.md 的命令 attest，再 render。两者都加载相同的 manifest 绑定事实；第二章范围来自 `audience-marketing-input.json`，第五章脚本引用来自 `material-deep-dive-input.json`，不会从图表范围或另一章拼凑引用。render 的显式事实路径必须与已证明的渲染事实一致。

新 `analysisContract` 批次要求组装收据；没有该字段的历史批次仍支持原来已签名 JSON 的重渲染，并回填正式章节事实进行校验。历史 JSON 可用于离线回归，但不能改称本轮重新分析。重新准备事实或修改提示词后需新建草稿目录，不能迁移旧绑定。

`model_generated`、`generator`、`viewedFrameRefs` 是执行者声明。收据可验证文件未变及正文无损组装，不能证明模型身份、真实看图或每条业务判断正确；模型调用或看图行为仍需对话执行日志佐证。

第三章品牌草稿的 key 为 `script-brand-<index>`，对应品牌由 task 明确给出。content 与全量脚本一样包含 scriptInsights、keywordCloudReview、keywordCloudInsight，由组装器无损收进 scriptBrandInsights[品牌]。task 提供该品牌独立统计的正文、公式和关键词；正文缺失时保持证据为空并说明数据不足，不能套用全量分析。
