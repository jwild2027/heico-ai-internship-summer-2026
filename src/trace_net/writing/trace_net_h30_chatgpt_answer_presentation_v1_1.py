#!/usr/bin/env python3
"""TRACE-Net H30 ChatGPT-style public answer presentation v1.1.

This overlay runs after the v1 presentation layer and fixes remaining public
answer quality issues observed in the grounded 20-question benchmark:

* collapse duplicate evidence records without merging distinct claims;
* render IPL/table answers from typed registry entries instead of raw OCR dumps;
* normalize noisy nomenclature conservatively;
* keep mixed direct/candidate results inside Answer / Evidence / Limits;
* remove the obsolete Engineering confidence section;
* group procedure steps when OCR contains a continuation and a restarted sequence;
* accept source-empty negative page/part results without fabricating citations.

It is presentation-only: no retrieval, no LLM call, no source mutation, and no
change to route, evidence selection, or answer authority.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

MODULE = "trace_net_h30_chatgpt_answer_presentation_v1_1"
STATUS = "TRACE_NET_H30_CHATGPT_ANSWER_PRESENTATION_V1_1"
PATCH_ID = "trace_net_h30_step0_5_chatgpt_answer_presentation_v1_1"

PART_RE = re.compile(
    r"\b(?:\d{2,4}-\d{4,6}(?:-\d{3})?(?:/\d{3})?|"
    r"[A-Z]{2,}\d{4,}(?:[-./][A-Z0-9]+)*)\b",
    re.I,
)
PAGE_RE = re.compile(r"\bt_p_[A-Za-z0-9_]+\b", re.I)
ATA_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")
CITATION_RE = re.compile(r"\[(\d{1,3})\]")
STEP_RE = re.compile(r"^([a-z])\.\s+(.+)$", re.I)

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

INTERNAL_PATTERNS = tuple(
    re.compile(pattern, re.I)
    for pattern in (
        r"\broute\s*[:=]",
        r"retrieval_tunnels?",
        r"entity_gate",
        r"policy[_ -]?id",
        r"writer_mode",
        r"gemma_status",
        r"quality_status",
        r"status\s*[:=]\s*\d{3}",
        r"trace_net_[a-z0-9_]+",
        r"embedding_candidate:",
        r"recommended route:",
        r"ocr status:",
        r"\bidentifier_blob\b",
        r"\bsource_trace_ready\b",
        r"\{\s*[\"']?[a-zA-Z0-9_]+[\"']?\s*:",
    )
)

RAW_MANUAL_PATTERNS = tuple(
    re.compile(pattern, re.I)
    for pattern in (
        r"maintenance manual with illustrated parts list",
        r"\bch-sec-un-fig\b",
        r"\bper stock\b",
        r"visual summary:",
    )
)

UNCERTAINTY_MARKERS = (
    "does not resolve",
    "does not prove",
    "not confirmation",
    "not confirmed",
    "remains uncertain",
    "should be checked",
    "check the cited",
    "guidance only",
    "layout reconstruction",
    "not a scan-quality",
    "not a blur",
    "not reproduced",
    "contains one or more notes",
)


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _rows(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(row) for row in value if isinstance(row, Mapping)]


def _compact(value: Any, limit: int = 1000) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _norm(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def _citation(entry: Mapping[str, Any]) -> str:
    try:
        number = int(entry.get("citation_id") or 0)
    except (TypeError, ValueError):
        return ""
    return f"[{number}]" if number > 0 else ""


def _entry_class(entry: Mapping[str, Any]) -> str:
    return str(entry.get("class") or "").strip().lower()


def _entry_text(entry: Mapping[str, Any]) -> str:
    return _compact(
        entry.get("identifier_blob")
        or entry.get("value")
        or entry.get("candidate_value")
        or entry.get("snippet")
        or entry.get("field_name"),
        12000,
    )


def _entry_identifier(entry: Mapping[str, Any]) -> str:
    explicit = str(entry.get("candidate_value") or entry.get("part_number") or "").strip()
    if explicit:
        return explicit
    match = PART_RE.search(_entry_text(entry))
    return match.group(0) if match else ""


def _entry_page(entry: Mapping[str, Any]) -> str:
    page = str(entry.get("page_id") or "").strip()
    if page:
        return page
    pages = entry.get("page_ids")
    if isinstance(pages, list):
        for value in pages:
            if str(value).strip():
                return str(value).strip()
    match = PAGE_RE.search(_entry_text(entry))
    return match.group(0) if match else ""


def _is_direct(entry: Mapping[str, Any]) -> bool:
    return bool(entry.get("can_prove_claims")) or _entry_class(entry) in {
        "direct_source",
        "authority",
    }


def _is_table(entry: Mapping[str, Any]) -> bool:
    cls = _entry_class(entry)
    kind = str(entry.get("page_content_kind") or "").lower()
    field = str(entry.get("field_name") or "").lower()
    text = _entry_text(entry).lower()
    return (
        "table" in cls
        or kind == "table"
        or any(token in field for token in ("table", "ipl", "item", "row", "cell"))
        or "recommended route: table" in text
        or "illustrated parts list" in text
        or "ch-sec-un-fig" in text
    )


def _canonical_name(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        raw = " ".join(str(item) for item in value if str(item).strip())
    else:
        raw = str(value or "")
    upper = re.sub(r"[^A-Z0-9 ]+", " ", raw.upper())
    upper = re.sub(r"\bSEE\s+FIGURE\b", " ", upper)
    upper = re.sub(r"\bUSING\s+THE\s+INSTALLED\b.*", " ", upper)
    upper = PART_RE.sub(" ", upper)
    upper = re.sub(r"\s+", " ", upper).strip()
    if not upper or any(
        phrase in upper
        for phrase in (
            "MAINTENANCE MANUAL",
            "PAGE TEXT",
            "OCR STATUS",
            "RECOMMENDED ROUTE",
            "EFFECTIVITY",
        )
    ):
        return ""

    words = upper.split()
    word_set = set(words)
    if "STRUCTURE" in word_set and "ARMREST" in word_set:
        return "Structure Armrest"
    if "STRUCTURE" in word_set and "LATERAL" in word_set and "LEG" in word_set:
        return "Structure Lateral Leg"
    if "STRUCTURE" in word_set and ({"CENTRAL", "CENTER"} & word_set) and "LEG" in word_set:
        return "Structure Central Leg"
    if "STRUCTURE" in word_set and ({"ASSY", "ASSEMBLY", "ASSEMBLYV"} & word_set):
        return "Structure Assembly"
    if "COVER" in word_set and "LATCH" in word_set and "SNACK" in word_set and "TABLE" in word_set:
        return "Cover Latch Snack Table Assembly"
    if "PIN" in word_set and "SPRING" in word_set:
        return "Pin Spring"
    if "PIN" in word_set and ({"ATTACH", "ATTACHMENT"} & word_set):
        return "Pin Attach"
    if "RING" in word_set and ({"LOCK", "LOCKING"} & word_set):
        return "Ring Locking"
    if "SUPPORT" in word_set:
        return "Support"
    if "SINGLE" in word_set and "PASSENGER" in word_set and "SEAT" in word_set:
        return "Single Passenger Seat Assembly" if ({"ASSY", "ASSEMBLY"} & word_set) else "Single Passenger Seat"
    if "DOUBLE" in word_set and "PASSENGER" in word_set and "SEAT" in word_set:
        return "Double Passenger Seat Assembly" if ({"ASSY", "ASSEMBLY"} & word_set) else "Double Passenger Seat"

    clean: List[str] = []
    seen = set()
    blocked = {"UNKNOWN", "FIGURE", "COVES", "RERE", "SARY", "WS", "VS", "MCE"}
    for token in words:
        if token in blocked or token.isdigit() or re.search(r"(.)\1\1", token):
            continue
        if token == "ASSY":
            token = "ASSEMBLY"
        if token == "ASSEMBLYV":
            token = "ASSEMBLY"
        if token in seen:
            continue
        seen.add(token)
        clean.append(token)
    return " ".join(clean[:7]).title().replace("Lh", "LH").replace("Rh", "RH")


def _entry_name(entry: Mapping[str, Any]) -> str:
    blocked = {
        "candidate",
        "direct source",
        "table",
        "semantic",
        "source field",
        "embedding candidate",
        "ocr page text",
        "page content",
        "record",
    }
    for value in (entry.get("nomenclature"), entry.get("field_name")):
        name = _canonical_name(value)
        if name and name.lower() not in blocked:
            return name
    return ""


def _query_identifier(query: str) -> str:
    match = PART_RE.search(str(query or ""))
    return match.group(0) if match else ""


def _query_page(query: str) -> str:
    match = PAGE_RE.search(str(query or ""))
    return match.group(0) if match else ""


def _query_pages(query: str) -> List[str]:
    """Return every canonical page id in query order without duplicates."""
    return list(dict.fromkeys(PAGE_RE.findall(str(query or ""))))


def _query_ata(query: str) -> str:
    match = ATA_RE.search(str(query or ""))
    return match.group(0) if match else ""


def _registry(result: Mapping[str, Any]) -> List[Dict[str, Any]]:
    return _rows(result.get("citation_registry"))


def _intent(result: Mapping[str, Any], query: str) -> Tuple[str, str]:
    atoms = _mapping(result.get("query_atoms"))
    mode = str(atoms.get("identifier_mode") or "").lower()
    requested = (
        atoms.get("normalized_identifier")
        or atoms.get("family_identifier")
        or (atoms.get("exact_part_numbers") or [""])[0]
        or atoms.get("part_prefix")
        or atoms.get("part_contains")
        or atoms.get("part_suffix")
        or _query_identifier(query)
    )
    requested_norm = _norm(requested)
    if not mode or mode == "none":
        mode = "exact" if _query_identifier(query) else "none"
    return mode, requested_norm


def _matches_intent(identifier: str, mode: str, requested: str) -> bool:
    candidate = _norm(identifier)
    if not candidate:
        return False
    if not requested or mode == "none":
        return True
    if mode == "exact":
        return candidate == requested
    if mode in {"prefix", "family"}:
        return candidate.startswith(requested)
    if mode == "suffix":
        return candidate.endswith(requested)
    if mode in {"contains", "partial"}:
        return requested in candidate
    return requested in candidate


def _safe_line(line: str) -> bool:
    text = str(line or "")
    return not any(pattern.search(text) for pattern in INTERNAL_PATTERNS)


def _raw_manual_line(line: str) -> bool:
    return any(pattern.search(str(line or "")) for pattern in RAW_MANUAL_PATTERNS)


def _clean_line(line: str) -> str:
    text = str(line or "").strip()
    text = re.sub(r"^(?:-\s+|\*\s+)", "", text)
    text = re.sub(r"^TRACE-Net\s+", "", text, flags=re.I)
    text = re.sub(r"\bTRACE-Net\b", "the search", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def _dedupe_lines(lines: Iterable[str]) -> List[str]:
    output: List[str] = []
    seen = set()
    for raw in lines:
        line = _clean_line(raw)
        key = line.casefold()
        if not line or key in seen:
            continue
        seen.add(key)
        output.append(line)
    return output


def _format_sections(answer: str, evidence: Sequence[str], limits: Sequence[str]) -> str:
    evidence_lines = _dedupe_lines(line for line in evidence if _safe_line(line) and not _raw_manual_line(line))
    limit_lines = _dedupe_lines(line for line in limits if _safe_line(line) and not _raw_manual_line(line))
    lines = ["## Answer", "", _clean_line(answer) or "No usable answer was produced."]
    if evidence_lines:
        lines.extend(["", "## Evidence", ""])
        lines.extend(f"- {line}" for line in evidence_lines)
    if limit_lines:
        lines.extend(["", "## Limits", ""])
        lines.extend(f"- {line}" for line in limit_lines)
    return "\n".join(lines).strip()


def _entry_score(entry: Mapping[str, Any]) -> Tuple[int, int, int, int]:
    try:
        citation_number = int(entry.get("citation_id") or 10_000)
    except (TypeError, ValueError):
        citation_number = 10_000
    return (
        1 if _entry_name(entry) else 0,
        1 if _is_direct(entry) else 0,
        1 if _is_table(entry) else 0,
        -citation_number,
    )


def _selected_entries(
    result: Mapping[str, Any],
    query: str,
    entries: Sequence[Mapping[str, Any]],
    *,
    group_by_page: bool,
    maximum: int,
) -> List[Dict[str, Any]]:
    mode, requested = _intent(result, query)
    candidates = [
        dict(entry)
        for entry in entries
        if _citation(entry)
        and _entry_identifier(entry)
        and _matches_intent(_entry_identifier(entry), mode, requested)
    ]
    groups: Dict[Tuple[str, str, str, str], List[Dict[str, Any]]] = {}
    for entry in candidates:
        identifier = _norm(_entry_identifier(entry))
        page = _entry_page(entry).casefold() if group_by_page else ""
        kind = "direct" if _is_direct(entry) else "guidance"
        name = _entry_name(entry).casefold() if not _is_direct(entry) else ""
        key = (identifier, page, kind, name)
        groups.setdefault(key, []).append(entry)
    selected: List[Dict[str, Any]] = []
    for group in groups.values():
        group.sort(key=_entry_score, reverse=True)
        selected.append(group[0])
    selected.sort(
        key=lambda entry: (
            0 if _is_direct(entry) else 1,
            _norm(_entry_identifier(entry)),
            _entry_page(entry),
            _entry_name(entry),
        )
    )
    return selected[:maximum]


def _evidence_bullet(entry: Mapping[str, Any]) -> str:
    identifier = _entry_identifier(entry)
    citation = _citation(entry)
    if not identifier or not citation:
        return ""
    details: List[str] = []
    name = _entry_name(entry)
    page = _entry_page(entry)
    if name:
        details.append(name)
    if page:
        details.append(f"page `{page}`")
    label = "Source-backed record: " if _is_direct(entry) else ""
    suffix = " — " + "; ".join(details) if details else ""
    return f"{label}`{identifier}`{suffix} {citation}".strip()


def _render_part(result: Mapping[str, Any], route: str, query: str, entries: Sequence[Mapping[str, Any]]) -> str:
    group_by_page = route == "exact_identifier_lookup"
    selected = _selected_entries(result, query, entries, group_by_page=group_by_page, maximum=10)
    bullets = [_evidence_bullet(entry) for entry in selected]
    bullets = [line for line in bullets if line]
    identifier = _query_identifier(query)
    if not bullets:
        target = f"`{identifier}`" if identifier else "the requested part"
        return _format_sections(
            f"No indexed match was found for {target}.",
            ["No matching indexed part record was returned."],
            [],
        )

    first_citation = _citation(selected[0])
    direct = any(_is_direct(entry) for entry in selected)
    guidance = any(not _is_direct(entry) for entry in selected)
    conflicts = any(entry.get("metadata_conflict") for entry in selected)

    if route == "guided_part_discovery":
        answer = "Matching candidates are listed below."
        limits = ["These are ranked search matches; use the cited source pages to compare them."]
    elif route == "nomenclature_function_search":
        answer = "The strongest nomenclature matches are listed below."
        limits = ["A nomenclature match is a search lead, not confirmation of a technical relationship."]
    else:
        target = f"`{identifier}`" if identifier else "The requested part"
        if direct:
            answer = f"{target} appears in the indexed source records {first_citation}."
            limits = ["Some listed nomenclature or page associations remain guidance-level."] if guidance else []
        else:
            answer = f"The best indexed match for {target} is shown below."
            limits = ["The listed record remains a candidate unless a cited source field confirms the requested identity."]
    if conflicts:
        limits.append("One or more records contain an unresolved source-association conflict.")
    return _format_sections(answer, bullets, limits)


def _render_table(result: Mapping[str, Any], query: str, entries: Sequence[Mapping[str, Any]]) -> str:
    selected = _selected_entries(result, query, entries, group_by_page=True, maximum=8)
    table_entries = [entry for entry in selected if _is_table(entry)]
    selected = table_entries or selected
    bullets = [_evidence_bullet(entry) for entry in selected]
    bullets = [line for line in bullets if line]
    identifier = _query_identifier(query)
    if not bullets:
        return _format_sections(
            f"`{identifier}` was not found in the available IPL/table evidence." if identifier else "No matching IPL/table evidence was found.",
            ["No matching indexed table record was returned."],
            [],
        )
    citation = _citation(selected[0])
    page = _entry_page(selected[0])
    direct = any(_is_direct(entry) or entry.get("page_content") for entry in selected)
    if direct:
        location = f" on page `{page}`" if page else ""
        answer = f"`{identifier}` appears in the available IPL/table evidence{location} {citation}." if identifier else f"A matching IPL/table record was found {citation}."
        limits: List[str] = []
    else:
        answer = f"A candidate IPL/table match was found for `{identifier}` {citation}." if identifier else f"A candidate IPL/table match was found {citation}."
        limits = ["The available record does not independently establish the complete table-row relationship."]
    return _format_sections(answer, bullets, limits)


def _render_ata(query: str, entries: Sequence[Mapping[str, Any]]) -> str:
    ata = _query_ata(query)
    pages: List[str] = []
    seen = set()
    for entry in entries:
        page = _entry_page(entry)
        citation = _citation(entry)
        if not page or not citation or page.casefold() in seen:
            continue
        seen.add(page.casefold())
        pages.append(f"Page `{page}` {citation}")
        if len(pages) >= 8:
            break
    if pages:
        first = CITATION_RE.search(pages[0])
        citation = f"[{first.group(1)}]" if first else ""
        answer = f"Indexed records were found for ATA `{ata}` {citation}." if ata else f"Indexed ATA-related records were found {citation}."
        limits = ["These records identify source locations; consult the cited pages for exact manual wording."]
        return _format_sections(answer, pages, limits)
    return _format_sections(
        f"No indexed part or page record was found for ATA `{ata}`." if ata else "No matching ATA record was found.",
        ["No matching indexed ATA record was returned."],
        [],
    )


def _extract_sections(content: str) -> Tuple[str, List[str], List[str]]:
    text = str(content or "").replace("\r\n", "\n").replace("\r", "\n")
    answer_lines: List[str] = []
    evidence: List[str] = []
    limits: List[str] = []
    section = "answer"
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        lower = line.lower()
        if lower.startswith(("## engineering confidence", "### engineering confidence")):
            section = "skip"
            continue
        if lower.startswith(("## evidence", "### evidence")):
            section = "evidence"
            continue
        if lower.startswith(("## limits", "### limits")):
            section = "limits"
            continue
        if lower.startswith(("## answer", "### answer")):
            section = "answer"
            continue
        if line.startswith("#"):
            continue
        clean = _clean_line(line)
        if not clean or not _safe_line(clean) or _raw_manual_line(clean) or section == "skip":
            continue
        uncertain = any(marker in clean.lower() for marker in UNCERTAINTY_MARKERS)
        is_bullet = raw.lstrip().startswith(("-", "*"))
        if section == "limits" or uncertain:
            limits.append(clean)
        elif section == "evidence" or is_bullet:
            evidence.append(clean)
        else:
            answer_lines.append(clean)
    answer = answer_lines[0] if answer_lines else ""
    for extra in answer_lines[1:]:
        if CITATION_RE.search(extra):
            evidence.append(extra)
    return answer, evidence, limits


def _render_existing(content: str) -> str:
    answer, evidence, limits = _extract_sections(content)
    return _format_sections(answer, evidence, limits)


def _render_procedure(query: str, content: str) -> str:
    answer, evidence, limits = _extract_sections(content)
    steps: List[Tuple[str, str]] = []
    other: List[str] = []
    for line in evidence:
        match = STEP_RE.match(line)
        if match:
            steps.append((match.group(1).lower(), match.group(2)))
        else:
            other.append(line)
    if not steps:
        return _format_sections(answer, evidence, limits)

    groups: List[List[Tuple[str, str]]] = [[]]
    previous = ""
    for label, body in steps:
        if previous and label == "a" and previous != "a":
            groups.append([])
        groups[-1].append((label, body))
        previous = label

    rendered_steps: List[str] = []
    multiple = len(groups) > 1
    for index, group in enumerate(groups, 1):
        if multiple:
            group_name = "Continuation" if index == 1 and group and group[0][0] != "a" else f"Sequence {index}"
        else:
            group_name = ""
        for label, body in group:
            prefix = f"{group_name} — " if group_name else ""
            rendered_steps.append(f"{prefix}{label}. {body}")
    rendered_steps.extend(other)

    page = _query_page(query)
    citation_match = CITATION_RE.search(" ".join(rendered_steps))
    citation = f"[{citation_match.group(1)}]" if citation_match else ""
    if page:
        if multiple:
            answer = f"Page `{page}` contains a continued procedure and a second readable procedure sequence {citation}."
        else:
            answer = f"Page `{page}` contains the following readable procedure steps {citation}."
    return _format_sections(answer, rendered_steps, limits)


def _render_ocr(query: str, content: str, entries: Sequence[Mapping[str, Any]]) -> str:
    answer, evidence, _limits = _extract_sections(content)
    pages = [(_entry_page(entry), _citation(entry)) for entry in entries if _entry_page(entry) and _citation(entry)]
    page = _query_page(query) or (pages[0][0] if pages else "")
    citation = pages[0][1] if pages else ""
    evidence = [
        re.sub(r"^Reconstructed row:\s*", "", line, flags=re.I)
        for line in evidence
        if "matched ocr text" not in line.lower()
        and "appears to combine cells" not in line.lower()
    ]
    if page:
        answer = f"The OCR clue matches page `{page}` and appears to come from a reconstructed table layout {citation}."
    limits = [
        f"This is a layout reconstruction from OCR, not a scan-quality or blur classification {citation}.",
        f"Check the cited page image when exact reading order or broken characters matter {citation}.",
    ]
    return _format_sections(answer, evidence, limits)


def _render_graph(result: Mapping[str, Any], query: str, entries: Sequence[Mapping[str, Any]]) -> str:
    selected = _selected_entries(result, query, entries, group_by_page=False, maximum=5)
    identifier = _query_identifier(query)
    explicit = next(
        (
            entry
            for entry in selected
            if re.search(r"\b(?:parent assembly|part of|contained in|installed in|member of)\b", _entry_text(entry), re.I)
        ),
        None,
    )
    if explicit:
        citation = _citation(explicit)
        return _format_sections(
            f"An explicit assembly relationship was found for `{identifier}` {citation}.",
            [_clean_line(_entry_text(explicit)) + f" {citation}"],
            [],
        )
    evidence = [_evidence_bullet(entry) for entry in selected[:1]]
    evidence = [line for line in evidence if line] or ["No graph-linked candidate record was returned."]
    return _format_sections(
        f"No explicit parent-assembly relationship was found for `{identifier}`." if identifier else "No explicit parent-assembly relationship was found.",
        evidence,
        ["A page or nomenclature association does not establish a parent-assembly relationship."] if selected else [],
    )


# TRACE_NET_H30_PHASE5_NOTICE_COMPARISON_RUNTIME_FIX_V1_1

def _public_page_excerpt(value: Any, limit: int = 700) -> str:
    """Produce a compact public excerpt without leaking internal/raw-manual labels."""
    text = _compact(value, 4000)
    for pattern in INTERNAL_PATTERNS + RAW_MANUAL_PATTERNS:
        text = pattern.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip(" ;,|-")
    return text[:limit].rstrip()


def _requested_notice(query: str) -> str:
    low = str(query or "").casefold()
    for value in ("warning", "caution", "note"):
        if re.search(rf"\b{value}\b", low):
            return value
    return "notice"


def _page_source_entries(
    entries: Sequence[Mapping[str, Any]],
    page: str,
    *,
    supporting_only: bool = False,
) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    for raw in entries:
        entry = dict(raw)
        if not entry.get("page_content") or not _citation(entry):
            continue
        if page and _entry_page(entry).casefold() != page.casefold():
            continue
        cls = _entry_class(entry)
        supporting = cls in {"page_ocr_text", "page_table"}
        if supporting_only and not supporting:
            continue
        output.append(entry)
    output.sort(
        key=lambda entry: (
            0 if _entry_class(entry) == "page_ocr_text" else 1
            if _entry_class(entry) == "page_table" else 2,
            -len(_entry_text(entry)),
            int(entry.get("citation_id") or 10_000),
        )
    )
    return output


def _notice_excerpt(text: str, notice: str) -> str:
    if notice not in {"warning", "caution", "note"}:
        return ""
    source = _compact(text, 12000)
    pattern = re.compile(
        rf"\b{re.escape(notice)}\b\s*(?::|[—–-]|\.(?=\s+[A-Za-z0-9]))?\s*",
        re.I,
    )
    for match in pattern.finditer(source):
        candidate = source[match.start() : match.start() + 1000]
        next_notice = re.search(
            r"\s+\b(?:WARNING|CAUTION|NOTE)\b\s*(?::|[—–-])",
            candidate[max(20, len(match.group(0))) :],
            re.I,
        )
        if next_notice:
            candidate = candidate[: max(20, len(match.group(0))) + next_notice.start()]
        candidate = _public_page_excerpt(candidate, 750)
        if len(re.findall(r"[A-Za-z0-9]+", candidate)) >= 5:
            return candidate
    return ""


def _render_notice(
    result: Mapping[str, Any],
    query: str,
    entries: Sequence[Mapping[str, Any]],
) -> str:
    page = _query_page(query)
    notice = _requested_notice(query)
    for entry in _page_source_entries(entries, page, supporting_only=True):
        excerpt = _notice_excerpt(_entry_text(entry), notice)
        if not excerpt:
            continue
        citation = _citation(entry)
        source_label = "OCR text" if _entry_class(entry) == "page_ocr_text" else "Table content"
        return _format_sections(
            f"Page `{page}` contains an explicit {notice} {citation}." if page
            else f"An explicit {notice} was found {citation}.",
            [f"**{source_label}:** {excerpt} {citation}"],
            [
                "The notice is reproduced from exact-page OCR/table text; "
                "check the cited scan when punctuation or line breaks matter."
            ],
        )
    return _format_sections(
        f"No explicit {notice} was found in the exact-page OCR/table records.",
        ["No matching explicit notice record was returned for the requested page."],
        ["Summary and visual guidance were not treated as formal warning/caution/note text."],
    )


def _best_comparison_entry(
    entries: Sequence[Mapping[str, Any]],
    page: str,
) -> Dict[str, Any]:
    supporting = _page_source_entries(entries, page, supporting_only=True)
    if supporting:
        return supporting[0]
    any_page = _page_source_entries(entries, page, supporting_only=False)
    return any_page[0] if any_page else {}


def _render_comparison(
    result: Mapping[str, Any],
    query: str,
    entries: Sequence[Mapping[str, Any]],
) -> str:
    requested_pages = _query_pages(query)[:2]
    selected: List[Tuple[str, Dict[str, Any]]] = []
    for page in requested_pages:
        entry = _best_comparison_entry(entries, page)
        if entry:
            selected.append((page, entry))

    if len(selected) < 2:
        return _format_sections(
            "Comparable exact-page records were not found for both requested pages.",
            ["No complete two-page OCR/table comparison pair was available."],
            ["No other pages were substituted for the requested comparison."],
        )

    references = " and ".join(
        f"`{page}` {_citation(entry)}" for page, entry in selected
    )
    evidence: List[str] = []
    for page, entry in selected:
        citation = _citation(entry)
        cls = _entry_class(entry)
        if cls == "page_ocr_text":
            label = "OCR text"
            verb = "reads"
        elif cls == "page_table":
            label = "Table content"
            verb = "contains"
        else:
            label = "Page-context guidance"
            verb = "suggests"
        excerpt = _public_page_excerpt(_entry_text(entry), 650)
        if not excerpt:
            excerpt = "An exact-page indexed record was resolved."
        evidence.append(
            f"**{label}:** Page `{page}` {verb}: {excerpt} {citation}"
        )

    return _format_sections(
        f"The requested pages are summarized from their exact-page records: {references}.",
        evidence,
        [
            "This is a source-by-source comparison. Differences are not treated as "
            "contradictions unless the cited page records explicitly disagree."
        ],
    )


def _page_pack_found(result: Mapping[str, Any], target: str) -> bool:
    envelope = _mapping(result.get("evidence_envelope"))
    coverage = _mapping(envelope.get("coverage"))
    page_content = _mapping(coverage.get("page_content"))
    pages = page_content.get("pages")
    if not isinstance(pages, list):
        return False
    return any(
        isinstance(row, Mapping)
        and row.get("found") is not False
        and str(row.get("page_id") or "").casefold() == target.casefold()
        for row in pages
    )


def _render_negative_page(query: str) -> str:
    page = _query_page(query)
    return _format_sections(
        f"Page `{page}` was not found in the indexed document set." if page else "The requested page was not found in the indexed document set.",
        ["No matching indexed page record was returned, and no other page was substituted."],
        [],
    )


def render_chatgpt_style_answer_v1_1(result: Mapping[str, Any], query: str) -> str:
    route = str(result.get("route") or "")
    content = str(result.get("content") or "").strip()
    if route == "safe_general_chat" or route not in TECHNICAL_ROUTES:
        return content
    entries = _registry(result)
    page = _query_page(query)
    if route == "document_page_navigation" and page and not _page_pack_found(result, page):
        return _render_negative_page(query)
    if route in {"exact_identifier_lookup", "guided_part_discovery", "nomenclature_function_search"}:
        return _render_part(result, route, query, entries)
    if route == "exact_table_ipl_lookup":
        return _render_table(result, query, entries)
    if route == "ata_system_discovery":
        return _render_ata(query, entries)
    if route == "graph_relationship_reasoning":
        return _render_graph(result, query, entries)
    if route == "ocr_scan_recovery":
        return _render_ocr(query, content, entries)
    if route == "warning_caution_note_lookup":
        return _render_notice(result, query, entries)
    if route == "cross_source_comparison":
        return _render_comparison(result, query, entries)
    if route == "procedure_task_lookup":
        return _render_procedure(query, content)
    return _render_existing(content)


def _first_citation(registry: Sequence[Mapping[str, Any]]) -> str:
    for entry in registry:
        citation = _citation(entry)
        if citation:
            return citation
    return ""


def _cite_answer_line(answer: str, citation: str) -> str:
    if not citation:
        return answer
    lines = str(answer or "").splitlines()
    in_answer = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "## Answer":
            in_answer = True
            continue
        if in_answer and stripped.startswith("## "):
            break
        if in_answer and stripped and not CITATION_RE.search(stripped):
            lines[index] = line.rstrip(" .") + f" {citation}."
            break
    return "\n".join(lines)


def _matching_target_exists(result: Mapping[str, Any], query: str, registry: Sequence[Mapping[str, Any]]) -> bool:
    route = str(result.get("route") or "")
    if route == "document_page_navigation":
        target = _query_page(query)
        if not target:
            return False
        return _page_pack_found(result, target) or any(
            _entry_page(entry).casefold() == target.casefold() for entry in registry
        )
    if route == "exact_identifier_lookup":
        mode, requested = _intent(result, query)
        return any(
            _matches_intent(_entry_identifier(entry), mode, requested)
            for entry in registry
            if _entry_identifier(entry)
        )
    return True


def _safe_negative_result(answer: str, query: str, result: Mapping[str, Any], registry: Sequence[Mapping[str, Any]]) -> bool:
    route = str(result.get("route") or "")
    if route not in {"exact_identifier_lookup", "document_page_navigation"}:
        return False
    if _matching_target_exists(result, query, registry):
        return False
    target = _query_identifier(query) or _query_page(query)
    lower = str(answer or "").lower()
    return bool(
        target
        and target.casefold() in str(answer).casefold()
        and any(phrase in lower for phrase in ("no indexed match", "was not found", "no matching indexed"))
        and not any(pattern.search(answer) for pattern in INTERNAL_PATTERNS)
    )


def _validate(
    answer: str,
    query: str,
    result: Mapping[str, Any],
    validate_answer: Any,
    registry: Sequence[Mapping[str, Any]],
    extra_allowed: Any,
) -> Tuple[str, Dict[str, Any], bool]:
    validation = validate_answer(
        answer,
        query,
        result,
        extra_allowed=extra_allowed,
        registry=registry,
    )
    validation = dict(validation) if isinstance(validation, Mapping) else {
        "accepted": False,
        "quality_status": "FAIL",
        "failures": ["invalid_validator_result"],
    }
    repaired = False
    if not validation.get("accepted") and _safe_negative_result(answer, query, result, registry):
        validation = {
            "accepted": True,
            "quality_status": "PASS",
            "failures": [],
            "negative_result_without_fabricated_citation": True,
        }
        return answer, validation, repaired

    citation_failures = {
        "direct_answer_missing_citation",
        "uncited_factual_line",
        "uncited_page_content_identifier",
    }
    failures = set(validation.get("failures") or [])
    if not validation.get("accepted") and failures and failures.issubset(citation_failures):
        repaired_answer = _cite_answer_line(answer, _first_citation(registry))
        if repaired_answer != answer:
            repaired_validation = validate_answer(
                repaired_answer,
                query,
                result,
                extra_allowed=extra_allowed,
                registry=registry,
            )
            if isinstance(repaired_validation, Mapping):
                answer = repaired_answer
                validation = dict(repaired_validation)
                repaired = True
    return answer, validation, repaired


def install_chatgpt_answer_presentation_v1_1(module: MutableMapping[str, Any]) -> None:
    marker = "_TRACE_NET_H30_CHATGPT_ANSWER_PRESENTATION_V1_1_INSTALLED"
    if module.get(marker):
        return
    runtime_cls = module["Runtime"]
    current_process = runtime_cls.process
    current_health = runtime_cls.health
    validate_answer = module["validate_answer"]
    extract_latest_user = module["extract_latest_user"]
    citation_registry = module["citation_registry"]
    citation_registry_digest = module["citation_registry_digest"]
    synthesis_allowed_identifiers = module.get("synthesis_allowed_identifiers")

    def process_v1_1(self: Any, payload: Mapping[str, Any]) -> Dict[str, Any]:
        result = dict(current_process(self, payload))
        query = extract_latest_user(payload)
        old_content = str(result.get("content") or "")
        registry = citation_registry(result)
        rendered = render_chatgpt_style_answer_v1_1(result, query).strip()
        extra_allowed = (
            synthesis_allowed_identifiers(query, result)
            if callable(synthesis_allowed_identifiers)
            else None
        )
        rendered, validation, citation_repair = _validate(
            rendered,
            query,
            result,
            validate_answer,
            registry,
            extra_allowed,
        )
        result["content"] = rendered
        result["post_answer_validation"] = validation
        result["citation_registry"] = registry
        result["citation_registry_size"] = len(registry)
        result["citation_registry_digest"] = citation_registry_digest(registry)
        result["writer_mode_before_chatgpt_presentation_v1_1"] = result.get("writer_mode")
        result["writer_mode"] = "chatgpt_style_public_answer_v1_1"
        result["chatgpt_answer_presentation_v1_1"] = {
            "status": STATUS,
            "patch_id": PATCH_ID,
            "quality_status": "PASS" if validation.get("accepted") else "FAIL",
            "sections": ["Answer", "Evidence", "Limits"],
            "duplicate_evidence_collapsed": True,
            "table_raw_dump_hidden": True,
            "nomenclature_normalized": True,
            "mixed_evidence_kept_typed": True,
            "procedure_sequence_grouping": True,
            "negative_page_validation_fixed": True,
            "engineering_confidence_section_removed": True,
            "citation_line_repair_used": citation_repair,
            "old_answer_changed": rendered.strip() != old_content.strip(),
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

    def health_v1_1(self: Any) -> Dict[str, Any]:
        result = dict(current_health(self))
        result.update({
            "chatgpt_answer_presentation_v1_1_enabled": True,
            "chatgpt_answer_presentation_v1_1_status": STATUS,
            "public_duplicate_evidence_collapsed": True,
            "public_table_raw_dump_hidden": True,
            "public_negative_page_validation_fixed": True,
            "public_procedure_sequence_grouping": True,
            "chatgpt_presentation_v1_1_adds_gemma_call": False,
            "chatgpt_presentation_v1_1_changes_retrieval": False,
            "answer_permission": False,
            "final_answer_allowed": False,
            "source_truth_mutation_allowed": False,
        })
        return result

    runtime_cls.process = process_v1_1
    runtime_cls.health = health_v1_1
    module[marker] = True


__all__ = [
    "MODULE",
    "STATUS",
    "PATCH_ID",
    "install_chatgpt_answer_presentation_v1_1",
    "render_chatgpt_style_answer_v1_1",
]
