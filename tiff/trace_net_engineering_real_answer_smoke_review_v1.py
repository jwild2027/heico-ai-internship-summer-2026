"""TRACE-Net Engineering Real Answer Smoke Review v1.

Review layer for H11 real-answer smoke tests. It does not run retrieval or
compose answers. It summarizes grades, weak intents, and next patch targets
from an existing H11 smoke-test manifest.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

MODULE = "trace_net_engineering_real_answer_smoke_review_v1"
VERSION = "v1"
STATUS_BUILT = "TRACE_NET_ENGINEERING_REAL_ANSWER_SMOKE_REVIEW_BUILT"
STATUS_CHECKED = "TRACE_NET_ENGINEERING_REAL_ANSWER_SMOKE_REVIEW_CHECKED"

GRADE_ORDER = {"GOOD": 0, "PARTIAL": 1, "BLOCKED": 2, "BAD": 3}
WEAK_GRADES = {"PARTIAL", "BLOCKED", "BAD"}

RECOMMENDATIONS = {
    "evidence_support": "Improve evidence-support answers so they directly explain why each citation supports the requested figure/part.",
    "source_page": "Add source-page answer shaping that leads with the exact page(s) supporting the requested claim.",
    "evidence_explanation": "Add visual-vs-OCR proof explanation answers that distinguish figure linkage from text/nomenclature proof.",
    "route_explanation": "Add route-explanation answers that name the required routes and what each route contributes.",
    "summary_limit": "Add summary-limit answers that lead with: v2 summaries guide planning/framing but cannot prove source claims.",
    "replacement_limit": "Add replacement-approval limitation answers that lead with: replacement approval is not proven without explicit source authority.",
    "fit_limit": "Add fit-approval limitation answers that lead with: fit approval is not proven from figure identity evidence.",
    "effectivity_limit": "Add effectivity limitation answers that lead with: aircraft/effectivity applicability requires explicit source proof.",
    "nomenclature_summary": "Add nomenclature aggregate answers that list all source-traced figures/parts linked to the requested nomenclature.",
    "unknown_part": "Improve unknown-part handling so no-proof answers lead with not found / not source-traced, not generic low-confidence evidence language.",
    "unknown_figure": "Improve unknown-figure handling so no-proof answers lead with not found / no source-trace-ready figure evidence.",
    "troubleshooting": "Extend troubleshooting answers beyond nomenclature recovery into pipeline-stage explanations.",
    "comparison": "Improve comparison scoring/formatting for cross-figure comparisons and ensure both entities are fully addressed.",
    "installation_safety": "Extend unsupported safety answers to all safety-style phrasings, including 'safe to install based only on figure'.",
    "interchangeability": "Extend unsupported interchangeability logic to replacement/supersedure wording variants.",
    "limitations": "Fix limitations wording and ensure limitations answers lead with boundary conditions before evidence details.",
}


def _load_json(path: Any) -> Dict[str, Any]:
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object at {p}")
    return data


def _write_json(path: Any, data: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_csv(path: Any, records: Sequence[Mapping[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "question_id",
        "grade",
        "category",
        "question",
        "runner_passed",
        "quality_status",
        "task_type",
        "intent_answer_used",
        "intent_answer_type",
        "proof_context_count",
        "source_trace_ready_citation_count",
        "unsupported_claim_count",
        "summary_used_as_proof_count",
        "failure_reason",
        "recommendation",
        "answer_preview",
    ]
    with p.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow({k: record.get(k, "") for k in fieldnames})


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _grade(record: Mapping[str, Any]) -> str:
    g = str(record.get("grade") or "").upper().strip()
    return g if g in GRADE_ORDER else "BAD"


def _category(record: Mapping[str, Any]) -> str:
    return str(record.get("category") or "uncategorized").strip() or "uncategorized"


def _recommendation_for(category: str, grade: str) -> str:
    if grade == "GOOD":
        return "No immediate action; keep this case as a regression guard."
    return RECOMMENDATIONS.get(category, "Inspect answer preview and add an intent-specific answer rule or retrieval route for this category.")


def _record_review(record: Mapping[str, Any]) -> Dict[str, Any]:
    grade = _grade(record)
    category = _category(record)
    answer_preview = str(record.get("answer_preview") or "")
    return {
        "question_id": record.get("question_id", ""),
        "grade": grade,
        "category": category,
        "question": record.get("question", ""),
        "runner_passed": bool(record.get("runner_passed")),
        "quality_status": record.get("quality_status", ""),
        "task_type": record.get("task_type", ""),
        "intent_answer_used": bool(record.get("intent_answer_used")),
        "intent_answer_type": record.get("intent_answer_type", ""),
        "proof_context_count": _as_int(record.get("proof_context_count")),
        "source_trace_ready_citation_count": _as_int(record.get("source_trace_ready_citation_count")),
        "unsupported_claim_count": _as_int(record.get("unsupported_claim_count")),
        "summary_used_as_proof_count": _as_int(record.get("summary_used_as_proof_count")),
        "failure_reason": record.get("failure_reason", ""),
        "error": record.get("error", ""),
        "answer_preview": answer_preview[:1200],
        "recommendation": _recommendation_for(category, grade),
    }


def _quality_gate(summary: Mapping[str, Any], *, min_smoke_questions: int, min_good_answers: int,
                  min_good_or_partial_answers: int, max_bad_answers: int, max_blocked_answers: Optional[int],
                  max_unsupported_claims: int, max_summary_used_as_proof: int,
                  max_invalid_citations: int, max_llava_only_part_identity_claims: int,
                  max_unsafe: int, max_answer_permission: int,
                  max_source_truth_mutation_allowed: int, max_write_attempts: int) -> Dict[str, Any]:
    failures: List[str] = []

    checks = [
        ("smoke_question_count", "below minimum", _as_int(summary.get("smoke_question_count")), min_smoke_questions, "min"),
        ("good_answer_count", "below minimum", _as_int(summary.get("good_answer_count")), min_good_answers, "min"),
        ("good_or_partial_answer_count", "below minimum", _as_int(summary.get("good_or_partial_answer_count")), min_good_or_partial_answers, "min"),
        ("bad_answer_count", "above maximum", _as_int(summary.get("bad_answer_count")), max_bad_answers, "max"),
        ("unsupported_claim_count", "above maximum", _as_int(summary.get("unsupported_claim_count")), max_unsupported_claims, "max"),
        ("summary_used_as_proof_count", "above maximum", _as_int(summary.get("summary_used_as_proof_count")), max_summary_used_as_proof, "max"),
        ("invalid_answer_citation_count", "above maximum", _as_int(summary.get("invalid_answer_citation_count")), max_invalid_citations, "max"),
        ("llava_only_part_identity_claim_count", "above maximum", _as_int(summary.get("llava_only_part_identity_claim_count")), max_llava_only_part_identity_claims, "max"),
        ("unsafe_record_count", "above maximum", _as_int(summary.get("unsafe_record_count")), max_unsafe, "max"),
        ("answer_permission_count", "above maximum", _as_int(summary.get("answer_permission_count")), max_answer_permission, "max"),
        ("source_truth_mutation_allowed_count", "above maximum", _as_int(summary.get("source_truth_mutation_allowed_count")), max_source_truth_mutation_allowed, "max"),
        ("write_attempt_count", "above maximum", _as_int(summary.get("write_attempt_count")), max_write_attempts, "max"),
    ]
    if max_blocked_answers is not None:
        checks.append(("blocked_answer_count", "above maximum", _as_int(summary.get("blocked_answer_count")), max_blocked_answers, "max"))

    for name, label, actual, expected, mode in checks:
        if mode == "min" and actual < expected:
            failures.append(f"{name} {label}: {actual} < {expected}")
        elif mode == "max" and actual > expected:
            failures.append(f"{name} {label}: {actual} > {expected}")

    return {"quality_status": "PASS" if not failures else "FAIL", "failures": failures}


def build_smoke_review(*, smoke_test: Any, output_dir: Any,
                       min_smoke_questions: int = 1, min_good_answers: int = 0,
                       min_good_or_partial_answers: int = 0, max_bad_answers: int = 0,
                       max_blocked_answers: Optional[int] = None,
                       max_unsupported_claims: int = 0, max_summary_used_as_proof: int = 0,
                       max_invalid_citations: int = 0, max_llava_only_part_identity_claims: int = 0,
                       max_unsafe: int = 0, max_answer_permission: int = 0,
                       max_source_truth_mutation_allowed: int = 0, max_write_attempts: int = 0,
                       require_quality_pass: bool = False) -> Dict[str, Any]:
    source = _load_json(smoke_test)
    source_records = source.get("records", [])
    if not isinstance(source_records, list):
        source_records = []

    records = [_record_review(r) for r in source_records if isinstance(r, Mapping)]
    grade_counts = Counter(r["grade"] for r in records)
    category_counts = Counter(r["category"] for r in records)
    weak_records = [r for r in records if r["grade"] in WEAK_GRADES]
    weak_category_counts = Counter(r["category"] for r in weak_records)

    by_category: Dict[str, Dict[str, Any]] = {}
    for category in sorted(category_counts):
        rows = [r for r in records if r["category"] == category]
        by_category[category] = {
            "category": category,
            "record_count": len(rows),
            "good_count": sum(1 for r in rows if r["grade"] == "GOOD"),
            "partial_count": sum(1 for r in rows if r["grade"] == "PARTIAL"),
            "blocked_count": sum(1 for r in rows if r["grade"] == "BLOCKED"),
            "bad_count": sum(1 for r in rows if r["grade"] == "BAD"),
            "recommendation": _recommendation_for(category, "PARTIAL" if any(r["grade"] != "GOOD" for r in rows) else "GOOD"),
        }

    source_summary = source.get("summary", {}) if isinstance(source.get("summary", {}), Mapping) else {}
    summary = {
        "module": MODULE,
        "version": VERSION,
        "source_smoke_test": str(smoke_test),
        "smoke_question_count": len(records),
        "good_answer_count": grade_counts.get("GOOD", 0),
        "partial_answer_count": grade_counts.get("PARTIAL", 0),
        "bad_answer_count": grade_counts.get("BAD", 0),
        "blocked_answer_count": grade_counts.get("BLOCKED", 0),
        "good_or_partial_answer_count": grade_counts.get("GOOD", 0) + grade_counts.get("PARTIAL", 0),
        "weak_answer_count": len(weak_records),
        "weak_category_count": len(weak_category_counts),
        "runner_pass_count": _as_int(source_summary.get("runner_pass_count")),
        "runner_fail_count": _as_int(source_summary.get("runner_fail_count")),
        "intent_answer_used_count": _as_int(source_summary.get("intent_answer_used_count")),
        "answer_citation_count": _as_int(source_summary.get("answer_citation_count")),
        "valid_answer_citation_count": _as_int(source_summary.get("valid_answer_citation_count")),
        "source_trace_ready_citation_count": _as_int(source_summary.get("source_trace_ready_citation_count")),
        "unsupported_claim_count": _as_int(source_summary.get("unsupported_claim_count")),
        "summary_used_as_proof_count": _as_int(source_summary.get("summary_used_as_proof_count")),
        "invalid_answer_citation_count": _as_int(source_summary.get("invalid_answer_citation_count")),
        "llava_only_part_identity_claim_count": _as_int(source_summary.get("llava_only_part_identity_claim_count")),
        "answer_permission_count": _as_int(source_summary.get("answer_permission_count")),
        "source_truth_mutation_allowed_count": _as_int(source_summary.get("source_truth_mutation_allowed_count")),
        "write_attempt_count": _as_int(source_summary.get("write_attempt_count")),
        "unsafe_record_count": _as_int(source_summary.get("unsafe_record_count")),
        "top_weak_categories": [
            {"category": cat, "weak_count": count, "recommendation": _recommendation_for(cat, "PARTIAL")}
            for cat, count in weak_category_counts.most_common()
        ],
        "ready_for_user_facing_answer_smoke": grade_counts.get("BAD", 0) == 0 and _as_int(source_summary.get("unsupported_claim_count")) == 0,
        "ready_for_next_intent_patch": len(weak_records) > 0,
    }

    gate = _quality_gate(
        summary,
        min_smoke_questions=min_smoke_questions,
        min_good_answers=min_good_answers,
        min_good_or_partial_answers=min_good_or_partial_answers,
        max_bad_answers=max_bad_answers,
        max_blocked_answers=max_blocked_answers,
        max_unsupported_claims=max_unsupported_claims,
        max_summary_used_as_proof=max_summary_used_as_proof,
        max_invalid_citations=max_invalid_citations,
        max_llava_only_part_identity_claims=max_llava_only_part_identity_claims,
        max_unsafe=max_unsafe,
        max_answer_permission=max_answer_permission,
        max_source_truth_mutation_allowed=max_source_truth_mutation_allowed,
        max_write_attempts=max_write_attempts,
    )

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "status": STATUS_BUILT,
        "quality_status": gate["quality_status"],
        "summary": summary,
        "quality_gate": gate,
        "records": records,
        "weak_records": weak_records,
        "category_reviews": list(by_category.values()),
        "recommendations": summary["top_weak_categories"],
    }

    report_path = out_dir / f"{MODULE}.json"
    qc_path = out_dir / f"{MODULE}_quality_check.json"
    csv_path = out_dir / f"{MODULE}_weak_records.csv"
    all_csv_path = out_dir / f"{MODULE}_records.csv"
    _write_json(report_path, report)
    _write_json(qc_path, {"status": STATUS_CHECKED, **gate, "summary": summary})
    _write_csv(csv_path, weak_records)
    _write_csv(all_csv_path, records)
    report["paths"] = {
        "review": str(report_path),
        "quality_check": str(qc_path),
        "weak_records_csv": str(csv_path),
        "records_csv": str(all_csv_path),
    }
    _write_json(report_path, report)

    if require_quality_pass and report["quality_status"] != "PASS":
        for failure in gate["failures"]:
            print(f"failure={failure}")
        raise SystemExit("quality_status is not PASS")

    return report


def check_smoke_review(*, review: Any, output: Any,
                       require_quality_pass: bool = False,
                       min_smoke_questions: int = 1, min_good_answers: int = 0,
                       min_good_or_partial_answers: int = 0, max_bad_answers: int = 0,
                       max_blocked_answers: Optional[int] = None,
                       max_unsupported_claims: int = 0, max_summary_used_as_proof: int = 0,
                       max_invalid_citations: int = 0, max_llava_only_part_identity_claims: int = 0,
                       max_unsafe: int = 0, max_answer_permission: int = 0,
                       max_source_truth_mutation_allowed: int = 0, max_write_attempts: int = 0) -> Dict[str, Any]:
    data = _load_json(review)
    summary = data.get("summary", {}) if isinstance(data.get("summary", {}), Mapping) else {}
    gate = _quality_gate(
        summary,
        min_smoke_questions=min_smoke_questions,
        min_good_answers=min_good_answers,
        min_good_or_partial_answers=min_good_or_partial_answers,
        max_bad_answers=max_bad_answers,
        max_blocked_answers=max_blocked_answers,
        max_unsupported_claims=max_unsupported_claims,
        max_summary_used_as_proof=max_summary_used_as_proof,
        max_invalid_citations=max_invalid_citations,
        max_llava_only_part_identity_claims=max_llava_only_part_identity_claims,
        max_unsafe=max_unsafe,
        max_answer_permission=max_answer_permission,
        max_source_truth_mutation_allowed=max_source_truth_mutation_allowed,
        max_write_attempts=max_write_attempts,
    )
    result = {"status": STATUS_CHECKED, **gate, "summary": summary}
    _write_json(output, result)
    if require_quality_pass and result["quality_status"] != "PASS":
        for failure in result["failures"]:
            print(f"failure={failure}")
        raise SystemExit("quality_status is not PASS")
    return result


def _add_common_threshold_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--min-smoke-questions", type=int, default=1)
    parser.add_argument("--min-good-answers", type=int, default=0)
    parser.add_argument("--min-good-or-partial-answers", type=int, default=0)
    parser.add_argument("--max-bad-answers", type=int, default=0)
    parser.add_argument("--max-blocked-answers", type=int, default=None)
    parser.add_argument("--max-unsupported-claims", type=int, default=0)
    parser.add_argument("--max-summary-used-as-proof", type=int, default=0)
    parser.add_argument("--max-invalid-citations", type=int, default=0)
    parser.add_argument("--max-llava-only-part-identity-claims", type=int, default=0)
    parser.add_argument("--max-unsafe", type=int, default=0)
    parser.add_argument("--max-answer-permission", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--max-write-attempts", type=int, default=0)
    parser.add_argument("--require-quality-pass", action="store_true")


def build_parser(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build TRACE-Net engineering real-answer smoke review v1")
    parser.add_argument("--smoke-test", required=True)
    parser.add_argument("--output-dir", required=True)
    _add_common_threshold_args(parser)
    return parser.parse_args(argv)


def check_parser(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check TRACE-Net engineering real-answer smoke review v1")
    parser.add_argument("--review", required=True)
    parser.add_argument("--output", required=True)
    _add_common_threshold_args(parser)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser(argv)
    result = build_smoke_review(**vars(args))
    s = result["summary"]
    print(f"status={result['status']}")
    print(f"quality_status={result['quality_status']}")
    for key in [
        "smoke_question_count",
        "good_answer_count",
        "partial_answer_count",
        "bad_answer_count",
        "blocked_answer_count",
        "weak_answer_count",
        "weak_category_count",
        "unsupported_claim_count",
        "summary_used_as_proof_count",
    ]:
        print(f"{key}={s.get(key)}")
    print(f"review={result['paths']['review']}")
    return 0


def check_main(argv: Optional[Sequence[str]] = None) -> int:
    args = check_parser(argv)
    result = check_smoke_review(**vars(args))
    s = result["summary"]
    print(f"status={result['status']}")
    print(f"quality_status={result['quality_status']}")
    for key in [
        "smoke_question_count",
        "good_answer_count",
        "partial_answer_count",
        "bad_answer_count",
        "blocked_answer_count",
        "weak_answer_count",
        "weak_category_count",
        "unsupported_claim_count",
        "summary_used_as_proof_count",
    ]:
        print(f"{key}={s.get(key)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
