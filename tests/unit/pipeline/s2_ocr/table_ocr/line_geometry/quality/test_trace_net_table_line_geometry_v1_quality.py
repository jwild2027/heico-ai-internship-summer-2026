from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_table_line_geometry_v1_quality import check_report


def test_quality_checker_passes_clean_report(tmp_path: Path) -> None:
    report_path = tmp_path / "trace_net_table_line_geometry_v1.json"
    report = {
        "quality_status": "PASS",
        "summary": {
            "schema_version": "trace_net_table_line_geometry_v1",
            "source_quality_status": "PASS",
            "table_geometry_card_count": 2,
            "cell_record_count": 10,
            "row_record_count": 4,
            "image_line_detection_card_count": 1,
            "unsafe_geometry_card_count": 0,
            "answer_permission_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        },
    }
    report_path.write_text(json.dumps(report), encoding="utf-8")

    quality = check_report(
        report_path,
        {
            "min_table_geometry_cards": 1,
            "min_cell_records": 1,
            "min_row_records": 1,
            "max_unsafe_geometry_cards": 0,
            "require_no_answer_permission": True,
        },
        write_json_flag=True,
    )

    assert quality["quality_status"] == "PASS"
    assert quality["checks"]["answer_permission_zero"] is True
    assert (tmp_path / "trace_net_table_line_geometry_v1_quality.json").exists()


def test_quality_checker_fails_unsafe_report(tmp_path: Path) -> None:
    report_path = tmp_path / "trace_net_table_line_geometry_v1.json"
    report = {
        "summary": {
            "schema_version": "trace_net_table_line_geometry_v1",
            "source_quality_status": "PASS",
            "table_geometry_card_count": 1,
            "cell_record_count": 1,
            "row_record_count": 0,
            "image_line_detection_card_count": 0,
            "unsafe_geometry_card_count": 1,
            "answer_permission_count": 1,
            "can_answer_directly_count": 1,
            "can_prove_claims_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        },
    }
    report_path.write_text(json.dumps(report), encoding="utf-8")

    quality = check_report(
        report_path,
        {
            "min_table_geometry_cards": 1,
            "max_unsafe_geometry_cards": 0,
            "max_answer_permission_count": 0,
            "require_no_answer_permission": True,
        },
    )

    assert quality["quality_status"] == "FAIL"
    assert quality["quality_errors"]
