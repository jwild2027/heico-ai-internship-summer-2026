from pathlib import Path
import json

from tiff.trace_net_fast_chat_multi_route_quality_gate_v1 import (
    check_fast_chat_multi_route_quality_gate_quality,
)


def _write_gate(path: Path, summary):
    payload = {"quality_status": "PASS", "summary": summary}
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_quality_check_passes(tmp_path: Path):
    report = _write_gate(tmp_path / "gate.json", {
        "route_check_count": 5,
        "violation_record_count": 0,
        "multi_route_quality_gate_passed": True,
        "webui_answer_ready": True,
        "query_type": "figure_or_item",
        "human_review_required_count": 0,
        "manual_review_required_count": 0,
        "unsafe_record_count": 0,
        "answer_permission_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "write_attempt_count": 0,
    })
    result = check_fast_chat_multi_route_quality_gate_quality(
        report_path=report,
        min_checks=3,
        max_violations=0,
        require_multi_route_quality_pass=True,
        require_webui_answer_ready=True,
        require_figure_item_query=True,
        require_no_human_review_required=True,
        max_unsafe=0,
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
        require_no_write_attempts=True,
    )
    assert result["quality_status"] == "PASS"


def test_quality_check_fails_wrong_query_type(tmp_path: Path):
    report = _write_gate(tmp_path / "gate.json", {
        "route_check_count": 5,
        "violation_record_count": 0,
        "multi_route_quality_gate_passed": True,
        "webui_answer_ready": True,
        "query_type": "part_family",
    })
    result = check_fast_chat_multi_route_quality_gate_quality(report_path=report, require_figure_item_query=True)
    assert result["quality_status"] == "FAIL"
