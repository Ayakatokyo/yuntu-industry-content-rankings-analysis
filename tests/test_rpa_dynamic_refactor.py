import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest import mock


SKILL_DIR = Path(__file__).resolve().parents[1]
CONNECTOR_PATH = SKILL_DIR / "scripts" / "rpa_connector.py"
LIST_CLIENT_PATH = SKILL_DIR / "scripts" / "rpa_dynamic_client.py"
DETAIL_CLIENT_PATH = SKILL_DIR / "scripts" / "rpa_dynamic_detail_client.py"


def load_module(name, path):
    scripts_dir = str(SKILL_DIR / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class SequencedSession:
    def __init__(self, *payloads):
        self.responses = [FakeResponse(payload) for payload in payloads]
        self.posts = []

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        if not self.responses:
            raise AssertionError("unexpected gateway request")
        return self.responses.pop(0)


def connector_detail(code, schema=None, platform="YUNTU_DYNAMIC_PLATFORM"):
    return {
        "id": "configuration-id-not-a-code",
        "connectorCode": code,
        "name": code.rsplit(".", 1)[-1],
        "platformCode": platform,
        "connectionTypeList": ["ACCOUNT_PASSWORD"],
        "inParamJsonSchemaText": None if schema is None else json.dumps(schema),
        "inParamList": [
            {
                "param": "industry",
                "isRequired": True,
                "dataTypeEnum": "STRING",
            }
        ],
        "outParamList": [],
    }


class DynamicRpaRefactorTest(unittest.TestCase):
    def setUp(self):
        self.connector = load_module("dynamic_refactor_connector", CONNECTOR_PATH)
        self.environment = {
            "ENV_BACKEND_HOST": "https://gateway.example",
            "YUCE_AUTHORIZATION": "authorization-token",
            "YUCE_SESSION_ID": "agent-session-123",
        }

    def test_each_runtime_entrypoint_owns_exactly_one_connector_code(self):
        list_client = load_module("dynamic_list_client", LIST_CLIENT_PATH)
        detail_client = load_module("dynamic_detail_client", DETAIL_CLIENT_PATH)

        self.assertEqual(
            list_client.CONNECTOR_CODE,
            "rpa.conn.juliang.yt.industry.content.rankings.list",
        )
        self.assertEqual(
            detail_client.CONNECTOR_CODE,
            "rpa.conn.juliang.yt.industry.content.rankings.details",
        )

    def test_invoke_reads_live_detail_validates_and_forwards_dynamic_platform(self):
        code = "rpa.conn.juliang.yt.industry.content.rankings.list"
        session = SequencedSession(
            {"success": True, "data": [connector_detail(code)]},
            {
                "success": True,
                "data": [{"platform": "YUNTU_DYNAMIC_PLATFORM", "accountId": "shop-42"}],
            },
            {"success": True, "data": {"task_group_id": "task-1"}},
            {"success": True, "data": {"status": "completed", "files": []}},
        )

        with mock.patch.object(self.connector.time, "sleep"):
            result = self.connector.invoke_list(
                "shop-42",
                {"industry": "食品饮料"},
                environ=self.environment,
                session=session,
            )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(
            [url.rsplit("/", 1)[-1] for url, _options in session.posts],
            ["listByConnectorCode", "query", "tasks", "status"],
        )
        detail_payload = session.posts[0][1]["json"]
        self.assertEqual(detail_payload, {"connectorCode": code})
        auth_payload = session.posts[1][1]["json"]
        self.assertEqual(
            auth_payload,
            {"authorization": "authorization-token", "platform": "YUNTU_DYNAMIC_PLATFORM"},
        )
        submit_payload = session.posts[2][1]["json"]
        self.assertEqual(submit_payload["platform"], "YUNTU_DYNAMIC_PLATFORM")
        self.assertEqual(submit_payload["function_code"], code)
        self.assertEqual(submit_payload["business_params"], {"industry": "食品饮料"})
        self.assertNotEqual(submit_payload["function_code"], "configuration-id-not-a-code")

    def test_invalid_dynamic_params_stop_before_task_submission(self):
        code = "rpa.conn.juliang.yt.industry.content.rankings.list"
        session = SequencedSession(
            {"success": True, "data": [connector_detail(code)]},
        )

        with self.assertRaisesRegex(self.connector.RpaConnectorError, "industry"):
            self.connector.invoke_list(
                "shop-42",
                {"unexpected": True},
                environ=self.environment,
                session=session,
            )

        self.assertEqual(len(session.posts), 1)
        self.assertTrue(session.posts[0][0].endswith("/dcConnector/v3/listByConnectorCode"))

    def test_list_accounts_uses_platform_from_live_detail(self):
        code = "rpa.conn.juliang.yt.industry.content.rankings.list"
        session = SequencedSession(
            {"success": True, "data": [connector_detail(code, {"type": "object"})]},
            {"success": True, "data": [{"shop_id": "shop-42"}]},
        )

        result = self.connector.list_accounts(
            operation="list",
            environ=self.environment,
            session=session,
        )

        self.assertEqual(result["data"][0]["shop_id"], "shop-42")
        self.assertEqual(
            session.posts[1][1]["json"]["platform"],
            "YUNTU_DYNAMIC_PLATFORM",
        )

    def test_fetch_accepts_one_json_contract_and_defaults_to_new_output_root(self):
        args = self.connector._parser().parse_args(
            [
                "fetch",
                "--shop-id",
                "shop-42",
                "--params-json",
                '{"list":{"industry":"食品饮料"},"detail":{"date_type":"LAST_7_DAYS"}}',
            ]
        )

        self.assertEqual(args.output_dir, "云图数据资源/yuntu-rankings-analysis")
        self.assertFalse(hasattr(args, "industry"))
        self.assertFalse(hasattr(args, "detail_date_range_type"))
        self.assertEqual(
            self.connector.load_batch_params(args),
            {
                "list": {"industry": "食品饮料"},
                "detail": {"date_type": "LAST_7_DAYS"},
            },
        )

    def test_params_file_must_stay_within_workspace(self):
        args = self.connector._parser().parse_args(
            ["fetch", "--shop-id", "shop-42", "--params-file", "../outside.json"]
        )

        with self.assertRaisesRegex(self.connector.RpaConnectorError, "workspace"):
            self.connector.load_batch_params(args)


if __name__ == "__main__":
    unittest.main()
