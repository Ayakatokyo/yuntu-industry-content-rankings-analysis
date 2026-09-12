#!/usr/bin/env python3
"""Analyze Yuntu industry-content rankings with fixed Yuce RPA connectors."""

import argparse
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import requests
from rpa_io import file_sha256


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

try:
    from yuntu_batch import (
        ConnectorInvoker,
        build_ranking_run_specs,
        collection_status,
        fetch_batch,
        retry_failed_batch,
        retry_unresolved_batch,
    )
except ImportError:
    ConnectorInvoker = None
    build_ranking_run_specs = None
    collection_status = None
    fetch_batch = None
    retry_failed_batch = None
    retry_unresolved_batch = None

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
DETAIL_FUNCTION_CODE = "rpa.conn.juliang.yt.industry.content.rankings.details"
PLATFORM = "RPA_JULIANG_YT_ACCOUNT_PASSWORD"
DATA_SOURCE_TYPE = "rpa"
HEADERS = {"Content-Type": "application/json"}
HTTP_REQUEST_TIMEOUT_SECONDS = 30
POLL_INTERVAL_SECONDS = 10
POLL_TIMEOUT_SECONDS = 3600
RUNNING_TASK_STATUSES = {"pending", "running"}
SUCCESS_TASK_STATUSES = {"completed", "partial_success"}
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
    "date_type",
    "custom_start_date",
    "custom_end_date",
}
SHANGHAI_TIMEZONE = ZoneInfo("Asia/Shanghai")

BUSINESS_PARAMS_SCHEMA = {
    "schema_type": "reference_metadata",
    "title": "云图行业内容榜单分析",
    "list_fields": sorted(LIST_FIELDS),
    "detail_date_fields": [
        "date_type",
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
        for name in REQUIRED_ENVIRONMENT[:2]
        if not str(environment.get(name) or "").strip()
    ]
    if not str(environment.get("YUCE_SESSION_ID") or environment.get("YCSESSIONID") or "").strip():
        missing.append("YUCE_SESSION_ID or YCSESSIONID")
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
    session_id = str(
        environment.get("YUCE_SESSION_ID")
        or environment.get("YCSESSIONID")
        or authorization
    ).strip()
    cookie_session = str(environment.get("YCSESSIONID") or authorization).strip()
    return api_base, authorization, session_id, {"YCSESSIONID": cookie_session}


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
    date_type = raw_params.get("date_type")
    if date_type not in DATE_RANGE_TYPES:
        raise RpaConnectorError(
            "date_type must be one of: " + ", ".join(sorted(DATE_RANGE_TYPES))
        )

    params = {"material_id": material_id, "date_type": date_type}
    start_date = raw_params.get("custom_start_date")
    end_date = raw_params.get("custom_end_date")
    if date_type == "CUSTOM":
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


def _operation_function_code(operation):
    # Keep the gateway route closed over the two supported operations.  Public
    # constants are display metadata and must not become caller-controlled code.
    if operation == "list":
        return "rpa.conn.juliang.yt.industry.content.rankings.list"
    if operation == "detail":
        return "rpa.conn.juliang.yt.industry.content.rankings.details"
    raise RpaConnectorError("operation must be list or detail")


def _response_data(response, action):
    _raise_for_status(response, action)
    result = _require_successful_result(_response_json(response, action))
    data = result.get("data")
    if not isinstance(data, dict):
        raise RpaConnectorError(f"gateway {action} response is missing an object data field")
    return data


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


def submit_fetch_task(operation, shop_id, business_params, *, environ=None, session=None):
    function_code = _operation_function_code(operation)
    if not isinstance(shop_id, str) or not shop_id.strip():
        raise RpaConnectorError("shop_id is required")
    session = _default_session() if session is None else session
    api_base, authorization, session_id, cookies = runtime_config(environ)
    try:
        response = session.post(
            f"{api_base}/adg/v1/agent/fetch/tasks",
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
            timeout=HTTP_REQUEST_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        raise RpaConnectorError(
            f"unable to submit RPA {operation}: transport request failed"
        ) from exc
    data = _response_data(response, f"submit RPA {operation}")
    task_group_id = data.get("task_group_id")
    if not isinstance(task_group_id, str) or not task_group_id.strip():
        raise RpaConnectorError(f"submit RPA {operation} response is missing task_group_id")
    return task_group_id.strip()


def query_fetch_task(
    task_group_id,
    *,
    environ=None,
    session=None,
    request_timeout_seconds=HTTP_REQUEST_TIMEOUT_SECONDS,
):
    if not isinstance(task_group_id, str) or not task_group_id.strip():
        raise RpaConnectorError("task_group_id is required")
    if request_timeout_seconds <= 0:
        raise RpaConnectorError("request_timeout_seconds must be positive")
    session = _default_session() if session is None else session
    api_base, authorization, _session_id, cookies = runtime_config(environ)
    try:
        response = session.post(
            f"{api_base}/adg/v1/agent/fetch/tasks/status",
            json={"authorization": authorization, "task_group_id": task_group_id},
            headers=HEADERS,
            cookies=cookies,
            timeout=request_timeout_seconds,
        )
    except Exception as exc:
        raise RpaConnectorError(
            "unable to query RPA task status: transport request failed"
        ) from exc
    return _response_data(response, "query RPA task status")


def wait_fetch_task(
    task_group_id,
    *,
    environ=None,
    session=None,
    timeout_seconds=POLL_TIMEOUT_SECONDS,
    poll_interval_seconds=POLL_INTERVAL_SECONDS,
):
    if timeout_seconds <= 0 or poll_interval_seconds <= 0:
        raise RpaConnectorError("task polling timeout and interval must be positive")
    deadline = time.monotonic() + timeout_seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RpaConnectorError(f"poll timeout: {task_group_id}")
        time.sleep(min(poll_interval_seconds, remaining))
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RpaConnectorError(f"poll timeout: {task_group_id}")
        result = query_fetch_task(
            task_group_id,
            environ=environ,
            session=session,
            request_timeout_seconds=min(HTTP_REQUEST_TIMEOUT_SECONDS, remaining),
        )
        status = result.get("status")
        if status in SUCCESS_TASK_STATUSES:
            return {**result, "task_group_id": task_group_id}
        if status == "failed":
            raise RpaConnectorError(f"RPA task failed: {task_group_id}")
        if status not in RUNNING_TASK_STATUSES:
            raise RpaConnectorError(f"RPA task returned unknown status {status!r}: {task_group_id}")


def _invoke(operation, shop_id, business_params, environ=None, session=None):
    task_group_id = submit_fetch_task(
        operation,
        shop_id,
        business_params,
        environ=environ,
        session=session,
    )
    return wait_fetch_task(
        task_group_id,
        environ=environ,
        session=session,
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
        validate_detail_business_params(business_params),
        environ=environ,
        session=session,
    )


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


def _batch_invoker():
    def detail_params(params):
        return {name: params[name] for name in DETAIL_FIELDS if name in params}

    return ConnectorInvoker(
        lambda sid, params: invoke_list(sid, params),
        # Selection groups are list-derived local scheduling context.  The
        # details connector contract accepts only the four DETAIL_FIELDS.
        lambda sid, params: invoke_detail(sid, detail_params(params)),
        submit_detail=lambda sid, params: submit_fetch_task(
            "detail", sid, validate_detail_business_params(detail_params(params))
        ),
        wait_detail=lambda task_group_id: wait_fetch_task(task_group_id),
    )


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
    if "time_range_type" not in raw_list_params:
        raw_list_params = {**raw_list_params, "time_range_type": "LAST_7_DAYS"}
    list_params = validate_list_business_params(raw_list_params)
    detail_date_params = _validate_detail_date_params(raw_detail_params)
    detail_date_range = {
        key: value for key, value in detail_date_params.items() if key != "material_id"
    }
    target_top_n = _validate_top_n(target_top_n)
    candidate_top_n = (
        target_top_n * 2 if candidate_top_n is None else _validate_top_n(candidate_top_n)
    )
    try:
        return fetch_batch(
            shop_id=shop_id,
            list_params=list_params,
            detail_date_params=detail_date_range,
            target_top_n=target_top_n,
            candidate_top_n=candidate_top_n,
            output_dir=output_dir,
            invoker=_batch_invoker(),
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
            invoker=_batch_invoker(),
        )
    except Exception as exc:
        raise RpaConnectorError(str(exc)) from exc


def retry_unresolved_batch_analysis(shop_id, *, output_dir):
    if retry_unresolved_batch is None or ConnectorInvoker is None:
        raise RpaConnectorError("batch unresolved retry support is unavailable")
    try:
        return retry_unresolved_batch(
            shop_id=shop_id,
            output_dir=output_dir,
            invoker=_batch_invoker(),
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
    prepare_parser.add_argument("--local-only", action="store_true", help="Reuse local assets without downloading missing videos")
    prepare_parser.add_argument("--input-dir", required=True)
    prepare_parser.add_argument("--output-dir", required=True)
    prepare_parser.add_argument(
        "--hot-material-config",
        help="Path to the project-scoped hot-material rules JSON",
    )
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
    begin_parser = commands.add_parser("begin-analysis", help="Create bound model JSON drafts and scoped contracts")
    begin_parser.add_argument("--fact-pack-json", required=True)
    begin_parser.add_argument("--workspace", required=True)
    check_parser = commands.add_parser("check-analysis", help="Check drafts without attestation or rendering")
    check_parser.add_argument("--workspace", required=True)
    check_parser.add_argument("--part", help="Only check this chapter or material key")
    assemble_parser = commands.add_parser("assemble-analysis", help="Losslessly assemble checked model drafts")
    assemble_parser.add_argument("--workspace", required=True)
    assemble_parser.add_argument("--output", required=True)
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
    retry_unresolved_parser = commands.add_parser(
        "retry-unresolved",
        help="Explicitly retry detail requests interrupted before persistence",
    )
    retry_unresolved_parser.add_argument("--shop-id", required=True)
    retry_unresolved_parser.add_argument("--output-dir", required=True)
    fetch_parser = commands.add_parser(
        "fetch", help="Fetch rankings and details in fixed three-material waves"
    )
    fetch_parser.add_argument("--shop-id", required=True)
    fetch_parser.add_argument("--top-n", type=_positive_int_argument, default=10)
    fetch_parser.add_argument(
        "--target-top-n",
        type=_positive_int_argument,
        help="Target number of materials whose details are fetched for second-level breakdown; defaults to --top-n (10)",
    )
    fetch_parser.add_argument(
        "--candidate-top-n",
        type=_positive_int_argument,
        help="Candidate-pool size for detail selection; defaults to 2x --target-top-n, not the brand analysis Top N",
    )
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
    if DETAIL_FUNCTION_CODE != "rpa.conn.juliang.yt.industry.content.rankings.details":
        raise RpaConnectorError("unexpected detail function code")
    if PLATFORM != "RPA_JULIANG_YT_ACCOUNT_PASSWORD" or DATA_SOURCE_TYPE != "rpa":
        raise RpaConnectorError("unexpected fixed gateway metadata")
    validate_list_business_params({})
    validate_detail_business_params(
        {"material_id": "1", "date_type": "LAST_7_DAYS"}
    )
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
            prepare_kwargs = {
                "input_dir": args.input_dir,
                "output_dir": args.output_dir,
            }
            if args.hot_material_config:
                prepare_kwargs["hot_material_config"] = args.hot_material_config
            return prepare_analysis(**prepare_kwargs)
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
        if args.command in {"begin-analysis", "check-analysis", "assemble-analysis"}:
            from yuntu_analysis_workspace import begin_workspace, check_workspace, assemble_workspace
            try:
                if args.command == "begin-analysis":
                    result = begin_workspace(args.fact_pack_json, args.workspace)
                elif args.command == "check-analysis":
                    result = check_workspace(args.workspace, args.part)
                else:
                    result = {"analysisJson": str(assemble_workspace(args.workspace, args.output))}
            except (ValueError, OSError) as exc:
                raise RpaConnectorError(str(exc)) from exc
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result.get("valid", True) else 1
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
            if args.fact_pack_json:
                fact_pack_path = Path(args.fact_pack_json)
            else:
                analysis_dir = Path(args.analysis_json).parent
                report_projection = analysis_dir / "report-data.json"
                fact_pack_path = (
                    report_projection
                    if report_projection.is_file()
                    else analysis_dir / "yuntu-analysis-data.json"
                )
            fact_pack = {}
            if fact_pack_path.exists():
                fact_pack = json.loads(fact_pack_path.read_text(encoding="utf-8"))
            bound = provenance.get("artifacts", {}).get("factPack", {})
            bound_path = provenance_path.parent / bound.get("path", "")
            if bound_path.is_file():
                bound_data = json.loads(bound_path.read_text(encoding="utf-8"))
                if isinstance(bound_data, dict) and bound_data.get("executionMode") == "single_model_call":
                    from yuntu_analysis_bundle import load_analysis_bundle
                    try:
                        bundle = load_analysis_bundle(bound_path)
                        if args.fact_pack_json and file_sha256(fact_pack_path) != file_sha256(bundle["reportPath"]):
                            raise ValueError("render fact pack differs from attested report projection")
                        if bundle["manifest"].get("analysisContract") and args.highlight_asset_root and Path(args.highlight_asset_root).resolve() != bundle["root"].parent.resolve():
                            raise ValueError("render asset root differs from attested asset root")
                        fact_pack, fact_pack_path = bundle["facts"], bundle["reportPath"]
                    except (ValueError, OSError) as exc:
                        raise RpaConnectorError(str(exc)) from exc
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
        if args.command == "retry-unresolved":
            status = retry_unresolved_batch_analysis(
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
                "date_type": args.detail_date_range_type,
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
