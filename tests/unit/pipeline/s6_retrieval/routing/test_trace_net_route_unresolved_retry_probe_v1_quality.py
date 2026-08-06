import json

from tiff.trace_net_route_unresolved_retry_probe_v1 import (
    build_route_unresolved_retry_probe,
    check_route_unresolved_retry_probe_quality,
)


def test_quality_checker_passes_thresholds(tmp_path):
    source = tmp_path / "source.json"
    source.write_text(json.dumps({
        "quality_status": "PASS",
        "records": [
            {
                "page_id": "p1",
                "page_number": 1,
                "source_operational_route": "table",
                "validation_decision": "validator_gated_unresolved",
                "validation_status": "VALIDATOR_GATED_UNRESOLVED",
                "final_do_not_embed": True,
                "ocr_word_count": 200,
                "part_number_count": 12,
                "ocr_sample_text": "120-12345-001 ASSY NUMBER CH-SEC-UN-FIG ITEM NOMENCLATURE",
            }
        ],
    }), encoding="utf-8")
    out = tmp_path / "out"
    build_route_unresolved_retry_probe(route_validator_runner_path=source, output_dir=out, quality=True)

    result = check_route_unresolved_retry_probe_quality(
        report_path=out / "trace_net_route_unresolved_retry_probe_v1.json",
        min_records=1,
        min_final_validated=1,
        min_retry_validated=1,
        require_source_quality_pass=True,
        require_no_human_review_required=True,
        require_decision_files=True,
        require_four_validated_routes_only=True,
        max_unsafe=0,
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
        require_no_write_attempts=True,
        write_json=True,
    )
    assert result["quality_status"] == "PASS"
    assert (out / "trace_net_route_unresolved_retry_probe_v1_quality_check.json").exists()


def test_quality_checker_fails_remaining_cap(tmp_path):
    source = tmp_path / "source.json"
    source.write_text(json.dumps({
        "quality_status": "PASS",
        "records": [
            {
                "page_id": "p1",
                "page_number": 1,
                "source_operational_route": "plain_text",
                "validation_decision": "validator_gated_unresolved",
                "validation_status": "VALIDATOR_GATED_UNRESOLVED",
                "final_do_not_embed": True,
                "ocr_word_count": 3,
                "part_number_count": 0,
                "ocr_sample_text": "noise ?",
            }
        ],
    }), encoding="utf-8")
    out = tmp_path / "out"
    build_route_unresolved_retry_probe(route_validator_runner_path=source, output_dir=out, quality=True)

    result = check_route_unresolved_retry_probe_quality(
        report_path=out / "trace_net_route_unresolved_retry_probe_v1.json",
        min_records=1,
        min_final_validated=0,
        max_remaining_unresolved=0,
    )
    assert result["quality_status"] == "FAIL"
