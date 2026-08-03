"""TRACE-Net Engineering Engram Self-RAG Critic v1.

Artifact-only critic for targeted Engram overlay answer-smoke runs.
It reads an answer-smoke manifest and emits per-answer Self-RAG style critic
records. It does not call an LLM and does not write to databases or vector/search
systems.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

MODULE = "trace_net_engineering_engram_self_rag_critic_v1"
VERSION = "v1"

EXPECTED_UNKNOWN_CATEGORIES = {"unknown_part", "unknown_figure"}
CITATION_RE = re.compile(r"\[[A-Za-z][A-Za-z0-9_\-]*\]")
GROUPED_CITATION_RE = re.compile(r"\[[A-Za-z][A-Za-z0-9_\-]*\s*,\s*[A-Za-z]")


def _read_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8"))


def _write_json(path: str | Path, data: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def _text(record: Mapping[str, Any]) -> str:
    return str(record.get("answer_text") or record.get("answer_preview") or "")


def _is_expected_unknown_boundary(record: Mapping[str, Any]) -> bool:
    category = str(record.get("category") or "")
    proof_context_count = _as_int(record.get("proof_context_count"))
    answer = _text(record).lower()
    return (
        category in EXPECTED_UNKNOWN_CATEGORIES
        and proof_context_count == 0
        and ("not found" in answer or "not source-trace-ready" in answer or "no proof_context" in answer)
    )


def _has_required_sections(answer: str) -> bool:
    lower = answer.lower()
    return all(token in lower for token in ("answer", "evidence", "engineering confidence", "limits"))


def _safe_but_generic_risk(record: Mapping[str, Any]) -> bool:
    answer = _text(record).lower()
    proof_context_count = _as_int(record.get("proof_context_count"))
    grade = str(record.get("grade") or "")
    if grade == "GOOD":
        return False
    if _is_expected_unknown_boundary(record):
        return False
    generic_markers = ["not proven", "cannot prove", "not source-trace-ready"]
    return proof_context_count > 0 and any(marker in answer for marker in generic_markers) and len(answer) < 900


def critique_answer_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Return a Self-RAG style critic record for one answer-smoke record."""
    answer = _text(record)
    grade = str(record.get("grade") or "")
    category = str(record.get("category") or "")
    question_id = str(record.get("question_id") or "")
    proof_context_count = _as_int(record.get("proof_context_count"))
    answer_citation_count = _as_int(record.get("answer_citation_count"))
    valid_answer_citation_count = _as_int(record.get("valid_answer_citation_count"))
    source_trace_ready_citation_count = _as_int(record.get("source_trace_ready_citation_count"))
    unsupported_claim_count = _as_int(record.get("unsupported_claim_count"))
    summary_used_as_proof_count = _as_int(record.get("summary_used_as_proof_count"))
    invalid_answer_citation_count = _as_int(record.get("invalid_answer_citation_count"))
    answer_permission = bool(record.get("answer_permission") or record.get("can_answer_directly"))
    unsafe = bool(record.get("unsafe") or answer_permission)

    findings: list[str] = []
    repair_hints: list[str] = []
    critic_status = "PASS"

    if answer_permission:
        findings.append("answer_permission_detected")
        repair_hints.append("Remove any direct-answer permission granted by Engram or prompt guidance.")
        unsafe = True

    if unsupported_claim_count > 0:
        findings.append("unsupported_claims_detected")
        repair_hints.append("Regenerate with stricter proof_context citation requirements.")
        critic_status = "REPAIR_RECOMMENDED"

    if summary_used_as_proof_count > 0:
        findings.append("summary_used_as_proof_detected")
        repair_hints.append("Rewrite so summaries are guidance only and factual claims cite proof_context.")
        critic_status = "REPAIR_RECOMMENDED"

    if invalid_answer_citation_count > 0:
        findings.append("invalid_citations_detected")
        repair_hints.append("Replace invalid labels with source-trace-ready citations only.")
        critic_status = "REPAIR_RECOMMENDED"

    if GROUPED_CITATION_RE.search(answer):
        findings.append("grouped_citation_syntax_risk")
        repair_hints.append("Use individual citation labels such as [V6] [O1], not grouped labels like [V6, O1].")

    if proof_context_count > 0 and answer_citation_count == 0:
        findings.append("proof_context_available_but_no_counted_citations")
        repair_hints.append("Add counted source labels from proof_context using individual bracket syntax.")
        critic_status = "REPAIR_RECOMMENDED"

    if proof_context_count > 0 and valid_answer_citation_count == 0:
        findings.append("no_valid_citations_despite_proof_context")
        repair_hints.append("Regenerate with explicit valid citation labels from proof_context.")
        critic_status = "REPAIR_RECOMMENDED"

    if proof_context_count > 0 and source_trace_ready_citation_count == 0:
        findings.append("no_source_trace_ready_citations_despite_proof_context")
        repair_hints.append("Prefer source-trace-ready citation labels from proof_context.")
        critic_status = "REPAIR_RECOMMENDED"

    if not _has_required_sections(answer):
        findings.append("missing_preferred_answer_sections")
        repair_hints.append("Use Answer, Evidence, Engineering confidence, and Limits sections.")
        if grade != "GOOD" and not _is_expected_unknown_boundary(record):
            critic_status = "REPAIR_RECOMMENDED"

    if _safe_but_generic_risk(record):
        findings.append("safe_but_too_generic_risk")
        repair_hints.append("Retrieve critic/episodic repair memory and explain what TRACE-Net can prove, not just what it cannot prove.")
        critic_status = "REPAIR_RECOMMENDED"

    expected_partial = _is_expected_unknown_boundary(record)
    if grade == "PARTIAL" and expected_partial:
        findings.append("expected_unknown_boundary_partial")
        repair_hints.append("No repair required if unknown/no-proof cases remain safe and clearly not source-trace-ready.")
        if critic_status != "REPAIR_RECOMMENDED":
            critic_status = "EXPECTED_BOUNDARY"
    elif grade not in {"GOOD", "PARTIAL"}:
        findings.append("bad_or_blocked_answer_grade")
        repair_hints.append("Run CRAG-style repair before accepting this answer.")
        critic_status = "REPAIR_RECOMMENDED"
    elif grade == "PARTIAL" and critic_status == "PASS":
        findings.append("unexpected_partial_answer")
        repair_hints.append("Review for missing citations, incomplete answer, or over-generic refusal.")
        critic_status = "REVIEW"

    if unsafe:
        critic_status = "REPAIR_RECOMMENDED"

    if not findings:
        findings.append("critic_checks_passed")

    return {
        "module": MODULE,
        "version": VERSION,
        "question_id": question_id,
        "category": category,
        "task_type": record.get("task_type"),
        "question": record.get("question"),
        "source_grade": grade,
        "critic_status": critic_status,
        "expected_unknown_boundary_partial": expected_partial,
        "proof_context_count": proof_context_count,
        "answer_citation_count": answer_citation_count,
        "valid_answer_citation_count": valid_answer_citation_count,
        "source_trace_ready_citation_count": source_trace_ready_citation_count,
        "unsupported_claim_count": unsupported_claim_count,
        "summary_used_as_proof_count": summary_used_as_proof_count,
        "invalid_answer_citation_count": invalid_answer_citation_count,
        "llm_retry_used": bool(record.get("llm_retry_used")),
        "llm_fallback_used": bool(record.get("llm_fallback_used")),
        "findings": findings,
        "repair_hints": repair_hints,
        "unsafe": unsafe,
        "answer_permission": answer_permission,
        "source_truth_mutation_allowed": False,
        "postgres_write_attempt": False,
        "qdrant_write_attempt": False,
        "opensearch_write_attempt": False,
        "opensearch_upload_attempt": False,
        "write_attempt": False,
        "answer_preview": answer[:1200],
    }


def build_self_rag_critic_manifest(
    *,
    answer_smoke: str | Path,
    output_dir: str | Path,
    min_records: int = 1,
    min_critic_pass_or_expected: int = 1,
    max_repair_recommended: int = 0,
    max_unsafe: int = 0,
    max_write_attempts: int = 0,
    require_source_quality_pass: bool = False,
    require_no_answer_permission: bool = False,
) -> dict[str, Any]:
    source = _read_json(answer_smoke)
    records = list(source.get("records") or source.get("smoke_records") or [])
    critic_records = [critique_answer_record(r) for r in records]

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = out_dir / "trace_net_engineering_engram_self_rag_critic_v1_records.jsonl"
    check_path = out_dir / "trace_net_engineering_engram_self_rag_critic_v1_quality_check.json"
    manifest_path = out_dir / "trace_net_engineering_engram_self_rag_critic_v1.json"
    _write_jsonl(jsonl_path, critic_records)

    pass_count = sum(1 for r in critic_records if r["critic_status"] == "PASS")
    expected_count = sum(1 for r in critic_records if r["critic_status"] == "EXPECTED_BOUNDARY")
    review_count = sum(1 for r in critic_records if r["critic_status"] == "REVIEW")
    repair_count = sum(1 for r in critic_records if r["critic_status"] == "REPAIR_RECOMMENDED")
    unsafe_count = sum(1 for r in critic_records if r.get("unsafe"))
    answer_permission_count = sum(1 for r in critic_records if r.get("answer_permission"))
    write_attempt_count = sum(1 for r in critic_records if r.get("write_attempt"))

    quality_failures: list[str] = []
    source_quality_status = source.get("quality_status")
    if require_source_quality_pass and source_quality_status != "PASS":
        quality_failures.append("source_answer_smoke_quality_status_not_pass")
    if len(critic_records) < min_records:
        quality_failures.append(f"critic_record_count_below_min:{len(critic_records)}<{min_records}")
    if pass_count + expected_count < min_critic_pass_or_expected:
        quality_failures.append(f"critic_pass_or_expected_count_below_min:{pass_count + expected_count}<{min_critic_pass_or_expected}")
    if repair_count > max_repair_recommended:
        quality_failures.append(f"repair_recommended_count_above_max:{repair_count}>{max_repair_recommended}")
    if unsafe_count > max_unsafe:
        quality_failures.append(f"unsafe_finding_count_above_max:{unsafe_count}>{max_unsafe}")
    if write_attempt_count > max_write_attempts:
        quality_failures.append(f"write_attempt_count_above_max:{write_attempt_count}>{max_write_attempts}")
    if require_no_answer_permission and answer_permission_count:
        quality_failures.append("answer_permission_detected")

    summary = {
        "module": MODULE,
        "version": VERSION,
        "source_answer_smoke_quality_status": source_quality_status,
        "critic_record_count": len(critic_records),
        "critic_pass_count": pass_count,
        "expected_boundary_count": expected_count,
        "review_count": review_count,
        "repair_recommended_count": repair_count,
        "critic_pass_or_expected_count": pass_count + expected_count,
        "unsafe_finding_count": unsafe_count,
        "answer_permission_count": answer_permission_count,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "opensearch_upload_attempt_count": 0,
        "write_attempt_count": write_attempt_count,
        "ready_for_crag_engram_repair": repair_count > 0 or review_count > 0,
        "ready_for_answer_smoke_overlay_commit_gate": not quality_failures,
        "quality_failures": quality_failures,
    }

    manifest = {
        "module": MODULE,
        "version": VERSION,
        "status": "TRACE_NET_ENGINEERING_ENGRAM_SELF_RAG_CRITIC_BUILT",
        "quality_status": "PASS" if not quality_failures else "FAIL",
        "source_answer_smoke_path": str(answer_smoke),
        "summary": summary,
        "critic_policy": {
            "mode": "artifact_only_self_rag_engram_critic",
            "proof_boundary": "The critic may identify behavior/citation/evidence weaknesses but cannot create proof; factual manual claims still require proof_context citations.",
            "forbidden": [
                "answer_permission_from_critic",
                "source_truth_mutation_from_critic",
                "summary_or_engram_used_as_proof",
                "live_db_or_qdrant_io_without_explicit_gate",
            ],
            "next_patch": "CRAG Engram repair only for REVIEW or REPAIR_RECOMMENDED records.",
        },
        "critic_records": critic_records,
        "artifact_paths": {
            "records_jsonl": str(jsonl_path),
            "quality_check": str(check_path),
            "manifest": str(manifest_path),
        },
    }

    _write_json(manifest_path, manifest)
    _write_json(check_path, {
        "status": "TRACE_NET_ENGINEERING_ENGRAM_SELF_RAG_CRITIC_CHECKED",
        "quality_status": manifest["quality_status"],
        "summary": summary,
    })
    return manifest


def check_self_rag_critic_manifest(
    *,
    critic: str | Path,
    min_records: int = 1,
    min_critic_pass_or_expected: int = 1,
    require_quality_pass: bool = False,
    require_no_answer_permission: bool = False,
    max_repair_recommended: int = 0,
    max_unsafe: int = 0,
    max_write_attempts: int = 0,
) -> dict[str, Any]:
    data = _read_json(critic)
    summary = dict(data.get("summary") or {})
    quality_failures = list(summary.get("quality_failures") or [])

    if require_quality_pass and data.get("quality_status") != "PASS":
        quality_failures.append("quality_status_not_pass")
    if _as_int(summary.get("critic_record_count")) < min_records:
        quality_failures.append("critic_record_count_below_min")
    if _as_int(summary.get("critic_pass_or_expected_count")) < min_critic_pass_or_expected:
        quality_failures.append("critic_pass_or_expected_count_below_min")
    if _as_int(summary.get("repair_recommended_count")) > max_repair_recommended:
        quality_failures.append("repair_recommended_count_above_max")
    if _as_int(summary.get("unsafe_finding_count")) > max_unsafe:
        quality_failures.append("unsafe_finding_count_above_max")
    if _as_int(summary.get("write_attempt_count")) > max_write_attempts:
        quality_failures.append("write_attempt_count_above_max")
    if require_no_answer_permission and _as_int(summary.get("answer_permission_count")):
        quality_failures.append("answer_permission_detected")

    return {
        "status": "TRACE_NET_ENGINEERING_ENGRAM_SELF_RAG_CRITIC_CHECKED",
        "quality_status": "PASS" if not quality_failures else "FAIL",
        "summary": summary,
        "quality_failures": quality_failures,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=MODULE)
    parser.add_argument("--answer-smoke", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--min-records", type=int, default=1)
    parser.add_argument("--min-critic-pass-or-expected", type=int, default=1)
    parser.add_argument("--max-repair-recommended", type=int, default=0)
    parser.add_argument("--max-unsafe", type=int, default=0)
    parser.add_argument("--max-write-attempts", type=int, default=0)
    parser.add_argument("--require-source-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    return parser


def check_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=MODULE + " checker")
    parser.add_argument("--critic", required=True)
    parser.add_argument("--min-records", type=int, default=1)
    parser.add_argument("--min-critic-pass-or-expected", type=int, default=1)
    parser.add_argument("--max-repair-recommended", type=int, default=0)
    parser.add_argument("--max-unsafe", type=int, default=0)
    parser.add_argument("--max-write-attempts", type=int, default=0)
    parser.add_argument("--require-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    manifest = build_self_rag_critic_manifest(**vars(args))
    s = manifest["summary"]
    print("status=" + manifest["status"])
    print("quality_status=" + manifest["quality_status"])
    print("critic_record_count=" + str(s["critic_record_count"]))
    print("critic_pass_count=" + str(s["critic_pass_count"]))
    print("expected_boundary_count=" + str(s["expected_boundary_count"]))
    print("review_count=" + str(s["review_count"]))
    print("repair_recommended_count=" + str(s["repair_recommended_count"]))
    print("unsafe_finding_count=" + str(s["unsafe_finding_count"]))
    print("answer_permission_count=" + str(s["answer_permission_count"]))
    print("write_attempt_count=" + str(s["write_attempt_count"]))
    print("output=" + manifest["artifact_paths"]["manifest"])
    return 0 if manifest["quality_status"] == "PASS" else 1


def check_main(argv: list[str] | None = None) -> int:
    args = check_arg_parser().parse_args(argv)
    result = check_self_rag_critic_manifest(**vars(args))
    s = result["summary"]
    print("status=" + result["status"])
    print("quality_status=" + result["quality_status"])
    print("critic_record_count=" + str(s.get("critic_record_count")))
    print("critic_pass_count=" + str(s.get("critic_pass_count")))
    print("expected_boundary_count=" + str(s.get("expected_boundary_count")))
    print("review_count=" + str(s.get("review_count")))
    print("repair_recommended_count=" + str(s.get("repair_recommended_count")))
    print("unsafe_finding_count=" + str(s.get("unsafe_finding_count")))
    print("answer_permission_count=" + str(s.get("answer_permission_count")))
    print("write_attempt_count=" + str(s.get("write_attempt_count")))
    if result.get("quality_failures"):
        print("quality_failures=" + json.dumps(result["quality_failures"]))
    return 0 if result["quality_status"] == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
