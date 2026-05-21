"""tools/chunking_strategy.py — Document profiler and strategy selector.

Analyzes a PDF to decide whether to use flat semantic chunking or
parent-child chunking. The decision is based on document characteristics
that map to real-world RAG patterns.

Decision rules:
    page_count >= 30                      → parent_child (long-form)
    heading_density >= 0.5/page           → parent_child (well-structured)
    avg_page_words >= 400 AND pages >= 10 → parent_child (dense content)
    otherwise                             → flat

Usage:
    from tools.chunking_strategy import choose_strategy
    strategy, reason = choose_strategy(pages)
    if strategy == "parent_child":
        chunks = chunk_parent_child(pages, ...)
    else:
        chunks = chunk_flat(pages, ...)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Literal

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tools.pymupdf_bge_chroma_cli as base


Strategy = Literal["flat", "parent_child"]


def profile_document(pages: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute structural metrics about a document."""
    page_count = len(pages)
    total_words = 0
    total_headings = 0
    has_tables_or_figures = False

    for page in pages:
        text = page.get("text", "") or ""
        words = len(re.findall(r"\S+", text))
        total_words += words

        # Count heading-like lines on this page
        for line in text.splitlines():
            if base.is_heading_line(line.strip()):
                total_headings += 1

        # Detect table/figure markers
        if re.search(r"\[(?:Figure|Table)\s+[\d-]+\]", text, re.IGNORECASE):
            has_tables_or_figures = True

    avg_page_words = total_words / page_count if page_count else 0
    heading_density = total_headings / page_count if page_count else 0

    return {
        "page_count":            page_count,
        "total_words":           total_words,
        "avg_page_words":        round(avg_page_words, 1),
        "total_headings":        total_headings,
        "heading_density":       round(heading_density, 2),
        "has_tables_or_figures": has_tables_or_figures,
    }


def choose_strategy(pages: list[dict[str, Any]]) -> tuple[Strategy, str]:
    """Return (strategy, human-readable reason) based on document profile.

    Returns 'flat' for short or simple documents, 'parent_child' for
    long-form structured documents where context windows matter.
    """
    profile = profile_document(pages)

    page_count       = profile["page_count"]
    avg_page_words   = profile["avg_page_words"]
    heading_density  = profile["heading_density"]

    # Rule 1: long documents always benefit from parent-child
    if page_count >= 30:
        return "parent_child", (
            f"long-form document ({page_count} pages) — parent-child preserves "
            f"section context across multiple chunks"
        )

    # Rule 2: strong heading hierarchy means natural parent boundaries
    if heading_density >= 0.5 and page_count >= 10:
        return "parent_child", (
            f"well-structured document ({heading_density:.1f} headings/page across "
            f"{page_count} pages) — parent boundaries align with document sections"
        )

    # Rule 3: dense content benefits from larger LLM context
    if avg_page_words >= 400 and page_count >= 10:
        return "parent_child", (
            f"dense content ({avg_page_words:.0f} words/page across {page_count} pages) "
            f"— LLM needs full surrounding context for accurate answers"
        )

    # Default: flat semantic chunking for short/simple documents
    return "flat", (
        f"compact document ({page_count} pages, {avg_page_words:.0f} words/page) "
        f"— self-contained chunks are precise enough without parent context"
    )


def explain_strategy(pages: list[dict[str, Any]]) -> str:
    """Human-readable explanation of the strategy decision."""
    strategy, reason = choose_strategy(pages)
    profile = profile_document(pages)
    return (
        f"Strategy: {strategy}\n"
        f"Reason:   {reason}\n"
        f"Profile:  {profile['page_count']} pages, "
        f"{profile['avg_page_words']} avg words/page, "
        f"{profile['heading_density']} headings/page, "
        f"tables/figures={profile['has_tables_or_figures']}"
    )