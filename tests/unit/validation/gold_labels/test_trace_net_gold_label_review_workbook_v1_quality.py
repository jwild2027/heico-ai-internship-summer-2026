import json
from pathlib import Path

from tiff.trace_net_gold_label_review_workbook_v1 import check_gold_label_review_workbook_quality, build_gold_label_review_workbook


def _write_inputs(tmp_path: Path):
    scan = tmp_path / "scan.json"
    taxonomy = tmp_path / "taxonomy.json"
    scan.write_text(json.dumps({
        "quality_status": "PASS",
        "records": [
            {"page_id": "p1", "canonical_page_number": 1, "accepted_route": "table", "ocr_text_word_count": 50, "ocr_text_char_count": 300, "ocr_sample_text": "PASSENGER SEATS COMPONENT MAINTENANCE MANUAL THIS PUBLICATION SUPERSEDES", "part_number_tokens": []},
            {"page_id": "p2", "canonical_page_number": 2, "accepted_route": "blank_candidate", "ocr_text_word_count": 0, "ocr_text_char_count": 0, "ocr_sample_text": "", "part_number_tokens": []},
            {"page_id": "p3", "canonical_page_number": 3, "accepted_route": "table", "ocr_text_word_count": 100, "ocr_text_char_count": 900, "ocr_sample_text": "PART NUMBER NOMENCLATURE UNITS PER ASSY", "part_number_tokens": ["120-36833-001", "120-36833-003", "120-36834-001"]},
        ],
    }), encoding="utf-8")
    taxonomy.write_text(json.dumps({
        "quality_status": "PASS",
        "records": [{"label": label, "display_name": label, "family": "test", "definition": "", "default_processor_contract": "", "review_policy": ""} for label in [
            "blank_candidate", "cover_or_title_page", "normal_text", "procedure_or_description", "table_or_index", "detailed_parts_list", "image_visual_diagram", "mixed_text_and_figure", "review_required"
        ]],
    }), encoding="utf-8")
    return scan, taxonomy


def test_quality_check_passes_with_review_columns(tmp_path):
    scan, taxonomy = _write_inputs(tmp_path)
    build_gold_label_review_workbook(scan_pack_path=scan, route_label_taxonomy_path=taxonomy, output_dir=tmp_path / "out")
    result = check_gold_label_review_workbook_quality(
        report_path=tmp_path / "out" / "trace_net_gold_label_review_workbook_v1.json",
        min_review_rows=3,
        min_route_labels=9,
        require_source_scan_pack_quality_pass=True,
        require_taxonomy_quality_pass=True,
        require_workbook=True,
        require_review_columns=True,
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
        require_no_write_attempts=True,
        max_unsafe=0,
    )
    assert result["quality_status"] == "PASS"
    assert result["failures"] == []
