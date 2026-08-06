from __future__ import annotations

from tiff.metadata_parser import parse_title_block_text


def test_parse_basic_title_block_fields():
    text = """
    ITAR CONTROLLED
    DRAWING NO: DWG-12345
    PART NO: 77821-001
    REV: C
    SHEET 1 OF 3
    TITLE: BRACKET ASSEMBLY
    """

    parsed = parse_title_block_text(text)

    assert parsed.classification == "ITAR"
    assert parsed.drawing_number == "DWG-12345"
    assert parsed.document_number == "DWG-12345"
    assert parsed.part_number == "77821-001"
    assert parsed.revision == "C"
    assert parsed.sheet_number == 1
    assert parsed.sheet_count == 3
    assert parsed.title == "BRACKET ASSEMBLY"
    assert parsed.metadata_confidence >= 0.9


def test_parse_cui_and_document_number():
    text = "CUI DOCUMENT NUMBER ABC-9000 REVISION 02 SHEET 2/4 DESCRIPTION: TEST PROCEDURE"
    parsed = parse_title_block_text(text)

    assert parsed.classification == "CUI"
    assert parsed.drawing_number == "ABC-9000"
    assert parsed.revision == "02"
    assert parsed.sheet_number == 2
    assert parsed.sheet_count == 4
    assert parsed.title == "TEST PROCEDURE"


def test_revision_history_is_not_revision_value():
    text = "REVISION HISTORY TABLE\nDRAWING NO A-1000\nSHEET 1 OF 1"
    parsed = parse_title_block_text(text)

    assert parsed.revision is None
    assert parsed.drawing_number == "A-1000"
