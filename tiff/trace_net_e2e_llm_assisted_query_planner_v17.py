from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

MODULE_NAME = "trace_net_e2e_llm_assisted_query_planner_v17"
DEFAULT_STATUS_READY = "E2E_LLM_ASSISTED_QUERY_PLANNER_READY_FOR_DYNAMIC_PLAN_EXECUTION"
DEFAULT_STATUS_NEEDS_REPAIR = "E2E_LLM_ASSISTED_QUERY_PLANNER_NEEDS_REPAIR"

ALLOWED_TUNNELS = {
    "table_exact_search_tunnel",
    "table_hybrid_bridge_tunnel",
    "qdrant_page_profile_tunnel",
    "page_summary_tunnel",
    "graph_community_tunnel",
    "graph_navigation_tunnel",
    "route_metadata_tunnel",
    "table_route_summary_tunnel",
}

SOURCE_TRUTH_TUNNELS = {"table_exact_search_tunnel"}
RANKING_SUPPORT_TUNNELS = {"table_hybrid_bridge_tunnel", "qdrant_page_profile_tunnel"}
GUIDANCE_ONLY_TUNNELS = {
    "page_summary_tunnel",
    "graph_community_tunnel",
    "graph_navigation_tunnel",
    "route_metadata_tunnel",
    "table_route_summary_tunnel",
}

STANDARD_QUERY_PROBES = [
    "Find part number 120-36834-509",
    "Find part number 120-36833-501",
    "What maintenance manual pages mention covered part numbers?",
    "Where is manual reference 25-21-00 used?",
    "Search table text MAINTENANCE MANUAL WITH",
    "Find IPL item 130",
    "How does manual reference 25-21-00 connect to the IPL table pages?",
]

FIELD_CATALOG_BY_INTENT = {
    "part_number": ["covered_part_number", "ipl_part_number", "part_number"],
    "covered_part_number": ["covered_part_number"],
    "manual_page_reference": ["manual_page_reference", "ipl_part_number"],
    "table_text": ["ipl_text", "table_text"],
    "ipl_item": ["ipl_figure_item_or_quantity", "ipl_item", "ipl_text"],
    "relationship_or_synthesis": [
        "covered_part_number",
        "ipl_part_number",
        "manual_page_reference",
        "ipl_text",
        "ipl_figure_item_or_quantity",
    ],
    "unknown": [
        "covered_part_number",
        "ipl_part_number",
        "manual_page_reference",
        "ipl_text",
        "table_text",
    ],
}

PART_NUMBER_RE = re.compile(r"\b\d{2,4}-\d{3,6}-\d{2,4}\b")
MANUAL_REF_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")
IPL_ITEM_RE = re.compile(r"\b(?:ipl\s+item|item)\s+([0-9]{1,4})\b", re.I)


def load_json(path: str | Path | None, default: Any = None) -> Any:
    if path is None:
        return default
    p = Path(path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


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


def nested_records(value: Any) -> List[Mapping[str, Any]]:
    """Collect shallow dictionaries from common artifact shapes without assuming schema."""
    if isinstance(value, dict):
        for key in (
            "records",
            "responses",
            "queries",
            "pipelines",
            "pipeline_records",
            "dynamic_fallback_probes",
            "probes",
            "final_answers",
            "final_answer_records",
            "exact_search_documents",
            "documents",
            "pages",
            "communities",
        ):
            rows = value.get(key)
            if isinstance(rows, list) and rows:
                return [r for r in rows if isinstance(r, Mapping)]
    if isinstance(value, list):
        return [r for r in value if isinstance(r, Mapping)]
    return []


def extract_queries(*artifacts: Any, min_count: int = 5) -> List[str]:
    queries: List[str] = []
    seen = set()

    def add(q: Any) -> None:
        if not isinstance(q, str):
            return
        q = " ".join(q.strip().split())
        if not q or q.lower() in seen:
            return
        seen.add(q.lower())
        queries.append(q)

    for artifact in artifacts:
        rows = nested_records(artifact)
        for row in rows:
            for key in ("user_query", "query", "question", "probe_query", "original_query"):
                add(row.get(key))
            message = row.get("message")
            if isinstance(message, Mapping):
                add(message.get("content"))

    for q in STANDARD_QUERY_PROBES:
        add(q)

    return queries[: max(min_count, len(queries))]


def detect_query_intent(query: str) -> Tuple[str, Dict[str, Any]]:
    q = query.lower()
    part_numbers = PART_NUMBER_RE.findall(query)
    manual_refs = MANUAL_REF_RE.findall(query)
    ipl_item = IPL_ITEM_RE.search(query)

    extracted = {
        "part_numbers": part_numbers,
        "manual_references": manual_refs,
        "ipl_items": [ipl_item.group(1)] if ipl_item else [],
    }

    if any(word in q for word in ("connect", "connected", "related", "relationship", "compare", "explain", "how does", "how are")):
        return "relationship_or_synthesis", extracted
    if "covered part" in q and ("pages" in q or "mention" in q or "list" in q):
        return "covered_part_number", extracted
    if part_numbers or "part number" in q or "part-number" in q:
        return "part_number", extracted
    if "manual reference" in q or (manual_refs and ("where" in q or "used" in q or "reference" in q)):
        return "manual_page_reference", extracted
    if "search table text" in q or "table text" in q or "maintenance manual with" in q:
        return "table_text", extracted
    if ipl_item or "ipl item" in q:
        return "ipl_item", extracted
    return "unknown", extracted


def build_tunnel_selection(intent: str) -> Dict[str, List[str]]:
    if intent in {"part_number", "covered_part_number", "manual_page_reference", "table_text", "ipl_item"}:
        primary = ["table_exact_search_tunnel"]
        secondary = ["table_hybrid_bridge_tunnel", "qdrant_page_profile_tunnel"]
        guidance = [
            "page_summary_tunnel",
            "graph_community_tunnel",
            "graph_navigation_tunnel",
            "route_metadata_tunnel",
            "table_route_summary_tunnel",
        ]
    elif intent == "relationship_or_synthesis":
        primary = ["table_exact_search_tunnel", "table_hybrid_bridge_tunnel"]
        secondary = ["qdrant_page_profile_tunnel"]
        guidance = [
            "page_summary_tunnel",
            "graph_community_tunnel",
            "graph_navigation_tunnel",
            "route_metadata_tunnel",
            "table_route_summary_tunnel",
        ]
    else:
        primary = ["table_exact_search_tunnel"]
        secondary = ["table_hybrid_bridge_tunnel", "qdrant_page_profile_tunnel"]
        guidance = ["page_summary_tunnel", "graph_community_tunnel", "graph_navigation_tunnel", "route_metadata_tunnel"]
    return {"primary_tunnels": primary, "secondary_tunnels": secondary, "guidance_tunnels": guidance}


def available_artifact_summary(
    page_context_v2: Any,
    leiden_communities: Any,
    community_navigation_metadata_bridge: Any,
    route_dispatch_manifest: Any,
    table_exact_search_adapter: Any,
) -> Dict[str, Any]:
    page_rows = nested_records(page_context_v2)
    community_rows = nested_records(leiden_communities)
    nav_rows = nested_records(community_navigation_metadata_bridge)
    route_rows = nested_records(route_dispatch_manifest)
    exact_rows = nested_records(table_exact_search_adapter)
    return {
        "page_context_v2_available": bool(page_rows),
        "page_context_v2_record_count": len(page_rows),
        "leiden_communities_available": bool(community_rows),
        "leiden_community_record_count": len(community_rows),
        "community_navigation_available": bool(nav_rows),
        "community_navigation_record_count": len(nav_rows),
        "route_dispatch_manifest_available": bool(route_rows),
        "route_dispatch_record_count": len(route_rows),
        "table_exact_search_available": bool(exact_rows),
        "table_exact_search_record_count": len(exact_rows),
    }


def build_query_plan(
    plan_id: str,
    query: str,
    artifact_summary: Mapping[str, Any],
) -> Dict[str, Any]:
    intent, extracted = detect_query_intent(query)
    tunnel_selection = build_tunnel_selection(intent)
    required_fields = FIELD_CATALOG_BY_INTENT.get(intent, FIELD_CATALOG_BY_INTENT["unknown"])

    subqueries: List[Dict[str, Any]] = []
    if extracted["part_numbers"]:
        for value in extracted["part_numbers"]:
            subqueries.append(
                {
                    "subquery_type": "exact_value_lookup",
                    "target_value": value,
                    "required_source_truth_fields": ["covered_part_number", "ipl_part_number"],
                    "preferred_tunnel": "table_exact_search_tunnel",
                }
            )
    elif extracted["manual_references"]:
        for value in extracted["manual_references"]:
            subqueries.append(
                {
                    "subquery_type": "manual_reference_lookup",
                    "target_value": value,
                    "required_source_truth_fields": ["manual_page_reference", "ipl_part_number"],
                    "preferred_tunnel": "table_exact_search_tunnel",
                }
            )
    elif extracted["ipl_items"]:
        for value in extracted["ipl_items"]:
            subqueries.append(
                {
                    "subquery_type": "ipl_item_lookup",
                    "target_value": value,
                    "required_source_truth_fields": ["ipl_figure_item_or_quantity", "ipl_text"],
                    "preferred_tunnel": "table_exact_search_tunnel",
                }
            )
    elif intent == "relationship_or_synthesis":
        subqueries.extend(
            [
                {
                    "subquery_type": "source_truth_anchor_lookup",
                    "target_value": None,
                    "required_source_truth_fields": required_fields,
                    "preferred_tunnel": "table_exact_search_tunnel",
                },
                {
                    "subquery_type": "graph_guided_related_page_expansion",
                    "target_value": None,
                    "guidance_tunnels": ["graph_community_tunnel", "graph_navigation_tunnel", "page_summary_tunnel"],
                    "proof_authority": False,
                },
            ]
        )
    else:
        subqueries.append(
            {
                "subquery_type": "field_aware_source_truth_lookup",
                "target_value": None,
                "required_source_truth_fields": required_fields,
                "preferred_tunnel": "table_exact_search_tunnel",
            }
        )

    if not subqueries:
        subqueries.append(
            {
                "subquery_type": "field_aware_source_truth_lookup",
                "target_value": None,
                "required_source_truth_fields": required_fields,
                "preferred_tunnel": "table_exact_search_tunnel",
            }
        )

    plan = {
        "query_plan_id": plan_id,
        "user_query": query,
        "query_intent": intent,
        "planner_mode": "llm_assisted_contract_simulated_deterministic_v17",
        "future_llm_role": "LLM may propose structured plan, subqueries, synonyms, and graph expansion hints; TRACE-Net validates and executes only allowed tunnels.",
        "extracted_query_terms": extracted,
        "query_goal": summarize_query_goal(intent, extracted),
        "subqueries": subqueries,
        "required_source_truth_fields": required_fields,
        **tunnel_selection,
        "tunnel_policy": {
            "allowed_tunnels": sorted(ALLOWED_TUNNELS),
            "source_truth_tunnels": sorted(SOURCE_TRUTH_TUNNELS),
            "ranking_support_tunnels": sorted(RANKING_SUPPORT_TUNNELS),
            "guidance_only_tunnels": sorted(GUIDANCE_ONLY_TUNNELS),
            "proof_authority": "source_truth_evidence_only",
            "summary_authority": "guidance_only",
            "graph_authority": "guidance_only",
            "v2_summaries_allowed": True,
            "leiden_communities_allowed": True,
            "leiden_use_for": ["related_page_expansion", "community_navigation", "crag_retry", "context_guidance"],
            "llm_may_choose_tunnels": False,
            "llm_may_suggest_tunnels_for_validation": True,
        },
        "artifact_guidance": {
            "page_context_v2": {
                "available": bool(artifact_summary.get("page_context_v2_available")),
                "record_count": int(artifact_summary.get("page_context_v2_record_count", 0)),
                "authority": "guidance_only",
                "use_for": ["query_planning", "context_compression", "crag_retry_page_targeting"],
            },
            "leiden_communities": {
                "available": bool(artifact_summary.get("leiden_communities_available")),
                "record_count": int(artifact_summary.get("leiden_community_record_count", 0)),
                "authority": "guidance_only",
                "use_for": ["relationship_navigation", "related_page_expansion", "graph_guided_retry"],
            },
            "community_navigation_metadata_bridge": {
                "available": bool(artifact_summary.get("community_navigation_available")),
                "record_count": int(artifact_summary.get("community_navigation_record_count", 0)),
                "authority": "guidance_only",
            },
            "route_dispatch_manifest": {
                "available": bool(artifact_summary.get("route_dispatch_manifest_available")),
                "record_count": int(artifact_summary.get("route_dispatch_record_count", 0)),
                "authority": "routing_guidance_only",
            },
        },
        "scalability_contract": {
            "designed_for_large_corpora": True,
            "expected_corpus_size_note": "Query-time planning must never scan raw 5TB source data. It must operate over prebuilt indexes, summaries, graph metadata, and source-truth evidence stores.",
            "raw_corpus_scan_at_query_time": False,
            "graph_built_offline": True,
            "graph_rebuild_at_query_time": False,
            "llm_reads_entire_graph": False,
            "llm_reads_context_pack_only": True,
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
    plan["validation"] = validate_query_plan(plan)
    plan["query_plan_status"] = (
        "QUERY_PLAN_VALIDATED_FOR_TUNNEL_EXECUTION" if plan["validation"]["validated"] else "QUERY_PLAN_REJECTED_OR_NEEDS_REPAIR"
    )
    return plan


def summarize_query_goal(intent: str, extracted: Mapping[str, Sequence[str]]) -> str:
    if intent == "part_number":
        values = ", ".join(extracted.get("part_numbers", [])) or "the requested part number"
        return f"Find source-truth evidence for {values} and return citation-ready page/value records."
    if intent == "covered_part_number":
        return "Find pages and source-truth records that list covered part numbers."
    if intent == "manual_page_reference":
        values = ", ".join(extracted.get("manual_references", [])) or "the requested manual reference"
        return f"Find where manual reference {values} is used and cite source-truth records."
    if intent == "table_text":
        return "Find exact or table-aware source-truth text matches in table/IPL evidence."
    if intent == "ipl_item":
        values = ", ".join(extracted.get("ipl_items", [])) or "the requested IPL item"
        return f"Find source-truth IPL item evidence for {values}."
    if intent == "relationship_or_synthesis":
        return "Plan a relationship-oriented search using source-truth anchors plus guidance-only summaries and graph communities."
    return "Plan a safe source-truth-first retrieval with guidance-only expansion if exact evidence is weak."


def validate_query_plan(plan: Mapping[str, Any]) -> Dict[str, Any]:
    tunnel_names: List[str] = []
    for key in ("primary_tunnels", "secondary_tunnels", "guidance_tunnels"):
        tunnel_names.extend(str(t) for t in plan.get(key, []) if isinstance(t, str))
    invalid = sorted({t for t in tunnel_names if t not in ALLOWED_TUNNELS})

    guidance = set(plan.get("guidance_tunnels", []))
    primary = set(plan.get("primary_tunnels", []))
    secondary = set(plan.get("secondary_tunnels", []))
    fields = plan.get("required_source_truth_fields", [])
    tunnel_policy = plan.get("tunnel_policy", {}) if isinstance(plan.get("tunnel_policy"), Mapping) else {}
    safety = plan.get("safety_contract", {}) if isinstance(plan.get("safety_contract"), Mapping) else {}

    proof_violations: List[str] = []
    if tunnel_policy.get("proof_authority") != "source_truth_evidence_only":
        proof_violations.append("proof_authority_not_source_truth_only")
    if tunnel_policy.get("summary_authority") != "guidance_only":
        proof_violations.append("summary_authority_not_guidance_only")
    if tunnel_policy.get("graph_authority") != "guidance_only":
        proof_violations.append("graph_authority_not_guidance_only")
    if any(t in SOURCE_TRUTH_TUNNELS for t in guidance):
        proof_violations.append("source_truth_tunnel_listed_as_guidance_only")

    validation_checks = {
        "all_tunnel_names_allowed": not invalid,
        "has_primary_tunnel": bool(primary),
        "has_source_truth_primary_or_secondary": bool((primary | secondary) & SOURCE_TRUTH_TUNNELS),
        "has_v2_summary_guidance": "page_summary_tunnel" in guidance,
        "has_leiden_guidance": bool({"graph_community_tunnel", "graph_navigation_tunnel"} & guidance),
        "has_required_source_truth_fields": bool(fields),
        "graph_and_summary_guidance_only": not proof_violations,
        "no_answer_permission": not bool(safety.get("answer_permission")),
        "no_source_truth_mutation": not bool(safety.get("source_truth_mutation_allowed")),
    }
    validated = all(validation_checks.values())
    return {
        "validated": validated,
        "validation_checks": validation_checks,
        "invalid_tunnels": invalid,
        "invalid_tunnel_count": len(invalid),
        "proof_authority_violations": proof_violations,
        "proof_authority_violation_count": len(proof_violations),
        "allowed_tunnel_validation_count": len(tunnel_names) - len(invalid),
    }


@dataclass
class QualityThresholds:
    min_query_plans: int = 5
    min_validated_query_plans: int = 5
    min_plans_with_v2_summary_guidance: int = 5
    min_plans_with_leiden_guidance: int = 5
    min_plans_with_source_truth_fields: int = 5
    min_allowed_tunnel_validations: int = 20
    max_invalid_tunnel_count: int = 0
    max_proof_authority_violations: int = 0
    max_answer_permission_count: int = 0
    max_source_truth_mutation_allowed: int = 0
    require_no_answer_permission: bool = False


def build_report(
    *,
    live_dynamic_fallback: Any = None,
    page_context_v2: Any = None,
    leiden_communities: Any = None,
    community_navigation_metadata_bridge: Any = None,
    route_dispatch_manifest: Any = None,
    table_exact_search_adapter: Any = None,
    min_query_plans: int = 5,
) -> Dict[str, Any]:
    artifact_summary = available_artifact_summary(
        page_context_v2,
        leiden_communities,
        community_navigation_metadata_bridge,
        route_dispatch_manifest,
        table_exact_search_adapter,
    )
    queries = extract_queries(live_dynamic_fallback, table_exact_search_adapter, min_count=min_query_plans)
    plans = [build_query_plan(f"query_plan_v17_{idx:04d}", query, artifact_summary) for idx, query in enumerate(queries[: max(min_query_plans, 5)], start=1)]

    counts = summarize_counts(plans)
    thresholds = QualityThresholds(min_query_plans=min_query_plans)
    quality = evaluate_quality_from_counts(counts, thresholds)
    status = DEFAULT_STATUS_READY if quality["quality_status"] == "PASS" else DEFAULT_STATUS_NEEDS_REPAIR

    return {
        "module": MODULE_NAME,
        "version": "v17",
        "status": status,
        "quality_status": quality["quality_status"],
        "artifact_summary": artifact_summary,
        **counts,
        "query_plans": plans,
        "quality_checks": quality["quality_checks"],
        "contract": {
            "llm_assisted_planning_allowed": True,
            "llm_plan_must_be_structured_json": True,
            "trace_net_validates_plan_before_execution": True,
            "trace_net_executes_only_allowed_tunnels": True,
            "v2_summaries_guidance_only": True,
            "leiden_communities_guidance_only": True,
            "source_truth_evidence_required_for_final_claims": True,
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
            "raw_5tb_scan_at_query_time": False,
        },
    }


def summarize_counts(plans: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    query_plan_count = len(plans)
    validated_query_plan_count = sum(1 for p in plans if p.get("validation", {}).get("validated"))
    plans_with_v2 = sum(1 for p in plans if "page_summary_tunnel" in p.get("guidance_tunnels", []))
    plans_with_leiden = sum(
        1
        for p in plans
        if "graph_community_tunnel" in p.get("guidance_tunnels", []) or "graph_navigation_tunnel" in p.get("guidance_tunnels", [])
    )
    plans_with_source_truth_fields = sum(1 for p in plans if p.get("required_source_truth_fields"))
    invalid_tunnel_count = sum(int(p.get("validation", {}).get("invalid_tunnel_count", 0)) for p in plans)
    proof_authority_violation_count = sum(int(p.get("validation", {}).get("proof_authority_violation_count", 0)) for p in plans)
    allowed_tunnel_validation_count = sum(int(p.get("validation", {}).get("allowed_tunnel_validation_count", 0)) for p in plans)
    answer_permission_count = sum(1 for p in plans if p.get("safety_contract", {}).get("answer_permission"))
    source_truth_mutation_allowed_count = sum(1 for p in plans if p.get("safety_contract", {}).get("source_truth_mutation_allowed"))
    relationship_or_synthesis_plan_count = sum(1 for p in plans if p.get("query_intent") == "relationship_or_synthesis")

    return {
        "query_plan_count": query_plan_count,
        "validated_query_plan_count": validated_query_plan_count,
        "plans_with_v2_summary_guidance_count": plans_with_v2,
        "plans_with_leiden_guidance_count": plans_with_leiden,
        "plans_with_source_truth_fields_count": plans_with_source_truth_fields,
        "allowed_tunnel_validation_count": allowed_tunnel_validation_count,
        "invalid_tunnel_count": invalid_tunnel_count,
        "proof_authority_violation_count": proof_authority_violation_count,
        "answer_permission_count": answer_permission_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "relationship_or_synthesis_plan_count": relationship_or_synthesis_plan_count,
    }


def evaluate_quality_from_counts(counts: Mapping[str, int], thresholds: QualityThresholds) -> Dict[str, Any]:
    checks = []

    def add(name: str, observed: int, op: str, expected: int) -> None:
        if op == ">=":
            passed = observed >= expected
        elif op == "<=":
            passed = observed <= expected
        elif op == "==":
            passed = observed == expected
        else:
            raise ValueError(op)
        checks.append({"name": name, "observed": observed, "op": op, "expected": expected, "passed": passed})

    add("query_plan_count", int(counts.get("query_plan_count", 0)), ">=", thresholds.min_query_plans)
    add("validated_query_plan_count", int(counts.get("validated_query_plan_count", 0)), ">=", thresholds.min_validated_query_plans)
    add(
        "plans_with_v2_summary_guidance_count",
        int(counts.get("plans_with_v2_summary_guidance_count", 0)),
        ">=",
        thresholds.min_plans_with_v2_summary_guidance,
    )
    add(
        "plans_with_leiden_guidance_count",
        int(counts.get("plans_with_leiden_guidance_count", 0)),
        ">=",
        thresholds.min_plans_with_leiden_guidance,
    )
    add(
        "plans_with_source_truth_fields_count",
        int(counts.get("plans_with_source_truth_fields_count", 0)),
        ">=",
        thresholds.min_plans_with_source_truth_fields,
    )
    add(
        "allowed_tunnel_validation_count",
        int(counts.get("allowed_tunnel_validation_count", 0)),
        ">=",
        thresholds.min_allowed_tunnel_validations,
    )
    add("invalid_tunnel_count", int(counts.get("invalid_tunnel_count", 0)), "<=", thresholds.max_invalid_tunnel_count)
    add(
        "proof_authority_violation_count",
        int(counts.get("proof_authority_violation_count", 0)),
        "<=",
        thresholds.max_proof_authority_violations,
    )
    add("answer_permission_count", int(counts.get("answer_permission_count", 0)), "<=", thresholds.max_answer_permission_count)
    add(
        "source_truth_mutation_allowed_count",
        int(counts.get("source_truth_mutation_allowed_count", 0)),
        "<=",
        thresholds.max_source_truth_mutation_allowed,
    )
    if thresholds.require_no_answer_permission:
        add("require_no_answer_permission", int(counts.get("answer_permission_count", 0)), "==", 0)

    return {"quality_status": "PASS" if all(c["passed"] for c in checks) else "FAIL", "quality_checks": checks}


def evaluate_quality(report: Mapping[str, Any], thresholds: QualityThresholds) -> Dict[str, Any]:
    counts = {k: int(report.get(k, 0)) for k in summarize_counts(report.get("query_plans", [])).keys()}
    return evaluate_quality_from_counts(counts, thresholds)


def render_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# TRACE-Net E2E LLM-Assisted Query Planner v17",
        "",
        f"Quality status: **{report.get('quality_status')}**",
        f"Status: `{report.get('status')}`",
        "",
        "## Summary",
    ]
    for key in (
        "query_plan_count",
        "validated_query_plan_count",
        "plans_with_v2_summary_guidance_count",
        "plans_with_leiden_guidance_count",
        "plans_with_source_truth_fields_count",
        "allowed_tunnel_validation_count",
        "invalid_tunnel_count",
        "proof_authority_violation_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
    ):
        lines.append(f"- {key}: {report.get(key, 0)}")

    lines.extend(
        [
            "",
            "## Contract",
            "- LLM may propose structured query plans, but TRACE-Net validates every plan before execution.",
            "- TRACE-Net executes only allowed tunnels.",
            "- v2 summaries are guidance only, not proof authority.",
            "- Leiden communities are graph/navigation guidance only, not proof authority.",
            "- Source-truth evidence is required for final claims.",
            "- Query-time planning must not scan raw 5TB source data; it uses prebuilt indexes, summaries, graph metadata, and evidence artifacts.",
            "",
            "## Query plans",
        ]
    )
    for plan in report.get("query_plans", []):
        lines.extend(
            [
                f"### {plan.get('query_plan_id')} — `{plan.get('query_intent')}`",
                f"- query: {plan.get('user_query')}",
                f"- status: `{plan.get('query_plan_status')}`",
                f"- primary_tunnels: {', '.join(plan.get('primary_tunnels', []))}",
                f"- guidance_tunnels: {', '.join(plan.get('guidance_tunnels', []))}",
                f"- required_source_truth_fields: {', '.join(plan.get('required_source_truth_fields', []))}",
                "",
            ]
        )
    lines.append("## Quality checks")
    for check in report.get("quality_checks", []):
        prefix = "PASS" if check.get("passed") else "FAIL"
        lines.append(
            f"- {prefix} {check.get('name')}: observed={check.get('observed')} expected={check.get('op')} {check.get('expected')}"
        )
    return "\n".join(lines) + "\n"


def write_report_files(report: Mapping[str, Any], output_dir: str | Path) -> Dict[str, str]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / "trace_net_e2e_llm_assisted_query_planner_v17.json"
    plans_path = out / "trace_net_e2e_llm_assisted_query_planner_records_v17.jsonl"
    inspect_path = out / "trace_net_e2e_llm_assisted_query_planner_v17.md"
    write_json(report_path, report)
    write_jsonl(plans_path, report.get("query_plans", []))
    inspect_path.write_text(render_markdown(report), encoding="utf-8")
    return {
        "report_path": str(report_path),
        "plans_jsonl_path": str(plans_path),
        "inspect_md_path": str(inspect_path),
    }
