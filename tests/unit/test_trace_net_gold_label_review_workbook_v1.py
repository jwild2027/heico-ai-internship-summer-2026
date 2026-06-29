import json
from pathlib import Path

from tiff.trace_net_gold_label_review_workbook_v1 import build_gold_label_review_workbook


def _write_inputs(tmp_path: Path):
    scan = tmp_path / "scan.json"
    taxonomy = tmp_path / "taxonomy.json"
    scan.write_text(json.dumps({
        "quality_status": "PASS",
        "summary": {"source_package": "metadata.zip"},
        "records": [
            {"page_id": "p1", "canonical_page_number": 1, "source_member": "00000001.tif", "accepted_route": "table", "ocr_text_word_count": 60, "ocr_text_char_count": 400, "ocr_sample_text": "PASSENGER SEATS COMPONENT MAINTENANCE MANUAL WITH ILLUSTRATED PARTS LIST THIS PUBLICATION SUPERSEDES", "part_number_tokens": [], "route_reasons": ["table_or_parts_list_text_cues"], "source_image_sha256": "abc"},
            {"page_id": "p17", "canonical_page_number": 17, "source_member": "00000017.tif", "accepted_route": "image_visual", "ocr_text_word_count": 39, "ocr_text_char_count": 271, "ocr_sample_text": "SEAT BACKREST ASHTRAY SEAT BELT Figure 1", "part_number_tokens": [], "route_reasons": ["visual_keywords_with_limited_text"], "source_image_sha256": "def"},
            {"page_id": "p35", "canonical_page_number": 35, "source_member": "00000035.tif", "accepted_route": "blank_candidate", "ocr_text_word_count": 0, "ocr_text_char_count": 0, "ocr_sample_text": "", "part_number_tokens": [], "route_reasons": ["empty_ocr_low_ink"], "source_image_sha256": "ghi"},
        ],
    }), encoding="utf-8")
    taxonomy.write_text(json.dumps({
        "quality_status": "PASS",
        "records": [{"label": label, "display_name": label, "family": "test", "definition": "", "default_processor_contract": "", "review_policy": ""} for label in [
            "blank_candidate", "cover_or_title_page", "normal_text", "procedure_or_description", "table_or_index", "detailed_parts_list", "image_visual_diagram", "mixed_text_and_figure", "review_required"
        ]],
    }), encoding="utf-8")
    return scan, taxonomy


def test_build_gold_label_review_workbook_outputs(tmp_path):
    scan, taxonomy = _write_inputs(tmp_path)
    payload = build_gold_label_review_workbook(
        scan_pack_path=scan,
        route_label_taxonomy_path=taxonomy,
        output_dir=tmp_path / "out",
        quality=True,
    )
    assert payload["quality_status"] == "PASS"
    assert len(payload["records"]) == 3
    assert (tmp_path / "out" / "trace_net_gold_label_review_workbook_v1.xlsx").exists()
    assert (tmp_path / "out" / "trace_net_gold_label_review_workbook_v1.csv").exists()
    assert payload["records"][0]["suggested_canonical_route"] == "cover_or_title_page"
    assert payload["records"][1]["suggested_canonical_route"] == "image_visual_diagram"
    assert payload["records"][2]["suggested_canonical_route"] == "blank_candidate"
    assert "gold_route_label" in payload["review_columns"]
