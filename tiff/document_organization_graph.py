"""Build graph-style organization objects from exported document organization JSON.

This module is intentionally read-only. It consumes the existing organization export
files and writes graph nodes/edges that a future API/UI can browse without knowing
raw SQLite table shapes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Any

REQUIRED_EXPORT_FILES = (
    "organization_summary.json",
    "page_index.json",
    "part_tree.json",
    "ata_tree.json",
    "manual_ata_tree.json",
)

GRAPH_NODES_FILE = "graph_nodes.json"
GRAPH_EDGES_FILE = "graph_edges.json"
GRAPH_SUMMARY_FILE = "graph_summary.json"


@dataclass
class GraphBuildResult:
    status: str
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    summary: dict[str, Any]
    warnings: list[str] = field(default_factory=list)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")


def _norm_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _slug(value: Any) -> str:
    text = _norm_text(value).lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = text.strip("_")
    return text or "unknown"


def _node_id(node_type: str, raw_id: Any) -> str:
    return f"{node_type}:{_slug(raw_id)}"


def _edge_id(edge_type: str, source: str, target: str) -> str:
    return f"edge:{_slug(edge_type)}:{_slug(source)}:{_slug(target)}"


def _first_nonempty(row: dict[str, Any], keys: tuple[str, ...], default: Any = None) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, "", [], {}):
            return value
    return default


def _as_records(value: Any, likely_id_keys: tuple[str, ...] = ("id",)) -> list[dict[str, Any]]:
    """Return a best-effort list of records from common JSON shapes.

    Supported shapes:
      * list[dict]
      * {"pages": [...]} / {"parts": [...]} / {"items": [...]}
      * {"id": {...}, "id2": {...}}
    """
    if value is None:
        return []
    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict)]
    if not isinstance(value, dict):
        return []

    for key in (
        "items",
        "records",
        "manuals",
        "documents",
        "pages",
        "parts",
        "atas",
        "ata_groups",
        "sections",
        "tree",
    ):
        child = value.get(key)
        if isinstance(child, list):
            return [x for x in child if isinstance(x, dict)]
        if isinstance(child, dict):
            return _as_records(child, likely_id_keys=likely_id_keys)

    records: list[dict[str, Any]] = []
    for map_key, map_value in value.items():
        if isinstance(map_value, dict):
            record = dict(map_value)
            if not any(record.get(k) for k in likely_id_keys):
                # Use the map key as the first preferred id key.
                record[likely_id_keys[0]] = map_key
            records.append(record)
    return records


def _nested_page_records(record: dict[str, Any]) -> list[dict[str, Any]]:
    pages = _first_nonempty(record, ("pages", "source_pages", "page_ids"), [])
    if isinstance(pages, list):
        out: list[dict[str, Any]] = []
        for item in pages:
            if isinstance(item, dict):
                out.append(item)
            elif isinstance(item, str):
                out.append({"page_id": item})
        return out
    if isinstance(pages, dict):
        return _as_records(pages, likely_id_keys=("page_id", "id"))
    return []


def _read_export_files(export_dir: Path, strict: bool = False) -> tuple[dict[str, Any], list[str]]:
    data: dict[str, Any] = {}
    warnings: list[str] = []
    for name in REQUIRED_EXPORT_FILES:
        path = export_dir / name
        if not path.exists():
            msg = f"missing export file: {path}"
            if strict:
                raise FileNotFoundError(msg)
            warnings.append(msg)
            data[name] = {}
            continue
        data[name] = load_json(path)
    return data, warnings


def _add_node(nodes: dict[str, dict[str, Any]], node_id: str, node_type: str, label: str, properties: dict[str, Any] | None = None) -> None:
    existing = nodes.get(node_id)
    clean_properties = {k: v for k, v in (properties or {}).items() if v not in (None, "")}
    if existing:
        existing.setdefault("properties", {}).update(clean_properties)
        if label and not existing.get("label"):
            existing["label"] = label
        return
    nodes[node_id] = {
        "id": node_id,
        "type": node_type,
        "label": label or node_id,
        "properties": clean_properties,
    }


def _add_edge(
    edges: dict[str, dict[str, Any]],
    edge_type: str,
    source: str,
    target: str,
    properties: dict[str, Any] | None = None,
) -> None:
    if not source or not target or source == target:
        return
    edge_id = _edge_id(edge_type, source, target)
    if edge_id in edges:
        edges[edge_id].setdefault("properties", {}).update({k: v for k, v in (properties or {}).items() if v not in (None, "")})
        return
    edges[edge_id] = {
        "id": edge_id,
        "type": edge_type,
        "from": source,
        "to": target,
        "properties": {k: v for k, v in (properties or {}).items() if v not in (None, "")},
    }


def _extract_pages(page_index: Any) -> list[dict[str, Any]]:
    return _as_records(page_index, likely_id_keys=("page_id", "id"))


def _extract_parts(part_tree: Any) -> list[dict[str, Any]]:
    return _as_records(part_tree, likely_id_keys=("part_number", "part", "id"))


def _extract_ata_groups(ata_tree: Any) -> list[dict[str, Any]]:
    return _as_records(ata_tree, likely_id_keys=("ata_code", "ata", "code", "id"))


def _page_key(page: dict[str, Any]) -> str:
    return _norm_text(_first_nonempty(page, ("page_id", "id", "page"), ""))


def _manual_identity(row: dict[str, Any]) -> tuple[str, str]:
    manual_id = _norm_text(_first_nonempty(row, ("manual_id", "document_id", "manual", "object_id"), ""))
    manual_label = _norm_text(_first_nonempty(row, ("manual", "manual_title", "title", "publication_number", "document_title"), ""))
    if not manual_id and manual_label:
        manual_id = manual_label
    if not manual_label and manual_id:
        manual_label = manual_id
    if not manual_id:
        manual_id = "library"
    if not manual_label:
        manual_label = "Library"
    return manual_id, manual_label


def build_graph_from_export(export_dir: str | Path, strict: bool = False) -> GraphBuildResult:
    export_path = Path(export_dir)
    data, warnings = _read_export_files(export_path, strict=strict)

    page_records = _extract_pages(data.get("page_index.json"))
    part_records = _extract_parts(data.get("part_tree.json"))
    ata_records = _extract_ata_groups(data.get("ata_tree.json"))
    summary_obj = data.get("organization_summary.json") if isinstance(data.get("organization_summary.json"), dict) else {}

    if strict and not page_records:
        raise ValueError("page_index export did not contain any pages")

    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[str, dict[str, Any]] = {}

    page_by_id: dict[str, dict[str, Any]] = {}
    pages_by_ata: dict[tuple[str, str], list[str]] = {}

    for page in page_records:
        page_id = _page_key(page)
        if not page_id:
            warnings.append("skipped page with no page_id")
            continue
        manual_id, manual_label = _manual_identity(page)
        ata_code = _norm_text(_first_nonempty(page, ("ata_code", "ata", "section_code"), "unknown")) or "unknown"
        page_label = _norm_text(_first_nonempty(page, ("page_label", "label", "page_number"), page_id))
        source_url = _norm_text(_first_nonempty(page, ("source_url", "rescarta_url", "source", "url"), ""))
        tiff_path = _norm_text(_first_nonempty(page, ("tiff_path", "tiff", "tiff_file", "image_path"), ""))
        ocr_path = _norm_text(_first_nonempty(page, ("ocr_path", "ocr", "ocr_file", "text_path"), ""))
        empty_ocr = bool(_first_nonempty(page, ("empty_ocr", "is_empty_ocr", "ocr_empty"), False))

        document_node = _node_id("document", manual_id)
        page_node = _node_id("page", page_id)
        ata_node = _node_id("ata_section", f"{manual_id}:{ata_code}")
        source_node = _node_id("source_link", page_id)

        _add_node(nodes, document_node, "document", manual_label, {"manual_id": manual_id, "title": manual_label})
        _add_node(
            nodes,
            page_node,
            "page",
            f"{manual_label} page {page_label}",
            {
                "page_id": page_id,
                "page_label": page_label,
                "ata_code": ata_code,
                "manual_id": manual_id,
                "manual": manual_label,
                "source_url": source_url,
                "tiff_path": tiff_path,
                "ocr_path": ocr_path,
                "empty_ocr": empty_ocr,
            },
        )
        _add_node(nodes, ata_node, "ata_section", f"ATA {ata_code}", {"ata_code": ata_code, "manual_id": manual_id, "manual": manual_label})
        _add_node(nodes, source_node, "source_link", f"source for {page_id}", {"source_url": source_url, "tiff_path": tiff_path, "ocr_path": ocr_path})

        _add_edge(edges, "HAS_PAGE", document_node, page_node, {"sequence": _first_nonempty(page, ("sequence", "sequence_number"), None)})
        _add_edge(edges, "BELONGS_TO_DOCUMENT", page_node, document_node)
        _add_edge(edges, "HAS_ATA_SECTION", document_node, ata_node)
        _add_edge(edges, "BELONGS_TO_ATA", page_node, ata_node)
        _add_edge(edges, "CONTAINS_PAGE", ata_node, page_node)
        _add_edge(edges, "HAS_SOURCE_LINK", page_node, source_node)
        _add_edge(edges, "OPENS", source_node, page_node)

        if tiff_path:
            tiff_node = _node_id("source_file", f"tiff:{tiff_path}")
            _add_node(nodes, tiff_node, "source_file", Path(tiff_path).name, {"role": "tiff", "path": tiff_path})
            _add_edge(edges, "HAS_TIFF", page_node, tiff_node)
            _add_edge(edges, "POINTS_TO_TIFF", source_node, tiff_node)
        if ocr_path:
            ocr_node = _node_id("source_file", f"ocr:{ocr_path}")
            _add_node(nodes, ocr_node, "source_file", Path(ocr_path).name, {"role": "ocr", "path": ocr_path, "empty": empty_ocr})
            _add_edge(edges, "HAS_OCR", page_node, ocr_node)
            _add_edge(edges, "POINTS_TO_OCR", source_node, ocr_node)

        page_by_id[page_id] = page
        pages_by_ata.setdefault((manual_id, ata_code), []).append(page_id)

    # Add or enrich ATA groups from ata_tree. This handles groups with page/part counts.
    for ata in ata_records:
        ata_code = _norm_text(_first_nonempty(ata, ("ata_code", "ata", "code", "id"), ""))
        if not ata_code:
            continue
        manual_id, manual_label = _manual_identity(ata)
        ata_node = _node_id("ata_section", f"{manual_id}:{ata_code}")
        _add_node(
            nodes,
            ata_node,
            "ata_section",
            f"ATA {ata_code}",
            {
                "ata_code": ata_code,
                "manual_id": manual_id,
                "manual": manual_label,
                "page_count": _first_nonempty(ata, ("page_count", "pages_count", "pages"), None),
                "part_count": _first_nonempty(ata, ("part_count", "parts_count", "parts"), None),
            },
        )
        document_node = _node_id("document", manual_id)
        _add_node(nodes, document_node, "document", manual_label, {"manual_id": manual_id, "title": manual_label})
        _add_edge(edges, "HAS_ATA_SECTION", document_node, ata_node)

    # Add parts and mention nodes using clean exported part tree.
    for part in part_records:
        part_number = _norm_text(_first_nonempty(part, ("part_number", "part", "id"), ""))
        if not part_number:
            warnings.append("skipped part with no part_number")
            continue
        nomenclature = _norm_text(_first_nonempty(part, ("nomenclature", "canonical_nomenclature", "name", "title"), ""))
        part_node = _node_id("part", part_number)
        _add_node(
            nodes,
            part_node,
            "part",
            part_number,
            {
                "part_number": part_number,
                "nomenclature": nomenclature,
                "page_count": _first_nonempty(part, ("page_count", "pages_count", "pages"), None),
                "mention_count": _first_nonempty(part, ("mention_count", "mentions", "mentions_count"), None),
            },
        )
        if nomenclature:
            nomen_node = _node_id("nomenclature", nomenclature)
            _add_node(nodes, nomen_node, "nomenclature", nomenclature, {"text": nomenclature})
            _add_edge(edges, "HAS_NOMENCLATURE", part_node, nomen_node)

        for page_ref in _nested_page_records(part):
            page_id = _page_key(page_ref)
            if not page_id:
                continue
            page_node = _node_id("page", page_id)
            if page_node not in nodes:
                # Keep a stub so graph remains connected even if page tree and part tree disagree.
                _add_node(nodes, page_node, "page", page_id, {"page_id": page_id, "stub": True})
            mention_node = _node_id("part_mention", f"{part_number}:{page_id}")
            _add_node(
                nodes,
                mention_node,
                "part_mention",
                f"{part_number} on {page_id}",
                {
                    "part_number": part_number,
                    "page_id": page_id,
                    "nomenclature": nomenclature,
                    "source_url": _first_nonempty(page_ref, ("source_url", "rescarta_url", "source"), None),
                },
            )
            _add_edge(edges, "HAS_MENTION", part_node, mention_node)
            _add_edge(edges, "REFERS_TO_PART", mention_node, part_node)
            _add_edge(edges, "FOUND_ON", mention_node, page_node)
            _add_edge(edges, "HAS_PART_MENTION", page_node, mention_node)
            _add_edge(edges, "MENTIONS_PART", page_node, part_node)
            _add_edge(edges, "APPEARS_ON", part_node, page_node)

    nodes_list = sorted(nodes.values(), key=lambda x: (x["type"], x["id"]))
    edges_list = sorted(edges.values(), key=lambda x: (x["type"], x["from"], x["to"]))

    node_counts: dict[str, int] = {}
    for node in nodes_list:
        node_counts[node["type"]] = node_counts.get(node["type"], 0) + 1
    edge_counts: dict[str, int] = {}
    for edge in edges_list:
        edge_counts[edge["type"]] = edge_counts.get(edge["type"], 0) + 1

    summary = {
        "status": "OK" if page_records and nodes_list else "NEEDS_ATTENTION",
        "export_dir": str(export_path),
        "input_counts": {
            "pages": len(page_records),
            "parts": len(part_records),
            "ata_groups": len(ata_records),
        },
        "graph_counts": {
            "nodes": len(nodes_list),
            "edges": len(edges_list),
            "node_types": node_counts,
            "edge_types": edge_counts,
        },
        "source_summary": {
            "manuals": _first_nonempty(summary_obj, ("manuals", "manual_count"), node_counts.get("document", 0)),
            "pages": _first_nonempty(summary_obj, ("pages", "page_count"), len(page_records)),
            "parts": _first_nonempty(summary_obj, ("parts", "distinct_parts", "part_count"), len(part_records)),
            "part_mentions": _first_nonempty(summary_obj, ("part_mentions", "mentions"), edge_counts.get("HAS_MENTION", 0)),
        },
        "warnings": warnings,
    }
    return GraphBuildResult(status=summary["status"], nodes=nodes_list, edges=edges_list, summary=summary, warnings=warnings)


def export_graph(export_dir: str | Path, output_dir: str | Path, strict: bool = False) -> GraphBuildResult:
    result = build_graph_from_export(export_dir, strict=strict)
    output_path = Path(output_dir)
    write_json(output_path / GRAPH_NODES_FILE, {"nodes": result.nodes})
    write_json(output_path / GRAPH_EDGES_FILE, {"edges": result.edges})
    write_json(output_path / GRAPH_SUMMARY_FILE, result.summary)
    return result
