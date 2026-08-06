from __future__ import annotations

import argparse
import json
from pathlib import Path

from tiff.trace_net_table_cell_normalizer_v1 import check_trace_net_table_cell_normalizer_quality, quality_checks


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_quality_checks_pass_for_safe_summary() -> None:
    summary = {
        "normalized_table_record_count": 20,
        "normalized_row_count": 100,
        "normalized_cell_count": 200,
        "part_number_merge_candidate_count": 3,
        "answer_support_row_count": 5,
        "unsafe_table_evidence_count": 0,
        "uncited_answer_capable_row_count": 0,
        "retrieval_only_answer_allowed_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "final_answer_allowed_count": 0,
    }
    args = argparse.Namespace(
        min_normalized_table_records=20,
        min_normalized_rows=100,
        min_normalized_cells=200,
        min_part_number_merge_candidates=1,
        min_answer_support_rows=1,
    )
    checks = quality_checks(summary, args)
    assert all(c["passed"] for c in checks)


def test_quality_checks_fail_for_unsafe_summary() -> None:
    summary = {
        "normalized_table_record_count": 1,
        "normalized_row_count": 1,
        "normalized_cell_count": 1,
        "part_number_merge_candidate_count": 0,
        "answer_support_row_count": 0,
        "unsafe_table_evidence_count": 1,
        "uncited_answer_capable_row_count": 1,
        "retrieval_only_answer_allowed_count": 1,
        "source_truth_mutation_allowed_count": 1,
        "final_answer_allowed_count": 1,
    }
    args = argparse.Namespace(
        min_normalized_table_records=1,
        min_normalized_rows=1,
        min_normalized_cells=1,
        min_part_number_merge_candidates=0,
        min_answer_support_rows=0,
    )
    checks = quality_checks(summary, args)
    failed = {c["name"] for c in checks if not c["passed"]}
    assert "unsafe_table_evidence_zero" in failed
    assert "uncited_answer_capable_rows_zero" in failed
    assert "source_truth_mutation_allowed_zero" in failed


def test_quality_main_writes_json(tmp_path: Path) -> None:
    report_path = tmp_path / "trace_net_table_cell_normalizer_v1.json"
    write_json(report_path, {
        "summary": {
            "normalized_table_record_count": 1,
            "normalized_row_count": 1,
            "normalized_cell_count": 1,
            "part_number_merge_candidate_count": 0,
            "answer_support_row_count": 0,
            "unsafe_table_evidence_count": 0,
            "uncited_answer_capable_row_count": 0,
            "retrieval_only_answer_allowed_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "final_answer_allowed_count": 0,
        }
    })
    args = argparse.Namespace(
        min_normalized_table_records=1,
        min_normalized_rows=1,
        min_normalized_cells=1,
        min_part_number_merge_candidates=0,
        min_answer_support_rows=0,
    )
    result = check_trace_net_table_cell_normalizer_quality(report_path=report_path, args=args, write_json_flag=True)
    assert result["status"] == "PASS"
    assert Path(result["quality_path"]).exists()
