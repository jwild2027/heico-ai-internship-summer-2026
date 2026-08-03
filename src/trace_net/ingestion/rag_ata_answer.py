"""Deterministic ATA-section answers for the TIFF RAG CLI.

Exact ATA section queries such as ``Find evidence for ATA 25-21-00`` should not
be routed through part-number lookup. This module reads the exported logical
organization JSON and returns a concise source-page answer without calling the
LLM or embeddings.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Iterable

from tiff.document_organization_query import (
    OrganizationExport,
    collect_pages,
    format_ata,
    load_export,
    query_ata,
)

ATA_RE = re.compile(r"\b(?:ATA\s*)?(\d{2}-\d{2}-\d{2})\b", re.IGNORECASE)
ATA_INTENT_WORDS = {
    "ata",
    "section",
    "evidence",
    "source",
    "sources",
    "page",
    "pages",
    "find",
    "show",
    "list",
    "browse",
    "open",
    "where",
}


@dataclass(frozen=True)
class AtaSectionAnswer:
    """A deterministic source-backed ATA section answer."""

    ata_code: str
    answer: str
    found: bool
    page_count: int = 0
    part_count: int = 0


def extract_ata_code(question: str) -> str:
    """Return the first ATA code in *question*, or an empty string."""
    match = ATA_RE.search(question or "")
    return match.group(1).upper() if match else ""


def looks_like_ata_query(question: str) -> bool:
    """Return True when the user appears to be asking for an ATA section.

    A bare ``25-21-00`` is allowed because that pattern is not a normal HEICO
    part-number shape in this backend, while ``120-37313-001`` will not match.
    """
    ata = extract_ata_code(question)
    if not ata:
        return False
    lowered = (question or "").lower()
    if "ata" in lowered:
        return True
    tokens = set(re.findall(r"[a-zA-Z]+", lowered))
    return bool(tokens & ATA_INTENT_WORDS)


def build_ata_section_answer(
    export_dir: str | Path,
    question: str,
    *,
    page_limit: int = 8,
) -> AtaSectionAnswer | None:
    """Build a deterministic ATA answer from organization export files.

    Returns ``None`` when *question* is not an ATA query so callers can continue
    with normal RAG routing.
    """
    ata_code = extract_ata_code(question)
    if not ata_code or not looks_like_ata_query(question):
        return None

    export = load_export(export_dir)
    matches = query_ata(export, ata_code, limit=10)
    if not matches:
        return AtaSectionAnswer(
            ata_code=ata_code,
            found=False,
            answer=f"I did not find ATA {ata_code} in the exported document organization tree.",
        )

    best = _best_ata_match(matches)
    page_count = _count_value(best, "page_count", "pages")
    part_count = _count_value(best, "distinct_part_count", "part_count", "parts", "part_mentions")
    manual = _first_text(best, "manual", "publication_number", "manual_id", "title") or "-"
    all_pages = _pages_for_ata(export, ata_code)
    page_rows = all_pages[: max(1, int(page_limit))]

    lines = [
        f"ATA {ata_code} is present in the local organization tree.",
        f"Manual: {manual}",
        f"Pages: {page_count}",
    ]
    if part_count:
        lines.append(f"Logical parts in section: {part_count}")
    lines.append("")
    lines.append("Sample source pages:")
    for idx, page in enumerate(page_rows, start=1):
        page_id = _first_text(page, "page_id", "id") or "-"
        page_label = _first_text(page, "page_label", "page", "page_number", "label") or "-"
        source = _first_text(page, "source_url", "rescarta_url", "url", "source") or "-"
        tiff = _first_text(page, "tiff_path", "image_path", "source_image_path", "tiff", "tiff_uri") or "-"
        ocr = _first_text(page, "ocr_text_path", "ocr_path", "text_path", "ocr", "ocr_file", "ocr_file_path", "ocr_uri") or "-"
        part_count_for_page = _page_part_count(page)
        details = f"parts={part_count_for_page}" if part_count_for_page else "parts=0"
        if _is_empty_ocr_page(page):
            details += " empty_ocr=True"
        lines.append(f"{idx}. page={page_id} label={page_label} {details}")
        lines.append(f"   Source: {source}")
        lines.append(f"   TIFF: {tiff}")
        lines.append(f"   OCR: {ocr}")
    if len(all_pages) > len(page_rows):
        lines.append(f"... {len(all_pages) - len(page_rows)} more pages not shown")
    lines.append("")
    lines.append("Note: this answer comes from the exported logical organization tree, not the LLM.")

    return AtaSectionAnswer(
        ata_code=ata_code,
        found=True,
        page_count=page_count,
        part_count=part_count,
        answer="\n".join(lines).strip(),
    )


def _best_ata_match(matches: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(matches)
    if not rows:
        return {}
    return sorted(rows, key=lambda row: _count_value(row, "page_count", "pages"), reverse=True)[0]


def _pages_for_ata(export: OrganizationExport, ata_code: str) -> list[dict[str, Any]]:
    needle = ata_code.upper()
    pages = []
    for page in collect_pages(export):
        value = _first_text(page, "ata", "ata_code", "ataCode") or ""
        if value.upper() == needle:
            pages.append(page)
    return sorted(pages, key=_page_sort_key)


def _page_sort_key(page: dict[str, Any]) -> tuple[int, int, int, str]:
    """Prefer useful evidence pages while keeping page order stable.

    ATA sections can contain front matter or intentionally blank pages. For a
    user asking for evidence, the first examples should be pages that have
    non-empty OCR and extracted logical parts, not blank/source-cover pages.
    """
    empty_rank = 1 if _is_empty_ocr_page(page) else 0
    part_rank = 0 if _page_part_count(page) > 0 else 1
    seq = page.get("page_sequence")
    if isinstance(seq, int):
        order = seq
    else:
        label = _first_text(page, "page_label", "page", "page_number", "label") or ""
        order = int(label) if label.isdigit() else 999999
    return (empty_rank, part_rank, order, str(page.get("page_id") or ""))


def _is_empty_ocr_page(page: dict[str, Any]) -> bool:
    for key in ("empty_ocr", "ocr_empty", "empty_ocr_file", "is_empty_ocr"):
        value = page.get(key)
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)) and value in {0, 1}:
            return bool(value)
        if isinstance(value, str) and value.strip().lower() in {"1", "true", "yes", "y"}:
            return True
    return False


def _page_part_count(page: dict[str, Any]) -> int:
    for key in ("part_numbers", "parts", "part_ids"):
        value = page.get(key)
        if isinstance(value, list):
            return len(value)
        if isinstance(value, dict):
            return len(value)
    for key in ("part_count", "distinct_part_count", "part_mention_count"):
        value = page.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
    return 0


def _first_text(mapping: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, (str, int, float)):
            text = str(value).strip()
            if text:
                return text
    return None


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
