"""TRACE-Net E2E Evidence Sufficiency Gate v1.

Reviews retrieval-only context packs and decides whether each pack is ready for
final-gate review or must remain audit-only due to insufficient evidence.

This module intentionally does not answer questions, prove claims, mutate source
truth, or write to Postgres/Qdrant/OpenSearch. It is a safety gate between
context-pack construction and any later final-answer policy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

QUALITY_PASS = "PASS"
QUALITY_FAIL = "FAIL"
STATUS_BUILT = "E2E_EVIDENCE_SUFFICIENCY_GATE_BUILT"
READY_STATUS = "E2E_EVIDENCE_SUFFICIENCY_READY_FOR_FINAL_GATE_SMOKE"

REPORT_NAME = "trace_net_e2e_evidence_sufficiency_gate_v1.json"
QUALITY_NAME = "trace_net_e2e_evidence_sufficiency_gate_v1_quality.json"
GATE_RECORDS_JSONL_NAME = "trace_net_e2e_evidence_sufficiency_gate_records_v1.jsonl"
INSPECT_MD_NAME = "trace_net_e2e_evidence_sufficiency_gate_v1_inspect.md"

SUFFICIENT_STATUS = "EVIDENCE_SUFFICIENT_FOR_FINAL_GATE_REVIEW"
AUDIT_ONLY_STATUS = "AUDIT_ONLY_INSUFFICIENT_EVIDENCE"


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


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _stable_id(prefix: str, *parts: Any) -> str:
    raw = "|".join(_safe_str(p) for p in parts)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _context_quality_pass(report: Mapping[str, Any]) -> bool:
    if _safe_str(report.get("quality_status")).upper() == QUALITY_PASS:
        return True
    summary = report.get("summary") or {}
    if isinstance(summary, Mapping):
        return _as_bool(summary.get("source_runtime_quality_pass")) and _as_bool(summary.get("all_context_retrieval_only"))
    return False


def _context_ready_for_final_gate(report: Mapping[str, Any]) -> bool:
    contract = report.get("context_pack_contract") or {}
    summary = report.get("summary") or {}
    if isinstance(contract, Mapping) and _as_bool(contract.get("ready_for_final_gate")):
        return True
    if isinstance(summary, Mapping) and _as_bool(summary.get("ready_for_final_gate")):
        return True
    status = _safe_str(report.get("e2e_context_pack_status"))
    return status == "E2E_CONTEXT_PACK_READY_FOR_FINAL_GATE"


def _get_context_packs(report: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    packs = report.get("context_packs")
    if isinstance(packs, list):
        return [p for p in packs if isinstance(p, Mapping)]
    return []


def _get_pack_items(pack: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    items = pack.get("top_context_items")
    if isinstance(items, list):
        return [i for i in items if isinstance(i, Mapping)]
    items = pack.get("context_items")
    if isinstance(items, list):
        return [i for i in items if isinstance(i, Mapping)]
    return []


def _count_bad(records: Iterable[Mapping[str, Any]], key: str) -> int:
    return sum(1 for rec in records if _as_bool(rec.get(key)))


def _quality_check(name: str, observed: Any, expected: str, passed: bool) -> Dict[str, Any]:
    return {"name": name, "observed": observed, "expected": expected, "passed": bool(passed)}


def build_gate_record(pack: Mapping[str, Any], *, min_items_per_pack: int, min_citation_ready_items_per_pack: int, min_source_trace_ready_items_per_pack: int) -> Dict[str, Any]:
    query_id = _safe_str(pack.get("query_id"))
    items = _get_pack_items(pack)
    citation_ready_count = sum(1 for item in items if _as_bool(item.get("citation_ready")))
    source_trace_ready_count = sum(1 for item in items if _as_bool(item.get("source_trace_ready")))
    schema_complete_count = sum(1 for item in items if _as_bool(item.get("schema_complete"), True))
    page_ids = sorted({_safe_str(item.get("page_id")) for item in items if _safe_str(item.get("page_id"))})
    field_names = sorted({_safe_str(item.get("field_name")) for item in items if _safe_str(item.get("field_name"))})
    unsafe_count = _count_bad(items, "unsafe")
    answer_permission_count = _count_bad(items, "answer_permission") + (1 if _as_bool(pack.get("answer_permission")) else 0)
    can_answer_directly_count = _count_bad(items, "can_answer_directly") + (1 if _as_bool(pack.get("can_answer_directly")) else 0)
    can_prove_claims_count = _count_bad(items, "can_prove_claims") + (1 if _as_bool(pack.get("can_prove_claims")) else 0)
    source_truth_mutation_allowed_count = _count_bad(items, "source_truth_mutation_allowed") + (1 if _as_bool(pack.get("source_truth_mutation_allowed")) else 0)

    reasons: List[str] = []
    if len(items) < min_items_per_pack:
        reasons.append(f"needs_at_least_{min_items_per_pack}_context_items")
    if citation_ready_count < min_citation_ready_items_per_pack:
        reasons.append(f"needs_at_least_{min_citation_ready_items_per_pack}_citation_ready_items")
    if source_trace_ready_count < min_source_trace_ready_items_per_pack:
        reasons.append(f"needs_at_least_{min_source_trace_ready_items_per_pack}_source_trace_ready_items")
    if unsafe_count:
        reasons.append("contains_unsafe_context_item")
    if answer_permission_count or can_answer_directly_count or can_prove_claims_count or source_truth_mutation_allowed_count:
        reasons.append("authority_or_source_truth_leak_detected")

    sufficient = not reasons
    status = SUFFICIENT_STATUS if sufficient else AUDIT_ONLY_STATUS
    # Important: sufficiency means ready for final gate review, not permission to answer.
    record = {
        "evidence_sufficiency_record_id": _stable_id("e2e_evidence_sufficiency_v1", query_id, pack.get("user_query"), len(items)),
        "query_id": query_id,
        "query_intent": _safe_str(pack.get("query_intent")),
        "user_query": _safe_str(pack.get("user_query")),
        "context_pack_id": _safe_str(pack.get("context_pack_id")),
        "evidence_sufficiency_status": status,
        "sufficient_for_final_gate_review": sufficient,
        "audit_only": not sufficient,
        "audit_reasons": reasons,
        "context_item_count": len(items),
        "citation_ready_item_count": citation_ready_count,
        "source_trace_ready_item_count": source_trace_ready_count,
        "schema_complete_item_count": schema_complete_count,
        "schema_missing_required_key_item_count": sum(1 for item in items if not _as_bool(item.get("schema_complete"), True)),
        "page_ids": page_ids,
        "field_names": field_names,
        "page_count": len(page_ids),
        "field_count": len(field_names),
        "top_context_items": list(items[:5]),
        "retrieval_permission": "ranking_only_until_final_gate",
        "answer_authority": "blocked_until_final_gate",
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "unsafe": False,
        "unsafe_context_item_count": unsafe_count,
        "source_answer_permission_count": answer_permission_count,
        "source_can_answer_directly_count": can_answer_directly_count,
        "source_can_prove_claims_count": can_prove_claims_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
    }
    return record


def evaluate_quality(report: Mapping[str, Any], args: argparse.Namespace) -> Tuple[str, List[Dict[str, Any]]]:
    summary = report.get("summary") or {}
    if not isinstance(summary, Mapping):
        summary = {}
    checks: List[Dict[str, Any]] = []
    add = checks.append
    add(_quality_check("source_context_pack_quality_pass", summary.get("source_context_pack_quality_pass"), "is True", _as_bool(summary.get("source_context_pack_quality_pass"))))
    add(_quality_check("source_context_pack_ready_for_final_gate", summary.get("source_context_pack_ready_for_final_gate"), "is True", _as_bool(summary.get("source_context_pack_ready_for_final_gate"))))
    add(_quality_check("source_context_pack_count", summary.get("source_context_pack_count", 0), f">= {args.min_source_context_packs}", _int(summary.get("source_context_pack_count")) >= args.min_source_context_packs))
    add(_quality_check("source_context_pack_with_items_count", summary.get("source_context_pack_with_items_count", 0), f">= {args.min_context_packs_with_items}", _int(summary.get("source_context_pack_with_items_count")) >= args.min_context_packs_with_items))
    add(_quality_check("evidence_sufficiency_gate_record_count", summary.get("evidence_sufficiency_gate_record_count", 0), f">= {args.min_evidence_gate_records}", _int(summary.get("evidence_sufficiency_gate_record_count")) >= args.min_evidence_gate_records))
    add(_quality_check("sufficient_context_pack_count", summary.get("sufficient_context_pack_count", 0), f">= {args.min_sufficient_context_packs}", _int(summary.get("sufficient_context_pack_count")) >= args.min_sufficient_context_packs))
    add(_quality_check("final_gate_review_ready_pack_count", summary.get("final_gate_review_ready_pack_count", 0), f">= {args.min_final_gate_ready_packs}", _int(summary.get("final_gate_review_ready_pack_count")) >= args.min_final_gate_ready_packs))
    add(_quality_check("total_evidence_item_count", summary.get("total_evidence_item_count", 0), f">= {args.min_total_evidence_items}", _int(summary.get("total_evidence_item_count")) >= args.min_total_evidence_items))
    add(_quality_check("citation_ready_evidence_item_count", summary.get("citation_ready_evidence_item_count", 0), f">= {args.min_citation_ready_evidence_items}", _int(summary.get("citation_ready_evidence_item_count")) >= args.min_citation_ready_evidence_items))
    add(_quality_check("source_trace_ready_evidence_item_count", summary.get("source_trace_ready_evidence_item_count", 0), f">= {args.min_source_trace_ready_evidence_items}", _int(summary.get("source_trace_ready_evidence_item_count")) >= args.min_source_trace_ready_evidence_items))
    add(_quality_check("page_with_evidence_item_count", summary.get("page_with_evidence_item_count", 0), f">= {args.min_pages_with_evidence_items}", _int(summary.get("page_with_evidence_item_count")) >= args.min_pages_with_evidence_items))
    add(_quality_check("field_count", summary.get("field_count", 0), f">= {args.min_field_count}", _int(summary.get("field_count")) >= args.min_field_count))
    add(_quality_check("schema_missing_required_key_item_count", summary.get("schema_missing_required_key_item_count", 0), "== 0", _int(summary.get("schema_missing_required_key_item_count")) == 0))
    add(_quality_check("unsafe_evidence_sufficiency_record_count", summary.get("unsafe_evidence_sufficiency_record_count", 0), f"<= {args.max_unsafe_records}", _int(summary.get("unsafe_evidence_sufficiency_record_count")) <= args.max_unsafe_records))
    add(_quality_check("answer_permission_count", summary.get("answer_permission_count", 0), f"<= {args.max_answer_permission_count}", _int(summary.get("answer_permission_count")) <= args.max_answer_permission_count))
    add(_quality_check("source_truth_mutation_allowed_count", summary.get("source_truth_mutation_allowed_count", 0), f"<= {args.max_source_truth_mutation_allowed}", _int(summary.get("source_truth_mutation_allowed_count")) <= args.max_source_truth_mutation_allowed))
    add(_quality_check("can_answer_directly_count", summary.get("can_answer_directly_count", 0), "== 0", _int(summary.get("can_answer_directly_count")) == 0))
    add(_quality_check("can_prove_claims_count", summary.get("can_prove_claims_count", 0), "== 0", _int(summary.get("can_prove_claims_count")) == 0))
    add(_quality_check("postgres_write_attempt_count", summary.get("postgres_write_attempt_count", 0), "== 0", _int(summary.get("postgres_write_attempt_count")) == 0))
    add(_quality_check("qdrant_write_attempt_count", summary.get("qdrant_write_attempt_count", 0), "== 0", _int(summary.get("qdrant_write_attempt_count")) == 0))
    add(_quality_check("opensearch_write_attempt_count", summary.get("opensearch_write_attempt_count", 0), "== 0", _int(summary.get("opensearch_write_attempt_count")) == 0))
    add(_quality_check("opensearch_upload_attempt_count", summary.get("opensearch_upload_attempt_count", 0), "== 0", _int(summary.get("opensearch_upload_attempt_count")) == 0))
    if args.require_no_answer_permission:
        add(_quality_check("all_gate_records_no_answer_authority", summary.get("all_gate_records_no_answer_authority", False), "is True", _as_bool(summary.get("all_gate_records_no_answer_authority"))))
    status = QUALITY_PASS if all(c["passed"] for c in checks) else QUALITY_FAIL
    return status, checks


def build_report(context_pack_path: Path, output_dir: Path, args: argparse.Namespace) -> Dict[str, Any]:
    source = _read_json(context_pack_path)
    packs = _get_context_packs(source)
    gate_records = [
        build_gate_record(
            pack,
            min_items_per_pack=args.min_items_per_pack,
            min_citation_ready_items_per_pack=args.min_citation_ready_items_per_pack,
            min_source_trace_ready_items_per_pack=args.min_source_trace_ready_items_per_pack,
        )
        for pack in packs
    ]
    evidence_items: List[Mapping[str, Any]] = []
    for pack in packs:
        evidence_items.extend(_get_pack_items(pack))

    page_ids = {_safe_str(item.get("page_id")) for item in evidence_items if _safe_str(item.get("page_id"))}
    field_counts: Dict[str, int] = {}
    for item in evidence_items:
        field = _safe_str(item.get("field_name"))
        if field:
            field_counts[field] = field_counts.get(field, 0) + 1

    sufficient_count = sum(1 for rec in gate_records if _as_bool(rec.get("sufficient_for_final_gate_review")))
    audit_only_count = sum(1 for rec in gate_records if _as_bool(rec.get("audit_only")))
    summary: Dict[str, Any] = {
        "source_context_pack_path": str(context_pack_path),
        "source_context_pack_quality_pass": _context_quality_pass(source),
        "source_context_pack_ready_for_final_gate": _context_ready_for_final_gate(source),
        "source_context_pack_count": len(packs),
        "source_context_pack_with_items_count": sum(1 for p in packs if len(_get_pack_items(p)) > 0),
        "evidence_sufficiency_gate_record_count": len(gate_records),
        "sufficient_context_pack_count": sufficient_count,
        "audit_only_context_pack_count": audit_only_count,
        "final_gate_review_ready_pack_count": sufficient_count,
        "total_evidence_item_count": len(evidence_items),
        "citation_ready_evidence_item_count": sum(1 for item in evidence_items if _as_bool(item.get("citation_ready"))),
        "source_trace_ready_evidence_item_count": sum(1 for item in evidence_items if _as_bool(item.get("source_trace_ready"))),
        "page_with_evidence_item_count": len(page_ids),
        "field_count": len(field_counts),
        "field_counts": dict(sorted(field_counts.items())),
        "schema_missing_required_key_item_count": sum(_int(rec.get("schema_missing_required_key_item_count")) for rec in gate_records),
        "unsafe_evidence_sufficiency_record_count": _count_bad(gate_records, "unsafe") + sum(_int(rec.get("unsafe_context_item_count")) for rec in gate_records),
        "answer_permission_count": _count_bad(gate_records, "answer_permission") + sum(_int(rec.get("source_answer_permission_count")) for rec in gate_records),
        "can_answer_directly_count": _count_bad(gate_records, "can_answer_directly") + sum(_int(rec.get("source_can_answer_directly_count")) for rec in gate_records),
        "can_prove_claims_count": _count_bad(gate_records, "can_prove_claims") + sum(_int(rec.get("source_can_prove_claims_count")) for rec in gate_records),
        "source_truth_mutation_allowed_count": _count_bad(gate_records, "source_truth_mutation_allowed") + sum(_int(rec.get("source_truth_mutation_allowed_count")) for rec in gate_records),
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "opensearch_upload_attempt_count": 0,
        "evidence_sufficiency_gate_status": READY_STATUS,
        "ready_for_final_gate_smoke": sufficient_count > 0,
        "retrieval_permission": "ranking_only_until_final_gate",
        "answer_authority": "blocked_until_final_gate",
        "all_gate_records_no_answer_authority": all(not _as_bool(rec.get("answer_permission")) and not _as_bool(rec.get("can_answer_directly")) and not _as_bool(rec.get("can_prove_claims")) for rec in gate_records) if gate_records else False,
    }
    report: Dict[str, Any] = {
        "artifact_name": "trace_net_e2e_evidence_sufficiency_gate_v1",
        "status": STATUS_BUILT,
        "quality_status": QUALITY_FAIL,
        "e2e_evidence_sufficiency_gate_status": READY_STATUS,
        "evidence_sufficiency_contract": {
            "purpose": "Review context packs for final-gate readiness without granting answer authority.",
            "retrieval_permission": "ranking_only_until_final_gate",
            "answer_authority": "blocked_until_final_gate",
            "ready_for_final_gate_smoke": True,
            "sufficiency_means": "ready_for_final_gate_review_not_answer_permission",
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
            "writes_to_postgres": False,
            "writes_to_qdrant": False,
            "writes_to_opensearch": False,
            "uploads_to_opensearch": False,
        },
        "summary": summary,
        "gate_records": gate_records,
        "quality_checks": [],
        "paths": {
            "report_path": str(output_dir / REPORT_NAME),
            "quality_path": str(output_dir / QUALITY_NAME),
            "gate_records_jsonl_path": str(output_dir / GATE_RECORDS_JSONL_NAME),
            "inspect_md_path": str(output_dir / INSPECT_MD_NAME),
        },
    }
    quality_status, checks = evaluate_quality(report, args)
    report["quality_status"] = quality_status
    report["quality_checks"] = checks
    return report


def write_inspect_md(path: Path, report: Mapping[str, Any]) -> None:
    summary = report.get("summary") or {}
    contract = report.get("evidence_sufficiency_contract") or {}
    records = report.get("gate_records") or []
    lines: List[str] = []
    lines.append("# TRACE-Net E2E Evidence Sufficiency Gate v1 Inspect")
    lines.append("")
    lines.append(f"Quality status: **{report.get('quality_status', QUALITY_FAIL)}**")
    lines.append("")
    lines.append("## Purpose")
    lines.append("This artifact checks whether each retrieval-only context pack has enough citation/source-trace-ready evidence for final-gate review.")
    lines.append("It does not answer, prove claims, mutate source truth, or write to runtime services.")
    lines.append("")
    lines.append("## Evidence sufficiency contract")
    for key in ("retrieval_permission", "answer_authority", "ready_for_final_gate_smoke", "sufficiency_means", "can_answer_directly", "can_prove_claims", "source_truth_mutation_allowed", "writes_to_postgres", "writes_to_qdrant", "writes_to_opensearch", "uploads_to_opensearch"):
        lines.append(f"- {key}: {contract.get(key)}")
    lines.append("")
    lines.append("## Main counters")
    for key in ("source_context_pack_count", "evidence_sufficiency_gate_record_count", "sufficient_context_pack_count", "audit_only_context_pack_count", "final_gate_review_ready_pack_count", "total_evidence_item_count", "citation_ready_evidence_item_count", "source_trace_ready_evidence_item_count", "page_with_evidence_item_count", "field_count", "schema_missing_required_key_item_count"):
        lines.append(f"- {key}: {summary.get(key)}")
    lines.append("")
    lines.append("## Field counts")
    field_counts = summary.get("field_counts") if isinstance(summary, Mapping) else {}
    if isinstance(field_counts, Mapping) and field_counts:
        for key, value in field_counts.items():
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Safety/write counters")
    for key in ("unsafe_evidence_sufficiency_record_count", "answer_permission_count", "can_answer_directly_count", "can_prove_claims_count", "source_truth_mutation_allowed_count", "postgres_write_attempt_count", "qdrant_write_attempt_count", "opensearch_write_attempt_count", "opensearch_upload_attempt_count"):
        lines.append(f"- {key}: {summary.get(key)}")
    lines.append("")
    lines.append("## Gate records")
    if isinstance(records, list):
        for rec in records:
            if not isinstance(rec, Mapping):
                continue
            lines.append(f"- {rec.get('query_id')} | {rec.get('query_intent')} | {rec.get('evidence_sufficiency_status')} | items={rec.get('context_item_count')} pages={','.join(rec.get('page_ids') or [])}")
            if rec.get("audit_reasons"):
                lines.append(f"  - audit_reasons: {', '.join(rec.get('audit_reasons') or [])}")
            items = rec.get("top_context_items") or []
            if isinstance(items, list):
                for item in items[:3]:
                    if isinstance(item, Mapping):
                        lines.append(f"  - {item.get('page_id')} | {item.get('field_name')} | {item.get('normalized_value')} | citation_ready={item.get('citation_ready')} | source_trace_ready={item.get('source_trace_ready')}")
    lines.append("")
    lines.append("## Quality checks")
    checks = report.get("quality_checks") or []
    if isinstance(checks, list):
        for check in checks:
            if isinstance(check, Mapping):
                status = "PASS" if check.get("passed") else "FAIL"
                lines.append(f"- {status} {check.get('name')}: observed={check.get('observed')} expected={check.get('expected')}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_outputs(report: Mapping[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / REPORT_NAME, report)
    _write_json(output_dir / QUALITY_NAME, {"quality_status": report.get("quality_status"), "quality_checks": report.get("quality_checks", []), "summary": report.get("summary", {})})
    records = report.get("gate_records") if isinstance(report.get("gate_records"), list) else []
    _write_jsonl(output_dir / GATE_RECORDS_JSONL_NAME, [r for r in records if isinstance(r, Mapping)])
    write_inspect_md(output_dir / INSPECT_MD_NAME, report)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net E2E evidence sufficiency gate from context packs.")
    parser.add_argument("--e2e-context-pack-builder", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--min-items-per-pack", type=int, default=3)
    parser.add_argument("--min-citation-ready-items-per-pack", type=int, default=3)
    parser.add_argument("--min-source-trace-ready-items-per-pack", type=int, default=3)
    parser.add_argument("--min-source-context-packs", type=int, default=5)
    parser.add_argument("--min-context-packs-with-items", type=int, default=5)
    parser.add_argument("--min-evidence-gate-records", type=int, default=5)
    parser.add_argument("--min-sufficient-context-packs", type=int, default=4)
    parser.add_argument("--min-final-gate-ready-packs", type=int, default=4)
    parser.add_argument("--min-total-evidence-items", type=int, default=20)
    parser.add_argument("--min-citation-ready-evidence-items", type=int, default=20)
    parser.add_argument("--min-source-trace-ready-evidence-items", type=int, default=20)
    parser.add_argument("--min-pages-with-evidence-items", type=int, default=2)
    parser.add_argument("--min-field-count", type=int, default=3)
    parser.add_argument("--max-unsafe-records", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-source-context-pack-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    report = build_report(args.e2e_context_pack_builder, args.output_dir, args)
    write_outputs(report, args.output_dir)
    summary = report["summary"]
    print("TRACE-Net E2E Evidence Sufficiency Gate v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    print(f" e2e_evidence_sufficiency_gate_status: {report['e2e_evidence_sufficiency_gate_status']}")
    for key in (
        "source_context_pack_count",
        "evidence_sufficiency_gate_record_count",
        "sufficient_context_pack_count",
        "audit_only_context_pack_count",
        "final_gate_review_ready_pack_count",
        "total_evidence_item_count",
        "citation_ready_evidence_item_count",
        "source_trace_ready_evidence_item_count",
        "page_with_evidence_item_count",
        "field_count",
        "schema_missing_required_key_item_count",
        "unsafe_evidence_sufficiency_record_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
        "opensearch_upload_attempt_count",
    ):
        print(f" {key}: {summary.get(key)}")
    print(f" report_path: {args.output_dir / REPORT_NAME}")
    print(f" gate_records_jsonl_path: {args.output_dir / GATE_RECORDS_JSONL_NAME}")
    print(f" inspect_md_path: {args.output_dir / INSPECT_MD_NAME}")
    if args.quality and report["quality_status"] != QUALITY_PASS:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
