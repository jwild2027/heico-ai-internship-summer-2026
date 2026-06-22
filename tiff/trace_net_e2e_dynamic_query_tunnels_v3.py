"""TRACE-Net E2E Dynamic Query Tunnels v3.

This module builds a query-time tunnel readiness report for the dynamic endpoint.
It does not rebuild OCR, embeddings, page summaries, graph communities, table
artifacts, or source-truth data. It only inspects already-built artifacts and
creates route-aware tunnel plans that later endpoint code can consume.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

REPORT_VERSION = "v3"
STATUS_BUILT = "E2E_DYNAMIC_QUERY_TUNNELS_BUILT"
READY_STATUS = "E2E_DYNAMIC_QUERY_TUNNELS_READY_FOR_ENDPOINT_INTEGRATION"
QUALITY_PASS = "PASS"
QUALITY_FAIL = "FAIL"

DEFAULT_QUERY_PROBES = [
    "Find part number 120-36833-001",
    "Find part number 120-36834-509",
    "Where is manual reference 25-21-00 used?",
    "Search table text MAINTENANCE MANUAL WITH",
    "What maintenance manual pages mention covered part numbers?",
]

AUTHORITY_ZERO_KEYS = [
    "answer_permission_count",
    "can_answer_directly_count",
    "can_prove_claims_count",
    "source_truth_mutation_allowed_count",
    "postgres_write_attempt_count",
    "qdrant_write_attempt_count",
    "opensearch_write_attempt_count",
    "opensearch_upload_attempt_count",
]

PART_NUMBER_RE = re.compile(r"\b\d{3}-\d{5}-\d{3}\b")
MANUAL_REF_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")


def _safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _load_json(path: Optional[Path]) -> Dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")


def _slug(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower()
    return value[:80] or "query"


def _stable_id(prefix: str, text: str, index: int) -> str:
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]
    return f"{prefix}_{index:04d}_{digest}"


def _summary(data: Mapping[str, Any]) -> Mapping[str, Any]:
    summary = data.get("summary")
    return summary if isinstance(summary, Mapping) else {}


def _quality_status(data: Mapping[str, Any]) -> str:
    return _safe_str(data.get("quality_status") or _summary(data).get("quality_status"), "UNKNOWN")


def _status_value(data: Mapping[str, Any], keys: Sequence[str]) -> str:
    summary = _summary(data)
    for key in keys:
        if key in data:
            return _safe_str(data[key])
        if key in summary:
            return _safe_str(summary[key])
    return "UNKNOWN"


def _count_value(data: Mapping[str, Any], keys: Sequence[str]) -> int:
    summary = _summary(data)
    for key in keys:
        value = data.get(key, summary.get(key))
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return 0


def _all_authority_zero(*datasets: Mapping[str, Any]) -> Dict[str, int]:
    totals = {key: 0 for key in AUTHORITY_ZERO_KEYS}
    for data in datasets:
        summary = _summary(data)
        for key in AUTHORITY_ZERO_KEYS:
            value = data.get(key, summary.get(key, 0))
            try:
                totals[key] += int(value)
            except (TypeError, ValueError):
                totals[key] += 0
    return totals


def classify_query_intent(query: str) -> str:
    q = query.lower()
    if PART_NUMBER_RE.search(query):
        return "covered_part_number"
    if "part number" in q or "covered part" in q:
        return "covered_part_number"
    if MANUAL_REF_RE.search(query) or "manual reference" in q or "manual page" in q:
        return "manual_page_reference"
    if "ipl item" in q or "item" in q and re.search(r"\b\d{1,4}\b", q):
        return "ipl_figure_item_or_quantity"
    if "table text" in q or "maintenance manual with" in q:
        return "table_text"
    if "diagram" in q or "callout" in q or "figure" in q:
        return "visual_or_callout_query"
    return "normal_text_query"


def query_terms(query: str) -> List[str]:
    terms: List[str] = []
    terms.extend(PART_NUMBER_RE.findall(query))
    terms.extend(MANUAL_REF_RE.findall(query))
    upper_phrases = re.findall(r"\b[A-Z][A-Z0-9-]*(?:\s+[A-Z][A-Z0-9-]*){1,}\b", query)
    terms.extend([p.strip() for p in upper_phrases if len(p.strip()) > 2])
    if not terms:
        terms = [t for t in re.findall(r"[A-Za-z0-9-]+", query) if len(t) > 2][:8]
    seen = set()
    out = []
    for term in terms:
        if term not in seen:
            seen.add(term)
            out.append(term)
    return out


@dataclass(frozen=True)
class ArtifactState:
    name: str
    tunnel_type: str
    path: str
    present: bool
    quality_status: str
    status: str
    record_count: int
    purpose: str
    required_for_v3: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "tunnel_type": self.tunnel_type,
            "path": self.path,
            "present": self.present,
            "quality_status": self.quality_status,
            "status": self.status,
            "record_count": self.record_count,
            "purpose": self.purpose,
            "required_for_v3": self.required_for_v3,
        }


def artifact_state(
    *,
    name: str,
    tunnel_type: str,
    path: Optional[Path],
    data: Mapping[str, Any],
    status_keys: Sequence[str],
    count_keys: Sequence[str],
    purpose: str,
    required_for_v3: bool = False,
) -> ArtifactState:
    p = str(path) if path else ""
    present = bool(path and Path(path).exists())
    return ArtifactState(
        name=name,
        tunnel_type=tunnel_type,
        path=p,
        present=present,
        quality_status=_quality_status(data) if present else "MISSING",
        status=_status_value(data, status_keys) if present else "MISSING",
        record_count=_count_value(data, count_keys) if present else 0,
        purpose=purpose,
        required_for_v3=required_for_v3,
    )


def build_artifact_states(
    *,
    dynamic_query_endpoint: Optional[Path] = None,
    table_exact_search_adapter: Optional[Path] = None,
    table_hybrid_retrieval_bridge: Optional[Path] = None,
    page_retrieval_profiles: Optional[Path] = None,
    page_context_v2: Optional[Path] = None,
    leiden_communities: Optional[Path] = None,
    community_navigation_metadata_bridge: Optional[Path] = None,
    route_dispatch_manifest: Optional[Path] = None,
    table_route_retrieval_handoff_summary: Optional[Path] = None,
) -> Tuple[List[ArtifactState], Dict[str, Dict[str, Any]]]:
    sources: List[Tuple[str, str, Optional[Path], Sequence[str], Sequence[str], str, bool]] = [
        (
            "dynamic_query_endpoint_manifest",
            "dynamic_endpoint_contract",
            dynamic_query_endpoint,
            ["e2e_dynamic_query_endpoint_status", "status"],
            ["exact_search_document_count", "source_exact_search_document_count"],
            "Confirms the dynamic endpoint consumes prebuilt evidence and keeps answer/write authority blocked.",
            True,
        ),
        (
            "table_exact_search_adapter",
            "table_exact_search_tunnel",
            table_exact_search_adapter,
            ["status"],
            ["table_exact_search_document_count", "source_evidence_document_count"],
            "Exact table value lookup for part numbers, manual references, IPL items, and table text.",
            True,
        ),
        (
            "table_hybrid_retrieval_bridge",
            "table_hybrid_bridge_tunnel",
            table_hybrid_retrieval_bridge,
            ["status"],
            ["table_hybrid_bridge_record_count", "bridge_record_count", "source_bridge_record_count"],
            "Table ranking signals, route boosts, and retrieval-only bridge records.",
            True,
        ),
        (
            "page_retrieval_profiles",
            "qdrant_page_profile_tunnel",
            page_retrieval_profiles,
            ["status"],
            ["page_retrieval_profile_count", "profile_count", "page_count"],
            "Prebuilt page/profile metadata used to guide semantic/Qdrant retrieval without rebuilding embeddings.",
            False,
        ),
        (
            "page_context_v2",
            "page_summary_tunnel",
            page_context_v2,
            ["status"],
            ["page_context_count", "page_count", "context_record_count"],
            "Page-level summaries/context used as query-time guide rails for the LLM and final gate.",
            False,
        ),
        (
            "leiden_communities",
            "graph_community_tunnel",
            leiden_communities,
            ["status"],
            ["community_count", "leiden_community_count", "graph_community_count"],
            "Graph/community navigation tunnel for related evidence discovery; not proof authority.",
            False,
        ),
        (
            "community_navigation_metadata_bridge",
            "graph_navigation_tunnel",
            community_navigation_metadata_bridge,
            ["status"],
            ["navigation_record_count", "bridge_record_count", "community_navigation_record_count"],
            "Community navigation metadata bridge for query-time graph traversal hints.",
            False,
        ),
        (
            "route_dispatch_manifest",
            "route_metadata_tunnel",
            route_dispatch_manifest,
            ["status"],
            ["route_dispatch_record_count", "page_route_count", "page_count"],
            "Route labels for table/image/normal-text/blank constraints during retrieval.",
            False,
        ),
        (
            "table_route_retrieval_handoff_summary",
            "table_route_summary_tunnel",
            table_route_retrieval_handoff_summary,
            ["handoff_status", "status"],
            ["bridge_record_count", "exact_search_document_count", "demo_query_count"],
            "Plain-English table route status and contract for query-time routing explanations.",
            False,
        ),
    ]

    states: List[ArtifactState] = []
    loaded: Dict[str, Dict[str, Any]] = {}
    for name, tunnel_type, path, status_keys, count_keys, purpose, required in sources:
        data = _load_json(path)
        loaded[name] = data
        states.append(
            artifact_state(
                name=name,
                tunnel_type=tunnel_type,
                path=path,
                data=data,
                status_keys=status_keys,
                count_keys=count_keys,
                purpose=purpose,
                required_for_v3=required,
            )
        )
    return states, loaded


def tunnel_purpose_for_query(intent: str, tunnel_type: str) -> str:
    if tunnel_type == "table_exact_search_tunnel":
        return "Look up exact table values that match query terms."
    if tunnel_type == "table_hybrid_bridge_tunnel":
        return "Apply table route ranking signals and intent-aware field boosts."
    if tunnel_type == "qdrant_page_profile_tunnel":
        return "Use prebuilt semantic/page-profile vectors as a route-aware semantic channel."
    if tunnel_type == "page_summary_tunnel":
        return "Use prebuilt page summaries as guide rails for context pack assembly."
    if tunnel_type in {"graph_community_tunnel", "graph_navigation_tunnel"}:
        return "Use graph/community navigation hints to find related source-trace evidence without treating graph as proof."
    if tunnel_type == "route_metadata_tunnel":
        return "Constrain retrieval by page route labels such as table, image_visual, and normal_text."
    if tunnel_type == "table_route_summary_tunnel":
        return "Carry the table route handoff contract into dynamic query explainability."
    if tunnel_type == "dynamic_endpoint_contract":
        return "Confirm the endpoint is dynamic, non-mutating, and retrieval/gate constrained."
    return f"Support {intent} query planning with prebuilt evidence metadata."


def tunnel_priority(intent: str, tunnel_type: str) -> int:
    preferred = {
        "covered_part_number": [
            "table_exact_search_tunnel",
            "table_hybrid_bridge_tunnel",
            "route_metadata_tunnel",
            "table_route_summary_tunnel",
            "qdrant_page_profile_tunnel",
            "graph_navigation_tunnel",
            "page_summary_tunnel",
        ],
        "manual_page_reference": [
            "table_exact_search_tunnel",
            "table_hybrid_bridge_tunnel",
            "route_metadata_tunnel",
            "graph_navigation_tunnel",
            "page_summary_tunnel",
            "qdrant_page_profile_tunnel",
        ],
        "ipl_figure_item_or_quantity": [
            "table_exact_search_tunnel",
            "table_hybrid_bridge_tunnel",
            "route_metadata_tunnel",
            "graph_navigation_tunnel",
            "page_summary_tunnel",
        ],
        "table_text": [
            "table_exact_search_tunnel",
            "table_hybrid_bridge_tunnel",
            "page_summary_tunnel",
            "route_metadata_tunnel",
            "qdrant_page_profile_tunnel",
        ],
        "visual_or_callout_query": [
            "route_metadata_tunnel",
            "graph_navigation_tunnel",
            "page_summary_tunnel",
            "qdrant_page_profile_tunnel",
            "table_hybrid_bridge_tunnel",
        ],
        "normal_text_query": [
            "qdrant_page_profile_tunnel",
            "page_summary_tunnel",
            "graph_navigation_tunnel",
            "route_metadata_tunnel",
            "table_exact_search_tunnel",
        ],
    }
    order = preferred.get(intent, preferred["normal_text_query"])
    try:
        return order.index(tunnel_type) + 1
    except ValueError:
        return 99


def make_query_records(queries: Sequence[str]) -> List[Dict[str, Any]]:
    records = []
    for idx, query in enumerate(queries, start=1):
        intent = classify_query_intent(query)
        records.append(
            {
                "query_id": _stable_id("dynamic_tunnel_query", query, idx),
                "user_query": query,
                "query_intent": intent,
                "query_terms": query_terms(query),
                "answer_permission": False,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "source_truth_mutation_allowed": False,
            }
        )
    return records


def build_tunnel_plans(
    query_records: Sequence[Mapping[str, Any]],
    artifact_states: Sequence[ArtifactState],
    *,
    max_tunnels_per_query: int = 8,
) -> List[Dict[str, Any]]:
    available = [s for s in artifact_states if s.present and s.tunnel_type != "dynamic_endpoint_contract"]
    plans: List[Dict[str, Any]] = []
    for record in query_records:
        query_id = _safe_str(record.get("query_id"), "query")
        intent = _safe_str(record.get("query_intent"), classify_query_intent(_safe_str(record.get("user_query"))))
        sorted_states = sorted(
            available,
            key=lambda s: (tunnel_priority(intent, s.tunnel_type), 0 if s.quality_status == QUALITY_PASS else 1, s.name),
        )[: max(1, max_tunnels_per_query)]
        tunnels = []
        for rank, state in enumerate(sorted_states, start=1):
            tunnels.append(
                {
                    "rank": rank,
                    "tunnel_type": state.tunnel_type,
                    "source_name": state.name,
                    "source_path": state.path,
                    "source_quality_status": state.quality_status,
                    "source_record_count": state.record_count,
                    "purpose": tunnel_purpose_for_query(intent, state.tunnel_type),
                    "retrieval_permission": "routing_and_ranking_only",
                    "answer_authority": "blocked",
                    "source_truth_mutation_allowed": False,
                    "rerun_corpus_processing": False,
                }
            )
        plans.append(
            {
                "query_id": query_id,
                "user_query": _safe_str(record.get("user_query")),
                "query_intent": intent,
                "query_terms": _as_list(record.get("query_terms")),
                "tunnel_count": len(tunnels),
                "tunnel_types": [t["tunnel_type"] for t in tunnels],
                "dynamic_tunnel_plan_status": "DYNAMIC_TUNNEL_PLAN_READY" if tunnels else "DYNAMIC_TUNNEL_PLAN_MISSING_TUNNELS",
                "tunnels": tunnels,
                "answer_permission": False,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "source_truth_mutation_allowed": False,
            }
        )
    return plans


def _count_plans_with(plans: Sequence[Mapping[str, Any]], tunnel_type: str) -> int:
    return sum(1 for plan in plans if tunnel_type in set(_as_list(plan.get("tunnel_types"))))


def _evaluate_quality(summary: Mapping[str, Any], thresholds: Mapping[str, Any], *, require_no_answer_permission: bool = True) -> Tuple[str, List[Dict[str, Any]]]:
    checks: List[Dict[str, Any]] = []

    def add(name: str, observed: Any, expected: str, passed: bool) -> None:
        checks.append({"name": name, "observed": observed, "expected": expected, "passed": bool(passed)})

    mins = [
        ("query_tunnel_plan_count", "min_query_tunnel_plans"),
        ("ready_query_tunnel_plan_count", "min_ready_query_tunnel_plans"),
        ("total_tunnel_count", "min_total_tunnels"),
        ("unique_tunnel_type_count", "min_unique_tunnel_types"),
        ("plans_with_table_tunnel_count", "min_plans_with_table_tunnels"),
        ("plans_with_graph_or_summary_tunnel_count", "min_plans_with_graph_or_summary_tunnels"),
        ("available_artifact_count", "min_available_artifacts"),
    ]
    for observed_key, threshold_key in mins:
        expected = int(thresholds.get(threshold_key, 0) or 0)
        observed = int(summary.get(observed_key, 0) or 0)
        add(observed_key, observed, f">= {expected}", observed >= expected)

    max_unsafe = int(thresholds.get("max_unsafe_records", 0) or 0)
    unsafe = int(summary.get("unsafe_record_count", 0) or 0)
    add("unsafe_record_count", unsafe, f"<= {max_unsafe}", unsafe <= max_unsafe)

    max_answer = int(thresholds.get("max_answer_permission_count", 0) or 0)
    answer = int(summary.get("answer_permission_count", 0) or 0)
    add("answer_permission_count", answer, f"<= {max_answer}", answer <= max_answer)

    max_mutation = int(thresholds.get("max_source_truth_mutation_allowed", 0) or 0)
    mutation = int(summary.get("source_truth_mutation_allowed_count", 0) or 0)
    add("source_truth_mutation_allowed_count", mutation, f"<= {max_mutation}", mutation <= max_mutation)

    if require_no_answer_permission:
        add("contract_no_answer_permission", answer, "== 0", answer == 0)
        add("contract_no_source_truth_mutation", mutation, "== 0", mutation == 0)

    return (QUALITY_PASS if all(c["passed"] for c in checks) else QUALITY_FAIL), checks


def build_dynamic_query_tunnels_report(
    *,
    queries: Sequence[str],
    dynamic_query_endpoint: Optional[Path] = None,
    table_exact_search_adapter: Optional[Path] = None,
    table_hybrid_retrieval_bridge: Optional[Path] = None,
    page_retrieval_profiles: Optional[Path] = None,
    page_context_v2: Optional[Path] = None,
    leiden_communities: Optional[Path] = None,
    community_navigation_metadata_bridge: Optional[Path] = None,
    route_dispatch_manifest: Optional[Path] = None,
    table_route_retrieval_handoff_summary: Optional[Path] = None,
    max_tunnels_per_query: int = 8,
    thresholds: Optional[Mapping[str, Any]] = None,
    require_no_answer_permission: bool = True,
) -> Dict[str, Any]:
    artifact_states, loaded = build_artifact_states(
        dynamic_query_endpoint=dynamic_query_endpoint,
        table_exact_search_adapter=table_exact_search_adapter,
        table_hybrid_retrieval_bridge=table_hybrid_retrieval_bridge,
        page_retrieval_profiles=page_retrieval_profiles,
        page_context_v2=page_context_v2,
        leiden_communities=leiden_communities,
        community_navigation_metadata_bridge=community_navigation_metadata_bridge,
        route_dispatch_manifest=route_dispatch_manifest,
        table_route_retrieval_handoff_summary=table_route_retrieval_handoff_summary,
    )
    query_records = make_query_records(queries)
    plans = build_tunnel_plans(query_records, artifact_states, max_tunnels_per_query=max_tunnels_per_query)

    tunnel_types = sorted({t for p in plans for t in _as_list(p.get("tunnel_types"))})
    available_artifacts = [s for s in artifact_states if s.present]
    required_missing = [s.name for s in artifact_states if s.required_for_v3 and not s.present]
    authority = _all_authority_zero(*loaded.values())

    plans_with_graph = _count_plans_with(plans, "graph_community_tunnel") + _count_plans_with(plans, "graph_navigation_tunnel")
    plans_with_summary = _count_plans_with(plans, "page_summary_tunnel") + _count_plans_with(plans, "table_route_summary_tunnel")
    plans_with_graph_or_summary = sum(
        1
        for plan in plans
        if any(
            t in set(_as_list(plan.get("tunnel_types")))
            for t in ["graph_community_tunnel", "graph_navigation_tunnel", "page_summary_tunnel", "table_route_summary_tunnel"]
        )
    )

    summary = {
        "query_record_count": len(query_records),
        "query_tunnel_plan_count": len(plans),
        "ready_query_tunnel_plan_count": sum(1 for p in plans if p.get("dynamic_tunnel_plan_status") == "DYNAMIC_TUNNEL_PLAN_READY"),
        "total_tunnel_count": sum(int(p.get("tunnel_count", 0) or 0) for p in plans),
        "unique_tunnel_type_count": len(tunnel_types),
        "unique_tunnel_types": tunnel_types,
        "available_artifact_count": len(available_artifacts),
        "required_missing_artifact_count": len(required_missing),
        "required_missing_artifacts": required_missing,
        "plans_with_table_tunnel_count": sum(
            1
            for p in plans
            if {"table_exact_search_tunnel", "table_hybrid_bridge_tunnel"}.intersection(set(_as_list(p.get("tunnel_types"))))
        ),
        "plans_with_qdrant_page_profile_tunnel_count": _count_plans_with(plans, "qdrant_page_profile_tunnel"),
        "plans_with_graph_tunnel_count": plans_with_graph,
        "plans_with_summary_tunnel_count": plans_with_summary,
        "plans_with_graph_or_summary_tunnel_count": plans_with_graph_or_summary,
        "plans_with_route_metadata_tunnel_count": _count_plans_with(plans, "route_metadata_tunnel"),
        "unsafe_record_count": 0,
        **authority,
    }

    thresholds = dict(thresholds or {})
    quality_status, checks = _evaluate_quality(summary, thresholds, require_no_answer_permission=require_no_answer_permission)
    if required_missing:
        quality_status = QUALITY_FAIL
        checks.append(
            {
                "name": "required_artifacts_present",
                "observed": required_missing,
                "expected": "no required artifacts missing",
                "passed": False,
            }
        )

    report = {
        "schema_version": REPORT_VERSION,
        "status": STATUS_BUILT,
        "quality_status": quality_status,
        "e2e_dynamic_query_tunnels_status": READY_STATUS if quality_status == QUALITY_PASS else "E2E_DYNAMIC_QUERY_TUNNELS_NOT_READY",
        "dynamic_query_tunnel_contract": {
            "reruns_ocr": False,
            "reruns_page_classification": False,
            "reruns_embeddings": False,
            "reruns_page_summaries": False,
            "reruns_graph_build": False,
            "uses_prebuilt_artifacts": True,
            "tunnels_are_routing_and_ranking_only": True,
            "graph_is_not_proof_authority": True,
            "summaries_are_not_source_truth": True,
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
        },
        "hybrid_tunnel_assessment": (
            "Dynamic v3 adds query-time tunnel plans over prebuilt table exact-search, table bridge, "
            "page/profile summaries, graph/community navigation, and route metadata when those artifacts are present. "
            "It does not rebuild corpus artifacts and does not grant answer authority."
        ),
        "summary": summary,
        "quality_checks": checks,
        "artifact_states": [s.to_dict() for s in artifact_states],
        "query_records": query_records,
        "query_tunnel_plans": plans,
    }
    return report


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary", {}) if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        "# TRACE-Net E2E Dynamic Query Tunnels v3",
        "",
        f"Quality status: **{report.get('quality_status', 'UNKNOWN')}**",
        f"Status: `{report.get('e2e_dynamic_query_tunnels_status', 'UNKNOWN')}`",
        "",
        "## Hybrid tunnel assessment",
        _safe_str(report.get("hybrid_tunnel_assessment")),
        "",
        "## Summary",
    ]
    for key in [
        "query_tunnel_plan_count",
        "ready_query_tunnel_plan_count",
        "total_tunnel_count",
        "unique_tunnel_type_count",
        "available_artifact_count",
        "plans_with_table_tunnel_count",
        "plans_with_qdrant_page_profile_tunnel_count",
        "plans_with_graph_tunnel_count",
        "plans_with_summary_tunnel_count",
        "plans_with_route_metadata_tunnel_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
    ]:
        lines.append(f"- {key}: {summary.get(key, 0)}")

    lines.extend(["", "## Available artifacts"])
    for state in _as_list(report.get("artifact_states")):
        if not isinstance(state, Mapping):
            continue
        mark = "PASS" if state.get("present") else "MISSING"
        lines.append(
            f"- **{mark}** `{state.get('name')}` → `{state.get('tunnel_type')}` "
            f"quality={state.get('quality_status')} records={state.get('record_count')}"
        )

    lines.extend(["", "## Query tunnel plans"])
    for plan in _as_list(report.get("query_tunnel_plans")):
        if not isinstance(plan, Mapping):
            continue
        lines.append("")
        lines.append(f"### {plan.get('user_query')}")
        lines.append(f"- intent: `{plan.get('query_intent')}`")
        lines.append(f"- status: `{plan.get('dynamic_tunnel_plan_status')}`")
        lines.append(f"- tunnels: {', '.join(_safe_str(t) for t in _as_list(plan.get('tunnel_types')))}")
    return "\n".join(lines).rstrip() + "\n"


def write_report_files(report: Mapping[str, Any], output_dir: Path) -> Dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "trace_net_e2e_dynamic_query_tunnels_v3.json"
    jsonl_path = output_dir / "trace_net_e2e_dynamic_query_tunnel_plans_v3.jsonl"
    md_path = output_dir / "trace_net_e2e_dynamic_query_tunnels_v3.md"
    _write_json(json_path, report)
    _write_jsonl(jsonl_path, _as_list(report.get("query_tunnel_plans")))
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return {"report_path": str(json_path), "plans_jsonl_path": str(jsonl_path), "inspect_md_path": str(md_path)}


def print_terminal_report(report: Mapping[str, Any]) -> str:
    summary = report.get("summary", {}) if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        "TRACE-Net E2E Dynamic Query Tunnels v3",
        f" Status: {report.get('e2e_dynamic_query_tunnels_status')}",
        f" Quality status: {report.get('quality_status')}",
        f" query_tunnel_plan_count: {summary.get('query_tunnel_plan_count', 0)}",
        f" ready_query_tunnel_plan_count: {summary.get('ready_query_tunnel_plan_count', 0)}",
        f" total_tunnel_count: {summary.get('total_tunnel_count', 0)}",
        f" unique_tunnel_type_count: {summary.get('unique_tunnel_type_count', 0)}",
        f" available_artifact_count: {summary.get('available_artifact_count', 0)}",
        f" plans_with_table_tunnel_count: {summary.get('plans_with_table_tunnel_count', 0)}",
        f" plans_with_graph_or_summary_tunnel_count: {summary.get('plans_with_graph_or_summary_tunnel_count', 0)}",
        f" answer_permission_count: {summary.get('answer_permission_count', 0)}",
        f" source_truth_mutation_allowed_count: {summary.get('source_truth_mutation_allowed_count', 0)}",
    ]
    return "\n".join(lines)


__all__ = [
    "DEFAULT_QUERY_PROBES",
    "READY_STATUS",
    "STATUS_BUILT",
    "build_dynamic_query_tunnels_report",
    "classify_query_intent",
    "query_terms",
    "render_markdown",
    "write_report_files",
    "print_terminal_report",
]
