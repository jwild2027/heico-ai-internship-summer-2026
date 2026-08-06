"""
TRACE-Net Graph Query API v1.

A small, read-only HTTP/API wrapper around the Graph Query Helper v1 artifact.
The API exposes controlled graph lookup results without granting answer permission.

Safety contract:
- No Postgres writes.
- No Qdrant writes.
- No OpenSearch writes.
- No source-truth mutation.
- No direct answer permission.
- No claim-proof authority.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

SCHEMA_VERSION = "trace_net_graph_query_api_v1"
DEFAULT_OUTPUT_NAME = "trace_net_graph_query_api_v1.json"
DEFAULT_QUALITY_NAME = "trace_net_graph_query_api_v1_quality.json"
DEFAULT_MARKDOWN_NAME = "trace_net_graph_query_api_v1.md"
DEFAULT_ROUTE_RECORDS_NAME = "trace_net_graph_query_api_v1_routes.jsonl"

GRAPH_QUERY_HELPER_REPORT = (
    "local_data/organization/trace_net/graph_query_helper/"
    "trace_net_graph_query_helper_v1.json"
)

SAFE_FALSE_KEYS = {
    "can_answer_directly": False,
    "can_prove_claims": False,
    "retrieval_only": True,
}


@dataclass(frozen=True)
class ApiQualityThresholds:
    min_route_records: int = 5
    min_query_records: int = 3
    require_helper_quality_pass: bool = False
    require_no_answer_permission: bool = False


def load_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Missing JSON input: {p}")
    with p.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise TypeError(f"Expected JSON object in {p}")
    return payload


def write_json(path: str | Path, payload: dict[str, Any]) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    return p


def write_jsonl(path: str | Path, records: list[dict[str, Any]]) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
    return p


def _status_pass(value: Any) -> bool:
    return str(value or "").upper() == "PASS"


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalize_identifier(value: Any) -> str:
    return str(value or "").strip().upper()


def _normalize_part_number(value: Any) -> str:
    return _normalize_identifier(value).replace(" ", "")


def _safe_bool_count(records: list[dict[str, Any]], key: str) -> int:
    return sum(1 for record in records if bool(record.get(key)))


def get_query_records(helper_payload: dict[str, Any]) -> list[dict[str, Any]]:
    records = helper_payload.get("query_records")
    if isinstance(records, list):
        return [r for r in records if isinstance(r, dict)]
    records = helper_payload.get("records")
    if isinstance(records, list):
        return [r for r in records if isinstance(r, dict)]
    return []


def build_route_records() -> list[dict[str, Any]]:
    route_specs = [
        {
            "route_id": "graph_api_health_v1",
            "method": "GET",
            "path_template": "/health",
            "intent": "api_health_check",
            "requires_graph_query_helper": False,
        },
        {
            "route_id": "graph_api_part_sources_v1",
            "method": "GET",
            "path_template": "/graph/part/{part_number}/sources",
            "intent": "part_to_pages_to_sources",
            "query_type": "part_lookup",
            "plan_id": "part_source_check_v1",
            "requires_graph_query_helper": True,
        },
        {
            "route_id": "graph_api_page_context_v1",
            "method": "GET",
            "path_template": "/graph/page/{page_id}",
            "intent": "page_to_source_ata_parts",
            "query_type": "page_lookup",
            "plan_id": "page_source_context_v1",
            "requires_graph_query_helper": True,
        },
        {
            "route_id": "graph_api_ata_pages_v1",
            "method": "GET",
            "path_template": "/graph/ata/{ata_code}/pages",
            "intent": "ata_to_pages_to_sources",
            "query_type": "ata_browse",
            "plan_id": "ata_pages_browse_v1",
            "requires_graph_query_helper": True,
        },
        {
            "route_id": "graph_api_post_query_v1",
            "method": "POST",
            "path_template": "/graph/query",
            "intent": "generic_controlled_graph_query",
            "requires_graph_query_helper": True,
        },
    ]

    route_records: list[dict[str, Any]] = []
    for index, spec in enumerate(route_specs, start=1):
        record = {
            "schema_version": SCHEMA_VERSION,
            "route_order": index,
            "bounded_traversal": True,
            "max_traversal_depth": 4,
            "allowed_to_mutate_source_truth": False,
            "source_truth_mutation_allowed": False,
            "postgres_write_allowed": False,
            "qdrant_write_allowed": False,
            "opensearch_write_allowed": False,
            **SAFE_FALSE_KEYS,
            **spec,
        }
        route_records.append(record)
    return route_records


def make_api_report(
    graph_query_helper_path: str | Path,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    helper_path = Path(graph_query_helper_path)
    helper = load_json(helper_path)
    helper_summary = _as_dict(helper.get("summary"))
    query_records = get_query_records(helper)
    route_records = build_route_records()

    query_type_counts: dict[str, int] = {}
    available_query_inputs: dict[str, list[dict[str, Any]]] = {}
    for record in query_records:
        query_type = str(record.get("query_type") or "unknown")
        query_type_counts[query_type] = query_type_counts.get(query_type, 0) + 1
        available_query_inputs.setdefault(query_type, []).append(_as_dict(record.get("input")))

    source_quality_status = helper.get("quality_status") or helper_summary.get("status")
    route_can_answer_directly_count = _safe_bool_count(route_records, "can_answer_directly")
    route_can_prove_claims_count = _safe_bool_count(route_records, "can_prove_claims")
    source_query_can_answer_directly_count = _safe_bool_count(query_records, "can_answer_directly")
    source_query_can_prove_claims_count = _safe_bool_count(query_records, "can_prove_claims")

    summary = {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS",
        "source_graph_query_helper_path": str(helper_path),
        "source_graph_query_helper_quality_status": source_quality_status,
        "source_graph_query_helper_status": helper.get("status"),
        "source_graph_node_count": helper_summary.get("graph_node_count", 0),
        "source_graph_edge_count": helper_summary.get("graph_edge_count", 0),
        "query_record_count": len(query_records),
        "route_record_count": len(route_records),
        "part_query_route_count": 1,
        "page_query_route_count": 1,
        "ata_query_route_count": 1,
        "generic_query_route_count": 1,
        "health_route_count": 1,
        "available_query_type_counts": query_type_counts,
        "available_query_inputs": available_query_inputs,
        "community_as_proof_count": 0,
        "category_as_proof_count": 0,
        "retrieval_only_answer_allowed_count": 0,
        "can_answer_directly_count": route_can_answer_directly_count + source_query_can_answer_directly_count,
        "can_prove_claims_count": route_can_prove_claims_count + source_query_can_prove_claims_count,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "unbounded_traversal_route_count": sum(1 for r in route_records if not r.get("bounded_traversal")),
        "source_load_statuses": {
            "graph_query_helper": "LOADED",
        },
        "source_quality_statuses": {
            "graph_query_helper": source_quality_status,
        },
    }

    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "GRAPH_QUERY_API_READY",
        "quality_status": "PASS",
        "summary": summary,
        "route_records": route_records,
        "query_records_available": query_records,
        "safety_contract": {
            "no_postgres_writes": True,
            "no_qdrant_writes": True,
            "no_opensearch_writes": True,
            "no_source_truth_mutation": True,
            "no_answer_permission": True,
            "no_claim_proof_authority": True,
        },
    }

    if output_dir is not None:
        out_dir = Path(output_dir)
        report_path = out_dir / DEFAULT_OUTPUT_NAME
        quality_path = out_dir / DEFAULT_QUALITY_NAME
        routes_path = out_dir / DEFAULT_ROUTE_RECORDS_NAME
        md_path = out_dir / DEFAULT_MARKDOWN_NAME
        write_json(report_path, report)
        write_json(quality_path, check_graph_query_api_quality(report, write_json_report=False))
        write_jsonl(routes_path, route_records)
        write_markdown_summary(md_path, report)
        report["artifact_paths"] = {
            "report_path": str(report_path),
            "quality_path": str(quality_path),
            "route_records_path": str(routes_path),
            "markdown_path": str(md_path),
        }
        write_json(report_path, report)
    return report


def check_graph_query_api_quality(
    report_or_path: dict[str, Any] | str | Path,
    thresholds: ApiQualityThresholds | None = None,
    write_json_report: bool = False,
) -> dict[str, Any]:
    thresholds = thresholds or ApiQualityThresholds()
    if isinstance(report_or_path, (str, Path)):
        report_path = Path(report_or_path)
        report = load_json(report_path)
    else:
        report_path = None
        report = report_or_path

    summary = _as_dict(report.get("summary"))
    failures: list[str] = []

    route_count = int(summary.get("route_record_count") or 0)
    query_count = int(summary.get("query_record_count") or 0)
    if route_count < thresholds.min_route_records:
        failures.append(f"route_record_count {route_count} < {thresholds.min_route_records}")
    if query_count < thresholds.min_query_records:
        failures.append(f"query_record_count {query_count} < {thresholds.min_query_records}")

    if thresholds.require_helper_quality_pass and not _status_pass(summary.get("source_graph_query_helper_quality_status")):
        failures.append("source graph query helper quality is not PASS")

    if thresholds.require_no_answer_permission:
        for key in (
            "can_answer_directly_count",
            "can_prove_claims_count",
            "retrieval_only_answer_allowed_count",
            "community_as_proof_count",
            "category_as_proof_count",
            "source_truth_mutation_allowed_count",
            "postgres_write_attempt_count",
            "qdrant_write_attempt_count",
            "opensearch_write_attempt_count",
            "unbounded_traversal_route_count",
        ):
            if int(summary.get(key) or 0) != 0:
                failures.append(f"{key} must be 0")

    quality_status = "FAIL" if failures else "PASS"
    quality = {
        "schema_version": SCHEMA_VERSION,
        "status": quality_status,
        "quality_status": quality_status,
        "summary": summary,
        "failures": failures,
    }

    if write_json_report and report_path is not None:
        quality_path = report_path.with_name(DEFAULT_QUALITY_NAME)
        write_json(quality_path, quality)
    return quality


def write_markdown_summary(path: str | Path, report: dict[str, Any]) -> Path:
    summary = _as_dict(report.get("summary"))
    lines = [
        "# TRACE-Net Graph Query API v1",
        "",
        "Read-only API wrapper for controlled graph query helper results.",
        "",
        "## Summary",
        "",
        f"- Quality status: {report.get('quality_status')}",
        f"- Status: {report.get('status')}",
        f"- Source helper quality: {summary.get('source_graph_query_helper_quality_status')}",
        f"- Route records: {summary.get('route_record_count')}",
        f"- Query records available: {summary.get('query_record_count')}",
        f"- Can answer directly count: {summary.get('can_answer_directly_count')}",
        f"- Can prove claims count: {summary.get('can_prove_claims_count')}",
        f"- Source truth mutation allowed count: {summary.get('source_truth_mutation_allowed_count')}",
        "",
        "## Routes",
        "",
    ]
    for route in _as_list(report.get("route_records")):
        if isinstance(route, dict):
            lines.append(f"- `{route.get('method')} {route.get('path_template')}` - {route.get('intent')}")
    lines.extend([
        "",
        "## Safety",
        "",
        "This API returns structured graph/source records. It does not grant answer permission or claim-proof authority.",
    ])
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


class GraphQueryService:
    def __init__(self, helper_report_path: str | Path, api_report: dict[str, Any] | None = None) -> None:
        self.helper_report_path = Path(helper_report_path)
        self.helper_payload = load_json(self.helper_report_path)
        self.api_report = api_report or make_api_report(self.helper_report_path)
        self.query_records = get_query_records(self.helper_payload)

    def health(self) -> dict[str, Any]:
        summary = _as_dict(self.api_report.get("summary"))
        return {
            "status": "ok",
            "service": SCHEMA_VERSION,
            "quality_status": self.api_report.get("quality_status"),
            "graph_query_helper_quality_status": summary.get("source_graph_query_helper_quality_status"),
            "route_record_count": summary.get("route_record_count"),
            "query_record_count": summary.get("query_record_count"),
            "can_answer_directly": False,
            "can_prove_claims": False,
        }

    def routes(self) -> dict[str, Any]:
        return {
            "status": "GRAPH_QUERY_API_ROUTES",
            "quality_status": self.api_report.get("quality_status"),
            "routes": self.api_report.get("route_records") or [],
            "can_answer_directly": False,
            "can_prove_claims": False,
        }

    def find_record(self, query_type: str, value: str) -> dict[str, Any] | None:
        norm_value = _normalize_identifier(value)
        norm_part = _normalize_part_number(value)
        for record in self.query_records:
            if record.get("query_type") != query_type:
                continue
            input_obj = _as_dict(record.get("input"))
            if query_type == "part_lookup":
                candidate = _normalize_part_number(input_obj.get("part_number"))
                if candidate == norm_part:
                    return record
            elif query_type == "page_lookup":
                candidate = _normalize_identifier(input_obj.get("page_id_or_label") or input_obj.get("page_id"))
                if candidate == norm_value:
                    return record
            elif query_type == "ata_browse":
                candidate = _normalize_identifier(input_obj.get("ata_code"))
                if candidate == norm_value:
                    return record
        return None

    def query(self, query_type: str, value: str) -> tuple[int, dict[str, Any]]:
        record = self.find_record(query_type, value)
        if record is None:
            return 404, {
                "status": "GRAPH_QUERY_RESULT_NOT_FOUND",
                "query_type": query_type,
                "input": value,
                "pages": [],
                "result_count": 0,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "retrieval_only": True,
            }
        response = {
            "status": "GRAPH_QUERY_RESULT_FOUND",
            "quality_status": "PASS",
            "plan_id": record.get("plan_id"),
            "query_type": record.get("query_type"),
            "input": record.get("input"),
            "result_count": record.get("result_count", len(_as_list(record.get("pages")))),
            "source_resolved_result_count": record.get("source_resolved_result_count"),
            "pages": record.get("pages") or [],
            "can_answer_directly": False,
            "can_prove_claims": False,
            "retrieval_only": True,
            "safety_contract": self.api_report.get("safety_contract"),
        }
        return 200, response

    def generic_query(self, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        query_type = str(body.get("query_type") or "")
        plan_id = str(body.get("plan_id") or "")
        if not query_type and plan_id:
            query_type = {
                "part_source_check_v1": "part_lookup",
                "page_source_context_v1": "page_lookup",
                "ata_pages_browse_v1": "ata_browse",
            }.get(plan_id, "")
        if query_type == "part_lookup":
            value = str(body.get("part_number") or body.get("value") or "")
        elif query_type == "page_lookup":
            value = str(body.get("page_id") or body.get("page_id_or_label") or body.get("value") or "")
        elif query_type == "ata_browse":
            value = str(body.get("ata_code") or body.get("value") or "")
        else:
            return 400, {
                "status": "GRAPH_QUERY_BAD_REQUEST",
                "message": "query_type must be one of part_lookup, page_lookup, ata_browse",
                "can_answer_directly": False,
                "can_prove_claims": False,
            }
        if not value:
            return 400, {
                "status": "GRAPH_QUERY_BAD_REQUEST",
                "message": "missing query value",
                "can_answer_directly": False,
                "can_prove_claims": False,
            }
        return self.query(query_type, value)


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    data = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def make_handler(service: GraphQueryService) -> type[BaseHTTPRequestHandler]:
    class GraphQueryApiHandler(BaseHTTPRequestHandler):
        server_version = "TRACE-Net Graph Query API v1"

        def log_message(self, fmt: str, *args: Any) -> None:  # pragma: no cover - keep CLI quiet
            sys.stderr.write("%s - - [%s] %s\n" % (self.client_address[0], self.log_date_time_string(), fmt % args))

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = unquote(parsed.path)
            parts = [p for p in path.split("/") if p]
            try:
                if path == "/health":
                    _json_response(self, 200, service.health())
                    return
                if path == "/graph/routes":
                    _json_response(self, 200, service.routes())
                    return
                if len(parts) == 4 and parts[0] == "graph" and parts[1] == "part" and parts[3] == "sources":
                    status, payload = service.query("part_lookup", parts[2])
                    _json_response(self, status, payload)
                    return
                if len(parts) == 3 and parts[0] == "graph" and parts[1] == "page":
                    status, payload = service.query("page_lookup", parts[2])
                    _json_response(self, status, payload)
                    return
                if len(parts) == 4 and parts[0] == "graph" and parts[1] == "ata" and parts[3] == "pages":
                    status, payload = service.query("ata_browse", parts[2])
                    _json_response(self, status, payload)
                    return
                _json_response(self, 404, {"status": "NOT_FOUND", "path": path})
            except Exception as exc:  # pragma: no cover
                _json_response(self, 500, {"status": "ERROR", "message": str(exc)})

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = unquote(parsed.path)
            try:
                length = int(self.headers.get("Content-Length") or "0")
                raw = self.rfile.read(length) if length else b"{}"
                body = json.loads(raw.decode("utf-8") or "{}")
                if not isinstance(body, dict):
                    body = {}
                if path == "/graph/query":
                    status, payload = service.generic_query(body)
                    _json_response(self, status, payload)
                    return
                _json_response(self, 404, {"status": "NOT_FOUND", "path": path})
            except Exception as exc:  # pragma: no cover
                _json_response(self, 500, {"status": "ERROR", "message": str(exc)})

    return GraphQueryApiHandler


def run_server(host: str, port: int, graph_query_helper_path: str | Path, api_report: dict[str, Any] | None = None) -> None:
    service = GraphQueryService(graph_query_helper_path, api_report=api_report)
    handler = make_handler(service)
    httpd = ThreadingHTTPServer((host, port), handler)
    print(f"TRACE-Net Graph Query API v1 serving on http://{host}:{port}")
    print("Routes: /health, /graph/routes, /graph/part/{part}/sources, /graph/page/{page}, /graph/ata/{ata}/pages, POST /graph/query")
    httpd.serve_forever()


def _thresholds_from_args(args: argparse.Namespace) -> ApiQualityThresholds:
    return ApiQualityThresholds(
        min_route_records=args.min_route_records,
        min_query_records=args.min_query_records,
        require_helper_quality_pass=args.require_helper_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
    )


def print_report_status(report: dict[str, Any]) -> None:
    summary = _as_dict(report.get("summary"))
    print("TRACE-Net Graph Query API v1")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in [
        "source_graph_query_helper_quality_status",
        "source_graph_node_count",
        "source_graph_edge_count",
        "route_record_count",
        "query_record_count",
        "part_query_route_count",
        "page_query_route_count",
        "ata_query_route_count",
        "community_as_proof_count",
        "category_as_proof_count",
        "retrieval_only_answer_allowed_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    artifact_paths = _as_dict(report.get("artifact_paths"))
    if artifact_paths:
        print(f" report_path: {artifact_paths.get('report_path')}")
        print(f" quality_path: {artifact_paths.get('quality_path')}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run or build TRACE-Net Graph Query API v1.")
    parser.add_argument("--graph-query-helper", default=GRAPH_QUERY_HELPER_REPORT)
    parser.add_argument("--output-dir", default="local_data/organization/trace_net/graph_query_api")
    parser.add_argument("--build-only", action="store_true")
    parser.add_argument("--quality", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8015)
    parser.add_argument("--min-route-records", type=int, default=5)
    parser.add_argument("--min-query-records", type=int, default=3)
    parser.add_argument("--require-helper-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    thresholds = _thresholds_from_args(args)

    report = make_api_report(args.graph_query_helper, output_dir=args.output_dir)
    if args.quality:
        quality = check_graph_query_api_quality(
            Path(args.output_dir) / DEFAULT_OUTPUT_NAME,
            thresholds=thresholds,
            write_json_report=True,
        )
        report["quality_status"] = quality["quality_status"]
        report["summary"]["status"] = quality["quality_status"]
        write_json(Path(args.output_dir) / DEFAULT_OUTPUT_NAME, report)
        if quality["failures"]:
            print_report_status(report)
            for failure in quality["failures"]:
                print(f" FAILURE: {failure}")
            return 2

    print_report_status(report)
    if args.build_only:
        return 0

    run_server(args.host, args.port, args.graph_query_helper, api_report=report)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
