
"""TRACE-Net Engineering Context Pack Blueprint v1.

Turns engineering query plans into dynamic context-pack contracts for Gemma/TRACE-Net.

This is the bridge between:
- the engineering brain (playbooks/examples/trust tiers)
- dynamic context engineering (what context to assemble at runtime)
- future retrieval/evidence pack building

Safety:
- does not answer questions
- does not call an LLM
- does not execute retrieval
- does not mutate source truth
- does not write DB/search/vector indexes
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence


MODULE_VERSION = "trace_net_engineering_context_pack_blueprint_v1"
REPORT_NAME = "trace_net_engineering_context_pack_blueprint_v1.json"


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


def _route_slot(route: str, plan: Mapping[str, Any]) -> Dict[str, Any]:
    intent = plan.get("intent_family")
    base = {
        "route": route,
        "required": True,
        "evidence_role": "supporting_context",
        "max_records": 6,
        "trust_tier": "candidate_or_supporting",
        "missing_behavior": "record_missing_evidence_and_continue_to_review",
    }
    if route == "table":
        base.update({
            "evidence_role": "structured_source_truth_or_candidate_table_evidence",
            "max_records": 12 if intent in ("engineering_change_candidate", "exact_part_lookup") else 8,
            "preferred_artifacts": [
                "table_exact_search_adapter",
                "promoted_table_value_evidence",
                "source_normalized_table_value_records",
                "table_route_evidence_package",
            ],
            "trust_tier": "source_truth_if_exact_match_else_candidate",
        })
    elif route == "normal_text":
        base.update({
            "evidence_role": "procedure_description_warning_context",
            "max_records": 8 if intent == "repair_or_fault_context" else 6,
            "preferred_artifacts": [
                "page_context_v2",
                "normal_text_route_handoff",
                "Dublin Core metadata",
            ],
            "trust_tier": "source_context_guidance",
        })
    elif route == "image_visual":
        base.update({
            "evidence_role": "visual_callout_candidate_context",
            "max_records": 8,
            "preferred_artifacts": [
                "image_visual_route_handoff",
                "visual_observer_route",
                "callout_candidates",
                "visual_part_verification_records",
            ],
            "trust_tier": "visual_candidate_only",
        })
    elif route == "graph":
        base.update({
            "evidence_role": "relationship_and_same_family_context",
            "max_records": 20,
            "preferred_artifacts": [
                "postgres_graph_neighbors",
                "Leiden communities",
                "same assembly/entity graph",
            ],
            "trust_tier": "relationship_candidate_until_source_backed",
        })
    elif route == "vector":
        base.update({
            "evidence_role": "semantic_similarity_leads",
            "max_records": 12,
            "preferred_artifacts": [
                "embedded vector DB",
                "semantic similarity candidates",
            ],
            "trust_tier": "semantic_lead_only",
        })
    elif route == "route_dispatch":
        base.update({
            "evidence_role": "route_availability_and_page_type_context",
            "max_records": 10,
            "preferred_artifacts": [
                "fishnet_route_dispatch_handoff",
                "accepted_route_manifest",
            ],
            "trust_tier": "routing_metadata_not_source_truth",
        })
    return base


def _section_contracts(plan: Mapping[str, Any]) -> List[Dict[str, Any]]:
    sections = plan.get("dynamic_context_pack_blueprint", {}).get("sections_in_order") or []
    contracts: List[Dict[str, Any]] = []
    for idx, section in enumerate(sections):
        contract: Dict[str, Any] = {
            "section_index": idx,
            "section_id": section,
            "required": True,
            "max_tokens_hint": 400,
            "source_truth_required": False,
            "may_use_summary_guidance": True,
            "missing_behavior": "include_empty_section_with_reason",
        }
        if section == "system_engineering_role":
            contract.update({
                "purpose": "make Gemma answer as an engineering assistant, not a generic chatbot",
                "max_tokens_hint": 300,
                "source_truth_required": False,
            })
        elif section == "selected_engineering_playbook":
            contract.update({
                "purpose": "inject the engineer-brain reasoning steps for this intent",
                "max_tokens_hint": 900,
                "source_truth_required": False,
            })
        elif section == "few_shot_engineering_examples":
            contract.update({
                "purpose": "show good/bad engineering reasoning examples without changing source truth",
                "max_tokens_hint": 900,
                "source_truth_required": False,
            })
        elif section == "structured_user_intent":
            contract.update({
                "purpose": "make seed entities, requested changes, and question type explicit",
                "max_tokens_hint": 500,
                "source_truth_required": False,
            })
        elif section == "route_handoff_availability":
            contract.update({
                "purpose": "tell the context builder which route queues are available",
                "max_tokens_hint": 400,
                "source_truth_required": False,
            })
        elif section == "source_truth_evidence":
            contract.update({
                "purpose": "source-backed evidence that may support claims",
                "max_tokens_hint": 1800,
                "source_truth_required": True,
                "may_use_summary_guidance": False,
                "missing_behavior": "mark_answer_not_proven_and_trigger_crag_retry",
            })
        elif section == "candidate_evidence":
            contract.update({
                "purpose": "candidate evidence for engineering review only",
                "max_tokens_hint": 1400,
                "source_truth_required": False,
            })
        elif section == "missing_evidence":
            contract.update({
                "purpose": "explicitly list missing proof, dimensions, effectivity, interface, or warnings",
                "max_tokens_hint": 500,
                "source_truth_required": False,
            })
        elif section == "trust_tier_policy":
            contract.update({
                "purpose": "force Gemma to separate exact proof, candidates, and weak leads",
                "max_tokens_hint": 600,
                "source_truth_required": False,
            })
        elif section == "forbidden_claims":
            contract.update({
                "purpose": "block unsafe/unproven engineering claims",
                "max_tokens_hint": 500,
                "source_truth_required": False,
            })
        elif section == "answer_format_contract":
            contract.update({
                "purpose": "shape final answer into source-backed facts, candidates, missing evidence, and review note",
                "max_tokens_hint": 500,
                "source_truth_required": False,
            })
        contracts.append(contract)
    return contracts


def _answer_format_contract(plan: Mapping[str, Any]) -> Dict[str, Any]:
    intent = plan.get("intent_family")
    if intent in ("engineering_change_candidate", "similarity_or_substitution_candidate", "visual_or_callout_similarity"):
        mode = "candidate_for_engineering_review"
    elif intent == "repair_or_fault_context":
        mode = "source_backed_procedure_context"
    elif intent == "exact_part_lookup":
        mode = "exact_evidence_first_then_related_context"
    else:
        mode = "engineering_triage"
    return {
        "answer_mode": mode,
        "required_blocks": [
            "what_is_proven",
            "candidate_or_related_findings",
            "missing_evidence",
            "review_boundary",
            "citations_or_source_trace",
        ],
        "must_not_include": plan.get("forbidden_answer_claims") or [],
        "must_include_if_missing": [
            "dimension_missing",
            "effectivity_missing",
            "interface_or_fit_missing",
            "approval_missing",
        ],
        "final_gate_inputs": [
            "source_truth_evidence",
            "candidate_evidence",
            "missing_evidence",
            "forbidden_claims",
        ],
    }


def _self_rag_crag_contract(plan: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "self_rag_checks": [
            "every factual claim has source evidence or is labeled candidate",
            "candidate claims do not become approved replacement claims",
            "visual-only evidence is not treated as exact proof",
            "semantic-only evidence is not treated as exact proof",
            "repair/procedure claims include warnings/cautions if present",
        ],
        "crag_retry_triggers": [
            "seed entity not resolved",
            "exact table evidence missing for part-number question",
            "dimension requested but source dimension missing",
            "candidate found but no source trace",
            "final answer would rely only on vector/visual similarity",
        ],
        "final_gate_rules": [
            "block answer if source_truth_evidence is empty for exact/procedure claim",
            "allow candidate-only answer only with explicit review language",
            "forbid fit/safety/approval claims unless source explicitly says so",
        ],
    }


def build_context_pack_blueprint_record(plan: Mapping[str, Any], index: int) -> Dict[str, Any]:
    route_needs = plan.get("dynamic_context_pack_blueprint", {}).get("route_context_needed") or []
    route_slots = [_route_slot(route, plan) for route in route_needs]
    section_contracts = _section_contracts(plan)
    source_truth_sections = [s for s in section_contracts if s.get("source_truth_required")]
    forbidden_claims = plan.get("forbidden_answer_claims") or []

    return {
        "context_pack_blueprint_version": MODULE_VERSION,
        "blueprint_id": f"context_pack_blueprint_{index+1:04d}",
        "question_id": plan.get("question_id"),
        "user_question": plan.get("user_question"),
        "intent_family": plan.get("intent_family"),
        "selected_playbook_id": plan.get("selected_playbook_id"),
        "seed_entities": plan.get("seed_entities") or [],
        "requested_change": plan.get("requested_change"),
        "context_pack_status": "blueprint_only_no_retrieval_executed",
        "dynamic_context_role": "assemble_question_specific_engineering_context_for_gemma",
        "engineer_brain_role": "provide_reasoning_playbook_examples_trust_boundaries",
        "section_contracts": section_contracts,
        "route_evidence_slots": route_slots,
        "context_budget": plan.get("dynamic_context_pack_blueprint", {}).get("context_budget") or {},
        "compression_policy": plan.get("dynamic_context_pack_blueprint", {}).get("compression_policy") or {},
        "trust_tier_policy": {
            "exact_source_evidence": "can support factual claim with citation",
            "cross_route_candidate": "candidate for engineering review only",
            "visual_candidate": "visual similarity only, requires table/source cross-check",
            "semantic_candidate": "retrieval lead only",
            "missing_evidence": "state missing proof and do not overclaim",
        },
        "answer_format_contract": _answer_format_contract(plan),
        "self_rag_crag_contract": _self_rag_crag_contract(plan),
        "forbidden_answer_claims": forbidden_claims,
        "source_truth_required_section_count": len(source_truth_sections),
        "route_slot_count": len(route_slots),
        "candidate_language_required": bool(plan.get("evidence_policy", {}).get("candidate_language_required")),
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


def build_engineering_context_pack_blueprint(
    *,
    query_planner_path: Path,
    output_dir: Path,
) -> Dict[str, Any]:
    planner_payload = _read_json(query_planner_path)
    plans = planner_payload.get("records") or []
    records = [
        build_context_pack_blueprint_record(plan, index)
        for index, plan in enumerate(plans)
        if isinstance(plan, dict)
    ]

    route_counts = Counter(
        slot["route"]
        for record in records
        for slot in record.get("route_evidence_slots", [])
    )
    intent_counts = Counter(record.get("intent_family") for record in records)

    summary = {
        "source_query_planner_quality_status": planner_payload.get("quality_status"),
        "source_query_plan_count": len(plans),
        "context_pack_blueprint_count": len(records),
        "intent_family_counts": dict(sorted(intent_counts.items())),
        "route_evidence_slot_counts": dict(sorted(route_counts.items())),
        "blueprints_with_source_truth_required_count": sum(
            1 for r in records if r.get("source_truth_required_section_count", 0) > 0
        ),
        "blueprints_with_candidate_language_required_count": sum(
            1 for r in records if r.get("candidate_language_required")
        ),
        "total_route_evidence_slot_count": sum(r.get("route_slot_count", 0) for r in records),
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
    if planner_payload.get("quality_status") != "PASS":
        quality_status = "FAIL"
    if not records:
        quality_status = "FAIL"
    if summary["unsafe_record_count"] != 0:
        quality_status = "FAIL"

    payload: Dict[str, Any] = {
        "module": MODULE_VERSION,
        "status": "ENGINEERING_CONTEXT_PACK_BLUEPRINT_BUILT",
        "quality_status": quality_status,
        "summary": summary,
        "source_query_planner_path": str(query_planner_path),
        "records": records,
        "safety_contract": {
            "artifact_authority": "context_pack_blueprint_only",
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
    _write_jsonl(output_dir / "trace_net_engineering_context_pack_blueprint_v1_records.jsonl", records)
    _write_json(output_dir / "trace_net_engineering_context_pack_blueprint_v1_summary.json", summary)
    _write_json(output_dir / "trace_net_engineering_context_pack_blueprint_v1_quality.json", {"quality_status": quality_status, "summary": summary})
    _write_markdown(output_dir / "trace_net_engineering_context_pack_blueprint_v1.md", payload)
    return payload


def _write_markdown(path: Path, payload: Mapping[str, Any]) -> None:
    summary = payload.get("summary") or {}
    lines = [
        "# TRACE-Net Engineering Context Pack Blueprint v1",
        "",
        f"Quality status: **{payload.get('quality_status')}**",
        "",
        "## Summary",
        "",
        f"- Blueprints: {summary.get('context_pack_blueprint_count')}",
        f"- Route evidence slots: `{summary.get('route_evidence_slot_counts')}`",
        f"- Blueprints requiring source truth: {summary.get('blueprints_with_source_truth_required_count')}",
        "",
        "## Blueprints",
        "",
    ]
    for record in payload.get("records") or []:
        lines.extend([
            f"### {record.get('blueprint_id')} — {record.get('intent_family')}",
            "",
            f"- Question: `{record.get('user_question')}`",
            f"- Playbook: `{record.get('selected_playbook_id')}`",
            f"- Routes: `{[slot.get('route') for slot in record.get('route_evidence_slots', [])]}`",
            f"- Candidate language required: `{record.get('candidate_language_required')}`",
            f"- Answer mode: `{record.get('answer_format_contract', {}).get('answer_mode')}`",
            "",
        ])
    path.write_text("\n".join(lines), encoding="utf-8")


def check_engineering_context_pack_blueprint_quality(
    *,
    report_path: Path,
    require_source_query_planner_quality_pass: bool = False,
    min_blueprints: int = 1,
    min_total_route_slots: int = 1,
    min_source_truth_required_blueprints: int = 1,
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

    if require_source_query_planner_quality_pass:
        fail_if(summary.get("source_query_planner_quality_status") != "PASS", "source query planner quality is not PASS")
    fail_if(summary.get("context_pack_blueprint_count", 0) < min_blueprints, "not enough blueprints")
    fail_if(summary.get("total_route_evidence_slot_count", 0) < min_total_route_slots, "not enough route evidence slots")
    fail_if(summary.get("blueprints_with_source_truth_required_count", 0) < min_source_truth_required_blueprints, "not enough source-truth-required blueprints")
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
    parser = argparse.ArgumentParser(description="Build TRACE-Net engineering context pack blueprint v1.")
    parser.add_argument("--query-planner", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)

    payload = build_engineering_context_pack_blueprint(
        query_planner_path=Path(args.query_planner),
        output_dir=Path(args.output_dir),
    )
    print("Status:", payload["status"])
    print("Quality status:", payload["quality_status"])
    print("Summary:", json.dumps(payload["summary"], sort_keys=True))
    return 0 if payload["quality_status"] == "PASS" else 1


def main_check(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net engineering context pack blueprint v1 quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--require-source-query-planner-quality-pass", action="store_true")
    parser.add_argument("--min-blueprints", type=int, default=1)
    parser.add_argument("--min-total-route-slots", type=int, default=1)
    parser.add_argument("--min-source-truth-required-blueprints", type=int, default=1)
    parser.add_argument("--max-unsafe", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-llm-calls", action="store_true")
    parser.add_argument("--require-no-retrieval-execution", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    args = parser.parse_args(argv)

    result = check_engineering_context_pack_blueprint_quality(
        report_path=Path(args.report_path),
        require_source_query_planner_quality_pass=args.require_source_query_planner_quality_pass,
        min_blueprints=args.min_blueprints,
        min_total_route_slots=args.min_total_route_slots,
        min_source_truth_required_blueprints=args.min_source_truth_required_blueprints,
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
        out = Path(args.report_path).with_name("trace_net_engineering_context_pack_blueprint_v1_quality_check.json")
        _write_json(out, result)
        print("Wrote:", out)
    return 0 if result["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main_build())
