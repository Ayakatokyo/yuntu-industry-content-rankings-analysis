# 云图详情 CSV 与第三章脚本洞察完善实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在保留现有 CSV 解析、连接器和五章报告结构的前提下，兼容当前扁平详情 CSV，并用可审计的脚本/内容公式事实补齐 03｜脚本洞察。

**Architecture:** 继续使用 `rpa_io.parse_csv_records()` 完成 CSV 到 Python 对象的转换；在 `yuntu_normalizer.py` 内同时兼容旧版 `trends/scriptText/contentFormula` 结构和当前 `coreData.* / secondTrend.* / contentFormula.* / creativeBreakdown.*` 扁平结构。新增脚本事实包作为章节 03 的唯一输入，事实层只做字段整理与确定性统计，模型负责脚本机制、改写方向和验证建议，渲染器只展示已校验结果。

**Tech Stack:** Python 3、标准库 `json/csv/ast/statistics`、现有 unittest、现有分析 Schema、离线 Markdown/HTML 报告渲染器。

**Spec:** `docs/superpowers/specs/2026-09-04-yuntu-detail-csv-script-insights-design.md`、`SKILL.md`、`docs/superpowers/specs/2026-08-14-yuntu-ai-report-depth-design.md`

## Global Constraints

- 不新建独立 CSV 导入脚本；复用 `parse_csv_records()`，只扩展现有规范化器。
- 原始字段保留原文；OCR 清洗只能作为新增分析字段，不能覆盖证据。
- 没有时间戳脚本段落时，不生成帧-话术对应关系，也不把脚本结论外推为 TOP1000 行业结论。
- 没有榜单列表、上一周期或行业大盘时，03 章范围必须标记为“已获取详情素材”，不得伪造排名或基准。
- 所有模型结论必须引用事实包中的素材 ID、脚本/公式字段、标签或确定性统计；缺失时输出“数据不足以判断”。
- 详情 CSV 中 `convertCnt` 与 `orderCnt` 保持分离，不能把 `convertCnt` 直接解释为订单数。

### Task 1: 兼容扁平详情 CSV 的现有规范化器

**Files:**
- Modify: `scripts/yuntu_normalizer.py`
- Test: `tests/test_yuntu_normalizer.py`
- Test: `tests/test_rpa_io.py`

**Interfaces:**
- Consumes: `parse_csv_records()` 返回的详情字典。
- Produces: 与现有 `normalize_detail_records()` 相同的标准字段，并补充 `source_schema`、脚本和内容公式可用性信息。

- [ ] **Step 1: 写失败测试**

测试当前扁平 CSV 字典应能得到：`date_range.type == "LAST_7_DAYS"`、5 条 `trend_series`、`script_text`、`content_formula`、`creative_breakdown`，并断言 `7659409261740343346` 的两份文件指标一致但 URL 可保留为版本差异。

- [ ] **Step 2: 运行测试确认失败**

运行：`python -m unittest tests.test_yuntu_normalizer -v`

预期：当前实现因为读取不到顶层 `trends`、`scriptText` 和 `contentFormula`，趋势与脚本字段为空。

- [ ] **Step 3: 实现兼容分支**

在 `normalize_detail_records()` 中增加扁平结构识别，并使用私有函数：

```python
def _flat_detail_trends(raw): ...
def _flat_content_formula(raw): ...
def _flat_creative_breakdown(raw): ...
```

`_flat_detail_trends()` 将 `secondTrend.<指标>.tendList` 映射为 `trend_name/series/high_point/loss_point`；缺少 `流失指数.highPoint` 时标记不可用，不补点。`_flat_content_formula()` 保留 `labels` 和动态 `detail.*` 键；`_flat_creative_breakdown()` 保留原始标签字符串及按顿号拆分后的可分析标签。

- [ ] **Step 4: 回归旧结构和当前结构**

运行：`python -m unittest tests.test_rpa_io tests.test_yuntu_normalizer tests.test_yuntu_batch -v`

- [ ] **Step 5: 提交规范化兼容改动**

```bash
git add scripts/yuntu_normalizer.py tests/test_rpa_io.py tests/test_yuntu_normalizer.py
git commit -m "feat: normalize flat yuntu detail csv schema"
```

### Task 2: 建立第三章脚本事实包

**Files:**
- Modify: `scripts/yuntu_analysis.py`
- Modify: `scripts/yuntu_presentation.py`
- Test: `tests/test_yuntu_analysis.py`
- Test: `tests/test_yuntu_presentation.py`

**Interfaces:**
- Consumes: `normalized/detail-records/*.json` 与已选素材清单。
- Produces: `analysis-units/script-input.json` 及 presentation 层的 `scriptDashboard`。

- [ ] **Step 1: 写事实边界测试**

测试覆盖：3/5 个唯一素材有脚本文本；2 个素材脚本缺失；没有时间戳段落；公式标签和创意拆解按素材去重统计；事实包标注 `scope="selected_detail_materials"`，不输出行业排名或脚本与高光帧的关联。

- [ ] **Step 2: 实现确定性事实构建**

新增纯函数：

```python
def build_script_facts(details, selected_materials): ...
```

输出每个素材的 `material_id`、`script_text`、`script_segments` 可用性、`content_formula`、`creative_breakdown`、`metrics` 引用和 `data_availability`；同时输出脚本覆盖数、公式标签频次、卖点/场景/营销形式频次。只统计源字段，不从标题或趋势推造脚本。

- [ ] **Step 3: 接入事实包清单**

在 `analysis-unit-manifest.json` 增加 `script-input.json`，并在 `report-data.json` 保存脚本事实投影。保留旧批次缺少该文件时的兼容读取路径。

- [ ] **Step 4: 验证事实层不生成业务结论**

运行：`python -m unittest tests.test_yuntu_analysis tests.test_yuntu_presentation -v`

断言事实包只包含统计、原文和可用性，不包含“有效”“导致”“提升”等业务判断。

### Task 3: 扩展单次 AI 分析契约，加入脚本洞察

**Files:**
- Modify: `prompts/yuntu-analysis-prompt.md`
- Modify: `scripts/yuntu_analysis.py`
- Modify: `scripts/yuntu_report.py`
- Test: `tests/test_yuntu_analysis.py`
- Test: `tests/test_yuntu_report.py`

**Interfaces:**
- Consumes: `script-input.json` 与其 Schema。
- Produces: `scriptInsights`，由 `title`、`summary`、`evidence`、`material_ids` 组成。

- [ ] **Step 1: 写契约测试**

拒绝缺少素材 ID 证据、把脚本与点击/转化写成因果、声称存在时间戳对应关系、或在脚本覆盖不足时使用“行业普遍”表述的 AI 输出。

- [ ] **Step 2: 增加脚本输入和输出 Schema**

在同一次模型调用中读取脚本事实包；`scriptInsights` 只分析已获取详情素材。要求模型分别覆盖：开场/钩子结构、信任或证明表达、卖点与场景组合、促销/行动表达、可测试改写方向。每条结论必须绑定 `material_ids`，不得把 `contentFormula` 标签当作自然发生的因果证据。

- [ ] **Step 3: 明确时间戳缺失降级**

提示词明确：当前 CSV 没有 `scriptSegments` 时只能做整段文本和公式结构分析；不得把某句脚本映射到某个秒点或高光帧。脚本为空时输出可用性说明和“数据不足以判断”。

- [ ] **Step 4: 运行分析与报告校验测试**

运行：`python -m unittest tests.test_yuntu_analysis tests.test_yuntu_report -v`

### Task 4: 将 03 章接入 Presentation 与 HTML

**Files:**
- Modify: `scripts/yuntu_presentation.py`
- Modify: `scripts/yuntu_report_sections.py`
- Modify: `scripts/yuntu_report.py`
- Modify: `scripts/templates/final-report-template.html`
- Test: `tests/test_yuntu_presentation.py`
- Test: `tests/test_yuntu_report.py`

**Interfaces:**
- Consumes: 已验证 `scriptDashboard` 与 `scriptInsights`。
- Produces: 03 章自然段洞察、脚本事实统计、缺失状态和单素材脚本分析 Tab。

- [ ] **Step 1: 替换固定占位文案**

将 `render_script_insights()` 改为接收脚本事实和 AI 投影；没有脚本事实时仍展示明确的不可用状态，不生成规则化结论。

- [ ] **Step 2: 增加范围与证据展示**

03 章显示“已获取详情素材”范围、脚本覆盖数、公式/卖点/场景汇总，并在 AI 正文下保留素材证据入口。不得显示为 TOP1000 行业脚本规律。

- [ ] **Step 3: 接入第五章脚本 Tab**

第五章脚本 Tab 展示原始脚本、内容公式和创意拆解；无时间戳时显示“未提供脚本时间段，暂不输出帧-话术对应关系”。

- [ ] **Step 4: 渲染回归**

运行：`python -m unittest tests.test_yuntu_presentation tests.test_yuntu_report -v`，并检查无脚本文本的素材不会出现空白卡片或推测性话术。

### Task 5: 用 6 份真实 CSV 做本地回归，不接入新连接器

**Files:**
- Read: `RPA数据汇总/industry_content_rankings_details_*.csv`
- Modify: `tests/fixtures/`（仅加入去除时效 URL 的最小样本）
- Test: `tests/test_yuntu_csv_regression.py`

**Interfaces:**
- Consumes: 当前 6 份真实详情 CSV 的字段结构。
- Produces: 可重复的规范化、事实包和报告渲染回归结果。

- [ ] **Step 1: 固化样本断言**

断言 6 文件、5 唯一素材、1 个重复素材；趋势序列长度与视频时长关系；脚本文本覆盖、内容公式覆盖和空字段比例；`convertCnt` 与 `orderCnt` 分离。

- [ ] **Step 2: 运行完整测试**

运行：`python -m unittest discover -s tests -q`、`python -m compileall -q scripts tests`、`git diff --check`。

- [ ] **Step 3: 更新技能说明**

在 `SKILL.md` 和连接器引用文档中说明：详情规范化同时兼容两种字段结构；03 章脚本洞察只在脚本文本或内容公式可用时生成；没有榜单列表时不生成行业脚本结论。

- [ ] **Step 4: 提交回归与文档**

```bash
git add SKILL.md references/connectors/juliang-yt tests/fixtures tests/test_yuntu_csv_regression.py
git commit -m "feat: add script insight regression for detail csv"
```
