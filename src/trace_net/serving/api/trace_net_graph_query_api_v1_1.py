#!/usr/bin/env python
"""TRACE-Net Graph Query API v1.1.

Read-only API wrapper for controlled graph query results with an optional
TRACE-Net v2 evidence-enriched view.

Default graph routes keep Graph Query API v1 behavior: organization-graph
lookups only. Passing include_evidence=true returns the enriched artifact view
from Graph Query Evidence Enrichment v1. Neither mode grants answer permission
or claim-proof authority.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import parse_qs, unquote, urlparse

SCHEMA_VERSION = "trace_net_graph_query_api_v1_1"
DEFAULT_MODEL_NAME = "trace-net-graph-query-api-v1.1"
DEFAULT_REPORT_NAME = "trace_net_graph_query_api_v1_1.json"
DEFAULT_QUALITY_NAME = "trace_net_graph_query_api_v1_1_quality.json"
DEFAULT_MARKDOWN_NAME = "trace_net_graph_query_api_v1_1.md"

ROUTE_RECORDS = [
    {"method": "GET", "path_template": "/health", "intent": "api_health_check", "plan_id": None},
    {"method": "GET", "path_template": "/graph/routes", "intent": "route_catalog", "plan_id": None},
    {"method": "GET", "path_template": "/graph/enrichment/summary", "intent": "evidence_enrichment_summary", "plan_id": None},
    {"method": "GET", "path_template": "/graph/part/{part_number}/sources", "intent": "part_to_pages_to_sources_optional_evidence", "plan_id": "part_source_check_v1"},
    {"method": "GET", "path_template": "/graph/page/{page_id}", "intent": "page_to_source_ata_parts_optional_evidence", "plan_id": "page_source_context_v1"},
    {"method": "GET", "path_template": "/graph/ata/{ata_code}/pages", "intent": "ata_to_pages_to_sources_optional_evidence", "plan_id": "ata_pages_browse_v1"},
    {"method": "POST", "path_template": "/graph/query", "intent": "generic_controlled_graph_query_optional_evidence", "plan_id": None},
]

SAFETY_ZERO_KEYS = [
    "community_as_proof_count",
    "category_as_proof_count",
    "retrieval_only_answer_allowed_count",
    "can_answer_directly_count",
    "can_prove_claims_count",
    "source_truth_mutation_allowed_count",
    "postgres_write_attempt_count",
    "qdrant_write_attempt_count",
    "opensearch_write_attempt_count",
]


@dataclass(frozen=True)
class QualityThresholds:
    min_route_records: int = 7
    min_query_records: int = 3
    min_enriched_query_records: int = 3
    min_evidence_enriched_pages: int = 1
    min_source_resolved_pages: int = 1
    require_helper_quality_pass: bool = False
    require_enrichment_quality_pass: bool = False
    require_no_answer_permission: bool = False


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: str | Path | None, *, optional: bool = False) -> dict[str, Any]:
    if path in (None, ""):
        if optional:
            return {}
        raise FileNotFoundError("Missing JSON path")
    p = Path(path)
    if not p.exists():
        if optional:
            return {}
        raise FileNotFoundError(f"Missing JSON input: {p}")
    with p.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise TypeError(f"Expected JSON object in {p}")
    return payload


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def write_jsonl(path: str | Path, records: list[Mapping[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def quality_status(payload: Mapping[str, Any]) -> str | None:
    value = payload.get("quality_status") or payload.get("status")
    if isinstance(value, str):
        return value
    summary = payload.get("summary")
    if isinstance(summary, dict):
        value = summary.get("quality_status") or summary.get("status")
        if isinstance(value, str):
            return value
    return None


def is_pass(payload: Mapping[str, Any]) -> bool:
    value = quality_status(payload)
    return isinstance(value, str) and value.upper() == "PASS"


def query_records(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [r for r in as_list(payload.get("query_records") or payload.get("enriched_query_records")) if isinstance(r, dict)]


def page_records(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    records = payload.get("page_result_records") or payload.get("enriched_page_records") or payload.get("page_result_sample_records")
    return [r for r in as_list(records) if isinstance(r, dict)]


def safe_copy(record: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(record)
    out["retrieval_only"] = True
    out["can_answer_directly"] = False
    out["can_prove_claims"] = False
    out["source_truth_mutation_allowed"] = False
    return out


def safe_pages(pages: list[dict[str, Any]], limit: int | None = None) -> list[dict[str, Any]]:
    selected = pages if limit is None else pages[: max(0, limit)]
    return [safe_copy(page) for page in selected if isinstance(page, dict)]


def _input_value(record: Mapping[str, Any], key: str) -> str | None:
    input_obj = as_dict(record.get("input"))
    value = input_obj.get(key)
    if value is None:
        value = record.get(key)
    if value is None:
        return None
    return str(value)


def find_part_record(payload: Mapping[str, Any], part_number: str) -> dict[str, Any] | None:
    target = part_number.strip().upper()
    for record in query_records(payload):
        if record.get("query_type") != "part_lookup":
            continue
        value = (_input_value(record, "part_number") or "").strip().upper()
        if value == target:
            return record
    return None


def find_page_record(payload: Mapping[str, Any], page_id: str) -> dict[str, Any] | None:
    target = page_id.strip()
    for record in query_records(payload):
        if record.get("query_type") != "page_lookup":
            continue
        value = (_input_value(record, "page_id_or_label") or _input_value(record, "page_id") or "").strip()
        if value == target:
            return record
    matches = [r for r in page_records(payload) if str(r.get("page_id") or "").strip() == target]
    if matches:
        return {
            "plan_id": "page_source_context_v1:fallback_page_result",
            "query_type": "page_lookup",
            "input": {"page_id_or_label": target},
            "result_count": len(matches),
            "source_resolved_result_count": sum(1 for r in matches if r.get("source_resolved")),
            "pages": matches,
            "retrieval_only": True,
            "can_answer_directly": False,
            "can_prove_claims": False,
        }
    return None


def find_ata_record(payload: Mapping[str, Any], ata_code: str) -> dict[str, Any] | None:
    target = ata_code.strip().upper()
    for record in query_records(payload):
        if record.get("query_type") != "ata_browse":
            continue
        value = (_input_value(record, "ata_code") or "").strip().upper()
        if value == target:
            return record
    return None


def parse_include_evidence(query: Mapping[str, list[str]], body: Mapping[str, Any] | None = None) -> bool:
    body = body or {}
    if "include_evidence" in body:
        return bool(body.get("include_evidence"))
    values = query.get("include_evidence") or query.get("evidence") or []
    if not values:
        return False
    return str(values[0]).strip().lower() in {"1", "true", "yes", "y", "on"}


def safe_response_record(record: Mapping[str, Any], *, view: str, limit: int | None = None) -> dict[str, Any]:
    out = safe_copy(record)
    pages = [p for p in as_list(record.get("pages")) if isinstance(p, dict)]
    if pages:
        out["pages"] = safe_pages(pages, limit=limit)
        out["result_count"] = len(out["pages"])
    out["view"] = view
    out["status"] = "OK"
    out["safety_contract"] = {
        "no_postgres_writes": True,
        "no_qdrant_writes": True,
        "no_opensearch_writes": True,
        "no_source_truth_mutation": True,
        "no_answer_permission": True,
        "no_claim_proof_authority": True,
    }
    return out


def route_records() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for route in ROUTE_RECORDS:
        item = dict(route)
        item.update(
            {
                "bounded_traversal": True,
                "retrieval_only": True,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "source_truth_mutation_allowed": False,
                "supports_include_evidence": route["path_template"].startswith("/graph/") and "{"
                in route["path_template"] or route["path_template"] == "/graph/query",
            }
        )
        out.append(item)
    return out


def count_answer_permission(records: list[dict[str, Any]]) -> int:
    count = 0
    for record in records:
        if record.get("can_answer_directly") or record.get("can_prove_claims") or record.get("source_truth_mutation_allowed"):
            count += 1
        for page in as_list(record.get("pages")):
            if isinstance(page, dict) and (page.get("can_answer_directly") or page.get("can_prove_claims") or page.get("source_truth_mutation_allowed")):
                count += 1
    return count


def build_summary(helper: Mapping[str, Any], enrichment: Mapping[str, Any], host: str, port: int, model_name: str) -> dict[str, Any]:
    helper_summary = as_dict(helper.get("summary"))
    enrichment_summary = as_dict(enrichment.get("summary"))
    helper_records = query_records(helper)
    enrichment_records = query_records(enrichment)
    enrichment_pages = page_records(enrichment)

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS",
        "host": host,
        "port": port,
        "model_name": model_name,
        "source_graph_query_helper_quality_status": quality_status(helper),
        "source_graph_query_evidence_enrichment_quality_status": quality_status(enrichment),
        "source_graph_node_count": helper_summary.get("graph_node_count") or helper_summary.get("source_graph_node_count"),
        "source_graph_edge_count": helper_summary.get("graph_edge_count") or helper_summary.get("source_graph_edge_count"),
        "route_record_count": len(ROUTE_RECORDS),
        "query_record_count": len(helper_records),
        "enriched_query_record_count": len(enrichment_records),
        "enriched_page_record_count": enrichment_summary.get("enriched_page_record_count") or len(enrichment_pages),
        "unique_enriched_page_count": enrichment_summary.get("unique_enriched_page_count"),
        "evidence_enriched_page_count": enrichment_summary.get("evidence_enriched_page_count"),
        "source_resolved_page_count": enrichment_summary.get("source_resolved_page_count") or helper_summary.get("source_resolved_result_count"),
        "opensearch_exact_channel_count": enrichment_summary.get("opensearch_exact_channel_count"),
        "hybrid_v2_channel_count": enrichment_summary.get("hybrid_v2_channel_count"),
        "leiden_navigation_channel_count": enrichment_summary.get("leiden_navigation_channel_count"),
        "claim_entailment_channel_count": enrichment_summary.get("claim_entailment_channel_count"),
        "review_record_count": enrichment_summary.get("review_record_count"),
        "part_query_route_count": 1,
        "page_query_route_count": 1,
        "ata_query_route_count": 1,
        "generic_query_route_count": 1,
        "health_route_count": 1,
        "enrichment_summary_route_count": 1,
        "include_evidence_enabled_route_count": 4,
        "community_as_proof_count": int(enrichment_summary.get("community_as_proof_count") or helper_summary.get("community_as_proof_count") or 0),
        "category_as_proof_count": int(enrichment_summary.get("category_as_proof_count") or helper_summary.get("category_as_proof_count") or 0),
        "retrieval_only_answer_allowed_count": int(enrichment_summary.get("retrieval_only_answer_allowed_count") or helper_summary.get("retrieval_only_answer_allowed_count") or 0),
        "can_answer_directly_count": count_answer_permission(helper_records) + count_answer_permission(enrichment_records),
        "can_prove_claims_count": count_answer_permission(helper_records) + count_answer_permission(enrichment_records),
        "source_truth_mutation_allowed_count": int(enrichment_summary.get("source_truth_mutation_allowed_count") or helper_summary.get("source_truth_mutation_allowed_count") or 0),
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "source_quality_statuses": {
            "graph_query_helper": quality_status(helper),
            "graph_query_evidence_enrichment": quality_status(enrichment),
        },
        "source_load_statuses": {
            "graph_query_helper": "LOADED" if helper else "MISSING",
            "graph_query_evidence_enrichment": "LOADED" if enrichment else "MISSING",
        },
    }


def quality_failures(summary: Mapping[str, Any], thresholds: QualityThresholds) -> list[str]:
    failures: list[str] = []
    if int(summary.get("route_record_count") or 0) < thresholds.min_route_records:
        failures.append("route_record_count_below_minimum")
    if int(summary.get("query_record_count") or 0) < thresholds.min_query_records:
        failures.append("query_record_count_below_minimum")
    if int(summary.get("enriched_query_record_count") or 0) < thresholds.min_enriched_query_records:
        failures.append("enriched_query_record_count_below_minimum")
    if int(summary.get("evidence_enriched_page_count") or 0) < thresholds.min_evidence_enriched_pages:
        failures.append("evidence_enriched_page_count_below_minimum")
    if int(summary.get("source_resolved_page_count") or 0) < thresholds.min_source_resolved_pages:
        failures.append("source_resolved_page_count_below_minimum")
    if thresholds.require_helper_quality_pass and summary.get("source_graph_query_helper_quality_status") != "PASS":
        failures.append("source_graph_query_helper_quality_not_pass")
    if thresholds.require_enrichment_quality_pass and summary.get("source_graph_query_evidence_enrichment_quality_status") != "PASS":
        failures.append("source_graph_query_evidence_enrichment_quality_not_pass")
    if thresholds.require_no_answer_permission:
        for key in SAFETY_ZERO_KEYS:
            if int(summary.get(key) or 0) != 0:
                failures.append(f"{key}_must_be_zero")
    return failures


def build_graph_query_api_v1_1_report(
    graph_query_helper_path: str | Path,
    graph_query_evidence_enrichment_path: str | Path,
    output_dir: str | Path,
    host: str = "0.0.0.0",
    port: int = 8016,
    model_name: str = DEFAULT_MODEL_NAME,
    thresholds: QualityThresholds | None = None,
    quality: bool = True,
) -> dict[str, Any]:
    thresholds = thresholds or QualityThresholds()
    helper = load_json(graph_query_helper_path)
    enrichment = load_json(graph_query_evidence_enrichment_path)
    summary = build_summary(helper, enrichment, host, port, model_name)
    failures = quality_failures(summary, thresholds) if quality else []
    quality_value = "PASS" if not failures else "FAIL"

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / DEFAULT_REPORT_NAME
    quality_path = out_dir / DEFAULT_QUALITY_NAME
    route_path = out_dir / "trace_net_graph_query_api_v1_1_routes.jsonl"
    query_path = out_dir / "trace_net_graph_query_api_v1_1_query_records.jsonl"
    markdown_path = out_dir / DEFAULT_MARKDOWN_NAME

    routes = route_records()
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "GRAPH_QUERY_API_V1_1_READY" if quality_value == "PASS" else "GRAPH_QUERY_API_V1_1_NEEDS_REVIEW",
        "quality_status": quality_value,
        "created_at": utc_now_iso(),
        "graph_query_helper_path": str(graph_query_helper_path),
        "graph_query_evidence_enrichment_path": str(graph_query_evidence_enrichment_path),
        "summary": summary,
        "route_records": routes,
        "routes": routes,
        "query_records": [safe_copy(r) for r in query_records(helper)],
        "enriched_query_records": [safe_copy(r) for r in query_records(enrichment)],
        "quality_failures": failures,
        "safety_contract": {
            "no_postgres_writes": True,
            "no_qdrant_writes": True,
            "no_opensearch_writes": True,
            "no_source_truth_mutation": True,
            "no_answer_permission": True,
            "no_claim_proof_authority": True,
        },
        "artifacts": {
            "report_path": str(report_path),
            "quality_path": str(quality_path),
            "route_path": str(route_path),
            "query_path": str(query_path),
            "markdown_path": str(markdown_path),
        },
    }
    write_json(report_path, report)
    write_json(quality_path, report)
    write_jsonl(route_path, routes)
    write_jsonl(query_path, report["enriched_query_records"])
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    return report


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = as_dict(report.get("summary"))
    lines = [
        "# TRACE-Net Graph Query API v1.1",
        "",
        f"Status: `{report.get('status')}`",
        f"Quality status: `{report.get('quality_status')}`",
        "",
        "This API keeps organization-graph lookups as the default and exposes an optional evidence-enriched view with `include_evidence=true`.",
        "It is retrieval-only and cannot prove claims or return final answers.",
        "",
        "## Key counts",
        "",
    ]
    for key in [
        "route_record_count",
        "query_record_count",
        "enriched_query_record_count",
        "evidence_enriched_page_count",
        "source_resolved_page_count",
        "opensearch_exact_channel_count",
        "hybrid_v2_channel_count",
        "leiden_navigation_channel_count",
        "claim_entailment_channel_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
    ]:
        lines.append(f"- {key}: `{summary.get(key)}`")
    lines.extend(["", "## Routes", ""])
    for route in report.get("route_records") or []:
        lines.append(f"- `{route.get('method')} {route.get('path_template')}` - {route.get('intent')}")
    lines.append("")
    return "\n".join(lines)


def check_graph_query_api_v1_1_quality(
    report_path: str | Path,
    thresholds: QualityThresholds | None = None,
    write_json_report: bool = False,
) -> dict[str, Any]:
    thresholds = thresholds or QualityThresholds()
    report = load_json(report_path)
    summary = as_dict(report.get("summary"))
    failures = quality_failures(summary, thresholds)
    quality_value = "PASS" if not failures else "FAIL"
    report["quality_status"] = quality_value
    report["status"] = "GRAPH_QUERY_API_V1_1_READY" if quality_value == "PASS" else "GRAPH_QUERY_API_V1_1_NEEDS_REVIEW"
    report["quality_failures"] = failures
    if write_json_report:
        write_json(report_path, report)
        write_json(Path(report_path).with_name(DEFAULT_QUALITY_NAME), report)
    return report


def json_response(handler: BaseHTTPRequestHandler, status: int, payload: Mapping[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def not_found(path: str, message: str = "Not found in precomputed graph query artifacts") -> dict[str, Any]:
    return {
        "status": "NOT_FOUND",
        "path": path,
        "message": message,
        "retrieval_only": True,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
    }


def select_payload(helper: Mapping[str, Any], enrichment: Mapping[str, Any], include_evidence: bool) -> tuple[Mapping[str, Any], str]:
    if include_evidence:
        return enrichment, "evidence_enriched_graph_query"
    return helper, "organization_graph_query"


def make_handler(helper: Mapping[str, Any], enrichment: Mapping[str, Any], model_name: str) -> type[BaseHTTPRequestHandler]:
    class GraphQueryAPIv11Handler(BaseHTTPRequestHandler):
        server_version = "TraceNetGraphQueryAPIv11/1.0"

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            sys.stderr.write("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), format % args))

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            query = parse_qs(parsed.query)
            include_evidence = parse_include_evidence(query)
            selected, view = select_payload(helper, enrichment, include_evidence)

            if path == "/health":
                json_response(
                    self,
                    200,
                    {
                        "status": "ok",
                        "schema_version": SCHEMA_VERSION,
                        "model": model_name,
                        "helper_quality_status": quality_status(helper),
                        "enrichment_quality_status": quality_status(enrichment),
                        "include_evidence_supported": True,
                        "retrieval_only": True,
                        "can_answer_directly": False,
                        "can_prove_claims": False,
                    },
                )
                return

            if path == "/v1/models":
                json_response(
                    self,
                    200,
                    {
                        "object": "list",
                        "data": [
                            {
                                "id": model_name,
                                "object": "model",
                                "owned_by": "trace-net",
                                "permission": [],
                                "description": "Read-only graph query API with optional evidence enrichment. Not a final answer model.",
                            }
                        ],
                    },
                )
                return

            if path == "/graph/routes":
                json_response(
                    self,
                    200,
                    {
                        "status": "OK",
                        "schema_version": SCHEMA_VERSION,
                        "routes": route_records(),
                        "include_evidence_supported": True,
                        "retrieval_only": True,
                        "can_answer_directly": False,
                        "can_prove_claims": False,
                    },
                )
                return

            if path == "/graph/enrichment/summary":
                json_response(
                    self,
                    200,
                    {
                        "status": "OK",
                        "schema_version": SCHEMA_VERSION,
                        "summary": enrichment.get("summary", {}),
                        "quality_status": enrichment.get("quality_status"),
                        "review_records": enrichment.get("review_records", [])[:20],
                        "retrieval_only": True,
                        "can_answer_directly": False,
                        "can_prove_claims": False,
                    },
                )
                return

            if path.startswith("/graph/part/") and path.endswith("/sources"):
                part_number = unquote(path[len("/graph/part/") : -len("/sources")])
                record = find_part_record(selected, part_number)
                if not record:
                    json_response(self, 404, not_found(path, "Rebuild helper/enrichment with this part number to serve it."))
                    return
                safe = safe_response_record(record, view=view)
                safe["part_number"] = part_number
                safe["include_evidence"] = include_evidence
                safe["enrichment_available"] = bool(find_part_record(enrichment, part_number))
                json_response(self, 200, safe)
                return

            if path.startswith("/graph/page/"):
                page_id = unquote(path[len("/graph/page/") :])
                record = find_page_record(selected, page_id)
                if not record:
                    json_response(self, 404, not_found(path))
                    return
                safe = safe_response_record(record, view=view)
                safe["page_id"] = page_id
                safe["include_evidence"] = include_evidence
                json_response(self, 200, safe)
                return

            if path.startswith("/graph/ata/") and path.endswith("/pages"):
                ata_code = unquote(path[len("/graph/ata/") : -len("/pages")])
                record = find_ata_record(selected, ata_code)
                if not record:
                    json_response(self, 404, not_found(path))
                    return
                limit = None
                values = query.get("limit") or []
                if values:
                    try:
                        limit = int(values[0])
                    except ValueError:
                        limit = None
                safe = safe_response_record(record, view=view, limit=limit)
                safe["ata_code"] = ata_code
                safe["include_evidence"] = include_evidence
                json_response(self, 200, safe)
                return

            json_response(self, 404, not_found(path))

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            if path != "/graph/query":
                json_response(self, 404, not_found(path))
                return
            length = int(self.headers.get("Content-Length") or 0)
            raw_body = self.rfile.read(length) if length else b"{}"
            try:
                body = json.loads(raw_body.decode("utf-8"))
                if not isinstance(body, dict):
                    body = {}
            except Exception:
                body = {}
            query = parse_qs(parsed.query)
            include_evidence = parse_include_evidence(query, body)
            selected, view = select_payload(helper, enrichment, include_evidence)
            query_type = str(body.get("query_type") or "").strip()
            record: dict[str, Any] | None = None
            if query_type == "part_lookup":
                record = find_part_record(selected, str(body.get("part_number") or body.get("query") or ""))
            elif query_type == "page_lookup":
                record = find_page_record(selected, str(body.get("page_id") or body.get("page_id_or_label") or body.get("query") or ""))
            elif query_type == "ata_browse":
                record = find_ata_record(selected, str(body.get("ata_code") or body.get("query") or ""))
            else:
                json_response(
                    self,
                    400,
                    {
                        "status": "BAD_REQUEST",
                        "message": "query_type must be part_lookup, page_lookup, or ata_browse",
                        "retrieval_only": True,
                        "can_answer_directly": False,
                        "can_prove_claims": False,
                    },
                )
                return
            if not record:
                json_response(self, 404, not_found(path))
                return
            safe = safe_response_record(record, view=view)
            safe["include_evidence"] = include_evidence
            json_response(self, 200, safe)

    return GraphQueryAPIv11Handler


def serve_graph_query_api_v1_1(
    graph_query_helper_path: str | Path,
    graph_query_evidence_enrichment_path: str | Path,
    host: str = "0.0.0.0",
    port: int = 8016,
    model_name: str = DEFAULT_MODEL_NAME,
) -> None:
    helper = load_json(graph_query_helper_path)
    enrichment = load_json(graph_query_evidence_enrichment_path)
    handler_class = make_handler(helper, enrichment, model_name=model_name)
    server = ThreadingHTTPServer((host, port), handler_class)
    print(f"TRACE-Net Graph Query API v1.1 serving on http://{host}:{port}")
    print("Routes: /health, /graph/routes, /graph/enrichment/summary, /graph/part/{part}/sources?include_evidence=true, /graph/page/{page}, /graph/ata/{ata}/pages, POST /graph/query")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nTRACE-Net Graph Query API v1.1 shutting down")
    finally:
        server.server_close()


def print_report(report: Mapping[str, Any]) -> None:
    summary = as_dict(report.get("summary"))
    print("TRACE-Net Graph Query API v1.1")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in [
        "source_graph_query_helper_quality_status",
        "source_graph_query_evidence_enrichment_quality_status",
        "route_record_count",
        "query_record_count",
        "enriched_query_record_count",
        "enriched_page_record_count",
        "evidence_enriched_page_count",
        "source_resolved_page_count",
        "opensearch_exact_channel_count",
        "hybrid_v2_channel_count",
        "leiden_navigation_channel_count",
        "claim_entailment_channel_count",
        "review_record_count",
        "include_evidence_enabled_route_count",
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
    artifacts = as_dict(report.get("artifacts"))
    if artifacts.get("report_path"):
        print(f" report_path: {artifacts.get('report_path')}")
    if artifacts.get("quality_path"):
        print(f" quality_path: {artifacts.get('quality_path')}")


def make_thresholds_from_args(args: argparse.Namespace) -> QualityThresholds:
    return QualityThresholds(
        min_route_records=args.min_route_records,
        min_query_records=args.min_query_records,
        min_enriched_query_records=args.min_enriched_query_records,
        min_evidence_enriched_pages=args.min_evidence_enriched_pages,
        min_source_resolved_pages=args.min_source_resolved_pages,
        require_helper_quality_pass=args.require_helper_quality_pass,
        require_enrichment_quality_pass=args.require_enrichment_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
    )


def add_quality_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--min-route-records", type=int, default=7)
    parser.add_argument("--min-query-records", type=int, default=3)
    parser.add_argument("--min-enriched-query-records", type=int, default=3)
    parser.add_argument("--min-evidence-enriched-pages", type=int, default=1)
    parser.add_argument("--min-source-resolved-pages", type=int, default=1)
    parser.add_argument("--require-helper-quality-pass", action="store_true")
    parser.add_argument("--require-enrichment-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build or serve TRACE-Net Graph Query API v1.1.")
    parser.add_argument("--graph-query-helper", required=True, help="Path to trace_net_graph_query_helper_v1.json")
    parser.add_argument("--graph-query-evidence-enrichment", required=True, help="Path to trace_net_graph_query_evidence_enrichment_v1.json")
    parser.add_argument("--output-dir", default="local_data/organization/trace_net/graph_query_api_v1_1")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8016)
    parser.add_argument("--model-name", default=DEFAULT_MODEL_NAME)
    parser.add_argument("--build-only", action="store_true", help="Write API manifest and exit.")
    parser.add_argument("--quality", action="store_true")
    add_quality_args(parser)
    args = parser.parse_args(argv)

    report = build_graph_query_api_v1_1_report(
        graph_query_helper_path=args.graph_query_helper,
        graph_query_evidence_enrichment_path=args.graph_query_evidence_enrichment,
        output_dir=args.output_dir,
        host=args.host,
        port=args.port,
        model_name=args.model_name,
        thresholds=make_thresholds_from_args(args),
        quality=args.quality,
    )
    print_report(report)
    if args.quality and report.get("quality_status") != "PASS":
        return 2
    if args.build_only:
        return 0
    serve_graph_query_api_v1_1(
        graph_query_helper_path=args.graph_query_helper,
        graph_query_evidence_enrichment_path=args.graph_query_evidence_enrichment,
        host=args.host,
        port=args.port,
        model_name=args.model_name,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
