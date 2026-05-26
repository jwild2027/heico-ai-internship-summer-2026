"""tools/parent_child_chunker.py — Hybrid parent-child chunking.

Strategy chain:
    1. Try PDF outline (best — uses document's own structure)
    2. Fall back to heading detector (good — uses regex patterns)
    3. Fall back to generic semantic chunker (works for any doc)
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tools.pymupdf_bge_chroma_cli as base
from tools.heading_detectors import select_detector, HeadingDetector
from tools.outline_chunker import (
    extract_outline, outline_is_usable, build_outline_chunks,
)


PARENT_TARGET_WORDS = 600
PARENT_MAX_WORDS    = 800
CHILD_TARGET_WORDS  = 90
CHILD_MAX_WORDS     = 140
CHILD_OVERLAP_WORDS = 20


@dataclass
class ParentChunk:
    parent_id:     str
    text:          str
    title:         str
    page_start:    int
    page_end:      int
    word_count:    int
    metadata:      dict[str, Any] = field(default_factory=dict)


@dataclass
class ChildChunk:
    child_id:      str
    parent_id:     str
    text:          str
    chunk_index:   int
    page_start:    int
    page_end:      int
    word_count:    int
    char_start:    int
    char_end:      int
    metadata:      dict[str, Any] = field(default_factory=dict)


def _make_id(source: str, kind: str, idx: int) -> str:
    import hashlib
    return hashlib.sha256(f"{source}::{kind}::{idx}".encode()).hexdigest()[:32]


def _split_into_word_windows(text: str, target_words: int, overlap: int) -> list[tuple[int, int, str]]:
    words_with_pos: list[tuple[int, int, str]] = []
    for m in re.finditer(r"\S+", text):
        words_with_pos.append((m.start(), m.end(), m.group()))
    if not words_with_pos:
        return []
    if len(words_with_pos) <= target_words:
        return [(0, len(text), text.strip())]
    step = max(target_words - overlap, 1)
    windows = []
    start = 0
    while start < len(words_with_pos):
        slice_ = words_with_pos[start: start + target_words]
        if not slice_:
            break
        char_start = slice_[0][0]
        char_end   = slice_[-1][1]
        window_text = text[char_start:char_end].strip()
        windows.append((char_start, char_end, window_text))
        start += step
    return windows


def _sample_document(pages: list[dict[str, Any]], max_chars: int = 30000) -> str:
    parts = []
    total = 0
    for page in pages[:15]:
        text = page.get("text", "") or ""
        snippet = text[:3000]
        parts.append(snippet)
        total += len(snippet)
        if total >= max_chars:
            break
    return "\n".join(parts)


def _split_chunk_on_headings(chunk_text: str, detector: HeadingDetector) -> list[str]:
    """Split a chunk's text at detected heading positions."""
    headings = detector.find_headings(chunk_text)
    if len(headings) <= 1:
        return [chunk_text]
    positions = [pos for pos, _ in headings]
    segments = []
    for i, pos in enumerate(positions):
        end = positions[i + 1] if i + 1 < len(positions) else len(chunk_text)
        segment = chunk_text[pos:end].strip()
        if segment:
            segments.append(segment)
    if positions[0] > 0:
        prefix = chunk_text[:positions[0]].strip()
        if prefix and segments:
            segments[0] = prefix + "\n\n" + segments[0]
    return segments


def _build_parents_from_outline(
    pages: list[dict[str, Any]],
    outline_parents: list[dict[str, Any]],
    source_name: str,
) -> list[ParentChunk]:
    """Convert outline_chunker output into ParentChunk objects."""
    parents: list[ParentChunk] = []
    for idx, op in enumerate(outline_parents):
        parent_id = _make_id(source_name, "parent", idx)
        parents.append(ParentChunk(
            parent_id=parent_id,
            text=op["text"],
            title=op["title"],
            page_start=op["page_start"],
            page_end=op["page_end"],
            word_count=op["word_count"],
            metadata={
                "source":           source_name,
                "section_title":    op["title"],
                "outline_level":    op.get("outline_level"),
                "chunking_method":  "pdf_outline",
                "detected_heading": op["title"],
                "detector_name":    "pdf_outline",
            },
        ))
    return parents


def _build_parents_from_detector(
    pages: list[dict[str, Any]],
    source_name: str,
    target_words: int,
    max_words: int,
) -> list[ParentChunk]:
    """Fallback: use heading detector + base chunker."""
    sample = _sample_document(pages)
    detector = select_detector(sample)
    print(f"[chunk] Heading detector: {detector.name}")

    base_chunks = base.build_chunks(
        pages,
        target_words=target_words,
        max_words=max_words,
        overlap_blocks=0,
        source_name=source_name,
    )

    split_chunks: list[tuple[str, str, dict]] = []
    for chunk in base_chunks:
        pieces = _split_chunk_on_headings(chunk.text, detector)
        if len(pieces) <= 1:
            split_chunks.append((chunk.text, chunk.title, chunk.metadata))
            continue
        for piece_text in pieces:
            split_chunks.append((piece_text, chunk.title, chunk.metadata))

    parents: list[ParentChunk] = []
    detected_count = 0
    for idx, (text, base_title, base_meta) in enumerate(split_chunks):
        parent_id = _make_id(source_name, "parent", idx)
        detected_title = detector.extract_title(text)
        if detected_title:
            detected_count += 1
        title = detected_title or base_title or "Untitled section"
        parents.append(ParentChunk(
            parent_id=parent_id,
            text=text,
            title=title,
            page_start=int(base_meta.get("page_start") or 0),
            page_end=int(base_meta.get("page_end") or 0),
            word_count=base.block_word_count(text),
            metadata={
                "source":           source_name,
                "section_title":    title,
                "block_count":      base_meta.get("block_count", 0),
                "detected_heading": detected_title,
                "detector_name":    detector.name,
                "chunking_method":  f"detector:{detector.name}",
            },
        ))

    if detected_count and parents:
        pct = (detected_count / len(parents) * 100)
        print(f"[chunk] {detected_count}/{len(parents)} parents got titles from {detector.name} detector ({pct:.0f}%)")

    return parents


def build_parent_chunks(
    pages: list[dict[str, Any]],
    source_name: str,
    pdf_path: Optional[Path] = None,
    target_words: int = PARENT_TARGET_WORDS,
    max_words: int = PARENT_MAX_WORDS,
) -> list[ParentChunk]:
    """Build parent chunks using best available strategy.

    Tries in order:
      1. PDF outline (if pdf_path provided and outline is rich enough)
      2. Heading detector + base chunker
      3. Base chunker alone (built into option 2 as fallback)
    """
    # === Strategy 1: PDF outline (best) ===
    if pdf_path is not None:
        try:
            outline = extract_outline(pdf_path)
            if outline_is_usable(outline):
                print(f"[chunk] Using PDF outline ({len(outline)} entries)")
                outline_parents = build_outline_chunks(pages, outline, source_name)
                if outline_parents:
                    print(f"[chunk] Built {len(outline_parents)} parents from outline")
                    return _build_parents_from_outline(pages, outline_parents, source_name)
                else:
                    print("[chunk] Outline produced no parents, falling back to detector")
            else:
                print(f"[chunk] PDF outline insufficient ({len(outline)} entries), falling back to detector")
        except Exception as exc:
            print(f"[chunk] Outline extraction failed: {exc}, falling back to detector")

    # === Strategy 2 & 3: Heading detector + base chunker ===
    return _build_parents_from_detector(pages, source_name, target_words, max_words)


def build_child_chunks(
    parents: list[ParentChunk],
    source_name: str,
    target_words: int = CHILD_TARGET_WORDS,
    overlap_words: int = CHILD_OVERLAP_WORDS,
) -> list[ChildChunk]:
    children: list[ChildChunk] = []
    global_idx = 0
    for parent in parents:
        windows = _split_into_word_windows(parent.text, target_words, overlap_words)
        for local_idx, (char_start, char_end, window_text) in enumerate(windows):
            if not window_text.strip():
                continue
            child_id = _make_id(source_name, "child", global_idx)
            children.append(ChildChunk(
                child_id=child_id,
                parent_id=parent.parent_id,
                text=window_text,
                chunk_index=local_idx,
                page_start=parent.page_start,
                page_end=parent.page_end,
                word_count=base.block_word_count(window_text),
                char_start=char_start,
                char_end=char_end,
                metadata={
                    "source":           source_name,
                    "parent_title":     parent.title,
                    "parent_id":        parent.parent_id,
                    "child_index":      local_idx,
                    "total_children":   len(windows),
                    "detected_heading": parent.metadata.get("detected_heading"),
                    "detector_name":    parent.metadata.get("detector_name"),
                    "chunking_method":  parent.metadata.get("chunking_method"),
                },
            ))
            global_idx += 1
    return children


def build_parent_child_chunks(
    pages: list[dict[str, Any]],
    source_name: str,
    pdf_path: Optional[Path] = None,
) -> tuple[list[ParentChunk], list[ChildChunk]]:
    parents = build_parent_chunks(pages, source_name, pdf_path=pdf_path)
    children = build_child_chunks(parents, source_name)
    return parents, children


def summarize(parents: list[ParentChunk], children: list[ChildChunk]) -> str:
    if not parents:
        return "no chunks produced"
    avg_parent = sum(p.word_count for p in parents) / len(parents)
    avg_child  = sum(c.word_count for c in children) / len(children) if children else 0
    avg_ratio  = len(children) / len(parents) if parents else 0
    detected = sum(1 for p in parents if p.metadata.get("detected_heading"))
    method = parents[0].metadata.get("chunking_method", "unknown") if parents else "none"
    return (
        f"{len(parents)} parents (avg {avg_parent:.0f} words, "
        f"{detected} titled via {method}), "
        f"{len(children)} children (avg {avg_child:.0f} words), "
        f"~{avg_ratio:.1f} children per parent"
    )


# Backwards-compat shim
def extract_nist_control_title(text: str) -> str | None:
    from tools.heading_detectors import NISTControlDetector
    detector = NISTControlDetector()
    return detector.extract_title(text)