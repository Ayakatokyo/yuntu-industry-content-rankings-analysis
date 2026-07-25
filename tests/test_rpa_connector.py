import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT_PATH = SKILL_DIR / "scripts" / "rpa_connector.py"
REQUIREMENTS_PATH = SKILL_DIR / "requirements.txt"


def load_connector():
    spec = importlib.util.spec_from_file_location("analysis_rpa_connector", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, payload, status_error=None, json_error=None):
        self.payload = payload
        self.status_error = status_error
        self.json_error = json_error

    def raise_for_status(self):
        if self.status_error:
            raise self.status_error

    def json(self):
        if self.json_error:
            raise self.json_error
        return self.payload


class RecordingSession:
    def __init__(self, response):
        self.response = response
        self.posts = []

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        return self.response


class RaisingSession:
    def __init__(self, error):
        self.error = error
        self.posts = []

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        raise self.error


class SequencedSession:
    """Offline session that returns or raises each configured outcome in order."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.posts = []

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class RpaConnectorTest(unittest.TestCase):
    def connector(self):
        self.assertTrue(SCRIPT_PATH.exists(), "analysis connector has not been implemented")
        return load_connector()

    def runtime_environment(self):
        return {
            "ENV_BACKEND_HOST": "https://gateway.example/",
            "YUCE_AUTHORIZATION": "authorization-token",
            "YUCE_SESSION_ID": "agent-session-123",
        }

    def test_connector_script_exists(self):
        self.assertTrue(SCRIPT_PATH.exists(), "analysis connector has not been implemented")

    def test_fixed_gateway_metadata_cannot_be_overridden(self):
        connector = self.connector()
        self.assertEqual(
            connector.LIST_FUNCTION_CODE,
            "rpa.conn.juliang.yt.industry.content.rankings.list",
        )
        self.assertEqual(
            connector.DETAIL_FUNCTION_CODE,
            "rpa.conn.juliang.yt.industry.content.rankings.detail",
        )
        self.assertEqual(connector.PLATFORM, "RPA_JULIANG_YT_ACCOUNT_PASSWORD")
        self.assertEqual(connector.DATA_SOURCE_TYPE, "rpa")

    def test_requirements_declare_requests_for_independent_installation(self):
        self.assertTrue(REQUIREMENTS_PATH.exists(), "requirements.txt is required")
        requirements = REQUIREMENTS_PATH.read_text(encoding="utf-8").splitlines()
        self.assertTrue(
            any(line.strip().lower().startswith("requests") for line in requirements),
            "requirements.txt must declare requests",
        )

    def test_runtime_config_requires_nonblank_values_and_safe_https_host(self):
        connector = self.connector()
        for name in connector.REQUIRED_ENVIRONMENT:
            for value in (None, "", "   "):
                with self.subTest(name=name, value=value):
                    environment = self.runtime_environment()
                    if value is None:
                        del environment[name]
                    else:
                        environment[name] = value
                    with self.assertRaisesRegex(connector.RpaConnectorError, name):
                        connector.runtime_config(environment)

        unsafe_hosts = (
            "http://gateway.example",
            "gateway.example",
            "https://user:password@gateway.example",
            "https://gateway.example/not-a-base-url",
            "https://gateway.example/?query=value",
            "https://gateway.example/#fragment",
            "https://127.0.0.1",
        )
        for host in unsafe_hosts:
            with self.subTest(host=host):
                environment = self.runtime_environment()
                environment["ENV_BACKEND_HOST"] = host
                session = RecordingSession(FakeResponse({"success": True, "data": []}))
                with self.assertRaisesRegex(connector.RpaConnectorError, "HTTPS|hostname"):
                    connector.list_accounts(environ=environment, session=session)
                self.assertEqual(session.posts, [])

    def test_shanghai_today_uses_the_business_calendar_at_a_timezone_boundary(self):
        connector = self.connector()
        boundary_instant = datetime(2026, 7, 25, 16, 30, tzinfo=timezone.utc)

        self.assertEqual(
            connector.shanghai_today(boundary_instant).isoformat(), "2026-07-26"
        )

    def test_list_validation_normalizes_filters_and_rejects_invalid_values(self):
        connector = self.connector()
        params = connector.validate_list_business_params(
            {
                "industry": "食品饮料",
                "time_range_type": "LAST_7_DAYS",
                "ages": "AGE_24_30,AGE_31_35",
                "genders": ["FEMALE"],
                "crowd_groups": '["REFINED_MOM", "NEW_WHITE_COLLAR"]',
                "brand_scope_type": "SPECIFIED_BRANDS",
                "brands": "燕之屋,王老吉,Oreo/奥利奥",
                "ranking_limit_type": "CTR_TOP1000",
            }
        )
        self.assertEqual(params["ages"], ["AGE_24_30", "AGE_31_35"])
        self.assertEqual(params["brands"], ["燕之屋", "王老吉", "Oreo/奥利奥"])
        invalid_cases = (
            ({"unrecognized": "value"}, "unexpected"),
            ({"ages": "AGE_24_30,AGE_24_30"}, "duplicates"),
            ({"genders": "OTHER"}, "genders"),
            ({"brand_scope_type": "SPECIFIED_BRANDS"}, "brands"),
        )
        for raw_params, message in invalid_cases:
            with self.subTest(raw_params=raw_params):
                with self.assertRaisesRegex(connector.RpaConnectorError, message):
                    connector.validate_list_business_params(raw_params)

    def test_detail_validation_requires_a_numeric_material_id_and_consistent_dates(self):
        connector = self.connector()
        self.assertEqual(
            connector.validate_detail_business_params(
                {
                    "material_id": "764",
                    "date_range_type": "CUSTOM",
                    "custom_start_date": "20260701",
                    "custom_end_date": "2026-07-02",
                }
            ),
            {
                "material_id": "764",
                "date_range_type": "CUSTOM",
                "custom_start_date": "20260701",
                "custom_end_date": "2026-07-02",
            },
        )
        invalid_cases = (
            ({"material_id": "not-an-id", "date_range_type": "LAST_7_DAYS"}, "material_id"),
            ({"material_id": "764", "date_range_type": "LAST_90_DAYS"}, "date_range_type"),
            ({"material_id": "764", "date_range_type": "CUSTOM"}, "CUSTOM requires"),
            ({"material_id": "764", "date_range_type": "LAST_7_DAYS", "custom_start_date": "20260701"}, "CUSTOM"),
            ({"material_id": "764", "date_range_type": "CUSTOM", "custom_start_date": "20260702", "custom_end_date": "20260701"}, "earlier"),
        )
        for raw_params, message in invalid_cases:
            with self.subTest(raw_params=raw_params):
                with self.assertRaisesRegex(connector.RpaConnectorError, message):
                    connector.validate_detail_business_params(raw_params)

    def test_list_accounts_uses_a_fixed_platform_payload(self):
        connector = self.connector()
        session = RecordingSession(FakeResponse({"success": True, "data": []}))
        self.assertEqual(
            connector.list_accounts(environ=self.runtime_environment(), session=session),
            {"success": True, "data": []},
        )
        self.assertEqual(
            session.posts,
            [
                (
                    "https://gateway.example/adg/v1/agent/rpa/authorizations/query",
                    {
                        "json": {
                            "authorization": "authorization-token",
                            "platform": "RPA_JULIANG_YT_ACCOUNT_PASSWORD",
                        },
                        "headers": {"Content-Type": "application/json"},
                        "cookies": {"YCSESSIONID": "authorization-token"},
                        "timeout": 30,
                    },
                )
            ],
        )

    def test_separate_list_and_detail_invocations_use_fixed_payloads(self):
        connector = self.connector()
        list_session = RecordingSession(FakeResponse({"success": True, "data": {}}))
        detail_session = RecordingSession(FakeResponse({"success": True, "data": {}}))
        environment = self.runtime_environment()

        connector.invoke_list(
            shop_id=" shop-42 ",
            business_params={"industry": "食品饮料"},
            environ=environment,
            session=list_session,
        )
        connector.invoke_detail(
            shop_id=" shop-42 ",
            business_params={"material_id": "764", "date_range_type": "LAST_7_DAYS"},
            environ=environment,
            session=detail_session,
        )

        for session, function_code, params in (
            (list_session, connector.LIST_FUNCTION_CODE, {"industry": "食品饮料"}),
            (detail_session, connector.DETAIL_FUNCTION_CODE, {"material_id": "764", "date_range_type": "LAST_7_DAYS"}),
        ):
            self.assertEqual(len(session.posts), 1)
            url, options = session.posts[0]
            self.assertEqual(url, "https://gateway.example/adg/v1/agent/invoke")
            self.assertEqual(
                options,
                {
                    "json": {
                        "authorization": "authorization-token",
                        "agent_session_id": "agent-session-123",
                        "data_source_type": "rpa",
                        "platform": "RPA_JULIANG_YT_ACCOUNT_PASSWORD",
                        "function_code": function_code,
                        "business_params": params,
                        "shop_id": "shop-42",
                    },
                    "headers": {"Content-Type": "application/json"},
                    "cookies": {"YCSESSIONID": "authorization-token"},
                    "timeout": 3600,
                },
            )

    def test_rebound_exported_metadata_cannot_change_gateway_payloads(self):
        connector = self.connector()
        original_values = {
            "LIST_FUNCTION_CODE": connector.LIST_FUNCTION_CODE,
            "DETAIL_FUNCTION_CODE": connector.DETAIL_FUNCTION_CODE,
            "PLATFORM": connector.PLATFORM,
            "DATA_SOURCE_TYPE": connector.DATA_SOURCE_TYPE,
        }
        list_session = RecordingSession(FakeResponse({"success": True, "data": {}}))
        detail_session = RecordingSession(FakeResponse({"success": True, "data": {}}))
        accounts_session = RecordingSession(FakeResponse({"success": True, "data": []}))
        try:
            connector.LIST_FUNCTION_CODE = "rpa.conn.attacker.list"
            connector.DETAIL_FUNCTION_CODE = "rpa.conn.attacker.detail"
            connector.PLATFORM = "ATTACKER_PLATFORM"
            connector.DATA_SOURCE_TYPE = "attacker"

            connector.invoke_list(
                "shop-42", {}, environ=self.runtime_environment(), session=list_session
            )
            connector.invoke_detail(
                "shop-42",
                {"material_id": "764", "date_range_type": "LAST_7_DAYS"},
                environ=self.runtime_environment(),
                session=detail_session,
            )
            connector.list_accounts(
                environ=self.runtime_environment(), session=accounts_session
            )
        finally:
            for name, value in original_values.items():
                setattr(connector, name, value)

        self.assertEqual(
            list_session.posts[0][1]["json"]["function_code"],
            "rpa.conn.juliang.yt.industry.content.rankings.list",
        )
        self.assertEqual(
            detail_session.posts[0][1]["json"]["function_code"],
            "rpa.conn.juliang.yt.industry.content.rankings.detail",
        )
        self.assertEqual(
            list_session.posts[0][1]["json"]["platform"],
            "RPA_JULIANG_YT_ACCOUNT_PASSWORD",
        )
        self.assertEqual(
            detail_session.posts[0][1]["json"]["platform"],
            "RPA_JULIANG_YT_ACCOUNT_PASSWORD",
        )
        self.assertEqual(list_session.posts[0][1]["json"]["data_source_type"], "rpa")
        self.assertEqual(detail_session.posts[0][1]["json"]["data_source_type"], "rpa")
        self.assertEqual(
            accounts_session.posts[0][1]["json"]["platform"],
            "RPA_JULIANG_YT_ACCOUNT_PASSWORD",
        )

    def test_public_list_wrapper_ignores_mutable_function_code_attributes(self):
        connector = self.connector()
        malicious_code = "rpa.conn.attacker.control"
        if hasattr(connector, "FUNCTION_CODES_BY_OPERATION"):
            connector.FUNCTION_CODES_BY_OPERATION["list"] = malicious_code
        else:
            setattr(connector, "FUNCTION_CODES_BY_OPERATION", {"list": malicious_code})
        session = RecordingSession(FakeResponse({"success": True, "data": {}}))

        connector.invoke_list(
            shop_id="shop-42",
            business_params={},
            environ=self.runtime_environment(),
            session=session,
        )

        self.assertEqual(
            session.posts[0][1]["json"]["function_code"],
            "rpa.conn.juliang.yt.industry.content.rankings.list",
        )

    def test_internal_dispatch_rejects_an_arbitrary_function_code(self):
        connector = self.connector()
        session = RecordingSession(FakeResponse({"success": True, "data": {}}))

        with self.assertRaisesRegex(connector.RpaConnectorError, "operation"):
            connector._invoke(
                operation="rpa.conn.attacker.control",
                shop_id="shop-42",
                business_params={},
                environ=self.runtime_environment(),
                session=session,
            )

        self.assertEqual(session.posts, [])

    def test_gateway_errors_are_credential_safe_and_do_not_write_outputs(self):
        connector = self.connector()
        for session in (
            RecordingSession(FakeResponse({"success": False})),
            RaisingSession(RuntimeError("network unavailable")),
        ):
            with self.subTest(session=type(session).__name__), tempfile.TemporaryDirectory() as temporary_directory:
                output = Path(temporary_directory) / "result.json"
                with self.assertRaisesRegex(connector.RpaConnectorError, "fetch RPA list|unsuccessful") as context:
                    connector.invoke_list(
                        shop_id="shop-42",
                        business_params={},
                        environ=self.runtime_environment(),
                        session=session,
                    )
                self.assertNotIn("authorization-token", str(context.exception))
                self.assertFalse(output.exists())

    def test_write_json_atomically_preserves_existing_file_when_replace_fails(self):
        connector = self.connector()
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "nested" / "result.json"
            output.parent.mkdir()
            output.write_text(json.dumps({"existing": True}), encoding="utf-8")
            with mock.patch.object(connector.os, "replace", side_effect=OSError("replace failed")):
                with self.assertRaisesRegex(connector.RpaConnectorError, "write"):
                    connector.write_json_atomically({"new": True}, output)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), {"existing": True})
            self.assertEqual(list(output.parent.glob("*.tmp")), [])

    def test_extract_material_ids_is_recursive_order_preserving_and_top_n_bounded(self):
        connector = self.connector()
        payload = {
            "data": {
                "items": [
                    {"material_id": "101"},
                    {"nested": [{"material_id": "202"}, {"material_id": "101"}]},
                    {"material_id": 303},
                    {"material_id": "not-numeric"},
                    {"material_id": "004"},
                    {"other": {"material_id": "505"}},
                ]
            }
        }
        self.assertEqual(connector.select_material_ids(payload, top_n=3), ["101", "202", "004"])
        self.assertEqual(connector.select_material_ids(payload, top_n=10), ["101", "202", "004", "505"])
        for invalid_top_n in (0, -1, True, "3"):
            with self.subTest(top_n=invalid_top_n):
                with self.assertRaisesRegex(connector.RpaConnectorError, "top_n"):
                    connector.select_material_ids(payload, top_n=invalid_top_n)

    def test_fetch_analysis_uses_default_top_n_and_fixed_list_detail_payloads(self):
        connector = self.connector()
        list_result = {
            "success": True,
            "data": {"items": [{"material_id": "11"}, {"material_id": "12"}, {"material_id": "13"}]},
        }
        session = SequencedSession(
            [
                FakeResponse(list_result),
                FakeResponse({"success": True, "data": {"id": "11"}}),
                FakeResponse({"success": True, "data": {"id": "12"}}),
                FakeResponse({"success": True, "data": {"id": "13"}}),
            ]
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "analysis"
            status = connector.fetch_analysis(
                shop_id="shop-42",
                raw_list_params={"industry": "食品饮料"},
                raw_detail_params={"date_range_type": "LAST_7_DAYS"},
                output_dir=output,
                environ=self.runtime_environment(),
                session=session,
            )

            self.assertEqual(status, 0)
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["filters"], {"industry": "食品饮料"})
            self.assertEqual(manifest["list_response_path"], "list-response.json")
            self.assertEqual(manifest["selected_material_ids"], ["11", "12", "13"])
            self.assertEqual([item["status"] for item in manifest["details"]], ["success", "success", "success"])
            self.assertTrue((output / "list-response.json").exists())
            self.assertTrue((output / "details" / "11.json").exists())
            self.assertEqual(len(session.posts), 4)
            self.assertEqual(session.posts[0][1]["json"]["function_code"], connector.LIST_FUNCTION_CODE)
            self.assertTrue(all(post[1]["json"]["function_code"] == connector.DETAIL_FUNCTION_CODE for post in session.posts[1:]))

    def test_fetch_analysis_deduplicates_valid_ids_in_response_order_and_honors_explicit_top_n(self):
        connector = self.connector()
        session = SequencedSession(
            [
                FakeResponse({"success": True, "data": {"items": [{"material_id": "11"}, {"material_id": "11"}, {"material_id": 12}, {"material_id": "bad"}, {"material_id": "004"}, {"material_id": "22"}]}}),
                FakeResponse({"success": True, "data": {}}),
                FakeResponse({"success": True, "data": {}}),
            ]
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "analysis"
            status = connector.fetch_analysis(
                "shop-42",
                {},
                {"date_range_type": "LAST_30_DAYS"},
                top_n=2,
                output_dir=output,
                environ=self.runtime_environment(),
                session=session,
            )
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(status, 0)
        self.assertEqual(manifest["selected_material_ids"], ["11", "004"])
        self.assertEqual([post[1]["json"]["business_params"]["material_id"] for post in session.posts[1:]], ["11", "004"])

    def test_fetch_analysis_stops_after_list_failure_or_missing_ids_and_writes_safe_manifest(self):
        connector = self.connector()
        cases = (
            ("list-failure", [FakeResponse({"success": False})], False),
            ("missing-ids", [FakeResponse({"success": True, "data": {"items": [{"material_id": "bad"}]}})], True),
        )
        for name, outcomes, list_file_expected in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary_directory:
                output = Path(temporary_directory) / "analysis"
                session = SequencedSession(outcomes)
                status = connector.fetch_analysis(
                    "shop-42",
                    {"industry": "食品饮料"},
                    {"date_range_type": "LAST_7_DAYS"},
                    output_dir=output,
                    environ=self.runtime_environment(),
                    session=session,
                )
                manifest_text = (output / "manifest.json").read_text(encoding="utf-8")
                manifest = json.loads(manifest_text)

                self.assertEqual(status, 1)
                self.assertEqual(len(session.posts), 1)
                self.assertEqual((output / "list-response.json").exists(), list_file_expected)
                self.assertEqual(manifest["details"], [])
                self.assertEqual(manifest["selected_material_ids"], [])
                self.assertIn(manifest["status"], {"list_failed", "no_material_ids"})
                self.assertNotIn("authorization-token", manifest_text)
                self.assertNotIn("agent-session-123", manifest_text)

    def test_fetch_analysis_continues_after_detail_failures_and_leaves_no_temporary_outputs(self):
        connector = self.connector()
        session = SequencedSession(
            [
                FakeResponse({"success": True, "data": {"items": [{"material_id": "11"}, {"material_id": "22"}, {"material_id": "33"}]}}),
                RaisingSession(RuntimeError("authorization-token agent-session-123 unavailable")).error,
                FakeResponse({"success": True, "data": {"id": "22"}}),
                FakeResponse({"success": False, "error": "authorization-token"}),
            ]
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "analysis"
            status = connector.fetch_analysis(
                "shop-42",
                {},
                {"date_range_type": "LAST_7_DAYS"},
                top_n=3,
                output_dir=output,
                environ=self.runtime_environment(),
                session=session,
            )
            manifest_text = (output / "manifest.json").read_text(encoding="utf-8")
            manifest = json.loads(manifest_text)

            self.assertEqual(status, 1)
            self.assertEqual([item["status"] for item in manifest["details"]], ["failed", "success", "failed"])
            self.assertTrue((output / "details" / "22.json").exists())
            self.assertFalse((output / "details" / "11.json").exists())
            self.assertFalse((output / "details" / "33.json").exists())
            self.assertEqual(list(output.rglob("*.tmp")), [])
            self.assertNotIn("authorization-token", manifest_text)
            self.assertNotIn("agent-session-123", manifest_text)
            self.assertEqual(len(session.posts), 4)

    def test_fetch_analysis_validates_every_input_before_any_network_request(self):
        connector = self.connector()
        session = SequencedSession([])
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "analysis"
            invalid_cases = (
                ({"industry": ""}, {"date_range_type": "LAST_7_DAYS"}, 1),
                ({}, {"date_range_type": "LAST_90_DAYS"}, 1),
                ({}, {"date_range_type": "LAST_7_DAYS"}, 0),
            )
            for list_params, detail_params, top_n in invalid_cases:
                with self.subTest(list_params=list_params, detail_params=detail_params, top_n=top_n):
                    with self.assertRaises(connector.RpaConnectorError):
                        connector.fetch_analysis(
                            "shop-42",
                            list_params,
                            detail_params,
                            top_n=top_n,
                            output_dir=output,
                            environ=self.runtime_environment(),
                            session=session,
                        )
            self.assertEqual(session.posts, [])


if __name__ == "__main__":
    unittest.main()
