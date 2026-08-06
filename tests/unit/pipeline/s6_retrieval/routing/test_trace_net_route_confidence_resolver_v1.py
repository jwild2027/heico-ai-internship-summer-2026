import json
from pathlib import Path

from tiff.trace_net_route_confidence_resolver_v1 import build_route_confidence_resolver


def _scan_pack(path: Path):
    records = [
        {"page_id": "p1", "canonical_page_number": 1, "accepted_route": "table", "ocr_sample_text": "T.P. 120/1176 Passenger Seats Component Maintenance Manual Revision 4", "ocr_text_word_count": 12, "part_number_tokens": []},
        {"page_id": "p2", "canonical_page_number": 2, "accepted_route": "blank_candidate", "ocr_sample_text": "", "ocr_text_word_count": 0, "part_number_tokens": [], "ink_density": 0.0},
        {"page_id": "p3", "canonical_page_number": 3, "accepted_route": "table", "ocr_sample_text": "PART NUMBER ASSY NUMBER CH-SEC-UN-FIG 120-36833-001 120-36833-003 120-41824-001 120-41825-001", "ocr_text_word_count": 40, "part_number_tokens": ["120-36833-001", "120-36833-003", "120-41824-001", "120-41825-001"]},
        {"page_id": "p4", "canonical_page_number": 4, "accepted_route": "normal_text", "ocr_sample_text": "Description and Operation General The passenger seats are arranged into rows. Installation and removal procedures are described.", "ocr_text_word_count": 60, "part_number_tokens": []},
        {"page_id": "p5", "canonical_page_number": 5, "accepted_route": "image_visual", "ocr_sample_text": "SEAT BACKREST SEAT BELT ASHTRAY FLOATABLE SEAT BOTTOM Figure 1", "ocr_text_word_count": 25, "part_number_tokens": []},
        {"page_id": "p6", "canonical_page_number": 6, "accepted_route": "table", "ocr_sample_text": "Some uncertain text with figure and table", "ocr_text_word_count": 20, "part_number_tokens": []},
    ]
    path.write_text(json.dumps({"quality_status": "PASS", "records": records}), encoding="utf-8")


def _taxonomy(path: Path):
    labels = [
        "blank_candidate", "cover_or_title_page", "normal_text", "procedure_or_description", "table_or_index",
        "detailed_parts_list", "image_visual_diagram", "mixed_text_and_figure", "review_required",
    ]
    path.write_text(json.dumps({"quality_status": "PASS", "records": [{"label": x} for x in labels]}), encoding="utf-8")


def test_build_route_confidence_resolver_outputs_expected_routes(tmp_path):
    scan = tmp_path / "scan.json"
    taxonomy = tmp_path / "taxonomy.json"
    _scan_pack(scan)
    _taxonomy(taxonomy)
    out = tmp_path / "out"

    payload = build_route_confidence_resolver(
        scan_pack=scan,
        route_label_taxonomy=taxonomy,
        output_dir=out,
        quality=True,
    )

    assert payload["quality_status"] == "PASS"
    records = {r["page_id"]: r for r in payload["records"]}
    assert records["p1"]["primary_route"] == "cover_or_title_page"
    assert records["p2"]["primary_route"] == "blank_candidate"
    assert records["p3"]["primary_route"] == "detailed_parts_list"
    assert records["p4"]["primary_route"] == "procedure_or_description"
    assert records["p5"]["primary_route"] == "image_visual_diagram"
    assert records["p6"]["validator_required"] is True
    assert payload["summary"]["human_review_required_count"] == 0
    assert (out / "trace_net_route_confidence_resolver_v1.json").exists()
    assert (out / "trace_net_route_confidence_resolver_v1_records.csv").exists()


def test_ambiguous_pages_are_validator_gated_not_human_review(tmp_path):
    scan = tmp_path / "scan.json"
    scan.write_text(json.dumps({"quality_status": "PASS", "records": [
        {"page_id": "amb", "canonical_page_number": 7, "accepted_route": "table", "ocr_sample_text": "uncertain figure table item", "ocr_text_word_count": 4, "part_number_tokens": []}
    ]}), encoding="utf-8")
    out = tmp_path / "out"
    payload = build_route_confidence_resolver(scan_pack=scan, output_dir=out)
    record = payload["records"][0]
    assert record["validator_required"] is True
    assert payload["summary"]["human_review_required_count"] == 0
