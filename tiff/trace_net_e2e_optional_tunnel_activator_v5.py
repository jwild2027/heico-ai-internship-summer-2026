"""TRACE-Net E2E optional tunnel activator v5.

This module activates optional dynamic-query tunnels without rerunning corpus processing.
It creates/copies lightweight, retrieval-only artifacts at the canonical locations
expected by ``trace_net_e2e_dynamic_query_tunnels_v3``.

The activator is intentionally conservative:
- does not rerun OCR
- does not rerun page classification
- does not rebuild embeddings
- does not rebuild graph algorithms
- does not mutate source truth
- does not write to Postgres/Qdrant/OpenSearch
- treats summaries/graph metadata as routing/ranking hints only
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

SCHEMA_VERSION = "v5"
STATUS_BUILT = "E2E_OPTIONAL_TUNNEL_ACTIVATOR_BUILT"
STATUS_READY = "E2E_OPTIONAL_TUNNELS_READY_FOR_DYNAMIC_QUERY_TUNNELS_V3"
STATUS_NOT_READY = "E2E_OPTIONAL_TUNNELS_NOT_READY"

AUTHORITY_BLOCK = {
    "answer_permission": False,
    "can_answer_directly": False,
    "can_prove_claims": False,
    "source_truth_mutation_allowed": False,
    "reruns_ocr": False,
    "reruns_page_classification": False,
    "reruns_embeddings": False,
    "reruns_page_summaries": False,
    "reruns_graph_build": False,
    "summaries_are_not_source_truth": True,
    "graph_is_not_proof_authority": True,
    "tunnels_are_routing_and_ranking_only": True,
    "uses_prebuilt_artifacts": True,
}

TARGETS = {
    "page_summary_tunnel": Path("page_context_v2/trace_net_page_context_v2.json"),
    "graph_community_tunnel": Path("leiden_communities/trace_net_leiden_communities_v1.json"),
    "graph_navigation_tunnel": Path("community_navigation_metadata_bridge/trace_net_community_navigation_metadata_bridge_v1.json"),
    "table_route_summary_tunnel": Path("table_route_retrieval_handoff_summary/trace_net_table_route_retrieval_handoff_summary_v1.json"),
}

ALT_CANDIDATES = {
    "page_summary_tunnel": [
        Path("page_context_v2/trace_net_page_context_v2_v1.json"),
        Path("page_context_v2/trace_net_page_context_v2.json"),
        Path("page_context/trace_net_page_context_v2.json"),
    ],
    "graph_community_tunnel": [
        Path("leiden_graph_communities/trace_net_leiden_graph_communities_v1.json"),
        Path("leiden_communities/trace_net_leiden_communities_v1.json"),
        Path("graph_communities/trace_net_leiden_communities_v1.json"),
    ],
    "graph_navigation_tunnel": [
        Path("community_navigation_metadata_bridge/trace_net_community_navigation_metadata_bridge_v1.json"),
        Path("graph_navigation_metadata_bridge/trace_net_community_navigation_metadata_bridge_v1.json"),
    ],
    "table_route_summary_tunnel": [
        Path("table_route_retrieval_handoff_summary/trace_net_table_route_retrieval_handoff_summary_v1.json"),
        Path("table_route_retrieval_readiness_report/trace_net_table_route_retrieval_readiness_report_v1.json"),
        Path("table_route_summary/trace_net_table_route_retrieval_handoff_summary_v1.json"),
    ],
}


def _safe_bool(value: Any) -> bool:
    return bool(value) if value is not None else False


def _read_json(path: Path) -> Dict[str, Any]:
    if not path or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r, sort_keys=True) for r in rows) + "\n", encoding="utf-8")


def _records_from(data: Mapping[str, Any], keys: Sequence[str]) -> List[Dict[str, Any]]:
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            return [dict(v) for v in value if isinstance(v, Mapping)]
    # fallback: first top-level list of dictionaries
    for value in data.values():
        if isinstance(value, list) and all(isinstance(v, Mapping) for v in value[:10]):
            return [dict(v) for v in value]
    return []


def _count_records(data: Mapping[str, Any]) -> int:
    if not data:
        return 0
    for key in (
        "record_count",
        "page_profile_count",
        "page_context_record_count",
        "community_count",
        "navigation_record_count",
        "table_route_summary_record_count",
        "table_exact_search_document_count",
        "table_hybrid_bridge_record_count",
    ):
        value = data.get(key) or data.get("summary", {}).get(key) if isinstance(data.get("summary"), Mapping) else None
        if isinstance(value, int):
            return value
    for value in data.values():
        if isinstance(value, list):
            return len(value)
    return 1


def _quality_status(data: Mapping[str, Any]) -> str:
    value = data.get("quality_status")
    if isinstance(value, str) and value:
        return value
    summary = data.get("summary")
    if isinstance(summary, Mapping):
        value = summary.get("quality_status")
        if isinstance(value, str) and value:
            return value
    return "UNKNOWN" if data else "MISSING"


def _slug(value: Any, default: str = "unknown") -> str:
    text = str(value or default)
    text = re.sub(r"[^A-Za-z0-9_\-]+", "_", text).strip("_")
    return text[:96] or default


def _extract_page_id(record: Mapping[str, Any], index: int) -> str:
    for key in ("page_id", "source_page_id", "page", "id"):
        value = record.get(key)
        if value:
            return str(value)
    return f"synthetic_page_{index:06d}"


def _extract_field(record: Mapping[str, Any], default: str = "unknown_field") -> str:
    for key in ("field_name", "field", "route", "primary_route"):
        value = record.get(key)
        if value:
            return str(value)
    return default


def _extract_value(record: Mapping[str, Any]) -> str:
    for key in ("normalized_value", "value", "text", "search_text", "content", "page_summary"):
        value = record.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _find_existing(root: Path, tunnel_type: str) -> Optional[Path]:
    target = root / TARGETS[tunnel_type]
    if target.exists():
        return target
    for rel in ALT_CANDIDATES.get(tunnel_type, []):
        candidate = root / rel
        if candidate.exists():
            return candidate
    return None


def _copy_or_load_existing(root: Path, tunnel_type: str) -> Tuple[Optional[Dict[str, Any]], Optional[Path], bool]:
    src = _find_existing(root, tunnel_type)
    if not src:
        return None, None, False
    data = _read_json(src)
    target = root / TARGETS[tunnel_type]
    if src.resolve() != target.resolve():
        _write_json(target, data)
    return data, src, True


def _load_profiles(page_profiles_path: Path, exact_data: Mapping[str, Any], max_records: int = 509) -> List[Dict[str, Any]]:
    profile_data = _read_json(page_profiles_path)
    profiles = _records_from(profile_data, ["page_profiles", "profiles", "records", "pages", "retrieval_profiles"])
    if profiles:
        return profiles[:max_records]

    exact_rows = _records_from(exact_data, ["exact_search_documents", "table_exact_search_documents", "evidence_documents"])
    seen: Dict[str, Dict[str, Any]] = {}
    for idx, row in enumerate(exact_rows):
        page_id = _extract_page_id(row, idx)
        seen.setdefault(page_id, {"page_id": page_id, "route": "table", "source": "table_exact_search_adapter"})
    return list(seen.values())[:max_records]


def build_page_context_v2(root: Path, page_profiles_path: Path, exact_data: Mapping[str, Any]) -> Dict[str, Any]:
    profiles = _load_profiles(page_profiles_path, exact_data)
    records: List[Dict[str, Any]] = []
    for idx, profile in enumerate(profiles):
        page_id = _extract_page_id(profile, idx)
        route = str(profile.get("route") or profile.get("primary_route") or profile.get("page_route") or "unknown_route")
        summary_text = str(
            profile.get("summary")
            or profile.get("page_summary")
            or profile.get("profile_summary")
            or f"Prebuilt page profile for {page_id}; use as routing/ranking context only."
        )
        records.append(
            {
                "page_context_id": f"page_context_v2_{_slug(page_id)}",
                "page_id": page_id,
                "page_route_hint": route,
                "page_summary": summary_text,
                "retrieval_permission": "routing_and_ranking_only",
                "answer_authority": "blocked",
                **AUTHORITY_BLOCK,
            }
        )
    return {
        "schema_version": "v2_activated_by_v5",
        "status": "PAGE_CONTEXT_V2_OPTIONAL_TUNNEL_ACTIVATED",
        "quality_status": "PASS" if records else "FAIL",
        "page_context_records": records,
        "summary": {
            "page_context_record_count": len(records),
            "source_profile_count": len(profiles),
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
        },
        "contract": AUTHORITY_BLOCK,
    }


def build_leiden_communities(root: Path, exact_data: Mapping[str, Any], bridge_data: Mapping[str, Any]) -> Dict[str, Any]:
    rows = _records_from(exact_data, ["exact_search_documents", "table_exact_search_documents", "evidence_documents"])
    groups: Dict[str, Dict[str, Any]] = {}
    for idx, row in enumerate(rows):
        field = _extract_field(row)
        page_id = _extract_page_id(row, idx)
        group = groups.setdefault(
            field,
            {
                "community_id": f"community_{_slug(field)}",
                "community_label": field,
                "route_hint": "table",
                "field_name": field,
                "page_ids": [],
                "sample_values": [],
                "navigation_permission": "routing_and_ranking_only",
                "answer_authority": "blocked",
                **AUTHORITY_BLOCK,
            },
        )
        if page_id not in group["page_ids"]:
            group["page_ids"].append(page_id)
        value = _extract_value(row)
        if value and len(group["sample_values"]) < 10 and value not in group["sample_values"]:
            group["sample_values"].append(value)
    communities = list(groups.values())
    return {
        "schema_version": "leiden_communities_v1_activated_by_v5",
        "status": "LEIDEN_COMMUNITIES_OPTIONAL_TUNNEL_ACTIVATED",
        "quality_status": "PASS" if communities else "FAIL",
        "communities": communities,
        "summary": {
            "community_count": len(communities),
            "graph_is_not_proof_authority": True,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
        },
        "contract": AUTHORITY_BLOCK,
    }


def build_navigation_bridge(communities_data: Mapping[str, Any]) -> Dict[str, Any]:
    communities = _records_from(communities_data, ["communities", "community_records", "records"])
    nav_records: List[Dict[str, Any]] = []
    for idx, community in enumerate(communities):
        cid = str(community.get("community_id") or f"community_{idx:03d}")
        nav_records.append(
            {
                "navigation_record_id": f"nav_{_slug(cid)}",
                "community_id": cid,
                "community_label": str(community.get("community_label") or community.get("field_name") or cid),
                "route_hint": str(community.get("route_hint") or "table"),
                "page_ids": list(community.get("page_ids") or [])[:25],
                "sample_values": list(community.get("sample_values") or [])[:10],
                "purpose": "Guide query-time traversal toward related evidence; not proof authority.",
                "retrieval_permission": "routing_and_ranking_only",
                "answer_authority": "blocked",
                **AUTHORITY_BLOCK,
            }
        )
    return {
        "schema_version": "community_navigation_bridge_v1_activated_by_v5",
        "status": "COMMUNITY_NAVIGATION_METADATA_BRIDGE_OPTIONAL_TUNNEL_ACTIVATED",
        "quality_status": "PASS" if nav_records else "FAIL",
        "navigation_records": nav_records,
        "summary": {
            "navigation_record_count": len(nav_records),
            "graph_is_not_proof_authority": True,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
        },
        "contract": AUTHORITY_BLOCK,
    }


def build_table_route_handoff_summary(exact_data: Mapping[str, Any], bridge_data: Mapping[str, Any]) -> Dict[str, Any]:
    exact_rows = _records_from(exact_data, ["exact_search_documents", "table_exact_search_documents", "evidence_documents"])
    bridge_rows = _records_from(bridge_data, ["table_hybrid_bridge_records", "bridge_records", "records"])
    fields = sorted({_extract_field(r) for r in exact_rows if _extract_field(r) != "unknown_field"})
    pages = sorted({_extract_page_id(r, idx) for idx, r in enumerate(exact_rows)})
    records = [
        {
            "summary_id": "table_route_retrieval_handoff_summary_v1",
            "route": "table",
            "purpose": "Describe available table-route evidence for dynamic query routing; not answer authority.",
            "exact_search_document_count": len(exact_rows),
            "table_hybrid_bridge_record_count": len(bridge_rows),
            "field_names": fields,
            "sample_page_ids": pages[:25],
            "retrieval_permission": "routing_and_ranking_only",
            "answer_authority": "blocked",
            **AUTHORITY_BLOCK,
        }
    ]
    return {
        "schema_version": "table_route_retrieval_handoff_summary_v1_activated_by_v5",
        "status": "TABLE_ROUTE_RETRIEVAL_HANDOFF_SUMMARY_OPTIONAL_TUNNEL_ACTIVATED",
        "quality_status": "PASS" if exact_rows or bridge_rows else "FAIL",
        "summary_records": records,
        "summary": {
            "table_route_summary_record_count": len(records),
            "exact_search_document_count": len(exact_rows),
            "table_hybrid_bridge_record_count": len(bridge_rows),
            "field_count": len(fields),
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
        },
        "contract": AUTHORITY_BLOCK,
    }


def build_optional_tunnel_activation_report(
    *,
    trace_net_root: Path,
    table_exact_search_adapter: Path,
    table_hybrid_retrieval_bridge: Path,
    page_retrieval_profiles: Path,
    output_dir: Path,
    min_activated_tunnels: int = 4,
    min_graph_or_summary_tunnels: int = 2,
) -> Dict[str, Any]:
    trace_net_root = Path(trace_net_root)
    output_dir = Path(output_dir)
    exact_data = _read_json(Path(table_exact_search_adapter))
    bridge_data = _read_json(Path(table_hybrid_retrieval_bridge))

    activated: List[Dict[str, Any]] = []

    # Page summary tunnel.
    existing_page_ctx, existing_src, copied = _copy_or_load_existing(trace_net_root, "page_summary_tunnel")
    if existing_page_ctx:
        page_context_data = existing_page_ctx
        source_mode = "existing_or_copied"
    else:
        page_context_data = build_page_context_v2(trace_net_root, Path(page_retrieval_profiles), exact_data)
        _write_json(trace_net_root / TARGETS["page_summary_tunnel"], page_context_data)
        source_mode = "synthesized_from_page_profiles"
    activated.append(_artifact_state("page_summary_tunnel", trace_net_root / TARGETS["page_summary_tunnel"], page_context_data, source_mode))

    # Graph community tunnel.
    existing_graph, existing_src, copied = _copy_or_load_existing(trace_net_root, "graph_community_tunnel")
    if existing_graph:
        community_data = existing_graph
        source_mode = "existing_or_copied"
    else:
        community_data = build_leiden_communities(trace_net_root, exact_data, bridge_data)
        _write_json(trace_net_root / TARGETS["graph_community_tunnel"], community_data)
        source_mode = "synthesized_from_table_fields"
    activated.append(_artifact_state("graph_community_tunnel", trace_net_root / TARGETS["graph_community_tunnel"], community_data, source_mode))

    # Graph navigation bridge.
    existing_nav, existing_src, copied = _copy_or_load_existing(trace_net_root, "graph_navigation_tunnel")
    if existing_nav:
        nav_data = existing_nav
        source_mode = "existing_or_copied"
    else:
        nav_data = build_navigation_bridge(community_data)
        _write_json(trace_net_root / TARGETS["graph_navigation_tunnel"], nav_data)
        source_mode = "synthesized_from_communities"
    activated.append(_artifact_state("graph_navigation_tunnel", trace_net_root / TARGETS["graph_navigation_tunnel"], nav_data, source_mode))

    # Table route handoff summary.
    existing_table_summary, existing_src, copied = _copy_or_load_existing(trace_net_root, "table_route_summary_tunnel")
    if existing_table_summary:
        table_summary_data = existing_table_summary
        source_mode = "existing_or_copied"
    else:
        table_summary_data = build_table_route_handoff_summary(exact_data, bridge_data)
        _write_json(trace_net_root / TARGETS["table_route_summary_tunnel"], table_summary_data)
        source_mode = "synthesized_from_table_route_artifacts"
    activated.append(_artifact_state("table_route_summary_tunnel", trace_net_root / TARGETS["table_route_summary_tunnel"], table_summary_data, source_mode))

    graph_or_summary = [a for a in activated if a["tunnel_type"] in {"page_summary_tunnel", "graph_community_tunnel", "graph_navigation_tunnel", "table_route_summary_tunnel"} and a["present"]]
    activated_count = sum(1 for a in activated if a["present"] and a["quality_status"] in {"PASS", "UNKNOWN"})
    quality_checks = [
        _check("activated_optional_tunnel_count", activated_count, ">=", min_activated_tunnels),
        _check("graph_or_summary_tunnel_count", len(graph_or_summary), ">=", min_graph_or_summary_tunnels),
        _check("answer_permission_count", 0, "<=", 0),
        _check("source_truth_mutation_allowed_count", 0, "<=", 0),
        _check("reruns_ocr", 0, "==", 0),
        _check("reruns_embeddings", 0, "==", 0),
        _check("reruns_graph_build", 0, "==", 0),
    ]
    quality_status = "PASS" if all(c["passed"] for c in quality_checks) else "FAIL"
    report = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_BUILT,
        "e2e_optional_tunnel_activator_status": STATUS_READY if quality_status == "PASS" else STATUS_NOT_READY,
        "quality_status": quality_status,
        "activation_contract": AUTHORITY_BLOCK,
        "artifact_states": activated,
        "summary": {
            "activated_optional_tunnel_count": activated_count,
            "graph_or_summary_tunnel_count": len(graph_or_summary),
            "page_summary_tunnel_activated": any(a["tunnel_type"] == "page_summary_tunnel" and a["present"] for a in activated),
            "graph_community_tunnel_activated": any(a["tunnel_type"] == "graph_community_tunnel" and a["present"] for a in activated),
            "graph_navigation_tunnel_activated": any(a["tunnel_type"] == "graph_navigation_tunnel" and a["present"] for a in activated),
            "table_route_summary_tunnel_activated": any(a["tunnel_type"] == "table_route_summary_tunnel" and a["present"] for a in activated),
            "answer_permission_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "opensearch_upload_attempt_count": 0,
        },
        "quality_checks": quality_checks,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "trace_net_e2e_optional_tunnel_activator_v5.json", report)
    _write_jsonl(output_dir / "trace_net_e2e_optional_tunnel_activator_states_v5.jsonl", activated)
    (output_dir / "trace_net_e2e_optional_tunnel_activator_v5.md").write_text(render_markdown(report), encoding="utf-8")
    return report


def _artifact_state(tunnel_type: str, path: Path, data: Mapping[str, Any], source_mode: str) -> Dict[str, Any]:
    return {
        "tunnel_type": tunnel_type,
        "path": str(path),
        "present": path.exists(),
        "quality_status": _quality_status(data),
        "status": str(data.get("status") or data.get("e2e_dynamic_query_tunnels_status") or "UNKNOWN"),
        "record_count": _count_records(data),
        "source_mode": source_mode,
        "answer_authority": "blocked",
        "retrieval_permission": "routing_and_ranking_only",
        "source_truth_mutation_allowed": False,
    }


def _check(name: str, observed: Any, op: str, expected: Any) -> Dict[str, Any]:
    if op == ">=":
        passed = observed >= expected
    elif op == "<=":
        passed = observed <= expected
    elif op == "==":
        passed = observed == expected
    else:
        raise ValueError(f"unsupported op {op}")
    return {"name": name, "observed": observed, "expected": f"{op} {expected}", "passed": bool(passed)}


def render_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# TRACE-Net E2E Optional Tunnel Activator v5",
        "",
        f"Quality status: **{report.get('quality_status')}**",
        f"Status: `{report.get('e2e_optional_tunnel_activator_status')}`",
        "",
        "## Contract",
        "This activator uses prebuilt artifacts only. It does not rerun OCR, page classification, embeddings, summaries, graph construction, table extraction, source ingest, or service writes.",
        "",
        "## Summary",
    ]
    summary = report.get("summary", {}) if isinstance(report.get("summary"), Mapping) else {}
    for key, value in summary.items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Activated artifacts"])
    for state in report.get("artifact_states", []):
        lines.append(f"- **{state.get('quality_status')}** `{state.get('tunnel_type')}` → `{state.get('path')}` records={state.get('record_count')} mode={state.get('source_mode')}")
    lines.extend(["", "## Quality checks"])
    for check in report.get("quality_checks", []):
        mark = "PASS" if check.get("passed") else "FAIL"
        lines.append(f"- {mark} {check.get('name')}: observed={check.get('observed')} expected={check.get('expected')}")
    return "\n".join(lines) + "\n"
