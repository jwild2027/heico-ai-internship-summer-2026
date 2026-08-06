"""TRACE-Net Leiden/community overlay.

This module builds a projected semantic graph from the existing page/trait/table
artifacts and runs community detection over that projection. It is intentionally
an overlay: it does not mutate the source/evidence graph.

If python-igraph + leidenalg are installed, the real Leiden algorithm is used.
Otherwise the module falls back to deterministic connected-component/community
heuristics so the planning/quality pipeline can still run in development.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable
import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone

DEFAULT_EXPORT_DIR = Path("local_data/organization/export")
DEFAULT_ENTITY_TRAIT_DIR = Path("local_data/organization/entity_traits")
DEFAULT_TRUST_TRAIT_DIR = Path("local_data/organization/trust_traits")
DEFAULT_TABLE_DIR = Path("local_data/organization/table_extraction")
DEFAULT_TRACE_NET_DIR = Path("local_data/organization/trace_net")
DEFAULT_OUTPUT_DIR = Path("local_data/organization/communities")

PAGE_PREFIX = "page:"
TRAIT_PREFIX = "trait:"
PART_PREFIX = "part:"
ATA_PREFIX = "ata:"
DOC_PREFIX = "document:"
ROUTE_PREFIX = "route:"
ROLE_PREFIX = "role:"
IMAGE_CLASS_PREFIX = "image_class:"
TRUST_PREFIX = "trust:"
TABLE_PREFIX = "table:"

STOP_TRAIT_FRAGMENTS = {
    "source",
    "has_source",
    "has_tiff",
    "has_ocr",
    "source_traceability",
    "answer_ready_page",
}


@dataclass(frozen=True)
class LeidenPaths:
    export_dir: Path = DEFAULT_EXPORT_DIR
    entity_trait_dir: Path = DEFAULT_ENTITY_TRAIT_DIR
    trust_trait_dir: Path = DEFAULT_TRUST_TRAIT_DIR
    table_dir: Path = DEFAULT_TABLE_DIR
    trace_net_dir: Path = DEFAULT_TRACE_NET_DIR
    output_dir: Path = DEFAULT_OUTPUT_DIR

    @property
    def page_index_path(self) -> Path:
        return self.export_dir / "page_index.json"

    @property
    def part_tree_path(self) -> Path:
        return self.export_dir / "part_tree.json"

    @property
    def page_cards_path(self) -> Path:
        return self.entity_trait_dir / "page_character_cards.json"

    @property
    def part_cards_path(self) -> Path:
        return self.entity_trait_dir / "part_character_cards.json"

    @property
    def trust_assertions_path(self) -> Path:
        return self.trust_trait_dir / "trust_trait_assertions.jsonl"

    @property
    def table_candidate_path(self) -> Path:
        return self.table_dir / "all_page_scan" / "table_candidate_plan.jsonl"

    @property
    def table_tile_plan_path(self) -> Path:
        return self.table_dir / "table_tile_plan.jsonl"

    @property
    def repair_plan_path(self) -> Path:
        return self.trace_net_dir / "trace_net_repair_plan.jsonl"

    @property
    def projection_nodes_path(self) -> Path:
        return self.output_dir / "semantic_projection_nodes.json"

    @property
    def projection_edges_path(self) -> Path:
        return self.output_dir / "semantic_projection_edges.json"

    @property
    def communities_path(self) -> Path:
        return self.output_dir / "leiden_communities.json"

    @property
    def communities_jsonl_path(self) -> Path:
        return self.output_dir / "leiden_communities.jsonl"

    @property
    def graph_nodes_path(self) -> Path:
        return self.output_dir / "leiden_graph_nodes.json"

    @property
    def graph_edges_path(self) -> Path:
        return self.output_dir / "leiden_graph_edges.json"

    @property
    def summary_path(self) -> Path:
        return self.output_dir / "leiden_community_summary.json"

    @property
    def review_md_path(self) -> Path:
        return self.output_dir / "leiden_community_review.md"


@dataclass
class CommunityOptions:
    algorithm: str = "auto"  # auto|leiden|greedy|components
    resolution: float = 1.0
    min_edge_weight: float = 0.0
    include_table_edges: bool = True
    include_trust_edges: bool = True
    include_part_edges: bool = True
    include_role_edges: bool = True
    include_ata_edges: bool = True
    max_sample_pages: int = 12
    seed: int = 42


@dataclass
class ProjectionGraph:
    nodes: dict[str, dict[str, Any]]
    edges: dict[tuple[str, str], dict[str, Any]]

    def add_node(self, node_id: str, node_type: str, **props: Any) -> None:
        current = self.nodes.setdefault(node_id, {"id": node_id, "type": node_type})
        current.update({k: v for k, v in props.items() if v is not None})

    def add_edge(self, source: str, target: str, edge_type: str, weight: float = 1.0, **props: Any) -> None:
        if not source or not target or source == target:
            return
        a, b = sorted((source, target))
        key = (a, b)
        edge = self.edges.setdefault(
            key,
            {"source": a, "target": b, "type": edge_type, "weight": 0.0, "edge_types": []},
        )
        edge["weight"] = round(float(edge.get("weight", 0.0)) + float(weight), 6)
        if edge_type not in edge["edge_types"]:
            edge["edge_types"].append(edge_type)
        for k, v in props.items():
            if v is not None:
                edge[k] = v


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                rows.append(obj)
        except Exception:
            continue
    return rows


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _slug(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_.:-]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "unknown"


def _normalize_page_id(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    if text.startswith(PAGE_PREFIX):
        return text[len(PAGE_PREFIX):]
    return text


def _node_page(page_id: str) -> str:
    return f"{PAGE_PREFIX}{page_id}"


def _node_trait(name: str) -> str:
    if name.startswith(TRAIT_PREFIX):
        return name
    return f"{TRAIT_PREFIX}{_slug(name)}"


def _get_field(obj: dict[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in obj and obj[name] not in (None, ""):
            return obj[name]
    return default


def _iter_page_cards(path: Path) -> list[dict[str, Any]]:
    data = _read_json(path, [])
    if isinstance(data, dict):
        for key in ("page_cards", "pages", "records", "items"):
            if isinstance(data.get(key), list):
                return [x for x in data[key] if isinstance(x, dict)]
        # Maybe dict keyed by page id.
        if all(isinstance(v, dict) for v in data.values()):
            out = []
            for k, v in data.items():
                row = dict(v)
                row.setdefault("page_id", k)
                out.append(row)
            return out
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    return []


def _iter_page_index(path: Path) -> list[dict[str, Any]]:
    data = _read_json(path, [])
    if isinstance(data, dict):
        for key in ("pages", "records", "page_index", "items"):
            if isinstance(data.get(key), list):
                return [x for x in data[key] if isinstance(x, dict)]
        if all(isinstance(v, dict) for v in data.values()):
            out = []
            for k, v in data.items():
                row = dict(v)
                row.setdefault("page_id", k)
                out.append(row)
            return out
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    return []


def _parts_from_page_card(card: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    for key in ("parts", "part_numbers", "part_mentions", "highlighted_parts"):
        for item in _as_list(card.get(key)):
            if isinstance(item, dict):
                value = _get_field(item, "part_number", "part_number_display", "display", "id")
            else:
                value = item
            if value:
                candidates.append(str(value).strip())
    return sorted(set(candidates))


def _traits_from_card(card: dict[str, Any]) -> list[str]:
    traits: list[str] = []
    for key in ("traits", "direct_traits", "derived_traits", "review_traits", "trust_traits"):
        for item in _as_list(card.get(key)):
            if isinstance(item, dict):
                t = _get_field(item, "trait_id", "id", "trait", "name", "value")
            else:
                t = item
            if t:
                traits.append(str(t))
    return sorted(set(traits))


def _is_low_value_trait(trait: str) -> bool:
    s = trait.lower()
    return any(fragment in s for fragment in STOP_TRAIT_FRAGMENTS)


def _merge_page_sources(paths: LeidenPaths) -> dict[str, dict[str, Any]]:
    pages: dict[str, dict[str, Any]] = {}

    for row in _iter_page_index(paths.page_index_path):
        page_id = _normalize_page_id(_get_field(row, "page_id", "id", "node_id", "page"))
        if not page_id:
            continue
        pages.setdefault(page_id, {}).update(row)
        pages[page_id]["page_id"] = page_id

    for card in _iter_page_cards(paths.page_cards_path):
        page_id = _normalize_page_id(_get_field(card, "page_id", "id", "node_id", "page"))
        if not page_id:
            continue
        merged = pages.setdefault(page_id, {})
        merged.update(card)
        merged["page_id"] = page_id

    # Attach table candidate routes.
    for row in _read_jsonl(paths.table_candidate_path):
        page_id = _normalize_page_id(_get_field(row, "page_id", "page", "id"))
        if not page_id:
            continue
        merged = pages.setdefault(page_id, {"page_id": page_id})
        merged["table_candidate_route"] = _get_field(row, "route", "repair_route")
        merged["table_candidate_status"] = _get_field(row, "status")
        merged["table_candidate_score"] = _get_field(row, "score", "table_score", "layout_score")

    # Attach table tile routes/status.
    for row in _read_jsonl(paths.table_tile_plan_path):
        page_id = _normalize_page_id(_get_field(row, "page_id", "page", "id"))
        if not page_id:
            continue
        merged = pages.setdefault(page_id, {"page_id": page_id})
        merged["table_tile_status"] = _get_field(row, "status")
        merged["table_tile_route"] = _get_field(row, "route", "repair_route")
        merged["table_tile_count"] = _get_field(row, "tile_count", "tiles", default=0)

    # Attach repair routes for 25-page pilot or other plans.
    for row in _read_jsonl(paths.repair_plan_path):
        page_id = _normalize_page_id(_get_field(row, "page_id", "page", "id"))
        if not page_id:
            continue
        merged = pages.setdefault(page_id, {"page_id": page_id})
        merged["trace_net_repair_route"] = _get_field(row, "repair_route", "route")
        merged["trace_net_repair_action"] = _get_field(row, "repair_action", "action")

    return pages


def _trust_assertions_by_page(path: Path) -> dict[str, list[dict[str, Any]]]:
    by_page: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in _read_jsonl(path):
        entity_id = str(_get_field(row, "entity_id", "subject", "page_id", default=""))
        page_id = _normalize_page_id(entity_id)
        if not page_id and entity_id.startswith("visual_text:"):
            page_id = entity_id.split(":", 1)[1]
        if page_id:
            by_page[page_id].append(row)
    return by_page


def build_semantic_projection(paths: LeidenPaths, options: CommunityOptions) -> tuple[ProjectionGraph, dict[str, Any]]:
    pages = _merge_page_sources(paths)
    trust_by_page = _trust_assertions_by_page(paths.trust_assertions_path) if options.include_trust_edges else {}
    graph = ProjectionGraph(nodes={}, edges={})

    for page_id, card in sorted(pages.items()):
        pnode = _node_page(page_id)
        page_role = _get_field(card, "role", "page_role", "context_role")
        image_class = _get_field(card, "image_class", "image_classification", "visual_class")
        ata = _get_field(card, "ata_code", "ata", "ata_section")
        document = _get_field(card, "document_id", "manual_id", "document", "manual")
        graph.add_node(
            pnode,
            "page",
            page_id=page_id,
            page_role=page_role,
            image_class=image_class,
            ata_code=ata,
            document_id=document,
        )

        if options.include_ata_edges and ata:
            anode = f"{ATA_PREFIX}{_slug(ata)}"
            graph.add_node(anode, "ata_section", ata_code=str(ata))
            graph.add_edge(pnode, anode, "PAGE_ATA", 1.0)
        if document:
            dnode = f"{DOC_PREFIX}{_slug(document)}"
            graph.add_node(dnode, "document", document_id=str(document))
            graph.add_edge(pnode, dnode, "PAGE_DOCUMENT", 0.25)

        if options.include_role_edges and page_role:
            rnode = f"{ROLE_PREFIX}{_slug(page_role)}"
            graph.add_node(rnode, "page_role", role=str(page_role))
            graph.add_edge(pnode, rnode, "PAGE_ROLE", 0.8)
        if image_class:
            inode = f"{IMAGE_CLASS_PREFIX}{_slug(image_class)}"
            graph.add_node(inode, "image_class", image_class=str(image_class))
            graph.add_edge(pnode, inode, "PAGE_IMAGE_CLASS", 0.7)

        if options.include_part_edges:
            for part in _parts_from_page_card(card):
                part_node = f"{PART_PREFIX}{_slug(part)}"
                graph.add_node(part_node, "part", part_number=part)
                graph.add_edge(pnode, part_node, "PAGE_PART", 2.0)

        for trait in _traits_from_card(card):
            if _is_low_value_trait(trait):
                continue
            tnode = _node_trait(trait)
            graph.add_node(tnode, "trait", trait_id=str(trait))
            graph.add_edge(pnode, tnode, "PAGE_TRAIT", 0.9)

        if options.include_trust_edges:
            for assertion in trust_by_page.get(page_id, []):
                trait = _get_field(assertion, "trait_id", "trait", "trait_value", "asserts_trait")
                scope = _get_field(assertion, "scope")
                if not trait:
                    continue
                trait_text = str(trait)
                if "exclude_visual_text" in trait_text or "include_visual_text" in trait_text:
                    # RAG gate edges are important for QA but too global for clustering.
                    continue
                tnode = _node_trait(trait_text)
                graph.add_node(tnode, "trust_or_review_trait", trait_id=trait_text, scope=scope)
                graph.add_edge(pnode, tnode, "PAGE_TRUST_REVIEW_TRAIT", 0.6)

        if options.include_table_edges:
            for route_key in ("table_candidate_route", "table_tile_route", "trace_net_repair_route"):
                route = card.get(route_key)
                if not route:
                    continue
                rnode = f"{ROUTE_PREFIX}{_slug(route)}"
                graph.add_node(rnode, "trace_net_route", route=str(route))
                graph.add_edge(pnode, rnode, "PAGE_ROUTE", 0.75)
            if card.get("table_tile_status") == "ok":
                tnode = f"{TABLE_PREFIX}tiles_created"
                graph.add_node(tnode, "table_trait", trait_id="table:tiles_created")
                graph.add_edge(pnode, tnode, "PAGE_TABLE_TRAIT", 1.0)

    # Part co-occurrence edges through pages.
    if options.include_part_edges:
        for page_id, card in pages.items():
            parts = _parts_from_page_card(card)
            if len(parts) < 2 or len(parts) > 80:
                continue
            nodes = [f"{PART_PREFIX}{_slug(p)}" for p in parts]
            # Keep bounded; dense part-list pages can explode.
            for i, a in enumerate(nodes[:30]):
                for b in nodes[i + 1 : min(i + 8, len(nodes))]:
                    graph.add_edge(a, b, "PART_CO_OCCURS_ON_PAGE", 0.1, page_id=page_id)

    if options.min_edge_weight > 0:
        graph.edges = {k: v for k, v in graph.edges.items() if float(v.get("weight", 0.0)) >= options.min_edge_weight}

    stats = {
        "pages_loaded": len(pages),
        "projection_nodes": len(graph.nodes),
        "projection_edges": len(graph.edges),
        "node_type_counts": dict(Counter(n.get("type", "unknown") for n in graph.nodes.values())),
        "edge_type_counts": dict(Counter(e.get("type", "unknown") for e in graph.edges.values())),
    }
    return graph, stats


def _connected_components(graph: ProjectionGraph) -> dict[str, int]:
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in graph.edges.values():
        s = edge["source"]
        t = edge["target"]
        adjacency[s].add(t)
        adjacency[t].add(s)
    partition: dict[str, int] = {}
    community = 0
    for node in graph.nodes:
        if node in partition:
            continue
        queue = deque([node])
        partition[node] = community
        while queue:
            cur = queue.popleft()
            for nxt in adjacency.get(cur, ()):
                if nxt not in partition:
                    partition[nxt] = community
                    queue.append(nxt)
        community += 1
    return partition


def _greedy_modularity_partition(graph: ProjectionGraph) -> tuple[dict[str, int], str]:
    try:
        import networkx as nx  # type: ignore
        from networkx.algorithms.community import greedy_modularity_communities  # type: ignore
    except Exception:
        return _connected_components(graph), "connected_components_fallback"

    g = nx.Graph()
    for node_id, node in graph.nodes.items():
        g.add_node(node_id, **node)
    for edge in graph.edges.values():
        g.add_edge(edge["source"], edge["target"], weight=float(edge.get("weight", 1.0)))
    if g.number_of_edges() == 0:
        return {n: i for i, n in enumerate(g.nodes())}, "singleton_no_edges"
    communities = list(greedy_modularity_communities(g, weight="weight"))
    partition = {}
    for idx, nodes in enumerate(communities):
        for node in nodes:
            partition[node] = idx
    return partition, "networkx_greedy_modularity"


def _leiden_partition(graph: ProjectionGraph, options: CommunityOptions) -> tuple[dict[str, int], str, dict[str, Any]]:
    try:
        import igraph as ig  # type: ignore
        import leidenalg  # type: ignore
    except Exception as exc:
        if options.algorithm == "leiden":
            raise RuntimeError(
                "Leiden requested but python-igraph/leidenalg are not installed. "
                "Install with: pip install igraph leidenalg"
            ) from exc
        partition, name = _greedy_modularity_partition(graph)
        return partition, name, {"leiden_available": False, "fallback_reason": str(exc)}

    node_ids = list(graph.nodes.keys())
    index = {node_id: i for i, node_id in enumerate(node_ids)}
    edges = []
    weights = []
    for edge in graph.edges.values():
        s = index.get(edge["source"])
        t = index.get(edge["target"])
        if s is None or t is None or s == t:
            continue
        edges.append((s, t))
        weights.append(float(edge.get("weight", 1.0)))
    g = ig.Graph(n=len(node_ids), edges=edges, directed=False)
    g.vs["name"] = node_ids
    if weights:
        g.es["weight"] = weights
    if not edges:
        return {node_id: i for i, node_id in enumerate(node_ids)}, "singleton_no_edges", {"leiden_available": True}

    kwargs: dict[str, Any] = {"weights": weights if weights else None, "seed": options.seed}
    if options.resolution and options.resolution > 0:
        kwargs["resolution_parameter"] = float(options.resolution)
    try:
        partition = leidenalg.find_partition(g, leidenalg.RBConfigurationVertexPartition, **kwargs)
    except TypeError:
        # Some leidenalg versions dislike seed or resolution kwargs.
        kwargs.pop("seed", None)
        partition = leidenalg.find_partition(g, leidenalg.RBConfigurationVertexPartition, **kwargs)
    out = {}
    for idx, community_id in enumerate(partition.membership):
        out[node_ids[idx]] = int(community_id)
    return out, "leidenalg_rbconfiguration", {
        "leiden_available": True,
        "modularity": getattr(partition, "modularity", None),
        "quality": getattr(partition, "quality", lambda: None)(),
    }


def detect_communities(graph: ProjectionGraph, options: CommunityOptions) -> tuple[dict[str, int], str, dict[str, Any]]:
    alg = options.algorithm.lower().strip()
    if alg in ("auto", "leiden"):
        return _leiden_partition(graph, options)
    if alg in ("greedy", "greedy_modularity"):
        partition, name = _greedy_modularity_partition(graph)
        return partition, name, {"leiden_available": False}
    if alg in ("components", "connected_components"):
        return _connected_components(graph), "connected_components", {"leiden_available": False}
    raise ValueError(f"Unknown community algorithm: {options.algorithm}")


def _community_label(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> str:
    page_roles = Counter(str(n.get("page_role")) for n in nodes if n.get("type") == "page" and n.get("page_role"))
    image_classes = Counter(str(n.get("image_class")) for n in nodes if n.get("type") == "page" and n.get("image_class"))
    node_types = Counter(str(n.get("type")) for n in nodes)
    routes = Counter(n.get("route") for n in nodes if n.get("type") == "trace_net_route" and n.get("route"))
    ata_codes = Counter(str(n.get("ata_code")) for n in nodes if n.get("ata_code"))
    parts = [str(n.get("part_number")) for n in nodes if n.get("type") == "part" and n.get("part_number")]

    bits = []
    if page_roles:
        bits.append(page_roles.most_common(1)[0][0])
    if routes:
        route = routes.most_common(1)[0][0]
        route = str(route).replace("table_crop_tile_repair_route_", "table_")
        bits.append(route)
    if image_classes:
        bits.append(image_classes.most_common(1)[0][0])
    if ata_codes:
        bits.append(f"ATA {ata_codes.most_common(1)[0][0]}")
    if not bits and node_types:
        bits.append(node_types.most_common(1)[0][0])
    label = " / ".join(bits[:4]) or "community"
    if parts:
        label += f" / {len(parts)} parts"
    return label


def _summarize_communities(graph: ProjectionGraph, partition: dict[str, int], options: CommunityOptions) -> list[dict[str, Any]]:
    by_comm: dict[int, list[str]] = defaultdict(list)
    for node_id, comm_id in partition.items():
        by_comm[int(comm_id)].append(node_id)
    edge_by_comm: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for edge in graph.edges.values():
        cs = partition.get(edge["source"])
        ct = partition.get(edge["target"])
        if cs is not None and cs == ct:
            edge_by_comm[int(cs)].append(edge)

    communities = []
    for comm_id, node_ids in sorted(by_comm.items(), key=lambda item: (-len(item[1]), item[0])):
        nodes = [graph.nodes[n] for n in node_ids if n in graph.nodes]
        edges = edge_by_comm.get(comm_id, [])
        pages = [n for n in nodes if n.get("type") == "page"]
        parts = [n for n in nodes if n.get("type") == "part"]
        traits = [n for n in nodes if "trait" in str(n.get("type", ""))]
        routes = [n for n in nodes if n.get("type") == "trace_net_route"]
        page_ids = [str(n.get("page_id")) for n in pages if n.get("page_id")]
        page_role_counts = Counter(str(n.get("page_role")) for n in pages if n.get("page_role"))
        image_class_counts = Counter(str(n.get("image_class")) for n in pages if n.get("image_class"))
        route_counts = Counter(str(n.get("route")) for n in routes if n.get("route"))
        part_numbers = [str(n.get("part_number")) for n in parts if n.get("part_number")]
        communities.append(
            {
                "community_id": comm_id,
                "label": _community_label(nodes, edges),
                "node_count": len(nodes),
                "edge_count": len(edges),
                "page_count": len(page_ids),
                "part_count": len(part_numbers),
                "trait_count": len(traits),
                "route_count": len(routes),
                "page_role_counts": dict(page_role_counts),
                "image_class_counts": dict(image_class_counts),
                "route_counts": dict(route_counts),
                "sample_pages": page_ids[: options.max_sample_pages],
                "sample_parts": part_numbers[: options.max_sample_pages],
                "node_type_counts": dict(Counter(str(n.get("type")) for n in nodes)),
            }
        )
    return communities


def _make_overlay_graph(communities: list[dict[str, Any]], graph: ProjectionGraph, partition: dict[str, int]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for community in communities:
        cid = community["community_id"]
        cnode = f"community:{cid}"
        nodes.append({"id": cnode, "type": "leiden_community", **community})
    for node_id, comm_id in partition.items():
        node = graph.nodes.get(node_id, {"id": node_id, "type": "unknown"})
        nodes.append(node)
        edges.append(
            {
                "source": node_id,
                "target": f"community:{comm_id}",
                "type": "IN_LEIDEN_COMMUNITY",
                "community_id": int(comm_id),
            }
        )
    return nodes, edges


def build_leiden_community_overlay(paths: LeidenPaths, options: CommunityOptions) -> dict[str, Any]:
    graph, projection_stats = build_semantic_projection(paths, options)
    partition, algorithm_used, algorithm_info = detect_communities(graph, options)
    communities = _summarize_communities(graph, partition, options)
    overlay_nodes, overlay_edges = _make_overlay_graph(communities, graph, partition)

    status = "OK" if communities else "FAIL"
    summary = {
        "status": status,
        "created_at": _utc_now(),
        "requested_algorithm": options.algorithm,
        "algorithm_used": algorithm_used,
        "resolution": options.resolution,
        "min_edge_weight": options.min_edge_weight,
        "leiden_available": bool(algorithm_info.get("leiden_available")),
        "algorithm_info": algorithm_info,
        **projection_stats,
        "community_count": len(communities),
        "communities_with_pages": sum(1 for c in communities if c.get("page_count", 0) > 0),
        "largest_community_pages": max((int(c.get("page_count", 0)) for c in communities), default=0),
        "largest_community_nodes": max((int(c.get("node_count", 0)) for c in communities), default=0),
        "singleton_communities": sum(1 for c in communities if int(c.get("node_count", 0)) == 1),
        "overlay_nodes": len(overlay_nodes),
        "overlay_edges": len(overlay_edges),
    }

    paths.output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(paths.projection_nodes_path, list(graph.nodes.values()))
    _write_json(paths.projection_edges_path, list(graph.edges.values()))
    _write_json(paths.communities_path, {"summary": summary, "communities": communities})
    _write_jsonl(paths.communities_jsonl_path, communities)
    _write_json(paths.graph_nodes_path, overlay_nodes)
    _write_json(paths.graph_edges_path, overlay_edges)
    _write_json(paths.summary_path, summary)
    paths.review_md_path.write_text(_render_review(summary, communities), encoding="utf-8")

    return {
        "status": status,
        "summary": summary,
        "communities": communities,
        "projection_nodes": list(graph.nodes.values()),
        "projection_edges": list(graph.edges.values()),
        "graph_nodes": overlay_nodes,
        "graph_edges": overlay_edges,
    }


def _render_review(summary: dict[str, Any], communities: list[dict[str, Any]]) -> str:
    lines = ["# TRACE-Net Leiden / Community Overlay", ""]
    lines.append("## Summary")
    for key in (
        "status",
        "algorithm_used",
        "leiden_available",
        "pages_loaded",
        "projection_nodes",
        "projection_edges",
        "community_count",
        "communities_with_pages",
        "largest_community_pages",
    ):
        lines.append(f"- **{key}**: {summary.get(key)}")
    lines.append("")
    lines.append("## Top communities")
    for community in communities[:25]:
        lines.append("")
        lines.append(f"### Community {community['community_id']}: {community['label']}")
        lines.append(f"- nodes: {community['node_count']}")
        lines.append(f"- pages: {community['page_count']}")
        lines.append(f"- parts: {community['part_count']}")
        if community.get("page_role_counts"):
            lines.append(f"- page roles: `{community['page_role_counts']}`")
        if community.get("image_class_counts"):
            lines.append(f"- image classes: `{community['image_class_counts']}`")
        if community.get("route_counts"):
            lines.append(f"- routes: `{community['route_counts']}`")
        if community.get("sample_pages"):
            lines.append("- sample pages: " + ", ".join(community["sample_pages"][:12]))
        if community.get("sample_parts"):
            lines.append("- sample parts: " + ", ".join(community["sample_parts"][:12]))
    lines.append("")
    return "\n".join(lines)


def _print_result(result: dict[str, Any], paths: LeidenPaths, samples: int) -> None:
    summary = result["summary"]
    print("TRACE-Net Leiden / community overlay")
    print(f"  Status: {summary['status']}")
    print(f"  Output dir: {paths.output_dir}")
    print("  Summary:")
    for key in (
        "requested_algorithm",
        "algorithm_used",
        "leiden_available",
        "pages_loaded",
        "projection_nodes",
        "projection_edges",
        "community_count",
        "communities_with_pages",
        "largest_community_pages",
        "singleton_communities",
    ):
        print(f"    {key}: {summary.get(key)}")
    print("  Top communities:")
    for community in result["communities"][:samples]:
        print(
            f"    {community['community_id']} | {community['label']} | "
            f"pages={community['page_count']} nodes={community['node_count']} parts={community['part_count']}"
        )
        if community.get("sample_pages"):
            print("      sample_pages: " + ", ".join(community["sample_pages"][:6]))
    print("Files written:")
    print(f"  summary: {paths.summary_path}")
    print(f"  communities: {paths.communities_path}")
    print(f"  communities_jsonl: {paths.communities_jsonl_path}")
    print(f"  projection_nodes: {paths.projection_nodes_path}")
    print(f"  projection_edges: {paths.projection_edges_path}")
    print(f"  graph_nodes: {paths.graph_nodes_path}")
    print(f"  graph_edges: {paths.graph_edges_path}")
    print(f"  review_md: {paths.review_md_path}")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Leiden/community overlay.")
    parser.add_argument("--export-dir", default=str(DEFAULT_EXPORT_DIR))
    parser.add_argument("--entity-trait-dir", default=str(DEFAULT_ENTITY_TRAIT_DIR))
    parser.add_argument("--trust-trait-dir", default=str(DEFAULT_TRUST_TRAIT_DIR))
    parser.add_argument("--table-dir", default=str(DEFAULT_TABLE_DIR))
    parser.add_argument("--trace-net-dir", default=str(DEFAULT_TRACE_NET_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--algorithm", choices=["auto", "leiden", "greedy", "components"], default="auto")
    parser.add_argument("--resolution", type=float, default=1.0)
    parser.add_argument("--min-edge-weight", type=float, default=0.0)
    parser.add_argument("--samples", type=int, default=12)
    parser.add_argument("--expect-pages", type=int, default=None)
    parser.add_argument("--no-table-edges", action="store_true")
    parser.add_argument("--no-trust-edges", action="store_true")
    parser.add_argument("--no-part-edges", action="store_true")
    parser.add_argument("--no-role-edges", action="store_true")
    parser.add_argument("--no-ata-edges", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    paths = LeidenPaths(
        export_dir=Path(args.export_dir),
        entity_trait_dir=Path(args.entity_trait_dir),
        trust_trait_dir=Path(args.trust_trait_dir),
        table_dir=Path(args.table_dir),
        trace_net_dir=Path(args.trace_net_dir),
        output_dir=Path(args.output_dir),
    )
    options = CommunityOptions(
        algorithm=args.algorithm,
        resolution=args.resolution,
        min_edge_weight=args.min_edge_weight,
        include_table_edges=not args.no_table_edges,
        include_trust_edges=not args.no_trust_edges,
        include_part_edges=not args.no_part_edges,
        include_role_edges=not args.no_role_edges,
        include_ata_edges=not args.no_ata_edges,
        max_sample_pages=args.samples,
    )
    try:
        result = build_leiden_community_overlay(paths, options)
    except Exception as exc:
        print(f"TRACE-Net Leiden/community overlay failed: {exc}", file=sys.stderr)
        return 1
    if args.expect_pages is not None and result["summary"].get("pages_loaded") != args.expect_pages:
        print(
            f"Expected {args.expect_pages} pages, found {result['summary'].get('pages_loaded')}",
            file=sys.stderr,
        )
        _print_result(result, paths, args.samples)
        return 1
    _print_result(result, paths, args.samples)
    return 0 if result["status"] == "OK" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
