"""TRACE-Net community ablation evaluation.

This module compares community/grouping strategies for the TRACE-Net semantic
projection without mutating the source graph.  It is intentionally artifact-based
so it can run against the local MVP outputs and in small unit-test fixtures.

The evaluator answers questions like:

* Is Leiden actually adding value over route grouping?
* Are communities coherent by page role, table route, trust tier, etc.?
* Are table/repair candidates concentrated enough to make batching useful?
* Are communities too broad or too fragmented?

It should be used as a measurement layer, not as a source-of-truth layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import argparse
import json
import math
from pathlib import Path
import re
from collections import Counter, defaultdict
from typing import Any, Iterable, Mapping, Sequence


PAGE_ID_RE = re.compile(r"p(\d{6})$")


@dataclass(frozen=True)
class CommunityAblationPaths:
    communities_dir: Path = Path("local_data/organization/communities")
    trace_net_dir: Path = Path("local_data/organization/trace_net")
    table_scan_dir: Path = Path("local_data/organization/table_extraction/all_page_scan")
    export_dir: Path = Path("local_data/organization/export")
    entity_trait_dir: Path = Path("local_data/organization/entity_traits")

    @property
    def projection_nodes_path(self) -> Path:
        return self.communities_dir / "semantic_projection_nodes.json"

    @property
    def projection_edges_path(self) -> Path:
        return self.communities_dir / "semantic_projection_edges.json"

    @property
    def repair_plan_path(self) -> Path:
        return self.trace_net_dir / "trace_net_repair_plan.jsonl"

    @property
    def table_candidate_plan_path(self) -> Path:
        return self.table_scan_dir / "table_candidate_plan.jsonl"

    @property
    def page_index_path(self) -> Path:
        return self.export_dir / "page_index.json"

    @property
    def page_cards_path(self) -> Path:
        return self.entity_trait_dir / "page_character_cards.json"

    @property
    def output_dir(self) -> Path:
        return self.communities_dir

    @property
    def eval_json_path(self) -> Path:
        return self.output_dir / "community_ablation_eval.json"

    @property
    def eval_md_path(self) -> Path:
        return self.output_dir / "community_ablation_eval.md"

    @property
    def quality_json_path(self) -> Path:
        return self.output_dir / "community_ablation_quality.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                records.append(obj)
        except json.JSONDecodeError:
            continue
    return records


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(dict(record), sort_keys=True) + "\n")


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        # Common artifact shapes sometimes store records under a top-level key.
        for key in ("records", "nodes", "edges", "pages", "items"):
            maybe = value.get(key)
            if isinstance(maybe, list):
                return maybe
    return []


def _node_id(node: Mapping[str, Any]) -> str:
    for key in ("id", "node_id", "uid", "name"):
        value = node.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _node_type(node: Mapping[str, Any]) -> str:
    for key in ("type", "node_type", "kind", "label"):
        value = node.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _edge_endpoints(edge: Mapping[str, Any]) -> tuple[str, str]:
    src = ""
    dst = ""
    for key in ("source", "src", "from", "source_id"):
        value = edge.get(key)
        if isinstance(value, str):
            src = value
            break
    for key in ("target", "dst", "to", "target_id"):
        value = edge.get(key)
        if isinstance(value, str):
            dst = value
            break
    return src, dst


def _extract_page_id(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    if value.startswith("page:"):
        return value.split(":", 1)[1]
    return value if "_p" in value or value.startswith("t_p_") else ""


def _page_sequence(page_id: str) -> int | None:
    m = PAGE_ID_RE.search(page_id)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def _find_first(record: Mapping[str, Any], keys: Sequence[str], default: Any = None) -> Any:
    for key in keys:
        if key in record and record[key] not in (None, ""):
            return record[key]
    return default


def _load_page_index(path: Path) -> dict[str, dict[str, Any]]:
    obj = _read_json(path, default={})
    page_map: dict[str, dict[str, Any]] = {}
    if isinstance(obj, dict):
        if all(isinstance(v, dict) for v in obj.values()):
            for key, value in obj.items():
                page_id = str(value.get("page_id") or value.get("id") or key)
                page_map[page_id] = dict(value)
        else:
            for key in ("pages", "records", "items"):
                if isinstance(obj.get(key), list):
                    for value in obj[key]:
                        if isinstance(value, dict):
                            page_id = str(value.get("page_id") or value.get("id") or "")
                            if page_id:
                                page_map[page_id] = dict(value)
    elif isinstance(obj, list):
        for value in obj:
            if isinstance(value, dict):
                page_id = str(value.get("page_id") or value.get("id") or "")
                if page_id:
                    page_map[page_id] = dict(value)
    return page_map


def _load_page_cards(path: Path) -> dict[str, dict[str, Any]]:
    obj = _read_json(path, default={})
    cards: dict[str, dict[str, Any]] = {}
    records = _as_list(obj)
    for rec in records:
        if not isinstance(rec, dict):
            continue
        page_id = str(rec.get("page_id") or rec.get("id") or rec.get("entity_id") or "")
        if page_id.startswith("page:"):
            page_id = page_id.split(":", 1)[1]
        if page_id:
            cards[page_id] = dict(rec)
    if isinstance(obj, dict) and not cards:
        for key, rec in obj.items():
            if isinstance(rec, dict):
                page_id = str(rec.get("page_id") or rec.get("id") or key)
                if page_id.startswith("page:"):
                    page_id = page_id.split(":", 1)[1]
                cards[page_id] = dict(rec)
    return cards


def _load_projection(paths: CommunityAblationPaths) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    nodes_raw = _as_list(_read_json(paths.projection_nodes_path, default=[]))
    edges_raw = _as_list(_read_json(paths.projection_edges_path, default=[]))
    nodes: dict[str, dict[str, Any]] = {}
    for node in nodes_raw:
        if not isinstance(node, dict):
            continue
        node_id = _node_id(node)
        if node_id:
            nodes[node_id] = dict(node)
    edges: list[dict[str, Any]] = []
    for edge in edges_raw:
        if not isinstance(edge, dict):
            continue
        src, dst = _edge_endpoints(edge)
        if src and dst:
            edges.append(dict(edge))
    return nodes, edges


def _load_page_metadata(paths: CommunityAblationPaths, projection_nodes: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    page_index = _load_page_index(paths.page_index_path)
    page_cards = _load_page_cards(paths.page_cards_path)
    repair_records = _read_jsonl(paths.repair_plan_path)
    table_records = _read_jsonl(paths.table_candidate_plan_path)

    pages: dict[str, dict[str, Any]] = {}

    def ensure(page_id: str) -> dict[str, Any]:
        if page_id not in pages:
            pages[page_id] = {
                "page_id": page_id,
                "page_sequence": _page_sequence(page_id),
                "page_role": "unknown",
                "image_class": "unknown",
                "ata_code": "unknown",
                "repair_route": "unknown",
                "repair_action": "unknown",
                "table_route": "unknown",
                "table_candidate_level": "none",
                "trust_tier": "unknown",
                "review_traits": [],
                "part_count": 0,
            }
        return pages[page_id]

    for node_id, node in projection_nodes.items():
        ntype = _node_type(node)
        page_id = ""
        if ntype == "page" or node_id.startswith("page:"):
            page_id = _extract_page_id(node_id) or str(node.get("page_id") or node.get("id") or "")
        if page_id:
            meta = ensure(page_id)
            meta["projection_node_id"] = node_id
            for key in ("page_role", "role", "image_class", "image_classification", "ata_code", "trust_tier"):
                if node.get(key):
                    out_key = "image_class" if key in ("image_classification",) else ("page_role" if key == "role" else key)
                    meta[out_key] = node.get(key)

    for page_id, rec in page_index.items():
        meta = ensure(page_id)
        meta["ata_code"] = _find_first(rec, ("ata_code", "ata", "ata_section"), meta.get("ata_code", "unknown"))
        meta["page_label"] = _find_first(rec, ("page_label", "label", "page_number"), meta.get("page_label"))
        meta["document_id"] = _find_first(rec, ("document_id", "manual_id", "manual"), meta.get("document_id"))
        meta["source_url"] = _find_first(rec, ("source_url", "url", "rescarta_url"), meta.get("source_url"))

    for page_id, rec in page_cards.items():
        meta = ensure(page_id)
        for key in ("page_role", "role", "image_class", "image_classification", "ata_code", "trust_tier"):
            value = _find_first(rec, (key,), None)
            if value:
                out_key = "image_class" if key == "image_classification" else ("page_role" if key == "role" else key)
                meta[out_key] = value
        roles = rec.get("roles")
        if isinstance(roles, dict):
            meta["page_role"] = roles.get("context_role") or roles.get("page_role") or meta.get("page_role", "unknown")
            img = roles.get("image_class") or roles.get("image_classes")
            if isinstance(img, list) and img:
                meta["image_class"] = str(img[0])
            elif isinstance(img, str) and img:
                meta["image_class"] = img
        traits = rec.get("traits")
        if isinstance(traits, list):
            meta["traits"] = traits

    for rec in repair_records:
        page_id = str(rec.get("page_id") or rec.get("page") or "")
        if not page_id:
            continue
        meta = ensure(page_id)
        meta["repair_route"] = _find_first(rec, ("repair_route", "route"), meta.get("repair_route", "unknown"))
        meta["repair_action"] = _find_first(rec, ("repair_action", "action"), meta.get("repair_action", "unknown"))
        meta["priority"] = _find_first(rec, ("priority",), meta.get("priority"))
        meta["trust_tier"] = _find_first(rec, ("trust_tier", "tier"), meta.get("trust_tier", "unknown"))
        traits = rec.get("review_traits") or rec.get("traits") or []
        if isinstance(traits, str):
            traits = [x.strip() for x in traits.split(",") if x.strip()]
        if isinstance(traits, list):
            meta["review_traits"] = sorted(set([str(x) for x in meta.get("review_traits", [])] + [str(x) for x in traits]))

    for rec in table_records:
        page_id = str(rec.get("page_id") or rec.get("page") or "")
        if not page_id:
            continue
        meta = ensure(page_id)
        meta["table_route"] = _find_first(rec, ("route", "repair_route", "table_route"), meta.get("table_route", "unknown"))
        meta["table_candidate_level"] = _find_first(rec, ("candidate_level", "table_candidate_level", "priority"), meta.get("table_candidate_level", "none"))
        if rec.get("status"):
            meta["table_candidate_status"] = rec.get("status")

    # Add part counts from projection edges.  This does not require knowing exact
    # edge type; a page-part adjacency in the projection is enough for metrics.
    return pages


def _page_nodes_from_projection(nodes: Mapping[str, Mapping[str, Any]]) -> list[str]:
    page_ids: list[str] = []
    for node_id, node in nodes.items():
        ntype = _node_type(node)
        if ntype == "page" or node_id.startswith("page:"):
            page_id = _extract_page_id(node_id) or str(node.get("page_id") or "")
            if page_id:
                page_ids.append(page_id)
    return sorted(set(page_ids))


def _build_adjacency(nodes: Mapping[str, Mapping[str, Any]], edges: Sequence[Mapping[str, Any]]) -> dict[str, set[str]]:
    adj: dict[str, set[str]] = {node_id: set() for node_id in nodes}
    for edge in edges:
        src, dst = _edge_endpoints(edge)
        if not src or not dst:
            continue
        if src not in adj:
            adj[src] = set()
        if dst not in adj:
            adj[dst] = set()
        adj[src].add(dst)
        adj[dst].add(src)
    return adj


def _count_page_parts(nodes: Mapping[str, Mapping[str, Any]], edges: Sequence[Mapping[str, Any]], page_meta: dict[str, dict[str, Any]]) -> None:
    for edge in edges:
        src, dst = _edge_endpoints(edge)
        if not src or not dst:
            continue
        src_page = _extract_page_id(src) if (src.startswith("page:") or _node_type(nodes.get(src, {})) == "page") else ""
        dst_page = _extract_page_id(dst) if (dst.startswith("page:") or _node_type(nodes.get(dst, {})) == "page") else ""
        src_type = _node_type(nodes.get(src, {}))
        dst_type = _node_type(nodes.get(dst, {}))
        if src_page and dst_type == "part":
            page_meta.setdefault(src_page, {"page_id": src_page})["part_count"] = int(page_meta.setdefault(src_page, {"page_id": src_page}).get("part_count", 0)) + 1
        if dst_page and src_type == "part":
            page_meta.setdefault(dst_page, {"page_id": dst_page})["part_count"] = int(page_meta.setdefault(dst_page, {"page_id": dst_page}).get("part_count", 0)) + 1


def _partition_no_community(page_ids: Sequence[str]) -> dict[str, list[str]]:
    return {f"page:{page_id}": [page_id] for page_id in page_ids}


def _route_key(meta: Mapping[str, Any]) -> str:
    route = str(meta.get("repair_route") or meta.get("table_route") or "unknown")
    if route == "unknown":
        route = str(meta.get("table_route") or "unknown")
    if route == "unknown":
        route = str(meta.get("page_role") or "unknown")
    trust = str(meta.get("trust_tier") or "unknown")
    role = str(meta.get("page_role") or "unknown")
    table_level = str(meta.get("table_candidate_level") or "none")
    return f"route={route}|table={table_level}|role={role}|trust={trust}"


def _partition_route_grouping(page_ids: Sequence[str], page_meta: Mapping[str, Mapping[str, Any]]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for page_id in page_ids:
        groups[_route_key(page_meta.get(page_id, {}))].append(page_id)
    return dict(groups)


def _networkx_graph(nodes: Mapping[str, Mapping[str, Any]], edges: Sequence[Mapping[str, Any]]):
    import networkx as nx  # type: ignore

    g = nx.Graph()
    for node_id in nodes:
        g.add_node(node_id)
    for edge in edges:
        src, dst = _edge_endpoints(edge)
        if src and dst:
            g.add_edge(src, dst)
    return g


def _partition_networkx_greedy(nodes: Mapping[str, Mapping[str, Any]], edges: Sequence[Mapping[str, Any]]) -> tuple[dict[str, list[str]], float | None]:
    import networkx as nx  # type: ignore
    from networkx.algorithms.community import greedy_modularity_communities, modularity  # type: ignore

    g = _networkx_graph(nodes, edges)
    communities = list(greedy_modularity_communities(g))
    partition: dict[str, list[str]] = {}
    node_to_pages = _node_to_page_map(nodes)
    for idx, comm in enumerate(communities):
        pages: list[str] = []
        for node_id in comm:
            pages.extend(node_to_pages.get(str(node_id), []))
        if pages:
            partition[f"greedy:{idx}"] = sorted(set(pages))
    mod: float | None = None
    try:
        mod = float(modularity(g, communities)) if communities else None
    except Exception:
        mod = None
    return partition, mod


def _node_to_page_map(nodes: Mapping[str, Mapping[str, Any]]) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for node_id, node in nodes.items():
        ntype = _node_type(node)
        if ntype == "page" or node_id.startswith("page:"):
            page_id = _extract_page_id(node_id) or str(node.get("page_id") or "")
            if page_id:
                mapping[node_id] = [page_id]
        else:
            mapping[node_id] = []
    return mapping


def _partition_leiden(nodes: Mapping[str, Mapping[str, Any]], edges: Sequence[Mapping[str, Any]], resolution: float = 1.0) -> tuple[dict[str, list[str]], float | None]:
    import igraph as ig  # type: ignore
    import leidenalg  # type: ignore

    node_ids = list(nodes.keys())
    idx = {node_id: i for i, node_id in enumerate(node_ids)}
    edge_pairs: list[tuple[int, int]] = []
    for edge in edges:
        src, dst = _edge_endpoints(edge)
        if src in idx and dst in idx:
            edge_pairs.append((idx[src], idx[dst]))
    g = ig.Graph(n=len(node_ids), edges=edge_pairs, directed=False)
    partition_obj = leidenalg.find_partition(
        g,
        leidenalg.RBConfigurationVertexPartition,
        resolution_parameter=resolution,
    )
    membership = list(partition_obj.membership)
    node_to_pages = _node_to_page_map(nodes)
    groups: dict[int, list[str]] = defaultdict(list)
    for node_id, comm_id in zip(node_ids, membership):
        groups[int(comm_id)].extend(node_to_pages.get(node_id, []))
    partition = {f"leiden:{comm_id}": sorted(set(pages)) for comm_id, pages in groups.items() if pages}
    quality: float | None = None
    try:
        quality = float(partition_obj.quality())
    except Exception:
        quality = None
    return partition, quality


def _entropy(counts: Sequence[int]) -> float:
    total = sum(counts)
    if total <= 0:
        return 0.0
    ent = 0.0
    for count in counts:
        if count <= 0:
            continue
        p = count / total
        ent -= p * math.log(p, 2)
    return round(ent, 6)


def _gini(values: Sequence[int]) -> float:
    vals = sorted([v for v in values if v >= 0])
    n = len(vals)
    if n == 0:
        return 0.0
    total = sum(vals)
    if total == 0:
        return 0.0
    cum = 0
    for i, val in enumerate(vals, start=1):
        cum += i * val
    return round((2 * cum) / (n * total) - (n + 1) / n, 6)


def _weighted_purity(groups: Mapping[str, Sequence[str]], page_meta: Mapping[str, Mapping[str, Any]], field: str) -> float:
    total_pages = 0
    weighted = 0.0
    for pages in groups.values():
        vals = [str(page_meta.get(page_id, {}).get(field, "unknown")) for page_id in pages]
        vals = [v for v in vals if v]
        if not vals:
            continue
        total_pages += len(vals)
        count = Counter(vals).most_common(1)[0][1]
        weighted += count
    if total_pages == 0:
        return 0.0
    return round(weighted / total_pages, 6)


def _weighted_trait_purity(groups: Mapping[str, Sequence[str]], page_meta: Mapping[str, Mapping[str, Any]], trait: str) -> float:
    # Binary trait purity: does a community contain mostly pages with/without a trait?
    total = 0
    score = 0
    for pages in groups.values():
        vals: list[bool] = []
        for page_id in pages:
            traits = page_meta.get(page_id, {}).get("review_traits", [])
            if isinstance(traits, list):
                vals.append(trait in traits)
        if not vals:
            continue
        total += len(vals)
        positives = sum(1 for v in vals if v)
        score += max(positives, len(vals) - positives)
    if total == 0:
        return 0.0
    return round(score / total, 6)


def _top_k_concentration(groups: Mapping[str, Sequence[str]], page_meta: Mapping[str, Mapping[str, Any]], predicate, k: int = 3) -> float:
    total_pos = 0
    group_pos: list[int] = []
    for pages in groups.values():
        c = 0
        for page_id in pages:
            if predicate(page_meta.get(page_id, {})):
                c += 1
        total_pos += c
        group_pos.append(c)
    if total_pos == 0:
        return 0.0
    return round(sum(sorted(group_pos, reverse=True)[:k]) / total_pos, 6)


def _page_sequence_locality(groups: Mapping[str, Sequence[str]]) -> float:
    scores: list[float] = []
    for pages in groups.values():
        seqs = sorted([s for s in (_page_sequence(page_id) for page_id in pages) if s is not None])
        if len(seqs) <= 1:
            continue
        gaps = [b - a for a, b in zip(seqs, seqs[1:])]
        if not gaps:
            continue
        avg_gap = sum(gaps) / len(gaps)
        # Score near 1 for adjacent/sequential clusters, decreasing as gaps grow.
        scores.append(1.0 / (1.0 + avg_gap / 25.0))
    if not scores:
        return 0.0
    return round(sum(scores) / len(scores), 6)


def _internal_edge_density(groups: Mapping[str, Sequence[str]], nodes: Mapping[str, Mapping[str, Any]], edges: Sequence[Mapping[str, Any]]) -> float:
    # Page-level density using only page nodes. This is not graph modularity; it is
    # a light diagnostic for whether pages in the same group have direct semantic
    # projection links through page nodes.
    page_node_for_id: dict[str, str] = {}
    for node_id, node in nodes.items():
        if _node_type(node) == "page" or node_id.startswith("page:"):
            page_id = _extract_page_id(node_id) or str(node.get("page_id") or "")
            if page_id:
                page_node_for_id[page_id] = node_id
    edge_set: set[tuple[str, str]] = set()
    for edge in edges:
        src, dst = _edge_endpoints(edge)
        if src and dst:
            edge_set.add(tuple(sorted((src, dst))))
    densities: list[float] = []
    for pages in groups.values():
        page_nodes = [page_node_for_id[p] for p in pages if p in page_node_for_id]
        n = len(page_nodes)
        if n <= 1:
            continue
        possible = n * (n - 1) / 2
        actual = 0
        for i in range(n):
            for j in range(i + 1, n):
                if tuple(sorted((page_nodes[i], page_nodes[j]))) in edge_set:
                    actual += 1
        densities.append(actual / possible if possible else 0.0)
    if not densities:
        return 0.0
    return round(sum(densities) / len(densities), 6)


def _evaluate_partition(
    name: str,
    groups: Mapping[str, Sequence[str]],
    page_meta: Mapping[str, Mapping[str, Any]],
    nodes: Mapping[str, Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]],
    algorithm_available: bool = True,
    algorithm_error: str | None = None,
    modularity_score: float | None = None,
) -> dict[str, Any]:
    page_counts = [len(set(pages)) for pages in groups.values() if len(set(pages)) > 0]
    total_pages = len(set(p for pages in groups.values() for p in pages))
    largest = max(page_counts) if page_counts else 0
    group_count = len(page_counts)
    singleton = sum(1 for c in page_counts if c == 1)
    table_pred = lambda meta: str(meta.get("repair_route", "")).startswith("table_crop_tile") or str(meta.get("table_route", "")).startswith("table_crop_tile") or str(meta.get("table_candidate_level", "")) in {"high", "medium"}
    halluc_pred = lambda meta: "hallucination_risk" in (meta.get("review_traits") or [])
    needs_review_pred = lambda meta: "needs_human_review" in (meta.get("review_traits") or [])

    route_purity = _weighted_purity(groups, page_meta, "repair_route")
    table_route_purity = _weighted_purity(groups, page_meta, "table_route")
    role_purity = _weighted_purity(groups, page_meta, "page_role")
    image_class_purity = _weighted_purity(groups, page_meta, "image_class")
    trust_purity = _weighted_purity(groups, page_meta, "trust_tier")
    table_trait_purity = _weighted_trait_purity(groups, page_meta, "table_expected_but_not_extracted")
    hallucination_trait_purity = _weighted_trait_purity(groups, page_meta, "hallucination_risk")

    table_concentration_top3 = _top_k_concentration(groups, page_meta, table_pred, k=3)
    hallucination_concentration_top3 = _top_k_concentration(groups, page_meta, halluc_pred, k=3)
    review_concentration_top3 = _top_k_concentration(groups, page_meta, needs_review_pred, k=3)

    # Repair batching score favors concentrated repair queues, coherent routes,
    # and moderate community sizes. Penalize singleton-only and huge-dominant partitions.
    largest_ratio = largest / total_pages if total_pages else 0.0
    anti_huge = max(0.0, 1.0 - max(0.0, largest_ratio - 0.35))
    anti_singleton = max(0.0, 1.0 - (singleton / group_count if group_count else 0.0))
    repair_batching_score = round(
        0.30 * route_purity
        + 0.25 * table_route_purity
        + 0.20 * table_concentration_top3
        + 0.15 * anti_huge
        + 0.10 * anti_singleton,
        6,
    )

    # Retrieval expansion score favors non-singleton communities that are not too huge,
    # preserve role/image coherence, and have page sequence locality.
    sequence_locality = _page_sequence_locality(groups)
    retrieval_expansion_score = round(
        0.25 * role_purity
        + 0.20 * image_class_purity
        + 0.20 * sequence_locality
        + 0.20 * anti_huge
        + 0.15 * anti_singleton,
        6,
    )

    return {
        "algorithm": name,
        "algorithm_available": algorithm_available,
        "algorithm_error": algorithm_error,
        "community_count": group_count,
        "communities_with_pages": group_count,
        "pages_covered": total_pages,
        "largest_community_pages": largest,
        "largest_community_ratio": round(largest_ratio, 6) if total_pages else 0.0,
        "singleton_communities": singleton,
        "community_size_entropy": _entropy(page_counts),
        "community_size_gini": _gini(page_counts),
        "mean_internal_page_edge_density": _internal_edge_density(groups, nodes, edges),
        "modularity_score": modularity_score,
        "route_purity": route_purity,
        "table_route_purity": table_route_purity,
        "page_role_purity": role_purity,
        "image_class_purity": image_class_purity,
        "trust_tier_purity": trust_purity,
        "table_trait_purity": table_trait_purity,
        "hallucination_trait_purity": hallucination_trait_purity,
        "table_repair_concentration_top3": table_concentration_top3,
        "hallucination_concentration_top3": hallucination_concentration_top3,
        "review_concentration_top3": review_concentration_top3,
        "page_sequence_locality": sequence_locality,
        "repair_batching_score": repair_batching_score,
        "retrieval_expansion_score": retrieval_expansion_score,
    }


def _algorithm_list(value: str) -> list[str]:
    if value == "all":
        return ["no_community", "route_grouping", "greedy_modularity", "leiden"]
    return [v.strip() for v in value.split(",") if v.strip()]


def evaluate_trace_net_community_ablation(
    paths: CommunityAblationPaths | None = None,
    algorithms: str = "all",
    leiden_resolution: float = 1.0,
    write: bool = True,
) -> dict[str, Any]:
    paths = paths or CommunityAblationPaths()
    nodes, edges = _load_projection(paths)
    page_ids = _page_nodes_from_projection(nodes)
    page_meta = _load_page_metadata(paths, nodes)
    _count_page_parts(nodes, edges, page_meta)

    # Ensure every projection page has metadata.
    for page_id in page_ids:
        page_meta.setdefault(page_id, {"page_id": page_id, "page_sequence": _page_sequence(page_id)})

    results: list[dict[str, Any]] = []
    requested = _algorithm_list(algorithms)

    if "no_community" in requested:
        results.append(_evaluate_partition("no_community", _partition_no_community(page_ids), page_meta, nodes, edges))

    if "route_grouping" in requested:
        results.append(_evaluate_partition("route_grouping", _partition_route_grouping(page_ids, page_meta), page_meta, nodes, edges))

    if "greedy_modularity" in requested or "networkx_greedy_modularity" in requested:
        try:
            part, modularity = _partition_networkx_greedy(nodes, edges)
            results.append(_evaluate_partition("networkx_greedy_modularity", part, page_meta, nodes, edges, modularity_score=modularity))
        except Exception as exc:
            results.append(_evaluate_partition("networkx_greedy_modularity", {}, page_meta, nodes, edges, algorithm_available=False, algorithm_error=str(exc)))

    if "leiden" in requested:
        try:
            part, quality = _partition_leiden(nodes, edges, resolution=leiden_resolution)
            results.append(_evaluate_partition("leiden", part, page_meta, nodes, edges, modularity_score=quality))
        except Exception as exc:
            results.append(_evaluate_partition("leiden", {}, page_meta, nodes, edges, algorithm_available=False, algorithm_error=str(exc)))

    usable_results = [r for r in results if r.get("algorithm_available") and r.get("community_count", 0) > 0]
    best_repair = max(usable_results, key=lambda r: r.get("repair_batching_score", 0.0), default=None)
    best_retrieval = max(usable_results, key=lambda r: r.get("retrieval_expansion_score", 0.0), default=None)

    leiden_result = next((r for r in results if r.get("algorithm") == "leiden"), None)
    route_result = next((r for r in results if r.get("algorithm") == "route_grouping"), None)
    no_result = next((r for r in results if r.get("algorithm") == "no_community"), None)

    def delta(a: Mapping[str, Any] | None, b: Mapping[str, Any] | None, key: str) -> float | None:
        if not a or not b:
            return None
        try:
            return round(float(a.get(key, 0.0)) - float(b.get(key, 0.0)), 6)
        except Exception:
            return None

    summary: dict[str, Any] = {
        "status": "OK",
        "created_at": _utc_now(),
        "requested_algorithms": requested,
        "projection_nodes": len(nodes),
        "projection_edges": len(edges),
        "pages_loaded": len(page_ids),
        "algorithm_count": len(results),
        "available_algorithm_count": len(usable_results),
        "leiden_available": bool(leiden_result and leiden_result.get("algorithm_available")),
        "best_repair_batching_algorithm": best_repair.get("algorithm") if best_repair else None,
        "best_repair_batching_score": best_repair.get("repair_batching_score") if best_repair else None,
        "best_retrieval_expansion_algorithm": best_retrieval.get("algorithm") if best_retrieval else None,
        "best_retrieval_expansion_score": best_retrieval.get("retrieval_expansion_score") if best_retrieval else None,
        "leiden_vs_route_repair_delta": delta(leiden_result, route_result, "repair_batching_score"),
        "leiden_vs_route_retrieval_delta": delta(leiden_result, route_result, "retrieval_expansion_score"),
        "leiden_vs_no_community_repair_delta": delta(leiden_result, no_result, "repair_batching_score"),
        "leiden_vs_no_community_retrieval_delta": delta(leiden_result, no_result, "retrieval_expansion_score"),
    }

    report = {
        "status": "OK",
        "summary": summary,
        "algorithms": results,
        "inputs": {
            "projection_nodes_path": str(paths.projection_nodes_path),
            "projection_edges_path": str(paths.projection_edges_path),
            "repair_plan_path": str(paths.repair_plan_path),
            "table_candidate_plan_path": str(paths.table_candidate_plan_path),
            "page_index_path": str(paths.page_index_path),
            "page_cards_path": str(paths.page_cards_path),
        },
        "notes": [
            "This is an ablation/measurement overlay; it does not mutate the source graph.",
            "Leiden should be used only where it improves retrieval, review batching, or community summaries.",
            "No-community and route-grouping baselines are included to detect redundant community overlays.",
        ],
    }

    if write:
        paths.output_dir.mkdir(parents=True, exist_ok=True)
        _write_json(paths.eval_json_path, report)
        paths.eval_md_path.write_text(render_community_ablation_markdown(report), encoding="utf-8")

    return report


def render_community_ablation_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary", {}) if isinstance(report.get("summary"), dict) else {}
    algs = report.get("algorithms", []) if isinstance(report.get("algorithms"), list) else []
    lines: list[str] = []
    lines.append("# TRACE-Net Community Ablation Evaluation")
    lines.append("")
    lines.append(f"Status: **{report.get('status', 'UNKNOWN')}**")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    for key in (
        "pages_loaded",
        "projection_nodes",
        "projection_edges",
        "algorithm_count",
        "available_algorithm_count",
        "leiden_available",
        "best_repair_batching_algorithm",
        "best_repair_batching_score",
        "best_retrieval_expansion_algorithm",
        "best_retrieval_expansion_score",
        "leiden_vs_route_repair_delta",
        "leiden_vs_route_retrieval_delta",
        "leiden_vs_no_community_repair_delta",
        "leiden_vs_no_community_retrieval_delta",
    ):
        lines.append(f"- `{key}`: {summary.get(key)}")
    lines.append("")
    lines.append("## Algorithm Comparison")
    lines.append("")
    lines.append("| Algorithm | Available | Communities | Largest pages | Largest ratio | Route purity | Table purity | Repair score | Retrieval score |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for alg in algs:
        if not isinstance(alg, dict):
            continue
        lines.append(
            "| {algorithm} | {available} | {communities} | {largest} | {largest_ratio} | {route_purity} | {table_purity} | {repair} | {retrieval} |".format(
                algorithm=alg.get("algorithm"),
                available=alg.get("algorithm_available"),
                communities=alg.get("community_count"),
                largest=alg.get("largest_community_pages"),
                largest_ratio=alg.get("largest_community_ratio"),
                route_purity=alg.get("route_purity"),
                table_purity=alg.get("table_route_purity"),
                repair=alg.get("repair_batching_score"),
                retrieval=alg.get("retrieval_expansion_score"),
            )
        )
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    lines.append("Use Leiden only if it improves a downstream task. If route grouping beats Leiden for repair batching, use route grouping for that job and keep Leiden for exploration/community summaries.")
    lines.append("")
    lines.append("Core source tracing should never depend on communities; it should continue to use deterministic graph traversal.")
    lines.append("")
    return "\n".join(lines)


def build_community_ablation_quality(
    paths: CommunityAblationPaths | None = None,
    min_pages: int = 1,
    min_algorithms: int = 2,
    require_leiden: bool = False,
    min_repair_score: float | None = None,
) -> dict[str, Any]:
    paths = paths or CommunityAblationPaths()
    report = _read_json(paths.eval_json_path, default={})
    summary = report.get("summary", {}) if isinstance(report, dict) and isinstance(report.get("summary"), dict) else {}
    algorithms = report.get("algorithms", []) if isinstance(report, dict) and isinstance(report.get("algorithms"), list) else []

    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, message: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "message": message})

    present = paths.eval_json_path.exists()
    add("community_ablation_report_present", present, f"Report present at {paths.eval_json_path}: {present}.")
    add("community_ablation_status", str(report.get("status", "")).upper() == "OK", f"Report status is {report.get('status')}.")

    pages = int(summary.get("pages_loaded") or 0)
    add("community_ablation_pages", pages >= min_pages, f"pages_loaded={pages}; minimum={min_pages}.")

    available = int(summary.get("available_algorithm_count") or 0)
    add("community_ablation_algorithms", available >= min_algorithms, f"available algorithms={available}; minimum={min_algorithms}.")

    leiden_available = bool(summary.get("leiden_available"))
    add("community_ablation_leiden_available", (not require_leiden) or leiden_available, f"leiden_available={leiden_available}; require_leiden={require_leiden}.")

    projection_edges = int(summary.get("projection_edges") or 0)
    add("community_ablation_projection_edges", projection_edges > 0, f"projection_edges={projection_edges}; expected > 0.")

    best_repair_score = summary.get("best_repair_batching_score")
    if min_repair_score is not None:
        try:
            score_ok = float(best_repair_score or 0.0) >= float(min_repair_score)
        except Exception:
            score_ok = False
        add("community_ablation_best_repair_score", score_ok, f"best_repair_batching_score={best_repair_score}; minimum={min_repair_score}.")
    else:
        add("community_ablation_best_repair_score", best_repair_score is not None, f"best_repair_batching_score={best_repair_score}.")

    # Ensure the baseline comparison is meaningful.
    alg_names = {str(a.get("algorithm")) for a in algorithms if isinstance(a, dict)}
    add("community_ablation_has_no_community_baseline", "no_community" in alg_names, f"algorithms={sorted(alg_names)} includes no_community.")
    add("community_ablation_has_route_grouping_baseline", "route_grouping" in alg_names, f"algorithms={sorted(alg_names)} includes route_grouping.")

    status = "OK" if all(c["ok"] for c in checks) else "FAIL"
    quality = {
        "status": status,
        "summary": {
            "community_ablation_report_present": present,
            "community_ablation_status": report.get("status"),
            "community_ablation_pages_loaded": pages,
            "community_ablation_projection_nodes": int(summary.get("projection_nodes") or 0),
            "community_ablation_projection_edges": projection_edges,
            "community_ablation_algorithm_count": int(summary.get("algorithm_count") or 0),
            "community_ablation_available_algorithm_count": available,
            "community_ablation_leiden_available": leiden_available,
            "community_ablation_best_repair_batching_algorithm": summary.get("best_repair_batching_algorithm"),
            "community_ablation_best_repair_batching_score": best_repair_score,
            "community_ablation_best_retrieval_expansion_algorithm": summary.get("best_retrieval_expansion_algorithm"),
            "community_ablation_best_retrieval_expansion_score": summary.get("best_retrieval_expansion_score"),
            "community_ablation_leiden_vs_route_repair_delta": summary.get("leiden_vs_route_repair_delta"),
            "community_ablation_leiden_vs_route_retrieval_delta": summary.get("leiden_vs_route_retrieval_delta"),
            "community_ablation_require_leiden": require_leiden,
            "community_ablation_eval_path": str(paths.eval_json_path),
        },
        "checks": checks,
    }
    return quality


def write_community_ablation_quality(quality: Mapping[str, Any], paths: CommunityAblationPaths | None = None) -> Path:
    paths = paths or CommunityAblationPaths()
    _write_json(paths.quality_json_path, quality)
    return paths.quality_json_path


def _print_eval(report: Mapping[str, Any]) -> None:
    summary = report.get("summary", {}) if isinstance(report.get("summary"), dict) else {}
    print("TRACE-Net community ablation evaluation")
    print(f"  Status: {report.get('status')}")
    print("  Summary:")
    for key in (
        "pages_loaded",
        "projection_nodes",
        "projection_edges",
        "available_algorithm_count",
        "leiden_available",
        "best_repair_batching_algorithm",
        "best_repair_batching_score",
        "best_retrieval_expansion_algorithm",
        "best_retrieval_expansion_score",
        "leiden_vs_route_repair_delta",
        "leiden_vs_route_retrieval_delta",
    ):
        print(f"    {key}: {summary.get(key)}")
    print("  Algorithms:")
    for alg in report.get("algorithms", []):
        if not isinstance(alg, dict):
            continue
        print(
            "    {algorithm}: available={available} communities={communities} largest={largest} repair={repair} retrieval={retrieval}".format(
                algorithm=alg.get("algorithm"),
                available=alg.get("algorithm_available"),
                communities=alg.get("community_count"),
                largest=alg.get("largest_community_pages"),
                repair=alg.get("repair_batching_score"),
                retrieval=alg.get("retrieval_expansion_score"),
            )
        )


def _print_quality(quality: Mapping[str, Any]) -> None:
    print("TRACE-Net community ablation quality gate")
    print(f"  Status: {quality.get('status')}")
    print("  Summary:")
    for key, value in (quality.get("summary") or {}).items():
        print(f"    {key}: {value}")
    print("  Checks:")
    for check in quality.get("checks") or []:
        status = "OK" if check.get("ok") else "FAIL"
        print(f"    {status} {check.get('name')}: {check.get('message')}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate TRACE-Net community algorithms against baselines.")
    parser.add_argument("--communities-dir", default="local_data/organization/communities")
    parser.add_argument("--trace-net-dir", default="local_data/organization/trace_net")
    parser.add_argument("--table-scan-dir", default="local_data/organization/table_extraction/all_page_scan")
    parser.add_argument("--export-dir", default="local_data/organization/export")
    parser.add_argument("--entity-trait-dir", default="local_data/organization/entity_traits")
    parser.add_argument("--algorithms", default="all", help="all or comma list: no_community,route_grouping,greedy_modularity,leiden")
    parser.add_argument("--leiden-resolution", type=float, default=1.0)
    parser.add_argument("--min-pages", type=int, default=1)
    parser.add_argument("--min-algorithms", type=int, default=2)
    parser.add_argument("--require-leiden", action="store_true")
    parser.add_argument("--min-repair-score", type=float, default=None)
    parser.add_argument("--check-quality", action="store_true")
    parser.add_argument("--write-json", action="store_true", help="Write quality JSON when --check-quality is used.")
    args = parser.parse_args(argv)

    paths = CommunityAblationPaths(
        communities_dir=Path(args.communities_dir),
        trace_net_dir=Path(args.trace_net_dir),
        table_scan_dir=Path(args.table_scan_dir),
        export_dir=Path(args.export_dir),
        entity_trait_dir=Path(args.entity_trait_dir),
    )

    if args.check_quality:
        quality = build_community_ablation_quality(
            paths,
            min_pages=args.min_pages,
            min_algorithms=args.min_algorithms,
            require_leiden=args.require_leiden,
            min_repair_score=args.min_repair_score,
        )
        _print_quality(quality)
        if args.write_json:
            out = write_community_ablation_quality(quality, paths)
            print(f"\nJSON: {out}")
        return 0 if quality.get("status") == "OK" else 1

    report = evaluate_trace_net_community_ablation(paths, algorithms=args.algorithms, leiden_resolution=args.leiden_resolution, write=True)
    _print_eval(report)
    print("Files written:")
    print(f"  eval_json: {paths.eval_json_path}")
    print(f"  eval_md: {paths.eval_md_path}")
    return 0 if report.get("status") == "OK" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
