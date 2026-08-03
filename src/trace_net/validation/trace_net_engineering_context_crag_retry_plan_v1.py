
"""TRACE-Net Engineering Context CRAG Retry Plan v1.

Builds corrective retrieval/repackaging plans for engineering context packs that
failed Self-RAG checks.

v1.1:
- avoids duplicate retry actions when both structured missing notes and reason
  strings describe the same gap
- suppresses target_route="unknown" when the same missing type already has a
  structured routed action
- adds unknown_target_route_count quality visibility

Safety:
- no LLM calls
- no live retrieval execution
- no DB/search/vector writes
- no source-truth mutation
- no answer permission
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


MODULE_VERSION = "trace_net_engineering_context_crag_retry_plan_v1"
REPORT_NAME = "trace_net_engineering_context_crag_retry_plan_v1.json"


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


def _seed_terms(record: Mapping[str, Any]) -> List[str]:
    """Extract useful question terms from the Self-RAG record without inventing facts."""
    question = str(record.get("user_question") or "")
    seeds: List[str] = []
    import re
    for token in re.findall(r"\b[A-Za-z]?\d{2,}(?:[-_][A-Za-z0-9]{1,})+\b", question):
        if token not in seeds:
            seeds.append(token)
    for term in (
        "dimension", "length", "shorter", "longer", "width", "height", "diameter",
        "warning", "caution", "clean", "cleaning", "solvent", "callout", "figure",
        "visual", "diagram", "part", "nomenclature", "assembly",
    ):
        if term.lower() in question.lower() and term not in seeds:
            seeds.append(term)
    return seeds[:12]


def _retry_action_for_missing(
    *,
    missing_type: str,
    route: Optional[str],
    record: Mapping[str, Any],
) -> Dict[str, Any]:
    intent = record.get("intent_family")
    seeds = _seed_terms(record)
    question = str(record.get("user_question") or "")

    base = {
        "missing_type": missing_type,
        "source_route": route,
        "intent_family": intent,
        "question_terms": seeds,
        "execution_allowed": False,
        "db_write_allowed": False,
        "answer_permission": False,
    }

    if missing_type == "source_dimension_not_confirmed":
        base.update({
            "retry_action_id": "retry_table_dimension_evidence",
            "target_route": "table",
            "target_artifacts": [
                "table_exact_search_adapter",
                "table_route_evidence_package",
                "source_normalized_table_value_records",
                "promoted_table_value_evidence",
            ],
            "query_hints": [
                question,
                " ".join(seeds + ["dimension", "length", "inch", "inches", "mm", "cm"]),
                "same part family dash number variant dimension length",
                "IPL table dimensions repair material part number",
            ],
            "success_conditions": [
                "at least one table/source record contains the seed entity or same-family candidate",
                "selected evidence contains a dimension/length/size term",
                "page_id/source_trace is present",
                "context pack no longer reports source_dimension_not_confirmed",
            ],
            "fallback_if_still_missing": "mark dimensional-change answer as candidate-only with missing dimension proof; do not allow fit/modification claim",
        })
    elif missing_type == "warning_caution_not_confirmed":
        base.update({
            "retry_action_id": "retry_warning_caution_procedure_evidence",
            "target_route": "normal_text",
            "target_artifacts": [
                "page_context_v2",
                "normal_text_handoff",
                "fishnet OCR text",
            ],
            "query_hints": [
                question,
                " ".join(seeds + ["WARNING", "CAUTION", "NOTE"]),
                "cleaning solvent warning caution procedure",
                "cleaners toxic ingredients gloves skin eyes",
            ],
            "success_conditions": [
                "normal_text/page_context evidence includes WARNING, CAUTION, or NOTE when present",
                "selected evidence has source page trace",
                "procedure context is source-backed before Gemma draft",
            ],
            "fallback_if_still_missing": "answer must say warning/caution evidence was not confirmed and avoid procedural instruction",
        })
    elif missing_type == "route_slot_unfilled" and route == "image_visual":
        base.update({
            "retry_action_id": "retry_image_visual_route_evidence",
            "target_route": "image_visual",
            "target_artifacts": [
                "image_visual_observer_route",
                "image_visual_handoff",
                "callout_candidates",
                "visual_part_verification_records",
            ],
            "query_hints": [
                question,
                " ".join(seeds + ["figure", "callout", "visual", "diagram"]),
                "same figure callout neighboring parts visual similarity",
            ],
            "success_conditions": [
                "image_visual artifact exists and is parsed",
                "at least one image/callout capsule is selected",
                "visual-only evidence remains candidate-only",
            ],
            "fallback_if_still_missing": "continue without image evidence only for non-visual questions; visual-similarity questions remain not draft-ready",
        })
    elif missing_type == "route_slot_unfilled":
        target = route or "unknown"
        base.update({
            "retry_action_id": "retry_unfilled_route_slot",
            "target_route": target,
            "target_artifacts": [
                f"{target}_route_artifacts" if target != "unknown" else "route_artifacts",
            ],
            "query_hints": [
                question,
                " ".join(seeds),
            ],
            "success_conditions": [
                "route slot receives at least one high-signal evidence capsule",
                "capsule has source trace if it supports a factual claim",
            ],
            "fallback_if_still_missing": "keep CRAG retry required or route to review",
        })
    elif missing_type == "exact_source_evidence_missing":
        base.update({
            "retry_action_id": "retry_exact_source_table_evidence",
            "target_route": "table",
            "target_artifacts": [
                "table_exact_search_adapter",
                "promoted_table_value_evidence",
                "table_route_evidence_package",
            ],
            "query_hints": [
                question,
                " ".join(seeds + ["exact", "part", "number", "P/N"]),
            ],
            "success_conditions": [
                "exact source-backed table evidence exists",
                "page_id/source_trace is present",
            ],
            "fallback_if_still_missing": "do not draft exact lookup answer; route to review",
        })
    else:
        target = route or "unknown"
        base.update({
            "retry_action_id": "retry_general_missing_evidence",
            "target_route": target,
            "target_artifacts": [
                "table artifacts",
                "normal_text artifacts",
                "graph artifacts",
                "image_visual artifacts",
            ],
            "query_hints": [
                question,
                " ".join(seeds),
            ],
            "success_conditions": [
                "missing evidence type is resolved or explicitly marked unresolvable",
                "context pack has sufficient source-truth or candidate evidence",
            ],
            "fallback_if_still_missing": "keep pack in review/CRAG state",
        })

    return base


def _structured_missing_keys(record: Mapping[str, Any]) -> List[Tuple[str, Optional[str]]]:
    keys: List[Tuple[str, Optional[str]]] = []
    missing_notes = record.get("missing_evidence") or []
    if isinstance(missing_notes, list):
        for note in missing_notes:
            if not isinstance(note, dict):
                continue
            missing_type = str(note.get("missing_type") or "")
            route = note.get("route")
            if missing_type:
                keys.append((missing_type, route))
    return keys


def _has_structured_key_for_missing(
    *,
    structured_keys: Sequence[Tuple[str, Optional[str]]],
    missing_type: str,
) -> bool:
    return any(key_type == missing_type and route not in (None, "", "unknown") for key_type, route in structured_keys)


def _actions_from_record(record: Mapping[str, Any]) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    emitted_action_keys = set()
    structured_keys = _structured_missing_keys(record)

    # First, use structured missing_evidence notes because they preserve route.
    for missing_type, route in structured_keys:
        key = (missing_type, route)
        if key in emitted_action_keys:
            continue
        emitted_action_keys.add(key)
        actions.append(_retry_action_for_missing(missing_type=missing_type, route=route, record=record))

    # Then parse reason strings only for gaps not already represented structurally.
    for reason in record.get("crag_retry_reasons") or []:
        if not isinstance(reason, str):
            continue
        parts = reason.split(":")
        missing_type: Optional[str] = None
        route: Optional[str] = None

        if reason.startswith("critical_missing:") and len(parts) >= 2:
            missing_type = parts[1]
            route = None
        elif reason.startswith("missing_evidence:") and len(parts) >= 3:
            missing_type = parts[1]
            route = parts[2]
        elif reason == "exact_part_lookup_missing_exact_source_evidence":
            missing_type = "exact_source_evidence_missing"
            route = "table"

        if not missing_type:
            continue

        # If we already have a routed structured action for this missing type,
        # do not add a duplicate unrouteable/unknown action from critical_missing.
        if route in (None, "", "unknown") and _has_structured_key_for_missing(
            structured_keys=structured_keys,
            missing_type=missing_type,
        ):
            continue

        key = (missing_type, route)
        if key in emitted_action_keys:
            continue
        emitted_action_keys.add(key)
        actions.append(_retry_action_for_missing(missing_type=missing_type, route=route, record=record))

    # Final dedupe by actual retry action target/action pair.
    deduped: List[Dict[str, Any]] = []
    seen_action_targets = set()
    for action in actions:
        key = (action.get("retry_action_id"), action.get("target_route"))
        if key in seen_action_targets:
            continue
        seen_action_targets.add(key)
        deduped.append(action)

    return deduped


def _retry_priority(record: Mapping[str, Any], actions: Sequence[Mapping[str, Any]]) -> str:
    score = int(record.get("evidence_strength_score") or 0)
    critical = record.get("critical_missing_evidence_types") or []
    if record.get("intent_family") == "visual_or_callout_similarity" and any(a.get("target_route") == "image_visual" for a in actions):
        return "high"
    if score < 30:
        return "high"
    if critical:
        return "medium"
    return "low"


def build_retry_record(record: Mapping[str, Any], index: int) -> Dict[str, Any]:
    actions = _actions_from_record(record)
    target_routes = sorted(set(str(a.get("target_route")) for a in actions if a.get("target_route")))
    target_artifacts = sorted(set(
        artifact
        for action in actions
        for artifact in action.get("target_artifacts", [])
    ))
    query_hints = []
    seen_hint = set()
    for action in actions:
        for hint in action.get("query_hints", []):
            if hint and hint not in seen_hint:
                seen_hint.add(hint)
                query_hints.append(hint)

    return {
        "crag_retry_plan_version": MODULE_VERSION,
        "crag_retry_plan_id": f"engineering_crag_retry_plan_{index+1:04d}",
        "source_self_rag_record_id": record.get("self_rag_record_id"),
        "context_pack_id": record.get("context_pack_id"),
        "question_id": record.get("question_id"),
        "user_question": record.get("user_question"),
        "intent_family": record.get("intent_family"),
        "selected_playbook_id": record.get("selected_playbook_id"),
        "source_self_rag_status": record.get("self_rag_status"),
        "source_evidence_strength_score": record.get("evidence_strength_score"),
        "source_truth_evidence_strength": record.get("source_truth_evidence_strength"),
        "missing_evidence_types": record.get("missing_evidence_types") or [],
        "critical_missing_evidence_types": record.get("critical_missing_evidence_types") or [],
        "source_crag_retry_reasons": record.get("crag_retry_reasons") or [],
        "retry_priority": _retry_priority(record, actions),
        "target_routes": target_routes,
        "unknown_target_route_count": sum(1 for route in target_routes if route == "unknown"),
        "target_artifacts": target_artifacts,
        "query_hints": query_hints[:20],
        "retry_actions": actions,
        "success_gate": {
            "must_rebuild_context_pack": True,
            "must_rerun_self_rag": True,
            "must_reduce_or_resolve_critical_missing_evidence": True,
            "answer_permission_after_retry": False,
            "can_prove_claims_after_retry": False,
        },
        "plan_status": "crag_retry_plan_ready_no_execution",
        "ready_for_crag_execution": True,
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
        "unsafe": False,
    }


def build_engineering_context_crag_retry_plan(
    *,
    self_rag_report_path: Path,
    output_dir: Path,
) -> Dict[str, Any]:
    self_rag_payload = _read_json(self_rag_report_path)
    source_records = self_rag_payload.get("records") or []
    retry_source_records = [
        record for record in source_records
        if isinstance(record, dict) and record.get("crag_retry_required")
    ]
    records = [
        build_retry_record(record, index)
        for index, record in enumerate(retry_source_records)
    ]

    priority_counts = Counter(record.get("retry_priority") for record in records)
    route_counts = Counter(route for record in records for route in record.get("target_routes", []))
    intent_counts = Counter(record.get("intent_family") for record in records)
    missing_counts = Counter(
        missing
        for record in records
        for missing in record.get("missing_evidence_types", [])
    )

    summary = {
        "source_self_rag_quality_status": self_rag_payload.get("quality_status"),
        "source_self_rag_record_count": len(source_records),
        "source_crag_retry_required_count": len(retry_source_records),
        "crag_retry_plan_count": len(records),
        "ready_for_crag_execution_count": sum(1 for r in records if r.get("ready_for_crag_execution")),
        "retry_priority_counts": dict(sorted(priority_counts.items())),
        "target_route_counts": dict(sorted(route_counts.items())),
        "unknown_target_route_count": sum(r.get("unknown_target_route_count", 0) for r in records),
        "intent_family_counts": dict(sorted(intent_counts.items())),
        "missing_evidence_type_counts": dict(sorted(missing_counts.items())),
        "total_retry_action_count": sum(len(r.get("retry_actions") or []) for r in records),
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
    if self_rag_payload.get("quality_status") != "PASS":
        quality_status = "FAIL"
    if len(records) != int((self_rag_payload.get("summary") or {}).get("crag_retry_required_count", len(records))):
        quality_status = "FAIL"
    if summary["unsafe_record_count"] != 0:
        quality_status = "FAIL"

    payload: Dict[str, Any] = {
        "module": MODULE_VERSION,
        "status": "ENGINEERING_CONTEXT_CRAG_RETRY_PLAN_BUILT",
        "quality_status": quality_status,
        "summary": summary,
        "source_self_rag_report_path": str(self_rag_report_path),
        "records": records,
        "safety_contract": {
            "artifact_authority": "crag_retry_planning_only",
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
    _write_jsonl(output_dir / "trace_net_engineering_context_crag_retry_plan_v1_records.jsonl", records)
    _write_json(output_dir / "trace_net_engineering_context_crag_retry_plan_v1_summary.json", summary)
    _write_json(output_dir / "trace_net_engineering_context_crag_retry_plan_v1_quality.json", {"quality_status": quality_status, "summary": summary})
    _write_markdown(output_dir / "trace_net_engineering_context_crag_retry_plan_v1.md", payload)
    return payload


def _write_markdown(path: Path, payload: Mapping[str, Any]) -> None:
    summary = payload.get("summary") or {}
    lines = [
        "# TRACE-Net Engineering Context CRAG Retry Plan v1.1",
        "",
        f"Quality status: **{payload.get('quality_status')}**",
        "",
        "## Summary",
        "",
        f"- CRAG retry plans: {summary.get('crag_retry_plan_count')}",
        f"- Ready for CRAG execution: {summary.get('ready_for_crag_execution_count')}",
        f"- Retry priority counts: `{summary.get('retry_priority_counts')}`",
        f"- Target route counts: `{summary.get('target_route_counts')}`",
        f"- Unknown target route count: `{summary.get('unknown_target_route_count')}`",
        f"- Missing evidence type counts: `{summary.get('missing_evidence_type_counts')}`",
        "",
        "## Retry plans",
        "",
    ]
    for record in payload.get("records") or []:
        lines.extend([
            f"### {record.get('crag_retry_plan_id')} — {record.get('retry_priority')}",
            "",
            f"- Question: `{record.get('user_question')}`",
            f"- Intent: `{record.get('intent_family')}`",
            f"- Source Self-RAG status: `{record.get('source_self_rag_status')}`",
            f"- Target routes: `{record.get('target_routes')}`",
            f"- Target artifacts: `{record.get('target_artifacts')}`",
            f"- Query hints: `{record.get('query_hints')}`",
            "",
        ])
    path.write_text("\n".join(lines), encoding="utf-8")


def check_engineering_context_crag_retry_plan_quality(
    *,
    report_path: Path,
    require_source_self_rag_quality_pass: bool = False,
    min_crag_retry_plans: int = 1,
    min_retry_actions: int = 1,
    min_ready_for_crag_execution: int = 1,
    max_unknown_target_routes: Optional[int] = None,
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

    if require_source_self_rag_quality_pass:
        fail_if(summary.get("source_self_rag_quality_status") != "PASS", "source Self-RAG quality is not PASS")
    fail_if(summary.get("crag_retry_plan_count", 0) < min_crag_retry_plans, "not enough CRAG retry plans")
    fail_if(summary.get("total_retry_action_count", 0) < min_retry_actions, "not enough retry actions")
    fail_if(summary.get("ready_for_crag_execution_count", 0) < min_ready_for_crag_execution, "not enough plans ready for CRAG execution")
    if max_unknown_target_routes is not None:
        fail_if(summary.get("unknown_target_route_count", 0) > max_unknown_target_routes, "too many unknown target routes")
    fail_if(summary.get("unsafe_record_count", 0) > max_unsafe, "unsafe record count exceeded")
    if require_no_answer_permission:
        fail_if(summary.get("answer_permission_count", 0) != 0, "answer permission count not zero")
        fail_if(summary.get("can_answer_directly_count", 0) != 0, "can answer directly count not zero")
        fail_if(summary.get("can_prove_claims_count", 0) != 0, "can prove claims count not zero")
    if require_no_llm_calls:
        fail_if(summary.get("llm_call_allowed_count", 0) != 0, "LLM call allowed count not zero")
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
    parser = argparse.ArgumentParser(description="Build TRACE-Net engineering context CRAG retry plan v1.")
    parser.add_argument("--self-rag-report", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)

    payload = build_engineering_context_crag_retry_plan(
        self_rag_report_path=Path(args.self_rag_report),
        output_dir=Path(args.output_dir),
    )
    print("Status:", payload["status"])
    print("Quality status:", payload["quality_status"])
    print("Summary:", json.dumps(payload["summary"], sort_keys=True))
    return 0 if payload["quality_status"] == "PASS" else 1


def main_check(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net engineering context CRAG retry plan v1 quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--require-source-self-rag-quality-pass", action="store_true")
    parser.add_argument("--min-crag-retry-plans", type=int, default=1)
    parser.add_argument("--min-retry-actions", type=int, default=1)
    parser.add_argument("--min-ready-for-crag-execution", type=int, default=1)
    parser.add_argument("--max-unknown-target-routes", type=int)
    parser.add_argument("--max-unsafe", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-llm-calls", action="store_true")
    parser.add_argument("--require-no-retrieval-execution", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    args = parser.parse_args(argv)

    result = check_engineering_context_crag_retry_plan_quality(
        report_path=Path(args.report_path),
        require_source_self_rag_quality_pass=args.require_source_self_rag_quality_pass,
        min_crag_retry_plans=args.min_crag_retry_plans,
        min_retry_actions=args.min_retry_actions,
        min_ready_for_crag_execution=args.min_ready_for_crag_execution,
        max_unknown_target_routes=args.max_unknown_target_routes,
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
        out = Path(args.report_path).with_name("trace_net_engineering_context_crag_retry_plan_v1_quality_check.json")
        _write_json(out, result)
        print("Wrote:", out)
    return 0 if result["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main_build())
