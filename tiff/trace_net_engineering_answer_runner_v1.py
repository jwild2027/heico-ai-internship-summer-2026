from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from tiff.trace_net_engineering_query_planner_v1 import build_engineering_query_planner
from tiff.trace_net_engineering_answer_context_pack_v1 import build_engineering_answer_context_pack
from tiff.trace_net_engineering_answer_composer_v1 import build_engineering_answer_composer

VERSION = "v1"
MODULE = "trace_net_engineering_answer_runner_v1"
STATUS_BUILT = "TRACE_NET_ENGINEERING_ANSWER_RUNNER_BUILT"
STATUS_CHECKED = "TRACE_NET_ENGINEERING_ANSWER_RUNNER_QUALITY_CHECKED"


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


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _stage_status(stage: Optional[Mapping[str, Any]]) -> str:
    if not isinstance(stage, Mapping):
        return "MISSING"
    return str(stage.get("quality_status") or "UNKNOWN")


def _first_record(manifest: Mapping[str, Any]) -> Dict[str, Any]:
    records = manifest.get("records")
    if isinstance(records, list) and records and isinstance(records[0], dict):
        return dict(records[0])
    return {}


def _answer_text(composer: Mapping[str, Any]) -> str:
    return str(composer.get("answer_text") or "")


def _quality_status(summary: Mapping[str, Any], *, require_quality_pass: bool, require_engineering_answer_ready: bool, min_stage_passes: int, min_answer_citations: int, min_source_trace_ready_citations: int, max_unsupported_claims: int, max_summary_used_as_proof: int, max_invalid_citations: int, max_llava_only_part_identity_claims: int, max_unsafe: int, max_answer_permission: int, max_source_truth_mutation_allowed: int, max_write_attempts: int) -> Tuple[str, List[str]]:
    failures: List[str] = []
    if require_quality_pass and str(summary.get("runner_quality_status")) != "PASS":
        failures.append("runner_quality_status is not PASS")
    if require_engineering_answer_ready and not bool(summary.get("ready_for_engineering_answer_delivery")):
        failures.append("ready_for_engineering_answer_delivery is not true")
    if _safe_int(summary.get("stage_pass_count")) < min_stage_passes:
        failures.append(f"stage_pass_count below minimum: {summary.get('stage_pass_count')} < {min_stage_passes}")
    if _safe_int(summary.get("answer_citation_count")) < min_answer_citations:
        failures.append(f"answer_citation_count below minimum: {summary.get('answer_citation_count')} < {min_answer_citations}")
    if _safe_int(summary.get("source_trace_ready_citation_count")) < min_source_trace_ready_citations:
        failures.append("source_trace_ready_citation_count below minimum")
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
    return ("PASS" if not failures else "FAIL", failures)


def build_engineering_answer_runner(
    *,
    question: str,
    v2_summary_guidance_index: Any,
    output_dir: Any,
    image_visual_evidence_pack: Optional[Any] = None,
    raw_ocr_nomenclature_extractor: Optional[Any] = None,
    table_route_evidence_packager: Optional[Any] = None,
    table_exact_search_adapter: Optional[Any] = None,
    max_guidance_pages: int = 8,
    min_planner_records: int = 1,
    min_required_routes: int = 1,
    min_guidance_context: int = 0,
    min_proof_context: int = 1,
    min_source_trace_ready: int = 1,
    min_answer_citations: int = 1,
    min_source_trace_ready_citations: int = 1,
    max_unsupported_claims: int = 0,
    max_summary_used_as_proof: int = 0,
    max_invalid_citations: int = 0,
    max_llava_only_part_identity_claims: int = 0,
    max_unsafe: int = 0,
    max_answer_permission: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    max_write_attempts: int = 0,
    require_quality_pass: bool = False,
    require_engineering_answer_ready: bool = False,
) -> Dict[str, Any]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    planner_dir = out_dir / "planner"
    context_dir = out_dir / "context_pack"
    composer_dir = out_dir / "composer"

    planner = build_engineering_query_planner(
        question=question,
        v2_summary_guidance_index=v2_summary_guidance_index,
        output_dir=planner_dir,
        max_guidance_pages=max_guidance_pages,
        min_planner_records=min_planner_records,
        min_required_routes=min_required_routes,
        max_unsafe=max_unsafe,
        max_answer_permission=max_answer_permission,
        max_source_truth_mutation_allowed=max_source_truth_mutation_allowed,
        max_write_attempts=max_write_attempts,
    )
    planner_path = planner.get("paths", {}).get("planner") or str(planner_dir / "trace_net_engineering_query_planner_v1.json")

    context_pack = build_engineering_answer_context_pack(
        engineering_query_planner=planner_path,
        v2_summary_guidance_index=v2_summary_guidance_index,
        image_visual_evidence_pack=image_visual_evidence_pack,
        raw_ocr_nomenclature_extractor=raw_ocr_nomenclature_extractor,
        table_route_evidence_packager=table_route_evidence_packager,
        table_exact_search_adapter=table_exact_search_adapter,
        output_dir=context_dir,
        min_guidance_context=min_guidance_context,
        min_proof_context=min_proof_context,
        min_source_trace_ready=min_source_trace_ready,
        max_unsafe=max_unsafe,
        max_answer_permission=max_answer_permission,
        max_source_truth_mutation_allowed=max_source_truth_mutation_allowed,
        max_write_attempts=max_write_attempts,
    )
    context_pack_path = context_pack.get("paths", {}).get("context_pack") or str(context_dir / "trace_net_engineering_answer_context_pack_v1.json")

    composer = build_engineering_answer_composer(
        context_pack=context_pack_path,
        output_dir=composer_dir,
        min_answer_citations=min_answer_citations,
        min_source_trace_ready_citations=min_source_trace_ready_citations,
        max_unsupported_claims=max_unsupported_claims,
        max_summary_used_as_proof=max_summary_used_as_proof,
        max_invalid_citations=max_invalid_citations,
        max_llava_only_part_identity_claims=max_llava_only_part_identity_claims,
        max_unsafe=max_unsafe,
        max_answer_permission=max_answer_permission,
        max_source_truth_mutation_allowed=max_source_truth_mutation_allowed,
        max_write_attempts=max_write_attempts,
    )
    composer_path = str(composer_dir / "trace_net_engineering_answer_composer_v1.json")

    planner_record = _first_record(planner)
    composer_summary = composer.get("summary", {}) if isinstance(composer.get("summary"), dict) else {}
    context_summary = context_pack.get("summary", {}) if isinstance(context_pack.get("summary"), dict) else {}
    planner_summary = planner.get("summary", {}) if isinstance(planner.get("summary"), dict) else {}

    stage_quality_statuses = {
        "engineering_query_planner": _stage_status(planner),
        "engineering_answer_context_pack": _stage_status(context_pack),
        "engineering_answer_composer": _stage_status(composer),
    }
    stage_pass_count = sum(1 for v in stage_quality_statuses.values() if v == "PASS")

    summary = {
        "runner_record_count": 1,
        "question": question,
        "task_type": planner_record.get("task_type"),
        "engineering_intent": planner_record.get("engineering_intent"),
        "required_route_count": len(planner_record.get("required_routes") or []),
        "selected_guidance_page_count": planner_summary.get("selected_guidance_page_count", 0),
        "guidance_context_count": context_summary.get("guidance_context_count", 0),
        "proof_context_count": context_summary.get("proof_context_count", 0),
        "summary_used_as_proof_count": composer_summary.get("summary_used_as_proof_count", context_summary.get("summary_used_as_proof_count", 0)),
        "answer_citation_count": composer_summary.get("answer_citation_count", 0),
        "valid_answer_citation_count": composer_summary.get("valid_answer_citation_count", 0),
        "source_trace_ready_citation_count": composer_summary.get("source_trace_ready_citation_count", 0),
        "invalid_answer_citation_count": composer_summary.get("invalid_answer_citation_count", 0),
        "unsupported_claim_count": composer_summary.get("unsupported_claim_count", 0),
        "llava_only_part_identity_claim_count": composer_summary.get("llava_only_part_identity_claim_count", 0),
        "stage_count": 3,
        "stage_pass_count": stage_pass_count,
        "stage_quality_statuses": stage_quality_statuses,
        "ready_for_engineering_context_pack": bool(planner_summary.get("ready_for_engineering_context_pack")),
        "ready_for_engineering_answer_composer": bool(context_summary.get("ready_for_engineering_answer_composer")),
        "ready_for_engineering_answer_delivery": bool(composer_summary.get("ready_for_engineering_answer_delivery")),
        "answer_permission_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "opensearch_upload_attempt_count": 0,
        "write_attempt_count": 0,
        "unsafe_record_count": 0,
    }
    # Stage failures are runner failures even before threshold checks.
    stage_failures = [f"{name} quality_status is {status}" for name, status in stage_quality_statuses.items() if status != "PASS"]
    provisional_status = "PASS" if not stage_failures else "FAIL"
    summary["runner_quality_status"] = provisional_status
    quality, threshold_failures = _quality_status(
        summary,
        require_quality_pass=require_quality_pass,
        require_engineering_answer_ready=require_engineering_answer_ready,
        min_stage_passes=3,
        min_answer_citations=min_answer_citations,
        min_source_trace_ready_citations=min_source_trace_ready_citations,
        max_unsupported_claims=max_unsupported_claims,
        max_summary_used_as_proof=max_summary_used_as_proof,
        max_invalid_citations=max_invalid_citations,
        max_llava_only_part_identity_claims=max_llava_only_part_identity_claims,
        max_unsafe=max_unsafe,
        max_answer_permission=max_answer_permission,
        max_source_truth_mutation_allowed=max_source_truth_mutation_allowed,
        max_write_attempts=max_write_attempts,
    )
    failures = stage_failures + [f for f in threshold_failures if f not in stage_failures]
    quality = "PASS" if not failures else "FAIL"
    summary["runner_quality_status"] = quality

    manifest_path = out_dir / f"{MODULE}.json"
    quality_path = out_dir / f"{MODULE}_quality_check.json"
    result = {
        "status": STATUS_BUILT,
        "module": MODULE,
        "version": VERSION,
        "quality_status": quality,
        "question": question,
        "answer_text": _answer_text(composer),
        "summary": summary,
        "failures": failures,
        "records": [{
            "question": question,
            "task_type": planner_record.get("task_type"),
            "engineering_intent": planner_record.get("engineering_intent"),
            "entities": planner_record.get("entities", {}),
            "required_routes": planner_record.get("required_routes", []),
            "optional_routes": planner_record.get("optional_routes", []),
            "stage_reports": {
                "engineering_query_planner": planner_path,
                "engineering_answer_context_pack": context_pack_path,
                "engineering_answer_composer": composer_path,
            },
            "answer_text": _answer_text(composer),
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
            "unsafe": False,
        }],
        "stage_reports": {
            "engineering_query_planner": planner_path,
            "engineering_answer_context_pack": context_pack_path,
            "engineering_answer_composer": composer_path,
        },
        "paths": {
            "runner": str(manifest_path),
            "quality_check": str(quality_path),
            "planner": planner_path,
            "context_pack": context_pack_path,
            "composer": composer_path,
        },
        "safety_contract": {
            "postgres_write_allowed": False,
            "qdrant_write_allowed": False,
            "opensearch_write_allowed": False,
            "opensearch_upload_allowed": False,
            "source_truth_mutation_allowed": False,
            "answer_permission": False,
        },
    }
    _write_json(manifest_path, result)
    _write_json(quality_path, {
        "status": STATUS_CHECKED,
        "module": MODULE,
        "version": VERSION,
        "quality_status": quality,
        "summary": summary,
        "failures": failures,
        "source_runner": str(manifest_path),
    })
    return result


def check_engineering_answer_runner(
    *,
    runner: Any,
    output: Any,
    require_quality_pass: bool = False,
    require_engineering_answer_ready: bool = False,
    min_stage_passes: int = 3,
    min_answer_citations: int = 1,
    min_source_trace_ready_citations: int = 1,
    max_unsupported_claims: int = 0,
    max_summary_used_as_proof: int = 0,
    max_invalid_citations: int = 0,
    max_llava_only_part_identity_claims: int = 0,
    max_unsafe: int = 0,
    max_answer_permission: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    max_write_attempts: int = 0,
) -> Dict[str, Any]:
    data = _load_json(runner)
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    quality, failures = _quality_status(
        summary,
        require_quality_pass=require_quality_pass,
        require_engineering_answer_ready=require_engineering_answer_ready,
        min_stage_passes=min_stage_passes,
        min_answer_citations=min_answer_citations,
        min_source_trace_ready_citations=min_source_trace_ready_citations,
        max_unsupported_claims=max_unsupported_claims,
        max_summary_used_as_proof=max_summary_used_as_proof,
        max_invalid_citations=max_invalid_citations,
        max_llava_only_part_identity_claims=max_llava_only_part_identity_claims,
        max_unsafe=max_unsafe,
        max_answer_permission=max_answer_permission,
        max_source_truth_mutation_allowed=max_source_truth_mutation_allowed,
        max_write_attempts=max_write_attempts,
    )
    if require_quality_pass and data.get("quality_status") != "PASS":
        failures.append("source runner quality_status is not PASS")
    final_quality = "PASS" if not failures else "FAIL"
    result = {
        "status": STATUS_CHECKED,
        "module": MODULE,
        "version": VERSION,
        "quality_status": final_quality,
        "source_runner": str(runner),
        "summary": summary,
        "failures": failures,
    }
    _write_json(output, result)
    return result


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Build TRACE-Net engineering answer runner v1")
    ap.add_argument("--question", required=True)
    ap.add_argument("--v2-summary-guidance-index", required=True)
    ap.add_argument("--image-visual-evidence-pack")
    ap.add_argument("--raw-ocr-nomenclature-extractor")
    ap.add_argument("--table-route-evidence-packager")
    ap.add_argument("--table-exact-search-adapter")
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--max-guidance-pages", type=int, default=8)
    ap.add_argument("--min-planner-records", type=int, default=1)
    ap.add_argument("--min-required-routes", type=int, default=1)
    ap.add_argument("--min-guidance-context", type=int, default=0)
    ap.add_argument("--min-proof-context", type=int, default=1)
    ap.add_argument("--min-source-trace-ready", type=int, default=1)
    ap.add_argument("--min-answer-citations", type=int, default=1)
    ap.add_argument("--min-source-trace-ready-citations", type=int, default=1)
    ap.add_argument("--max-unsupported-claims", type=int, default=0)
    ap.add_argument("--max-summary-used-as-proof", type=int, default=0)
    ap.add_argument("--max-invalid-citations", type=int, default=0)
    ap.add_argument("--max-llava-only-part-identity-claims", type=int, default=0)
    ap.add_argument("--max-unsafe", type=int, default=0)
    ap.add_argument("--max-answer-permission", type=int, default=0)
    ap.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    ap.add_argument("--max-write-attempts", type=int, default=0)
    ap.add_argument("--require-quality-pass", action="store_true")
    ap.add_argument("--require-engineering-answer-ready", action="store_true")
    return ap


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    result = build_engineering_answer_runner(**vars(args))
    s = result.get("summary", {})
    print(f"status={result.get('status')}")
    print(f"quality_status={result.get('quality_status')}")
    print(f"task_type={s.get('task_type')}")
    print(f"stage_pass_count={s.get('stage_pass_count')}")
    print(f"guidance_context_count={s.get('guidance_context_count')}")
    print(f"proof_context_count={s.get('proof_context_count')}")
    print(f"answer_citation_count={s.get('answer_citation_count')}")
    print(f"source_trace_ready_citation_count={s.get('source_trace_ready_citation_count')}")
    print(f"summary_used_as_proof_count={s.get('summary_used_as_proof_count')}")
    print(f"unsupported_claim_count={s.get('unsupported_claim_count')}")
    print(f"ready_for_engineering_answer_delivery={s.get('ready_for_engineering_answer_delivery')}")
    print(f"unsafe_record_count={s.get('unsafe_record_count')}")
    print(f"answer_permission_count={s.get('answer_permission_count')}")
    print(f"source_truth_mutation_allowed_count={s.get('source_truth_mutation_allowed_count')}")
    print(f"write_attempt_count={s.get('write_attempt_count')}")
    print(f"answer={result.get('answer_text')}")
    print(f"runner={result.get('paths', {}).get('runner')}")
    return 0 if result.get("quality_status") == "PASS" else 1


def _check_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Check TRACE-Net engineering answer runner v1")
    ap.add_argument("--runner", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--require-quality-pass", action="store_true")
    ap.add_argument("--require-engineering-answer-ready", action="store_true")
    ap.add_argument("--min-stage-passes", type=int, default=3)
    ap.add_argument("--min-answer-citations", type=int, default=1)
    ap.add_argument("--min-source-trace-ready-citations", type=int, default=1)
    ap.add_argument("--max-unsupported-claims", type=int, default=0)
    ap.add_argument("--max-summary-used-as-proof", type=int, default=0)
    ap.add_argument("--max-invalid-citations", type=int, default=0)
    ap.add_argument("--max-llava-only-part-identity-claims", type=int, default=0)
    ap.add_argument("--max-unsafe", type=int, default=0)
    ap.add_argument("--max-answer-permission", type=int, default=0)
    ap.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    ap.add_argument("--max-write-attempts", type=int, default=0)
    return ap


def check_main(argv: Optional[Sequence[str]] = None) -> int:
    args = _check_parser().parse_args(argv)
    result = check_engineering_answer_runner(**vars(args))
    s = result.get("summary", {})
    print(f"status={result.get('status')}")
    print(f"quality_status={result.get('quality_status')}")
    print(f"stage_pass_count={s.get('stage_pass_count')}")
    print(f"answer_citation_count={s.get('answer_citation_count')}")
    print(f"source_trace_ready_citation_count={s.get('source_trace_ready_citation_count')}")
    print(f"summary_used_as_proof_count={s.get('summary_used_as_proof_count')}")
    print(f"unsupported_claim_count={s.get('unsupported_claim_count')}")
    print(f"ready_for_engineering_answer_delivery={s.get('ready_for_engineering_answer_delivery')}")
    print(f"unsafe_record_count={s.get('unsafe_record_count')}")
    print(f"answer_permission_count={s.get('answer_permission_count')}")
    print(f"source_truth_mutation_allowed_count={s.get('source_truth_mutation_allowed_count')}")
    print(f"write_attempt_count={s.get('write_attempt_count')}")
    return 0 if result.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
