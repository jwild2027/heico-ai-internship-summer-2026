from pathlib import Path

from tiff.trace_net_table_crop_selection_diagnostics_v1 import build_report


def test_build_crop_selection_diagnostics_counts(tmp_path: Path):
    tlg = tmp_path / "tlg.json"
    bbox = tmp_path / "bbox.json"
    ocr = tmp_path / "ocr.json"
    tlg.write_text('''{
      "quality_status":"PASS",
      "table_geometry_cards":[
        {"page_id":"p1","table_id":"t1","table_type":"parts_list_table","selected_morphology_scope":"table_region_crop","table_region_crop_available":true,"table_region_crop_applied":true,"horizontal_line_count":4,"vertical_line_count":2,"intersection_count":8,"morphology_signal_strength":"GRID","morphology_quality_score":22,"geometry_confidence":0.9,"review_required":false,"review_flags":[]},
        {"page_id":"p2","table_id":"t2","table_type":"list_of_effective_pages","selected_morphology_scope":"page","table_region_crop_available":true,"table_region_crop_applied":true,"horizontal_line_count":1,"vertical_line_count":0,"intersection_count":0,"morphology_signal_strength":"WEAK_LINE_SIGNAL","morphology_quality_score":1,"geometry_confidence":0.6,"review_required":true,"review_flags":["no_vertical_lines_detected"]}
      ]
    }''', encoding="utf-8")
    bbox.write_text('''{"quality_status":"PASS","table_bbox_cards":[
      {"page_id":"p1","table_id":"t1","bbox_source":"explicit_table_bbox","bbox_confidence":0.95,"bbox_coverage_ratio":0.25,"review_required":false},
      {"page_id":"p2","table_id":"t2","bbox_source":"ocr_table_text_token_match","bbox_confidence":0.83,"bbox_coverage_ratio":0.86,"review_required":true}
    ]}''', encoding="utf-8")
    ocr.write_text('''{"quality_status":"PASS","table_ocr_bbox_enrichment_cards":[
      {"page_id":"p1","table_id":"t1","bbox_source":"ocr_part_number_token_match","bbox_confidence":0.92,"bbox_coverage_ratio":0.3,"matched_ocr_bbox_count":20,"part_number_ocr_match_count":10},
      {"page_id":"p2","table_id":"t2","bbox_source":"ocr_table_text_token_match","bbox_confidence":0.83,"bbox_coverage_ratio":0.86,"matched_ocr_bbox_count":30,"part_number_ocr_match_count":0}
    ]}''', encoding="utf-8")

    report = build_report(
        table_line_geometry_path=tlg,
        table_bbox_resolver_path=bbox,
        table_ocr_bbox_enrichment_path=ocr,
        thresholds={
            "min_diagnostic_cards": 2,
            "min_crop_selected_cards": 1,
            "min_page_selected_cards": 1,
            "max_unsafe_diagnostic_cards": 0,
            "max_answer_permission_count": 0,
            "max_source_truth_mutation_allowed": 0,
            "require_table_line_geometry_quality_pass": True,
            "require_table_bbox_resolver_quality_pass": True,
            "require_table_ocr_bbox_enrichment_quality_pass": True,
            "require_no_answer_permission": True,
        },
    )
    summary = report["summary"]
    assert report["quality_status"] == "PASS"
    assert summary["diagnostic_card_count"] == 2
    assert summary["crop_selected_card_count"] == 1
    assert summary["page_selected_card_count"] == 1
    assert summary["broad_bbox_candidate_card_count"] == 1
    assert summary["unsafe_diagnostic_card_count"] == 0
    assert report["diagnostic_cards"][0]["can_answer_directly"] is False


def test_quality_fails_when_crop_selected_threshold_not_met(tmp_path: Path):
    tlg = tmp_path / "tlg.json"
    tlg.write_text('''{"quality_status":"PASS","table_geometry_cards":[
      {"page_id":"p1","table_id":"t1","selected_morphology_scope":"page","table_region_crop_available":true,"table_region_crop_applied":true}
    ]}''', encoding="utf-8")
    report = build_report(
        table_line_geometry_path=tlg,
        table_bbox_resolver_path=None,
        table_ocr_bbox_enrichment_path=None,
        thresholds={
            "min_diagnostic_cards": 1,
            "min_crop_selected_cards": 1,
            "min_page_selected_cards": 0,
            "max_unsafe_diagnostic_cards": 0,
            "max_answer_permission_count": 0,
            "max_source_truth_mutation_allowed": 0,
            "require_table_line_geometry_quality_pass": True,
            "require_table_bbox_resolver_quality_pass": False,
            "require_table_ocr_bbox_enrichment_quality_pass": False,
            "require_no_answer_permission": True,
        },
    )
    assert report["quality_status"] == "FAIL"
    assert "min_crop_selected_cards_not_met" in report["summary"]["quality_fail_reasons"]
