from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_fishnet_retry_engine_v1 import (
    check_trace_net_fishnet_retry_engine_quality,
)


def test_quality_check_reads_report_and_writes_json(tmp_path: Path) -> None:
    report = tmp_path / "trace_net_fishnet_retry_engine_v1.json"
    payload = {
        "summary": {
            "fishnet_record_count": 2,
            "pages_with_retry_plan_count": 2,
            "pages_with_review_count": 1,
            "pages_with_retry_count": 1,
            "extractor_family_count": 5,
            "table_retry_action_count": 1,
            "visual_retry_action_count": 1,
            "ocr_retry_action_count": 1,
            "unsafe_fishnet_record_count": 0,
            "direct_answer_allowed_count": 0,
            "claim_proof_allowed_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "final_answer_allowed_count": 0,
            "missing_page_id_count": 0,
        }
    }
    report.write_text(json.dumps(payload), encoding="utf-8")

    quality = check_trace_net_fishnet_retry_engine_quality(
        report_path=report,
        require_page_count=2,
        min_fishnet_records=2,
        min_pages_with_retry_plan=2,
        min_pages_with_review_or_retry=1,
        min_extractor_family_count=4,
        min_table_retry_actions=1,
        min_visual_retry_actions=1,
        min_ocr_retry_actions=1,
        write_json_quality=True,
    )
    assert quality["status"] == "PASS"
    assert report.with_name("trace_net_fishnet_retry_engine_v1_quality.json").exists()


def test_quality_check_fails_when_source_truth_mutation_allowed(tmp_path: Path) -> None:
    report = tmp_path / "trace_net_fishnet_retry_engine_v1.json"
    payload = {
        "summary": {
            "fishnet_record_count": 2,
            "pages_with_retry_plan_count": 2,
            "extractor_family_count": 5,
            "unsafe_fishnet_record_count": 0,
            "direct_answer_allowed_count": 0,
            "claim_proof_allowed_count": 0,
            "source_truth_mutation_allowed_count": 1,
            "final_answer_allowed_count": 0,
            "missing_page_id_count": 0,
        }
    }
    report.write_text(json.dumps(payload), encoding="utf-8")
    quality = check_trace_net_fishnet_retry_engine_quality(report_path=report, require_page_count=2, min_fishnet_records=2, min_pages_with_retry_plan=2)
    assert quality["status"] == "FAIL"

