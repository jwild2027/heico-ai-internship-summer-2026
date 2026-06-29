from tiff.trace_net_gold_label_review_workbook_v1 import _suggest_canonical_route, check_gold_label_review_workbook_quality, build_gold_label_review_workbook
import json
from pathlib import Path


def test_detailed_parts_list_wins_over_generic_figure_text():
    route, confidence, reasons = _suggest_canonical_route({
        "accepted_route": "table",
        "canonical_page_number": 101,
        "ocr_text_word_count": 260,
        "ocr_text_char_count": 1800,
        "ocr_sample_text": "FIG - ITEM PART NUMBER NOMENCLATURE UNITS PER ASSY Figure item detailed parts list",
        "part_number_tokens": [
            "120-36833-001", "120-36833-003", "120-36834-001", "120-41824-001",
            "120-41824-003", "120-41825-001", "120-42547-001", "120-45850-001",
        ],
    })
    assert route == "detailed_parts_list"
    assert confidence == "high"
    assert "detailed_parts_list_candidate" in reasons


def test_figure_reference_without_visual_labels_does_not_become_diagram():
    route, confidence, reasons = _suggest_canonical_route({
        "accepted_route": "table",
        "canonical_page_number": 21,
        "ocr_text_word_count": 237,
        "ocr_text_char_count": 1500,
        "ocr_sample_text": "Figure Parts List Content FIG ITEM Column PART NUMBER Column The purpose of this index is to provide a complete list",
        "part_number_tokens": [],
    })
    assert route in {"procedure_or_description", "table_or_index"}
    assert route != "image_visual_diagram"


def test_legacy_image_visual_with_limited_labels_stays_diagram():
    route, confidence, reasons = _suggest_canonical_route({
        "accepted_route": "image_visual",
        "canonical_page_number": 17,
        "ocr_text_word_count": 39,
        "ocr_text_char_count": 271,
        "ocr_sample_text": "SEAT BACKREST ASHTRAY SEAT BELT FLOATABLE SEAT BOTTOM Figure 1 Single Passenger Seat",
        "part_number_tokens": [],
    })
    assert route == "image_visual_diagram"
    assert confidence == "high"


def test_prose_with_visual_signal_becomes_mixed_not_table():
    route, confidence, reasons = _suggest_canonical_route({
        "accepted_route": "table",
        "canonical_page_number": 15,
        "ocr_text_word_count": 305,
        "ocr_text_char_count": 1900,
        "ocr_sample_text": "DESCRIPTION AND OPERATION 1. General The passenger seats are arranged into two rows. The Single Passenger Seat Figure 1 configurations listed below may be found.",
        "part_number_tokens": [],
    })
    assert route == "mixed_text_and_figure"
    assert confidence == "medium"


def test_quality_can_gate_overbroad_visual_suggestions(tmp_path: Path):
    taxonomy = tmp_path / "taxonomy.json"
    labels = [
        "blank_candidate", "cover_or_title_page", "normal_text", "procedure_or_description",
        "table_or_index", "detailed_parts_list", "image_visual_diagram", "mixed_text_and_figure", "review_required",
    ]
    taxonomy.write_text(json.dumps({"quality_status": "PASS", "records": [{"label": label} for label in labels]}), encoding="utf-8")
    scan = tmp_path / "scan.json"
    scan.write_text(json.dumps({
        "quality_status": "PASS",
        "records": [
            {"page_id": "p1", "canonical_page_number": 1, "accepted_route": "table", "ocr_text_word_count": 60, "ocr_text_char_count": 400, "ocr_sample_text": "PASSENGER SEATS COMPONENT MAINTENANCE MANUAL THIS PUBLICATION SUPERSEDES", "part_number_tokens": []},
            {"page_id": "p3", "canonical_page_number": 3, "accepted_route": "table", "ocr_text_word_count": 200, "ocr_text_char_count": 1200, "ocr_sample_text": "FIG ITEM PART NUMBER NOMENCLATURE UNITS PER ASSY Figure", "part_number_tokens": ["120-36833-001", "120-36833-003", "120-36834-001", "120-41824-001", "120-41824-003", "120-41825-001", "120-42547-001", "120-45850-001"]},
            {"page_id": "p17", "canonical_page_number": 17, "accepted_route": "image_visual", "ocr_text_word_count": 39, "ocr_text_char_count": 271, "ocr_sample_text": "SEAT BACKREST ASHTRAY Figure 1", "part_number_tokens": []},
        ],
    }), encoding="utf-8")
    payload = build_gold_label_review_workbook(scan_pack_path=scan, route_label_taxonomy_path=taxonomy, output_dir=tmp_path / "out")
    assert payload["summary"]["suggested_route_counts"]["image_visual_diagram"] == 1
    assert payload["summary"]["suggested_route_counts"]["detailed_parts_list"] == 1
    result = check_gold_label_review_workbook_quality(
        report_path=tmp_path / "out" / "trace_net_gold_label_review_workbook_v1.json",
        min_review_rows=3,
        min_route_labels=9,
        max_suggested_image_visual_diagram=1,
        min_suggested_detailed_parts_list=1,
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
        require_no_write_attempts=True,
        max_unsafe=0,
    )
    assert result["quality_status"] == "PASS"
