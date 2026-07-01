"""TRACE-Net Engineering Runner Evaluation Set v1.

Runs the H5 engineering-answer runner over a small question set and aggregates
stage quality/safety signals. This module is intentionally an evaluator only:
it does not mutate source-truth artifacts and does not write to external stores.
"""

from __future__ import annotations

import argparse
import csv
import importlib
import inspect
import json
import re
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence
import hashlib

STATUS = "TRACE_NET_ENGINEERING_RUNNER_EVAL_SET_BUILT"
CHECK_STATUS = "TRACE_NET_ENGINEERING_RUNNER_EVAL_SET_QUALITY_CHECKED"
VERSION = "v1"

DEFAULT_QUESTIONS = [
    "What does figure 69 show?",
    "What does figure 75 show?",
    "What does figure 91 show?",
    "Find part number 120-50645-005 and cite the source.",
    "Why was nomenclature missing from the visual route evidence?",
    "Compare figure 69 and figure 75.",
]

RUNNER_FUNCTION_NAMES = [
    "build_engineering_answer_runner",
    "build_trace_net_engineering_answer_runner_v1",
    "build_runner",
    "build",
]

SAFETY_COUNTER_KEYS = [
    "answer_permission_count",
    "source_truth_mutation_allowed_count",
    "postgres_write_attempt_count",
    "qdrant_write_attempt_count",
    "opensearch_write_attempt_count",
    "opensearch_upload_attempt_count",
    "write_attempt_count",
    "unsafe_record_count",
]

QUALITY_COUNTER_KEYS = [
    "unsupported_claim_count",
    "summary_used_as_proof_count",
    "invalid_answer_citation_count",
    "llava_only_part_identity_claim_count",
]


def _to_path(value: Any) -> Path:
    return value if isinstance(value, Path) else Path(str(value))


def _read_json(path: Any) -> Dict[str, Any]:
    p = _to_path(path)
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected object JSON at {p}")
    return data


def _write_json(path: Any, data: Mapping[str, Any]) -> None:
    p = _to_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _slug(text: str, max_len: int = 64) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", str(text or "").strip().lower()).strip("_")
    return (slug or "question")[:max_len]



def _eval_run_task_hint(question: str) -> str:
    """Return a short stable hint for H6 eval run folders.

    The full question remains inside the JSON record; the folder name is kept
    intentionally short to avoid Windows MAX_PATH failures in nested stage
    outputs such as trace_net_engineering_answer_context_pack_v1_quality_check.json.
    """
    q = str(question or "").lower()
    if "why" in q or "missing" in q or "fail" in q or "error" in q:
        return "debug"
    if "compare" in q:
        return "compare"
    if "part number" in q or "find part" in q:
        return "part"
    if "figure" in q or "diagram" in q or "show" in q:
        return "fig"
    return "q"

def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def _get_summary(result: Mapping[str, Any]) -> Dict[str, Any]:
    summary = result.get("summary")
    return summary if isinstance(summary, dict) else {}


def _normalize_path_text(text: str) -> str:
    return str(text or "").replace("\\", "/").lower()


def _infer_failed_stage(error_text: str) -> str:
    lowered = _normalize_path_text(error_text)
    if "/planner/" in lowered or "engineering_query_planner" in lowered:
        return "engineering_query_planner"
    if "/context_pack/" in lowered or "engineering_answer_context_pack" in lowered:
        return "engineering_answer_context_pack"
    if "/composer/" in lowered or "engineering_answer_composer" in lowered:
        return "engineering_answer_composer"
    if "engineering_answer_runner" in lowered:
        return "engineering_answer_runner"
    return "unknown"


def _classify_failure(exc: BaseException) -> Dict[str, str]:
    error_text = f"{type(exc).__name__}: {exc}"
    lowered = _normalize_path_text(error_text)
    failed_stage = _infer_failed_stage(error_text)

    if isinstance(exc, FileNotFoundError) and "quality_check" in lowered:
        failure_type = "missing_stage_quality_check"
        failure_reason = (
            f"{failed_stage} did not produce the expected quality-check artifact. "
            "This is a runner/stage-report plumbing failure, not an unsupported or unsafe answer."
        )
    elif isinstance(exc, FileNotFoundError):
        failure_type = "missing_stage_artifact"
        failure_reason = (
            f"{failed_stage} did not produce an expected artifact path. "
            "The eval harness recorded the failure without treating it as a harmful answer."
        )
    elif isinstance(exc, SystemExit):
        failure_type = "stage_quality_gate_exit"
        failure_reason = (
            f"{failed_stage} exited during a quality gate or required PASS check. "
            "Inspect the stage report for the exact gate failure."
        )
    else:
        failure_type = "runner_exception"
        failure_reason = f"{failed_stage} raised {type(exc).__name__}; inspect traceback_tail for details."

    return {
        "failed_stage": failed_stage,
        "failure_type": failure_type,
        "failure_reason": failure_reason,
    }


def _load_runner_builder() -> Callable[..., Dict[str, Any]]:
    mod = importlib.import_module("tiff.trace_net_engineering_answer_runner_v1")
    for name in RUNNER_FUNCTION_NAMES:
        fn = getattr(mod, name, None)
        if callable(fn):
            return fn
    names = ", ".join(RUNNER_FUNCTION_NAMES)
    raise RuntimeError(f"Could not find H5 runner builder function. Tried: {names}")


def _call_builder(builder: Callable[..., Any], kwargs: Mapping[str, Any]) -> Dict[str, Any]:
    sig = inspect.signature(builder)
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
        filtered = dict(kwargs)
    else:
        filtered = {k: v for k, v in kwargs.items() if k in sig.parameters}
    result = builder(**filtered)
    if result is None:
        raise RuntimeError("H5 runner builder returned None")
    if not isinstance(result, dict):
        raise TypeError(f"H5 runner builder returned {type(result).__name__}, expected dict")
    return result


def _classify_record(question: str, result: Mapping[str, Any], error: str = "") -> Dict[str, Any]:
    summary = _get_summary(result)
    quality_status = str(result.get("quality_status") or summary.get("runner_quality_status") or summary.get("quality_status") or "FAIL")
    ready = bool(summary.get("ready_for_engineering_answer_delivery") or result.get("ready_for_engineering_answer_delivery"))
    passed = quality_status == "PASS" and ready and not error
    answer = str(result.get("answer_text") or result.get("answer") or "")

    record = {
        "question": question,
        "quality_status": quality_status,
        "runner_passed": passed,
        "ready_for_engineering_answer_delivery": ready,
        "task_type": summary.get("task_type"),
        "stage_pass_count": _safe_int(summary.get("stage_pass_count")),
        "proof_context_count": _safe_int(summary.get("proof_context_count")),
        "answer_citation_count": _safe_int(summary.get("answer_citation_count")),
        "valid_answer_citation_count": _safe_int(summary.get("valid_answer_citation_count")),
        "source_trace_ready_citation_count": _safe_int(summary.get("source_trace_ready_citation_count")),
        "answer_preview": answer[:800],
        "runner_report_path": str(result.get("runner") or result.get("path") or ""),
        "stage_reports": result.get("stage_reports", {}),
        "error": error,
        "failed_stage": result.get("failed_stage", ""),
        "failure_type": result.get("failure_type", ""),
        "failure_reason": result.get("failure_reason", ""),
    }
    for key in SAFETY_COUNTER_KEYS + QUALITY_COUNTER_KEYS:
        record[key] = _safe_int(summary.get(key, result.get(key, 0)))
    return record


def _sum(records: Sequence[Mapping[str, Any]], key: str) -> int:
    return sum(_safe_int(r.get(key)) for r in records)


def _make_summary(records: Sequence[Mapping[str, Any]], source_questions: Sequence[str]) -> Dict[str, Any]:
    pass_records = [r for r in records if r.get("runner_passed")]
    summary = {
        "eval_question_count": len(records),
        "source_question_count": len(source_questions),
        "runner_pass_count": len(pass_records),
        "runner_fail_count": len(records) - len(pass_records),
        "runner_plumbing_failure_count": sum(1 for r in records if r.get("failure_type") in {"missing_stage_quality_check", "missing_stage_artifact"}),
        "missing_stage_quality_check_count": sum(1 for r in records if r.get("failure_type") == "missing_stage_quality_check"),
        "stage_quality_gate_exit_count": sum(1 for r in records if r.get("failure_type") == "stage_quality_gate_exit"),
        "runner_exception_count": sum(1 for r in records if r.get("failure_type") == "runner_exception"),
        "stage_pass_count": _sum(records, "stage_pass_count"),
        "proof_context_count": _sum(records, "proof_context_count"),
        "answer_citation_count": _sum(records, "answer_citation_count"),
        "valid_answer_citation_count": _sum(records, "valid_answer_citation_count"),
        "source_trace_ready_citation_count": _sum(records, "source_trace_ready_citation_count"),
        "ready_for_engineering_answer_delivery_count": sum(1 for r in records if r.get("ready_for_engineering_answer_delivery")),
        "answer_permission_count": _sum(records, "answer_permission_count"),
        "source_truth_mutation_allowed_count": _sum(records, "source_truth_mutation_allowed_count"),
        "postgres_write_attempt_count": _sum(records, "postgres_write_attempt_count"),
        "qdrant_write_attempt_count": _sum(records, "qdrant_write_attempt_count"),
        "opensearch_write_attempt_count": _sum(records, "opensearch_write_attempt_count"),
        "opensearch_upload_attempt_count": _sum(records, "opensearch_upload_attempt_count"),
        "write_attempt_count": _sum(records, "write_attempt_count"),
        "unsafe_record_count": _sum(records, "unsafe_record_count"),
        "unsupported_claim_count": _sum(records, "unsupported_claim_count"),
        "summary_used_as_proof_count": _sum(records, "summary_used_as_proof_count"),
        "invalid_answer_citation_count": _sum(records, "invalid_answer_citation_count"),
        "llava_only_part_identity_claim_count": _sum(records, "llava_only_part_identity_claim_count"),
    }
    summary["ready_for_engineering_runner_expansion"] = summary["runner_pass_count"] >= 1
    return summary


def _evaluate_quality(
    summary: Mapping[str, Any],
    *,
    min_eval_questions: int,
    min_runner_passes: int,
    max_unsupported_claims: int,
    max_summary_used_as_proof: int,
    max_invalid_citations: int,
    max_llava_only_part_identity_claims: int,
    max_unsafe: int,
    max_answer_permission: int,
    max_source_truth_mutation_allowed: int,
    max_write_attempts: int,
) -> List[str]:
    failures: List[str] = []
    if _safe_int(summary.get("eval_question_count")) < min_eval_questions:
        failures.append(f"eval_question_count below minimum: {summary.get('eval_question_count')} < {min_eval_questions}")
    if _safe_int(summary.get("runner_pass_count")) < min_runner_passes:
        failures.append(f"runner_pass_count below minimum: {summary.get('runner_pass_count')} < {min_runner_passes}")
    if _safe_int(summary.get("unsupported_claim_count")) > max_unsupported_claims:
        failures.append("unsupported_claim_count above maximum")
    if _safe_int(summary.get("summary_used_as_proof_count")) > max_summary_used_as_proof:
        failures.append("summary_used_as_proof_count above maximum")
    if _safe_int(summary.get("invalid_answer_citation_count")) > max_invalid_citations:
        failures.append("invalid_answer_citation_count above maximum")
    if _safe_int(summary.get("llava_only_part_identity_claim_count")) > max_llava_only_part_identity_claims:
        failures.append("llava_only_part_identity_claim_count above maximum")
    if _safe_int(summary.get("unsafe_record_count")) > max_unsafe:
        failures.append("unsafe_record_count above maximum")
    if _safe_int(summary.get("answer_permission_count")) > max_answer_permission:
        failures.append("answer_permission_count above maximum")
    if _safe_int(summary.get("source_truth_mutation_allowed_count")) > max_source_truth_mutation_allowed:
        failures.append("source_truth_mutation_allowed_count above maximum")
    if _safe_int(summary.get("write_attempt_count")) > max_write_attempts:
        failures.append("write_attempt_count above maximum")
    return failures


def _write_csv(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "question",
        "quality_status",
        "runner_passed",
        "task_type",
        "stage_pass_count",
        "proof_context_count",
        "answer_citation_count",
        "source_trace_ready_citation_count",
        "unsupported_claim_count",
        "summary_used_as_proof_count",
        "invalid_answer_citation_count",
        "llava_only_part_identity_claim_count",
        "unsafe_record_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
        "write_attempt_count",
        "failed_stage",
        "failure_type",
        "failure_reason",
        "error",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow({name: record.get(name, "") for name in fieldnames})


def build_engineering_runner_eval_set(
    *,
    questions: Optional[Sequence[str]] = None,
    v2_summary_guidance_index: Any,
    image_visual_evidence_pack: Any,
    raw_ocr_nomenclature_extractor: Any,
    table_route_evidence_packager: Any,
    table_exact_search_adapter: Any,
    output_dir: Any,
    max_guidance_pages: int = 8,
    min_eval_questions: int = 1,
    min_runner_passes: int = 1,
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
    runner_builder: Optional[Callable[..., Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    source_questions = list(questions or DEFAULT_QUESTIONS)
    out_dir = _to_path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    runs_dir = out_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    builder = runner_builder or _load_runner_builder()

    records: List[Dict[str, Any]] = []
    for idx, question in enumerate(source_questions, start=1):
        question_hash = hashlib.sha1(str(question or "").encode("utf-8")).hexdigest()[:8]
        task_hint = _eval_run_task_hint(str(question or ""))
        run_dir = runs_dir / f"q{idx:02d}_{task_hint}_{question_hash}"
        run_dir.mkdir(parents=True, exist_ok=True)
        try:
            result = _call_builder(builder, {
                "question": question,
                "v2_summary_guidance_index": _to_path(v2_summary_guidance_index),
                "image_visual_evidence_pack": _to_path(image_visual_evidence_pack),
                "raw_ocr_nomenclature_extractor": _to_path(raw_ocr_nomenclature_extractor),
                "table_route_evidence_packager": _to_path(table_route_evidence_packager),
                "table_exact_search_adapter": _to_path(table_exact_search_adapter),
                "output_dir": run_dir,
                "max_guidance_pages": max_guidance_pages,
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
                "require_engineering_answer_ready": False,
            })
            record = _classify_record(question, result)
        except Exception as exc:
            failure = _classify_failure(exc)
            failure_result = {"quality_status": "FAIL", "summary": {}, **failure}
            record = _classify_record(question, failure_result, error=f"{type(exc).__name__}: {exc}")
            record["traceback_tail"] = "\n".join(traceback.format_exc().splitlines()[-12:])
        record["eval_index"] = idx
        record["run_output_dir"] = str(run_dir)
        records.append(record)

    summary = _make_summary(records, source_questions)
    failures = _evaluate_quality(
        summary,
        min_eval_questions=min_eval_questions,
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
    quality_status = "PASS" if not failures else "FAIL"

    manifest = {
        "status": STATUS,
        "quality_status": quality_status,
        "version": VERSION,
        "module": "trace_net_engineering_runner_eval_set_v1",
        "summary": summary,
        "failures": failures,
        "records": records,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
    }

    manifest_path = out_dir / "trace_net_engineering_runner_eval_set_v1.json"
    _write_json(manifest_path, manifest)
    _write_json(out_dir / "trace_net_engineering_runner_eval_set_v1_quality_check.json", {
        "status": CHECK_STATUS,
        "quality_status": quality_status,
        "summary": summary,
        "failures": failures,
    })
    _write_csv(out_dir / "trace_net_engineering_runner_eval_set_v1_records.csv", records)

    if require_quality_pass and quality_status != "PASS":
        raise SystemExit("quality_status is not PASS")
    return manifest


def check_engineering_runner_eval_set(
    *,
    eval_set: Any,
    output: Any,
    require_quality_pass: bool = False,
    min_eval_questions: int = 1,
    min_runner_passes: int = 1,
    max_unsupported_claims: int = 0,
    max_summary_used_as_proof: int = 0,
    max_invalid_citations: int = 0,
    max_llava_only_part_identity_claims: int = 0,
    max_unsafe: int = 0,
    max_answer_permission: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    max_write_attempts: int = 0,
) -> Dict[str, Any]:
    data = _read_json(eval_set)
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    failures = []
    if data.get("quality_status") != "PASS":
        failures.append("quality_status is not PASS")
    failures.extend(_evaluate_quality(
        summary,
        min_eval_questions=min_eval_questions,
        min_runner_passes=min_runner_passes,
        max_unsupported_claims=max_unsupported_claims,
        max_summary_used_as_proof=max_summary_used_as_proof,
        max_invalid_citations=max_invalid_citations,
        max_llava_only_part_identity_claims=max_llava_only_part_identity_claims,
        max_unsafe=max_unsafe,
        max_answer_permission=max_answer_permission,
        max_source_truth_mutation_allowed=max_source_truth_mutation_allowed,
        max_write_attempts=max_write_attempts,
    ))
    quality_status = "PASS" if not failures else "FAIL"
    report = {
        "status": CHECK_STATUS,
        "quality_status": quality_status,
        "summary": summary,
        "failures": failures,
    }
    _write_json(output, report)
    if require_quality_pass and quality_status != "PASS":
        raise SystemExit("quality_status is not PASS")
    return report


def _add_threshold_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--min-eval-questions", type=int, default=1)
    parser.add_argument("--min-runner-passes", type=int, default=1)
    parser.add_argument("--max-unsupported-claims", type=int, default=0)
    parser.add_argument("--max-summary-used-as-proof", type=int, default=0)
    parser.add_argument("--max-invalid-citations", type=int, default=0)
    parser.add_argument("--max-llava-only-part-identity-claims", type=int, default=0)
    parser.add_argument("--max-unsafe", type=int, default=0)
    parser.add_argument("--max-answer-permission", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--max-write-attempts", type=int, default=0)


def build_parser(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build TRACE-Net engineering runner evaluation set v1")
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
    parser.add_argument("--require-quality-pass", action="store_true")
    _add_threshold_args(parser)
    return parser.parse_args(argv)


def check_parser(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check TRACE-Net engineering runner evaluation set v1")
    parser.add_argument("--eval-set", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--require-quality-pass", action="store_true")
    _add_threshold_args(parser)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser(argv)
    manifest = build_engineering_runner_eval_set(
        questions=args.questions or None,
        v2_summary_guidance_index=args.v2_summary_guidance_index,
        image_visual_evidence_pack=args.image_visual_evidence_pack,
        raw_ocr_nomenclature_extractor=args.raw_ocr_nomenclature_extractor,
        table_route_evidence_packager=args.table_route_evidence_packager,
        table_exact_search_adapter=args.table_exact_search_adapter,
        output_dir=args.output_dir,
        max_guidance_pages=args.max_guidance_pages,
        min_eval_questions=args.min_eval_questions,
        min_runner_passes=args.min_runner_passes,
        min_planner_records=args.min_planner_records,
        min_required_routes=args.min_required_routes,
        min_guidance_context=args.min_guidance_context,
        min_proof_context=args.min_proof_context,
        min_source_trace_ready=args.min_source_trace_ready,
        min_answer_citations=args.min_answer_citations,
        min_source_trace_ready_citations=args.min_source_trace_ready_citations,
        max_unsupported_claims=args.max_unsupported_claims,
        max_summary_used_as_proof=args.max_summary_used_as_proof,
        max_invalid_citations=args.max_invalid_citations,
        max_llava_only_part_identity_claims=args.max_llava_only_part_identity_claims,
        max_unsafe=args.max_unsafe,
        max_answer_permission=args.max_answer_permission,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        max_write_attempts=args.max_write_attempts,
        require_quality_pass=args.require_quality_pass,
    )
    s = manifest["summary"]
    print(f"status={manifest['status']}")
    print(f"quality_status={manifest['quality_status']}")
    print(f"eval_question_count={s.get('eval_question_count')}")
    print(f"runner_pass_count={s.get('runner_pass_count')}")
    print(f"runner_fail_count={s.get('runner_fail_count')}")
    print(f"runner_plumbing_failure_count={s.get('runner_plumbing_failure_count')}")
    print(f"missing_stage_quality_check_count={s.get('missing_stage_quality_check_count')}")
    print(f"answer_citation_count={s.get('answer_citation_count')}")
    print(f"source_trace_ready_citation_count={s.get('source_trace_ready_citation_count')}")
    print(f"summary_used_as_proof_count={s.get('summary_used_as_proof_count')}")
    print(f"unsupported_claim_count={s.get('unsupported_claim_count')}")
    print(f"eval_set={Path(args.output_dir) / 'trace_net_engineering_runner_eval_set_v1.json'}")
    return 0


def check_main(argv: Optional[Sequence[str]] = None) -> int:
    args = check_parser(argv)
    report = check_engineering_runner_eval_set(
        eval_set=args.eval_set,
        output=args.output,
        require_quality_pass=args.require_quality_pass,
        min_eval_questions=args.min_eval_questions,
        min_runner_passes=args.min_runner_passes,
        max_unsupported_claims=args.max_unsupported_claims,
        max_summary_used_as_proof=args.max_summary_used_as_proof,
        max_invalid_citations=args.max_invalid_citations,
        max_llava_only_part_identity_claims=args.max_llava_only_part_identity_claims,
        max_unsafe=args.max_unsafe,
        max_answer_permission=args.max_answer_permission,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        max_write_attempts=args.max_write_attempts,
    )
    s = report["summary"]
    print(f"status={report['status']}")
    print(f"quality_status={report['quality_status']}")
    print(f"eval_question_count={s.get('eval_question_count')}")
    print(f"runner_pass_count={s.get('runner_pass_count')}")
    print(f"runner_fail_count={s.get('runner_fail_count')}")
    print(f"runner_plumbing_failure_count={s.get('runner_plumbing_failure_count')}")
    print(f"missing_stage_quality_check_count={s.get('missing_stage_quality_check_count')}")
    print(f"summary_used_as_proof_count={s.get('summary_used_as_proof_count')}")
    print(f"unsupported_claim_count={s.get('unsupported_claim_count')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
