from tiff.document_classifier import classify_document
from tiff.manual_metadata_parser import parse_manual_page_text


def _classify(text: str):
    manual = parse_manual_page_text(text)
    return manual, classify_document(ocr_text=text, manual_metadata=manual)


def test_parse_component_manual_cover_page():
    text = """
    T.P. 120/1176
    PASSENGER SEATS
    COMPONENT MAINTENANCE MANUAL
    WITH
    ILLUSTRATED PARTS LIST
    25-21-00
    30 SEPTEMBER 1998
    REVISION 4 - 10 APRIL 2006
    EMBRAER
    """

    manual, classification = _classify(text)

    assert classification.detected_type == "manual_cover_page"
    assert manual.document_code == "T.P. 120/1176"
    assert manual.publication_number == "T.P. 120/1176"
    assert manual.component_title == "PASSENGER SEATS"
    assert manual.ata_code == "25-21-00"
    assert manual.issue_date == "30 September 1998"
    assert manual.revision_label == "REVISION 4 - 10 APRIL 2006"


def test_parse_manual_applicability_page():
    text = """
    EMBRAER
    MAINTENANCE MANUAL WITH
    ILLUSTRATED PARTS LIST
    APPLICABILITY
    This publication covers the following part numbers:
    120-36833-001 120-36833-003 120-61549-503
    EFFECTIVITY: ALL
    25-APPLICABILITY
    Page i/ii
    T.P. 120/1176 Jan 15/01
    """

    manual, classification = _classify(text)

    assert classification.detected_type == "manual_applicability_page"
    assert manual.section_title == "APPLICABILITY"
    assert manual.document_code == "T.P. 120/1176"
    assert manual.publication_number == "T.P. 120/1176"
    assert manual.page_label == "i/ii"
    assert manual.revision_date == "Jan 15/01"
    assert "120-36833-001" in manual.part_numbers
    assert "120-61549-503" in manual.part_numbers


def test_parse_manual_introduction_page():
    text = """
    EMBRAER
    MAINTENANCE MANUAL WITH
    ILLUSTRATED PARTS LIST
    INTRODUCTION
    EFFECTIVITY: ALL
    25-INTRODUCTION
    Page 1/2
    T.P. 120/1176 Sep 30/98
    """

    manual, classification = _classify(text)

    assert classification.detected_type == "manual_introduction_page"
    assert manual.section_title == "INTRODUCTION"
    assert manual.page_label == "1/2"
    assert manual.page_number == 1
    assert manual.revision_date == "Sep 30/98"


def test_parse_list_of_effective_pages():
    text = """
    EMBRAER
    MAINTENANCE MANUAL WITH
    ILLUSTRATED PARTS LIST
    CHAPTER SECTION SUBJECT PAGE DATE
    25 - Title - Apr 10/06
    25 - Introduction 1 Sep 30/98
    25-LIST OF EFFECTIVE PAGES
    Page 1
    T.P. 120/1176 Apr 10/06
    """

    manual, classification = _classify(text)

    assert classification.detected_type == "manual_list_of_effective_pages"
    assert manual.section_title == "LIST OF EFFECTIVE PAGES"
    assert manual.document_code == "T.P. 120/1176"
    assert manual.page_number == 1
    assert manual.revision_date == "Apr 10/06"


def test_blank_ocr_classifies_blank_page():
    classification = classify_document(ocr_text="")
    assert classification.detected_type == "blank_page"
