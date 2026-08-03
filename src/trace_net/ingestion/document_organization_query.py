"""Query exported document-organization JSON artifacts.

This module intentionally reads the exported JSON files rather than SQLite.
That makes it a small stand-in for the future UI/API consumption layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
from typing import Any, Iterable

REQUIRED_EXPORT_FILES = (
    "manual_ata_tree.json",
    "ata_tree.json",
    "part_tree.json",
    "page_index.json",
    "organization_summary.json",
)

PART_KEYS = ("part_number", "part", "number", "canonical_part_number")
ATA_KEYS = ("ata", "ata_code", "ataCode")
PAGE_ID_KEYS = ("page_id", "pageId", "id")
PAGE_LABEL_KEYS = ("page_label", "page", "page_number", "label")
SOURCE_KEYS = ("source_url", "rescarta_url", "url", "source")
TIFF_KEYS = ("tiff_path", "image_path", "source_image_path", "tiff", "tiff_uri")
OCR_KEYS = ("ocr_text_path", "ocr_path", "text_path", "ocr", "ocr_file", "ocr_file_path", "ocr_uri")
NOMENCLATURE_KEYS = ("nomenclature", "name", "title", "description")


@dataclass(frozen=True)
class OrganizationExport:
    export_dir: Path
    manual_ata_tree: Any
    ata_tree: Any
    part_tree: Any
    page_index: Any
    organization_summary: Any


def load_export(export_dir: str | Path) -> OrganizationExport:
    """Load all organization-export JSON files from *export_dir*."""
    root = Path(export_dir)
    missing = [name for name in REQUIRED_EXPORT_FILES if not (root / name).exists()]
    if missing:
        raise FileNotFoundError(
            "Missing organization export files: " + ", ".join(missing)
        )
    return OrganizationExport(
        export_dir=root,
        manual_ata_tree=_load_json(root / "manual_ata_tree.json"),
        ata_tree=_load_json(root / "ata_tree.json"),
        part_tree=_load_json(root / "part_tree.json"),
        page_index=_load_json(root / "page_index.json"),
        organization_summary=_load_json(root / "organization_summary.json"),
    )


def summarize_export(export: OrganizationExport) -> dict[str, Any]:
    """Return a compact summary that is stable across export schema variants."""
    summary = export.organization_summary if isinstance(export.organization_summary, dict) else {}
    counts = summary.get("counts") if isinstance(summary.get("counts"), dict) else summary
    parts = collect_parts(export)
    pages = collect_pages(export)
    ata_entries = collect_ata_entries(export)
    return {
        "export_dir": str(export.export_dir),
        "manuals": _first_int(counts, "manuals", "manual_count", default=None),
        "pages": _first_int(counts, "pages", "page_count", default=len(pages)),
        "ata_groups": _first_int(
            counts,
            "ata_groups",
            "ata_group_count",
            "ata_count",
            default=len(ata_entries),
        ),
        "parts": _first_int(
            counts,
            "parts",
            "part_count",
            "distinct_parts",
            "logical_distinct_parts",
            default=len(parts),
        ),
        "part_mentions": _first_int(
            counts,
            "part_mentions",
            "part_mention_count",
            "mentions",
            "logical_part_mentions",
            default=None,
        ),
        "files_present": {
            name: (export.export_dir / name).exists() for name in REQUIRED_EXPORT_FILES
        },
    }


def query_part(export: OrganizationExport, part_number: str, *, limit: int = 10) -> list[dict[str, Any]]:
    """Find exported part-tree entries by exact part number, case-insensitive."""
    needle = _norm(part_number)
    matches = [entry for entry in collect_parts(export) if _norm(_part_number(entry)) == needle]
    return matches[:limit]


def query_ata(export: OrganizationExport, ata_code: str, *, limit: int = 10) -> list[dict[str, Any]]:
    """Find exported ATA entries by exact ATA code, case-insensitive."""
    needle = _norm(ata_code)
    matches = [entry for entry in collect_ata_entries(export) if _norm(_ata_code(entry)) == needle]
    return matches[:limit]


def query_page(export: OrganizationExport, page_query: str, *, limit: int = 10) -> list[dict[str, Any]]:
    """Find pages by page id or page label substring."""
    needle = _norm(page_query)
    results: list[dict[str, Any]] = []
    for page in collect_pages(export):
        values = [_page_id(page), _page_label(page)]
        if any(needle in _norm(value) for value in values if value is not None):
            results.append(page)
    return results[:limit]


def collect_parts(export: OrganizationExport) -> list[dict[str, Any]]:
    """Collect top-level part entries from part_tree.json."""
    return _collect_named_collection(export.part_tree, "parts", value_keys=PART_KEYS, key_name="part_number")


def collect_ata_entries(export: OrganizationExport) -> list[dict[str, Any]]:
    """Collect top-level ATA group entries, excluding nested page rows.

    The exported ATA tree contains ATA records that themselves contain page
    records. Page rows also carry an ``ata`` field, so the generic recursive
    collector used for parts/pages would over-count ATA groups and produce many
    duplicate zero-page rows. This collector intentionally accepts only
    group-level ATA records.
    """
    records = _collect_ata_group_records(export.ata_tree)
    if records:
        return records
    return _collect_ata_group_records(export.manual_ata_tree)


def collect_pages(export: OrganizationExport) -> list[dict[str, Any]]:
    """Collect top-level page entries from page_index.json."""
    return _collect_named_collection(export.page_index, "pages", value_keys=PAGE_ID_KEYS, key_name="page_id")


def format_summary(summary: dict[str, Any]) -> str:
    lines = ["Document organization query", f"  Export dir: {summary.get('export_dir')}"]
    lines.append("  Files present:")
    for name, exists in summary.get("files_present", {}).items():
        lines.append(f"    {name}: {exists}")
    lines.append("  Counts:")
    for key in ("manuals", "pages", "ata_groups", "parts", "part_mentions"):
        value = summary.get(key)
        if value is not None:
            label = key.replace("_", " ").title()
            lines.append(f"    {label}: {value}")
    return "\n".join(lines)


def format_part(entry: dict[str, Any]) -> str:
    part = _part_number(entry) or "-"
    name = _first_text(entry, *NOMENCLATURE_KEYS) or "-"
    page_count = _count_value(entry, "pages", "page_count")
    mention_count = _count_value(entry, "mentions", "mention_count", "part_mentions")
    lines = [f"{part} | {name} | pages={page_count} mentions={mention_count}"]
    for row in _first_nested_records(entry, ("pages", "source_pages", "sources"), limit=5):
        page_id = _page_id(row) or "-"
        ata = _ata_code(row) or "-"
        label = _page_label(row) or "-"
        source = _first_text(row, *SOURCE_KEYS) or "-"
        lines.append(f"  - page={page_id} ata={ata} label={label} source={source}")
    return "\n".join(lines)


def format_ata(entry: dict[str, Any]) -> str:
    ata = _ata_code(entry) or "-"
    manual = _first_text(entry, "manual", "title", "publication_number", "manual_id") or "-"
    pages = _count_value(entry, "page_count", "pages")
    parts = _count_value(
        entry,
        "distinct_part_count",
        "part_count",
        "parts",
        "part_mention_count",
        "part_mentions",
    )
    return f"ATA {ata} | manual={manual} | pages={pages} parts={parts}"


def format_page(entry: dict[str, Any]) -> str:
    page_id = _page_id(entry) or "-"
    ata = _ata_code(entry) or "-"
    label = _page_label(entry) or "-"
    source = _first_text(entry, *SOURCE_KEYS) or "-"
    tiff = _first_text(entry, *TIFF_KEYS) or "-"
    ocr = _first_text(entry, *OCR_KEYS) or "-"
    return f"{page_id} | ATA {ata} | page {label}\n  Source: {source}\n  TIFF: {tiff}\n  OCR: {ocr}"


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)



def _collect_named_collection(data: Any, collection_key: str, *, value_keys: Iterable[str], key_name: str) -> list[dict[str, Any]]:
    """Collect records from a named top-level collection or keyed mapping.

    This avoids accidentally treating nested source pages as top-level parts,
    pages, or ATA groups when the export contains a tree with nested objects.
    """
    if isinstance(data, dict):
        collection = data.get(collection_key)
        if isinstance(collection, list):
            return _dedupe_records([item for item in collection if isinstance(item, dict)])
        if isinstance(collection, dict):
            return _dedupe_records(
                _record_with_key(value, str(key), value_keys=value_keys, key_name=key_name)
                for key, value in collection.items()
                if isinstance(value, dict)
            )

        keyed: list[dict[str, Any]] = []
        for key, value in data.items():
            if isinstance(value, dict) and _looks_like_external_key(str(key), key_name):
                keyed.append(_record_with_key(value, str(key), value_keys=value_keys, key_name=key_name))
        if keyed:
            return _dedupe_records(keyed)

    if isinstance(data, list):
        return _dedupe_records([item for item in data if isinstance(item, dict)])

    return []


def _record_with_key(record: dict[str, Any], fallback_key: str, *, value_keys: Iterable[str], key_name: str) -> dict[str, Any]:
    item = dict(record)
    if fallback_key and not any(item.get(k) for k in value_keys):
        item[key_name] = fallback_key
    return item


def _dedupe_records(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in records:
        identity = json.dumps(record, sort_keys=True, default=str)
        if identity not in seen:
            seen.add(identity)
            output.append(record)
    return output


def _collect_ata_group_records(data: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def is_group(record: dict[str, Any]) -> bool:
        # Page records usually have page_id/source fields and should not become
        # ATA search results. ATA group records have aggregate fields such as
        # page_count, pages, distinct_part_count, or part_mention_count.
        if _page_id(record):
            return False
        if not _ata_code(record):
            return False
        group_markers = (
            "page_count",
            "pages",
            "page_ids",
            "part_count",
            "parts",
            "part_mention_count",
            "distinct_part_count",
            "empty_ocr_page_count",
            "manual",
            "manual_id",
            "publication_number",
        )
        return any(key in record for key in group_markers)

    def add(record: dict[str, Any], fallback_ata: str | None = None) -> None:
        item = dict(record)
        if fallback_ata and not _ata_code(item):
            item["ata"] = fallback_ata
        ata = _ata_code(item) or ""
        manual = _first_text(item, "manual", "publication_number", "manual_id", "title") or ""
        identity = (manual, ata)
        if ata and identity not in seen and is_group(item):
            seen.add(identity)
            records.append(item)

    def visit(node: Any, fallback_key: str | None = None, depth: int = 0) -> None:
        if depth > 5:
            return
        if isinstance(node, dict):
            if is_group(node):
                add(node, fallback_key)
            # Common schema: {"ata_groups": [ ... ]}
            groups = node.get("ata_groups")
            if isinstance(groups, list):
                for item in groups:
                    if isinstance(item, dict):
                        add(item, fallback_key)
                return
            # Common keyed schema: {"25-21-00": { ... }}
            for key, value in node.items():
                if key in {"pages", "page_ids", "source_pages"}:
                    continue
                if isinstance(value, dict):
                    key_text = str(key)
                    if _looks_like_external_key(key_text, "ata"):
                        add(value, key_text)
                    else:
                        visit(value, key_text, depth + 1)
                elif isinstance(value, list) and key not in {"pages", "page_ids", "source_pages"}:
                    visit(value, str(key), depth + 1)
        elif isinstance(node, list):
            for item in node:
                visit(item, fallback_key, depth + 1)

    visit(data)
    return records

def _collect_keyed_records(data: Any, *, value_keys: Iterable[str], key_name: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_record(record: dict[str, Any], fallback_key: str | None = None) -> None:
        item = dict(record)
        if fallback_key and not any(item.get(k) for k in value_keys):
            item[key_name] = fallback_key
        identity = json.dumps(item, sort_keys=True, default=str)
        if identity not in seen:
            seen.add(identity)
            records.append(item)

    def visit(node: Any, fallback_key: str | None = None, depth: int = 0) -> None:
        if depth > 8:
            return
        if isinstance(node, dict):
            # A direct record.
            if any(k in node for k in value_keys):
                add_record(node, fallback_key)
            # A mapping keyed by part number, ATA code, or page id.
            for key, value in node.items():
                if isinstance(value, dict):
                    key_text = str(key)
                    if _looks_like_external_key(key_text, key_name):
                        add_record(value, key_text)
                    visit(value, key_text, depth + 1)
                elif isinstance(value, list):
                    visit(value, str(key), depth + 1)
        elif isinstance(node, list):
            for item in node:
                visit(item, fallback_key, depth + 1)

    visit(data)
    return records


def _looks_like_external_key(value: str, key_name: str) -> bool:
    if key_name == "ata":
        return bool(value) and any(ch.isdigit() for ch in value) and "-" in value
    if key_name == "part_number":
        return bool(value) and any(ch.isdigit() for ch in value) and len(value) >= 4
    if key_name == "page_id":
        return bool(value)
    return False


def _first_text(mapping: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, (str, int, float)):
            text = str(value)
            if text:
                return text
    return None


def _first_int(mapping: dict[str, Any], *keys: str, default: int | None = None) -> int | None:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return default


def _count_value(mapping: dict[str, Any], *keys: str) -> int:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
        if isinstance(value, list):
            return len(value)
        if isinstance(value, dict):
            return len(value)
    return 0


def _first_nested_records(mapping: dict[str, Any], keys: Iterable[str], *, limit: int) -> list[dict[str, Any]]:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)][:limit]
        if isinstance(value, dict):
            return [dict(item, page_id=str(name)) if isinstance(item, dict) and "page_id" not in item else item for name, item in value.items() if isinstance(item, dict)][:limit]
    return []


def _part_number(entry: dict[str, Any]) -> str | None:
    return _first_text(entry, *PART_KEYS)


def _ata_code(entry: dict[str, Any]) -> str | None:
    return _first_text(entry, *ATA_KEYS)


def _page_id(entry: dict[str, Any]) -> str | None:
    return _first_text(entry, *PAGE_ID_KEYS)


def _page_label(entry: dict[str, Any]) -> str | None:
    return _first_text(entry, *PAGE_LABEL_KEYS)


def _norm(value: Any) -> str:
    return str(value or "").strip().upper()
