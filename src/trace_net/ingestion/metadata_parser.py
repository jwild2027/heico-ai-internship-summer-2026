"""Parse drawing/header metadata from OCR text or filenames.

This parser is intentionally conservative. It extracts likely fields and a rough
confidence score, but the source TIFF remains the authority.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Optional


@dataclass(frozen=True)
class ParsedDrawingMetadata:
    drawing_number: Optional[str] = None
    document_number: Optional[str] = None
    part_number: Optional[str] = None
    revision: Optional[str] = None
    sheet_number: Optional[int] = None
    sheet_count: Optional[int] = None
    title: Optional[str] = None
    classification: Optional[str] = None
    metadata_confidence: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


_FIELD_PATTERNS = {
    "drawing_number": [
        re.compile(r"\b(?:DWG|DRWG|DRAWING)\s*(?:NO\.?|NUMBER|#)?\s*[:#-]?\s*([A-Z0-9][A-Z0-9._/-]{2,})\b", re.I),
        re.compile(r"\b(?:DOCUMENT|DOC)\b\s*(?:NO\.?|NUMBER|#)?\s*[:#-]?\s*([A-Z0-9][A-Z0-9._/-]{2,})\b", re.I),
    ],
    "part_number": [
        re.compile(r"\b(?:PART\s*(?:NO\.?|NUMBER|#)|P/N|PN)\s*[:#-]?\s*([A-Z0-9][A-Z0-9._/-]{2,})\b", re.I),
    ],
    "revision": [
        re.compile(r"\bREV(?:ISION)?\s*(?:LEVEL|NO\.?|#)?\s*[:#-]?\s*([A-Z0-9]{1,4})\b", re.I),
        re.compile(r"\bREV[._ -]?([A-Z0-9]{1,4})\b", re.I),
    ],
    "sheet": [
        re.compile(r"\bSHEET\s*([0-9]{1,4})\s*(?:OF|/)\s*([0-9]{1,4})\b", re.I),
        re.compile(r"\bSHT\s*([0-9]{1,4})\s*(?:OF|/)\s*([0-9]{1,4})\b", re.I),
    ],
    "title": [
        re.compile(r"\bTITLE\s*[:#-]?\s*([^\n\r|]{3,80})", re.I),
        re.compile(r"\bDESCRIPTION\s*[:#-]?\s*([^\n\r|]{3,80})", re.I),
    ],
}

_CLASSIFICATION_PATTERNS = [
    ("ITAR", re.compile(r"\bITAR\b|INTERNATIONAL\s+TRAFFIC\s+IN\s+ARMS", re.I)),
    ("CUI", re.compile(r"\bCUI\b|CONTROLLED\s+UNCLASSIFIED\s+INFORMATION", re.I)),
    ("EAR", re.compile(r"\bEAR\b|EXPORT\s+ADMINISTRATION\s+REGULATIONS", re.I)),
    ("CONFIDENTIAL", re.compile(r"\bCONFIDENTIAL\b|PROPRIETARY", re.I)),
    ("PUBLIC", re.compile(r"\bPUBLIC\b|APPROVED\s+FOR\s+PUBLIC\s+RELEASE", re.I)),
]

_BAD_REVISION_VALUES = {"HISTORY", "TABLE", "ZONE", "DATE", "DESC", "DESCRIPTION"}


def normalize_ocr_text(text: str) -> str:
    """Normalize common OCR/title-block separators while preserving words."""

    text = text.replace("\u2013", "-").replace("\u2014", "-")
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[\t ]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _first_match(patterns: list[re.Pattern[str]], text: str) -> Optional[str]:
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            value = match.group(1).strip(" .,:;|[]{}()")
            if value:
                return value.upper()
    return None


def _parse_sheet(text: str) -> tuple[Optional[int], Optional[int]]:
    for pattern in _FIELD_PATTERNS["sheet"]:
        match = pattern.search(text)
        if match:
            return int(match.group(1)), int(match.group(2))
    return None, None


def _parse_title(text: str) -> Optional[str]:
    for pattern in _FIELD_PATTERNS["title"]:
        match = pattern.search(text)
        if match:
            value = re.sub(r"\s+", " ", match.group(1)).strip(" .,:;|[]{}()")
            if value:
                return value[:80]
    return None


def _parse_classification(text: str) -> Optional[str]:
    for label, pattern in _CLASSIFICATION_PATTERNS:
        if pattern.search(text):
            return label
    return None


def _clean_revision(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    value = value.strip().upper()
    if value in _BAD_REVISION_VALUES:
        return None
    return value


def _confidence(parsed: dict[str, object]) -> float:
    """Rough confidence based on how many high-value fields were found."""

    weights = {
        "drawing_number": 0.25,
        "part_number": 0.20,
        "revision": 0.20,
        "sheet_number": 0.10,
        "sheet_count": 0.05,
        "title": 0.10,
        "classification": 0.10,
    }
    score = sum(weight for key, weight in weights.items() if parsed.get(key) not in (None, ""))
    return round(min(score, 1.0), 3)


def parse_title_block_text(text: str) -> ParsedDrawingMetadata:
    """Extract drawing metadata from OCR text or a file name string."""

    cleaned = normalize_ocr_text(text)
    drawing_number = _first_match(_FIELD_PATTERNS["drawing_number"], cleaned)
    part_number = _first_match(_FIELD_PATTERNS["part_number"], cleaned)
    revision = _clean_revision(_first_match(_FIELD_PATTERNS["revision"], cleaned))
    sheet_number, sheet_count = _parse_sheet(cleaned)
    title = _parse_title(cleaned)
    classification = _parse_classification(cleaned)

    parsed_dict: dict[str, object] = {
        "drawing_number": drawing_number,
        "document_number": drawing_number,
        "part_number": part_number,
        "revision": revision,
        "sheet_number": sheet_number,
        "sheet_count": sheet_count,
        "title": title,
        "classification": classification,
    }

    return ParsedDrawingMetadata(
        drawing_number=drawing_number,
        document_number=drawing_number,
        part_number=part_number,
        revision=revision,
        sheet_number=sheet_number,
        sheet_count=sheet_count,
        title=title,
        classification=classification,
        metadata_confidence=_confidence(parsed_dict),
    )
