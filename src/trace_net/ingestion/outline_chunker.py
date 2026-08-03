"""tools/outline_chunker.py — Build chunks from PDF outline/bookmarks.

When a PDF has a proper outline (table of contents bookmarks), it's the
authoritative source of section boundaries. We use it to build chunks where
each outline entry becomes one parent chunk, with the entry title as the
chunk title.

This is the highest-quality chunking strategy because it uses the document's
own declared structure rather than guessing from text patterns.

Usage:
    from tools.outline_chunker import extract_outline, build_outline_chunks
    outline = extract_outline(pdf_path)
    if outline_is_usable(outline):
        parents = build_outline_chunks(pages, outline, source_name)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tools.pymupdf_bge_chroma_cli as base


MIN_OUTLINE_ENTRIES = 10        # require at least 10 outline entries to use this strategy
MIN_LEAF_ENTRIES    = 5         # and at least 5 leaf (deepest-level) entries
MAX_PARENT_WORDS    = 1500      # split outline sections that exceed this


def extract_outline(pdf_path: Path) -> list[dict[str, Any]]:
    """Extract the PDF outline as a list of {level, title, page_start, page_end}.

    PyMuPDF returns the outline as [(level, title, page_number), ...].
    We post-process to compute page_end for each entry (next entry's page - 1).
    """
    import fitz
    with fitz.open(str(pdf_path)) as doc:
        toc = doc.get_toc()  # [[level, title, page], ...]
        total_pages = doc.page_count

    if not toc:
        return []

    entries: list[dict[str, Any]] = []
    for level, title, page in toc:
        entries.append({
            "level":      int(level),
            "title":      title.strip(),
            "page_start": int(page),
            "page_end":   total_pages,  # tentative, fixed in next pass
        })

    # Set page_end for each entry to (next entry's page - 1), at the same or higher level
    for i, entry in enumerate(entries):
        next_page = total_pages
        for later in entries[i + 1:]:
            if later["page_start"] > entry["page_start"]:
                next_page = later["page_start"] - 1
                break
        entry["page_end"] = max(entry["page_start"], next_page)

    return entries


def outline_is_usable(outline: list[dict[str, Any]]) -> bool:
    """Decide if the outline is rich enough to chunk from.
    Need enough entries AND meaningful leaf entries (not just chapter-level)."""
    if len(outline) < MIN_OUTLINE_ENTRIES:
        return False
    max_level = max((e["level"] for e in outline), default=0)
    if max_level < 2:
        return False  # too coarse — only chapter-level entries
    leaf_count = sum(1 for e in outline if e["level"] == max_level)
    return leaf_count >= MIN_LEAF_ENTRIES


def _select_chunkable_entries(outline: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pick which outline entries become parent chunks.

    Strategy: use the deepest level entries (leaves). Chapter and section
    headers above them serve as parent context but don't make their own chunks.
    For NIST 800-53 this means each control (L3: 'AC-2 ACCOUNT MANAGEMENT')
    is its own chunk, while L1/L2 headers like 'THE CONTROLS' / '3.1 ACCESS
    CONTROL' are dropped (their content is already covered by the L3 children).
    """
    if not outline:
        return []

    max_level = max(e["level"] for e in outline)
    # Use deepest level
    leaves = [e for e in outline if e["level"] == max_level]

    # If deepest level still has < 5 entries, also include the level above
    if len(leaves) < 5 and max_level > 1:
        leaves = [e for e in outline if e["level"] >= max_level - 1]

    return leaves


def _collect_pages_for_range(
    pages: list[dict[str, Any]],
    page_start: int,
    page_end: int,
) -> str:
    """Concatenate page text for a given page range."""
    parts = []
    for page in pages:
        pn = int(page.get("page", 0))
        if page_start <= pn <= page_end:
            text = (page.get("text") or "").strip()
            if text:
                parts.append(text)
    return "\n\n".join(parts)


def _split_oversized_section(text: str, max_words: int) -> list[str]:
    """If an outline section is too long, split into word-target subsections."""
    words = re.findall(r"\S+", text)
    if len(words) <= max_words:
        return [text]

    # Split into chunks of max_words with no overlap (parents don't overlap)
    pieces = []
    for start in range(0, len(words), max_words):
        slice_ = words[start: start + max_words]
        pieces.append(" ".join(slice_))
    return pieces


def build_outline_chunks(
    pages: list[dict[str, Any]],
    outline: list[dict[str, Any]],
    source_name: str,
) -> list[dict[str, Any]]:
    """Build parent chunks from outline entries.

    Returns list of dicts with:
        text, title, page_start, page_end, word_count, outline_level
    """
    entries = _select_chunkable_entries(outline)
    parents: list[dict[str, Any]] = []

    for entry in entries:
        text = _collect_pages_for_range(pages, entry["page_start"], entry["page_end"])
        if not text.strip():
            continue

        # Split oversized sections (e.g. a control with multi-page enhancements)
        pieces = _split_oversized_section(text, MAX_PARENT_WORDS)
        for piece_idx, piece in enumerate(pieces):
            title = entry["title"]
            if len(pieces) > 1:
                title = f"{title} (part {piece_idx + 1}/{len(pieces)})"
            parents.append({
                "text":          piece,
                "title":         title,
                "page_start":    entry["page_start"],
                "page_end":      entry["page_end"],
                "word_count":    len(piece.split()),
                "outline_level": entry["level"],
                "source":        source_name,
            })

    return parents


def summarize(parents: list[dict[str, Any]]) -> str:
    if not parents:
        return "no chunks produced from outline"
    avg = sum(p["word_count"] for p in parents) / len(parents)
    return f"{len(parents)} outline-based parents (avg {avg:.0f} words)"