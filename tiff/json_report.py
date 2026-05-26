"""Create JSON scan reports for single TIFF files.

This module is local-only. It uses the TIFF inventory scanner, optional local
Tesseract OCR, drawing metadata parsing, manual/IPL metadata parsing, and a
simple document-type classifier to create a JSON-ready scan result.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .document_classifier import DocumentClassification, classify_document
from .inventory import build_tiff_inventory_record
from .manual_metadata_parser import ParsedManualMetadata, parse_manual_page_text
from .metadata_parser import ParsedDrawingMetadata, parse_title_block_text
from .title_block_ocr import TitleBlockOCRResult, run_title_block_ocr


SCHEMA_VERSION = "tiff_scan_report.v3"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _filename_to_parse_text(path: Path) -> str:
    """Turn common drawing-style filenames into parser-friendly text.

    Example: DWG-12345_REV-C_SHEET-1-OF-2.tif
    becomes: DWG-12345 REV C SHEET 1 OF 2
    """

    stem = path.stem
    text = stem.replace("_", " ")
    text = re.sub(r"\bREV[-. ]?([A-Za-z0-9]{1,4})\b", r"REV \1", text, flags=re.I)
    text = re.sub(
        r"\b(?:SHEET|SHT)[-. ]?([0-9]{1,4})[-. ]?(?:OF)?[-. ]?([0-9]{1,4})\b",
        r"SHEET \1 OF \2",
        text,
        flags=re.I,
    )
    return text


def _json_default(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _drawing_metadata_to_dict(value: ParsedDrawingMetadata | None) -> dict[str, object] | None:
    return value.to_dict() if value is not None else None


def _manual_metadata_to_dict(value: ParsedManualMetadata | None) -> dict[str, object] | None:
    return value.to_dict() if value is not None else None


def _classification_to_dict(value: DocumentClassification | None) -> dict[str, object] | None:
    return value.to_dict() if value is not None else None


def _not_blank(value: object) -> bool:
    return value is not None and value != ""


def merge_metadata(
    *,
    filename_metadata: ParsedDrawingMetadata | None,
    ocr_metadata: ParsedDrawingMetadata | None,
) -> tuple[ParsedDrawingMetadata | None, dict[str, str]]:
    """Merge OCR drawing metadata with filename drawing metadata.

    OCR usually has better title-block fields, but filenames often preserve the
    drawing number or revision when OCR is noisy. This merges field-by-field:
    OCR wins when it found a value; filename fills the gaps.
    """

    if filename_metadata is None and ocr_metadata is None:
        return None, {}

    sources: dict[str, str] = {}
    fields = [
        "drawing_number",
        "document_number",
        "part_number",
        "revision",
        "sheet_number",
        "sheet_count",
        "title",
        "classification",
    ]
    values: dict[str, object] = {}
    filename_dict = filename_metadata.to_dict() if filename_metadata else {}
    ocr_dict = ocr_metadata.to_dict() if ocr_metadata else {}

    for field in fields:
        ocr_value = ocr_dict.get(field)
        filename_value = filename_dict.get(field)
        if _not_blank(ocr_value):
            values[field] = ocr_value
            sources[field] = "ocr"
        elif _not_blank(filename_value):
            values[field] = filename_value
            sources[field] = "filename"
        else:
            values[field] = None
            sources[field] = "none"

    confidence = max(
        filename_metadata.metadata_confidence if filename_metadata else 0.0,
        ocr_metadata.metadata_confidence if ocr_metadata else 0.0,
    )
    if filename_metadata and ocr_metadata:
        confidence = min(1.0, confidence + 0.05)

    merged = ParsedDrawingMetadata(
        drawing_number=values["drawing_number"],
        document_number=values["document_number"],
        part_number=values["part_number"],
        revision=values["revision"],
        sheet_number=values["sheet_number"],
        sheet_count=values["sheet_count"],
        title=values["title"],
        classification=values["classification"],
        metadata_confidence=round(confidence, 3),
    )
    return merged, sources


def scan_tiff_to_dict(
    tiff_path: str | Path,
    *,
    source_root: str | Path | None = None,
    hash_file: bool = True,
    parse_filename: bool = True,
    run_ocr: bool = False,
    ocr_page_index: int = 0,
    ocr_lang: str = "eng",
    tesseract_cmd: str | None = None,
) -> dict[str, Any]:
    """Scan one TIFF and return a JSON-ready dictionary.

    Args:
        tiff_path: Path to a .tif or .tiff file.
        source_root: Optional root used to calculate relative_path.
        hash_file: Calculate SHA-256. For very large files, disable for speed.
        parse_filename: Run first-pass drawing metadata extraction from filename.
        run_ocr: Run local Tesseract on likely title-block/header regions.
        ocr_page_index: Zero-based page index for OCR.
        ocr_lang: Tesseract language code, usually ``eng``.
        tesseract_cmd: Optional explicit path to tesseract.exe.

    Returns:
        A JSON-ready dictionary suitable for saving or returning from an API.
    """

    path = Path(tiff_path)
    root = Path(source_root) if source_root is not None else path.parent

    inventory = build_tiff_inventory_record(path, source_root=root, hash_file=hash_file)
    filename_metadata = parse_title_block_text(_filename_to_parse_text(path)) if parse_filename else None

    ocr_result: TitleBlockOCRResult | None = None
    ocr_drawing_metadata: ParsedDrawingMetadata | None = None
    manual_metadata: ParsedManualMetadata | None = None
    classification: DocumentClassification | None = None
    ocr_text = ""

    if run_ocr:
        ocr_result = run_title_block_ocr(
            path,
            page_index=ocr_page_index,
            lang=ocr_lang,
            tesseract_cmd=tesseract_cmd,
        )
        ocr_text = ocr_result.combined_text or ""
        if ocr_text:
            ocr_drawing_metadata = parse_title_block_text(ocr_text)
            manual_metadata = parse_manual_page_text(ocr_text)

    merged_drawing_metadata, field_sources = merge_metadata(
        filename_metadata=filename_metadata,
        ocr_metadata=ocr_drawing_metadata,
    )

    # Classify from OCR text when available; otherwise use filename text as a weak hint.
    classifier_text = ocr_text or _filename_to_parse_text(path)
    classification = classify_document(
        ocr_text=classifier_text,
        drawing_metadata=merged_drawing_metadata,
        manual_metadata=manual_metadata,
    )

    ocr_report: dict[str, object]
    if ocr_result is None:
        ocr_report = {
            "enabled": False,
            "status": "not_run",
            "note": "OCR was not run. Enable OCR to read the drawing header/title block or manual footer.",
        }
    else:
        ocr_report = ocr_result.to_dict()
        ocr_report["parsed_drawing_metadata"] = _drawing_metadata_to_dict(ocr_drawing_metadata)
        ocr_report["parsed_manual_metadata"] = _manual_metadata_to_dict(manual_metadata)
        # Keep the old key for backward compatibility with the first OCR patch.
        ocr_report["parsed_metadata"] = _drawing_metadata_to_dict(ocr_drawing_metadata)

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "scan_status": "ok" if inventory.error is None else "warning",
        "source": {
            "type": "single_tiff_upload_or_file",
            "path": inventory.source_path,
            "relative_path": inventory.relative_path,
        },
        "file": {
            "file_name": inventory.file_name,
            "extension": inventory.extension,
            "file_size_bytes": inventory.file_size_bytes,
            "modified_time_utc": inventory.modified_time_utc,
            "sha256": inventory.sha256,
        },
        "tiff": {
            "page_count": inventory.page_count,
            "width_px": inventory.width_px,
            "height_px": inventory.height_px,
            "dpi_x": inventory.dpi_x,
            "dpi_y": inventory.dpi_y,
            "color_mode": inventory.color_mode,
            "compression": inventory.compression,
            "read_error": inventory.error,
        },
        "document_classification": _classification_to_dict(classification),
        "drawing_metadata": _drawing_metadata_to_dict(merged_drawing_metadata),
        "drawing_metadata_sources": field_sources,
        "manual_metadata": _manual_metadata_to_dict(manual_metadata),
        "filename_metadata": _drawing_metadata_to_dict(filename_metadata),
        "ocr": ocr_report,
    }


def write_scan_json(report: dict[str, Any], output_path: str | Path) -> Path:
    """Write a scan report dictionary to JSON."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, indent=2, sort_keys=False, default=_json_default),
        encoding="utf-8",
    )
    return path


def scan_tiff_to_json_file(
    tiff_path: str | Path,
    output_path: str | Path,
    *,
    source_root: str | Path | None = None,
    hash_file: bool = True,
    parse_filename: bool = True,
    run_ocr: bool = False,
    ocr_page_index: int = 0,
    ocr_lang: str = "eng",
    tesseract_cmd: str | None = None,
) -> Path:
    """Scan one TIFF and write the result to output_path."""

    report = scan_tiff_to_dict(
        tiff_path,
        source_root=source_root,
        hash_file=hash_file,
        parse_filename=parse_filename,
        run_ocr=run_ocr,
        ocr_page_index=ocr_page_index,
        ocr_lang=ocr_lang,
        tesseract_cmd=tesseract_cmd,
    )
    return write_scan_json(report, output_path)
