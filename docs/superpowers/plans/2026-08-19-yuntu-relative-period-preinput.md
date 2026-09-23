# 云图相对周期输入 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将“近7天/近30天”明确为直传云图枚举的技能输入，并显式列出首个 RPA 的筛选条件。

**Architecture:** 连接器保持现有 `LAST_7_DAYS`、`LAST_30_DAYS` 与 `CUSTOM` 三种枚举校验。仅由 `SKILL.md` 将自然语言周期映射写清楚，`tests/test_skill_contract.py` 防止契约回退。

**Tech Stack:** Markdown、Python `unittest`

---

### Task 1: 锁定相对周期契约

**Files:**
- Modify: `tests/test_skill_contract.py`
- Modify: `SKILL.md`

- [x] **Step 1: 写入失败的契约测试**

```python
def test_documents_relative_periods_as_yuntu_enums(self):
    skill = self.read_skill()
    for phrase in (
        "近7天",
        "LAST_7_DAYS",
        "近30天",
        "LAST_30_DAYS",
        "不换算为自定义日期",
    ):
        self.assertIn(phrase, skill)
```

- [x] **Step 2: 运行测试，确认因文案尚未覆盖而失败**

Run: `python -m unittest tests.test_skill_contract.AnalysisSkillContractTests.test_documents_relative_periods_as_yuntu_enums`

Expected: FAIL，缺少“近30天”或“不换算为自定义日期”。

- [x] **Step 3: 最小化更新技能契约**

将 `pre_input` 中的分析周期说明改为“近7天、近30天或自定义起止日期”，展开首个 RPA 的六类筛选项；在时间口径中列出下列映射：

```text
近7天 -> LAST_7_DAYS
近30天 -> LAST_30_DAYS
明确起止日期 -> CUSTOM + 相同起止日期
```

- [x] **Step 4: 运行契约测试，确认通过**

Run: `python -m unittest tests.test_skill_contract.AnalysisSkillContractTests.test_documents_relative_periods_as_yuntu_enums`

Expected: PASS。

### Task 2: 回归验证

**Files:**
- Modify: `SKILL.md`
- Modify: `tests/test_skill_contract.py`

- [x] **Step 1: 执行完整技能契约测试**

Run: `python -m unittest tests.test_skill_contract`

Expected: PASS。

- [x] **Step 2: 执行离线连接器自检**

Run: `python scripts/rpa_connector.py self-test`

Expected: `self-test passed`；不访问网关。
