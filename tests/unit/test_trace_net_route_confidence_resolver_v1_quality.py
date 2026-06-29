import json
from pathlib import Path

from tiff.trace_net_route_confidence_resolver_v1 import build_route_confidence_resolver, check_quality


def test_quality_check_passes_with_required_flags(tmp_path):
    scan = tmp_path / "scan.json"
    scan.write_text(json.dumps({"quality_status": "PASS", "records": [
        {"page_id": "p", "canonical_page_number": 1, "accepted_route": "blank_candidate", "ocr_sample_text": "", "ocr_text_word_count": 0, "part_number_tokens": []}
    ]}), encoding="utf-8")
    out = tmp_path / "out"
    build_route_confidence_resolver(scan_pack=scan, output_dir=out, quality=True)
    result = check_quality(
        report_path=out / "trace_net_route_confidence_resolver_v1.json",
        write_json=True,
        min_records=1,
        require_source_quality_pass=True,
        require_no_human_review_required=True,
        max_unsafe=0,
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
        require_no_write_attempts=True,
    )
    assert result["quality_status"] == "PASS"
    assert (out / "trace_net_route_confidence_resolver_v1_quality_check.json").exists()


def test_quality_check_fails_when_auto_resolved_requirement_not_met(tmp_path):
    report = tmp_path / "report.json"
    report.write_text(json.dumps({
        "quality_status": "PASS",
        "summary": {"resolver_record_count": 1, "auto_resolved_route_count": 0, "human_review_required_count": 0, "source_scan_pack_quality_status": "PASS"},
    }), encoding="utf-8")
    result = check_quality(report_path=report, min_auto_resolved=1)
    assert result["quality_status"] == "FAIL"
