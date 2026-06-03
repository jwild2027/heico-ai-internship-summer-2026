import json
from pathlib import Path

from tiff.trace_net_regression_report import RegressionPaths, build_regression_report


def write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


def write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def make_case(root: Path, name: str, *, top_before: str, top_after: str, unsafe: int = 0, weighted_unsafe: int = 0, scores=None):
    case = root / name
    write_json(case / "ask_summary.json", {"status": "OK", "query": name, "feedback_mode": "off", "stage_failures": 0})
    write_json(case / "answer_summary.json", {"status": "OK", "answer_page_records": 2, "answer_evidence_records": 3, "unsafe_answer_groups": unsafe, "groups_with_citations": 2})
    write_json(case / "search_summary.json", {"status": "OK", "result_records": 3})
    write_json(case / "grouped_summary.json", {"status": "OK", "grouped_page_records": 2, "supporting_result_records": 3, "unsafe_grouped_records": 0, "excluded_grouped_records": 0, "groups_with_multiple_buckets": 1})
    write_json(case / "weighted_search_summary.json", {
        "status": "OK",
        "top_page_before": top_before,
        "top_page_after": top_after,
        "weighted_group_records": 2,
        "rank_changed_records": 1 if top_before != top_after else 0,
        "unsafe_weighted_records": weighted_unsafe,
        "excluded_weighted_records": 0,
        "source_truth_mutation_records": 0,
        "context_warning_signals_used": 0,
        "weights_policy_version": "trace_net_weights_policy_v1",
    })
    scores = scores or [10.0, 9.0]
    write_jsonl(case / "weighted_search_results.jsonl", [{"page_id": f"p{i}", "weighted_score": s} for i, s in enumerate(scores)])


def test_build_report_summarizes_fixed_cases(tmp_path):
    root = tmp_path / "fixed_set_v1"
    out = tmp_path / "report"
    make_case(root, "case_ok", top_before="p1", top_after="p1")
    make_case(root, "case_top_changed", top_before="p1", top_after="p2", scores=[7.0, 7.0, 7.0])

    result = build_regression_report(RegressionPaths(regression_dir=root, output_dir=out))
    summary = result["summary"]

    assert summary["status"] == "OK"
    assert summary["case_records"] == 2
    assert summary["failed_cases"] == 0
    assert summary["top_page_changed_cases"] == 1
    assert summary["tie_heavy_cases"] >= 1
    assert (out / "trace_net_regression_report_summary.json").exists()
    assert (out / "trace_net_regression_report_cases.jsonl").exists()
    assert (out / "trace_net_regression_report.html").exists()


def test_build_report_marks_blocking_failures(tmp_path):
    root = tmp_path / "fixed_set_v1"
    out = tmp_path / "report"
    make_case(root, "unsafe_case", top_before="p1", top_after="p1", unsafe=1)

    result = build_regression_report(RegressionPaths(regression_dir=root, output_dir=out))
    summary = result["summary"]

    assert summary["status"] == "FAIL"
    assert summary["failed_cases"] == 1
    records = (out / "trace_net_regression_report_cases.jsonl").read_text(encoding="utf-8")
    assert "unsafe_answer" in records or "unsafe_answer_groups" in records
