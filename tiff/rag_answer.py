"""Answer generation for local TIFF RAG.

The LLM is deliberately used after source retrieval. For exact part-number
questions, this module answers directly from the cleaned/canonical part catalog
when available. That keeps core part facts deterministic and prevents the LLM
from repeating noisy OCR variants as if they were separate nomenclatures.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .ollama_client import DEFAULT_OLLAMA_URL, OllamaClient, OllamaError
from .rag_chunks import collapse_ws
from .rag_retriever import RagSource, RetrievalResult, retrieve_rag_context
from .rag_router import classify_query


@dataclass(frozen=True)
class RagAnswer:
    question: str
    answer: str
    sources: tuple[RagSource, ...]
    used_llm: bool = False
    used_embeddings: bool = False
    warnings: tuple[str, ...] = ()


PART_NUMBER_RE = re.compile(r"[A-Za-z0-9]+(?:[-/][A-Za-z0-9]+){1,}")
PRIMARY_PART_SOURCE_TYPES = {"part_catalog_clean", "part_catalog"}
NOMENCLATURE_SOURCE_TYPES = {"nomenclature_catalog_clean", "nomenclature_catalog"}
MENTION_SOURCE_TYPES = {"part_mentions"}


def format_source_label(source: RagSource, index: int | None = None) -> str:
    prefix = f"[{index}] " if index is not None else ""
    bits: list[str] = []
    if source.publication_number:
        bits.append(source.publication_number)
    elif source.manual_id:
        bits.append(source.manual_id)
    if source.ata_code:
        bits.append(f"ATA {source.ata_code}")
    if source.page_label:
        bits.append(f"Page {source.page_label}")
    elif source.page_sequence is not None:
        bits.append(f"Seq {source.page_sequence}")
    return prefix + " - ".join(bits)


def _source_page_key(source: RagSource) -> tuple[str, str, str]:
    return (source.manual_id or "", source.page_id or "", source.page_label or "")


def _dedupe_by_page(sources: Iterable[RagSource]) -> list[RagSource]:
    out: list[RagSource] = []
    seen: set[tuple[str, str, str]] = set()
    for source in sources:
        key = _source_page_key(source)
        if key in seen:
            continue
        seen.add(key)
        out.append(source)
    return out


def primary_part_sources(sources: Iterable[RagSource]) -> list[RagSource]:
    """Return catalog sources that can prove a part nomenclature."""

    cleaned = [
        s
        for s in sources
        if s.source_type == "part_catalog_clean" and s.matched_part_number and s.part_nomenclature
    ]
    if cleaned:
        return _dedupe_by_page(cleaned)
    catalog = [
        s
        for s in sources
        if s.source_type == "part_catalog" and s.matched_part_number and s.part_nomenclature
    ]
    return _dedupe_by_page(catalog)


def matching_nomenclature_sources(sources: Iterable[RagSource]) -> list[RagSource]:
    """Return catalog rows found by name/nomenclature lookup."""

    cleaned = [
        s
        for s in sources
        if s.source_type == "nomenclature_catalog_clean" and s.matched_part_number and s.part_nomenclature
    ]
    if cleaned:
        return _dedupe_by_page(cleaned)
    catalog = [
        s
        for s in sources
        if s.source_type == "nomenclature_catalog" and s.matched_part_number and s.part_nomenclature
    ]
    return _dedupe_by_page(catalog)


def additional_part_mentions(sources: Iterable[RagSource], primary: Iterable[RagSource]) -> list[RagSource]:
    """Return extra pages that mention the part but do not prove the name."""

    primary_pages = {_source_page_key(s) for s in primary}
    extras: list[RagSource] = []
    seen: set[tuple[str, str, str]] = set()
    for source in sources:
        if source.source_type not in MENTION_SOURCE_TYPES:
            continue
        if not source.matched_part_number:
            continue
        key = _source_page_key(source)
        if key in primary_pages or key in seen:
            continue
        seen.add(key)
        extras.append(source)
    return extras




def _part_key(source: RagSource) -> str:
    """Return the display part number used for grouping citation evidence."""

    return (source.matched_part_number or "").strip().upper()


def _source_priority(source: RagSource) -> int:
    """Lower values are more useful in the compact evidence pack."""

    order = {
        "part_catalog_clean": 0,
        "nomenclature_catalog_clean": 0,
        "part_catalog": 1,
        "nomenclature_catalog": 1,
        "part_mentions": 2,
        "keyword-and": 3,
        "keyword-or": 4,
        "vector": 5,
    }
    return order.get(source.source_type, 9)


def _dedupe_sources(sources: Iterable[RagSource]) -> list[RagSource]:
    """Dedupe sources by source type, page, and part when possible."""

    out: list[RagSource] = []
    seen: set[tuple[str, str, str, str]] = set()
    for source in sources:
        key = (source.source_type, source.manual_id or "", source.page_id or "", _part_key(source))
        if key in seen:
            continue
        seen.add(key)
        out.append(source)
    return out


def pack_sources_for_llm(
    sources: Iterable[RagSource],
    *,
    answer_mode: str = "auto",
    top_k: int = 6,
) -> tuple[RagSource, ...]:
    """Create a compact, citation-safer source list for the LLM and display.

    Hybrid retrieval can return a flat mix of catalog rows, mention-only pages,
    keyword hits, and vector hits. In a flat list, the LLM may accidentally cite
    a mention page for the wrong part number. For nomenclature summary/compare
    questions, pack sources by part number instead:

    1. catalog/nomenclature rows that prove the name;
    2. a limited number of mention-only pages for the same part number;
    3. a small amount of supplemental keyword/vector context.

    The returned sources preserve the original RagSource objects and source
    numbers are generated from this safer packed order.
    """

    all_sources = sorted(
        _dedupe_sources(sources),
        key=lambda s: (_source_priority(s), -(s.score or 0.0), s.page_sequence or 999999),
    )
    mode = (answer_mode or "auto").lower()
    if mode not in {"nomenclature_summary", "compare", "summarize", "summary", "broad"}:
        return tuple(all_sources)

    catalog_sources = [
        s for s in all_sources
        if s.source_type in {"nomenclature_catalog_clean", "nomenclature_catalog", "part_catalog_clean", "part_catalog"}
        and s.matched_part_number
    ]
    if not catalog_sources:
        return tuple(all_sources[: max(1, top_k * 3)])

    # Keep catalog sources first, one clean source per part where possible.
    packed: list[RagSource] = []
    catalog_by_part: dict[str, RagSource] = {}
    for source in catalog_sources:
        part = _part_key(source)
        if not part:
            continue
        # First source is already the best due to sorting.
        catalog_by_part.setdefault(part, source)

    for part in sorted(catalog_by_part, key=lambda k: catalog_by_part[k].page_sequence or 999999):
        packed.append(catalog_by_part[part])

    # Add mention-only sources under each identified part number.
    mentions_by_part: dict[str, list[RagSource]] = {part: [] for part in catalog_by_part}
    for source in all_sources:
        if source.source_type != "part_mentions":
            continue
        part = _part_key(source)
        if part in mentions_by_part:
            mentions_by_part[part].append(source)

    per_part_limit = max(2, min(6, int(top_k)))
    for part in sorted(catalog_by_part, key=lambda k: catalog_by_part[k].page_sequence or 999999):
        added = 0
        catalog_page = _source_page_key(catalog_by_part[part])
        for source in mentions_by_part.get(part, []):
            if _source_page_key(source) == catalog_page:
                continue
            packed.append(source)
            added += 1
            if added >= per_part_limit:
                break

    # Add a little supplemental context, but keep it after structured evidence.
    packed_pages = {_source_page_key(s) for s in packed}
    supplemental: list[RagSource] = []
    for source in all_sources:
        if source.source_type not in {"keyword-and", "keyword-or", "vector"}:
            continue
        key = _source_page_key(source)
        if key in packed_pages:
            continue
        supplemental.append(source)
        packed_pages.add(key)
        if len(supplemental) >= max(2, min(4, top_k // 2 if top_k > 3 else 2)):
            break
    packed.extend(supplemental)

    return tuple(_dedupe_sources(packed))


def build_structured_evidence_map(sources: Iterable[RagSource]) -> str:
    """Build a grouped evidence map for part/nomenclature summary prompts."""

    source_list = list(sources)
    catalog_sources = [
        s for s in source_list
        if s.source_type in {"nomenclature_catalog_clean", "nomenclature_catalog", "part_catalog_clean", "part_catalog"}
        and s.matched_part_number
    ]
    if not catalog_sources:
        return ""

    source_numbers = {id(source): idx for idx, source in enumerate(source_list, start=1)}
    lines = [
        "STRUCTURED EVIDENCE MAP:",
        "Use this map to keep citations attached to the correct part number.",
        "Do not cite a source for a part unless that source is listed under that same part below.",
    ]
    for catalog in catalog_sources:
        part = catalog.matched_part_number or "UNKNOWN PART"
        nomenclature = catalog.part_nomenclature or "UNKNOWN NOMENCLATURE"
        lines.append("")
        lines.append(f"PART {part}: {nomenclature}")
        lines.append(f"  Catalog source: [{source_numbers[id(catalog)]}]")
        mention_nums: list[str] = []
        for source in source_list:
            if source.source_type != "part_mentions":
                continue
            if _part_key(source) != _part_key(catalog):
                continue
            mention_nums.append(f"[{source_numbers[id(source)]}]")
        if mention_nums:
            lines.append("  Mention-only pages for this same part: " + ", ".join(mention_nums))
        else:
            lines.append("  Mention-only pages for this same part: none in packed context")
    supplemental_nums = [
        f"[{source_numbers[id(source)]}]"
        for source in source_list
        if source.source_type.startswith("keyword") or source.source_type == "vector"
    ]
    if supplemental_nums:
        lines.append("")
        lines.append(
            "Supplemental keyword/vector context, not catalog proof of a part number: "
            + ", ".join(supplemental_nums)
        )
    return "\n".join(lines)

def source_role(source: RagSource) -> str:
    if source.source_type == "part_catalog_clean":
        return "primary cleaned nomenclature source"
    if source.source_type == "part_catalog":
        return "primary catalog nomenclature source"
    if source.source_type == "nomenclature_catalog_clean":
        return "matching cleaned nomenclature source"
    if source.source_type == "nomenclature_catalog":
        return "matching catalog nomenclature source"
    if source.source_type == "part_mentions":
        return "additional part-number mention"
    if source.source_type.startswith("keyword"):
        return "keyword OCR context"
    if source.source_type == "vector":
        return "semantic OCR context"
    return source.source_type


def make_context_block(sources: Iterable[RagSource], max_chars_per_source: int = 1800) -> str:
    blocks: list[str] = []
    for idx, source in enumerate(sources, start=1):
        text = source.evidence_text or source.chunk_text or ""
        text = collapse_ws(text)
        if len(text) > max_chars_per_source:
            text = text[:max_chars_per_source].rstrip() + " ..."
        details: list[str] = [f"SOURCE {idx}: {format_source_label(source)}"]
        details.append(f"Source role: {source_role(source)}")
        if source.matched_part_number:
            details.append(f"Part number: {source.matched_part_number}")
        if source.part_nomenclature:
            details.append(f"Nomenclature: {source.part_nomenclature}")
        if source.part_item_number:
            details.append(f"Item: {source.part_item_number}")
        if source.part_quantity:
            details.append(f"Quantity: {source.part_quantity}")
        if getattr(source, "rescarta_url", None):
            details.append(f"ResCarta URL: {source.rescarta_url}")
        if getattr(source, "source_url", None):
            details.append(f"Source URL: {source.source_url}")
        if source.tiff_path:
            details.append(f"TIFF: {source.tiff_path}")
        if source.ocr_text_path:
            details.append(f"OCR: {source.ocr_text_path}")
        details.append(f"Evidence: {text}")
        blocks.append("\n".join(details))
    return "\n\n".join(blocks)


def build_rag_prompt(question: str, sources: Iterable[RagSource]) -> list[dict[str, str]]:
    source_tuple = tuple(sources)
    evidence_map = build_structured_evidence_map(source_tuple)
    context = make_context_block(source_tuple)
    system = (
        "You are a local aircraft manual assistant. Answer using only the provided "
        "local OCR/context. Do not guess. If the answer is not in the sources, say "
        "that the local sources provided do not show the answer. Always cite source "
        "numbers like [1] or [2]. Keep the answer concise and factual. For exact "
        "part-number questions, prefer sources marked as primary cleaned nomenclature "
        "source or primary catalog nomenclature source. For nomenclature/name searches, "
        "prefer sources marked as matching cleaned nomenclature source and use them to "
        "identify the part number. Treat part_mentions sources as additional appearances "
        "only unless they also contain nomenclature metadata. Do not claim every mention "
        "source proves the part name. Do not list noisy OCR variants unless the user asks. "
        "For broad summary or compare questions, organize the answer by part number first, "
        "then mention the source pages. Follow the STRUCTURED EVIDENCE MAP exactly when it "
        "is provided: never attach a citation to a part number unless that citation is "
        "listed under the same part in the map. Treat keyword/vector sources as supplemental "
        "context, not as proof of a catalog part number."
    )
    map_block = f"\n\n{evidence_map}" if evidence_map else ""
    user = f"Question:\n{question}{map_block}\n\nLocal sources:\n{context}\n\nAnswer with citations:"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _format_source_line(source: RagSource, number: int | None = None) -> str:
    label = format_source_label(source)
    prefix = f"{number}. " if number is not None else "- "
    return f"{prefix}{label}"


def _append_source_paths(lines: list[str], source: RagSource, indent: str = "   ") -> None:
    if getattr(source, "rescarta_url", None):
        lines.append(f"{indent}ResCarta: {source.rescarta_url}")
    if getattr(source, "source_url", None):
        lines.append(f"{indent}Source URL: {source.source_url}")
    if source.tiff_path:
        lines.append(f"{indent}TIFF: {source.tiff_path}")
    if source.ocr_text_path:
        lines.append(f"{indent}OCR: {source.ocr_text_path}")


def build_structured_part_answer(question: str, retrieval: RetrievalResult) -> str | None:
    """Build a deterministic answer for exact part lookups.

    This separates the source that proves the nomenclature from additional pages
    that merely mention the same part number.
    """

    sources = list(retrieval.sources)
    primary = primary_part_sources(sources)
    if not primary:
        return None

    best = primary[0]
    part_number = best.matched_part_number or "The requested part number"
    nomenclature = best.part_nomenclature or "UNKNOWN"

    lines: list[str] = [f"{part_number} is listed as {nomenclature}."]
    detail_bits: list[str] = []
    if best.part_item_number:
        detail_bits.append(f"item {best.part_item_number}")
    if best.part_quantity:
        detail_bits.append(f"quantity {best.part_quantity}")
    if detail_bits:
        lines.append("Catalog details: " + "; ".join(detail_bits) + ".")

    lines.append("")
    lines.append("Primary nomenclature source:")
    lines.append(_format_source_line(best, 1))
    _append_source_paths(lines, best)
    evidence = collapse_ws(best.evidence_text or best.chunk_text)
    if evidence:
        lines.append(f"   Evidence: {evidence[:280]}{'...' if len(evidence) > 280 else ''}")

    # Other cleaned/catalog rows with the same nomenclature are still primary
    # support, but usually one clean source is enough for the main answer.
    other_primary = _dedupe_by_page(primary[1:])
    if other_primary:
        lines.append("")
        lines.append("Other catalog pages with the same cleaned nomenclature:")
        for source in other_primary[:5]:
            lines.append(_format_source_line(source))

    mentions = additional_part_mentions(sources, primary)
    if mentions:
        lines.append("")
        lines.append("Additional pages where this part number appears:")
        for source in mentions[:8]:
            lines.append(_format_source_line(source))
            _append_source_paths(lines, source)

    if mentions:
        lines.append("")
        lines.append(
            "Note: additional appearance pages show where the part number is mentioned; "
            "the primary source above is the source used for the nomenclature."
        )

    return "\n".join(lines).strip()


def build_structured_nomenclature_answer(question: str, retrieval: RetrievalResult) -> str | None:
    """Build a deterministic answer for reverse nomenclature lookups.

    Example: a user enters ``magazine holder`` and the cleaned catalog contains
    ``HOLDER, MAGAZINE`` for ``120-37313-001``. The answer should identify the
    part number and then list additional pages where that part number appears.
    """

    sources = list(retrieval.sources)
    matches = matching_nomenclature_sources(sources)
    if not matches:
        return None

    lines: list[str] = []
    if len(matches) == 1:
        first = matches[0]
        lines.append(
            f"{first.part_nomenclature} matches part number {first.matched_part_number}."
        )
    else:
        lines.append("I found these part numbers matching that nomenclature:")
        for source in matches[:10]:
            lines.append(f"- {source.matched_part_number}: {source.part_nomenclature}")

    for idx, match in enumerate(matches[:10], start=1):
        if len(matches) > 1:
            lines.append("")
            lines.append(f"Match {idx}: {match.matched_part_number} — {match.part_nomenclature}")

        lines.append("")
        lines.append("Matching catalog source:")
        lines.append(_format_source_line(match, 1 if len(matches) == 1 else None))
        _append_source_paths(lines, match)
        evidence = collapse_ws(match.evidence_text or match.chunk_text)
        if evidence:
            lines.append(f"   Evidence: {evidence[:280]}{'...' if len(evidence) > 280 else ''}")

        part_mentions = [
            s
            for s in additional_part_mentions(sources, [match])
            if s.matched_part_number and match.matched_part_number and s.matched_part_number == match.matched_part_number
        ]
        if part_mentions:
            lines.append("")
            lines.append(f"Additional pages where {match.matched_part_number} appears:")
            for source in part_mentions[:12]:
                lines.append(_format_source_line(source))
                _append_source_paths(lines, source)

    lines.append("")
    lines.append(
        "Note: the matching catalog source identifies the part number for the nomenclature; "
        "the additional pages show where that part number is mentioned."
    )
    return "\n".join(lines).strip()


STRUCTURED_PART_SUMMARY_MODES = {"nomenclature_summary", "compare", "summarize", "summary", "broad"}


def _best_catalog_sources_by_part(sources: Iterable[RagSource]) -> dict[str, RagSource]:
    """Return the strongest catalog/nomenclature source for each part number."""

    catalog_types = {
        "nomenclature_catalog_clean",
        "part_catalog_clean",
        "nomenclature_catalog",
        "part_catalog",
    }
    candidates = [
        s
        for s in sources
        if s.source_type in catalog_types
        and s.matched_part_number
        and s.part_nomenclature
    ]
    candidates.sort(key=lambda s: (_source_priority(s), -(s.score or 0.0), s.page_sequence or 999999))
    by_part: dict[str, RagSource] = {}
    for source in candidates:
        part = _part_key(source)
        if not part:
            continue
        by_part.setdefault(part, source)
    return by_part


def _mentions_for_exact_part(
    sources: Iterable[RagSource],
    part_key: str,
    catalog_source: RagSource,
) -> list[RagSource]:
    """Return mention-only sources for one part, never crossing part numbers."""

    out: list[RagSource] = []
    seen_pages = {_source_page_key(catalog_source)}
    for source in sorted(sources, key=lambda s: (s.page_sequence or 999999, -(s.score or 0.0))):
        if source.source_type != "part_mentions":
            continue
        if _part_key(source) != part_key:
            continue
        page_key = _source_page_key(source)
        if page_key in seen_pages:
            continue
        seen_pages.add(page_key)
        out.append(source)
    return out


def _related_supplemental_sources(
    sources: Iterable[RagSource],
    used_pages: set[tuple[str, str, str]],
    *,
    limit: int = 6,
) -> list[RagSource]:
    """Return keyword/vector context that is related but not proof of part identity."""

    out: list[RagSource] = []
    for source in sorted(sources, key=lambda s: (_source_priority(s), -(s.score or 0.0), s.page_sequence or 999999)):
        if source.source_type not in {"keyword-and", "keyword-or", "vector"}:
            continue
        page_key = _source_page_key(source)
        if page_key in used_pages:
            continue
        used_pages.add(page_key)
        out.append(source)
        if len(out) >= limit:
            break
    return out


def _primary_summary_nomenclature(catalog_by_part: dict[str, RagSource]) -> str:
    counts: dict[str, int] = {}
    for source in catalog_by_part.values():
        name = (source.part_nomenclature or "UNKNOWN").strip()
        counts[name] = counts.get(name, 0) + 1
    if not counts:
        return "matching catalog nomenclature"
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _source_mentions_item_not_illustrated(source: RagSource) -> bool:
    text = f"{source.evidence_text or ''} {source.chunk_text or ''}".upper()
    return "ITEM NOT ILLUSTRATED" in text


def build_structured_part_summary_answer(
    question: str,
    retrieval: RetrievalResult,
    *,
    top_k: int = 8,
    supplemental_limit: int = 4,
) -> str | None:
    """Build a deterministic grouped answer for part/nomenclature summaries.

    Broad hybrid retrieval can collect the right evidence, but an LLM may still
    attach a citation from one part number to another. This function writes the
    structured portion in code:

    * one catalog/nomenclature source per part as primary proof;
    * only part_mentions with the same part number under that part;
    * keyword/vector hits listed separately as supplemental related pages.
    """

    sources = list(retrieval.sources)
    catalog_by_part = _best_catalog_sources_by_part(sources)
    if len(catalog_by_part) < 2:
        return None

    ordered_parts = sorted(
        catalog_by_part,
        key=lambda part: (
            catalog_by_part[part].part_nomenclature or "",
            catalog_by_part[part].page_sequence if catalog_by_part[part].page_sequence is not None else 999999,
            part,
        ),
    )
    common_name = _primary_summary_nomenclature(catalog_by_part)
    part_word = "part number" if len(ordered_parts) == 1 else "part numbers"
    lines: list[str] = [
        f"The local sources identify {len(ordered_parts)} {part_word} matching {common_name}:",
        "",
    ]

    used_pages: set[tuple[str, str, str]] = set()
    for idx, part in enumerate(ordered_parts, start=1):
        catalog = catalog_by_part[part]
        display_part = catalog.matched_part_number or part
        nomenclature = catalog.part_nomenclature or "UNKNOWN"
        lines.append(f"{idx}. {display_part} - {nomenclature}")
        detail_bits: list[str] = []
        if catalog.part_item_number:
            detail_bits.append(f"item {catalog.part_item_number}")
        if catalog.part_quantity:
            detail_bits.append(f"quantity {catalog.part_quantity}")
        if detail_bits:
            lines.append("   Catalog details: " + "; ".join(detail_bits) + ".")

        lines.append("   Primary catalog source:")
        lines.append(f"   - {format_source_label(catalog)}")
        _append_source_paths(lines, catalog, indent="     ")
        evidence = collapse_ws(catalog.evidence_text or catalog.chunk_text)
        if evidence:
            lines.append(f"     Evidence: {evidence[:260]}{'...' if len(evidence) > 260 else ''}")
        used_pages.add(_source_page_key(catalog))

        mentions = _mentions_for_exact_part(sources, part, catalog)
        if mentions:
            lines.append(f"   Additional pages where {display_part} appears:")
            for source in mentions[: max(1, top_k)]:
                lines.append(f"   - {format_source_label(source)}")
                _append_source_paths(lines, source, indent="     ")
                used_pages.add(_source_page_key(source))

        if _source_mentions_item_not_illustrated(catalog) or any(_source_mentions_item_not_illustrated(m) for m in mentions[: max(1, top_k)]):
            lines.append("   Note: at least one local source marks this part as ITEM NOT ILLUSTRATED.")
        lines.append("")

    supplemental = _related_supplemental_sources(sources, used_pages, limit=supplemental_limit)
    if supplemental:
        lines.append("Supplemental related pages from keyword/vector retrieval:")
        for source in supplemental:
            lines.append(f"- {format_source_label(source)} ({source.source_type})")
            _append_source_paths(lines, source)
        lines.append("")

    lines.append(
        "Note: primary catalog sources prove the part-number/nomenclature relationship. "
        "Additional pages only show where the exact part number appears. "
        "Supplemental keyword/vector pages are related context, not catalog proof."
    )
    return "\n".join(lines).strip()


def extractive_answer(question: str, retrieval: RetrievalResult, *, allow_structured: bool = True) -> str:
    """Create a safe non-LLM answer from retrieved evidence."""

    if allow_structured:
        structured = build_structured_part_answer(question, retrieval)
        if structured:
            return structured
        structured_name = build_structured_nomenclature_answer(question, retrieval)
        if structured_name:
            return structured_name

    sources = list(retrieval.sources)
    if not sources:
        return "I did not find matching local TIFF/OCR sources for that question."

    answer = "I found relevant local sources, but I did not find a structured part-name answer in the catalog. Review these source pages:\n"
    for idx, source in enumerate(sources[:5], start=1):
        answer += f"{idx}. {format_source_label(source)}\n"
        evidence = collapse_ws(source.evidence_text or source.chunk_text)
        if evidence:
            answer += f"   Evidence: {evidence[:240]}{'...' if len(evidence) > 240 else ''}\n"
        if source.tiff_path:
            answer += f"   TIFF: {source.tiff_path}\n"
    return answer.strip()


def answer_question(
    db_path: Path | str,
    question: str,
    *,
    embed_model: str = "bge-m3:latest",
    llm_model: str = "llama3.1:8b",
    ollama_url: str = DEFAULT_OLLAMA_URL,
    top_k: int = 6,
    use_llm: bool = True,
    use_embeddings: bool = True,
    answer_mode: str = "auto",
    retrieval_mode: str = "auto",
    force_llm: bool = False,
    force_embeddings: bool = False,
) -> RagAnswer:
    route = classify_query(question, answer_mode=answer_mode, retrieval_mode=retrieval_mode, force_llm=force_llm)
    retrieval = retrieve_rag_context(
        db_path,
        question,
        top_k=top_k,
        embed_model=embed_model,
        ollama_url=ollama_url,
        use_embeddings=use_embeddings,
        answer_mode=answer_mode,
        retrieval_mode=retrieval_mode,
        force_embeddings=force_embeddings,
    )
    warnings = list(retrieval.warnings)
    if not retrieval.sources:
        return RagAnswer(
            question=question,
            answer="I did not find matching local TIFF/OCR sources for that question.",
            sources=(),
            used_llm=False,
            used_embeddings=retrieval.used_embeddings,
            warnings=tuple(warnings),
        )

    # Structured part/nomenclature summaries are safest when grouped by code.
    # This prevents the LLM from assigning a mention page from one part number to
    # a different part number. Users can still force an LLM-written version with
    # --force-llm.
    if route.answer_mode in STRUCTURED_PART_SUMMARY_MODES and not force_llm:
        structured_summary = build_structured_part_summary_answer(question, retrieval, top_k=top_k)
        if structured_summary:
            packed_sources = pack_sources_for_llm(
                retrieval.sources,
                answer_mode=route.answer_mode,
                top_k=top_k,
            )
            return RagAnswer(
                question=question,
                answer=structured_summary,
                sources=packed_sources,
                used_llm=False,
                used_embeddings=retrieval.used_embeddings,
                warnings=tuple(warnings),
            )

    # Lookup and locate questions are safest when answered deterministically from
    # the cleaned catalog. Summarize/compare/broad questions skip these templates
    # unless the structured part-summary template above matched.
    if route.allow_structured_answer and not force_llm:
        structured = build_structured_part_answer(question, retrieval)
        if structured:
            return RagAnswer(
                question=question,
                answer=structured,
                sources=retrieval.sources,
                used_llm=False,
                used_embeddings=retrieval.used_embeddings,
                warnings=tuple(warnings),
            )

        structured_name = build_structured_nomenclature_answer(question, retrieval)
        if structured_name:
            return RagAnswer(
                question=question,
                answer=structured_name,
                sources=retrieval.sources,
                used_llm=False,
                used_embeddings=retrieval.used_embeddings,
                warnings=tuple(warnings),
            )

    if use_llm:
        try:
            packed_sources = pack_sources_for_llm(
                retrieval.sources,
                answer_mode=route.answer_mode,
                top_k=top_k,
            )
            messages = build_rag_prompt(question, packed_sources)
            answer = OllamaClient(ollama_url).chat(llm_model, messages, temperature=0.0, num_ctx=8192)
            return RagAnswer(
                question=question,
                answer=answer,
                sources=packed_sources,
                used_llm=True,
                used_embeddings=retrieval.used_embeddings,
                warnings=tuple(warnings),
            )
        except OllamaError as exc:
            warnings.append(f"LLM answer fell back to extractive mode: {exc}")
        except Exception as exc:
            warnings.append(f"LLM answer fell back to extractive mode: {exc}")

    return RagAnswer(
        question=question,
        answer=extractive_answer(question, retrieval, allow_structured=route.allow_structured_answer and not force_llm),
        sources=retrieval.sources,
        used_llm=False,
        used_embeddings=retrieval.used_embeddings,
        warnings=tuple(warnings),
    )
