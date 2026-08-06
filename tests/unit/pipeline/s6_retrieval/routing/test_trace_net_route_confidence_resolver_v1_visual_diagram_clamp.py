import json
from pathlib import Path

from tiff.trace_net_route_confidence_resolver_v1 import build_route_confidence_resolver, check_quality


def test_generic_ipl_figure_terms_do_not_create_visual_diagram_route(tmp_path):
    scan = tmp_path / "scan.json"
    scan.write_text(json.dumps({"quality_status": "PASS", "records": [
        {
            "page_id": "ipl_table_with_fig_item_terms",
            "canonical_page_number": 120,
            "accepted_route": "table",
            "ocr_sample_text": (
                "CH-SEC-UN-FIG ITEM ASSY NUMBER ITEM ASSY NUMBER FIG ITEM "
                "25-21-00 120-29067-001 120-29068-001 PARTS LIST "
                "ITEM ASSY NUMBER CH-SEC-UN-FIG"
            ),
            "ocr_text_word_count": 95,
            "part_number_tokens": ["120-29067-001", "120-29068-001"],
        },
        {
            "page_id": "real_legacy_visual",
            "canonical_page_number": 17,
            "accepted_route": "image_visual",
            "ocr_sample_text": "Figure Passenger Seat seat backrest seat belt ashtray",
            "ocr_text_word_count": 42,
            "part_number_tokens": [],
        },
    ]}), encoding="utf-8")

    payload = build_route_confidence_resolver(scan_pack=scan, output_dir=tmp_path / "out", quality=True)
    records = {r["page_id"]: r for r in payload["records"]}

    ipl = records["ipl_table_with_fig_item_terms"]
    assert ipl["primary_route"] != "image_visual_diagram"
    assert ipl["signal_counts"]["ipl_visual_blocker"] is True
    assert ipl["route_scores"].get("image_visual_diagram", 0) == 0

    visual = records["real_legacy_visual"]
    assert visual["primary_route"] == "image_visual_diagram"
    assert visual["auto_resolved"] is True


def test_quality_can_gate_image_visual_route_count(tmp_path):
    report = tmp_path / "report.json"
    report.write_text(json.dumps({
        "quality_status": "PASS",
        "summary": {
            "resolver_record_count": 509,
            "auto_resolved_route_count": 150,
            "multi_route_required_count": 1,
            "validator_required_count": 1,
            "human_review_required_count": 0,
            "source_scan_pack_quality_status": "PASS",
            "primary_route_counts": {"cover_or_title_page": 1, "image_visual_diagram": 151},
            "unsafe_record_count": 0,
            "answer_permission_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        },
    }), encoding="utf-8")

    result = check_quality(report_path=report, max_image_visual_diagram_routes=80)
    assert result["quality_status"] == "FAIL"
    assert "too many image_visual_diagram primary routes" in result["failures"]
