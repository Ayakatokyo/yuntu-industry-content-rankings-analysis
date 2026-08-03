# 云图 RPA 网关兼容性 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Yuntu RPA connector accept the platform-injected gateway base URL while preserving credentials and fixed-connector safeguards.

**Architecture:** Keep gateway configuration in `scripts/rpa_connector.py`. Replace the HTTPS/domain-only policy with syntax-only base-URL validation and preserve the supplied path when constructing fixed RPA endpoints. Extend offline session tests and skill contract tests to pin platform compatibility and operator guidance.

**Tech Stack:** Python 3, `unittest`, `requests`, Markdown skill documentation.

---

## File Structure

- `scripts/rpa_connector.py`: validates and normalizes the platform gateway base URL before existing fixed endpoint concatenation.
- `tests/test_rpa_connector.py`: verifies accepted runtime hosts and rejected URL components without network access.
- `tests/test_skill_contract.py`: verifies operator guidance covers platform-injected gateways and 404/504 diagnosis.
- `SKILL.md`: directs users to retain injected hosts and distinguishes 404 base-path failures from 504 gateway timeouts.

### Task 1: Establish Gateway Contract Tests

**Files:**
- Modify: `tests/test_rpa_connector.py:109-138`

- [x] **Step 1: Write failing tests for supported platform gateway forms**

```python
def test_runtime_config_accepts_platform_injected_gateway_base_urls(self):
    connector = self.connector()
    cases = (
        ("http://127.0.0.1:29090", "http://127.0.0.1:29090/adg/v1/agent/rpa/authorizations/query"),
        ("https://gateway.example/api/", "https://gateway.example/api/adg/v1/agent/rpa/authorizations/query"),
    )
    for host, expected_url in cases:
        with self.subTest(host=host):
            environment = self.runtime_environment()
            environment["ENV_BACKEND_HOST"] = host
            session = RecordingSession(FakeResponse({"success": True, "data": []}))
            connector.list_accounts(environ=environment, session=session)
            self.assertEqual(session.posts[0][0], expected_url)
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_rpa_connector.RpaConnectorTest.test_runtime_config_accepts_platform_injected_gateway_base_urls -v`

Expected: FAIL because `runtime_config` rejects HTTP/IP and `/api` bases before the session posts.

- [x] **Step 3: Add failing tests for unsafe URL components**

```python
def test_runtime_config_rejects_unsafe_gateway_url_components(self):
    connector = self.connector()
    for host in ("gateway.example", "https://user:password@gateway.example", "https://gateway.example/?query=value", "https://gateway.example/#fragment"):
        with self.subTest(host=host):
            environment = self.runtime_environment()
            environment["ENV_BACKEND_HOST"] = host
            session = RecordingSession(FakeResponse({"success": True, "data": []}))
            with self.assertRaisesRegex(connector.RpaConnectorError, "gateway|URL|HTTP"):
                connector.list_accounts(environ=environment, session=session)
            self.assertEqual(session.posts, [])
```

- [x] **Step 4: Run the unsafe-component test**

Run: `python -m unittest tests.test_rpa_connector.RpaConnectorTest.test_runtime_config_rejects_unsafe_gateway_url_components -v`

Expected: PASS for existing invalid forms; the accepted-base test remains red.

### Task 2: Normalize the Platform Gateway Base

**Files:**
- Modify: `scripts/rpa_connector.py:124-163`
- Test: `tests/test_rpa_connector.py:109-138`

- [x] **Step 1: Implement the smallest URL validation change**

Replace the HTTPS/domain-only condition with:

```python
if (
    parsed.scheme not in {"http", "https"}
    or not parsed.hostname
    or "@" in parsed.netloc
    or parsed.query
    or parsed.fragment
    or not valid_port
):
    raise RpaConnectorError(
        "ENV_BACKEND_HOST must be an HTTP(S) gateway URL without credentials, query, or fragment"
    )
```

Remove the `ipaddress` import and IP-literal rejection. Do not restrict `parsed.path`.

- [x] **Step 2: Run focused connector tests**

Run: `python -m unittest tests.test_rpa_connector.RpaConnectorTest.test_runtime_config_accepts_platform_injected_gateway_base_urls tests.test_rpa_connector.RpaConnectorTest.test_runtime_config_rejects_unsafe_gateway_url_components -v`

Expected: PASS; accepted inputs yield exactly one expected request and rejected inputs yield none.

- [x] **Step 3: Commit the runtime change**

Run: `git add scripts/rpa_connector.py tests/test_rpa_connector.py && git commit -m "fix: accept platform yuntu gateway bases"`

Expected: a commit containing only the runtime code and its direct tests.

### Task 3: Encode Operating Guidance and Gateway Failure Diagnosis

**Files:**
- Modify: `SKILL.md:20-35,103-117`
- Modify: `tests/test_skill_contract.py:85-140`

- [x] **Step 1: Write a failing skill-contract assertion**

```python
def test_skill_guides_platform_injected_gateway_diagnosis(self):
    skill = self.read_skill()
    self.assertIn("平台运行时注入", skill)
    self.assertRegex(skill, r"(?s)404.{0,160}基路径")
    self.assertRegex(skill, r"(?s)504.{0,160}网关超时")
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_skill_contract.SkillContractTest.test_skill_guides_platform_injected_gateway_diagnosis -v`

Expected: FAIL because the current skill requires a pure HTTPS hostname and has no 404/504 decision path.

- [x] **Step 3: Update `SKILL.md` runtime and failure sections**

Add these operational rules while retaining the instruction not to expose credentials:

```markdown
- 保留平台运行时注入的 `ENV_BACKEND_HOST`，不要用 `.env` 中的值覆盖它；该值可为 HTTP/IP 或含 `/api` 的基路径。
- `list-accounts` 成功后再运行 `fetch`。若返回 404，检查注入网关是否缺少或多出平台基路径；若返回 504，保留 `batch-manifest.json` 并按网关超时排查，不要将其解释为无素材。
```

- [x] **Step 4: Run the contract test to verify it passes**

Run: `python -m unittest tests.test_skill_contract.SkillContractTest.test_skill_guides_platform_injected_gateway_diagnosis -v`

Expected: PASS.

- [x] **Step 5: Commit the guidance change**

Run: `git add SKILL.md tests/test_skill_contract.py && git commit -m "docs: clarify yuntu gateway diagnostics"`

Expected: a commit containing only the guidance and its contract test.

### Task 4: Run Full Regression and Validate the Skill

**Files:**
- Verify: `SKILL.md`
- Verify: `scripts/rpa_connector.py`
- Verify: `tests/`

- [x] **Step 1: Run all automated tests**

Run: `python -m unittest discover -s tests -v`

Expected: PASS with no skipped or failing test.

- [x] **Step 2: Run the offline connector self-test**

Run: `python scripts/rpa_connector.py self-test`

Expected: `self-test passed`.

- [x] **Step 3: Validate the skill package**

Run: `python /Users/shuzida/.codex/skills/.system/skill-creator/scripts/quick_validate.py .`

Expected: validator exits 0 and reports no frontmatter or structural errors.

- [x] **Step 4: Inspect the final change set**

Run: `git status --short && git diff HEAD~2..HEAD --check`

Expected: clean working tree and no whitespace errors.

Observed: `quick_validate.py` reports only the pre-existing Chinese skill name as non-hyphen-case. The repository contract requires this public Chinese name, so it is intentionally retained.
