"""TRACE-Net OCR Cleanup & Extraction v1 (Patch 5).

Confirmed, additive extraction/cleanup for OCR scan-pack records. This module is
deliberately narrow: it produces CLEANED DERIVATIVE fields and filtered supplemental
callout CANDIDATES alongside — never in place of — the raw OCR. It is not a new OCR
engine and computes no new geometry.

Hard contract (enforced by tests):
  * Raw OCR text and raw PSM-11 supplemental text are preserved byte-for-byte.
  * Cleanup only ever adds fields; it never mutates or drops raw text.
  * PSM-11 callout candidates are candidates only: confirmed == False,
    source_truth == False. OCR-only callouts never prove a part identity.
  * When only flattened OCR exists, flat_text_row_association_forbidden == True:
    a flattened row may be searchable but may NOT assert
    item -> part -> nomenclature -> quantity without a reconstructed, coordinate-
    linked row record.
  * No answer permission and no source-truth mutation are granted anywhere.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

CLEANUP_VERSION = "trace_net_ocr_cleanup_extraction_v1"

_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./:-]*")
# A dotted leader is a run of >= 4 dots (optionally space-separated) that connects a
# left label to a right page/target. Ordinary sentence periods (single '.') and
# part-number punctuation are never matched.
_LEADER_RUN_RE = re.compile(r"(?:\s*\.\s*){4,}")
_TRAILING_TARGET_RE = re.compile(r"^(\d{1,5}|NOT\s+APPLICABLE|[ivxlcdm]{1,6})$", re.I)
# Part numbers / ATA codes whose internal hyphens must never be touched.
_PART_RE = re.compile(r"\b\d{2,3}-\d{2,5}(?:-\d{1,4})?[A-Z]?\b")
_ATA_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")

# Repeated page furniture / manual boilerplate for the EMBRAER CMM/IPL corpus.
_BOILERPLATE_TOKENS = frozenset({
    "embraer", "maintenance", "manual", "with", "illustrated", "parts", "list",
    "effectivity", "all", "page", "sheet", "revision", "temporary", "record",
    "component", "contents", "subject",
})
_BOILERPLATE_LINE_RES = (
    re.compile(r"^\s*embraer\b", re.I),
    re.compile(r"maintenance\s+manual", re.I),
    re.compile(r"illustrated\s+parts\s+list", re.I),
    re.compile(r"^\s*effectivity\b", re.I),
    re.compile(r"\bt\.?\s*p\.?\s*\d", re.I),                # T.P. 120/1176
    re.compile(r"^\s*page\s+\d", re.I),
    re.compile(r"\b[A-Z][a-z]{2}\s*\d{1,2}\s*/\s*\d{2}\b"),  # Sep 30/98
)
_EMBRAER_HEADER_VARIANT_RE = re.compile(r"^\s*[«<]?\s*embraer\b.*$", re.I)


def _lines(text: str) -> List[str]:
    return (text or "").splitlines()


def _tokens(text: str) -> List[str]:
    return _WORD_RE.findall(text or "")

# --- Patch 5.1 semantic cleanup contracts -----------------------------------
PATCH51_SEMANTIC_VERSION = "trace_net_ocr_patch5_1_semantic_v1"
_VISUAL_CALLOUT_ROUTES = frozenset({"image_visual", "mixed_text_and_figure"})
_DATE_ROW_RE = re.compile(
    r"\b(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s+\d{1,2}/\d{2}\b",
    re.I,
)
_ATA_FIG_ROW_RE = re.compile(r"\b\d{2}\s*-\s*\d{2}\s*-\s*\d{2}\s*-\s*\d{1,3}[A-Z]?\b", re.I)
_VENDOR_CODE_ONLY_PATCH51_RE = re.compile(r"^[A-Z]{1,3}\d{4,}$")
_VENDOR_CODE_PATCH51_RE = re.compile(r"^[A-Z]{1,3}\d{4,}\b")
_DOTTED_TARGET_PATCH51_RE = re.compile(
    r"\.{4,}\s*(?:\d{1,5}|NOT\s+APPLICABLE|[ivxlcdm]{1,6})\s*$",
    re.I,
)
_TRAILING_PAGE_PATCH51_RE = re.compile(
    r"(?:\d{1,4}|NOT\s+APPLICABLE|[ivxlcdm]{1,6})\s*$",
    re.I,
)


def _normalize_structure_line(value: str) -> str:
    text = (value or "").upper().replace("’", "'").replace("`", "'")
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def detect_index_toc_structure(text: str) -> Dict[str, Any]:
    """Detect actual vendor/numerical indexes, LEP pages, and a real TOC.

    Patch 5 treated any table route containing dotted leaders as an index. That
    inverted precision/recall on the 509-page corpus because detailed-parts-list
    nomenclature also contains leaders. Patch 5.1 requires a page-level structural
    header plus repeated rows of the matching type.
    """
    content = [line.strip() for line in _lines(text) if line.strip()]
    normalized = [_normalize_structure_line(line) for line in content]
    normalized_joined = " | ".join(normalized)

    dotted_rows = 0
    vendor_rows = 0
    vendor_only_rows = 0
    trailing_page_rows = 0
    ata_figure_rows = 0
    dated_rows = 0
    lep_label_rows = 0

    for line in content:
        if _DOTTED_TARGET_PATCH51_RE.search(line):
            dotted_rows += 1
        vendor_match = _VENDOR_CODE_PATCH51_RE.match(line)
        if vendor_match:
            rest = line[vendor_match.end():]
            alpha_words = [
                word for word in rest.split()
                if len(word) >= 3 and any(char.isalpha() for char in word)
            ]
            if alpha_words:
                vendor_rows += 1
        if _VENDOR_CODE_ONLY_PATCH51_RE.match(line):
            vendor_only_rows += 1
        alpha_count = sum(
            1 for word in line.split()
            if len(word) >= 3 and any(char.isalpha() for char in word)
        )
        if alpha_count >= 1 and _TRAILING_PAGE_PATCH51_RE.search(line):
            trailing_page_rows += 1
        if _ATA_FIG_ROW_RE.search(line):
            ata_figure_rows += 1
        if _DATE_ROW_RE.search(line):
            dated_rows += 1
        if re.search(r"\b25\s*-\s*(?:LEP|IPL|NUMERICAL\s+INDEX|CONTENTS)\b", line, re.I):
            lep_label_rows += 1

    header_toc = (
        "TABLE OF CONTENTS" in normalized
        or any(line == "SUBJECT PAGE" for line in normalized)
    )
    header_vendor = (
        (
            "VENDORS NAMES AND ADDRESSES" in normalized_joined
            or "VENDOR NAMES AND ADDRESSES" in normalized_joined
        )
        and (
            "VENDOR" in normalized
            or "CODE" in normalized
            or any("VENDOR CODE" in line for line in normalized)
        )
    )
    header_numerical = (
        any("PART NUMBER UNITS AIRLINE" in line for line in normalized)
        and any("CH SEC UN FIG" in line for line in normalized)
    )
    header_lep = (
        any("SUBJECT PAGE DATE" in line for line in normalized)
        and any(line.startswith("CHAPTER") for line in normalized)
        and any(line.startswith("SECTION") for line in normalized)
    )
    header_lep_cover = (
        "CHAPTER" in normalized
        and "SECTION" in normalized
        and "SUBJECT" in normalized
        and dated_rows >= 3
        and lep_label_rows >= 3
    )

    kind: Optional[str] = None
    rows = 0
    reasons: List[str] = []
    if header_vendor and max(vendor_rows, vendor_only_rows) >= 2:
        kind = "vendor_index"
        rows = max(vendor_rows, vendor_only_rows)
        reasons = ["vendor_header", "repeated_vendor_codes"]
    elif header_numerical and ata_figure_rows >= 3:
        kind = "numerical_index"
        rows = ata_figure_rows
        reasons = ["numerical_index_columns", "repeated_ata_figure_rows"]
    elif (header_lep or header_lep_cover) and dated_rows >= 3:
        kind = "list_of_effective_pages"
        rows = max(dated_rows, lep_label_rows)
        reasons = ["lep_columns", "repeated_dated_page_rows"]
    elif header_toc and (dotted_rows >= 3 or trailing_page_rows >= 3):
        kind = "table_of_contents"
        rows = max(dotted_rows, trailing_page_rows)
        reasons = ["table_of_contents_header", "repeated_subject_page_rows"]

    return {
        "fires": kind is not None,
        "kind": kind,
        "rows": rows,
        "reasons": reasons,
        "is_index_or_toc": kind in {"vendor_index", "numerical_index", "table_of_contents"},
        "is_list_of_effective_pages": kind == "list_of_effective_pages",
        "dotted_leader_rows": dotted_rows,
        "vendor_code_rows": vendor_rows,
        "vendor_code_only_rows": vendor_only_rows,
        "trailing_page_rows": trailing_page_rows,
        "ata_figure_rows": ata_figure_rows,
        "dated_rows": dated_rows,
    }

TRACE_NET_OCR_PATCH_5_1_APPLIED = True



# --------------------------------------------------------------------------- #
# B. Dotted-leader cleanup + TOC/index parsing
# --------------------------------------------------------------------------- #
def _split_leader_line(line: str) -> Optional[Tuple[str, Optional[str], bool]]:
    """If `line` contains a dotted leader, return (label, page_target, uncertain).

    label is the text left of the leader; page_target is the text to the right
    (a page number, roman numeral, or NOT APPLICABLE) or None; uncertain is True
    when the right side is not a clean page target.
    """
    m = _LEADER_RUN_RE.search(line)
    if not m:
        return None
    label = line[: m.start()].strip()
    right = line[m.end():].strip()
    if not label:
        return None
    if right and _TRAILING_TARGET_RE.match(right):
        return label, right, False
    # Leader present but no clean trailing target -> keep label, mark uncertain.
    return label, (right or None), True


def clean_dotted_leaders(text: str) -> Tuple[str, List[Dict[str, Any]]]:
    """Collapse dotted-leader noise in a CLEANED DERIVATIVE, preserving the left
    label and the right page target. Returns (cleaned_text, operations)."""
    ops: List[Dict[str, Any]] = []
    out_lines: List[str] = []
    for idx, line in enumerate(_lines(text)):
        split = _split_leader_line(line)
        if split is None:
            out_lines.append(line)
            continue
        label, target, uncertain = split
        cleaned = f"{label}\t{target}" if target else label
        out_lines.append(cleaned)
        ops.append({
            "operation": "collapse_dotted_leader",
            "line_index": idx,
            "label": label,
            "page_target": target,
            "uncertain_label_page_relationship": uncertain,
        })
    return "\n".join(out_lines), ops


def parse_toc_index_entries(text: str) -> List[Dict[str, Any]]:
    """Parse subject/page index entries from dotted-leader lines. Each entry keeps
    the raw line and marks uncertain label/page relationships rather than guessing."""
    entries: List[Dict[str, Any]] = []
    for idx, line in enumerate(_lines(text)):
        split = _split_leader_line(line)
        if split is None:
            continue
        label, target, uncertain = split
        page_number: Optional[int] = None
        if target and target.isdigit():
            page_number = int(target)
        entries.append({
            "line_index": idx,
            "label": label,
            "page_target": target,
            "page_number": page_number,
            "uncertain": uncertain or page_number is None,
            "raw_line": line,
        })
    return entries


# --------------------------------------------------------------------------- #
# C. Diagram supplemental callout candidates (PSM 11)
# --------------------------------------------------------------------------- #
def _is_boilerplate_token(tok: str) -> bool:
    return re.sub(r"[^a-z0-9]", "", tok.lower()) in _BOILERPLATE_TOKENS


def _boilerplate_reason(tok: str) -> Optional[str]:
    low = tok.lower()
    if _is_boilerplate_token(tok):
        return "manual_header_or_footer_token"
    if _ATA_RE.match(tok):
        return "ata_chapter_footer_code"
    if re.fullmatch(r"t\.?p\.?", low) or re.fullmatch(r"\d{3}/\d{4}", tok):
        return "technical_publication_footer"
    return None


def _noise_reason(tok: str) -> Optional[str]:
    non_alnum = sum(1 for c in tok if not c.isalnum())
    if non_alnum and non_alnum >= max(1, len(tok) // 2):
        return "punctuation_or_grid_noise"
    if re.fullmatch(r"[._·:;,\-]+", tok):
        return "punctuation_run"
    return None


def filter_supplemental_callout_candidates(
    psm11_raw_text: str,
    primary_text: str,
    *,
    page_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Filter PSM-11 into conservative, unconfirmed visual-label candidates.

    Patch 5.1 rejects tokens already available in PSM 3 and removes the generic
    ``len(token) <= 12`` retention rule. Coordinates remain unavailable because
    stdout OCR has no bounding boxes; every candidate is explicitly unlocalized,
    unconfirmed, and non-source-truth.
    """
    primary_tokens = {token.lower() for token in _tokens(primary_text)}
    seen: set[str] = set()
    candidates: List[Dict[str, Any]] = []
    for token in _tokens(psm11_raw_text):
        key = token.lower()
        if key in seen:
            continue
        seen.add(key)
        base = {
            "candidate_text": token,
            "source_psm": 11,
            "page_id": page_id,
            "bounding_box": None,
            "coordinate_status": "unavailable_stdout_ocr",
            "unlocalized_candidate": True,
            "also_in_primary_psm3": key in primary_tokens,
            "confirmed": False,
            "source_truth": False,
        }
        boilerplate = _boilerplate_reason(token)
        if boilerplate:
            candidates.append({
                **base,
                "candidate_status": "rejected_boilerplate",
                "filtering_reason": "boilerplate_rejected",
                "boilerplate_rejection_reason": boilerplate,
            })
            continue
        noise = _noise_reason(token)
        if noise:
            candidates.append({
                **base,
                "candidate_status": "rejected_noise",
                "filtering_reason": noise,
                "boilerplate_rejection_reason": None,
            })
            continue
        if key in primary_tokens:
            candidates.append({
                **base,
                "candidate_status": "rejected_primary_duplicate",
                "filtering_reason": "already_present_in_primary_psm3",
                "boilerplate_rejection_reason": None,
            })
            continue

        if re.fullmatch(r"\d{1,4}[A-Z]?", token):
            reason = "numeric_callout_label"
        elif re.fullmatch(r"[A-Z](?:-[A-Z])?", token):
            reason = "letter_detail_label"
        elif _PART_RE.fullmatch(token):
            reason = "part_number_shaped_candidate"
        elif re.fullmatch(r"[A-Z][A-Z0-9./:-]{1,11}", token):
            reason = "uppercase_sparse_label"
        else:
            candidates.append({
                **base,
                "candidate_status": "rejected_noise",
                "filtering_reason": "non_callout_shape",
                "boilerplate_rejection_reason": None,
            })
            continue

        candidates.append({
            **base,
            "candidate_status": "retained",
            "filtering_reason": reason,
            "boilerplate_rejection_reason": None,
        })
    return candidates



# --------------------------------------------------------------------------- #
# F. Conservative boilerplate + dehyphenation cleanup (CLEANED DERIVATIVE only)
# --------------------------------------------------------------------------- #
def _is_boilerplate_line(line: str) -> bool:
    return any(r.search(line) for r in _BOILERPLATE_LINE_RES)


def clean_boilerplate_and_dehyphenate(text: str) -> Tuple[str, List[Dict[str, Any]]]:
    """Remove only exact, zone-bounded page furniture from the derivative.

    Substring matches are forbidden. A prose sentence that merely mentions an
    illustrated parts list, an LEP data row, and procedure/assembly headings remain
    untouched. Cover/title pages are preserved. On pages containing a repeated
    ``ILLUSTRATED PARTS LIST`` header plus a semantic section title, only the first
    top-zone occurrence is removed.
    """
    raw_lines = _lines(text)
    nonempty_positions = [index for index, line in enumerate(raw_lines) if line.strip()]
    position_rank = {position: rank for rank, position in enumerate(nonempty_positions)}
    normalized_lines = [_normalize_structure_line(line) for line in raw_lines]
    normalized_joined = " | ".join(normalized_lines)
    title_page = (
        "THIS PUBLICATION SUPERSEDES" in normalized_joined
        or "PASSENGER SEATS" in normalized_lines
    )
    ipl_total = sum(1 for line in normalized_lines if line == "ILLUSTRATED PARTS LIST")
    ipl_occurrence = 0

    top_exact = {
        "EMBRAER",
        "MAINTENANCE MANUAL WITH",
        "EMBRAER COMPONENT MAINTENANCE MANUAL",
        "COMPONENT MAINTENANCE MANUAL",
        "WITH ILLUSTRATED PARTS LIST",
        "MAINTENANCE MANUAL WITH ILLUSTRATED PARTS LIST",
    }

    operations: List[Dict[str, Any]] = []
    kept: List[str] = []
    for index, line in enumerate(raw_lines):
        normalized = normalized_lines[index]
        if normalized == "ILLUSTRATED PARTS LIST":
            ipl_occurrence += 1
        rank = position_rank.get(index, -1)
        in_top_zone = 0 <= rank < 8
        in_bottom_zone = rank >= max(0, len(nonempty_positions) - 8)

        match_rule: Optional[str] = None
        zone: Optional[str] = None
        if not title_page and in_top_zone and normalized in top_exact:
            match_rule = "exact_top_header"
            zone = "top"
        elif not title_page and in_top_zone and normalized == "ILLUSTRATED PARTS LIST":
            # Preserve the later semantic title on pages such as the IPL section
            # title page; remove only the repeated page-furniture occurrence.
            if not (ipl_total >= 2 and ipl_occurrence >= 2):
                match_rule = "exact_top_ipl_header"
                zone = "top"
        elif not title_page and in_bottom_zone:
            if re.fullmatch(r"EFFECTIVITY(?: ALL)?(?: \d{2} \d{2} \d{2})?", normalized):
                match_rule = "exact_bottom_effectivity"
                zone = "bottom"
            elif re.fullmatch(r"PAGE [0-9IVXLCDM]+(?: [0-9IVXLCDM]+)?", normalized):
                match_rule = "exact_bottom_page"
                zone = "bottom"
            elif re.fullmatch(
                r"T P \d{2,4} \d{2,4}(?: [A-Z]{3} \d{1,2} \d{2})?",
                normalized,
            ):
                match_rule = "exact_bottom_technical_publication"
                zone = "bottom"
            elif re.fullmatch(r"\d{2} \d{2} \d{2}", normalized):
                match_rule = "exact_bottom_ata_code"
                zone = "bottom"

        if match_rule:
            operations.append({
                "operation": "remove_repeated_header_footer",
                "line_index": index,
                "removed": line.strip(),
                "confirmed_boilerplate": True,
                "match_rule": match_rule,
                "zone": zone,
            })
            continue
        kept.append(line)

    joined: List[str] = []
    index = 0
    while index < len(kept):
        line = kept[index]
        stripped = line.rstrip()
        if (
            index + 1 < len(kept)
            and stripped.endswith("-")
            and not stripped.endswith("--")
            and len(stripped) >= 2
            and stripped[-2].isalpha()
            and kept[index + 1][:1].islower()
        ):
            next_line = kept[index + 1].lstrip()
            joined.append(stripped[:-1] + next_line)
            operations.append({
                "operation": "join_linebreak_hyphen",
                "line_index": index,
                "left": stripped,
                "right": next_line,
            })
            index += 2
            continue
        joined.append(line)
        index += 1
    return "\n".join(joined), operations



# --------------------------------------------------------------------------- #
# D. Revision / service-record grid handling
# --------------------------------------------------------------------------- #
def revision_grid_extraction(primary_text: str, *, is_grid_route: bool) -> Dict[str, Any]:
    """Identify only revision/service-record grids with explicit header evidence."""
    header_lines = [line.strip() for line in _lines(primary_text) if line.strip()]
    normalized = [_normalize_structure_line(line) for line in header_lines]
    tokens = {token for line in normalized for token in line.split()}

    kind: Optional[str] = None
    evidence: List[str] = []
    if (
        "RECORD OF TEMPORARY REVISIONS" in normalized
        and {"REV", "DATE", "INSERTED"}.issubset(tokens)
    ):
        kind = "temporary_revision_record"
        evidence = ["record_of_temporary_revisions", "rev", "date", "inserted"]
    elif (
        "RECORD OF REVISIONS" in normalized
        and {"REV", "DATE", "INSERTED"}.issubset(tokens)
    ):
        kind = "revision_record"
        evidence = ["record_of_revisions", "rev", "date", "inserted"]
    elif (
        "SERVICE BULLETIN RECORD" in normalized
        and {"SERVICE", "BULLETIN", "INCORPORATION"}.issubset(tokens)
    ):
        kind = "service_bulletin_record"
        evidence = ["service_bulletin_record", "service", "bulletin", "incorporation"]

    is_revision_grid = bool(is_grid_route and kind)
    return {
        "is_revision_grid": is_revision_grid,
        "revision_grid_kind": kind if is_grid_route else None,
        "revision_header_evidence": evidence if is_grid_route else [],
        "preserved_header_lines": header_lines[:12] if is_revision_grid else [],
        "empty_cells_preserved_as_uncertain": True,
        "invented_cell_text": False,
        "psm6_grid_noise_promoted": False,
    }



# --------------------------------------------------------------------------- #
# E. Flattened-table safety
# --------------------------------------------------------------------------- #
def flat_table_row_association_contract(has_reconstructed_rows: bool) -> Dict[str, Any]:
    """When only flattened OCR exists, row association is forbidden. A row may be
    considered usable ONLY when the record carries source page, row/column
    assignment, coordinates, reconstruction method, and confidence/status."""
    return {
        "flat_text_row_association_forbidden": not has_reconstructed_rows,
        "searchable_flat_text_allowed": True,
        "row_relationship_usable": bool(has_reconstructed_rows),
        "required_fields_for_row_usability": [
            "source_page", "row_column_assignment", "coordinates",
            "reconstruction_method", "confidence_or_status", "raw_source_linkage",
        ],
        "proves_item_part_nomenclature_quantity": False,
    }


# --------------------------------------------------------------------------- #
# Top-level additive record builder
# --------------------------------------------------------------------------- #
_SAFETY = {
    "answer_permission": False,
    "can_prove_claims": False,
    "source_truth_mutation_allowed": False,
    "source_truth_mutations_performed": 0,
    "postgres_write_attempt_count": 0,
    "qdrant_write_attempt_count": 0,
    "opensearch_write_attempt_count": 0,
}


def build_cleanup_extraction(
    record: Mapping[str, Any],
    *,
    final_route: Optional[str] = None,
    has_reconstructed_rows: bool = False,
) -> Dict[str, Any]:
    """Produce Patch-5.1 additive cleanup fields without mutating raw evidence."""
    raw_ocr_text = record.get("primary_ocr_text")
    if raw_ocr_text is None:
        raw_ocr_text = record.get("best_ocr_text")
    if raw_ocr_text is None:
        raw_ocr_text = record.get("ocr_sample_text") or ""
    raw_psm11 = (
        record.get("tesseract_supplemental_psm11_raw_text")
        or record.get("supplemental_psm11_raw_text")
        or ""
    )
    page_id = record.get("page_id")
    route = final_route or record.get("accepted_route")

    index_structure = detect_index_toc_structure(raw_ocr_text)
    apply_leader_cleanup = index_structure.get("kind") == "table_of_contents"
    if apply_leader_cleanup:
        cleaned_text, leader_operations = clean_dotted_leaders(raw_ocr_text)
    else:
        cleaned_text, leader_operations = raw_ocr_text, []
    cleaned_text, boilerplate_operations = clean_boilerplate_and_dehyphenate(cleaned_text)
    operations = leader_operations + boilerplate_operations

    callout_scope_applied = route in _VISUAL_CALLOUT_ROUTES
    if callout_scope_applied:
        callout_candidates = filter_supplemental_callout_candidates(
            raw_psm11,
            raw_ocr_text,
            page_id=page_id,
        )
    else:
        callout_candidates = []
    retained = [
        candidate for candidate in callout_candidates
        if candidate.get("candidate_status") == "retained"
    ]

    is_index_or_toc = bool(
        route == "table" and index_structure.get("is_index_or_toc")
    )
    is_list_of_effective_pages = bool(
        route == "table" and index_structure.get("is_list_of_effective_pages")
    )
    toc_entries = (
        parse_toc_index_entries(raw_ocr_text)
        if is_index_or_toc and index_structure.get("kind") == "table_of_contents"
        else []
    )

    grid = revision_grid_extraction(
        raw_ocr_text,
        is_grid_route=route == "table",
    )
    flat_contract = flat_table_row_association_contract(has_reconstructed_rows)

    return {
        "cleanup_version": CLEANUP_VERSION,
        "cleanup_semantic_version": PATCH51_SEMANTIC_VERSION,
        "final_route_for_cleanup": route,
        "raw_ocr_text": raw_ocr_text,
        "raw_psm11_supplemental_text": raw_psm11,
        "cleaned_ocr_text": cleaned_text,
        "cleanup_operations_applied": operations,
        "cleanup_operation_count": len(operations),
        "dotted_leader_cleanup_scope_applied": apply_leader_cleanup,
        "is_index_or_toc": is_index_or_toc,
        "is_list_of_effective_pages": is_list_of_effective_pages,
        "index_or_toc_kind": index_structure.get("kind"),
        "index_structure_detection": index_structure,
        "toc_index_entries": toc_entries,
        "supplemental_callout_scope_applied": callout_scope_applied,
        "supplemental_callout_scope_reason": (
            "visual_or_mixed_route" if callout_scope_applied
            else "not_visual_route_no_callout_candidates"
        ),
        "filtered_supplemental_callout_candidates": callout_candidates,
        "retained_callout_candidate_count": len(retained),
        "rejected_callout_candidate_count": len(callout_candidates) - len(retained),
        "supplemental_callouts_confirmed": False,
        "supplemental_callouts_are_source_truth": False,
        "revision_grid_extraction": grid,
        "flat_text_row_association_forbidden": flat_contract["flat_text_row_association_forbidden"],
        "table_row_association_contract": flat_contract,
        **_SAFETY,
    }

