"""Final user-facing answer quality overlay for TRACE-Net H30.

This layer runs after the existing evidence-aware answer modes, exact-page
answer mode, and final Engram rollout. It does not retrieve evidence, select a
route, call an LLM, or mutate source stores. It only:

* renders concise route-specific answers from the already-selected evidence;
* uses the writer's existing citation registry;
* removes internal status/debug wording from user-visible text;
* suppresses generic follow-ups for already-specific requests; and
* revalidates the final rendered answer against the same registry.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

from scripts.trace_net_h30_layout_aware_ocr_v1 import (
    format_layout_row,
    reconstruct_layout_aware_ocr,
)

MODULE = "trace_net_h30_answer_quality_v1"
STATUS = "TRACE_NET_H30_ANSWER_QUALITY_V1"
PATCH_ID = "trace_net_h30_answer_quality_patch_v1"

PAGE_RE = re.compile(r"\bt_p_[A-Za-z0-9_]+\b", re.I)
STD_PART_RE = re.compile(r"\b\d{2,4}-\d{4,6}(?:-\d{3})?(?:/\d{3})?\b", re.I)
ALT_PART_RE = re.compile(r"\b(?:[A-Z]{2,}\d{5,}|\d{2,4}[A-Z]{2,}\d{4,})(?:[.\-/][A-Z0-9]+)*\b", re.I)
ATA_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")
FIGURE_RE = re.compile(r"\bfigure\s+\d+[a-z]?(?:\s+sheet\s+\d+)?\b", re.I)
QUOTED_RE = re.compile(r"['\"]([^'\"]{4,})['\"]")
CITATION_RE = re.compile(r"\[(\d{1,3})\]")

SPECIFIC_ROUTES = {
    "exact_identifier_lookup",
    "guided_part_discovery",
    "nomenclature_function_search",
    "ata_system_discovery",
    "exact_table_ipl_lookup",
    "visual_figure_callout_lookup",
    "procedure_task_lookup",
    "ocr_scan_recovery",
    "graph_relationship_reasoning",
    "document_page_navigation",
    "warning_caution_note_lookup",
    "cross_source_comparison",
    "contradiction_resolution",
    "high_degree_entity_aggregation",
    "multi_question_research",
}

INTERNAL_PATTERNS = tuple(
    re.compile(pattern, re.I)
    for pattern in (
        r"entity_gate_removed_",
        r"returned status\s+\d+",
        r"\bstatus\s+599\b",
        r"calibrated cascade route brain",
        r"unlinked_visual_candidate",
        r"trace_net_[a-z0-9_]+",
        r"retrieval_tunnels?",
        r"candidate/source conflict record",
        r"internal identifier",
    )
)

NOISE_TOKENS = {
    "CCCC", "CCCCC", "EEEE", "EEEEE", "SSSS", "TTTT", "NNNN",
    "WS4956", "VS4956", "MCE", "LEP",
}

TECHNICAL_LABEL_PATTERNS: Tuple[Tuple[str, str], ...] = (
    (r"\bSEAT BACKRESTS?\b", "Seat backrest"),
    (r"\bSEAT BELT\b", "Seat belt"),
    (r"\bASHTRAY\b", "Ashtray"),
    (r"\bFLOATABLE SEAT BOTTOM\b", "Floatable seat bottom"),
    (r"\bDOUBLE PASSENGER SEAT\b", "Double passenger seat"),
    (r"\bSINGLE PASSENGER SEAT\b", "Single passenger seat"),
    (r"\bTRIPLE PASSENGER SEAT\b", "Triple passenger seat"),
    (r"\bBAGGAGE PROTECTOR\b", "Baggage protector"),
    (r"\bLUGGAGE PROTECTOR\b", "Luggage protector"),
    (r"\bLATERAL LEG STRUCTURE\b", "Lateral leg structure"),
    (r"\bCENTER LEG STRUCTURE\b", "Center leg structure"),
    (r"\bCENTRAL LEG STRUCTURE\b", "Central leg structure"),
    (r"\bLEG STRUCTURE\b", "Leg structure"),
    (r"\bSTRINGER\b", "Stringer"),
    (r"\bARMREST\b", "Armrest"),
    (r"\bLOCKING RING\b", "Locking ring"),
    (r"\bSPRING PIN\b", "Spring pin"),
    (r"\bATTACH(?:MENT)? PIN\b", "Attachment pin"),
    (r"\bSNACK TABLE ASSY\b", "Snack-table assembly"),
    (r"\bCOVER,? LATCH\b", "Latch cover"),
)


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _rows(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _compact(value: Any, limit: int = 1200) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()[:limit]


def _norm_identifier(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def _citation(entry: Mapping[str, Any]) -> str:
    try:
        number = int(entry.get("citation_id"))
    except (TypeError, ValueError):
        return ""
    return f"[{number}]" if number > 0 else ""


def _entry_text(entry: Mapping[str, Any]) -> str:
    return _compact(
        entry.get("identifier_blob")
        or entry.get("value")
        or entry.get("candidate_value")
        or entry.get("field_name"),
        12000,
    )


def _entry_page(entry: Mapping[str, Any]) -> str:
    page = str(entry.get("page_id") or "").strip()
    if page:
        return page
    for value in entry.get("page_ids") or []:
        if value:
            return str(value)
    match = PAGE_RE.search(_entry_text(entry))
    return match.group(0) if match else ""


def _entry_identifier(entry: Mapping[str, Any]) -> str:
    value = str(entry.get("candidate_value") or "").strip()
    if value:
        return value
    text = _entry_text(entry)
    match = STD_PART_RE.search(text) or ALT_PART_RE.search(text)
    return match.group(0) if match else ""


def _all_identifiers(text: str) -> List[str]:
    output: List[str] = []
    seen = set()
    for pattern in (STD_PART_RE, ALT_PART_RE):
        for match in pattern.findall(str(text or "")):
            value = str(match).strip(".,;:()[]")
            key = _norm_identifier(value)
            if not value or not key or key in seen:
                continue
            # Drop normal words accidentally caught by the alternate pattern.
            if value.isalpha():
                continue
            seen.add(key)
            output.append(value)
    return output


def _query_identifier(query: str) -> str:
    match = STD_PART_RE.search(query) or ALT_PART_RE.search(query)
    return match.group(0) if match else ""


def _query_page(query: str) -> str:
    match = PAGE_RE.search(query)
    return match.group(0) if match else ""


def _query_ata(query: str) -> str:
    match = ATA_RE.search(query)
    return match.group(0) if match else ""


def _query_clue(query: str) -> str:
    match = QUOTED_RE.search(query)
    return _compact(match.group(1), 320) if match else ""


def _page_content(result: Mapping[str, Any]) -> Mapping[str, Any]:
    envelope = _mapping(result.get("evidence_envelope"))
    coverage = _mapping(envelope.get("coverage"))
    return _mapping(coverage.get("page_content"))


def _page_packs(result: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    page_content = _page_content(result)
    pages = page_content.get("pages")
    if not page_content.get("available") or not isinstance(pages, list):
        return []
    return [row for row in pages if isinstance(row, Mapping) and row.get("found") is not False]


def _record_citation(record: Mapping[str, Any]) -> str:
    try:
        number = int(record.get("citation_id"))
    except (TypeError, ValueError):
        return ""
    return f"[{number}]" if number > 0 else ""


def _is_internal_text(text: str) -> bool:
    return any(pattern.search(str(text or "")) for pattern in INTERNAL_PATTERNS)


def _strip_internal_lines(text: str) -> str:
    output: List[str] = []
    for line in str(text or "").splitlines():
        if _is_internal_text(line):
            continue
        output.append(line.rstrip())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(output)).strip()


def _clean_nomenclature(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        raw = " ".join(str(item) for item in value if str(item).strip())
    else:
        raw = str(value or "")
    text = _compact(raw, 500).upper()
    if not text:
        return ""
    if any(phrase in text for phrase in ("USING THE INSTALLED", "PAGE TEXT", "EFFECTIVITY", "MAINTENANCE MANUAL")):
        return ""
    text = re.sub(r"\([^)]*P/?N[^)]*\)", " ", text)
    text = re.sub(r"\b\d{2,4}-\d{4,6}(?:-\d{3})?(?:/\d{3})?\b", " ", text)
    text = re.sub(r"[^A-Z0-9,./() -]+", " ", text)
    tokens: List[str] = []
    for token in re.findall(r"[A-Z0-9]+", text):
        if token in NOISE_TOKENS:
            continue
        if re.search(r"(.)\1\1", token):
            continue
        if any(ch.isdigit() for ch in token) and any(ch.isalpha() for ch in token):
            continue
        if token.isdigit():
            continue
        if len(token) <= 2 and token not in {"LH", "RH"}:
            continue
        if len(token) == 3 and token not in {
            "PIN", "LEG", "ASSY", "SEAT", "RING", "NUT", "CAP", "ARM",
        }:
            continue
        tokens.append(token)
    # Collapse repeated words while preserving order.
    clean: List[str] = []
    for token in tokens:
        if clean and clean[-1] == token:
            continue
        clean.append(token)
    if not clean:
        return ""
    value = " ".join(clean[:8])
    value = value.replace(" ASSY", " assembly")
    value = value.title().replace("Lh", "LH").replace("Rh", "RH")
    return value.strip()


def _entry_nomenclature(entry: Mapping[str, Any]) -> str:
    names = entry.get("nomenclature")
    clean = _clean_nomenclature(names)
    if clean:
        return clean
    field = str(entry.get("field_name") or "")
    if field and field.lower() not in {"candidate", "summary", "value", "part_number"}:
        clean = _clean_nomenclature(field)
        if clean:
            return clean
    text = _entry_text(entry)
    # Prefer the text after the candidate identifier when it looks like a label.
    identifier = _entry_identifier(entry)
    if identifier and identifier in text:
        clean = _clean_nomenclature(text.split(identifier, 1)[1])
        if clean:
            return clean
    return ""


def _technical_labels(text: str) -> List[str]:
    output: List[str] = []
    seen = set()
    upper = str(text or "").upper()
    for pattern, label in TECHNICAL_LABEL_PATTERNS:
        if re.search(pattern, upper, re.I) and label.casefold() not in seen:
            seen.add(label.casefold())
            output.append(label)
    return output


def _figures(text: str) -> List[str]:
    output: List[str] = []
    seen = set()
    for match in FIGURE_RE.findall(str(text or "")):
        value = re.sub(r"\s+", " ", match).strip().title()
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            output.append(value)
    return output


def _registry_by_class(registry: Sequence[Mapping[str, Any]], *tokens: str) -> List[Mapping[str, Any]]:
    allowed = tuple(token.lower() for token in tokens)
    return [
        entry for entry in registry
        if any(token in str(entry.get("class") or "").lower() for token in allowed)
    ]


def _dedupe_entries(entries: Iterable[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    output: List[Mapping[str, Any]] = []
    seen = set()
    for entry in entries:
        identifier = _entry_identifier(entry)
        page = _entry_page(entry)
        text = _entry_text(entry)
        key = (
            _norm_identifier(identifier),
            page.casefold(),
            text[:180].casefold(),
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(entry)
    return output


def _matching_identifier_entries(
    registry: Sequence[Mapping[str, Any]],
    query_identifier: str,
) -> List[Mapping[str, Any]]:
    target = _norm_identifier(query_identifier)
    entries = _dedupe_entries(registry)
    if not target:
        return entries
    exact: List[Mapping[str, Any]] = []
    partial: List[Mapping[str, Any]] = []
    for entry in entries:
        candidate = _norm_identifier(_entry_identifier(entry))
        blob = _norm_identifier(_entry_text(entry))
        if candidate == target:
            exact.append(entry)
        elif target and (target in candidate or target in blob):
            partial.append(entry)
    return exact + partial


def _candidate_lines(
    registry: Sequence[Mapping[str, Any]],
    query: str,
    *,
    maximum: int,
) -> List[str]:
    query_id = _query_identifier(query)
    entries = _matching_identifier_entries(
        [
            entry for entry in registry
            if str(entry.get("class") or "").lower() in {"candidate", "direct_source"}
            or "candidate" in str(entry.get("class") or "").lower()
        ],
        query_id,
    )
    output: List[str] = []
    seen = set()
    for entry in entries:
        identifier = _entry_identifier(entry)
        citation = _citation(entry)
        if not identifier or not citation:
            continue
        key = _norm_identifier(identifier)
        if key in seen:
            continue
        seen.add(key)
        page = _entry_page(entry)
        name = _entry_nomenclature(entry)
        details = []
        if name:
            details.append(name)
        if page:
            details.append(f"page `{page}`")
        suffix = " — " + "; ".join(details) if details else ""
        output.append(f"- `{identifier}`{suffix} {citation}")
        if len(output) >= maximum:
            break
    return output


def _page_entries(registry: Sequence[Mapping[str, Any]], maximum: int = 8) -> List[Tuple[str, str]]:
    output: List[Tuple[str, str]] = []
    seen = set()
    for entry in registry:
        page = _entry_page(entry)
        citation = _citation(entry)
        if not page or not citation or page.casefold() in seen:
            continue
        seen.add(page.casefold())
        output.append((page, citation))
        if len(output) >= maximum:
            break
    return output


def _extract_procedure_steps(text: str, maximum: int = 10) -> List[str]:
    source = _compact(text, 12000)
    if not source:
        return []
    source = re.sub(r"^.*?ILLUSTRATED PARTS LIST", "", source, flags=re.I)
    source = re.sub(r"\bEFFECTIVITY\s*:\s*.*$", "", source, flags=re.I)
    pattern = re.compile(
        r"(?:\(([a-z])\)|\b([a-z])\))\s+(.+?)(?=(?:\([a-z]\)|\b[a-z]\))\s+|\bNOTE\s*:|\b[A-Z]\.\s+[A-Z][A-Za-z ]+\(figure|$)",
        re.I,
    )
    output: List[str] = []
    for match in pattern.finditer(source):
        label = (match.group(1) or match.group(2) or "").lower()
        body = _compact(match.group(3), 700)
        body = re.split(r"\b(?:PART QTY MATERIAL|Repair Materials|Repair Procedure)\b", body, maxsplit=1, flags=re.I)[0]
        body = body.strip(" .;:-")
        if len(body) < 10:
            continue
        body = body[0].upper() + body[1:]
        output.append(f"{label}. {body}")
        if len(output) >= maximum:
            break
    return output


def _render_procedure_page(pack: Mapping[str, Any]) -> str:
    page = str(pack.get("page_id") or "the requested page")
    ocr_records = [row for row in pack.get("ocr") or [] if isinstance(row, Mapping)]
    if not ocr_records:
        return f"## Answer\n\nNo readable procedure text was recovered for page `{page}`."
    record = ocr_records[0]
    citation = _record_citation(record)
    text = str(record.get("text") or "")
    steps = _extract_procedure_steps(text)
    lines = ["## Answer", "", f"Page `{page}` contains the following readable procedure steps {citation}:".strip()]
    if steps:
        lines.extend(f"- {step} {citation}".strip() for step in steps)
    else:
        summary = _compact(text, 700)
        lines.append(f"- The OCR recovered this procedure text: {summary} {citation}".strip())
    notes: List[str] = []
    if re.search(r"\bNOTE\s*:", text, re.I):
        notes.append("The page also contains one or more notes; follow the cited source page for their exact wording.")
    if re.search(r"\bas described in item\s+\w+", text, re.I):
        notes.append("Some steps refer to other numbered items that are not reproduced on this page.")
    if notes:
        lines.extend(["", "### Limits"])
        lines.extend(f"- {note} {citation}".strip() for note in notes)
    return "\n".join(lines).strip()


def _render_visual_page(pack: Mapping[str, Any]) -> str:
    page = str(pack.get("page_id") or "the requested page")
    ocr_records = [row for row in pack.get("ocr") or [] if isinstance(row, Mapping)]
    visual_records = [row for row in pack.get("visuals") or [] if isinstance(row, Mapping)]
    context_records: List[Mapping[str, Any]] = []
    for key in ("v3_page_intelligence", "v2_context", "v1_context"):
        context_records.extend(row for row in pack.get(key) or [] if isinstance(row, Mapping))

    ocr = ocr_records[0] if ocr_records else {}
    ocr_text = str(ocr.get("text") or "")
    ocr_citation = _record_citation(ocr)
    visual = visual_records[0] if visual_records else {}
    visual_text = str(visual.get("text") or "")
    visual_citation = _record_citation(visual)
    if _is_internal_text(visual_text):
        visual_text = ""

    labels = _technical_labels(ocr_text)
    identifiers = _all_identifiers(ocr_text)
    figures = _figures(ocr_text)
    for row in context_records:
        text = str(row.get("text") or "")
        for label in _technical_labels(text):
            if label not in labels:
                labels.append(label)
        for identifier in _all_identifiers(text):
            if _norm_identifier(identifier) not in {_norm_identifier(x) for x in identifiers}:
                identifiers.append(identifier)
        for figure in _figures(text):
            if figure.casefold() not in {x.casefold() for x in figures}:
                figures.append(figure)

    heading_bits: List[str] = []
    if labels:
        heading_bits.append(labels[0])
    if figures:
        heading_bits.append(figures[0])
    heading = " — ".join(heading_bits) or "illustrated page"
    lines = ["## Answer", "", f"Page `{page}` contains an illustrated diagram: {heading} {ocr_citation or visual_citation}.".strip()]
    if labels:
        lines.append(f"- Visible labels include: {', '.join(labels[:8])} {ocr_citation}.".replace(" .", "."))
    if identifiers:
        lines.append(f"- Printed identifier(s): {', '.join(f'`{value}`' for value in identifiers[:8])} {ocr_citation}.".replace(" .", "."))
    if figures:
        lines.append(f"- Figure reference(s): {', '.join(figures[:4])} {ocr_citation}.".replace(" .", "."))
    if visual_text:
        clean_visual = _compact(visual_text, 360)
        lines.append(f"- Visual summary: {clean_visual} {visual_citation}.".replace(" .", "."))
    elif visual_citation:
        lines.append(f"- A diagram is present, but the current visual record does not resolve every numbered callout to a specific item {visual_citation}.")
    elif re.search(r"\b\d{1,3}\b", ocr_text):
        lines.append(f"- Numbered callouts are visible in the OCR, but their item mapping remains uncertain {ocr_citation}.")
    return "\n".join(lines).strip()


def _render_generic_page(pack: Mapping[str, Any]) -> str:
    page = str(pack.get("page_id") or "the requested page")
    records: List[Mapping[str, Any]] = []
    for key in ("ocr", "tables", "visuals", "v3_page_intelligence", "v2_context", "v1_context"):
        records.extend(row for row in pack.get(key) or [] if isinstance(row, Mapping))
    if not records:
        return f"## Answer\n\nNo content was recovered for page `{page}`."
    first = records[0]
    citation = _record_citation(first)
    text = _compact(first.get("text"), 600)
    return f"## Answer\n\nPage `{page}` contains: {text} {citation}".strip()


def _render_exact_page(result: Mapping[str, Any], route: str) -> str:
    packs = _page_packs(result)
    if not packs:
        page = _query_page(str(result.get("query") or ""))
        return f"## Answer\n\nPage `{page}` was not found in the indexed evidence." if page else ""
    pack = packs[0]
    if route == "procedure_task_lookup":
        return _render_procedure_page(pack)
    if route == "visual_figure_callout_lookup":
        return _render_visual_page(pack)
    return _render_generic_page(pack)


def _render_ata(query: str, registry: Sequence[Mapping[str, Any]]) -> str:
    ata = _query_ata(query)
    candidate_lines = _candidate_lines(registry, query, maximum=6)
    pages = _page_entries(registry, maximum=8)
    lines = ["## Answer", ""]
    if ata:
        lines.append(f"For ATA `{ata}`, TRACE-Net found the following indexed evidence:")
    else:
        lines.append("TRACE-Net found the following ATA-related indexed evidence:")
    if candidate_lines:
        lines.extend(["", "### Part candidates"])
        lines.extend(candidate_lines)
    if pages:
        lines.extend(["", "### Source pages"])
        lines.extend(f"- `{page}` {citation}" for page, citation in pages)
    if not candidate_lines and not pages:
        lines.append("\nNo matching parts or source pages were recovered.")
    else:
        lines.extend(["", "The available records are navigation and candidate evidence; use the cited pages for the exact table or manual wording."])
    return "\n".join(lines).strip()


def _render_table(query: str, registry: Sequence[Mapping[str, Any]]) -> str:
    identifier = _query_identifier(query)
    table_entries = [entry for entry in registry if "table" in str(entry.get("class") or "").lower()]
    matching = _matching_identifier_entries(table_entries, identifier)
    if matching:
        entry = matching[0]
        page = _entry_page(entry)
        citation = _citation(entry)
        text = _compact(_entry_text(entry), 520)
        lines = ["## Answer", "", f"The IPL/table record contains `{identifier}` {citation}." if identifier else f"A matching IPL/table record was found {citation}."]
        if page:
            lines.append(f"- Source page: `{page}` {citation}")
        if text:
            lines.append(f"- Table text: {text} {citation}")
        return "\n".join(lines).strip()
    candidate_lines = _candidate_lines(registry, query, maximum=4)
    if candidate_lines:
        return "\n".join([
            "## Answer",
            "",
            f"The table search found `{identifier}` as a candidate, but no exact table-cell record was available in the final evidence pack." if identifier else "The table search found candidate records, but no exact table-cell record was available in the final evidence pack.",
            "",
            *candidate_lines,
        ]).strip()
    return f"## Answer\n\n`{identifier}` was not found in the available IPL/table evidence." if identifier else "## Answer\n\nNo matching IPL/table evidence was found."


def _render_ocr_recovery(query: str, registry: Sequence[Mapping[str, Any]]) -> str:
    clue = _query_clue(query)
    pages = _page_entries(registry, maximum=4)
    lines = ["## Answer", ""]
    if pages:
        page, citation = pages[0]
        lines.append(f"The strongest indexed match for the supplied OCR clue is page `{page}` {citation}.")
        entry = next((row for row in registry if _entry_page(row) == page and _citation(row) == citation), None)
        evidence_text = _entry_text(entry or {})
        if clue and clue.casefold() in evidence_text.casefold():
            lines.append(f"- Matched OCR text: “{clue}” {citation}")
        elif clue:
            lines.append(f"- Search clue: “{clue}”")

        layout = reconstruct_layout_aware_ocr(evidence_text)
        if layout.get("reconstruction_available"):
            if layout.get("table_kind") == "list_of_effective_pages":
                lines.append("- The clue appears to combine cells from a List of Effective Pages table rather than one continuous sentence.")
            else:
                lines.append("- The OCR appears to combine values from separate table columns or rows.")
            for row in layout.get("rows") or []:
                rendered_row = format_layout_row(row)
                if rendered_row:
                    lines.append(f"- Reconstructed row: {rendered_row} {citation}")
            lines.append("- This is a layout reconstruction from OCR, not a scan-quality or blur classification.")
        elif evidence_text:
            excerpt = _compact(evidence_text, 420)
            if not _is_internal_text(excerpt):
                lines.append(f"- Evidence excerpt: {excerpt} {citation}")
        lines.append("- OCR reading order and broken characters should be checked against the page image; no scan-quality condition is inferred from OCR alone.")
    else:
        lines.append("No indexed page matched the supplied OCR clue.")
    return "\n".join(lines).strip()


def _render_graph_relationship(query: str, registry: Sequence[Mapping[str, Any]]) -> str:
    identifier = _query_identifier(query)
    entries = _matching_identifier_entries(registry, identifier)
    candidate = next((entry for entry in entries if _entry_identifier(entry)), None)
    lines = ["## Answer", ""]
    explicit = next(
        (
            entry for entry in entries
            if re.search(r"\b(?:part of|contained in|installed in|member of|assembly)\b", _entry_text(entry), re.I)
            and _citation(entry)
        ),
        None,
    )
    if explicit:
        citation = _citation(explicit)
        lines.append(f"The graph evidence describes this relationship: {_compact(_entry_text(explicit), 420)} {citation}")
        return "\n".join(lines).strip()
    if identifier:
        lines.append(f"No explicit assembly relationship was recovered for `{identifier}`.")
    else:
        lines.append("No explicit assembly relationship was recovered.")
    if candidate:
        citation = _citation(candidate)
        page = _entry_page(candidate)
        name = _entry_nomenclature(candidate)
        details = []
        if name:
            details.append(name)
        if page:
            details.append(f"page `{page}`")
        suffix = "; ".join(details) or "a graph-linked candidate record"
        lines.append(f"- The graph-linked evidence associates `{_entry_identifier(candidate)}` with {suffix} {citation}.")
    return "\n".join(lines).strip()


def _render_candidate_route(query: str, registry: Sequence[Mapping[str, Any]], route: str) -> str:
    identifier = _query_identifier(query)
    lines_found = _candidate_lines(registry, query, maximum=10)
    if not lines_found:
        if identifier:
            return f"## Answer\n\nNo indexed match was found for `{identifier}`."
        return "## Answer\n\nNo matching part candidates were found."
    title = "Matching candidates"
    if route == "exact_identifier_lookup" and identifier:
        title = f"Best indexed match for `{identifier}`"
    elif route == "nomenclature_function_search":
        title = "Best matching part candidates"
    lines = ["## Answer", "", f"### {title}", *lines_found]
    if route == "guided_part_discovery" and len(lines_found) > 1:
        lines.extend(["", "These are ranked candidates; the cited page should be used to choose among them."])
    elif route == "exact_identifier_lookup":
        lines.extend(["", "The record is a candidate unless a direct table or source field is shown above."])
    return "\n".join(lines).strip()


def _render_negative_page(query: str, result: Mapping[str, Any]) -> str:
    page = _query_page(query)
    packs = _page_packs(result)
    if page and not packs:
        return f"## Answer\n\nPage `{page}` was not found in the indexed document set. No other page was substituted."
    return ""


def _specific_request(query: str, route: str, result: Mapping[str, Any]) -> bool:
    if route in SPECIFIC_ROUTES:
        return True
    if _query_identifier(query) or _query_page(query) or _query_ata(query) or _query_clue(query):
        return True
    return bool(_page_packs(result))


def render_quality_answer(
    result: Mapping[str, Any],
    query: str,
    registry: Sequence[Mapping[str, Any]],
) -> str:
    route = str(result.get("route") or "")
    packs = _page_packs(result)
    if packs:
        return _render_exact_page(result, route)
    negative_page = _render_negative_page(query, result)
    if negative_page:
        return negative_page
    if route == "ata_system_discovery":
        return _render_ata(query, registry)
    if route == "exact_table_ipl_lookup":
        return _render_table(query, registry)
    if route == "ocr_scan_recovery":
        return _render_ocr_recovery(query, registry)
    if route == "graph_relationship_reasoning":
        return _render_graph_relationship(query, registry)
    if route in {"exact_identifier_lookup", "guided_part_discovery", "nomenclature_function_search"}:
        return _render_candidate_route(query, registry, route)
    content = _strip_internal_lines(str(result.get("content") or ""))
    return content


def install_answer_quality(module: MutableMapping[str, Any]) -> None:
    marker = "_TRACE_NET_H30_ANSWER_QUALITY_V1_INSTALLED"
    if module.get(marker):
        return

    runtime_cls = module["Runtime"]
    current_process = runtime_cls.process
    current_health = runtime_cls.health
    citation_registry = module["citation_registry"]
    citation_registry_digest = module["citation_registry_digest"]
    validate_answer = module["validate_answer"]
    extract_latest_user = module["extract_latest_user"]
    synthesis_allowed_identifiers = module.get("synthesis_allowed_identifiers")

    def process_answer_quality(self: Any, payload: Mapping[str, Any]) -> Dict[str, Any]:
        result = dict(current_process(self, payload))
        query = extract_latest_user(payload)
        registry = citation_registry(result)
        old_content = str(result.get("content") or "")
        rendered = render_quality_answer(result, query, registry).strip()
        if not rendered:
            rendered = _strip_internal_lines(old_content)

        specific = _specific_request(query, str(result.get("route") or ""), result)
        if specific:
            # The user already supplied enough identifying context for the current
            # task. Do not append generic discovery questions.
            marker_index = rendered.find("Helpful follow-up questions:")
            if marker_index >= 0:
                rendered = rendered[:marker_index].rstrip()
            result["follow_up_questions"] = []

        extra_allowed = (
            synthesis_allowed_identifiers(query, result)
            if callable(synthesis_allowed_identifiers)
            else None
        )
        validation = validate_answer(
            rendered,
            query,
            result,
            extra_allowed=extra_allowed,
            registry=registry,
        )

        # A quality renderer must never make the answer less safe. If its route-
        # specific version fails validation, fall back to a scrubbed version of the
        # already-produced answer and validate that instead.
        fallback_used = False
        if not validation.get("accepted"):
            fallback = _strip_internal_lines(old_content)
            marker_index = fallback.find("Helpful follow-up questions:")
            if specific and marker_index >= 0:
                fallback = fallback[:marker_index].rstrip()
            fallback_validation = validate_answer(
                fallback,
                query,
                result,
                extra_allowed=extra_allowed,
                registry=registry,
            )
            if fallback_validation.get("accepted"):
                rendered = fallback
                validation = fallback_validation
                fallback_used = True

        result["content"] = rendered
        result["post_answer_validation"] = validation
        result["citation_registry"] = registry
        result["citation_registry_size"] = len(registry)
        result["citation_registry_digest"] = citation_registry_digest(registry)
        result["writer_mode_before_answer_quality"] = result.get("writer_mode")
        result["writer_mode"] = (
            "answer_quality_scrubbed_existing_answer"
            if fallback_used
            else "answer_quality_route_renderer"
        )
        result["answer_quality"] = {
            "status": STATUS,
            "quality_status": "PASS" if validation.get("accepted") else "FAIL",
            "patch_id": PATCH_ID,
            "route": str(result.get("route") or ""),
            "rendered_from_selected_evidence": True,
            "old_answer_changed": rendered.strip() != old_content.strip(),
            "specific_followups_suppressed": bool(specific),
            "internal_status_text_hidden": True,
            "nomenclature_cleaning_enabled": True,
            "ocr_summary_enabled": True,
            "graph_direct_answer_enabled": True,
            "ocr_direct_answer_enabled": True,
            "layout_aware_ocr_reconstruction_enabled": True,
            "layout_reconstruction_is_guidance_only": True,
            "scan_quality_inferred_from_ocr": False,
            "final_validation_accepted": bool(validation.get("accepted")),
            "final_validation_failures": list(validation.get("failures") or []),
            "gemma_call_count_added": 0,
            "retrieval_changed": False,
            "route_changed": False,
            "source_truth_mutation_allowed": False,
            "write_attempt_count": 0,
        }
        result["answer_permission"] = False
        result["final_answer_allowed"] = False
        result["can_answer_directly"] = False
        result["can_prove_claims"] = False
        result["source_truth_mutation_allowed"] = False
        return result

    def health_answer_quality(self: Any) -> Dict[str, Any]:
        result = dict(current_health(self))
        result.update({
            "answer_quality_overlay_enabled": True,
            "answer_quality_status": STATUS,
            "answer_quality_route_specific_rendering": True,
            "answer_quality_final_revalidation": True,
            "answer_quality_internal_status_hidden": True,
            "answer_quality_ocr_summary": True,
            "answer_quality_layout_aware_ocr": True,
            "answer_quality_infers_blur_from_ocr": False,
            "answer_quality_nomenclature_cleaning": True,
            "answer_quality_specific_followups_suppressed": True,
            "answer_quality_adds_gemma_call": False,
            "answer_quality_changes_retrieval": False,
            "answer_permission": False,
            "final_answer_allowed": False,
            "source_truth_mutation_allowed": False,
        })
        return result

    runtime_cls.process = process_answer_quality
    runtime_cls.health = health_answer_quality
    module[marker] = True


__all__ = [
    "MODULE",
    "STATUS",
    "PATCH_ID",
    "install_answer_quality",
    "render_quality_answer",
    "_clean_nomenclature",
    "_extract_procedure_steps",
    "_strip_internal_lines",
]
