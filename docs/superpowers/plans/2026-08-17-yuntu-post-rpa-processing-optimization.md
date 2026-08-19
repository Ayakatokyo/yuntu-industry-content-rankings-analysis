# 云图 RPA 落盘后处理优化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按技能真实执行顺序，逐步优化 RPA 数据落盘后的质量门禁、事实包、视觉资产、AI 分析契约、展示投影和最终报告渲染，并保证每一步都能独立回归。

**Architecture:** 保留现有 RPA 采集和原始/规范化落盘结构，以 `normalized/` 作为后处理唯一输入边界。将后处理明确拆为“输入门禁 -> 事实包与高光资产 -> AI 分析 -> provenance -> presentation -> report rendering”六个可验收阶段；每个阶段只消费上游已验证产物，不跨层读取原始 CSV 或临时 RPA 响应。

**Tech Stack:** Python 3、标准库 JSON/Path、现有 unittest、HTML 静态模板、离线 JavaScript、SHA-256 provenance。

---

### Task 1: 建立落盘后输入门禁

**Files:**
- Modify: `scripts/rpa_connector.py`（`status` / `prepare-analysis` 分发前）
- Modify: `scripts/yuntu_run_state.py`（复用现有 artifact 校验）
- Create: `scripts/yuntu_post_rpa_gate.py`
- Test: `tests/test_yuntu_post_rpa_gate.py`

- [ ] **Step 1: 写失败测试，覆盖批次状态、契约和必需文件**

测试必须验证：`run-summary.json`、`batch-manifest.json`、`normalized/list-records.json`、`normalized/detail-request-params.json` 存在且非空；批次契约可验证；列表上下文已校验；详情文件与 `selectedMaterials[].detailRecordPath` 一一对应；不满足条件时禁止进入 `prepare-analysis`。

- [ ] **Step 2: 运行门禁测试确认失败**

运行：

```bash
python -m unittest tests.test_yuntu_post_rpa_gate -v
```

预期：新测试因门禁模块或函数尚不存在而失败。

- [ ] **Step 3: 实现纯本地门禁函数**

在 `scripts/yuntu_post_rpa_gate.py` 提供：

```python
def validate_post_rpa_inputs(input_dir) -> dict:
    """Return verified batch inputs or raise a local validation error."""
```

函数只读取本地文件，返回批次状态、候选数、成功详情数、拒绝数和可继续处理的详情路径；不得访问网关，不得修改批次文件。

- [ ] **Step 4: 接入 `prepare-analysis` 前置检查**

在 `scripts/yuntu_analysis.py:506` 的 `prepare_analysis` 开头调用门禁；错误信息必须指出具体缺失文件、状态或契约问题。

- [ ] **Step 5: 运行门禁和既有分析测试**

```bash
python -m unittest tests.test_yuntu_post_rpa_gate tests.test_yuntu_analysis -v
```

预期：全部通过；门禁失败不得创建 `yuntu-analysis-data.json`。

---

### Task 2: 将 `prepare-analysis` 的事实构建拆成稳定阶段

**Files:**
- Modify: `scripts/yuntu_analysis.py:506-660`
- Modify: `scripts/yuntu_normalizer.py`
- Test: `tests/test_yuntu_analysis.py`
- Test: `tests/test_yuntu_normalizer.py`

- [ ] **Step 1: 为事实包输入输出写契约测试**

覆盖四个边界：榜单事实只来自完整 `list-records.json`；品牌 Top N 只来自同一榜单池；秒级事实只来自成功详情；缺失指标/标签/趋势必须写入 `dataAvailability` 或 `dataLimitations`，不能补造数值。

- [ ] **Step 2: 运行测试确认新增边界失败**

```bash
python -m unittest tests.test_yuntu_analysis tests.test_yuntu_normalizer -v
```

- [ ] **Step 3: 抽取三个纯函数并保持现有字段兼容**

在 `yuntu_analysis.py` 明确形成：

```python
def build_ranking_facts(list_records, *, brand_top_n, brands): ...
def build_detail_facts(list_records, selected, rejected, input_dir): ...
def build_model_input(ranking_facts, detail_facts, filters): ...
```

现有 schema v4 字段必须继续输出，新增字段只能作为向后兼容扩展。

- [ ] **Step 4: 运行事实包回归**

```bash
python -m unittest tests.test_yuntu_analysis tests.test_yuntu_top_materials tests.test_yuntu_normalizer -v
```

预期：现有事实字段、范围口径和缺失数据表达不变。

---

### Task 3: 独立化高光帧后处理状态

**Files:**
- Modify: `scripts/yuntu_highlights.py`
- Modify: `scripts/yuntu_analysis.py`
- Modify: `scripts/yuntu_batch.py`（只保留已成功详情后的触发和状态回写）
- Test: `tests/test_yuntu_highlights.py`
- Test: `tests/test_yuntu_batch.py`

- [ ] **Step 1: 写高光帧状态测试**

覆盖：完整帧集复用、单帧失败、无视频 URL、FFmpeg 失败、帧清单与详情素材 ID 不一致；失败必须只影响对应素材的 `highlightFrameAvailability`。

- [ ] **Step 2: 运行测试确认新增状态断言失败**

```bash
python -m unittest tests.test_yuntu_highlights tests.test_yuntu_batch -v
```

- [ ] **Step 3: 明确 `highlights-manifest.json` 为唯一帧状态源**

`prepare-analysis` 不重新推导已经完整的帧；仅对缺失或不完整素材补处理，并把每个帧的 `available`、`failure_reason`、`frame_ref`、来源路径写入 manifest。

- [ ] **Step 4: 运行高光帧回归**

```bash
python -m unittest tests.test_yuntu_highlights tests.test_yuntu_analysis tests.test_yuntu_batch -v
```

---

### Task 4: 固化 AI 二次分析输入与输出契约

**Files:**
- Modify: `scripts/yuntu_analysis.py`（提示词和模型输入段）
- Modify: `scripts/yuntu_report.py`（AI JSON 校验）
- Test: `tests/test_yuntu_analysis.py`
- Test: `tests/test_yuntu_report.py`

- [ ] **Step 1: 为八个基础键、证据引用和数据范围写契约测试**

AI JSON 必须包含 `topMaterialCombination`、`rankingOverview`、`audienceInsights`、`materialComparison`、`materialDiagnoses`、`competitorPatterns`、`opportunityMap`、`experimentMatrix`；每条洞察必须引用事实包中存在的素材 ID、指标、秒级点或 `frame_ref`。

- [ ] **Step 2: 运行 AI 契约测试确认缺失输出被拒绝**

```bash
python -m unittest tests.test_yuntu_report -v
```

- [ ] **Step 3: 收敛提示词中的数据边界**

明确禁止模型读取原始 CSV、使用详情素材替代 Top1000 榜单结论、从截图补写事实、把点击指数称为真实点击次数、把共现关系写成因果关系。

- [ ] **Step 4: 运行分析和报告契约回归**

```bash
python -m unittest tests.test_yuntu_analysis tests.test_yuntu_report tests.test_yuntu_presentation -v
```

---

### Task 5: 强化 provenance 与渲染前门禁

**Files:**
- Modify: `scripts/yuntu_analysis_provenance.py`
- Modify: `scripts/rpa_connector.py:871-910`
- Test: `tests/test_rpa_connector.py`
- Test: `tests/test_yuntu_analysis_provenance.py`

- [ ] **Step 1: 写回执篡改和来源类型测试**

覆盖：分析 JSON、事实包、提示词任一改变后哈希不匹配；`programmatic_fallback` 永远拒绝；回执路径必须位于当前诊断目录或明确的受控路径。

- [ ] **Step 2: 实现严格加载和错误分类**

把“缺回执”“回执格式错误”“哈希不一致”“来源不允许”分别返回可诊断错误，不触碰报告输出目录。

- [ ] **Step 3: 运行 provenance 回归**

```bash
python -m unittest tests.test_rpa_connector tests.test_yuntu_analysis_provenance -v
```

---

### Task 6: 优化 Presentation 与最终报告渲染

**Files:**
- Modify: `scripts/yuntu_presentation.py`
- Modify: `scripts/yuntu_report.py`
- Modify: `scripts/yuntu_report_sections.py`
- Test: `tests/test_yuntu_presentation.py`
- Test: `tests/test_yuntu_report.py`

- [ ] **Step 1: 写事实层与 AI 层分离测试**

图表、标签、趋势、帧元数据只能来自事实包；AI 文本只能来自已验证分析 JSON；presentation 不得补写结论。

- [ ] **Step 2: 保持现有五章和离线资产路径兼容**

继续输出 `final-report.html`、`final-report.md`、`final-report-data.json`、`presentation-report.json`，高光图片只复制当前批次本地资产。

- [ ] **Step 3: 运行完整后处理回归**

```bash
python -m unittest discover -s tests -v
```

预期：所有测试通过，且报告渲染拒绝无证据或越界路径。

---

### Task 7: 使用真实批次逐阶段验收

**Files:**
- Read: `RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict/`
- Read: `docs/20260809_云图真实流程执行复盘.md`

- [ ] **Step 1: 运行 `status`，确认只读状态和输入契约**
- [ ] **Step 2: 运行 `prepare-analysis`，核对事实包范围、缺失状态和高光清单**
- [ ] **Step 3: 核对模型分析 provenance，不重新调用 RPA**
- [ ] **Step 4: 运行 `render-report`，核对四个非空报告产物**
- [ ] **Step 5: 检查 HTML 的本地图片引用和五个章节结构**
- [ ] **Step 6: 在桌面与移动宽度检查首屏、02 章、04 章、05 章的溢出和空白**

每阶段保留命令输出、产物清单和 SHA-256；任何阶段失败都停止向后推进。

---

## 实施顺序与第一批范围

第一批只实施 **Task 1：落盘后输入门禁**。它风险最低、不会改变业务结论或报告样式，却能为后续所有优化提供稳定边界。Task 1 通过后，再进入 Task 2 的事实包拆分；不要同时修改 AI prompt、presentation 和 HTML，以免无法判断问题来源。
