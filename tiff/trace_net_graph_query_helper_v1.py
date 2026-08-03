"""TRACE-Net Graph Query Helper v1.

Read-only, bounded graph query helper for TRACE-Net.

This module executes a small set of approved deterministic graph lookups over
local graph/export artifacts:

- part -> page/source lookup
- page -> parts/source lookup
- ATA -> pages/source lookup

It is deliberately not an LLM answerer and not a graph writeback tool. The
helper returns structured source-trace/navigation records for APIs, UI, and
retrieval-side source resolution. All results remain advisory until the normal
TRACE-Net citation/authority/final-gate path approves an answer.

Safety contract:
- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission
- no claim-proof authority
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "trace_net_graph_query_helper_v1"
STATUS_BUILT = "GRAPH_QUERY_HELPER_BUILT"
STATUS_FAIL = "GRAPH_QUERY_HELPER_QUALITY_FAIL"
DEFAULT_REPORT_NAME = "trace_net_graph_query_helper_v1.json"
DEFAULT_QUALITY_NAME = "trace_net_graph_query_helper_v1_quality.json"
DEFAULT_RECORDS_NAME = "trace_net_graph_query_helper_v1_records.jsonl"
DEFAULT_PAGE_RESULTS_NAME = "trace_net_graph_query_helper_v1_page_results.jsonl"
DEFAULT_MARKDOWN_NAME = "trace_net_graph_query_helper_v1.md"

PART_RE = re.compile(r"\b\d{3}-\d{5}(?:-\d{3})?\b")
ATA_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")

SAFE_ZERO_COUNTERS = [
    "community_as_proof_count",
    "category_as_proof_count",
    "feedback_as_proof_count",
    "retrieval_only_answer_allowed_count",
    "can_answer_directly_count",
    "can_prove_claims_count",
    "source_truth_mutation_allowed_count",
    "postgres_write_attempt_count",
    "qdrant_write_attempt_count",
    "opensearch_write_attempt_count",
]


@dataclass(frozen=True)
class QualityThresholds:
    min_query_records: int = 1
    min_page_results: int = 1
    min_source_resolved_results: int = 1
    min_part_query_results: int = 0
    min_page_query_results: int = 0
    min_ata_query_results: int = 0
    require_graph_nodes: bool = False
    require_graph_edges: bool = False
    require_no_answer_permission: bool = False


def load_json_any(path: str | Path) -> Any:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Missing JSON input: {p}")
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_json(path: str | Path) -> dict[str, Any]:
    payload = load_json_any(path)
    if not isinstance(payload, dict):
        raise TypeError(f"Expected top-level JSON object in {path}")
    return payload


def read_optional_json(path: str | Path | None) -> tuple[str, Any | None]:
    if not path:
        return "NOT_PROVIDED", None
    p = Path(path)
    if not p.exists():
        return "MISSING", None
    try:
        return "LOADED", load_json_any(p)
    except Exception as exc:  # pragma: no cover - defensive reporting path
        return f"UNREADABLE:{type(exc).__name__}", None


def write_json(path: str | Path, payload: dict[str, Any]) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return p


def write_jsonl(path: str | Path, records: Iterable[dict[str, Any]]) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return p


def stable_id(*parts: Any, prefix: str = "gqh") -> str:
    raw = "|".join(str(p) for p in parts if p is not None)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def normalize_token(value: Any) -> str:
    return str(value or "").strip()


def upper_clean(value: Any) -> str:
    return normalize_token(value).upper()


def dict_get_any(d: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in d and d.get(key) not in (None, "", [], {}):
            return d.get(key)
    props = d.get("properties") if isinstance(d.get("properties"), dict) else {}
    data = d.get("data") if isinstance(d.get("data"), dict) else {}
    attrs = d.get("attributes") if isinstance(d.get("attributes"), dict) else {}
    for space in (props, data, attrs):
        for key in keys:
            if key in space and space.get(key) not in (None, "", [], {}):
                return space.get(key)
    return None


def node_id_of(row: dict[str, Any], fallback: str) -> str:
    return str(dict_get_any(row, "node_id", "id", "uid", "key", "name") or fallback)


def node_type_of(row: dict[str, Any]) -> str:
    return str(dict_get_any(row, "node_type", "type", "kind", "label_type", "category") or "unknown")


def node_label_of(row: dict[str, Any], node_id: str) -> str:
    return str(dict_get_any(row, "label", "name", "title", "display_name", "part_number", "page_id", "ata_code") or node_id)


def properties_of(row: dict[str, Any]) -> dict[str, Any]:
    props: dict[str, Any] = {}
    for key in ("properties", "data", "attributes", "metadata"):
        value = row.get(key)
        if isinstance(value, dict):
            props.update(value)
    # Keep common top-level values as searchable properties.
    for key in [
        "page_id",
        "page_label",
        "page_number",
        "ata_code",
        "source_url",
        "source_uri",
        "href",
        "url",
        "tiff_path",
        "ocr_path",
        "file_path",
        "part_number",
        "nomenclature",
    ]:
        if row.get(key) not in (None, "", [], {}):
            props.setdefault(key, row.get(key))
    return props


def extract_nodes(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        raw_nodes = payload
    elif isinstance(payload, dict):
        raw_nodes = (
            payload.get("nodes")
            or payload.get("graph_nodes")
            or payload.get("node_records")
            or payload.get("records")
            or payload.get("items")
        )
        if raw_nodes is None and all(isinstance(v, dict) for v in payload.values()):
            raw_nodes = []
            for key, value in payload.items():
                row = dict(value)
                row.setdefault("node_id", key)
                raw_nodes.append(row)
    else:
        raw_nodes = []

    nodes: list[dict[str, Any]] = []
    for idx, raw in enumerate(raw_nodes or []):
        if not isinstance(raw, dict):
            continue
        node_id = node_id_of(raw, f"node_{idx:06d}")
        node_type = node_type_of(raw)
        label = node_label_of(raw, node_id)
        nodes.append(
            {
                "node_id": node_id,
                "node_type": node_type,
                "label": label,
                "properties": properties_of(raw),
                "raw": raw,
            }
        )
    return nodes


def edge_id_of(row: dict[str, Any], idx: int, source_id: str, target_id: str, edge_type: str) -> str:
    return str(dict_get_any(row, "edge_id", "id", "uid", "key") or stable_id(idx, source_id, target_id, edge_type, prefix="edge"))


def edge_source_of(row: dict[str, Any]) -> str | None:
    value = dict_get_any(row, "source_id", "source", "from", "from_id", "src", "start", "source_node_id")
    if isinstance(value, dict):
        value = dict_get_any(value, "node_id", "id")
    return str(value) if value not in (None, "") else None


def edge_target_of(row: dict[str, Any]) -> str | None:
    value = dict_get_any(row, "target_id", "target", "to", "to_id", "dst", "end", "target_node_id")
    if isinstance(value, dict):
        value = dict_get_any(value, "node_id", "id")
    return str(value) if value not in (None, "") else None


def edge_type_of(row: dict[str, Any]) -> str:
    return str(dict_get_any(row, "edge_type", "type", "relation", "relationship", "label") or "UNKNOWN_EDGE")


def extract_edges(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        raw_edges = payload
    elif isinstance(payload, dict):
        raw_edges = (
            payload.get("edges")
            or payload.get("graph_edges")
            or payload.get("edge_records")
            or payload.get("records")
            or payload.get("items")
        )
    else:
        raw_edges = []

    edges: list[dict[str, Any]] = []
    for idx, raw in enumerate(raw_edges or []):
        if not isinstance(raw, dict):
            continue
        source_id = edge_source_of(raw)
        target_id = edge_target_of(raw)
        if not source_id or not target_id:
            continue
        edge_type = edge_type_of(raw)
        edge_id = edge_id_of(raw, idx, source_id, target_id, edge_type)
        edges.append(
            {
                "edge_id": edge_id,
                "source_id": source_id,
                "target_id": target_id,
                "edge_type": edge_type,
                "properties": properties_of(raw),
                "raw": raw,
            }
        )
    return edges


def node_search_text(node: dict[str, Any]) -> str:
    props = node.get("properties") if isinstance(node.get("properties"), dict) else {}
    values = [node.get("node_id"), node.get("node_type"), node.get("label")]
    for key in [
        "page_id",
        "page_label",
        "page_number",
        "ata_code",
        "part_number",
        "nomenclature",
        "source_url",
        "source_uri",
        "href",
        "url",
        "tiff_path",
    ]:
        values.append(props.get(key))
    return " ".join(str(x) for x in values if x not in (None, ""))


def node_type_contains(node: dict[str, Any], token: str) -> bool:
    return token.lower() in str(node.get("node_type", "")).lower()


def is_part_node(node: dict[str, Any]) -> bool:
    t = str(node.get("node_type", "")).lower()
    return "part" in t and "mention" not in t


def is_part_mention_node(node: dict[str, Any]) -> bool:
    return "part_mention" in str(node.get("node_type", "")).lower() or "mention" in str(node.get("node_type", "")).lower()


def is_page_node(node: dict[str, Any]) -> bool:
    return str(node.get("node_type", "")).lower() == "page" or "page" == str(node.get("node_type", "")).lower()


def is_ata_node(node: dict[str, Any]) -> bool:
    return "ata" in str(node.get("node_type", "")).lower()


def page_id(node: dict[str, Any]) -> str:
    return str(dict_get_any(node, "page_id") or node.get("node_id"))


def page_label(node: dict[str, Any]) -> str | None:
    return dict_get_any(node, "page_label", "label", "page_number") or node.get("label")


def part_number(node: dict[str, Any]) -> str | None:
    value = dict_get_any(node, "part_number")
    if value:
        return str(value)
    matches = PART_RE.findall(node_search_text(node))
    return matches[0] if matches else None


def ata_code_from_node(node: dict[str, Any]) -> str | None:
    value = dict_get_any(node, "ata_code", "ata")
    if value:
        return str(value)
    matches = ATA_RE.findall(node_search_text(node))
    return matches[0] if matches else None


def source_uri_from_node(node: dict[str, Any]) -> str | None:
    value = dict_get_any(node, "source_uri", "source_url", "url", "href", "target", "path")
    return str(value) if value not in (None, "") else None


def file_path_from_node(node: dict[str, Any]) -> str | None:
    value = dict_get_any(node, "tiff_path", "ocr_path", "file_path", "path", "href")
    return str(value) if value not in (None, "") else None


class GraphIndex:
    def __init__(self, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> None:
        self.nodes = nodes
        self.edges = edges
        self.nodes_by_id = {n["node_id"]: n for n in nodes}
        self.out_edges: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.in_edges: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for edge in edges:
            self.out_edges[edge["source_id"]].append(edge)
            self.in_edges[edge["target_id"]].append(edge)

    def get(self, node_id: str | None) -> dict[str, Any] | None:
        if not node_id:
            return None
        return self.nodes_by_id.get(str(node_id))

    def out_neighbors(self, node_id: str, edge_types: Iterable[str] | None = None) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        allowed = {e.upper() for e in edge_types or []}
        out: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for edge in self.out_edges.get(node_id, []):
            if allowed and str(edge.get("edge_type", "")).upper() not in allowed:
                continue
            target = self.get(edge.get("target_id"))
            if target:
                out.append((edge, target))
        return out

    def in_neighbors(self, node_id: str, edge_types: Iterable[str] | None = None) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        allowed = {e.upper() for e in edge_types or []}
        out: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for edge in self.in_edges.get(node_id, []):
            if allowed and str(edge.get("edge_type", "")).upper() not in allowed:
                continue
            source = self.get(edge.get("source_id"))
            if source:
                out.append((edge, source))
        return out

    def find_part_nodes(self, value: str) -> list[dict[str, Any]]:
        needle = upper_clean(value)
        matches = []
        for node in self.nodes:
            if not is_part_node(node):
                continue
            if needle and needle in upper_clean(node_search_text(node)):
                matches.append(node)
        return sorted(matches, key=lambda n: n["node_id"])

    def find_page_nodes(self, value: str) -> list[dict[str, Any]]:
        # Page ids require EXACT normalized equality. A full canonical page id
        # must never substring-match a different page (e.g. p000018 vs p000181,
        # p000081 vs p000181); the old `needle in node_search_text` clause matched
        # the bare page number inside a longer page's blob. Part/ATA fragment
        # matchers keep substring behavior on purpose; page ids do not.
        needle = upper_clean(value)
        if not needle:
            return []
        matches = []
        for node in self.nodes:
            if not is_page_node(node):
                continue
            if needle == upper_clean(node.get("node_id")) or needle == upper_clean(page_id(node)):
                matches.append(node)
        return sorted(matches, key=lambda n: n["node_id"])

    def find_ata_nodes(self, value: str) -> list[dict[str, Any]]:
        needle = upper_clean(value)
        matches = []
        for node in self.nodes:
            if not is_ata_node(node):
                continue
            if needle in upper_clean(node_search_text(node)):
                matches.append(node)
        return sorted(matches, key=lambda n: n["node_id"])

    def page_nodes_with_ata(self, ata_code: str) -> list[dict[str, Any]]:
        needle = upper_clean(ata_code)
        matches = []
        for node in self.nodes:
            if is_page_node(node) and needle in upper_clean(node_search_text(node)):
                matches.append(node)
        return sorted(matches, key=lambda n: page_id(n))


def infer_quality_status(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return payload.get("quality_status") or payload.get("status") or summary.get("quality_status") or summary.get("status")


def extract_page_records(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    for key in ["page_records", "records", "pages", "page_profiles"]:
        value = payload.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
    return []


def page_record_id(record: dict[str, Any]) -> str | None:
    return str(dict_get_any(record, "page_id", "id", "source_page_id") or "") or None


def index_dublin_core_pages(payload: Any) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for record in extract_page_records(payload):
        pid = page_record_id(record)
        if not pid:
            continue
        dc = record.get("dc") if isinstance(record.get("dc"), dict) else {}
        source_pkg = (
            record.get("source_package")
            or record.get("source_package_entry")
            or record.get("source_package_summary")
            or record.get("source_trace")
            or {}
        )
        index[pid] = {
            "page_id": pid,
            "dc_identifier": dc.get("dc:identifier") or dc.get("identifier") or record.get("dc_identifier"),
            "dc_title": dc.get("dc:title") or dc.get("title") or record.get("title"),
            "dc_type": dc.get("dc:type") or dc.get("type") or record.get("dc_type"),
            "source_package": source_pkg,
            "source_identity_status": "DUBLIN_CORE_SOURCE_IDENTITY_RESOLVED",
        }
    return index


def index_leiden_page_hints(payload: Any) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(payload, dict):
        return {}
    hints = payload.get("page_navigation_hints") or []
    community_records = payload.get("community_navigation_records") or []
    by_community = {
        str(r.get("community_id")): r for r in community_records if isinstance(r, dict) and r.get("community_id")
    }
    index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for hint in hints:
        if not isinstance(hint, dict):
            continue
        pid = hint.get("page_id") or hint.get("source_page_id")
        if not pid:
            continue
        cid = str(hint.get("community_id") or "")
        community = by_community.get(cid, {})
        record = {
            "community_id": cid or None,
            "refined_label": hint.get("refined_label") or community.get("refined_label"),
            "navigation_intent": hint.get("navigation_intent") or community.get("navigation_intent"),
            "navigation_confidence": hint.get("navigation_confidence") or community.get("navigation_confidence"),
            "retrieval_only": True,
            "can_answer_directly": False,
            "can_prove_claims": False,
        }
        index[str(pid)].append(record)
    if not index:
        for community in community_records:
            if not isinstance(community, dict):
                continue
            for pid in as_list(community.get("representative_page_ids")):
                if not pid:
                    continue
                index[str(pid)].append(
                    {
                        "community_id": community.get("community_id"),
                        "refined_label": community.get("refined_label"),
                        "navigation_intent": community.get("navigation_intent"),
                        "navigation_confidence": community.get("navigation_confidence"),
                        "retrieval_only": True,
                        "can_answer_directly": False,
                        "can_prove_claims": False,
                    }
                )
    return dict(index)


def unique_dicts(records: Iterable[dict[str, Any]], key_fields: list[str]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    out: list[dict[str, Any]] = []
    for record in records:
        key = tuple(json.dumps(record.get(f), sort_keys=True, ensure_ascii=False) for f in key_fields)
        if key in seen:
            continue
        seen.add(key)
        out.append(record)
    return out


def collect_ata_codes(graph: GraphIndex, page: dict[str, Any]) -> list[str]:
    codes: list[str] = []
    own = ata_code_from_node(page)
    if own:
        codes.append(own)
    for _edge, ata in graph.out_neighbors(page["node_id"], ["BELONGS_TO_ATA"]):
        code = ata_code_from_node(ata)
        if code:
            codes.append(code)
    for _edge, ata in graph.in_neighbors(page["node_id"], ["CONTAINS_PAGE"]):
        code = ata_code_from_node(ata)
        if code:
            codes.append(code)
    return sorted(set(codes))


def collect_sources(graph: GraphIndex, page: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    source_links: list[dict[str, Any]] = []
    tiff_files: list[dict[str, Any]] = []

    direct_uri = source_uri_from_node(page)
    if direct_uri:
        source_links.append({"source_link_id": f"page_source::{page_id(page)}", "source_uri": direct_uri, "source_kind": "page_property"})
    direct_file = file_path_from_node(page)
    if direct_file:
        tiff_files.append({"source_file_id": f"page_file::{page_id(page)}", "file_path": direct_file, "source_kind": "page_property"})

    for edge, source in graph.out_neighbors(page["node_id"], ["HAS_SOURCE_LINK"]):
        source_uri = source_uri_from_node(source)
        source_links.append(
            {
                "source_link_id": source.get("node_id"),
                "source_uri": source_uri,
                "label": source.get("label"),
                "via_edge": edge.get("edge_type"),
                "source_kind": source.get("node_type"),
            }
        )
        for file_edge, source_file in graph.out_neighbors(source["node_id"], ["POINTS_TO_TIFF", "HAS_TIFF"]):
            path = file_path_from_node(source_file)
            tiff_files.append(
                {
                    "source_file_id": source_file.get("node_id"),
                    "file_path": path,
                    "label": source_file.get("label"),
                    "via_edge": file_edge.get("edge_type"),
                    "source_kind": source_file.get("node_type"),
                }
            )
    for edge, source_file in graph.out_neighbors(page["node_id"], ["HAS_TIFF"]):
        path = file_path_from_node(source_file)
        tiff_files.append(
            {
                "source_file_id": source_file.get("node_id"),
                "file_path": path,
                "label": source_file.get("label"),
                "via_edge": edge.get("edge_type"),
                "source_kind": source_file.get("node_type"),
            }
        )
    return unique_dicts(source_links, ["source_link_id", "source_uri"]), unique_dicts(tiff_files, ["source_file_id", "file_path"])


def collect_page_parts(graph: GraphIndex, page: dict[str, Any]) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = []
    for edge, part in graph.out_neighbors(page["node_id"], ["MENTIONS_PART"]):
        if is_part_node(part):
            parts.append({"part_number": part_number(part), "part_node_id": part["node_id"], "via_edge": edge.get("edge_type")})
    for edge, mention in graph.out_neighbors(page["node_id"], ["HAS_PART_MENTION"]):
        if not is_part_mention_node(mention):
            continue
        for ref_edge, part in graph.out_neighbors(mention["node_id"], ["REFERS_TO_PART"]):
            if is_part_node(part):
                parts.append(
                    {
                        "part_number": part_number(part),
                        "part_node_id": part["node_id"],
                        "mention_node_id": mention["node_id"],
                        "via_edge": f"{edge.get('edge_type')}->{ref_edge.get('edge_type')}",
                    }
                )
    for edge, part in graph.in_neighbors(page["node_id"], ["APPEARS_ON"]):
        if is_part_node(part):
            parts.append({"part_number": part_number(part), "part_node_id": part["node_id"], "via_edge": edge.get("edge_type")})
    return [p for p in unique_dicts(parts, ["part_number", "part_node_id"]) if p.get("part_number")]


def collect_part_nomenclature(graph: GraphIndex, part: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for _edge, node in graph.out_neighbors(part["node_id"], ["HAS_NOMENCLATURE"]):
        if node.get("label"):
            names.append(str(node.get("label")))
    return sorted(set(names))


def page_card(
    graph: GraphIndex,
    page: dict[str, Any],
    *,
    dublin_index: dict[str, dict[str, Any]] | None = None,
    leiden_page_index: dict[str, list[dict[str, Any]]] | None = None,
    include_parts: bool = False,
) -> dict[str, Any]:
    pid = page_id(page)
    source_links, tiff_files = collect_sources(graph, page)
    dublin_identity = (dublin_index or {}).get(pid)
    leiden_hints = (leiden_page_index or {}).get(pid, [])
    source_resolved = bool(source_links or tiff_files or dublin_identity)
    card = {
        "page_id": pid,
        "page_node_id": page.get("node_id"),
        "page_label": page_label(page),
        "ata_codes": collect_ata_codes(graph, page),
        "source_links": source_links,
        "source_files": tiff_files,
        "dublin_core_source_identity": dublin_identity,
        "leiden_navigation_hints": leiden_hints[:5],
        "source_resolved": source_resolved,
        "retrieval_only": True,
        "can_answer_directly": False,
        "can_prove_claims": False,
    }
    if include_parts:
        card["part_mentions"] = collect_page_parts(graph, page)
    return card


def part_to_pages_query(
    graph: GraphIndex,
    part_value: str,
    *,
    dublin_index: dict[str, dict[str, Any]] | None = None,
    leiden_page_index: dict[str, list[dict[str, Any]]] | None = None,
    max_results: int = 50,
) -> dict[str, Any]:
    parts = graph.find_part_nodes(part_value)
    page_nodes: list[dict[str, Any]] = []
    path_evidence: list[dict[str, Any]] = []
    nomenclature: list[str] = []

    for part in parts:
        nomenclature.extend(collect_part_nomenclature(graph, part))
        for edge, page in graph.out_neighbors(part["node_id"], ["APPEARS_ON"]):
            if is_page_node(page):
                page_nodes.append(page)
                path_evidence.append({"part_node_id": part["node_id"], "page_id": page_id(page), "path": [edge.get("edge_type")]})
        for edge, mention in graph.out_neighbors(part["node_id"], ["HAS_MENTION"]):
            for edge2, page in graph.out_neighbors(mention["node_id"], ["FOUND_ON"]):
                if is_page_node(page):
                    page_nodes.append(page)
                    path_evidence.append({"part_node_id": part["node_id"], "mention_node_id": mention["node_id"], "page_id": page_id(page), "path": [edge.get("edge_type"), edge2.get("edge_type")]})
        for edge, mention in graph.in_neighbors(part["node_id"], ["REFERS_TO_PART"]):
            for edge2, page in graph.out_neighbors(mention["node_id"], ["FOUND_ON"]):
                if is_page_node(page):
                    page_nodes.append(page)
                    path_evidence.append({"part_node_id": part["node_id"], "mention_node_id": mention["node_id"], "page_id": page_id(page), "path": [edge.get("edge_type"), edge2.get("edge_type")]})
        for edge, page in graph.in_neighbors(part["node_id"], ["MENTIONS_PART"]):
            if is_page_node(page):
                page_nodes.append(page)
                path_evidence.append({"part_node_id": part["node_id"], "page_id": page_id(page), "path": [edge.get("edge_type")]})

    unique_pages = {page_id(p): p for p in page_nodes}
    pages = [page_card(graph, p, dublin_index=dublin_index, leiden_page_index=leiden_page_index) for p in unique_pages.values()]
    pages = sorted(pages, key=lambda x: str(x.get("page_id")))[:max_results]
    return {
        "query_record_id": stable_id("part", part_value, prefix="graph_query"),
        "plan_id": "part_source_check_v1",
        "query_type": "part_lookup",
        "input": {"part_number": part_value},
        "status": "GRAPH_QUERY_RESULT",
        "matched_part_node_count": len(parts),
        "result_count": len(pages),
        "source_resolved_result_count": sum(1 for p in pages if p.get("source_resolved")),
        "nomenclature": sorted(set(nomenclature)),
        "pages": pages,
        "path_evidence_sample": path_evidence[:20],
        "bounded_traversal": True,
        "stop_condition": "stop_after_page_source_resolution",
        "retrieval_only": True,
        "can_answer_directly": False,
        "can_prove_claims": False,
    }


def page_context_query(
    graph: GraphIndex,
    page_value: str,
    *,
    dublin_index: dict[str, dict[str, Any]] | None = None,
    leiden_page_index: dict[str, list[dict[str, Any]]] | None = None,
    max_results: int = 50,
) -> dict[str, Any]:
    pages = graph.find_page_nodes(page_value)
    cards = [page_card(graph, p, dublin_index=dublin_index, leiden_page_index=leiden_page_index, include_parts=True) for p in pages]
    cards = sorted(cards, key=lambda x: str(x.get("page_id")))[:max_results]
    return {
        "query_record_id": stable_id("page", page_value, prefix="graph_query"),
        "plan_id": "page_source_context_v1",
        "query_type": "page_lookup",
        "input": {"page_id_or_label": page_value},
        "status": "GRAPH_QUERY_RESULT",
        "result_count": len(cards),
        "source_resolved_result_count": sum(1 for p in cards if p.get("source_resolved")),
        "pages": cards,
        "bounded_traversal": True,
        "stop_condition": "stop_after_page_local_neighborhood",
        "retrieval_only": True,
        "can_answer_directly": False,
        "can_prove_claims": False,
    }


def ata_pages_query(
    graph: GraphIndex,
    ata_value: str,
    *,
    dublin_index: dict[str, dict[str, Any]] | None = None,
    leiden_page_index: dict[str, list[dict[str, Any]]] | None = None,
    max_results: int = 50,
) -> dict[str, Any]:
    ata_nodes = graph.find_ata_nodes(ata_value)
    page_nodes: list[dict[str, Any]] = []
    for ata in ata_nodes:
        for _edge, page in graph.out_neighbors(ata["node_id"], ["CONTAINS_PAGE"]):
            if is_page_node(page):
                page_nodes.append(page)
        for _edge, page in graph.in_neighbors(ata["node_id"], ["BELONGS_TO_ATA"]):
            if is_page_node(page):
                page_nodes.append(page)
    page_nodes.extend(graph.page_nodes_with_ata(ata_value))
    unique_pages = {page_id(p): p for p in page_nodes}
    cards = [page_card(graph, p, dublin_index=dublin_index, leiden_page_index=leiden_page_index, include_parts=False) for p in unique_pages.values()]
    cards = sorted(cards, key=lambda x: str(x.get("page_id")))[:max_results]
    return {
        "query_record_id": stable_id("ata", ata_value, prefix="graph_query"),
        "plan_id": "ata_pages_browse_v1",
        "query_type": "ata_browse",
        "input": {"ata_code": ata_value},
        "status": "GRAPH_QUERY_RESULT",
        "matched_ata_node_count": len(ata_nodes),
        "result_count": len(cards),
        "source_resolved_result_count": sum(1 for p in cards if p.get("source_resolved")),
        "pages": cards,
        "bounded_traversal": True,
        "stop_condition": "stop_after_section_page_table",
        "retrieval_only": True,
        "can_answer_directly": False,
        "can_prove_claims": False,
    }


def flatten_page_results(query_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in query_records:
        for rank, page in enumerate(record.get("pages") or [], 1):
            rows.append(
                {
                    "query_record_id": record.get("query_record_id"),
                    "plan_id": record.get("plan_id"),
                    "query_type": record.get("query_type"),
                    "rank": rank,
                    **page,
                    "retrieval_only": True,
                    "can_answer_directly": False,
                    "can_prove_claims": False,
                }
            )
    return rows


def count_source_resolved_rows(rows: list[dict[str, Any]]) -> int:
    return sum(1 for row in rows if row.get("source_resolved"))


def compute_summary(
    *,
    graph_nodes: list[dict[str, Any]],
    graph_edges: list[dict[str, Any]],
    query_records: list[dict[str, Any]],
    page_results: list[dict[str, Any]],
    source_load_statuses: dict[str, str],
    source_quality_statuses: dict[str, str | None],
) -> dict[str, Any]:
    query_type_counts = Counter(record.get("query_type") for record in query_records)
    page_result_count = len(page_results)
    source_resolved_result_count = count_source_resolved_rows(page_results)
    result_with_dublin = sum(1 for row in page_results if row.get("dublin_core_source_identity"))
    result_with_leiden = sum(1 for row in page_results if row.get("leiden_navigation_hints"))
    return {
        "schema_version": SCHEMA_VERSION,
        "algorithm": "trace_net_bounded_read_only_graph_query_helper_v1",
        "graph_node_count": len(graph_nodes),
        "graph_edge_count": len(graph_edges),
        "graph_node_type_counts": dict(Counter(n.get("node_type") for n in graph_nodes)),
        "graph_edge_type_counts": dict(Counter(e.get("edge_type") for e in graph_edges)),
        "query_record_count": len(query_records),
        "query_type_counts": dict(query_type_counts),
        "part_query_record_count": query_type_counts.get("part_lookup", 0),
        "page_query_record_count": query_type_counts.get("page_lookup", 0),
        "ata_query_record_count": query_type_counts.get("ata_browse", 0),
        "page_result_count": page_result_count,
        "source_resolved_result_count": source_resolved_result_count,
        "source_resolved_result_ratio": round(source_resolved_result_count / page_result_count, 6) if page_result_count else 0.0,
        "result_with_dublin_core_identity_count": result_with_dublin,
        "result_with_leiden_navigation_hint_count": result_with_leiden,
        "source_load_statuses": source_load_statuses,
        "source_quality_statuses": source_quality_statuses,
        "bounded_traversal_record_count": sum(1 for r in query_records if r.get("bounded_traversal")),
        "unbounded_traversal_record_count": sum(1 for r in query_records if not r.get("bounded_traversal")),
        "community_as_proof_count": 0,
        "category_as_proof_count": 0,
        "feedback_as_proof_count": 0,
        "retrieval_only_answer_allowed_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }


def evaluate_quality(summary: dict[str, Any], thresholds: QualityThresholds) -> tuple[str, list[str]]:
    issues: list[str] = []
    if summary.get("query_record_count", 0) < thresholds.min_query_records:
        issues.append(f"query_record_count below threshold: {summary.get('query_record_count')} < {thresholds.min_query_records}")
    if summary.get("page_result_count", 0) < thresholds.min_page_results:
        issues.append(f"page_result_count below threshold: {summary.get('page_result_count')} < {thresholds.min_page_results}")
    if summary.get("source_resolved_result_count", 0) < thresholds.min_source_resolved_results:
        issues.append(
            f"source_resolved_result_count below threshold: {summary.get('source_resolved_result_count')} < {thresholds.min_source_resolved_results}"
        )
    if summary.get("part_query_record_count", 0) < thresholds.min_part_query_results:
        issues.append("part_query_record_count below threshold")
    if summary.get("page_query_record_count", 0) < thresholds.min_page_query_results:
        issues.append("page_query_record_count below threshold")
    if summary.get("ata_query_record_count", 0) < thresholds.min_ata_query_results:
        issues.append("ata_query_record_count below threshold")
    if thresholds.require_graph_nodes and summary.get("graph_node_count", 0) <= 0:
        issues.append("graph nodes are required but graph_node_count is zero")
    if thresholds.require_graph_edges and summary.get("graph_edge_count", 0) <= 0:
        issues.append("graph edges are required but graph_edge_count is zero")
    if summary.get("unbounded_traversal_record_count", 0) > 0:
        issues.append("unbounded traversal records are not allowed")
    if thresholds.require_no_answer_permission:
        for key in SAFE_ZERO_COUNTERS:
            if summary.get(key, 0) != 0:
                issues.append(f"{key} must be 0, got {summary.get(key)}")
    return ("PASS" if not issues else "FAIL"), issues


def quality_report_from_summary(summary: dict[str, Any], thresholds: QualityThresholds) -> dict[str, Any]:
    quality_status, issues = evaluate_quality(summary, thresholds)
    return {
        "schema_version": f"{SCHEMA_VERSION}_quality",
        "status": "PASS" if quality_status == "PASS" else STATUS_FAIL,
        "quality_status": quality_status,
        "summary": summary,
        "quality_issues": issues,
        "thresholds": {
            "min_query_records": thresholds.min_query_records,
            "min_page_results": thresholds.min_page_results,
            "min_source_resolved_results": thresholds.min_source_resolved_results,
            "min_part_query_results": thresholds.min_part_query_results,
            "min_page_query_results": thresholds.min_page_query_results,
            "min_ata_query_results": thresholds.min_ata_query_results,
            "require_graph_nodes": thresholds.require_graph_nodes,
            "require_graph_edges": thresholds.require_graph_edges,
            "require_no_answer_permission": thresholds.require_no_answer_permission,
        },
    }


def markdown_summary(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        "# TRACE-Net Graph Query Helper v1",
        "",
        f"Status: `{report.get('status')}`",
        f"Quality status: `{report.get('quality_status')}`",
        "",
        "## Summary",
        "",
        f"- Graph nodes: {summary.get('graph_node_count')}",
        f"- Graph edges: {summary.get('graph_edge_count')}",
        f"- Query records: {summary.get('query_record_count')}",
        f"- Page results: {summary.get('page_result_count')}",
        f"- Source-resolved results: {summary.get('source_resolved_result_count')}",
        f"- Dublin Core identities: {summary.get('result_with_dublin_core_identity_count')}",
        f"- Leiden navigation hints: {summary.get('result_with_leiden_navigation_hint_count')}",
        "",
        "## Safety contract",
        "",
        "This helper is read-only. It returns structured graph/source/navigation records only; it does not grant answer permission or prove claims.",
    ]
    return "\n".join(lines) + "\n"


def build_graph_query_helper(
    *,
    graph_nodes_path: str | Path,
    graph_edges_path: str | Path,
    output_dir: str | Path,
    part_numbers: list[str] | None = None,
    page_ids: list[str] | None = None,
    ata_codes: list[str] | None = None,
    dublin_core_source_package_extension: str | Path | None = None,
    leiden_navigation_metadata_bridge: str | Path | None = None,
    max_results_per_query: int = 50,
    thresholds: QualityThresholds | None = None,
    write_quality: bool = False,
) -> dict[str, Any]:
    thresholds = thresholds or QualityThresholds()
    nodes_payload = load_json_any(graph_nodes_path)
    edges_payload = load_json_any(graph_edges_path)
    nodes = extract_nodes(nodes_payload)
    edges = extract_edges(edges_payload)
    graph = GraphIndex(nodes, edges)

    dublin_status, dublin_payload = read_optional_json(dublin_core_source_package_extension)
    leiden_status, leiden_payload = read_optional_json(leiden_navigation_metadata_bridge)
    dublin_index = index_dublin_core_pages(dublin_payload)
    leiden_page_index = index_leiden_page_hints(leiden_payload)

    part_numbers = part_numbers or []
    page_ids = page_ids or []
    ata_codes = ata_codes or []

    query_records: list[dict[str, Any]] = []
    for value in part_numbers:
        query_records.append(
            part_to_pages_query(
                graph,
                value,
                dublin_index=dublin_index,
                leiden_page_index=leiden_page_index,
                max_results=max_results_per_query,
            )
        )
    for value in page_ids:
        query_records.append(
            page_context_query(
                graph,
                value,
                dublin_index=dublin_index,
                leiden_page_index=leiden_page_index,
                max_results=max_results_per_query,
            )
        )
    for value in ata_codes:
        query_records.append(
            ata_pages_query(
                graph,
                value,
                dublin_index=dublin_index,
                leiden_page_index=leiden_page_index,
                max_results=max_results_per_query,
            )
        )

    page_results = flatten_page_results(query_records)
    source_load_statuses = {
        "graph_nodes": "LOADED",
        "graph_edges": "LOADED",
        "dublin_core_source_package_extension": dublin_status,
        "leiden_navigation_metadata_bridge": leiden_status,
    }
    source_quality_statuses = {
        "dublin_core_source_package_extension": infer_quality_status(dublin_payload),
        "leiden_navigation_metadata_bridge": infer_quality_status(leiden_payload),
    }
    summary = compute_summary(
        graph_nodes=nodes,
        graph_edges=edges,
        query_records=query_records,
        page_results=page_results,
        source_load_statuses=source_load_statuses,
        source_quality_statuses=source_quality_statuses,
    )
    quality_status, issues = evaluate_quality(summary, thresholds)

    out_dir = Path(output_dir)
    records_path = out_dir / DEFAULT_RECORDS_NAME
    page_results_path = out_dir / DEFAULT_PAGE_RESULTS_NAME
    report_path = out_dir / DEFAULT_REPORT_NAME
    quality_path = out_dir / DEFAULT_QUALITY_NAME
    markdown_path = out_dir / DEFAULT_MARKDOWN_NAME

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_BUILT,
        "quality_status": quality_status,
        "quality_issues": issues,
        "summary": summary,
        "query_records": query_records,
        "page_result_records": page_results,
        "safety_contract": {
            "postgres_write_allowed": False,
            "qdrant_write_allowed": False,
            "opensearch_write_allowed": False,
            "source_truth_mutation_allowed": False,
            "answer_permission_allowed": False,
            "claim_proof_allowed": False,
            "community_as_proof_allowed": False,
            "category_as_proof_allowed": False,
            "feedback_as_proof_allowed": False,
        },
        "output_paths": {
            "report_path": str(report_path),
            "quality_path": str(quality_path),
            "records_path": str(records_path),
            "page_results_path": str(page_results_path),
            "markdown_path": str(markdown_path),
        },
    }
    write_jsonl(records_path, query_records)
    write_jsonl(page_results_path, page_results)
    write_json(report_path, report)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(markdown_summary(report), encoding="utf-8")
    if write_quality:
        write_json(quality_path, quality_report_from_summary(summary, thresholds))
    return report


def check_graph_query_helper_quality(
    *,
    report_path: str | Path,
    thresholds: QualityThresholds | None = None,
    write_json_report: bool = False,
) -> dict[str, Any]:
    thresholds = thresholds or QualityThresholds()
    report = load_json(report_path)
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    quality = quality_report_from_summary(summary, thresholds)
    if write_json_report:
        quality_path = Path(report_path).with_name(DEFAULT_QUALITY_NAME)
        write_json(quality_path, quality)
    return quality


def print_summary(report: dict[str, Any], quality_only: bool = False) -> None:
    summary = report.get("summary", {})
    title = "TRACE-Net Graph Query Helper v1 quality" if quality_only else "TRACE-Net Graph Query Helper v1"
    print(title)
    print(" Status:", report.get("status"))
    print(" Quality status:", report.get("quality_status"))
    for key in [
        "graph_node_count",
        "graph_edge_count",
        "query_record_count",
        "part_query_record_count",
        "page_query_record_count",
        "ata_query_record_count",
        "page_result_count",
        "source_resolved_result_count",
        "result_with_dublin_core_identity_count",
        "result_with_leiden_navigation_hint_count",
        "unbounded_traversal_record_count",
        "community_as_proof_count",
        "category_as_proof_count",
        "retrieval_only_answer_allowed_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ]:
        if key in summary:
            print(f" {key}: {summary.get(key)}")
    if report.get("quality_issues"):
        print(" Quality issues:")
        for issue in report.get("quality_issues", []):
            print("  -", issue)
    output_paths = report.get("output_paths") if isinstance(report.get("output_paths"), dict) else {}
    if not quality_only and output_paths.get("report_path"):
        print(" report_path:", output_paths.get("report_path"))
        print(" quality_path:", output_paths.get("quality_path"))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Graph Query Helper v1")
    parser.add_argument("--graph-nodes", required=True)
    parser.add_argument("--graph-edges", required=True)
    parser.add_argument("--dublin-core-source-package-extension")
    parser.add_argument("--leiden-navigation-metadata-bridge")
    parser.add_argument("--part-number", action="append", default=[])
    parser.add_argument("--page-id", action="append", default=[])
    parser.add_argument("--ata-code", action="append", default=[])
    parser.add_argument("--max-results-per-query", type=int, default=50)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--min-query-records", type=int, default=1)
    parser.add_argument("--min-page-results", type=int, default=1)
    parser.add_argument("--min-source-resolved-results", type=int, default=1)
    parser.add_argument("--min-part-query-results", type=int, default=0)
    parser.add_argument("--min-page-query-results", type=int, default=0)
    parser.add_argument("--min-ata-query-results", type=int, default=0)
    parser.add_argument("--require-graph-nodes", action="store_true")
    parser.add_argument("--require-graph-edges", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    thresholds = QualityThresholds(
        min_query_records=args.min_query_records,
        min_page_results=args.min_page_results,
        min_source_resolved_results=args.min_source_resolved_results,
        min_part_query_results=args.min_part_query_results,
        min_page_query_results=args.min_page_query_results,
        min_ata_query_results=args.min_ata_query_results,
        require_graph_nodes=args.require_graph_nodes,
        require_graph_edges=args.require_graph_edges,
        require_no_answer_permission=args.require_no_answer_permission,
    )
    report = build_graph_query_helper(
        graph_nodes_path=args.graph_nodes,
        graph_edges_path=args.graph_edges,
        dublin_core_source_package_extension=args.dublin_core_source_package_extension,
        leiden_navigation_metadata_bridge=args.leiden_navigation_metadata_bridge,
        part_numbers=args.part_number,
        page_ids=args.page_id,
        ata_codes=args.ata_code,
        max_results_per_query=args.max_results_per_query,
        output_dir=args.output_dir,
        thresholds=thresholds,
        write_quality=args.quality,
    )
    print_summary(report)
    return 0 if report.get("quality_status") == "PASS" else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
