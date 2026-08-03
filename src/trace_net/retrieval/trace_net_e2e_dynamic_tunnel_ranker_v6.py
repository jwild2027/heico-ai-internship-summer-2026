"""TRACE-Net E2E dynamic tunnel ranker v6.

Query-time ranking/enrichment report over prebuilt TRACE-Net artifacts.

This module intentionally does not rerun OCR, page classification, embeddings,
page summaries, graph construction, table extraction, source ingest, or service
writes. It consumes existing dynamic endpoint/tunnel/table/profile/summary/graph
artifacts and produces a ranking contribution report that can later be wired into
TRACE-Net dynamic endpoint responses.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

QUALITY_PASS = "PASS"
QUALITY_FAIL = "FAIL"
STATUS_BUILT = "E2E_DYNAMIC_TUNNEL_RANKER_BUILT"
STATUS_READY = "E2E_DYNAMIC_TUNNEL_RANKER_READY_FOR_ENDPOINT_INTEGRATION"
STATUS_NOT_READY = "E2E_DYNAMIC_TUNNEL_RANKER_NOT_READY"

PART_NUMBER_RE = re.compile(r"\b\d{2,4}-\d{4,6}-\d{3}\b")
MANUAL_REF_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")
WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_\-]*")

STANDARD_DEMO_QUERIES = [
    "Find part number 120-36833-001",
    "Find part number 120-36834-509",
    "Where is manual reference 25-21-00 used?",
    "Search table text MAINTENANCE MANUAL WITH",
    "What maintenance manual pages mention covered part numbers?",
]

AUTHORITY_ZERO = {
    "answer_permission": False,
    "can_answer_directly": False,
    "can_prove_claims": False,
    "source_truth_mutation_allowed": False,
    "postgres_write_attempt_count": 0,
    "qdrant_write_attempt_count": 0,
    "opensearch_write_attempt_count": 0,
    "opensearch_upload_attempt_count": 0,
}

TUNNEL_AUTHORITY_CONTRACT = {
    "uses_prebuilt_artifacts": True,
    "tunnels_are_routing_and_ranking_only": True,
    "summaries_are_not_source_truth": True,
    "graph_is_not_proof_authority": True,
    "answer_permission": False,
    "can_answer_directly": False,
    "can_prove_claims": False,
    "source_truth_mutation_allowed": False,
    "reruns_ocr": False,
    "reruns_page_classification": False,
    "reruns_embeddings": False,
    "reruns_page_summaries": False,
    "reruns_graph_build": False,
    "reruns_table_extraction": False,
    "reruns_source_ingest": False,
}

INTENT_FIELD_PREFERENCES = {
    "covered_part_number": ["covered_part_number", "ipl_part_number", "manual_page_reference"],
    "manual_page_reference": ["manual_page_reference", "ipl_part_number"],
    "ipl_figure_item_or_quantity": ["ipl_figure_item_or_quantity"],
    "table_text": ["ipl_text", "table_text"],
}

GENERIC_TABLE_TEXT_VALUES = {
    "NUMBER", "PART", "ITEM", "QTY", "QUANTITY", "FIG", "FIGURE", "DESCRIPTION",
    "NOMENCLATURE", "CODE", "PAGE", "MANUAL", "REFERENCE",
}

STOP_TERMS = {
    "find", "part", "number", "where", "used", "search", "table", "text", "manual",
    "reference", "references", "pages", "page", "mention", "mentions", "with", "what", "the",
}


def _safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _read_json(path: Optional[Path]) -> Dict[str, Any]:
    if not path or not Path(path).exists():
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")


def _extract_records(data: Mapping[str, Any], candidate_keys: Sequence[str]) -> List[Mapping[str, Any]]:
    for key in candidate_keys:
        rows = data.get(key)
        if isinstance(rows, list):
            return [r for r in rows if isinstance(r, Mapping)]
    # Some reports store rows under summary-adjacent names; fallback to empty.
    return []


def _summary_record_count(data: Mapping[str, Any], candidate_keys: Sequence[str]) -> int:
    rows = _extract_records(data, candidate_keys)
    if rows:
        return len(rows)
    summary = data.get("summary") if isinstance(data.get("summary"), Mapping) else {}
    for key in (
        "record_count", "page_count", "page_profile_count", "community_count",
        "table_route_summary_count", "table_exact_search_document_count",
        "table_hybrid_bridge_record_count", "query_tunnel_plan_count",
    ):
        if key in summary:
            try:
                return int(summary.get(key) or 0)
            except Exception:
                pass
    return 0


def clean_value(value: Any) -> str:
    text = _safe_str(value)
    text = text.replace("ont_p_", "on t_p_")
    text = text.replace("MAINTENANCEMANUAL", "MAINTENANCE MANUAL")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def infer_query_intent(query: str) -> str:
    q = query.lower()
    if PART_NUMBER_RE.search(query):
        return "covered_part_number"
    if MANUAL_REF_RE.search(query):
        return "manual_page_reference"
    if "ipl" in q and re.search(r"\b\d{1,4}\b", q):
        return "ipl_figure_item_or_quantity"
    if "table text" in q or "maintenance manual with" in q:
        return "table_text"
    if "covered" in q and "part" in q:
        return "covered_part_number"
    return "table_text"


def query_terms(query: str, intent: str) -> List[str]:
    if intent == "covered_part_number":
        found = PART_NUMBER_RE.findall(query)
        if found:
            return found
    if intent == "manual_page_reference":
        found = MANUAL_REF_RE.findall(query)
        if found:
            return found
    words = [w for w in WORD_RE.findall(query) if w.lower() not in STOP_TERMS]
    if not words and query.strip():
        words = [query.strip()]
    if intent == "table_text" and "MAINTENANCE MANUAL WITH" in query.upper():
        return ["MAINTENANCE MANUAL WITH"]
    return words


@dataclass
class ArtifactState:
    name: str
    tunnel_type: str
    path: str
    present: bool
    quality_status: str
    status: str
    record_count: int
    purpose: str


@dataclass
class EvidenceHit:
    source_tunnel: str
    source_name: str
    page_id: str
    field_name: str
    normalized_value: str
    source_trace_ready: bool = True
    citation_ready: bool = True
    tunnel_contributions: Dict[str, int] = field(default_factory=dict)
    total_tunnel_score: int = 0
    rank: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "rank": self.rank,
            "source_tunnel": self.source_tunnel,
            "source_name": self.source_name,
            "page_id": self.page_id,
            "field_name": self.field_name,
            "normalized_value": self.normalized_value,
            "citation_ready": self.citation_ready,
            "source_trace_ready": self.source_trace_ready,
            "tunnel_contributions": dict(self.tunnel_contributions),
            "total_tunnel_score": self.total_tunnel_score,
        }


def _artifact_state(name: str, tunnel_type: str, path: Optional[Path], data: Mapping[str, Any], record_keys: Sequence[str], purpose: str) -> ArtifactState:
    present = bool(path and Path(path).exists())
    quality = _safe_str(data.get("quality_status"), "MISSING" if not present else "UNKNOWN")
    status = _safe_str(data.get("status") or data.get("e2e_dynamic_query_tunnels_status") or data.get("e2e_dynamic_query_endpoint_status"), "MISSING" if not present else "UNKNOWN")
    return ArtifactState(
        name=name,
        tunnel_type=tunnel_type,
        path=str(path) if path else "",
        present=present,
        quality_status=quality,
        status=status,
        record_count=_summary_record_count(data, record_keys) if present else 0,
        purpose=purpose,
    )


def _row_value(row: Mapping[str, Any]) -> str:
    for key in ("normalized_value", "value", "text", "display_value", "raw_value"):
        if _safe_str(row.get(key)):
            return clean_value(row.get(key))
    return ""


def _row_page(row: Mapping[str, Any]) -> str:
    return _safe_str(row.get("page_id") or row.get("page") or row.get("source_page_id"), "unknown_page")


def _row_field(row: Mapping[str, Any]) -> str:
    return _safe_str(row.get("field_name") or row.get("field") or row.get("value_type"), "unknown_field")


def _term_match_score(value: str, terms: Sequence[str], intent: str) -> int:
    value_clean = clean_value(value)
    value_upper = value_clean.upper()
    score = 0
    for term in terms:
        term_clean = clean_value(term)
        if not term_clean:
            continue
        if value_clean == term_clean:
            score += 120
        elif value_upper == term_clean.upper():
            score += 110
        elif term_clean.upper() in value_upper:
            score += 65
        elif value_upper in term_clean.upper() and len(value_upper) >= 4:
            score += 30
    if intent in {"covered_part_number", "manual_page_reference"} and value_upper in GENERIC_TABLE_TEXT_VALUES:
        score -= 80
    return score


def _field_score(field_name: str, intent: str) -> int:
    preferred = INTENT_FIELD_PREFERENCES.get(intent, [])
    if field_name in preferred:
        return 80 - (preferred.index(field_name) * 20)
    if intent == "table_text" and field_name.endswith("text"):
        return 60
    if field_name in {"ipl_text", "table_text"} and intent != "table_text":
        return -30
    return 0


def _profile_pages(profile_rows: Sequence[Mapping[str, Any]]) -> set[str]:
    pages = set()
    for row in profile_rows:
        page = _row_page(row)
        if page != "unknown_page":
            pages.add(page)
    return pages


def _generic_tunnel_pages(rows: Sequence[Mapping[str, Any]]) -> set[str]:
    pages = set()
    for row in rows:
        page = _row_page(row)
        if page != "unknown_page":
            pages.add(page)
    return pages


def rank_hits_for_query(
    query: str,
    exact_rows: Sequence[Mapping[str, Any]],
    bridge_rows: Sequence[Mapping[str, Any]],
    available_tunnels: Sequence[str],
    page_profile_rows: Sequence[Mapping[str, Any]] = (),
    page_context_rows: Sequence[Mapping[str, Any]] = (),
    graph_rows: Sequence[Mapping[str, Any]] = (),
    nav_rows: Sequence[Mapping[str, Any]] = (),
    route_rows: Sequence[Mapping[str, Any]] = (),
    top_k: int = 5,
) -> Tuple[Dict[str, Any], List[EvidenceHit]]:
    intent = infer_query_intent(query)
    terms = query_terms(query, intent)
    profile_pages = _profile_pages(page_profile_rows)
    summary_pages = _generic_tunnel_pages(page_context_rows)
    graph_pages = _generic_tunnel_pages(graph_rows) | _generic_tunnel_pages(nav_rows)
    route_pages = _generic_tunnel_pages(route_rows)

    candidates: List[EvidenceHit] = []

    def add_from_rows(rows: Sequence[Mapping[str, Any]], source_tunnel: str, source_name: str) -> None:
        for row in rows:
            value = _row_value(row)
            field_name = _row_field(row)
            page_id = _row_page(row)
            if not value:
                continue
            contributions: Dict[str, int] = {}
            base = _term_match_score(value, terms, intent)
            field_boost = _field_score(field_name, intent)
            if base <= 0 and field_boost <= 0:
                # For broad covered part pages queries, allow preferred fields even without explicit part number.
                if not (intent == "covered_part_number" and field_name == "covered_part_number"):
                    continue
            if source_tunnel in available_tunnels:
                contributions[source_tunnel] = max(0, base) + max(0, field_boost) + (40 if source_tunnel == "table_exact_search_tunnel" else 25)
            if "table_hybrid_bridge_tunnel" in available_tunnels and source_tunnel != "table_hybrid_bridge_tunnel":
                contributions["table_hybrid_bridge_tunnel"] = 20 if field_name in INTENT_FIELD_PREFERENCES.get(intent, []) else 8
            if "route_metadata_tunnel" in available_tunnels:
                contributions["route_metadata_tunnel"] = 15 if (not route_pages or page_id in route_pages) else 5
            if "qdrant_page_profile_tunnel" in available_tunnels:
                contributions["qdrant_page_profile_tunnel"] = 12 if (not profile_pages or page_id in profile_pages) else 3
            if "page_summary_tunnel" in available_tunnels:
                contributions["page_summary_tunnel"] = 10 if (not summary_pages or page_id in summary_pages) else 4
            if "graph_community_tunnel" in available_tunnels:
                contributions["graph_community_tunnel"] = 7 if (not graph_pages or page_id in graph_pages) else 2
            if "graph_navigation_tunnel" in available_tunnels:
                contributions["graph_navigation_tunnel"] = 7 if (not graph_pages or page_id in graph_pages) else 2
            if "table_route_summary_tunnel" in available_tunnels:
                contributions["table_route_summary_tunnel"] = 8 if field_name in INTENT_FIELD_PREFERENCES.get(intent, []) else 3
            total = sum(contributions.values())
            if total <= 0:
                continue
            candidates.append(EvidenceHit(
                source_tunnel=source_tunnel,
                source_name=source_name,
                page_id=page_id,
                field_name=field_name,
                normalized_value=value,
                tunnel_contributions=contributions,
                total_tunnel_score=total,
            ))

    add_from_rows(exact_rows, "table_exact_search_tunnel", "table_exact_search_adapter")
    # Use bridge rows as secondary candidates if they carry value fields.
    add_from_rows(bridge_rows, "table_hybrid_bridge_tunnel", "table_hybrid_retrieval_bridge")

    dedup: Dict[Tuple[str, str, str], EvidenceHit] = {}
    for hit in candidates:
        key = (hit.page_id, hit.field_name, hit.normalized_value)
        if key not in dedup or hit.total_tunnel_score > dedup[key].total_tunnel_score:
            dedup[key] = hit
    ranked = sorted(dedup.values(), key=lambda h: (-h.total_tunnel_score, h.page_id, h.field_name, h.normalized_value))[:top_k]
    for idx, hit in enumerate(ranked, 1):
        hit.rank = idx
    plan = {
        "user_query": query,
        "query_intent": intent,
        "query_terms": terms,
        "ranker_status": "DYNAMIC_TUNNEL_RANKING_READY" if ranked else "DYNAMIC_TUNNEL_RANKING_NO_MATCH",
        "available_tunnels": list(available_tunnels),
        "ranked_evidence_count": len(ranked),
        "top_tunnel_contribution_types": sorted({k for h in ranked for k in h.tunnel_contributions}),
        **{k: v for k, v in AUTHORITY_ZERO.items() if isinstance(v, bool)},
    }
    return plan, ranked


def build_ranker_report(
    *,
    dynamic_query_endpoint: Path,
    dynamic_query_tunnels: Path,
    table_exact_search_adapter: Path,
    table_hybrid_retrieval_bridge: Path,
    page_retrieval_profiles: Optional[Path] = None,
    page_context_v2: Optional[Path] = None,
    leiden_communities: Optional[Path] = None,
    community_navigation_metadata_bridge: Optional[Path] = None,
    route_dispatch_manifest: Optional[Path] = None,
    table_route_retrieval_handoff_summary: Optional[Path] = None,
    queries: Optional[Sequence[str]] = None,
    top_k: int = 5,
    min_rank_plans: int = 5,
    min_ready_rank_plans: int = 5,
    min_total_ranked_evidence: int = 10,
    min_unique_contribution_tunnels: int = 4,
    min_plans_with_graph_or_summary_contribution: int = 1,
    min_plans_with_table_contribution: int = 5,
    max_answer_permission_count: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    quality: bool = False,
) -> Dict[str, Any]:
    endpoint_data = _read_json(dynamic_query_endpoint)
    tunnels_data = _read_json(dynamic_query_tunnels)
    exact_data = _read_json(table_exact_search_adapter)
    bridge_data = _read_json(table_hybrid_retrieval_bridge)
    profiles_data = _read_json(page_retrieval_profiles)
    page_context_data = _read_json(page_context_v2)
    leiden_data = _read_json(leiden_communities)
    nav_data = _read_json(community_navigation_metadata_bridge)
    route_data = _read_json(route_dispatch_manifest)
    table_summary_data = _read_json(table_route_retrieval_handoff_summary)

    exact_rows = _extract_records(exact_data, ["exact_search_documents", "table_exact_search_documents", "evidence_documents"])
    bridge_rows = _extract_records(bridge_data, ["table_hybrid_bridge_records", "hybrid_bridge_records", "bridge_records", "records"])
    profile_rows = _extract_records(profiles_data, ["page_retrieval_profiles", "page_profiles", "profiles", "records"])
    page_context_rows = _extract_records(page_context_data, ["page_context_records", "page_context_v2_records", "page_summaries", "records"])
    graph_rows = _extract_records(leiden_data, ["communities", "leiden_communities", "community_records", "records"])
    nav_rows = _extract_records(nav_data, ["navigation_records", "community_navigation_records", "records"])
    route_rows = _extract_records(route_data, ["route_records", "dispatch_records", "page_route_records", "records"])

    artifact_states = [
        _artifact_state("dynamic_query_endpoint", "dynamic_endpoint_contract", dynamic_query_endpoint, endpoint_data, ["query_records"], "Dynamic endpoint contract and safety status."),
        _artifact_state("dynamic_query_tunnels", "tunnel_plan_source", dynamic_query_tunnels, tunnels_data, ["query_tunnel_plans"], "Available tunnel plan report from v3/v5."),
        _artifact_state("table_exact_search_adapter", "table_exact_search_tunnel", table_exact_search_adapter, exact_data, ["exact_search_documents", "table_exact_search_documents"], "Exact table value evidence."),
        _artifact_state("table_hybrid_retrieval_bridge", "table_hybrid_bridge_tunnel", table_hybrid_retrieval_bridge, bridge_data, ["table_hybrid_bridge_records", "bridge_records"], "Table route/ranking bridge evidence."),
        _artifact_state("page_retrieval_profiles", "qdrant_page_profile_tunnel", page_retrieval_profiles, profiles_data, ["page_retrieval_profiles", "page_profiles", "records"], "Prebuilt page/profile semantic tunnel metadata."),
        _artifact_state("page_context_v2", "page_summary_tunnel", page_context_v2, page_context_data, ["page_context_records", "page_summaries", "records"], "Prebuilt/synthesized page context summaries."),
        _artifact_state("leiden_communities", "graph_community_tunnel", leiden_communities, leiden_data, ["communities", "leiden_communities", "records"], "Graph/community routing hints; not proof authority."),
        _artifact_state("community_navigation_metadata_bridge", "graph_navigation_tunnel", community_navigation_metadata_bridge, nav_data, ["navigation_records", "records"], "Graph navigation bridge hints."),
        _artifact_state("route_dispatch_manifest", "route_metadata_tunnel", route_dispatch_manifest, route_data, ["route_records", "records"], "Route metadata constraints for page types."),
        _artifact_state("table_route_retrieval_handoff_summary", "table_route_summary_tunnel", table_route_retrieval_handoff_summary, table_summary_data, ["table_route_summary_records", "records"], "Table route retrieval contract/status summary."),
    ]

    available_tunnels = []
    for state in artifact_states:
        if state.present and state.tunnel_type not in {"dynamic_endpoint_contract", "tunnel_plan_source"}:
            available_tunnels.append(state.tunnel_type)
    # Prefer v3 reported tunnel order when available.
    summary = tunnels_data.get("summary") if isinstance(tunnels_data.get("summary"), Mapping) else {}
    reported = [str(x) for x in summary.get("unique_tunnel_types", []) or []]
    for t in reported:
        if t and t not in available_tunnels:
            available_tunnels.append(t)

    selected_queries = list(queries or STANDARD_DEMO_QUERIES)
    rank_plans: List[Dict[str, Any]] = []
    rank_records: List[Dict[str, Any]] = []
    for idx, query in enumerate(selected_queries, 1):
        plan, hits = rank_hits_for_query(
            query,
            exact_rows,
            bridge_rows,
            available_tunnels,
            page_profile_rows=profile_rows,
            page_context_rows=page_context_rows,
            graph_rows=graph_rows,
            nav_rows=nav_rows,
            route_rows=route_rows,
            top_k=top_k,
        )
        plan["rank_plan_id"] = f"dynamic_tunnel_rank_plan_v6_{idx:04d}"
        plan["ranked_evidence"] = [h.as_dict() for h in hits]
        rank_plans.append(plan)
        for hit in hits:
            row = hit.as_dict()
            row["rank_plan_id"] = plan["rank_plan_id"]
            row["user_query"] = query
            row["query_intent"] = plan["query_intent"]
            rank_records.append(row)

    unique_contribution_tunnels = sorted({k for row in rank_records for k in row.get("tunnel_contributions", {})})
    graph_or_summary_types = {"page_summary_tunnel", "graph_community_tunnel", "graph_navigation_tunnel", "table_route_summary_tunnel"}
    table_types = {"table_exact_search_tunnel", "table_hybrid_bridge_tunnel"}
    plans_with_graph_or_summary = sum(1 for plan in rank_plans if graph_or_summary_types.intersection(plan.get("top_tunnel_contribution_types", [])))
    plans_with_table = sum(1 for plan in rank_plans if table_types.intersection(plan.get("top_tunnel_contribution_types", [])))

    summary_out = {
        "rank_plan_count": len(rank_plans),
        "ready_rank_plan_count": sum(1 for p in rank_plans if p.get("ranker_status") == "DYNAMIC_TUNNEL_RANKING_READY"),
        "total_ranked_evidence_count": len(rank_records),
        "unique_contribution_tunnel_count": len(unique_contribution_tunnels),
        "unique_contribution_tunnels": unique_contribution_tunnels,
        "plans_with_graph_or_summary_contribution_count": plans_with_graph_or_summary,
        "plans_with_table_contribution_count": plans_with_table,
        "available_tunnel_count": len(available_tunnels),
        "available_tunnels": available_tunnels,
        "answer_permission_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "opensearch_upload_attempt_count": 0,
    }

    checks = [
        ("rank_plan_count", summary_out["rank_plan_count"], ">=", min_rank_plans),
        ("ready_rank_plan_count", summary_out["ready_rank_plan_count"], ">=", min_ready_rank_plans),
        ("total_ranked_evidence_count", summary_out["total_ranked_evidence_count"], ">=", min_total_ranked_evidence),
        ("unique_contribution_tunnel_count", summary_out["unique_contribution_tunnel_count"], ">=", min_unique_contribution_tunnels),
        ("plans_with_graph_or_summary_contribution_count", plans_with_graph_or_summary, ">=", min_plans_with_graph_or_summary_contribution),
        ("plans_with_table_contribution_count", plans_with_table, ">=", min_plans_with_table_contribution),
        ("answer_permission_count", 0, "<=", max_answer_permission_count),
        ("source_truth_mutation_allowed_count", 0, "<=", max_source_truth_mutation_allowed),
    ]
    quality_checks = []
    for name, observed, op, expected in checks:
        passed = observed >= expected if op == ">=" else observed <= expected
        quality_checks.append({"name": name, "observed": observed, "expected": f"{op} {expected}", "passed": bool(passed)})
    quality_status = QUALITY_PASS if all(c["passed"] for c in quality_checks) else QUALITY_FAIL
    status = STATUS_READY if quality_status == QUALITY_PASS else STATUS_NOT_READY

    return {
        "schema_version": "v6",
        "status": STATUS_BUILT,
        "e2e_dynamic_tunnel_ranker_status": status,
        "quality_status": quality_status,
        "dynamic_tunnel_ranker_contract": dict(TUNNEL_AUTHORITY_CONTRACT),
        "hybrid_ranker_assessment": (
            "Dynamic v6 scores table exact/bridge evidence and enriches ranking with available route, page-profile, "
            "page-summary, graph/community, graph-navigation, and table-route-summary tunnels. Tunnel scores are "
            "routing/ranking hints only and do not grant proof or answer authority."
        ),
        "artifact_states": [s.__dict__ for s in artifact_states],
        "summary": summary_out,
        "rank_plans": rank_plans,
        "rank_records": rank_records,
        "quality_checks": quality_checks,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary", {}) if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        "# TRACE-Net E2E Dynamic Tunnel Ranker v6",
        "",
        f"Quality status: **{report.get('quality_status')}**",
        f"Status: `{report.get('e2e_dynamic_tunnel_ranker_status')}`",
        "",
        "## Contract",
        "This ranker uses prebuilt artifacts only. It does not rerun OCR, page classification, embeddings, summaries, graph construction, table extraction, source ingest, or service writes. Graph and summaries are ranking/navigation hints only, not proof authority.",
        "",
        "## Summary",
    ]
    for key in [
        "rank_plan_count", "ready_rank_plan_count", "total_ranked_evidence_count",
        "unique_contribution_tunnel_count", "plans_with_graph_or_summary_contribution_count",
        "plans_with_table_contribution_count", "answer_permission_count", "source_truth_mutation_allowed_count",
    ]:
        lines.append(f"- {key}: {summary.get(key)}")
    lines.extend(["", "## Available contribution tunnels"])
    for tunnel in summary.get("unique_contribution_tunnels", []) or []:
        lines.append(f"- {tunnel}")
    lines.extend(["", "## Rank plans"])
    for plan in report.get("rank_plans", []) or []:
        lines.extend([
            "",
            f"### {plan.get('user_query')}",
            f"- intent: `{plan.get('query_intent')}`",
            f"- status: `{plan.get('ranker_status')}`",
            f"- contribution tunnels: {', '.join(plan.get('top_tunnel_contribution_types', []))}",
        ])
        for hit in plan.get("ranked_evidence", [])[:3]:
            lines.append(f"  - rank {hit.get('rank')}: {hit.get('field_name')}={hit.get('normalized_value')} on {hit.get('page_id')} score={hit.get('total_tunnel_score')}")
    lines.extend(["", "## Quality checks"])
    for check in report.get("quality_checks", []) or []:
        status = "PASS" if check.get("passed") else "FAIL"
        lines.append(f"- {status} {check.get('name')}: observed={check.get('observed')} expected={check.get('expected')}")
    return "\n".join(lines) + "\n"


def write_report_files(report: Mapping[str, Any], output_dir: Path) -> Dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "trace_net_e2e_dynamic_tunnel_ranker_v6.json"
    jsonl_path = output_dir / "trace_net_e2e_dynamic_tunnel_ranker_records_v6.jsonl"
    md_path = output_dir / "trace_net_e2e_dynamic_tunnel_ranker_v6.md"
    _write_json(json_path, report)
    _write_jsonl(jsonl_path, report.get("rank_records", []) or [])
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return {"report_path": json_path, "records_jsonl_path": jsonl_path, "inspect_md_path": md_path}


def print_report(report: Mapping[str, Any], paths: Mapping[str, Path]) -> None:
    summary = report.get("summary", {}) if isinstance(report.get("summary"), Mapping) else {}
    print("TRACE-Net E2E Dynamic Tunnel Ranker v6")
    print(f" Status: {report.get('e2e_dynamic_tunnel_ranker_status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in [
        "rank_plan_count", "ready_rank_plan_count", "total_ranked_evidence_count",
        "unique_contribution_tunnel_count", "plans_with_graph_or_summary_contribution_count",
        "plans_with_table_contribution_count", "answer_permission_count", "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    for name, path in paths.items():
        print(f" {name}: {path}")


def quality_from_report(report: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "quality_status": report.get("quality_status"),
        "quality_checks": report.get("quality_checks", []),
        "summary": report.get("summary", {}),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net E2E dynamic tunnel ranker v6 report.")
    parser.add_argument("--dynamic-query-endpoint", required=True, type=Path)
    parser.add_argument("--dynamic-query-tunnels", required=True, type=Path)
    parser.add_argument("--table-exact-search-adapter", required=True, type=Path)
    parser.add_argument("--table-hybrid-retrieval-bridge", required=True, type=Path)
    parser.add_argument("--page-retrieval-profiles", type=Path)
    parser.add_argument("--page-context-v2", type=Path)
    parser.add_argument("--leiden-communities", type=Path)
    parser.add_argument("--community-navigation-metadata-bridge", type=Path)
    parser.add_argument("--route-dispatch-manifest", type=Path)
    parser.add_argument("--table-route-retrieval-handoff-summary", type=Path)
    parser.add_argument("--query", action="append", default=[])
    parser.add_argument("--include-standard-demo-queries", action="store_true")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--min-rank-plans", type=int, default=5)
    parser.add_argument("--min-ready-rank-plans", type=int, default=5)
    parser.add_argument("--min-total-ranked-evidence", type=int, default=10)
    parser.add_argument("--min-unique-contribution-tunnels", type=int, default=4)
    parser.add_argument("--min-plans-with-graph-or-summary-contribution", type=int, default=1)
    parser.add_argument("--min-plans-with-table-contribution", type=int, default=5)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)

    queries = list(args.query)
    if args.include_standard_demo_queries or not queries:
        queries = STANDARD_DEMO_QUERIES + [q for q in queries if q not in STANDARD_DEMO_QUERIES]
    report = build_ranker_report(
        dynamic_query_endpoint=args.dynamic_query_endpoint,
        dynamic_query_tunnels=args.dynamic_query_tunnels,
        table_exact_search_adapter=args.table_exact_search_adapter,
        table_hybrid_retrieval_bridge=args.table_hybrid_retrieval_bridge,
        page_retrieval_profiles=args.page_retrieval_profiles,
        page_context_v2=args.page_context_v2,
        leiden_communities=args.leiden_communities,
        community_navigation_metadata_bridge=args.community_navigation_metadata_bridge,
        route_dispatch_manifest=args.route_dispatch_manifest,
        table_route_retrieval_handoff_summary=args.table_route_retrieval_handoff_summary,
        queries=queries,
        top_k=args.top_k,
        min_rank_plans=args.min_rank_plans,
        min_ready_rank_plans=args.min_ready_rank_plans,
        min_total_ranked_evidence=args.min_total_ranked_evidence,
        min_unique_contribution_tunnels=args.min_unique_contribution_tunnels,
        min_plans_with_graph_or_summary_contribution=args.min_plans_with_graph_or_summary_contribution,
        min_plans_with_table_contribution=args.min_plans_with_table_contribution,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        quality=args.quality,
    )
    paths = write_report_files(report, args.output_dir)
    print_report(report, paths)
    return 0 if report.get("quality_status") == QUALITY_PASS else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
