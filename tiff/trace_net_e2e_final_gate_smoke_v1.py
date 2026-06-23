"""TRACE-Net E2E final gate smoke v1.

This module consumes the E2E evidence sufficiency gate artifact and creates a
local, deterministic final-gate smoke report. It is intentionally conservative:
records can produce citation-backed response *drafts* for review, but they do
not mutate source truth, write to runtime services, or grant proof authority.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

REPORT_FILENAME = "trace_net_e2e_final_gate_smoke_v1.json"
QUALITY_FILENAME = "trace_net_e2e_final_gate_smoke_v1_quality.json"
RECORDS_JSONL_FILENAME = "trace_net_e2e_final_gate_smoke_records_v1.jsonl"
INSPECT_MD_FILENAME = "trace_net_e2e_final_gate_smoke_v1_inspect.md"

STATUS_BUILT = "E2E_FINAL_GATE_SMOKE_BUILT"
STATUS_READY = "E2E_FINAL_GATE_SMOKE_READY_FOR_API_OR_AUDIT_RESPONSE"
DECISION_SAFE_DRAFT = "FINAL_GATE_SAFE_CITATION_BACKED_RESPONSE_DRAFT"
DECISION_AUDIT_ONLY = "FINAL_GATE_AUDIT_ONLY_RESPONSE"
SUFFICIENCY_READY = "EVIDENCE_SUFFICIENT_FOR_FINAL_GATE_REVIEW"

REQUIRED_RECORD_KEYS = (
    "query_id",
    "query_intent",
    "user_query",
    "final_gate_decision",
    "response_mode",
    "citation_count",
    "source_trace_count",
    "answer_permission",
    "can_answer_directly",
    "can_prove_claims",
    "source_truth_mutation_allowed",
)


def _read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return data


def _write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")


def _as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "pass"}
    return bool(value)


def _safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _slug(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return text or "unknown"


def _collection_from(data: Mapping[str, Any], keys: Sequence[str]) -> List[Dict[str, Any]]:
    for key in keys:
        rows = data.get(key)
        if isinstance(rows, list):
            return [r for r in rows if isinstance(r, dict)]
    return []


def _items_from_gate_record(record: Mapping[str, Any]) -> List[Dict[str, Any]]:
    keys = (
        "evidence_items",
        "top_evidence_items",
        "context_items",
        "top_context_items",
        "items",
        "citations",
    )
    for key in keys:
        rows = record.get(key)
        if isinstance(rows, list):
            return [r for r in rows if isinstance(r, dict)]
    # Conservative fallback: preserve page-level citations if the gate artifact
    # only carried page_ids in each record.
    page_ids = [str(p) for p in _as_list(record.get("page_ids")) if p]
    fallback: List[Dict[str, Any]] = []
    for i, page_id in enumerate(page_ids):
        fallback.append(
            {
                "context_item_id": f"fallback_context_item_{i+1:03d}",
                "page_id": page_id,
                "field_name": record.get("query_intent", "source_trace"),
                "normalized_value": record.get("user_query") or record.get("query") or "source-trace-ready context item",
                "citation_ready": True,
                "source_trace_ready": True,
                "retrieval_permission": "ranking_only_until_final_gate",
            }
        )
    return fallback


def _citation_id(query_id: str, item: Mapping[str, Any], index: int) -> str:
    page_id = _safe_str(item.get("page_id"), "unknown_page")
    field_name = _safe_str(item.get("field_name"), "evidence")
    return f"cite_{_slug(query_id)}_{_slug(page_id)}_{_slug(field_name)}_{index:03d}"


def _normalize_citation(query_id: str, item: Mapping[str, Any], index: int) -> Dict[str, Any]:
    page_id = _safe_str(item.get("page_id"), "unknown_page")
    field_name = _safe_str(item.get("field_name") or item.get("field_role"), "evidence")
    normalized_value = _safe_str(
        item.get("normalized_value")
        or item.get("evidence_value")
        or item.get("display_value")
        or item.get("text")
        or item.get("value"),
        "",
    )
    return {
        "citation_id": _citation_id(query_id, item, index),
        "page_id": page_id,
        "field_name": field_name,
        "normalized_value": normalized_value,
        "source_trace_ready": _bool(item.get("source_trace_ready", True)),
        "citation_ready": _bool(item.get("citation_ready", True)),
        "retrieval_score": item.get("retrieval_score"),
        "routing_boost": item.get("routing_boost"),
        "evidence_route": item.get("route") or item.get("evidence_route") or "table",
        "retrieval_permission": item.get("retrieval_permission", "ranking_only_until_final_gate"),
    }


def _draft_response(user_query: str, citations: Sequence[Mapping[str, Any]], audit_only: bool) -> str:
    if audit_only:
        return (
            "I found related TRACE-Net retrieval context, but the evidence did not meet the "
            "final-gate smoke threshold. This should remain audit-only until more source-traced "
            "evidence is available."
        )
    bullets = []
    for cite in citations[:3]:
        value = _safe_str(cite.get("normalized_value"), "")
        field_name = _safe_str(cite.get("field_name"), "evidence")
        page_id = _safe_str(cite.get("page_id"), "unknown_page")
        bullets.append(f"{field_name}={value} on {page_id}".strip())
    joined = "; ".join(bullets) if bullets else "source-traced context items were found"
    return (
        f"Final-gate smoke draft for query: {user_query!r}. "
        f"TRACE-Net found citation/source-trace-ready evidence: {joined}. "
        "This draft is safe for final-gate review and remains non-mutating; it does not rewrite source truth."
    )


def _record_schema_complete(record: Mapping[str, Any]) -> bool:
    return all(k in record for k in REQUIRED_RECORD_KEYS)


def build_final_gate_smoke(
    *,
    evidence_sufficiency_gate_path: Path,
    output_dir: Path,
    top_k: int = 3,
    min_citations_per_response: int = 1,
    min_source_traces_per_response: int = 1,
    min_source_gate_records: int = 1,
    min_final_gate_records: int = 1,
    min_safe_response_drafts: int = 1,
    min_citation_backed_response_drafts: int = 1,
    min_audit_or_safe_responses: int = 1,
    min_total_citations: int = 1,
    min_pages_cited: int = 1,
    min_field_count: int = 1,
    max_unsafe_records: int = 0,
    max_answer_permission_count: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    require_source_sufficiency_quality_pass: bool = False,
    require_no_answer_permission: bool = False,
    write_quality: bool = True,
) -> Dict[str, Any]:
    source = _read_json(evidence_sufficiency_gate_path)
    source_summary = source.get("summary", {}) if isinstance(source.get("summary"), dict) else {}
    source_quality_pass = source.get("quality_status") == "PASS" or source_summary.get("source_context_pack_quality_pass") is True
    source_ready = _bool(
        source_summary.get("ready_for_final_gate_smoke")
        or source.get("evidence_sufficiency_contract", {}).get("ready_for_final_gate_smoke")
    )

    gate_records = _collection_from(source, ("gate_records", "evidence_sufficiency_gate_records", "records"))

    final_records: List[Dict[str, Any]] = []
    field_counts: Counter[str] = Counter()
    cited_pages: set[str] = set()

    for index, gate_record in enumerate(gate_records, start=1):
        query_id = _safe_str(gate_record.get("query_id"), f"e2e_final_gate_query_{index:04d}")
        query_intent = _safe_str(gate_record.get("query_intent"), "unknown")
        user_query = _safe_str(gate_record.get("user_query") or gate_record.get("query"), query_id)
        status = _safe_str(gate_record.get("evidence_sufficiency_status"), "")
        items = _items_from_gate_record(gate_record)
        citations = [
            _normalize_citation(query_id, item, i)
            for i, item in enumerate(items[: max(0, top_k)], start=1)
        ]
        citation_ready_count = sum(1 for c in citations if _bool(c.get("citation_ready")))
        source_trace_ready_count = sum(1 for c in citations if _bool(c.get("source_trace_ready")))
        for c in citations:
            if c.get("page_id"):
                cited_pages.add(str(c["page_id"]))
            if c.get("field_name"):
                field_counts[str(c["field_name"])] += 1

        evidence_ready = status == SUFFICIENCY_READY or _bool(gate_record.get("final_gate_review_ready"))
        has_citation_floor = citation_ready_count >= min_citations_per_response
        has_trace_floor = source_trace_ready_count >= min_source_traces_per_response
        safe_draft = evidence_ready and has_citation_floor and has_trace_floor
        decision = DECISION_SAFE_DRAFT if safe_draft else DECISION_AUDIT_ONLY
        response_mode = "citation_backed_response_draft" if safe_draft else "audit_only_response"
        audit_reasons = list(_as_list(gate_record.get("audit_reasons")))
        if not evidence_ready:
            audit_reasons.append("evidence_sufficiency_gate_did_not_mark_pack_ready")
        if not has_citation_floor:
            audit_reasons.append("not_enough_citation_ready_items_for_smoke_threshold")
        if not has_trace_floor:
            audit_reasons.append("not_enough_source_trace_ready_items_for_smoke_threshold")

        record = {
            "final_gate_record_id": f"e2e_final_gate_smoke_v1_{index:04d}",
            "query_id": query_id,
            "query_intent": query_intent,
            "user_query": user_query,
            "source_evidence_sufficiency_status": status,
            "final_gate_decision": decision,
            "response_mode": response_mode,
            "response_draft": _draft_response(user_query, citations, audit_only=not safe_draft),
            "citation_count": len(citations),
            "citation_ready_count": citation_ready_count,
            "source_trace_count": source_trace_ready_count,
            "page_ids": sorted({str(c.get("page_id")) for c in citations if c.get("page_id")}),
            "field_names": sorted({str(c.get("field_name")) for c in citations if c.get("field_name")}),
            "citations": citations,
            "audit_reasons": audit_reasons,
            "safe_for_user_review": safe_draft,
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
            "retrieval_permission": "ranking_only_until_final_gate",
            "answer_authority": "blocked_in_smoke_draft",
            "writes_to_postgres": False,
            "writes_to_qdrant": False,
            "writes_to_opensearch": False,
            "uploads_to_opensearch": False,
            "unsafe_record": False,
        }
        record["schema_complete"] = _record_schema_complete(record)
        final_records.append(record)

    safe_response_draft_count = sum(1 for r in final_records if r["final_gate_decision"] == DECISION_SAFE_DRAFT)
    audit_only_response_count = sum(1 for r in final_records if r["final_gate_decision"] == DECISION_AUDIT_ONLY)
    citation_backed_response_draft_count = sum(
        1 for r in final_records if r["final_gate_decision"] == DECISION_SAFE_DRAFT and r["citation_ready_count"] >= min_citations_per_response
    )
    unsafe_count = sum(1 for r in final_records if _bool(r.get("unsafe_record")))
    answer_permission_count = sum(1 for r in final_records if _bool(r.get("answer_permission")))
    can_answer_directly_count = sum(1 for r in final_records if _bool(r.get("can_answer_directly")))
    can_prove_claims_count = sum(1 for r in final_records if _bool(r.get("can_prove_claims")))
    source_truth_mutation_allowed_count = sum(1 for r in final_records if _bool(r.get("source_truth_mutation_allowed")))
    schema_missing_required_key_record_count = sum(1 for r in final_records if not r.get("schema_complete"))
    total_citation_count = sum(int(r.get("citation_count", 0)) for r in final_records)
    postgres_write_attempt_count = sum(1 for r in final_records if _bool(r.get("writes_to_postgres")))
    qdrant_write_attempt_count = sum(1 for r in final_records if _bool(r.get("writes_to_qdrant")))
    opensearch_write_attempt_count = sum(1 for r in final_records if _bool(r.get("writes_to_opensearch")))
    opensearch_upload_attempt_count = sum(1 for r in final_records if _bool(r.get("uploads_to_opensearch")))

    summary = {
        "source_sufficiency_gate_path": str(evidence_sufficiency_gate_path),
        "source_sufficiency_quality_pass": bool(source_quality_pass),
        "source_sufficiency_ready_for_final_gate_smoke": bool(source_ready),
        "source_gate_record_count": len(gate_records),
        "final_gate_record_count": len(final_records),
        "safe_response_draft_count": safe_response_draft_count,
        "citation_backed_response_draft_count": citation_backed_response_draft_count,
        "audit_only_response_count": audit_only_response_count,
        "audit_or_safe_response_count": safe_response_draft_count + audit_only_response_count,
        "total_citation_count": total_citation_count,
        "page_with_citation_count": len(cited_pages),
        "field_count": len(field_counts),
        "field_counts": dict(sorted(field_counts.items())),
        "schema_missing_required_key_record_count": schema_missing_required_key_record_count,
        "unsafe_final_gate_smoke_record_count": unsafe_count,
        "answer_permission_count": answer_permission_count,
        "can_answer_directly_count": can_answer_directly_count,
        "can_prove_claims_count": can_prove_claims_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "postgres_write_attempt_count": postgres_write_attempt_count,
        "qdrant_write_attempt_count": qdrant_write_attempt_count,
        "opensearch_write_attempt_count": opensearch_write_attempt_count,
        "opensearch_upload_attempt_count": opensearch_upload_attempt_count,
        "all_final_gate_smoke_records_no_answer_authority": answer_permission_count == 0 and can_answer_directly_count == 0 and can_prove_claims_count == 0,
        "e2e_final_gate_smoke_status": STATUS_READY,
    }

    quality_checks = evaluate_quality(
        summary,
        min_source_gate_records=min_source_gate_records,
        min_final_gate_records=min_final_gate_records,
        min_safe_response_drafts=min_safe_response_drafts,
        min_citation_backed_response_drafts=min_citation_backed_response_drafts,
        min_audit_or_safe_responses=min_audit_or_safe_responses,
        min_total_citations=min_total_citations,
        min_pages_cited=min_pages_cited,
        min_field_count=min_field_count,
        max_unsafe_records=max_unsafe_records,
        max_answer_permission_count=max_answer_permission_count,
        max_source_truth_mutation_allowed=max_source_truth_mutation_allowed,
        require_source_sufficiency_quality_pass=require_source_sufficiency_quality_pass,
        require_no_answer_permission=require_no_answer_permission,
    )
    quality_status = "PASS" if all(c["passed"] for c in quality_checks) else "FAIL"

    report = {
        "artifact_type": "trace_net_e2e_final_gate_smoke_v1",
        "status": STATUS_BUILT,
        "quality_status": quality_status,
        "e2e_final_gate_smoke_status": STATUS_READY,
        "final_gate_smoke_contract": {
            "purpose": "Create citation-backed final-gate smoke response drafts or audit-only responses from sufficiency-gated context packs.",
            "response_permission": "draft_for_review_or_audit_only",
            "answer_authority": "blocked_in_smoke_draft",
            "safety_note": "This smoke artifact demonstrates response shaping but does not grant direct answer/proof authority.",
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
            "writes_to_postgres": False,
            "writes_to_qdrant": False,
            "writes_to_opensearch": False,
            "uploads_to_opensearch": False,
            "ready_for_api_or_audit_response": quality_status == "PASS",
        },
        "summary": summary,
        "final_gate_records": final_records,
        "quality_checks": quality_checks,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / REPORT_FILENAME
    quality_path = output_dir / QUALITY_FILENAME
    records_jsonl_path = output_dir / RECORDS_JSONL_FILENAME
    inspect_md_path = output_dir / INSPECT_MD_FILENAME
    _write_json(report_path, report)
    _write_jsonl(records_jsonl_path, final_records)
    if write_quality:
        _write_json(quality_path, {"quality_status": quality_status, "quality_checks": quality_checks, "summary": summary})
    _write_inspect_md(inspect_md_path, report)

    report["report_path"] = str(report_path)
    report["records_jsonl_path"] = str(records_jsonl_path)
    report["inspect_md_path"] = str(inspect_md_path)
    if write_quality:
        report["quality_path"] = str(quality_path)
    _write_json(report_path, report)
    return report


def evaluate_quality(
    summary: Mapping[str, Any],
    *,
    min_source_gate_records: int = 1,
    min_final_gate_records: int = 1,
    min_safe_response_drafts: int = 1,
    min_citation_backed_response_drafts: int = 1,
    min_audit_or_safe_responses: int = 1,
    min_total_citations: int = 1,
    min_pages_cited: int = 1,
    min_field_count: int = 1,
    max_unsafe_records: int = 0,
    max_answer_permission_count: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    require_source_sufficiency_quality_pass: bool = False,
    require_no_answer_permission: bool = False,
) -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []

    def ge(name: str, expected: int) -> None:
        observed = int(summary.get(name, 0) or 0)
        checks.append({"name": name, "observed": observed, "expected": f">= {expected}", "passed": observed >= expected})

    def le(name: str, expected: int) -> None:
        observed = int(summary.get(name, 0) or 0)
        checks.append({"name": name, "observed": observed, "expected": f"<= {expected}", "passed": observed <= expected})

    def eq(name: str, expected: int) -> None:
        observed = int(summary.get(name, 0) or 0)
        checks.append({"name": name, "observed": observed, "expected": f"== {expected}", "passed": observed == expected})

    def is_true(name: str) -> None:
        observed = bool(summary.get(name))
        checks.append({"name": name, "observed": observed, "expected": "is True", "passed": observed is True})

    if require_source_sufficiency_quality_pass:
        is_true("source_sufficiency_quality_pass")
        is_true("source_sufficiency_ready_for_final_gate_smoke")
    ge("source_gate_record_count", min_source_gate_records)
    ge("final_gate_record_count", min_final_gate_records)
    ge("safe_response_draft_count", min_safe_response_drafts)
    ge("citation_backed_response_draft_count", min_citation_backed_response_drafts)
    ge("audit_or_safe_response_count", min_audit_or_safe_responses)
    ge("total_citation_count", min_total_citations)
    ge("page_with_citation_count", min_pages_cited)
    ge("field_count", min_field_count)
    eq("schema_missing_required_key_record_count", 0)
    le("unsafe_final_gate_smoke_record_count", max_unsafe_records)
    le("answer_permission_count", max_answer_permission_count)
    le("source_truth_mutation_allowed_count", max_source_truth_mutation_allowed)
    eq("can_answer_directly_count", 0)
    eq("can_prove_claims_count", 0)
    eq("postgres_write_attempt_count", 0)
    eq("qdrant_write_attempt_count", 0)
    eq("opensearch_write_attempt_count", 0)
    eq("opensearch_upload_attempt_count", 0)
    if require_no_answer_permission:
        is_true("all_final_gate_smoke_records_no_answer_authority")
    return checks


def _write_inspect_md(path: Path, report: Mapping[str, Any]) -> None:
    summary = report.get("summary", {})
    records = report.get("final_gate_records", [])
    checks = report.get("quality_checks", [])
    lines: List[str] = []
    lines.append("# TRACE-Net E2E Final Gate Smoke v1 Inspect")
    lines.append("")
    lines.append(f"Quality status: **{report.get('quality_status')}**")
    lines.append("")
    lines.append("## Purpose")
    lines.append("This artifact turns sufficiency-gated context packs into citation-backed response drafts or audit-only responses.")
    lines.append("It is intentionally conservative: the smoke draft does not mutate source truth, prove claims, or grant direct answer authority.")
    lines.append("")
    lines.append("## Final gate smoke contract")
    for k, v in report.get("final_gate_smoke_contract", {}).items():
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("## Main counters")
    for k in [
        "source_gate_record_count",
        "final_gate_record_count",
        "safe_response_draft_count",
        "citation_backed_response_draft_count",
        "audit_only_response_count",
        "total_citation_count",
        "page_with_citation_count",
        "field_count",
        "schema_missing_required_key_record_count",
    ]:
        lines.append(f"- {k}: {summary.get(k)}")
    lines.append("")
    lines.append("## Field counts")
    for k, v in (summary.get("field_counts") or {}).items():
        lines.append(f"- {k}: {v}")
    if not summary.get("field_counts"):
        lines.append("- none")
    lines.append("")
    lines.append("## Safety/write counters")
    for k in [
        "unsafe_final_gate_smoke_record_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
        "opensearch_upload_attempt_count",
    ]:
        lines.append(f"- {k}: {summary.get(k)}")
    lines.append("")
    lines.append("## Final gate records")
    for record in records:
        lines.append(
            f"- {record.get('query_id')} | {record.get('query_intent')} | {record.get('final_gate_decision')} | citations={record.get('citation_count')}"
        )
        draft = _safe_str(record.get("response_draft"), "")
        lines.append(f"  - draft: {draft[:240]}{'...' if len(draft) > 240 else ''}")
        for cite in record.get("citations", [])[:3]:
            lines.append(
                f"  - {cite.get('citation_id')} | {cite.get('page_id')} | {cite.get('field_name')} | {cite.get('normalized_value')}"
            )
        if record.get("audit_reasons"):
            lines.append(f"  - audit_reasons: {', '.join(map(str, record.get('audit_reasons', [])))}")
    lines.append("")
    lines.append("## Quality checks")
    for check in checks:
        status = "PASS" if check.get("passed") else "FAIL"
        lines.append(f"- {status} {check.get('name')}: observed={check.get('observed')} expected={check.get('expected')}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def add_common_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--e2e-evidence-sufficiency-gate", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--min-citations-per-response", type=int, default=1)
    parser.add_argument("--min-source-traces-per-response", type=int, default=1)
    parser.add_argument("--min-source-gate-records", type=int, default=1)
    parser.add_argument("--min-final-gate-records", type=int, default=1)
    parser.add_argument("--min-safe-response-drafts", type=int, default=1)
    parser.add_argument("--min-citation-backed-response-drafts", type=int, default=1)
    parser.add_argument("--min-audit-or-safe-responses", type=int, default=1)
    parser.add_argument("--min-total-citations", type=int, default=1)
    parser.add_argument("--min-pages-cited", type=int, default=1)
    parser.add_argument("--min-field-count", type=int, default=1)
    parser.add_argument("--max-unsafe-records", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-source-sufficiency-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = add_common_args(argparse.ArgumentParser(description="Build TRACE-Net E2E final gate smoke v1."))
    args = parser.parse_args(argv)
    report = build_final_gate_smoke(
        evidence_sufficiency_gate_path=Path(args.e2e_evidence_sufficiency_gate),
        output_dir=Path(args.output_dir),
        top_k=args.top_k,
        min_citations_per_response=args.min_citations_per_response,
        min_source_traces_per_response=args.min_source_traces_per_response,
        min_source_gate_records=args.min_source_gate_records,
        min_final_gate_records=args.min_final_gate_records,
        min_safe_response_drafts=args.min_safe_response_drafts,
        min_citation_backed_response_drafts=args.min_citation_backed_response_drafts,
        min_audit_or_safe_responses=args.min_audit_or_safe_responses,
        min_total_citations=args.min_total_citations,
        min_pages_cited=args.min_pages_cited,
        min_field_count=args.min_field_count,
        max_unsafe_records=args.max_unsafe_records,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_source_sufficiency_quality_pass=args.require_source_sufficiency_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
        write_quality=True,
    )
    print("TRACE-Net E2E Final Gate Smoke v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    for key in [
        "e2e_final_gate_smoke_status",
        "source_gate_record_count",
        "final_gate_record_count",
        "safe_response_draft_count",
        "citation_backed_response_draft_count",
        "audit_only_response_count",
        "total_citation_count",
        "page_with_citation_count",
        "field_count",
        "schema_missing_required_key_record_count",
        "unsafe_final_gate_smoke_record_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
        "opensearch_upload_attempt_count",
    ]:
        print(f" {key}: {report['summary'].get(key)}")
    print(f" report_path: {report.get('report_path')}")
    print(f" records_jsonl_path: {report.get('records_jsonl_path')}")
    print(f" inspect_md_path: {report.get('inspect_md_path')}")
    return 0 if report["quality_status"] == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
