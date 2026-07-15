#!/usr/bin/env python3
"""Canonical H30 answer boundaries shared by the router and benchmark.

This module is deliberately deterministic and read-only.  It does not promote
candidate, semantic, visual, graph, summary, OCR, or table guidance into source
truth.  It only makes the requested field, query clues, proof boundary, and
source-authority boundary explicit in user-visible text.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Mapping, Sequence

MODULE = "trace_net_h30_answer_boundary_v1"

TECHNICAL_ROUTES = {
    "exact_identifier_lookup",
    "guided_part_discovery",
    "ata_system_discovery",
    "nomenclature_function_search",
    "exact_table_ipl_lookup",
    "visual_figure_callout_lookup",
    "procedure_task_lookup",
    "warning_caution_note_lookup",
    "authority_eligibility_verification",
    "document_page_navigation",
    "graph_relationship_reasoning",
    "semantic_discovery",
    "cross_source_comparison",
    "contradiction_resolution",
    "ocr_scan_recovery",
    "high_degree_entity_aggregation",
    "multi_question_research",
}

ROUTE_FIELD_MARKERS: Dict[str, Sequence[str]] = {
    "exact_identifier_lookup": ("part", "p/n", "component", "identifier"),
    "guided_part_discovery": ("candidate", "part", "p/n", "prefix", "suffix", "contains"),
    "ata_system_discovery": ("ata", "chapter", "system"),
    "nomenclature_function_search": ("nomenclature", "component", "assembly", "function"),
    "exact_table_ipl_lookup": ("table", "ipl", "item", "row", "column", "nomenclature", "quantity", "vendor"),
    "visual_figure_callout_lookup": ("figure", "diagram", "drawing", "visual", "image", "callout", "illustration"),
    "procedure_task_lookup": ("procedure", "step", "remove", "removal", "install", "installation", "tool", "task"),
    "warning_caution_note_lookup": ("warning", "caution", "note", "precaution", "hazard", "safety"),
    "authority_eligibility_verification": ("approval", "approved", "effectivity", "interchange", "authority", "eligibility", "applicability", "installation"),
    "document_page_navigation": ("page", "location", "manual", "nearby"),
    "graph_relationship_reasoning": ("assembly", "relationship", "linked", "connected", "contains", "references"),
    "semantic_discovery": ("page", "topic", "related", "about", "information", "material"),
    "cross_source_comparison": ("compare", "comparison", "difference", "revision", "source", "manual"),
    "contradiction_resolution": ("conflict", "contradiction", "mismatch", "disagree", "different", "unresolved"),
    "ocr_scan_recovery": ("ocr", "scan", "scanned", "blurry", "faint", "image", "read"),
    "high_degree_entity_aggregation": ("all", "every", "across", "coverage", "page", "document", "reference"),
    "multi_question_research": ("part", "figure", "table", "warning", "procedure", "authority", "ata", "page", "revision"),
}

ROUTE_FOCUS_LINES: Dict[str, str] = {
    "exact_identifier_lookup": "Requested field: exact part, P/N, component, or identifier lookup.",
    "guided_part_discovery": "Requested field: candidate part discovery using the stated prefix, suffix, contains, nomenclature, or component clues.",
    "ata_system_discovery": "Requested field: ATA chapter and aircraft system discovery.",
    "nomenclature_function_search": "Requested field: component nomenclature, function, or assembly context.",
    "exact_table_ipl_lookup": "Requested field: IPL table row, item, column, nomenclature, quantity, or vendor code.",
    "visual_figure_callout_lookup": "Requested field: figure, diagram, drawing, visual image, illustration, or callout.",
    "procedure_task_lookup": "Requested field: procedure, task, removal, installation, tools, or ordered steps.",
    "warning_caution_note_lookup": "Requested field: warning, caution, note, precaution, hazard, or safety information.",
    "authority_eligibility_verification": "Requested field: approval, fit, effectivity, interchangeability, eligibility, applicability, or installation authority.",
    "document_page_navigation": "Requested field: manual page, nearby page, or source location.",
    "graph_relationship_reasoning": "Requested field: assembly relationship, connection, containment, linkage, or reference.",
    "semantic_discovery": "Requested field: related pages, topic information, or semantically relevant manual material.",
    "cross_source_comparison": "Requested field: comparison or difference between manuals, sources, or revisions.",
    "contradiction_resolution": "Requested field: conflict, contradiction, mismatch, disagreement, or unresolved source difference.",
    "ocr_scan_recovery": "Requested field: OCR and scan recovery from blurry, faint, scanned, or image-based text.",
    "high_degree_entity_aggregation": "Requested field: all references, pages, or documents needed for broad coverage.",
    "multi_question_research": "Requested fields: multiple bounded technical claims covering the relevant part, figure, table, procedure, warning, authority, ATA, page, or revision aspects.",
}

PROOF_BOUNDARY = (
    "No direct citation-ready source evidence was found. Candidate, visual, semantic, "
    "graph, summary, OCR, and table-derived results remain guidance only and do not "
    "establish the requested technical claim."
)

AUTHORITY_BOUNDARY = (
    "No explicit authority was found for approval, fit, effectivity, "
    "interchangeability, eligibility, applicability, or installation. None of those "
    "claims is confirmed."
)

CONFLICT_BOUNDARY = (
    "A source or metadata conflict remains unresolved; conflicting values were not "
    "promoted to fact."
)

AUTHORITY_TERMS = (
    "approved replacement",
    "approved for installation",
    "approval",
    "safe to install",
    "fitment",
    "effectivity",
    "interchangeability",
    "eligibility",
    "installation authority",
    "applicability",
    "applicable to",
)


def _rows(envelope: Mapping[str, Any], key: str) -> List[Mapping[str, Any]]:
    value = envelope.get(key)
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, Mapping)]


def _normalized(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _append_unique(lines: List[str], sentence: str) -> None:
    sentence = _normalized(sentence)
    if not sentence:
        return
    existing = "\n".join(lines).casefold()
    if sentence.casefold() not in existing:
        lines.append(sentence)


def _contains_any(text: str, markers: Iterable[str]) -> bool:
    low = text.casefold()
    return any(str(marker).casefold() in low for marker in markers)


def _unique_strings(values: Iterable[Any]) -> List[str]:
    output: List[str] = []
    seen = set()
    for value in values:
        text = _normalized(value)
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(text)
    return output


def query_clue_lines(query: str, query_atoms: Mapping[str, Any], route: str = "") -> List[str]:
    """Return explicit, non-assertive lines that preserve user-supplied clues."""

    lines: List[str] = []

    exact = _unique_strings(query_atoms.get("exact_part_numbers") or [])
    if exact:
        lines.append("Requested exact identifier clue: " + ", ".join(exact) + ".")

    ata_exact = _unique_strings(query_atoms.get("ata_exact") or [])
    ata_prefix = _normalized(query_atoms.get("ata_prefix"))
    ata_values = ata_exact or ([ata_prefix] if ata_prefix else [])
    if ata_values:
        lines.append("Requested ATA chapter/system clue: " + ", ".join(ata_values) + ".")

    part_prefix = _normalized(query_atoms.get("part_prefix"))
    part_contains = _normalized(query_atoms.get("part_contains"))
    part_suffix = _normalized(query_atoms.get("part_suffix"))
    if part_prefix:
        lines.append(f"Requested P/N prefix clue: {part_prefix}.")
    if part_contains:
        lines.append(f"Requested P/N contains clue: {part_contains}.")
    if part_suffix:
        lines.append(f"Requested P/N suffix clue: {part_suffix}.")

    figures = _unique_strings(query_atoms.get("figures") or [])
    if figures:
        lines.append("Requested figure clue: " + ", ".join(figures) + ".")

    items = _unique_strings(query_atoms.get("items") or [])
    if items:
        lines.append("Requested IPL item clue: " + ", ".join(f"item {value}" for value in items) + ".")

    pages = _unique_strings(query_atoms.get("page_ids") or [])
    if pages:
        lines.append("Requested manual page clue: " + ", ".join(pages) + ".")

    nomenclature = _unique_strings(query_atoms.get("nomenclature_terms") or [])
    nomenclature_routes = {
        "guided_part_discovery",
        "nomenclature_function_search",
        "exact_identifier_lookup",
        "exact_table_ipl_lookup",
        "visual_figure_callout_lookup",
        "graph_relationship_reasoning",
        "multi_question_research",
    }
    if nomenclature and route in nomenclature_routes:
        lines.append("Requested nomenclature clue: " + ", ".join(nomenclature) + ".")

    manufacturer = _normalized(query_atoms.get("manufacturer"))
    if manufacturer:
        lines.append(f"Requested manufacturer clue: {manufacturer}.")

    # Preserve the literal user wording as a last-resort clue boundary for unusual
    # figure/item/page syntax without making the wording a factual assertion.
    if not lines and _normalized(query):
        lines.append("Requested technical query: " + _normalized(query) + ".")

    return lines


def enforce_h30_answer_boundaries(
    *,
    route: str,
    query: str,
    query_atoms: Mapping[str, Any],
    evidence_envelope: Mapping[str, Any],
    answer: str,
) -> str:
    """Make route, clue, proof, conflict, and authority boundaries explicit.

    The function only adds user-supplied clues and deterministic limitation text.
    It never creates or promotes evidence.
    """

    text = str(answer or "").strip()
    if route not in TECHNICAL_ROUTES:
        return text

    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    current = "\n".join(lines)

    markers = ROUTE_FIELD_MARKERS.get(route, ())
    if markers and not _contains_any(current, markers):
        _append_unique(lines, ROUTE_FOCUS_LINES[route])

    combined = "\n".join(lines)
    for clue_line in query_clue_lines(query, query_atoms, route=route):
        # Keep each explicit clue visible, even when other generic identifiers occur.
        clue_payload = clue_line.split(":", 1)[-1].strip().rstrip(".")
        if clue_payload and clue_payload.casefold() not in combined.casefold():
            _append_unique(lines, clue_line)
            combined = "\n".join(lines)

    direct = _rows(evidence_envelope, "direct_evidence")
    authority = _rows(evidence_envelope, "authority_evidence")
    contradictions = _rows(evidence_envelope, "contradictions")

    if not direct:
        _append_unique(lines, PROOF_BOUNDARY)

    authority_sensitive = (
        route == "authority_eligibility_verification"
        or _contains_any(query, AUTHORITY_TERMS)
        or _contains_any("\n".join(lines), AUTHORITY_TERMS)
    )
    if authority_sensitive and not authority:
        _append_unique(lines, AUTHORITY_BOUNDARY)

    if contradictions and not _contains_any("\n".join(lines), ("conflict", "mismatch", "unresolved", "contradiction")):
        _append_unique(lines, CONFLICT_BOUNDARY)

    return "\n".join(lines).strip()


def apply_bounded_gemma_fallback(
    gemma: Mapping[str, Any],
    *,
    safe_answer: str,
    failures: Sequence[str],
    follow_up_questions: Sequence[str],
) -> Dict[str, Any]:
    """Replace a rejected benchmark rendering with the validated safe draft.

    Raw model output and raw validation failures remain in the record, so the
    fallback is explicit rather than being reported as a raw-model success.
    """

    output = dict(gemma)
    output["raw_model_answer"] = str(gemma.get("answer") or "")
    output["raw_model_follow_up_questions"] = list(gemma.get("follow_up_questions") or [])
    output["answer"] = str(safe_answer or "").strip()
    output["follow_up_questions"] = _unique_strings(follow_up_questions)
    output["repair_applied"] = True
    output["repair_reasons"] = _unique_strings(failures)
    output["render_mode"] = "deterministic_bounded_fallback_after_gemma_validation"
    review = dict(gemma.get("review") or {}) if isinstance(gemma.get("review"), Mapping) else {}
    review.update({
        "post_answer_validation": "REPAIRED",
        "bounded_fallback_used": True,
        "raw_model_output_accepted": False,
    })
    output["review"] = review
    return output
