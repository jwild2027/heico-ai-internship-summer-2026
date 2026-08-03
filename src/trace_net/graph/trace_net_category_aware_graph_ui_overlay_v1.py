"""TRACE-Net Category-Aware Graph UI Overlay v1.

Read-only UI overlay that joins the existing graph UI community overlay with the
category-aware Leiden overlay. The goal is to make category-aware community labels,
page category profiles, and category grouping hints visible in the graph/admin UI.

Safety contract:
- Category and community metadata is navigation/retrieval/review-only.
- No Postgres/Qdrant/OpenSearch writes are attempted.
- No source truth mutation is allowed.
- Categories, communities, and UI cards cannot answer directly or prove claims.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "trace_net_category_aware_graph_ui_overlay_v1"
ALGORITHM = "trace_net_read_only_category_aware_graph_ui_overlay_builder_v1"
WRITEBACK_MODE = "dry_run_category_aware_ui_overlay"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/category_aware_graph_ui_overlay")

FORBIDDEN_TRUE_KEYS = {
    "can_answer_directly",
    "can_prove_claims",
    "can_mutate_source_truth",
    "source_truth_mutation_allowed",
    "final_answer_allowed",
}


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":"))


def stable_hash(value: Any, length: int = 16) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()[:length]


def read_json(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    with p.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected object JSON at {p}")
    return payload


def write_json(path: str | Path, payload: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return sorted(value)
    return [value]


def unique_strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (str, int, float, bool)):
        value = [value]
    out = {str(v).strip() for v in value if v is not None and str(v).strip()}
    return sorted(out)


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "allowed", "pass"}
    return bool(value)


def get_quality_status(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("quality_status"), str):
        return payload["quality_status"]
    quality = payload.get("quality")
    if isinstance(quality, dict) and isinstance(quality.get("status"), str):
        return quality["status"]
    summary = payload.get("summary")
    if isinstance(summary, dict):
        for key in ("quality_status", "status"):
            if isinstance(summary.get(key), str):
                return summary[key]
    if isinstance(payload.get("status"), str) and payload.get("status") in {"PASS", "FAIL"}:
        return payload["status"]
    return ""


def normalize_community_id(value: Any) -> str:
    text = str(value or "").strip()
    if text.startswith("community::"):
        text = text.split("::", 1)[1]
    if text.startswith("leiden_community::"):
        text = text.split("::", 1)[1]
    return text


def community_node_id(community_id: Any) -> str:
    return f"leiden_community::{normalize_community_id(community_id)}"


def community_card_node_id(community_id: Any) -> str:
    return f"category_aware_community_card::{normalize_community_id(community_id)}"


def page_node_id(page_id: str) -> str:
    return f"page::{page_id}"


def page_profile_node_id(page_id: str) -> str:
    return f"page_category_profile::{page_id}"


def safe_properties(raw: dict[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
    props: dict[str, Any] = {}
    if raw:
        props.update(raw)
    props.update(extra)
    props.setdefault("can_answer_directly", False)
    props.setdefault("can_prove_claims", False)
    props.setdefault("can_mutate_source_truth", False)
    props.setdefault("source_truth_mutation_allowed", False)
    props.setdefault("source_truth_mutations_performed", 0)
    props.setdefault("final_answer_allowed", False)
    props.setdefault("authority", "category_graph_ui_navigation_only")
    props.setdefault("requires_source_resolution", True)
    props.setdefault("requires_citation", True)
    props.setdefault("requires_authority_gate", True)
    return props


def make_node(
    node_id: str,
    node_type: str,
    label: str,
    *,
    page_id: str | None = None,
    source_page_ids: list[str] | None = None,
    properties: dict[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "node_id": node_id,
        "node_type": node_type,
        "label": label,
        "page_id": page_id,
        "source_page_ids": unique_strings(source_page_ids or []),
        "properties": safe_properties(properties),
    }
    row.update(extra)
    return row


def make_edge(
    edge_type: str,
    source_node_id: str,
    target_node_id: str,
    *,
    page_id: str | None = None,
    properties: dict[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    seed = [edge_type, source_node_id, target_node_id, page_id, properties or {}, extra]
    row: dict[str, Any] = {
        "edge_id": f"catui_edge_{stable_hash(seed)}",
        "edge_type": edge_type,
        "source_node_id": source_node_id,
        "target_node_id": target_node_id,
        "page_id": page_id,
        "properties": safe_properties(properties),
    }
    row.update(extra)
    return row


def extract_nodes_edges(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes = payload.get("node_plans") or payload.get("nodes") or []
    edges = payload.get("edge_plans") or payload.get("edges") or []
    if not isinstance(nodes, list):
        nodes = []
    if not isinstance(edges, list):
        edges = []
    return [dict(n) for n in nodes if isinstance(n, dict)], [dict(e) for e in edges if isinstance(e, dict)]


def extract_category_nodes_edges(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes = payload.get("category_overlay_nodes") or payload.get("node_plans") or payload.get("nodes") or []
    edges = payload.get("category_overlay_edges") or payload.get("edge_plans") or payload.get("edges") or []
    if not isinstance(nodes, list):
        nodes = []
    if not isinstance(edges, list):
        edges = []
    return [dict(n) for n in nodes if isinstance(n, dict)], [dict(e) for e in edges if isinstance(e, dict)]


def extract_community_profiles(category_overlay: dict[str, Any]) -> list[dict[str, Any]]:
    profiles = category_overlay.get("community_category_profiles") or category_overlay.get("communities") or []
    if not isinstance(profiles, list):
        return []
    return [dict(p) for p in profiles if isinstance(p, dict)]


def extract_page_membership(category_overlay: dict[str, Any]) -> list[dict[str, Any]]:
    rows = category_overlay.get("page_category_membership") or category_overlay.get("page_membership") or []
    if not isinstance(rows, list):
        return []
    return [dict(r) for r in rows if isinstance(r, dict)]


def merge_by_id(rows: Iterable[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        row_id = str(row.get(key) or "").strip()
        if not row_id:
            continue
        by_id.setdefault(row_id, row)
    return list(by_id.values())


def count_forbidden_true(obj: Any) -> int:
    count = 0
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in FORBIDDEN_TRUE_KEYS and truthy(value):
                count += 1
            if key == "source_truth_mutations_performed" and isinstance(value, (int, float)) and value > 0:
                count += 1
            count += count_forbidden_true(value)
    elif isinstance(obj, list):
        for item in obj:
            count += count_forbidden_true(item)
    return count


def build_community_card(profile: dict[str, Any]) -> dict[str, Any]:
    community_id = normalize_community_id(profile.get("community_id") or profile.get("id"))
    label = str(profile.get("category_aware_label") or profile.get("label") or f"Category-aware community {community_id}")
    page_ids = unique_strings(profile.get("page_ids") or profile.get("source_page_ids"))
    props = {
        "community_id": community_id,
        "source_community_label": profile.get("source_community_label") or "",
        "category_aware_label": label,
        "page_count": int(profile.get("page_count") or len(page_ids)),
        "review_page_count": int(profile.get("review_page_count") or 0),
        "review_required": truthy(profile.get("review_required")),
        "dominant_page_category_labels": unique_strings(profile.get("dominant_page_category_labels"))[:20],
        "dominant_leiden_hint_families": unique_strings(profile.get("dominant_leiden_hint_families"))[:20],
        "dominant_element_categories": unique_strings(profile.get("dominant_element_categories"))[:25],
        "part_numbers": unique_strings(profile.get("part_numbers"))[:50],
        "authority": "category_aware_community_ui_summary_only",
    }
    return make_node(
        community_card_node_id(community_id),
        "CategoryAwareCommunityCard",
        label,
        source_page_ids=page_ids,
        properties=props,
        node_scope="category_aware_ui_card",
        community_id=community_id,
    )


def build_page_profile_card(row: dict[str, Any]) -> dict[str, Any]:
    page_id = str(row.get("page_id") or "").strip()
    label = str(row.get("page_category_label") or "trace_net_page")
    props = {
        "page_id": page_id,
        "page_category_label": label,
        "category_aware_label": row.get("category_aware_label") or "",
        "community_id": normalize_community_id(row.get("community_id")),
        "dc_type": unique_strings(row.get("dc_type")),
        "leiden_hint_element_families": unique_strings(row.get("leiden_hint_element_families")),
        "suppressed_leiden_hint_families": unique_strings(row.get("suppressed_leiden_hint_families")),
        "review_required": truthy(row.get("review_required")),
        "authority": "page_category_ui_profile_only",
    }
    return make_node(
        page_profile_node_id(page_id),
        "PageCategoryProfileCard",
        f"{page_id} | {label}",
        page_id=page_id,
        source_page_ids=[page_id] if page_id else [],
        properties=props,
        node_scope="page_category_ui_card",
        community_id=props["community_id"],
    )


def ensure_reference_nodes(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    node_ids = {str(n.get("node_id")) for n in nodes if n.get("node_id")}
    added = 0
    for edge in edges:
        for side in ("source_node_id", "target_node_id"):
            node_id = str(edge.get(side) or "")
            if not node_id or node_id in node_ids:
                continue
            if node_id.startswith("page::"):
                page_id = node_id.split("::", 1)[1]
                nodes.append(make_node(node_id, "PageReference", f"Page | {page_id}", page_id=page_id, source_page_ids=[page_id], properties={"authority": "external_page_reference_only"}))
                node_ids.add(node_id)
                added += 1
            elif node_id.startswith("leiden_community::"):
                community_id = node_id.split("::", 1)[1]
                nodes.append(make_node(node_id, "LeidenCommunityReference", f"LeidenCommunity | {community_id}", properties={"community_id": community_id, "authority": "external_community_reference_only"}, node_scope="community_reference"))
                node_ids.add(node_id)
                added += 1
    return nodes, added


def count_orphan_edges(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> int:
    node_ids = {str(n.get("node_id")) for n in nodes if n.get("node_id")}
    count = 0
    for edge in edges:
        if str(edge.get("source_node_id")) not in node_ids or str(edge.get("target_node_id")) not in node_ids:
            count += 1
    return count


def build_overlay_report(
    *,
    graph_ui_community_overlay: dict[str, Any],
    category_aware_leiden_overlay: dict[str, Any],
    element_category_taxonomy: dict[str, Any] | None = None,
    dublin_core_refined: dict[str, Any] | None = None,
) -> dict[str, Any]:
    element_category_taxonomy = element_category_taxonomy or {}
    dublin_core_refined = dublin_core_refined or {}
    source_nodes, source_edges = extract_nodes_edges(graph_ui_community_overlay)
    category_nodes, category_edges = extract_category_nodes_edges(category_aware_leiden_overlay)
    community_profiles = extract_community_profiles(category_aware_leiden_overlay)
    page_membership = extract_page_membership(category_aware_leiden_overlay)

    community_cards = [build_community_card(p) for p in community_profiles if normalize_community_id(p.get("community_id") or p.get("id"))]

    # One page profile card per page, using the first membership row for stable UI display.
    page_rows_by_id: dict[str, dict[str, Any]] = {}
    for row in page_membership:
        page_id = str(row.get("page_id") or "").strip()
        if page_id:
            page_rows_by_id.setdefault(page_id, row)
    page_cards = [build_page_profile_card(row) for _page_id, row in sorted(page_rows_by_id.items())]

    extra_edges: list[dict[str, Any]] = []
    for profile in community_profiles:
        community_id = normalize_community_id(profile.get("community_id") or profile.get("id"))
        if not community_id:
            continue
        extra_edges.append(make_edge(
            "COMMUNITY_HAS_CATEGORY_AWARE_CARD",
            community_node_id(community_id),
            community_card_node_id(community_id),
            properties={"community_id": community_id, "edge_weight": 0.5, "authority": "category_aware_ui_navigation_only"},
        ))
    for row in page_membership:
        page_id = str(row.get("page_id") or "").strip()
        community_id = normalize_community_id(row.get("community_id"))
        if not page_id:
            continue
        extra_edges.append(make_edge(
            "PAGE_HAS_CATEGORY_PROFILE_CARD",
            page_node_id(page_id),
            page_profile_node_id(page_id),
            page_id=page_id,
            properties={"page_category_label": row.get("page_category_label"), "authority": "page_category_ui_navigation_only"},
        ))
        if community_id:
            extra_edges.append(make_edge(
                "CATEGORY_AWARE_COMMUNITY_CARD_HAS_PAGE_PROFILE",
                community_card_node_id(community_id),
                page_profile_node_id(page_id),
                page_id=page_id,
                properties={"community_id": community_id, "page_category_label": row.get("page_category_label"), "edge_weight": 0.25, "authority": "category_aware_ui_navigation_only"},
            ))

    all_nodes = merge_by_id([*source_nodes, *category_nodes, *community_cards, *page_cards], "node_id")
    all_edges = merge_by_id([*source_edges, *category_edges, *extra_edges], "edge_id")
    all_nodes, external_reference_node_count = ensure_reference_nodes(all_nodes, all_edges)
    orphan_edge_count = count_orphan_edges(all_nodes, all_edges)

    summary = build_summary(
        graph_ui_community_overlay=graph_ui_community_overlay,
        category_aware_leiden_overlay=category_aware_leiden_overlay,
        element_category_taxonomy=element_category_taxonomy,
        dublin_core_refined=dublin_core_refined,
        all_nodes=all_nodes,
        all_edges=all_edges,
        community_profiles=community_profiles,
        page_membership=page_membership,
        community_cards=community_cards,
        page_cards=page_cards,
        external_reference_node_count=external_reference_node_count,
        orphan_edge_count=orphan_edge_count,
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "status": "CATEGORY_AWARE_GRAPH_UI_OVERLAY_BUILT",
        "quality_status": "PASS",
        "writeback_mode": WRITEBACK_MODE,
        "generated_at": now_iso(),
        "summary": summary,
        "node_plans": all_nodes,
        "edge_plans": all_edges,
        "category_aware_community_cards": community_cards,
        "page_category_profile_cards": page_cards,
        "community_category_profiles": community_profiles,
        "page_category_membership": page_membership,
    }
    report["quality"] = quality_report(report)
    report["quality_status"] = report["quality"]["status"]
    report["summary"]["status"] = report["quality_status"]
    return report


def build_summary(
    *,
    graph_ui_community_overlay: dict[str, Any],
    category_aware_leiden_overlay: dict[str, Any],
    element_category_taxonomy: dict[str, Any],
    dublin_core_refined: dict[str, Any],
    all_nodes: list[dict[str, Any]],
    all_edges: list[dict[str, Any]],
    community_profiles: list[dict[str, Any]],
    page_membership: list[dict[str, Any]],
    community_cards: list[dict[str, Any]],
    page_cards: list[dict[str, Any]],
    external_reference_node_count: int,
    orphan_edge_count: int,
) -> dict[str, Any]:
    graph_summary = graph_ui_community_overlay.get("summary") or {}
    category_summary = category_aware_leiden_overlay.get("summary") or {}
    taxonomy_summary = element_category_taxonomy.get("summary") or {}
    dc_summary = dublin_core_refined.get("summary") or {}
    node_type_counts = Counter(str(n.get("node_type")) for n in all_nodes)
    edge_type_counts = Counter(str(e.get("edge_type")) for e in all_edges)
    label_counts = Counter(str(c.get("category_aware_label") or "unknown") for c in community_profiles)
    page_label_counts = Counter(str(m.get("page_category_label") or "unknown") for m in page_membership)

    added_nodes = len(all_nodes) - int(graph_summary.get("overlay_node_count") or graph_summary.get("node_plan_count") or 0)
    added_edges = len(all_edges) - int(graph_summary.get("overlay_edge_count") or graph_summary.get("edge_plan_count") or 0)

    forbidden_count = count_forbidden_true([community_cards, page_cards])
    source_truth_mutation_allowed = 0
    for obj in [*community_cards, *page_cards, *all_edges]:
        props = obj.get("properties") if isinstance(obj.get("properties"), dict) else {}
        if truthy(obj.get("source_truth_mutation_allowed")) or truthy(props.get("source_truth_mutation_allowed")):
            source_truth_mutation_allowed += 1

    global_hubs = [n for n in all_nodes if str(n.get("node_type")) == "ElementCategory" or str(n.get("node_id", "")).startswith("category::")]

    return {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "writeback_mode": WRITEBACK_MODE,
        "source_graph_ui_quality_status": get_quality_status(graph_ui_community_overlay),
        "source_category_aware_leiden_quality_status": get_quality_status(category_aware_leiden_overlay),
        "source_element_taxonomy_quality_status": get_quality_status(element_category_taxonomy),
        "source_dublin_core_refined_quality_status": get_quality_status(dublin_core_refined),
        "page_count": int(category_summary.get("page_count") or taxonomy_summary.get("page_count") or dc_summary.get("page_record_count") or len(page_cards)),
        "community_count": int(category_summary.get("community_count") or len(community_profiles)),
        "graph_ui_source_node_count": int(graph_summary.get("overlay_node_count") or graph_summary.get("node_plan_count") or 0),
        "graph_ui_source_edge_count": int(graph_summary.get("overlay_edge_count") or graph_summary.get("edge_plan_count") or 0),
        "category_aware_source_node_count": int(category_summary.get("category_overlay_node_count") or 0),
        "category_aware_source_edge_count": int(category_summary.get("category_overlay_edge_count") or 0),
        "category_aware_community_card_count": len(community_cards),
        "page_category_profile_card_count": len(page_cards),
        "community_cards_with_review_summary_count": sum(1 for n in community_cards if int((n.get("properties") or {}).get("review_page_count") or 0) > 0),
        "total_ui_node_count": len(all_nodes),
        "total_ui_edge_count": len(all_edges),
        "added_category_ui_node_count": max(0, added_nodes),
        "added_category_ui_edge_count": max(0, added_edges),
        "node_type_counts": dict(sorted(node_type_counts.items())),
        "edge_type_counts": dict(sorted(edge_type_counts.items())),
        "category_aware_community_label_counts": dict(sorted(label_counts.items())),
        "page_category_label_counts": dict(sorted(page_label_counts.items())),
        "category_similarity_edge_count": int(category_summary.get("category_similarity_edge_count") or edge_type_counts.get("PAGE_SIMILAR_CATEGORY_PROFILE_TO", 0)),
        "page_local_category_node_count": int(category_summary.get("page_local_category_node_count") or node_type_counts.get("PageLocalCategoryHint", 0)),
        "giant_global_category_hub_count": len(global_hubs),
        "external_reference_node_count": external_reference_node_count,
        "orphan_edge_count": orphan_edge_count,
        "orphan_category_ui_edge_count": orphan_edge_count,
        "category_as_proof_count": forbidden_count,
        "direct_answer_allowed_count": 0,
        "claim_proof_allowed_count": 0,
        "retrieval_only_answer_allowed_count": 0,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed,
        "source_truth_mutations_performed": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "status": "PASS",
    }


def quality_report(
    report: dict[str, Any],
    *,
    require_page_count: int | None = None,
    min_communities: int = 1,
    min_category_aware_community_cards: int = 1,
    min_page_category_profile_cards: int = 1,
    min_category_ui_edges: int = 1,
    require_source_graph_ui_quality_pass: bool = False,
    require_source_category_overlay_quality_pass: bool = False,
    write_json: bool = False,
) -> dict[str, Any]:
    summary = dict(report.get("summary") or {})
    issues: list[str] = []
    if require_page_count is not None and int(summary.get("page_count") or 0) != int(require_page_count):
        issues.append(f"page_count {summary.get('page_count')} != required {require_page_count}")
    if int(summary.get("community_count") or 0) < min_communities:
        issues.append("community_count below minimum")
    if int(summary.get("category_aware_community_card_count") or 0) < min_category_aware_community_cards:
        issues.append("category_aware_community_card_count below minimum")
    if int(summary.get("page_category_profile_card_count") or 0) < min_page_category_profile_cards:
        issues.append("page_category_profile_card_count below minimum")
    if int(summary.get("total_ui_edge_count") or 0) < min_category_ui_edges:
        issues.append("total_ui_edge_count below minimum")
    if int(summary.get("orphan_edge_count") or 0) != 0:
        issues.append("orphan_edge_count must be zero")
    if int(summary.get("giant_global_category_hub_count") or 0) != 0:
        issues.append("giant_global_category_hub_count must be zero")
    if int(summary.get("category_as_proof_count") or 0) != 0:
        issues.append("category_as_proof_count must be zero")
    if int(summary.get("source_truth_mutation_allowed_count") or 0) != 0:
        issues.append("source_truth_mutation_allowed_count must be zero")
    if require_source_graph_ui_quality_pass and summary.get("source_graph_ui_quality_status") != "PASS":
        issues.append("source graph UI quality is not PASS")
    if require_source_category_overlay_quality_pass and summary.get("source_category_aware_leiden_quality_status") != "PASS":
        issues.append("source category-aware Leiden quality is not PASS")
    status = "PASS" if not issues else "FAIL"
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "issues": issues,
        "checks": {
            "page_count": summary.get("page_count"),
            "community_count": summary.get("community_count"),
            "category_aware_community_card_count": summary.get("category_aware_community_card_count"),
            "page_category_profile_card_count": summary.get("page_category_profile_card_count"),
            "total_ui_node_count": summary.get("total_ui_node_count"),
            "total_ui_edge_count": summary.get("total_ui_edge_count"),
            "orphan_edge_count": summary.get("orphan_edge_count"),
            "giant_global_category_hub_count": summary.get("giant_global_category_hub_count"),
            "category_as_proof_count": summary.get("category_as_proof_count"),
            "source_truth_mutation_allowed_count": summary.get("source_truth_mutation_allowed_count"),
        },
        "write_json": bool(write_json),
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = dict(report.get("summary") or {})
    lines = [
        "# TRACE-Net Category-Aware Graph UI Overlay v1",
        "",
        f"**Status:** {report.get('status')}",
        f"**Quality:** {report.get('quality_status')}",
        f"**Writeback mode:** {report.get('writeback_mode')}",
        "",
        "## Summary",
        "",
    ]
    for key in [
        "page_count",
        "community_count",
        "category_aware_community_card_count",
        "page_category_profile_card_count",
        "total_ui_node_count",
        "total_ui_edge_count",
        "category_similarity_edge_count",
        "giant_global_category_hub_count",
        "orphan_edge_count",
        "category_as_proof_count",
        "source_truth_mutation_allowed_count",
    ]:
        lines.append(f"- {key}: {summary.get(key)}")
    lines.extend(["", "## Top category-aware labels", ""])
    counts = summary.get("category_aware_community_label_counts") or {}
    if isinstance(counts, dict):
        for label, count in sorted(counts.items(), key=lambda kv: (-int(kv[1]), kv[0]))[:20]:
            lines.append(f"- {label}: {count}")
    return "\n".join(lines) + "\n"


def render_html(report: dict[str, Any]) -> str:
    body = "\n".join(html.escape(line) for line in render_markdown(report).splitlines())
    return f"<!doctype html><html><head><meta charset='utf-8'><title>TRACE-Net Category-Aware Graph UI Overlay v1</title></head><body><pre>{body}</pre></body></html>\n"


def write_outputs(report: dict[str, Any], output_dir: str | Path) -> dict[str, str]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "report_path": out / "trace_net_category_aware_graph_ui_overlay_v1.json",
        "nodes_path": out / "trace_net_category_aware_graph_ui_overlay_v1_nodes.jsonl",
        "edges_path": out / "trace_net_category_aware_graph_ui_overlay_v1_edges.jsonl",
        "community_cards_path": out / "trace_net_category_aware_graph_ui_overlay_v1_community_cards.jsonl",
        "page_cards_path": out / "trace_net_category_aware_graph_ui_overlay_v1_page_cards.jsonl",
        "summary_path": out / "trace_net_category_aware_graph_ui_overlay_v1_summary.json",
        "quality_path": out / "trace_net_category_aware_graph_ui_overlay_v1_quality.json",
        "manifest_path": out / "trace_net_category_aware_graph_ui_overlay_v1_manifest.json",
        "markdown_path": out / "trace_net_category_aware_graph_ui_overlay_v1.md",
        "html_path": out / "trace_net_category_aware_graph_ui_overlay_v1.html",
    }
    write_json(paths["report_path"], report)
    write_jsonl(paths["nodes_path"], report.get("node_plans", []))
    write_jsonl(paths["edges_path"], report.get("edge_plans", []))
    write_jsonl(paths["community_cards_path"], report.get("category_aware_community_cards", []))
    write_jsonl(paths["page_cards_path"], report.get("page_category_profile_cards", []))
    write_json(paths["summary_path"], report.get("summary", {}))
    write_json(paths["quality_path"], report.get("quality", {}))
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_iso(),
        **{key: str(value) for key, value in paths.items() if key.endswith("_path")},
    }
    write_json(paths["manifest_path"], manifest)
    paths["markdown_path"].write_text(render_markdown(report), encoding="utf-8")
    paths["html_path"].write_text(render_html(report), encoding="utf-8")
    return {key: str(value) for key, value in paths.items()}


def build_category_aware_graph_ui_overlay(
    *,
    graph_ui_community_overlay_path: str | Path,
    category_aware_leiden_overlay_path: str | Path,
    element_category_taxonomy_path: str | Path | None = None,
    dublin_core_refined_path: str | Path | None = None,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    require_page_count: int | None = None,
    min_communities: int = 1,
    min_category_aware_community_cards: int = 1,
    min_page_category_profile_cards: int = 1,
    min_category_ui_edges: int = 1,
    require_source_graph_ui_quality_pass: bool = False,
    require_source_category_overlay_quality_pass: bool = False,
    write_quality: bool = True,
) -> dict[str, Any]:
    graph_ui = read_json(graph_ui_community_overlay_path)
    category_overlay = read_json(category_aware_leiden_overlay_path)
    taxonomy = read_json(element_category_taxonomy_path) if element_category_taxonomy_path else {}
    dublin = read_json(dublin_core_refined_path) if dublin_core_refined_path else {}
    report = build_overlay_report(
        graph_ui_community_overlay=graph_ui,
        category_aware_leiden_overlay=category_overlay,
        element_category_taxonomy=taxonomy,
        dublin_core_refined=dublin,
    )
    q = quality_report(
        report,
        require_page_count=require_page_count,
        min_communities=min_communities,
        min_category_aware_community_cards=min_category_aware_community_cards,
        min_page_category_profile_cards=min_page_category_profile_cards,
        min_category_ui_edges=min_category_ui_edges,
        require_source_graph_ui_quality_pass=require_source_graph_ui_quality_pass,
        require_source_category_overlay_quality_pass=require_source_category_overlay_quality_pass,
        write_json=write_quality,
    )
    report["quality"] = q
    report["quality_status"] = q["status"]
    report["summary"]["status"] = q["status"]
    output_paths = write_outputs(report, output_dir)
    report.update(output_paths)
    return report


def print_summary(report: dict[str, Any]) -> None:
    summary = dict(report.get("summary") or {})
    print("TRACE-Net category-aware graph UI overlay v1")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in [
        "page_count",
        "community_count",
        "category_aware_community_card_count",
        "page_category_profile_card_count",
        "total_ui_node_count",
        "total_ui_edge_count",
        "category_similarity_edge_count",
        "giant_global_category_hub_count",
        "orphan_edge_count",
        "category_as_proof_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    if report.get("report_path"):
        print(f" report_path: {report.get('report_path')}")
    if report.get("quality_path"):
        print(f" quality_path: {report.get('quality_path')}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Category-Aware Graph UI Overlay v1")
    parser.add_argument("--graph-ui-community-overlay", required=True)
    parser.add_argument("--category-aware-leiden-overlay", required=True)
    parser.add_argument("--element-category-taxonomy", default="")
    parser.add_argument("--dublin-core-refined", default="")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--require-page-count", type=int)
    parser.add_argument("--min-communities", type=int, default=1)
    parser.add_argument("--min-category-aware-community-cards", type=int, default=1)
    parser.add_argument("--min-page-category-profile-cards", type=int, default=1)
    parser.add_argument("--min-category-ui-edges", type=int, default=1)
    parser.add_argument("--require-source-graph-ui-quality-pass", action="store_true")
    parser.add_argument("--require-source-category-overlay-quality-pass", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report = build_category_aware_graph_ui_overlay(
        graph_ui_community_overlay_path=args.graph_ui_community_overlay,
        category_aware_leiden_overlay_path=args.category_aware_leiden_overlay,
        element_category_taxonomy_path=args.element_category_taxonomy or None,
        dublin_core_refined_path=args.dublin_core_refined or None,
        output_dir=args.output_dir,
        require_page_count=args.require_page_count,
        min_communities=args.min_communities,
        min_category_aware_community_cards=args.min_category_aware_community_cards,
        min_page_category_profile_cards=args.min_page_category_profile_cards,
        min_category_ui_edges=args.min_category_ui_edges,
        require_source_graph_ui_quality_pass=args.require_source_graph_ui_quality_pass,
        require_source_category_overlay_quality_pass=args.require_source_category_overlay_quality_pass,
        write_quality=args.quality,
    )
    print_summary(report)
    return 0 if report.get("quality_status") == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
