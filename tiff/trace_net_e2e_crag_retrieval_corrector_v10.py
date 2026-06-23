"""TRACE-Net E2E CRAG retrieval corrector v10.

This module consumes Self-RAG context critic output and creates a corrective
retrieval plan for each context. It is intentionally plan-only: it does not
call an LLM, rerun retrieval, mutate source truth, or write to external
services. Later endpoint/runtime modules can consume these plans to decide
whether to retry retrieval, repair routing, or request human review.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

SCHEMA_VERSION = "v10"
STATUS_BUILT = "E2E_CRAG_RETRIEVAL_CORRECTOR_BUILT"
STATUS_READY = "E2E_CRAG_RETRIEVAL_CORRECTOR_READY_FOR_PROMPT_OR_RETRY"
QUALITY_PASS = "PASS"
QUALITY_FAIL = "FAIL"

NO_RETRY_STATUS = "CRAG_NO_RETRY_NEEDED"
RETRY_READY_STATUS = "CRAG_RETRY_PLAN_READY"
HUMAN_REVIEW_STATUS = "CRAG_HUMAN_REVIEW_PLAN_READY"
UNRESOLVED_STATUS = "CRAG_UNRESOLVED"

DEFAULT_CONTRACT: Dict[str, Any] = {
    "uses_prebuilt_self_rag_critiques": True,
    "uses_prebuilt_context_packs": True,
    "corrector_emits_plan_only": True,
    "corrector_does_not_call_llm": True,
    "corrector_does_not_rerun_retrieval": True,
    "corrector_does_not_rerun_ocr": True,
    "corrector_does_not_rerun_page_classification": True,
    "corrector_does_not_rerun_embeddings": True,
    "corrector_does_not_rerun_page_summaries": True,
    "corrector_does_not_rerun_graph_build": True,
    "corrector_does_not_rerun_table_extraction": True,
    "graph_is_not_proof_authority": True,
    "summaries_are_not_source_truth": True,
    "guidance_box_is_not_source_truth": True,
    "answer_permission": False,
    "can_answer_directly": False,
    "can_prove_claims": False,
    "source_truth_mutation_allowed": False,
    "postgres_write_attempt_count": 0,
    "qdrant_write_attempt_count": 0,
    "opensearch_write_attempt_count": 0,
    "opensearch_upload_attempt_count": 0,
}


def read_json(path: Path | str) -> Dict[str, Any]:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8"))


def write_json(path: Path | str, data: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def write_jsonl(path: Path | str, rows: Iterable[Mapping[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "pass", "ready"}
    return bool(value)


def as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        if isinstance(value, bool):
            return int(value)
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def nested_get(data: Mapping[str, Any], path: Sequence[str], default: Any = None) -> Any:
    cur: Any = data
    for key in path:
        if not isinstance(cur, Mapping) or key not in cur:
            return default
        cur = cur[key]
    return cur


def extract_critiques(self_rag_report: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Return critic records across possible report key names."""
    for key in (
        "critiques",
        "self_rag_critiques",
        "context_critiques",
        "critique_records",
        "records",
    ):
        rows = self_rag_report.get(key)
        if isinstance(rows, list):
            return [dict(r) for r in rows if isinstance(r, Mapping)]
    # Some reports may only store a single critique-like record.
    if "context_pack_id" in self_rag_report:
        return [dict(self_rag_report)]
    return []


def _has_failed_findings(critique: Mapping[str, Any], severity: Optional[str] = None) -> List[Dict[str, Any]]:
    failed: List[Dict[str, Any]] = []
    for finding in safe_list(critique.get("findings")):
        if not isinstance(finding, Mapping):
            continue
        if as_bool(finding.get("passed")):
            continue
        if severity and str(finding.get("severity", "")).lower() != severity.lower():
            continue
        failed.append(dict(finding))
    return failed


def infer_retry_reasons(critique: Mapping[str, Any]) -> List[str]:
    reasons: List[str] = []
    status = str(critique.get("self_rag_critic_status", ""))
    if status and status not in {"SELF_RAG_CONTEXT_READY", "READY", "PASS"}:
        reasons.append(f"self_rag_status={status}")

    if as_bool(critique.get("needs_crag_retry")):
        reasons.append("self_rag_marked_needs_crag_retry")
    if as_bool(critique.get("needs_human_review")):
        reasons.append("self_rag_marked_needs_human_review")

    evidence_count = as_int(critique.get("evidence_item_count"))
    source_truth_count = as_int(critique.get("source_truth_evidence_count"))
    citation_ready_count = as_int(critique.get("citation_ready_evidence_count"))
    source_trace_count = as_int(critique.get("source_trace_ready_evidence_count"))
    intent_relevant_count = as_int(critique.get("intent_relevant_evidence_count"))
    guidance_count = as_int(critique.get("guidance_item_count"))
    safe_guidance_count = as_int(critique.get("safe_guidance_item_count"))
    graph_summary_violation = as_int(critique.get("graph_summary_proof_violation_count"))

    if evidence_count <= 0:
        reasons.append("missing_evidence_box_items")
    if source_truth_count < evidence_count:
        reasons.append("non_source_truth_evidence_present")
    if citation_ready_count < evidence_count:
        reasons.append("citation_repair_needed")
    if source_trace_count < evidence_count:
        reasons.append("source_trace_repair_needed")
    if intent_relevant_count <= 0:
        reasons.append("query_intent_mismatch_or_wrong_field")
    if guidance_count > safe_guidance_count:
        reasons.append("guidance_authority_repair_needed")
    if graph_summary_violation > 0:
        reasons.append("graph_or_summary_used_as_proof")

    for finding in _has_failed_findings(critique):
        name = str(finding.get("name", "failed_finding"))
        if name:
            reasons.append(f"failed_finding:{name}")

    blockers = safe_list(critique.get("blockers"))
    warnings = safe_list(critique.get("warnings"))
    for blocker in blockers:
        if isinstance(blocker, str):
            reasons.append(f"blocker:{blocker}")
        elif isinstance(blocker, Mapping):
            reasons.append(f"blocker:{blocker.get('name', blocker.get('detail', 'unknown'))}")
    for warning in warnings:
        if isinstance(warning, str):
            reasons.append(f"warning:{warning}")
        elif isinstance(warning, Mapping):
            reasons.append(f"warning:{warning.get('name', warning.get('detail', 'unknown'))}")

    # Preserve order while removing duplicates.
    seen: set[str] = set()
    unique: List[str] = []
    for reason in reasons:
        if reason not in seen:
            seen.add(reason)
            unique.append(reason)
    return unique


def build_corrective_actions(critique: Mapping[str, Any], retry_reasons: Sequence[str]) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    query_intent = str(critique.get("query_intent") or "unknown")
    user_query = str(critique.get("user_query") or "")

    if not retry_reasons:
        return [
            {
                "action_type": "no_retry_required",
                "action_status": "READY",
                "description": "Self-RAG marked the context ready. Preserve the current context pack for prompt construction.",
                "route_policy": "preserve_current_route_and_evidence",
            }
        ]

    if any(r in retry_reasons for r in ("missing_evidence_box_items", "source_trace_repair_needed")):
        actions.append(
            {
                "action_type": "expand_source_truth_retrieval",
                "action_status": "READY",
                "description": "Retry retrieval against source-truth evidence pools and require citation/source-trace-ready records.",
                "preferred_tunnels": ["table_exact_search_tunnel", "table_hybrid_bridge_tunnel", "route_metadata_tunnel"],
                "forbidden_authority": ["graph_summary_as_proof", "summary_only_answer"],
            }
        )

    if any("query_intent_mismatch" in r or "wrong_field" in r or "intent_relevant" in r for r in retry_reasons):
        field_preference = "covered_part_number" if "covered" in user_query.lower() or query_intent == "covered_part_number" else query_intent
        actions.append(
            {
                "action_type": "route_and_field_correction",
                "action_status": "READY",
                "description": "Retry with the detected/expected route and field preference instead of broad table text matching.",
                "query_intent": query_intent,
                "field_preference": field_preference,
                "preferred_tunnels": ["table_exact_search_tunnel", "route_metadata_tunnel"],
            }
        )

    if any("citation_repair" in r for r in retry_reasons):
        actions.append(
            {
                "action_type": "citation_repair",
                "action_status": "READY",
                "description": "Keep only evidence records that have citation_ready=True and non-empty page/field/value metadata.",
                "preferred_tunnels": ["table_exact_search_tunnel"],
            }
        )

    if any("graph_or_summary_used_as_proof" in r or "guidance_authority" in r for r in retry_reasons):
        actions.append(
            {
                "action_type": "guidance_authority_repair",
                "action_status": "READY",
                "description": "Demote graph, summary, vector, and route guidance to navigation-only context; never use it as proof.",
                "guidance_policy": "guidance_only_not_source_truth",
            }
        )

    if as_bool(critique.get("needs_human_review")) or any("human" in r.lower() for r in retry_reasons):
        actions.append(
            {
                "action_type": "human_review_enqueue",
                "action_status": "READY",
                "description": "Create or preserve a human-review task if retry cannot produce source-truth evidence.",
                "review_priority": "medium",
            }
        )

    if not actions:
        actions.append(
            {
                "action_type": "generic_retrieval_retry",
                "action_status": "READY",
                "description": "Retry retrieval with stricter source-truth, citation, and route filters.",
                "preferred_tunnels": [
                    "table_exact_search_tunnel",
                    "table_hybrid_bridge_tunnel",
                    "qdrant_page_profile_tunnel",
                    "page_summary_tunnel",
                    "graph_community_tunnel",
                    "graph_navigation_tunnel",
                    "route_metadata_tunnel",
                    "table_route_summary_tunnel",
                ],
            }
        )

    return actions


def build_crag_plan(critique: Mapping[str, Any], index: int) -> Dict[str, Any]:
    retry_reasons = infer_retry_reasons(critique)
    corrective_actions = build_corrective_actions(critique, retry_reasons)
    needs_human_review = as_bool(critique.get("needs_human_review")) or any(
        a.get("action_type") == "human_review_enqueue" for a in corrective_actions
    )
    needs_retry = bool(retry_reasons) and not needs_human_review

    if not retry_reasons:
        status = NO_RETRY_STATUS
    elif needs_human_review:
        status = HUMAN_REVIEW_STATUS
    elif needs_retry:
        status = RETRY_READY_STATUS
    else:
        status = UNRESOLVED_STATUS

    plan_ready = status in {NO_RETRY_STATUS, RETRY_READY_STATUS, HUMAN_REVIEW_STATUS}

    return {
        "schema_version": SCHEMA_VERSION,
        "crag_plan_id": f"crag_retrieval_corrector_v10_{index:04d}",
        "context_pack_id": critique.get("context_pack_id", f"unknown_context_{index:04d}"),
        "user_query": critique.get("user_query", ""),
        "query_intent": critique.get("query_intent", "unknown"),
        "source_self_rag_status": critique.get("self_rag_critic_status", "UNKNOWN"),
        "crag_plan_status": status,
        "ready_for_prompt_contract": status == NO_RETRY_STATUS,
        "ready_for_retry_execution": status == RETRY_READY_STATUS,
        "ready_for_human_review_queue": status == HUMAN_REVIEW_STATUS,
        "needs_retry": status == RETRY_READY_STATUS,
        "needs_human_review": status == HUMAN_REVIEW_STATUS,
        "plan_ready": plan_ready,
        "retry_reasons": list(retry_reasons),
        "corrective_actions": corrective_actions,
        "corrective_action_count": len([a for a in corrective_actions if a.get("action_type") != "no_retry_required"]),
        "source_truth_evidence_count": as_int(critique.get("source_truth_evidence_count")),
        "citation_ready_evidence_count": as_int(critique.get("citation_ready_evidence_count")),
        "source_trace_ready_evidence_count": as_int(critique.get("source_trace_ready_evidence_count")),
        "intent_relevant_evidence_count": as_int(critique.get("intent_relevant_evidence_count")),
        "guidance_item_count": as_int(critique.get("guidance_item_count")),
        "safe_guidance_item_count": as_int(critique.get("safe_guidance_item_count")),
        "graph_summary_proof_violation_count": as_int(critique.get("graph_summary_proof_violation_count")),
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "contract": DEFAULT_CONTRACT,
    }


def build_crag_corrector_report(self_rag_context_critic: Mapping[str, Any], source_path: str = "") -> Dict[str, Any]:
    critiques = extract_critiques(self_rag_context_critic)
    plans = [build_crag_plan(critique, i + 1) for i, critique in enumerate(critiques)]

    retry_required_plan_count = sum(1 for p in plans if p["crag_plan_status"] == RETRY_READY_STATUS)
    no_retry_needed_count = sum(1 for p in plans if p["crag_plan_status"] == NO_RETRY_STATUS)
    human_review_plan_count = sum(1 for p in plans if p["crag_plan_status"] == HUMAN_REVIEW_STATUS)
    unresolved_plan_count = sum(1 for p in plans if p["crag_plan_status"] == UNRESOLVED_STATUS)
    ready_crag_plan_count = sum(1 for p in plans if as_bool(p.get("plan_ready")))
    corrective_action_count = sum(as_int(p.get("corrective_action_count")) for p in plans)
    crag_retry_candidate_count = sum(1 for p in plans if as_bool(p.get("needs_retry")))
    graph_summary_proof_violation_count = sum(as_int(p.get("graph_summary_proof_violation_count")) for p in plans)

    answer_permission_count = sum(1 for p in plans if as_bool(p.get("answer_permission")))
    can_answer_directly_count = sum(1 for p in plans if as_bool(p.get("can_answer_directly")))
    can_prove_claims_count = sum(1 for p in plans if as_bool(p.get("can_prove_claims")))
    source_truth_mutation_allowed_count = sum(1 for p in plans if as_bool(p.get("source_truth_mutation_allowed")))

    summary = {
        "quality_status": QUALITY_PASS,
        "context_critique_count": len(critiques),
        "crag_plan_count": len(plans),
        "ready_crag_plan_count": ready_crag_plan_count,
        "no_retry_needed_count": no_retry_needed_count,
        "retry_required_plan_count": retry_required_plan_count,
        "crag_retry_candidate_count": crag_retry_candidate_count,
        "human_review_plan_count": human_review_plan_count,
        "unresolved_plan_count": unresolved_plan_count,
        "corrective_action_count": corrective_action_count,
        "graph_summary_proof_violation_count": graph_summary_proof_violation_count,
        "answer_permission_count": answer_permission_count,
        "can_answer_directly_count": can_answer_directly_count,
        "can_prove_claims_count": can_prove_claims_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "opensearch_upload_attempt_count": 0,
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_BUILT,
        "e2e_crag_retrieval_corrector_status": STATUS_READY,
        "quality_status": QUALITY_PASS,
        "source_self_rag_context_critic_path": source_path,
        "crag_retrieval_corrector_contract": DEFAULT_CONTRACT,
        "summary": summary,
        "crag_plans": plans,
    }


def evaluate_quality(report: Mapping[str, Any], args: argparse.Namespace) -> Tuple[str, List[Dict[str, Any]]]:
    summary = report.get("summary", {}) if isinstance(report.get("summary"), Mapping) else {}

    checks: List[Dict[str, Any]] = []

    def add(name: str, observed: Any, expected: str, passed: bool) -> None:
        checks.append({"name": name, "observed": observed, "expected": expected, "passed": bool(passed)})

    add("quality_status", report.get("quality_status"), "== PASS", report.get("quality_status") == QUALITY_PASS)
    add("context_critique_count", summary.get("context_critique_count", 0), f">= {args.min_context_critiques}", as_int(summary.get("context_critique_count")) >= args.min_context_critiques)
    add("crag_plan_count", summary.get("crag_plan_count", 0), f">= {args.min_crag_plans}", as_int(summary.get("crag_plan_count")) >= args.min_crag_plans)
    add("ready_crag_plan_count", summary.get("ready_crag_plan_count", 0), f">= {args.min_ready_crag_plans}", as_int(summary.get("ready_crag_plan_count")) >= args.min_ready_crag_plans)
    add("no_retry_needed_count", summary.get("no_retry_needed_count", 0), f">= {args.min_no_retry_needed_count}", as_int(summary.get("no_retry_needed_count")) >= args.min_no_retry_needed_count)
    add("corrective_action_count", summary.get("corrective_action_count", 0), f">= {args.min_corrective_actions}", as_int(summary.get("corrective_action_count")) >= args.min_corrective_actions)
    add("retry_required_plan_count", summary.get("retry_required_plan_count", 0), f"<= {args.max_retry_required_plan_count}", as_int(summary.get("retry_required_plan_count")) <= args.max_retry_required_plan_count)
    add("human_review_plan_count", summary.get("human_review_plan_count", 0), f"<= {args.max_human_review_plan_count}", as_int(summary.get("human_review_plan_count")) <= args.max_human_review_plan_count)
    add("unresolved_plan_count", summary.get("unresolved_plan_count", 0), f"<= {args.max_unresolved_plan_count}", as_int(summary.get("unresolved_plan_count")) <= args.max_unresolved_plan_count)
    add("graph_summary_proof_violation_count", summary.get("graph_summary_proof_violation_count", 0), f"<= {args.max_graph_summary_proof_violations}", as_int(summary.get("graph_summary_proof_violation_count")) <= args.max_graph_summary_proof_violations)
    add("answer_permission_count", summary.get("answer_permission_count", 0), f"<= {args.max_answer_permission_count}", as_int(summary.get("answer_permission_count")) <= args.max_answer_permission_count)
    add("source_truth_mutation_allowed_count", summary.get("source_truth_mutation_allowed_count", 0), f"<= {args.max_source_truth_mutation_allowed}", as_int(summary.get("source_truth_mutation_allowed_count")) <= args.max_source_truth_mutation_allowed)
    add("contract_can_answer_directly", summary.get("can_answer_directly_count", 0), "== 0", as_int(summary.get("can_answer_directly_count")) == 0)
    add("contract_can_prove_claims", summary.get("can_prove_claims_count", 0), "== 0", as_int(summary.get("can_prove_claims_count")) == 0)
    add("postgres_write_attempt_count", summary.get("postgres_write_attempt_count", 0), "== 0", as_int(summary.get("postgres_write_attempt_count")) == 0)
    add("qdrant_write_attempt_count", summary.get("qdrant_write_attempt_count", 0), "== 0", as_int(summary.get("qdrant_write_attempt_count")) == 0)
    add("opensearch_write_attempt_count", summary.get("opensearch_write_attempt_count", 0), "== 0", as_int(summary.get("opensearch_write_attempt_count")) == 0)

    if args.require_no_answer_permission:
        add("require_no_answer_permission", summary.get("answer_permission_count", 0), "== 0", as_int(summary.get("answer_permission_count")) == 0)

    status = QUALITY_PASS if all(c["passed"] for c in checks) else QUALITY_FAIL
    return status, checks


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary", {}) if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        "# TRACE-Net E2E CRAG Retrieval Corrector v10",
        "",
        f"Quality status: **{report.get('quality_status', 'UNKNOWN')}**",
        f"Status: `{report.get('e2e_crag_retrieval_corrector_status', report.get('status', 'UNKNOWN'))}`",
        "",
        "## Contract",
        "This CRAG stage emits corrective retrieval plans only. It does not call an LLM, rerun retrieval, rerun OCR, rebuild embeddings, rebuild graph, rerun table extraction, mutate source truth, or write to services.",
        "",
        "## Summary",
    ]
    for key in [
        "context_critique_count",
        "crag_plan_count",
        "ready_crag_plan_count",
        "no_retry_needed_count",
        "retry_required_plan_count",
        "human_review_plan_count",
        "unresolved_plan_count",
        "corrective_action_count",
        "graph_summary_proof_violation_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
    ]:
        lines.append(f"- {key}: {summary.get(key, 0)}")
    lines.extend(["", "## Plans"])
    for plan in safe_list(report.get("crag_plans"))[:20]:
        if not isinstance(plan, Mapping):
            continue
        lines.append(
            f"- **{plan.get('crag_plan_status')}** `{plan.get('crag_plan_id')}` | "
            f"{plan.get('query_intent')} | {plan.get('user_query')} | "
            f"actions={len(safe_list(plan.get('corrective_actions')))}"
        )
        reasons = safe_list(plan.get("retry_reasons"))
        if reasons:
            lines.append(f"  - retry_reasons: {', '.join(str(r) for r in reasons[:8])}")
    return "\n".join(lines) + "\n"


def write_report_files(report: MutableMapping[str, Any], output_dir: Path | str) -> Dict[str, str]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / "trace_net_e2e_crag_retrieval_corrector_v10.json"
    plans_jsonl_path = out / "trace_net_e2e_crag_retrieval_corrector_plans_v10.jsonl"
    inspect_md_path = out / "trace_net_e2e_crag_retrieval_corrector_v10.md"

    paths = {
        "report_path": str(report_path),
        "plans_jsonl_path": str(plans_jsonl_path),
        "inspect_md_path": str(inspect_md_path),
    }
    report.update(paths)
    write_json(report_path, report)
    write_jsonl(plans_jsonl_path, safe_list(report.get("crag_plans")))
    inspect_md_path.write_text(render_markdown(report), encoding="utf-8")
    return paths


def add_quality_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--min-context-critiques", type=int, default=1)
    parser.add_argument("--min-crag-plans", type=int, default=1)
    parser.add_argument("--min-ready-crag-plans", type=int, default=1)
    parser.add_argument("--min-no-retry-needed-count", type=int, default=0)
    parser.add_argument("--min-corrective-actions", type=int, default=0)
    parser.add_argument("--max-retry-required-plan-count", type=int, default=999999)
    parser.add_argument("--max-human-review-plan-count", type=int, default=999999)
    parser.add_argument("--max-unresolved-plan-count", type=int, default=0)
    parser.add_argument("--max-graph-summary-proof-violations", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    return parser


def print_quality_result(report: Mapping[str, Any], checks: Sequence[Mapping[str, Any]], title: str = "TRACE-Net E2E CRAG Retrieval Corrector v10 Quality") -> None:
    print(title)
    print(f" quality_status: {report.get('quality_status')}")
    for check in checks:
        prefix = "PASS" if check.get("passed") else "FAIL"
        print(f" {prefix} {check.get('name')}: observed={check.get('observed')} expected={check.get('expected')}")
