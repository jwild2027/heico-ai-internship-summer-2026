#!/usr/bin/env python3
"""Clean ChatGPT-style public answer presentation for TRACE-Net H30.

This overlay runs after answer-quality rendering. It changes presentation only:

* user-visible technical answers use Answer / Evidence / Limits;
* raw OCR, JSON, route/tunnel names, status text, and evidence-pack dumps stay hidden;
* exact identifiers and existing numeric citations are preserved;
* negative retrieval results may be stated without a fabricated citation;
* the full TRACE-Net result remains available as developer/auditor telemetry.

It performs no retrieval, makes no LLM call, writes no database, and never grants
answer permission or promotes guidance to source truth.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

MODULE = "trace_net_h30_chatgpt_answer_presentation_v1"
STATUS = "TRACE_NET_H30_CHATGPT_ANSWER_PRESENTATION_V1"
PATCH_ID = "trace_net_h30_step0_5_chatgpt_answer_presentation_v1"

PART_RE = re.compile(r"\b(?:\d{2,4}-\d{4,6}(?:-\d{3})?(?:/\d{3})?|[A-Z]{2,}\d{4,}(?:[-./][A-Z0-9]+)*)\b", re.I)
PAGE_RE = re.compile(r"\bt_p_[A-Za-z0-9_]+\b", re.I)
ATA_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")
CITATION_RE = re.compile(r"\[(\d{1,3})\]")

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
        r"\broute\s*=",
        r"\bexpected_route\b",
        r"\bactual_route\b",
        r"retrieval_tunnels?",
        r"entity_gate",
        r"policy[_ -]?id",
        r"writer_mode",
        r"gemma_status",
        r"quality_status",
        r"status\s*[:=]\s*\d{3}",
        r"trace_net_[a-z0-9_]+",
        r"\{\s*[\"']?[a-zA-Z0-9_]+[\"']?\s*:",
    )
)

RAW_DUMP_PATTERNS = tuple(
    re.compile(pattern, re.I)
    for pattern in (
        r"embedding_candidate:",
        r"recommended route:",
        r"ocr status:",
        r"maintenance manual with illustrated parts list",
        r"\bch-sec-un-fig\b",
        r"\bper stock\b",
        r"\bidentifier_blob\b",
        r"\bsource_trace_ready\b",
    )
)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _rows(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(row) for row in value if isinstance(row, Mapping)]


def _compact(value: Any, limit: int = 700) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _norm(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def _citation(entry: Mapping[str, Any]) -> str:
    try:
        number = int(entry.get("citation_id") or 0)
    except (TypeError, ValueError):
        return ""
    return f"[{number}]" if number > 0 else ""


def _entry_text(entry: Mapping[str, Any]) -> str:
    return _compact(
        entry.get("identifier_blob")
        or entry.get("value")
        or entry.get("candidate_value")
        or entry.get("snippet")
        or entry.get("field_name"),
        6000,
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


def _clean_name(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        text = " ".join(str(item) for item in value if str(item).strip())
    else:
        text = str(value or "")
    text = re.sub(r"\b(?:PAGE TEXT|OCR STATUS|RECOMMENDED ROUTE|EFFECTIVITY)\b.*", " ", text, flags=re.I)
    text = PART_RE.sub(" ", text)
    text = re.sub(r"[^A-Za-z0-9,./() -]+", " ", text)
    tokens: List[str] = []
    for token in re.findall(r"[A-Za-z]+", text.upper()):
        if len(token) <= 2 and token not in {"LH", "RH"}:
            continue
        if re.search(r"(.)\1\1", token):
            continue
        if tokens and tokens[-1] == token:
            continue
        tokens.append(token)
    if not tokens:
        return ""
    cleaned = " ".join(tokens[:8]).replace(" ASSY", " ASSEMBLY")
    return cleaned.title().replace("Lh", "LH").replace("Rh", "RH")


def _entry_name(entry: Mapping[str, Any]) -> str:
    blocked = {
        "candidate", "direct source", "table", "semantic", "source field",
        "embedding candidate", "ocr page text", "page content", "record",
    }
    for value in (entry.get("nomenclature"), entry.get("field_name")):
        name = _clean_name(value)
        if name and name.lower() not in blocked:
            return name
    return ""


def _query_identifier(query: str) -> str:
    match = PART_RE.search(str(query or ""))
    return match.group(0) if match else ""


def _query_page(query: str) -> str:
    match = PAGE_RE.search(str(query or ""))
    return match.group(0) if match else ""


def _query_ata(query: str) -> str:
    match = ATA_RE.search(str(query or ""))
    return match.group(0) if match else ""


def _registry(result: Mapping[str, Any]) -> List[Dict[str, Any]]:
    return _rows(result.get("citation_registry"))


def _entry_class(entry: Mapping[str, Any]) -> str:
    return str(entry.get("class") or "").strip().lower()


def _is_direct(entry: Mapping[str, Any]) -> bool:
    cls = _entry_class(entry)
    return bool(entry.get("can_prove_claims")) or cls in {"direct_source", "authority"}


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


def _dedupe_entries(entries: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    seen = set()
    for raw in entries:
        entry = dict(raw)
        key = (
            _norm(_entry_identifier(entry)),
            _entry_page(entry).casefold(),
            _citation(entry),
            _entry_text(entry)[:120].casefold(),
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(entry)
    return output


def _matching_entries(entries: Sequence[Mapping[str, Any]], identifier: str) -> List[Dict[str, Any]]:
    target = _norm(identifier)
    output: List[Dict[str, Any]] = []
    for entry in _dedupe_entries(entries):
        candidate = _norm(_entry_identifier(entry))
        blob = _norm(_entry_text(entry))
        if not target or candidate == target or target in candidate or target in blob:
            output.append(entry)
    output.sort(key=lambda row: (0 if _is_direct(row) else 1, 0 if _is_table(row) else 1, _entry_page(row)))
    return output


def _page_entries(entries: Sequence[Mapping[str, Any]], maximum: int = 8) -> List[Tuple[str, str]]:
    output: List[Tuple[str, str]] = []
    seen = set()
    for entry in entries:
        page = _entry_page(entry)
        citation = _citation(entry)
        if not page or not citation or page.casefold() in seen:
            continue
        seen.add(page.casefold())
        output.append((page, citation))
        if len(output) >= maximum:
            break
    return output


def _safe_line(line: str) -> bool:
    text = str(line or "")
    return not any(pattern.search(text) for pattern in INTERNAL_PATTERNS + RAW_DUMP_PATTERNS)


def _clean_public_line(line: str) -> str:
    text = str(line or "").strip()
    text = re.sub(r"^[-*]\s*", "", text)
    text = re.sub(r"^TRACE-Net\s+", "", text, flags=re.I)
    text = re.sub(r"\bTRACE-Net\b", "the search", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _dedupe_lines(lines: Iterable[str]) -> List[str]:
    output: List[str] = []
    seen = set()
    for raw in lines:
        line = str(raw or "").strip()
        key = re.sub(r"\s+", " ", line).casefold()
        if not line or key in seen:
            continue
        seen.add(key)
        output.append(line)
    return output


def _format_sections(answer: str, evidence: Sequence[str], limits: Sequence[str]) -> str:
    answer = _clean_public_line(answer)
    evidence_lines = _dedupe_lines(_clean_public_line(line) for line in evidence if _safe_line(line))
    limit_lines = _dedupe_lines(_clean_public_line(line) for line in limits if _safe_line(line))

    lines = ["## Answer", "", answer or "No usable answer was produced."]
    if evidence_lines:
        lines.extend(["", "## Evidence", ""])
        lines.extend(f"- {line}" for line in evidence_lines)
    if limit_lines:
        lines.extend(["", "## Limits", ""])
        lines.extend(f"- {line}" for line in limit_lines)
    return "\n".join(lines).strip()


def _candidate_bullet(entry: Mapping[str, Any]) -> str:
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
    suffix = " — " + "; ".join(details) if details else ""
    return f"`{identifier}`{suffix} {citation}".strip()


# ---------------------------------------------------------------------------
# Route-specific public rendering
# ---------------------------------------------------------------------------


def _render_part_route(route: str, query: str, entries: Sequence[Mapping[str, Any]]) -> str:
    identifier = _query_identifier(query)
    matching = _matching_entries(entries, identifier)
    bullets = [_candidate_bullet(entry) for entry in matching]
    bullets = _dedupe_lines(line for line in bullets if line)[:10]

    if not bullets:
        target = f"`{identifier}`" if identifier else "the requested part"
        return _format_sections(
            f"No indexed match was found for {target}.",
            ["No matching indexed part record was returned."],
            [],
        )

    direct = any(_is_direct(entry) for entry in matching)
    if route == "guided_part_discovery":
        answer = f"The search found {len(bullets)} matching part candidate{'s' if len(bullets) != 1 else ''}."
        limits = ["These are ranked candidates; use the cited source page to choose among them."] if len(bullets) > 1 else ["The result remains a candidate until the cited source record confirms the identity."]
        if any(entry.get("metadata_conflict") for entry in matching):
            limits.append("One or more candidate records contain an unresolved ATA/document mismatch.")
    elif route == "nomenclature_function_search":
        answer = f"The search found {len(bullets)} part candidate{'s' if len(bullets) != 1 else ''} matching the requested component name."
        limits = ["A nomenclature match does not by itself prove fit, effectivity, or installation authority."]
    else:
        target = f"`{identifier}`" if identifier else "the requested part"
        answer = f"{target} was found in the indexed records." if direct else f"The best indexed match for {target} is shown below."
        limits = [] if direct else ["The indexed record is candidate evidence unless the cited source field explicitly confirms the part identity."]
    return _format_sections(answer, bullets, limits)


def _render_table(query: str, entries: Sequence[Mapping[str, Any]]) -> str:
    identifier = _query_identifier(query)
    matching = _matching_entries(entries, identifier)
    table = [entry for entry in matching if _is_table(entry)]
    selected = table or matching
    bullets = [_candidate_bullet(entry) for entry in selected[:5]]
    bullets = [line for line in bullets if line]

    if not bullets:
        return _format_sections(
            f"`{identifier}` was not found in the available IPL/table evidence." if identifier else "No matching IPL/table evidence was found.",
            ["No matching indexed table record was returned."],
            [],
        )

    direct_table = bool(table and any(_is_direct(entry) or entry.get("page_content") for entry in table))
    if direct_table:
        answer = f"`{identifier}` appears in the available IPL/table evidence." if identifier else "A matching IPL/table record was found."
        limits: List[str] = []
    else:
        answer = f"A candidate IPL/table match was found for `{identifier}`." if identifier else "A candidate IPL/table match was found."
        limits = ["The final evidence pack did not include an exact source table cell that independently confirms the full row relationship."]
    return _format_sections(answer, bullets, limits)


def _render_ata(query: str, entries: Sequence[Mapping[str, Any]]) -> str:
    ata = _query_ata(query)
    part_lines = [_candidate_bullet(entry) for entry in entries if _entry_identifier(entry)]
    part_lines = [line for line in _dedupe_lines(part_lines) if line][:6]
    pages = [f"Page `{page}` {citation}" for page, citation in _page_entries(entries, maximum=8)]
    evidence = part_lines + pages
    answer = f"Indexed records were found for ATA `{ata}`." if ata and evidence else (
        f"No indexed part or page record was found for ATA `{ata}`." if ata else "No matching ATA record was found."
    )
    limits = ["These are navigation and candidate records; use the cited source page for exact manual wording."] if evidence else []
    return _format_sections(answer, evidence or ["No matching indexed ATA record was returned."], limits)


def _render_graph(query: str, entries: Sequence[Mapping[str, Any]]) -> str:
    identifier = _query_identifier(query)
    matching = _matching_entries(entries, identifier)
    explicit: Optional[Mapping[str, Any]] = None
    for entry in matching:
        text = _entry_text(entry)
        if re.search(r"\b(?:parent assembly|part of|contained in|installed in|member of)\b", text, re.I):
            explicit = entry
            break

    if explicit:
        evidence = [_clean_public_line(_entry_text(explicit)) + " " + _citation(explicit)]
        return _format_sections(
            f"An explicit assembly relationship was found for `{identifier}`." if identifier else "An explicit assembly relationship was found.",
            evidence,
            [],
        )

    candidate = next((entry for entry in matching if _entry_identifier(entry) and _citation(entry)), None)
    evidence = [_candidate_bullet(candidate)] if candidate else ["No graph-linked candidate record was returned."]
    answer = f"No explicit parent-assembly relationship was found for `{identifier}`." if identifier else "No explicit parent-assembly relationship was found."
    limits = ["A page or nomenclature association does not prove a parent-assembly relationship."] if candidate else []
    return _format_sections(answer, evidence, limits)


def _extract_existing_sections(content: str) -> Tuple[str, List[str], List[str]]:
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
        if lower.startswith("## evidence") or lower.startswith("### evidence"):
            section = "evidence"
            continue
        if lower.startswith("## limits") or lower.startswith("### limits"):
            section = "limits"
            continue
        if lower.startswith("## answer") or lower.startswith("### answer"):
            section = "answer"
            continue
        if line.startswith("#"):
            continue
        clean = _clean_public_line(line)
        if not clean or not _safe_line(clean):
            continue
        is_bullet = raw.lstrip().startswith(("-", "*"))
        if section == "limits":
            limits.append(clean)
        elif section == "evidence" or is_bullet:
            evidence.append(clean)
        else:
            answer_lines.append(clean)

    answer = answer_lines[0] if answer_lines else ""
    for extra in answer_lines[1:]:
        if CITATION_RE.search(extra):
            evidence.append(extra)
        elif any(token in extra.lower() for token in ("uncertain", "not prove", "not confirm", "should be checked", "guidance only")):
            limits.append(extra)
        elif not answer:
            answer = extra
    return answer, evidence, limits


def _render_existing_clean(content: str) -> str:
    answer, evidence, limits = _extract_existing_sections(content)
    return _format_sections(answer, evidence, limits)


def _render_ocr(query: str, content: str, entries: Sequence[Mapping[str, Any]]) -> str:
    answer, evidence, limits = _extract_existing_sections(content)
    page = _query_page(query)
    if not page:
        pages = _page_entries(entries, maximum=1)
        page = pages[0][0] if pages else ""
    citation = _page_entries(entries, maximum=1)[0][1] if _page_entries(entries, maximum=1) else ""

    reconstructed = [
        line for line in evidence
        if "reconstructed row" in line.lower()
    ]
    if reconstructed:
        clean_rows = []
        for line in reconstructed:
            line = re.sub(r"^Reconstructed row:\s*", "", line, flags=re.I)
            if citation and not CITATION_RE.search(line):
                line = f"{line} {citation}"
            clean_rows.append(line)
        evidence = clean_rows

    if page:
        answer = f"The OCR clue matches page `{page}` and appears to come from a reconstructed table layout{f' {citation}' if citation else ''}."
    elif not answer:
        answer = "The OCR clue matched an indexed record and was reconstructed as table content."

    limits = [
        f"This is a layout reconstruction from OCR, not a scan-quality or blur classification{f' {citation}' if citation else ''}.",
        f"Check the cited page image when exact reading order or broken characters matter{f' {citation}' if citation else ''}.",
    ]
    return _format_sections(answer, evidence, limits)


def _render_negative_page(query: str) -> str:
    page = _query_page(query)
    return _format_sections(
        f"Page `{page}` was not found in the indexed document set." if page else "The requested page was not found in the indexed document set.",
        ["No matching indexed page record was returned, and no other page was substituted."],
        [],
    )


def render_chatgpt_style_answer(result: Mapping[str, Any], query: str) -> str:
    """Render the public technical response without changing internal telemetry."""
    route = str(result.get("route") or "")
    content = str(result.get("content") or "").strip()
    if route == "safe_general_chat" or route not in TECHNICAL_ROUTES:
        return content

    entries = _registry(result)
    page = _query_page(query)
    envelope = _mapping(result.get("evidence_envelope"))
    coverage = _mapping(envelope.get("coverage"))
    page_content = _mapping(coverage.get("page_content"))
    packs = page_content.get("pages") if isinstance(page_content.get("pages"), list) else []

    if route == "document_page_navigation" and page and not packs:
        return _render_negative_page(query)
    if route in {"exact_identifier_lookup", "guided_part_discovery", "nomenclature_function_search"}:
        return _render_part_route(route, query, entries)
    if route == "exact_table_ipl_lookup":
        return _render_table(query, entries)
    if route == "ata_system_discovery":
        return _render_ata(query, entries)
    if route == "graph_relationship_reasoning":
        return _render_graph(query, entries)
    if route == "ocr_scan_recovery":
        return _render_ocr(query, content, entries)
    return _render_existing_clean(content)


# ---------------------------------------------------------------------------
# Validation integration
# ---------------------------------------------------------------------------


def _no_evidence(result: Mapping[str, Any]) -> bool:
    envelope = _mapping(result.get("evidence_envelope"))
    coverage = _mapping(envelope.get("coverage"))
    return not any(
        (
            _rows(envelope.get("direct_evidence")),
            _rows(envelope.get("candidate_evidence")),
            _rows(envelope.get("visual_guidance")),
            _rows(envelope.get("semantic_guidance")),
            _rows(envelope.get("authority_evidence")),
            _rows(coverage.get("navigation_leads")),
            _rows(coverage.get("ocr_evidence")),
            _rows(coverage.get("table_guidance")),
            _rows(coverage.get("graph_guidance")),
        )
    )


def _safe_negative_result(answer: str, query: str, result: Mapping[str, Any]) -> bool:
    route = str(result.get("route") or "")
    if route not in {"exact_identifier_lookup", "document_page_navigation"} or not _no_evidence(result):
        return False
    target = _query_identifier(query) or _query_page(query)
    lower = str(answer or "").lower()
    target_present = bool(target and target.casefold() in str(answer).casefold())
    negative_wording = any(phrase in lower for phrase in ("no indexed match", "was not found", "no matching indexed"))
    return target_present and negative_wording and not any(pattern.search(answer) for pattern in INTERNAL_PATTERNS)


def _validate_public_answer(
    answer: str,
    query: str,
    result: Mapping[str, Any],
    validate_answer: Any,
    registry: Sequence[Mapping[str, Any]],
    extra_allowed: Any,
) -> Dict[str, Any]:
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
    if not validation.get("accepted") and _safe_negative_result(answer, query, result):
        validation = {
            "accepted": True,
            "quality_status": "PASS",
            "failures": [],
            "negative_result_without_fabricated_citation": True,
        }
    return validation


def install_chatgpt_answer_presentation(module: MutableMapping[str, Any]) -> None:
    marker = "_TRACE_NET_H30_CHATGPT_ANSWER_PRESENTATION_V1_INSTALLED"
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

    def process_chatgpt_presentation(self: Any, payload: Mapping[str, Any]) -> Dict[str, Any]:
        result = dict(current_process(self, payload))
        query = extract_latest_user(payload)
        old_content = str(result.get("content") or "")
        registry = citation_registry(result)
        rendered = render_chatgpt_style_answer(result, query).strip()
        extra_allowed = (
            synthesis_allowed_identifiers(query, result)
            if callable(synthesis_allowed_identifiers)
            else None
        )
        validation = _validate_public_answer(
            rendered,
            query,
            result,
            validate_answer,
            registry,
            extra_allowed,
        )

        fallback_used = False
        if not validation.get("accepted"):
            old_validation = _validate_public_answer(
                old_content,
                query,
                result,
                validate_answer,
                registry,
                extra_allowed,
            )
            if old_validation.get("accepted"):
                rendered = old_content
                validation = old_validation
                fallback_used = True

        result["content"] = rendered
        result["post_answer_validation"] = validation
        result["citation_registry"] = registry
        result["citation_registry_size"] = len(registry)
        result["citation_registry_digest"] = citation_registry_digest(registry)
        result["writer_mode_before_chatgpt_presentation"] = result.get("writer_mode")
        result["writer_mode"] = (
            "chatgpt_presentation_fallback_to_prior_valid_answer"
            if fallback_used
            else "chatgpt_style_public_answer"
        )
        result["chatgpt_answer_presentation"] = {
            "status": STATUS,
            "patch_id": PATCH_ID,
            "quality_status": "PASS" if validation.get("accepted") else "FAIL",
            "sections": ["Answer", "Evidence", "Limits"],
            "engineering_confidence_section_removed": True,
            "raw_json_hidden": True,
            "route_and_tunnel_names_hidden": True,
            "status_codes_hidden": True,
            "internal_policy_messages_hidden": True,
            "raw_ocr_dump_hidden": True,
            "confidence_percentages_hidden": True,
            "specific_followups_hidden": True,
            "auditor_telemetry_preserved": True,
            "old_answer_changed": rendered.strip() != old_content.strip(),
            "fallback_used": fallback_used,
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

    def health_chatgpt_presentation(self: Any) -> Dict[str, Any]:
        result = dict(current_health(self))
        result.update({
            "chatgpt_answer_presentation_enabled": True,
            "chatgpt_answer_presentation_status": STATUS,
            "public_answer_sections": ["Answer", "Evidence", "Limits"],
            "public_raw_json_hidden": True,
            "public_internal_telemetry_hidden": True,
            "public_raw_ocr_dump_hidden": True,
            "auditor_telemetry_preserved": True,
            "chatgpt_presentation_adds_gemma_call": False,
            "chatgpt_presentation_changes_retrieval": False,
            "answer_permission": False,
            "final_answer_allowed": False,
            "source_truth_mutation_allowed": False,
        })
        return result

    runtime_cls.process = process_chatgpt_presentation
    runtime_cls.health = health_chatgpt_presentation
    module[marker] = True


__all__ = [
    "MODULE",
    "STATUS",
    "PATCH_ID",
    "install_chatgpt_answer_presentation",
    "render_chatgpt_style_answer",
]
