from __future__ import annotations

import argparse
import json
from pathlib import Path

from tiff.trace_net_table_understanding_v1 import check_table_understanding_quality, quality_checks


def base_summary() -> dict:
    return {
        "table_understanding_record_count": 2,
        "pages_with_structured_cells_count": 2,
        "cell_count": 10,
        "table_type_assigned_count": 2,
        "source_trace_table_count": 2,
        "missing_page_id_count": 0,
        "uncited_answer_capable_table_count": 0,
        "retrieval_only_table_answer_allowed_count": 0,
        "unsafe_table_evidence_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "final_answer_allowed_count": 0,
    }


def test_quality_checks_pass() -> None:
    args = argparse.Namespace(
        min_table_records=1,
        min_pages_with_structured_cells=1,
        min_cell_records=1,
        min_table_types_assigned=1,
        min_source_trace_tables=1,
        max_missing_page_id=0,
        max_uncited_answer_capable_tables=0,
    )
    status, checks = quality_checks(base_summary(), args)
    assert status == "PASS"
    assert all(check["ok"] for check in checks)


def test_quality_checks_fail_on_unsafe() -> None:
    summary = base_summary()
    summary["unsafe_table_evidence_count"] = 1
    status, checks = quality_checks(summary, argparse.Namespace())
    assert status == "FAIL"
    assert any(check["name"] == "unsafe_table_evidence" and not check["ok"] for check in checks)


def test_quality_file_write(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps({"summary": base_summary()}), encoding="utf-8")
    payload = check_table_understanding_quality(report_path=report_path, write_json_flag=True, quality_args=argparse.Namespace())
    assert payload["status"] == "PASS"
    assert (tmp_path / "trace_net_table_understanding_v1_quality.json").exists()
