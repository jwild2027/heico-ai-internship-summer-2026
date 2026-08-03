from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

VERSION = "v30"
MODULE = "trace_net_e2e_relationship_final_gate_hardener_v30"
STATUS_READY = "E2E_RELATIONSHIP_FINAL_GATE_HARDENER_READY"
STATUS_NEEDS_REPAIR = "E2E_RELATIONSHIP_FINAL_GATE_HARDENER_NEEDS_REPAIR"

SAFETY_CONTRACT = {
    "answer_permission": False,
    "can_answer_directly": False,
    "can_prove_claims": False,
    "source_truth_mutation_allowed": False,
    "writes_to_postgres": False,
    "writes_to_qdrant": False,
    "writes_to_opensearch": False,
    "uploads_to_opensearch": False,
    "raw_5tb_scan_at_query_time": False,
    "graph_rebuild_at_query_time": False,
    "relationship_final_gate_required": True,
}

UNSUPPORTED_RELATIONSHIP_PATTERNS = [
    re.compile(r"\b(leiden|community|graph)\s+(proves|confirms|establishes|demonstrates)\b", re.I),
    re.compile(r"\b(v2 summary|summary guidance)\s+(proves|confirms|establishes|demonstrates)\b", re.I),
    re.compile(r"\b(nomenclature|nomeclature)\s+(proves|confirms|establishes|demonstrates|means)\b", re.I),
    re.compile(r"\btherefore\b.*\b(related|relationship|used in|applies to|belongs to)\b", re.I),
]

GUIDANCE_SAFE_PATTERNS = [
    re.compile(r"guidance only", re.I),
    re.compile(r"not proof", re.I),
    re.compile(r"requires source[- ]truth confirmation", re.I),
    re.compile(r"confirm .*source[- ]truth", re.I),
]


def _now_ms() -> float:
    return time.perf_counter() * 1000.0


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _compact(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _extract_samples(source_report: Dict[str, Any]) -> List[Dict[str, Any]]:
    samples = (
        source_report.get("sample_records")
        or source_report.get("samples")
        or source_report.get("eval_records")
        or source_report.get("records")
        or []
    )
    if isinstance(samples, list):
        return [r for r in samples if isinstance(r, dict)]
    return []


def _answer_from_record(record: Dict[str, Any]) -> str:
    # Different earlier modules used different keys. This keeps v30 compatible.
    choice_answer = ""
    choices = record.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
        choice_answer = message.get("content") or ""
    return _compact(
        record.get("final_answer")
        or record.get("answer")
        or record.get("content")
        or record.get("preview")
        or choice_answer
        or ""
    )


def _query_from_record(record: Dict[str, Any]) -> str:
    return _compact(record.get("user_query") or record.get("query") or record.get("input") or "")


def _is_relationship_record(record: Dict[str, Any], query: str) -> bool:
    if record.get("relationship_query") is True:
        return True
    mode = str(record.get("response_mode") or "").lower()
    if "relationship" in mode:
        return True
    q = query.lower()
    return any(token in q for token in ["related", "relationship", "same leiden", "same community", "graph neighbor", "graph neighbours", "connect", "connection", "relates to"])


def _is_guidance_safe(text: str) -> bool:
    return any(p.search(text) for p in GUIDANCE_SAFE_PATTERNS)


def detect_relationship_gate_issues(record: Dict[str, Any], draft_text: Optional[str] = None) -> Dict[str, Any]:
    query = _query_from_record(record)
    text = _compact(draft_text if draft_text is not None else _answer_from_record(record))
    lower = text.lower()
    is_relationship = _is_relationship_record(record, query)

    graph_as_proof = bool(re.search(r"\b(leiden|community|graph)\s+(proves|confirms|establishes|demonstrates)\b", text, re.I))
    summary_as_proof = bool(re.search(r"\b(v2 summary|summary guidance)\s+(proves|confirms|establishes|demonstrates)\b", text, re.I))
    nomenclature_as_proof = bool(re.search(r"\b(nomenclature|nomeclature)\s+(proves|confirms|establishes|demonstrates|means)\b", text, re.I))

    unsupported_relationship_claim = False
    unsupported_patterns = []
    for pattern in UNSUPPORTED_RELATIONSHIP_PATTERNS:
        if pattern.search(text):
            unsupported_relationship_claim = True
            unsupported_patterns.append(pattern.pattern)

    # If a relationship answer has strong relationship wording but no guidance-only qualifier, force repair.
    if is_relationship and re.search(r"\b(related to|relates to|relationship|connected to|same community|graph neighbors?)\b", lower):
        if not _is_guidance_safe(text):
            unsupported_relationship_claim = True
            unsupported_patterns.append("relationship_claim_without_guidance_only_disclaimer")

    issue_count = sum([
        graph_as_proof,
        summary_as_proof,
        nomenclature_as_proof,
        unsupported_relationship_claim,
    ])

    return {
        "is_relationship_record": is_relationship,
        "graph_as_proof_violation": graph_as_proof,
        "v2_summary_as_proof_violation": summary_as_proof,
        "nomenclature_as_proof_violation": nomenclature_as_proof,
        "unsupported_relationship_claim": unsupported_relationship_claim,
        "unsupported_relationship_patterns": unsupported_patterns,
        "relationship_gate_issue_count": issue_count,
    }


def _safe_relationship_answer(record: Dict[str, Any], original_answer: str) -> str:
    query = _query_from_record(record)
    pages: List[str] = []

    for key in ["candidate_page_ids", "related_candidate_page_ids", "pages", "page_ids"]:
        value = record.get(key)
        if isinstance(value, list):
            pages.extend(str(v) for v in value if v)

    # Pull page IDs from existing text too.
    pages.extend(re.findall(r"t_p_\d+_\d+_p\d{6}", original_answer))
    pages = list(dict.fromkeys(pages))[:8]

    source_hint = ""
    if pages:
        source_hint = " Candidate page(s) for inspection include " + ", ".join(pages) + "."

    if "same leiden" in query.lower() or "same community" in query.lower():
        return (
            "TRACE-Net found graph/Leiden navigation guidance for this request. "
            f"{source_hint.strip()} Graph/Leiden output is guidance only, not proof. "
            "Do not treat community membership as a factual part/manual relationship unless direct source-truth evidence confirms it."
        ).strip()

    if "nomenclature" in query.lower() or "nomeclature" in query.lower():
        return (
            "TRACE-Net found nomenclature metadata/navigation signals for this request. "
            f"{source_hint.strip()} Nomenclature graph signals are guidance only, not proof of a factual part/manual relationship. "
            "Direct source-truth evidence is required before making a relationship claim."
        ).strip()

    if original_answer:
        # Preserve safe existing answer when possible, then append the hard gate rule.
        if _is_guidance_safe(original_answer):
            return original_answer

    return (
        "TRACE-Net found relationship/navigation guidance, but the available graph, Leiden, v2 summary, "
        "or nomenclature metadata is not proof authority. No factual relationship claim is made unless direct "
        "source-truth evidence supports it."
    )


def final_gate_record(record: Dict[str, Any], *, record_id: str) -> Dict[str, Any]:
    t0 = _now_ms()
    query = _query_from_record(record)
    original_answer = _answer_from_record(record)
    issues = detect_relationship_gate_issues(record, original_answer)
    repaired = False
    final_answer = original_answer

    if issues["relationship_gate_issue_count"] > 0:
        final_answer = _safe_relationship_answer(record, original_answer)
        repaired = True

    final_status = "RELATIONSHIP_FINAL_GATE_PASS"
    final_issues = detect_relationship_gate_issues(record, final_answer)
    if final_issues["relationship_gate_issue_count"] > 0:
        final_status = "RELATIONSHIP_FINAL_GATE_NEEDS_REPAIR"

    return {
        "relationship_final_gate_id": record_id,
        "user_query": query,
        "source_response_mode": record.get("response_mode"),
        "source_final_gate_status": record.get("final_gate_status"),
        "relationship_record": issues["is_relationship_record"],
        "final_gate_status": final_status,
        "repaired_from_draft": repaired,
        "original_answer_preview": original_answer[:500],
        "final_answer": final_answer,
        "graph_as_proof_violation_detected": issues["graph_as_proof_violation"],
        "v2_summary_as_proof_violation_detected": issues["v2_summary_as_proof_violation"],
        "nomenclature_as_proof_violation_detected": issues["nomenclature_as_proof_violation"],
        "unsupported_relationship_claim_detected": issues["unsupported_relationship_claim"],
        "post_gate_issue_count": final_issues["relationship_gate_issue_count"],
        "relationship_guidance_only_enforced": issues["is_relationship_record"],
        "source_truth_required_for_relationship_claims": True,
        "safety_contract": SAFETY_CONTRACT,
        "latency_ms": round(_now_ms() - t0, 3),
    }


def _synthetic_violation_records() -> List[Dict[str, Any]]:
    return [
        {
            "user_query": "Explain how part number 120-36833-503 relates to manual reference 25-21-00",
            "response_mode": "relationship_synthesis",
            "relationship_query": True,
            "final_answer": "The Leiden community proves that part number 120-36833-503 is related to manual reference 25-21-00.",
        },
        {
            "user_query": "What does the nomenclature mean for this part relationship?",
            "response_mode": "relationship_synthesis",
            "relationship_query": True,
            "final_answer": "The nomenclature means this part belongs to the manual relationship and confirms the connection.",
        },
        {
            "user_query": "Does the v2 summary prove page t_p_120_1176_p000003 is related?",
            "response_mode": "relationship_synthesis",
            "relationship_query": True,
            "final_answer": "The V2 summary confirms the relationship between the page and the part.",
        },
    ]


def _quality_check(name: str, observed: Any, op: str, expected: Any) -> Dict[str, Any]:
    if op == ">=":
        passed = observed >= expected
    elif op == "<=":
        passed = observed <= expected
    elif op == "==":
        passed = observed == expected
    elif op == "is":
        passed = observed is expected
    else:
        raise ValueError(f"Unsupported op {op}")
    return {"name": name, "observed": observed, "op": op, "expected": expected, "passed": bool(passed)}


def _write_inspect_md(path: Path, report: Dict[str, Any], records: List[Dict[str, Any]]) -> None:
    lines = [
        "# TRACE-Net E2E Relationship Final Gate Hardener v30",
        "",
        f"Quality status: **{report['quality_status']}**",
        f"Status: `{report['status']}`",
        "",
        "## Summary",
    ]
    for key in [
        "relationship_final_gate_count",
        "passed_relationship_final_gate_count",
        "relationship_record_count",
        "repaired_relationship_answer_count",
        "graph_as_proof_violation_count",
        "v2_summary_as_proof_violation_count",
        "nomenclature_as_proof_violation_count",
        "unsupported_relationship_claim_count",
        "post_gate_issue_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
    ]:
        lines.append(f"- {key}: {report.get(key)}")

    lines.extend([
        "",
        "## Contract",
        "- Graph, Leiden, v2 summaries, and nomenclature metadata are guidance only.",
        "- Relationship/synthesis answers may use guidance for navigation, but not as proof authority.",
        "- Direct source-truth evidence is required for factual relationship claims.",
        "- This gate validates and repairs relationship drafts; it does not call an LLM.",
        "",
        "## Final gate records",
    ])

    for r in records[:12]:
        lines.extend([
            f"### {r['relationship_final_gate_id']} — `{r['final_gate_status']}`",
            f"- query: {r.get('user_query')}",
            f"- relationship_record: {r.get('relationship_record')}",
            f"- repaired_from_draft: {r.get('repaired_from_draft')}",
            f"- graph_as_proof_violation: {r.get('graph_as_proof_violation_detected')}",
            f"- v2_summary_as_proof_violation: {r.get('v2_summary_as_proof_violation_detected')}",
            f"- nomenclature_as_proof_violation: {r.get('nomenclature_as_proof_violation_detected')}",
            f"- unsupported_relationship_claim: {r.get('unsupported_relationship_claim_detected')}",
            f"- final_answer_preview: {r.get('final_answer', '')[:240]}",
            "",
        ])

    lines.extend(["## Quality checks"])
    for check in report.get("quality_checks", []):
        status = "PASS" if check["passed"] else "FAIL"
        lines.append(
            f"- {status} {check['name']}: observed={check['observed']} expected={check['op']} {check['expected']}"
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_report(
    *,
    relationship_router_hardening: Path,
    output_dir: Path,
    include_synthetic_violations: bool = True,
    min_relationship_final_gates: int = 0,
    min_passed_relationship_final_gates: int = 0,
    min_repaired_relationship_answers: int = 0,
    min_relationship_records: int = 0,
    max_post_gate_issue_count: int = 0,
    max_answer_permission_count: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    require_no_answer_permission: bool = False,
    quality: bool = False,
) -> Dict[str, Any]:
    source_report = _read_json(relationship_router_hardening)
    source_samples = _extract_samples(source_report)

    # Add synthetic bad drafts so the gate proves it can catch and repair the high-risk classes.
    all_inputs = list(source_samples)
    if include_synthetic_violations:
        all_inputs.extend(_synthetic_violation_records())

    if not all_inputs:
        all_inputs = _synthetic_violation_records()

    records = [
        final_gate_record(record, record_id=f"relationship_final_gate_v30_{idx:04d}")
        for idx, record in enumerate(all_inputs, 1)
    ]

    relationship_record_count = sum(1 for r in records if r["relationship_record"])
    passed_count = sum(1 for r in records if r["final_gate_status"] == "RELATIONSHIP_FINAL_GATE_PASS")
    repaired_count = sum(1 for r in records if r["repaired_from_draft"])
    graph_violation_count = sum(1 for r in records if r["graph_as_proof_violation_detected"])
    summary_violation_count = sum(1 for r in records if r["v2_summary_as_proof_violation_detected"])
    nomenclature_violation_count = sum(1 for r in records if r["nomenclature_as_proof_violation_detected"])
    unsupported_count = sum(1 for r in records if r["unsupported_relationship_claim_detected"])
    post_gate_issue_count = sum(int(r["post_gate_issue_count"]) for r in records)

    answer_permission_count = 0
    source_truth_mutation_allowed_count = 0

    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "trace_net_e2e_relationship_final_gate_hardener_v30.json"
    records_jsonl_path = output_dir / "trace_net_e2e_relationship_final_gate_hardener_records_v30.jsonl"
    inspect_md_path = output_dir / "trace_net_e2e_relationship_final_gate_hardener_v30.md"

    quality_checks = [
        _quality_check("relationship_final_gate_count", len(records), ">=", min_relationship_final_gates),
        _quality_check("passed_relationship_final_gate_count", passed_count, ">=", min_passed_relationship_final_gates),
        _quality_check("relationship_record_count", relationship_record_count, ">=", min_relationship_records),
        _quality_check("repaired_relationship_answer_count", repaired_count, ">=", min_repaired_relationship_answers),
        _quality_check("post_gate_issue_count", post_gate_issue_count, "<=", max_post_gate_issue_count),
        _quality_check("answer_permission_count", answer_permission_count, "<=", max_answer_permission_count),
        _quality_check("source_truth_mutation_allowed_count", source_truth_mutation_allowed_count, "<=", max_source_truth_mutation_allowed),
    ]
    if require_no_answer_permission:
        quality_checks.append(_quality_check("require_no_answer_permission", answer_permission_count, "==", 0))

    quality_status = "PASS" if all(c["passed"] for c in quality_checks) else "FAIL"
    status = STATUS_READY if quality_status == "PASS" else STATUS_NEEDS_REPAIR

    report = {
        "module": MODULE,
        "version": VERSION,
        "status": status,
        "quality_status": quality_status,
        "relationship_router_hardening_path": str(relationship_router_hardening),
        "relationship_final_gate_count": len(records),
        "passed_relationship_final_gate_count": passed_count,
        "relationship_record_count": relationship_record_count,
        "repaired_relationship_answer_count": repaired_count,
        "graph_as_proof_violation_count": graph_violation_count,
        "v2_summary_as_proof_violation_count": summary_violation_count,
        "nomenclature_as_proof_violation_count": nomenclature_violation_count,
        "unsupported_relationship_claim_count": unsupported_count,
        "post_gate_issue_count": post_gate_issue_count,
        "answer_permission_count": answer_permission_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "contract": {
            **SAFETY_CONTRACT,
            "llm_called": False,
            "graph_leiden_guidance_only": True,
            "v2_summaries_guidance_only": True,
            "nomenclature_metadata_guidance_only": True,
            "source_truth_required_for_relationship_claims": True,
            "repairs_unsafe_relationship_drafts": True,
        },
        "quality_checks": quality_checks,
        "relationship_final_gate_records": records,
        "report_path": str(report_path),
        "records_jsonl_path": str(records_jsonl_path),
        "inspect_md_path": str(inspect_md_path),
    }

    _write_json(report_path, report)
    _write_jsonl(records_jsonl_path, records)
    _write_inspect_md(inspect_md_path, report, records)
    return report


def check_report(
    *,
    report_path: Path,
    min_relationship_final_gates: int = 0,
    min_passed_relationship_final_gates: int = 0,
    min_repaired_relationship_answers: int = 0,
    min_relationship_records: int = 0,
    max_post_gate_issue_count: int = 0,
    max_answer_permission_count: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    require_no_answer_permission: bool = False,
    write_json: bool = False,
) -> Dict[str, Any]:
    report = _read_json(report_path)
    checks = [
        _quality_check("quality_status", report.get("quality_status"), "==", "PASS"),
        _quality_check("relationship_final_gate_count", report.get("relationship_final_gate_count", 0), ">=", min_relationship_final_gates),
        _quality_check("passed_relationship_final_gate_count", report.get("passed_relationship_final_gate_count", 0), ">=", min_passed_relationship_final_gates),
        _quality_check("relationship_record_count", report.get("relationship_record_count", 0), ">=", min_relationship_records),
        _quality_check("repaired_relationship_answer_count", report.get("repaired_relationship_answer_count", 0), ">=", min_repaired_relationship_answers),
        _quality_check("post_gate_issue_count", report.get("post_gate_issue_count", 0), "<=", max_post_gate_issue_count),
        _quality_check("answer_permission_count", report.get("answer_permission_count", 0), "<=", max_answer_permission_count),
        _quality_check("source_truth_mutation_allowed_count", report.get("source_truth_mutation_allowed_count", 0), "<=", max_source_truth_mutation_allowed),
    ]
    if require_no_answer_permission:
        checks.append(_quality_check("require_no_answer_permission", report.get("answer_permission_count", 0), "==", 0))

    checked = dict(report)
    checked["quality_checks"] = checks
    checked["quality_status"] = "PASS" if all(c["passed"] for c in checks) else "FAIL"
    if write_json:
        _write_json(report_path, checked)
    return checked
