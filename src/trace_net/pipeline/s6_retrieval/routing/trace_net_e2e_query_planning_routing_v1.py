"""TRACE-Net E2E query planning and routing v1.

This module sits between the safe E2E query-input harness and the hybrid
retrieval runtime. It enriches each user query with deterministic routing plans
and "tunnels" through graph/source-trace summaries, page/profile summaries,
table-route summaries, and visual summaries when relevant.

The tunnel metaphor is intentional: these records are navigation paths that help
retrieval reach useful evidence neighborhoods. They are not proof, final-answer
authority, source-truth mutations, or runtime service writes.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

REPORT_FILENAME = "trace_net_e2e_query_planning_routing_v1.json"
QUALITY_FILENAME = "trace_net_e2e_query_planning_routing_v1_quality.json"
ROUTE_PLANS_JSONL_FILENAME = "trace_net_e2e_query_route_plans_v1.jsonl"
INSPECT_MD_FILENAME = "trace_net_e2e_query_planning_routing_v1_inspect.md"

STATUS_BUILT = "E2E_QUERY_PLANNING_ROUTING_BUILT"
READY_STATUS = "E2E_QUERY_PLANNING_ROUTING_READY_FOR_HYBRID_RETRIEVAL_RUNTIME"
QUALITY_PASS = "PASS"
QUALITY_FAIL = "FAIL"

REQUIRED_PLAN_KEYS = {
    "query_id",
    "user_query",
    "query_intent",
    "routing_status",
    "requested_routes",
    "retrieval_channels",
    "planned_retrieval_order",
    "query_tunnels",
    "answer_permission",
    "can_answer_directly",
    "can_prove_claims",
    "source_truth_mutation_allowed",
}

GRAPH_HINT_KEYS = {
    "page_id",
    "source_page_id",
    "source_trace",
    "citation",
    "citation_id",
    "community_id",
    "community_label",
    "node_id",
    "edge_id",
    "graph_path",
}
SUMMARY_HINT_KEYS = {
    "summary",
    "page_summary",
    "label",
    "title",
    "description",
    "retrieval_hint",
    "retrieval_hints",
    "query_hint",
    "likely_queries",
    "field_counts",
}
TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./:-]*")
PAGE_ID_RE = re.compile(r"t_p_\d+_\d+_p\d{6}")


@dataclass(frozen=True)
class QualityThresholds:
    min_source_query_records: int = 1
    min_route_plans: int = 1
    min_routeable_plans: int = 1
    min_plans_with_graph_tunnels: int = 1
    min_plans_with_summary_tunnels: int = 1
    min_plans_with_table_tunnels: int = 1
    min_total_tunnels: int = 1
    min_unique_tunnel_types: int = 2
    min_planned_retrieval_steps: int = 1
    max_schema_missing_required_key_records: int = 0
    max_unsafe_records: int = 0
    max_answer_permission_count: int = 0
    max_source_truth_mutation_allowed: int = 0
    require_source_query_input_quality_pass: bool = False
    require_no_answer_permission: bool = False


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
    p.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _lower(value: Any) -> str:
    return _text(value).lower()


def _dedupe_keep_order(values: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for value in values:
        clean = _text(value)
        if clean and clean not in seen:
            seen.add(clean)
            out.append(clean)
    return out


def _slug(value: Any) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", _text(value).lower()).strip("_")
    return s or "unknown"


def _tokens(value: Any) -> List[str]:
    return [m.group(0).lower() for m in TOKEN_RE.finditer(_text(value))]


def extract_query_records(query_input: Mapping[str, Any]) -> List[Dict[str, Any]]:
    rows = _as_list(query_input.get("query_records"))
    return [dict(row) for row in rows if isinstance(row, dict)]


def _short_text(value: Any, limit: int = 180) -> str:
    text = " ".join(_text(value).split())
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def _walk_summary_artifact(obj: Any, source_name: str, out: List[Dict[str, Any]], depth: int = 0) -> None:
    """Collect lightweight graph/summary hints from arbitrary JSON structures.

    The project has many summary artifact shapes. This intentionally avoids
    strong assumptions and extracts small hint cards wherever it sees graph-ish
    keys, page ids, or summary-ish text fields.
    """
    if depth > 6 or len(out) >= 500:
        return
    if isinstance(obj, dict):
        keys = set(obj.keys())
        page_values = []
        for k, v in obj.items():
            if isinstance(v, str) and (k in GRAPH_HINT_KEYS or PAGE_ID_RE.search(v)):
                page_values.append(v)
        summary_pieces: List[str] = []
        for k in SUMMARY_HINT_KEYS:
            v = obj.get(k)
            if isinstance(v, str):
                summary_pieces.append(v)
            elif isinstance(v, list):
                summary_pieces.extend(_text(x) for x in v[:6] if isinstance(x, (str, int, float)))
            elif isinstance(v, dict):
                summary_pieces.append(" ".join(f"{_text(a)}:{_text(b)}" for a, b in list(v.items())[:8]))

        graphish = bool(keys & GRAPH_HINT_KEYS) or bool(page_values)
        summaryish = bool(keys & SUMMARY_HINT_KEYS) or bool(summary_pieces)
        if graphish or summaryish:
            out.append(
                {
                    "source_artifact": source_name,
                    "hint_type": "graph_summary" if graphish and summaryish else ("graph" if graphish else "summary"),
                    "page_ids": sorted({m.group(0) for v in page_values for m in PAGE_ID_RE.finditer(_text(v))}),
                    "community_id": _text(obj.get("community_id")),
                    "node_id": _text(obj.get("node_id")),
                    "label": _short_text(obj.get("label") or obj.get("title") or obj.get("community_label")),
                    "summary_text": _short_text(" | ".join(p for p in summary_pieces if p), 360),
                    "tokens": sorted(set(_tokens(" ".join(summary_pieces + page_values))))[:40],
                }
            )
        for value in obj.values():
            if isinstance(value, (dict, list)):
                _walk_summary_artifact(value, source_name, out, depth + 1)
    elif isinstance(obj, list):
        for item in obj[:1000]:
            _walk_summary_artifact(item, source_name, out, depth + 1)


def load_summary_hints(paths: Sequence[str | Path], allow_missing: bool = False) -> Tuple[List[Dict[str, Any]], List[str]]:
    hints: List[Dict[str, Any]] = []
    loaded: List[str] = []
    for raw_path in paths:
        p = Path(raw_path)
        if not p.exists():
            if allow_missing:
                continue
            raise FileNotFoundError(str(p))
        candidates: List[Path]
        if p.is_dir():
            candidates = sorted([x for x in p.rglob("*.json") if x.is_file()])[:50]
        else:
            candidates = [p]
        for candidate in candidates:
            try:
                data = load_json(candidate)
            except Exception:
                if allow_missing:
                    continue
                raise
            before = len(hints)
            _walk_summary_artifact(data, str(candidate), hints)
            if len(hints) > before:
                loaded.append(str(candidate))
    return hints, _dedupe_keep_order(loaded)


def _query_text(record: Mapping[str, Any]) -> str:
    return _text(record.get("user_query") or record.get("query") or record.get("normalized_query"))


def _query_terms(record: Mapping[str, Any]) -> List[str]:
    terms: List[str] = []
    for item in _as_list(record.get("query_terms")):
        if isinstance(item, dict):
            terms.append(_text(item.get("term") or item.get("value") or item.get("text")))
        elif item:
            terms.append(_text(item))
    terms.extend(_tokens(_query_text(record)))
    terms.append(_text(record.get("query_intent")))
    return [t for t in _dedupe_keep_order(terms) if t]


def _summary_hint_score(record: Mapping[str, Any], hint: Mapping[str, Any]) -> float:
    q_terms = {_lower(t) for t in _query_terms(record) if _lower(t)}
    hint_tokens = {_lower(t) for t in _as_list(hint.get("tokens")) if _lower(t)}
    hint_text = _lower(" ".join([hint.get("label", ""), hint.get("summary_text", ""), hint.get("source_artifact", "")]))
    score = 0.0
    for term in q_terms:
        if term in hint_tokens:
            score += 10.0
        elif term and term in hint_text:
            score += 6.0
    if _lower(record.get("query_intent")) and _lower(record.get("query_intent")) in hint_text:
        score += 15.0
    return score


def _base_tunnel(record: Mapping[str, Any], tunnel_type: str, role: str, reason: str, source: str, priority: int) -> Dict[str, Any]:
    return {
        "tunnel_id": f"{_text(record.get('query_id')) or 'query'}::{tunnel_type}::{priority:02d}",
        "tunnel_type": tunnel_type,
        "tunnel_role": role,
        "tunnel_source": source,
        "routing_reason": reason,
        "priority": priority,
        "retrieval_permission": "ranking_only_until_final_gate",
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
    }


def build_tunnels_for_query(record: Mapping[str, Any], summary_hints: Sequence[Mapping[str, Any]], max_summary_tunnels: int = 3) -> List[Dict[str, Any]]:
    channels = set(_as_list(record.get("retrieval_channels")))
    routes = set(_as_list(record.get("requested_routes")))
    intent = _lower(record.get("query_intent"))
    tunnels: List[Dict[str, Any]] = []
    priority = 1

    # Graph/source trace tunnel: source graph is the safe navigation backbone.
    if "graph_source_trace" in channels or "normal_text" in routes or "table" in routes or "image_visual" in routes:
        tunnels.append(
            _base_tunnel(
                record,
                "graph_source_trace_tunnel",
                "Use graph/source-trace neighborhoods to move from query terms to page/source/citation identities.",
                "query requested graph/source trace or source-routed retrieval",
                "route_contract.graph_source_trace",
                priority,
            )
        )
        priority += 1

    # Summary tunnel: page retrieval profiles and generated summaries help free-text find the right page neighborhood.
    if "qdrant_page_profiles" in channels or intent in {"normal_text_query", "table_text", "covered_part_number", "manual_page_reference"}:
        tunnels.append(
            _base_tunnel(
                record,
                "page_summary_tunnel",
                "Use page/profile summaries as a semantic tunnel before exact page evidence is judged.",
                "query requested page-profile/summary retrieval or has free-text wording",
                "summary_profiles.page_context_or_retrieval_profile",
                priority,
            )
        )
        priority += 1

    # Table tunnel: exact table route should be a first-class shortcut for part/table queries.
    if "table" in routes or any(c in channels for c in ["table_exact_search", "table_hybrid_retrieval_bridge"]):
        tunnels.append(
            _base_tunnel(
                record,
                "table_route_summary_tunnel",
                "Use table-route evidence summaries to jump from part/manual/table terms to table evidence cards.",
                "query requested table route or table exact/hybrid channels",
                "table_route.retrieval_handoff_summary",
                priority,
            )
        )
        priority += 1

    # Visual tunnel for IPL/callout queries.
    if "image_visual" in routes or "visual_retrieval" in channels:
        tunnels.append(
            _base_tunnel(
                record,
                "visual_summary_tunnel",
                "Use visual/callout summaries as an advisory tunnel for diagram or IPL-style lookup.",
                "query requested image/visual route",
                "visual_route.callout_and_figure_summaries",
                priority,
            )
        )
        priority += 1

    # Optional artifact-backed graph/summary tunnels from loaded artifacts.
    scored = sorted(
        [(float(_summary_hint_score(record, hint)), hint) for hint in summary_hints],
        key=lambda pair: pair[0],
        reverse=True,
    )
    added = 0
    for score, hint in scored:
        if score <= 0 or added >= max_summary_tunnels:
            break
        source = _text(hint.get("source_artifact")) or "summary_artifact"
        label = _text(hint.get("label")) or _text(hint.get("summary_text"))[:80] or "summary hint"
        tunnel_type = "artifact_graph_summary_tunnel" if "graph" in _lower(hint.get("hint_type")) else "artifact_summary_tunnel"
        t = _base_tunnel(
            record,
            tunnel_type,
            "Use a loaded graph/summary artifact as a query-specific tunnel into likely evidence neighborhoods.",
            f"matched summary hint score={score:g}; label={label}",
            source,
            priority,
        )
        t["hint_score"] = round(score, 4)
        t["hint_page_ids"] = list(_as_list(hint.get("page_ids")))[:10]
        t["hint_label"] = label
        tunnels.append(t)
        priority += 1
        added += 1

    return tunnels


def _planned_retrieval_order(record: Mapping[str, Any], tunnels: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    order: List[Dict[str, Any]] = []
    tunnel_types = [t.get("tunnel_type") for t in tunnels]
    channels = _as_list(record.get("retrieval_channels"))
    step = 1

    if "graph_source_trace_tunnel" in tunnel_types:
        order.append({"step": step, "stage": "graph_source_trace_tunnel", "purpose": "anchor source/page/citation neighborhoods"})
        step += 1
    if "page_summary_tunnel" in tunnel_types:
        order.append({"step": step, "stage": "page_summary_tunnel", "purpose": "expand free-text query into page/profile summary neighborhoods"})
        step += 1
    if "table_route_summary_tunnel" in tunnel_types:
        order.append({"step": step, "stage": "table_exact_and_bridge_tunnel", "purpose": "match table values and apply ranking boosts"})
        step += 1
    if "visual_summary_tunnel" in tunnel_types:
        order.append({"step": step, "stage": "visual_advisory_tunnel", "purpose": "route IPL/diagram-style query to visual evidence candidates"})
        step += 1

    for channel in channels:
        if channel not in {"graph_source_trace", "qdrant_page_profiles", "table_exact_search", "table_hybrid_retrieval_bridge", "visual_retrieval"}:
            order.append({"step": step, "stage": _text(channel), "purpose": "preserve requested retrieval channel"})
            step += 1

    order.append({"step": step, "stage": "final_gate_boundary", "purpose": "do not answer until final TRACE-Net gate reviews the context"})
    return order


def build_route_plan(record: Mapping[str, Any], summary_hints: Sequence[Mapping[str, Any]], max_summary_tunnels: int = 3) -> Dict[str, Any]:
    tunnels = build_tunnels_for_query(record, summary_hints, max_summary_tunnels=max_summary_tunnels)
    planned_order = _planned_retrieval_order(record, tunnels)
    route_status = "QUERY_ROUTE_PLAN_READY_FOR_RETRIEVAL_RUNTIME" if tunnels and planned_order else "QUERY_ROUTE_PLAN_REVIEW_REQUIRED"
    tunnel_types = sorted({_text(t.get("tunnel_type")) for t in tunnels if _text(t.get("tunnel_type"))})
    return {
        "query_id": _text(record.get("query_id")),
        "user_query": _query_text(record),
        "normalized_query": _text(record.get("normalized_query")),
        "query_intent": _text(record.get("query_intent")) or "unknown",
        "routing_status": route_status,
        "requested_routes": list(_as_list(record.get("requested_routes"))),
        "retrieval_channels": list(_as_list(record.get("retrieval_channels"))),
        "query_terms": list(_as_list(record.get("query_terms"))),
        "query_tunnels": tunnels,
        "tunnel_count": len(tunnels),
        "tunnel_types": tunnel_types,
        "planned_retrieval_order": planned_order,
        "planned_retrieval_step_count": len(planned_order),
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "postgres_write_attempt": False,
        "qdrant_write_attempt": False,
        "opensearch_write_attempt": False,
        "opensearch_upload_attempt": False,
    }


def augment_query_record(record: Mapping[str, Any], plan: Mapping[str, Any]) -> Dict[str, Any]:
    augmented = dict(record)
    channels = list(_as_list(augmented.get("retrieval_channels")))
    # Add explicit tunnel channels for later runtime modules while preserving old channels.
    tunnel_channel_map = {
        "graph_source_trace_tunnel": "graph_summary_tunnels",
        "page_summary_tunnel": "page_summary_tunnels",
        "table_route_summary_tunnel": "table_route_summary_tunnels",
        "visual_summary_tunnel": "visual_summary_tunnels",
        "artifact_graph_summary_tunnel": "artifact_graph_summary_tunnels",
        "artifact_summary_tunnel": "artifact_summary_tunnels",
    }
    for tunnel in _as_list(plan.get("query_tunnels")):
        if isinstance(tunnel, dict):
            channel = tunnel_channel_map.get(_text(tunnel.get("tunnel_type")))
            if channel:
                channels.append(channel)
    augmented["retrieval_channels"] = _dedupe_keep_order(channels)
    augmented["query_routing_plan"] = {
        "routing_status": plan.get("routing_status"),
        "query_tunnels": plan.get("query_tunnels"),
        "planned_retrieval_order": plan.get("planned_retrieval_order"),
        "routing_contract": {
            "graph_and_summaries_are_tunnels": True,
            "tunnels_can_rank_or_route": True,
            "tunnels_can_prove_claims": False,
            "tunnels_can_answer_directly": False,
        },
    }
    # Top-level alias to make the artifact easier for future scripts to consume.
    augmented["query_tunnels"] = plan.get("query_tunnels")
    return augmented


def _schema_missing_count(plans: Sequence[Mapping[str, Any]]) -> int:
    return sum(1 for plan in plans if not REQUIRED_PLAN_KEYS.issubset(set(plan.keys())))


def _tunnel_type_counts(plans: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    counts: Counter[str] = Counter()
    for plan in plans:
        for tunnel in _as_list(plan.get("query_tunnels")):
            if isinstance(tunnel, dict):
                counts[_text(tunnel.get("tunnel_type")) or "unknown"] += 1
    return dict(sorted(counts.items()))


def _route_counts(plans: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    counts: Counter[str] = Counter()
    for plan in plans:
        for route in _as_list(plan.get("requested_routes")):
            counts[_text(route) or "unknown"] += 1
    return dict(sorted(counts.items()))


def _channel_counts(records: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    counts: Counter[str] = Counter()
    for record in records:
        for channel in _as_list(record.get("retrieval_channels")):
            counts[_text(channel) or "unknown"] += 1
    return dict(sorted(counts.items()))


def _check(name: str, observed: Any, expected: str, passed: bool) -> Dict[str, Any]:
    return {"name": name, "observed": observed, "expected": expected, "passed": bool(passed)}


def evaluate_quality(report: Mapping[str, Any], thresholds: QualityThresholds) -> Tuple[str, List[Dict[str, Any]]]:
    summary = _as_dict(report.get("summary"))
    checks: List[Dict[str, Any]] = []

    def ge(name: str, observed: Any, minimum: int) -> None:
        try:
            value = int(observed)
        except (TypeError, ValueError):
            value = -1
        checks.append(_check(name, observed, f">= {minimum}", value >= minimum))

    def le(name: str, observed: Any, maximum: int) -> None:
        try:
            value = int(observed)
        except (TypeError, ValueError):
            value = 10**9
        checks.append(_check(name, observed, f"<= {maximum}", value <= maximum))

    def eq(name: str, observed: Any, expected: Any) -> None:
        checks.append(_check(name, observed, f"== {expected}", observed == expected))

    def true(name: str, observed: Any) -> None:
        checks.append(_check(name, observed, "is True", bool(observed) is True))

    ge("source_query_input_record_count", summary.get("source_query_input_record_count"), thresholds.min_source_query_records)
    ge("query_route_plan_count", summary.get("query_route_plan_count"), thresholds.min_route_plans)
    ge("routeable_query_route_plan_count", summary.get("routeable_query_route_plan_count"), thresholds.min_routeable_plans)
    ge("plans_with_graph_tunnel_count", summary.get("plans_with_graph_tunnel_count"), thresholds.min_plans_with_graph_tunnels)
    ge("plans_with_summary_tunnel_count", summary.get("plans_with_summary_tunnel_count"), thresholds.min_plans_with_summary_tunnels)
    ge("plans_with_table_tunnel_count", summary.get("plans_with_table_tunnel_count"), thresholds.min_plans_with_table_tunnels)
    ge("total_query_tunnel_count", summary.get("total_query_tunnel_count"), thresholds.min_total_tunnels)
    ge("unique_tunnel_type_count", summary.get("unique_tunnel_type_count"), thresholds.min_unique_tunnel_types)
    ge("planned_retrieval_step_count", summary.get("planned_retrieval_step_count"), thresholds.min_planned_retrieval_steps)

    le("schema_missing_required_key_record_count", summary.get("schema_missing_required_key_record_count"), thresholds.max_schema_missing_required_key_records)
    le("unsafe_query_route_plan_count", summary.get("unsafe_query_route_plan_count"), thresholds.max_unsafe_records)
    le("answer_permission_count", summary.get("answer_permission_count"), thresholds.max_answer_permission_count)
    le("source_truth_mutation_allowed_count", summary.get("source_truth_mutation_allowed_count"), thresholds.max_source_truth_mutation_allowed)
    eq("can_answer_directly_count", summary.get("can_answer_directly_count"), 0)
    eq("can_prove_claims_count", summary.get("can_prove_claims_count"), 0)
    eq("postgres_write_attempt_count", summary.get("postgres_write_attempt_count"), 0)
    eq("qdrant_write_attempt_count", summary.get("qdrant_write_attempt_count"), 0)
    eq("opensearch_write_attempt_count", summary.get("opensearch_write_attempt_count"), 0)
    eq("opensearch_upload_attempt_count", summary.get("opensearch_upload_attempt_count"), 0)

    if thresholds.require_source_query_input_quality_pass:
        true("source_query_input_quality_pass", summary.get("source_query_input_quality_pass"))
    if thresholds.require_no_answer_permission:
        true("all_plans_retrieval_only", summary.get("all_plans_retrieval_only"))

    status = QUALITY_PASS if all(c["passed"] for c in checks) else QUALITY_FAIL
    return status, checks


def build_report(
    *,
    e2e_query_input: Mapping[str, Any],
    e2e_query_input_path: str | Path,
    output_dir: str | Path | None = None,
    summary_artifact_paths: Sequence[str | Path] = (),
    allow_missing_summary_artifacts: bool = False,
    max_summary_tunnels_per_query: int = 3,
    thresholds: QualityThresholds | None = None,
) -> Dict[str, Any]:
    thresholds = thresholds or QualityThresholds()
    query_records = extract_query_records(e2e_query_input)
    summary_hints, loaded_summary_artifacts = load_summary_hints(summary_artifact_paths, allow_missing=allow_missing_summary_artifacts)

    route_plans = [
        build_route_plan(record, summary_hints, max_summary_tunnels=max_summary_tunnels_per_query)
        for record in query_records
    ]
    augmented_records = [augment_query_record(record, plan) for record, plan in zip(query_records, route_plans)]

    tunnel_counts = _tunnel_type_counts(route_plans)
    routes = _route_counts(route_plans)
    channels = _channel_counts(augmented_records)
    total_tunnels = sum(tunnel_counts.values())
    planned_steps = sum(int(plan.get("planned_retrieval_step_count") or 0) for plan in route_plans)
    plans_with_graph = sum(
        1 for plan in route_plans
        if any("graph" in _lower(t.get("tunnel_type")) for t in _as_list(plan.get("query_tunnels")) if isinstance(t, dict))
    )
    plans_with_summary = sum(
        1 for plan in route_plans
        if any("summary" in _lower(t.get("tunnel_type")) for t in _as_list(plan.get("query_tunnels")) if isinstance(t, dict))
    )
    plans_with_table = sum(
        1 for plan in route_plans
        if any("table" in _lower(t.get("tunnel_type")) for t in _as_list(plan.get("query_tunnels")) if isinstance(t, dict))
    )

    source_quality_pass = e2e_query_input.get("quality_status") == QUALITY_PASS
    summary: Dict[str, Any] = {
        "e2e_query_planning_routing_status": READY_STATUS,
        "source_query_input_path": str(e2e_query_input_path),
        "source_query_input_quality_pass": bool(source_quality_pass),
        "source_query_input_record_count": len(query_records),
        "loaded_summary_artifact_count": len(loaded_summary_artifacts),
        "summary_hint_count": len(summary_hints),
        "query_route_plan_count": len(route_plans),
        "routeable_query_route_plan_count": sum(1 for p in route_plans if p.get("routing_status") == "QUERY_ROUTE_PLAN_READY_FOR_RETRIEVAL_RUNTIME"),
        "plans_with_graph_tunnel_count": plans_with_graph,
        "plans_with_summary_tunnel_count": plans_with_summary,
        "plans_with_table_tunnel_count": plans_with_table,
        "total_query_tunnel_count": total_tunnels,
        "unique_tunnel_type_count": len(tunnel_counts),
        "planned_retrieval_step_count": planned_steps,
        "route_counts": routes,
        "retrieval_channel_counts": channels,
        "tunnel_type_counts": tunnel_counts,
        "schema_missing_required_key_record_count": _schema_missing_count(route_plans),
        "unsafe_query_route_plan_count": 0,
        "answer_permission_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "opensearch_upload_attempt_count": 0,
        "all_plans_retrieval_only": True,
    }

    report: Dict[str, Any] = {
        "artifact_name": "trace_net_e2e_query_planning_routing_v1",
        "status": STATUS_BUILT,
        "quality_status": QUALITY_FAIL,
        "query_planning_routing_contract": {
            "purpose": "Use graph/source-trace and summary tunnels to enrich safe query plans before hybrid retrieval.",
            "tunnel_metaphor": "Graph and summaries are navigation tunnels, not proof or final-answer authority.",
            "retrieval_permission": "ranking_only_until_final_gate",
            "answer_authority": "blocked",
            "graph_and_summaries_are_tunnels": True,
            "tunnels_can_rank_or_route": True,
            "tunnels_can_answer_directly": False,
            "tunnels_can_prove_claims": False,
            "source_truth_mutation_allowed": False,
            "writes_to_postgres": False,
            "writes_to_qdrant": False,
            "writes_to_opensearch": False,
            "uploads_to_opensearch": False,
            "ready_for_hybrid_retrieval_runtime": True,
        },
        "summary": summary,
        "loaded_summary_artifacts": loaded_summary_artifacts,
        "query_records": augmented_records,
        "query_route_plans": route_plans,
        "quality_checks": [],
    }
    quality_status, checks = evaluate_quality(report, thresholds)
    report["quality_status"] = quality_status
    report["quality_checks"] = checks
    return report


def render_inspect_markdown(report: Mapping[str, Any]) -> str:
    summary = _as_dict(report.get("summary"))
    contract = _as_dict(report.get("query_planning_routing_contract"))
    lines = [
        "# TRACE-Net E2E Query Planning Routing v1 Inspect",
        "",
        f"Quality status: **{report.get('quality_status', QUALITY_FAIL)}**",
        "",
        "## Purpose",
        "This artifact enriches safe query-input records with graph/source-trace and summary tunnels before hybrid retrieval.",
        "The tunnels help route/rank evidence. They do not prove claims or answer directly.",
        "",
        "## Routing contract",
    ]
    for key in [
        "retrieval_permission",
        "answer_authority",
        "graph_and_summaries_are_tunnels",
        "tunnels_can_rank_or_route",
        "tunnels_can_answer_directly",
        "tunnels_can_prove_claims",
        "source_truth_mutation_allowed",
        "writes_to_postgres",
        "writes_to_qdrant",
        "writes_to_opensearch",
        "uploads_to_opensearch",
        "ready_for_hybrid_retrieval_runtime",
    ]:
        lines.append(f"- {key}: {contract.get(key)}")

    lines.extend(["", "## Main counters"])
    for key in [
        "source_query_input_record_count",
        "query_route_plan_count",
        "routeable_query_route_plan_count",
        "plans_with_graph_tunnel_count",
        "plans_with_summary_tunnel_count",
        "plans_with_table_tunnel_count",
        "total_query_tunnel_count",
        "unique_tunnel_type_count",
        "planned_retrieval_step_count",
        "loaded_summary_artifact_count",
        "summary_hint_count",
        "schema_missing_required_key_record_count",
    ]:
        lines.append(f"- {key}: {summary.get(key)}")

    lines.extend(["", "## Tunnel type counts"])
    tunnel_counts = _as_dict(summary.get("tunnel_type_counts"))
    if tunnel_counts:
        for key, value in tunnel_counts.items():
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- none")

    lines.extend(["", "## Safety/write counters"])
    for key in [
        "unsafe_query_route_plan_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
        "opensearch_upload_attempt_count",
    ]:
        lines.append(f"- {key}: {summary.get(key)}")

    lines.extend(["", "## Query route plans"])
    for plan in _as_list(report.get("query_route_plans")):
        if not isinstance(plan, dict):
            continue
        lines.append(
            f"- {plan.get('query_id')} | {plan.get('query_intent')} | query='{plan.get('user_query')}' | tunnels={plan.get('tunnel_count')}"
        )
        for tunnel in _as_list(plan.get("query_tunnels"))[:6]:
            if isinstance(tunnel, dict):
                lines.append(
                    f"  - {tunnel.get('tunnel_type')} | priority={tunnel.get('priority')} | source={tunnel.get('tunnel_source')}"
                )
        for step in _as_list(plan.get("planned_retrieval_order"))[:6]:
            if isinstance(step, dict):
                lines.append(f"  - step {step.get('step')}: {step.get('stage')} — {step.get('purpose')}")

    lines.extend(["", "## Quality checks"])
    for check in _as_list(report.get("quality_checks")):
        if isinstance(check, dict):
            label = "PASS" if check.get("passed") else "FAIL"
            lines.append(
                f"- {label} {check.get('name')}: observed={check.get('observed')} expected={check.get('expected')}"
            )
    return "\n".join(lines) + "\n"


def write_report(report: Mapping[str, Any], output_dir: str | Path) -> Dict[str, str]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / REPORT_FILENAME
    quality_path = out / QUALITY_FILENAME
    plans_path = out / ROUTE_PLANS_JSONL_FILENAME
    inspect_path = out / INSPECT_MD_FILENAME

    write_json(report_path, report)
    write_json(quality_path, {"quality_status": report.get("quality_status"), "quality_checks": report.get("quality_checks", [])})
    write_jsonl(plans_path, [p for p in _as_list(report.get("query_route_plans")) if isinstance(p, dict)])
    inspect_path.write_text(render_inspect_markdown(report), encoding="utf-8")
    return {
        "report_path": str(report_path),
        "quality_path": str(quality_path),
        "route_plans_jsonl_path": str(plans_path),
        "inspect_md_path": str(inspect_path),
    }


def build_query_planning_routing(
    *,
    e2e_query_input_path: str | Path,
    output_dir: str | Path,
    summary_artifact_paths: Sequence[str | Path] = (),
    allow_missing_summary_artifacts: bool = False,
    max_summary_tunnels_per_query: int = 3,
    thresholds: QualityThresholds | None = None,
) -> Dict[str, Any]:
    query_input = load_json(e2e_query_input_path)
    report = build_report(
        e2e_query_input=query_input,
        e2e_query_input_path=e2e_query_input_path,
        summary_artifact_paths=summary_artifact_paths,
        allow_missing_summary_artifacts=allow_missing_summary_artifacts,
        max_summary_tunnels_per_query=max_summary_tunnels_per_query,
        thresholds=thresholds,
    )
    paths = write_report(report, output_dir)
    report.update(paths)
    write_json(paths["report_path"], report)
    return report
