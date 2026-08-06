"""TRACE-Net E2E dynamic context pack v8.

Builds LLM-ready context packs from dynamic tunnel ranked evidence.

This module is intentionally retrieval/context-only. It does not call an LLM,
rerun OCR, rebuild embeddings, rebuild graph artifacts, or mutate source truth.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

SCHEMA_VERSION = "v8"
STATUS_BUILT = "E2E_DYNAMIC_CONTEXT_PACK_BUILT"
STATUS_READY = "E2E_DYNAMIC_CONTEXT_PACK_READY_FOR_SELF_RAG"
STATUS_NOT_READY = "E2E_DYNAMIC_CONTEXT_PACK_NOT_READY"
QUALITY_PASS = "PASS"
QUALITY_FAIL = "FAIL"

GUIDANCE_TUNNELS = {
    "qdrant_page_profile_tunnel",
    "page_summary_tunnel",
    "graph_community_tunnel",
    "graph_navigation_tunnel",
    "route_metadata_tunnel",
    "table_route_summary_tunnel",
}
GRAPH_OR_SUMMARY_TUNNELS = {
    "page_summary_tunnel",
    "graph_community_tunnel",
    "graph_navigation_tunnel",
}
TABLE_TUNNELS = {"table_exact_search_tunnel", "table_hybrid_bridge_tunnel"}

TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_\-]*")


def load_json(path: str | Path | None) -> Dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def write_json(path: str | Path, data: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def write_jsonl(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")


def _as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    return []


def normalize_text(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    text = text.replace("MAINTENANCEMANUAL", "MAINTENANCE MANUAL")
    return text.strip()


def query_terms(text: str) -> List[str]:
    terms = []
    for token in TOKEN_RE.findall(text or ""):
        if len(token) <= 2 and not re.search(r"\d", token):
            continue
        if token.lower() in {"the", "and", "for", "with", "where", "what", "which", "list", "used", "find", "search"}:
            continue
        terms.append(token)
    # keep order while deduping case-insensitively
    out: List[str] = []
    seen = set()
    for term in terms:
        key = term.lower()
        if key not in seen:
            out.append(term)
            seen.add(key)
    return out


def get_quality_status(data: Mapping[str, Any]) -> str:
    value = data.get("quality_status") or data.get("summary", {}).get("quality_status")
    return str(value or "UNKNOWN")


def get_status(data: Mapping[str, Any]) -> str:
    return str(data.get("status") or data.get("e2e_dynamic_query_tunnels_status") or data.get("e2e_dynamic_context_pack_status") or "UNKNOWN")


def count_records(data: Mapping[str, Any], preferred_keys: Sequence[str] = ()) -> int:
    for key in preferred_keys:
        value = data.get(key)
        if isinstance(value, list):
            return len(value)
    for key in (
        "rank_records",
        "rank_plans",
        "query_tunnel_plans",
        "exact_search_documents",
        "table_exact_search_documents",
        "page_context_records",
        "pages",
        "communities",
        "community_records",
        "records",
    ):
        value = data.get(key)
        if isinstance(value, list):
            return len(value)
    summary = data.get("summary")
    if isinstance(summary, Mapping):
        for key in (
            "total_ranked_evidence_count",
            "query_tunnel_plan_count",
            "table_exact_search_document_count",
            "source_exact_search_document_count",
            "page_count",
            "record_count",
        ):
            if isinstance(summary.get(key), int):
                return int(summary[key])
    return 0


def extract_rank_plans(ranker: Mapping[str, Any]) -> List[Dict[str, Any]]:
    plans = ranker.get("rank_plans")
    if isinstance(plans, list):
        return [dict(p) for p in plans if isinstance(p, Mapping)]
    plans = ranker.get("query_rank_plans")
    if isinstance(plans, list):
        return [dict(p) for p in plans if isinstance(p, Mapping)]

    # Fallback: group rank_records by rank_plan_id.
    grouped: Dict[str, Dict[str, Any]] = {}
    for row in _as_list(ranker.get("rank_records")):
        if not isinstance(row, Mapping):
            continue
        plan_id = str(row.get("rank_plan_id") or "dynamic_context_pack_fallback")
        plan = grouped.setdefault(
            plan_id,
            {
                "rank_plan_id": plan_id,
                "user_query": row.get("user_query", ""),
                "query_intent": row.get("query_intent", "unknown"),
                "query_terms": query_terms(str(row.get("user_query", ""))),
                "ranked_evidence": [],
                "available_tunnels": ranker.get("summary", {}).get("available_tunnels", []),
                "ranker_status": "DYNAMIC_TUNNEL_RANKING_READY",
                "answer_permission": False,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "source_truth_mutation_allowed": False,
            },
        )
        plan["ranked_evidence"].append(dict(row))
    return list(grouped.values())


def _page_id_from_record(record: Mapping[str, Any]) -> str:
    return str(record.get("page_id") or record.get("page") or "").strip()


def _first_text_field(record: Mapping[str, Any], keys: Sequence[str]) -> str:
    for key in keys:
        value = record.get(key)
        if value:
            return normalize_text(value)
    return ""


def build_page_context_index(page_context: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    rows: List[Any] = []
    for key in ("page_context_records", "page_contexts", "pages", "records"):
        if isinstance(page_context.get(key), list):
            rows = page_context[key]
            break
    index: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        page_id = _page_id_from_record(row)
        if not page_id:
            continue
        index[page_id] = dict(row)
    return index


def build_route_index(route_manifest: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    rows: List[Any] = []
    for key in ("route_cards", "route_records", "page_routes", "records", "dispatch_records"):
        if isinstance(route_manifest.get(key), list):
            rows = route_manifest[key]
            break
    index: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        page_id = _page_id_from_record(row)
        if page_id:
            index[page_id] = dict(row)
    return index


def build_community_index(communities: Mapping[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    rows: List[Any] = []
    for key in ("communities", "community_records", "records", "leiden_communities"):
        if isinstance(communities.get(key), list):
            rows = communities[key]
            break
    index: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        page_ids: List[str] = []
        for key in ("page_ids", "source_page_ids", "member_page_ids", "pages"):
            value = row.get(key)
            if isinstance(value, list):
                page_ids.extend(str(v) for v in value if v)
        single = _page_id_from_record(row)
        if single:
            page_ids.append(single)
        for page_id in set(page_ids):
            index.setdefault(page_id, []).append(dict(row))
    return index


def _make_evidence_item(record: Mapping[str, Any], ordinal: int) -> Dict[str, Any]:
    contributions = record.get("tunnel_contributions")
    if not isinstance(contributions, Mapping):
        contributions = {}
    return {
        "evidence_id": f"evidence_{ordinal:03d}",
        "rank": int(record.get("rank") or ordinal),
        "page_id": _page_id_from_record(record),
        "field_name": normalize_text(record.get("field_name")),
        "normalized_value": normalize_text(record.get("normalized_value") or record.get("value")),
        "source_name": normalize_text(record.get("source_name") or "unknown"),
        "source_tunnel": normalize_text(record.get("source_tunnel") or "unknown"),
        "citation_ready": bool(record.get("citation_ready", True)),
        "source_trace_ready": bool(record.get("source_trace_ready", True)),
        "total_tunnel_score": int(record.get("total_tunnel_score") or record.get("score") or 0),
        "tunnel_contributions": {str(k): int(v) for k, v in contributions.items() if isinstance(v, (int, float))},
        "answer_authority": "source_truth_evidence_only",
    }


def _guidance_from_page_summary(page_id: str, page_context_index: Mapping[str, Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    row = page_context_index.get(page_id)
    if not row:
        return None
    summary = _first_text_field(row, ["summary", "page_summary", "context_summary", "text", "content"])
    if not summary:
        summary = f"Prebuilt page context is available for {page_id}."
    return {
        "guidance_id": f"page_summary_{page_id}",
        "tunnel_type": "page_summary_tunnel",
        "page_id": page_id,
        "guidance_text": summary[:800],
        "authority": "guidance_only_not_source_truth",
    }


def _guidance_from_route(page_id: str, route_index: Mapping[str, Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    row = route_index.get(page_id)
    if not row:
        return None
    route = row.get("primary_route") or row.get("route") or row.get("route_label") or row.get("page_route") or "route_metadata_available"
    return {
        "guidance_id": f"route_metadata_{page_id}",
        "tunnel_type": "route_metadata_tunnel",
        "page_id": page_id,
        "guidance_text": f"Page {page_id} has route metadata: {route}.",
        "route_label": normalize_text(route),
        "authority": "routing_constraint_only_not_source_truth",
    }


def _guidance_from_communities(page_id: str, community_index: Mapping[str, List[Mapping[str, Any]]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for i, row in enumerate(community_index.get(page_id, [])[:2], start=1):
        community_id = row.get("community_id") or row.get("id") or row.get("leiden_community_id") or f"community_{i}"
        label = _first_text_field(row, ["label", "title", "community_label", "summary", "description"])
        if not label:
            label = f"Graph/community metadata is available for page {page_id}."
        out.append(
            {
                "guidance_id": f"graph_community_{page_id}_{i}",
                "tunnel_type": "graph_community_tunnel",
                "page_id": page_id,
                "community_id": str(community_id),
                "guidance_text": label[:600],
                "authority": "graph_guidance_only_not_proof",
            }
        )
    return out


def _fallback_guidance(plan: Mapping[str, Any], tunnel_type: str, page_ids: Sequence[str]) -> Dict[str, Any]:
    page_text = ", ".join(page_ids[:5]) if page_ids else "retrieved pages"
    purpose = {
        "qdrant_page_profile_tunnel": "Prebuilt page/profile vector metadata can guide semantic retrieval without rebuilding embeddings.",
        "page_summary_tunnel": "Prebuilt page summaries can orient the LLM but are not source truth.",
        "graph_community_tunnel": "Graph communities can suggest related evidence but are not proof authority.",
        "graph_navigation_tunnel": "Graph navigation metadata can guide traversal to related evidence but is not proof authority.",
        "route_metadata_tunnel": "Route metadata constrains table/image/text handling.",
        "table_route_summary_tunnel": "Table route summary explains table extraction status and limitations.",
    }.get(tunnel_type, "Prebuilt retrieval guidance is available.")
    return {
        "guidance_id": f"{tunnel_type}_fallback",
        "tunnel_type": tunnel_type,
        "page_id": page_ids[0] if page_ids else "",
        "guidance_text": f"{purpose} Applies to {page_text} for query intent {plan.get('query_intent', 'unknown')}.",
        "authority": "guidance_only_not_source_truth",
    }


def build_guidance_box(
    plan: Mapping[str, Any],
    evidence_items: Sequence[Mapping[str, Any]],
    page_context_index: Mapping[str, Mapping[str, Any]],
    route_index: Mapping[str, Mapping[str, Any]],
    community_index: Mapping[str, List[Mapping[str, Any]]],
) -> List[Dict[str, Any]]:
    available_tunnels = set(str(v) for v in plan.get("available_tunnels", []) if v)
    if not available_tunnels:
        for item in evidence_items:
            for tunnel in item.get("tunnel_contributions", {}).keys():
                available_tunnels.add(str(tunnel))
    page_ids = []
    seen = set()
    for item in evidence_items:
        page_id = str(item.get("page_id") or "")
        if page_id and page_id not in seen:
            page_ids.append(page_id)
            seen.add(page_id)

    guidance: List[Dict[str, Any]] = []

    if "page_summary_tunnel" in available_tunnels:
        for page_id in page_ids[:3]:
            item = _guidance_from_page_summary(page_id, page_context_index)
            if item:
                guidance.append(item)
        if not any(g.get("tunnel_type") == "page_summary_tunnel" for g in guidance):
            guidance.append(_fallback_guidance(plan, "page_summary_tunnel", page_ids))

    if "route_metadata_tunnel" in available_tunnels:
        for page_id in page_ids[:3]:
            item = _guidance_from_route(page_id, route_index)
            if item:
                guidance.append(item)
        if not any(g.get("tunnel_type") == "route_metadata_tunnel" for g in guidance):
            guidance.append(_fallback_guidance(plan, "route_metadata_tunnel", page_ids))

    if "graph_community_tunnel" in available_tunnels:
        for page_id in page_ids[:3]:
            guidance.extend(_guidance_from_communities(page_id, community_index))
        if not any(g.get("tunnel_type") == "graph_community_tunnel" for g in guidance):
            guidance.append(_fallback_guidance(plan, "graph_community_tunnel", page_ids))

    if "graph_navigation_tunnel" in available_tunnels:
        guidance.append(_fallback_guidance(plan, "graph_navigation_tunnel", page_ids))

    if "qdrant_page_profile_tunnel" in available_tunnels:
        guidance.append(_fallback_guidance(plan, "qdrant_page_profile_tunnel", page_ids))

    if "table_route_summary_tunnel" in available_tunnels:
        guidance.append(_fallback_guidance(plan, "table_route_summary_tunnel", page_ids))

    # De-dupe guidance by id.
    out: List[Dict[str, Any]] = []
    seen_ids = set()
    for item in guidance:
        key = str(item.get("guidance_id"))
        if key not in seen_ids:
            out.append(item)
            seen_ids.add(key)
    return out


def build_rules_box() -> Dict[str, Any]:
    return {
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "uses_prebuilt_artifacts": True,
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
        "cite_every_factual_claim": True,
        "unsupported_claim_policy": "say_evidence_is_insufficient_or_keep_audit_draft",
        "llm_instruction_summary": (
            "Use the evidence box for factual claims and citations. Use the guidance box only "
            "to understand route, graph, summary, and semantic context. Do not treat graph or "
            "summary guidance as proof. Do not invent missing part descriptions."
        ),
    }


@dataclass(frozen=True)
class QualityThresholds:
    min_context_packs: int = 1
    min_ready_context_packs: int = 1
    min_total_evidence_items: int = 1
    min_packs_with_evidence_box: int = 1
    min_packs_with_guidance_box: int = 1
    min_packs_with_rules_box: int = 1
    min_packs_with_graph_or_summary_guidance: int = 0
    max_answer_permission_count: int = 0
    max_source_truth_mutation_allowed: int = 0
    require_no_answer_permission: bool = False


def evaluate_quality(summary: Mapping[str, Any], thresholds: QualityThresholds) -> List[Dict[str, Any]]:
    checks = [
        ("context_pack_count", summary.get("context_pack_count", 0), ">=", thresholds.min_context_packs),
        ("ready_context_pack_count", summary.get("ready_context_pack_count", 0), ">=", thresholds.min_ready_context_packs),
        ("total_evidence_item_count", summary.get("total_evidence_item_count", 0), ">=", thresholds.min_total_evidence_items),
        ("packs_with_evidence_box_count", summary.get("packs_with_evidence_box_count", 0), ">=", thresholds.min_packs_with_evidence_box),
        ("packs_with_guidance_box_count", summary.get("packs_with_guidance_box_count", 0), ">=", thresholds.min_packs_with_guidance_box),
        ("packs_with_rules_box_count", summary.get("packs_with_rules_box_count", 0), ">=", thresholds.min_packs_with_rules_box),
        (
            "packs_with_graph_or_summary_guidance_count",
            summary.get("packs_with_graph_or_summary_guidance_count", 0),
            ">=",
            thresholds.min_packs_with_graph_or_summary_guidance,
        ),
        ("answer_permission_count", summary.get("answer_permission_count", 0), "<=", thresholds.max_answer_permission_count),
        (
            "source_truth_mutation_allowed_count",
            summary.get("source_truth_mutation_allowed_count", 0),
            "<=",
            thresholds.max_source_truth_mutation_allowed,
        ),
    ]
    if thresholds.require_no_answer_permission:
        checks.append(("contract_answer_permission", summary.get("answer_permission_count", 0), "==", 0))
        checks.append(("contract_can_answer_directly", summary.get("can_answer_directly_count", 0), "==", 0))
        checks.append(("contract_can_prove_claims", summary.get("can_prove_claims_count", 0), "==", 0))

    out: List[Dict[str, Any]] = []
    for name, observed, op, expected in checks:
        if op == ">=":
            passed = observed >= expected
            exp_text = f">= {expected}"
        elif op == "<=":
            passed = observed <= expected
            exp_text = f"<= {expected}"
        elif op == "==":
            passed = observed == expected
            exp_text = f"== {expected}"
        else:
            passed = False
            exp_text = str(expected)
        out.append({"name": name, "observed": observed, "expected": exp_text, "passed": bool(passed)})
    return out


def build_context_pack_report(
    *,
    dynamic_tunnel_ranker: Mapping[str, Any],
    dynamic_query_tunnels: Mapping[str, Any] | None = None,
    table_exact_search_adapter: Mapping[str, Any] | None = None,
    table_hybrid_retrieval_bridge: Mapping[str, Any] | None = None,
    page_retrieval_profiles: Mapping[str, Any] | None = None,
    page_context_v2: Mapping[str, Any] | None = None,
    leiden_communities: Mapping[str, Any] | None = None,
    community_navigation_metadata_bridge: Mapping[str, Any] | None = None,
    route_dispatch_manifest: Mapping[str, Any] | None = None,
    table_route_retrieval_handoff_summary: Mapping[str, Any] | None = None,
    max_evidence_per_pack: int = 5,
    thresholds: QualityThresholds | None = None,
) -> Dict[str, Any]:
    thresholds = thresholds or QualityThresholds()
    dynamic_query_tunnels = dynamic_query_tunnels or {}
    table_exact_search_adapter = table_exact_search_adapter or {}
    table_hybrid_retrieval_bridge = table_hybrid_retrieval_bridge or {}
    page_retrieval_profiles = page_retrieval_profiles or {}
    page_context_v2 = page_context_v2 or {}
    leiden_communities = leiden_communities or {}
    community_navigation_metadata_bridge = community_navigation_metadata_bridge or {}
    route_dispatch_manifest = route_dispatch_manifest or {}
    table_route_retrieval_handoff_summary = table_route_retrieval_handoff_summary or {}

    page_context_index = build_page_context_index(page_context_v2)
    route_index = build_route_index(route_dispatch_manifest)
    community_index = build_community_index(leiden_communities)
    rank_plans = extract_rank_plans(dynamic_tunnel_ranker)

    packs: List[Dict[str, Any]] = []
    evidence_records: List[Dict[str, Any]] = []

    for idx, plan in enumerate(rank_plans, start=1):
        ranked = [r for r in _as_list(plan.get("ranked_evidence")) if isinstance(r, Mapping)]
        evidence_items = [_make_evidence_item(row, ordinal=i) for i, row in enumerate(ranked[:max_evidence_per_pack], start=1)]
        guidance_items = build_guidance_box(plan, evidence_items, page_context_index, route_index, community_index)
        rules = build_rules_box()
        has_graph_or_summary = any(str(g.get("tunnel_type")) in GRAPH_OR_SUMMARY_TUNNELS for g in guidance_items)
        status = "DYNAMIC_CONTEXT_PACK_READY" if evidence_items and rules else "DYNAMIC_CONTEXT_PACK_NOT_READY"

        pack = {
            "schema_version": SCHEMA_VERSION,
            "context_pack_id": f"dynamic_context_pack_v8_{idx:04d}",
            "context_pack_status": status,
            "self_rag_next_status": "READY_FOR_SELF_RAG_CONTEXT_CRITIC" if status == "DYNAMIC_CONTEXT_PACK_READY" else "NEEDS_CONTEXT_REPAIR",
            "user_query": normalize_text(plan.get("user_query")),
            "query_intent": normalize_text(plan.get("query_intent") or "unknown"),
            "query_terms": [normalize_text(v) for v in _as_list(plan.get("query_terms"))] or query_terms(str(plan.get("user_query", ""))),
            "evidence_box": {
                "authority": "source_truth_evidence_only",
                "items": evidence_items,
                "citation_required": True,
            },
            "guidance_box": {
                "authority": "guidance_only_not_source_truth",
                "items": guidance_items,
                "contains_graph_or_summary_guidance": has_graph_or_summary,
            },
            "rules_box": rules,
            "context_pack_contract": {
                "evidence_box_is_source_truth": True,
                "guidance_box_is_not_source_truth": True,
                "graph_is_not_proof_authority": True,
                "summaries_are_not_source_truth": True,
                "llm_may_answer_from_guidance_only": False,
                "source_truth_mutation_allowed": False,
            },
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
        }
        packs.append(pack)
        for item in evidence_items:
            rec = dict(item)
            rec.update(
                {
                    "context_pack_id": pack["context_pack_id"],
                    "user_query": pack["user_query"],
                    "query_intent": pack["query_intent"],
                }
            )
            evidence_records.append(rec)

    artifact_states = [
        _artifact_state("dynamic_tunnel_ranker", dynamic_tunnel_ranker, "dynamic_ranker_source", ["rank_plans", "rank_records"]),
        _artifact_state("dynamic_query_tunnels", dynamic_query_tunnels, "tunnel_plan_source", ["query_tunnel_plans"]),
        _artifact_state("table_exact_search_adapter", table_exact_search_adapter, "source_truth_evidence", ["exact_search_documents", "table_exact_search_documents"]),
        _artifact_state("table_hybrid_retrieval_bridge", table_hybrid_retrieval_bridge, "ranking_guidance", ["bridge_records", "retrieval_bridge_records", "records"]),
        _artifact_state("page_retrieval_profiles", page_retrieval_profiles, "semantic_profile_guidance", ["page_retrieval_profiles", "records", "pages"]),
        _artifact_state("page_context_v2", page_context_v2, "page_summary_guidance", ["page_context_records", "pages", "records"]),
        _artifact_state("leiden_communities", leiden_communities, "graph_community_guidance", ["communities", "community_records", "records"]),
        _artifact_state("community_navigation_metadata_bridge", community_navigation_metadata_bridge, "graph_navigation_guidance", ["records", "community_navigation_records"]),
        _artifact_state("route_dispatch_manifest", route_dispatch_manifest, "route_metadata_guidance", ["route_cards", "route_records", "records"]),
        _artifact_state("table_route_retrieval_handoff_summary", table_route_retrieval_handoff_summary, "table_route_guidance", ["records", "summary_records"]),
    ]

    summary = {
        "context_pack_count": len(packs),
        "ready_context_pack_count": sum(1 for p in packs if p["context_pack_status"] == "DYNAMIC_CONTEXT_PACK_READY"),
        "total_evidence_item_count": len(evidence_records),
        "packs_with_evidence_box_count": sum(1 for p in packs if p["evidence_box"]["items"]),
        "packs_with_guidance_box_count": sum(1 for p in packs if p["guidance_box"]["items"]),
        "packs_with_rules_box_count": sum(1 for p in packs if bool(p.get("rules_box"))),
        "packs_with_graph_or_summary_guidance_count": sum(1 for p in packs if p["guidance_box"].get("contains_graph_or_summary_guidance")),
        "guidance_item_count": sum(len(p["guidance_box"]["items"]) for p in packs),
        "available_artifact_count": sum(1 for a in artifact_states if a["present"]),
        "answer_permission_count": sum(1 for p in packs if p.get("answer_permission")),
        "can_answer_directly_count": sum(1 for p in packs if p.get("can_answer_directly")),
        "can_prove_claims_count": sum(1 for p in packs if p.get("can_prove_claims")),
        "source_truth_mutation_allowed_count": sum(1 for p in packs if p.get("source_truth_mutation_allowed")),
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "opensearch_upload_attempt_count": 0,
    }
    checks = evaluate_quality(summary, thresholds)
    quality_status = QUALITY_PASS if all(c["passed"] for c in checks) else QUALITY_FAIL
    e2e_status = STATUS_READY if quality_status == QUALITY_PASS else STATUS_NOT_READY
    summary["quality_status"] = quality_status

    return {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_BUILT,
        "e2e_dynamic_context_pack_status": e2e_status,
        "quality_status": quality_status,
        "context_engineering_assessment": (
            "Dynamic context pack v8 separates source-truth evidence, guidance-only graph/vector/summary/route "
            "signals, and answer rules so a downstream LLM can reason without treating guidance as proof."
        ),
        "artifact_states": artifact_states,
        "context_packs": packs,
        "evidence_records": evidence_records,
        "summary": summary,
        "quality_checks": checks,
        "dynamic_context_pack_contract": build_rules_box(),
    }


def _artifact_state(name: str, data: Mapping[str, Any], purpose: str, preferred_keys: Sequence[str]) -> Dict[str, Any]:
    return {
        "name": name,
        "present": bool(data),
        "purpose": purpose,
        "quality_status": get_quality_status(data) if data else "MISSING",
        "status": get_status(data) if data else "MISSING",
        "record_count": count_records(data, preferred_keys) if data else 0,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    s = report.get("summary", {})
    lines = [
        "# TRACE-Net E2E Dynamic Context Pack v8",
        "",
        f"Quality status: **{report.get('quality_status', 'UNKNOWN')}**",
        f"Status: `{report.get('e2e_dynamic_context_pack_status', 'UNKNOWN')}`",
        "",
        "## Context engineering assessment",
        str(report.get("context_engineering_assessment", "")),
        "",
        "## Summary",
    ]
    for key in [
        "context_pack_count",
        "ready_context_pack_count",
        "total_evidence_item_count",
        "packs_with_evidence_box_count",
        "packs_with_guidance_box_count",
        "packs_with_rules_box_count",
        "packs_with_graph_or_summary_guidance_count",
        "guidance_item_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
    ]:
        lines.append(f"- {key}: {s.get(key, 0)}")

    lines.extend(["", "## Artifact states"])
    for a in report.get("artifact_states", []):
        if not isinstance(a, Mapping):
            continue
        label = "PASS" if a.get("present") else "MISSING"
        lines.append(
            f"- **{label}** `{a.get('name')}` purpose={a.get('purpose')} quality={a.get('quality_status')} records={a.get('record_count')}"
        )

    lines.extend(["", "## Context packs"])
    for pack in report.get("context_packs", []):
        if not isinstance(pack, Mapping):
            continue
        lines.extend(
            [
                "",
                f"### {pack.get('user_query')}",
                f"- intent: `{pack.get('query_intent')}`",
                f"- status: `{pack.get('context_pack_status')}`",
                f"- evidence items: {len(pack.get('evidence_box', {}).get('items', []))}",
                f"- guidance items: {len(pack.get('guidance_box', {}).get('items', []))}",
                f"- graph/summary guidance: {pack.get('guidance_box', {}).get('contains_graph_or_summary_guidance')}",
            ]
        )
        for item in pack.get("evidence_box", {}).get("items", [])[:3]:
            lines.append(
                f"  - evidence: {item.get('field_name')}={item.get('normalized_value')} on {item.get('page_id')} score={item.get('total_tunnel_score')}"
            )

    lines.extend(["", "## Quality checks"])
    for check in report.get("quality_checks", []):
        result = "PASS" if check.get("passed") else "FAIL"
        lines.append(f"- {result} {check.get('name')}: observed={check.get('observed')} expected={check.get('expected')}")
    lines.append("")
    return "\n".join(lines)


def write_report_files(report: Mapping[str, Any], output_dir: str | Path) -> Dict[str, str]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / "trace_net_e2e_dynamic_context_pack_v8.json"
    packs_jsonl_path = out / "trace_net_e2e_dynamic_context_pack_records_v8.jsonl"
    evidence_jsonl_path = out / "trace_net_e2e_dynamic_context_pack_evidence_v8.jsonl"
    inspect_md_path = out / "trace_net_e2e_dynamic_context_pack_v8.md"
    write_json(report_path, report)
    write_jsonl(packs_jsonl_path, report.get("context_packs", []))
    write_jsonl(evidence_jsonl_path, report.get("evidence_records", []))
    inspect_md_path.write_text(render_markdown(report), encoding="utf-8")
    return {
        "report_path": str(report_path),
        "packs_jsonl_path": str(packs_jsonl_path),
        "evidence_jsonl_path": str(evidence_jsonl_path),
        "inspect_md_path": str(inspect_md_path),
    }
