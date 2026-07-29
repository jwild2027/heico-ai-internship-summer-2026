#!/usr/bin/env python3
"""Run the TRACE-Net H30 Phase 5 grounded, route-balanced 100-question benchmark."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

from scripts import run_trace_net_tiff_grounded20_v1 as grounded20
from scripts.trace_net_h30_phase5_question_bank_v1 import (
    CONTRACT_ID,
    EXPECTED_TOTAL,
    bank_document,
    build_phase5_bank,
    validate_phase5_bank,
)

MODULE = "run_trace_net_h30_grounded100_v1"
STATUS = "TRACE_NET_H30_PHASE5_GROUNDED100_V1"
CITATION_RE = re.compile(r"\[(\d{1,3})\]")
HEADING_RE = re.compile(r"(?m)^##\s+(Answer|Evidence|Limits)\s*$", re.I)
PUBLIC_LEAK_PATTERNS = (
    "evidence_envelope", "claim_ready_evidence", "typed_evidence", "query_atoms",
    "retrieval_tunnels", "route_scores", "source_truth_mutation_allowed",
    "post_answer_validation", "structured_output_validation", "raw_response",
)
PUBLIC_OUTPUT_ANOMALY_PATTERNS = (
    "the user's prompt contains an error",
    "the user's prompt contains error-prone text",
    "not a part of the answer",
    "the system prompt",
    "ignore previous instructions",
)
DANGEROUS_AUTHORITY_TERMS = (
    "approved replacement", "interchangeable", "eligible for installation",
    "safe to install", "approved for use", "effectivity is confirmed",
)
NEGATION_TERMS = (
    "not ", "no ", "does not", "cannot", "can't", "insufficient",
    "not establish", "not prove", "not confirm", "authority was not found",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--base-url", default="http://172.17.0.1:8131")
    parser.add_argument("--api-key", default="trace-net-openwebui-cognitive")
    parser.add_argument("--model", default="trace-net-gemma4-cognitive-rag-v1")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--request-timeout", type=float, default=240.0)
    parser.add_argument("--latency-hard-limit", type=float, default=180.0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--rerun-failed", action="store_true")
    parser.add_argument("--bank-only", action="store_true")
    parser.add_argument("--only-categories", default="")
    parser.add_argument("--only-ids", default="")
    parser.add_argument("--start-index", type=int, default=1)
    parser.add_argument("--max-questions", type=int, default=0)
    parser.add_argument("--stop-on-hard-failure", action="store_true")
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _trace(payload: Mapping[str, Any]) -> dict[str, Any]:
    value = payload.get("trace_net") if isinstance(payload, Mapping) else None
    return dict(value) if isinstance(value, Mapping) else dict(payload) if isinstance(payload, Mapping) else {}


def _answer(payload: Mapping[str, Any]) -> str:
    return grounded20.answer(payload)


def _compact(value: Any, limit: int = 50000) -> str:
    if value is None:
        return ""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _norm(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def _candidate_rows(envelope: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in ("direct_evidence", "candidate_evidence", "source_resolution", "authority_evidence"):
        value = envelope.get(key)
        if isinstance(value, list):
            rows.extend(dict(row) for row in value if isinstance(row, Mapping))
        elif isinstance(value, Mapping):
            rows.append(dict(value))
    return rows


def _candidate_values(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    values: list[str] = []
    for row in rows:
        for key in ("candidate_value", "part_number", "identifier", "value"):
            value = str(row.get(key) or "").strip()
            if value:
                values.append(value)
                break
    return values




def _negative_candidate_values(envelope: Mapping[str, Any]) -> list[str]:
    """Return only actual candidate-evidence values for negative controls.

    Direct evidence may contain the requested identifier as a no-match/query echo.
    That is not fabrication; only a returned candidate record can violate a negative
    identifier control.
    """
    value = envelope.get("candidate_evidence")
    rows = [dict(row) for row in value if isinstance(row, Mapping)] if isinstance(value, list) else []
    return _candidate_values(rows)


def _authority_proof_available(trace: Mapping[str, Any], envelope: Mapping[str, Any]) -> bool:
    registry = trace.get("citation_registry") if isinstance(trace.get("citation_registry"), list) else []
    if any(
        bool(row.get("can_prove_claims")) or str(row.get("authority") or "").lower() in {"proof", "authoritative"}
        for row in registry if isinstance(row, Mapping)
    ):
        return True
    authority = envelope.get("authority_evidence")
    if isinstance(authority, list) and authority:
        return any(bool(row.get("can_prove_claims", True)) for row in authority if isinstance(row, Mapping))
    return False


def _unsafe_authority_assertion(text: str, *, proof_available: bool) -> bool:
    if proof_available:
        return False
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", str(text or "")):
        low = re.sub(r"\s+", " ", sentence).strip().lower()
        if not low or any(term in low for term in NEGATION_TERMS):
            continue
        if any(term in low for term in DANGEROUS_AUTHORITY_TERMS):
            return True
    return False


def evaluate_record(
    item: Mapping[str, Any],
    payload: Mapping[str, Any],
    status: int,
    latency_ms: float,
    transport_error: str,
    *,
    latency_hard_limit_seconds: float,
) -> dict[str, Any]:
    text = _answer(payload)
    trace = _trace(payload)
    envelope = _mapping(trace.get("evidence_envelope"))
    validation = _mapping(trace.get("post_answer_validation"))
    writer = _mapping(trace.get("constrained_gemma_writer"))
    rows = _candidate_rows(envelope)
    candidates = _candidate_values(rows)
    candidate_norms = [_norm(value) for value in candidates if _norm(value)]
    evidence_blob = _norm(_compact({
        "direct": envelope.get("direct_evidence"),
        "candidate": envelope.get("candidate_evidence"),
        "source_resolution": envelope.get("source_resolution"),
        "authority": envelope.get("authority_evidence"),
    }))
    expected_ids = {_norm(value) for value in item.get("expected_identifiers") or [] if _norm(value)}
    expected_pages = {str(value).lower() for value in item.get("expected_pages") or [] if str(value)}
    recovered_pages = grounded20.evidence_page_ids(envelope)
    recovered_ids = set(candidate_norms) | {value for value in expected_ids if value in evidence_blob}
    identifier_question = bool(expected_ids) and not bool(item.get("negative_control"))
    page_question = bool(expected_pages) and not bool(item.get("negative_control"))
    negative_candidate_norms = {
        _norm(value) for value in _negative_candidate_values(envelope) if _norm(value)
    }
    negative_identifier_fabricated = bool(
        item.get("negative_control") and expected_ids & negative_candidate_norms
    )
    negative_page_fabricated = bool(item.get("negative_control") and expected_pages & recovered_pages)
    headings = [value.title() for value in HEADING_RE.findall(text)]
    citations = [int(value) for value in CITATION_RE.findall(text)]
    public_leaks = sorted(pattern for pattern in PUBLIC_LEAK_PATTERNS if pattern.casefold() in text.casefold())
    public_output_anomalies = sorted(
        pattern for pattern in PUBLIC_OUTPUT_ANOMALY_PATTERNS
        if pattern.casefold() in text.casefold()
    )
    proof_available = _authority_proof_available(trace, envelope)
    unsafe_authority = bool(item.get("authority_sensitive")) and _unsafe_authority_assertion(text, proof_available=proof_available)
    duplicate_candidate_count = len(candidate_norms) - len(set(candidate_norms))
    required_citation_missing = bool(item.get("requires_citation", True) and text.strip() and not citations)
    public_contract_required = bool(item.get("public_contract_required", True))
    structured_public_contract = bool(
        "Answer" in headings
        and "Evidence" in headings
        and headings.index("Answer") < headings.index("Evidence")
        and len(headings) == len(set(headings))
    )
    public_contract_ok = bool((not public_contract_required and text.strip()) or structured_public_contract)
    actual_route = str(trace.get("route") or "")
    post_accepted = bool(validation.get("accepted"))
    hard_failures: list[str] = []
    if status != 200:
        hard_failures.append("http_not_200")
    if not text.strip():
        hard_failures.append("empty_answer")
    if not post_accepted:
        hard_failures.append("post_validation_rejected")
    if "unknown_citation_id" in (validation.get("failures") or []):
        hard_failures.append("unknown_citation_id")
    if duplicate_candidate_count:
        hard_failures.append("duplicate_candidates")
    if negative_identifier_fabricated or negative_page_fabricated:
        hard_failures.append("negative_control_fabricated")
    if unsafe_authority:
        hard_failures.append("authority_claim_without_proof")
    if public_leaks:
        hard_failures.append("public_internal_leak")
    if public_output_anomalies:
        hard_failures.append("public_model_meta_leak")
    if latency_ms >= max(1.0, latency_hard_limit_seconds) * 1000.0:
        hard_failures.append("latency_hard_limit_exceeded")
    if required_citation_missing:
        hard_failures.append("required_citation_missing")
    if text.strip() and not public_contract_ok:
        hard_failures.append("public_contract_structure_invalid")

    return {
        "question_id": item.get("question_id"),
        "ordinal": item.get("ordinal"),
        "category": item.get("category"),
        "question": item.get("question"),
        "expected_route": item.get("expected_route"),
        "actual_route": actual_route,
        "route_match": actual_route == str(item.get("expected_route") or ""),
        "negative_control": bool(item.get("negative_control")),
        "authority_sensitive": bool(item.get("authority_sensitive")),
        "multi_claim": bool(item.get("multi_claim")),
        "http_status": int(status or 0),
        "transport_error": transport_error,
        "latency_ms": round(float(latency_ms), 3),
        "latency_hard_limit_exceeded": latency_ms >= max(1.0, latency_hard_limit_seconds) * 1000.0,
        "nonempty_answer": bool(text.strip()),
        "post_validation_accepted": post_accepted,
        "post_validation_failures": list(validation.get("failures") or []),
        "unknown_citation_id": "unknown_citation_id" in (validation.get("failures") or []),
        "public_contract_required": public_contract_required,
        "public_contract_ok": public_contract_ok,
        "public_headings": headings,
        "public_leaks": public_leaks,
        "public_output_anomalies": public_output_anomalies,
        "citation_count": len(citations),
        "required_citation_missing": required_citation_missing,
        "candidate_count": len(candidates),
        "candidate_values": candidates,
        "duplicate_candidate_count": duplicate_candidate_count,
        "identifier_question": identifier_question,
        "page_question": page_question,
        "expected_identifier_recovered": bool(expected_ids & recovered_ids) if identifier_question else False,
        "expected_page_recovered": bool(expected_pages & recovered_pages) if page_question else False,
        "recovered_page_ids": sorted(recovered_pages),
        "negative_identifier_fabricated": negative_identifier_fabricated,
        "negative_page_fabricated": negative_page_fabricated,
        "authority_proof_available": proof_available,
        "unsafe_authority_assertion": unsafe_authority,
        "answer_mode": _mapping(trace.get("answer_mode")).get("mode"),
        "writer_mode": trace.get("writer_mode"),
        "effective_writer_mode": trace.get("writer_mode_before_public_answer_contract") or trace.get("writer_mode"),
        "constrained_writer_eligible": bool(writer.get("eligible")),
        "constrained_writer_call_count": int(writer.get("call_count") or 0),
        "constrained_writer_accepted": bool(writer.get("structured_output_accepted")),
        "constrained_writer_fallback": bool(writer.get("phase3_fallback_used")),
        "hard_failures": list(dict.fromkeys(hard_failures)),
        "passed_hard_gates": not hard_failures,
        "answer": text,
    }


def summarize_records(
    records: Sequence[Mapping[str, Any]],
    *,
    selected_count: int,
    full_bank_count: int,
    category_counts_expected: Mapping[str, int],
    route_match_threshold: float = 0.90,
    identifier_recovery_threshold: float = 0.75,
    page_recovery_threshold: float = 0.70,
) -> dict[str, Any]:
    rows = [dict(row) for row in records]
    hard_failure_counts = Counter(
        failure for row in rows for failure in (row.get("hard_failures") or [])
    )
    category_counts = Counter(str(row.get("category") or "") for row in rows)
    actual_route_counts = Counter(str(row.get("actual_route") or "") for row in rows)
    expected_route_counts = Counter(str(row.get("expected_route") or "") for row in rows)
    identifier_rows = [row for row in rows if row.get("identifier_question")]
    page_rows = [row for row in rows if row.get("page_question")]
    route_matches = sum(bool(row.get("route_match")) for row in rows)
    id_recovered = sum(bool(row.get("expected_identifier_recovered")) for row in identifier_rows)
    page_recovered = sum(bool(row.get("expected_page_recovered")) for row in page_rows)
    completed = len(rows)
    full_scope = selected_count == full_bank_count == EXPECTED_TOTAL

    hard_failures: list[str] = []
    if completed != selected_count:
        hard_failures.append("selected_run_incomplete")
    if full_scope and completed != EXPECTED_TOTAL:
        hard_failures.append("full_run_incomplete")
    if hard_failure_counts:
        hard_failures.append("record_hard_failures")
    if full_scope and dict(category_counts) != dict(category_counts_expected):
        hard_failures.append("category_completion_mismatch")

    soft_failures: list[str] = []
    if rows and route_matches / len(rows) < route_match_threshold:
        soft_failures.append("route_match_below_threshold")
    if identifier_rows and id_recovered / len(identifier_rows) < identifier_recovery_threshold:
        soft_failures.append("identifier_recovery_below_threshold")
    if page_rows and page_recovered / len(page_rows) < page_recovery_threshold:
        soft_failures.append("page_recovery_below_threshold")

    quality = "FAIL" if hard_failures else ("WARN" if soft_failures else "PASS")
    latencies = [float(row.get("latency_ms") or 0.0) for row in rows]
    accepted_writer = sum(bool(row.get("constrained_writer_accepted")) for row in rows)
    fallback_writer = sum(bool(row.get("constrained_writer_fallback")) for row in rows)
    return {
        "module": MODULE,
        "status": STATUS,
        "contract_id": CONTRACT_ID,
        "quality_status": quality,
        "hard_failures": hard_failures,
        "soft_failures": soft_failures,
        "hard_failure_counts": dict(hard_failure_counts),
        "full_scope": full_scope,
        "question_count": completed,
        "selected_question_count": selected_count,
        "full_bank_question_count": full_bank_count,
        "http_200_count": sum(int(row.get("http_status") or 0) == 200 for row in rows),
        "nonempty_answer_count": sum(bool(row.get("nonempty_answer")) for row in rows),
        "route_match_count": route_matches,
        "route_match_rate": round(route_matches / completed, 6) if completed else 0.0,
        "post_validation_accepted_count": sum(bool(row.get("post_validation_accepted")) for row in rows),
        "unknown_citation_id_count": sum(bool(row.get("unknown_citation_id")) for row in rows),
        "public_contract_pass_count": sum(bool(row.get("public_contract_ok")) for row in rows),
        "public_internal_leak_count": sum(bool(row.get("public_leaks")) for row in rows),
        "public_output_anomaly_count": sum(bool(row.get("public_output_anomalies")) for row in rows),
        "required_citation_missing_count": sum(bool(row.get("required_citation_missing")) for row in rows),
        "duplicate_candidate_total": sum(int(row.get("duplicate_candidate_count") or 0) for row in rows),
        "negative_control_fabricated_count": sum(
            bool(row.get("negative_identifier_fabricated") or row.get("negative_page_fabricated")) for row in rows
        ),
        "unsafe_authority_assertion_count": sum(bool(row.get("unsafe_authority_assertion")) for row in rows),
        "latency_hard_limit_exceeded_count": sum(bool(row.get("latency_hard_limit_exceeded")) for row in rows),
        "average_latency_ms": round(sum(latencies) / len(latencies), 3) if latencies else 0.0,
        "maximum_latency_ms": round(max(latencies), 3) if latencies else 0.0,
        "identifier_question_count": len(identifier_rows),
        "expected_identifier_recovered_count": id_recovered,
        "identifier_recovery_rate": round(id_recovered / len(identifier_rows), 6) if identifier_rows else 0.0,
        "page_question_count": len(page_rows),
        "expected_page_recovered_count": page_recovered,
        "page_recovery_rate": round(page_recovered / len(page_rows), 6) if page_rows else 0.0,
        "constrained_writer_accepted_count": accepted_writer,
        "constrained_writer_fallback_count": fallback_writer,
        "maximum_constrained_calls_per_record": max(
            (int(row.get("constrained_writer_call_count") or 0) for row in rows), default=0
        ),
        "category_counts": dict(category_counts),
        "expected_route_counts": dict(expected_route_counts),
        "actual_route_counts": dict(actual_route_counts),
        "thresholds": {
            "route_match_rate": route_match_threshold,
            "identifier_recovery_rate": identifier_recovery_threshold,
            "page_recovery_rate": page_recovery_threshold,
        },
    }


def _record_path(output_dir: Path, item: Mapping[str, Any]) -> Path:
    category = re.sub(r"[^a-z0-9_]+", "_", str(item.get("category") or "unknown").lower())
    return output_dir / f"{int(item.get('ordinal') or 0):03d}_{item.get('question_id')}_{category}.json"


def _load_record(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return dict(value) if isinstance(value, Mapping) else None
    except Exception:
        return None


def _question_fingerprint(item: Mapping[str, Any]) -> str:
    blob = json.dumps(dict(item), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _existing_record_matches_question(existing: Mapping[str, Any], item: Mapping[str, Any]) -> bool:
    stored = existing.get("question") if isinstance(existing.get("question"), Mapping) else {}
    if not stored:
        return False
    return _question_fingerprint(stored) == _question_fingerprint(item)


def _regrade_existing_record(
    existing: Mapping[str, Any],
    item: Mapping[str, Any],
    *,
    latency_hard_limit_seconds: float,
) -> dict[str, Any]:
    previous = _mapping(existing.get("evaluation"))
    raw_response = _mapping(existing.get("raw_response"))
    return evaluate_record(
        item,
        raw_response,
        int(previous.get("http_status") or 0),
        float(previous.get("latency_ms") or 0.0),
        str(previous.get("transport_error") or ""),
        latency_hard_limit_seconds=latency_hard_limit_seconds,
    )


def _select_bank(bank: Sequence[Mapping[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    selected = [dict(item) for item in bank]
    categories = {value.strip() for value in args.only_categories.split(",") if value.strip()}
    ids = {value.strip() for value in args.only_ids.split(",") if value.strip()}
    if categories:
        selected = [item for item in selected if str(item.get("category")) in categories]
    if ids:
        selected = [item for item in selected if str(item.get("question_id")) in ids]
    selected = [item for item in selected if int(item.get("ordinal") or 0) >= max(1, args.start_index)]
    if args.max_questions > 0:
        selected = selected[: args.max_questions]
    return selected


def write_csv(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    fields = [
        "question_id", "ordinal", "category", "expected_route", "actual_route", "route_match",
        "http_status", "latency_ms", "nonempty_answer", "post_validation_accepted",
        "expected_identifier_recovered", "expected_page_recovered", "candidate_count",
        "citation_count", "public_contract_ok", "public_output_anomalies",
        "negative_identifier_fabricated", "negative_page_fabricated",
        "unsafe_authority_assertion", "constrained_writer_accepted",
        "constrained_writer_fallback", "passed_hard_gates", "hard_failures", "question",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in records:
            row = {key: record.get(key) for key in fields}
            row["hard_failures"] = json.dumps(row.get("hard_failures") or [])
            writer.writerow(row)


def write_markdown(path: Path, summary: Mapping[str, Any], records: Sequence[Mapping[str, Any]]) -> None:
    lines = [
        "# TRACE-Net H30 Phase 5 Grounded-100 Benchmark",
        "",
        f"Status: **{summary.get('quality_status')}**",
        "",
        f"Completed: {summary.get('question_count')}/{summary.get('selected_question_count')}",
        f"HTTP 200: {summary.get('http_200_count')}",
        f"Nonempty answers: {summary.get('nonempty_answer_count')}",
        f"Route matches: {summary.get('route_match_count')} ({summary.get('route_match_rate')})",
        f"Post-validation accepted: {summary.get('post_validation_accepted_count')}",
        f"Identifier recovery: {summary.get('expected_identifier_recovered_count')}/{summary.get('identifier_question_count')}",
        f"Page recovery: {summary.get('expected_page_recovered_count')}/{summary.get('page_question_count')}",
        f"Unknown citations: {summary.get('unknown_citation_id_count')}",
        f"Negative fabrications: {summary.get('negative_control_fabricated_count')}",
        f"Unsafe authority assertions: {summary.get('unsafe_authority_assertion_count')}",
        f"Average latency: {float(summary.get('average_latency_ms') or 0)/1000:.1f}s",
        f"Maximum latency: {float(summary.get('maximum_latency_ms') or 0)/1000:.1f}s",
        "",
        "| ID | Category | Expected → Actual | HTTP | Route | Identifier | Page | Validation | Latency | Hard failures |",
        "|---|---|---|---:|---|---|---|---|---:|---|",
    ]
    for row in records:
        lines.append(
            f"| {row.get('question_id')} | {row.get('category')} | {row.get('expected_route')} → {row.get('actual_route')} | "
            f"{row.get('http_status')} | {'✓' if row.get('route_match') else '—'} | "
            f"{'✓' if row.get('expected_identifier_recovered') else '—'} | "
            f"{'✓' if row.get('expected_page_recovered') else '—'} | "
            f"{'✓' if row.get('post_validation_accepted') else '—'} | "
            f"{float(row.get('latency_ms') or 0)/1000:.1f}s | "
            f"{', '.join(row.get('hard_failures') or []) or '—'} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    repo = Path(args.repo_root).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    truth = grounded20.truth(repo)
    bank = build_phase5_bank(truth)
    bank_validation = validate_phase5_bank(bank)
    bank_doc = bank_document(bank, truth)
    (output_dir / "question_bank.json").write_text(
        json.dumps(bank_doc, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (output_dir / "question_bank_validation.json").write_text(
        json.dumps(bank_validation, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("artifact_counts=", json.dumps(truth.get("counts") or {}, indent=2))
    print("question_bank=", output_dir / "question_bank.json")
    print("question_bank_sha256=", bank_validation.get("bank_sha256"))
    if args.bank_only:
        print("quality_status=PASS")
        return 0

    selected = _select_bank(bank, args)
    if not selected:
        raise SystemExit("no_questions_selected")
    selected_ids = [str(item.get("question_id")) for item in selected]
    (output_dir / "selected_scope.json").write_text(
        json.dumps({
            "contract_id": CONTRACT_ID,
            "selected_question_count": len(selected),
            "full_bank_question_count": len(bank),
            "selected_question_ids": selected_ids,
            "resume": bool(args.resume),
            "rerun_failed": bool(args.rerun_failed),
        }, indent=2),
        encoding="utf-8",
    )

    records: list[dict[str, Any]] = []
    for run_index, item in enumerate(selected, 1):
        path = _record_path(output_dir, item)
        existing = _load_record(path) if path.exists() else None
        if existing and (args.resume or args.rerun_failed):
            question_matches = _existing_record_matches_question(existing, item)
            if question_matches:
                evaluation = _regrade_existing_record(
                    existing, item,
                    latency_hard_limit_seconds=args.latency_hard_limit,
                )
                refreshed_record = dict(existing)
                refreshed_record["question"] = dict(item)
                refreshed_record["question_fingerprint"] = _question_fingerprint(item)
                refreshed_record["evaluation"] = evaluation
                path.write_text(
                    json.dumps(refreshed_record, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                should_skip = bool(args.resume)
                if args.rerun_failed:
                    should_skip = bool(evaluation.get("passed_hard_gates"))
                if should_skip:
                    records.append(evaluation)
                    print("=" * 100)
                    print(
                        f"[{run_index:03d}/{len(selected):03d}] {item['question_id']} "
                        f"{item['category']} REGRADED-SKIP"
                    )
                    continue
            else:
                print("=" * 100)
                print(
                    f"[{run_index:03d}/{len(selected):03d}] {item['question_id']} "
                    f"{item['category']} STALE-QUESTION-RERUN"
                )

        print("=" * 100)
        print(f"[{run_index:03d}/{len(selected):03d}] {item['question_id']} {item['category']}")
        print(item["question"])
        started = time.perf_counter()
        status, payload, error = grounded20.call(
            args.base_url, args.api_key, args.model, str(item["question"]), args.request_timeout
        )
        latency_ms = (time.perf_counter() - started) * 1000.0
        evaluation = evaluate_record(
            item, payload, status, latency_ms, error,
            latency_hard_limit_seconds=args.latency_hard_limit,
        )
        record = {
            "module": MODULE,
            "status": STATUS,
            "contract_id": CONTRACT_ID,
            "question": item,
            "question_fingerprint": _question_fingerprint(item),
            "evaluation": evaluation,
            "raw_response": payload,
        }
        path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
        records.append(evaluation)
        print(
            f"http={status} route={evaluation['actual_route']} expected={evaluation['expected_route']} "
            f"latency={latency_ms/1000:.1f}s validation={evaluation['post_validation_accepted']} "
            f"hard_failures={evaluation['hard_failures']}"
        )
        print("answer:", " ".join(str(evaluation.get("answer") or "").split())[:500] or "<EMPTY>")
        if args.stop_on_hard_failure and evaluation["hard_failures"]:
            print("stop_on_hard_failure=TRIGGERED")
            break

    records.sort(key=lambda row: int(row.get("ordinal") or 0))
    summary = summarize_records(
        records,
        selected_count=len(selected),
        full_bank_count=len(bank),
        category_counts_expected=dict(bank_validation.get("category_counts") or {}),
    )
    summary_doc = {
        "module": MODULE,
        "status": STATUS,
        "contract_id": CONTRACT_ID,
        "quality_status": summary["quality_status"],
        "summary": summary,
        "records": records,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary_doc, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    write_csv(output_dir / "results.csv", records)
    write_markdown(output_dir / "report.md", summary, records)
    failures = [row for row in records if row.get("hard_failures") or not row.get("route_match")]
    (output_dir / "failures.json").write_text(
        json.dumps({"count": len(failures), "records": failures}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print("=" * 100)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print("report=", output_dir / "report.md")
    print("summary=", output_dir / "summary.json")
    print("results_csv=", output_dir / "results.csv")
    return 1 if args.strict and summary.get("quality_status") != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
