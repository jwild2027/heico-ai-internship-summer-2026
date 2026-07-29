#!/usr/bin/env python3
"""Phase 4.2 user-facing presentation hardening for TRACE-Net H30.

This overlay is deterministic and read-only. It changes only query-claim scoping and
user-facing rendering. It does not retrieve evidence, modify source truth, write to
Postgres/Qdrant/OpenSearch, or grant answer permission.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence, Tuple

MODULE = "trace_net_h30_user_facing_renderer_v1"
PATCH_ID = "trace_net_h30_phase4_2_user_facing_renderer_v1"
PART_RE = re.compile(r"\b\d{2,3}-\d{5}(?:-\d{3})?\b", re.I)
PAGE_RE = re.compile(r"\bt_p_[A-Za-z0-9_]+\b", re.I)
INTERNAL_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:[A-Za-z0-9_.-]+::)+[^\s;|,]+",
    re.I,
)
LONG_HASH_RE = re.compile(r"\b[a-f0-9]{16,}\b", re.I)
INTERNAL_TUNNEL_RE = re.compile(
    r"\b(?:claim_subquery|direct_source_resolution|crag_[a-z0-9_]+|"
    r"[a-z0-9_]+_specialized)_?\d*\b",
    re.I,
)

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

CLAIM_LABELS = {
    "exact_identifier": "Exact part identity",
    "nomenclature": "Nomenclature",
    "relationship": "Parent assembly / relationships",
    "visual_identity": "Figure / diagram",
    "table_value": "IPL / table row",
    "procedure": "Procedure",
    "warning": "Warnings / cautions / notes",
    "ocr": "OCR recovery",
    "comparison": "Cross-source comparison",
    "authority": "Replacement / applicability authority",
}


def _compact(value: Any, limit: int = 1200) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, sort_keys=True)
        except Exception:
            text = str(value)
    return re.sub(r"\s+", " ", text).strip()[:limit]


def sanitize_user_text(value: Any, limit: int = 1200) -> str:
    """Remove implementation identifiers while preserving technical identifiers."""
    text = _compact(value, limit)
    if not text:
        return ""
    text = INTERNAL_TOKEN_RE.sub("", text)
    text = LONG_HASH_RE.sub("", text)
    text = INTERNAL_TUNNEL_RE.sub("", text)
    text = re.sub(r"\s*;\s*;\s*", "; ", text)
    text = re.sub(r"\s+([,;:.])", r"\1", text)
    text = re.sub(r"(?:^|\s)[;,:-]+(?=\s|$)", " ", text)
    return re.sub(r"\s+", " ", text).strip(" ;,|-")


def _md_cell(value: Any, fallback: str = "Not stored", limit: int = 500) -> str:
    text = sanitize_user_text(value, limit) or fallback
    return text.replace("|", r"\|").replace("\n", " ")


def _rows(envelope: Any, attribute: str) -> List[Dict[str, Any]]:
    value = getattr(envelope, attribute, []) or []
    return [dict(row) for row in value if isinstance(row, Mapping)]


def _coverage(envelope: Any) -> Mapping[str, Any]:
    value = getattr(envelope, "coverage", {})
    return value if isinstance(value, Mapping) else {}


def _row_parts(row: Mapping[str, Any]) -> set[str]:
    values: List[str] = []
    for value in row.values():
        if isinstance(value, (str, int, float, bool)):
            values.append(str(value))
        elif isinstance(value, list):
            values.extend(str(item) for item in value if isinstance(item, (str, int, float, bool)))
    return {part.upper() for part in PART_RE.findall(" ".join(values))}


def _figure_text(row: Mapping[str, Any]) -> str:
    values = row.get("figure_refs")
    if not isinstance(values, list):
        return ""
    cleaned = [sanitize_user_text(value, 120) for value in values]
    return ", ".join(value for value in cleaned if value)


def _row_value(row: Mapping[str, Any], limit: int = 500) -> str:
    for key in (
        "normalized_value", "value", "snippet", "subject", "nomenclature",
        "candidate_value", "candidate_part_number", "description",
    ):
        text = sanitize_user_text(row.get(key), limit)
        if text:
            return text
    return ""


def _source_label(value: Any) -> str:
    key = _compact(value, 100).lower()
    labels = {
        "source_citation": "source record",
        "visual": "visual lead",
        "table": "table/IPL lead",
        "ocr": "OCR lead",
        "candidate": "candidate lead",
        "semantic": "semantic lead",
        "graph": "relationship lead",
        "record": "indexed record",
    }
    return labels.get(key, "indexed lead")


def _evidence_footer(*, direct: bool, authority_missing: bool = False) -> str:
    if authority_missing:
        return (
            "**Evidence status:** No explicit authority evidence was located; approval, "
            "interchangeability, applicability, eligibility, and installation safety remain unconfirmed."
        )
    if direct:
        return "**Evidence status:** Citation-ready source evidence is listed above."
    return (
        "**Evidence status:** Current matches are guidance only; they identify where to inspect "
        "but do not prove the requested technical claim."
    )


def _independent_identity_request(low: str) -> bool:
    return any(
        phrase in low
        for phrase in (
            "find part", "identify part", "identify the part", "confirm part",
            "confirm the part", "verify part", "verify the part",
            "determine the part number",
        )
    )


def _explicit_procedure_request(low: str) -> bool:
    return any(
        phrase in low
        for phrase in (
            "how do i install", "how to install", "installation steps",
            "steps to install", "installation procedure", "install procedure",
            "removal and installation", "installation instructions",
            "instructions to install", "tools required", "procedure for installation",
            "procedure to install",
        )
    )


def _authority_installation_phrase(low: str) -> bool:
    return any(
        phrase in low
        for phrase in (
            "safe to install", "approved for installation", "approved to install",
            "installation eligibility", "eligible for installation",
            "installation authority", "applicable for installation",
        )
    )


def _lead_score(row: Mapping[str, Any], requested_parts: set[str]) -> Tuple[int, int, int, int, int]:
    observed = _row_parts(row)
    exact = bool(requested_parts and observed.intersection(requested_parts))
    figures = bool(_figure_text(row))
    value = bool(_row_value(row))
    citation = bool(row.get("citation_ready") or row.get("source_trace_ready"))
    source_rank = {
        "visual": 7,
        "source_citation": 6,
        "table": 5,
        "ocr": 4,
        "candidate": 3,
        "semantic": 2,
        "graph": 1,
    }.get(_compact(row.get("source_type"), 100).lower(), 0)
    return (1 if exact else 0, 1 if figures else 0, 1 if value else 0, 1 if citation else 0, source_rank)


def _best_leads(atoms: Any, envelope: Any) -> List[Dict[str, Any]]:
    coverage = _coverage(envelope)
    rows: List[Dict[str, Any]] = [
        dict(row) for row in coverage.get("navigation_leads", []) if isinstance(row, Mapping)
    ]
    for attribute, source_type in (
        ("visual_guidance", "visual"),
        ("candidate_evidence", "candidate"),
        ("semantic_guidance", "semantic"),
    ):
        for raw in _rows(envelope, attribute):
            row = dict(raw)
            row.setdefault("source_type", source_type)
            rows.append(row)

    requested = {
        str(value).upper()
        for value in (getattr(atoms, "exact_part_numbers", []) or [])
        if value
    }
    exact_rows = [row for row in rows if requested.intersection(_row_parts(row))]
    if exact_rows:
        rows = exact_rows

    by_page: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        page = _compact(row.get("page_id"), 200)
        if not page:
            continue
        current = by_page.get(page)
        if current is None or _lead_score(row, requested) > _lead_score(current, requested):
            by_page[page] = row

    return sorted(
        by_page.values(),
        key=lambda row: (
            tuple(-value for value in _lead_score(row, requested)),
            _compact(row.get("page_id"), 200),
        ),
    )


def render_navigation(atoms: Any, envelope: Any) -> str:
    direct = _rows(envelope, "direct_evidence")
    if direct:
        lines = ["## Source location", "", "| # | Document | Page | Source evidence |", "|---:|---|---|---|"]
        for index, row in enumerate(direct[:5], 1):
            lines.append(
                f"| {index} | {_md_cell(row.get('document'), 'Not stored', 300)} | "
                f"`{_md_cell(row.get('page_id'), 'Unknown page', 180)}` | "
                f"{_md_cell(row.get('normalized_value') or row.get('value'), 'Source field resolved', 500)} |"
            )
        lines.extend(["", _evidence_footer(direct=True)])
        return "\n".join(lines)

    leads = _best_leads(atoms, envelope)
    if not leads:
        return (
            "## Source location\n\nNo matching source page or indexed navigation lead was resolved.\n\n"
            + _evidence_footer(direct=False)
        )

    best = leads[0]
    page = _compact(best.get("page_id"), 200) or "Unknown page"
    document = sanitize_user_text(best.get("document"), 300)
    figures = _figure_text(best)
    summary = _row_value(best, 450)
    lines = ["## Best indexed location", "", f"**Page:** `{page}`"]
    if document:
        lines.append(f"**Document:** {document}")
    if figures:
        lines.append(f"**Figure:** {figures}")
    if summary:
        lines.append(f"**Match:** {summary}")
    lines.append(f"**Record type:** {_source_label(best.get('source_type'))}")

    supporting = leads[1:6]
    if supporting:
        lines.extend(["", "### Supporting page leads", ""])
        for row in supporting:
            support_page = _compact(row.get("page_id"), 200) or "Unknown page"
            figures = _figure_text(row)
            details = _source_label(row.get("source_type"))
            if figures:
                details += f"; {figures}"
            lines.append(f"- `{support_page}` — {details}")

    lines.extend(["", _evidence_footer(direct=False)])
    return "\n".join(lines)


def _dedupe_ocr(rows: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    ranked = sorted(
        (dict(row) for row in rows if isinstance(row, Mapping)),
        key=lambda row: (
            0 if _row_value(row) else 1,
            0 if row.get("citation_ready") else 1,
            0 if row.get("engine") else 1,
            0 if row.get("confidence") else 1,
            _compact(row.get("page_id"), 200),
        ),
    )
    output: List[Dict[str, Any]] = []
    seen = set()
    for row in ranked:
        page = _compact(row.get("page_id"), 200)
        snippet = _row_value(row, 500)
        key = (page.casefold(), snippet.casefold() if snippet else "__empty__")
        if key in seen:
            continue
        seen.add(key)
        output.append(row)
    return output


def render_ocr(atoms: Any, envelope: Any) -> str:
    coverage = _coverage(envelope)
    rows = _dedupe_ocr(
        row for row in coverage.get("ocr_evidence", []) if isinstance(row, Mapping)
    )
    if not rows:
        leads = _best_leads(atoms, envelope)
        pages = [_compact(row.get("page_id"), 200) for row in leads if row.get("page_id")]
        lines = ["## OCR recovery", "", "No matching OCR record was resolved from the indexed OCR artifacts."]
        if pages:
            lines.append("Pages available for OCR retry or visual inspection: " + ", ".join(f"`{page}`" for page in pages[:6]) + ".")
        lines.extend(["", _evidence_footer(direct=False)])
        return "\n".join(lines)

    lines = [
        "## OCR recovery",
        "",
        "| Page | Evidence status | OCR engine | Confidence | Readable text |",
        "|---|---|---|---|---|",
    ]
    for row in rows[:8]:
        status = "Citation-ready record" if row.get("citation_ready") else "Guidance only"
        lines.append(
            f"| `{_md_cell(row.get('page_id'), 'Unknown page', 180)}` | {status} | "
            f"{_md_cell(row.get('engine'), 'Not stored', 120)} | "
            f"{_md_cell(row.get('confidence'), 'Not stored', 100)} | "
            f"{_md_cell(_row_value(row, 500), 'No readable text stored', 500)} |"
        )
    direct = any(bool(row.get("citation_ready")) and bool(_row_value(row)) for row in rows)
    lines.extend([
        "",
        "Unclear OCR characters were not silently corrected or inferred.",
        "",
        _evidence_footer(direct=direct),
    ])
    return "\n".join(lines)


def render_authority(atoms: Any, envelope: Any) -> str:
    authority = _rows(envelope, "authority_evidence")
    if authority:
        lines = ["## Result: Explicit authority evidence located", ""]
        for index, row in enumerate(authority[:6], 1):
            page = _compact(row.get("page_id"), 180) or "Unknown page"
            field = sanitize_user_text(row.get("field_name"), 180) or "authority field"
            value = _row_value(row, 500) or "Authority record resolved"
            lines.append(f"- [{index}] `{page}` — **{field}:** {value}")
        lines.extend(["", _evidence_footer(direct=True)])
        return "\n".join(lines)

    low = str(getattr(atoms, "latest_query", "") or "").lower()
    requested: List[str] = []
    if any(term in low for term in ("replacement", "interchange")):
        requested.append("approved replacement or interchangeability")
    if any(term in low for term in ("effectivity", "applicable", "applicability", "eligible", "eligibility")):
        requested.append("effectivity, applicability, or eligibility")
    if any(term in low for term in ("safe to install", "installation", "install")):
        requested.append("installation approval or safety")
    if not requested:
        requested.append("the requested approval or applicability claim")

    lines = [
        "## Result: Not confirmed",
        "",
        "TRACE-Net did not find explicit source authority confirming:",
    ]
    lines.extend(f"- {item};" for item in requested[:-1])
    lines.append(f"- {requested[-1]}.")
    lines.extend([
        "",
        "Available page, visual, OCR, table, or family matches may help locate records, but they cannot establish authority.",
        "",
        _evidence_footer(direct=False, authority_missing=True),
    ])
    return "\n".join(lines)


def _best_claim_row(rows: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    if not rows:
        return None
    return max(
        rows,
        key=lambda row: (
            1 if row.get("citation_ready") or row.get("source_trace_ready") else 0,
            1 if _figure_text(row) else 0,
            1 if row.get("item") or row.get("item_number") else 0,
            1 if _row_value(row) else 0,
            1 if row.get("page_id") else 0,
        ),
    )


def _claim_summary(row: Mapping[str, Any] | None) -> str:
    if not row:
        return "No matching indexed record"
    page = _compact(row.get("page_id"), 180)
    document = sanitize_user_text(row.get("document"), 250)
    figures = _figure_text(row)
    item = sanitize_user_text(row.get("item") or row.get("item_number"), 80)
    value = _row_value(row, 350)
    parts: List[str] = []
    if document:
        parts.append(document)
    if page:
        parts.append(f"`{page}`")
    if figures:
        parts.append(figures)
    if item:
        parts.append(f"item {item}")
    if value:
        parts.append(value)
    return "; ".join(parts) or "Matching indexed record"


def render_claims(atoms: Any, envelope: Any) -> str:
    coverage = _coverage(envelope)
    results = coverage.get("claim_results", {})
    if not isinstance(results, Mapping) or not results:
        return (
            "## Claim results\n\nNo claim-level evidence buckets were produced.\n\n"
            + _evidence_footer(direct=False)
        )

    lines = [
        "## Claim results",
        "",
        "| Requested claim | Status | Best current result |",
        "|---|---|---|",
    ]
    any_direct = False
    authority_missing = False
    for claim, raw in results.items():
        if not isinstance(raw, Mapping):
            continue
        label = CLAIM_LABELS.get(str(claim), str(claim).replace("_", " ").title())
        status = str(raw.get("status") or "NOT_FOUND")
        direct = [row for row in raw.get("direct_evidence", []) if isinstance(row, Mapping)] if isinstance(raw.get("direct_evidence"), list) else []
        guidance = [row for row in raw.get("guidance", []) if isinstance(row, Mapping)] if isinstance(raw.get("guidance"), list) else []
        if status == "DIRECT" and direct:
            display_status = "Citation-ready"
            best = _best_claim_row(direct)
            any_direct = True
        elif status == "GUIDANCE_ONLY" and guidance:
            display_status = "Guidance only"
            best = _best_claim_row(guidance)
        elif claim == "authority":
            display_status = "Not confirmed"
            best = None
            authority_missing = True
        else:
            display_status = "Not resolved"
            best = None
        lines.append(
            f"| {_md_cell(label, label, 180)} | {display_status} | "
            f"{_md_cell(_claim_summary(best), 'No matching indexed record', 650)} |"
        )

    lines.extend(["", _evidence_footer(direct=any_direct, authority_missing=authority_missing)])
    return "\n".join(lines)


def render_aggregation(atoms: Any, envelope: Any) -> str:
    coverage = _coverage(envelope)
    local = coverage.get("retrieval_completion", {}) if isinstance(coverage.get("retrieval_completion"), Mapping) else {}
    records = [dict(row) for row in coverage.get("aggregate_records", []) if isinstance(row, Mapping)]
    pages = sorted({_compact(row.get("page_id"), 200) for row in records if _compact(row.get("page_id"), 200)})
    documents = sorted({sanitize_user_text(row.get("document"), 400) for row in records if sanitize_user_text(row.get("document"), 400)})
    lines = [
        "## Indexed coverage",
        "",
        f"- **Coverage telemetry — matching pages:** {len(pages)}",
        f"- **Coverage telemetry — matching documents:** {len(documents)}",
    ]
    if local:
        lines.append(f"- **Coverage telemetry — artifact files scanned:** {int(local.get('scanned_file_count', 0) or 0)}")
        lines.append(f"- **Coverage telemetry — files with matching records:** {int(local.get('matched_file_count', 0) or 0)}")
        lines.append(
            "- **Coverage telemetry — coverage:** "
            + ("Complete for the bounded indexed artifact set" if local.get("coverage_complete_for_candidate_files") else "Capped or incomplete")
        )
    if pages:
        lines.extend(["", "### Resolved pages", ""])
        lines.extend(f"- **Coverage telemetry — page:** `{page}`" for page in pages[:12])
    lines.extend([
        "",
        "**Coverage telemetry — scope:** This summarizes the currently indexed TRACE-Net artifact set, not manuals or pages that have not been indexed.",
    ])
    return "\n".join(lines)


def finalize_content(route: str, content: Any, result: Mapping[str, Any]) -> str:
    """Sanitize all routes and collapse canonical boundary boilerplate."""
    text = str(content or "").strip()
    text = text.replace(PROOF_BOUNDARY, "").replace(AUTHORITY_BOUNDARY, "")
    lines: List[str] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if route in {
            "authority_eligibility_verification", "multi_question_research",
            "document_page_navigation", "ocr_scan_recovery",
        } and line.startswith("Requested exact identifier clue:"):
            continue
        sanitized = sanitize_user_text(line, 5000) if "::" in line or LONG_HASH_RE.search(line) else line
        if sanitized.strip():
            lines.append(sanitized)
    text = "\n".join(lines)
    text = INTERNAL_TOKEN_RE.sub("", text)
    text = LONG_HASH_RE.sub("", text)
    text = INTERNAL_TUNNEL_RE.sub("", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def install_user_facing_renderer(router: MutableMapping[str, Any]) -> None:
    """Install Phase 4.2 after retrieval completion and Engram critic repair."""
    if router.get("_H30_USER_FACING_RENDERER_V1_INSTALLED"):
        return

    runtime_cls = router["CognitiveRuntime"]
    original_extract = router["extract_query_atoms"]
    original_render = runtime_cls.render
    original_process = runtime_cls.process
    original_health = runtime_cls.health

    def extract_v1(query: str) -> Any:
        atoms = original_extract(query)
        low = str(query or "").lower()

        authority_installation = bool(
            getattr(atoms, "authority_requested", False)
            and _authority_installation_phrase(low)
        )
        explicit_procedure = _explicit_procedure_request(low)
        if authority_installation and not explicit_procedure:
            atoms.procedure_requested = False
            atoms.requested_claims = [
                claim for claim in (getattr(atoms, "requested_claims", []) or [])
                if claim != "procedure"
            ]

        material_claims = set(getattr(atoms, "requested_claims", []) or [])
        if getattr(atoms, "ocr_requested", False):
            material_claims.discard("visual_identity")
            if not _independent_identity_request(low):
                material_claims.discard("exact_identifier")
        if getattr(atoms, "authority_requested", False) and not _independent_identity_request(low):
            material_claims.discard("exact_identifier")
        if authority_installation and not explicit_procedure:
            material_claims.discard("procedure")

        atoms.multi_question = len(material_claims) >= 2 and any(
            connector in low for connector in (" and ", ";", " also ", " then ", " plus ")
        )
        return atoms

    router["extract_query_atoms"] = extract_v1

    def render_v1(self: Any, plan: Any, atoms: Any, envelope: Any, critic: Mapping[str, Any]) -> str:
        route = str(getattr(plan, "primary_route", "") or "")
        if route == "document_page_navigation":
            return render_navigation(atoms, envelope)
        if route == "ocr_scan_recovery":
            return render_ocr(atoms, envelope)
        if route == "authority_eligibility_verification":
            return render_authority(atoms, envelope)
        if route == "multi_question_research":
            return render_claims(atoms, envelope)
        if route == "high_degree_entity_aggregation":
            return render_aggregation(atoms, envelope)
        return original_render(self, plan, atoms, envelope, critic)

    def process_v1(self: Any, payload: Mapping[str, Any]) -> Dict[str, Any]:
        result = dict(original_process(self, payload))
        route = str(result.get("route") or "")
        result["content"] = finalize_content(route, result.get("content"), result)
        result["presentation_hardening"] = {
            "module": MODULE,
            "patch_id": PATCH_ID,
            "internal_identifier_sanitization": True,
            "claim_aware_deduplication": True,
            "single_evidence_footer": True,
            "authority_procedure_scope_separation": True,
            "read_only": True,
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
        }
        return result

    def health_v1(self: Any) -> Dict[str, Any]:
        result = dict(original_health(self))
        result.update({
            "user_facing_renderer_v1": True,
            "internal_identifier_sanitization": True,
            "claim_aware_deduplication": True,
            "single_evidence_footer": True,
            "authority_procedure_scope_separation": True,
        })
        return result

    runtime_cls.render = render_v1
    runtime_cls.process = process_v1
    runtime_cls.health = health_v1
    router["_H30_USER_FACING_RENDERER_V1_INSTALLED"] = True
