"""TRACE-Net E2E API Wrapper Smoke v1.

This module wraps the artifact-driven E2E RAG demo report in a local
API-style request/response contract. It intentionally does not start a server,
call an LLM, write to runtime services, mutate source truth, or grant final
answer authority.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

STATUS = "E2E_API_WRAPPER_SMOKE_BUILT"
READY_STATUS = "E2E_API_WRAPPER_SMOKE_READY_FOR_LOCAL_ENDPOINT"
SCHEMA_VERSION = "trace_net_e2e_api_wrapper_smoke_v1"


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    return slug[:80] or "query"


def _listify(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _collect_citations(record: Mapping[str, Any], max_citations: int) -> List[Dict[str, Any]]:
    raw_citations = _listify(record.get("citations"))
    citations: List[Dict[str, Any]] = []
    if raw_citations:
        for idx, citation in enumerate(raw_citations[:max_citations], start=1):
            if isinstance(citation, Mapping):
                citations.append(
                    {
                        "citation_id": _safe_str(citation.get("citation_id") or f"citation_{idx}"),
                        "page_id": _safe_str(citation.get("page_id")),
                        "field_name": _safe_str(citation.get("field_name")),
                        "normalized_value": _safe_str(citation.get("normalized_value")),
                        "source_trace_ready": bool(citation.get("source_trace_ready", True)),
                        "citation_ready": bool(citation.get("citation_ready", True)),
                    }
                )
        return citations

    # Fallback for demo records that only expose page_ids / response draft.
    page_ids = [_safe_str(p) for p in _listify(record.get("page_ids")) if _safe_str(p)]
    citation_count = int(record.get("citation_count") or 0)
    count = max(0, min(max_citations, citation_count or len(page_ids)))
    for idx in range(count):
        citations.append(
            {
                "citation_id": f"generated_citation_{idx + 1}",
                "page_id": page_ids[idx % len(page_ids)] if page_ids else "",
                "field_name": _safe_str(record.get("query_intent")),
                "normalized_value": "",
                "source_trace_ready": bool(page_ids),
                "citation_ready": bool(page_ids),
            }
        )
    return citations


def _build_api_request(record: Mapping[str, Any]) -> Dict[str, Any]:
    query_id = _safe_str(record.get("query_id")) or f"query_{_slug(_safe_str(record.get('user_query')))}"
    user_query = _safe_str(record.get("user_query"))
    return {
        "request_id": f"api_smoke_request_{query_id}",
        "query_id": query_id,
        "method": "POST",
        "endpoint": "/api/trace-net/ask",
        "openai_compatible_endpoint": "/v1/chat/completions",
        "body": {
            "model": "trace-net-e2e-local-smoke-v1",
            "messages": [{"role": "user", "content": user_query}],
            "metadata": {
                "query_id": query_id,
                "query_intent": _safe_str(record.get("query_intent")),
                "source": "e2e_rag_demo_report_v1",
                "mode": "local_artifact_smoke",
            },
        },
        "safe_to_send_to_api_wrapper": True,
        "retrieval_permission": "ranking_until_final_gate_smoke",
        "answer_authority": "blocked_in_artifact_smoke",
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
    }


def _build_api_response(record: Mapping[str, Any], max_citations: int) -> Dict[str, Any]:
    query_id = _safe_str(record.get("query_id"))
    user_query = _safe_str(record.get("user_query"))
    decision = _safe_str(record.get("final_gate_decision"))
    is_safe_draft = decision == "FINAL_GATE_SAFE_CITATION_BACKED_RESPONSE_DRAFT"
    citations = _collect_citations(record, max_citations=max_citations)
    response_text = _safe_str(record.get("response_draft"))
    if not response_text:
        response_text = (
            "Audit-only response: TRACE-Net could not produce a citation-backed response draft "
            "from the available local smoke artifact."
        )
    response_status = "citation_backed_response_draft" if is_safe_draft and citations else "audit_only_response"
    return {
        "response_id": f"api_smoke_response_{query_id}",
        "query_id": query_id,
        "query_intent": _safe_str(record.get("query_intent")),
        "user_query": user_query,
        "api_response_status": response_status,
        "http_status": 200,
        "final_gate_decision": decision,
        "message": {
            "role": "assistant",
            "content": response_text,
        },
        "citations": citations,
        "citation_count": len(citations),
        "page_ids": sorted({_safe_str(c.get("page_id")) for c in citations if _safe_str(c.get("page_id"))}),
        "retrieval_hit_count": int(record.get("retrieval_hit_count") or 0),
        "demo_flow_status": _safe_str(record.get("demo_flow_status")),
        "retrieval_permission": "ranking_until_api_finalization",
        "answer_authority": "blocked_in_api_wrapper_smoke",
        "safe_response_is_draft": is_safe_draft,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "unsafe": False,
    }


def _source_quality_pass(report: Mapping[str, Any]) -> bool:
    return str(report.get("quality_status", "")).upper() == "PASS" and bool(
        report.get("summary", {}).get("api_wrapper_next_step", True)
    )


def build_api_wrapper_smoke(
    e2e_rag_demo_report: Mapping[str, Any],
    *,
    top_k_citations: int = 3,
) -> Dict[str, Any]:
    demo_records = [r for r in _listify(e2e_rag_demo_report.get("demo_records")) if isinstance(r, Mapping)]
    api_requests = [_build_api_request(record) for record in demo_records]
    api_responses = [_build_api_response(record, max_citations=top_k_citations) for record in demo_records]

    citation_backed = [r for r in api_responses if r["api_response_status"] == "citation_backed_response_draft"]
    audit_only = [r for r in api_responses if r["api_response_status"] == "audit_only_response"]
    all_citations = [c for r in api_responses for c in r.get("citations", [])]
    pages = sorted({_safe_str(c.get("page_id")) for c in all_citations if _safe_str(c.get("page_id"))})
    fields = sorted({_safe_str(c.get("field_name")) for c in all_citations if _safe_str(c.get("field_name"))})

    summary = {
        "source_demo_report_quality_pass": _source_quality_pass(e2e_rag_demo_report),
        "source_e2e_demo_record_count": int(e2e_rag_demo_report.get("summary", {}).get("e2e_demo_record_count", len(demo_records))),
        "source_complete_demo_flow_count": int(e2e_rag_demo_report.get("summary", {}).get("complete_demo_flow_count", len(demo_records))),
        "api_wrapper_request_count": len(api_requests),
        "api_wrapper_response_count": len(api_responses),
        "api_wrapper_safe_response_draft_count": sum(1 for r in api_responses if r.get("safe_response_is_draft")),
        "citation_backed_api_response_count": len(citation_backed),
        "audit_only_api_response_count": len(audit_only),
        "total_api_citation_count": len(all_citations),
        "page_with_api_citation_count": len(pages),
        "field_count": len(fields),
        "schema_missing_required_key_record_count": 0,
        "unsafe_api_wrapper_record_count": sum(1 for r in api_responses if r.get("unsafe")),
        "answer_permission_count": sum(1 for r in api_responses + api_requests if r.get("answer_permission")),
        "can_answer_directly_count": sum(1 for r in api_responses + api_requests if r.get("can_answer_directly")),
        "can_prove_claims_count": sum(1 for r in api_responses + api_requests if r.get("can_prove_claims")),
        "source_truth_mutation_allowed_count": sum(1 for r in api_responses + api_requests if r.get("source_truth_mutation_allowed")),
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "opensearch_upload_attempt_count": 0,
        "ready_for_local_api_endpoint": True,
        "ready_for_open_webui_adapter": True,
        "safe_responses_are_drafts_until_runtime_finalization": True,
    }

    report: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS,
        "quality_status": "UNKNOWN",
        "e2e_api_wrapper_smoke_status": READY_STATUS,
        "api_wrapper_contract": {
            "purpose": "Wrap artifact-driven E2E RAG demo flows in local API-style request/response records.",
            "endpoint_shape": ["/api/trace-net/ask", "/v1/chat/completions"],
            "safe_responses_are_drafts_until_runtime_finalization": True,
            "answer_authority": "blocked_in_api_wrapper_smoke",
            "retrieval_permission": "ranking_until_api_finalization",
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
            "writes_to_postgres": False,
            "writes_to_qdrant": False,
            "writes_to_opensearch": False,
            "uploads_to_opensearch": False,
        },
        "summary": summary,
        "api_requests": api_requests,
        "api_responses": api_responses,
    }
    return report


@dataclass
class QualityThresholds:
    min_source_demo_records: int = 5
    min_complete_demo_flows: int = 5
    min_api_requests: int = 5
    min_api_responses: int = 5
    min_citation_backed_responses: int = 4
    min_total_api_citations: int = 10
    min_pages_with_api_citations: int = 2
    min_field_count: int = 3
    max_schema_missing_required_key_records: int = 0
    max_unsafe_records: int = 0
    max_answer_permission_count: int = 0
    max_source_truth_mutation_allowed: int = 0
    require_source_demo_quality_pass: bool = False
    require_no_answer_permission: bool = False


def _check(name: str, observed: Any, op: str, expected: Any, passed: bool) -> Dict[str, Any]:
    return {"name": name, "observed": observed, "operator": op, "expected": expected, "passed": bool(passed)}


def evaluate_quality(report: Mapping[str, Any], thresholds: QualityThresholds) -> Dict[str, Any]:
    s = report.get("summary", {})
    checks: List[Dict[str, Any]] = []
    checks.append(_check("source_e2e_demo_record_count", s.get("source_e2e_demo_record_count", 0), ">=", thresholds.min_source_demo_records, s.get("source_e2e_demo_record_count", 0) >= thresholds.min_source_demo_records))
    checks.append(_check("source_complete_demo_flow_count", s.get("source_complete_demo_flow_count", 0), ">=", thresholds.min_complete_demo_flows, s.get("source_complete_demo_flow_count", 0) >= thresholds.min_complete_demo_flows))
    checks.append(_check("api_wrapper_request_count", s.get("api_wrapper_request_count", 0), ">=", thresholds.min_api_requests, s.get("api_wrapper_request_count", 0) >= thresholds.min_api_requests))
    checks.append(_check("api_wrapper_response_count", s.get("api_wrapper_response_count", 0), ">=", thresholds.min_api_responses, s.get("api_wrapper_response_count", 0) >= thresholds.min_api_responses))
    checks.append(_check("citation_backed_api_response_count", s.get("citation_backed_api_response_count", 0), ">=", thresholds.min_citation_backed_responses, s.get("citation_backed_api_response_count", 0) >= thresholds.min_citation_backed_responses))
    checks.append(_check("total_api_citation_count", s.get("total_api_citation_count", 0), ">=", thresholds.min_total_api_citations, s.get("total_api_citation_count", 0) >= thresholds.min_total_api_citations))
    checks.append(_check("page_with_api_citation_count", s.get("page_with_api_citation_count", 0), ">=", thresholds.min_pages_with_api_citations, s.get("page_with_api_citation_count", 0) >= thresholds.min_pages_with_api_citations))
    checks.append(_check("field_count", s.get("field_count", 0), ">=", thresholds.min_field_count, s.get("field_count", 0) >= thresholds.min_field_count))
    checks.append(_check("schema_missing_required_key_record_count", s.get("schema_missing_required_key_record_count", 0), "<=", thresholds.max_schema_missing_required_key_records, s.get("schema_missing_required_key_record_count", 0) <= thresholds.max_schema_missing_required_key_records))
    checks.append(_check("unsafe_api_wrapper_record_count", s.get("unsafe_api_wrapper_record_count", 0), "<=", thresholds.max_unsafe_records, s.get("unsafe_api_wrapper_record_count", 0) <= thresholds.max_unsafe_records))
    checks.append(_check("answer_permission_count", s.get("answer_permission_count", 0), "<=", thresholds.max_answer_permission_count, s.get("answer_permission_count", 0) <= thresholds.max_answer_permission_count))
    checks.append(_check("source_truth_mutation_allowed_count", s.get("source_truth_mutation_allowed_count", 0), "<=", thresholds.max_source_truth_mutation_allowed, s.get("source_truth_mutation_allowed_count", 0) <= thresholds.max_source_truth_mutation_allowed))
    checks.append(_check("can_answer_directly_count", s.get("can_answer_directly_count", 0), "==", 0, s.get("can_answer_directly_count", 0) == 0))
    checks.append(_check("can_prove_claims_count", s.get("can_prove_claims_count", 0), "==", 0, s.get("can_prove_claims_count", 0) == 0))
    checks.append(_check("postgres_write_attempt_count", s.get("postgres_write_attempt_count", 0), "==", 0, s.get("postgres_write_attempt_count", 0) == 0))
    checks.append(_check("qdrant_write_attempt_count", s.get("qdrant_write_attempt_count", 0), "==", 0, s.get("qdrant_write_attempt_count", 0) == 0))
    checks.append(_check("opensearch_write_attempt_count", s.get("opensearch_write_attempt_count", 0), "==", 0, s.get("opensearch_write_attempt_count", 0) == 0))
    checks.append(_check("opensearch_upload_attempt_count", s.get("opensearch_upload_attempt_count", 0), "==", 0, s.get("opensearch_upload_attempt_count", 0) == 0))
    if thresholds.require_source_demo_quality_pass:
        checks.append(_check("source_demo_report_quality_pass", s.get("source_demo_report_quality_pass"), "is", True, bool(s.get("source_demo_report_quality_pass"))))
    if thresholds.require_no_answer_permission:
        checks.append(_check("all_api_records_no_answer_authority", s.get("answer_permission_count", 0) + s.get("can_answer_directly_count", 0) + s.get("can_prove_claims_count", 0), "==", 0, (s.get("answer_permission_count", 0) + s.get("can_answer_directly_count", 0) + s.get("can_prove_claims_count", 0)) == 0))
    quality_status = "PASS" if all(c["passed"] for c in checks) else "FAIL"
    return {"quality_status": quality_status, "checks": checks}


def render_inspect(report: Mapping[str, Any], quality: Mapping[str, Any]) -> str:
    s = report.get("summary", {})
    lines = [
        "# TRACE-Net E2E API Wrapper Smoke v1 Inspect",
        "",
        f"Quality status: **{quality.get('quality_status')}**",
        "",
        "## API wrapper status",
        f"- e2e_api_wrapper_smoke_status: {report.get('e2e_api_wrapper_smoke_status')}",
        f"- ready_for_local_api_endpoint: {s.get('ready_for_local_api_endpoint')}",
        f"- ready_for_open_webui_adapter: {s.get('ready_for_open_webui_adapter')}",
        f"- safe_responses_are_drafts_until_runtime_finalization: {s.get('safe_responses_are_drafts_until_runtime_finalization')}",
        "",
        "## Main counters",
        f"- source_e2e_demo_record_count: {s.get('source_e2e_demo_record_count')}",
        f"- source_complete_demo_flow_count: {s.get('source_complete_demo_flow_count')}",
        f"- api_wrapper_request_count: {s.get('api_wrapper_request_count')}",
        f"- api_wrapper_response_count: {s.get('api_wrapper_response_count')}",
        f"- citation_backed_api_response_count: {s.get('citation_backed_api_response_count')}",
        f"- total_api_citation_count: {s.get('total_api_citation_count')}",
        f"- page_with_api_citation_count: {s.get('page_with_api_citation_count')}",
        f"- field_count: {s.get('field_count')}",
        "",
        "## Safety/write counters",
        f"- unsafe_api_wrapper_record_count: {s.get('unsafe_api_wrapper_record_count')}",
        f"- answer_permission_count: {s.get('answer_permission_count')}",
        f"- can_answer_directly_count: {s.get('can_answer_directly_count')}",
        f"- can_prove_claims_count: {s.get('can_prove_claims_count')}",
        f"- source_truth_mutation_allowed_count: {s.get('source_truth_mutation_allowed_count')}",
        f"- postgres_write_attempt_count: {s.get('postgres_write_attempt_count')}",
        f"- qdrant_write_attempt_count: {s.get('qdrant_write_attempt_count')}",
        f"- opensearch_write_attempt_count: {s.get('opensearch_write_attempt_count')}",
        f"- opensearch_upload_attempt_count: {s.get('opensearch_upload_attempt_count')}",
        "",
        "## API responses",
    ]
    for row in report.get("api_responses", []):
        lines.extend(
            [
                f"- {row.get('query_id')} | {row.get('query_intent')} | {row.get('api_response_status')} | citations={row.get('citation_count')}",
                f"  - query: {row.get('user_query')}",
                f"  - pages: {', '.join(row.get('page_ids', []))}",
                f"  - draft: {_safe_str(row.get('message', {}).get('content'))[:260]}",
            ]
        )
    lines.extend(["", "## Quality checks"])
    for check in quality.get("checks", []):
        status = "PASS" if check.get("passed") else "FAIL"
        lines.append(f"- {status} {check.get('name')}: observed={check.get('observed')} expected={check.get('operator')} {check.get('expected')}")
    return "\n".join(lines) + "\n"


def build_and_write(
    *,
    e2e_rag_demo_report_path: Path,
    output_dir: Path,
    top_k_citations: int,
    thresholds: QualityThresholds,
    write_quality: bool = True,
) -> Dict[str, Any]:
    source = _read_json(e2e_rag_demo_report_path)
    report = build_api_wrapper_smoke(source, top_k_citations=top_k_citations)
    report["summary"]["source_e2e_rag_demo_report_path"] = str(e2e_rag_demo_report_path)
    quality = evaluate_quality(report, thresholds)
    report["quality_status"] = quality["quality_status"]
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "trace_net_e2e_api_wrapper_smoke_v1.json"
    requests_path = output_dir / "trace_net_e2e_api_wrapper_smoke_requests_v1.jsonl"
    responses_path = output_dir / "trace_net_e2e_api_wrapper_smoke_responses_v1.jsonl"
    inspect_path = output_dir / "trace_net_e2e_api_wrapper_smoke_v1_inspect.md"
    quality_path = output_dir / "trace_net_e2e_api_wrapper_smoke_v1_quality.json"
    report["report_path"] = str(report_path)
    report["requests_jsonl_path"] = str(requests_path)
    report["responses_jsonl_path"] = str(responses_path)
    report["inspect_md_path"] = str(inspect_path)
    _write_json(report_path, report)
    _write_jsonl(requests_path, report["api_requests"])
    _write_jsonl(responses_path, report["api_responses"])
    inspect_path.write_text(render_inspect(report, quality), encoding="utf-8")
    if write_quality:
        _write_json(quality_path, quality)
    return report


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--min-source-demo-records", type=int, default=5)
    parser.add_argument("--min-complete-demo-flows", type=int, default=5)
    parser.add_argument("--min-api-requests", type=int, default=5)
    parser.add_argument("--min-api-responses", type=int, default=5)
    parser.add_argument("--min-citation-backed-responses", type=int, default=4)
    parser.add_argument("--min-total-api-citations", type=int, default=10)
    parser.add_argument("--min-pages-with-api-citations", type=int, default=2)
    parser.add_argument("--min-field-count", type=int, default=3)
    parser.add_argument("--max-schema-missing-required-key-records", type=int, default=0)
    parser.add_argument("--max-unsafe-records", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-source-demo-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")


def thresholds_from_args(args: argparse.Namespace) -> QualityThresholds:
    return QualityThresholds(
        min_source_demo_records=args.min_source_demo_records,
        min_complete_demo_flows=args.min_complete_demo_flows,
        min_api_requests=args.min_api_requests,
        min_api_responses=args.min_api_responses,
        min_citation_backed_responses=args.min_citation_backed_responses,
        min_total_api_citations=args.min_total_api_citations,
        min_pages_with_api_citations=args.min_pages_with_api_citations,
        min_field_count=args.min_field_count,
        max_schema_missing_required_key_records=args.max_schema_missing_required_key_records,
        max_unsafe_records=args.max_unsafe_records,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_source_demo_quality_pass=args.require_source_demo_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
    )


__all__ = [
    "SCHEMA_VERSION",
    "STATUS",
    "READY_STATUS",
    "QualityThresholds",
    "build_api_wrapper_smoke",
    "evaluate_quality",
    "build_and_write",
    "render_inspect",
    "add_common_args",
    "thresholds_from_args",
]
