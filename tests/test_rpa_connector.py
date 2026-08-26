import importlib.util
import hashlib
import io
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

    def test_runtime_config_accepts_explicit_cookie_session_without_agent_session_id(self):
        connector = self.connector()
        environment = {
            "ENV_BACKEND_HOST": "https://gateway.example/",
            "YUCE_AUTHORIZATION": "authorization-token",
            "YCSESSIONID": "cookie-session-456",
        }

        _api_base, authorization, session_id, cookies = connector.runtime_config(environment)

        self.assertEqual(authorization, "authorization-token")
        self.assertEqual(session_id, "cookie-session-456")
        self.assertEqual(cookies, {"YCSESSIONID": "cookie-session-456"})

    def test_legacy_serial_fetch_helpers_are_removed(self):
        connector = self.connector()
        for name in (
            "fetch_analysis",
            "select_material_ids",
            "_manifest",
            "write_json_atomically",
            "_safe_error_summary",
        ):
            with self.subTest(name=name):
                self.assertFalse(hasattr(connector, name))

    def test_connector_script_exists(self):
        self.assertTrue(SCRIPT_PATH.exists(), "analysis connector has not been implemented")

    def test_fetch_batch_uses_double_target_candidates_by_default(self):
        connector = self.connector()
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            connector, "fetch_batch", return_value=0
        ) as fetch_batch:
            status = connector.fetch_batch_analysis(
                "shop-42",
                {"industry": "食品饮料"},
                {"date_range_type": "LAST_7_DAYS"},
                target_top_n=5,
                output_dir=directory,
            )

        self.assertEqual(status, 0)
        self.assertEqual(fetch_batch.call_args.kwargs["candidate_top_n"], 10)

    def test_batch_invoker_forwards_to_current_public_invocations(self):
        connector = self.connector()
        with mock.patch.object(
            connector, "invoke_list", return_value={"kind": "list"}
        ) as invoke_list, mock.patch.object(
            connector, "invoke_detail", return_value={"kind": "detail"}
        ) as invoke_detail:
            invoker = connector._batch_invoker()
            self.assertEqual(invoker.invoke_list("shop-42", {"page": 1}), {"kind": "list"})
            self.assertEqual(
                invoker.invoke_detail("shop-42", {"material_id": "101"}),
                {"kind": "detail"},
            )

        invoke_list.assert_called_once_with("shop-42", {"page": 1})
        invoke_detail.assert_called_once_with("shop-42", {"material_id": "101"})

    def test_main_dispatches_explicit_unresolved_retry(self):
        connector = self.connector()
        with mock.patch.object(
            connector, "retry_unresolved_batch_analysis", return_value=0
        ) as retry, mock.patch("sys.stdout", new_callable=io.StringIO):
            status = connector.main(
                [
                    "retry-unresolved",
                    "--shop-id",
                    "shop-42",
                    "--output-dir",
                    "output",
                ]
            )

        self.assertEqual(status, 0)
        retry.assert_called_once_with("shop-42", output_dir="output")

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

    def test_runtime_config_requires_nonblank_values_and_safe_gateway_host(self):
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
            "gateway.example",
            "https://user:password@gateway.example",
            "https://gateway.example/?query=value",
            "https://gateway.example/#fragment",
        )
        for host in unsafe_hosts:
            with self.subTest(host=host):
                environment = self.runtime_environment()
                environment["ENV_BACKEND_HOST"] = host
                session = RecordingSession(FakeResponse({"success": True, "data": []}))
                with self.assertRaisesRegex(connector.RpaConnectorError, "HTTP|gateway"):
                    connector.list_accounts(environ=environment, session=session)
                self.assertEqual(session.posts, [])

    def test_runtime_config_accepts_platform_injected_gateway_base_urls(self):
        connector = self.connector()
        cases = (
            (
                "http://127.0.0.1:29090",
                "http://127.0.0.1:29090/adg/v1/agent/rpa/authorizations/query",
            ),
            (
                "https://gateway.example/api/",
                "https://gateway.example/api/adg/v1/agent/rpa/authorizations/query",
            ),
        )
        for host, expected_url in cases:
            with self.subTest(host=host):
                environment = self.runtime_environment()
                environment["ENV_BACKEND_HOST"] = host
                session = RecordingSession(FakeResponse({"success": True, "data": []}))

                connector.list_accounts(environ=environment, session=session)

                self.assertEqual(session.posts[0][0], expected_url)

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
        passthrough = connector.validate_list_business_params(
            {
                "ages": "18-23,24-30",
                "genders": ["男"],
                "crowd_groups": '["都市银发", "小镇中老年"]',
            }
        )
        self.assertEqual(passthrough["ages"], ["18-23", "24-30"])
        self.assertEqual(passthrough["genders"], ["男"])
        self.assertEqual(passthrough["crowd_groups"], ["都市银发", "小镇中老年"])
        invalid_cases = (
            ({"unrecognized": "value"}, "unexpected"),
            ({"ages": "AGE_24_30,AGE_24_30"}, "duplicates"),
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

    def test_list_accounts_prefers_explicit_cookie_session_for_gateway_authentication(self):
        connector = self.connector()
        environment = self.runtime_environment()
        environment["YCSESSIONID"] = "cookie-session-456"
        session = RecordingSession(FakeResponse({"success": True, "data": []}))

        connector.list_accounts(environ=environment, session=session)

        self.assertEqual(session.posts[0][1]["cookies"], {"YCSESSIONID": "cookie-session-456"})

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
                    "timeout": 300,
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

    def test_main_prepare_analysis_uses_fixed_standard_highlight_selection(self):
        connector = self.connector()
        with mock.patch.object(connector, "prepare_analysis", return_value=0) as prepare:
            status = connector.main(
                [
                    "prepare-analysis",
                    "--input-dir", "in",
                    "--output-dir", "out",
                ]
            )

        self.assertEqual(status, 0)
        self.assertEqual(
            prepare.call_args.kwargs,
            {"input_dir": "in", "output_dir": "out", "brand_top_n": 30},
        )

    def test_main_status_reads_local_collection_state_without_runtime_credentials(self):
        connector = self.connector()
        with tempfile.TemporaryDirectory() as directory, mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            status = connector.main(["status", "--output-dir", directory])

        self.assertEqual(status, 0)
        self.assertEqual(json.loads(stdout.getvalue())["status"], "not_started")

    def test_render_command_requires_a_model_analysis_provenance_receipt(self):
        connector = self.connector()
        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "sys.stderr", new_callable=io.StringIO
        ):
            analysis_path = Path(directory) / "yuntu-ai-analysis.json"
            analysis_path.write_text("{}", encoding="utf-8")
            with self.assertRaises(SystemExit) as context:
                connector.main(
                    [
                        "render-report",
                        "--analysis-json",
                        str(analysis_path),
                        "--output-dir",
                        str(Path(directory) / "report"),
                    ]
                )
        self.assertEqual(context.exception.code, 2)

    def test_attest_analysis_writes_a_model_generated_receipt(self):
        connector = self.connector()
        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "sys.stdout", new_callable=io.StringIO
        ) as stdout:
            root = Path(directory)
            analysis_path = root / "yuntu-ai-analysis.json"
            fact_pack_path = root / "yuntu-analysis-data.json"
            prompt_path = root / "yuntu-analysis-prompt.md"
            analysis_path.write_text("{}", encoding="utf-8")
            fact_pack_path.write_text("{}", encoding="utf-8")
            prompt_path.write_text("prompt", encoding="utf-8")

            status = connector.main(
                [
                    "attest-analysis",
                    "--analysis-json", str(analysis_path),
                    "--fact-pack-json", str(fact_pack_path),
                    "--prompt", str(prompt_path),
                    "--source", "model_generated",
                    "--generator", "codex",
                ]
            )
            receipt = json.loads(
                (root / "yuntu-ai-analysis.provenance.json").read_text(encoding="utf-8")
            )

        self.assertEqual(status, 0)
        self.assertIn("yuntu-ai-analysis.provenance.json", stdout.getvalue())
        self.assertEqual(receipt["analysisSource"], "model_generated")
        self.assertEqual(receipt["generator"], "codex")

    def test_attest_analysis_can_write_a_receipt_outside_the_analysis_directory(self):
        connector = self.connector()
        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "sys.stdout", new_callable=io.StringIO
        ):
            root = Path(directory)
            analysis_path = root / "analysis" / "yuntu-ai-analysis.json"
            fact_pack_path = root / "analysis" / "yuntu-analysis-data.json"
            prompt_path = root / "analysis" / "yuntu-analysis-prompt.md"
            receipt_path = root / "receipts" / "analysis-provenance.json"
            analysis_path.parent.mkdir()
            analysis_path.write_text("{}", encoding="utf-8")
            fact_pack_path.write_text("{}", encoding="utf-8")
            prompt_path.write_text("prompt", encoding="utf-8")
            connector.main(
                [
                    "attest-analysis",
                    "--analysis-json", str(analysis_path),
                    "--fact-pack-json", str(fact_pack_path),
                    "--prompt", str(prompt_path),
                    "--source", "model_generated",
                    "--generator", "codex",
                    "--output", str(receipt_path),
                ]
            )
            receipt = connector.load_verified_provenance(
                analysis_json=analysis_path, provenance_path=receipt_path
            )

        self.assertEqual(receipt["analysisSource"], "model_generated")

    def test_analysis_unit_manifest_receipt_rejects_a_tampered_unit(self):
        connector = self.connector()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            unit_dir = root / "analysis-units"
            unit_dir.mkdir()
            analysis_path = root / "yuntu-ai-analysis.json"
            prompt_path = root / "yuntu-analysis-prompt.md"
            report_path = root / "report-data.json"
            unit_path = unit_dir / "ranking-brand-input.json"
            manifest_path = unit_dir / "analysis-unit-manifest.json"
            analysis_path.write_text(
                json.dumps(
                    {
                        "topMaterialCombination": {
                            "executiveSummary": {
                                "summary": "模型综合结论",
                                "evidence": [{"metric": "exposure", "value": 1}],
                                "material_ids": ["1"],
                            },
                            "brandConclusions": [],
                            "brandComparisonConclusion": {
                                "summary": "模型品牌比较结论",
                                "evidence": [
                                    {"brand": "示例品牌", "metric": "exposure", "value": 1}
                                ],
                                "material_ids": ["1"],
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )
            prompt_path.write_text("prompt", encoding="utf-8")
            report_path.write_text("{}", encoding="utf-8")
            unit_path.write_text('{"evidence":{}}', encoding="utf-8")
            digest = hashlib.sha256(unit_path.read_bytes()).hexdigest()
            manifest_path.write_text(
                json.dumps(
                    {
                        "executionMode": "single_model_call",
                        "units": [
                            {
                                "path": "analysis-units/ranking-brand-input.json",
                                "bytes": unit_path.stat().st_size,
                                "sha256": digest,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            receipt_path = connector.attest_analysis(
                analysis_json=analysis_path,
                fact_pack_json=manifest_path,
                prompt_path=prompt_path,
                source="model_generated",
                generator="codex",
            )
            unit_path.write_text('{"evidence":{"changed":true}}', encoding="utf-8")

            with self.assertRaisesRegex(
                connector.YuntuAnalysisProvenanceError,
                "analysis unit does not match manifest",
            ):
                connector.load_verified_provenance(
                    analysis_json=analysis_path,
                    provenance_path=receipt_path,
                )

    def test_attest_analysis_validates_single_call_output_before_writing_receipt(self):
        connector = self.connector()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            unit_dir = root / "analysis-units"
            unit_dir.mkdir()
            analysis_path = root / "yuntu-ai-analysis.json"
            prompt_path = root / "yuntu-analysis-prompt.md"
            report_path = root / "report-data.json"
            unit_path = unit_dir / "ranking-brand-input.json"
            manifest_path = unit_dir / "analysis-unit-manifest.json"
            analysis_path.write_text("{}", encoding="utf-8")
            prompt_path.write_text("prompt", encoding="utf-8")
            report_path.write_text("{}", encoding="utf-8")
            unit_path.write_text('{"evidence":{}}', encoding="utf-8")
            manifest_path.write_text(
                json.dumps(
                    {
                        "executionMode": "single_model_call",
                        "units": [
                            {
                                "path": "analysis-units/ranking-brand-input.json",
                                "bytes": unit_path.stat().st_size,
                                "sha256": hashlib.sha256(unit_path.read_bytes()).hexdigest(),
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                connector.YuntuAnalysisProvenanceError,
                "analysis validation failed",
            ):
                connector.attest_analysis(
                    analysis_json=analysis_path,
                    fact_pack_json=manifest_path,
                    prompt_path=prompt_path,
                    source="model_generated",
                    generator="current-dialog-model",
                )

            self.assertFalse(
                (root / "yuntu-ai-analysis.provenance.json").exists()
            )

    def test_render_command_passes_verified_model_source_to_renderer(self):
        connector = self.connector()
        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "sys.stdout", new_callable=io.StringIO
        ):
            root = Path(directory)
            analysis_path = root / "yuntu-ai-analysis.json"
            fact_pack_path = root / "yuntu-analysis-data.json"
            prompt_path = root / "yuntu-analysis-prompt.md"
            analysis_path.write_text("{}", encoding="utf-8")
            fact_pack_path.write_text("{}", encoding="utf-8")
            prompt_path.write_text("prompt", encoding="utf-8")
            connector.main(
                [
                    "attest-analysis",
                    "--analysis-json", str(analysis_path),
                    "--fact-pack-json", str(fact_pack_path),
                    "--prompt", str(prompt_path),
                    "--source", "manual_model_generated",
                    "--generator", "reviewer",
                ]
            )
            with mock.patch.object(connector, "render_report", return_value=0) as render:
                status = connector.main(
                    [
                        "render-report",
                        "--analysis-json", str(analysis_path),
                        "--fact-pack-json", str(fact_pack_path),
                        "--output-dir", str(root / "report"),
                    ]
                )

        self.assertEqual(status, 0)
        self.assertEqual(
            render.call_args.kwargs["analysis_provenance"]["analysisSource"],
            "manual_model_generated",
        )

    def test_render_command_prefers_report_projection_when_no_fact_pack_is_given(self):
        connector = self.connector()
        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "sys.stdout", new_callable=io.StringIO
        ):
            root = Path(directory)
            analysis_path = root / "yuntu-ai-analysis.json"
            complete_path = root / "yuntu-analysis-data.json"
            report_path = root / "report-data.json"
            prompt_path = root / "yuntu-analysis-prompt.md"
            analysis_path.write_text("{}", encoding="utf-8")
            complete_path.write_text('{"source":"complete"}', encoding="utf-8")
            report_path.write_text('{"source":"report"}', encoding="utf-8")
            prompt_path.write_text("prompt", encoding="utf-8")
            connector.main(
                [
                    "attest-analysis",
                    "--analysis-json", str(analysis_path),
                    "--fact-pack-json", str(complete_path),
                    "--prompt", str(prompt_path),
                    "--source", "model_generated",
                    "--generator", "codex",
                ]
            )
            with mock.patch.object(connector, "render_report", return_value=0) as render:
                status = connector.main(
                    [
                        "render-report",
                        "--analysis-json", str(analysis_path),
                        "--output-dir", str(root / "report"),
                    ]
                )

        self.assertEqual(status, 0)
        self.assertEqual(render.call_args.kwargs["fact_pack"], {"source": "report"})
        self.assertEqual(render.call_args.kwargs["highlight_asset_root"], root.parent)

    def test_render_command_falls_back_to_complete_fact_pack_for_legacy_batches(self):
        connector = self.connector()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis_path = root / "yuntu-ai-analysis.json"
            complete_path = root / "yuntu-analysis-data.json"
            analysis_path.write_text("{}", encoding="utf-8")
            complete_path.write_text('{"source":"complete"}', encoding="utf-8")
            with mock.patch.object(
                connector, "load_verified_provenance", return_value={}
            ), mock.patch.object(connector, "render_report", return_value=0) as render:
                status = connector.main(
                    [
                        "render-report",
                        "--analysis-json", str(analysis_path),
                        "--output-dir", str(root / "report"),
                    ]
                )

        self.assertEqual(status, 0)
        self.assertEqual(render.call_args.kwargs["fact_pack"], {"source": "complete"})

    def test_programmatic_fallback_analysis_is_disabled(self):
        connector = self.connector()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis_path = root / "yuntu-ai-analysis.json"
            fact_pack_path = root / "yuntu-analysis-data.json"
            prompt_path = root / "yuntu-analysis-prompt.md"
            analysis_path.write_text("{}", encoding="utf-8")
            fact_pack_path.write_text("{}", encoding="utf-8")
            prompt_path.write_text("prompt", encoding="utf-8")

            with self.assertRaises(SystemExit) as context:
                connector.main(
                    [
                        "attest-analysis",
                        "--analysis-json", str(analysis_path),
                        "--fact-pack-json", str(fact_pack_path),
                        "--prompt", str(prompt_path),
                        "--source", "programmatic_fallback",
                        "--generator", "rules",
                        "--allow-programmatic-fallback",
                    ]
                )

        self.assertEqual(context.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
