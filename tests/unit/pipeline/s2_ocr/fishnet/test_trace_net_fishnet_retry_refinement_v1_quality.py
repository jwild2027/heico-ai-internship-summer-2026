from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_fishnet_retry_refinement_v1 import (
    build_fishnet_retry_refinement,
    check_fishnet_retry_refinement_quality,
    evaluate_quality,
)

from test_trace_net_fishnet_retry_refinement_v1 import sample_report


def test_quality_fails_when_actual_retry_pages_not_less_than_count() -> None:
    summary = {
        "refined_fishnet_record_count": 2,
        "baseline_validation_page_count": 2,
        "actual_retry_page_count": 2,
        "missing_page_id_count": 0,
        "unsafe_refined_record_count": 0,
        "unsafe_refined_action_count": 0,
        "direct_answer_allowed_count": 0,
        "claim_proof_allowed_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "final_answer_allowed_count": 0,
        "confirmed_blank_pages_with_visual_retry_count": 0,
        "text_heavy_pages_with_vision_retry_count": 0,
        "unknown_table_pages_with_table_answer_retry_count": 0,
    }
    quality = evaluate_quality(summary, require_actual_retry_less_than_page_count=True)
    assert quality["status"] == "FAIL"


def test_quality_fails_on_blank_visual_retry() -> None:
    summary = {
        "refined_fishnet_record_count": 2,
        "baseline_validation_page_count": 2,
        "actual_retry_page_count": 1,
        "missing_page_id_count": 0,
        "unsafe_refined_record_count": 0,
        "unsafe_refined_action_count": 0,
        "direct_answer_allowed_count": 0,
        "claim_proof_allowed_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "final_answer_allowed_count": 0,
        "confirmed_blank_pages_with_visual_retry_count": 1,
        "text_heavy_pages_with_vision_retry_count": 0,
        "unknown_table_pages_with_table_answer_retry_count": 0,
    }
    quality = evaluate_quality(summary)
    assert quality["status"] == "FAIL"


def test_quality_check_reads_written_report(tmp_path: Path) -> None:
    source = tmp_path / "fishnet.json"
    source.write_text(json.dumps(sample_report()), encoding="utf-8")
    out = tmp_path / "out"
    build_fishnet_retry_refinement(source, out, require_page_count=3, write_quality=True)
    quality = check_fishnet_retry_refinement_quality(
        out / "trace_net_fishnet_retry_refinement_v1.json",
        require_page_count=3,
        min_refined_records=3,
        min_baseline_validation_pages=3,
        require_actual_retry_less_than_page_count=True,
        write_json_flag=True,
    )
    assert quality["status"] == "PASS"
    assert (out / "trace_net_fishnet_retry_refinement_v1_quality.json").exists()
