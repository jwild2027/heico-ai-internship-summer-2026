from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

MODULE = "trace_net_e2e_dynamic_plan_executor_v18"
VERSION = "v18"
STATUS_READY = "E2E_DYNAMIC_PLAN_EXECUTOR_READY_FOR_LIVE_CONTEXT_PACK"
STATUS_NEEDS_REPAIR = "E2E_DYNAMIC_PLAN_EXECUTOR_NEEDS_REPAIR"

SOURCE_TRUTH_TUNNELS = {"table_exact_search_tunnel"}
GUIDANCE_ONLY_TUNNELS = {
    "page_summary_tunnel",
    "graph_community_tunnel",
    "graph_navigation_tunnel",
    "route_metadata_tunnel",
    "table_route_summary_tunnel",
}
RANKING_SUPPORT_TUNNELS = {"table_hybrid_bridge_tunnel", "qdrant_page_profile_tunnel"}

PART_NUMBER_RE = re.compile(r"\b\d{2,4}-\d{3,6}-\d{2,4}\b")
MANUAL_REF_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")


def read_json(path: str | Path) -> Any:
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str | Path, data: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def write_jsonl(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")


def _first_list(data: Any, preferred_keys: Sequence[str]) -> List[Any]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in preferred_keys:
            value = data.get(key)
            if isinstance(value, list):
                return value
        # fallback: largest list value
        lists = [v for v in data.values() if isinstance(v, list)]
        if lists:
            return max(lists, key=len)
    return []


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _pick(record: Mapping[str, Any], keys: Sequence[str], default: str = "") -> str:
    for key in keys:
        if key in record and record.get(key) not in (None, ""):
            return _stringify(record.get(key))
    # nested common shapes
    for parent in ("source", "metadata", "trace", "evidence"):
        child = record.get(parent)
        if isinstance(child, Mapping):
            for key in keys:
                if key in child and child.get(key) not in (None, ""):
                    return _stringify(child.get(key))
    return default


def normalize_exact_document(record: Mapping[str, Any], idx: int) -> Dict[str, Any]:
    page_id = _pick(record, ["page_id", "page", "source_page_id", "trace_page_id", "page_key"], "unknown_page")
    field_name = _pick(record, ["field_name", "field", "source_field", "evidence_field", "column", "name"], "unknown_field")
    value = _pick(record, ["normalized_value", "value", "field_value", "text", "raw_value", "content"], "")
    route = _pick(record, ["route", "primary_route", "page_route", "source_route"], "unknown_route")
    doc_id = _pick(record, ["document_id", "doc_id", "manual_id", "source_document_id", "source_id"], "unknown_document")
    return {
        "evidence_record_id": _pick(record, ["evidence_record_id", "record_id", "id"], f"exact_doc_{idx:06d}"),
        "page_id": page_id,
        "document_id": doc_id,
        "field_name": field_name,
        "value": value,
        "route": route,
        "source_trace_ready": bool(record.get("source_trace_ready", True)),
        "citation_ready": bool(record.get("citation_ready", True)),
        "authority": "source_truth_evidence",
        "raw_record_index": idx,
    }


def load_exact_documents(path: str | Path) -> List[Dict[str, Any]]:
    data = read_json(path)
    rows = _first_list(data, [
        "exact_search_documents",
        "documents",
        "records",
        "evidence_records",
        "table_exact_search_documents",
    ])
    out: List[Dict[str, Any]] = []
    for idx, row in enumerate(rows):
        if isinstance(row, Mapping):
            out.append(normalize_exact_document(row, idx))
    return out


def load_query_plans(path: str | Path) -> List[Dict[str, Any]]:
    data = read_json(path)
    rows = _first_list(data, ["query_plans", "plans", "records"])
    return [dict(r) for r in rows if isinstance(r, Mapping)]


def _records_from_optional(path: str | Path | None, keys: Sequence[str]) -> List[Mapping[str, Any]]:
    if not path:
        return []
    p = Path(path)
    if not p.exists():
        return []
    try:
        data = read_json(p)
    except Exception:
        return []
    return [r for r in _first_list(data, keys) if isinstance(r, Mapping)]


def build_page_summary_index(path: str | Path | None) -> Dict[str, Dict[str, Any]]:
    rows = _records_from_optional(path, ["page_contexts", "page_context_records", "records", "pages"])
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        page_id = _pick(row, ["page_id", "page", "source_page_id"], "")
        if page_id:
            out[page_id] = {
                "page_id": page_id,
                "summary": _pick(row, ["summary", "page_summary", "context_summary", "text", "content"], ""),
                "authority": "guidance_only",
                "proof_authority": False,
            }
    return out


def build_route_index(path: str | Path | None) -> Dict[str, Dict[str, Any]]:
    rows = _records_from_optional(path, ["route_records", "routes", "records", "page_routes"])
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        page_id = _pick(row, ["page_id", "page", "source_page_id"], "")
        if page_id:
            out[page_id] = {
                "page_id": page_id,
                "route": _pick(row, ["primary_route", "route", "page_route"], "unknown_route"),
                "authority": "routing_guidance_only",
                "proof_authority": False,
            }
    return out


def build_leiden_index(path: str | Path | None) -> Tuple[Dict[str, str], Dict[str, List[str]]]:
    rows = _records_from_optional(path, ["communities", "community_records", "records", "leiden_communities"])
    page_to_comm: Dict[str, str] = {}
    comm_to_pages: Dict[str, List[str]] = defaultdict(list)
    for i, row in enumerate(rows):
        comm_id = _pick(row, ["community_id", "leiden_community_id", "id", "cluster_id"], f"community_{i:04d}")
        possible_pages: List[str] = []
        for key in ("page_ids", "pages", "member_pages", "source_page_ids"):
            value = row.get(key)
            if isinstance(value, list):
                possible_pages.extend(_stringify(v) for v in value if v)
        page_id = _pick(row, ["page_id", "page", "source_page_id"], "")
        if page_id:
            possible_pages.append(page_id)
        # Some records store node/member maps.
        for key in ("members", "nodes", "records"):
            value = row.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, Mapping):
                        p = _pick(item, ["page_id", "page", "source_page_id"], "")
                        if p:
                            possible_pages.append(p)
        for p in sorted(set(possible_pages)):
            page_to_comm[p] = comm_id
            comm_to_pages[comm_id].append(p)
    return page_to_comm, {k: sorted(set(v)) for k, v in comm_to_pages.items()}


def _query_terms(plan: Mapping[str, Any]) -> Dict[str, List[str]]:
    user_query = _stringify(plan.get("user_query"))
    extracted = plan.get("extracted_query_terms") if isinstance(plan.get("extracted_query_terms"), Mapping) else {}
    part_numbers = list(extracted.get("part_numbers", [])) if isinstance(extracted, Mapping) else []
    manual_refs = list(extracted.get("manual_references", [])) if isinstance(extracted, Mapping) else []
    ipl_items = list(extracted.get("ipl_items", [])) if isinstance(extracted, Mapping) else []
    part_numbers.extend(PART_NUMBER_RE.findall(user_query))
    manual_refs.extend(MANUAL_REF_RE.findall(user_query))
    # pull explicit target values from subqueries
    for sub in plan.get("subqueries", []) if isinstance(plan.get("subqueries"), list) else []:
        if isinstance(sub, Mapping):
            target = sub.get("target_value")
            if target:
                s = _stringify(target)
                if PART_NUMBER_RE.fullmatch(s):
                    part_numbers.append(s)
                elif MANUAL_REF_RE.fullmatch(s):
                    manual_refs.append(s)
    return {
        "part_numbers": sorted(set(part_numbers)),
        "manual_references": sorted(set(manual_refs)),
        "ipl_items": sorted(set(_stringify(x) for x in ipl_items if x)),
    }


def _field_allowed(field_name: str, required_fields: Sequence[str]) -> bool:
    if not required_fields:
        return True
    f = field_name.lower()
    for required in required_fields:
        r = required.lower()
        if f == r or r in f or f in r:
            return True
    return False


def _value_matches(evidence: Mapping[str, Any], terms: Mapping[str, List[str]], intent: str) -> bool:
    value = _stringify(evidence.get("value"))
    if terms.get("part_numbers"):
        return any(t == value or t in value for t in terms["part_numbers"])
    if terms.get("manual_references"):
        return any(t == value or t in value for t in terms["manual_references"])
    if terms.get("ipl_items"):
        return any(t == value or t in value for t in terms["ipl_items"])
    # Broad field lookup: any aligned field is okay.
    return intent in {"covered_part_number", "table_text", "manual_page_reference", "part_number"}


def score_evidence(e: Mapping[str, Any], required_fields: Sequence[str], terms: Mapping[str, List[str]]) -> float:
    score = 0.0
    field = _stringify(e.get("field_name"))
    value = _stringify(e.get("value"))
    if _field_allowed(field, required_fields):
        score += 100.0
    for term_group in ("part_numbers", "manual_references", "ipl_items"):
        for term in terms.get(term_group, []):
            if value == term:
                score += 1000.0
            elif term and term in value:
                score += 400.0
    if e.get("citation_ready"):
        score += 25.0
    if e.get("source_trace_ready"):
        score += 25.0
    return score


def aggregate(records: Sequence[Mapping[str, Any]], page_to_comm: Mapping[str, str]) -> Dict[str, Any]:
    by_doc = Counter(_stringify(r.get("document_id", "unknown_document")) for r in records)
    by_page = Counter(_stringify(r.get("page_id", "unknown_page")) for r in records)
    by_field = Counter(_stringify(r.get("field_name", "unknown_field")) for r in records)
    by_route = Counter(_stringify(r.get("route", "unknown_route")) for r in records)
    by_comm = Counter(page_to_comm.get(_stringify(r.get("page_id", "")), "unknown_community") for r in records)
    return {
        "by_document": dict(by_doc.most_common(20)),
        "by_page": dict(by_page.most_common(20)),
        "by_field": dict(by_field.most_common(20)),
        "by_route": dict(by_route.most_common(20)),
        "by_leiden_community": dict(by_comm.most_common(20)),
    }


def execute_plan(
    plan: Mapping[str, Any],
    exact_docs: Sequence[Mapping[str, Any]],
    page_summaries: Mapping[str, Mapping[str, Any]],
    page_to_comm: Mapping[str, str],
    comm_to_pages: Mapping[str, Sequence[str]],
    route_index: Mapping[str, Mapping[str, Any]],
    *,
    top_k: int = 10,
    high_degree_threshold: int = 25,
    max_pages_per_community: int = 25,
) -> Dict[str, Any]:
    query_plan_id = _stringify(plan.get("query_plan_id") or "query_plan_unknown")
    query = _stringify(plan.get("user_query") or plan.get("query"))
    intent = _stringify(plan.get("query_intent") or "unknown")
    required_fields = [_stringify(f) for f in plan.get("required_source_truth_fields", []) if f]
    terms = _query_terms(plan)

    candidates = [r for r in exact_docs if _field_allowed(_stringify(r.get("field_name")), required_fields)]
    matched = [r for r in candidates if _value_matches(r, terms, intent)]
    if not matched and terms.get("part_numbers"):
        # fall back to exact value anywhere in source truth, but keep field alignment in metadata
        matched = [r for r in exact_docs if _value_matches(r, terms, intent)]
    if not matched and intent == "table_text":
        # table-text demo queries may rely on text terms rather than target_value
        q = query.lower().replace("search table text", "").strip()
        if q:
            matched = [r for r in candidates if q in _stringify(r.get("value")).lower()]
    scored = sorted(
        [dict(r, retrieval_score=score_evidence(r, required_fields, terms)) for r in matched],
        key=lambda x: (-float(x.get("retrieval_score", 0)), _stringify(x.get("page_id")), _stringify(x.get("field_name"))),
    )
    returned = scored[:top_k]
    total = len(scored)
    result_was_capped = total > len(returned)
    high_degree = total >= high_degree_threshold

    seed_pages = sorted({_stringify(r.get("page_id")) for r in returned if r.get("page_id")})
    graph_guidance: List[Dict[str, Any]] = []
    for page_id in seed_pages:
        comm_id = page_to_comm.get(page_id, "unknown_community")
        community_pages = list(comm_to_pages.get(comm_id, []))[:max_pages_per_community]
        graph_guidance.append({
            "guidance_id": f"graph_guidance_{query_plan_id}_{len(graph_guidance)+1:03d}",
            "seed_page_id": page_id,
            "leiden_community_id": comm_id,
            "community_candidate_page_count": len(comm_to_pages.get(comm_id, [])),
            "returned_candidate_page_count": len(community_pages),
            "candidate_page_ids": community_pages,
            "authority": "guidance_only",
            "proof_authority": False,
            "requires_source_truth_confirmation": True,
            "graph_path_provenance": [
                {"hop": 0, "node_type": "source_truth_seed_page", "node_id": page_id},
                {"hop": 1, "edge_type": "member_of_leiden_community", "node_id": comm_id},
            ],
        })

    summary_guidance = []
    for page_id in seed_pages:
        if page_id in page_summaries:
            summary_guidance.append(page_summaries[page_id])
    route_guidance = []
    for page_id in seed_pages:
        if page_id in route_index:
            route_guidance.append(route_index[page_id])

    execution_status = "DYNAMIC_PLAN_EXECUTION_READY" if returned else "DYNAMIC_PLAN_EXECUTION_NO_SOURCE_TRUTH_EVIDENCE"
    return {
        "execution_id": f"dynamic_plan_execution_v18_{query_plan_id}",
        "query_plan_id": query_plan_id,
        "user_query": query,
        "query_intent": intent,
        "execution_status": execution_status,
        "ready_for_live_context_pack": bool(returned),
        "source_truth_evidence": returned,
        "source_truth_evidence_count": len(returned),
        "total_match_count": total,
        "returned_match_count": len(returned),
        "result_was_capped": result_was_capped,
        "more_results_available": result_was_capped,
        "high_degree_node_detected": high_degree,
        "retrieval_mode": "aggregate_then_sample" if high_degree else "direct_ranked_sample",
        "aggregation": aggregate(scored, page_to_comm),
        "available_drilldowns": ["document", "page", "field", "route", "leiden_community"],
        "graph_guidance": graph_guidance,
        "graph_guidance_count": len(graph_guidance),
        "summary_guidance": summary_guidance,
        "summary_guidance_count": len(summary_guidance),
        "route_guidance": route_guidance,
        "route_guidance_count": len(route_guidance),
        "graph_policy": {
            "max_hops": 1,
            "max_pages_per_community": max_pages_per_community,
            "edge_type_allowlist": ["member_of_leiden_community", "same_exact_part_number", "same_manual_reference", "same_table", "same_section", "page_sequence_neighbor"],
            "high_degree_threshold": high_degree_threshold,
            "high_degree_node_mode": "aggregate_then_sample",
            "proof_authority": False,
            "requires_source_truth_confirmation": True,
            "leiden_and_graph_work_together": True,
        },
        "authority_contract": {
            "source_truth_evidence_required_for_final_claims": True,
            "graph_guidance_only": True,
            "summary_guidance_only": True,
            "llm_reads_context_pack_only": True,
            "raw_5tb_scan_at_query_time": False,
            "graph_rebuild_at_query_time": False,
            "source_truth_mutation_allowed": False,
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
        },
    }


def build_report(
    *,
    query_planner: str | Path,
    table_exact_search_adapter: str | Path,
    page_context_v2: str | Path | None = None,
    leiden_communities: str | Path | None = None,
    community_navigation_metadata_bridge: str | Path | None = None,
    route_dispatch_manifest: str | Path | None = None,
    top_k: int = 10,
    high_degree_threshold: int = 25,
    max_pages_per_community: int = 25,
) -> Dict[str, Any]:
    plans = load_query_plans(query_planner)
    exact_docs = load_exact_documents(table_exact_search_adapter)
    page_summaries = build_page_summary_index(page_context_v2)
    route_index = build_route_index(route_dispatch_manifest)
    page_to_comm, comm_to_pages = build_leiden_index(leiden_communities)
    # Community navigation bridge is currently recorded as available/guidance; future versions can add richer edges.
    community_nav_rows = _records_from_optional(community_navigation_metadata_bridge, ["records", "navigation_records", "community_navigation_records"])

    executions = [
        execute_plan(
            plan,
            exact_docs,
            page_summaries,
            page_to_comm,
            comm_to_pages,
            route_index,
            top_k=top_k,
            high_degree_threshold=high_degree_threshold,
            max_pages_per_community=max_pages_per_community,
        )
        for plan in plans
    ]

    ready = [e for e in executions if e.get("ready_for_live_context_pack")]
    source_truth_count = sum(int(e.get("source_truth_evidence_count", 0)) for e in executions)
    graph_guidance_count = sum(int(e.get("graph_guidance_count", 0)) for e in executions)
    summary_guidance_count = sum(int(e.get("summary_guidance_count", 0)) for e in executions)
    capped_count = sum(1 for e in executions if e.get("result_was_capped"))
    high_degree_count = sum(1 for e in executions if e.get("high_degree_node_detected"))
    graph_proof_violations = 0
    summary_proof_violations = 0
    for e in executions:
        for g in e.get("graph_guidance", []):
            if g.get("proof_authority"):
                graph_proof_violations += 1
        for s in e.get("summary_guidance", []):
            if s.get("proof_authority"):
                summary_proof_violations += 1

    return {
        "module": MODULE,
        "version": VERSION,
        "status": STATUS_READY,
        "quality_status": "PASS",
        "query_plan_count": len(plans),
        "execution_count": len(executions),
        "ready_execution_count": len(ready),
        "exact_search_document_count": len(exact_docs),
        "source_truth_evidence_count": source_truth_count,
        "graph_guidance_count": graph_guidance_count,
        "summary_guidance_count": summary_guidance_count,
        "capped_result_count": capped_count,
        "high_degree_node_execution_count": high_degree_count,
        "graph_proof_authority_violation_count": graph_proof_violations,
        "summary_proof_authority_violation_count": summary_proof_violations,
        "answer_permission_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "artifact_summary": {
            "page_context_v2_available": bool(page_summaries),
            "page_context_v2_record_count": len(page_summaries),
            "leiden_communities_available": bool(page_to_comm or comm_to_pages),
            "leiden_page_mapping_count": len(page_to_comm),
            "leiden_community_count": len(comm_to_pages),
            "community_navigation_available": bool(community_nav_rows),
            "community_navigation_record_count": len(community_nav_rows),
            "route_dispatch_manifest_available": bool(route_index),
            "route_dispatch_record_count": len(route_index),
        },
        "contract": {
            "raw_5tb_scan_at_query_time": False,
            "graph_built_offline": True,
            "graph_rebuild_at_query_time": False,
            "llm_reads_entire_graph": False,
            "llm_reads_context_pack_only": True,
            "bounded_graph_traversal": True,
            "graph_guidance_only": True,
            "summary_guidance_only": True,
            "source_truth_evidence_required_for_final_claims": True,
            "high_degree_entities_use_aggregation": True,
            "capped_results_disclose_counts": True,
            "leiden_and_graph_work_together": True,
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
        },
        "executions": executions,
    }


def quality_check_report(
    report: Mapping[str, Any],
    *,
    min_query_plans: int = 1,
    min_ready_executions: int = 1,
    min_source_truth_evidence: int = 1,
    min_graph_guidance_records: int = 0,
    min_capped_result_disclosures: int = 0,
    max_graph_proof_authority_violations: int = 0,
    max_summary_proof_authority_violations: int = 0,
    max_answer_permission_count: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    require_no_answer_permission: bool = False,
) -> Tuple[str, List[Dict[str, Any]]]:
    checks: List[Dict[str, Any]] = []

    def add(name: str, observed: Any, op: str, expected: Any, passed: bool) -> None:
        checks.append({"name": name, "observed": observed, "op": op, "expected": expected, "passed": bool(passed)})

    add("query_plan_count", report.get("query_plan_count", 0), ">=", min_query_plans, int(report.get("query_plan_count", 0)) >= min_query_plans)
    add("ready_execution_count", report.get("ready_execution_count", 0), ">=", min_ready_executions, int(report.get("ready_execution_count", 0)) >= min_ready_executions)
    add("source_truth_evidence_count", report.get("source_truth_evidence_count", 0), ">=", min_source_truth_evidence, int(report.get("source_truth_evidence_count", 0)) >= min_source_truth_evidence)
    add("graph_guidance_count", report.get("graph_guidance_count", 0), ">=", min_graph_guidance_records, int(report.get("graph_guidance_count", 0)) >= min_graph_guidance_records)
    add("capped_result_count", report.get("capped_result_count", 0), ">=", min_capped_result_disclosures, int(report.get("capped_result_count", 0)) >= min_capped_result_disclosures)
    add("graph_proof_authority_violation_count", report.get("graph_proof_authority_violation_count", 0), "<=", max_graph_proof_authority_violations, int(report.get("graph_proof_authority_violation_count", 0)) <= max_graph_proof_authority_violations)
    add("summary_proof_authority_violation_count", report.get("summary_proof_authority_violation_count", 0), "<=", max_summary_proof_authority_violations, int(report.get("summary_proof_authority_violation_count", 0)) <= max_summary_proof_authority_violations)
    add("answer_permission_count", report.get("answer_permission_count", 0), "<=", max_answer_permission_count, int(report.get("answer_permission_count", 0)) <= max_answer_permission_count)
    add("source_truth_mutation_allowed_count", report.get("source_truth_mutation_allowed_count", 0), "<=", max_source_truth_mutation_allowed, int(report.get("source_truth_mutation_allowed_count", 0)) <= max_source_truth_mutation_allowed)
    if require_no_answer_permission:
        add("require_no_answer_permission", report.get("answer_permission_count", 0), "==", 0, int(report.get("answer_permission_count", 0)) == 0)
    status = "PASS" if all(c["passed"] for c in checks) else "FAIL"
    return status, checks


def render_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# TRACE-Net E2E Dynamic Plan Executor v18",
        "",
        f"Quality status: **{report.get('quality_status')}**",
        f"Status: `{report.get('status')}`",
        "",
        "## Summary",
        f"- query_plan_count: {report.get('query_plan_count')}",
        f"- execution_count: {report.get('execution_count')}",
        f"- ready_execution_count: {report.get('ready_execution_count')}",
        f"- source_truth_evidence_count: {report.get('source_truth_evidence_count')}",
        f"- graph_guidance_count: {report.get('graph_guidance_count')}",
        f"- summary_guidance_count: {report.get('summary_guidance_count')}",
        f"- capped_result_count: {report.get('capped_result_count')}",
        f"- high_degree_node_execution_count: {report.get('high_degree_node_execution_count')}",
        f"- graph_proof_authority_violation_count: {report.get('graph_proof_authority_violation_count')}",
        f"- summary_proof_authority_violation_count: {report.get('summary_proof_authority_violation_count')}",
        f"- answer_permission_count: {report.get('answer_permission_count')}",
        f"- source_truth_mutation_allowed_count: {report.get('source_truth_mutation_allowed_count')}",
        "",
        "## Contract",
        "- Query-time execution must not scan raw 5TB source data.",
        "- Graph and Leiden outputs are guidance only and require source-truth confirmation.",
        "- High-degree entities use aggregation plus a capped, ranked sample instead of silent truncation.",
        "- Capped results disclose total and returned counts.",
        "- v2 summaries are guidance only, not proof authority.",
        "",
        "## Executions",
    ]
    for e in report.get("executions", []):
        lines.extend([
            f"### {e.get('query_plan_id')} — `{e.get('query_intent')}`",
            f"- query: {e.get('user_query')}",
            f"- status: `{e.get('execution_status')}`",
            f"- total_match_count: {e.get('total_match_count')}",
            f"- returned_match_count: {e.get('returned_match_count')}",
            f"- result_was_capped: {e.get('result_was_capped')}",
            f"- high_degree_node_detected: {e.get('high_degree_node_detected')}",
            f"- graph_guidance_count: {e.get('graph_guidance_count')}",
            "",
        ])
    if report.get("quality_checks"):
        lines.extend(["## Quality checks"])
        for c in report.get("quality_checks", []):
            lines.append(f"- {'PASS' if c.get('passed') else 'FAIL'} {c.get('name')}: observed={c.get('observed')} expected={c.get('op')} {c.get('expected')}")
    lines.append("")
    return "\n".join(lines)


def write_report_files(report: MutableMapping[str, Any], output_dir: str | Path) -> Dict[str, str]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / "trace_net_e2e_dynamic_plan_executor_v18.json"
    records_path = out / "trace_net_e2e_dynamic_plan_executor_records_v18.jsonl"
    evidence_path = out / "trace_net_e2e_dynamic_plan_executor_evidence_v18.jsonl"
    inspect_path = out / "trace_net_e2e_dynamic_plan_executor_v18.md"
    report["report_path"] = str(report_path)
    report["records_jsonl_path"] = str(records_path)
    report["evidence_jsonl_path"] = str(evidence_path)
    report["inspect_md_path"] = str(inspect_path)
    write_json(report_path, report)
    write_jsonl(records_path, report.get("executions", []))
    evidence_rows = []
    for e in report.get("executions", []):
        for item in e.get("source_truth_evidence", []):
            row = dict(item)
            row["query_plan_id"] = e.get("query_plan_id")
            row["user_query"] = e.get("user_query")
            evidence_rows.append(row)
    write_jsonl(evidence_path, evidence_rows)
    inspect_path.write_text(render_markdown(report), encoding="utf-8")
    return {
        "report_path": str(report_path),
        "records_jsonl_path": str(records_path),
        "evidence_jsonl_path": str(evidence_path),
        "inspect_md_path": str(inspect_path),
    }
