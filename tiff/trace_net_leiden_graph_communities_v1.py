"""TRACE-Net Leiden Graph Communities v1.

Step 20 consumes the enriched dry-run graph overlay from Step 19.2 and
builds graph communities for UI navigation, retrieval hints, review grouping,
and future feedback memory. It is read-only: it does not write to Postgres,
mutate source truth, or grant answer authority.

If python-igraph + leidenalg are installed, the module uses the real Leiden
algorithm. Otherwise it uses a deterministic connected-component fallback so
that the pipeline remains runnable in local/dev environments.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = "trace_net_leiden_graph_communities_v1"
ALGORITHM = "trace_net_leiden_graph_communities_v1"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/leiden_graph_communities")

DEFAULT_EXCLUDED_NODE_TYPES = {"TrustAuthority"}
DEFAULT_EXCLUDED_EDGE_TYPES = {"HAS_TRUST_AUTHORITY"}
RETRIEVAL_ONLY_NODE_TYPES = {
    "PageElementRegistry",
    "VisualUnderstanding",
    "VisualRegion",
    "CalloutCandidate",
    "FishnetRetryPlan",
    "FishnetRetryAction",
    "ExtractionRoutePlan",
    "BlankSourceTracePreservation",
    "PartCandidate",
}

EDGE_WEIGHTS = {
    "HAS_TABLE_ELEMENT": 1.8,
    "HAS_TABLE_ROW": 1.4,
    "HAS_TABLE_CELL": 1.1,
    "HAS_VISUAL_UNDERSTANDING": 1.6,
    "HAS_VISUAL_REGION": 1.3,
    "HAS_CALLOUT_CANDIDATE": 1.1,
    "MAY_REFER_TO_PART": 2.0,
    "HAS_EVIDENCE_CANDIDATE": 1.8,
    "HAS_CITATION": 1.3,
    "HAS_FISHNET_RETRY_PLAN": 0.8,
    "HAS_FISHNET_ACTION": 0.6,
    "RECOMMENDS_EXTRACTION_ROUTE": 0.4,
    "HAS_PAGE_ELEMENT_REGISTRY": 0.8,
    "HAS_BLANK_SOURCE_TRACE_PRESERVATION": 1.0,
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_jsonl(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> int:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with p.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")
            count += 1
    return count


def stable_id(prefix: str, *parts: Any) -> str:
    raw = "|".join("" if p is None else str(p) for p in parts)
    return f"{prefix}::{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "allowed"}
    return False


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def props(record: Mapping[str, Any]) -> dict[str, Any]:
    value = record.get("properties")
    return dict(value) if isinstance(value, Mapping) else {}


def node_id(node: Mapping[str, Any]) -> str:
    return str(node.get("node_id") or node.get("id") or stable_id("node", node.get("label"), props(node)))


def node_type(node: Mapping[str, Any]) -> str:
    return str(node.get("node_type") or node.get("type") or "")


def edge_type(edge: Mapping[str, Any]) -> str:
    return str(edge.get("edge_type") or edge.get("type") or "")


def edge_source(edge: Mapping[str, Any]) -> str:
    return str(edge.get("source_node_id") or edge.get("source") or "")


def edge_target(edge: Mapping[str, Any]) -> str:
    return str(edge.get("target_node_id") or edge.get("target") or "")


def page_id_from_node(node: Mapping[str, Any]) -> str | None:
    if node.get("page_id"):
        return str(node["page_id"])
    p = props(node)
    if p.get("page_id"):
        return str(p["page_id"])
    pages = node.get("source_page_ids") or p.get("source_page_ids")
    if isinstance(pages, list) and len(pages) == 1:
        return str(pages[0])
    return None


def source_page_ids_from_node(node: Mapping[str, Any]) -> list[str]:
    p = props(node)
    values = node.get("source_page_ids") or p.get("source_page_ids") or []
    if not isinstance(values, list):
        values = [values]
    page = page_id_from_node(node)
    if page:
        values.append(page)
    return sorted({str(v) for v in values if v})


def normalize_node(node: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(node)
    out.setdefault("node_id", node_id(node))
    out.setdefault("node_type", node_type(node))
    out.setdefault("label", str(node.get("label") or out["node_id"]))
    out["properties"] = props(out)
    return out


def normalize_edge(edge: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(edge)
    out.setdefault("edge_id", str(edge.get("edge_id") or stable_id("edge", edge_source(edge), edge_type(edge), edge_target(edge))))
    out.setdefault("source_node_id", edge_source(edge))
    out.setdefault("target_node_id", edge_target(edge))
    out.setdefault("edge_type", edge_type(edge))
    return out


def compute_orphan_edges(nodes: list[Mapping[str, Any]], edges: list[Mapping[str, Any]]) -> int:
    ids = {node_id(n) for n in nodes}
    return sum(1 for e in edges if edge_source(e) not in ids or edge_target(e) not in ids)


def edge_weight(et: str) -> float:
    return float(EDGE_WEIGHTS.get(et, 1.0))


def filter_edges_for_communities(
    nodes_by_id: Mapping[str, Mapping[str, Any]],
    edges: list[dict[str, Any]],
    excluded_node_types: set[str] | None = None,
    excluded_edge_types: set[str] | None = None,
) -> list[dict[str, Any]]:
    excluded_node_types = excluded_node_types or set(DEFAULT_EXCLUDED_NODE_TYPES)
    excluded_edge_types = excluded_edge_types or set(DEFAULT_EXCLUDED_EDGE_TYPES)
    out: list[dict[str, Any]] = []
    for edge in edges:
        src = edge_source(edge)
        tgt = edge_target(edge)
        if src not in nodes_by_id or tgt not in nodes_by_id:
            continue
        et = edge_type(edge)
        if et in excluded_edge_types:
            continue
        if node_type(nodes_by_id[src]) in excluded_node_types or node_type(nodes_by_id[tgt]) in excluded_node_types:
            continue
        out.append(edge)
    return out


class UnionFind:
    def __init__(self, values: Iterable[str]) -> None:
        self.parent = {v: v for v in values}
        self.size = {v: 1 for v in values}

    def find(self, value: str) -> str:
        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, a: str, b: str) -> None:
        ra = self.find(a)
        rb = self.find(b)
        if ra == rb:
            return
        if self.size[ra] < self.size[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        self.size[ra] += self.size[rb]

    def groups(self) -> list[list[str]]:
        buckets: dict[str, list[str]] = defaultdict(list)
        for value in self.parent:
            buckets[self.find(value)].append(value)
        return [sorted(v) for v in buckets.values()]


def connected_component_fallback(node_ids: list[str], edges: list[dict[str, Any]]) -> tuple[dict[str, int], str, bool]:
    uf = UnionFind(node_ids)
    for edge in edges:
        src = edge_source(edge)
        tgt = edge_target(edge)
        if src in uf.parent and tgt in uf.parent:
            uf.union(src, tgt)
    groups = sorted(uf.groups(), key=lambda g: (-len(g), g[0] if g else ""))
    membership: dict[str, int] = {}
    for idx, group in enumerate(groups, start=1):
        for nid in group:
            membership[nid] = idx
    return membership, "connected_components_fallback", False


def leiden_membership(
    node_ids: list[str],
    edges: list[dict[str, Any]],
    resolution: float,
) -> tuple[dict[str, int], str, bool]:
    try:
        import igraph as ig  # type: ignore
        import leidenalg  # type: ignore
    except Exception:
        return connected_component_fallback(node_ids, edges)

    if not node_ids:
        return {}, "leiden", True

    index = {nid: idx for idx, nid in enumerate(node_ids)}
    edge_pairs: list[tuple[int, int]] = []
    weights: list[float] = []
    for edge in edges:
        src = edge_source(edge)
        tgt = edge_target(edge)
        if src in index and tgt in index and src != tgt:
            edge_pairs.append((index[src], index[tgt]))
            weights.append(edge_weight(edge_type(edge)))

    if not edge_pairs:
        return connected_component_fallback(node_ids, edges)

    graph = ig.Graph(n=len(node_ids), edges=edge_pairs, directed=False)
    graph.vs["name"] = node_ids
    graph.es["weight"] = weights
    partition = leidenalg.find_partition(  # type: ignore[attr-defined]
        graph,
        leidenalg.RBConfigurationVertexPartition,  # type: ignore[attr-defined]
        weights="weight",
        resolution_parameter=resolution,
    )
    membership: dict[str, int] = {}
    for idx, community_id in enumerate(partition.membership):
        membership[node_ids[idx]] = int(community_id) + 1
    return membership, "leiden", True


def detect_membership(
    nodes: list[dict[str, Any]],
    community_edges: list[dict[str, Any]],
    algorithm: str,
    resolution: float,
) -> tuple[dict[str, int], str, bool]:
    node_ids = sorted(node_id(n) for n in nodes)
    if algorithm == "connected-components":
        return connected_component_fallback(node_ids, community_edges)
    if algorithm == "leiden":
        return leiden_membership(node_ids, community_edges, resolution)
    # auto
    return leiden_membership(node_ids, community_edges, resolution)


def community_id_name(raw_id: int) -> str:
    return f"tracenet_community_{raw_id:05d}"


def summarize_community(
    raw_id: int,
    node_ids: list[str],
    nodes_by_id: Mapping[str, dict[str, Any]],
    edges: list[dict[str, Any]],
    edge_membership: Mapping[str, int],
) -> dict[str, Any]:
    community_nodes = [nodes_by_id[nid] for nid in node_ids if nid in nodes_by_id]
    node_type_counts = Counter(node_type(n) for n in community_nodes)
    page_ids: set[str] = set()
    source_page_ids: set[str] = set()
    part_numbers: set[str] = set()
    part_families: set[str] = set()
    citation_ids: set[str] = set()

    for node in community_nodes:
        if node_type(node) == "Page" and page_id_from_node(node):
            page_ids.add(page_id_from_node(node) or "")
        for p in source_page_ids_from_node(node):
            source_page_ids.add(p)
            page_ids.add(p)
        p = props(node)
        part = node.get("part_number") or p.get("part_number") or p.get("canonical_part_candidate")
        if part:
            part_numbers.add(str(part))
        family = node.get("part_family") or p.get("part_family")
        if family:
            part_families.add(str(family))
        if node_type(node) == "Citation":
            citation_ids.add(node_id(node).replace("citation::", ""))

    edge_count = sum(1 for e in edges if edge_membership.get(e.get("edge_id")) == raw_id)
    dominant_node_types = [name for name, _ in node_type_counts.most_common(5)]
    label = make_community_label(node_type_counts, sorted(page_ids), sorted(part_families), sorted(part_numbers))
    return {
        "community_id": community_id_name(raw_id),
        "community_index": raw_id,
        "label": label,
        "node_count": len(community_nodes),
        "edge_count": edge_count,
        "page_count": len(page_ids),
        "source_page_count": len(source_page_ids),
        "node_type_counts": dict(sorted(node_type_counts.items())),
        "dominant_node_types": dominant_node_types,
        "page_ids": sorted(page_ids)[:50],
        "part_numbers": sorted(part_numbers)[:50],
        "part_families": sorted(part_families)[:50],
        "citation_count": len(citation_ids),
        "citation_ids": sorted(citation_ids)[:50],
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "authority": "community_retrieval_and_review_only",
        "safety_bucket": "leiden_graph_community_retrieval_helper",
        "requires_source_resolution": True,
        "requires_citation": True,
        "requires_authority_gate": True,
    }


def make_community_label(
    node_type_counts: Counter[str],
    page_ids: list[str],
    part_families: list[str],
    part_numbers: list[str],
) -> str:
    if part_families:
        return f"Part family community {part_families[0]}"
    if part_numbers:
        return f"Part candidate community {part_numbers[0]}"
    if node_type_counts.get("TableCell") or node_type_counts.get("TableRow"):
        return f"Table evidence community ({len(page_ids)} page(s))"
    if node_type_counts.get("VisualUnderstanding") or node_type_counts.get("VisualRegion"):
        return f"Visual evidence community ({len(page_ids)} page(s))"
    if page_ids:
        return f"Page community {page_ids[0]}"
    return "TRACE-Net graph community"


def assign_edge_membership(edges: list[dict[str, Any]], membership: Mapping[str, int]) -> dict[str, int | None]:
    out: dict[str, int | None] = {}
    for edge in edges:
        src = membership.get(edge_source(edge))
        tgt = membership.get(edge_target(edge))
        if src is not None and src == tgt:
            out[edge.get("edge_id", stable_id("edge", edge_source(edge), edge_target(edge)))] = src
        else:
            out[edge.get("edge_id", stable_id("edge", edge_source(edge), edge_target(edge)))] = None
    return out


def build_node_membership(nodes: list[dict[str, Any]], membership: Mapping[str, int]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for node in nodes:
        nid = node_id(node)
        raw_id = membership.get(nid)
        rows.append({
            "node_id": nid,
            "node_type": node_type(node),
            "label": str(node.get("label") or nid),
            "page_id": page_id_from_node(node),
            "source_page_ids": source_page_ids_from_node(node),
            "community_index": raw_id,
            "community_id": community_id_name(raw_id) if raw_id is not None else None,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "can_mutate_source_truth": False,
            "authority": "community_membership_retrieval_helper_only",
        })
    return rows


def safety_counts(nodes: list[dict[str, Any]], communities: list[dict[str, Any]]) -> dict[str, int]:
    direct_answer_allowed = 0
    claim_proof_allowed = 0
    source_truth_mutation_allowed = 0
    retrieval_only_answer_allowed = 0
    for node in nodes:
        p = props(node)
        can_answer = truthy(node.get("can_answer_directly")) or truthy(p.get("can_answer_directly"))
        can_prove = truthy(node.get("can_prove_claims")) or truthy(p.get("can_prove_claims"))
        can_mutate = truthy(node.get("can_mutate_source_truth")) or truthy(p.get("can_mutate_source_truth"))
        if can_answer:
            direct_answer_allowed += 1
        if can_prove:
            claim_proof_allowed += 1
        if can_mutate:
            source_truth_mutation_allowed += 1
        if node_type(node) in RETRIEVAL_ONLY_NODE_TYPES and can_answer:
            retrieval_only_answer_allowed += 1
    for comm in communities:
        if truthy(comm.get("can_answer_directly")):
            direct_answer_allowed += 1
        if truthy(comm.get("can_prove_claims")):
            claim_proof_allowed += 1
        if truthy(comm.get("can_mutate_source_truth")):
            source_truth_mutation_allowed += 1
    return {
        "direct_answer_allowed_count": direct_answer_allowed,
        "claim_proof_allowed_count": claim_proof_allowed,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed,
        "retrieval_only_answer_allowed_count": retrieval_only_answer_allowed,
    }


def build_quality(summary: Mapping[str, Any], args: argparse.Namespace | None = None) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, actual: Any = None, expected: Any = None) -> None:
        checks.append({"name": name, "passed": bool(passed), "actual": actual, "expected": expected})

    if args is not None:
        if args.require_page_count is not None:
            add("page_count", summary.get("page_count") == args.require_page_count, summary.get("page_count"), args.require_page_count)
        add("community_count", summary.get("community_count", 0) >= args.min_communities, summary.get("community_count"), f">={args.min_communities}")
        add("node_count", summary.get("node_count", 0) >= args.min_nodes, summary.get("node_count"), f">={args.min_nodes}")
        add("edge_count", summary.get("edge_count", 0) >= args.min_edges, summary.get("edge_count"), f">={args.min_edges}")
        add("page_nodes_with_community", summary.get("page_nodes_with_community_count", 0) >= args.min_page_nodes_with_community, summary.get("page_nodes_with_community_count"), f">={args.min_page_nodes_with_community}")
        add("part_candidate_nodes_with_community", summary.get("part_candidate_nodes_with_community_count", 0) >= args.min_part_candidate_nodes_with_community, summary.get("part_candidate_nodes_with_community_count"), f">={args.min_part_candidate_nodes_with_community}")
        add("table_cell_nodes_with_community", summary.get("table_cell_nodes_with_community_count", 0) >= args.min_table_cell_nodes_with_community, summary.get("table_cell_nodes_with_community_count"), f">={args.min_table_cell_nodes_with_community}")
        add("nomenclature_edges_preserved", summary.get("has_nomenclature_edges_preserved", 0) >= args.min_nomenclature_edges_preserved, summary.get("has_nomenclature_edges_preserved"), f">={args.min_nomenclature_edges_preserved}")
        add("context_v2_edges_preserved", summary.get("has_context_v2_edges_preserved", 0) >= args.min_context_v2_edges_preserved, summary.get("has_context_v2_edges_preserved"), f">={args.min_context_v2_edges_preserved}")
        add("confirmed_blank_pages_preserve_source_trace", summary.get("confirmed_blank_pages_preserve_source_trace_count", 0) >= args.min_confirmed_blank_preserve_source_trace, summary.get("confirmed_blank_pages_preserve_source_trace_count"), f">={args.min_confirmed_blank_preserve_source_trace}")
        if args.require_source_overlay_quality_pass:
            add("source_overlay_quality_status", summary.get("source_overlay_quality_status") == "PASS", summary.get("source_overlay_quality_status"), "PASS")

    add("orphan_edge_count", summary.get("orphan_edge_count", 0) == 0, summary.get("orphan_edge_count"), 0)
    add("direct_answer_allowed_count", summary.get("direct_answer_allowed_count", 0) == 0, summary.get("direct_answer_allowed_count"), 0)
    add("claim_proof_allowed_count", summary.get("claim_proof_allowed_count", 0) == 0, summary.get("claim_proof_allowed_count"), 0)
    add("retrieval_only_answer_allowed_count", summary.get("retrieval_only_answer_allowed_count", 0) == 0, summary.get("retrieval_only_answer_allowed_count"), 0)
    add("source_truth_mutation_allowed_count", summary.get("source_truth_mutation_allowed_count", 0) == 0, summary.get("source_truth_mutation_allowed_count"), 0)

    status = "PASS" if all(c["passed"] for c in checks) else "FAIL"
    return {"status": status, "checks": checks}


def build_report(
    source_report: Mapping[str, Any],
    algorithm: str = "auto",
    resolution: float = 1.0,
) -> dict[str, Any]:
    nodes = [normalize_node(n) for n in source_report.get("node_plans") or source_report.get("nodes") or []]
    edges = [normalize_edge(e) for e in source_report.get("edge_plans") or source_report.get("edges") or []]
    nodes_by_id = {node_id(n): n for n in nodes}
    community_edges = filter_edges_for_communities(nodes_by_id, edges)
    membership, algorithm_used, leiden_used = detect_membership(nodes, community_edges, algorithm, resolution)
    edge_membership_raw = assign_edge_membership(community_edges, membership)

    community_nodes: dict[int, list[str]] = defaultdict(list)
    for nid, raw_id in membership.items():
        community_nodes[int(raw_id)].append(nid)

    edge_membership: dict[str, int] = {eid: int(cid) for eid, cid in edge_membership_raw.items() if cid is not None}
    communities = [
        summarize_community(raw_id, sorted(nids), nodes_by_id, community_edges, edge_membership)
        for raw_id, nids in sorted(community_nodes.items(), key=lambda item: (-len(item[1]), item[0]))
    ]

    node_membership = build_node_membership(nodes, membership)
    node_type_counts = Counter(node_type(n) for n in nodes)
    community_size_counts = Counter(str(c["node_count"]) for c in communities)
    source_summary = dict(source_report.get("summary") or {})
    orphan_edges = compute_orphan_edges(nodes, edges)
    scounts = safety_counts(nodes, communities)
    page_count = source_summary.get("page_count") or node_type_counts.get("Page", 0)
    part_candidate_count = node_type_counts.get("PartCandidate", 0)
    table_cell_count = node_type_counts.get("TableCell", 0)
    page_nodes_with_community_count = sum(1 for r in node_membership if r["node_type"] == "Page" and r.get("community_id"))
    part_candidate_nodes_with_community_count = sum(1 for r in node_membership if r["node_type"] == "PartCandidate" and r.get("community_id"))
    table_cell_nodes_with_community_count = sum(1 for r in node_membership if r["node_type"] == "TableCell" and r.get("community_id"))

    summary = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "community_algorithm_requested": algorithm,
        "community_algorithm_used": algorithm_used,
        "leiden_used": leiden_used,
        "fallback_used": not leiden_used,
        "resolution": resolution,
        "source_overlay_quality_status": source_report.get("quality_status") or source_summary.get("quality_status"),
        "page_count": int(page_count or 0),
        "node_count": len(nodes),
        "edge_count": len(edges),
        "community_graph_edge_count": len(community_edges),
        "community_count": len(communities),
        "largest_community_node_count": max((c["node_count"] for c in communities), default=0),
        "smallest_community_node_count": min((c["node_count"] for c in communities), default=0),
        "node_type_counts": dict(sorted(node_type_counts.items())),
        "community_size_counts": dict(sorted(community_size_counts.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 0)),
        "page_nodes_with_community_count": page_nodes_with_community_count,
        "part_candidate_node_count": part_candidate_count,
        "part_candidate_nodes_with_community_count": part_candidate_nodes_with_community_count,
        "table_cell_node_count": table_cell_count,
        "table_cell_nodes_with_community_count": table_cell_nodes_with_community_count,
        "has_nomenclature_edges_preserved": source_summary.get("has_nomenclature_edges_preserved", source_summary.get("nomenclature_edges_preserved", 0)),
        "has_context_v2_edges_preserved": source_summary.get("has_context_v2_edges_preserved", source_summary.get("context_v2_edges_preserved", 0)),
        "confirmed_blank_pages_preserve_source_trace_count": source_summary.get("confirmed_blank_pages_preserve_source_trace_count", 0),
        "orphan_edge_count": orphan_edges,
        "source_truth_mutation_allowed_count": scounts["source_truth_mutation_allowed_count"],
        "direct_answer_allowed_count": scounts["direct_answer_allowed_count"],
        "claim_proof_allowed_count": scounts["claim_proof_allowed_count"],
        "retrieval_only_answer_allowed_count": scounts["retrieval_only_answer_allowed_count"],
        "can_mutate_source_truth": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "authority": "community_retrieval_and_review_only",
    }
    quality = build_quality(summary)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "LEIDEN_GRAPH_COMMUNITIES_BUILT",
        "quality_status": quality["status"],
        "created_at": now_iso(),
        "summary": summary,
        "quality": quality,
        "communities": communities,
        "node_membership": node_membership,
        "community_edges": community_edges,
        "source_report_summary": source_summary,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    s = report["summary"]
    lines = [
        "# TRACE-Net Leiden Graph Communities v1",
        "",
        f"**Status:** {report.get('status')}",
        f"**Quality:** {report.get('quality_status')}",
        f"**Algorithm used:** {s.get('community_algorithm_used')}",
        f"**Leiden used:** {s.get('leiden_used')}",
        "",
        "## Summary",
        "",
        f"- Nodes: {s.get('node_count')}",
        f"- Edges: {s.get('edge_count')}",
        f"- Community graph edges: {s.get('community_graph_edge_count')}",
        f"- Communities: {s.get('community_count')}",
        f"- Page nodes with community: {s.get('page_nodes_with_community_count')}",
        f"- PartCandidate nodes with community: {s.get('part_candidate_nodes_with_community_count')}",
        f"- TableCell nodes with community: {s.get('table_cell_nodes_with_community_count')}",
        f"- Orphan edges: {s.get('orphan_edge_count')}",
        f"- Source truth mutations allowed: {s.get('source_truth_mutation_allowed_count')}",
        "",
        "## Top communities",
        "",
    ]
    for comm in report.get("communities", [])[:25]:
        lines.append(f"- **{comm['community_id']}**: {comm['label']} — {comm['node_count']} nodes, {comm['page_count']} pages")
    lines.extend([
        "",
        "## Safety note",
        "",
        "Communities are retrieval/review helpers only. They do not prove claims, answer directly, or mutate source truth.",
    ])
    return "\n".join(lines) + "\n"


def render_html(markdown_text: str) -> str:
    escaped = html.escape(markdown_text)
    return f"<!doctype html><html><head><meta charset='utf-8'><title>TRACE-Net Leiden Communities</title></head><body><pre>{escaped}</pre></body></html>"


def write_outputs(report: dict[str, Any], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "trace_net_leiden_graph_communities_v1.json"
    communities_path = output_dir / "trace_net_leiden_graph_communities_v1_communities.jsonl"
    membership_path = output_dir / "trace_net_leiden_graph_communities_v1_node_membership.jsonl"
    edges_path = output_dir / "trace_net_leiden_graph_communities_v1_edges.jsonl"
    summary_path = output_dir / "trace_net_leiden_graph_communities_v1_summary.json"
    manifest_path = output_dir / "trace_net_leiden_graph_communities_v1_manifest.json"
    quality_path = output_dir / "trace_net_leiden_graph_communities_v1_quality.json"
    md_path = output_dir / "trace_net_leiden_graph_communities_v1.md"
    html_path = output_dir / "trace_net_leiden_graph_communities_v1.html"

    write_json(report_path, report)
    write_jsonl(communities_path, report["communities"])
    write_jsonl(membership_path, report["node_membership"])
    write_jsonl(edges_path, report["community_edges"])
    write_json(summary_path, report["summary"])
    write_json(quality_path, report["quality"])
    md = render_markdown(report)
    md_path.write_text(md, encoding="utf-8")
    html_path.write_text(render_html(md), encoding="utf-8")
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "created_at": now_iso(),
        "report_path": str(report_path),
        "communities_path": str(communities_path),
        "membership_path": str(membership_path),
        "edges_path": str(edges_path),
        "summary_path": str(summary_path),
        "quality_path": str(quality_path),
        "markdown_path": str(md_path),
        "html_path": str(html_path),
        "quality_status": report.get("quality_status"),
    }
    write_json(manifest_path, manifest)
    return {
        "report_path": str(report_path),
        "communities_path": str(communities_path),
        "membership_path": str(membership_path),
        "edges_path": str(edges_path),
        "summary_path": str(summary_path),
        "manifest_path": str(manifest_path),
        "quality_path": str(quality_path),
        "markdown_path": str(md_path),
        "html_path": str(html_path),
    }


def build_leiden_graph_communities(
    graph_overlay_part_normalizer_path: str | Path,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    algorithm: str = "auto",
    resolution: float = 1.0,
    quality_args: argparse.Namespace | None = None,
) -> dict[str, Any]:
    source_report = read_json(graph_overlay_part_normalizer_path)
    report = build_report(source_report, algorithm=algorithm, resolution=resolution)
    if quality_args is not None:
        report["quality"] = build_quality(report["summary"], quality_args)
        report["quality_status"] = report["quality"]["status"]
    paths = write_outputs(report, Path(output_dir))
    report.update(paths)
    write_json(paths["report_path"], report)
    return report


def add_quality_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--require-page-count", type=int, default=None)
    parser.add_argument("--min-communities", type=int, default=1)
    parser.add_argument("--min-nodes", type=int, default=1)
    parser.add_argument("--min-edges", type=int, default=1)
    parser.add_argument("--min-page-nodes-with-community", type=int, default=1)
    parser.add_argument("--min-part-candidate-nodes-with-community", type=int, default=0)
    parser.add_argument("--min-table-cell-nodes-with-community", type=int, default=0)
    parser.add_argument("--min-nomenclature-edges-preserved", type=int, default=0)
    parser.add_argument("--min-context-v2-edges-preserved", type=int, default=0)
    parser.add_argument("--min-confirmed-blank-preserve-source-trace", type=int, default=0)
    parser.add_argument("--require-source-overlay-quality-pass", action="store_true")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Leiden graph communities v1.")
    parser.add_argument("--graph-overlay-part-normalizer", required=True)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--algorithm", choices=["auto", "leiden", "connected-components"], default="auto")
    parser.add_argument("--resolution", type=float, default=1.0)
    parser.add_argument("--quality", action="store_true")
    add_quality_args(parser)
    args = parser.parse_args(argv)

    report = build_leiden_graph_communities(
        graph_overlay_part_normalizer_path=args.graph_overlay_part_normalizer,
        output_dir=args.output_dir,
        algorithm=args.algorithm,
        resolution=args.resolution,
        quality_args=args if args.quality else None,
    )
    s = report["summary"]
    print("TRACE-Net Leiden graph communities v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    print(f" algorithm_used: {s['community_algorithm_used']}")
    print(f" leiden_used: {s['leiden_used']}")
    print(f" page_count: {s['page_count']}")
    print(f" node_count: {s['node_count']}")
    print(f" edge_count: {s['edge_count']}")
    print(f" community_count: {s['community_count']}")
    print(f" page_nodes_with_community_count: {s['page_nodes_with_community_count']}")
    print(f" part_candidate_nodes_with_community_count: {s['part_candidate_nodes_with_community_count']}")
    print(f" table_cell_nodes_with_community_count: {s['table_cell_nodes_with_community_count']}")
    print(f" orphan_edge_count: {s['orphan_edge_count']}")
    print(f" source_truth_mutation_allowed_count: {s['source_truth_mutation_allowed_count']}")
    print(f" report_path: {report['report_path']}")
    print(f" quality_path: {report['quality_path']}")
    return 0 if report["quality_status"] == "PASS" else 1


def quality_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Leiden graph communities v1 quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    add_quality_args(parser)
    args = parser.parse_args(argv)
    report = read_json(args.report_path)
    quality = build_quality(report.get("summary", {}), args)
    if args.write_json:
        qpath = Path(args.report_path).with_name("trace_net_leiden_graph_communities_v1_quality.json")
        write_json(qpath, quality)
        report["quality"] = quality
        report["quality_status"] = quality["status"]
        write_json(args.report_path, report)
    s = report.get("summary", {})
    print("TRACE-Net Leiden graph communities v1 quality")
    print(f" Status: {quality['status']}")
    print(f" community_count: {s.get('community_count')}")
    print(f" page_nodes_with_community_count: {s.get('page_nodes_with_community_count')}")
    print(f" part_candidate_nodes_with_community_count: {s.get('part_candidate_nodes_with_community_count')}")
    print(f" table_cell_nodes_with_community_count: {s.get('table_cell_nodes_with_community_count')}")
    print(f" orphan_edge_count: {s.get('orphan_edge_count')}")
    print(f" source_truth_mutation_allowed_count: {s.get('source_truth_mutation_allowed_count')}")
    return 0 if quality["status"] == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
