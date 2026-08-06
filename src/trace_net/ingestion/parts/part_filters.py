"""Shared filters for aircraft part-number and nomenclature cleanup.

The OCR extractor intentionally starts broad so that it does not miss real
technical values. This module is the second-stage filter that separates likely
catalog parts from ATA/page/figure/manual references and rejects obvious OCR
nomenclature noise.
"""

from __future__ import annotations

import re

WS_RE = re.compile(r"\s+")


def collapse_ws(value: str | None) -> str:
    if not value:
        return ""
    return WS_RE.sub(" ", str(value)).strip()


def normalize_part_key(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^A-Za-z0-9]", "", str(value)).upper()


def _display(value: str | None) -> str:
    return collapse_ws(value).upper().strip(" |:;,.()[]{}")


ATA_REFERENCE_RE = re.compile(
    r"^(?:\d{2}|[O0Q]\d|\d[O0Q])[-\s](?:\d{2}|[O0Q]\d|\d[O0Q])[-\s](?:\d{2}|[O0Q]\d|\d[O0Q])(?:[-\s][A-Z0-9]{1,4})?$",
    re.I,
)
ATA_DERIVED_LABEL_RE = re.compile(
    r"^(?:\d{2}|[O0Q]\d|\d[O0Q])[-\s]?(?:IPL|CONTENTS|INTRODUCTION|APPLICABILITY|VENDORS?|LIST)$",
    re.I,
)
PAGE_RANGE_RE = re.compile(r"^\d{3,5}\s*/\s*\d{3,5}$")
DRAWING_REFERENCE_RE = re.compile(r"^\d{2,4}\s*(?:TP|CMM|1P)\s*\d{5,8}[A-Z]?\s*[.]?\s*MCE$", re.I)
TASK_REFERENCE_RE = re.compile(r"^120[-\s]\d{2}[-\s]\d{3,5}[A-Z]?$", re.I)
BAD_PART_PREFIX_RE = re.compile(r"^(?:TP|T\.P|PAGE|FIG|FIGURE|SHEET|SEP|JAN|APR|JUL|OCT|NOV|DEC)\b", re.I)

BAD_NOMENCLATURE_EXACT = {
    "T.P",
    "T.P.",
    "T P",
    "TP",
    "IGURE",
    "FIGURE",
    "SHEET",
    "SEP",
    "JAN",
    "APR",
    "JUL",
    "AND",
    "PER STOCK",
    "OOF [IN",
    "OOF [TN",
    "ROO [REN",
    "UNITS AIRLINE",
    "EFFECTIVITY",
    "PAGE",
    "CONTENTS",
    "APPLICABILITY",
}
BAD_NOMENCLATURE_STARTS = (
    "T.P",
    "TP ",
    "IGURE",
    "FIGURE",
    "SHEET",
    "SEP",
    "JAN",
    "APR",
    "JUL",
    "PAGE ",
    "EFFECTIVITY",
    "THIS PUBLICATION COVERS",
    "SAO JOSE",
    "UNITS AIRLINE",
    "OOF [",
    "ROO [",
    "BOTTOM ",
    "TOP ",
    "25-",
    "20-21-",
    "Z20-",
)
BAD_NOMENCLATURE_CONTAINS = (
    "MAINTENANCE MANUAL",
    "ILLUSTRATED PARTS LIST",
    "BLANK JAN",
    "BLANK SEP",
    "PAGES DELETED",
    "5-APPLICABILITY",
    "25-APPLICABILITY",
    "25-CONTENTS",
    "25-INTRODUCTION",
)
GENERIC_ONE_WORDS = {
    "AND",
    "SHEET",
    "SEP",
    "IGURE",
    "FIGURE",
    "TABLE",
    "MATERIAL",
    "TERIAL",
    "DESCRIBED",
    "ITION",
}


def is_ata_reference_number(value: str | None) -> bool:
    display = _display(value)
    if not display:
        return False
    if ATA_REFERENCE_RE.fullmatch(display):
        return True
    if ATA_DERIVED_LABEL_RE.fullmatch(display):
        return True
    # Normalized forms such as 25210046 are ATA 25-21-00-46 style values.
    norm = normalize_part_key(display)
    if re.fullmatch(r"\d{8,10}[A-Z]?", norm) and norm.startswith(("252100", "202100", "512500", "517001")):
        return True
    return False


def is_obvious_reference_number(value: str | None) -> bool:
    display = _display(value)
    if not display:
        return True
    norm = normalize_part_key(display)
    if is_ata_reference_number(display):
        return True
    if ATA_DERIVED_LABEL_RE.fullmatch(display):
        return True
    if PAGE_RANGE_RE.fullmatch(display):
        return True
    if BAD_PART_PREFIX_RE.search(display):
        return True
    if TASK_REFERENCE_RE.fullmatch(display):
        return True
    # MCE values are drawing/repair document references in this pilot, not catalog parts.
    if DRAWING_REFERENCE_RE.fullmatch(display.replace(" ", "")):
        return True
    if norm.endswith("MCE") and norm.startswith(("120TP", "120CMM", "420TP", "420CMM", "1201P")):
        return True
    if display in {"T.P", "T.P.", "T P", "25-IPL", "25-CONTENTS", "25-VENDORS", "25-INTRODUCTION"}:
        return True
    return False


def is_probable_real_part_number(value: str | None) -> bool:
    """Return True for likely catalog part numbers, False for ATA/page references."""

    display = _display(value)
    norm = normalize_part_key(display)
    if not display or not norm:
        return False
    if is_obvious_reference_number(display):
        return False
    if len(norm) < 5:
        return False
    if not any(ch.isdigit() for ch in norm):
        return False
    has_alpha = any(ch.isalpha() for ch in norm)

    # Common aircraft/hardware part families in the pilot.
    if re.fullmatch(r"120[-\s]\d{5}[-\s][A-Z0-9]{2,5}(?:/[A-Z0-9]{2,5})*", display):
        return True
    if re.fullmatch(r"(?:AM|AN|MS|NAS|HL|CR|PE|H)\s*[A-Z0-9.-]{3,20}", display):
        return True
    if re.fullmatch(r"\d{3}[-\s]\d{4,6}(?:/[A-Z0-9]{1,6})?", display):
        return True
    if has_alpha and re.search(r"[-/.]", display) and len(norm) >= 5:
        return True
    if not has_alpha and re.search(r"[-/]", display) and len(norm) >= 8:
        return True
    return False


# More explicit aliases used by QA and scripts.
def is_reference_like_part_number(value: str | None) -> bool:
    return is_obvious_reference_number(value) or is_ata_reference_number(value)


def is_catalog_part_candidate(value: str | None) -> bool:
    return is_probable_real_part_number(value)


def clean_name_for_filter(value: str | None) -> str:
    text = collapse_ws(value).upper()
    text = text.strip(" |:;,.()[]{}")
    text = re.sub(r"\s*,\s*", ", ", text)
    return collapse_ws(text)


def is_bad_nomenclature(value: str | None) -> bool:
    """Reject strings that are clearly page/header/OCR noise, not catalog names."""

    text = clean_name_for_filter(value)
    if not text:
        return True
    if text in BAD_NOMENCLATURE_EXACT:
        return True
    if any(text.startswith(prefix) for prefix in BAD_NOMENCLATURE_STARTS):
        return True
    if any(phrase in text for phrase in BAD_NOMENCLATURE_CONTAINS):
        return True
    if is_ata_reference_number(text):
        return True
    tokens = re.findall(r"[A-Z0-9/.-]+", text)
    if not tokens:
        return True
    alpha_tokens = [tok for tok in tokens if any(ch.isalpha() for ch in tok)]
    if not alpha_tokens:
        return True
    if len(tokens) == 1 and tokens[0] in GENERIC_ONE_WORDS:
        return True
    if len(tokens) <= 2 and all(tok in GENERIC_ONE_WORDS for tok in tokens):
        return True
    # Reject mostly date/page fragments and OCR junk groups.
    code_like = sum(1 for tok in tokens if re.fullmatch(r"[A-Z]{0,4}\d{2,8}[A-Z]?", tok))
    if code_like >= max(1, len(tokens) - 1) and len(alpha_tokens) <= 1:
        return True
    if len(text) > 96:
        return True
    return False


def is_good_qa_nomenclature(value: str | None) -> bool:
    return bool(value and not is_bad_nomenclature(value))


def canonicalize_nomenclature_for_comparison(value: str | None) -> str:
    """Return a stable key used for conflict detection."""

    text = clean_name_for_filter(value)
    if not text:
        return ""
    # Drop common trailing dot leaders, OCR filler, effectivity/model codes.
    text = re.sub(r"\s+[.·:_=»~\-]+\s*$", "", text)
    text = re.sub(r"\s+[.·:_=»~\-]*\s*(?:0+[COEES]*|[COEES]{2,}|[VWES]{0,4}\d{3,6}[A-Z]?|V[SW]4956|E\d{5,6}\s*[A-Z]?)\s*$", "", text)
    text = re.sub(r"\s+[.·:_=»~\-]+\s*(?:0+[COEES]*|[COEES]{2,}|[VWES]{0,4}\d{3,6}[A-Z]?).*$", "", text)
    text = re.sub(r"\s+[.=:\-]+\s*$", "", text)
    text = collapse_ws(text.strip(" |:;,."))
    return text
