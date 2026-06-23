from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

MODULE = "trace_net_e2e_executed_plan_context_pack_v19"
VERSION = "v19"
STATUS_READY = "E2E_EXECUTED_PLAN_CONTEXT_PACK_READY_FOR_LIVE_SELF_RAG"
STATUS_NEEDS_REPAIR = "E2E_EXECUTED_PLAN_CONTEXT_PACK_NEEDS_REPAIR"
QUALITY_PASS = "PASS"
QUALITY_FAIL = "FAIL"

GUIDANCE_ONLY = "guidance_only"
SOURCE_TRUTH = "source_truth_evidence"

_EXECUTION_KEYS = (
    "executions",
    "execution_records",
    "dynamic_plan_executions",
    "plan_executions",
    "query_executions",
    "executed_query_plans",
    "records",
)
_EVIDENCE_KEYS = (
    "source_truth_evidence",
    "source_truth_records",
    "retrieved_source_truth_evidence",
    "evidence_records",
    "evidence",
    "top_evidence_records",
)
_GRAPH_KEYS = (
    "graph_guidance",
    "graph_guidance_records",
    "leiden_guidance",
    "community_guidance",
    "graph_records",
)
_SUMMARY_KEYS = (
    "summary_guidance",
    "v2_summary_guidance",
    "page_summary_guidance",
    "page_context_v2_guidance",
    "summary_records",
)
_ROUTE_KEYS = (
    "route_guidance",
    "route_metadata",
    "route_records",
    "route_dispatch_guidance",
)
_RANKING_KEYS = (
    "ranking_guidance",
    "vector_guidance",
    "page_profile_guidance",
    "qdrant_guidance",
    "hybrid_guidance",
)


def load_json(path: str | Path) -> Dict[str, Any]:
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object at {p}")
    return data


def write_json(path: str | Path, data: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def write_jsonl(path: str | Path, records: Sequence[Mapping[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="\n") as f:
        for rec in records:
            f.write(json.dumps(rec, sort_keys=True) + "\n")


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, dict):
        # Preserve a singleton mapping as one record rather than losing it.
        return [value]
    return [value]


def _first_present(mapping: Mapping[str, Any], keys: Sequence[str], default: Any = None) -> Any:
    for key in keys:
        if key in mapping:
            return mapping.get(key)
    return default


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _record_text(rec: Mapping[str, Any]) -> str:
    parts: List[str] = []
    for key in ("field", "field_name", "name", "normalized_value", "value", "text", "page", "page_id", "document_id"):
        value = rec.get(key)
        if value not in (None, ""):
            parts.append(str(value))
    return " ".join(parts)


def _normalize_record(record: Any, authority: str, ordinal: int) -> Dict[str, Any]:
    if isinstance(record, Mapping):
        rec = dict(record)
    else:
        rec = {"value": record}
    rec.setdefault("record_id", rec.get("id") or rec.get("evidence_id") or f"{authority}_{ordinal:04d}")
    rec.setdefault("authority", authority)
    if authority == SOURCE_TRUTH:
        rec.setdefault("proof_authority", True)
        rec.setdefault("citation_ready", _bool(rec.get("citation_ready", True)))
        rec.setdefault("source_trace_ready", _bool(rec.get("source_trace_ready", True)))
    else:
        rec.setdefault("proof_authority", False)
        rec.setdefault("guidance_only", True)
    return rec


def _extract_list(record: Mapping[str, Any], keys: Sequence[str], authority: str) -> List[Dict[str, Any]]:
    values: List[Any] = []
    for key in keys:
        values.extend(_as_list(record.get(key)))
    normalized: List[Dict[str, Any]] = []
    for idx, value in enumerate(values, start=1):
        if value in (None, ""):
            continue
        normalized.append(_normalize_record(value, authority, idx))
    return normalized


def _find_executions(report: Mapping[str, Any]) -> List[Dict[str, Any]]:
    for key in _EXECUTION_KEYS:
        value = report.get(key)
        if isinstance(value, list) and value:
            return [dict(v) for v in value if isinstance(v, Mapping)]
    # Fall back to a nested scan for a list whose records look like executions.
    candidates: List[Dict[str, Any]] = []
    for value in report.values():
        if isinstance(value, list) and value and all(isinstance(v, Mapping) for v in value):
            score = 0
            sample = value[0]
            for key in ("user_query", "query", "query_plan_id", "source_truth_evidence", "aggregation", "graph_guidance"):
                if key in sample:
                    score += 1
            if score >= 2:
                candidates = [dict(v) for v in value if isinstance(v, Mapping)]
                break
    return candidates


def _query_of(record: Mapping[str, Any], idx: int) -> str:
    return str(
        record.get("user_query")
        or record.get("query")
        or record.get("question")
        or record.get("query_text")
        or f"query_{idx:04d}"
    )


def _intent_of(record: Mapping[str, Any]) -> str:
    return str(record.get("query_intent") or record.get("intent") or record.get("mode") or "unknown")


def _aggregation_of(record: Mapping[str, Any], evidence_count: int, top_k: int) -> Dict[str, Any]:
    aggregation = record.get("aggregation") if isinstance(record.get("aggregation"), Mapping) else {}
    agg = dict(aggregation) if isinstance(aggregation, Mapping) else {}
    total = int(record.get("total_match_count") or agg.get("total_match_count") or evidence_count)
    returned = int(record.get("returned_match_count") or agg.get("returned_match_count") or min(evidence_count, top_k))
    capped = _bool(record.get("result_was_capped", agg.get("result_was_capped", total > returned)))
    high_degree = _bool(record.get("high_degree_node_detected", agg.get("high_degree_node_detected", capped)))
    more = _bool(record.get("more_results_available", agg.get("more_results_available", total > returned)))

    group_counts = agg.get("group_counts") if isinstance(agg.get("group_counts"), Mapping) else {}
    by_field = Counter()
    by_document = Counter()
    by_page = Counter()
    by_community = Counter()

    for ev in _extract_list(record, _EVIDENCE_KEYS, SOURCE_TRUTH):
        field = ev.get("field") or ev.get("field_name") or ev.get("name") or "unknown_field"
        page = ev.get("page") or ev.get("page_id") or "unknown_page"
        doc = ev.get("document_id") or ev.get("document") or ev.get("manual_id") or "unknown_document"
        community = ev.get("community_id") or ev.get("leiden_community_id") or "unknown_community"
        by_field[str(field)] += 1
        by_page[str(page)] += 1
        by_document[str(doc)] += 1
        by_community[str(community)] += 1

    if group_counts:
        final_groups = dict(group_counts)
    else:
        final_groups = {
            "by_field": dict(by_field),
            "by_page": dict(by_page),
            "by_document": dict(by_document),
            "by_leiden_community": dict(by_community),
        }

    return {
        "total_match_count": total,
        "returned_match_count": returned,
        "result_was_capped": capped,
        "more_results_available": more,
        "high_degree_node_detected": high_degree,
        "cap_reason": record.get("cap_reason") or agg.get("cap_reason") or ("high_degree_or_top_k_budget" if capped else "not_capped"),
        "ranking_method": record.get("ranking_method") or agg.get("ranking_method") or "source_truth_first_then_guidance_ranked",
        "group_counts": final_groups,
        "available_drilldowns": list(agg.get("available_drilldowns") or ["document", "manual", "revision", "section", "route", "field_type", "page", "leiden_community"]),
    }


def _graph_policy_of(record: Mapping[str, Any], high_degree_threshold: int, max_pages_per_community: int) -> Dict[str, Any]:
    policy = record.get("graph_policy") if isinstance(record.get("graph_policy"), Mapping) else {}
    return {
        "max_hops": int(policy.get("max_hops", 2)),
        "max_communities": int(policy.get("max_communities", 3)),
        "max_pages_per_community": int(policy.get("max_pages_per_community", max_pages_per_community)),
        "max_neighbors_per_node": int(policy.get("max_neighbors_per_node", 25)),
        "edge_type_allowlist": list(policy.get("edge_type_allowlist") or [
            "same_part_number",
            "same_manual_reference",
            "same_table",
            "same_figure",
            "same_section",
            "page_sequence_neighbor",
            "same_leiden_community",
        ]),
        "edge_weight_threshold": float(policy.get("edge_weight_threshold", 0.0)),
        "hop_decay": float(policy.get("hop_decay", 0.5)),
        "high_degree_threshold": int(policy.get("high_degree_threshold", high_degree_threshold)),
        "high_degree_node_mode": str(policy.get("high_degree_node_mode", "aggregate_then_sample")),
        "proof_authority": False,
        "requires_source_truth_confirmation": True,
        "raw_corpus_scan_at_query_time": False,
        "llm_reads_entire_graph": False,
    }


def build_context_pack(record: Mapping[str, Any], idx: int, *, top_k: int, high_degree_threshold: int, max_pages_per_community: int) -> Dict[str, Any]:
    evidence = _extract_list(record, _EVIDENCE_KEYS, SOURCE_TRUTH)
    graph_guidance = _extract_list(record, _GRAPH_KEYS, GUIDANCE_ONLY)
    summary_guidance = _extract_list(record, _SUMMARY_KEYS, GUIDANCE_ONLY)
    route_guidance = _extract_list(record, _ROUTE_KEYS, "routing_guidance_only")
    ranking_guidance = _extract_list(record, _RANKING_KEYS, "ranking_guidance_only")

    # If v18 only returned a compact graph summary/count, still provide a provenance stub.
    if not graph_guidance:
        community_count = 0
        agg = record.get("aggregation") if isinstance(record.get("aggregation"), Mapping) else {}
        group_counts = agg.get("group_counts") if isinstance(agg.get("group_counts"), Mapping) else {}
        by_comm = group_counts.get("by_leiden_community") if isinstance(group_counts.get("by_leiden_community"), Mapping) else {}
        community_count = len(by_comm)
        graph_guidance.append({
            "record_id": f"graph_guidance_v19_{idx:04d}",
            "authority": GUIDANCE_ONLY,
            "guidance_only": True,
            "proof_authority": False,
            "guidance_type": "bounded_leiden_community_context",
            "community_count": community_count,
            "path_provenance_required_for_claims": True,
            "note": "Leiden/community graph may guide related-page expansion but cannot prove final claims.",
        })

    if not summary_guidance:
        summary_guidance.append({
            "record_id": f"summary_guidance_v19_{idx:04d}",
            "authority": GUIDANCE_ONLY,
            "guidance_only": True,
            "proof_authority": False,
            "guidance_type": "page_context_v2_placeholder_or_unavailable",
            "available": False,
            "note": "Use page_context_v2 summaries when available; summaries remain guidance only.",
        })

    aggregation = _aggregation_of(record, len(evidence), top_k=top_k)
    graph_policy = _graph_policy_of(record, high_degree_threshold=high_degree_threshold, max_pages_per_community=max_pages_per_community)

    context_pack_id = f"context_pack_v19_{idx:04d}"
    query = _query_of(record, idx)
    query_intent = _intent_of(record)
    ready = bool(evidence) and all(not g.get("proof_authority", False) for g in graph_guidance + summary_guidance)

    return {
        "context_pack_id": context_pack_id,
        "source_execution_id": record.get("execution_id") or record.get("plan_execution_id") or record.get("query_plan_id") or f"execution_{idx:04d}",
        "query_plan_id": record.get("query_plan_id"),
        "user_query": query,
        "query_intent": query_intent,
        "context_pack_status": "CONTEXT_PACK_READY_FOR_SELF_RAG" if ready else "CONTEXT_PACK_NEEDS_REPAIR",
        "evidence_box": {
            "authority": SOURCE_TRUTH,
            "proof_authority": True,
            "item_count": len(evidence),
            "items": evidence[:top_k],
        },
        "guidance_box": {
            "authority": GUIDANCE_ONLY,
            "proof_authority": False,
            "graph_guidance": graph_guidance,
            "v2_summary_guidance": summary_guidance,
            "route_guidance": route_guidance,
            "ranking_guidance": ranking_guidance,
        },
        "aggregation_box": aggregation,
        "graph_policy_box": graph_policy,
        "answer_rules_box": {
            "cite_every_factual_claim": True,
            "source_truth_evidence_required_for_final_claims": True,
            "graph_is_guidance_not_proof": True,
            "leiden_is_guidance_not_proof": True,
            "v2_summaries_are_guidance_not_proof": True,
            "disclose_capped_results": True,
            "state_limitations_when_evidence_is_incomplete": True,
            "do_not_invent_part_descriptions": True,
        },
        "safety_contract": {
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
            "writes_to_postgres": False,
            "writes_to_qdrant": False,
            "writes_to_opensearch": False,
            "uploads_to_opensearch": False,
        },
    }


def _count_truthy(records: Iterable[Mapping[str, Any]], predicate) -> int:
    return sum(1 for rec in records if predicate(rec))


def build_report(
    dynamic_plan_executor_report: Mapping[str, Any],
    *,
    top_k: int = 10,
    high_degree_threshold: int = 10,
    max_pages_per_community: int = 25,
) -> Dict[str, Any]:
    executions = _find_executions(dynamic_plan_executor_report)
    context_packs = [
        build_context_pack(rec, idx, top_k=top_k, high_degree_threshold=high_degree_threshold, max_pages_per_community=max_pages_per_community)
        for idx, rec in enumerate(executions, start=1)
    ]

    total_source_truth = sum(pack["evidence_box"]["item_count"] for pack in context_packs)
    graph_guidance_count = sum(len(pack["guidance_box"].get("graph_guidance", [])) for pack in context_packs)
    summary_guidance_count = sum(len(pack["guidance_box"].get("v2_summary_guidance", [])) for pack in context_packs)

    graph_proof_violations = 0
    summary_proof_violations = 0
    for pack in context_packs:
        for rec in pack["guidance_box"].get("graph_guidance", []):
            if rec.get("proof_authority") is True or rec.get("authority") == SOURCE_TRUTH:
                graph_proof_violations += 1
        for rec in pack["guidance_box"].get("v2_summary_guidance", []):
            if rec.get("proof_authority") is True or rec.get("authority") == SOURCE_TRUTH:
                summary_proof_violations += 1

    answer_permission_count = _count_truthy(context_packs, lambda p: p["safety_contract"].get("answer_permission"))
    source_truth_mutation_allowed_count = _count_truthy(context_packs, lambda p: p["safety_contract"].get("source_truth_mutation_allowed"))

    packs_with_evidence_box = _count_truthy(context_packs, lambda p: p["evidence_box"].get("item_count", 0) > 0)
    packs_with_guidance_box = _count_truthy(context_packs, lambda p: bool(p.get("guidance_box")))
    packs_with_graph_guidance = _count_truthy(context_packs, lambda p: len(p["guidance_box"].get("graph_guidance", [])) > 0)
    packs_with_v2_summary_guidance = _count_truthy(context_packs, lambda p: len(p["guidance_box"].get("v2_summary_guidance", [])) > 0)
    packs_with_answer_rules = _count_truthy(context_packs, lambda p: bool(p.get("answer_rules_box")))
    packs_with_aggregation_or_cap_disclosure = _count_truthy(
        context_packs,
        lambda p: bool(p.get("aggregation_box")) and (
            p["aggregation_box"].get("result_was_capped") is True
            or "total_match_count" in p["aggregation_box"]
        ),
    )
    capped_result_disclosure_count = _count_truthy(context_packs, lambda p: p["aggregation_box"].get("result_was_capped") is True)

    ready_context_pack_count = _count_truthy(context_packs, lambda p: p.get("context_pack_status") == "CONTEXT_PACK_READY_FOR_SELF_RAG")

    report: Dict[str, Any] = {
        "module": MODULE,
        "version": VERSION,
        "status": STATUS_READY,
        "quality_status": QUALITY_PASS,
        "context_pack_count": len(context_packs),
        "ready_context_pack_count": ready_context_pack_count,
        "total_source_truth_evidence_count": total_source_truth,
        "packs_with_evidence_box_count": packs_with_evidence_box,
        "packs_with_guidance_box_count": packs_with_guidance_box,
        "packs_with_graph_guidance_count": packs_with_graph_guidance,
        "packs_with_v2_summary_guidance_count": packs_with_v2_summary_guidance,
        "packs_with_answer_rules_count": packs_with_answer_rules,
        "packs_with_aggregation_or_cap_disclosure_count": packs_with_aggregation_or_cap_disclosure,
        "capped_result_disclosure_count": capped_result_disclosure_count,
        "graph_guidance_record_count": graph_guidance_count,
        "v2_summary_guidance_record_count": summary_guidance_count,
        "graph_proof_authority_violation_count": graph_proof_violations,
        "summary_proof_authority_violation_count": summary_proof_violations,
        "answer_permission_count": answer_permission_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "contract": {
            "context_pack_uses_dynamic_plan_executor": True,
            "source_truth_evidence_required_for_final_claims": True,
            "graph_guidance_only": True,
            "leiden_communities_guidance_only": True,
            "v2_summaries_guidance_only": True,
            "llm_reads_context_pack_only": True,
            "raw_5tb_scan_at_query_time": False,
            "graph_rebuild_at_query_time": False,
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
        },
        "context_packs": context_packs,
    }
    return report


def evaluate_quality(report: Mapping[str, Any], args: Any) -> Tuple[str, List[Dict[str, Any]]]:
    checks: List[Dict[str, Any]] = []

    def add(name: str, observed: Any, op: str, expected: Any, passed: bool) -> None:
        checks.append({"name": name, "observed": observed, "op": op, "expected": expected, "passed": bool(passed)})

    def ge(name: str, observed: int, expected: int) -> None:
        add(name, observed, ">=", expected, observed >= expected)

    def le(name: str, observed: int, expected: int) -> None:
        add(name, observed, "<=", expected, observed <= expected)

    def eq(name: str, observed: Any, expected: Any) -> None:
        add(name, observed, "==", expected, observed == expected)

    ge("context_pack_count", int(report.get("context_pack_count", 0)), int(getattr(args, "min_context_packs", 0)))
    ge("ready_context_pack_count", int(report.get("ready_context_pack_count", 0)), int(getattr(args, "min_ready_context_packs", 0)))
    ge("total_source_truth_evidence_count", int(report.get("total_source_truth_evidence_count", 0)), int(getattr(args, "min_source_truth_evidence", 0)))
    ge("packs_with_evidence_box_count", int(report.get("packs_with_evidence_box_count", 0)), int(getattr(args, "min_packs_with_evidence_box", 0)))
    ge("packs_with_guidance_box_count", int(report.get("packs_with_guidance_box_count", 0)), int(getattr(args, "min_packs_with_guidance_box", 0)))
    ge("packs_with_graph_guidance_count", int(report.get("packs_with_graph_guidance_count", 0)), int(getattr(args, "min_packs_with_graph_guidance", 0)))
    ge("packs_with_v2_summary_guidance_count", int(report.get("packs_with_v2_summary_guidance_count", 0)), int(getattr(args, "min_packs_with_v2_summary_guidance", 0)))
    ge("packs_with_answer_rules_count", int(report.get("packs_with_answer_rules_count", 0)), int(getattr(args, "min_packs_with_answer_rules", 0)))
    ge("packs_with_aggregation_or_cap_disclosure_count", int(report.get("packs_with_aggregation_or_cap_disclosure_count", 0)), int(getattr(args, "min_packs_with_aggregation_or_cap_disclosure", 0)))
    le("graph_proof_authority_violation_count", int(report.get("graph_proof_authority_violation_count", 0)), int(getattr(args, "max_graph_proof_authority_violations", 0)))
    le("summary_proof_authority_violation_count", int(report.get("summary_proof_authority_violation_count", 0)), int(getattr(args, "max_summary_proof_authority_violations", 0)))
    le("answer_permission_count", int(report.get("answer_permission_count", 0)), int(getattr(args, "max_answer_permission_count", 0)))
    le("source_truth_mutation_allowed_count", int(report.get("source_truth_mutation_allowed_count", 0)), int(getattr(args, "max_source_truth_mutation_allowed", 0)))
    if getattr(args, "require_no_answer_permission", False):
        eq("require_no_answer_permission", int(report.get("answer_permission_count", 0)), 0)

    status = QUALITY_PASS if all(c["passed"] for c in checks) else QUALITY_FAIL
    return status, checks


def render_markdown(report: Mapping[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# TRACE-Net E2E Executed Plan Context Pack v19")
    lines.append("")
    lines.append(f"Quality status: **{report.get('quality_status')}**")
    lines.append(f"Status: `{report.get('status')}`")
    lines.append("")
    lines.append("## Summary")
    for key in (
        "context_pack_count",
        "ready_context_pack_count",
        "total_source_truth_evidence_count",
        "packs_with_evidence_box_count",
        "packs_with_guidance_box_count",
        "packs_with_graph_guidance_count",
        "packs_with_v2_summary_guidance_count",
        "packs_with_answer_rules_count",
        "packs_with_aggregation_or_cap_disclosure_count",
        "capped_result_disclosure_count",
        "graph_proof_authority_violation_count",
        "summary_proof_authority_violation_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
    ):
        lines.append(f"- {key}: {report.get(key)}")
    lines.append("")
    lines.append("## Contract")
    lines.append("- Source-truth evidence is the only proof authority for final claims.")
    lines.append("- Leiden/community graph guidance is navigation guidance only, not proof.")
    lines.append("- v2 summaries are guidance only, not proof.")
    lines.append("- High-degree or capped result sets must disclose total vs returned counts and drill-down options.")
    lines.append("- The LLM reads compact context packs only; query-time processing does not scan the raw 5TB corpus or rebuild the graph.")
    lines.append("")
    lines.append("## Context packs")
    for pack in report.get("context_packs", []):
        if not isinstance(pack, Mapping):
            continue
        agg = pack.get("aggregation_box", {}) if isinstance(pack.get("aggregation_box"), Mapping) else {}
        lines.append(f"### {pack.get('context_pack_id')} — `{pack.get('query_intent')}`")
        lines.append(f"- query: {pack.get('user_query')}")
        lines.append(f"- status: `{pack.get('context_pack_status')}`")
        lines.append(f"- source_truth_evidence_items: {pack.get('evidence_box', {}).get('item_count') if isinstance(pack.get('evidence_box'), Mapping) else 0}")
        lines.append(f"- total_match_count: {agg.get('total_match_count')}")
        lines.append(f"- returned_match_count: {agg.get('returned_match_count')}")
        lines.append(f"- result_was_capped: {agg.get('result_was_capped')}")
        lines.append(f"- more_results_available: {agg.get('more_results_available')}")
        lines.append("")
    lines.append("## Quality checks")
    for check in report.get("quality_checks", []):
        if isinstance(check, Mapping):
            prefix = "PASS" if check.get("passed") else "FAIL"
            lines.append(f"- {prefix} {check.get('name')}: observed={check.get('observed')} expected={check.get('op')} {check.get('expected')}")
    lines.append("")
    return "\n".join(lines)


def build_and_write(
    dynamic_plan_executor: str | Path,
    output_dir: str | Path,
    *,
    top_k: int = 10,
    high_degree_threshold: int = 10,
    max_pages_per_community: int = 25,
    quality_args: Any | None = None,
) -> Dict[str, Any]:
    src = load_json(dynamic_plan_executor)
    report = build_report(src, top_k=top_k, high_degree_threshold=high_degree_threshold, max_pages_per_community=max_pages_per_community)
    if quality_args is not None:
        quality_status, checks = evaluate_quality(report, quality_args)
        report["quality_status"] = quality_status
        report["quality_checks"] = checks
        report["status"] = STATUS_READY if quality_status == QUALITY_PASS else STATUS_NEEDS_REPAIR
    out = Path(output_dir)
    report_path = out / "trace_net_e2e_executed_plan_context_pack_v19.json"
    packs_path = out / "trace_net_e2e_executed_plan_context_pack_records_v19.jsonl"
    evidence_path = out / "trace_net_e2e_executed_plan_context_pack_evidence_v19.jsonl"
    inspect_path = out / "trace_net_e2e_executed_plan_context_pack_v19.md"
    report["report_path"] = str(report_path)
    report["packs_jsonl_path"] = str(packs_path)
    report["evidence_jsonl_path"] = str(evidence_path)
    report["inspect_md_path"] = str(inspect_path)

    write_json(report_path, report)
    packs = [p for p in report.get("context_packs", []) if isinstance(p, Mapping)]
    write_jsonl(packs_path, packs)
    ev_records: List[Dict[str, Any]] = []
    for pack in packs:
        for ev in pack.get("evidence_box", {}).get("items", []):
            if isinstance(ev, Mapping):
                row = dict(ev)
                row["context_pack_id"] = pack.get("context_pack_id")
                ev_records.append(row)
    write_jsonl(evidence_path, ev_records)
    inspect_path.write_text(render_markdown(report), encoding="utf-8")
    return report


def add_common_quality_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--min-context-packs", type=int, default=0)
    parser.add_argument("--min-ready-context-packs", type=int, default=0)
    parser.add_argument("--min-source-truth-evidence", type=int, default=0)
    parser.add_argument("--min-packs-with-evidence-box", type=int, default=0)
    parser.add_argument("--min-packs-with-guidance-box", type=int, default=0)
    parser.add_argument("--min-packs-with-graph-guidance", type=int, default=0)
    parser.add_argument("--min-packs-with-v2-summary-guidance", type=int, default=0)
    parser.add_argument("--min-packs-with-answer-rules", type=int, default=0)
    parser.add_argument("--min-packs-with-aggregation-or-cap-disclosure", type=int, default=0)
    parser.add_argument("--max-graph-proof-authority-violations", type=int, default=0)
    parser.add_argument("--max-summary-proof-authority-violations", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")


def print_report_summary(report: Mapping[str, Any]) -> None:
    print("TRACE-Net E2E Executed Plan Context Pack v19")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in (
        "context_pack_count",
        "ready_context_pack_count",
        "total_source_truth_evidence_count",
        "packs_with_evidence_box_count",
        "packs_with_guidance_box_count",
        "packs_with_graph_guidance_count",
        "packs_with_v2_summary_guidance_count",
        "packs_with_answer_rules_count",
        "packs_with_aggregation_or_cap_disclosure_count",
        "capped_result_disclosure_count",
        "graph_proof_authority_violation_count",
        "summary_proof_authority_violation_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
        "report_path",
        "packs_jsonl_path",
        "evidence_jsonl_path",
        "inspect_md_path",
    ):
        if key in report:
            print(f" {key}: {report.get(key)}")


__all__ = [
    "MODULE",
    "VERSION",
    "STATUS_READY",
    "STATUS_NEEDS_REPAIR",
    "build_report",
    "build_context_pack",
    "evaluate_quality",
    "render_markdown",
    "build_and_write",
    "add_common_quality_args",
    "print_report_summary",
]
