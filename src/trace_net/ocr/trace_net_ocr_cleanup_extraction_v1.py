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
    """Filter raw PSM-11 sparse text into supplemental callout CANDIDATES.

    Prefers locally dispersed short labels and numeric callouts; rejects repeated
    manual headers/footers, ATA/TP footers, and punctuation/grid noise. Every entry
    is a candidate only (confirmed == False, source_truth == False) and carries its
    filtering/rejection reason. Coordinates are None here (stdout OCR carries no
    bounding boxes); downstream fishnet/coordinate tooling may attach them later.
    """
    primary_tokens = {t.lower() for t in _tokens(primary_text)}
    seen: set[str] = set()
    candidates: List[Dict[str, Any]] = []
    for tok in _tokens(psm11_raw_text):
        key = tok.lower()
        if key in seen:
            continue
        seen.add(key)
        base = {
            "candidate_text": tok,
            "source_psm": 11,
            "page_id": page_id,
            "bounding_box": None,
            "also_in_primary_psm3": key in primary_tokens,
            "confirmed": False,
            "source_truth": False,
        }
        bp = _boilerplate_reason(tok)
        if bp:
            candidates.append({**base, "candidate_status": "rejected_boilerplate",
                               "filtering_reason": "boilerplate_rejected",
                               "boilerplate_rejection_reason": bp})
            continue
        nz = _noise_reason(tok)
        if nz:
            candidates.append({**base, "candidate_status": "rejected_noise",
                               "filtering_reason": nz,
                               "boilerplate_rejection_reason": None})
            continue
        # Preferred callout shapes: short numeric item labels, single/short letter
        # detail labels (A, B, C, A-A), and part-number-shaped tokens.
        if re.fullmatch(r"\d{1,4}[A-Z]?", tok):
            reason = "numeric_callout_label"
        elif re.fullmatch(r"[A-Z](?:-[A-Z])?", tok):
            reason = "letter_detail_label"
        elif _PART_RE.fullmatch(tok):
            reason = "part_number_shaped_candidate"
        elif len(tok) <= 12:
            reason = "short_dispersed_label"
        else:
            candidates.append({**base, "candidate_status": "rejected_noise",
                               "filtering_reason": "long_non_label_token",
                               "boilerplate_rejection_reason": None})
            continue
        candidates.append({**base, "candidate_status": "retained",
                           "filtering_reason": reason,
                           "boilerplate_rejection_reason": None})
    return candidates


# --------------------------------------------------------------------------- #
# F. Conservative boilerplate + dehyphenation cleanup (CLEANED DERIVATIVE only)
# --------------------------------------------------------------------------- #
def _is_boilerplate_line(line: str) -> bool:
    return any(r.search(line) for r in _BOILERPLATE_LINE_RES)


def clean_boilerplate_and_dehyphenate(text: str) -> Tuple[str, List[Dict[str, Any]]]:
    """Remove confirmed repeated headers/footers, normalize EMBRAER header variants,
    and join line-break hyphens ONLY when the previous line ends in a hyphen and the
    next begins with a lowercase continuation. Legitimate part-number hyphens are
    never touched. Operates on a cleaned derivative; raw text is untouched."""
    ops: List[Dict[str, Any]] = []
    raw_lines = _lines(text)
    kept: List[str] = []
    for idx, line in enumerate(raw_lines):
        if _EMBRAER_HEADER_VARIANT_RE.match(line) and "embraer" in line.lower():
            ops.append({"operation": "normalize_embraer_header", "line_index": idx, "removed": line.strip()})
            continue
        if _is_boilerplate_line(line):
            ops.append({"operation": "remove_repeated_header_footer", "line_index": idx, "removed": line.strip()})
            continue
        kept.append(line)

    # Dehyphenation across line breaks.
    joined: List[str] = []
    i = 0
    while i < len(kept):
        line = kept[i]
        stripped = line.rstrip()
        if (
            i + 1 < len(kept)
            and stripped.endswith("-")
            and not stripped.endswith(("--",))
            and len(stripped) >= 2
            and stripped[-2].isalpha()
            and kept[i + 1][:1].islower()
        ):
            nxt = kept[i + 1].lstrip()
            merged = stripped[:-1] + nxt
            # Never merge across a part-number hyphen: guard is the lowercase-next +
            # alpha-before-hyphen condition above (part numbers are digit-bounded).
            joined.append(merged)
            ops.append({"operation": "join_linebreak_hyphen", "line_index": i,
                        "left": stripped, "right": nxt})
            i += 2
            continue
        joined.append(line)
        i += 1
    return "\n".join(joined), ops


# --------------------------------------------------------------------------- #
# D. Revision / service-record grid handling
# --------------------------------------------------------------------------- #
def revision_grid_extraction(primary_text: str, *, is_grid_route: bool) -> Dict[str, Any]:
    """Preserve meaningful headers of a revision/service-record grid without
    inventing text for empty cells or promoting PSM-6 grid noise. Empty-cell
    uncertainty is preserved explicitly."""
    header_lines = [ln.strip() for ln in _lines(primary_text) if ln.strip()]
    return {
        "is_revision_grid": bool(is_grid_route),
        "preserved_header_lines": header_lines[:8],
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
    """Produce the additive Patch-5 cleanup/extraction fields for one scan-pack
    record. Never mutates the input; returns only new fields to merge alongside it.

    `final_route` is the canonical manifest route (table/normal_text/image_visual/
    blank_candidate); it selects which derivative extractions are attached. Raw OCR
    and raw PSM-11 text are echoed unchanged for provenance.
    """
    raw_ocr_text = record.get("ocr_sample_text")
    if raw_ocr_text is None:
        raw_ocr_text = record.get("best_ocr_text") or record.get("primary_ocr_text") or ""
    raw_psm11 = record.get("tesseract_supplemental_psm11_raw_text") or record.get("supplemental_psm11_raw_text") or ""
    page_id = record.get("page_id")
    route = final_route or record.get("accepted_route")

    cleaned_text, leader_ops = clean_dotted_leaders(raw_ocr_text)
    cleaned_text, bp_ops = clean_boilerplate_and_dehyphenate(cleaned_text)
    operations = leader_ops + bp_ops

    callout_candidates = filter_supplemental_callout_candidates(raw_psm11, raw_ocr_text, page_id=page_id)
    retained = [c for c in callout_candidates if c["candidate_status"] == "retained"]

    is_index = route == "table" and bool(parse_toc_index_entries(raw_ocr_text))
    toc_entries = parse_toc_index_entries(raw_ocr_text) if route == "table" else []

    is_grid_route = route == "table"
    grid = revision_grid_extraction(raw_ocr_text, is_grid_route=is_grid_route)

    flat_contract = flat_table_row_association_contract(has_reconstructed_rows)

    return {
        "cleanup_version": CLEANUP_VERSION,
        "final_route_for_cleanup": route,
        # A. raw preserved unchanged (echoed for provenance; never overwritten)
        "raw_ocr_text": raw_ocr_text,
        "raw_psm11_supplemental_text": raw_psm11,
        # A/B/F. cleaned derivative + operations log
        "cleaned_ocr_text": cleaned_text,
        "cleanup_operations_applied": operations,
        "cleanup_operation_count": len(operations),
        # B. TOC/index parse (table route only)
        "is_index_or_toc": is_index,
        "toc_index_entries": toc_entries,
        # C. supplemental callout candidates (candidates only)
        "filtered_supplemental_callout_candidates": callout_candidates,
        "retained_callout_candidate_count": len(retained),
        "rejected_callout_candidate_count": len(callout_candidates) - len(retained),
        "supplemental_callouts_confirmed": False,
        "supplemental_callouts_are_source_truth": False,
        # D. revision/grid handling
        "revision_grid_extraction": grid,
        # E. flattened-table safety
        "flat_text_row_association_forbidden": flat_contract["flat_text_row_association_forbidden"],
        "table_row_association_contract": flat_contract,
        **_SAFETY,
    }
