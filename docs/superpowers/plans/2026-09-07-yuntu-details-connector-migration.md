# 云图素材详情连接器直接替换执行方案

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 当前仅交付方案，待新连接器正式上线后执行；不启动实现或子代理。

**Goal:** 新连接器上线后，以 `rpa.conn.juliang.yt.industry.content.rankings.details` 直接替换当前详情连接器，完成异步采集、文件规范化、恢复和报告验收。

**Architecture:** 在当前技能内复用批次调度、文件解析、事实包与报告链路；列表/详情共用异步提交和轮询，调度主线程负责状态及产物写入。新采集只用新详情连接器，旧格式仅用于历史读取，不提供双路由或自动回退。

**Tech Stack:** Python 3、requests、标准库 json/csv/ast/concurrent.futures/unittest、现有分析与离线报告脚本。沿用现有依赖；不为复用工具包调用方式引入外部脚本子进程或全套工具包运行依赖。

**Spec:** [云图素材详情连接器直接替换设计方案](../specs/2026-09-07-yuntu-details-connector-migration-design.md)

## Global Constraints

- 新详情唯一代码：`rpa.conn.juliang.yt.industry.content.rankings.details`；列表代码：`rpa.conn.juliang.yt.industry.content.rankings.list`。
- platform 固定 `RPA_JULIANG_YT_ACCOUNT_PASSWORD`，data_source_type 固定 `rpa`，不接受外部 function_code。
- 新详情业务周期字段为 `date_type`；CLI 保留 `--detail-date-range-type` 并在边界转换。
- HTTP 单次 30 秒，内部轮询 10 秒，单任务等待窗口最多 3600 秒；详情并发 3，高光并发 3。
- 新批次 schemaVersion 为 4，normalization_version 为 2；旧批次只读兼容，不能向旧目录发起新请求。
- 同一输出目录仅一个 writer；工作线程不写共享 manifest；status 保持纯本地只读。
- 新连接器正式上线前，本计划不执行代码替换或线上采集。
- 原始样本、历史 normalized、报告和 ZIP 不原地覆盖；新验证使用独立目录。
- 模型分析只用已落盘事实；第五章脚本证据限本素材脚本域，无时间戳不建立秒点/帧与话术对应。
- 任务已提交、HTTP 成功或拿到 fileUrl 都不等于迁移成功。
- 不修改参考工具包仓库；不自动发布、推送或创建监控。提交/发布在届时授权范围内进行。

## 0. 执行约定与文件地图

以下命令均在技能根目录执行。先阅读设计方案，再逐任务实现。每任务先增加能复现缺口的测试，确认失败原因，再实现并验证；本计划代码块是接口或关键断言示例，非已实现代码，不应把计划中的示例任务 ID 当作真实记录。

| 阶段 | 主要文件 | 可独立验收的产出 |
| --- | --- | --- |
| Task 1 | 正式资料、fixtures、执行记录 | 上线契约及样本基线 |
| Task 2 | rpa_connector、connector 测试 | 唯一新路由、日期验证、异步网络接口 |
| Task 3 | rpa_io、IO 测试 | 完整终态与多文件识别 |
| Task 4 | normalizer、normalizer 测试 | 新旧数据同构、来源与周期校验 |
| Task 5 | run_state、batch 及测试 | v4 账本、异步调度、恢复和物化 |
| Task 6 | analysis、presentation、report 及测试 | 事实与脚本证据消费者兼容 |
| Task 7 | SKILL、连接器知识页、协议回归 | 活动知识路由同步和离线闭环 |
| Task 8 | 独立 RPA 输出、执行记录 | 线上冒烟、小批次、报告与完成证据 |

未来执行时创建记录文件 `docs/handoffs/2026-09-07-yuntu-details-connector-migration-execution.md`；文件名标识本方案，正文填写实际执行日期，不暗示 9 月 7 日已上线。记录分段：正式契约、代码变更、各任务检查、离线回放、线上任务与产物、发布范围、剩余问题。

## Task 1：核对正式上线契约并固定测试依据

**Files:**
- Read: 设计方案 §2.1 指定的新旧连接器文档。
- Read: `/Users/shuzida/Desktop/yuce-plugin/查数工具包/skills/预策RPA连接器取数/` 中正式的新知识页和对应脚本；先从平台地图定位，不猜脚本存在。
- Create at execution: `tests/fixtures/yuntu_details_v2/nested-detail.json`。
- Create at execution: `tests/fixtures/yuntu_details_v2/flat-detail.csv`。
- Create at execution: `tests/fixtures/yuntu_details_v2/async-completed.json`、`async-partial.json`。
- Create at execution: 上述执行记录。

**Interfaces:** 消费正式 schema 与已授权的协议样例；产出只含合成身份及非敏感数据的 fixture，以及正式版本来源记录。

- [ ] **1.1 核对仓库与当前指令。** 检查工作区是否已有其他变更，记录分支和基准版本。已有变更不清理、不混入迁移；需要隔离时按当前项目规则创建 `codex/` 分支/worktree。

```bash
git status --short
git branch --show-current
git rev-parse HEAD
command -v python3
```

- [ ] **1.2 核对正式上线证据。** 记录正式上线状态来源与查证时间、新代码、platform、schema、异步端点和文件字段。仍未上线则保持本任务未完成，交付记录注明“等待正式上线”；不尝试替换生产调用。
- [ ] **1.3 比较正式契约与设计快照。** 若业务键不再是 date_type、终态枚举或文件结构发生变化，先在本设计和本计划统一修订，并新增真实结构测试；不绕过差异继续采集。
- [ ] **1.4 固定最小合成数据。** 保留五类曲线、零值、空脚本、来源域标签重复和中文字段；素材 ID 使用纯数字字符串。文件 URL 使用 `https://example.invalid/`。保留真实字段类型，不把列表单元格简化成无法覆盖 CSV 的纯文本。

嵌套 fixture 的关键结构如下，生成时五类指数分别配置 trendType 1–5：

```python
names = ["点赞指数", "流失指数", "点击指数", "互动指数", "评论指数"]
record = {
    "materialId": "101", "dateType": "LAST_7_DAYS",
    "customStartDate": None, "customEndDate": None,
    "videoUrl": "https://example.invalid/101.mp4",
    "coreData": {"objectId": "101", "title": "测试素材", "videoDuration": 2,
                 "convertCnt": "17", "orderCnt": "3", "showCnt": "90-100w"},
    "audiencePortrait": {"八大人群": ["新锐白领"], "年龄特征": [], "性别特征": ["女"]},
    "secondTrend": {name: {"trendType": i, "tendList": [{"x": 0, "y": 0}, {"x": 1, "y": 1}],
                           "highPoint": None, "lossPoint": None}
                    for i, name in enumerate(names, 1)},
    "contentFormula": {
        "本视频内容公式": {"labels": [{"level_1_label": 10, "level_2_labels": [40]}]},
        "视频标题": {"text": "标题词", "detail": {"40": ["标题词"]}},
        "视频画面": {"text": "画面词", "detail": {"40": ["画面词"]}},
        "视频脚本": {"text": "脚本词", "detail": {"40": ["脚本词"]}}
    },
    "creativeBreakdown": {"使用场景": ["早餐"], "营销活动": []}
}
```

- [ ] **1.5 验证 fixture。** 以 `json.loads()` 读取 JSON，以现有 `parse_csv_records()` 读取 CSV，确认纯数字字符串 ID、零值、空数组和中文标签类型未改变。记录脱敏方式，不复制凭证或视频签名 URL 到版本库。

**完成条件：** 正式上线状态可验证，schema 差异已处理，夹具真实反映该版本协议。A10 线上成功证据要到 Task 8 才能勾选，不能在这里预填。

## Task 2：固定新连接器请求及异步网络接口

**Files:** Modify `scripts/rpa_connector.py`；Test `tests/test_rpa_connector.py`。

**Interfaces:**
- `validate_detail_business_params(raw_params) -> dict`：只返回 material_id、date_type 及必要日期。
- `submit_fetch_task(operation, shop_id, business_params, *, environ=None, session=None) -> str`。
- `query_fetch_task(task_group_id, *, environ=None, session=None, request_timeout_seconds=30) -> dict`。
- `wait_fetch_task(task_group_id, *, environ=None, session=None, timeout_seconds=3600, poll_interval_seconds=10) -> dict`。
- `fetch_batch_analysis()` 的 raw_detail_params 从本任务起使用 date_type。

- [ ] **2.1 添加路由与参数失败测试。** 在现有 RpaConnectorTest 中加入：

```python
def test_new_detail_params_and_code(self):
    c = self.connector()
    self.assertEqual(c.DETAIL_FUNCTION_CODE,
                     "rpa.conn.juliang.yt.industry.content.rankings.details")
    self.assertEqual(c.validate_detail_business_params({
        "material_id": "101", "date_type": "LAST_7_DAYS"
    }), {"material_id": "101", "date_type": "LAST_7_DAYS"})
    with self.assertRaises(c.RpaConnectorError):
        c.validate_detail_business_params({"material_id": "101", "date_range_type": "LAST_7_DAYS"})
```

额外用 subTest 覆盖非法 ID、非法枚举、自定义缺日期、结束早于开始、非自定义携带日期、额外 selectionGroupId、两种日期格式等价。新增 CLI mock 测试验证旧参数名转换到新键，列表/详情周期冲突时提交次数为 0。

- [ ] **2.2 运行测试确认缺口。**

```bash
python3 -m unittest tests.test_rpa_connector -v
```

预期新增断言在旧代码或旧键处失败；其他既有失败单独记录，不将环境缺依赖当作功能失败。

- [ ] **2.3 收敛固定代码与业务键。** `_invoke()` 中的字面量路由移入唯一常量；删除生产旧同步请求分支。CLI 组装新键，内部 schema、self-test 和 detailDateRange 全部一致。保留运行时环境及 list-accounts 行为。

构造请求必须等价于：

```python
code = {"list": LIST_FUNCTION_CODE, "detail": DETAIL_FUNCTION_CODE}[operation]
payload = {
    "authorization": authorization,
    "agent_session_id": session_id,
    "data_source_type": DATA_SOURCE_TYPE,
    "platform": PLATFORM,
    "function_code": code,
    "business_params": business_params,
    "shop_id": shop_id,
}
```

- [ ] **2.4 实现提交、单次查询和等待。** 提交只发一次 POST，返回非空 task_group_id。查询严格检查 HTTP、网关 success 与 data 类型；等待用 monotonic 截止时间，单次 timeout 取 30 秒和剩余时间较小者。

```python
deadline = time.monotonic() + timeout_seconds
while True:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise RpaConnectorError(f"poll timeout: {task_group_id}")
    time.sleep(min(poll_interval_seconds, remaining))
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise RpaConnectorError(f"poll timeout: {task_group_id}")
    result = query_fetch_task(task_group_id, environ=environ, session=session,
                              request_timeout_seconds=min(30, remaining))
    status = result.get("status")
    if status in {"completed", "partial_success"}:
        return {**result, "task_group_id": task_group_id}
    if status == "failed":
        return {**result, "task_group_id": task_group_id}
    if status not in {"pending", "running"}:
        raise RpaConnectorError(f"unknown task status {status!r}: {task_group_id}")
```

查询使用剩余时间限制 HTTP；任何失败/超时异常带任务 ID 和错误类别，但不带凭证。failed 作为已知终态交给调度器持久化，区别于查询异常。调度器首次等待时传入从提交前起算的剩余窗口；恢复任务可开启新窗口但不重置原提交时间。提交的传输不确定错误由调度器标记 submit_unknown，不能通用重试 POST。

- [ ] **2.5 使用 RecordingSession 扩展为响应队列，测试请求内容与轮询。** 覆盖 pending→running→completed、partial、failed、未知状态、网关失败、缺任务 ID、查询超时；mock `time.sleep/monotonic`，测试不等待真实 10 秒或 1 小时。断言提交 URL 仅出现一次，后续全为 status，查询 body 不带 business_params。
- [ ] **2.6 重跑本模块并记录结果。** 新旧 CLI 参数边界、日期校验和所有网络状态均通过；不进行真实网络调用。

**完成条件：** A1/A2/A3 的连接器层测试通过。批次层暂在 Task 5 接入，不为让旧 FakeInvoker 暂时通过而保留生产旧路由。

## Task 3：支持异步终态及完整文件列表

**Files:** Modify `scripts/rpa_io.py`；Test `tests/test_rpa_io.py`；Fixtures Task 1 的异步终态。

**Interfaces:** `unpack_gateway_result(result) -> GatewayResult`；GatewayResult 的 files 为文件描述列表，records 为记录列表，另含 remote_status/errors/task_group_id。旧 file_url 属性只对单文件兼容。

- [ ] **3.1 写多文件和错误外壳测试。** 在现有 RpaIoTests 中加入：

```python
def test_async_terminal_preserves_all_files_and_errors(self):
    io = load_module()
    result = io.unpack_gateway_result({
        "status": "partial_success", "task_group_id": "task-101",
        "files": [{"fileUrl": "https://example.invalid/a.csv"},
                  {"fileUrl": "https://example.invalid/b.csv"}],
        "errors": [{"message": "another instance failed"}]
    })
    self.assertEqual(len(result.files), 2)
    self.assertEqual(result.remote_status, "partial_success")
    self.assertTrue(result.errors)

def test_unknown_success_wrapper_is_not_a_record(self):
    io = load_module()
    with self.assertRaises(io.RpaIoError):
        io.unpack_gateway_result({"success": True, "data": {"status": "mystery"}})
```

- [ ] **3.2 运行确认失败。** `python3 -m unittest tests.test_rpa_io -v`。
- [ ] **3.3 显式识别协议分支。** 先验证完整外壳再取 data；只接受已知终态。旧 files-envelope 保持可读，JSON payload 的单对象转一行。拒绝无业务结构的成功外壳、空 files、非法 URL 字段类型、非终态结果。

```python
if isinstance(payload, dict):
    records = [payload]
elif isinstance(payload, list) and all(isinstance(row, dict) for row in payload):
    records = payload
else:
    raise RpaIoError("payload must contain business objects")
```

payload 的业务身份由列表/详情规范化器最终验证；这里不能因 dict 类型正确就绕过下游身份检查。文件项字段若正式版本有差异，仅增加有夹具证据的显式分支。

- [ ] **3.4 更新下载/解析错误测试。** 验证 UTF-8 BOM、JSON/Python 字面量单元格、空行、零值、空文件、表头冲突和截断文件处理。继续复用现有安全解析，不使用 eval。
- [ ] **3.5 重跑模块。** 确认旧文件外壳、旧 payload、新单/多文件和 partial 错误均保留正确语义。

**完成条件：** 任何文件不会因只取 files[0] 而丢失，任何未知成功外壳不会被误标业务记录。

## Task 4：新 CSV 与嵌套 JSON 统一规范化

**Files:** Modify `scripts/yuntu_normalizer.py`；Test `tests/test_yuntu_normalizer.py`；Fixtures Task 1 的详情样例。

**Interfaces:** 扩展现有 `normalize_detail_records(raw_records, *, material_id, source_path, source_hash=None, expected_selection_group=None, expected_context=None, source_artifacts=None)`。新输出字段严格遵循设计 §5.3–5.5；旧调用可省略新增参数。新批次不再传 expected_selection_group 作为远端回显要求，分组关联由批次层加入。

- [ ] **4.1 增加嵌套 JSON 失败测试。** 在现有 YuntuNormalizerTests 中读取 fixture，断言：

```python
record = normalizer.normalize_detail_records(
    raw, material_id="101", source_path="fixture.json",
    expected_context={"date_type": "LAST_7_DAYS"})
self.assertEqual(len(record["trend_series"]), 5)
self.assertEqual(record["script_text"], "脚本词")
self.assertEqual(record["metrics"]["convertCnt"], 17)
self.assertEqual(record["metrics"]["orderCnt"], 3)
self.assertNotIn("objectId", record["metrics"])
self.assertEqual(record["core_data"]["showCnt"], "90-100w")
self.assertEqual(record["audience_portrait"]["八大人群"], ["新锐白领"])
self.assertEqual(record["content_formula"]["sources"]["script"]["detail"]["40"], ["脚本词"])
self.assertEqual(record["content_formula"]["sources"]["title"]["detail"]["40"], ["标题词"])
```

- [ ] **4.2 增加身份、周期和多行测试。** 覆盖 materialId/coreData.objectId 冲突、请求 ID 不匹配、缺身份、CUSTOM 错日期、相对类型错配、两条同素材仅 URL 不同、两条同素材曲线冲突、其他素材混入。断言所有行均检查，不能仅读取第一行。
- [ ] **4.3 运行确认失败。** `python3 -m unittest tests.test_yuntu_normalizer -v`。
- [ ] **4.4 复用公共字段读取与曲线转换。** 新嵌套结构和点号字段读到同一局部业务对象，再运行现有数值/时间点转换。五类名称与编号固定映射，缺失与全零区别记录，core_data 保存完整原值，metrics 排除身份和日期。

统一公式投影应等价于：

```python
formula = {
    "labels": labels,
    "sources": {
        "title": {"text": title_text, "detail": title_detail},
        "visual": {"text": visual_text, "detail": visual_detail},
        "script": {"text": script_text, "detail": script_detail},
    },
}
```

labels/title_text 等局部值由原始对应域取得；不能用同名标签覆盖前一域。旧 legacy_detail 分支仍读历史字段，但不把旧混合 detail.* 伪装为已知 script 来源。

- [ ] **4.5 实现多行归并与 provenance。** 比较所有业务字段，URL 差异独立记录；任何真实冲突报 duplicate_conflict。source_artifacts 含每条来源的路径、行号与哈希，保留代表性的 source_paths.detail 供旧消费者读取。
- [ ] **4.6 实现 expected_context 校验。** 自定义回显严格核对；相对类型只确认类型，填 date_verification=relative_type_only。本机日期不注入 start_date/end_date；跨日周期风险由批次层结合列表/提交时间补充。
- [ ] **4.7 CSV/JSON 等价与历史回归。** 两份 fixture 规范化后去除来源差异，业务投影一致；旧 trends/scriptText 输入仍通过。脚本空、公式空和缺 timestamp 都正确标记。

```bash
python3 -m unittest tests.test_rpa_io tests.test_yuntu_normalizer -v
```

**完成条件：** A5/A6/A7 的字段层用例通过，新格式不再漏人群、嵌套曲线或脚本，公式证据不覆盖。

## Task 5：接入 v4 任务账本、物化与恢复

**Files:** Modify `scripts/yuntu_run_state.py`、`scripts/yuntu_batch.py`、`scripts/rpa_connector.py`；Test `tests/test_yuntu_run_state.py`、`tests/test_yuntu_batch.py`、`tests/test_rpa_connector.py`。

**Interfaces:**
- `collection_contract()` 增加固定 connectorContract，包含代码、transport 与 normalizationVersion；新 schemaVersion=4。
- ConnectorInvoker 注入 Task 2 三函数；fake invoker 同步改为 submit/query/wait，显式记录 submit 次数。
- `resume_batch_analysis(*, output_dir, invoker, downloader=None) -> int`，新增 CLI `resume --output-dir`。
- `_materialize_records()` 遍历全部文件，返回合并 records 与全部 source_artifacts；更新列表/详情调用点，不保留偷偷只取第一项的兼容路径。
- 在 run_state 内增加 `collection_write_lock(output_dir)` 上下文管理器，入口 fetch/resume/retry-* 共用；status 不加写锁。

- [ ] **5.1 写状态身份和写互斥测试。** 同筛选但连接器/规范化版本不同不能复用；v3 可读但网络写命令拒绝；两进程同时写同目录只允许一个取得锁。目标运行时 macOS/Linux 可使用标准库 fcntl.flock 的非阻塞独占锁，进程退出由系统释放。未支持的平台明确报错，不静默无锁运行。
- [ ] **5.2 写故障恢复测试。** 为 FakeInvoker 增加提交、轮询序列及调用账本；每种故障使用临时目录和 FakeDownloader。

关键断言：

```python
# fixture: manifest 已存 task-101，恢复返回 completed 和文件清单。
exit_code = batch.resume_batch_analysis(output_dir=directory,
                                        invoker=fake, downloader=downloader)
self.assertEqual(fake.submit_calls, [])
self.assertEqual(fake.wait_calls, ["task-101"])
self.assertEqual(exit_code, 0)
self.assertTrue((Path(directory) / "normalized/detail-records/101.json").is_file())
```

测试 fixture 必须构造已通过的必要榜单和 targetTopN=1；否则 resume 的正确退出码应为部分完成，不应为了测试而绕过整批门槛。

- [ ] **5.3 运行相关测试确认失败。**

```bash
python3 -m unittest tests.test_yuntu_run_state tests.test_yuntu_batch -v
```

- [ ] **5.4 实现单 writer 调度。** 将原“一个 future 等到完整返回”的调用拆为提交 future 和等待 future；主线程保存 submitting、处理提交结果、原子保存任务 ID 后才派发等待。每个 task key 用 attempts 数组保存重试历史。

```text
持有写锁
  → 读取契约和 manifest
  → 为新工作项写 submitting
  → worker 提交一次
  → 主线程取得 ID、原子保存 manifest
  → worker 等待该 ID 的终态
  → 主线程保存终态与 errors
  → 物化全部文件、规范化、保存 manifest
  → 更新 summary 投影
```

保持实际列表依赖：CUSTOM 三类榜单可并发；相对周期 query 与 industry 并发，previous_period 依赖 query 实际日期。保留详情波次及高光屏障和候选补位规则；新详情业务请求仅四个白名单字段。关联 selection_group 来自本地候选，provenance 标记为榜单上下文而非连接器回显。

- [ ] **5.5 更新文件物化。** 使用 `raw-csv/tasks/<safe-key>/<attempt>/<index>.csv`，每个文件独立哈希并记录行号；所有文件全部解析。JSON payload 写 raw-json 对应目录。下载/解析失败保存已成功来源及错误，不抹除终态。
- [ ] **5.6 实现恢复分派。** 已有有效 normalized 直接复用；下载完成但未规范化重新解析；已知 ID 等待/刷新文件；无 ID submit_unknown 保持 unresolved。resume 不发新请求，fetch 恢复后仅提交从未处理的项。明确失败才参与补位或显式 retry-failed。
- [ ] **5.7 收紧成功门槛。** 不再让 `require_no_unresolved=False` 隐藏未知任务；partial_success 的 errors 不因素材达标被清空。保留字段缺失、采集失败、高光失败的不同状态。
- [ ] **5.8 验证断点与重复。** 覆盖提交响应丢失、保存 ID 后中断、终态保存后中断、CSV 后中断、normalized 后 summary 未写、文件 hash 被改、同目录重复启动、部分成功及素材补位。每个已知 ID 场景断言 submit 次数不增长。
- [ ] **5.9 验证相对周期跨日恢复。** 同日期类型但提交跨上海自然日且缺实际窗口，详情保留，整批严格周期验收不通过；不能自动重发所有任务来消除标记。
- [ ] **5.10 重跑四个模块。**

```bash
python3 -m unittest tests.test_rpa_connector tests.test_rpa_io tests.test_yuntu_run_state tests.test_yuntu_batch -v
```

**完成条件：** A3/A4/A5/A9 调度级用例通过；CLI status 无网络、resume 无提交；即使 targetTopN 达标，不确定任务仍明确可见。

## Task 6：同步事实包与公式证据消费者

**Files:** Modify `scripts/yuntu_analysis.py`、`scripts/yuntu_presentation.py`；按实际读取点修改 `scripts/yuntu_report_sections.py`、`scripts/yuntu_report.py`。Test 对应四个 `tests/test_yuntu_*.py`。

**Interfaces:** 保留 report-data、analysis-units、script、evidenceIndex.script、presentation 的既有输出用途；读取新 content_formula.sources，追加 core_data/audience_portrait/source_artifacts 的事实字段，旧字段继续可读。

- [ ] **6.1 写来源隔离测试。** 用同一个 label 40 的标题词/画面词/脚本词构造素材事实，断言脚本 evidence 只含脚本域中且确实命中脚本文本的词。用另一素材同标签值断言证据不串素材。

```python
self.assertIn("脚本词", script_evidence_text)
self.assertNotIn("标题词", script_evidence_text)
self.assertNotIn("画面词", script_evidence_text)
self.assertEqual(script_fact["material_id"], "101")
```

这些局部变量取自现有事实构建输出的 script 投影，沿用该测试文件现有入口和 fixture，不另建业务分析旁路。

- [ ] **6.2 运行确认当前错误来源键影响。** 分别运行 analysis/presentation 定向测试，确保失败来自 sources 未被消费，而不是另造 AI schema。
- [ ] **6.3 更新消费者。** 优先从 sources.script.detail 获取脚本证据，labels 继续使用现有已验证 ID 映射；标题/画面保留在各自事实域。新结构不得降级成跨域 detail.*。历史来源不明的旧混合键可展示历史原文，不用于构建新的确定脚本证据。

```python
sources = formula.get("sources") if isinstance(formula, dict) else None
if isinstance(sources, dict):
    script_source = sources.get("script") or {}
    script_detail = script_source.get("detail") or {}
else:
    script_detail = {}  # 历史混合键不提供已验证的脚本来源。
```

- [ ] **6.4 核验分析范围。** 保留 03 的 selected_detail_materials 和 05 的当前素材 script/evidenceIndex 输入；不把新全量核心数据或人群画像顺手加入脚本 AI 的白名单。全零指数可读、缺脚本继续显示数据不足，原文不重写。
- [ ] **6.5 回归报告输出契约。** 有脚本/无脚本、旧格式/新格式均能生成 presentation；五章导航、曲线、脚本引用、高光资产路径、Excel/ZIP 验证不退化，不增加浏览器人工截图门槛。

```bash
python3 -m unittest tests.test_yuntu_analysis tests.test_yuntu_presentation tests.test_yuntu_report -v
```

若存在独立 report_sections 测试，先 `rg --files tests` 确认实际模块名再运行，不发明测试文件。

**完成条件：** A8 离线消费者验证通过，不为展示新增数据改写分析方法或模板视觉结构。

## Task 7：知识页同步与完整离线回放

**Files:** Modify `SKILL.md`、`references/platforms/juliang-yt.md`、旧详情知识页；Create `references/connectors/juliang-yt/rpa_conn_juliang_yt_industry_content_rankings_details.md`；Update 执行记录。

**Interfaces:** 活动知识入口与实际 schema/CLI 完全一致；已有 historical 路径仅指导读取。

- [ ] **7.1 编写正式新知识页。** 内容包含固定 details code、date_type schema、CLI 兼容映射、五区块、异步提交/状态/终态、files 全量读取和空字段边界。所有技能内部路径相对 skill 根，不绑定本机 yuce-plugin 绝对路径。
- [ ] **7.2 同步 SKILL 与平台路由。** 活动详情链接只指向新页；更新 300 秒同步说明、resume 使用和整批观测时间含义。旧页标“历史格式说明”，移除可执行的旧连接器 fetch 示例。
- [ ] **7.3 搜索残留并逐项分类。**

```bash
rg -n 'rankings\.detail\b|date_range_type|agent/invoke|300 秒|300秒' SKILL.md references scripts tests
```

允许旧 CLI 名、历史字段解析、历史夹具和测试断言；不允许活动 code、请求业务键和路由继续用旧值。`rg` 有结果不等于失败，必须按语义检查，不能全局字符串替换。

- [ ] **7.4 在独立目录回放六份本地样本。** 复制或只读原样本，使用 Task 4 正式规范化器在 `RPA数据汇总/yuntu-details-migration-offline/` 内输出。执行前目录如已存在，先检查契约，不覆盖不同验证运行。

核验结果固定为 5 个唯一素材、3 个有脚本、2 个缺脚本、5×5 类曲线；重复 `7659409261740343346` 仅 URL 差异。每条 provenance 指向实际原文件和 hash，date_range 为 LAST_7_DAYS 且实际日期未回显。该批不能冒充父目录所示 8 月自定义周期，也不算 A10 线上证据。
- [ ] **7.5 完成定向离线回归。**

```bash
python3 scripts/rpa_connector.py schema
python3 scripts/rpa_connector.py self-test
python3 -m unittest tests.test_rpa_connector tests.test_rpa_io tests.test_yuntu_normalizer tests.test_yuntu_run_state tests.test_yuntu_batch tests.test_yuntu_analysis tests.test_yuntu_presentation tests.test_yuntu_report -v
git diff --check
```

记录实际命令、退出码与数量，不复制历史测试结果。仅在有新失败或未覆盖风险时扩大测试。
- [ ] **7.6 检查实现与设计逐条对应。** 在执行记录登记 A1–A9 通过/未通过及证据；A10/A11 保留未执行。自查改动范围、源数据未变、代码常量唯一、无凭证泄露。

**完成条件：** 活动知识入口和代码一致，原始六文件事实回放成立，定向回归通过。此时可称“离线实现完成”，不能称“迁移上线完成”。

## Task 8：正式新连接器冒烟、完整业务验证与同步完成

**Files:** 使用独立目录 `RPA数据汇总/yuntu-details-migration-smoke-<实际运行日期>/` 及另一个小批次目录；Update 执行记录。占位日期/账号须由实际运行上下文确定，不照字面创建带占位符目录。

**Interfaces:** 使用技能现有 fetch/prepare-analysis/attest-analysis/render-report 及新 resume；所有线上证据由正式调用产生。

- [ ] **8.1 确认账号与业务范围。** 使用现有明确授权账号；账号不明确时先 list-accounts 并由用户确定。复用已明确的行业/日期/筛选，不从样本目录推断真实周期。验证凭证在环境中存在但不打印值。
- [ ] **8.2 执行目标 1、候选 1 的冒烟。** 下面为命令模板，行业、账号、日期和输出目录用已确认真实值替换；此步骤会提交三类必要榜单和一条详情，不是“只一个网关请求”。

```bash
python3 scripts/rpa_connector.py fetch \
  --shop-id "<已确认账号>" \
  --industry "<已确认行业>" \
  --time-range-type LAST_7_DAYS \
  --detail-date-range-type LAST_7_DAYS \
  --target-top-n 1 \
  --candidate-top-n 1 \
  --output-dir "<独立冒烟目录>"
```

实际业务若为 CUSTOM，两组自定义参数填写一致，不为套用模板改成近 7 天。按第 3/30 秒及后续每 60 秒观测同一进程，不重启 fetch。
- [ ] **8.3 核验 A10。** 在请求证据中确认 code 为 details、业务键为 date_type；确认任务 ID、终态、全部文件与 hashes、素材/周期、五区块、normalized。视频链接是否有效另作高光/视频阶段检查，不能以非空 URL 代替。
- [ ] **8.4 验证恢复。** 优先利用实际自然中断或在测试环境可控中断已保存 ID 的本地进程；不取消远端任务。使用 `resume --output-dir` 验证查询相同 ID，submit 次数不增加。若首次真实任务无中断，离线注入已覆盖恢复，不为制造故障重复采集生产素材。
- [ ] **8.5 执行小批次。** 用相同已确认业务范围、独立目录、目标 3/候选 6 验证并发、补位和文件消费；最终完整验收使用届时确认的素材数量，未指定则沿用技能默认目标 10。目标不足不能因为小批次成功标正式任务完成。
- [ ] **8.6 验证 A11。** 三类榜单上下文、候选排序、目标数量、未解决任务数、部分成功 errors、各详情周期均核对；相对日期缺实际窗口时如实保留核验级别，跨日无法确认同周期则不得标完整报告通过。
- [ ] **8.7 完成真实报告链路。** prepare-analysis 生成事实包；当前对话模型按 SKILL 读取事实和实际高光帧，生成模型分析并 attestation；只经 render-report 生成交付，不手工改 HTML，不用程序模板伪造模型结论。

```bash
python3 scripts/rpa_connector.py status --output-dir "<正式验证目录>"
python3 scripts/rpa_connector.py prepare-analysis \
  --input-dir "<正式验证目录>" \
  --output-dir "<正式验证目录>/diagnostic-analysis"
```

后续 attest-analysis/render-report 使用生成的实际路径和 SKILL 中命令。验收 HTML、Markdown、report-data、presentation、Excel、高光本地引用及 ZIP 完整性；第三/五章脚本证据来自正确素材与来源域，其他章节指标保持原范围。
- [ ] **8.8 完成差异审查与授权范围内同步。** 检查最终代码与文档、实际测试证据、运行包目标。若用户本轮只授权实施，不自动扩展为推送/发布；先准备可审查 diff、测试及交付清单，再按实际授权完成对应动作。提交标题用中文说明实际业务改进。
- [ ] **8.9 写完成记录。** 列出正式版本来源、实际运行日期、代码版本、A1–A11 结果、任务 ID、normalized 与交付路径、已同步位置和未同步位置。不存 authorization/cookie，文件 URL 含签名时不复制到对外记录。

**完成条件：** A1–A11 全通过，所有新请求只用 details，当前授权范围内的代码/知识页/交付同步完成。若线上仍不可用、采集部分失败、目标不足或周期未能核验，记录具体阻塞，保留新路径与成功文件，不自动回退旧连接器。

## 设计覆盖自查

| 设计要求 | 对应任务 |
| --- | --- |
| 直接替换，无双路由/自动回退 | 2、7、8 |
| 正式契约与参考工具包同步 | 1、2、7 |
| 日期/身份、分组本地化 | 2、4、5 |
| 异步状态、单 writer、ID 立即落盘 | 2、5 |
| 多文件、重复与来源哈希 | 3、4、5 |
| 新旧格式、完整区块、零/空边界 | 4、7 |
| 公式来源、脚本与分析范围 | 4、6 |
| 历史版本隔离、可恢复不重发 | 5、7、8 |
| 完整报告、离线交付、正式同步 | 6、8 |

## 当前交付状态

本执行方案与设计文档已编写。上述复选框均表示未来执行项，未执行上线检查、代码替换、测试实现或 RPA。后续从 Task 1 开始，根据正式上线版本验证契约，再连续推进至授权范围内的完整验收。
