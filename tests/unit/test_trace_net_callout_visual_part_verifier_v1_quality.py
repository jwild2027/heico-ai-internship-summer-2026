import json
from pathlib import Path

from tiff.trace_net_callout_visual_part_verifier_v1 import evaluate_quality, quality_report


def test_evaluate_quality_fails_when_answer_allowed() -> None:
    summary = {
        "callout_verifier_record_count": 1,
        "clean_callout_count": 1,
        "random_number_suppressed_count": 0,
        "callout_to_table_row_link_count": 0,
        "catalog_verified_visual_part_count": 0,
        "records_with_graph_attachment_plan_count": 1,
        "unsafe_visual_evidence_count": 0,
        "visual_answer_allowed_count": 1,
        "unverified_visual_claim_count": 1,
        "source_truth_mutation_allowed_count": 0,
    }
    quality = evaluate_quality(summary)
    assert quality["status"] == "FAIL"


def test_quality_report_writes_json(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps({
        "summary": {
            "callout_verifier_record_count": 2,
            "clean_callout_count": 3,
            "random_number_suppressed_count": 1,
            "callout_to_table_row_link_count": 1,
            "catalog_verified_visual_part_count": 1,
            "records_with_graph_attachment_plan_count": 2,
            "unsafe_visual_evidence_count": 0,
            "visual_answer_allowed_count": 0,
            "unverified_visual_claim_count": 0,
            "source_truth_mutation_allowed_count": 0,
        }
    }), encoding="utf-8")
    quality = quality_report(report_path=report_path, write_json_report=True, quality_config={"min_clean_callouts": 1})
    assert quality["status"] == "PASS"
    assert (tmp_path / "trace_net_callout_visual_part_verifier_v1_quality.json").exists()
