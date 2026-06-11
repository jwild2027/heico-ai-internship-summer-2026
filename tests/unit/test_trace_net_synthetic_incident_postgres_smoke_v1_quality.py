from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_synthetic_incident_postgres_smoke_v1 import check_quality_file


def test_check_quality_file_writes_json(tmp_path: Path) -> None:
    report_path = tmp_path / "trace_net_synthetic_incident_postgres_smoke_v1.json"
    report_path.write_text(
        json.dumps(
            {
                "status": "POSTGRES_SMOKE_RAN",
                "summary": {
                    "storage_mode": "postgres",
                    "postgres_table": "trace_net_synthetic_incident_events",
                    "inserted_incident_count": 1,
                    "created_incident_found_count": 1,
                    "unsafe_incident_count": 0,
                    "source_truth_mutation_allowed_count": 0,
                    "raw_feedback_direct_to_llm_count": 0,
                    "affects_real_pipeline_count": 0,
                },
            }
        ),
        encoding="utf-8",
    )
    quality = check_quality_file(report_path, min_inserted_incidents=1, write_json_report=True)
    assert quality["status"] == "PASS"
    assert (tmp_path / "trace_net_synthetic_incident_postgres_smoke_v1_quality.json").exists()


def test_check_quality_file_fails_unsafe(tmp_path: Path) -> None:
    report_path = tmp_path / "trace_net_synthetic_incident_postgres_smoke_v1.json"
    report_path.write_text(
        json.dumps(
            {
                "status": "POSTGRES_SMOKE_RAN",
                "summary": {
                    "storage_mode": "postgres",
                    "postgres_table": "trace_net_synthetic_incident_events",
                    "inserted_incident_count": 1,
                    "created_incident_found_count": 1,
                    "unsafe_incident_count": 1,
                    "source_truth_mutation_allowed_count": 0,
                    "raw_feedback_direct_to_llm_count": 0,
                    "affects_real_pipeline_count": 0,
                },
            }
        ),
        encoding="utf-8",
    )
    quality = check_quality_file(report_path, min_inserted_incidents=1)
    assert quality["status"] == "FAIL"
