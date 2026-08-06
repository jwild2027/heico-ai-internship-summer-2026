import json
from pathlib import Path

from tiff.trace_net_route_confidence_resolver_v1 import build_route_confidence_resolver, check_quality


def test_header_footer_identity_does_not_steal_content_page(tmp_path):
    scan = tmp_path / "scan.json"
    scan.write_text(json.dumps({"quality_status": "PASS", "records": [
        {
            "page_id": "header_only_content",
            "canonical_page_number": 26,
            "accepted_route": "normal_text",
            "ocr_sample_text": "T.P. 120/1176 Jan 15/01 25-21-00 page footer EMBRAER",
            "ocr_text_word_count": 20,
            "part_number_tokens": [],
        },
        {
            "page_id": "real_cover",
            "canonical_page_number": 1,
            "accepted_route": "table",
            "ocr_sample_text": "Passenger Seats Component Maintenance Manual Revision 4 T.P. 120/1176",
            "ocr_text_word_count": 12,
            "part_number_tokens": [],
        },
    ]}), encoding="utf-8")

    out = tmp_path / "out"
    payload = build_route_confidence_resolver(scan_pack=scan, output_dir=out, quality=True)
    records = {r["page_id"]: r for r in payload["records"]}

    assert records["real_cover"]["primary_route"] == "cover_or_title_page"
    assert records["header_only_content"]["primary_route"] != "cover_or_title_page"
    assert records["header_only_content"]["signal_counts"]["weak_cover_header_term_count"] >= 1
    assert records["header_only_content"]["signal_counts"]["strong_cover_term_count"] == 0


def test_quality_can_gate_cover_route_count(tmp_path):
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
            "primary_route_counts": {"cover_or_title_page": 109},
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

    result = check_quality(report_path=report, max_cover_or_title_page_routes=50)
    assert result["quality_status"] == "FAIL"
    assert "too many cover_or_title_page primary routes" in result["failures"]
