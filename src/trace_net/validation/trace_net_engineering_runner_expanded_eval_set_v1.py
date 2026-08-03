"""TRACE-Net Engineering Runner Expanded Evaluation Set v1.

This module wraps the already validated H6 engineering runner eval set with a
broader default question set. It does not change retrieval, routing, proof
selection, answer composition, or safety policy. Its purpose is to measure
coverage and expose the next weak question types.
"""

from __future__ import annotations

import argparse
import inspect
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

STATUS_BUILT = "TRACE_NET_ENGINEERING_RUNNER_EXPANDED_EVAL_SET_BUILT"
STATUS_CHECKED = "TRACE_NET_ENGINEERING_RUNNER_EXPANDED_EVAL_SET_QUALITY_CHECKED"
MODULE = "trace_net_engineering_runner_expanded_eval_set_v1"
VERSION = "v1"

DEFAULT_EXPANDED_QUESTIONS: List[str] = [
    "What does figure 69 show?",
    "What does figure 75 show?",
    "What does figure 91 show?",
    "Compare figure 69 and figure 75.",
    "Find part number 120-50645-005 and cite the source.",
    "Find part number 120-50645-011 and cite the source.",
    "Find part number 120-29068-003 and cite the source.",
    "Why was nomenclature missing from the visual route evidence?",
    "What evidence supports part number 120-50645-005?",
    "What can TRACE-Net not prove about part number 120-50645-005?",
    "Is 120-50645-005 interchangeable with 120-50645-011?",
    "Does figure 69 prove installation safety?",
]


def _write_json(path: Any, data: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _read_json(path: Any) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _filter_kwargs(fn: Any, kwargs: Dict[str, Any]) -> Dict[str, Any]:
    sig = inspect.signature(fn)
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
        return kwargs
    return {k: v for k, v in kwargs.items() if k in sig.parameters}


def _load_h6_builder() -> Any:
    try:
        from tiff import trace_net_engineering_runner_eval_set_v1 as h6
    except Exception as exc:  # pragma: no cover - import error text is user-facing
        raise RuntimeError(f"Could not import H6 eval module: {exc}") from exc

    for name in ("build_engineering_runner_eval_set", "build_runner_eval_set", "build_eval_set"):
        fn = getattr(h6, name, None)
        if callable(fn):
            return fn
    raise RuntimeError("Could not find H6 eval builder function in trace_net_engineering_runner_eval_set_v1")


def _collect_summary(h6_manifest: Mapping[str, Any]) -> Dict[str, Any]:
    source_summary = dict(h6_manifest.get("summary", {}) or {})
    records = list(h6_manifest.get("records", []) or [])
    task_types = sorted({str(r.get("task_type") or "unknown") for r in records})
    failing_questions = [r.get("question") for r in records if not r.get("runner_passed")]
    passing_questions = [r.get("question") for r in records if r.get("runner_passed")]

    summary: Dict[str, Any] = {
        "expanded_question_count": len(records),
        "runner_pass_count": int(source_summary.get("runner_pass_count", 0) or 0),
        "runner_fail_count": int(source_summary.get("runner_fail_count", 0) or 0),
        "stage_pass_count": int(source_summary.get("stage_pass_count", 0) or 0),
        "proof_context_count": int(source_summary.get("proof_context_count", 0) or 0),
        "answer_citation_count": int(source_summary.get("answer_citation_count", 0) or 0),
        "valid_answer_citation_count": int(source_summary.get("valid_answer_citation_count", 0) or 0),
        "source_trace_ready_citation_count": int(source_summary.get("source_trace_ready_citation_count", 0) or 0),
        "summary_used_as_proof_count": int(source_summary.get("summary_used_as_proof_count", 0) or 0),
        "unsupported_claim_count": int(source_summary.get("unsupported_claim_count", 0) or 0),
        "invalid_answer_citation_count": int(source_summary.get("invalid_answer_citation_count", 0) or 0),
        "llava_only_part_identity_claim_count": int(source_summary.get("llava_only_part_identity_claim_count", 0) or 0),
        "answer_permission_count": int(source_summary.get("answer_permission_count", 0) or 0),
        "source_truth_mutation_allowed_count": int(source_summary.get("source_truth_mutation_allowed_count", 0) or 0),
        "postgres_write_attempt_count": int(source_summary.get("postgres_write_attempt_count", 0) or 0),
        "qdrant_write_attempt_count": int(source_summary.get("qdrant_write_attempt_count", 0) or 0),
        "opensearch_write_attempt_count": int(source_summary.get("opensearch_write_attempt_count", 0) or 0),
        "opensearch_upload_attempt_count": int(source_summary.get("opensearch_upload_attempt_count", 0) or 0),
        "write_attempt_count": int(source_summary.get("write_attempt_count", 0) or 0),
        "unsafe_record_count": int(source_summary.get("unsafe_record_count", 0) or 0),
        "task_types": task_types,
        "task_type_count": len(task_types),
        "passing_question_count": len(passing_questions),
        "failing_question_count": len(failing_questions),
        "ready_for_next_coverage_patch": bool(records),
    }
    return summary


def _evaluate_quality(
    summary: Mapping[str, Any],
    *,
    min_expanded_questions: int = 6,
    min_runner_passes: int = 6,
    max_unsupported_claims: int = 0,
    max_summary_used_as_proof: int = 0,
    max_invalid_citations: int = 0,
    max_llava_only_part_identity_claims: int = 0,
    max_unsafe: int = 0,
    max_answer_permission: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    max_write_attempts: int = 0,
) -> List[str]:
    failures: List[str] = []

    checks = [
        ("expanded_question_count", min_expanded_questions, "below minimum"),
        ("runner_pass_count", min_runner_passes, "below minimum"),
    ]
    for key, minimum, label in checks:
        value = int(summary.get(key, 0) or 0)
        if value < minimum:
            failures.append(f"{key} {label}: {value} < {minimum}")

    max_checks = [
        ("unsupported_claim_count", max_unsupported_claims),
        ("summary_used_as_proof_count", max_summary_used_as_proof),
        ("invalid_answer_citation_count", max_invalid_citations),
        ("llava_only_part_identity_claim_count", max_llava_only_part_identity_claims),
        ("unsafe_record_count", max_unsafe),
        ("answer_permission_count", max_answer_permission),
        ("source_truth_mutation_allowed_count", max_source_truth_mutation_allowed),
        ("write_attempt_count", max_write_attempts),
    ]
    for key, maximum in max_checks:
        value = int(summary.get(key, 0) or 0)
        if value > maximum:
            failures.append(f"{key} above maximum: {value} > {maximum}")

    return failures


def build_engineering_runner_expanded_eval_set(
    *,
    questions: Optional[Sequence[str]] = None,
    v2_summary_guidance_index: Any,
    image_visual_evidence_pack: Any,
    raw_ocr_nomenclature_extractor: Any,
    table_route_evidence_packager: Any,
    table_exact_search_adapter: Any,
    output_dir: Any,
    max_guidance_pages: int = 8,
    min_expanded_questions: int = 6,
    min_runner_passes: int = 6,
    min_planner_records: int = 1,
    min_required_routes: int = 1,
    min_guidance_context: int = 0,
    min_proof_context: int = 2,
    min_source_trace_ready: int = 2,
    min_answer_citations: int = 2,
    min_source_trace_ready_citations: int = 2,
    max_unsupported_claims: int = 0,
    max_summary_used_as_proof: int = 0,
    max_invalid_citations: int = 0,
    max_llava_only_part_identity_claims: int = 0,
    max_unsafe: int = 0,
    max_answer_permission: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    max_write_attempts: int = 0,
    require_quality_pass: bool = False,
) -> Dict[str, Any]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    eval_questions = list(questions or DEFAULT_EXPANDED_QUESTIONS)
    h6_dir = out_dir / "h6_eval"
    h6_builder = _load_h6_builder()

    h6_kwargs = {
        "questions": eval_questions,
        "v2_summary_guidance_index": v2_summary_guidance_index,
        "image_visual_evidence_pack": image_visual_evidence_pack,
        "raw_ocr_nomenclature_extractor": raw_ocr_nomenclature_extractor,
        "table_route_evidence_packager": table_route_evidence_packager,
        "table_exact_search_adapter": table_exact_search_adapter,
        "output_dir": h6_dir,
        "max_guidance_pages": max_guidance_pages,
        "min_eval_questions": min_expanded_questions,
        "min_runner_passes": min_runner_passes,
        "min_planner_records": min_planner_records,
        "min_required_routes": min_required_routes,
        "min_guidance_context": min_guidance_context,
        "min_proof_context": min_proof_context,
        "min_source_trace_ready": min_source_trace_ready,
        "min_answer_citations": min_answer_citations,
        "min_source_trace_ready_citations": min_source_trace_ready_citations,
        "max_unsupported_claims": max_unsupported_claims,
        "max_summary_used_as_proof": max_summary_used_as_proof,
        "max_invalid_citations": max_invalid_citations,
        "max_llava_only_part_identity_claims": max_llava_only_part_identity_claims,
        "max_unsafe": max_unsafe,
        "max_answer_permission": max_answer_permission,
        "max_source_truth_mutation_allowed": max_source_truth_mutation_allowed,
        "max_write_attempts": max_write_attempts,
        "require_quality_pass": False,
    }

    h6_manifest = h6_builder(**_filter_kwargs(h6_builder, h6_kwargs))
    summary = _collect_summary(h6_manifest)
    failures = _evaluate_quality(
        summary,
        min_expanded_questions=min_expanded_questions,
        min_runner_passes=min_runner_passes,
        max_unsupported_claims=max_unsupported_claims,
        max_summary_used_as_proof=max_summary_used_as_proof,
        max_invalid_citations=max_invalid_citations,
        max_llava_only_part_identity_claims=max_llava_only_part_identity_claims,
        max_unsafe=max_unsafe,
        max_answer_permission=max_answer_permission,
        max_source_truth_mutation_allowed=max_source_truth_mutation_allowed,
        max_write_attempts=max_write_attempts,
    )

    manifest: Dict[str, Any] = {
        "status": STATUS_BUILT,
        "quality_status": "PASS" if not failures else "FAIL",
        "module": MODULE,
        "version": VERSION,
        "questions": eval_questions,
        "summary": summary,
        "failures": failures,
        "source_h6_eval_set": str(h6_dir / "trace_net_engineering_runner_eval_set_v1.json"),
        "records": h6_manifest.get("records", []),
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
    }

    out_path = out_dir / "trace_net_engineering_runner_expanded_eval_set_v1.json"
    qc_path = out_dir / "trace_net_engineering_runner_expanded_eval_set_v1_quality_check.json"
    _write_json(out_path, manifest)
    _write_json(qc_path, {"status": STATUS_CHECKED, **manifest})

    if require_quality_pass and manifest["quality_status"] != "PASS":
        raise SystemExit("quality_status is not PASS")

    return manifest


def check_engineering_runner_expanded_eval_set(
    *,
    expanded_eval_set: Any,
    output: Any,
    require_quality_pass: bool = False,
    min_expanded_questions: int = 6,
    min_runner_passes: int = 6,
    max_unsupported_claims: int = 0,
    max_summary_used_as_proof: int = 0,
    max_invalid_citations: int = 0,
    max_llava_only_part_identity_claims: int = 0,
    max_unsafe: int = 0,
    max_answer_permission: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    max_write_attempts: int = 0,
) -> Dict[str, Any]:
    data = _read_json(expanded_eval_set)
    summary = data.get("summary", {}) or {}
    failures = _evaluate_quality(
        summary,
        min_expanded_questions=min_expanded_questions,
        min_runner_passes=min_runner_passes,
        max_unsupported_claims=max_unsupported_claims,
        max_summary_used_as_proof=max_summary_used_as_proof,
        max_invalid_citations=max_invalid_citations,
        max_llava_only_part_identity_claims=max_llava_only_part_identity_claims,
        max_unsafe=max_unsafe,
        max_answer_permission=max_answer_permission,
        max_source_truth_mutation_allowed=max_source_truth_mutation_allowed,
        max_write_attempts=max_write_attempts,
    )

    if data.get("quality_status") != "PASS":
        failures.append("expanded eval source quality_status is not PASS")

    result = {
        "status": STATUS_CHECKED,
        "quality_status": "PASS" if not failures else "FAIL",
        "summary": summary,
        "failures": failures,
    }
    _write_json(output, result)
    if require_quality_pass and result["quality_status"] != "PASS":
        raise SystemExit("quality_status is not PASS")
    return result


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--min-expanded-questions", type=int, default=6)
    parser.add_argument("--min-runner-passes", type=int, default=6)
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
    parser = argparse.ArgumentParser(description="Build TRACE-Net engineering runner expanded eval set v1")
    parser.add_argument("--question", action="append", dest="questions", default=[])
    parser.add_argument("--v2-summary-guidance-index", required=True)
    parser.add_argument("--image-visual-evidence-pack", required=True)
    parser.add_argument("--raw-ocr-nomenclature-extractor", required=True)
    parser.add_argument("--table-route-evidence-packager", required=True)
    parser.add_argument("--table-exact-search-adapter", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--max-guidance-pages", type=int, default=8)
    parser.add_argument("--min-planner-records", type=int, default=1)
    parser.add_argument("--min-required-routes", type=int, default=1)
    parser.add_argument("--min-guidance-context", type=int, default=0)
    parser.add_argument("--min-proof-context", type=int, default=2)
    parser.add_argument("--min-source-trace-ready", type=int, default=2)
    parser.add_argument("--min-answer-citations", type=int, default=2)
    parser.add_argument("--min-source-trace-ready-citations", type=int, default=2)
    _add_common_args(parser)
    return parser.parse_args(argv)


def check_parser(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check TRACE-Net engineering runner expanded eval set v1")
    parser.add_argument("--expanded-eval-set", required=True)
    parser.add_argument("--output", required=True)
    _add_common_args(parser)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser(argv)
    result = build_engineering_runner_expanded_eval_set(**vars(args))
    s = result.get("summary", {})
    print(f"status={result.get('status')}")
    print(f"quality_status={result.get('quality_status')}")
    print(f"expanded_question_count={s.get('expanded_question_count')}")
    print(f"runner_pass_count={s.get('runner_pass_count')}")
    print(f"runner_fail_count={s.get('runner_fail_count')}")
    print(f"summary_used_as_proof_count={s.get('summary_used_as_proof_count')}")
    print(f"unsupported_claim_count={s.get('unsupported_claim_count')}")
    print(f"expanded_eval_set={Path(args.output_dir) / 'trace_net_engineering_runner_expanded_eval_set_v1.json'}")
    return 0


def check_main(argv: Optional[Sequence[str]] = None) -> int:
    args = check_parser(argv)
    result = check_engineering_runner_expanded_eval_set(**vars(args))
    s = result.get("summary", {})
    print(f"status={result.get('status')}")
    print(f"quality_status={result.get('quality_status')}")
    print(f"expanded_question_count={s.get('expanded_question_count')}")
    print(f"runner_pass_count={s.get('runner_pass_count')}")
    print(f"runner_fail_count={s.get('runner_fail_count')}")
    print(f"summary_used_as_proof_count={s.get('summary_used_as_proof_count')}")
    print(f"unsupported_claim_count={s.get('unsupported_claim_count')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
