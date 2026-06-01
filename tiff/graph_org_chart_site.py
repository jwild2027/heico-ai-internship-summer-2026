"""Build an interactive organization-chart style viewer for the TIFF graph.

The viewer is intentionally static: it reads generated local artifacts and writes
HTML/JSON files that can be opened in a browser or served with
``python -m http.server``.  It does not mutate the graph or require a web server.
"""
from __future__ import annotations

import html
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, MutableMapping, Sequence


DEFAULT_EXPORT_DIR = Path("local_data/organization/export")
DEFAULT_GRAPH_DIR = Path("local_data/organization/graph")
DEFAULT_TRAIT_DIR = Path("local_data/organization/entity_traits")
DEFAULT_IMAGE_RECOGNITION_DIR = Path("local_data/organization/image_recognition")
DEFAULT_ORG_DIR = Path("local_data/organization")
DEFAULT_OUTPUT_DIR = Path("local_data/organization/org_chart_site")


@dataclass(frozen=True)
class OrgChartPaths:
    """Input/output paths used by the org-chart site builder."""

    export_dir: Path = DEFAULT_EXPORT_DIR
    graph_dir: Path = DEFAULT_GRAPH_DIR
    trait_dir: Path = DEFAULT_TRAIT_DIR
    image_recognition_dir: Path = DEFAULT_IMAGE_RECOGNITION_DIR
    organization_dir: Path = DEFAULT_ORG_DIR
    output_dir: Path = DEFAULT_OUTPUT_DIR

    @classmethod
    def from_strings(
        cls,
        export_dir: str | Path = DEFAULT_EXPORT_DIR,
        graph_dir: str | Path = DEFAULT_GRAPH_DIR,
        trait_dir: str | Path = DEFAULT_TRAIT_DIR,
        image_recognition_dir: str | Path = DEFAULT_IMAGE_RECOGNITION_DIR,
        organization_dir: str | Path = DEFAULT_ORG_DIR,
        output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    ) -> "OrgChartPaths":
        return cls(
            export_dir=Path(export_dir),
            graph_dir=Path(graph_dir),
            trait_dir=Path(trait_dir),
            image_recognition_dir=Path(image_recognition_dir),
            organization_dir=Path(organization_dir),
            output_dir=Path(output_dir),
        )


def _load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _first_mapping_value(mapping: Mapping[str, Any], keys: Sequence[str], default: Any = None) -> Any:
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return default


def _strip_entity_prefix(value: Any) -> str:
    text = str(value or "").strip()
    for prefix in ("page:", "part:", "document:", "ata_section:", "source_link:", "source_file:"):
        if text.startswith(prefix):
            return text[len(prefix) :]
    return text


def _normalize_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "y", "1", "ok"}:
            return True
        if lowered in {"false", "no", "n", "0", "none", "null"}:
            return False
    return None


def _records_from_any(value: Any, preferred_keys: Sequence[str]) -> list[dict[str, Any]]:
    """Return a list of records from common JSON artifact shapes.

    Supported shapes:
    - list[dict]
    - dict containing one of preferred_keys as list/dict
    - dict keyed by id with record values
    """
    if isinstance(value, list):
        return [record for record in value if isinstance(record, dict)]
    if not isinstance(value, dict):
        return []

    for key in preferred_keys:
        child = value.get(key)
        if isinstance(child, list):
            return [record for record in child if isinstance(record, dict)]
        if isinstance(child, dict):
            out: list[dict[str, Any]] = []
            for child_key, child_value in child.items():
                if isinstance(child_value, dict):
                    record = dict(child_value)
                    record.setdefault("id", child_key)
                    record.setdefault("page_id", child_key if "page" in key else record.get("page_id"))
                    record.setdefault("part_number", child_key if "part" in key else record.get("part_number"))
                    out.append(record)
            return out

    # Treat a plain mapping of id -> record as records.
    if all(isinstance(v, dict) for v in value.values()):
        out = []
        for child_key, child_value in value.items():
            record = dict(child_value)
            record.setdefault("id", child_key)
            out.append(record)
        return out

    return []


def _node_type(record: Mapping[str, Any]) -> str:
    value = _first_mapping_value(record, ("node_type", "type", "kind", "label"), "unknown")
    return str(value or "unknown")


def _edge_type(record: Mapping[str, Any]) -> str:
    value = _first_mapping_value(record, ("edge_type", "type", "kind", "label", "relationship"), "unknown")
    return str(value or "unknown")


def _safe_text(value: Any, max_len: int = 220) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    if len(text) > max_len:
        return text[: max_len - 1].rstrip() + "…"
    return text


def _stringify_trait(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Mapping):
        key = _first_mapping_value(value, ("trait_key", "key", "name", "type", "trait_type"), "trait")
        trait_value = _first_mapping_value(value, ("trait_value", "value", "label"), None)
        if trait_value not in (None, ""):
            return f"{key}={trait_value}"
        return str(key)
    return str(value).strip()


def _listify_traits(*values: Any) -> list[str]:
    traits: list[str] = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, str):
            if value.strip():
                traits.append(value.strip())
            continue
        if isinstance(value, Mapping):
            # Dictionaries can be either trait records or key/value buckets.
            if any(k in value for k in ("trait_key", "trait_value", "key", "value", "name")):
                trait = _stringify_trait(value)
                if trait:
                    traits.append(trait)
            else:
                for child_key, child_value in value.items():
                    if isinstance(child_value, (list, tuple, set)):
                        for item in child_value:
                            traits.append(f"{child_key}={_stringify_trait(item)}")
                    elif isinstance(child_value, Mapping):
                        traits.append(f"{child_key}:{_stringify_trait(child_value)}")
                    elif child_value not in (None, ""):
                        traits.append(f"{child_key}={child_value}")
            continue
        if isinstance(value, (list, tuple, set)):
            for item in value:
                trait = _stringify_trait(item)
                if trait:
                    traits.append(trait)
            continue
        trait = _stringify_trait(value)
        if trait:
            traits.append(trait)

    # Stable de-duplication while preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for trait in traits:
        if trait and trait not in seen:
            out.append(trait)
            seen.add(trait)
    return out


def _extract_role(card: Mapping[str, Any], traits: Sequence[str]) -> str:
    roles = _as_dict(card.get("roles"))
    context = _as_dict(card.get("context"))
    role = _first_mapping_value(
        card,
        ("page_role", "role", "context_role", "document_role", "page_type"),
        None,
    )
    role = role or _first_mapping_value(roles, ("context_role", "page_role", "role", "primary_role"), None)
    role = role or _first_mapping_value(context, ("page_role", "role", "primary_role"), None)
    if role:
        return str(role)

    for trait in traits:
        text = trait.lower()
        for token in ("page_role=", "role=", "context:page_role="):
            if token in text:
                return trait.split("=", 1)[-1].strip()
    return "unknown"


def _extract_image_classes(card: Mapping[str, Any], traits: Sequence[str]) -> list[str]:
    roles = _as_dict(card.get("roles"))
    values = []
    for key in (
        "image_class",
        "image_classes",
        "visual_class",
        "visual_classes",
        "image_recognition_class",
        "classification",
    ):
        if key in card:
            values.append(card[key])
        if key in roles:
            values.append(roles[key])

    image_classes = _listify_traits(*values)
    for trait in traits:
        lower = trait.lower()
        if "image_class=" in lower or "visual_class=" in lower or "classification=" in lower:
            image_classes.append(trait.split("=", 1)[-1].strip())
        elif lower.startswith("visual:") or lower.startswith("image:"):
            image_classes.append(trait)
    seen: set[str] = set()
    out: list[str] = []
    for item in image_classes:
        if item and item not in seen:
            out.append(item)
            seen.add(item)
    return out


def _extract_source(card: Mapping[str, Any]) -> dict[str, Any]:
    source = dict(_as_dict(card.get("source")))
    for source_key, possible in {
        "source_url": ("source_url", "url", "rescarta_url", "source_link", "local_url"),
        "tiff_path": ("tiff_path", "source_tiff_path", "image_path", "image_file", "tiff_file"),
        "ocr_path": ("ocr_path", "source_ocr_path", "ocr_file", "text_path"),
    }.items():
        source.setdefault(source_key, _first_mapping_value(card, possible, None))
    return {key: value for key, value in source.items() if value not in (None, "")}


def _extract_parts(card: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = _first_mapping_value(card, ("parts", "part_mentions", "mentioned_parts", "part_numbers"), [])
    parts: list[dict[str, Any]] = []
    if isinstance(raw, Mapping):
        iterable: Iterable[Any] = raw.values()
    elif isinstance(raw, (list, tuple, set)):
        iterable = raw
    else:
        iterable = [raw] if raw else []

    for item in iterable:
        if isinstance(item, Mapping):
            number = _first_mapping_value(
                item,
                ("part_number", "part_number_display", "part", "id", "value", "number"),
                "",
            )
            parts.append(
                {
                    "part_number": _strip_entity_prefix(number),
                    "nomenclature": _first_mapping_value(item, ("nomenclature", "name", "description", "title"), ""),
                    "item_number": _first_mapping_value(item, ("item_number", "item", "ipl_item"), ""),
                    "quantity": _first_mapping_value(item, ("quantity", "qty"), ""),
                }
            )
        elif item:
            parts.append({"part_number": _strip_entity_prefix(item), "nomenclature": "", "item_number": "", "quantity": ""})

    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for part in parts:
        number = str(part.get("part_number") or "").strip()
        if not number or number in seen:
            continue
        out.append(part)
        seen.add(number)
    return out


def _extract_summary(card: Mapping[str, Any]) -> str:
    context = _as_dict(card.get("context"))
    return _safe_text(
        _first_mapping_value(
            card,
            ("summary", "page_summary", "context_summary", "description", "text"),
            _first_mapping_value(context, ("summary", "page_summary", "description", "text"), ""),
        ),
        max_len=600,
    )


def _normalize_page_card(card: Mapping[str, Any], fallback_page_id: str | None = None) -> dict[str, Any] | None:
    page_id = _first_mapping_value(
        card,
        ("page_id", "id", "entity_id", "node_id", "page", "page_key"),
        fallback_page_id,
    )
    if not page_id:
        return None
    clean_page_id = _strip_entity_prefix(page_id)
    document = _first_mapping_value(
        card,
        ("document", "document_title", "manual", "manual_title", "publication_number", "document_id", "manual_id"),
        "Document 1",
    )
    document_id = _strip_entity_prefix(
        _first_mapping_value(card, ("document_id", "manual_id", "document_node_id"), document)
    )
    ata_code = str(_first_mapping_value(card, ("ata_code", "ata", "ata_section", "ata_id"), "unknown") or "unknown")
    ata_title = str(_first_mapping_value(card, ("ata_title", "ata_name", "section_title"), "") or "")
    sequence = _first_mapping_value(card, ("page_sequence", "sequence", "page_number", "page_index"), None)
    page_label = str(_first_mapping_value(card, ("page_label", "label", "sheet", "page_display"), sequence or clean_page_id) or clean_page_id)

    direct_traits = _listify_traits(
        card.get("direct_traits"),
        card.get("traits"),
        card.get("trait_keys"),
        card.get("role_traits"),
        card.get("visual_traits"),
    )
    derived_traits = _listify_traits(card.get("derived_traits"), card.get("derived"), card.get("combo_traits"))
    all_traits = _listify_traits(direct_traits, derived_traits)
    role = _extract_role(card, all_traits)
    image_classes = _extract_image_classes(card, all_traits)

    signals = dict(_as_dict(card.get("signals")))
    for key in ("has_ocr", "has_context", "has_source_url", "has_tiff", "source_traceable"):
        if key in card and key not in signals:
            signals[key] = card[key]
    if "ink_ratio" not in signals:
        ink_ratio = _first_mapping_value(card, ("ink_ratio", "avg_ink_ratio", "average_ink_ratio"), None)
        if ink_ratio not in (None, ""):
            signals["ink_ratio"] = ink_ratio

    return {
        "page_id": clean_page_id,
        "entity_id": str(page_id),
        "document": str(document or "Document 1"),
        "document_id": document_id or str(document or "Document 1"),
        "ata_code": ata_code,
        "ata_title": ata_title,
        "page_label": page_label,
        "page_sequence": sequence,
        "role": role,
        "image_classes": image_classes,
        "summary": _extract_summary(card),
        "source": _extract_source(card),
        "parts": _extract_parts(card),
        "direct_traits": direct_traits,
        "derived_traits": derived_traits,
        "traits": all_traits,
        "signals": signals,
        "raw_keys": sorted(str(key) for key in card.keys()),
    }


def _page_cards_from_page_index(page_index: Any) -> list[dict[str, Any]]:
    records = _records_from_any(page_index, ("pages", "page_index", "records", "items"))
    out: list[dict[str, Any]] = []
    for record in records:
        page_id = _first_mapping_value(record, ("page_id", "id", "page", "node_id"), None)
        normalized = _normalize_page_card(record, fallback_page_id=str(page_id or ""))
        if normalized:
            out.append(normalized)
    return out


def _load_page_cards(paths: OrgChartPaths) -> tuple[list[dict[str, Any]], str]:
    page_cards_path = paths.trait_dir / "page_character_cards.json"
    raw_page_cards = _load_json(page_cards_path, None)
    records = _records_from_any(raw_page_cards, ("pages", "page_cards", "cards", "records", "items"))
    if records:
        page_cards = []
        for record in records:
            fallback = str(record.get("id") or "") if isinstance(record, dict) else ""
            normalized = _normalize_page_card(record, fallback_page_id=fallback)
            if normalized:
                page_cards.append(normalized)
        if page_cards:
            return page_cards, str(page_cards_path)

    page_index_path = paths.export_dir / "page_index.json"
    page_cards = _page_cards_from_page_index(_load_json(page_index_path, None))
    return page_cards, str(page_index_path)


def _load_part_cards(paths: OrgChartPaths) -> tuple[list[dict[str, Any]], str]:
    part_cards_path = paths.trait_dir / "part_character_cards.json"
    raw_part_cards = _load_json(part_cards_path, None)
    records = _records_from_any(raw_part_cards, ("parts", "part_cards", "cards", "records", "items"))
    if not records:
        part_tree_path = paths.export_dir / "part_tree.json"
        records = _records_from_any(_load_json(part_tree_path, None), ("parts", "part_tree", "records", "items"))
        source_path = str(part_tree_path)
    else:
        source_path = str(part_cards_path)

    out: list[dict[str, Any]] = []
    for record in records:
        number = _strip_entity_prefix(
            _first_mapping_value(record, ("part_number", "part_number_display", "id", "entity_id", "number"), "")
        )
        if not number:
            continue
        page_refs = _first_mapping_value(record, ("pages", "page_ids", "appearances", "mentions"), [])
        pages: list[str] = []
        if isinstance(page_refs, Mapping):
            pages = [_strip_entity_prefix(key) for key in page_refs.keys()]
        elif isinstance(page_refs, (list, tuple, set)):
            for item in page_refs:
                if isinstance(item, Mapping):
                    page_id = _first_mapping_value(item, ("page_id", "id", "page"), "")
                    if page_id:
                        pages.append(_strip_entity_prefix(page_id))
                elif item:
                    pages.append(_strip_entity_prefix(item))
        out.append(
            {
                "part_number": number,
                "nomenclature": _first_mapping_value(record, ("nomenclature", "name", "description", "title"), ""),
                "pages": sorted(set(pages)),
                "traits": _listify_traits(record.get("traits"), record.get("derived_traits")),
            }
        )
    return out, source_path


def _attach_parts_from_part_cards(page_cards: list[dict[str, Any]], part_cards: Sequence[Mapping[str, Any]]) -> None:
    by_page = {page["page_id"]: page for page in page_cards}
    existing: dict[str, set[str]] = {
        page["page_id"]: {str(part.get("part_number")) for part in page.get("parts", []) if part.get("part_number")}
        for page in page_cards
    }
    for part in part_cards:
        number = str(part.get("part_number") or "").strip()
        if not number:
            continue
        for page_id in _as_list(part.get("pages")):
            clean_page_id = _strip_entity_prefix(page_id)
            page = by_page.get(clean_page_id)
            if not page:
                continue
            if number in existing.setdefault(clean_page_id, set()):
                continue
            page.setdefault("parts", []).append(
                {
                    "part_number": number,
                    "nomenclature": part.get("nomenclature", ""),
                    "item_number": "",
                    "quantity": "",
                }
            )
            existing[clean_page_id].add(number)


def _summarize_json_status(raw: Any) -> dict[str, Any]:
    data = _as_dict(raw)
    summary = _as_dict(data.get("summary"))
    status = data.get("status") or summary.get("status")
    out: dict[str, Any] = {}
    if status:
        out["status"] = str(status).lower()
    for key, value in summary.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            out[key] = value
    for key, value in data.items():
        if key == "summary":
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            out.setdefault(key, value)
    return out


def _artifact_overview(paths: OrgChartPaths) -> dict[str, Any]:
    graph_nodes = _records_from_any(_load_json(paths.graph_dir / "graph_nodes.json", []), ("nodes", "records", "items"))
    graph_edges = _records_from_any(_load_json(paths.graph_dir / "graph_edges.json", []), ("edges", "records", "items"))
    node_types = Counter(_node_type(node) for node in graph_nodes)
    edge_types = Counter(_edge_type(edge) for edge in graph_edges)

    trait_summary = _summarize_json_status(_load_json(paths.trait_dir / "trait_graph_summary.json", {}))
    entity_trait_quality = _summarize_json_status(_load_json(paths.trait_dir / "entity_trait_quality.json", {}))
    page_image_quality = _summarize_json_status(
        _load_json(paths.image_recognition_dir / "page_image_recognition_quality.json", {})
    )
    page_visual_quality = _summarize_json_status(
        _load_json(paths.organization_dir / "page_visual_object_quality.json", {})
    )
    organization_summary = _summarize_json_status(_load_json(paths.export_dir / "organization_summary.json", {}))

    return {
        "graph_nodes": len(graph_nodes),
        "graph_edges": len(graph_edges),
        "node_types": dict(sorted(node_types.items())),
        "edge_types": dict(sorted(edge_types.items())),
        "trait_summary": trait_summary,
        "entity_trait_quality": entity_trait_quality,
        "page_image_quality": page_image_quality,
        "page_visual_quality": page_visual_quality,
        "organization_summary": organization_summary,
    }


def _sort_key(value: Any) -> tuple[int, str]:
    text = str(value or "")
    try:
        return (0, f"{int(text):010d}")
    except ValueError:
        return (1, text)


def _page_sort_key(page: Mapping[str, Any]) -> tuple[Any, ...]:
    sequence = page.get("page_sequence")
    if sequence not in (None, ""):
        try:
            return (0, int(sequence), page.get("page_id", ""))
        except (TypeError, ValueError):
            pass
    return (1, str(page.get("page_label") or ""), str(page.get("page_id") or ""))


def build_org_chart_data(paths: OrgChartPaths | None = None) -> dict[str, Any]:
    """Read local artifacts and return a browser-friendly graph view model."""
    paths = paths or OrgChartPaths()
    page_cards, page_source_path = _load_page_cards(paths)
    part_cards, part_source_path = _load_part_cards(paths)
    _attach_parts_from_part_cards(page_cards, part_cards)

    # Keep deterministic order and remove duplicate page ids.
    deduped_pages: dict[str, dict[str, Any]] = {}
    for page in page_cards:
        page_id = str(page.get("page_id") or "").strip()
        if not page_id:
            continue
        if page_id in deduped_pages:
            # Merge parts/traits from duplicate records if they appear.
            current = deduped_pages[page_id]
            for key in ("parts", "direct_traits", "derived_traits", "traits", "image_classes"):
                merged = _listify_traits(current.get(key), page.get(key)) if key != "parts" else None
                if key == "parts":
                    seen = {part.get("part_number") for part in current.get("parts", [])}
                    for part in page.get("parts", []):
                        if part.get("part_number") not in seen:
                            current.setdefault("parts", []).append(part)
                            seen.add(part.get("part_number"))
                else:
                    current[key] = merged
            continue
        deduped_pages[page_id] = page
    pages = sorted(deduped_pages.values(), key=_page_sort_key)

    role_counts = Counter(str(page.get("role") or "unknown") for page in pages)
    ata_counts = Counter(str(page.get("ata_code") or "unknown") for page in pages)
    derived_counts = Counter(trait for page in pages for trait in page.get("derived_traits", []))
    direct_trait_counts = Counter(trait for page in pages for trait in page.get("direct_traits", []))
    image_class_counts = Counter(item for page in pages for item in page.get("image_classes", []))

    doc_map: dict[str, dict[str, Any]] = {}
    for page in pages:
        doc_id = str(page.get("document_id") or page.get("document") or "Document 1")
        doc = doc_map.setdefault(
            doc_id,
            {
                "document_id": doc_id,
                "title": str(page.get("document") or doc_id),
                "ata_sections": {},
                "page_count": 0,
                "part_count": 0,
                "role_counts": Counter(),
            },
        )
        doc["page_count"] += 1
        doc["role_counts"][str(page.get("role") or "unknown")] += 1
        ata_code = str(page.get("ata_code") or "unknown")
        ata = doc["ata_sections"].setdefault(
            ata_code,
            {
                "ata_code": ata_code,
                "title": str(page.get("ata_title") or ""),
                "pages": [],
                "page_count": 0,
                "part_count": 0,
                "role_counts": Counter(),
            },
        )
        ata["pages"].append(page)
        ata["page_count"] += 1
        ata["role_counts"][str(page.get("role") or "unknown")] += 1

    for doc in doc_map.values():
        doc_parts: set[str] = set()
        ata_sections = []
        for ata in doc["ata_sections"].values():
            ata_parts = {part.get("part_number") for page in ata["pages"] for part in page.get("parts", []) if part.get("part_number")}
            doc_parts.update(ata_parts)
            ata["part_count"] = len(ata_parts)
            ata["role_counts"] = dict(sorted(ata["role_counts"].items()))
            ata["pages"] = sorted(ata["pages"], key=_page_sort_key)
            ata_sections.append(ata)
        doc["part_count"] = len(doc_parts)
        doc["role_counts"] = dict(sorted(doc["role_counts"].items()))
        doc["ata_sections"] = sorted(ata_sections, key=lambda item: _sort_key(item.get("ata_code")))

    documents = sorted(doc_map.values(), key=lambda item: str(item.get("title")))
    overview = _artifact_overview(paths)

    page_part_count = sum(len(page.get("parts", [])) for page in pages)
    pages_with_parts = sum(1 for page in pages if page.get("parts"))
    pages_with_source = sum(1 for page in pages if _as_dict(page.get("source")).get("source_url"))
    pages_with_tiff = sum(1 for page in pages if _as_dict(page.get("source")).get("tiff_path"))
    pages_with_ocr = sum(1 for page in pages if _as_dict(page.get("source")).get("ocr_path"))
    pages_with_derived = sum(1 for page in pages if page.get("derived_traits"))

    return {
        "status": "ok" if pages else "missing_pages",
        "generated_by": "tiff.graph_org_chart_site",
        "artifact_paths": {
            "export_dir": str(paths.export_dir),
            "graph_dir": str(paths.graph_dir),
            "trait_dir": str(paths.trait_dir),
            "image_recognition_dir": str(paths.image_recognition_dir),
            "organization_dir": str(paths.organization_dir),
            "page_cards_source": page_source_path,
            "part_cards_source": part_source_path,
        },
        "summary": {
            "documents": len(documents),
            "pages": len(pages),
            "ata_sections": sum(len(doc.get("ata_sections", [])) for doc in documents),
            "parts": len(part_cards),
            "page_part_links": page_part_count,
            "pages_with_parts": pages_with_parts,
            "pages_with_source_url": pages_with_source,
            "pages_with_tiff_path": pages_with_tiff,
            "pages_with_ocr_path": pages_with_ocr,
            "pages_with_derived_traits": pages_with_derived,
            "graph_nodes": overview.get("graph_nodes", 0),
            "graph_edges": overview.get("graph_edges", 0),
            "trait_assertions": overview.get("trait_summary", {}).get("assertions", overview.get("trait_summary", {}).get("entity_trait_assertions", 0)),
            "trait_nodes": overview.get("trait_summary", {}).get("trait_nodes", overview.get("trait_summary", {}).get("entity_trait_nodes", 0)),
        },
        "counts": {
            "roles": dict(sorted(role_counts.items())),
            "ata_sections": dict(sorted(ata_counts.items(), key=lambda item: _sort_key(item[0]))),
            "derived_traits": dict(derived_counts.most_common(80)),
            "direct_traits": dict(direct_trait_counts.most_common(80)),
            "image_classes": dict(image_class_counts.most_common(40)),
            "node_types": overview.get("node_types", {}),
            "edge_types": overview.get("edge_types", {}),
        },
        "documents": documents,
        "pages": pages,
        "parts": sorted(part_cards, key=lambda item: str(item.get("part_number") or "")),
        "quality": {
            "entity_trait": overview.get("entity_trait_quality", {}),
            "page_image": overview.get("page_image_quality", {}),
            "page_visual": overview.get("page_visual_quality", {}),
            "organization": overview.get("organization_summary", {}),
            "trait_summary": overview.get("trait_summary", {}),
        },
    }


def _escape_script_json(data: Any) -> str:
    # Prevent accidental </script> termination and keep local HTML self-contained.
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")


def _html_shell(data: Mapping[str, Any]) -> str:
    title = "HEICO Graph Org Chart Viewer"
    embedded = _escape_script_json(data)
    return f"""<!doctype html>
<html lang=\"en\">
<head>
<meta charset=\"utf-8\" />
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
<title>{html.escape(title)}</title>
<style>
:root {{
  --bg: #f7f1ea;
  --panel: #fffaf4;
  --ink: #1e293b;
  --muted: #64748b;
  --line: #c9b9aa;
  --doc: #f7b3a8;
  --ata: #f7e7a6;
  --page: #d9f0e4;
  --trait: #cce8ec;
  --part: #e8d7fb;
  --source: #f9d7b5;
  --danger: #fee2e2;
  --ok: #dcfce7;
  --shadow: 0 10px 30px rgba(30, 41, 59, 0.12);
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  background: radial-gradient(circle at top, #fffaf4, var(--bg));
  color: var(--ink);
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, \"Segoe UI\", sans-serif;
}}
header {{
  position: sticky;
  top: 0;
  z-index: 10;
  background: rgba(255, 250, 244, 0.94);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid #e7d9ca;
  padding: 14px 18px 10px;
}}
.header-row {{ display: flex; gap: 16px; align-items: center; justify-content: space-between; flex-wrap: wrap; }}
h1 {{ margin: 0; font-size: 20px; letter-spacing: 0.02em; }}
.subtitle {{ color: var(--muted); margin-top: 4px; font-size: 13px; }}
.stats {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }}
.stat {{
  background: white;
  border: 1px solid #eadcca;
  border-radius: 999px;
  padding: 7px 10px;
  font-size: 12px;
  box-shadow: 0 3px 10px rgba(30,41,59,0.05);
}}
.toolbar {{
  display: grid;
  grid-template-columns: minmax(230px, 1.7fr) repeat(3, minmax(140px, 0.7fr)) auto auto;
  gap: 8px;
  margin-top: 12px;
}}
input, select, button {{
  border: 1px solid #d9cabb;
  border-radius: 10px;
  padding: 10px 11px;
  background: white;
  color: var(--ink);
  font: inherit;
  font-size: 13px;
}}
button {{ cursor: pointer; font-weight: 650; }}
button:hover {{ background: #fff4e6; }}
main {{ display: grid; grid-template-columns: minmax(0, 1fr) 390px; gap: 16px; padding: 16px; }}
.canvas-shell {{
  background: rgba(255, 250, 244, 0.68);
  border: 1px solid #eadcca;
  border-radius: 20px;
  min-height: calc(100vh - 150px);
  overflow: auto;
  box-shadow: var(--shadow);
}}
.canvas-top {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  padding: 12px 14px;
  border-bottom: 1px solid #eadcca;
  background: rgba(255,255,255,0.55);
  position: sticky;
  top: 0;
  z-index: 3;
}}
.legend {{ display: flex; flex-wrap: wrap; gap: 7px; font-size: 12px; color: var(--muted); }}
.legend span {{ display: inline-flex; align-items: center; gap: 5px; }}
.dot {{ width: 10px; height: 10px; border-radius: 99px; display: inline-block; }}
.zoom {{ display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--muted); }}
#orgCanvas {{ transform-origin: top center; transition: transform .12s ease; padding: 18px; min-width: 1000px; }}
.doc-block {{ margin: 0 auto 30px; text-align: center; }}
.card {{
  border-radius: 14px;
  border: 1px solid rgba(15, 23, 42, 0.10);
  box-shadow: 0 4px 12px rgba(30,41,59,0.08);
  padding: 10px 12px;
  min-height: 48px;
  display: inline-flex;
  flex-direction: column;
  justify-content: center;
  cursor: pointer;
  transition: transform .1s ease, box-shadow .1s ease, border-color .1s ease;
  position: relative;
}}
.card:hover {{ transform: translateY(-2px); box-shadow: 0 8px 20px rgba(30,41,59,0.14); border-color: #64748b55; }}
.card.selected {{ outline: 3px solid rgba(59,130,246,.35); }}
.card-title {{ font-weight: 800; font-size: 12px; line-height: 1.2; }}
.card-meta {{ margin-top: 4px; color: var(--muted); font-size: 11px; line-height: 1.25; }}
.doc-card {{ background: linear-gradient(180deg, #ffd6ce, var(--doc)); min-width: 230px; }}
.ata-row {{ display: flex; gap: 22px; align-items: flex-start; justify-content: center; position: relative; margin-top: 34px; }}
.ata-row::before {{
  content: \"\";
  position: absolute;
  top: -18px;
  left: 9%; right: 9%;
  border-top: 2px solid var(--line);
}}
.ata-wrap {{ position: relative; min-width: 260px; max-width: 520px; }}
.ata-wrap::before {{
  content: \"\";
  position: absolute;
  top: -18px; left: 50%; height: 18px;
  border-left: 2px solid var(--line);
}}
.ata-card {{ background: linear-gradient(180deg, #fff6c9, var(--ata)); min-width: 170px; max-width: 260px; }}
details {{ margin-top: 12px; }}
summary {{ cursor: pointer; color: var(--muted); font-weight: 700; font-size: 12px; list-style-position: inside; }}
.page-grid {{
  margin-top: 14px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(106px, 1fr));
  gap: 9px;
  padding-top: 14px;
  border-top: 2px solid rgba(201,185,170,.65);
}}
.page-card {{
  background: linear-gradient(180deg, #e9fbf2, var(--page));
  min-width: 0;
  width: 100%;
  text-align: left;
  padding: 8px;
}}
.page-card .card-title {{ font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.role-pill {{
  display: inline-block;
  margin-top: 5px;
  padding: 2px 6px;
  border-radius: 999px;
  background: rgba(255,255,255,.68);
  border: 1px solid rgba(15,23,42,.08);
  font-size: 10px;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}}
.drawer {{
  background: rgba(255, 250, 244, .92);
  border: 1px solid #eadcca;
  border-radius: 20px;
  box-shadow: var(--shadow);
  min-height: calc(100vh - 150px);
  max-height: calc(100vh - 120px);
  overflow: auto;
  position: sticky;
  top: 142px;
}}
.drawer-header {{ padding: 15px; border-bottom: 1px solid #eadcca; }}
.drawer-title {{ font-size: 16px; font-weight: 850; margin: 0; }}
.drawer-subtitle {{ color: var(--muted); font-size: 12px; margin-top: 5px; }}
.drawer-body {{ padding: 14px; }}
.section {{
  background: white;
  border: 1px solid #eadcca;
  border-radius: 14px;
  padding: 12px;
  margin-bottom: 12px;
}}
.section h3 {{ margin: 0 0 8px; font-size: 12px; text-transform: uppercase; letter-spacing: .08em; color: #475569; }}
.path {{ display: flex; flex-wrap: wrap; align-items: center; gap: 7px; }}
.path span {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 999px; padding: 5px 8px; font-size: 12px; }}
.badges {{ display: flex; flex-wrap: wrap; gap: 6px; }}
.badge {{ border-radius: 999px; border: 1px solid #d8c8b9; padding: 4px 7px; font-size: 11px; background: #fffaf4; }}
.badge.derived {{ background: var(--trait); }}
.badge.part {{ background: var(--part); }}
.badge.source {{ background: var(--source); }}
.kv {{ display: grid; grid-template-columns: 118px minmax(0, 1fr); gap: 6px 10px; font-size: 12px; }}
.kv b {{ color: #475569; }}
.kv code {{ white-space: normal; word-break: break-word; }}
a {{ color: #2563eb; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
.empty {{ color: var(--muted); font-style: italic; font-size: 13px; }}
.mini-bars {{ display: grid; gap: 7px; }}
.bar-row {{ display: grid; grid-template-columns: 150px 1fr 46px; gap: 8px; align-items: center; font-size: 12px; }}
.bar-label {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #475569; }}
.bar {{ background: #f1e6da; border-radius: 999px; height: 9px; overflow: hidden; }}
.bar > i {{ display: block; height: 100%; background: #94a3b8; border-radius: 999px; }}
.hidden {{ display: none !important; }}
@media (max-width: 1100px) {{
  main {{ grid-template-columns: 1fr; }}
  .drawer {{ position: static; max-height: none; }}
  .toolbar {{ grid-template-columns: 1fr 1fr; }}
}}
</style>
</head>
<body>
<header>
  <div class=\"header-row\">
    <div>
      <h1>HEICO Graph Org Chart Viewer</h1>
      <div class=\"subtitle\">Interactive document → ATA → page → source/context/part/trait view</div>
    </div>
    <div class=\"stats\" id=\"headerStats\"></div>
  </div>
  <div class=\"toolbar\">
    <input id=\"searchBox\" placeholder=\"Search page, part, ATA, source, trait, summary…\" />
    <select id=\"ataFilter\"><option value=\"\">All ATA sections</option></select>
    <select id=\"roleFilter\"><option value=\"\">All page roles</option></select>
    <select id=\"traitFilter\"><option value=\"\">All derived traits</option></select>
    <button id=\"resetBtn\">Reset</button>
    <button id=\"toggleBtn\">Collapse Pages</button>
  </div>
</header>
<main>
  <section class=\"canvas-shell\">
    <div class=\"canvas-top\">
      <div class=\"legend\">
        <span><i class=\"dot\" style=\"background:var(--doc)\"></i>Document</span>
        <span><i class=\"dot\" style=\"background:var(--ata)\"></i>ATA</span>
        <span><i class=\"dot\" style=\"background:var(--page)\"></i>Page</span>
        <span><i class=\"dot\" style=\"background:var(--trait)\"></i>Traits</span>
        <span><i class=\"dot\" style=\"background:var(--part)\"></i>Parts</span>
      </div>
      <label class=\"zoom\">Zoom <input id=\"zoomRange\" type=\"range\" min=\"60\" max=\"125\" value=\"92\" /></label>
    </div>
    <div id=\"orgCanvas\"></div>
  </section>
  <aside class=\"drawer\" id=\"drawer\">
    <div class=\"drawer-header\">
      <p class=\"drawer-title\">Select a page, ATA, document, or part</p>
      <div class=\"drawer-subtitle\">Click a card in the chart to inspect its source-backed data.</div>
    </div>
    <div class=\"drawer-body\" id=\"drawerBody\"></div>
  </aside>
</main>
<script>
window.HEICO_GRAPH_DATA = {embedded};
const DATA = window.HEICO_GRAPH_DATA;
const state = {{ search: '', ata: '', role: '', trait: '', showPages: true, selectedType: '', selectedId: '' }};
const byPage = new Map(DATA.pages.map(p => [p.page_id, p]));
const byPart = new Map(DATA.parts.map(p => [p.part_number, p]));
function esc(value) {{
  return String(value ?? '').replace(/[&<>\"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}}[c]));
}}
function compactId(value) {{
  const text = String(value ?? '');
  return text.replace(/^t_p_120_1176_/, '').replace(/^page:/, '').replace(/^part:/, '');
}}
function countText(n, label) {{ return `${{Number(n || 0).toLocaleString()}} ${{label}}`; }}
function init() {{
  renderStats();
  fillFilters();
  bindControls();
  renderTree();
  renderOverviewDrawer();
}}
function renderStats() {{
  const s = DATA.summary || {{}};
  const stats = [
    countText(s.documents, 'document'), countText(s.ata_sections, 'ATA'), countText(s.pages, 'pages'),
    countText(s.parts, 'parts'), countText(s.graph_nodes, 'graph nodes'), countText(s.trait_assertions, 'trait assertions')
  ];
  document.getElementById('headerStats').innerHTML = stats.map(x => `<span class=\"stat\">${{esc(x)}}</span>`).join('');
}}
function fillSelect(id, values, labeler = x => x) {{
  const select = document.getElementById(id);
  values.forEach(value => {{
    const option = document.createElement('option'); option.value = value; option.textContent = labeler(value); select.appendChild(option);
  }});
}}
function fillFilters() {{
  fillSelect('ataFilter', Object.keys(DATA.counts.ata_sections || {{}}), x => `${{x}} (${{DATA.counts.ata_sections[x]}})`);
  fillSelect('roleFilter', Object.keys(DATA.counts.roles || {{}}), x => `${{x}} (${{DATA.counts.roles[x]}})`);
  fillSelect('traitFilter', Object.keys(DATA.counts.derived_traits || {{}}).slice(0, 80), x => `${{x}} (${{DATA.counts.derived_traits[x]}})`);
}}
function bindControls() {{
  const rerender = () => renderTree();
  document.getElementById('searchBox').addEventListener('input', e => {{ state.search = e.target.value.toLowerCase(); rerender(); }});
  document.getElementById('ataFilter').addEventListener('change', e => {{ state.ata = e.target.value; rerender(); }});
  document.getElementById('roleFilter').addEventListener('change', e => {{ state.role = e.target.value; rerender(); }});
  document.getElementById('traitFilter').addEventListener('change', e => {{ state.trait = e.target.value; rerender(); }});
  document.getElementById('resetBtn').addEventListener('click', () => {{
    state.search = ''; state.ata = ''; state.role = ''; state.trait = '';
    document.getElementById('searchBox').value = '';
    document.getElementById('ataFilter').value = '';
    document.getElementById('roleFilter').value = '';
    document.getElementById('traitFilter').value = '';
    renderTree();
  }});
  document.getElementById('toggleBtn').addEventListener('click', () => {{
    state.showPages = !state.showPages;
    document.getElementById('toggleBtn').textContent = state.showPages ? 'Collapse Pages' : 'Show Pages';
    renderTree();
  }});
  document.getElementById('zoomRange').addEventListener('input', e => {{
    document.getElementById('orgCanvas').style.transform = `scale(${{Number(e.target.value) / 100}})`;
  }});
  document.getElementById('orgCanvas').style.transform = 'scale(.92)';
}}
function pageSearchText(page) {{
  return [page.page_id, page.document, page.ata_code, page.role, page.summary,
    ...(page.image_classes || []), ...(page.direct_traits || []), ...(page.derived_traits || []),
    ...(page.parts || []).map(p => `${{p.part_number}} ${{p.nomenclature || ''}}`),
    Object.values(page.source || {{}}).join(' ')
  ].join(' ').toLowerCase();
}}
function pageMatches(page) {{
  if (state.ata && page.ata_code !== state.ata) return false;
  if (state.role && page.role !== state.role) return false;
  if (state.trait && !(page.derived_traits || []).includes(state.trait)) return false;
  if (state.search && !pageSearchText(page).includes(state.search)) return false;
  return true;
}}
function card(classes, title, meta, onclick, extra='') {{
  return `<div class=\"card ${{classes}}\" onclick=\"${{onclick}}\"><div class=\"card-title\">${{esc(title)}}</div><div class=\"card-meta\">${{esc(meta)}}</div>${{extra}}</div>`;
}}
function renderTree() {{
  const pieces = [];
  for (const doc of DATA.documents) {{
    const docPages = doc.ata_sections.flatMap(a => a.pages).filter(pageMatches);
    if (!docPages.length) continue;
    pieces.push(`<div class=\"doc-block\">`);
    pieces.push(card('doc-card' + selectedClass('document', doc.document_id), doc.title || doc.document_id, `${{docPages.length}} visible / ${{doc.page_count}} pages · ${{doc.part_count}} parts`, `selectDocument('${{escAttr(doc.document_id)}}')`));
    pieces.push(`<div class=\"ata-row\">`);
    for (const ata of doc.ata_sections) {{
      const pages = ata.pages.filter(pageMatches);
      if (!pages.length) continue;
      pieces.push(`<div class=\"ata-wrap\">`);
      pieces.push(card('ata-card' + selectedClass('ata', doc.document_id + '|' + ata.ata_code), ata.ata_code, `${{pages.length}} visible / ${{ata.page_count}} pages · ${{ata.part_count}} parts`, `selectAta('${{escAttr(doc.document_id)}}','${{escAttr(ata.ata_code)}}')`));
      if (state.showPages) {{
        pieces.push(`<details open><summary>Pages in ${{esc(ata.ata_code)}}</summary><div class=\"page-grid\">`);
        for (const page of pages) {{
          const meta = `${{page.role || 'unknown'}} · ${{(page.parts || []).length}} parts`;
          pieces.push(card('page-card' + selectedClass('page', page.page_id), compactId(page.page_id), meta, `selectPage('${{escAttr(page.page_id)}}')`, `<span class=\"role-pill\">${{esc(page.role || 'unknown')}}</span>`));
        }}
        pieces.push(`</div></details>`);
      }}
      pieces.push(`</div>`);
    }}
    pieces.push(`</div></div>`);
  }}
  document.getElementById('orgCanvas').innerHTML = pieces.join('') || `<div class=\"empty\">No pages match the current filters.</div>`;
}}
function escAttr(value) {{
  const bs = String.fromCharCode(92);
  return String(value ?? '')
    .split(bs).join(bs + bs)
    .split("'").join(bs + "'")
    .split(String.fromCharCode(10)).join(' ')
    .split(String.fromCharCode(13)).join(' ');
}}
function selectedClass(type, id) {{ return state.selectedType === type && state.selectedId === id ? ' selected' : ''; }}
function setSelected(type, id) {{ state.selectedType = type; state.selectedId = id; renderTree(); }}
window.selectPage = function(pageId) {{ const page = byPage.get(pageId); if (!page) return; setSelected('page', pageId); renderPageDrawer(page); }}
window.selectDocument = function(docId) {{ const doc = DATA.documents.find(d => d.document_id === docId); if (!doc) return; setSelected('document', docId); renderDocumentDrawer(doc); }}
window.selectAta = function(docId, ataCode) {{ const doc = DATA.documents.find(d => d.document_id === docId); if (!doc) return; const ata = doc.ata_sections.find(a => a.ata_code === ataCode); if (!ata) return; setSelected('ata', docId + '|' + ataCode); renderAtaDrawer(doc, ata); }}
function kv(rows) {{
  return `<div class=\"kv\">${{rows.filter(r => r[1] !== undefined && r[1] !== null && r[1] !== '').map(r => `<b>${{esc(r[0])}}</b><span>${{r[2] === 'link' ? linkHtml(r[1]) : `<code>${{esc(r[1])}}</code>`}}</span>`).join('')}}</div>`;
}}
function linkHtml(value) {{ const text = String(value || ''); if (/^https?:|^file:|^rescarta:/i.test(text)) return `<a href=\"${{esc(text)}}\" target=\"_blank\" rel=\"noopener\">${{esc(text)}}</a>`; return `<code>${{esc(text)}}</code>`; }}
function badges(items, cls='') {{ const list = (items || []).filter(Boolean); return list.length ? `<div class=\"badges\">${{list.map(x => `<span class=\"badge ${{cls}}\">${{esc(x)}}</span>`).join('')}}</div>` : `<div class=\"empty\">None</div>`; }}
function section(title, body) {{ return `<div class=\"section\"><h3>${{esc(title)}}</h3>${{body}}</div>`; }}
function renderPageDrawer(page) {{
  document.querySelector('.drawer-title').textContent = `Page ${{page.page_label || compactId(page.page_id)}}`;
  document.querySelector('.drawer-subtitle').textContent = page.page_id;
  const parts = (page.parts || []).map(p => `${{p.part_number}}${{p.nomenclature ? ' · ' + p.nomenclature : ''}}`);
  const source = page.source || {{}};
  document.getElementById('drawerBody').innerHTML = [
    section('Path', `<div class=\"path\"><span>${{esc(page.document)}}</span><span>→</span><span>ATA ${{esc(page.ata_code)}}</span><span>→</span><span>${{esc(page.page_id)}}</span></div>`),
    section('Page', kv([['Role', page.role], ['Image classes', (page.image_classes || []).join(', ')], ['Summary', page.summary], ['Parts on page', (page.parts || []).length], ['Derived traits', (page.derived_traits || []).length]])),
    section('Source / evidence', kv([['Source URL', source.source_url, 'link'], ['TIFF path', source.tiff_path], ['OCR path', source.ocr_path]])),
    section('Parts', badges(parts, 'part')),
    section('Derived traits', badges(page.derived_traits, 'derived')),
    section('Direct traits', badges(page.direct_traits)),
    section('Signals', kv(Object.entries(page.signals || {{}}))),
  ].join('');
}}
function renderDocumentDrawer(doc) {{
  document.querySelector('.drawer-title').textContent = doc.title || doc.document_id;
  document.querySelector('.drawer-subtitle').textContent = doc.document_id;
  document.getElementById('drawerBody').innerHTML = [
    section('Document totals', kv([['Pages', doc.page_count], ['ATA sections', doc.ata_sections.length], ['Distinct parts on visible cards', doc.part_count]])),
    section('Page roles', bars(doc.role_counts || {{}})),
    section('ATA sections', badges(doc.ata_sections.map(a => `${{a.ata_code}} · ${{a.page_count}} pages`))),
  ].join('');
}}
function renderAtaDrawer(doc, ata) {{
  document.querySelector('.drawer-title').textContent = `ATA ${{ata.ata_code}}`;
  document.querySelector('.drawer-subtitle').textContent = `${{doc.title}} · ${{ata.title || 'section'}}`;
  const parts = new Set(); ata.pages.forEach(p => (p.parts || []).forEach(part => parts.add(part.part_number)));
  document.getElementById('drawerBody').innerHTML = [
    section('ATA totals', kv([['Document', doc.title], ['Pages', ata.page_count], ['Visible pages now', ata.pages.filter(pageMatches).length], ['Distinct parts on page cards', parts.size]])),
    section('Page roles', bars(ata.role_counts || {{}})),
    section('Sample pages', badges(ata.pages.slice(0, 40).map(p => `${{compactId(p.page_id)}} · ${{p.role}}`))),
  ].join('');
}}
function bars(counts) {{
  const entries = Object.entries(counts || {{}}).sort((a,b) => b[1] - a[1]);
  if (!entries.length) return '<div class=\"empty\">None</div>';
  const max = Math.max(...entries.map(x => Number(x[1]) || 0), 1);
  return `<div class=\"mini-bars\">${{entries.map(([k,v]) => `<div class=\"bar-row\"><div class=\"bar-label\" title=\"${{esc(k)}}\">${{esc(k)}}</div><div class=\"bar\"><i style=\"width:${{Math.max(2, (Number(v)||0) / max * 100)}}%\"></i></div><div>${{v}}</div></div>`).join('')}}</div>`;
}}
function renderOverviewDrawer() {{
  document.getElementById('drawerBody').innerHTML = [
    section('Corpus summary', kv(Object.entries(DATA.summary || {{}}))),
    section('Page roles', bars(DATA.counts.roles || {{}})),
    section('Image classes', bars(DATA.counts.image_classes || {{}})),
    section('Top derived traits', bars(DATA.counts.derived_traits || {{}})),
    section('Quality snapshots', kv([
      ['Entity trait status', DATA.quality?.entity_trait?.status || DATA.quality?.trait_summary?.status],
      ['Page image status', DATA.quality?.page_image?.status],
      ['Page visual status', DATA.quality?.page_visual?.status],
      ['Organization status', DATA.quality?.organization?.status || DATA.quality?.organization?.document_organization_ready],
    ])),
  ].join('');
}}
init();
</script>
</body>
</html>
"""


def write_org_chart_site(data: Mapping[str, Any], output_dir: Path | str = DEFAULT_OUTPUT_DIR) -> dict[str, str]:
    """Write the interactive org-chart HTML site and companion JSON files."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    index_path = out / "index.html"
    data_path = out / "graph_org_chart_data.json"
    summary_path = out / "graph_org_chart_summary.json"
    index_path.write_text(_html_shell(data), encoding="utf-8")
    _write_json(data_path, data)
    _write_json(
        summary_path,
        {
            "status": data.get("status"),
            "summary": data.get("summary", {}),
            "artifact_paths": data.get("artifact_paths", {}),
            "counts": {
                "roles": data.get("counts", {}).get("roles", {}),
                "ata_sections": data.get("counts", {}).get("ata_sections", {}),
                "image_classes": data.get("counts", {}).get("image_classes", {}),
            },
        },
    )
    return {"index": str(index_path), "data_json": str(data_path), "summary_json": str(summary_path)}


def build_and_write_org_chart_site(paths: OrgChartPaths | None = None) -> dict[str, Any]:
    """Build the view model, write the site, and return a small report."""
    paths = paths or OrgChartPaths()
    data = build_org_chart_data(paths)
    files = write_org_chart_site(data, paths.output_dir)
    return {"status": data.get("status"), "summary": data.get("summary", {}), "files": files, "data": data}
