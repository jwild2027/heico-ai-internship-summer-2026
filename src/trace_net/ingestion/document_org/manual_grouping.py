"""Group scanned TIFF pages into logical manual objects.

This module is intentionally read-only: it reads the existing TIFF scan SQLite
DB and produces a JSON manifest. It does not change the scan tables.

Why this exists:
- The scanner works page-by-page.
- ResCarta should usually receive a manual/document object made of many pages.
- RAG citations should point to logical manual/page metadata, not only raw TIFF
  filenames.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
import json
import re
import sqlite3
from collections import Counter
from typing import Any, Iterable

PUBLICATION_PATTERNS = [
    re.compile(r"\bT\.?\s*P\.?\s*[- ]?\s*(\d{2,4}\s*/\s*\d{2,5})\b", re.IGNORECASE),
    re.compile(r"\bTP\s*[- ]?\s*(\d{2,4}\s*/\s*\d{2,5})\b", re.IGNORECASE),
]

# Page/figure/document codes commonly seen inside IPL pages. These are useful
# page-level identifiers, but they should not normally split the sample folder
# into separate manual objects.
PAGE_SPECIFIC_CODE_RE = re.compile(
    r"^(?:\d{2,4})?(?:TP|CMM)\d{5,}(?:[A-Z])?\.M[A-Z]{1,3}$",
    re.IGNORECASE,
)


def normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_publication_number(value: Any) -> str | None:
    """Normalize variants like 'TP. 120/1176' to 'T.P. 120/1176'."""
    text = normalize_text(value)
    if not text:
        return None
    text = text.replace("T.-P.", "T.P.").replace("T . P .", "T.P.")
    for pattern in PUBLICATION_PATTERNS:
        match = pattern.search(text)
        if match:
            number = re.sub(r"\s+", "", match.group(1))
            return f"T.P. {number}"
    return None


def is_page_specific_code(value: Any) -> bool:
    text = normalize_text(value)
    if not text:
        return False
    compact = re.sub(r"\s+", "", text).upper()
    return bool(PAGE_SPECIFIC_CODE_RE.match(compact))


def natural_sort_key(value: str) -> list[object]:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", value)]


def safe_json_loads(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(str(value))
    except Exception:
        return default


@dataclass
class ManualPage:
    file_id: str
    file_name: str
    source_path: str
    relative_path: str | None = None
    page_sequence: int | None = None
    detected_type: str | None = None
    document_code: str | None = None
    publication_number: str | None = None
    page_document_code: str | None = None
    manufacturer: str | None = None
    manual_title: str | None = None
    component_title: str | None = None
    section_title: str | None = None
    figure_title: str | None = None
    figure_number: str | None = None
    effectivity: str | None = None
    ata_code: str | None = None
    page_number: int | None = None
    page_label: str | None = None
    issue_date: str | None = None
    revision_date: str | None = None
    revision_label: str | None = None
    part_numbers: list[str] = field(default_factory=list)
    callouts: list[str] = field(default_factory=list)
    ocr_text: str | None = None

    def citation_label(self, publication_number: str | None = None) -> str:
        pub = self.publication_number or publication_number or self.document_code or "Manual"
        bits = [pub]
        if self.section_title:
            bits.append(self.section_title.title())
        elif self.figure_title:
            bits.append(self.figure_title)
        if self.page_label:
            bits.append(f"Page {self.page_label}")
        elif self.page_number is not None:
            bits.append(f"Page {self.page_number}")
        return ", ".join(bits)


@dataclass
class ManualGroup:
    manual_id: str
    publication_number: str | None
    manufacturer: str | None
    manual_title: str | None
    component_title: str | None
    ata_code: str | None
    source_folder: str | None
    page_count: int
    pages: list[ManualPage]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["pages"] = [asdict(page) | {"citation_label": page.citation_label(self.publication_number)} for page in self.pages]
        return data


def _mode(values: Iterable[str | None]) -> str | None:
    cleaned = [v for v in values if v]
    if not cleaned:
        return None
    return Counter(cleaned).most_common(1)[0][0]


def _dominant_publication(rows: list[dict[str, Any]]) -> str | None:
    candidates: list[str] = []
    for row in rows:
        for key in ("publication_number", "document_code"):
            pub = normalize_publication_number(row.get(key))
            if pub:
                candidates.append(pub)
    if not candidates:
        return None
    return Counter(candidates).most_common(1)[0][0]


def _common_source_folder(rows: list[dict[str, Any]]) -> str | None:
    paths = [str(row.get("source_path")) for row in rows if row.get("source_path")]
    if not paths:
        return None
    try:
        return str(Path(paths[0]).parent) if len(paths) == 1 else str(Path(__import__("os").path.commonpath(paths)))
    except Exception:
        return str(Path(paths[0]).parent)


def _manual_id(publication_number: str | None, source_folder: str | None) -> str:
    base = publication_number or Path(source_folder or "manual").name or "manual"
    text = base.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text or "manual"


def rows_to_pages(rows: list[dict[str, Any]], dominant_publication: str | None = None) -> list[ManualPage]:
    pages: list[ManualPage] = []
    sorted_rows = sorted(rows, key=lambda row: natural_sort_key(str(row.get("file_name") or "")))
    for index, row in enumerate(sorted_rows, start=1):
        document_code = normalize_text(row.get("document_code"))
        publication_number = normalize_publication_number(row.get("publication_number")) or normalize_publication_number(document_code)
        page_document_code = None
        if document_code and not publication_number and is_page_specific_code(document_code):
            page_document_code = document_code
        elif document_code and publication_number != document_code:
            # Keep non-publication codes on the page too; they can be useful for
            # figure/page lookup even when the manual publication is inherited.
            if is_page_specific_code(document_code):
                page_document_code = document_code

        pages.append(
            ManualPage(
                file_id=str(row.get("file_id") or row.get("id") or ""),
                file_name=str(row.get("file_name") or ""),
                source_path=str(row.get("source_path") or ""),
                relative_path=normalize_text(row.get("relative_path")),
                page_sequence=index,
                detected_type=normalize_text(row.get("detected_type")),
                document_code=document_code,
                publication_number=publication_number or dominant_publication,
                page_document_code=page_document_code,
                manufacturer=normalize_text(row.get("manufacturer")),
                manual_title=normalize_text(row.get("manual_title")),
                component_title=normalize_text(row.get("component_title")),
                section_title=normalize_text(row.get("section_title")),
                figure_title=normalize_text(row.get("figure_title")),
                figure_number=normalize_text(row.get("figure_number")),
                effectivity=normalize_text(row.get("effectivity")),
                ata_code=normalize_text(row.get("ata_code")),
                page_number=row.get("page_number"),
                page_label=normalize_text(row.get("page_label")),
                issue_date=normalize_text(row.get("issue_date")),
                revision_date=normalize_text(row.get("revision_date")),
                revision_label=normalize_text(row.get("revision_label")),
                part_numbers=safe_json_loads(row.get("part_numbers_json"), []),
                callouts=safe_json_loads(row.get("callouts_json"), []),
                ocr_text=normalize_text(row.get("ocr_text")),
            )
        )
    return pages


def build_single_manual_group(rows: list[dict[str, Any]]) -> ManualGroup:
    """Build one logical manual object from a folder scan.

    This is the right first model for the current 509-page sample: the TIFFs are
    pages from a manual/publication, while many 120TP... codes are page/figure
    identifiers inside that manual.
    """
    if not rows:
        raise ValueError("Cannot group an empty TIFF scan result")

    publication = _dominant_publication(rows)
    source_folder = _common_source_folder(rows)
    pages = rows_to_pages(rows, dominant_publication=publication)
    manufacturer = _mode([p.manufacturer for p in pages]) or "EMBRAER"
    manual_title = _mode([p.manual_title for p in pages]) or "Maintenance Manual with Illustrated Parts List"
    component_title = _mode([p.component_title for p in pages])
    # Avoid one-off OCR mistakes by picking the most frequent ATA code.
    ata_code = _mode([p.ata_code for p in pages])

    return ManualGroup(
        manual_id=_manual_id(publication, source_folder),
        publication_number=publication,
        manufacturer=manufacturer,
        manual_title=manual_title,
        component_title=component_title,
        ata_code=ata_code,
        source_folder=source_folder,
        page_count=len(pages),
        pages=pages,
    )


def load_scan_rows(db_path: str | Path) -> list[dict[str, Any]]:
    """Load page-level scan rows from the TIFF SQLite DB."""
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"SQLite DB does not exist: {path}")

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT
                f.id AS file_id,
                f.source_path,
                f.relative_path,
                f.file_name,
                dc.detected_type,
                mm.document_type,
                mm.manufacturer,
                mm.manual_title,
                mm.document_code,
                mm.publication_number,
                mm.component_title,
                mm.section_title,
                mm.figure_title,
                mm.figure_number,
                mm.effectivity,
                mm.ata_code,
                mm.page_number,
                mm.page_label,
                mm.issue_date,
                mm.revision_date,
                mm.revision_label,
                mm.part_numbers_json,
                mm.callouts_json,
                o.text AS ocr_text
            FROM tiff_files f
            LEFT JOIN tiff_document_classification dc ON dc.file_id = f.id
            LEFT JOIN tiff_manual_metadata mm ON mm.file_id = f.id
            LEFT JOIN tiff_ocr_texts o ON o.file_id = f.id AND o.region_type = 'combined'
            ORDER BY f.file_name
            """
        ).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


def build_manifest(db_path: str | Path) -> dict[str, Any]:
    rows = load_scan_rows(db_path)
    group = build_single_manual_group(rows)
    return {
        "schema_version": "manual_group_manifest.v1",
        "source_db": str(db_path),
        "grouping_strategy": "single_manual_by_dominant_publication_number",
        "manuals": [group.to_dict()],
    }


def write_manifest(manifest: dict[str, Any], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
