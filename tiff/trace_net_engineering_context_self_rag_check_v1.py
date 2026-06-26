
"""TRACE-Net Engineering Context Self-RAG Check v1.

Scores engineering context packs before Gemma drafting.

This module checks:
- source-truth evidence strength
- candidate-only evidence
- missing evidence notes
- route coverage
- forbidden-claim risk
- CRAG retry need
- draft readiness

Safety:
- does not answer the user question
- does not call an LLM
- does not execute retrieval
- does not mutate source truth
- does not grant final answer permission
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence


MODULE_VERSION = "trace_net_engineering_context_self_rag_check_v1"
REPORT_NAME = "trace_net_engineering_context_self_rag_check_v1.json"

SOURCE_TRUTH_TIERS = {
    "exact_source_evidence_candidate",
    "source_context_guidance",
    "structured_table_candidate",
}

CANDIDATE_TIERS = {
    "relationship_candidate",
    "visual_candidate_only",
    "semantic_lead_only",
    "routing_metadata_not_source_truth",
    "candidate_or_supporting",
}


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"missing JSON file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def _all_capsules(pack: Mapping[str, Any]) -> List[Dict[str, Any]]:
    capsules: List[Dict[str, Any]] = []
    route_caps = pack.get("route_evidence_capsules") or {}
    if isinstance(route_caps, dict):
        for route, items in route_caps.items():
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        clone = dict(item)
                        clone.setdefault("route", route)
                        capsules.append(clone)
    return capsules


def _missing_notes(pack: Mapping[str, Any]) -> List[Dict[str, Any]]:
    notes = pack.get("missing_evidence") or []
    return [n for n in notes if isinstance(n, dict)]


def _clamp(value: float, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, int(round(value))))


def _critical_missing_types(pack: Mapping[str, Any]) -> List[str]:
    intent = pack.get("intent_family")
    critical = []
    for note in _missing_notes(pack):
        mtype = note.get("missing_type")
        if mtype == "route_slot_unfilled":
            critical.append(str(mtype))
        if intent == "engineering_change_candidate" and mtype == "source_dimension_not_confirmed":
            critical.append(str(mtype))
        if intent == "repair_or_fault_context" and mtype == "warning_caution_not_confirmed":
            critical.append(str(mtype))
        if intent == "visual_or_callout_similarity" and note.get("route") == "image_visual":
            critical.append(str(mtype))
    return sorted(set(critical))


def _capsule_counts(capsules: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    trust_counts = Counter(str(c.get("trust_tier")) for c in capsules)
    route_counts = Counter(str(c.get("route")) for c in capsules)
    source_truth_count = sum(
        1 for c in capsules
        if c.get("trust_tier") in SOURCE_TRUTH_TIERS and not c.get("fallback_available_context")
    )
    exact_count = sum(
        1 for c in capsules
        if c.get("trust_tier") == "exact_source_evidence_candidate" and not c.get("fallback_available_context")
    )
    candidate_count = sum(
        1 for c in capsules
        if c.get("trust_tier") in CANDIDATE_TIERS or c.get("fallback_available_context")
    )
    high_signal_count = sum(1 for c in capsules if not c.get("fallback_available_context"))
    fallback_count = sum(1 for c in capsules if c.get("fallback_available_context"))
    source_trace_ready_count = sum(1 for c in capsules if c.get("source_trace_ready"))
    return {
        "trust_tier_counts": dict(sorted(trust_counts.items())),
        "route_capsule_counts": dict(sorted(route_counts.items())),
        "source_truth_capsule_count": source_truth_count,
        "exact_source_capsule_count": exact_count,
        "candidate_capsule_count": candidate_count,
        "high_signal_capsule_count": high_signal_count,
        "fallback_capsule_count": fallback_count,
        "source_trace_ready_capsule_count": source_trace_ready_count,
    }


def _route_coverage(pack: Mapping[str, Any]) -> Dict[str, Any]:
    required = int(pack.get("required_route_slot_count") or 0)
    filled = int(pack.get("filled_route_slot_count") or 0)
    high_signal_filled = int(pack.get("high_signal_filled_route_slot_count") or 0)
    if required <= 0:
        status = "no_route_slots_declared"
    elif high_signal_filled >= required:
        status = "complete_high_signal_route_coverage"
    elif filled >= required:
        status = "complete_with_fallback_or_weak_route_coverage"
    elif filled > 0:
        status = "partial_route_coverage"
    else:
        status = "missing_route_coverage"
    return {
        "required_route_slot_count": required,
        "filled_route_slot_count": filled,
        "high_signal_filled_route_slot_count": high_signal_filled,
        "route_coverage_ratio": round(filled / required, 4) if required else 0.0,
        "high_signal_route_coverage_ratio": round(high_signal_filled / required, 4) if required else 0.0,
        "route_coverage_status": status,
    }


def _source_truth_strength(pack: Mapping[str, Any], counts: Mapping[str, Any], missing_count: int) -> str:
    intent = pack.get("intent_family")
    exact = int(counts.get("exact_source_capsule_count", 0))
    source_truth = int(counts.get("source_truth_capsule_count", 0))
    high_signal = int(counts.get("high_signal_capsule_count", 0))
    if intent == "exact_part_lookup" and exact > 0 and missing_count == 0:
        return "strong_exact_source_truth"
    if exact > 0:
        return "exact_source_truth_with_open_risks"
    if source_truth > 0 and missing_count == 0:
        return "source_truth_context_available"
    if source_truth > 0:
        return "partial_source_truth_context"
    if high_signal > 0:
        return "candidate_only_or_context_only"
    return "no_evidence"


def _evidence_strength_score(
    *,
    counts: Mapping[str, Any],
    route_coverage: Mapping[str, Any],
    missing_count: int,
    critical_missing_count: int,
    forbidden_claim_count: int,
) -> int:
    high_signal = int(counts.get("high_signal_capsule_count", 0))
    exact = int(counts.get("exact_source_capsule_count", 0))
    source_truth = int(counts.get("source_truth_capsule_count", 0))
    source_trace = int(counts.get("source_trace_ready_capsule_count", 0))
    fallback = int(counts.get("fallback_capsule_count", 0))
    route_score = float(route_coverage.get("high_signal_route_coverage_ratio", 0.0)) * 25.0

    score = 0.0
    score += min(30.0, high_signal * 2.0)
    score += min(25.0, exact * 12.0)
    score += min(15.0, source_truth * 1.5)
    score += min(10.0, source_trace * 1.0)
    score += route_score
    score -= min(30.0, missing_count * 8.0)
    score -= min(30.0, critical_missing_count * 18.0)
    score -= min(10.0, fallback * 2.0)
    score -= min(8.0, forbidden_claim_count * 0.25)
    return _clamp(score)


def evaluate_context_pack(
    *,
    pack: Mapping[str, Any],
    index: int,
    min_high_signal_capsules: int,
    min_evidence_strength_score: int,
) -> Dict[str, Any]:
    capsules = _all_capsules(pack)
    counts = _capsule_counts(capsules)
    missing = _missing_notes(pack)
    missing_types = sorted(set(str(n.get("missing_type")) for n in missing))
    critical_missing = _critical_missing_types(pack)
    route_cov = _route_coverage(pack)
    forbidden_claims = pack.get("forbidden_answer_claims") or []
    forbidden_claim_count = len(forbidden_claims) if isinstance(forbidden_claims, list) else 0

    safety_violations = []
    for key in (
        "answers_user_question",
        "llm_call_allowed",
        "answer_permission",
        "can_answer_directly",
        "can_prove_claims",
        "retrieval_execution_allowed",
        "source_truth_mutation_allowed",
        "postgres_write_attempt",
        "qdrant_write_attempt",
        "opensearch_write_attempt",
        "unsafe",
    ):
        if pack.get(key):
            safety_violations.append(key)

    evidence_score = _evidence_strength_score(
        counts=counts,
        route_coverage=route_cov,
        missing_count=len(missing),
        critical_missing_count=len(critical_missing),
        forbidden_claim_count=forbidden_claim_count,
    )
    source_strength = _source_truth_strength(pack, counts, len(missing))

    exact_required_but_missing = (
        pack.get("intent_family") == "exact_part_lookup"
        and int(counts.get("exact_source_capsule_count", 0)) == 0
    )
    no_high_signal = int(counts.get("high_signal_capsule_count", 0)) < min_high_signal_capsules
    weak_score = evidence_score < min_evidence_strength_score
    crag_retry_required = bool(
        critical_missing
        or exact_required_but_missing
        or no_high_signal
        or weak_score
        or any(n.get("crag_retry_recommended") for n in missing)
    )

    ready_for_gemma_draft = bool(
        not crag_retry_required
        and not safety_violations
        and int(counts.get("high_signal_capsule_count", 0)) >= min_high_signal_capsules
        and evidence_score >= min_evidence_strength_score
    )

    if safety_violations:
        self_rag_status = "SAFETY_FAIL"
    elif ready_for_gemma_draft:
        self_rag_status = "READY_FOR_GEMMA_DRAFT_CONTEXT_ONLY"
    elif crag_retry_required:
        self_rag_status = "CRAG_RETRY_REQUIRED"
    else:
        self_rag_status = "REVIEW_REQUIRED"

    return {
        "self_rag_check_version": MODULE_VERSION,
        "self_rag_record_id": f"engineering_self_rag_{index+1:04d}",
        "context_pack_id": pack.get("context_pack_id"),
        "question_id": pack.get("question_id"),
        "user_question": pack.get("user_question"),
        "intent_family": pack.get("intent_family"),
        "selected_playbook_id": pack.get("selected_playbook_id"),
        "source_blueprint_id": pack.get("source_blueprint_id"),
        "evidence_strength_score": evidence_score,
        "source_truth_evidence_strength": source_strength,
        "route_coverage": route_cov,
        "capsule_counts": counts,
        "missing_evidence_count": len(missing),
        "missing_evidence_types": missing_types,
        "critical_missing_evidence_types": critical_missing,
        "missing_evidence": missing,
        "forbidden_claim_count": forbidden_claim_count,
        "forbidden_claims_sample": forbidden_claims[:12] if isinstance(forbidden_claims, list) else [],
        "crag_retry_required": crag_retry_required,
        "crag_retry_reasons": _crag_retry_reasons(
            missing=missing,
            critical_missing=critical_missing,
            exact_required_but_missing=exact_required_but_missing,
            no_high_signal=no_high_signal,
            weak_score=weak_score,
            safety_violations=safety_violations,
        ),
        "ready_for_gemma_draft": ready_for_gemma_draft,
        "draft_mode": (
            "context_draft_allowed_no_final_answer"
            if ready_for_gemma_draft
            else "crag_retry_or_review_required_before_draft"
        ),
        "self_rag_status": self_rag_status,
        "answers_user_question": False,
        "llm_call_allowed": False,
        "retrieval_execution_allowed": False,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "postgres_write_attempt": False,
        "qdrant_write_attempt": False,
        "opensearch_write_attempt": False,
        "unsafe": bool(safety_violations),
        "safety_violations": safety_violations,
    }


def _crag_retry_reasons(
    *,
    missing: Sequence[Mapping[str, Any]],
    critical_missing: Sequence[str],
    exact_required_but_missing: bool,
    no_high_signal: bool,
    weak_score: bool,
    safety_violations: Sequence[str],
) -> List[str]:
    reasons: List[str] = []
    for item in critical_missing:
        reasons.append(f"critical_missing:{item}")
    for note in missing:
        if note.get("crag_retry_recommended"):
            reasons.append(f"missing_evidence:{note.get('missing_type')}:{note.get('route')}")
    if exact_required_but_missing:
        reasons.append("exact_part_lookup_missing_exact_source_evidence")
    if no_high_signal:
        reasons.append("insufficient_high_signal_evidence_capsules")
    if weak_score:
        reasons.append("evidence_strength_score_below_threshold")
    for violation in safety_violations:
        reasons.append(f"safety_violation:{violation}")
    return sorted(set(reasons))


def build_engineering_context_self_rag_check(
    *,
    context_pack_path: Path,
    output_dir: Path,
    min_high_signal_capsules: int = 1,
    min_evidence_strength_score: int = 35,
) -> Dict[str, Any]:
    pack_payload = _read_json(context_pack_path)
    packs = pack_payload.get("records") or []

    records = [
        evaluate_context_pack(
            pack=pack,
            index=index,
            min_high_signal_capsules=min_high_signal_capsules,
            min_evidence_strength_score=min_evidence_strength_score,
        )
        for index, pack in enumerate(packs)
        if isinstance(pack, dict)
    ]

    status_counts = Counter(record.get("self_rag_status") for record in records)
    intent_counts = Counter(record.get("intent_family") for record in records)
    source_strength_counts = Counter(record.get("source_truth_evidence_strength") for record in records)

    summary = {
        "source_context_pack_builder_quality_status": pack_payload.get("quality_status"),
        "source_context_pack_count": len(packs),
        "self_rag_record_count": len(records),
        "self_rag_status_counts": dict(sorted(status_counts.items())),
        "intent_family_counts": dict(sorted(intent_counts.items())),
        "source_truth_evidence_strength_counts": dict(sorted(source_strength_counts.items())),
        "ready_for_gemma_draft_count": sum(1 for r in records if r.get("ready_for_gemma_draft")),
        "crag_retry_required_count": sum(1 for r in records if r.get("crag_retry_required")),
        "average_evidence_strength_score": round(
            sum(r.get("evidence_strength_score", 0) for r in records) / len(records),
            4,
        ) if records else 0.0,
        "min_evidence_strength_score": min((r.get("evidence_strength_score", 0) for r in records), default=0),
        "max_evidence_strength_score": max((r.get("evidence_strength_score", 0) for r in records), default=0),
        "total_missing_evidence_count": sum(r.get("missing_evidence_count", 0) for r in records),
        "unsafe_record_count": sum(1 for r in records if r.get("unsafe")),
        "answer_permission_count": sum(1 for r in records if r.get("answer_permission")),
        "can_answer_directly_count": sum(1 for r in records if r.get("can_answer_directly")),
        "can_prove_claims_count": sum(1 for r in records if r.get("can_prove_claims")),
        "llm_call_allowed_count": sum(1 for r in records if r.get("llm_call_allowed")),
        "retrieval_execution_allowed_count": sum(1 for r in records if r.get("retrieval_execution_allowed")),
        "source_truth_mutation_allowed_count": sum(1 for r in records if r.get("source_truth_mutation_allowed")),
        "postgres_write_attempt_count": sum(1 for r in records if r.get("postgres_write_attempt")),
        "qdrant_write_attempt_count": sum(1 for r in records if r.get("qdrant_write_attempt")),
        "opensearch_write_attempt_count": sum(1 for r in records if r.get("opensearch_write_attempt")),
    }

    quality_status = "PASS"
    if pack_payload.get("quality_status") != "PASS":
        quality_status = "FAIL"
    if not records:
        quality_status = "FAIL"
    if summary["unsafe_record_count"] != 0:
        quality_status = "FAIL"

    payload: Dict[str, Any] = {
        "module": MODULE_VERSION,
        "status": "ENGINEERING_CONTEXT_SELF_RAG_CHECK_BUILT",
        "quality_status": quality_status,
        "summary": summary,
        "source_context_pack_builder_path": str(context_pack_path),
        "thresholds": {
            "min_high_signal_capsules": min_high_signal_capsules,
            "min_evidence_strength_score": min_evidence_strength_score,
        },
        "records": records,
        "safety_contract": {
            "artifact_authority": "self_rag_check_only",
            "answers_user_question": False,
            "llm_call_allowed": False,
            "retrieval_execution_allowed": False,
            "source_truth_mutation_allowed": False,
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "postgres_write_allowed": False,
            "qdrant_write_allowed": False,
            "opensearch_write_allowed": False,
        },
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / REPORT_NAME, payload)
    _write_jsonl(output_dir / "trace_net_engineering_context_self_rag_check_v1_records.jsonl", records)
    _write_json(output_dir / "trace_net_engineering_context_self_rag_check_v1_summary.json", summary)
    _write_json(output_dir / "trace_net_engineering_context_self_rag_check_v1_quality.json", {"quality_status": quality_status, "summary": summary})
    _write_markdown(output_dir / "trace_net_engineering_context_self_rag_check_v1.md", payload)
    return payload


def _write_markdown(path: Path, payload: Mapping[str, Any]) -> None:
    summary = payload.get("summary") or {}
    lines = [
        "# TRACE-Net Engineering Context Self-RAG Check v1",
        "",
        f"Quality status: **{payload.get('quality_status')}**",
        "",
        "## Summary",
        "",
        f"- Self-RAG records: {summary.get('self_rag_record_count')}",
        f"- Ready for Gemma draft: {summary.get('ready_for_gemma_draft_count')}",
        f"- CRAG retry required: {summary.get('crag_retry_required_count')}",
        f"- Status counts: `{summary.get('self_rag_status_counts')}`",
        f"- Source-truth strength counts: `{summary.get('source_truth_evidence_strength_counts')}`",
        f"- Average evidence score: {summary.get('average_evidence_strength_score')}",
        "",
        "## Records",
        "",
    ]
    for record in payload.get("records") or []:
        lines.extend([
            f"### {record.get('self_rag_record_id')} — {record.get('self_rag_status')}",
            "",
            f"- Question: `{record.get('user_question')}`",
            f"- Intent: `{record.get('intent_family')}`",
            f"- Evidence strength score: `{record.get('evidence_strength_score')}`",
            f"- Source-truth strength: `{record.get('source_truth_evidence_strength')}`",
            f"- Ready for Gemma draft: `{record.get('ready_for_gemma_draft')}`",
            f"- CRAG retry required: `{record.get('crag_retry_required')}`",
            f"- CRAG retry reasons: `{record.get('crag_retry_reasons')}`",
            "",
        ])
    path.write_text("\n".join(lines), encoding="utf-8")


def check_engineering_context_self_rag_check_quality(
    *,
    report_path: Path,
    require_source_context_pack_quality_pass: bool = False,
    min_self_rag_records: int = 1,
    min_ready_for_gemma_draft: int = 0,
    min_crag_retry_required: int = 0,
    max_unsafe: int = 0,
    require_no_answer_permission: bool = False,
    require_no_llm_calls: bool = False,
    require_no_retrieval_execution: bool = False,
    require_no_source_truth_mutation: bool = False,
) -> Dict[str, Any]:
    payload = _read_json(report_path)
    summary = payload.get("summary") or {}
    failures: List[str] = []

    def fail_if(condition: bool, msg: str) -> None:
        if condition:
            failures.append(msg)

    if require_source_context_pack_quality_pass:
        fail_if(summary.get("source_context_pack_builder_quality_status") != "PASS", "source context pack builder quality is not PASS")
    fail_if(summary.get("self_rag_record_count", 0) < min_self_rag_records, "not enough self-rag records")
    fail_if(summary.get("ready_for_gemma_draft_count", 0) < min_ready_for_gemma_draft, "not enough records ready for Gemma draft")
    fail_if(summary.get("crag_retry_required_count", 0) < min_crag_retry_required, "not enough CRAG retry records")
    fail_if(summary.get("unsafe_record_count", 0) > max_unsafe, "unsafe record count exceeded")
    if require_no_answer_permission:
        fail_if(summary.get("answer_permission_count", 0) != 0, "answer permission count not zero")
        fail_if(summary.get("can_answer_directly_count", 0) != 0, "can answer directly count not zero")
        fail_if(summary.get("can_prove_claims_count", 0) != 0, "can prove claims count not zero")
    if require_no_llm_calls:
        fail_if(summary.get("llm_call_allowed_count", 0) != 0, "llm call allowed count not zero")
    if require_no_retrieval_execution:
        fail_if(summary.get("retrieval_execution_allowed_count", 0) != 0, "retrieval execution allowed count not zero")
    if require_no_source_truth_mutation:
        fail_if(summary.get("source_truth_mutation_allowed_count", 0) != 0, "source truth mutation allowed count not zero")

    quality_status = "FAIL" if failures else "PASS"
    return {
        "quality_status": quality_status,
        "summary": summary,
        "failures": failures,
        "checked_report_path": str(report_path),
    }


def main_build(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net engineering context Self-RAG check v1.")
    parser.add_argument("--context-pack", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--min-high-signal-capsules", type=int, default=1)
    parser.add_argument("--min-evidence-strength-score", type=int, default=35)
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)

    payload = build_engineering_context_self_rag_check(
        context_pack_path=Path(args.context_pack),
        output_dir=Path(args.output_dir),
        min_high_signal_capsules=args.min_high_signal_capsules,
        min_evidence_strength_score=args.min_evidence_strength_score,
    )
    print("Status:", payload["status"])
    print("Quality status:", payload["quality_status"])
    print("Summary:", json.dumps(payload["summary"], sort_keys=True))
    return 0 if payload["quality_status"] == "PASS" else 1


def main_check(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net engineering context Self-RAG check v1 quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--require-source-context-pack-quality-pass", action="store_true")
    parser.add_argument("--min-self-rag-records", type=int, default=1)
    parser.add_argument("--min-ready-for-gemma-draft", type=int, default=0)
    parser.add_argument("--min-crag-retry-required", type=int, default=0)
    parser.add_argument("--max-unsafe", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-llm-calls", action="store_true")
    parser.add_argument("--require-no-retrieval-execution", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    args = parser.parse_args(argv)

    result = check_engineering_context_self_rag_check_quality(
        report_path=Path(args.report_path),
        require_source_context_pack_quality_pass=args.require_source_context_pack_quality_pass,
        min_self_rag_records=args.min_self_rag_records,
        min_ready_for_gemma_draft=args.min_ready_for_gemma_draft,
        min_crag_retry_required=args.min_crag_retry_required,
        max_unsafe=args.max_unsafe,
        require_no_answer_permission=args.require_no_answer_permission,
        require_no_llm_calls=args.require_no_llm_calls,
        require_no_retrieval_execution=args.require_no_retrieval_execution,
        require_no_source_truth_mutation=args.require_no_source_truth_mutation,
    )
    print("Quality status:", result["quality_status"])
    print("Summary:", json.dumps(result["summary"], sort_keys=True))
    if result["failures"]:
        print("Failures:", json.dumps(result["failures"], indent=2))
    if args.write_json:
        out = Path(args.report_path).with_name("trace_net_engineering_context_self_rag_check_v1_quality_check.json")
        _write_json(out, result)
        print("Wrote:", out)
    return 0 if result["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main_build())
