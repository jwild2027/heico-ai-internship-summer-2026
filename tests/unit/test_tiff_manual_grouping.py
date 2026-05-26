from tiff.manual_grouping import (
    build_single_manual_group,
    is_page_specific_code,
    normalize_publication_number,
)


def test_normalize_publication_number_variants():
    assert normalize_publication_number("T.P. 120/1176") == "T.P. 120/1176"
    assert normalize_publication_number("TP 120 / 1176") == "T.P. 120/1176"
    assert normalize_publication_number("T.-P. 120/1176 Jan 15/01") == "T.P. 120/1176"


def test_page_specific_code_detection():
    assert is_page_specific_code("120TP250083.MCE")
    assert is_page_specific_code("120CMM250085.MCE")
    assert is_page_specific_code("TP250007.MCE")
    assert not is_page_specific_code("T.P. 120/1176")


def test_build_single_manual_group_inherits_dominant_publication():
    rows = [
        {
            "file_id": "a",
            "source_path": "local_data/sample_tiffs/00000001.tif",
            "file_name": "00000001.tif",
            "detected_type": "manual_page",
            "document_code": "T.P. 120/1176",
            "manufacturer": "EMBRAER",
            "manual_title": "MAINTENANCE MANUAL WITH ILLUSTRATED PARTS LIST",
            "ata_code": "25-21-00",
        },
        {
            "file_id": "b",
            "source_path": "local_data/sample_tiffs/00000002.tif",
            "file_name": "00000002.tif",
            "detected_type": "blank_page",
            "document_code": None,
        },
        {
            "file_id": "c",
            "source_path": "local_data/sample_tiffs/00000010.tif",
            "file_name": "00000010.tif",
            "detected_type": "maintenance_manual_ipl",
            "document_code": "120TP250083.MCE",
            "page_number": 12,
        },
    ]

    group = build_single_manual_group(rows)
    assert group.manual_id == "t_p_120_1176"
    assert group.publication_number == "T.P. 120/1176"
    assert group.page_count == 3
    assert group.pages[1].publication_number == "T.P. 120/1176"
    assert group.pages[2].page_document_code == "120TP250083.MCE"
    assert group.pages[2].page_sequence == 3
