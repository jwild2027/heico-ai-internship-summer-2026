"""Parse maintenance manual / illustrated-parts-list metadata from OCR text.

This parser handles more than figure pages. The TIFF collection may contain
manual covers, applicability pages, introductions, lists of effective pages,
illustrated-parts-list figures, and blank/unknown pages.

The parser is intentionally rule-based and explainable. It extracts values only
when the OCR text provides clear signals; the source TIFF remains the authority.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Optional

from .metadata_parser import normalize_ocr_text


@dataclass(frozen=True)
class ParsedManualMetadata:
    """Metadata found on a maintenance manual / IPL page."""

    document_type: Optional[str] = None
    manufacturer: Optional[str] = None
    manual_title: Optional[str] = None
    document_code: Optional[str] = None
    publication_number: Optional[str] = None
    component_title: Optional[str] = None
    section_title: Optional[str] = None
    figure_title: Optional[str] = None
    figure_number: Optional[str] = None
    effectivity: Optional[str] = None
    ata_code: Optional[str] = None
    page_number: Optional[int] = None
    page_label: Optional[str] = None
    issue_date: Optional[str] = None
    revision_date: Optional[str] = None
    revision_label: Optional[str] = None
    part_numbers: list[str] = field(default_factory=list)
    callouts: list[str] = field(default_factory=list)
    metadata_confidence: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


_MONTH_SHORT_RE = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?"
_MONTH_LONG_RE = r"(?:JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)"
_DATE_SHORT_PATTERN = re.compile(rf"\b({_MONTH_SHORT_RE}\s*\d{{1,2}}/\d{{2,4}})\b", re.I)
_DATE_LONG_PATTERN = re.compile(rf"\b(\d{{1,2}}\s+{_MONTH_LONG_RE}\s+\d{{4}})\b", re.I)
_ATA_PATTERN = re.compile(r"\b(\d{2}-\d{2}-\d{2})\b")
_ATA_SECTION_PATTERN = re.compile(r"\b(\d{2})\s*-\s*([A-Z][A-Z ]{3,40})\b", re.I)
_PAGE_PATTERN = re.compile(r"\bPage\s+([0-9]{1,5})\b", re.I)
_PAGE_LABEL_PATTERN = re.compile(r"\bPage\s+([0-9ivxlcdmIVXLCDM]+(?:\s*/\s*[0-9ivxlcdmIVXLCDM]+)?)\b", re.I)
_FIGURE_PATTERN = re.compile(r"\bFig(?:ure|\.)?\s*([0-9A-Z]{1,8})\b", re.I)
_EFFECTIVITY_PATTERN = re.compile(r"\bEFFECTIVITY\s*[:\-]?\s*([^\n\r]+)", re.I)
_DOT_DOCUMENT_CODE_PATTERN = re.compile(r"\b([A-Z0-9]{4,}\.[A-Z0-9]{2,8})\b", re.I)
_PUBLICATION_PATTERN = re.compile(r"\bT\s*\.?\s*P\s*\.?\s*[:\-]?\s*(\d{2,4}\s*/\s*\d{2,5})\b", re.I)
_PART_NUMBER_PATTERN = re.compile(r"\b\d{3}-\d{5}-\d{3}\b")
_REVISION_LABEL_PATTERN = re.compile(r"\b(REVISION\s+[A-Z0-9]+\s*[-–]\s*[^\n\r]+)", re.I)

# Region labels from the OCR report should not become callouts.
_REGION_LABEL_PATTERN = re.compile(r"^\[[A-Za-z0-9_ -]+\]$")

_EXCLUDED_CALLOUTS = {
    "EMBRAER",
    "MAINTENANCE MANUAL WITH",
    "COMPONENT MAINTENANCE MANUAL",
    "ILLUSTRATED PARTS LIST",
    "EFFECTIVITY",
    "EFFECTIVITY ALL",
    "ALL",
    "APPLICABILITY",
    "INTRODUCTION",
    "LIST OF EFFECTIVE PAGES",
}

_SECTION_TITLES = [
    "LIST OF EFFECTIVE PAGES",
    "NUMERICAL INDEX",
    "APPLICABILITY",
    "INTRODUCTION",
    "CONTENTS",
    "VENDORS",
]


_ROMAN_NUMERAL_RE = re.compile(r"^[ivxlcdmIVXLCDM]+(?:\s*/\s*[ivxlcdmIVXLCDM]+)?$")


def _lines(text: str) -> list[str]:
    cleaned = normalize_ocr_text(text)
    out: list[str] = []
    for raw_line in cleaned.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip(" .,:;|[]{}()")
        if not line:
            continue
        if _REGION_LABEL_PATTERN.match(line):
            continue
        out.append(line)
    return out


def _find_manufacturer(text: str) -> Optional[str]:
    if re.search(r"\bEMBRAER\b", text, re.I):
        return "EMBRAER"
    if re.search(r"\bBOEING\b", text, re.I):
        return "BOEING"
    if re.search(r"\bAIRBUS\b", text, re.I):
        return "AIRBUS"
    return None


def _find_manual_title(text: str) -> Optional[str]:
    compact = re.sub(r"\s+", " ", text).strip()
    if re.search(
        r"COMPONENT\s+MAINTENANCE\s+MANUAL\s+WITH\s+ILLUSTRATED\s+PARTS\s+LIST",
        compact,
        re.I,
    ):
        return "COMPONENT MAINTENANCE MANUAL WITH ILLUSTRATED PARTS LIST"
    if re.search(r"MAINTENANCE\s+MANUAL\s+WITH\s+ILLUSTRATED\s+PARTS\s+LIST", compact, re.I):
        return "MAINTENANCE MANUAL WITH ILLUSTRATED PARTS LIST"
    if re.search(r"ILLUSTRATED\s+PARTS\s+(?:LIST|CATALOG|CATALOGUE)", compact, re.I):
        return "ILLUSTRATED PARTS LIST"
    if re.search(r"MAINTENANCE\s+MANUAL", compact, re.I):
        return "MAINTENANCE MANUAL"
    return None


def _normalize_publication_number(match_value: str) -> str:
    value = re.sub(r"\s+", "", match_value)
    return f"T.P. {value}"


def _find_publication_number(text: str) -> Optional[str]:
    match = _PUBLICATION_PATTERN.search(text)
    if not match:
        return None
    return _normalize_publication_number(match.group(1))


def _looks_like_domain_code(value: str) -> bool:
    upper = value.upper()
    return (
        "WWW" in upper
        or upper.startswith("AVWW")
        or ".EMBRAER" in upper
        or upper.endswith(".COM")
        or upper.endswith(".BR")
    )


def _find_document_code(lines: list[str], text: str, publication_number: Optional[str]) -> Optional[str]:
    # Prefer a dot-code like 120TP250002.MCE when it is on a line by itself.
    for line in lines:
        match = _DOT_DOCUMENT_CODE_PATTERN.fullmatch(line.strip())
        if match:
            candidate = match.group(1).upper()
            if not _looks_like_domain_code(candidate):
                return candidate

    for match in _DOT_DOCUMENT_CODE_PATTERN.finditer(text):
        candidate = match.group(1).upper()
        if not _looks_like_domain_code(candidate):
            return candidate

    # Manual cover/section pages often use T.P. 120/1176 as the stable identifier.
    return publication_number


def _find_section_title(lines: list[str], text: str) -> Optional[str]:
    upper_text = text.upper()
    for title in _SECTION_TITLES:
        if title in upper_text:
            return title

    # Footer style examples: 25-APPLICABILITY, 25-INTRODUCTION.
    for match in _ATA_SECTION_PATTERN.finditer(text):
        candidate = re.sub(r"\s+", " ", match.group(2)).strip().upper()
        candidate = candidate.replace("  ", " ")
        for title in _SECTION_TITLES:
            if title in candidate:
                return title
    return None


def _looks_like_non_title_line(line: str) -> bool:
    upper = line.upper().strip()
    if _REGION_LABEL_PATTERN.match(line):
        return True
    if _DOT_DOCUMENT_CODE_PATTERN.search(line) or _PUBLICATION_PATTERN.search(line):
        return True
    if _ATA_PATTERN.search(line) or _ATA_SECTION_PATTERN.search(line):
        return True
    if _PAGE_LABEL_PATTERN.search(line):
        return True
    if _DATE_SHORT_PATTERN.search(line) or _DATE_LONG_PATTERN.search(line):
        return True
    if _PART_NUMBER_PATTERN.search(line):
        return True
    if upper.startswith("EFFECTIVITY"):
        return True
    if upper.startswith("FIGURE") or upper.startswith("FIG."):
        return True
    if upper.startswith("THIS PUBLICATION"):
        return True
    if upper.startswith("EMPRESA") or upper.startswith("AV. ") or upper.startswith("FAX"):
        return True
    if "MAINTENANCE MANUAL" in upper or "ILLUSTRATED PARTS" in upper:
        return True
    if upper in _EXCLUDED_CALLOUTS:
        return True
    return False


def _find_component_title(lines: list[str], section_title: Optional[str]) -> Optional[str]:
    # On cover pages this is usually a large all-caps line such as PASSENGER SEATS.
    for line in lines:
        upper = line.upper().strip(" .,:;|[]{}()")
        if not upper or upper == section_title:
            continue
        if _looks_like_non_title_line(line):
            continue
        if len(upper) < 5 or len(upper) > 80:
            continue
        if _uppercase_letter_ratio(line) < 0.85:
            continue
        # Avoid taking body/table headings as the component title.
        if upper in {"CHAPTER", "SECTION", "SUBJECT", "PAGE", "DATE"}:
            continue
        return upper
    return None


def _find_figure(lines: list[str], text: str) -> tuple[Optional[str], Optional[str]]:
    figure_number: Optional[str] = None
    figure_title: Optional[str] = None

    for idx, line in enumerate(lines):
        match = _FIGURE_PATTERN.search(line)
        if not match:
            continue
        figure_number = match.group(1).upper()

        # The line before "Figure 2" is often the figure title.
        for previous in reversed(lines[:idx]):
            if _looks_like_non_title_line(previous):
                continue
            figure_title = previous.strip()
            break
        break

    if figure_number is None:
        match = _FIGURE_PATTERN.search(text)
        if match:
            figure_number = match.group(1).upper()

    return figure_title, figure_number


def _find_effectivity(text: str) -> Optional[str]:
    match = _EFFECTIVITY_PATTERN.search(text)
    if not match:
        return None
    value = re.sub(r"\s+", " ", match.group(1)).strip(" .,:;|[]{}()")
    # Avoid accidentally swallowing the next field if OCR missed a newline.
    split_patterns = [
        r"\bPage\b",
        r"\bFig(?:ure)?\b",
        r"\b[0-9]{2}\s*-\s*[0-9]{2}\s*-\s*[0-9]{2}\b",
        r"\b[0-9]{2}\s*-\s*[A-Z][A-Z ]+\b",
        _DATE_SHORT_PATTERN.pattern,
        _DATE_LONG_PATTERN.pattern,
    ]
    for pattern in split_patterns:
        value = re.split(pattern, value, maxsplit=1, flags=re.I)[0]
    return value.strip(" .,:;|[]{}()") or None


def _find_page_label(text: str) -> Optional[str]:
    match = _PAGE_LABEL_PATTERN.search(text)
    if not match:
        return None
    return re.sub(r"\s+", "", match.group(1)).lower()


def _find_page_number(page_label: Optional[str]) -> Optional[int]:
    if not page_label:
        return None
    first = page_label.split("/")[0]
    if first.isdigit():
        return int(first)
    return None


def _normalize_date(value: str) -> str:
    value = re.sub(r"\s+", " ", value).replace("Sept", "Sep").strip()
    parts = value.split()
    if len(parts) >= 3 and parts[1].isalpha():
        return " ".join([parts[0], parts[1].title(), parts[2]])
    return value


def _find_dates(text: str) -> list[str]:
    dates: list[str] = []
    # Preserve order and duplicates. On list-of-effective-pages pages, the same
    # date can appear in a body table and again in the page footer; the footer
    # date should remain visible as the last date.
    matches: list[tuple[int, str]] = []
    for pattern in (_DATE_SHORT_PATTERN, _DATE_LONG_PATTERN):
        for match in pattern.finditer(text):
            matches.append((match.start(), _normalize_date(match.group(1))))
    for _, value in sorted(matches, key=lambda item: item[0]):
        dates.append(value)
    return dates


def _find_revision_label(text: str) -> Optional[str]:
    match = _REVISION_LABEL_PATTERN.search(text)
    if not match:
        return None
    return re.sub(r"\s+", " ", match.group(1)).strip(" .,:;|[]{}()")


def _find_part_numbers(text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for match in _PART_NUMBER_PATTERN.finditer(text):
        value = match.group(0)
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _uppercase_letter_ratio(line: str) -> float:
    letters = [char for char in line if char.isalpha()]
    if not letters:
        return 0.0
    uppercase = [char for char in letters if char.isupper()]
    return len(uppercase) / len(letters)


def _find_callouts(lines: list[str]) -> list[str]:
    callouts: list[str] = []
    seen: set[str] = set()
    for line in lines:
        upper = line.upper().strip(" .,:;|[]{}()")
        if not upper or upper in seen or upper in _EXCLUDED_CALLOUTS:
            continue
        if _looks_like_non_title_line(line):
            continue
        # Visual labels/callouts are usually printed in all caps. This avoids
        # turning mixed-case figure titles or OCR fragments into callouts.
        if _uppercase_letter_ratio(line) < 0.85:
            continue
        if re.fullmatch(r"[A-Z][A-Z0-9&/ -]{2,40}", upper):
            callouts.append(upper)
            seen.add(upper)
    return callouts[:25]


def _document_type(
    *,
    manual_title: Optional[str],
    figure_number: Optional[str],
    ata_code: Optional[str],
    section_title: Optional[str],
    component_title: Optional[str],
    publication_number: Optional[str],
) -> Optional[str]:
    if section_title == "LIST OF EFFECTIVE PAGES":
        return "manual_list_of_effective_pages"
    if section_title == "APPLICABILITY":
        return "manual_applicability_page"
    if section_title == "INTRODUCTION":
        return "manual_introduction_page"
    if section_title == "CONTENTS":
        return "manual_contents_page"
    if section_title == "NUMERICAL INDEX":
        return "manual_numerical_index_page"
    if section_title == "VENDORS":
        return "manual_vendors_page"
    if manual_title and component_title and publication_number:
        return "manual_cover_page"
    if manual_title and "PARTS" in manual_title:
        return "maintenance_manual_ipl"
    if manual_title:
        return "maintenance_manual"
    if figure_number and ata_code:
        return "manual_illustration_page"
    if ata_code or publication_number:
        return "manual_page"
    return None


def _confidence(values: dict[str, object]) -> float:
    weights = {
        "document_type": 0.12,
        "manufacturer": 0.08,
        "manual_title": 0.14,
        "document_code": 0.12,
        "publication_number": 0.10,
        "component_title": 0.08,
        "section_title": 0.10,
        "figure_title": 0.10,
        "figure_number": 0.08,
        "effectivity": 0.06,
        "ata_code": 0.06,
        "page_label": 0.04,
        "revision_date": 0.06,
        "part_numbers": 0.04,
    }
    score = 0.0
    for key, weight in weights.items():
        if values.get(key) not in (None, "", []):
            score += weight
    return round(min(score, 1.0), 3)


def parse_manual_page_text(text: str) -> ParsedManualMetadata:
    """Extract manual/IPL metadata from OCR text."""

    cleaned = normalize_ocr_text(text)
    lines = _lines(cleaned)

    manufacturer = _find_manufacturer(cleaned)
    manual_title = _find_manual_title(cleaned)
    publication_number = _find_publication_number(cleaned)
    document_code = _find_document_code(lines, cleaned, publication_number)
    section_title = _find_section_title(lines, cleaned)
    component_title = _find_component_title(lines, section_title)
    figure_title, figure_number = _find_figure(lines, cleaned)
    effectivity = _find_effectivity(cleaned)
    ata_match = _ATA_PATTERN.search(cleaned)
    ata_code = ata_match.group(1) if ata_match else None
    page_label = _find_page_label(cleaned)
    page_number = _find_page_number(page_label)
    dates = _find_dates(cleaned)
    revision_label = _find_revision_label(cleaned)
    issue_date = dates[0] if dates else None
    revision_date = dates[-1] if dates else None
    part_numbers = _find_part_numbers(cleaned)
    callouts = _find_callouts(lines)
    document_type = _document_type(
        manual_title=manual_title,
        figure_number=figure_number,
        ata_code=ata_code,
        section_title=section_title,
        component_title=component_title,
        publication_number=publication_number,
    )

    parsed = {
        "document_type": document_type,
        "manufacturer": manufacturer,
        "manual_title": manual_title,
        "document_code": document_code,
        "publication_number": publication_number,
        "component_title": component_title,
        "section_title": section_title,
        "figure_title": figure_title,
        "figure_number": figure_number,
        "effectivity": effectivity,
        "ata_code": ata_code,
        "page_number": page_number,
        "page_label": page_label,
        "issue_date": issue_date,
        "revision_date": revision_date,
        "revision_label": revision_label,
        "part_numbers": part_numbers,
    }

    return ParsedManualMetadata(
        document_type=document_type,
        manufacturer=manufacturer,
        manual_title=manual_title,
        document_code=document_code,
        publication_number=publication_number,
        component_title=component_title,
        section_title=section_title,
        figure_title=figure_title,
        figure_number=figure_number,
        effectivity=effectivity,
        ata_code=ata_code,
        page_number=page_number,
        page_label=page_label,
        issue_date=issue_date,
        revision_date=revision_date,
        revision_label=revision_label,
        part_numbers=part_numbers,
        callouts=callouts,
        metadata_confidence=_confidence(parsed),
    )
