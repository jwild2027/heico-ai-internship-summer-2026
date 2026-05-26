"""Parse maintenance manual / illustrated-parts-list metadata from OCR text.

The TIFF collection may contain more than engineering drawings. This parser is
for manual/IPL pages like manufacturer maintenance manual figures. It is
conservative: it extracts high-value fields when the OCR text gives clear
signals, but the source TIFF remains the authority.
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
    figure_title: Optional[str] = None
    figure_number: Optional[str] = None
    effectivity: Optional[str] = None
    ata_code: Optional[str] = None
    page_number: Optional[int] = None
    revision_date: Optional[str] = None
    callouts: list[str] = field(default_factory=list)
    metadata_confidence: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


_MONTH_RE = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?"
_DATE_PATTERN = re.compile(rf"\b({_MONTH_RE}\s*\d{{1,2}}/\d{{2,4}})\b", re.I)
_ATA_PATTERN = re.compile(r"\b(\d{2}-\d{2}-\d{2})\b")
_PAGE_PATTERN = re.compile(r"\bPage\s+([0-9]{1,5})\b", re.I)
_FIGURE_PATTERN = re.compile(r"\bFig(?:ure|\.)?\s*([0-9A-Z]{1,8})\b", re.I)
_EFFECTIVITY_PATTERN = re.compile(r"\bEFFECTIVITY\s*[:\-]?\s*([^\n\r]+)", re.I)
_DOCUMENT_CODE_PATTERN = re.compile(r"\b([A-Z0-9]{4,}\.[A-Z0-9]{2,8})\b", re.I)

# Region labels from the OCR report should not become callouts.
_REGION_LABEL_PATTERN = re.compile(r"^\[[A-Za-z0-9_ -]+\]$")

_EXCLUDED_CALLOUTS = {
    "EMBRAER",
    "MAINTENANCE MANUAL WITH",
    "ILLUSTRATED PARTS LIST",
    "EFFECTIVITY",
    "EFFECTIVITY ALL",
    "ALL",
}


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
    if re.search(r"MAINTENANCE\s+MANUAL\s+WITH\s+ILLUSTRATED\s+PARTS\s+LIST", compact, re.I):
        return "MAINTENANCE MANUAL WITH ILLUSTRATED PARTS LIST"
    if re.search(r"ILLUSTRATED\s+PARTS\s+(?:LIST|CATALOG|CATALOGUE)", compact, re.I):
        return "ILLUSTRATED PARTS LIST"
    if re.search(r"MAINTENANCE\s+MANUAL", compact, re.I):
        return "MAINTENANCE MANUAL"
    return None


def _find_document_code(lines: list[str], text: str) -> Optional[str]:
    # Prefer a line that is only the document code; otherwise use first match.
    for line in lines:
        match = _DOCUMENT_CODE_PATTERN.fullmatch(line.strip())
        if match:
            return match.group(1).upper()
    match = _DOCUMENT_CODE_PATTERN.search(text)
    return match.group(1).upper() if match else None


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


def _looks_like_non_title_line(line: str) -> bool:
    upper = line.upper()
    if _REGION_LABEL_PATTERN.match(line):
        return True
    if _DOCUMENT_CODE_PATTERN.search(line):
        return True
    if _ATA_PATTERN.search(line):
        return True
    if _PAGE_PATTERN.search(line):
        return True
    if _DATE_PATTERN.search(line):
        return True
    if upper.startswith("EFFECTIVITY"):
        return True
    if upper.startswith("FIGURE") or upper.startswith("FIG."):
        return True
    if "MAINTENANCE MANUAL" in upper or "ILLUSTRATED PARTS" in upper:
        return True
    if upper in _EXCLUDED_CALLOUTS:
        return True
    return False


def _find_effectivity(text: str) -> Optional[str]:
    match = _EFFECTIVITY_PATTERN.search(text)
    if not match:
        return None
    value = re.sub(r"\s+", " ", match.group(1)).strip(" .,:;|[]{}()")
    # Avoid accidentally swallowing the next field if OCR missed a newline.
    # Tesseract may read the ATA code as either 25-21-00 or 25-21 -00.
    split_patterns = [
        r"\bPage\b",
        r"\bFig(?:ure)?\b",
        r"\b[0-9]{2}\s*-\s*[0-9]{2}\s*-\s*[0-9]{2}\b",
        _DATE_PATTERN.pattern,
    ]
    for pattern in split_patterns:
        value = re.split(pattern, value, maxsplit=1, flags=re.I)[0]
    return value.strip(" .,:;|[]{}()") or None


def _find_page_number(text: str) -> Optional[int]:
    match = _PAGE_PATTERN.search(text)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _find_date(text: str) -> Optional[str]:
    match = _DATE_PATTERN.search(text)
    if not match:
        return None
    return re.sub(r"\s+", " ", match.group(1)).replace("Sept", "Sep").strip()


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
        # Keep one-word labels too because examples include ASHTRAY.
        if re.fullmatch(r"[A-Z][A-Z0-9&/ -]{2,40}", upper):
            callouts.append(upper)
            seen.add(upper)
    return callouts[:25]


def _document_type(manual_title: Optional[str], figure_number: Optional[str], ata_code: Optional[str]) -> Optional[str]:
    if manual_title and "PARTS" in manual_title:
        return "maintenance_manual_ipl"
    if manual_title:
        return "maintenance_manual"
    if figure_number and ata_code:
        return "manual_illustration_page"
    if ata_code:
        return "manual_page"
    return None


def _confidence(values: dict[str, object]) -> float:
    weights = {
        "document_type": 0.10,
        "manufacturer": 0.10,
        "manual_title": 0.20,
        "document_code": 0.15,
        "figure_title": 0.15,
        "figure_number": 0.10,
        "effectivity": 0.08,
        "ata_code": 0.08,
        "page_number": 0.02,
        "revision_date": 0.02,
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
    document_code = _find_document_code(lines, cleaned)
    figure_title, figure_number = _find_figure(lines, cleaned)
    effectivity = _find_effectivity(cleaned)
    ata_match = _ATA_PATTERN.search(cleaned)
    ata_code = ata_match.group(1) if ata_match else None
    page_number = _find_page_number(cleaned)
    revision_date = _find_date(cleaned)
    callouts = _find_callouts(lines)
    document_type = _document_type(manual_title, figure_number, ata_code)

    parsed = {
        "document_type": document_type,
        "manufacturer": manufacturer,
        "manual_title": manual_title,
        "document_code": document_code,
        "figure_title": figure_title,
        "figure_number": figure_number,
        "effectivity": effectivity,
        "ata_code": ata_code,
        "page_number": page_number,
        "revision_date": revision_date,
    }

    return ParsedManualMetadata(
        document_type=document_type,
        manufacturer=manufacturer,
        manual_title=manual_title,
        document_code=document_code,
        figure_title=figure_title,
        figure_number=figure_number,
        effectivity=effectivity,
        ata_code=ata_code,
        page_number=page_number,
        revision_date=revision_date,
        callouts=callouts,
        metadata_confidence=_confidence(parsed),
    )
