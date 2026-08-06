from tiff.document_classifier import classify_document, classify_document_type
from tiff.manual_metadata_parser import parse_manual_page_text
from tiff.metadata_parser import parse_title_block_text


MANUAL_TEXT = """
EMBRAER
MAINTENANCE MANUAL WITH ILLUSTRATED PARTS LIST
120TP250002.MCE
Double Passenger Seat
Figure 2
EFFECTIVITY: ALL
25-21-00
Page 4
Sep 30/98
"""


def test_classify_manual_ipl_page():
    manual = parse_manual_page_text(MANUAL_TEXT)
    drawing = parse_title_block_text(MANUAL_TEXT)

    classification = classify_document(
        ocr_text=MANUAL_TEXT,
        drawing_metadata=drawing,
        manual_metadata=manual,
    )

    assert classification.detected_type == "maintenance_manual_ipl"
    assert classification.confidence >= 0.7
    assert "ocr_contains_maintenance_manual" in classification.signals


def test_classify_document_type_alias():
    manual = parse_manual_page_text(MANUAL_TEXT)
    classification = classify_document_type(ocr_text=MANUAL_TEXT, manual_metadata=manual)

    assert classification.detected_type == "maintenance_manual_ipl"


def test_classify_engineering_drawing_title_block():
    text = """
    DRAWING NO: DWG-12345
    PART NO: 77821-001
    REV: C
    SHEET 1 OF 3
    TITLE: BRACKET ASSEMBLY
    """
    drawing = parse_title_block_text(text)

    classification = classify_document(ocr_text=text, drawing_metadata=drawing)

    assert classification.detected_type == "engineering_drawing"
    assert classification.confidence >= 0.5
