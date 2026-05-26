"""tools/heading_detectors.py — Pluggable heading detectors for any document type.

Each detector knows how to:
  1. Recognize whether a document fits its format (`matches`)
  2. Find every heading position in a chunk (`find_headings`)
  3. Extract the heading nearest the start of a chunk (`extract_title`)

The chunker auto-selects the best detector by sampling document text.
To support a new document type, add a subclass and register it in DETECTORS.

Usage:
    from tools.heading_detectors import select_detector
    detector = select_detector(text_sample)
    headings = detector.find_headings(chunk_text)   # [(position, title), ...]
    title = detector.extract_title(chunk_text)
"""
from __future__ import annotations

import re
from typing import Optional


class HeadingDetector:
    """Base class — generic fallback that finds no special headings."""
    name: str = "generic"

    def matches(self, text: str) -> bool:
        """Quick check — does this document type apply?"""
        return False

    def find_headings(self, text: str) -> list[tuple[int, str]]:
        """Return [(position, title), ...] for every heading found in text."""
        return []

    def extract_title(self, text: str) -> Optional[str]:
        """Extract the heading nearest the start of the text.
        Falls back to searching the tail of the text if nothing found at start.
        """
        # Search start of text first (most common case)
        headings = self.find_headings(text[:1500])
        if headings:
            return headings[0][1]
        # Fallback: search end of text — heading at end of chunk usually
        # marks the topic of subsequent content
        if len(text) > 1500:
            tail_headings = self.find_headings(text[-1500:])
            if tail_headings:
                return tail_headings[-1][1]
        return None


# ===========================================================================
# NIST Control Detector (800-53, 800-171, 800-82 etc.)
# ===========================================================================

class NISTControlDetector(HeadingDetector):
    """Detects NIST SP 800-series control headings like 'AC-2 ACCOUNT MANAGEMENT'.

    NIST control headings appear as:
        AC-2
        ACCOUNT MANAGEMENT
        Control:
        a. Define and document ...
    """
    name = "nist_control"

    # Heading regex — control ID on its own line, followed by ALL-CAPS title.
    # Permissive: doesn't require "Control:" to follow (catches Withdrawn controls etc.)
    HEADING_RE = re.compile(
        r'(?:^|\n)\s*([A-Z]{2}-\d+(?:\s*\(\d+\))?)\s*\n+'
        r'\s*([A-Z][A-Z][A-Z][A-Z\s,/()\-\|]{2,120}?)\s*(?=\n)',
        re.MULTILINE
    )

    def matches(self, text: str) -> bool:
        # Strong signal: explicit NIST SP citation + control ID pattern present
        has_nist_cite = bool(re.search(r'NIST\s+SP\s+800-\d+', text))
        has_control_pattern = bool(re.search(r'\b[A-Z]{2}-\d+\b.*\n.*[A-Z]{4}', text))
        return has_nist_cite and has_control_pattern

    def find_headings(self, text: str) -> list[tuple[int, str]]:
        results = []
        for match in self.HEADING_RE.finditer(text):
            position = match.start()
            control_id = match.group(1).replace(" ", "")
            control_name = re.sub(r'\s+', ' ', match.group(2)).strip()
            control_name = re.sub(r'\s+[A-Z]\.?$', '', control_name).strip()
            if len(control_name) < 3:
                continue
            title = f"{control_id} {control_name}"
            results.append((position, title))
        return results

    def extract_title(self, text: str) -> Optional[str]:
        # Search start of text first (most common case)
        headings = self.find_headings(text[:1500])
        if headings:
            return headings[0][1]
        # Fallback: search end of text. Many NIST control bodies are long
        # enough that the NEXT control's heading lands at the end of a chunk
        # rather than the start of the next chunk.
        if len(text) > 1500:
            tail_headings = self.find_headings(text[-1500:])
            if tail_headings:
                return tail_headings[-1][1]
        return None


# ===========================================================================
# Markdown Heading Detector
# ===========================================================================

class MarkdownHeadingDetector(HeadingDetector):
    """Detects markdown-style headings like '## 3.1 Methodology'."""
    name = "markdown"

    HEADING_RE = re.compile(r'^(#{1,6})\s+(.+?)\s*$', re.MULTILINE)

    def matches(self, text: str) -> bool:
        headings = self.HEADING_RE.findall(text)
        return len(headings) >= 5

    def find_headings(self, text: str) -> list[tuple[int, str]]:
        results = []
        for match in self.HEADING_RE.finditer(text):
            title = match.group(2).strip()
            if title:
                results.append((match.start(), title))
        return results


# ===========================================================================
# Numbered Section Detector
# ===========================================================================

class NumberedSectionDetector(HeadingDetector):
    """Detects strongly-numbered section headings like '3.1.2 Authentication'.

    Common in government, technical, and academic documents.
    """
    name = "numbered_section"

    HEADING_RE = re.compile(
        r'(?:^|\n)\s*(?:Section\s+)?'
        r'(\d+(?:\.\d+){1,3}\.?)\s+'
        r'([A-Z][A-Za-z][\w\s,/()\-:&]{3,100}?)\s*(?=\n)',
        re.MULTILINE
    )

    def matches(self, text: str) -> bool:
        headings = self.HEADING_RE.findall(text)
        return len(headings) >= 20

    def find_headings(self, text: str) -> list[tuple[int, str]]:
        results = []
        for match in self.HEADING_RE.finditer(text):
            number = match.group(1).rstrip('.')
            title_part = re.sub(r'\s+', ' ', match.group(2)).strip()
            if len(title_part) < 3:
                continue
            results.append((match.start(), f"{number} {title_part}"))
        return results


# ===========================================================================
# Legal Section Detector (contracts, regulations, statutes)
# ===========================================================================

class LegalSectionDetector(HeadingDetector):
    """Detects legal-style section headings like 'Section 4.2 Indemnification'
    or '§ 91.115 Right of Way' or 'ARTICLE V — Termination'."""
    name = "legal_section"

    HEADING_RE = re.compile(
        r'(?:^|\n)\s*'
        r'(?:Section|SECTION|Article|ARTICLE|§|Clause|CLAUSE)\s+'
        r'([\dIVXLC]+(?:\.\d+)*)\s*[.\-—]?\s*'
        r'([A-Z][A-Za-z][\w\s,/()\-:&]{3,100}?)\s*(?=\n)',
        re.MULTILINE
    )

    def matches(self, text: str) -> bool:
        return len(self.HEADING_RE.findall(text)) >= 5

    def find_headings(self, text: str) -> list[tuple[int, str]]:
        results = []
        for match in self.HEADING_RE.finditer(text):
            number = match.group(1)
            title_part = re.sub(r'\s+', ' ', match.group(2)).strip()
            results.append((match.start(), f"Section {number} {title_part}"))
        return results


# ===========================================================================
# Chapter Detector (manuals, books, handbooks)
# ===========================================================================

class ChapterDetector(HeadingDetector):
    """Detects chapter-style headings like 'Chapter 5 — Sponsons' or
    'CHAPTER 3: Risk Management'."""
    name = "chapter"

    HEADING_RE = re.compile(
        r'(?:^|\n)\s*'
        r'(?:Chapter|CHAPTER|Part|PART)\s+'
        r'(\d+|[IVXLC]+)\s*[.\-—:]?\s*'
        r'([A-Z][A-Za-z][\w\s,/()\-:&]{3,100}?)\s*(?=\n)',
        re.MULTILINE
    )

    def matches(self, text: str) -> bool:
        return len(self.HEADING_RE.findall(text)) >= 3

    def find_headings(self, text: str) -> list[tuple[int, str]]:
        results = []
        for match in self.HEADING_RE.finditer(text):
            number = match.group(1)
            title_part = re.sub(r'\s+', ' ', match.group(2)).strip()
            results.append((match.start(), f"Chapter {number} {title_part}"))
        return results


# ===========================================================================
# Registry — order matters (most specific first)
# ===========================================================================

DETECTORS: list[HeadingDetector] = [
    NISTControlDetector(),
    MarkdownHeadingDetector(),
    LegalSectionDetector(),
    NumberedSectionDetector(),
    ChapterDetector(),
]


def select_detector(text_sample: str) -> HeadingDetector:
    """Auto-select the best heading detector for a document.

    Tries each registered detector in order and returns the first match.
    Falls back to the generic detector (which finds no headings) if none match.
    """
    for detector in DETECTORS:
        try:
            if detector.matches(text_sample):
                return detector
        except Exception:
            continue
    return HeadingDetector()