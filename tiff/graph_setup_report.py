"""Inspect the current TIFF document graph and entity-trait overlay.

This module is intentionally read-only. It loads the generated local artifacts
and produces a human-readable "character sheet" report for the currently
processed corpus.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
import json
from typing import Any, Iterable, Mapping

DEFAULT_EXPORT_DIR = Path("local_data/organization/export")
DEFAULT_GRAPH_DIR = Path("local_data/organization/graph")
DEFAULT_TRAIT_DIR = Path("local_data/organization/entity_traits")
DEFAULT_IMAGE_QUALITY_PATH = Path(
    "local_data/organization/image_recognition/page_image_recognition_quality.json"
)
DEFAULT_VISUAL_QUALITY_PATH = Path("local_data/organization/page_visual_object_quality.json")


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _safe_read_json(path: Path) -> tuple[Any, str | None]:
    if not path.exists():
        return None, f"missing artifact: {path}"
    try:
        return _read_json(path), None
    except Exception as exc:  # pragma: no cover - exact parser errors are platform dependent.
        return None, f"could not read {path}: {exc}"


def _as_records(value: Any, preferred_keys: tuple[str, ...] = ("id",)) -> list[dict[str, Any]]:
    """Return records from common JSON artifact shapes.

    Supported shapes include:
    - list[dict]
    - {"nodes": [...]} / {"edges": [...]} / {"pages": [...]} / {"items": [...]}
    - {"some_id": {...}, "other_id": {...}}
    """
    if value is None:
        return []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if not isinstance(value, dict):
        return []

    for key in (
        "nodes",
        "edges",
        "assertions",
        "entity_traits",
        "traits",
        "cards",
        "page_cards",
        "part_cards",
        "records",
        "items",
        "pages",
        "parts",
        "atas",
        "ata_groups",
        "sections",
        "documents",
        "manuals",
    ):
        child = value.get(key)
        if isinstance(child, list):
            return [item for item in child if isinstance(item, dict)]
        if isinstance(child, dict):
            return _as_records(child, preferred_keys=preferred_keys)

    records: list[dict[str, Any]] = []
    for map_key, map_value in value.items():
        if isinstance(map_value, dict):
            record = dict(map_value)
            if not any(record.get(key) for key in preferred_keys):
                record[preferred_keys[0]] = map_key
            records.append(record)
    return records


def _load_records(path: Path, preferred_keys: tuple[str, ...] = ("id",)) -> tuple[list[dict[str, Any]], str | None]:
    data, warning = _safe_read_json(path)
    if warning:
        return [], warning
    return _as_records(data, preferred_keys=preferred_keys), None


def _load_mapping(path: Path) -> tuple[dict[str, Any], str | None]:
    data, warning = _safe_read_json(path)
    if warning:
        return {}, warning
    return data if isinstance(data, dict) else {}, None


def _node_id(node: Mapping[str, Any]) -> str:
    return str(node.get("id") or node.get("node_id") or node.get("entity_id") or "").strip()


def _node_type(node: Mapping[str, Any]) -> str:
    return str(node.get("type") or node.get("node_type") or node.get("kind") or "unknown").strip() or "unknown"


def _edge_id(edge: Mapping[str, Any]) -> str:
    return str(edge.get("id") or edge.get("edge_id") or "").strip()


def _edge_type(edge: Mapping[str, Any]) -> str:
    return str(edge.get("type") or edge.get("edge_type") or edge.get("label") or "unknown").strip() or "unknown"


def _edge_from(edge: Mapping[str, Any]) -> str:
    return str(edge.get("from") or edge.get("source") or edge.get("source_id") or "").strip()


def _edge_to(edge: Mapping[str, Any]) -> str:
    return str(edge.get("to") or edge.get("target") or edge.get("target_id") or "").strip()


def _props(record: Mapping[str, Any]) -> dict[str, Any]:
    props = record.get("properties")
    return props if isinstance(props, dict) else {}


def _label(node: Mapping[str, Any]) -> str:
    props = _props(node)
    for key in ("label", "title", "name", "page_id", "part_number", "ata_code", "manual_id"):
        value = node.get(key)
        if value not in (None, ""):
            return str(value)
        value = props.get(key)
        if value not in (None, ""):
            return str(value)
    return _node_id(node)


def _summary_value(summary: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in summary and summary[key] not in (None, ""):
            return summary[key]
    nested = summary.get("summary")
    if isinstance(nested, dict):
        for key in keys:
            if key in nested and nested[key] not in (None, ""):
                return nested[key]
    return default


def _count_records_by_type(records: Iterable[Mapping[str, Any]], type_reader) -> Counter[str]:
    counts: Counter[str] = Counter()
    for record in records:
        counts[type_reader(record)] += 1
    return counts


def _sort_counter(counter: Mapping[str, int]) -> dict[str, int]:
    return dict(sorted(counter.items(), key=lambda item: (-item[1], item[0])))


def _edges_by_type(edges: Iterable[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in edges:
        grouped[_edge_type(edge)].append(dict(edge))
    return grouped


def _outgoing_targets(edges: Iterable[Mapping[str, Any]], source_id: str, edge_type: str) -> list[str]:
    out: list[str] = []
    for edge in edges:
        if _edge_type(edge) == edge_type and _edge_from(edge) == source_id:
            target = _edge_to(edge)
            if target:
                out.append(target)
    return out


def _incoming_sources(edges: Iterable[Mapping[str, Any]], target_id: str, edge_type: str) -> list[str]:
    out: list[str] = []
    for edge in edges:
        if _edge_type(edge) == edge_type and _edge_to(edge) == target_id:
            source = _edge_from(edge)
            if source:
                out.append(source)
    return out


def _pages_with_edge(edges: Iterable[Mapping[str, Any]], edge_type: str, page_side: str = "from") -> set[str]:
    pages: set[str] = set()
    for edge in edges:
        if _edge_type(edge) != edge_type:
            continue
        value = _edge_from(edge) if page_side == "from" else _edge_to(edge)
        if value.startswith("page:"):
            pages.add(value)
    return pages


def _coverage(total_pages: int, pages: set[str]) -> dict[str, Any]:
    count = len(pages)
    return {
        "count": count,
        "total": total_pages,
        "missing": max(total_pages - count, 0),
        "pct": round((count / total_pages) * 100.0, 2) if total_pages else 0.0,
    }


def _entity_id_from_record(record: Mapping[str, Any]) -> str:
    for key in ("entity_id", "owner_id", "subject_id", "page_node_id", "part_node_id", "id"):
        value = record.get(key)
        if value not in (None, ""):
            return str(value)
    page_id = record.get("page_id")
    if page_id:
        text = str(page_id)
        return text if text.startswith("page:") else f"page:{text}"
    part_number = record.get("part_number")
    if part_number:
        text = str(part_number)
        return text if text.startswith("part:") else f"part:{text}"
    return ""


def _trait_string(record: Mapping[str, Any]) -> str:
    trait_id = record.get("trait_id") or record.get("trait")
    if trait_id:
        return str(trait_id)
    key = record.get("trait_key") or record.get("key") or record.get("category")
    value = record.get("trait_value") or record.get("value")
    if key is not None and value is not None:
        return f"{key}={value}"
    if key is not None:
        return str(key)
    return ""


def _flatten_trait_list(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        out: list[str] = []
        for key, child in value.items():
            if isinstance(child, (list, tuple, set)):
                for item in child:
                    out.append(f"{key}:{item}")
            elif child not in (None, ""):
                out.append(f"{key}={child}")
        return out
    if isinstance(value, list):
        out = []
        for item in value:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, Mapping):
                text = _trait_string(item)
                if text:
                    out.append(text)
        return out
    return [str(value)]


def _card_entity_id(card: Mapping[str, Any], fallback_prefix: str) -> str:
    value = _entity_id_from_record(card)
    if value:
        return value
    for key in ("page_id", "part_number"):
        item = card.get(key)
        if item:
            text = str(item)
            return text if text.startswith(f"{fallback_prefix}:") else f"{fallback_prefix}:{text}"
    return ""


def _card_traits(card: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    direct: list[str] = []
    derived: list[str] = []
    for key in ("direct_traits", "traits", "base_traits", "inherited_traits"):
        direct.extend(_flatten_trait_list(card.get(key)))
    for key in ("derived_traits", "derived", "combo_traits"):
        derived.extend(_flatten_trait_list(card.get(key)))
    # Preserve order while de-duplicating.
    direct = list(dict.fromkeys([item for item in direct if item]))
    derived = list(dict.fromkeys([item for item in derived if item]))
    return direct, derived


def _trait_category_from_assertion(assertion: Mapping[str, Any]) -> str:
    key = assertion.get("trait_key") or assertion.get("category")
    if key:
        return str(key).split(":", 1)[0]
    trait = str(assertion.get("trait_id") or assertion.get("trait") or "")
    if trait.startswith("trait:"):
        parts = trait.split(":")
        if len(parts) >= 2:
            return parts[1]
    if ":" in trait:
        return trait.split(":", 1)[0]
    return "unknown"


def _is_derived_assertion(assertion: Mapping[str, Any]) -> bool:
    for key in ("derived", "is_derived"):
        if isinstance(assertion.get(key), bool):
            return bool(assertion[key])
    value = assertion.get("assertion_kind") or assertion.get("kind") or assertion.get("trait_kind") or assertion.get("source_type")
    return str(value).lower() in {"derived", "combo", "inferred"}


def build_current_graph_setup_report(
    *,
    export_dir: str | Path = DEFAULT_EXPORT_DIR,
    graph_dir: str | Path = DEFAULT_GRAPH_DIR,
    trait_dir: str | Path = DEFAULT_TRAIT_DIR,
    image_quality_path: str | Path = DEFAULT_IMAGE_QUALITY_PATH,
    visual_quality_path: str | Path = DEFAULT_VISUAL_QUALITY_PATH,
    expected_pages: int | None = None,
    expected_documents: int | None = None,
    sample_limit: int = 8,
) -> dict[str, Any]:
    """Build a read-only report of the current graph artifact layout."""
    export_path = Path(export_dir)
    graph_path = Path(graph_dir)
    trait_path = Path(trait_dir)

    warnings: list[str] = []

    nodes, warning = _load_records(graph_path / "graph_nodes.json", preferred_keys=("id", "node_id"))
    if warning:
        warnings.append(warning)
    edges, warning = _load_records(graph_path / "graph_edges.json", preferred_keys=("id", "edge_id"))
    if warning:
        warnings.append(warning)

    graph_summary, warning = _load_mapping(graph_path / "graph_summary.json")
    if warning:
        warnings.append(warning)

    page_index, warning = _load_records(export_path / "page_index.json", preferred_keys=("page_id", "id"))
    if warning:
        warnings.append(warning)
    part_tree, warning = _load_records(export_path / "part_tree.json", preferred_keys=("part_number", "id"))
    if warning:
        warnings.append(warning)
    ata_tree, warning = _load_records(export_path / "ata_tree.json", preferred_keys=("ata_code", "id"))
    if warning:
        warnings.append(warning)
    organization_summary, warning = _load_mapping(export_path / "organization_summary.json")
    if warning:
        warnings.append(warning)

    trait_summary, warning = _load_mapping(trait_path / "trait_graph_summary.json")
    if warning:
        warnings.append(warning)
    entity_traits, warning = _load_records(trait_path / "entity_traits.json", preferred_keys=("assertion_id", "id"))
    if warning:
        warnings.append(warning)
    trait_nodes, warning = _load_records(trait_path / "trait_graph_nodes.json", preferred_keys=("id", "node_id"))
    if warning:
        warnings.append(warning)
    trait_edges, warning = _load_records(trait_path / "trait_graph_edges.json", preferred_keys=("id", "edge_id"))
    if warning:
        warnings.append(warning)
    page_cards, warning = _load_records(trait_path / "page_character_cards.json", preferred_keys=("entity_id", "page_id", "id"))
    if warning:
        warnings.append(warning)
    part_cards, warning = _load_records(trait_path / "part_character_cards.json", preferred_keys=("entity_id", "part_number", "id"))
    if warning:
        warnings.append(warning)

    image_quality, image_warning = _load_mapping(Path(image_quality_path))
    if image_warning:
        warnings.append(image_warning)
    visual_quality, visual_warning = _load_mapping(Path(visual_quality_path))
    if visual_warning:
        warnings.append(visual_warning)

    node_by_id = {_node_id(node): node for node in nodes if _node_id(node)}
    edge_groups = _edges_by_type(edges)
    node_counts = _count_records_by_type(nodes, _node_type)
    edge_counts = _count_records_by_type(edges, _edge_type)

    page_node_ids = sorted([node_id for node_id, node in node_by_id.items() if _node_type(node) == "page"])
    total_pages = len(page_node_ids) or len(page_index)
    document_count = node_counts.get("document", 0)

    page_coverages = {
        "belongs_to_document": _coverage(total_pages, _pages_with_edge(edges, "BELONGS_TO_DOCUMENT", "from")),
        "belongs_to_ata": _coverage(total_pages, _pages_with_edge(edges, "BELONGS_TO_ATA", "from")),
        "has_source_link": _coverage(total_pages, _pages_with_edge(edges, "HAS_SOURCE_LINK", "from")),
        "has_tiff": _coverage(total_pages, _pages_with_edge(edges, "HAS_TIFF", "from")),
        "has_ocr": _coverage(total_pages, _pages_with_edge(edges, "HAS_OCR", "from")),
        "has_context": _coverage(total_pages, _pages_with_edge(edges, "HAS_CONTEXT", "from")),
        "has_part_mention": _coverage(total_pages, _pages_with_edge(edges, "HAS_PART_MENTION", "from")),
        "mentions_part": _coverage(total_pages, _pages_with_edge(edges, "MENTIONS_PART", "from")),
    }

    docs: dict[str, dict[str, Any]] = {}
    for doc_id, doc_node in sorted(node_by_id.items()):
        if _node_type(doc_node) != "document":
            continue
        pages = _outgoing_targets(edges, doc_id, "HAS_PAGE")
        atas = _outgoing_targets(edges, doc_id, "HAS_ATA_SECTION")
        docs[doc_id] = {
            "label": _label(doc_node),
            "pages": len(set(pages)),
            "ata_sections": len(set(atas)),
        }

    ata_distribution: list[dict[str, Any]] = []
    for ata_id, ata_node in sorted(node_by_id.items()):
        if _node_type(ata_node) != "ata_section":
            continue
        pages = set(_outgoing_targets(edges, ata_id, "CONTAINS_PAGE"))
        mentioned_parts: set[str] = set()
        for page_id in pages:
            mentioned_parts.update(_outgoing_targets(edges, page_id, "MENTIONS_PART"))
        ata_distribution.append(
            {
                "id": ata_id,
                "label": _label(ata_node),
                "pages": len(pages),
                "mentioned_parts": len(mentioned_parts),
            }
        )
    ata_distribution.sort(key=lambda row: (-int(row["pages"]), row["id"]))

    page_card_by_entity: dict[str, dict[str, Any]] = {}
    for card in page_cards:
        entity_id = _card_entity_id(card, "page")
        if entity_id:
            page_card_by_entity[entity_id] = card

    part_card_by_entity: dict[str, dict[str, Any]] = {}
    for card in part_cards:
        entity_id = _card_entity_id(card, "part")
        if entity_id:
            part_card_by_entity[entity_id] = card

    trait_assertions_by_entity: Counter[str] = Counter()
    derived_assertions_by_entity: Counter[str] = Counter()
    trait_categories: Counter[str] = Counter()
    for assertion in entity_traits:
        entity_id = _entity_id_from_record(assertion)
        if entity_id:
            trait_assertions_by_entity[entity_id] += 1
            if _is_derived_assertion(assertion):
                derived_assertions_by_entity[entity_id] += 1
        trait_categories[_trait_category_from_assertion(assertion)] += 1

    pages_without_traits = [page_id for page_id in page_node_ids if trait_assertions_by_entity.get(page_id, 0) == 0 and page_id not in page_card_by_entity]

    page_samples: list[dict[str, Any]] = []
    for page_id in page_node_ids[: max(sample_limit, 0)]:
        page_node = node_by_id.get(page_id, {})
        doc_targets = _outgoing_targets(edges, page_id, "BELONGS_TO_DOCUMENT")
        ata_targets = _outgoing_targets(edges, page_id, "BELONGS_TO_ATA")
        source_targets = _outgoing_targets(edges, page_id, "HAS_SOURCE_LINK")
        context_targets = _outgoing_targets(edges, page_id, "HAS_CONTEXT")
        tiff_targets = _outgoing_targets(edges, page_id, "HAS_TIFF")
        ocr_targets = _outgoing_targets(edges, page_id, "HAS_OCR")
        part_targets = _outgoing_targets(edges, page_id, "MENTIONS_PART")
        mention_targets = _outgoing_targets(edges, page_id, "HAS_PART_MENTION")
        card = page_card_by_entity.get(page_id, {})
        direct_traits, derived_traits = _card_traits(card)
        if not direct_traits and trait_assertions_by_entity.get(page_id):
            direct_traits = [f"assertions={trait_assertions_by_entity[page_id]}"]
        if not derived_traits and derived_assertions_by_entity.get(page_id):
            derived_traits = [f"derived_assertions={derived_assertions_by_entity[page_id]}"]
        page_samples.append(
            {
                "id": page_id,
                "label": _label(page_node) if page_node else page_id,
                "document": _label(node_by_id.get(doc_targets[0], {})) if doc_targets else "",
                "ata": _label(node_by_id.get(ata_targets[0], {})) if ata_targets else "",
                "source_links": len(source_targets),
                "tiff_files": len(tiff_targets),
                "ocr_files": len(ocr_targets),
                "contexts": len(context_targets),
                "part_edges": len(set(part_targets)),
                "part_mentions": len(set(mention_targets)),
                "trait_assertions": trait_assertions_by_entity.get(page_id, 0),
                "derived_assertions": derived_assertions_by_entity.get(page_id, 0),
                "direct_traits_sample": direct_traits[:4],
                "derived_traits_sample": derived_traits[:4],
            }
        )

    trait_summary_counts = trait_summary.get("counts") if isinstance(trait_summary.get("counts"), dict) else {}
    if not trait_summary_counts:
        trait_summary_counts = trait_summary.get("overlay_counts") if isinstance(trait_summary.get("overlay_counts"), dict) else {}
    if not trait_summary_counts:
        trait_summary_counts = trait_summary.get("summary") if isinstance(trait_summary.get("summary"), dict) else {}

    trait_overlay = {
        "present": bool(trait_summary or entity_traits or page_cards or part_cards),
        "status": str(_summary_value(trait_summary, "status", default="missing")).lower(),
        "nodes": int(_summary_value(trait_summary_counts, "nodes", "entity_trait_nodes", default=len(trait_nodes))),
        "edges": int(_summary_value(trait_summary_counts, "edges", "entity_trait_edges", default=len(trait_edges))),
        "assertions": int(_summary_value(trait_summary_counts, "assertions", "entity_trait_assertions", default=len(entity_traits))),
        "trait_nodes": int(_summary_value(trait_summary_counts, "trait_nodes", "entity_trait_nodes", default=0) or node_counts.get("trait", 0) or len([node for node in trait_nodes if _node_type(node) == "trait"])),
        "trait_assertion_nodes": int(_summary_value(trait_summary_counts, "trait_assertion_nodes", "entity_trait_assertion_nodes", default=len([node for node in trait_nodes if _node_type(node) == "trait_assertion"]))),
        "evidence_source_nodes": int(_summary_value(trait_summary_counts, "evidence_source_nodes", "entity_trait_evidence_source_nodes", default=len([node for node in trait_nodes if _node_type(node) == "evidence_source"]))),
        "derived_assertions": int(_summary_value(trait_summary_counts, "derived_assertions", "entity_trait_derived_assertions", default=sum(1 for assertion in entity_traits if _is_derived_assertion(assertion)))),
        "page_cards": len(page_cards),
        "part_cards": len(part_cards),
        "pages_without_traits": len(pages_without_traits),
        "trait_categories": _sort_counter(trait_categories),
    }

    image_summary = image_quality.get("summary") if isinstance(image_quality.get("summary"), dict) else image_quality
    visual_summary = visual_quality.get("summary") if isinstance(visual_quality.get("summary"), dict) else visual_quality

    quality_signals = {
        "image_recognition_status": str(_summary_value(image_quality, "status", default=_summary_value(image_summary, "status", default="missing"))).lower(),
        "image_pages_checked": _summary_value(image_summary, "page_image_pages_checked", "pages_checked", default=None),
        "image_readable_images": _summary_value(image_summary, "page_image_readable_images", "readable_images", "images_readable", default=None),
        "image_likely_visual_pages": _summary_value(image_summary, "page_image_likely_visual_pages", "likely_visual_pages", default=None),
        "visual_object_status": str(_summary_value(visual_quality, "status", default=_summary_value(visual_summary, "status", default="missing"))).lower(),
        "visual_pages_checked": _summary_value(visual_summary, "page_visual_pages_checked", "pages_checked", default=None),
        "visual_pages_with_context": _summary_value(visual_summary, "page_visual_pages_with_context", "pages_with_context", default=None),
    }

    processed_corpus = {
        "documents": document_count,
        "pages": total_pages,
        "ata_sections": node_counts.get("ata_section", len(ata_tree)),
        "parts": node_counts.get("part", len(part_tree)),
        "part_mentions": node_counts.get("part_mention", 0),
        "nomenclature_nodes": node_counts.get("nomenclature", 0),
        "source_link_nodes": node_counts.get("source_link", 0),
        "source_file_nodes": node_counts.get("source_file", 0),
        "page_context_nodes": node_counts.get("page_context", 0),
        "topic_nodes": node_counts.get("topic", 0),
        "page_index_records": len(page_index),
        "part_tree_records": len(part_tree),
        "ata_tree_records": len(ata_tree),
    }

    status = "OK" if nodes and edges else "NEEDS_ATTENTION"
    expectation_failures: list[str] = []
    if expected_pages is not None and total_pages != expected_pages:
        expectation_failures.append(f"expected {expected_pages} pages, found {total_pages}")
    if expected_documents is not None and document_count != expected_documents:
        expectation_failures.append(f"expected {expected_documents} documents, found {document_count}")
    if expectation_failures:
        status = "NEEDS_ATTENTION"
        warnings.extend(expectation_failures)

    report = {
        "status": status,
        "artifact_paths": {
            "export_dir": str(export_path),
            "graph_dir": str(graph_path),
            "trait_dir": str(trait_path),
            "image_quality_path": str(Path(image_quality_path)),
            "visual_quality_path": str(Path(visual_quality_path)),
        },
        "core_graph": {
            "nodes": len(nodes),
            "edges": len(edges),
            "node_types": _sort_counter(node_counts),
            "edge_types": _sort_counter(edge_counts),
            "graph_summary_status": str(_summary_value(graph_summary, "status", default="missing")).lower(),
        },
        "processed_corpus": processed_corpus,
        "documents": docs,
        "ata_distribution": ata_distribution,
        "page_coverage": page_coverages,
        "trait_overlay": trait_overlay,
        "quality_signals": quality_signals,
        "page_samples": page_samples,
        "warnings": warnings,
    }
    return report


def _format_count_line(key: str, value: Any, indent: int = 4) -> str:
    return f"{' ' * indent}{key}: {value}"


def _format_coverage_line(label: str, row: Mapping[str, Any], indent: int = 4) -> str:
    return (
        f"{' ' * indent}{label}: {row.get('count', 0)}/{row.get('total', 0)} "
        f"({row.get('pct', 0.0):.2f}%), missing={row.get('missing', 0)}"
    )


def format_current_graph_setup_report(report: Mapping[str, Any], *, sample_limit: int = 8, top_edge_types: int = 20) -> str:
    """Format a graph setup report for terminal/debug-test output."""
    lines: list[str] = []
    lines.append("Current TIFF document graph setup")
    lines.append(f"  Status: {report.get('status', 'UNKNOWN')}")

    paths = report.get("artifact_paths", {}) if isinstance(report.get("artifact_paths"), dict) else {}
    lines.append("  Artifact paths:")
    for key in ("export_dir", "graph_dir", "trait_dir"):
        lines.append(_format_count_line(key, paths.get(key, "")))

    corpus = report.get("processed_corpus", {}) if isinstance(report.get("processed_corpus"), dict) else {}
    lines.append("  Processed corpus:")
    for key in (
        "documents",
        "pages",
        "ata_sections",
        "parts",
        "part_mentions",
        "source_link_nodes",
        "source_file_nodes",
        "page_context_nodes",
        "topic_nodes",
    ):
        lines.append(_format_count_line(key, corpus.get(key, 0)))

    core = report.get("core_graph", {}) if isinstance(report.get("core_graph"), dict) else {}
    lines.append("  Core graph:")
    lines.append(_format_count_line("nodes", core.get("nodes", 0)))
    lines.append(_format_count_line("edges", core.get("edges", 0)))
    node_types = core.get("node_types", {}) if isinstance(core.get("node_types"), dict) else {}
    edge_types = core.get("edge_types", {}) if isinstance(core.get("edge_types"), dict) else {}
    lines.append("  Core node types:")
    for key, value in node_types.items():
        lines.append(_format_count_line(key, value))
    lines.append(f"  Core edge types, top {top_edge_types}:")
    for index, (key, value) in enumerate(edge_types.items()):
        if index >= top_edge_types:
            break
        lines.append(_format_count_line(key, value))

    documents = report.get("documents", {}) if isinstance(report.get("documents"), dict) else {}
    lines.append("  Documents:")
    if documents:
        for doc_id, row in documents.items():
            label = row.get("label", doc_id) if isinstance(row, dict) else doc_id
            pages = row.get("pages", 0) if isinstance(row, dict) else 0
            atas = row.get("ata_sections", 0) if isinstance(row, dict) else 0
            lines.append(f"    {doc_id} | label={label} | pages={pages} | ata_sections={atas}")
    else:
        lines.append("    none")

    lines.append("  Page coverage:")
    coverage = report.get("page_coverage", {}) if isinstance(report.get("page_coverage"), dict) else {}
    for key in (
        "belongs_to_document",
        "belongs_to_ata",
        "has_source_link",
        "has_tiff",
        "has_ocr",
        "has_context",
        "has_part_mention",
        "mentions_part",
    ):
        row = coverage.get(key, {}) if isinstance(coverage.get(key), dict) else {}
        lines.append(_format_coverage_line(key, row))

    ata_rows = report.get("ata_distribution", []) if isinstance(report.get("ata_distribution"), list) else []
    lines.append("  ATA distribution:")
    for row in ata_rows[:10]:
        if not isinstance(row, dict):
            continue
        lines.append(
            f"    {row.get('id', '')} | label={row.get('label', '')} | "
            f"pages={row.get('pages', 0)} | mentioned_parts={row.get('mentioned_parts', 0)}"
        )
    if not ata_rows:
        lines.append("    none")

    trait = report.get("trait_overlay", {}) if isinstance(report.get("trait_overlay"), dict) else {}
    lines.append("  Entity-trait overlay:")
    for key in (
        "present",
        "status",
        "nodes",
        "edges",
        "assertions",
        "trait_nodes",
        "trait_assertion_nodes",
        "evidence_source_nodes",
        "derived_assertions",
        "page_cards",
        "part_cards",
        "pages_without_traits",
    ):
        lines.append(_format_count_line(key, trait.get(key, 0)))
    categories = trait.get("trait_categories", {}) if isinstance(trait.get("trait_categories"), dict) else {}
    lines.append("  Trait categories:")
    for key, value in list(categories.items())[:15]:
        lines.append(_format_count_line(key, value))
    if not categories:
        lines.append("    none")

    quality = report.get("quality_signals", {}) if isinstance(report.get("quality_signals"), dict) else {}
    lines.append("  Quality/image signals:")
    for key in (
        "image_recognition_status",
        "image_pages_checked",
        "image_readable_images",
        "image_likely_visual_pages",
        "visual_object_status",
        "visual_pages_checked",
        "visual_pages_with_context",
    ):
        lines.append(_format_count_line(key, quality.get(key, "")))

    samples = report.get("page_samples", []) if isinstance(report.get("page_samples"), list) else []
    lines.append(f"  Sample page character sheets, first {min(sample_limit, len(samples))}:")
    for row in samples[:sample_limit]:
        if not isinstance(row, dict):
            continue
        lines.append(
            f"    {row.get('id', '')} | doc={row.get('document', '')} | ata={row.get('ata', '')} | "
            f"source={row.get('source_links', 0)} | tiff={row.get('tiff_files', 0)} | "
            f"ocr={row.get('ocr_files', 0)} | context={row.get('contexts', 0)} | "
            f"parts={row.get('part_edges', 0)} | mentions={row.get('part_mentions', 0)} | "
            f"traits={row.get('trait_assertions', 0)} | derived={row.get('derived_assertions', 0)}"
        )
        direct = row.get("direct_traits_sample") or []
        derived = row.get("derived_traits_sample") or []
        if direct:
            lines.append(f"      direct: {', '.join(str(x) for x in direct)}")
        if derived:
            lines.append(f"      derived: {', '.join(str(x) for x in derived)}")

    warnings = report.get("warnings", []) if isinstance(report.get("warnings"), list) else []
    if warnings:
        lines.append("  Warnings:")
        for warning in warnings:
            lines.append(f"    {warning}")

    return "\n".join(lines)


def write_graph_setup_report_json(report: Mapping[str, Any], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return path
