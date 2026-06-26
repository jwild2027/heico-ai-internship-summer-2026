
"""TRACE-Net Engineering Query Planner v1.

Turns user engineering questions into structured TRACE-Net retrieval/context plans.

This is dynamic context engineering glue:
- reads the engineering reasoning kernel
- selects an engineering playbook
- extracts seed entities and requested changes
- maps retrieval steps to route handoff families
- emits a context-pack blueprint for later retrieval/LLM stages

Safety:
- does not answer the question
- does not call an LLM
- does not execute retrieval
- does not write DBs
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


MODULE_VERSION = "trace_net_engineering_query_planner_v1"
REPORT_NAME = "trace_net_engineering_query_planner_v1.json"


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


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _part_like_tokens(question: str) -> List[str]:
    # Preserve broad CMM/IPC-style tokens such as 120-29073-001 and 123-45.
    tokens = re.findall(r"\b[A-Z]?\d{2,}(?:[-_][A-Za-z0-9]{1,}){1,}\b", question, flags=re.I)
    # Also capture explicit P/N forms when punctuation separates the label.
    pn_tokens = re.findall(r"\b(?:P/N|PN|part number|model number)\s*[:#]?\s*([A-Z]?\d{2,}(?:[-_][A-Za-z0-9]{1,})*)", question, flags=re.I)
    seen = set()
    out = []
    for token in tokens + pn_tokens:
        key = token.upper()
        if key not in seen:
            seen.add(key)
            out.append(token)
    return out


def _requested_change(question: str) -> Optional[Dict[str, Any]]:
    q = _normalize_text(question)
    direction = None
    property_name = None
    if "shorter" in q:
        direction = "decrease"
        property_name = "length"
    elif "longer" in q:
        direction = "increase"
        property_name = "length"
    elif "wider" in q:
        direction = "increase"
        property_name = "width"
    elif "narrower" in q:
        direction = "decrease"
        property_name = "width"
    elif "thicker" in q:
        direction = "increase"
        property_name = "thickness"
    elif "thinner" in q:
        direction = "decrease"
        property_name = "thickness"

    match = re.search(r"\b(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>inches|inch|in|mm|cm|feet|ft)\b", q)
    if not direction and not match:
        return None
    return {
        "property": property_name or "dimension",
        "direction": direction or "unspecified",
        "delta_value": float(match.group("value")) if match else None,
        "delta_unit": match.group("unit") if match else None,
        "requires_source_dimension_before_computing_target": True,
    }


def _score_playbooks(question: str, playbooks: Sequence[Mapping[str, Any]]) -> List[Tuple[int, Mapping[str, Any], List[str]]]:
    q = _normalize_text(question)
    part_tokens = _part_like_tokens(question)
    change = _requested_change(question)
    scored: List[Tuple[int, Mapping[str, Any], List[str]]] = []
    for playbook in playbooks:
        score = 0
        matched: List[str] = []
        for trigger in playbook.get("trigger_phrases") or []:
            t = _normalize_text(str(trigger))
            if t and t in q:
                score += 1
                matched.append(str(trigger))
        pid = playbook.get("playbook_id")
        if pid == "dimensional_change_candidate_search" and change:
            score += 3
            matched.append("requested_change")
        if pid == "part_number_evidence_pack" and part_tokens:
            score += 2
            matched.append("part_like_token")
        if pid == "fault_repair_procedure_reasoning" and re.search(r"\b(clean|cleaning|solvent|warning|caution|repair|test|fault)\b", q):
            score += 2
            matched.append("procedure_or_warning_language")
        if pid == "visual_similarity_candidate_search" and re.search(r"\b(visual|figure|callout|diagram|picture|looks like)\b", q):
            score += 2
            matched.append("visual_language")
        scored.append((score, playbook, matched))
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored


def _route_for_retrieval_step(step: str) -> Dict[str, Any]:
    s = step.lower()
    routes: List[str] = []
    tools: List[str] = []
    if "table" in s or "dimension" in s or "ipl" in s or "exact" in s or "part" in s or "dash" in s:
        routes.append("table")
        tools.append("table_exact_or_value_search")
    if "page_context" in s or "text" in s or "procedure" in s or "warning" in s or "caution" in s:
        routes.append("normal_text")
        tools.append("page_context_v2")
    if "figure" in s or "callout" in s or "visual" in s or "image" in s:
        routes.append("image_visual")
        tools.append("visual_or_callout_search")
    if "graph" in s or "assembly" in s or "neighbor" in s or "leiden" in s:
        routes.append("graph")
        tools.append("graph_or_leiden_search")
    if "vector" in s or "semantic" in s or "nomenclature" in s:
        routes.append("vector")
        tools.append("vector_semantic_search")
    if not routes:
        routes = ["route_dispatch"]
        tools = ["route_handoff_lookup"]
    return {"retrieval_step": step, "routes": sorted(set(routes)), "tools": sorted(set(tools))}


def _context_budget(intent_family: str) -> Dict[str, int]:
    if intent_family == "engineering_change_candidate":
        return {
            "engineering_playbook_cards": 1,
            "few_shot_examples": 2,
            "exact_evidence_records": 8,
            "table_records": 12,
            "normal_text_context_pages": 6,
            "visual_or_callout_records": 8,
            "graph_neighbors": 20,
            "candidate_records": 10,
        }
    if intent_family == "repair_or_fault_context":
        return {
            "engineering_playbook_cards": 1,
            "few_shot_examples": 2,
            "procedure_context_pages": 8,
            "warning_caution_notes": 10,
            "table_records": 6,
            "visual_or_callout_records": 4,
        }
    return {
        "engineering_playbook_cards": 1,
        "few_shot_examples": 1,
        "exact_evidence_records": 8,
        "table_records": 8,
        "normal_text_context_pages": 4,
        "visual_or_callout_records": 4,
        "graph_neighbors": 12,
    }


def plan_engineering_question(
    *,
    question: str,
    kernel_payload: Mapping[str, Any],
    question_index: int = 0,
) -> Dict[str, Any]:
    playbooks = kernel_payload.get("playbooks") or []
    scored = _score_playbooks(question, playbooks)
    best_score, selected_playbook, matched = scored[0] if scored else (0, {}, [])
    selected = dict(selected_playbook) if best_score > 0 else {}
    intent_family = selected.get("intent_family", "general_engineering_question")
    retrieval_plan = list(selected.get("retrieval_plan") or [
        "exact_seed_lookup_if_entities_present",
        "page_context_v2_search",
        "table_exact_search_if_part_or_dimension_present",
        "graph_or_vector_search_if_similarity_language_present",
    ])

    seed_entities = _part_like_tokens(question)
    requested_change = _requested_change(question)
    mapped_steps = [_route_for_retrieval_step(step) for step in retrieval_plan]
    all_routes = sorted({route for step in mapped_steps for route in step["routes"]})
    route_context = (kernel_payload.get("route_dispatch_context") or {})
    route_handoff_counts = route_context.get("route_handoff_counts") or {}

    evidence_policy = {
        "must_retrieve_exact_seed_first": bool(seed_entities),
        "must_separate_proven_facts_from_candidates": True,
        "candidate_language_required": intent_family in {
            "engineering_change_candidate",
            "similarity_or_substitution_candidate",
            "visual_or_callout_similarity",
        },
        "source_truth_required_for_final_claims": True,
        "self_rag_required": True,
        "crag_retry_if_evidence_weak": True,
        "final_gate_required": True,
    }

    dynamic_context_pack_blueprint = {
        "sections_in_order": [
            "system_engineering_role",
            "selected_engineering_playbook",
            "few_shot_engineering_examples",
            "structured_user_intent",
            "route_handoff_availability",
            "source_truth_evidence",
            "candidate_evidence",
            "missing_evidence",
            "trust_tier_policy",
            "forbidden_claims",
            "answer_format_contract",
        ],
        "context_budget": _context_budget(intent_family),
        "route_context_needed": all_routes,
        "route_handoff_counts": route_handoff_counts,
        "compression_policy": {
            "prefer_source_truth_over_summary": True,
            "summaries_are_guidance_not_proof": True,
            "deduplicate_by_page_id_and_source_trace": True,
            "include_missing_evidence_explicitly": True,
        },
    }

    forbidden = list(kernel_payload.get("forbidden_global_claims") or [])
    forbidden.extend(selected.get("forbidden_answer_claims") or [])
    allowed = selected.get("allowed_answer_claims") or []

    return {
        "query_plan_version": MODULE_VERSION,
        "question_id": f"engineering_q{question_index+1:04d}",
        "user_question": question,
        "selected_playbook_id": selected.get("playbook_id"),
        "intent_family": intent_family,
        "intent_score": best_score,
        "matched_triggers": matched,
        "seed_entities": seed_entities,
        "requested_change": requested_change,
        "retrieval_plan": retrieval_plan,
        "route_mapped_retrieval_steps": mapped_steps,
        "dynamic_context_pack_blueprint": dynamic_context_pack_blueprint,
        "evidence_policy": evidence_policy,
        "allowed_answer_claims": allowed,
        "forbidden_answer_claims": sorted(set(forbidden)),
        "planner_status": "planned_no_retrieval_executed",
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


def build_engineering_query_planner(
    *,
    kernel_path: Path,
    output_dir: Path,
    questions: Sequence[str],
) -> Dict[str, Any]:
    kernel_payload = _read_json(kernel_path)
    plans = [
        plan_engineering_question(
            question=question,
            kernel_payload=kernel_payload,
            question_index=index,
        )
        for index, question in enumerate(questions)
    ]

    intent_counts = Counter(plan.get("intent_family") for plan in plans)
    playbook_counts = Counter(plan.get("selected_playbook_id") for plan in plans)
    route_need_counts = Counter(
        route
        for plan in plans
        for route in plan.get("dynamic_context_pack_blueprint", {}).get("route_context_needed", [])
    )

    summary = {
        "source_kernel_quality_status": kernel_payload.get("quality_status"),
        "query_plan_count": len(plans),
        "intent_family_counts": dict(sorted(intent_counts.items())),
        "selected_playbook_counts": dict(sorted((str(k), v) for k, v in playbook_counts.items())),
        "route_context_need_counts": dict(sorted(route_need_counts.items())),
        "plans_with_seed_entities_count": sum(1 for p in plans if p.get("seed_entities")),
        "plans_with_requested_change_count": sum(1 for p in plans if p.get("requested_change")),
        "plans_with_candidate_language_required_count": sum(1 for p in plans if p.get("evidence_policy", {}).get("candidate_language_required")),
        "unsafe_record_count": sum(1 for p in plans if p.get("unsafe")),
        "answer_permission_count": sum(1 for p in plans if p.get("answer_permission")),
        "can_answer_directly_count": sum(1 for p in plans if p.get("can_answer_directly")),
        "can_prove_claims_count": sum(1 for p in plans if p.get("can_prove_claims")),
        "llm_call_allowed_count": sum(1 for p in plans if p.get("llm_call_allowed")),
        "retrieval_execution_allowed_count": sum(1 for p in plans if p.get("retrieval_execution_allowed")),
        "source_truth_mutation_allowed_count": sum(1 for p in plans if p.get("source_truth_mutation_allowed")),
        "postgres_write_attempt_count": sum(1 for p in plans if p.get("postgres_write_attempt")),
        "qdrant_write_attempt_count": sum(1 for p in plans if p.get("qdrant_write_attempt")),
        "opensearch_write_attempt_count": sum(1 for p in plans if p.get("opensearch_write_attempt")),
    }

    quality_status = "PASS"
    if kernel_payload.get("quality_status") != "PASS":
        quality_status = "FAIL"
    if not plans:
        quality_status = "FAIL"

    payload: Dict[str, Any] = {
        "module": MODULE_VERSION,
        "status": "ENGINEERING_QUERY_PLANNER_BUILT",
        "quality_status": quality_status,
        "summary": summary,
        "source_kernel_path": str(kernel_path),
        "records": plans,
        "safety_contract": {
            "artifact_authority": "query_planning_only",
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
    _write_jsonl(output_dir / "trace_net_engineering_query_planner_v1_records.jsonl", plans)
    _write_json(output_dir / "trace_net_engineering_query_planner_v1_summary.json", summary)
    _write_json(output_dir / "trace_net_engineering_query_planner_v1_quality.json", {"quality_status": quality_status, "summary": summary})
    _write_markdown(output_dir / "trace_net_engineering_query_planner_v1.md", payload)
    return payload


def _write_markdown(path: Path, payload: Mapping[str, Any]) -> None:
    summary = payload.get("summary") or {}
    lines = [
        "# TRACE-Net Engineering Query Planner v1",
        "",
        f"Quality status: **{payload.get('quality_status')}**",
        "",
        "## Summary",
        "",
        f"- Query plans: {summary.get('query_plan_count')}",
        f"- Intent families: `{summary.get('intent_family_counts')}`",
        f"- Route context needs: `{summary.get('route_context_need_counts')}`",
        "",
        "## Query plans",
        "",
    ]
    for plan in payload.get("records") or []:
        lines.extend([
            f"### {plan.get('question_id')} — {plan.get('intent_family')}",
            "",
            f"- Question: `{plan.get('user_question')}`",
            f"- Playbook: `{plan.get('selected_playbook_id')}`",
            f"- Seed entities: `{plan.get('seed_entities')}`",
            f"- Requested change: `{plan.get('requested_change')}`",
            f"- Retrieval plan: `{plan.get('retrieval_plan')}`",
            f"- Route context needed: `{plan.get('dynamic_context_pack_blueprint', {}).get('route_context_needed')}`",
            "",
        ])
    path.write_text("\n".join(lines), encoding="utf-8")


def check_engineering_query_planner_quality(
    *,
    report_path: Path,
    require_source_kernel_quality_pass: bool = False,
    min_query_plans: int = 1,
    min_plans_with_seed_entities: int = 0,
    min_plans_with_requested_change: int = 0,
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

    if require_source_kernel_quality_pass:
        fail_if(summary.get("source_kernel_quality_status") != "PASS", "source kernel quality is not PASS")
    fail_if(summary.get("query_plan_count", 0) < min_query_plans, "not enough query plans")
    fail_if(summary.get("plans_with_seed_entities_count", 0) < min_plans_with_seed_entities, "not enough plans with seed entities")
    fail_if(summary.get("plans_with_requested_change_count", 0) < min_plans_with_requested_change, "not enough plans with requested changes")
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
    parser = argparse.ArgumentParser(description="Build TRACE-Net engineering query planner v1.")
    parser.add_argument("--kernel", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--question", action="append", default=[])
    parser.add_argument("--questions-json")
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)

    questions = list(args.question or [])
    if args.questions_json:
        payload = _read_json(Path(args.questions_json))
        extra = payload if isinstance(payload, list) else payload.get("questions", [])
        questions.extend([str(q) for q in extra])
    if not questions:
        questions = [
            "This model number 123-45 needs to be 4 inches shorter. Any part that looks like that?",
            "Find part number 120-29073-001 and nearby similar parts.",
            "Can I clean this part with solvent?",
            "Show visually similar callout parts in the same figure.",
        ]

    payload = build_engineering_query_planner(
        kernel_path=Path(args.kernel),
        output_dir=Path(args.output_dir),
        questions=questions,
    )
    print("Status:", payload["status"])
    print("Quality status:", payload["quality_status"])
    print("Summary:", json.dumps(payload["summary"], sort_keys=True))
    return 0 if payload["quality_status"] == "PASS" else 1


def main_check(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net engineering query planner v1 quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--require-source-kernel-quality-pass", action="store_true")
    parser.add_argument("--min-query-plans", type=int, default=1)
    parser.add_argument("--min-plans-with-seed-entities", type=int, default=0)
    parser.add_argument("--min-plans-with-requested-change", type=int, default=0)
    parser.add_argument("--max-unsafe", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-llm-calls", action="store_true")
    parser.add_argument("--require-no-retrieval-execution", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    args = parser.parse_args(argv)

    result = check_engineering_query_planner_quality(
        report_path=Path(args.report_path),
        require_source_kernel_quality_pass=args.require_source_kernel_quality_pass,
        min_query_plans=args.min_query_plans,
        min_plans_with_seed_entities=args.min_plans_with_seed_entities,
        min_plans_with_requested_change=args.min_plans_with_requested_change,
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
        out = Path(args.report_path).with_name("trace_net_engineering_query_planner_v1_quality_check.json")
        _write_json(out, result)
        print("Wrote:", out)
    return 0 if result["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main_build())
