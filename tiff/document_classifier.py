"""Document-type classification for TIFF OCR results."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

from .manual_metadata_parser import ParsedManualMetadata
from .metadata_parser import ParsedDrawingMetadata


@dataclass(frozen=True)
class DocumentClassification:
    """A coarse document type and the signals used to choose it."""

    detected_type: str = "unknown"
    confidence: float = 0.0
    signals: list[str] = field(default_factory=list)

    @property
    def reasons(self) -> list[str]:
        """Backward-compatible alias for older tests/UI wording."""

        return self.signals

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def classify_document(
    *,
    drawing_metadata: Optional[ParsedDrawingMetadata] = None,
    manual_metadata: Optional[ParsedManualMetadata] = None,
    ocr_text: str = "",
) -> DocumentClassification:
    """Classify a TIFF page using parsed metadata and OCR text.

    This is intentionally simple and explainable. It should be expanded as more
    document families show up in the TIFF repository.
    """

    signals: list[str] = []
    upper_text = (ocr_text or "").upper()

    cleaned_text = (ocr_text or "").strip()
    manual_score = manual_metadata.metadata_confidence if manual_metadata else 0.0
    drawing_score = drawing_metadata.metadata_confidence if drawing_metadata else 0.0

    if not cleaned_text and manual_score == 0.0 and drawing_score == 0.0:
        return DocumentClassification(
            detected_type="blank_page",
            confidence=0.9,
            signals=["no_ocr_text"],
        )

    if manual_metadata:
        if manual_metadata.manual_title:
            signals.append("manual_title")
        if manual_metadata.figure_number:
            signals.append("figure_number")
        if manual_metadata.ata_code:
            signals.append("ata_code")
        if manual_metadata.document_code:
            signals.append("manual_document_code")
        if getattr(manual_metadata, "publication_number", None):
            signals.append("publication_number")
        if getattr(manual_metadata, "section_title", None):
            signals.append("section_title")
        if getattr(manual_metadata, "component_title", None):
            signals.append("component_title")
        if getattr(manual_metadata, "part_numbers", None):
            signals.append("part_numbers")

    if drawing_metadata:
        if drawing_metadata.drawing_number:
            signals.append("drawing_number")
        if drawing_metadata.part_number:
            signals.append("part_number")
        if drawing_metadata.revision:
            signals.append("revision")
        if drawing_metadata.sheet_number:
            signals.append("sheet_number")

    if "MAINTENANCE MANUAL" in upper_text:
        signals.append("ocr_contains_maintenance_manual")
        manual_score = max(manual_score, 0.45)
    if "ILLUSTRATED PARTS" in upper_text:
        signals.append("ocr_contains_illustrated_parts")
        manual_score = max(manual_score, 0.55)

    # Prefer the document family with stronger evidence. Manual/IPL pages often
    # have codes that look like drawing numbers, so require meaningful drawing
    # signals before calling something an engineering drawing.
    if manual_metadata and manual_metadata.document_type and manual_score >= max(0.35, drawing_score):
        return DocumentClassification(
            detected_type=manual_metadata.document_type,
            confidence=round(min(1.0, manual_score), 3),
            signals=signals,
        )

    if drawing_metadata and drawing_score >= 0.35:
        return DocumentClassification(
            detected_type="engineering_drawing",
            confidence=round(min(1.0, drawing_score), 3),
            signals=signals,
        )

    if ocr_text.strip():
        return DocumentClassification(
            detected_type="unclassified_ocr_page",
            confidence=0.15,
            signals=signals or ["ocr_text_present"],
        )

    return DocumentClassification(detected_type="unknown", confidence=0.0, signals=signals)


def classify_document_type(
    *,
    ocr_text: str,
    drawing_metadata: ParsedDrawingMetadata | None = None,
    manual_metadata: ParsedManualMetadata | None = None,
) -> DocumentClassification:
    """Backward-compatible wrapper around :func:`classify_document`."""

    return classify_document(
        ocr_text=ocr_text,
        drawing_metadata=drawing_metadata,
        manual_metadata=manual_metadata,
    )
