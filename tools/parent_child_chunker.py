"""tools/parent_child_chunker.py — Hybrid parent-child chunking.

Produces two levels of chunks from the same pages:
    - PARENT chunks: large (~600 words) for LLM context
    - CHILD chunks:  small (~120 words) for embedding/search

Only children get embedded into ChromaDB. At retrieval time, the child's
parent_id is used to fetch the full parent text from SQLite for the LLM.

This is the enterprise pattern: precise search + full context.

Usage:
    from tools.parent_child_chunker import build_parent_child_chunks
    parents, children = build_parent_child_chunks(pages, source_name="my_doc")
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tools.pymupdf_bge_chroma_cli as base


# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

PARENT_TARGET_WORDS = 600
PARENT_MAX_WORDS    = 800
CHILD_TARGET_WORDS  = 90
CHILD_MAX_WORDS     = 140
CHILD_OVERLAP_WORDS = 20


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

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
    chunk_index:   int             # order within the parent
    page_start:    int
    page_end:      int
    word_count:    int
    char_start:    int             # offset into the parent's text
    char_end:      int
    metadata:      dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def _make_id(source: str, kind: str, idx: int) -> str:
    """Deterministic ID based on source + kind + index."""
    import hashlib
    return hashlib.sha256(f"{source}::{kind}::{idx}".encode()).hexdigest()[:32]


def _split_into_word_windows(
    text: str,
    target_words: int,
    overlap: int,
) -> list[tuple[int, int, str]]:
    """Split text into overlapping word windows.

    Returns list of (char_start, char_end, window_text).
    """
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


def build_parent_chunks(
    pages: list[dict[str, Any]],
    source_name: str,
    target_words: int = PARENT_TARGET_WORDS,
    max_words: int = PARENT_MAX_WORDS,
) -> list[ParentChunk]:
    """Build large parent chunks using the existing semantic chunker logic.

    Reuses base.build_chunks() with parent-sized targets so heading detection
    and block boundaries stay consistent with the flat strategy.
    """
    base_chunks = base.build_chunks(
        pages,
        target_words=target_words,
        max_words=max_words,
        overlap_blocks=0,           # parents don't overlap; children do
        source_name=source_name,
    )

    parents: list[ParentChunk] = []
    for idx, chunk in enumerate(base_chunks):
        parent_id = _make_id(source_name, "parent", idx)
        parents.append(ParentChunk(
            parent_id=parent_id,
            text=chunk.text,
            title=chunk.title or "Untitled section",
            page_start=int(chunk.metadata.get("page_start") or 0),
            page_end=int(chunk.metadata.get("page_end") or 0),
            word_count=base.block_word_count(chunk.text),
            metadata={
                "source":        source_name,
                "section_title": chunk.title or "Untitled section",
                "block_count":   chunk.metadata.get("block_count", 0),
            },
        ))
    return parents


def build_child_chunks(
    parents: list[ParentChunk],
    source_name: str,
    target_words: int = CHILD_TARGET_WORDS,
    overlap_words: int = CHILD_OVERLAP_WORDS,
) -> list[ChildChunk]:
    """Split each parent into smaller, overlapping child chunks for embedding."""
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
                    "source":          source_name,
                    "parent_title":    parent.title,
                    "parent_id":       parent.parent_id,
                    "child_index":     local_idx,
                    "total_children":  len(windows),
                },
            ))
            global_idx += 1

    return children


def build_parent_child_chunks(
    pages: list[dict[str, Any]],
    source_name: str,
) -> tuple[list[ParentChunk], list[ChildChunk]]:
    """Convenience function that builds both levels in one call."""
    parents = build_parent_chunks(pages, source_name)
    children = build_child_chunks(parents, source_name)
    return parents, children


# ---------------------------------------------------------------------------
# Quick stats helper
# ---------------------------------------------------------------------------

def summarize(parents: list[ParentChunk], children: list[ChildChunk]) -> str:
    if not parents:
        return "no chunks produced"
    avg_parent = sum(p.word_count for p in parents) / len(parents)
    avg_child  = sum(c.word_count for c in children) / len(children) if children else 0
    avg_ratio  = len(children) / len(parents) if parents else 0
    return (
        f"{len(parents)} parents (avg {avg_parent:.0f} words), "
        f"{len(children)} children (avg {avg_child:.0f} words), "
        f"~{avg_ratio:.1f} children per parent"
    )
