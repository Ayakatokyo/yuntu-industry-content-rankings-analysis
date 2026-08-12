#!/usr/bin/env python3
"""Analyze Yuntu industry-content rankings with fixed Yuce RPA connectors."""

import argparse
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import requests


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

try:
    from yuntu_batch import (
        ConnectorInvoker,
        collection_status,
        fetch_batch,
        retry_failed_batch,
    )
except ImportError:
    ConnectorInvoker = None
    collection_status = None
    fetch_batch = None
    retry_failed_batch = None

try:
    from yuntu_analysis import prepare_analysis
except ImportError:
    prepare_analysis = None

try:
    from yuntu_analysis_provenance import (
        ALL_SOURCES,
        YuntuAnalysisProvenanceError,
        attest_analysis,
        default_provenance_path,
        load_verified_provenance,
    )
except ImportError:
    ALL_SOURCES = ()
    YuntuAnalysisProvenanceError = RuntimeError
    attest_analysis = None
    default_provenance_path = None
    load_verified_provenance = None

try:
    from yuntu_report import render_report
except ImportError:
    render_report = None


LIST_FUNCTION_CODE = "rpa.conn.juliang.yt.industry.content.rankings.list"
DETAIL_FUNCTION_CODE = "rpa.conn.juliang.yt.industry.content.rankings.detail"
PLATFORM = "RPA_JULIANG_YT_ACCOUNT_PASSWORD"
DATA_SOURCE_TYPE = "rpa"
HEADERS = {"Content-Type": "application/json"}
REQUIRED_ENVIRONMENT = (
    "ENV_BACKEND_HOST",
    "YUCE_AUTHORIZATION",
    "YUCE_SESSION_ID",
)
DATE_RANGE_TYPES = {"LAST_7_DAYS", "LAST_30_DAYS", "CUSTOM"}
AGE_VALUES = {
    "AGE_18_19",
    "AGE_20_23",
    "AGE_24_30",
    "AGE_31_35",
    "AGE_36_40",
    "AGE_41_45",
    "AGE_46_50",
    "AGE_51_55",
    "AGE_56_59",
    "AGE_60_PLUS",
}
GENDER_VALUES = {"MALE", "FEMALE"}
CROWD_GROUP_VALUES = {
    "TOWN_YOUTH",
    "GENZ",
    "SENIOR_MIDDLE",
    "REFINED_MOM",
    "NEW_WHITE_COLLAR",
    "URBAN_SILVER",
    "TOWN_MIDDLE_ELDER",
    "URBAN_BLUE_COLLAR",
}
RANKING_LIMIT_VALUES = {
    "EXPOSURE_TOP1000",
    "CTR_TOP1000",
    "INTERACTION_RATE_TOP1000",
    "COMPLETION_RATE_TOP1000",
}
BRAND_SCOPE_VALUES = {"ALL_INDUSTRY", "SPECIFIED_BRANDS"}
LIST_FIELDS = {
    "industry",
    "time_range_type",
    "custom_start_date",
    "custom_end_date",
    "ages",
    "genders",
    "crowd_groups",
    "brand_scope_type",
    "brands",
    "ranking_limit_type",
}
DETAIL_FIELDS = {
    "material_id",
    "date_range_type",
    "custom_start_date",
    "custom_end_date",
}
SHANGHAI_TIMEZONE = ZoneInfo("Asia/Shanghai")

BUSINESS_PARAMS_SCHEMA = {
    "schema_type": "reference_metadata",
    "title": "云图行业内容榜单分析",
    "list_fields": sorted(LIST_FIELDS),
    "detail_date_fields": [
        "date_range_type",
        "custom_start_date",
        "custom_end_date",
    ],
    "top_n": {"type": "positive integer", "default": 10},
}


class RpaConnectorError(RuntimeError):
    """Raised when the connector cannot safely complete an operation."""


def shanghai_today(now=None):
    if now is None:
        return datetime.now(SHANGHAI_TIMEZONE).date()
    return now.astimezone(SHANGHAI_TIMEZONE).date()


def runtime_config(environ=None):
    environment = os.environ if environ is None else environ
    missing = [
        name
        for name in REQUIRED_ENVIRONMENT
        if not str(environment.get(name) or "").strip()
    ]
    if missing:
        raise RpaConnectorError(
            "missing RPA runtime environment variables: " + ", ".join(missing)
        )

    api_base = environment["ENV_BACKEND_HOST"].strip().rstrip("/")
    parsed = urlsplit(api_base)
    try:
        valid_port = parsed.port is None or parsed.port > 0
    except ValueError:
        valid_port = False
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

    authorization = environment["YUCE_AUTHORIZATION"].strip()
    session_id = environment["YUCE_SESSION_ID"].strip()
    return api_base, authorization, session_id, {"YCSESSIONID": authorization}


def _parse_date(value, field_name):
    if not isinstance(value, str):
        raise RpaConnectorError(
            f"{field_name} must use YYYYMMDD or YYYY-MM-DD format"
        )
    for date_format in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, date_format).date()
        except ValueError:
            pass
    raise RpaConnectorError(f"{field_name} must use YYYYMMDD or YYYY-MM-DD format")


def _normalize_multivalue(value, field_name, allowed_values=None):
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("["):
            try:
                values = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise RpaConnectorError(
                    f"{field_name} must be a comma-separated string or JSON array"
                ) from exc
        else:
            values = value.split(",")
    elif isinstance(value, list):
        values = value
    else:
        raise RpaConnectorError(
            f"{field_name} must be a comma-separated string or JSON array"
        )

    if not isinstance(values, list) or not values:
        raise RpaConnectorError(f"{field_name} must contain one or more strings")
    normalized = []
    for item in values:
        if not isinstance(item, str):
            raise RpaConnectorError(f"{field_name} values must be strings")
        item = item.strip()
        if not item:
            raise RpaConnectorError(f"{field_name} values cannot be blank")
        if item in normalized:
            raise RpaConnectorError(f"{field_name} cannot contain duplicates")
        if allowed_values is not None and item not in allowed_values:
            raise RpaConnectorError(
                f"{field_name} contains an unsupported value: {item}"
            )
        normalized.append(item)
    return normalized


def validate_list_business_params(raw_params):
    if not isinstance(raw_params, dict):
        raise RpaConnectorError("list business_params must be an object")
    unexpected = set(raw_params) - LIST_FIELDS
    if unexpected:
        raise RpaConnectorError(
            "unexpected list business parameters: " + ", ".join(sorted(unexpected))
        )

    params = {}
    if "industry" in raw_params:
        industry = raw_params["industry"]
        if not isinstance(industry, str) or not industry.strip():
            raise RpaConnectorError("industry must be a nonblank string")
        params["industry"] = industry.strip()

    date_range_type = raw_params.get("time_range_type")
    if date_range_type is not None:
        if not isinstance(date_range_type, str) or date_range_type not in DATE_RANGE_TYPES:
            raise RpaConnectorError(
                "time_range_type must be one of: " + ", ".join(sorted(DATE_RANGE_TYPES))
            )
        params["time_range_type"] = date_range_type

    custom_start = raw_params.get("custom_start_date")
    custom_end = raw_params.get("custom_end_date")
    if date_range_type == "CUSTOM":
        if not custom_start or not custom_end:
            raise RpaConnectorError("CUSTOM requires custom_start_date and custom_end_date")
        start = _parse_date(custom_start, "custom_start_date")
        end = _parse_date(custom_end, "custom_end_date")
        today = shanghai_today()
        if start < today - timedelta(days=369):
            raise RpaConnectorError("custom_start_date cannot be more than 369 days before today")
        if end > today - timedelta(days=4):
            raise RpaConnectorError("custom_end_date cannot be later than today-4")
        if end < start:
            raise RpaConnectorError("custom_end_date cannot be earlier than custom_start_date")
        if (end - start).days > 44:
            raise RpaConnectorError("custom date span cannot exceed 44 days")
        params["custom_start_date"] = custom_start
        params["custom_end_date"] = custom_end
    elif custom_start is not None or custom_end is not None:
        raise RpaConnectorError(
            "custom_start_date and custom_end_date are only valid for CUSTOM"
        )

    for field_name in ("ages", "genders", "crowd_groups"):
        if field_name in raw_params:
            params[field_name] = _normalize_multivalue(raw_params[field_name], field_name)

    scope = raw_params.get("brand_scope_type")
    if scope is not None:
        if not isinstance(scope, str) or scope not in BRAND_SCOPE_VALUES:
            raise RpaConnectorError(
                "brand_scope_type must be one of: "
                + ", ".join(sorted(BRAND_SCOPE_VALUES))
            )
        params["brand_scope_type"] = scope
    if "brands" in raw_params:
        brands = _normalize_multivalue(raw_params["brands"], "brands")
        if scope != "SPECIFIED_BRANDS":
            raise RpaConnectorError("brands requires brand_scope_type SPECIFIED_BRANDS")
        if not 3 <= len(brands) <= 10:
            raise RpaConnectorError("brands must contain 3 to 10 values")
        params["brands"] = brands
    elif scope == "SPECIFIED_BRANDS":
        raise RpaConnectorError("SPECIFIED_BRANDS requires brands")

    if "ranking_limit_type" in raw_params:
        ranking_limit_type = raw_params["ranking_limit_type"]
        if (
            not isinstance(ranking_limit_type, str)
            or ranking_limit_type not in RANKING_LIMIT_VALUES
        ):
            raise RpaConnectorError(
                "ranking_limit_type must be one of: "
                + ", ".join(sorted(RANKING_LIMIT_VALUES))
            )
        params["ranking_limit_type"] = ranking_limit_type
    return params


def validate_detail_business_params(raw_params):
    if not isinstance(raw_params, dict):
        raise RpaConnectorError("detail business_params must be an object")
    unexpected = set(raw_params) - DETAIL_FIELDS
    if unexpected:
        raise RpaConnectorError(
            "unexpected detail business parameters: " + ", ".join(sorted(unexpected))
        )
    material_id = raw_params.get("material_id")
    if not isinstance(material_id, str) or not material_id.isdigit():
        raise RpaConnectorError("material_id must contain digits only")
    date_range_type = raw_params.get("date_range_type")
    if date_range_type not in DATE_RANGE_TYPES:
        raise RpaConnectorError(
            "date_range_type must be one of: " + ", ".join(sorted(DATE_RANGE_TYPES))
        )

    params = {"material_id": material_id, "date_range_type": date_range_type}
    start_date = raw_params.get("custom_start_date")
    end_date = raw_params.get("custom_end_date")
    if date_range_type == "CUSTOM":
        if not start_date or not end_date:
            raise RpaConnectorError("CUSTOM requires custom_start_date and custom_end_date")
        start = _parse_date(start_date, "custom_start_date")
        end = _parse_date(end_date, "custom_end_date")
        if end < start:
            raise RpaConnectorError(
                "custom_end_date cannot be earlier than custom_start_date"
            )
        params["custom_start_date"] = start_date
        params["custom_end_date"] = end_date
    elif start_date is not None or end_date is not None:
        raise RpaConnectorError(
            "custom_start_date and custom_end_date are only valid for CUSTOM"
        )
    return params


def _default_session():
    return requests.Session()


def _raise_for_status(response, action):
    try:
        response.raise_for_status()
    except Exception as exc:
        raise RpaConnectorError(f"unable to {action}: {exc}") from exc


def _response_json(response, action):
    try:
        return response.json()
    except Exception as exc:
        raise RpaConnectorError(
            f"unable to decode {action} response as JSON: {exc}"
        ) from exc


def _require_successful_result(result):
    if not isinstance(result, dict) or result.get("success") is not True:
        raise RpaConnectorError("gateway returned an unsuccessful result")
    return result


def list_accounts(environ=None, session=None):
    session = _default_session() if session is None else session
    api_base, authorization, _session_id, cookies = runtime_config(environ)
    try:
        response = session.post(
            f"{api_base}/adg/v1/agent/rpa/authorizations/query",
            json={
                "authorization": authorization,
                "platform": "RPA_JULIANG_YT_ACCOUNT_PASSWORD",
            },
            headers=HEADERS,
            cookies=cookies,
            timeout=30,
        )
    except Exception as exc:
        raise RpaConnectorError(
            "unable to list RPA accounts: transport request failed"
        ) from exc
    _raise_for_status(response, "list RPA accounts")
    return _require_successful_result(_response_json(response, "list RPA accounts"))


def _invoke(operation, shop_id, business_params, environ=None, session=None):
    if operation == "list":
        function_code = "rpa.conn.juliang.yt.industry.content.rankings.list"
    elif operation == "detail":
        function_code = "rpa.conn.juliang.yt.industry.content.rankings.detail"
    else:
        raise RpaConnectorError("operation must be list or detail")
    if not isinstance(shop_id, str) or not shop_id.strip():
        raise RpaConnectorError("shop_id is required")
    session = _default_session() if session is None else session
    api_base, authorization, session_id, cookies = runtime_config(environ)
    try:
        response = session.post(
            f"{api_base}/adg/v1/agent/invoke",
            json={
                "authorization": authorization,
                "agent_session_id": session_id,
                "data_source_type": "rpa",
                "platform": "RPA_JULIANG_YT_ACCOUNT_PASSWORD",
                "function_code": function_code,
                "business_params": business_params,
                "shop_id": shop_id.strip(),
            },
            headers=HEADERS,
            cookies=cookies,
            timeout=3600,
        )
    except Exception as exc:
        raise RpaConnectorError(
            f"unable to fetch RPA {operation}: transport request failed"
        ) from exc
    _raise_for_status(response, f"fetch RPA {operation}")
    return _require_successful_result(
        _response_json(response, f"fetch RPA {operation}")
    )


def invoke_list(shop_id, business_params, environ=None, session=None):
    return _invoke(
        "list",
        shop_id,
        business_params,
        environ=environ,
        session=session,
    )


def invoke_detail(shop_id, business_params, environ=None, session=None):
    return _invoke(
        "detail",
        shop_id,
        business_params,
        environ=environ,
        session=session,
    )


def write_json_atomically(result, output_path):
    target = Path(output_path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".tmp",
            dir=target.parent,
            delete=False,
        ) as staging_file:
            staging_path = Path(staging_file.name)
            json.dump(result, staging_file, ensure_ascii=False, indent=2)
            staging_file.write("\n")
        os.replace(staging_path, target)
    except Exception as exc:
        if "staging_path" in locals():
            try:
                staging_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise RpaConnectorError(f"unable to write JSON output: {exc}") from exc
    return target


def select_material_ids(result, top_n):
    if isinstance(top_n, bool) or not isinstance(top_n, int) or top_n <= 0:
        raise RpaConnectorError("top_n must be a positive integer")

    selected = []
    seen = set()

    def visit(value):
        if len(selected) >= top_n:
            return
        if isinstance(value, dict):
            for key, nested_value in value.items():
                if key == "material_id" and isinstance(nested_value, str) and nested_value.isdigit():
                    if nested_value not in seen:
                        seen.add(nested_value)
                        selected.append(nested_value)
                        if len(selected) >= top_n:
                            return
                visit(nested_value)
                if len(selected) >= top_n:
                    return
        elif isinstance(value, list):
            for nested_value in value:
                visit(nested_value)
                if len(selected) >= top_n:
                    return

    visit(result)
    return selected


def _validate_top_n(top_n):
    if isinstance(top_n, bool) or not isinstance(top_n, int) or top_n <= 0:
        raise RpaConnectorError("top_n must be a positive integer")
    return top_n


def _validate_detail_date_params(raw_params):
    if not isinstance(raw_params, dict):
        raise RpaConnectorError("detail business_params must be an object")
    if "material_id" in raw_params:
        raise RpaConnectorError("material_id is selected from the list response")
    return validate_detail_business_params({"material_id": "0", **raw_params})


def _safe_error_summary(error, environ):
    message = str(error).strip() or error.__class__.__name__
    environment = os.environ if environ is None else environ
    for name in REQUIRED_ENVIRONMENT:
        value = str(environment.get(name) or "").strip()
        if value:
            message = message.replace(value, "[redacted]")
    return message


def _manifest(*, status, filters, detail_date_range, list_response_path,
              selected_material_ids, details, error=None):
    result = {
        "status": status,
        "filters": filters,
        "detail_date_range": detail_date_range,
        "list_response_path": list_response_path,
        "selected_material_ids": selected_material_ids,
        "details": details,
    }
    if error:
        result["error"] = error
    return result


def fetch_analysis(
    shop_id,
    raw_list_params,
    raw_detail_params,
    *,
    top_n=10,
    output_dir,
    environ=None,
    session=None,
):
    """Fetch a rankings list, then retain seconds-level details for its materials.

    A failed list is terminal. Detail failures are recorded and do not stop the
    remaining material requests; callers receive 1 when any terminal or detail
    failure occurs and 0 only when every selected material succeeds.
    """
    list_params = validate_list_business_params(raw_list_params)
    detail_date_params = _validate_detail_date_params(raw_detail_params)
    top_n = _validate_top_n(top_n)
    if not isinstance(shop_id, str) or not shop_id.strip():
        raise RpaConnectorError("shop_id is required")

    output = Path(output_dir)
    manifest_path = output / "manifest.json"
    list_response_path = output / "list-response.json"
    detail_date_range = {
        key: value for key, value in detail_date_params.items() if key != "material_id"
    }

    try:
        list_result = invoke_list(
            shop_id, list_params, environ=environ, session=session
        )
    except RpaConnectorError as exc:
        write_json_atomically(
            _manifest(
                status="list_failed",
                filters=list_params,
                detail_date_range=detail_date_range,
                list_response_path=None,
                selected_material_ids=[],
                details=[],
                error=_safe_error_summary(exc, environ),
            ),
            manifest_path,
        )
        return 1

    write_json_atomically(list_result, list_response_path)
    material_ids = select_material_ids(list_result, top_n)
    if not material_ids:
        write_json_atomically(
            _manifest(
                status="no_material_ids",
                filters=list_params,
                detail_date_range=detail_date_range,
                list_response_path="list-response.json",
                selected_material_ids=[],
                details=[],
                error="list response contained no valid material_id values",
            ),
            manifest_path,
        )
        return 1

    details = []
    for material_id in material_ids:
        relative_path = f"details/{material_id}.json"
        try:
            detail_result = invoke_detail(
                shop_id,
                {**detail_date_range, "material_id": material_id},
                environ=environ,
                session=session,
            )
            write_json_atomically(detail_result, output / relative_path)
            details.append(
                {
                    "material_id": material_id,
                    "status": "success",
                    "path": relative_path,
                }
            )
        except RpaConnectorError as exc:
            details.append(
                {
                    "material_id": material_id,
                    "status": "failed",
                    "error": _safe_error_summary(exc, environ),
                }
            )

    has_failures = any(item["status"] == "failed" for item in details)
    write_json_atomically(
        _manifest(
            status="details_failed" if has_failures else "success",
            filters=list_params,
            detail_date_range=detail_date_range,
            list_response_path="list-response.json",
            selected_material_ids=material_ids,
            details=details,
        ),
        manifest_path,
    )
    return 1 if has_failures else 0


def fetch_batch_analysis(
    shop_id,
    raw_list_params,
    raw_detail_params,
    *,
    target_top_n=10,
    candidate_top_n=None,
    output_dir,
):
    if fetch_batch is None or ConnectorInvoker is None:
        raise RpaConnectorError("batch fetch support is unavailable")
    list_params = validate_list_business_params(raw_list_params)
    detail_date_params = _validate_detail_date_params(raw_detail_params)
    detail_date_range = {
        key: value for key, value in detail_date_params.items() if key != "material_id"
    }
    target_top_n = _validate_top_n(target_top_n)
    candidate_top_n = (
        target_top_n * 3 if candidate_top_n is None else _validate_top_n(candidate_top_n)
    )
    try:
        return fetch_batch(
            shop_id=shop_id,
            list_params=list_params,
            detail_date_params=detail_date_range,
            target_top_n=target_top_n,
            candidate_top_n=candidate_top_n,
            output_dir=output_dir,
            invoker=ConnectorInvoker(
                lambda sid, params: invoke_list(sid, params),
                lambda sid, params: invoke_detail(sid, params),
            ),
        )
    except Exception as exc:
        raise RpaConnectorError(str(exc)) from exc


def retry_failed_batch_analysis(shop_id, *, output_dir):
    if retry_failed_batch is None or ConnectorInvoker is None:
        raise RpaConnectorError("batch retry support is unavailable")
    try:
        return retry_failed_batch(
            shop_id=shop_id,
            output_dir=output_dir,
            invoker=ConnectorInvoker(
                lambda sid, params: invoke_list(sid, params),
                lambda sid, params: invoke_detail(sid, params),
            ),
        )
    except Exception as exc:
        raise RpaConnectorError(str(exc)) from exc


def _positive_int_argument(value):
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _parser():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list-accounts", help="List available RPA accounts")
    commands.add_parser("schema", help="Print analysis parameter metadata")
    commands.add_parser("self-test", help="Run offline connector checks")
    status_parser = commands.add_parser("status", help="Read collection lifecycle state")
    status_parser.add_argument("--output-dir", required=True)
    prepare_parser = commands.add_parser(
        "prepare-analysis", help="Prepare Yuntu analysis facts"
    )
    prepare_parser.add_argument("--input-dir", required=True)
    prepare_parser.add_argument("--output-dir", required=True)
    attest_parser = commands.add_parser(
        "attest-analysis", help="Record the source of a model-authored analysis JSON"
    )
    attest_parser.add_argument("--analysis-json", required=True)
    attest_parser.add_argument("--fact-pack-json", required=True)
    attest_parser.add_argument("--prompt", required=True)
    attest_parser.add_argument("--source", required=True, choices=sorted(ALL_SOURCES))
    attest_parser.add_argument("--generator", required=True)
    attest_parser.add_argument("--output")
    attest_parser.add_argument("--allow-programmatic-fallback", action="store_true")
    report_parser = commands.add_parser("render-report", help="Render Yuntu final report")
    report_parser.add_argument("--analysis-json", required=True)
    report_parser.add_argument("--output-dir", required=True)
    report_parser.add_argument("--fact-pack-json")
    report_parser.add_argument("--analysis-provenance")
    report_parser.add_argument("--highlight-asset-root")
    report_parser.add_argument("--allow-programmatic-fallback", action="store_true")
    retry_parser = commands.add_parser(
        "retry-failed", help="Retry rejected detail fetches from an existing batch"
    )
    retry_parser.add_argument("--shop-id", required=True)
    retry_parser.add_argument("--output-dir", required=True)
    fetch_parser = commands.add_parser("fetch", help="Fetch a list and details")
    fetch_parser.add_argument("--shop-id", required=True)
    fetch_parser.add_argument("--top-n", type=_positive_int_argument, default=10)
    fetch_parser.add_argument("--target-top-n", type=_positive_int_argument)
    fetch_parser.add_argument("--candidate-top-n", type=_positive_int_argument)
    fetch_parser.add_argument("--output-dir", required=True)
    fetch_parser.add_argument("--industry")
    fetch_parser.add_argument("--time-range-type")
    fetch_parser.add_argument("--custom-start-date")
    fetch_parser.add_argument("--custom-end-date")
    fetch_parser.add_argument("--ages")
    fetch_parser.add_argument("--genders")
    fetch_parser.add_argument("--crowd-groups")
    fetch_parser.add_argument("--brand-scope-type")
    fetch_parser.add_argument("--brands")
    fetch_parser.add_argument("--ranking-limit-type")
    fetch_parser.add_argument("--detail-date-range-type", required=True)
    fetch_parser.add_argument("--detail-custom-start-date")
    fetch_parser.add_argument("--detail-custom-end-date")
    return parser


def _cmd_self_test():
    if LIST_FUNCTION_CODE != "rpa.conn.juliang.yt.industry.content.rankings.list":
        raise RpaConnectorError("unexpected list function code")
    if DETAIL_FUNCTION_CODE != "rpa.conn.juliang.yt.industry.content.rankings.detail":
        raise RpaConnectorError("unexpected detail function code")
    if PLATFORM != "RPA_JULIANG_YT_ACCOUNT_PASSWORD" or DATA_SOURCE_TYPE != "rpa":
        raise RpaConnectorError("unexpected fixed gateway metadata")
    validate_list_business_params({})
    validate_detail_business_params(
        {"material_id": "1", "date_range_type": "LAST_7_DAYS"}
    )
    if select_material_ids({"material_id": "1"}, 10) != ["1"]:
        raise RpaConnectorError("unexpected material ID selection")
    print("self-test passed")


def _list_params_from_args(args):
    return {
        name: value
        for name, value in {
            "industry": args.industry,
            "time_range_type": args.time_range_type,
            "custom_start_date": args.custom_start_date,
            "custom_end_date": args.custom_end_date,
            "ages": args.ages,
            "genders": args.genders,
            "crowd_groups": args.crowd_groups,
            "brand_scope_type": args.brand_scope_type,
            "brands": args.brands,
            "ranking_limit_type": args.ranking_limit_type,
        }.items()
        if value is not None
    }


def main(argv=None):
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "list-accounts":
            print(json.dumps(list_accounts(), ensure_ascii=False, indent=2))
            return 0
        if args.command == "schema":
            print(json.dumps(BUSINESS_PARAMS_SCHEMA, ensure_ascii=False, indent=2))
            return 0
        if args.command == "self-test":
            _cmd_self_test()
            return 0
        if args.command == "status":
            if collection_status is None:
                raise RpaConnectorError("batch status support is unavailable")
            print(json.dumps(collection_status(output_dir=args.output_dir), ensure_ascii=False, indent=2))
            return 0
        if args.command == "prepare-analysis":
            if prepare_analysis is None:
                raise RpaConnectorError("analysis preparation support is unavailable")
            return prepare_analysis(
                input_dir=args.input_dir,
                output_dir=args.output_dir,
            )
        if args.command == "attest-analysis":
            if attest_analysis is None:
                raise RpaConnectorError("analysis provenance support is unavailable")
            try:
                receipt = attest_analysis(
                    analysis_json=args.analysis_json,
                    fact_pack_json=args.fact_pack_json,
                    prompt_path=args.prompt,
                    source=args.source,
                    generator=args.generator,
                    output_path=args.output,
                    allow_programmatic_fallback=args.allow_programmatic_fallback,
                )
            except YuntuAnalysisProvenanceError as exc:
                raise RpaConnectorError(str(exc)) from exc
            print(receipt)
            return 0
        if args.command == "render-report":
            if render_report is None:
                raise RpaConnectorError("report rendering support is unavailable")
            if load_verified_provenance is None or default_provenance_path is None:
                raise RpaConnectorError("analysis provenance support is unavailable")
            provenance_path = (
                Path(args.analysis_provenance)
                if args.analysis_provenance
                else default_provenance_path(args.analysis_json)
            )
            try:
                provenance = load_verified_provenance(
                    analysis_json=args.analysis_json,
                    provenance_path=provenance_path,
                    allow_programmatic_fallback=args.allow_programmatic_fallback,
                )
            except YuntuAnalysisProvenanceError as exc:
                raise RpaConnectorError(str(exc)) from exc
            fact_pack_path = Path(args.fact_pack_json) if args.fact_pack_json else Path(args.analysis_json).with_name("yuntu-analysis-data.json")
            fact_pack = {}
            if fact_pack_path.exists():
                fact_pack = json.loads(fact_pack_path.read_text(encoding="utf-8"))
            return render_report(
                analysis_json=args.analysis_json,
                output_dir=args.output_dir,
                fact_pack=fact_pack,
                analysis_provenance=provenance,
                highlight_asset_root=args.highlight_asset_root or fact_pack_path.parent.parent,
            )
        if args.command == "retry-failed":
            status = retry_failed_batch_analysis(
                args.shop_id,
                output_dir=args.output_dir,
            )
            print(Path(args.output_dir) / "batch-manifest.json")
            return status
        target_top_n = args.target_top_n or args.top_n
        status = fetch_batch_analysis(
            args.shop_id,
            _list_params_from_args(args),
            {
                "date_range_type": args.detail_date_range_type,
                "custom_start_date": args.detail_custom_start_date,
                "custom_end_date": args.detail_custom_end_date,
            },
            target_top_n=target_top_n,
            candidate_top_n=args.candidate_top_n,
            output_dir=args.output_dir,
        )
        print(Path(args.output_dir) / "batch-manifest.json")
        return status
    except RpaConnectorError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
