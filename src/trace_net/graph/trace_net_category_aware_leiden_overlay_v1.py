"""TRACE-Net Category-Aware Leiden Overlay v1.

Read-only overlay that combines existing Leiden graph communities with the
TRACE-Net Element Category Taxonomy page profiles. The overlay improves
community labels, page grouping hints, and UI/review summaries without
rerunning graph writeback or treating categories as proof.

Safety contract:
- Categories and communities are retrieval/navigation/review metadata only.
- No Postgres/Qdrant/OpenSearch writes.
- No source-truth mutation.
- No answer or claim-proof authority is granted by this overlay.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "trace_net_category_aware_leiden_overlay_v1"
ALGORITHM = "trace_net_category_aware_leiden_overlay_builder_v1"
WRITEBACK_MODE = "dry_run_category_overlay"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/category_aware_leiden_overlay")

SAFE_FALSE_KEYS = {
    "can_answer_directly",
    "can_prove_claims",
    "can_mutate_source_truth",
    "source_truth_mutation_allowed",
    "source_truth_mutations_performed",
    "final_answer_allowed",
}

CONTENT_FAMILIES = {
    "source",
    "text",
    "table",
    "visual",
    "diagram",
    "chart",
    "part",
    "citation",
    "evidence",
    "context",
    "review",
    "blank",
}

INFRASTRUCTURE_FAMILIES = {
    "search",
    "community",
    "operation",
    "feedback",
    "incident",
    "trust",
    "page_trait",
    "other",
}

FAMILY_ORDER = [
    "source",
    "text",
    "table",
    "visual",
    "diagram",
    "chart",
    "part",
    "citation",
    "evidence",
    "context",
    "review",
    "blank",
    "search",
    "community",
    "operation",
    "feedback",
    "incident",
    "trust",
    "page_trait",
    "other",
]


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


def unique_strings(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, (str, int, float, bool)):
        values = [values]
    out = {str(v).strip() for v in values if v is not None and str(v).strip()}
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


def family_rank(family: str) -> int:
    try:
        return FAMILY_ORDER.index(family)
    except ValueError:
        return len(FAMILY_ORDER)


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


def safe_properties(raw: dict[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if raw:
        payload.update(raw)
    payload.update(extra)
    payload.setdefault("can_answer_directly", False)
    payload.setdefault("can_prove_claims", False)
    payload.setdefault("can_mutate_source_truth", False)
    payload.setdefault("source_truth_mutation_allowed", False)
    payload.setdefault("source_truth_mutations_performed", 0)
    payload.setdefault("final_answer_allowed", False)
    payload.setdefault("authority", "category_community_navigation_only")
    payload.setdefault("requires_source_resolution", True)
    payload.setdefault("requires_citation", True)
    payload.setdefault("requires_authority_gate", True)
    return payload


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
    out: dict[str, Any] = {
        "node_id": node_id,
        "node_type": node_type,
        "label": label,
        "page_id": page_id,
        "source_page_ids": unique_strings(source_page_ids or []),
        "properties": safe_properties(properties),
    }
    out.update(extra)
    return out


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
    out: dict[str, Any] = {
        "edge_id": f"catleiden_edge_{stable_hash(seed)}",
        "edge_type": edge_type,
        "source_node_id": source_node_id,
        "target_node_id": target_node_id,
        "page_id": page_id,
        "properties": safe_properties(properties),
    }
    out.update(extra)
    return out


def normalize_community_id(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.startswith("community::"):
        text = text.split("::", 1)[1]
    if text.startswith("leiden_community::"):
        text = text.split("::", 1)[1]
    return text


def community_node_id(community_id: Any) -> str:
    return f"leiden_community::{normalize_community_id(community_id)}"


def category_summary_node_id(community_id: Any) -> str:
    return f"community_category_summary::{normalize_community_id(community_id)}"


def page_node_id(page_id: str) -> str:
    return f"page::{page_id}"


def page_category_node_id(page_id: str, family: str) -> str:
    return f"page_category::{page_id}::{family}"


def page_similarity_edge_key(a: str, b: str) -> tuple[str, str]:
    return tuple(sorted([a, b]))  # type: ignore[return-value]


def dominant_from_counter(counter: Counter[str], limit: int = 8) -> list[str]:
    return [
        key
        for key, _count in sorted(counter.items(), key=lambda kv: (-kv[1], family_rank(kv[0]), kv[0]))[:limit]
    ]


def int_counter_map(value: Any) -> Counter[str]:
    out: Counter[str] = Counter()
    if not isinstance(value, dict):
        return out
    for key, raw in value.items():
        try:
            count = int(raw or 0)
        except (TypeError, ValueError):
            continue
        if count > 0:
            out[str(key)] += count
    return out


def normalize_page_profile(profile: dict[str, Any]) -> dict[str, Any]:
    page_id = str(profile.get("page_id") or "").strip()
    profile = dict(profile)
    profile["page_id"] = page_id
    profile["dc_type"] = unique_strings(profile.get("dc_type"))
    profile["page_category_label"] = str(profile.get("page_category_label") or "trace_net_page")
    profile["element_family_counts"] = dict(int_counter_map(profile.get("element_family_counts")))
    profile["element_category_counts"] = dict(int_counter_map(profile.get("element_category_counts")))
    profile["leiden_hint_element_families"] = unique_strings(profile.get("leiden_hint_element_families"))
    profile["suppressed_leiden_hint_families"] = unique_strings(profile.get("suppressed_leiden_hint_families"))
    profile["dominant_element_families"] = unique_strings(profile.get("dominant_element_families"))
    profile["semantic_dominant_element_families"] = unique_strings(profile.get("semantic_dominant_element_families"))
    profile["infrastructure_dominant_element_families"] = unique_strings(profile.get("infrastructure_dominant_element_families"))
    profile["community_ids"] = unique_strings(profile.get("community_ids"))
    profile["part_numbers"] = unique_strings(profile.get("part_numbers"))
    profile["review_required"] = truthy(profile.get("review_required"))
    profile["can_answer_directly"] = False
    profile["can_prove_claims"] = False
    profile["can_mutate_source_truth"] = False
    profile["source_truth_mutation_allowed"] = False
    return profile


def load_page_profiles(taxonomy: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for raw in as_list(taxonomy.get("page_category_profiles")):
        if not isinstance(raw, dict):
            continue
        profile = normalize_page_profile(raw)
        if profile.get("page_id"):
            out[profile["page_id"]] = profile
    return out


def collect_community_pages(leiden: dict[str, Any]) -> dict[str, set[str]]:
    pages_by_comm: dict[str, set[str]] = defaultdict(set)
    for comm in as_list(leiden.get("communities")):
        if not isinstance(comm, dict):
            continue
        community_id = normalize_community_id(comm.get("community_id") or comm.get("community_index"))
        if not community_id:
            continue
        for page_id in unique_strings(comm.get("page_ids")):
            pages_by_comm[community_id].add(page_id)
    for member in as_list(leiden.get("node_membership")):
        if not isinstance(member, dict):
            continue
        community_id = normalize_community_id(member.get("community_id") or member.get("community_index"))
        if not community_id:
            continue
        page_id = str(member.get("page_id") or "").strip()
        if page_id:
            pages_by_comm[community_id].add(page_id)
        for page in unique_strings(member.get("source_page_ids")):
            pages_by_comm[community_id].add(page)
    return pages_by_comm


def source_communities_by_id(leiden: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for comm in as_list(leiden.get("communities")):
        if not isinstance(comm, dict):
            continue
        community_id = normalize_community_id(comm.get("community_id") or comm.get("community_index"))
        if community_id:
            out[community_id] = comm
    return out


def label_for_community(
    family_counts: Counter[str],
    page_label_counts: Counter[str],
    source_comm: dict[str, Any] | None = None,
) -> str:
    source_comm = source_comm or {}
    dominant_label = page_label_counts.most_common(1)[0][0] if page_label_counts else ""
    existing_label = str(source_comm.get("label") or "").strip()
    has_table = family_counts.get("table", 0) > 0 or "table" in dominant_label
    has_diagram = family_counts.get("diagram", 0) > 0 or family_counts.get("visual", 0) > 0 or "diagram" in dominant_label or "visual" in dominant_label
    has_part = family_counts.get("part", 0) > 0 or "part" in dominant_label
    has_chart = family_counts.get("chart", 0) > 0 or "chart" in dominant_label
    has_blank = family_counts.get("blank", 0) > 0 or "blank" in dominant_label
    has_text = family_counts.get("text", 0) > 0 or "text" in dominant_label
    has_review = family_counts.get("review", 0) > 0 or "review" in dominant_label

    suffix = " review community" if has_review else " community"
    if has_blank and not any([has_table, has_diagram, has_part, has_chart]):
        return "Blank / source-trace" + suffix
    if has_table and has_diagram and has_part:
        return "Table + parts + diagram" + suffix
    if has_table and has_part:
        return "Parts-list table" + suffix
    if has_diagram and has_part:
        return "Visual part / diagram" + suffix
    if has_chart:
        return "Chart / visual" + suffix
    if has_table:
        return "Table evidence" + suffix
    if has_diagram:
        return "Visual / diagram" + suffix
    if has_part:
        if existing_label.lower().startswith("part"):
            return existing_label
        return "Part candidate" + suffix
    if has_text:
        return "Text / source evidence" + suffix
    return existing_label or "TRACE-Net category-aware community"


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / max(1, len(a | b))


def build_overlay(
    *,
    leiden: dict[str, Any],
    taxonomy: dict[str, Any],
    dublin_core_refined: dict[str, Any] | None = None,
    graph_ui_overlay: dict[str, Any] | None = None,
    max_page_similarity_edges_per_community: int = 25,
) -> dict[str, Any]:
    page_profiles = load_page_profiles(taxonomy)
    pages_by_comm = collect_community_pages(leiden)
    source_by_comm = source_communities_by_id(leiden)
    all_page_ids = set(page_profiles)

    community_profiles: list[dict[str, Any]] = []
    page_membership: list[dict[str, Any]] = []
    overlay_nodes: list[dict[str, Any]] = []
    overlay_edges: list[dict[str, Any]] = []
    category_similarity_edges: list[dict[str, Any]] = []

    communities_seen = set(pages_by_comm) | set(source_by_comm)
    for community_id in sorted(communities_seen):
        source_comm = source_by_comm.get(community_id, {})
        page_ids = sorted(pages_by_comm.get(community_id, set()) & all_page_ids)
        profiles = [page_profiles[p] for p in page_ids if p in page_profiles]

        family_counts: Counter[str] = Counter()
        category_counts: Counter[str] = Counter()
        page_label_counts: Counter[str] = Counter()
        hint_family_counts: Counter[str] = Counter()
        suppressed_family_counts: Counter[str] = Counter()
        dc_type_counts: Counter[str] = Counter()
        review_page_count = 0
        part_numbers: set[str] = set()
        source_page_ids: set[str] = set(page_ids)
        complexity_counts: Counter[str] = Counter()

        for profile in profiles:
            page_label_counts[str(profile.get("page_category_label") or "unknown")] += 1
            family_counts.update(int_counter_map(profile.get("element_family_counts")))
            category_counts.update(int_counter_map(profile.get("element_category_counts")))
            hint_family_counts.update({fam: 1 for fam in unique_strings(profile.get("leiden_hint_element_families"))})
            suppressed_family_counts.update({fam: 1 for fam in unique_strings(profile.get("suppressed_leiden_hint_families"))})
            dc_type_counts.update({typ: 1 for typ in unique_strings(profile.get("dc_type"))})
            if truthy(profile.get("review_required")):
                review_page_count += 1
            part_numbers.update(unique_strings(profile.get("part_numbers")))
            complexity_counts[str(profile.get("complexity_class") or "unknown")] += 1

        dominant_families = dominant_from_counter(family_counts, 10)
        dominant_hint_families = dominant_from_counter(hint_family_counts, 10)
        dominant_categories = [name for name, _ in category_counts.most_common(15)]
        dominant_page_labels = [name for name, _ in page_label_counts.most_common(10)]
        category_label = label_for_community(hint_family_counts or family_counts, page_label_counts, source_comm)
        community_node = community_node_id(community_id)
        summary_node = category_summary_node_id(community_id)

        profile_payload = {
            "community_id": community_id,
            "source_community_label": source_comm.get("label") or "",
            "category_aware_label": category_label,
            "page_count": len(page_ids),
            "page_ids": page_ids[:200],
            "source_page_ids": sorted(source_page_ids)[:200],
            "dominant_page_category_labels": dominant_page_labels,
            "page_category_label_counts": dict(sorted(page_label_counts.items())),
            "element_family_counts": dict(sorted(family_counts.items(), key=lambda kv: (family_rank(kv[0]), kv[0]))),
            "element_category_counts": dict(sorted(category_counts.items())),
            "leiden_hint_family_counts": dict(sorted(hint_family_counts.items(), key=lambda kv: (family_rank(kv[0]), kv[0]))),
            "suppressed_hint_family_counts": dict(sorted(suppressed_family_counts.items(), key=lambda kv: (family_rank(kv[0]), kv[0]))),
            "dominant_element_families": dominant_families,
            "dominant_leiden_hint_families": dominant_hint_families,
            "dominant_element_categories": dominant_categories,
            "dc_type_counts": dict(sorted(dc_type_counts.items())),
            "review_page_count": review_page_count,
            "review_required": review_page_count > 0,
            "complexity_class_counts": dict(sorted(complexity_counts.items())),
            "part_numbers": sorted(part_numbers)[:100],
            "category_overlay_policy": {
                "policy_name": "page_local_category_nodes_and_similarity_edges_v1",
                "avoid_global_category_hubs": True,
                "use_page_local_category_nodes": True,
                "use_page_similarity_edges": True,
                "category_edges_are_low_weight": True,
            },
            "can_answer_directly": False,
            "can_prove_claims": False,
            "can_mutate_source_truth": False,
            "source_truth_mutation_allowed": False,
            "authority": "category_aware_community_navigation_only",
        }
        community_profiles.append(profile_payload)

        overlay_nodes.append(make_node(
            summary_node,
            "CommunityCategorySummary",
            f"{community_id} | {category_label}",
            source_page_ids=page_ids,
            properties={
                "community_id": community_id,
                "category_aware_label": category_label,
                "page_count": len(page_ids),
                "review_page_count": review_page_count,
                "dominant_page_category_labels": dominant_page_labels[:5],
                "dominant_leiden_hint_families": dominant_hint_families[:8],
                "authority": "category_summary_navigation_only",
            },
        ))
        overlay_edges.append(make_edge(
            "COMMUNITY_HAS_CATEGORY_SUMMARY",
            community_node,
            summary_node,
            properties={
                "community_id": community_id,
                "edge_weight": 0.25,
                "authority": "category_summary_navigation_only",
            },
        ))

        # Page-local category nodes and edges. No global category hubs.
        for profile in profiles:
            page_id = profile["page_id"]
            hint_families = unique_strings(profile.get("leiden_hint_element_families"))
            page_membership.append({
                "page_category_membership_id": f"catmem_{stable_hash([community_id, page_id])}",
                "community_id": community_id,
                "page_id": page_id,
                "page_category_label": profile.get("page_category_label"),
                "dc_type": profile.get("dc_type", []),
                "leiden_hint_element_families": hint_families,
                "suppressed_leiden_hint_families": unique_strings(profile.get("suppressed_leiden_hint_families")),
                "element_family_counts": profile.get("element_family_counts", {}),
                "review_required": truthy(profile.get("review_required")),
                "category_aware_label": category_label,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "can_mutate_source_truth": False,
                "source_truth_mutation_allowed": False,
            })
            for family in hint_families:
                if family not in CONTENT_FAMILIES:
                    continue
                node_id = page_category_node_id(page_id, family)
                overlay_nodes.append(make_node(
                    node_id,
                    "PageLocalCategoryHint",
                    f"{page_id} | {family}",
                    page_id=page_id,
                    source_page_ids=[page_id],
                    properties={
                        "page_id": page_id,
                        "element_family": family,
                        "page_category_label": profile.get("page_category_label"),
                        "community_id": community_id,
                        "node_scope": "page_local_category_hint",
                        "avoid_global_category_hub": True,
                        "authority": "page_category_navigation_only",
                    },
                ))
                overlay_edges.append(make_edge(
                    "PAGE_HAS_CATEGORY_HINT",
                    page_node_id(page_id),
                    node_id,
                    page_id=page_id,
                    properties={
                        "element_family": family,
                        "edge_weight": 0.35,
                        "avoid_global_category_hub": True,
                        "authority": "page_category_navigation_only",
                    },
                ))
                overlay_edges.append(make_edge(
                    "COMMUNITY_GROUPS_PAGE_CATEGORY_HINT",
                    summary_node,
                    node_id,
                    page_id=page_id,
                    properties={
                        "community_id": community_id,
                        "element_family": family,
                        "edge_weight": 0.25,
                        "authority": "community_category_navigation_only",
                    },
                ))

        # Page-to-page similarity edges by overlap of tightened hint families.
        pair_scores: list[tuple[float, str, str, list[str]]] = []
        for idx, a in enumerate(profiles):
            a_page = a["page_id"]
            a_hints = set(unique_strings(a.get("leiden_hint_element_families")))
            if not a_hints:
                continue
            for b in profiles[idx + 1:]:
                b_page = b["page_id"]
                b_hints = set(unique_strings(b.get("leiden_hint_element_families")))
                if not b_hints:
                    continue
                score = jaccard(a_hints, b_hints)
                if score >= 0.5:
                    pair_scores.append((score, a_page, b_page, sorted(a_hints & b_hints)))
        pair_scores.sort(key=lambda row: (-row[0], row[1], row[2]))
        seen_pairs: set[tuple[str, str]] = set()
        for score, a_page, b_page, shared in pair_scores[:max_page_similarity_edges_per_community]:
            pair = page_similarity_edge_key(a_page, b_page)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            edge_row = make_edge(
                "PAGE_SIMILAR_CATEGORY_PROFILE_TO",
                page_node_id(a_page),
                page_node_id(b_page),
                properties={
                    "community_id": community_id,
                    "similarity_score": round(score, 6),
                    "shared_hint_families": shared,
                    "edge_weight": round(min(0.75, 0.25 + score / 2), 6),
                    "authority": "category_similarity_navigation_only",
                },
            )
            overlay_edges.append(edge_row)
            category_similarity_edges.append(edge_row)

    # Deduplicate nodes and edges by IDs.
    node_by_id: dict[str, dict[str, Any]] = {}
    for n in overlay_nodes:
        node_by_id.setdefault(str(n["node_id"]), n)
    edge_by_id: dict[str, dict[str, Any]] = {}
    for e in overlay_edges:
        edge_by_id.setdefault(str(e["edge_id"]), e)
    overlay_nodes = list(node_by_id.values())
    overlay_edges = list(edge_by_id.values())

    node_ids = {str(n["node_id"]) for n in overlay_nodes}
    # External source/target nodes are allowed for source graph Page/Community nodes.
    allowed_external_prefixes = ("page::", "leiden_community::")
    orphan_overlay_edges = 0
    for edge in overlay_edges:
        source = str(edge.get("source_node_id") or "")
        target = str(edge.get("target_node_id") or "")
        source_ok = source in node_ids or source.startswith(allowed_external_prefixes)
        target_ok = target in node_ids or target.startswith(allowed_external_prefixes)
        if not source_ok or not target_ok:
            orphan_overlay_edges += 1

    summary = build_summary(
        leiden=leiden,
        taxonomy=taxonomy,
        dublin_core_refined=dublin_core_refined or {},
        graph_ui_overlay=graph_ui_overlay or {},
        page_profiles=page_profiles,
        community_profiles=community_profiles,
        page_membership=page_membership,
        overlay_nodes=overlay_nodes,
        overlay_edges=overlay_edges,
        category_similarity_edges=category_similarity_edges,
        orphan_overlay_edges=orphan_overlay_edges,
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "status": "CATEGORY_AWARE_LEIDEN_OVERLAY_BUILT",
        "quality_status": "PASS",
        "writeback_mode": WRITEBACK_MODE,
        "generated_at": now_iso(),
        "summary": summary,
        "community_category_profiles": community_profiles,
        "page_category_membership": page_membership,
        "category_overlay_nodes": overlay_nodes,
        "category_overlay_edges": overlay_edges,
        "category_similarity_edges": category_similarity_edges,
    }
    report["quality"] = quality_report(report)
    report["quality_status"] = report["quality"]["status"]
    report["summary"]["status"] = report["quality_status"]
    return report


def build_summary(
    *,
    leiden: dict[str, Any],
    taxonomy: dict[str, Any],
    dublin_core_refined: dict[str, Any],
    graph_ui_overlay: dict[str, Any],
    page_profiles: dict[str, dict[str, Any]],
    community_profiles: list[dict[str, Any]],
    page_membership: list[dict[str, Any]],
    overlay_nodes: list[dict[str, Any]],
    overlay_edges: list[dict[str, Any]],
    category_similarity_edges: list[dict[str, Any]],
    orphan_overlay_edges: int,
) -> dict[str, Any]:
    leiden_summary = dict(leiden.get("summary") or {})
    taxonomy_summary = dict(taxonomy.get("summary") or {})
    graph_summary = dict(graph_ui_overlay.get("summary") or {})
    family_counts: Counter[str] = Counter()
    page_label_counts: Counter[str] = Counter()
    community_label_counts: Counter[str] = Counter()
    for profile in page_profiles.values():
        family_counts.update(int_counter_map(profile.get("element_family_counts")))
        page_label_counts[str(profile.get("page_category_label") or "unknown")] += 1
    for comm in community_profiles:
        community_label_counts[str(comm.get("category_aware_label") or "unknown")] += 1

    direct_answer_allowed = 0
    claim_proof_allowed = 0
    source_truth_mutation_allowed = 0
    final_answer_allowed = 0
    for obj in [*overlay_nodes, *overlay_edges, *community_profiles, *page_membership]:
        props = obj.get("properties") if isinstance(obj.get("properties"), dict) else {}
        if truthy(obj.get("can_answer_directly")) or truthy(props.get("can_answer_directly")):
            direct_answer_allowed += 1
        if truthy(obj.get("can_prove_claims")) or truthy(props.get("can_prove_claims")):
            claim_proof_allowed += 1
        if truthy(obj.get("source_truth_mutation_allowed")) or truthy(props.get("source_truth_mutation_allowed")):
            source_truth_mutation_allowed += 1
        if truthy(obj.get("final_answer_allowed")) or truthy(props.get("final_answer_allowed")):
            final_answer_allowed += 1

    global_category_hubs = [
        node for node in overlay_nodes
        if str(node.get("node_type")) == "ElementCategory" or str(node.get("node_id", "")).startswith("category::")
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "writeback_mode": WRITEBACK_MODE,
        "source_leiden_quality_status": get_quality_status(leiden),
        "source_taxonomy_quality_status": get_quality_status(taxonomy),
        "source_dublin_core_refined_quality_status": get_quality_status(dublin_core_refined),
        "source_graph_ui_overlay_quality_status": get_quality_status(graph_ui_overlay),
        "page_count": len(page_profiles),
        "community_count": len(community_profiles),
        "source_leiden_community_count": int(leiden_summary.get("community_count") or len(as_list(leiden.get("communities"))) or 0),
        "page_category_profile_count": len(page_profiles),
        "page_nodes_with_category_profile_count": len(page_profiles),
        "page_category_membership_count": len(page_membership),
        "communities_with_category_summary_count": sum(1 for c in community_profiles if c.get("dominant_leiden_hint_families") or c.get("dominant_page_category_labels")),
        "communities_with_review_summary_count": sum(1 for c in community_profiles if int(c.get("review_page_count") or 0) > 0),
        "category_overlay_node_count": len(overlay_nodes),
        "category_overlay_edge_count": len(overlay_edges),
        "page_local_category_node_count": sum(1 for n in overlay_nodes if n.get("node_type") == "PageLocalCategoryHint"),
        "community_category_summary_node_count": sum(1 for n in overlay_nodes if n.get("node_type") == "CommunityCategorySummary"),
        "page_category_hint_edge_count": sum(1 for e in overlay_edges if e.get("edge_type") == "PAGE_HAS_CATEGORY_HINT"),
        "community_category_summary_edge_count": sum(1 for e in overlay_edges if e.get("edge_type") == "COMMUNITY_HAS_CATEGORY_SUMMARY"),
        "category_similarity_edge_count": len(category_similarity_edges),
        "orphan_category_overlay_edge_count": orphan_overlay_edges,
        "giant_global_category_hub_count": len(global_category_hubs),
        "page_category_label_counts": dict(sorted(page_label_counts.items())),
        "category_aware_community_label_counts": dict(sorted(community_label_counts.items())),
        "element_family_total_counts": dict(sorted(family_counts.items(), key=lambda kv: (family_rank(kv[0]), kv[0]))),
        "taxonomy_category_count": int(taxonomy_summary.get("category_count") or 0),
        "taxonomy_family_count": int(taxonomy_summary.get("family_count") or 0),
        "taxonomy_table_hint_without_table_type_count": int(taxonomy_summary.get("table_hint_without_table_type_count") or 0),
        "taxonomy_visual_hint_without_visual_type_count": int(taxonomy_summary.get("visual_hint_without_visual_type_count") or 0),
        "graph_ui_community_count": int(graph_summary.get("community_count") or 0),
        "category_as_proof_count": claim_proof_allowed,
        "direct_answer_allowed_count": direct_answer_allowed,
        "claim_proof_allowed_count": claim_proof_allowed,
        "retrieval_only_answer_allowed_count": 0,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed,
        "source_truth_mutations_performed": 0,
        "final_answer_allowed_count": final_answer_allowed,
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
    min_page_category_profiles: int = 1,
    min_communities_with_category_summary: int = 1,
    min_category_overlay_edges: int = 1,
    require_source_leiden_quality_pass: bool = False,
    require_source_taxonomy_quality_pass: bool = False,
    write_json: bool = False,
) -> dict[str, Any]:
    summary = dict(report.get("summary") or {})
    issues: list[str] = []
    if require_page_count is not None and int(summary.get("page_count") or 0) != int(require_page_count):
        issues.append(f"page_count {summary.get('page_count')} != required {require_page_count}")
    if int(summary.get("community_count") or 0) < int(min_communities):
        issues.append("community_count below minimum")
    if int(summary.get("page_category_profile_count") or 0) < int(min_page_category_profiles):
        issues.append("page_category_profile_count below minimum")
    if int(summary.get("communities_with_category_summary_count") or 0) < int(min_communities_with_category_summary):
        issues.append("communities_with_category_summary_count below minimum")
    if int(summary.get("category_overlay_edge_count") or 0) < int(min_category_overlay_edges):
        issues.append("category_overlay_edge_count below minimum")
    if require_source_leiden_quality_pass and summary.get("source_leiden_quality_status") != "PASS":
        issues.append("source Leiden quality is not PASS")
    if require_source_taxonomy_quality_pass and summary.get("source_taxonomy_quality_status") != "PASS":
        issues.append("source taxonomy quality is not PASS")
    for key in [
        "category_as_proof_count",
        "direct_answer_allowed_count",
        "claim_proof_allowed_count",
        "retrieval_only_answer_allowed_count",
        "source_truth_mutation_allowed_count",
        "final_answer_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
        "orphan_category_overlay_edge_count",
        "giant_global_category_hub_count",
    ]:
        if int(summary.get(key) or 0) != 0:
            issues.append(f"{key} must be zero")
    status = "PASS" if not issues else "FAIL"
    return {
        "status": status,
        "issues": issues,
        "summary": {
            "page_count": summary.get("page_count"),
            "community_count": summary.get("community_count"),
            "page_category_profile_count": summary.get("page_category_profile_count"),
            "communities_with_category_summary_count": summary.get("communities_with_category_summary_count"),
            "category_overlay_edge_count": summary.get("category_overlay_edge_count"),
            "giant_global_category_hub_count": summary.get("giant_global_category_hub_count"),
            "source_truth_mutation_allowed_count": summary.get("source_truth_mutation_allowed_count"),
            "status": status,
        },
        "write_json": bool(write_json),
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = dict(report.get("summary") or {})
    lines = [
        "# TRACE-Net Category-Aware Leiden Overlay v1",
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
        "page_category_profile_count",
        "communities_with_category_summary_count",
        "category_overlay_node_count",
        "category_overlay_edge_count",
        "page_local_category_node_count",
        "category_similarity_edge_count",
        "giant_global_category_hub_count",
        "category_as_proof_count",
        "source_truth_mutation_allowed_count",
    ]:
        lines.append(f"- {key}: {summary.get(key)}")
    lines.extend(["", "## Top community labels", ""])
    counts = summary.get("category_aware_community_label_counts") or {}
    if isinstance(counts, dict):
        for label, count in sorted(counts.items(), key=lambda kv: (-int(kv[1]), kv[0]))[:20]:
            lines.append(f"- {label}: {count}")
    return "\n".join(lines) + "\n"


def render_html(report: dict[str, Any]) -> str:
    md = render_markdown(report)
    body = "<br/>".join(html.escape(line) for line in md.splitlines())
    return f"<!doctype html><html><head><meta charset='utf-8'><title>TRACE-Net Category-Aware Leiden Overlay v1</title></head><body><pre>{body}</pre></body></html>\n"


def write_outputs(report: dict[str, Any], output_dir: str | Path) -> dict[str, str]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / "trace_net_category_aware_leiden_overlay_v1.json"
    profiles_path = out / "trace_net_category_aware_leiden_overlay_v1_communities.jsonl"
    memberships_path = out / "trace_net_category_aware_leiden_overlay_v1_page_membership.jsonl"
    nodes_path = out / "trace_net_category_aware_leiden_overlay_v1_nodes.jsonl"
    edges_path = out / "trace_net_category_aware_leiden_overlay_v1_edges.jsonl"
    summary_path = out / "trace_net_category_aware_leiden_overlay_v1_summary.json"
    quality_path = out / "trace_net_category_aware_leiden_overlay_v1_quality.json"
    manifest_path = out / "trace_net_category_aware_leiden_overlay_v1_manifest.json"
    md_path = out / "trace_net_category_aware_leiden_overlay_v1.md"
    html_path = out / "trace_net_category_aware_leiden_overlay_v1.html"

    write_json(report_path, report)
    write_jsonl(profiles_path, report.get("community_category_profiles", []))
    write_jsonl(memberships_path, report.get("page_category_membership", []))
    write_jsonl(nodes_path, report.get("category_overlay_nodes", []))
    write_jsonl(edges_path, report.get("category_overlay_edges", []))
    write_json(summary_path, report.get("summary", {}))
    write_json(quality_path, report.get("quality", {}))
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_iso(),
        "report_path": str(report_path),
        "community_profiles_path": str(profiles_path),
        "page_membership_path": str(memberships_path),
        "nodes_path": str(nodes_path),
        "edges_path": str(edges_path),
        "summary_path": str(summary_path),
        "quality_path": str(quality_path),
    }
    write_json(manifest_path, manifest)
    md_path.write_text(render_markdown(report), encoding="utf-8")
    html_path.write_text(render_html(report), encoding="utf-8")
    return {
        "report_path": str(report_path),
        "community_profiles_path": str(profiles_path),
        "page_membership_path": str(memberships_path),
        "nodes_path": str(nodes_path),
        "edges_path": str(edges_path),
        "summary_path": str(summary_path),
        "quality_path": str(quality_path),
        "manifest_path": str(manifest_path),
        "markdown_path": str(md_path),
        "html_path": str(html_path),
    }


def build_category_aware_leiden_overlay(
    *,
    leiden_communities_path: str | Path,
    element_category_taxonomy_path: str | Path,
    dublin_core_refined_path: str | Path | None = None,
    graph_ui_community_overlay_path: str | Path | None = None,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    max_page_similarity_edges_per_community: int = 25,
    require_page_count: int | None = None,
    min_communities: int = 1,
    min_page_category_profiles: int = 1,
    min_communities_with_category_summary: int = 1,
    min_category_overlay_edges: int = 1,
    require_source_leiden_quality_pass: bool = False,
    require_source_taxonomy_quality_pass: bool = False,
    write_quality: bool = True,
) -> dict[str, Any]:
    leiden = read_json(leiden_communities_path)
    taxonomy = read_json(element_category_taxonomy_path)
    dublin_core_refined = read_json(dublin_core_refined_path) if dublin_core_refined_path else {}
    graph_ui_overlay = read_json(graph_ui_community_overlay_path) if graph_ui_community_overlay_path else {}
    report = build_overlay(
        leiden=leiden,
        taxonomy=taxonomy,
        dublin_core_refined=dublin_core_refined,
        graph_ui_overlay=graph_ui_overlay,
        max_page_similarity_edges_per_community=max_page_similarity_edges_per_community,
    )
    q = quality_report(
        report,
        require_page_count=require_page_count,
        min_communities=min_communities,
        min_page_category_profiles=min_page_category_profiles,
        min_communities_with_category_summary=min_communities_with_category_summary,
        min_category_overlay_edges=min_category_overlay_edges,
        require_source_leiden_quality_pass=require_source_leiden_quality_pass,
        require_source_taxonomy_quality_pass=require_source_taxonomy_quality_pass,
        write_json=write_quality,
    )
    report["quality"] = q
    report["quality_status"] = q["status"]
    report["summary"]["status"] = q["status"]
    paths = write_outputs(report, output_dir)
    report.update(paths)
    return report


def print_summary(report: dict[str, Any]) -> None:
    summary = dict(report.get("summary") or {})
    print("TRACE-Net category-aware Leiden overlay v1")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in [
        "page_count",
        "community_count",
        "page_category_profile_count",
        "communities_with_category_summary_count",
        "category_overlay_node_count",
        "category_overlay_edge_count",
        "page_local_category_node_count",
        "category_similarity_edge_count",
        "giant_global_category_hub_count",
        "category_as_proof_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    if report.get("report_path"):
        print(f" report_path: {report.get('report_path')}")
    if report.get("quality_path"):
        print(f" quality_path: {report.get('quality_path')}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Category-Aware Leiden Overlay v1")
    parser.add_argument("--leiden-communities", required=True)
    parser.add_argument("--element-category-taxonomy", required=True)
    parser.add_argument("--dublin-core-refined", default="")
    parser.add_argument("--graph-ui-community-overlay", default="")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--max-page-similarity-edges-per-community", type=int, default=25)
    parser.add_argument("--require-page-count", type=int)
    parser.add_argument("--min-communities", type=int, default=1)
    parser.add_argument("--min-page-category-profiles", type=int, default=1)
    parser.add_argument("--min-communities-with-category-summary", type=int, default=1)
    parser.add_argument("--min-category-overlay-edges", type=int, default=1)
    parser.add_argument("--require-source-leiden-quality-pass", action="store_true")
    parser.add_argument("--require-source-taxonomy-quality-pass", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report = build_category_aware_leiden_overlay(
        leiden_communities_path=args.leiden_communities,
        element_category_taxonomy_path=args.element_category_taxonomy,
        dublin_core_refined_path=args.dublin_core_refined or None,
        graph_ui_community_overlay_path=args.graph_ui_community_overlay or None,
        output_dir=args.output_dir,
        max_page_similarity_edges_per_community=args.max_page_similarity_edges_per_community,
        require_page_count=args.require_page_count,
        min_communities=args.min_communities,
        min_page_category_profiles=args.min_page_category_profiles,
        min_communities_with_category_summary=args.min_communities_with_category_summary,
        min_category_overlay_edges=args.min_category_overlay_edges,
        require_source_leiden_quality_pass=args.require_source_leiden_quality_pass,
        require_source_taxonomy_quality_pass=args.require_source_taxonomy_quality_pass,
        write_quality=args.quality,
    )
    print_summary(report)
    return 0 if report.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
