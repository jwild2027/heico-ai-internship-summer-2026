from pathlib import Path
import json

from tiff.trace_net_vision_model_pilot_v1 import QualityThresholds, build_quality, check_vision_model_pilot_quality


def safe_report():
    return {
        "source_calibrator_summary": {"calibrated_page_count": 2},
        "summary": {
            "vision_pilot_record_count": 2,
            "selected_page_count": 2,
            "prompt_record_count": 2,
            "retrieval_only_record_count": 2,
            "visual_answer_allowed_count": 0,
            "direct_answer_allowed_count": 0,
            "claim_proof_allowed_count": 0,
            "unverified_visual_claim_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "final_answer_allowed_count": 0,
            "model_output_allowed_for_final_count": 0,
            "unsafe_vision_pilot_record_count": 0,
            "model_error_count": 0,
        },
    }


def test_quality_passes_for_safe_summary():
    q = build_quality(
        safe_report(),
        QualityThresholds(
            require_page_count=2,
            min_pilot_records=1,
            min_selected_pages=1,
            min_prompt_records=1,
            min_retrieval_only_records=1,
        ),
    )
    assert q["status"] == "PASS"


def test_quality_fails_if_visual_can_answer():
    report = safe_report()
    report["summary"]["visual_answer_allowed_count"] = 1
    q = build_quality(report, QualityThresholds(min_pilot_records=1, min_selected_pages=1, min_prompt_records=1, min_retrieval_only_records=1))
    assert q["status"] == "FAIL"


def test_quality_cli_helper_reads_report(tmp_path: Path):
    p = tmp_path / "report.json"
    p.write_text(json.dumps(safe_report()), encoding="utf-8")
    result = check_vision_model_pilot_quality(
        report_path=p,
        thresholds=QualityThresholds(min_pilot_records=1, min_selected_pages=1, min_prompt_records=1, min_retrieval_only_records=1),
        write_json_quality=True,
    )
    assert result["status"] == "PASS"
    assert (tmp_path / "trace_net_vision_model_pilot_v1_quality.json").exists()
