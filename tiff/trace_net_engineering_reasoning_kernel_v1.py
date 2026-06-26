
"""TRACE-Net Engineering Reasoning Kernel v1.

Builds an artifact-only engineering reasoning kernel for TRACE-Net.

Purpose:
- Give Gemma/TRACE-Net a reusable engineering reasoning layer using RAG-friendly
  playbooks, examples, intent patterns, retrieval plans, and answer safety rules.
- Do not answer user questions directly.
- Do not call an LLM.
- Do not mutate source truth or write vector/search/databases.

This is the first step in the "RAG + engineering examples + reasoning playbooks" path.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence


MODULE_VERSION = "trace_net_engineering_reasoning_kernel_v1"
REPORT_NAME = "trace_net_engineering_reasoning_kernel_v1.json"


DEFAULT_ENGINEERING_PLAYBOOKS: List[Dict[str, Any]] = [
    {
        "playbook_id": "similar_part_candidate_search",
        "title": "Similar Part Candidate Search",
        "intent_family": "similarity_or_substitution_candidate",
        "trigger_phrases": [
            "looks like", "similar", "same kind", "replacement", "alternate",
            "substitute", "another part", "compatible", "interchangeable",
        ],
        "engineering_steps": [
            "resolve seed part/model/entity exactly",
            "identify function, assembly, subassembly, and nomenclature",
            "retrieve same IPL/table family and nearby item numbers",
            "retrieve same figure/callout neighborhood",
            "retrieve same graph/Leiden community",
            "compare candidate function, form, fit, interface, effectivity, material, and dimensions",
            "separate candidate-for-review from approved replacement",
        ],
        "retrieval_plan": [
            "exact_seed_lookup",
            "same_assembly_graph_search",
            "same_ipl_table_search",
            "same_figure_callout_search",
            "nomenclature_similarity_search",
            "vector_semantic_similarity_search",
            "page_context_v2_supporting_text_search",
        ],
        "allowed_answer_claims": [
            "candidate for engineering review",
            "appears related by source evidence",
            "shares assembly/table/figure/nomenclature evidence",
            "missing proof must be reviewed",
        ],
        "forbidden_answer_claims": [
            "approved replacement",
            "guaranteed fit",
            "safe to install",
            "interchangeable unless source explicitly says so",
        ],
        "trust_tier": "candidate_guidance_only",
    },
    {
        "playbook_id": "dimensional_change_candidate_search",
        "title": "Dimensional Change Candidate Search",
        "intent_family": "engineering_change_candidate",
        "trigger_phrases": [
            "shorter", "longer", "wider", "narrower", "thicker", "thinner",
            "4 inches", "dimension", "length", "height", "diameter", "size",
        ],
        "engineering_steps": [
            "extract requested dimensional property and delta",
            "resolve seed part/model/entity exactly",
            "retrieve tables with dimensions, dash variants, and repair materials",
            "compute target dimension only if source dimension is proven",
            "search same part family/dash-number variants",
            "rank candidates by dimension closeness plus same-family evidence",
            "require review for fit, tolerance, interface, and approval",
        ],
        "retrieval_plan": [
            "exact_seed_lookup",
            "dimension_table_search",
            "dash_number_variant_search",
            "same_assembly_graph_search",
            "same_ipl_table_search",
            "engineering_text_context_search",
        ],
        "allowed_answer_claims": [
            "dimension candidate for review",
            "source shows a listed dimension",
            "candidate appears shorter/longer only if source proves dimensions",
        ],
        "forbidden_answer_claims": [
            "will fit",
            "approved modification",
            "safe dimensional change",
            "manufacturing/tolerance approval",
        ],
        "trust_tier": "candidate_guidance_only",
    },
    {
        "playbook_id": "fault_repair_procedure_reasoning",
        "title": "Fault, Repair, and Procedure Reasoning",
        "intent_family": "repair_or_fault_context",
        "trigger_phrases": [
            "repair", "fix", "fault", "test", "inspection", "cleaning", "clean",
            "cleaner", "cleaners", "solvent", "solvents", "remove", "install",
            "procedure", "warning", "caution", "note", "damage", "stripper",
            "paint", "topcoat", "finish",
        ],
        "engineering_steps": [
            "identify the affected part/assembly and procedure section",
            "retrieve source procedure text and warnings first",
            "retrieve associated figures/tables only as supporting context",
            "preserve sequence, warnings, tools/materials, and limits",
            "do not invent missing steps",
            "route missing/ambiguous procedural claims to review",
        ],
        "retrieval_plan": [
            "normal_text_page_context_search",
            "exact_part_lookup",
            "procedure_section_search",
            "warning_caution_note_search",
            "associated_figure_callout_search",
            "associated_table_search",
        ],
        "allowed_answer_claims": [
            "source-backed procedure summary",
            "warning/caution/note citation",
            "review required for missing steps",
        ],
        "forbidden_answer_claims": [
            "uncited repair procedure",
            "skipped warning",
            "approval to perform maintenance",
        ],
        "trust_tier": "source_summary_required",
    },
    {
        "playbook_id": "part_number_evidence_pack",
        "title": "Part Number Evidence Pack",
        "intent_family": "exact_part_lookup",
        "trigger_phrases": [
            "part number", "P/N", "pn", "model number", "find", "where is",
            "item number", "assy number", "nomenclature",
        ],
        "engineering_steps": [
            "normalize seed part/model number without changing source truth",
            "perform exact table/evidence lookup",
            "retrieve row fields, page id, table/figure context, and nomenclature",
            "retrieve graph neighbors and page context as supporting evidence",
            "report exact evidence first, then candidate context separately",
        ],
        "retrieval_plan": [
            "table_exact_search",
            "promoted_table_value_evidence_search",
            "page_context_v2_search",
            "graph_neighbor_search",
            "route_handoff_lookup",
        ],
        "allowed_answer_claims": [
            "exact source-backed part record",
            "candidate related context clearly labeled",
        ],
        "forbidden_answer_claims": [
            "unproven synonym",
            "unverified alternate part",
        ],
        "trust_tier": "source_evidence_first",
    },
    {
        "playbook_id": "visual_similarity_candidate_search",
        "title": "Visual Similarity Candidate Search",
        "intent_family": "visual_or_callout_similarity",
        "trigger_phrases": [
            "looks like", "diagram", "picture", "visual", "callout", "figure",
            "shape", "looks similar", "same drawing",
        ],
        "engineering_steps": [
            "resolve seed figure/callout/part if possible",
            "retrieve image_visual route candidates and callout records",
            "retrieve same figure and neighboring callouts",
            "cross-check with table/IPL part records",
            "label visual similarity as candidate evidence only",
        ],
        "retrieval_plan": [
            "image_visual_handoff_search",
            "callout_candidate_search",
            "same_figure_graph_search",
            "table_exact_cross_check",
            "visual_observer_review_search",
        ],
        "allowed_answer_claims": [
            "visually similar candidate",
            "same figure/callout neighborhood",
            "needs table/source confirmation",
        ],
        "forbidden_answer_claims": [
            "same part based only on image",
            "approved visual replacement",
        ],
        "trust_tier": "visual_candidate_only",
    },
]


DEFAULT_EXAMPLE_CARDS: List[Dict[str, Any]] = [
    {
        "example_id": "ex_dimensional_shorter_part",
        "user_question": "This model number 123-45 needs to be 4 inches shorter. Any part that looks like that?",
        "expected_intent_family": "engineering_change_candidate",
        "good_reasoning_pattern": [
            "identify 123-45 as the seed entity",
            "extract requested change: length -4 inches",
            "look for same family and dimensions before suggesting candidates",
            "use table/graph/visual evidence together",
            "answer as candidate-for-review, not approved replacement",
        ],
        "bad_answer_pattern": [
            "inventing a replacement part",
            "claiming it will fit",
            "ignoring dimensions/effectivity/interface",
        ],
    },
    {
        "example_id": "ex_similar_repair_leg",
        "user_question": "Find parts like this seat leg repair piece.",
        "expected_intent_family": "similarity_or_substitution_candidate",
        "good_reasoning_pattern": [
            "resolve the exact seat leg repair part",
            "search same repair section and part/material table",
            "compare single/double/triple seat variants",
            "separate similar material/context from approved interchangeability",
        ],
        "bad_answer_pattern": [
            "assuming single/double/triple variants are interchangeable",
            "not checking material or repair context",
        ],
    },
    {
        "example_id": "ex_procedure_warning",
        "user_question": "Can I clean this part with solvent?",
        "expected_intent_family": "repair_or_fault_context",
        "good_reasoning_pattern": [
            "retrieve cleaning procedure and warnings",
            "cite warnings/cautions before steps",
            "do not invent chemicals or PPE",
            "flag maintenance approval boundaries",
        ],
        "bad_answer_pattern": [
            "giving generic cleaning advice",
            "omitting source warnings",
        ],
    },
    {
        "example_id": "ex_exact_part_lookup",
        "user_question": "Find part number 120-29073-001 and tell me what it is near.",
        "expected_intent_family": "exact_part_lookup",
        "good_reasoning_pattern": [
            "perform exact part lookup first",
            "retrieve table row/page/nomenclature",
            "retrieve graph neighbors and same figure context",
            "separate exact record from nearby candidates",
        ],
        "bad_answer_pattern": [
            "using semantic similarity before exact lookup",
            "treating neighbors as exact matches",
        ],
    },
]


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


def _load_extra_cards(path: Optional[Path]) -> List[Dict[str, Any]]:
    if path is None:
        return []
    payload = _read_json(path)
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    for key in ("cards", "records", "examples", "playbooks"):
        value = payload.get(key)
        if isinstance(value, list):
            return [r for r in value if isinstance(r, dict)]
    return []


def _route_handoff_summary(path: Optional[Path]) -> Dict[str, Any]:
    if path is None:
        return {
            "route_dispatch_available": False,
            "route_handoff_counts": {},
            "source_route_dispatch_quality_status": None,
            "source_route_dispatch_path": None,
        }
    payload = _read_json(path)
    summary = payload.get("summary") or {}
    return {
        "route_dispatch_available": True,
        "route_handoff_counts": summary.get("route_handoff_counts") or {},
        "source_route_dispatch_quality_status": payload.get("quality_status"),
        "source_route_dispatch_path": str(path),
        "normal_text_handoff_count": summary.get("normal_text_handoff_count", 0),
        "table_handoff_count": summary.get("table_handoff_count", 0),
        "image_visual_handoff_count": summary.get("image_visual_handoff_count", 0),
        "blank_candidate_handoff_count": summary.get("blank_candidate_handoff_count", 0),
    }


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _infer_intent(question: str, playbooks: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    q = _normalize_text(question)
    scored = []
    for playbook in playbooks:
        triggers = playbook.get("trigger_phrases") or []
        score = 0
        matched = []
        for trigger in triggers:
            t = _normalize_text(str(trigger))
            if t and t in q:
                score += 1
                matched.append(trigger)
        if playbook.get("playbook_id") == "dimensional_change_candidate_search":
            if re.search(r"\b\d+(\.\d+)?\s*(in|inch|inches|mm|cm|ft|feet)\b", q):
                score += 2
                matched.append("dimension_with_unit")
        if playbook.get("playbook_id") == "part_number_evidence_pack":
            if re.search(r"\b\d{2,}[-_]\d{2,}[-_]?\d*\b", q):
                score += 2
                matched.append("part_like_token")
        scored.append((score, playbook, matched))
    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best, matched = scored[0] if scored else (0, {}, [])
    intent_family = best.get("intent_family") if best_score > 0 else "general_engineering_question"
    return {
        "question": question,
        "selected_playbook_id": best.get("playbook_id") if best_score > 0 else None,
        "intent_family": intent_family,
        "score": best_score,
        "matched_triggers": matched,
        "retrieval_plan": best.get("retrieval_plan", []) if best_score > 0 else [
            "exact_seed_lookup_if_entities_present",
            "page_context_v2_search",
            "table_exact_search_if_part_or_dimension_present",
            "graph_or_vector_search_if_similarity_language_present",
        ],
        "answer_policy": {
            "must_separate_proven_vs_candidate": True,
            "must_cite_source_truth_for_claims": True,
            "must_not_certify_fit_or_replacement": True,
        },
        "requires_review": True,
    }


def _safety_contract() -> Dict[str, Any]:
    return {
        "artifact_authority": "engineering_reasoning_guidance_only",
        "llm_call_allowed": False,
        "answers_user_question": False,
        "retrieval_execution_allowed": False,
        "source_truth_mutation_allowed": False,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "postgres_write_allowed": False,
        "qdrant_write_allowed": False,
        "opensearch_write_allowed": False,
    }


def build_engineering_reasoning_kernel(
    *,
    output_dir: Path,
    route_dispatch_handoff: Optional[Path] = None,
    extra_playbooks: Optional[Path] = None,
    extra_examples: Optional[Path] = None,
    sample_questions: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    playbooks = [dict(card) for card in DEFAULT_ENGINEERING_PLAYBOOKS]
    playbooks.extend(_load_extra_cards(extra_playbooks))

    examples = [dict(card) for card in DEFAULT_EXAMPLE_CARDS]
    examples.extend(_load_extra_cards(extra_examples))

    route_summary = _route_handoff_summary(route_dispatch_handoff)

    sample_questions = list(sample_questions or [
        "This model number 123-45 needs to be 4 inches shorter. Any part that looks like that?",
        "Find part number 120-29073-001 and nearby similar parts.",
        "Can I clean this part with solvent?",
        "Show visually similar callout parts in the same figure.",
    ])
    sample_intent_plans = [_infer_intent(question, playbooks) for question in sample_questions]

    query_plan_templates = [
        {
            "template_id": "engineering_question_to_trace_net_plan",
            "pipeline": [
                "engineering_intent_parse",
                "select_reasoning_playbook",
                "build_structured_retrieval_plan",
                "execute_allowed_trace_net_routes",
                "assemble_evidence_pack",
                "self_rag_evidence_check",
                "crag_retry_if_weak",
                "draft_candidate_answer_with_boundaries",
                "final_gate",
            ],
            "required_context_sections": [
                "source_truth_evidence",
                "engineering_playbook",
                "retrieval_plan",
                "trust_tier_policy",
                "forbidden_claims",
                "missing_evidence",
            ],
        }
    ]

    trust_tier_policy = {
        "exact_source_evidence": "claim may be stated with citation",
        "cross_route_supported_candidate": "candidate may be suggested for review only",
        "visual_only_candidate": "visual similarity only; must be cross-checked",
        "semantic_only_candidate": "retrieval lead only; not a claim",
        "missing_evidence": "state missing evidence and route to review",
    }

    forbidden_global_claims = [
        "approved replacement without explicit source evidence",
        "guaranteed fit/form/function",
        "safe to install",
        "engineering approval",
        "uncited repair procedure",
        "uncited dimension or material claim",
    ]

    records: List[Dict[str, Any]] = []
    for card in playbooks:
        record = dict(card)
        record["record_type"] = "engineering_playbook"
        record["kernel_version"] = MODULE_VERSION
        record["answer_permission"] = False
        record["source_truth_mutation_allowed"] = False
        records.append(record)
    for card in examples:
        record = dict(card)
        record["record_type"] = "engineering_example"
        record["kernel_version"] = MODULE_VERSION
        record["answer_permission"] = False
        record["source_truth_mutation_allowed"] = False
        records.append(record)

    summary = {
        "playbook_count": len(playbooks),
        "example_card_count": len(examples),
        "query_plan_template_count": len(query_plan_templates),
        "sample_intent_plan_count": len(sample_intent_plans),
        "intent_family_counts": dict(sorted(Counter(p.get("intent_family") for p in playbooks).items())),
        "route_dispatch_available": route_summary.get("route_dispatch_available", False),
        "source_route_dispatch_quality_status": route_summary.get("source_route_dispatch_quality_status"),
        "route_handoff_counts": route_summary.get("route_handoff_counts", {}),
        "normal_text_handoff_count": route_summary.get("normal_text_handoff_count", 0),
        "table_handoff_count": route_summary.get("table_handoff_count", 0),
        "image_visual_handoff_count": route_summary.get("image_visual_handoff_count", 0),
        "blank_candidate_handoff_count": route_summary.get("blank_candidate_handoff_count", 0),
        "unsafe_record_count": 0,
        "answer_permission_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "llm_call_allowed_count": 0,
        "retrieval_execution_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }

    quality_status = "PASS"
    if len(playbooks) < 5 or len(examples) < 4:
        quality_status = "FAIL"
    if route_dispatch_handoff is not None and route_summary.get("source_route_dispatch_quality_status") != "PASS":
        quality_status = "FAIL"

    payload: Dict[str, Any] = {
        "module": MODULE_VERSION,
        "status": "ENGINEERING_REASONING_KERNEL_BUILT",
        "quality_status": quality_status,
        "summary": summary,
        "playbooks": playbooks,
        "example_cards": examples,
        "query_plan_templates": query_plan_templates,
        "trust_tier_policy": trust_tier_policy,
        "forbidden_global_claims": forbidden_global_claims,
        "sample_intent_plans": sample_intent_plans,
        "route_dispatch_context": route_summary,
        "records": records,
        "safety_contract": _safety_contract(),
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / REPORT_NAME, payload)
    _write_jsonl(output_dir / "trace_net_engineering_reasoning_kernel_v1_records.jsonl", records)
    _write_json(output_dir / "trace_net_engineering_reasoning_kernel_v1_summary.json", summary)
    _write_json(output_dir / "trace_net_engineering_reasoning_kernel_v1_quality.json", {"quality_status": quality_status, "summary": summary})
    _write_markdown(output_dir / "trace_net_engineering_reasoning_kernel_v1.md", payload)
    return payload


def _write_markdown(path: Path, payload: Mapping[str, Any]) -> None:
    summary = payload.get("summary") or {}
    lines = [
        "# TRACE-Net Engineering Reasoning Kernel v1",
        "",
        f"Quality status: **{payload.get('quality_status')}**",
        "",
        "## Summary",
        "",
        f"- Playbooks: {summary.get('playbook_count')}",
        f"- Example cards: {summary.get('example_card_count')}",
        f"- Query plan templates: {summary.get('query_plan_template_count')}",
        f"- Route dispatch available: {summary.get('route_dispatch_available')}",
        "",
        "## Engineering playbooks",
        "",
    ]
    for playbook in payload.get("playbooks") or []:
        lines.extend([
            f"### {playbook.get('playbook_id')}",
            "",
            f"- Intent family: `{playbook.get('intent_family')}`",
            f"- Trust tier: `{playbook.get('trust_tier')}`",
            f"- Retrieval plan: `{playbook.get('retrieval_plan')}`",
            "",
        ])
    lines.extend([
        "## Global forbidden claims",
        "",
    ])
    for claim in payload.get("forbidden_global_claims") or []:
        lines.append(f"- {claim}")
    path.write_text("\n".join(lines), encoding="utf-8")


def check_engineering_reasoning_kernel_quality(
    *,
    report_path: Path,
    require_route_dispatch_quality_pass: bool = False,
    min_playbooks: int = 5,
    min_examples: int = 4,
    min_query_plan_templates: int = 1,
    min_sample_intent_plans: int = 4,
    max_unsafe: int = 0,
    require_no_answer_permission: bool = False,
    require_no_source_truth_mutation: bool = False,
    require_no_llm_calls: bool = False,
    require_no_retrieval_execution: bool = False,
) -> Dict[str, Any]:
    payload = _read_json(report_path)
    summary = payload.get("summary") or {}
    failures: List[str] = []

    def fail_if(condition: bool, msg: str) -> None:
        if condition:
            failures.append(msg)

    fail_if(summary.get("playbook_count", 0) < min_playbooks, "not enough playbooks")
    fail_if(summary.get("example_card_count", 0) < min_examples, "not enough examples")
    fail_if(summary.get("query_plan_template_count", 0) < min_query_plan_templates, "not enough query plan templates")
    fail_if(summary.get("sample_intent_plan_count", 0) < min_sample_intent_plans, "not enough sample intent plans")
    fail_if(summary.get("unsafe_record_count", 0) > max_unsafe, "unsafe record count exceeded")
    if require_route_dispatch_quality_pass:
        fail_if(summary.get("source_route_dispatch_quality_status") != "PASS", "source route dispatch quality is not PASS")
    if require_no_answer_permission:
        fail_if(summary.get("answer_permission_count", 0) != 0, "answer permission count not zero")
        fail_if(summary.get("can_answer_directly_count", 0) != 0, "can answer directly count not zero")
        fail_if(summary.get("can_prove_claims_count", 0) != 0, "can prove claims count not zero")
    if require_no_source_truth_mutation:
        fail_if(summary.get("source_truth_mutation_allowed_count", 0) != 0, "source truth mutation allowed count not zero")
    if require_no_llm_calls:
        fail_if(summary.get("llm_call_allowed_count", 0) != 0, "LLM call allowed count not zero")
    if require_no_retrieval_execution:
        fail_if(summary.get("retrieval_execution_allowed_count", 0) != 0, "retrieval execution allowed count not zero")

    quality_status = "FAIL" if failures else "PASS"
    return {
        "quality_status": quality_status,
        "summary": summary,
        "failures": failures,
        "checked_report_path": str(report_path),
    }


def main_build(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net engineering reasoning kernel v1.")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--route-dispatch-handoff")
    parser.add_argument("--extra-playbooks")
    parser.add_argument("--extra-examples")
    parser.add_argument("--sample-question", action="append", default=[])
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)

    payload = build_engineering_reasoning_kernel(
        output_dir=Path(args.output_dir),
        route_dispatch_handoff=Path(args.route_dispatch_handoff) if args.route_dispatch_handoff else None,
        extra_playbooks=Path(args.extra_playbooks) if args.extra_playbooks else None,
        extra_examples=Path(args.extra_examples) if args.extra_examples else None,
        sample_questions=args.sample_question or None,
    )
    print("Status:", payload["status"])
    print("Quality status:", payload["quality_status"])
    print("Summary:", json.dumps(payload["summary"], sort_keys=True))
    return 0 if payload["quality_status"] == "PASS" else 1


def main_check(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net engineering reasoning kernel v1 quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--require-route-dispatch-quality-pass", action="store_true")
    parser.add_argument("--min-playbooks", type=int, default=5)
    parser.add_argument("--min-examples", type=int, default=4)
    parser.add_argument("--min-query-plan-templates", type=int, default=1)
    parser.add_argument("--min-sample-intent-plans", type=int, default=4)
    parser.add_argument("--max-unsafe", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    parser.add_argument("--require-no-llm-calls", action="store_true")
    parser.add_argument("--require-no-retrieval-execution", action="store_true")
    args = parser.parse_args(argv)

    result = check_engineering_reasoning_kernel_quality(
        report_path=Path(args.report_path),
        require_route_dispatch_quality_pass=args.require_route_dispatch_quality_pass,
        min_playbooks=args.min_playbooks,
        min_examples=args.min_examples,
        min_query_plan_templates=args.min_query_plan_templates,
        min_sample_intent_plans=args.min_sample_intent_plans,
        max_unsafe=args.max_unsafe,
        require_no_answer_permission=args.require_no_answer_permission,
        require_no_source_truth_mutation=args.require_no_source_truth_mutation,
        require_no_llm_calls=args.require_no_llm_calls,
        require_no_retrieval_execution=args.require_no_retrieval_execution,
    )
    print("Quality status:", result["quality_status"])
    print("Summary:", json.dumps(result["summary"], sort_keys=True))
    if result["failures"]:
        print("Failures:", json.dumps(result["failures"], indent=2))
    if args.write_json:
        out = Path(args.report_path).with_name("trace_net_engineering_reasoning_kernel_v1_quality_check.json")
        _write_json(out, result)
        print("Wrote:", out)
    return 0 if result["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main_build())
