from tiff.manual_metadata_parser import parse_manual_page_text


SAMPLE_MANUAL_OCR = """
[top_strip]
-< EMBRAER
MAINTENANCE MANUAL WITH
ILLUSTRATED PARTS LIST

[bottom_strip]
120TP250002.MCE
Double Passenger Seat
Figure 2
EFFECTIVITY: ALL
25-21-00 _....
Sep 30/98

[right_strip]
ASHTRAY
120TP250002.MCE
Page 4
Sep 30/98
"""


def test_parse_manual_page_extracts_embraer_ipl_fields():
    parsed = parse_manual_page_text(SAMPLE_MANUAL_OCR)

    assert parsed.document_type == "maintenance_manual_ipl"
    assert parsed.manufacturer == "EMBRAER"
    assert parsed.manual_title == "MAINTENANCE MANUAL WITH ILLUSTRATED PARTS LIST"
    assert parsed.document_code == "120TP250002.MCE"
    assert parsed.figure_number == "2"
    assert parsed.figure_title == "Double Passenger Seat"
    assert parsed.effectivity == "ALL"
    assert parsed.ata_code == "25-21-00"
    assert parsed.page_number == 4
    assert parsed.revision_date == "Sep 30/98"
    assert "ASHTRAY" in parsed.callouts
    assert parsed.metadata_confidence >= 0.9


def test_parse_manual_page_returns_low_confidence_for_unrelated_text():
    parsed = parse_manual_page_text("random scanned text without known manual fields")

    assert parsed.document_type is None
    assert parsed.metadata_confidence == 0
