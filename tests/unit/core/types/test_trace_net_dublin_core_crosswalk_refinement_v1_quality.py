import json
from pathlib import Path

from tiff.trace_net_dublin_core_crosswalk_refinement_v1 import quality_report


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_quality_report_passes_minimums(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    write_json(
        report,
        {
            "summary": {
                "page_record_count": 2,
                "records_with_physical_element_counts": 2,
                "records_with_operational_element_counts": 2,
                "records_with_review_summary": 2,
                "blank_pages_with_low_physical_count": 1,
                "missing_clean_dc_type_count": 0,
                "clean_overbroad_dc_type_count": 0,
                "direct_answer_allowed_count": 0,
                "claim_proof_allowed_count": 0,
                "source_truth_mutation_allowed_count": 0,
                "postgres_write_attempt_count": 0,
                "qdrant_write_attempt_count": 0,
                "opensearch_write_attempt_count": 0,
            }
        },
    )
    quality = quality_report(
        report_path=report,
        quality_config={
            "require_page_count": 2,
            "min_records_with_physical_counts": 2,
            "min_records_with_operational_counts": 2,
            "min_records_with_review_summary": 2,
            "min_blank_pages_with_low_physical": 1,
            "max_clean_overbroad_dc_type": 0,
        },
    )
    assert quality["status"] == "PASS"


def test_quality_report_writes_json(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    write_json(
        report,
        {
            "summary": {
                "page_record_count": 1,
                "records_with_physical_element_counts": 1,
                "records_with_operational_element_counts": 1,
                "records_with_review_summary": 1,
                "missing_clean_dc_type_count": 0,
                "direct_answer_allowed_count": 0,
                "claim_proof_allowed_count": 0,
                "source_truth_mutation_allowed_count": 0,
                "postgres_write_attempt_count": 0,
                "qdrant_write_attempt_count": 0,
                "opensearch_write_attempt_count": 0,
            }
        },
    )
    quality = quality_report(report_path=report, write_json_report=True)
    assert quality["status"] == "PASS"
    assert Path(quality["quality_path"]).exists()
