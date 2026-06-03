import json
from pathlib import Path

from tiff.trace_net_regression_report_quality import run_quality


def test_quality_passes_valid_summary(tmp_path):
    summary = {
        "status": "OK",
        "case_count": 2,
        "case_fail_count": 0,
        "review_case_count": 1,
        "unsafe_answer_case_count": 0,
        "weighted_unsafe_case_count": 0,
        "source_truth_mutation_case_count": 0,
        "context_warning_used_case_count": 0,
        "top_changed_case_count": 1,
        "tie_case_count": 0,
        "graph_nodes": 3,
        "graph_edges": 2,
    }
    summary_path = tmp_path / "regression_summary.json"
    records_path = tmp_path / "regression_records.jsonl"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    records_path.write_text(json.dumps({"case_id": "a"}) + "\n" + json.dumps({"case_id": "b"}) + "\n", encoding="utf-8")

    quality = run_quality(summary_path, records_path, tmp_path / "quality.json", min_cases=2, write_json=True)

    assert quality["status"] == "OK"
    assert quality["regression_cases"] == 2
    assert (tmp_path / "quality.json").exists()


def test_quality_fails_unsafe_cases(tmp_path):
    summary = {
        "status": "OK",
        "case_count": 1,
        "case_fail_count": 0,
        "review_case_count": 0,
        "unsafe_answer_case_count": 1,
        "weighted_unsafe_case_count": 0,
        "source_truth_mutation_case_count": 0,
        "context_warning_used_case_count": 0,
        "graph_nodes": 1,
        "graph_edges": 0,
    }
    summary_path = tmp_path / "regression_summary.json"
    records_path = tmp_path / "regression_records.jsonl"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    records_path.write_text(json.dumps({"case_id": "a"}) + "\n", encoding="utf-8")

    quality = run_quality(summary_path, records_path, tmp_path / "quality.json", max_unsafe_answer_cases=0)

    assert quality["status"] == "FAIL"
    assert any(c["name"] == "unsafe_answer_cases" and not c["ok"] for c in quality["checks"])
