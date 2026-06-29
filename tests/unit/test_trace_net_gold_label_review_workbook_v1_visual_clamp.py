from tiff.trace_net_gold_label_review_workbook_v1 import _suggest_canonical_route


def test_legacy_image_visual_still_maps_to_diagram():
    route, confidence, reasons = _suggest_canonical_route(
        {
            "accepted_route": "image_visual",
            "canonical_page_number": 17,
            "ocr_text_word_count": 43,
            "ocr_text_char_count": 250,
            "ocr_sample_text": "SEAT BACKRESTS SEAT BELT ASHTRAY FLOATABLE SEAT BOTTOM Figure 2",
            "part_number_tokens": [],
        }
    )
    assert route == "image_visual_diagram"
    assert confidence == "high"
    assert "legacy_image_visual_route" in reasons


def test_ipl_figure_reference_with_part_numbers_is_detailed_parts_not_diagram():
    route, confidence, reasons = _suggest_canonical_route(
        {
            "accepted_route": "table",
            "canonical_page_number": 250,
            "ocr_text_word_count": 95,
            "ocr_text_char_count": 800,
            "ocr_sample_text": "CH-SEC-UN-FIG ITEM ASSY NUMBER PART NUMBER NOMENCLATURE Figure 1002 Item 12",
            "part_number_tokens": ["120-29067-001", "120-29067-003", "120-29068-001"],
        }
    )
    assert route == "detailed_parts_list"
    assert "ipl_column_terms" in reasons


def test_sparse_figure_reference_without_concrete_visual_labels_does_not_become_diagram():
    route, confidence, reasons = _suggest_canonical_route(
        {
            "accepted_route": "table",
            "canonical_page_number": 301,
            "ocr_text_word_count": 70,
            "ocr_text_char_count": 500,
            "ocr_sample_text": "Figure 1003 Item Assy Number CH-SEC-UN-FIG",
            "part_number_tokens": [],
        }
    )
    assert route == "table_or_index"
    assert route != "image_visual_diagram"


def test_sparse_concrete_visual_label_can_be_diagram_without_legacy_route():
    route, confidence, reasons = _suggest_canonical_route(
        {
            "accepted_route": "normal_text",
            "canonical_page_number": 88,
            "ocr_text_word_count": 42,
            "ocr_text_char_count": 250,
            "ocr_sample_text": "SEAT BACKREST ASHTRAY SEAT BELT FLOATABLE SEAT BOTTOM Figure 1",
            "part_number_tokens": [],
        }
    )
    assert route == "image_visual_diagram"
    assert confidence == "medium"
    assert "concrete_visual_label_signal" in reasons
