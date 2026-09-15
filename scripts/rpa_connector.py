#!/usr/bin/env python3
"""Analyze Yuntu industry-content rankings with live Yuce RPA contracts."""

import argparse
import json
import os
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit

import requests


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from rpa_io import file_sha256
from rpa_dynamic_client import (
    CONNECTOR_CODE as LIST_CONNECTOR_CODE,
    ContractError as DynamicContractError,
    ValidationContractError as DynamicValidationError,
    normalized_detail,
    resolve_platform,
    validate_business_params as validate_dynamic_business_params,
)
from rpa_dynamic_detail_client import CONNECTOR_CODE as DETAIL_CONNECTOR_CODE

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
DEFAULT_OUTPUT_DIR = "云图数据资源/yuntu-rankings-analysis"
LOCAL_DETAIL_CONTEXT_FIELDS = {
    "selectionGroupId",
    "brandId",
    "brandName",
    "touchpointCode",
    "touchpointName",
}


class RpaConnectorError(RuntimeError):
    """Raised when the connector cannot safely complete an operation."""


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


def _operation_connector_code(operation):
    if operation == "list":
        return LIST_CONNECTOR_CODE
    if operation == "detail":
        return DETAIL_CONNECTOR_CODE
    raise RpaConnectorError("operation must be list or detail")


def _response_data(response, action):
    _raise_for_status(response, action)
    result = _require_successful_result(_response_json(response, action))
    data = result.get("data")
    if not isinstance(data, dict):
        raise RpaConnectorError(f"gateway {action} response is missing an object data field")
    return data


def fetch_connector_detail(operation, *, environ=None, session=None):
    connector_code = _operation_connector_code(operation)
    session = _default_session() if session is None else session
    api_base, authorization, _session_id, cookies = runtime_config(environ)
    try:
        response = session.post(
            f"{api_base}/dcConnector/v3/listByConnectorCode",
            json={"connectorCode": connector_code},
            headers=HEADERS,
            cookies=cookies,
            timeout=HTTP_REQUEST_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        raise RpaConnectorError(
            f"unable to read RPA {operation} connector detail: transport request failed"
        ) from exc
    _raise_for_status(response, f"read RPA {operation} connector detail")
    body = _require_successful_result(
        _response_json(response, f"read RPA {operation} connector detail")
    )
    data = body.get("data")
    if not isinstance(data, list):
        raise RpaConnectorError("connector detail response data must be an array")
    matches = [
        item
        for item in data
        if isinstance(item, dict) and item.get("connectorCode") == connector_code
    ]
    if not matches:
        raise RpaConnectorError(
            f"connector {connector_code} is unavailable, unpublished, or does not support BIZ_EXPERT"
        )
    if len(matches) != 1:
        ids = [str(item.get("id") or "") for item in matches]
        raise RpaConnectorError(
            f"connector {connector_code} returned multiple details and cannot be selected uniquely: {ids}"
        )
    try:
        normalized_detail(matches[0])
    except DynamicContractError as exc:
        raise RpaConnectorError(str(exc)) from exc
    return matches[0]


def _validate_live_params(detail, business_params):
    try:
        return validate_dynamic_business_params(detail, business_params)
    except (DynamicContractError, DynamicValidationError) as exc:
        raise RpaConnectorError(str(exc)) from exc


def list_accounts(operation="list", environ=None, session=None):
    session = _default_session() if session is None else session
    detail = fetch_connector_detail(operation, environ=environ, session=session)
    api_base, authorization, _session_id, cookies = runtime_config(environ)
    try:
        response = session.post(
            f"{api_base}/adg/v1/agent/rpa/authorizations/query",
            json={
                "authorization": authorization,
                "platform": resolve_platform(detail),
            },
            headers=HEADERS,
            cookies=cookies,
            timeout=HTTP_REQUEST_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        raise RpaConnectorError(
            "unable to list RPA accounts: transport request failed"
        ) from exc
    _raise_for_status(response, "list RPA accounts")
    return _require_successful_result(_response_json(response, "list RPA accounts"))


def submit_fetch_task(operation, shop_id, business_params, *, environ=None, session=None):
    connector_code = _operation_connector_code(operation)
    if not isinstance(shop_id, str) or not shop_id.strip():
        raise RpaConnectorError("shop_id is required")
    session = _default_session() if session is None else session
    detail = fetch_connector_detail(operation, environ=environ, session=session)
    params = _validate_live_params(detail, business_params)
    api_base, authorization, session_id, cookies = runtime_config(environ)
    try:
        response = session.post(
            f"{api_base}/adg/v1/agent/fetch/tasks",
            json={
                "authorization": authorization,
                "agent_session_id": session_id,
                "data_source_type": "rpa",
                "platform": resolve_platform(detail),
                "function_code": connector_code,
                "business_params": params,
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
        business_params,
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
    return dict(raw_params)


def _batch_invoker():
    def detail_params(params):
        return {
            name: value
            for name, value in params.items()
            if name not in LOCAL_DETAIL_CONTEXT_FIELDS
        }

    return ConnectorInvoker(
        lambda sid, params: invoke_list(sid, params),
        # Selection groups are local scheduling context. Every remaining field
        # is checked against the current detail contract before submission.
        lambda sid, params: invoke_detail(sid, detail_params(params)),
        submit_detail=lambda sid, params: submit_fetch_task(
            "detail", sid, detail_params(params)
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
    if not isinstance(raw_list_params, dict):
        raise RpaConnectorError("list business_params must be an object")
    list_params = dict(raw_list_params)
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
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    commands = parser.add_subparsers(dest="command", required=True)
    account_parser = commands.add_parser("list-accounts", help="List available RPA accounts using a live platformCode")
    account_parser.add_argument("--connector", choices=("list", "detail"), default="list")
    commands.add_parser("detail", help="Read both live connector details")
    commands.add_parser("schema", help="Print both live connector input contracts")
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
    check_parser.add_argument("--part", action="append", help="Check this chapter or material key; repeat to check a group with one input verification")
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
        "fetch",
        help="Fetch rankings and details in fixed three-material waves",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    fetch_parser.add_argument("--shop-id", required=True)
    params_source = fetch_parser.add_mutually_exclusive_group(required=True)
    params_source.add_argument(
        "--params-json",
        help="Complete batch JSON: dynamic list/detail objects plus optional target_top_n and candidate_top_n",
    )
    params_source.add_argument(
        "--params-file",
        help="Same batch JSON in a file relative to workspace root; target_top_n owns second-level breakdown and candidate_top_n is not the brand analysis Top N",
    )
    fetch_parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help="Collection output directory",
    )
    return parser


def _cmd_self_test():
    if _operation_connector_code("list") != LIST_CONNECTOR_CODE:
        raise RpaConnectorError("unexpected list connector code")
    if _operation_connector_code("detail") != DETAIL_CONNECTOR_CODE:
        raise RpaConnectorError("unexpected detail connector code")
    schema_detail = {
        "inParamJsonSchemaText": json.dumps(
            {
                "type": "object",
                "properties": {"industry": {"type": "string"}},
                "required": ["industry"],
                "additionalProperties": False,
            }
        )
    }
    _validate_live_params(schema_detail, {"industry": "食品饮料"})
    print("self-test passed")


def load_batch_params(args):
    if args.params_json:
        raw = args.params_json
    else:
        relative = Path(args.params_file)
        if relative.is_absolute():
            raise RpaConnectorError("params-file must be relative to the workspace root")
        workspace_root = Path.cwd().resolve()
        path = (workspace_root / relative).resolve()
        try:
            path.relative_to(workspace_root)
        except ValueError as exc:
            raise RpaConnectorError("params-file cannot leave the workspace root") from exc
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise RpaConnectorError(f"unable to read params-file: {exc}") from exc
    try:
        params = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RpaConnectorError(f"batch params are not valid JSON: {exc}") from exc
    if not isinstance(params, dict):
        raise RpaConnectorError("batch params must be a JSON object")
    allowed = {"list", "detail", "target_top_n", "candidate_top_n"}
    unknown = sorted(set(params) - allowed)
    if unknown:
        raise RpaConnectorError("unknown batch params: " + ", ".join(unknown))
    if not isinstance(params.get("list"), dict):
        raise RpaConnectorError("batch params.list must be a JSON object")
    if not isinstance(params.get("detail"), dict):
        raise RpaConnectorError("batch params.detail must be a JSON object")
    if "material_id" in params["detail"]:
        raise RpaConnectorError("params.detail.material_id is selected from the list response")
    if "target_top_n" in params:
        _validate_top_n(params["target_top_n"])
    if "candidate_top_n" in params:
        _validate_top_n(params["candidate_top_n"])
    return params


def main(argv=None):
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "list-accounts":
            print(json.dumps(list_accounts(args.connector), ensure_ascii=False, indent=2))
            return 0
        if args.command in {"detail", "schema"}:
            details = {
                operation: normalized_detail(fetch_connector_detail(operation))
                for operation in ("list", "detail")
            }
            if args.command == "schema":
                details = {
                    operation: {
                        "connectorCode": value["connectorCode"],
                        "name": value["name"],
                        "inputMode": value["inputMode"],
                        "schema": value["inputSchema"],
                        "inParamList": value["inputParams"],
                    }
                    for operation, value in details.items()
                }
            print(json.dumps(details, ensure_ascii=False, indent=2))
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
        batch_params = load_batch_params(args)
        target_top_n = batch_params.get("target_top_n", 10)
        status = fetch_batch_analysis(
            args.shop_id,
            batch_params["list"],
            batch_params["detail"],
            target_top_n=target_top_n,
            candidate_top_n=batch_params.get("candidate_top_n"),
            output_dir=args.output_dir,
        )
        print(Path(args.output_dir) / "batch-manifest.json")
        return status
    except RpaConnectorError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
