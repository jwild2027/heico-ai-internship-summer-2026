"""Read and smoke-test exported document organization JSON artifacts.

This module intentionally works with plain JSON artifacts so it can be used by
future API/UI work without opening the SQLite database.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json
from typing import Any, Iterable

EXPECTED_EXPORT_FILES = [
    "manual_ata_tree.json",
    "ata_tree.json",
    "part_tree.json",
    "page_index.json",
    "organization_summary.json",
]


@dataclass
class OrganizationExportInspection:
    export_dir: Path
    files_present: dict[str, bool] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)
    manual_count: int = 0
    ata_group_count: int = 0
    page_count: int = 0
    part_count: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    sample_parts: list[dict[str, Any]] = field(default_factory=list)
    sample_pages: list[dict[str, Any]] = field(default_factory=list)
    sample_ata: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "OK" if self.ok else "NEEDS_ATTENTION",
            "export_dir": str(self.export_dir),
            "files_present": self.files_present,
            "summary": self.summary,
            "manual_count": self.manual_count,
            "ata_group_count": self.ata_group_count,
            "page_count": self.page_count,
            "part_count": self.part_count,
            "sample_parts": self.sample_parts,
            "sample_pages": self.sample_pages,
            "sample_ata": self.sample_ata,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        # Common container keys first.
        for key in ("items", "entries", "children", "pages", "parts", "ata_groups", "manuals"):
            child = value.get(key)
            if isinstance(child, list):
                return child
        # Mapping of id -> object.
        if value and all(isinstance(v, dict) for v in value.values()):
            out: list[dict[str, Any]] = []
            for k, v in value.items():
                item = dict(v)
                item.setdefault("id", k)
                item.setdefault("key", k)
                out.append(item)
            return out
    return [value]


def _get_first(d: dict[str, Any], keys: Iterable[str], default: Any = None) -> Any:
    for key in keys:
        if key in d and d[key] not in (None, ""):
            return d[key]
    return default


def _find_container(data: Any, names: Iterable[str]) -> Any:
    if not isinstance(data, dict):
        return data
    for name in names:
        if name in data:
            return data[name]
    return data


def load_export_bundle(export_dir: str | Path) -> dict[str, Any]:
    root = Path(export_dir)
    bundle: dict[str, Any] = {}
    for name in EXPECTED_EXPORT_FILES:
        path = root / name
        if path.exists():
            bundle[name] = load_json(path)
    return bundle


def normalize_pages(page_index: Any) -> list[dict[str, Any]]:
    data = _find_container(page_index, ("pages", "page_index", "items", "entries"))
    pages = []
    for item in _as_list(data):
        if not isinstance(item, dict):
            continue
        page = dict(item)
        page_id = _get_first(page, ("page_id", "id", "key", "source_page_id"))
        if page_id:
            page["page_id"] = page_id
        pages.append(page)
    return pages


def normalize_parts(part_tree: Any) -> list[dict[str, Any]]:
    data = _find_container(part_tree, ("parts", "part_tree", "items", "entries"))
    parts = []
    for item in _as_list(data):
        if not isinstance(item, dict):
            continue
        part = dict(item)
        number = _get_first(part, ("part_number", "part", "id", "key", "number"))
        if number:
            part["part_number"] = str(number)
        pages = _get_first(part, ("pages", "source_pages", "page_ids", "mentions"), [])
        if isinstance(pages, dict):
            pages = _as_list(pages)
        part["_page_count"] = len(pages) if isinstance(pages, list) else 0
        parts.append(part)
    return parts


def normalize_ata_groups(ata_tree: Any, manual_tree: Any | None = None) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []

    def visit(node: Any, inherited_manual: str | None = None) -> None:
        if isinstance(node, list):
            for child in node:
                visit(child, inherited_manual)
            return
        if not isinstance(node, dict):
            return
        manual = _get_first(
            node,
            ("manual", "manual_title", "publication_number", "manual_id", "document", "title"),
            inherited_manual,
        )
        ata = _get_first(node, ("ata", "ata_code", "code", "id", "key"))
        pages = _get_first(node, ("pages", "page_ids", "children"), [])
        if ata and _looks_like_ata(str(ata)):
            groups.append({
                "ata": str(ata),
                "manual": manual,
                "pages": pages if isinstance(pages, list) else [],
                "page_count": len(pages) if isinstance(pages, list) else _get_first(node, ("page_count", "pages_count"), 0),
            })
        for key in ("children", "ata_groups", "manuals", "items", "entries"):
            child = node.get(key)
            if child is not None:
                visit(child, manual)

    visit(_find_container(ata_tree, ("ata_groups", "ata_tree", "items", "entries")))
    if not groups and manual_tree is not None:
        visit(manual_tree)
    # Deduplicate by manual+ATA.
    seen: set[tuple[str | None, str]] = set()
    out: list[dict[str, Any]] = []
    for group in groups:
        key = (group.get("manual"), group["ata"])
        if key in seen:
            continue
        seen.add(key)
        out.append(group)
    return out


def _looks_like_ata(value: str) -> bool:
    parts = value.split("-")
    return len(parts) >= 2 and all(p.isdigit() for p in parts if p)


def _summarize_part(part: dict[str, Any]) -> dict[str, Any]:
    return {
        "part_number": part.get("part_number"),
        "nomenclature": _get_first(part, ("nomenclature", "name", "description"), ""),
        "page_count": _get_first(part, ("page_count", "pages_count"), part.get("_page_count", 0)),
        "mention_count": _get_first(part, ("mention_count", "mentions_count", "mentions"), ""),
        "ata": _get_first(part, ("ata", "ata_codes", "atas"), ""),
    }


def _summarize_page(page: dict[str, Any]) -> dict[str, Any]:
    return {
        "page_id": page.get("page_id"),
        "manual": _get_first(page, ("manual", "manual_title", "publication_number", "manual_id", "document", "title"), ""),
        "ata": _get_first(page, ("ata", "ata_code"), ""),
        "page_label": _get_first(page, ("page_label", "label", "page_number"), ""),
        "tiff_path": _get_first(page, ("tiff_path", "image_path", "tif_path"), ""),
        "ocr_path": _get_first(page, ("ocr_path", "text_path"), ""),
        "source_url": _get_first(page, ("rescarta_url", "source_url", "url"), ""),
    }


def inspect_export(
    export_dir: str | Path,
    sample_parts: Iterable[str] | None = None,
    sample_pages: Iterable[str] | None = None,
    sample_atas: Iterable[str] | None = None,
    limit: int = 10,
) -> OrganizationExportInspection:
    root = Path(export_dir)
    result = OrganizationExportInspection(export_dir=root)
    result.files_present = {name: (root / name).exists() for name in EXPECTED_EXPORT_FILES}
    missing = [name for name, exists in result.files_present.items() if not exists]
    if missing:
        result.errors.append("Missing organization export file(s): " + ", ".join(missing))
        return result

    bundle = load_export_bundle(root)
    result.summary = bundle.get("organization_summary.json", {}) if isinstance(bundle.get("organization_summary.json"), dict) else {}
    pages = normalize_pages(bundle.get("page_index.json"))
    parts = normalize_parts(bundle.get("part_tree.json"))
    atas = normalize_ata_groups(bundle.get("ata_tree.json"), bundle.get("manual_ata_tree.json"))

    result.page_count = len(pages)
    result.part_count = len([p for p in parts if p.get("part_number")])
    result.ata_group_count = len(atas)
    result.manual_count = int(_get_first(result.summary, ("manuals", "manual_count", "document_count"), 0) or 0)

    if result.page_count <= 0:
        result.errors.append("page_index.json did not expose any pages.")
    if result.part_count <= 0:
        result.errors.append("part_tree.json did not expose any parts.")
    if result.ata_group_count <= 0:
        result.errors.append("ata_tree.json/manual_ata_tree.json did not expose any ATA groups.")

    by_part = {str(p.get("part_number", "")).upper(): p for p in parts if p.get("part_number")}
    by_page = {str(p.get("page_id", "")): p for p in pages if p.get("page_id")}
    ata_values = {str(a.get("ata", "")): a for a in atas if a.get("ata")}

    for part_number in sample_parts or []:
        key = str(part_number).upper()
        item = by_part.get(key)
        if item is None:
            result.errors.append(f"Sample part not found in exported part_tree.json: {part_number}")
        else:
            result.sample_parts.append(_summarize_part(item))

    for page_id in sample_pages or []:
        item = by_page.get(str(page_id))
        if item is None:
            result.errors.append(f"Sample page not found in exported page_index.json: {page_id}")
        else:
            result.sample_pages.append(_summarize_page(item))

    for ata in sample_atas or []:
        item = ata_values.get(str(ata))
        if item is None:
            result.errors.append(f"Sample ATA not found in exported ATA tree: {ata}")
        else:
            result.sample_ata.append(item)

    if not result.sample_parts:
        result.sample_parts = [_summarize_part(p) for p in parts[:limit]]
    if not result.sample_pages:
        result.sample_pages = [_summarize_page(p) for p in pages[:limit]]
    if not result.sample_ata:
        result.sample_ata = atas[:limit]

    return result


def write_inspection_json(result: OrganizationExportInspection, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return path
