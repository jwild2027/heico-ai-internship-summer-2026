"""TRACE-Net Graph UI Community Overlay v1.

Read-only overlay builder that links Leiden communities and sanitized feedback/community-aware
retrieval signals onto the enriched TRACE-Net graph overlay.

This module intentionally does not write to Postgres, Qdrant, source files, trust records, or
source truth. Community and feedback records are advisory only.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "trace_net_graph_ui_community_overlay_v1"
ALGORITHM = "trace_net_read_only_graph_ui_community_overlay_v1"
WRITEBACK_MODE = "dry_run_ui_overlay"


COMMUNITY_EDGE_TYPES = {
    "HAS_COMMUNITY_MEMBER",
    "HAS_FEEDBACK_MEMORY_SIGNAL",
    "COMMUNITY_BOOSTS_RETRIEVAL_RESULT",
    "PAGE_HAS_COMMUNITY_AWARE_RESULT",
}


FORBIDDEN_TRUE_KEYS = {
    "can_answer_directly",
    "can_prove_claims",
    "can_mutate_source_truth",
    "source_truth_mutation_allowed",
    "source_truth_mutations_performed",
    "final_answer_allowed",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_hash(value: Any, n: int = 16) -> str:
    blob = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:n]


def read_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected object JSON at {p}")
    return payload


def write_json(path: str | Path, payload: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write("\n")


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def get_payload_quality_status(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("quality_status"), str):
        return payload["quality_status"]
    if isinstance(payload.get("status"), str) and payload.get("status") in {"PASS", "FAIL"}:
        return payload["status"]
    quality = payload.get("quality")
    if isinstance(quality, dict) and isinstance(quality.get("status"), str):
        return quality["status"]
    summary = payload.get("summary")
    if isinstance(summary, dict):
        for key in ("quality_status", "status"):
            if isinstance(summary.get(key), str):
                return summary[key]
    return ""


def safe_properties(raw: dict[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
    props: dict[str, Any] = {}
    if raw:
        props.update(raw)
    props.update(extra)
    props.setdefault("can_answer_directly", False)
    props.setdefault("can_prove_claims", False)
    props.setdefault("can_mutate_source_truth", False)
    props.setdefault("source_truth_mutation_allowed", False)
    props.setdefault("final_answer_allowed", False)
    props.setdefault("authority", "community_feedback_advisory_only")
    props.setdefault("requires_source_resolution", True)
    props.setdefault("requires_citation", True)
    props.setdefault("requires_authority_gate", True)
    return props


def node(
    node_id: str,
    node_type: str,
    label: str,
    page_id: str | None = None,
    properties: dict[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "node_id": node_id,
        "node_type": node_type,
        "label": label,
        "page_id": page_id,
        "properties": safe_properties(properties),
    }
    payload.update(extra)
    return payload


def edge(
    edge_id: str,
    edge_type: str,
    source_node_id: str,
    target_node_id: str,
    page_id: str | None = None,
    properties: dict[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "edge_id": edge_id,
        "edge_type": edge_type,
        "source_node_id": source_node_id,
        "target_node_id": target_node_id,
        "page_id": page_id,
        "properties": safe_properties(properties),
    }
    payload.update(extra)
    return payload


def normalize_community_id(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.startswith("community::"):
        text = text.split("::", 1)[1]
    return text


def community_node_id(community_id: Any) -> str:
    return f"leiden_community::{normalize_community_id(community_id)}"


def feedback_node_id(memory_id: Any) -> str:
    return f"feedback_memory::{memory_id}"


def retrieval_result_node_id(query_id: Any, rank: Any, page_id: Any) -> str:
    return f"community_aware_result::{stable_hash([query_id, rank, page_id])}"


def infer_page_id_from_node_id(node_id: str) -> str | None:
    marker = "t_p_120_1176_p"
    if marker in node_id:
        start = node_id.find(marker)
        candidate = node_id[start : start + len(marker) + 6]
        if len(candidate) == len(marker) + 6:
            return candidate
    return None


def extract_source_nodes_edges(overlay_payload: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes = overlay_payload.get("node_plans") or overlay_payload.get("nodes") or []
    edges = overlay_payload.get("edge_plans") or overlay_payload.get("edges") or []
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ValueError("Source overlay report must contain node_plans/nodes and edge_plans/edges lists")
    return list(nodes), list(edges)


def extract_communities(leiden_payload: dict[str, Any]) -> list[dict[str, Any]]:
    communities = leiden_payload.get("communities") or leiden_payload.get("community_records") or []
    if not isinstance(communities, list):
        return []
    return list(communities)


def extract_node_membership(leiden_payload: dict[str, Any]) -> list[dict[str, Any]]:
    memberships = leiden_payload.get("node_membership") or leiden_payload.get("node_memberships") or []
    if not isinstance(memberships, list):
        return []
    return list(memberships)


def extract_feedback_memory_records(feedback_payload: dict[str, Any]) -> list[dict[str, Any]]:
    records = feedback_payload.get("memory_records") or feedback_payload.get("records") or []
    if not isinstance(records, list):
        return []
    return list(records)


def iter_community_aware_groups(payload: dict[str, Any]) -> Iterable[dict[str, Any]]:
    for query in as_list(payload.get("query_results") or payload.get("results")):
        if not isinstance(query, dict):
            continue
        query_id = query.get("query_id") or query.get("id") or stable_hash(query, 8)
        query_text = query.get("query") or query.get("query_text") or ""
        for group in as_list(query.get("ranked_groups") or query.get("groups")):
            if not isinstance(group, dict):
                continue
            out = dict(group)
            out.setdefault("query_id", query_id)
            out.setdefault("query", query_text)
            yield out


def count_true_in_object(obj: Any, key_names: set[str] = FORBIDDEN_TRUE_KEYS) -> int:
    count = 0
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in key_names and value is True:
                count += 1
            elif key == "source_truth_mutations_performed" and isinstance(value, (int, float)) and value > 0:
                count += 1
            count += count_true_in_object(value, key_names)
    elif isinstance(obj, list):
        for item in obj:
            count += count_true_in_object(item, key_names)
    return count


def community_summary_label(community: dict[str, Any]) -> str:
    community_id = normalize_community_id(community.get("community_id") or community.get("id"))
    label = str(community.get("label") or "").strip()
    if label:
        return label
    families = [str(x) for x in as_list(community.get("part_families")) if str(x)]
    if families:
        return f"Community {community_id} | parts {', '.join(families[:3])}"
    node_types = community.get("dominant_node_types") or community.get("node_type_counts") or []
    if isinstance(node_types, dict):
        top_types = list(node_types.keys())[:3]
    else:
        top_types = [str(x) for x in as_list(node_types)[:3]]
    if top_types:
        return f"Community {community_id} | {', '.join(top_types)}"
    return f"Community {community_id}"


def build_graph_ui_community_overlay(
    graph_overlay_part_normalizer_path: str | Path,
    leiden_communities_path: str | Path,
    feedback_memory_path: str | Path,
    community_aware_retrieval_path: str | Path,
    output_dir: str | Path,
    *,
    require_source_overlay_quality_pass: bool = False,
    require_leiden_quality_pass: bool = False,
    require_feedback_quality_pass: bool = False,
    require_community_aware_quality_pass: bool = False,
    write_quality: bool = False,
) -> dict[str, Any]:
    source_overlay = read_json(graph_overlay_part_normalizer_path)
    leiden = read_json(leiden_communities_path)
    feedback = read_json(feedback_memory_path)
    community_aware = read_json(community_aware_retrieval_path)

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    source_nodes, source_edges = extract_source_nodes_edges(source_overlay)
    node_plans: list[dict[str, Any]] = [dict(n) for n in source_nodes]
    edge_plans: list[dict[str, Any]] = [dict(e) for e in source_edges]
    node_ids = {str(n.get("node_id")) for n in node_plans if n.get("node_id")}

    communities = extract_communities(leiden)
    memberships = extract_node_membership(leiden)
    memory_records = extract_feedback_memory_records(feedback)

    community_id_to_node: dict[str, str] = {}
    community_nodes: list[dict[str, Any]] = []
    for community in communities:
        raw_id = community.get("community_id") or community.get("id") or stable_hash(community, 12)
        cid = normalize_community_id(raw_id)
        cnode_id = community_node_id(cid)
        community_id_to_node[cid] = cnode_id
        props = safe_properties(
            {
                "community_id": cid,
                "node_count": community.get("node_count", 0),
                "page_count": community.get("page_count", 0),
                "dominant_node_types": community.get("dominant_node_types", []),
                "part_families": community.get("part_families", []),
                "part_numbers": community.get("part_numbers", []),
                "page_ids": community.get("page_ids", []),
                "authority": "community_retrieval_review_advisory_only",
                "community_can_prove_claims": False,
                "community_can_answer_directly": False,
            }
        )
        cnode = node(
            cnode_id,
            "LeidenCommunity",
            community_summary_label(community),
            None,
            props,
            node_scope="community_entity",
            community_id=cid,
        )
        community_nodes.append(cnode)
        node_ids.add(cnode_id)
    node_plans.extend(community_nodes)

    membership_edges: list[dict[str, Any]] = []
    membership_by_node_id: dict[str, set[str]] = {}
    membership_by_community: dict[str, set[str]] = {}
    for membership in memberships:
        node_id = str(membership.get("node_id") or membership.get("id") or membership.get("member_node_id") or "")
        cid = normalize_community_id(membership.get("community_id") or membership.get("community") or membership.get("leiden_community_id"))
        if not node_id or not cid:
            continue
        cnode_id = community_id_to_node.get(cid)
        if not cnode_id or node_id not in node_ids:
            continue
        membership_by_node_id.setdefault(node_id, set()).add(cid)
        membership_by_community.setdefault(cid, set()).add(node_id)
        eid = f"community_membership::{stable_hash([cid, node_id])}"
        membership_edges.append(
            edge(
                eid,
                "HAS_COMMUNITY_MEMBER",
                cnode_id,
                node_id,
                membership.get("page_id") or infer_page_id_from_node_id(node_id),
                {
                    "community_id": cid,
                    "authority": "community_membership_advisory_only",
                    "membership_source": "leiden_graph_communities_v1",
                },
            )
        )
    edge_plans.extend(membership_edges)

    # Feedback memory nodes and edges. Link feedback to communities by exact target id and by
    # community-aware retrieval groups that applied the feedback memory.
    feedback_nodes: list[dict[str, Any]] = []
    feedback_by_id: dict[str, dict[str, Any]] = {}
    for record in memory_records:
        memory_id = str(record.get("memory_id") or record.get("feedback_memory_id") or stable_hash(record, 12))
        feedback_by_id[memory_id] = record
        fnode_id = feedback_node_id(memory_id)
        props = safe_properties(
            {
                "memory_id": memory_id,
                "target_type": record.get("target_type"),
                "target_id": record.get("target_id"),
                "feedback_signal": record.get("feedback_signal"),
                "rating_score": record.get("rating_score", 0),
                "feedback_summary": record.get("feedback_summary"),
                "llm_reference_allowed": bool(record.get("llm_reference_allowed")),
                "retrieval_advisory_allowed": bool(record.get("retrieval_advisory_allowed", True)),
                "prompt_injection_flagged": bool(record.get("prompt_injection_flagged")),
                "authority": "feedback_advisory_only",
            }
        )
        fnode = node(
            fnode_id,
            "FeedbackMemory",
            f"FeedbackMemory | {record.get('target_type', 'target')} | {memory_id}",
            None,
            props,
            node_scope="feedback_memory_advisory",
            memory_id=memory_id,
        )
        feedback_nodes.append(fnode)
        node_ids.add(fnode_id)
    node_plans.extend(feedback_nodes)

    feedback_edges: list[dict[str, Any]] = []
    linked_feedback_ids: set[str] = set()
    for memory_id, record in feedback_by_id.items():
        target_type = str(record.get("target_type") or "").lower()
        target_id = normalize_community_id(record.get("target_id"))
        if target_type == "community" and target_id:
            cnode_id = community_id_to_node.get(target_id)
            # Some artifacts use community labels with different zero padding. Try suffix match.
            if not cnode_id:
                for cid, node_id in community_id_to_node.items():
                    if cid.endswith(target_id) or target_id.endswith(cid):
                        cnode_id = node_id
                        break
            if cnode_id:
                eid = f"community_feedback::{stable_hash([target_id, memory_id])}"
                feedback_edges.append(
                    edge(
                        eid,
                        "HAS_FEEDBACK_MEMORY_SIGNAL",
                        cnode_id,
                        feedback_node_id(memory_id),
                        None,
                        {
                            "memory_id": memory_id,
                            "target_type": target_type,
                            "rating_score": record.get("rating_score", 0),
                            "authority": "feedback_advisory_only",
                            "feedback_can_prove_claims": False,
                        },
                    )
                )
                linked_feedback_ids.add(memory_id)

    # Community-aware retrieval nodes and links.
    retrieval_nodes: list[dict[str, Any]] = []
    retrieval_edges: list[dict[str, Any]] = []
    linked_result_ids: set[str] = set()
    for group in iter_community_aware_groups(community_aware):
        community_ids = [normalize_community_id(c) for c in as_list(group.get("community_ids") or group.get("communities"))]
        community_ids = [c for c in community_ids if c in community_id_to_node]
        if not community_ids:
            continue
        query_id = group.get("query_id") or "query"
        rank = group.get("community_aware_rank") or group.get("rank") or group.get("hybrid_rank") or 0
        page_id = group.get("page_id") or group.get("top_page_id")
        result_id = retrieval_result_node_id(query_id, rank, page_id)
        props = safe_properties(
            {
                "query_id": query_id,
                "query": group.get("query"),
                "page_id": page_id,
                "community_ids": community_ids,
                "base_hybrid_score": group.get("base_hybrid_score"),
                "community_boost": group.get("community_boost", 0),
                "feedback_advisory_delta": group.get("feedback_advisory_delta", 0),
                "community_aware_score": group.get("community_aware_score"),
                "feedback_memory_ids_applied": group.get("feedback_memory_ids_applied", []),
                "authority": "community_feedback_retrieval_advisory_only",
            }
        )
        rnode = node(
            result_id,
            "CommunityAwareRetrievalResult",
            f"CommunityAwareResult | {query_id} | rank {rank}",
            page_id,
            props,
            node_scope="retrieval_advisory_result",
            retrieval_result_id=result_id,
        )
        retrieval_nodes.append(rnode)
        node_ids.add(result_id)
        linked_result_ids.add(result_id)
        for cid in community_ids:
            eid = f"community_result::{stable_hash([cid, result_id])}"
            retrieval_edges.append(
                edge(
                    eid,
                    "COMMUNITY_BOOSTS_RETRIEVAL_RESULT",
                    community_id_to_node[cid],
                    result_id,
                    page_id,
                    {
                        "community_id": cid,
                        "authority": "community_retrieval_advisory_only",
                        "community_boost": group.get("community_boost", 0),
                    },
                )
            )
        if page_id:
            page_node_id = f"page::{page_id}"
            if page_node_id in node_ids:
                eid = f"page_result::{stable_hash([page_node_id, result_id])}"
                retrieval_edges.append(
                    edge(
                        eid,
                        "PAGE_HAS_COMMUNITY_AWARE_RESULT",
                        page_node_id,
                        result_id,
                        page_id,
                        {"authority": "retrieval_advisory_only"},
                    )
                )
        for memory_id in as_list(group.get("feedback_memory_ids_applied")):
            memory_id = str(memory_id)
            if memory_id in feedback_by_id:
                linked_feedback_ids.add(memory_id)
                for cid in community_ids[:3]:
                    eid = f"community_feedback_via_result::{stable_hash([cid, memory_id, result_id])}"
                    feedback_edges.append(
                        edge(
                            eid,
                            "HAS_FEEDBACK_MEMORY_SIGNAL",
                            community_id_to_node[cid],
                            feedback_node_id(memory_id),
                            page_id,
                            {
                                "memory_id": memory_id,
                                "linked_via": "community_aware_retrieval_result",
                                "retrieval_result_id": result_id,
                                "authority": "feedback_advisory_only",
                            },
                        )
                    )
    node_plans.extend(retrieval_nodes)
    edge_plans.extend(retrieval_edges)
    edge_plans.extend(feedback_edges)

    all_node_ids = {str(n.get("node_id")) for n in node_plans if n.get("node_id")}
    orphan_edges = [
        e
        for e in edge_plans
        if str(e.get("source_node_id")) not in all_node_ids or str(e.get("target_node_id")) not in all_node_ids
    ]
    orphan_community_edges = [e for e in orphan_edges if e.get("edge_type") in COMMUNITY_EDGE_TYPES]

    node_type_counts: dict[str, int] = {}
    for n in node_plans:
        node_type_counts[str(n.get("node_type"))] = node_type_counts.get(str(n.get("node_type")), 0) + 1
    edge_type_counts: dict[str, int] = {}
    for e in edge_plans:
        edge_type_counts[str(e.get("edge_type"))] = edge_type_counts.get(str(e.get("edge_type")), 0) + 1

    source_summary = source_overlay.get("summary", {}) if isinstance(source_overlay.get("summary"), dict) else {}
    leiden_summary = leiden.get("summary", {}) if isinstance(leiden.get("summary"), dict) else {}
    feedback_summary = feedback.get("summary", {}) if isinstance(feedback.get("summary"), dict) else {}
    community_aware_summary = community_aware.get("summary", {}) if isinstance(community_aware.get("summary"), dict) else {}

    page_nodes_with_community = sum(1 for m in memberships if str(m.get("node_type")) == "Page")
    part_nodes_with_community = sum(1 for m in memberships if str(m.get("node_type")) == "PartCandidate")
    table_cell_nodes_with_community = sum(1 for m in memberships if str(m.get("node_type")) == "TableCell")
    # If membership rows are not included, use Step 20 summary counts.
    page_nodes_with_community = max(page_nodes_with_community, int(leiden_summary.get("page_nodes_with_community_count", 0) or 0))
    part_nodes_with_community = max(part_nodes_with_community, int(leiden_summary.get("part_candidate_nodes_with_community_count", 0) or 0))
    table_cell_nodes_with_community = max(table_cell_nodes_with_community, int(leiden_summary.get("table_cell_nodes_with_community_count", 0) or 0))

    has_nomenclature_edges_preserved = int(
        source_summary.get("has_nomenclature_edges_preserved")
        or source_summary.get("has_nomenclature_edges")
        or edge_type_counts.get("HAS_NOMENCLATURE", 0)
        or 0
    )
    has_context_v2_edges_preserved = int(
        source_summary.get("has_context_v2_edges_preserved")
        or source_summary.get("has_context_v2_edges")
        or edge_type_counts.get("HAS_CONTEXT_V2", 0)
        or 0
    )
    confirmed_blank = int(
        source_summary.get("confirmed_blank_pages_preserve_source_trace_count")
        or leiden_summary.get("confirmed_blank_pages_preserve_source_trace_count")
        or 0
    )

    community_as_proof_count = sum(
        1
        for n in community_nodes
        if n.get("can_answer_directly") is True
        or n.get("can_prove_claims") is True
        or n.get("properties", {}).get("community_can_prove_claims") is True
    )
    feedback_as_proof_count = sum(
        1
        for n in feedback_nodes
        if n.get("can_answer_directly") is True
        or n.get("can_prove_claims") is True
        or n.get("properties", {}).get("feedback_can_prove_claims") is True
    )
    source_truth_mutation_allowed_count = count_true_in_object(
        {
            "community_nodes": community_nodes,
            "feedback_nodes": feedback_nodes,
            "retrieval_nodes": retrieval_nodes,
            "community_edges": membership_edges + retrieval_edges + feedback_edges,
        },
        {"can_mutate_source_truth", "source_truth_mutation_allowed", "source_truth_mutations_performed"},
    )
    retrieval_only_answer_allowed_count = count_true_in_object(
        {
            "community_nodes": community_nodes,
            "feedback_nodes": feedback_nodes,
            "retrieval_nodes": retrieval_nodes,
        },
        {"can_answer_directly", "final_answer_allowed"},
    )

    summary = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "writeback_mode": WRITEBACK_MODE,
        "source_overlay_quality_status": get_payload_quality_status(source_overlay),
        "leiden_quality_status": get_payload_quality_status(leiden),
        "feedback_memory_quality_status": get_payload_quality_status(feedback),
        "community_aware_quality_status": get_payload_quality_status(community_aware),
        "page_count": int(source_summary.get("page_count") or leiden_summary.get("page_count") or node_type_counts.get("Page", 0) or 0),
        "overlay_node_count": len(node_plans),
        "overlay_edge_count": len(edge_plans),
        "node_type_counts": node_type_counts,
        "edge_type_counts": edge_type_counts,
        "community_count": len(communities),
        "community_node_count": len(community_nodes),
        "page_nodes_with_community_count": page_nodes_with_community,
        "part_candidate_nodes_with_community_count": part_nodes_with_community,
        "table_cell_nodes_with_community_count": table_cell_nodes_with_community,
        "feedback_memory_record_count": len(memory_records),
        "feedback_memory_nodes_count": len(feedback_nodes),
        "feedback_memory_records_linked_count": len(linked_feedback_ids),
        "community_aware_result_node_count": len(retrieval_nodes),
        "community_aware_results_linked_count": len(linked_result_ids),
        "orphan_edge_count": len(orphan_edges),
        "orphan_community_edge_count": len(orphan_community_edges),
        "has_nomenclature_edges_preserved": has_nomenclature_edges_preserved,
        "has_context_v2_edges_preserved": has_context_v2_edges_preserved,
        "confirmed_blank_pages_preserve_source_trace_count": confirmed_blank,
        "community_as_proof_count": community_as_proof_count,
        "feedback_as_proof_count": feedback_as_proof_count,
        "retrieval_only_answer_allowed_count": retrieval_only_answer_allowed_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "postgres_write_attempt_count": 0,
        "source_summaries": {
            "source_overlay": source_summary,
            "leiden": leiden_summary,
            "feedback_memory": feedback_summary,
            "community_aware_retrieval": community_aware_summary,
        },
    }

    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "GRAPH_UI_COMMUNITY_OVERLAY_BUILT",
        "quality_status": "PENDING",
        "created_at": utc_now(),
        "writeback_mode": WRITEBACK_MODE,
        "node_plans": node_plans,
        "edge_plans": edge_plans,
        "community_nodes": community_nodes,
        "feedback_memory_nodes": feedback_nodes,
        "community_aware_result_nodes": retrieval_nodes,
        "summary": summary,
    }

    quality = quality_report(
        report,
        require_page_count=None,
        min_overlay_nodes=0,
        min_overlay_edges=0,
        min_communities=0,
        min_page_nodes_with_community=0,
        min_part_candidate_nodes_with_community=0,
        min_table_cell_nodes_with_community=0,
        min_feedback_memory_records_linked=0,
        min_community_aware_results_linked=0,
        min_nomenclature_edges_preserved=0,
        min_context_v2_edges_preserved=0,
        min_confirmed_blank_preserve_source_trace=0,
        require_source_overlay_quality_pass=require_source_overlay_quality_pass,
        require_leiden_quality_pass=require_leiden_quality_pass,
        require_feedback_quality_pass=require_feedback_quality_pass,
        require_community_aware_quality_pass=require_community_aware_quality_pass,
        write_json_report=False,
    )
    report["quality"] = quality
    report["quality_status"] = quality["status"]
    summary["quality_status"] = quality["status"]

    report_path = output / "trace_net_graph_ui_community_overlay_v1.json"
    nodes_path = output / "trace_net_graph_ui_community_overlay_v1_nodes.jsonl"
    edges_path = output / "trace_net_graph_ui_community_overlay_v1_edges.jsonl"
    communities_path = output / "trace_net_graph_ui_community_overlay_v1_communities.jsonl"
    feedback_path = output / "trace_net_graph_ui_community_overlay_v1_feedback_memory.jsonl"
    results_path = output / "trace_net_graph_ui_community_overlay_v1_results.jsonl"
    summary_path = output / "trace_net_graph_ui_community_overlay_v1_summary.json"
    manifest_path = output / "trace_net_graph_ui_community_overlay_v1_manifest.json"
    quality_path = output / "trace_net_graph_ui_community_overlay_v1_quality.json"
    md_path = output / "trace_net_graph_ui_community_overlay_v1.md"
    html_path = output / "trace_net_graph_ui_community_overlay_v1.html"

    write_json(report_path, report)
    write_jsonl(nodes_path, node_plans)
    write_jsonl(edges_path, edge_plans)
    write_jsonl(communities_path, community_nodes)
    write_jsonl(feedback_path, feedback_nodes)
    write_jsonl(results_path, retrieval_nodes)
    write_json(summary_path, summary)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now(),
        "report_path": str(report_path),
        "nodes_path": str(nodes_path),
        "edges_path": str(edges_path),
        "communities_path": str(communities_path),
        "feedback_path": str(feedback_path),
        "results_path": str(results_path),
        "summary_path": str(summary_path),
        "quality_path": str(quality_path),
        "markdown_path": str(md_path),
        "html_path": str(html_path),
        "source_paths": {
            "graph_overlay_part_normalizer": str(graph_overlay_part_normalizer_path),
            "leiden_communities": str(leiden_communities_path),
            "feedback_memory": str(feedback_memory_path),
            "community_aware_retrieval": str(community_aware_retrieval_path),
        },
    }
    write_json(manifest_path, manifest)
    if write_quality:
        write_json(quality_path, quality)

    markdown = render_markdown(report)
    md_path.write_text(markdown, encoding="utf-8")
    html_path.write_text(render_html(markdown), encoding="utf-8")

    report.update(
        {
            "report_path": str(report_path),
            "nodes_path": str(nodes_path),
            "edges_path": str(edges_path),
            "communities_path": str(communities_path),
            "feedback_path": str(feedback_path),
            "results_path": str(results_path),
            "summary_path": str(summary_path),
            "manifest_path": str(manifest_path),
            "quality_path": str(quality_path),
            "markdown_path": str(md_path),
            "html_path": str(html_path),
        }
    )
    return report


def quality_report(
    report_or_path: dict[str, Any] | str | Path,
    *,
    require_page_count: int | None = None,
    min_overlay_nodes: int = 0,
    min_overlay_edges: int = 0,
    min_communities: int = 0,
    min_page_nodes_with_community: int = 0,
    min_part_candidate_nodes_with_community: int = 0,
    min_table_cell_nodes_with_community: int = 0,
    min_feedback_memory_records_linked: int = 0,
    min_community_aware_results_linked: int = 0,
    min_nomenclature_edges_preserved: int = 0,
    min_context_v2_edges_preserved: int = 0,
    min_confirmed_blank_preserve_source_trace: int = 0,
    require_source_overlay_quality_pass: bool = False,
    require_leiden_quality_pass: bool = False,
    require_feedback_quality_pass: bool = False,
    require_community_aware_quality_pass: bool = False,
    write_json_report: bool = False,
) -> dict[str, Any]:
    if isinstance(report_or_path, (str, Path)):
        report = read_json(report_or_path)
        report_path = Path(report_or_path)
    else:
        report = report_or_path
        report_path = None
    summary = dict(report.get("summary", {}))
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, actual: Any = None, expected: Any = None) -> None:
        checks.append({"name": name, "passed": bool(passed), "actual": actual, "expected": expected})

    if require_page_count is not None:
        check("page_count", summary.get("page_count") == require_page_count, summary.get("page_count"), require_page_count)
    check("min_overlay_nodes", int(summary.get("overlay_node_count", 0)) >= min_overlay_nodes, summary.get("overlay_node_count"), f">={min_overlay_nodes}")
    check("min_overlay_edges", int(summary.get("overlay_edge_count", 0)) >= min_overlay_edges, summary.get("overlay_edge_count"), f">={min_overlay_edges}")
    check("min_communities", int(summary.get("community_count", 0)) >= min_communities, summary.get("community_count"), f">={min_communities}")
    check("min_page_nodes_with_community", int(summary.get("page_nodes_with_community_count", 0)) >= min_page_nodes_with_community, summary.get("page_nodes_with_community_count"), f">={min_page_nodes_with_community}")
    check("min_part_candidate_nodes_with_community", int(summary.get("part_candidate_nodes_with_community_count", 0)) >= min_part_candidate_nodes_with_community, summary.get("part_candidate_nodes_with_community_count"), f">={min_part_candidate_nodes_with_community}")
    check("min_table_cell_nodes_with_community", int(summary.get("table_cell_nodes_with_community_count", 0)) >= min_table_cell_nodes_with_community, summary.get("table_cell_nodes_with_community_count"), f">={min_table_cell_nodes_with_community}")
    check("min_feedback_memory_records_linked", int(summary.get("feedback_memory_records_linked_count", 0)) >= min_feedback_memory_records_linked, summary.get("feedback_memory_records_linked_count"), f">={min_feedback_memory_records_linked}")
    check("min_community_aware_results_linked", int(summary.get("community_aware_results_linked_count", 0)) >= min_community_aware_results_linked, summary.get("community_aware_results_linked_count"), f">={min_community_aware_results_linked}")
    check("min_nomenclature_edges_preserved", int(summary.get("has_nomenclature_edges_preserved", 0)) >= min_nomenclature_edges_preserved, summary.get("has_nomenclature_edges_preserved"), f">={min_nomenclature_edges_preserved}")
    check("min_context_v2_edges_preserved", int(summary.get("has_context_v2_edges_preserved", 0)) >= min_context_v2_edges_preserved, summary.get("has_context_v2_edges_preserved"), f">={min_context_v2_edges_preserved}")
    check("min_confirmed_blank_preserve_source_trace", int(summary.get("confirmed_blank_pages_preserve_source_trace_count", 0)) >= min_confirmed_blank_preserve_source_trace, summary.get("confirmed_blank_pages_preserve_source_trace_count"), f">={min_confirmed_blank_preserve_source_trace}")

    check("orphan_edge_count_zero", int(summary.get("orphan_edge_count", 0)) == 0, summary.get("orphan_edge_count"), 0)
    check("orphan_community_edge_count_zero", int(summary.get("orphan_community_edge_count", 0)) == 0, summary.get("orphan_community_edge_count"), 0)
    check("community_as_proof_zero", int(summary.get("community_as_proof_count", 0)) == 0, summary.get("community_as_proof_count"), 0)
    check("feedback_as_proof_zero", int(summary.get("feedback_as_proof_count", 0)) == 0, summary.get("feedback_as_proof_count"), 0)
    check("retrieval_only_answer_allowed_zero", int(summary.get("retrieval_only_answer_allowed_count", 0)) == 0, summary.get("retrieval_only_answer_allowed_count"), 0)
    check("source_truth_mutation_allowed_zero", int(summary.get("source_truth_mutation_allowed_count", 0)) == 0, summary.get("source_truth_mutation_allowed_count"), 0)
    check("postgres_write_attempt_count_zero", int(summary.get("postgres_write_attempt_count", 0)) == 0, summary.get("postgres_write_attempt_count"), 0)

    if require_source_overlay_quality_pass:
        check("source_overlay_quality_pass", summary.get("source_overlay_quality_status") == "PASS", summary.get("source_overlay_quality_status"), "PASS")
    if require_leiden_quality_pass:
        check("leiden_quality_pass", summary.get("leiden_quality_status") == "PASS", summary.get("leiden_quality_status"), "PASS")
    if require_feedback_quality_pass:
        check("feedback_quality_pass", summary.get("feedback_memory_quality_status") == "PASS", summary.get("feedback_memory_quality_status"), "PASS")
    if require_community_aware_quality_pass:
        check("community_aware_quality_pass", summary.get("community_aware_quality_status") == "PASS", summary.get("community_aware_quality_status"), "PASS")

    status = "PASS" if all(c["passed"] for c in checks) else "FAIL"
    quality = {
        "schema_version": f"{SCHEMA_VERSION}_quality",
        "status": status,
        "created_at": utc_now(),
        "checks": checks,
        **{k: summary.get(k) for k in [
            "page_count",
            "overlay_node_count",
            "overlay_edge_count",
            "community_count",
            "page_nodes_with_community_count",
            "part_candidate_nodes_with_community_count",
            "table_cell_nodes_with_community_count",
            "feedback_memory_record_count",
            "feedback_memory_records_linked_count",
            "community_aware_result_node_count",
            "community_aware_results_linked_count",
            "orphan_edge_count",
            "orphan_community_edge_count",
            "has_nomenclature_edges_preserved",
            "has_context_v2_edges_preserved",
            "confirmed_blank_pages_preserve_source_trace_count",
            "community_as_proof_count",
            "feedback_as_proof_count",
            "retrieval_only_answer_allowed_count",
            "source_truth_mutation_allowed_count",
            "postgres_write_attempt_count",
        ]},
    }
    if write_json_report and report_path:
        out = report_path.with_name("trace_net_graph_ui_community_overlay_v1_quality.json")
        write_json(out, quality)
        quality["quality_path"] = str(out)
    return quality


def render_markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        "# TRACE-Net Graph UI Community Overlay v1",
        "",
        f"**Status:** {report.get('status')}",
        f"**Quality:** {report.get('quality_status')}",
        f"**Writeback mode:** {report.get('writeback_mode')}",
        "",
        "## Summary",
        "",
    ]
    keys = [
        "page_count",
        "overlay_node_count",
        "overlay_edge_count",
        "community_count",
        "page_nodes_with_community_count",
        "part_candidate_nodes_with_community_count",
        "table_cell_nodes_with_community_count",
        "feedback_memory_record_count",
        "feedback_memory_records_linked_count",
        "community_aware_result_node_count",
        "community_aware_results_linked_count",
        "orphan_edge_count",
        "orphan_community_edge_count",
        "has_nomenclature_edges_preserved",
        "has_context_v2_edges_preserved",
        "confirmed_blank_pages_preserve_source_trace_count",
        "community_as_proof_count",
        "feedback_as_proof_count",
        "retrieval_only_answer_allowed_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
    ]
    for key in keys:
        lines.append(f"- {key}: {s.get(key)}")
    lines.extend([
        "",
        "## Safety rule",
        "",
        "Community and feedback overlay records are advisory only. They can help routing, review, UI navigation, and ranking simulation. They cannot answer directly, prove claims, mutate source truth, or override citation/trust/final-gate checks.",
    ])
    return "\n".join(lines) + "\n"


def render_html(markdown: str) -> str:
    body = "\n".join(f"<p>{html.escape(line)}</p>" if line else "" for line in markdown.splitlines())
    return f"<!doctype html><html><head><meta charset='utf-8'><title>TRACE-Net Graph UI Community Overlay v1</title></head><body>{body}</body></html>\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net graph UI community overlay v1")
    parser.add_argument("--graph-overlay-part-normalizer", required=True)
    parser.add_argument("--leiden-communities", required=True)
    parser.add_argument("--feedback-memory", required=True)
    parser.add_argument("--community-aware-retrieval", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--require-page-count", type=int, default=None)
    parser.add_argument("--min-overlay-nodes", type=int, default=0)
    parser.add_argument("--min-overlay-edges", type=int, default=0)
    parser.add_argument("--min-communities", type=int, default=0)
    parser.add_argument("--min-page-nodes-with-community", type=int, default=0)
    parser.add_argument("--min-part-candidate-nodes-with-community", type=int, default=0)
    parser.add_argument("--min-table-cell-nodes-with-community", type=int, default=0)
    parser.add_argument("--min-feedback-memory-records-linked", type=int, default=0)
    parser.add_argument("--min-community-aware-results-linked", type=int, default=0)
    parser.add_argument("--min-nomenclature-edges-preserved", type=int, default=0)
    parser.add_argument("--min-context-v2-edges-preserved", type=int, default=0)
    parser.add_argument("--min-confirmed-blank-preserve-source-trace", type=int, default=0)
    parser.add_argument("--require-source-overlay-quality-pass", action="store_true")
    parser.add_argument("--require-leiden-quality-pass", action="store_true")
    parser.add_argument("--require-feedback-quality-pass", action="store_true")
    parser.add_argument("--require-community-aware-quality-pass", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_graph_ui_community_overlay(
        args.graph_overlay_part_normalizer,
        args.leiden_communities,
        args.feedback_memory,
        args.community_aware_retrieval,
        args.output_dir,
        require_source_overlay_quality_pass=args.require_source_overlay_quality_pass,
        require_leiden_quality_pass=args.require_leiden_quality_pass,
        require_feedback_quality_pass=args.require_feedback_quality_pass,
        require_community_aware_quality_pass=args.require_community_aware_quality_pass,
        write_quality=args.quality,
    )
    quality = quality_report(
        report,
        require_page_count=args.require_page_count,
        min_overlay_nodes=args.min_overlay_nodes,
        min_overlay_edges=args.min_overlay_edges,
        min_communities=args.min_communities,
        min_page_nodes_with_community=args.min_page_nodes_with_community,
        min_part_candidate_nodes_with_community=args.min_part_candidate_nodes_with_community,
        min_table_cell_nodes_with_community=args.min_table_cell_nodes_with_community,
        min_feedback_memory_records_linked=args.min_feedback_memory_records_linked,
        min_community_aware_results_linked=args.min_community_aware_results_linked,
        min_nomenclature_edges_preserved=args.min_nomenclature_edges_preserved,
        min_context_v2_edges_preserved=args.min_context_v2_edges_preserved,
        min_confirmed_blank_preserve_source_trace=args.min_confirmed_blank_preserve_source_trace,
        require_source_overlay_quality_pass=args.require_source_overlay_quality_pass,
        require_leiden_quality_pass=args.require_leiden_quality_pass,
        require_feedback_quality_pass=args.require_feedback_quality_pass,
        require_community_aware_quality_pass=args.require_community_aware_quality_pass,
        write_json_report=False,
    )
    # Update report and quality files with threshold-aware status.
    report["quality"] = quality
    report["quality_status"] = quality["status"]
    report["summary"]["quality_status"] = quality["status"]
    write_json(report["report_path"], report)
    write_json(report["summary_path"], report["summary"])
    if args.quality:
        write_json(report["quality_path"], quality)

    s = report["summary"]
    print("TRACE-Net graph UI community overlay v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {quality['status']}")
    print(f" writeback_mode: {report['writeback_mode']}")
    for key in [
        "page_count",
        "overlay_node_count",
        "overlay_edge_count",
        "community_count",
        "page_nodes_with_community_count",
        "part_candidate_nodes_with_community_count",
        "table_cell_nodes_with_community_count",
        "feedback_memory_record_count",
        "feedback_memory_records_linked_count",
        "community_aware_result_node_count",
        "community_aware_results_linked_count",
        "orphan_edge_count",
        "orphan_community_edge_count",
        "has_nomenclature_edges_preserved",
        "has_context_v2_edges_preserved",
        "community_as_proof_count",
        "feedback_as_proof_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {s.get(key)}")
    print(f" report_path: {report['report_path']}")
    if args.quality:
        print(f" quality_path: {report['quality_path']}")
    return 0 if quality["status"] == "PASS" else 1


def quality_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net graph UI community overlay v1 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--require-page-count", type=int, default=None)
    parser.add_argument("--min-overlay-nodes", type=int, default=0)
    parser.add_argument("--min-overlay-edges", type=int, default=0)
    parser.add_argument("--min-communities", type=int, default=0)
    parser.add_argument("--min-page-nodes-with-community", type=int, default=0)
    parser.add_argument("--min-part-candidate-nodes-with-community", type=int, default=0)
    parser.add_argument("--min-table-cell-nodes-with-community", type=int, default=0)
    parser.add_argument("--min-feedback-memory-records-linked", type=int, default=0)
    parser.add_argument("--min-community-aware-results-linked", type=int, default=0)
    parser.add_argument("--min-nomenclature-edges-preserved", type=int, default=0)
    parser.add_argument("--min-context-v2-edges-preserved", type=int, default=0)
    parser.add_argument("--min-confirmed-blank-preserve-source-trace", type=int, default=0)
    parser.add_argument("--require-source-overlay-quality-pass", action="store_true")
    parser.add_argument("--require-leiden-quality-pass", action="store_true")
    parser.add_argument("--require-feedback-quality-pass", action="store_true")
    parser.add_argument("--require-community-aware-quality-pass", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args(argv)
    quality = quality_report(
        args.report_path,
        require_page_count=args.require_page_count,
        min_overlay_nodes=args.min_overlay_nodes,
        min_overlay_edges=args.min_overlay_edges,
        min_communities=args.min_communities,
        min_page_nodes_with_community=args.min_page_nodes_with_community,
        min_part_candidate_nodes_with_community=args.min_part_candidate_nodes_with_community,
        min_table_cell_nodes_with_community=args.min_table_cell_nodes_with_community,
        min_feedback_memory_records_linked=args.min_feedback_memory_records_linked,
        min_community_aware_results_linked=args.min_community_aware_results_linked,
        min_nomenclature_edges_preserved=args.min_nomenclature_edges_preserved,
        min_context_v2_edges_preserved=args.min_context_v2_edges_preserved,
        min_confirmed_blank_preserve_source_trace=args.min_confirmed_blank_preserve_source_trace,
        require_source_overlay_quality_pass=args.require_source_overlay_quality_pass,
        require_leiden_quality_pass=args.require_leiden_quality_pass,
        require_feedback_quality_pass=args.require_feedback_quality_pass,
        require_community_aware_quality_pass=args.require_community_aware_quality_pass,
        write_json_report=args.write_json,
    )
    print("TRACE-Net graph UI community overlay v1 quality")
    print(f" Status: {quality['status']}")
    for key in [
        "page_count",
        "overlay_node_count",
        "overlay_edge_count",
        "community_count",
        "page_nodes_with_community_count",
        "part_candidate_nodes_with_community_count",
        "table_cell_nodes_with_community_count",
        "feedback_memory_records_linked_count",
        "community_aware_results_linked_count",
        "orphan_edge_count",
        "orphan_community_edge_count",
        "community_as_proof_count",
        "feedback_as_proof_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {quality.get(key)}")
    if quality.get("quality_path"):
        print(f" quality_path: {quality['quality_path']}")
    return 0 if quality["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
