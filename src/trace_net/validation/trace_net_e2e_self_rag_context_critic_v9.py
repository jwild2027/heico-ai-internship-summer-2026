"""TRACE-Net E2E Self-RAG Context Critic v9.

This module critiques dynamic context packs before they are handed to an LLM.
It is intentionally non-mutating: it reads prebuilt context-pack artifacts and
writes an audit/critic artifact. It does not rerun OCR, embeddings, graph build,
table extraction, or source ingest.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

SCHEMA_VERSION = "v9"
STATUS_BUILT = "E2E_SELF_RAG_CONTEXT_CRITIC_BUILT"
STATUS_READY_FOR_CRAG_OR_PROMPT = "E2E_SELF_RAG_CONTEXT_CRITIC_READY_FOR_CRAG_OR_PROMPT"
STATUS_NOT_READY = "E2E_SELF_RAG_CONTEXT_CRITIC_NOT_READY"

CRITIC_READY = "SELF_RAG_CONTEXT_READY"
CRITIC_WEAK = "SELF_RAG_CONTEXT_WEAK"
CRITIC_NEEDS_CRAG_RETRY = "SELF_RAG_CONTEXT_NEEDS_CRAG_RETRY"
CRITIC_NEEDS_HUMAN_REVIEW = "SELF_RAG_CONTEXT_NEEDS_HUMAN_REVIEW"

SOURCE_TRUTH_AUTHORITY = "source_truth_evidence_only"
GUIDANCE_AUTHORITY_MARKERS = ("guidance_only", "not_source_truth", "not_proof")

INTENT_FIELD_MAP: Dict[str, Tuple[str, ...]] = {
    "covered_part_number": ("covered_part_number",),
    "manual_page_reference": ("manual_page_reference", "ipl_part_number"),
    "table_text": ("ipl_text", "table_text"),
    "ipl_text": ("ipl_text", "table_text"),
    "ipl_part_number": ("ipl_part_number", "manual_page_reference"),
    "ipl_figure_item_or_quantity": ("ipl_figure_item_or_quantity",),
    "figure_item_or_quantity": ("ipl_figure_item_or_quantity",),
}


def load_json(path: Path | str) -> Dict[str, Any]:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8"))


def write_json(path: Path | str, data: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path | str, rows: Iterable[Mapping[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(dict(row), sort_keys=True) + "\n")


def as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "pass"}
    return bool(value)


def truthy_count(rows: Iterable[Mapping[str, Any]], key: str) -> int:
    return sum(1 for row in rows if as_bool(row.get(key)))


def get_context_packs(context_pack_report: Mapping[str, Any]) -> List[Dict[str, Any]]:
    for key in ("context_packs", "packs", "records", "context_pack_records"):
        rows = context_pack_report.get(key)
        if isinstance(rows, list):
            return [dict(row) for row in rows if isinstance(row, Mapping)]
    # Some generated artifacts may place packs under data/context_packs.
    data = context_pack_report.get("data")
    if isinstance(data, Mapping):
        rows = data.get("context_packs")
        if isinstance(rows, list):
            return [dict(row) for row in rows if isinstance(row, Mapping)]
    return []


def get_evidence_items(pack: Mapping[str, Any]) -> List[Dict[str, Any]]:
    evidence_box = pack.get("evidence_box")
    if isinstance(evidence_box, Mapping):
        return [dict(row) for row in as_list(evidence_box.get("items")) if isinstance(row, Mapping)]
    return []


def get_guidance_items(pack: Mapping[str, Any]) -> List[Dict[str, Any]]:
    guidance_box = pack.get("guidance_box")
    if isinstance(guidance_box, Mapping):
        return [dict(row) for row in as_list(guidance_box.get("items")) if isinstance(row, Mapping)]
    return []


def get_rules_box(pack: Mapping[str, Any]) -> Dict[str, Any]:
    rules_box = pack.get("rules_box")
    return dict(rules_box) if isinstance(rules_box, Mapping) else {}


def expected_fields_for_intent(intent: str) -> Tuple[str, ...]:
    intent_norm = str(intent or "").strip().lower()
    if intent_norm in INTENT_FIELD_MAP:
        return INTENT_FIELD_MAP[intent_norm]
    # Conservative fallback: an unknown intent can still be context-ready if it
    # has citation-ready source-truth evidence, but it receives a warning.
    return ()


def field_relevant_for_intent(field_name: str, intent: str) -> bool:
    allowed = expected_fields_for_intent(intent)
    if not allowed:
        return True
    return str(field_name or "").strip().lower() in allowed


def guidance_item_is_safe(item: Mapping[str, Any]) -> bool:
    authority = str(item.get("authority") or "").lower()
    tunnel_type = str(item.get("tunnel_type") or "").lower()
    if "graph" in tunnel_type:
        return "not_proof" in authority or "guidance" in authority
    return any(marker in authority for marker in GUIDANCE_AUTHORITY_MARKERS)


def critique_context_pack(pack: Mapping[str, Any]) -> Dict[str, Any]:
    pack_id = str(pack.get("context_pack_id") or pack.get("id") or "unknown_context_pack")
    user_query = str(pack.get("user_query") or "")
    query_intent = str(pack.get("query_intent") or "unknown")
    evidence_items = get_evidence_items(pack)
    guidance_items = get_guidance_items(pack)
    rules_box = get_rules_box(pack)

    findings: List[Dict[str, Any]] = []
    blockers: List[str] = []
    warnings: List[str] = []

    def add_finding(name: str, passed: bool, severity: str, detail: str, observed: Any = None) -> None:
        finding = {
            "name": name,
            "passed": bool(passed),
            "severity": severity,
            "detail": detail,
        }
        if observed is not None:
            finding["observed"] = observed
        findings.append(finding)
        if not passed and severity == "blocker":
            blockers.append(name)
        elif not passed:
            warnings.append(name)

    status_ready = str(pack.get("context_pack_status") or "").upper().endswith("READY")
    add_finding(
        "context_pack_status_ready",
        status_ready,
        "blocker",
        "Context pack must be marked ready before LLM prompt construction.",
        pack.get("context_pack_status"),
    )

    has_evidence = len(evidence_items) > 0
    add_finding(
        "has_evidence_box_items",
        has_evidence,
        "blocker",
        "Context pack must include source-truth evidence items.",
        len(evidence_items),
    )

    citation_ready_count = sum(1 for item in evidence_items if as_bool(item.get("citation_ready")))
    source_trace_ready_count = sum(1 for item in evidence_items if as_bool(item.get("source_trace_ready")))
    source_truth_authority_count = sum(
        1 for item in evidence_items if str(item.get("answer_authority") or "") == SOURCE_TRUTH_AUTHORITY
    )
    relevant_evidence_count = sum(
        1 for item in evidence_items if field_relevant_for_intent(str(item.get("field_name") or ""), query_intent)
    )

    add_finding(
        "all_evidence_citation_ready",
        citation_ready_count == len(evidence_items) and has_evidence,
        "blocker",
        "Every evidence item must be citation-ready.",
        {"citation_ready_count": citation_ready_count, "evidence_item_count": len(evidence_items)},
    )
    add_finding(
        "all_evidence_source_trace_ready",
        source_trace_ready_count == len(evidence_items) and has_evidence,
        "blocker",
        "Every evidence item must be source-trace-ready.",
        {"source_trace_ready_count": source_trace_ready_count, "evidence_item_count": len(evidence_items)},
    )
    add_finding(
        "all_evidence_source_truth_authority",
        source_truth_authority_count == len(evidence_items) and has_evidence,
        "blocker",
        "Evidence box items must be marked source-truth evidence only.",
        {"source_truth_authority_count": source_truth_authority_count, "evidence_item_count": len(evidence_items)},
    )
    add_finding(
        "intent_relevant_evidence_present",
        relevant_evidence_count > 0,
        "blocker",
        "At least one evidence item should match the detected query intent.",
        {"query_intent": query_intent, "relevant_evidence_count": relevant_evidence_count},
    )

    safe_guidance_count = sum(1 for item in guidance_items if guidance_item_is_safe(item))
    graph_or_summary_guidance_count = sum(
        1
        for item in guidance_items
        if "graph" in str(item.get("tunnel_type") or "").lower()
        or "summary" in str(item.get("tunnel_type") or "").lower()
    )
    add_finding(
        "guidance_box_present",
        len(guidance_items) > 0,
        "warning",
        "Guidance helps the LLM navigate graph/vector/summary/route context.",
        len(guidance_items),
    )
    add_finding(
        "all_guidance_is_not_source_truth",
        safe_guidance_count == len(guidance_items) and len(guidance_items) > 0,
        "blocker",
        "Guidance items must be marked guidance-only/not-source-truth/not-proof.",
        {"safe_guidance_count": safe_guidance_count, "guidance_item_count": len(guidance_items)},
    )
    add_finding(
        "graph_or_summary_guidance_available",
        graph_or_summary_guidance_count > 0,
        "warning",
        "Graph/summary guidance should be available for context engineering.",
        graph_or_summary_guidance_count,
    )

    required_rule_bools = {
        "evidence_box_is_source_truth": True,
        "guidance_box_is_not_source_truth": True,
        "graph_is_not_proof_authority": True,
        "summaries_are_not_source_truth": True,
        "cite_every_factual_claim": True,
        "source_truth_mutation_allowed": False,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "reruns_ocr": False,
        "reruns_embeddings": False,
        "reruns_graph_build": False,
        "reruns_table_extraction": False,
    }
    for key, expected in required_rule_bools.items():
        observed = as_bool(rules_box.get(key))
        add_finding(
            f"rules_box_{key}",
            observed is expected,
            "blocker" if key in {"source_truth_mutation_allowed", "answer_permission", "can_answer_directly", "can_prove_claims"} else "warning",
            f"Rules box must keep {key}={expected}.",
            observed,
        )

    # Determine critic status.
    if blockers:
        # Missing evidence or intent mismatch should go to CRAG retry. Unsafe authority issues need human review.
        unsafe_blockers = {
            "all_guidance_is_not_source_truth",
            "rules_box_source_truth_mutation_allowed",
            "rules_box_answer_permission",
            "rules_box_can_answer_directly",
            "rules_box_can_prove_claims",
        }
        critic_status = CRITIC_NEEDS_HUMAN_REVIEW if any(b in unsafe_blockers for b in blockers) else CRITIC_NEEDS_CRAG_RETRY
    elif warnings:
        critic_status = CRITIC_WEAK
    else:
        critic_status = CRITIC_READY

    ready_for_prompt = critic_status == CRITIC_READY
    needs_crag_retry = critic_status == CRITIC_NEEDS_CRAG_RETRY
    needs_human_review = critic_status == CRITIC_NEEDS_HUMAN_REVIEW

    return {
        "schema_version": SCHEMA_VERSION,
        "context_pack_id": pack_id,
        "user_query": user_query,
        "query_intent": query_intent,
        "self_rag_critic_status": critic_status,
        "ready_for_prompt_contract": ready_for_prompt,
        "needs_crag_retry": needs_crag_retry,
        "needs_human_review": needs_human_review,
        "evidence_item_count": len(evidence_items),
        "citation_ready_evidence_count": citation_ready_count,
        "source_trace_ready_evidence_count": source_trace_ready_count,
        "source_truth_evidence_count": source_truth_authority_count,
        "intent_relevant_evidence_count": relevant_evidence_count,
        "guidance_item_count": len(guidance_items),
        "safe_guidance_item_count": safe_guidance_count,
        "graph_or_summary_guidance_count": graph_or_summary_guidance_count,
        "blocker_count": len(blockers),
        "warning_count": len(warnings),
        "blockers": blockers,
        "warnings": warnings,
        "findings": findings,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "self_rag_next_status": "READY_FOR_CRAG_RETRIEVAL_CORRECTOR" if needs_crag_retry else "READY_FOR_LLM_PROMPT_CONTRACT" if ready_for_prompt else "NEEDS_HUMAN_REVIEW",
    }


def make_quality_check(name: str, observed: Any, expected: str, passed: bool) -> Dict[str, Any]:
    return {"name": name, "observed": observed, "expected": expected, "passed": bool(passed)}


def build_self_rag_context_critic(
    dynamic_context_pack: Path | str,
    *,
    min_context_packs: int = 1,
    min_context_critiques: int = 1,
    min_ready_contexts: int = 1,
    min_contexts_with_source_truth_evidence: int = 1,
    min_contexts_with_guidance_separation: int = 1,
    max_needs_crag_retry_count: Optional[int] = None,
    max_human_review_count: int = 0,
    max_graph_summary_proof_violations: int = 0,
    max_answer_permission_count: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    require_no_answer_permission: bool = False,
) -> Dict[str, Any]:
    source = load_json(dynamic_context_pack)
    packs = get_context_packs(source)
    critiques = [critique_context_pack(pack) for pack in packs]

    ready_context_count = sum(1 for c in critiques if c.get("self_rag_critic_status") == CRITIC_READY)
    weak_context_count = sum(1 for c in critiques if c.get("self_rag_critic_status") == CRITIC_WEAK)
    needs_crag_retry_count = sum(1 for c in critiques if c.get("needs_crag_retry"))
    human_review_count = sum(1 for c in critiques if c.get("needs_human_review"))
    contexts_with_source_truth_evidence_count = sum(1 for c in critiques if int(c.get("source_truth_evidence_count") or 0) > 0)
    contexts_with_guidance_separation_count = sum(
        1 for c in critiques if int(c.get("safe_guidance_item_count") or 0) == int(c.get("guidance_item_count") or 0) and int(c.get("guidance_item_count") or 0) > 0
    )
    contexts_with_graph_or_summary_guidance_count = sum(1 for c in critiques if int(c.get("graph_or_summary_guidance_count") or 0) > 0)
    graph_summary_proof_violation_count = sum(
        1 for c in critiques for f in as_list(c.get("findings")) if isinstance(f, Mapping) and f.get("name") == "all_guidance_is_not_source_truth" and not f.get("passed")
    )
    answer_permission_count = truthy_count(critiques, "answer_permission")
    can_answer_directly_count = truthy_count(critiques, "can_answer_directly")
    can_prove_claims_count = truthy_count(critiques, "can_prove_claims")
    source_truth_mutation_allowed_count = truthy_count(critiques, "source_truth_mutation_allowed")

    quality_checks: List[Dict[str, Any]] = [
        make_quality_check("context_pack_count", len(packs), f">= {min_context_packs}", len(packs) >= min_context_packs),
        make_quality_check("self_rag_critique_count", len(critiques), f">= {min_context_critiques}", len(critiques) >= min_context_critiques),
        make_quality_check("ready_context_count", ready_context_count, f">= {min_ready_contexts}", ready_context_count >= min_ready_contexts),
        make_quality_check(
            "contexts_with_source_truth_evidence_count",
            contexts_with_source_truth_evidence_count,
            f">= {min_contexts_with_source_truth_evidence}",
            contexts_with_source_truth_evidence_count >= min_contexts_with_source_truth_evidence,
        ),
        make_quality_check(
            "contexts_with_guidance_separation_count",
            contexts_with_guidance_separation_count,
            f">= {min_contexts_with_guidance_separation}",
            contexts_with_guidance_separation_count >= min_contexts_with_guidance_separation,
        ),
        make_quality_check("human_review_count", human_review_count, f"<= {max_human_review_count}", human_review_count <= max_human_review_count),
        make_quality_check(
            "graph_summary_proof_violation_count",
            graph_summary_proof_violation_count,
            f"<= {max_graph_summary_proof_violations}",
            graph_summary_proof_violation_count <= max_graph_summary_proof_violations,
        ),
        make_quality_check("answer_permission_count", answer_permission_count, f"<= {max_answer_permission_count}", answer_permission_count <= max_answer_permission_count),
        make_quality_check(
            "source_truth_mutation_allowed_count",
            source_truth_mutation_allowed_count,
            f"<= {max_source_truth_mutation_allowed}",
            source_truth_mutation_allowed_count <= max_source_truth_mutation_allowed,
        ),
        make_quality_check("contract_answer_permission", answer_permission_count, "== 0", answer_permission_count == 0),
        make_quality_check("contract_can_answer_directly", can_answer_directly_count, "== 0", can_answer_directly_count == 0),
        make_quality_check("contract_can_prove_claims", can_prove_claims_count, "== 0", can_prove_claims_count == 0),
    ]
    if max_needs_crag_retry_count is not None:
        quality_checks.append(
            make_quality_check("needs_crag_retry_count", needs_crag_retry_count, f"<= {max_needs_crag_retry_count}", needs_crag_retry_count <= max_needs_crag_retry_count)
        )
    if require_no_answer_permission:
        quality_checks.append(make_quality_check("require_no_answer_permission", answer_permission_count, "== 0", answer_permission_count == 0))

    quality_status = "PASS" if all(check["passed"] for check in quality_checks) else "FAIL"
    e2e_status = STATUS_READY_FOR_CRAG_OR_PROMPT if quality_status == "PASS" else STATUS_NOT_READY

    summary = {
        "quality_status": quality_status,
        "context_pack_count": len(packs),
        "self_rag_critique_count": len(critiques),
        "ready_context_count": ready_context_count,
        "weak_context_count": weak_context_count,
        "needs_crag_retry_count": needs_crag_retry_count,
        "human_review_count": human_review_count,
        "contexts_with_source_truth_evidence_count": contexts_with_source_truth_evidence_count,
        "contexts_with_guidance_separation_count": contexts_with_guidance_separation_count,
        "contexts_with_graph_or_summary_guidance_count": contexts_with_graph_or_summary_guidance_count,
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
        "e2e_self_rag_context_critic_status": e2e_status,
        "quality_status": quality_status,
        "source_dynamic_context_pack_path": str(dynamic_context_pack),
        "summary": summary,
        "self_rag_context_critic_contract": {
            "uses_prebuilt_context_packs": True,
            "critic_does_not_call_llm": True,
            "critic_does_not_rerun_retrieval": True,
            "reruns_ocr": False,
            "reruns_page_classification": False,
            "reruns_embeddings": False,
            "reruns_page_summaries": False,
            "reruns_graph_build": False,
            "reruns_table_extraction": False,
            "evidence_box_is_source_truth": True,
            "guidance_box_is_not_source_truth": True,
            "graph_is_not_proof_authority": True,
            "summaries_are_not_source_truth": True,
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
        },
        "critiques": critiques,
        "quality_checks": quality_checks,
    }


def render_markdown_report(report: Mapping[str, Any]) -> str:
    summary = dict(report.get("summary") or {})
    lines = [
        "# TRACE-Net E2E Self-RAG Context Critic v9",
        "",
        f"Quality status: **{report.get('quality_status')}**",
        f"Status: `{report.get('e2e_self_rag_context_critic_status')}`",
        "",
        "## Summary",
    ]
    for key in [
        "context_pack_count",
        "self_rag_critique_count",
        "ready_context_count",
        "weak_context_count",
        "needs_crag_retry_count",
        "human_review_count",
        "contexts_with_source_truth_evidence_count",
        "contexts_with_guidance_separation_count",
        "contexts_with_graph_or_summary_guidance_count",
        "graph_summary_proof_violation_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
    ]:
        lines.append(f"- {key}: {summary.get(key, 0)}")

    lines.extend(["", "## Critiques"])
    for critique in as_list(report.get("critiques"))[:20]:
        if not isinstance(critique, Mapping):
            continue
        lines.append(
            f"- **{critique.get('self_rag_critic_status')}** `{critique.get('context_pack_id')}` | "
            f"intent={critique.get('query_intent')} | evidence={critique.get('evidence_item_count')} | "
            f"relevant={critique.get('intent_relevant_evidence_count')} | warnings={critique.get('warning_count')} | blockers={critique.get('blocker_count')}"
        )

    lines.extend(["", "## Quality checks"])
    for check in as_list(report.get("quality_checks")):
        if isinstance(check, Mapping):
            prefix = "PASS" if check.get("passed") else "FAIL"
            lines.append(f"- {prefix} {check.get('name')}: observed={check.get('observed')} expected={check.get('expected')}")
    lines.append("")
    return "\n".join(lines)


def write_report_files(report: Mapping[str, Any], output_dir: Path | str) -> Dict[str, str]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / "trace_net_e2e_self_rag_context_critic_v9.json"
    critiques_jsonl_path = out / "trace_net_e2e_self_rag_context_critic_records_v9.jsonl"
    inspect_md_path = out / "trace_net_e2e_self_rag_context_critic_v9.md"
    write_json(report_path, report)
    write_jsonl(critiques_jsonl_path, [row for row in as_list(report.get("critiques")) if isinstance(row, Mapping)])
    inspect_md_path.write_text(render_markdown_report(report), encoding="utf-8")
    return {
        "report_path": str(report_path),
        "critiques_jsonl_path": str(critiques_jsonl_path),
        "inspect_md_path": str(inspect_md_path),
    }


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dynamic-context-pack", required=True)
    parser.add_argument("--output-dir", default="local_data/organization/trace_net/e2e_self_rag_context_critic")
    parser.add_argument("--min-context-packs", type=int, default=1)
    parser.add_argument("--min-context-critiques", type=int, default=1)
    parser.add_argument("--min-ready-contexts", type=int, default=1)
    parser.add_argument("--min-contexts-with-source-truth-evidence", type=int, default=1)
    parser.add_argument("--min-contexts-with-guidance-separation", type=int, default=1)
    parser.add_argument("--max-needs-crag-retry-count", type=int, default=None)
    parser.add_argument("--max-human-review-count", type=int, default=0)
    parser.add_argument("--max-graph-summary-proof-violations", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--quality", action="store_true")


def build_from_args(args: argparse.Namespace) -> Dict[str, Any]:
    return build_self_rag_context_critic(
        args.dynamic_context_pack,
        min_context_packs=args.min_context_packs,
        min_context_critiques=args.min_context_critiques,
        min_ready_contexts=args.min_ready_contexts,
        min_contexts_with_source_truth_evidence=args.min_contexts_with_source_truth_evidence,
        min_contexts_with_guidance_separation=args.min_contexts_with_guidance_separation,
        max_needs_crag_retry_count=args.max_needs_crag_retry_count,
        max_human_review_count=args.max_human_review_count,
        max_graph_summary_proof_violations=args.max_graph_summary_proof_violations,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_no_answer_permission=args.require_no_answer_permission,
    )
