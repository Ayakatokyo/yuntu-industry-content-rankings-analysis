# 2026-09-12 重跑报告的四项修复

本次依据 `work/latest-flow-20260912/input-batch/final-report-rerun/final-report.html` 和同批分析 JSON 修复。原报告、事实与资产保留；新报告位于 `work/report-fixes-20260912/input-batch/final-report/`，ZIP 位于其同级。没有启动 RPA、外部模型或实际浏览器，没有提交或推送 Git。

## 原因与改动

| 用户反馈 | 已确认原因 | 修复 |
| --- | --- | --- |
| 02、03、04 分析缩水 | 新模型 JSON 自身过短，渲染未截断；原门禁缺少充分性底线 | 增加 `analysisQualityVersion=2`，在生成 Schema、草稿 task 和提示词中前置同一要求；有事实的段落包含观察、业务含义、建议及验证边界。02/03 主摘要最低 180 字，04 标准分类共性与方向分别最低 100 字。无事实走明确缺失分支，不填充正文。 |
| 04 只有所有指定品牌 | 模型只输出全品牌，校验仅检查已提供的品牌 | 固定全品牌及指定品牌顺序和范围，非空品牌只覆盖本品牌成功帧；无帧品牌必须给出缺失原因，并在报告中保留入口。动态主题仍只分类。 |
| 05 公式联动整段文案 | 自动句子全部挂到第一条公式，投影遗漏 `sources.script.detail`，按相同一级或二级标签宽泛匹配 | 分离分析句子引用与交互词句目标；读取脚本专属词条，按精确公式索引连接。重叠词保留各自引用；没有对应词句的按钮禁用且解释原因，不再指向缺失区域。 |
| 03 新增品牌筛选及品牌分析 | 原来只有全量脚本事实和正文 | 生成 `scriptFacts.brandScopes`，各品牌重新统计公式与关键词；新增独立 `script-brand-<index>` 草稿，无损组装为 `scriptBrandInsights`。品牌切换同步正文、关键词和公式分布，各面板使用独立 DOM ID。 |

稳定性补充：完整 `check-analysis` 现在也检查合并后的分析值，将跨部分错误提前到草稿阶段。准备命令新增 `--local-only`，本地续跑不下载缺失视频。当前报告 Schema 与 canonical renderer facts 重新生成的 Schema 已逐字段验证一致。

`yuntu_analysis_quality.py` 集中维护新版本的可机器检查要求；历史事实包不追溯强制新字段。段落长度只是结构底线，不能证明事实正确或分析质量；模型仍须阅读本范围事实和图片，不允许业务正文生成脚本。

## 本次真实批次验证

- 10 条选中详情中有 4 条脚本文本：喜纯 2/5，九阳豆浆 2/2；另外四个指定品牌未进入详情集合，独立显示数据不足。全量仍覆盖全部选中详情，不能将标题未匹配到品牌的详情强行归入品牌。
- 重新阅读第二章各 scope 和四条正文，查看全部 37 张成功 JPEG，直接撰写 02、03、04 的受影响正文。第二章同时纠正旧摘要遗漏 36–40 岁、万益蓝成熟职场与男女性别结构的问题。
- 02 的 14 段摘要由 45–61 字变为 240–262 字；03 全量及两个有正文品牌的 6 段为 234–262 字；04 标准分类共性/方向的 16 段为 146–166 字。没有把全量结论复制到品牌。
- 保留未经本次请求改变的第一章、单素材分析与逐帧观察，以及原有逐帧理解/两套分类记录；新模型正文和复用范围记录在 `analysis-reuse.json`。不把局部重写宣称为五章全部重新分析。
- 20 份草稿首次分段检查通过，没有为过门禁反复改写业务正文。首次组装暴露出紧凑报告事实没有 `visualAssets` 时重新生成 Schema 遗漏高光字段的问题，已修复并新增测试。随后统一提示词的章节范围措辞，使用相同事实、相同正文创建最终绑定和 assembly；没有改写旧收据。
- 最终 `assemble-analysis → attest-analysis → render-report` 通过。验收 JSON 记录源批次 245 文件哈希不变，ZIP 的 50 个条目与报告目录逐字节一致，含 Excel、图片和视频。

## 自动化验收

- 新增 12 个回归测试：充分性、空范围、品牌必填、跨品牌/跨来源引用、精确公式联动、面板隔离和草稿无损组装。
- 全套 382 tests：380 通过、1 跳过、1 原有失败。原有失败为 `test_shared_style_defines_text_card_and_control_contract`，期待 CSS 字面值 `grid-template-columns: repeat(auto-fit, minmax(112px, 1fr));`；修改前即存在，本轮没有调整无关 CSS。
- CLI `self-test` 通过；Python 编译和 `git diff --check` 通过。
- `tests/verify_report_interactions.py` 从本次实际 HTML 提取结构和 JavaScript，在 Node 环境检查：03/04 各 7 个品牌入口的切换；03 键盘操作；20 个公式按钮，其中 16 个精确定位、4 个无源词句而禁用；无重复 ID、无失效控制目标、本地资源齐全、JavaScript 语法有效。此检查不声称做过浏览器视觉验收。
- 对真实分析注入短摘要、缺脚本品牌、跨品牌脚本 ID、缺高光品牌四类错误，全部被门禁拒绝。

结果记录：`work/report-fixes-20260912/verification/acceptance.json`、`interactions.json`、`all-tests.log`、`attest-final.log`。最终绑定及原始草稿快照位于 `input-batch/diagnostic-analysis-final/`。

复验命令（使用已安装 requirements 的 Python）：

```bash
python -m unittest discover -s tests
python tests/verify_report_interactions.py work/report-fixes-20260912/input-batch/final-report/final-report.html work/report-fixes-20260912/verification
python scripts/rpa_connector.py check-analysis --workspace work/report-fixes-20260912/input-batch/diagnostic-analysis-final/model-drafts
```
