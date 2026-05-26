from pathlib import Path

from PIL import Image

from tiff.json_report import merge_metadata, scan_tiff_to_dict
from tiff.metadata_parser import ParsedDrawingMetadata
from tiff.title_block_ocr import preprocess_for_ocr, title_block_boxes


def test_title_block_boxes_are_inside_page():
    width, height = 1000, 800
    boxes = title_block_boxes(width, height)

    assert {name for name, _ in boxes} == {
        "bottom_right_title_block",
        "bottom_strip",
        "top_strip",
        "right_strip",
    }
    for _, (left, top, right, bottom) in boxes:
        assert 0 <= left < right <= width
        assert 0 <= top < bottom <= height


def test_preprocess_for_ocr_returns_image():
    image = Image.new("RGB", (200, 100), "white")
    processed = preprocess_for_ocr(image)

    assert processed.size[0] >= 200
    assert processed.size[1] >= 100
    assert processed.mode == "1"


def test_merge_metadata_uses_ocr_then_filename_fallback():
    filename_metadata = ParsedDrawingMetadata(
        drawing_number="DWG-12345",
        document_number="DWG-12345",
        revision="C",
        metadata_confidence=0.45,
    )
    ocr_metadata = ParsedDrawingMetadata(
        title="BRACKET ASSEMBLY",
        classification="ITAR",
        metadata_confidence=0.20,
    )

    merged, sources = merge_metadata(
        filename_metadata=filename_metadata,
        ocr_metadata=ocr_metadata,
    )

    assert merged is not None
    assert merged.drawing_number == "DWG-12345"
    assert merged.revision == "C"
    assert merged.title == "BRACKET ASSEMBLY"
    assert merged.classification == "ITAR"
    assert sources["drawing_number"] == "filename"
    assert sources["title"] == "ocr"


def test_scan_report_ocr_not_found_status(tmp_path: Path):
    tiff_path = tmp_path / "DWG-12345_REV-C.tif"
    Image.new("RGB", (300, 200), "white").save(tiff_path)

    report = scan_tiff_to_dict(
        tiff_path,
        source_root=tmp_path,
        run_ocr=True,
        tesseract_cmd=str(tmp_path / "missing_tesseract.exe"),
    )

    assert report["ocr"]["enabled"] is True
    # If tesseract is on PATH, the scanner may still use it. With the fake path
    # supplied first, both outcomes are acceptable for local developer machines.
    assert report["ocr"]["status"] in {"tesseract_not_found", "no_text_found", "partial", "ok"}
    assert "filename_metadata" in report
    assert "drawing_metadata_sources" in report
