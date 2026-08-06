import json

from tiff.trace_net_ask_quality import evaluate_trace_net_ask_quality


def test_trace_net_ask_quality_ok_default_off(tmp_path):
    summary = {
        "status": "OK",
        "version": "trace_net_ask_v1_1_feedback_mode",
        "effective_query": "120-50645-009",
        "options": {"feedback_mode": "off"},
        "stages": [
            {"name": "search", "status": "OK"},
            {"name": "citations", "status": "OK"},
            {"name": "group", "status": "OK"},
            {"name": "answer", "status": "OK"},
        ],
        "summary": {"answer_page_records": 3, "answer_evidence_records": 8, "unsafe_answer_groups": 0},
        "artifacts": {"answer_md": "answer.md"},
    }
    path = tmp_path / "trace_net_ask_summary.json"
    path.write_text(json.dumps(summary), encoding="utf-8")
    report = evaluate_trace_net_ask_quality(path, min_answer_pages=1, min_evidence_records=1, require_feedback_mode="off")
    assert report["status"] == "OK"


def test_trace_net_ask_quality_ok_feedback_simulate(tmp_path):
    summary = {
        "status": "OK",
        "version": "trace_net_ask_v1_1_feedback_mode",
        "effective_query": "120-50645-009",
        "options": {"feedback_mode": "simulate"},
        "stages": [
            {"name": "search", "status": "OK"},
            {"name": "citations", "status": "OK"},
            {"name": "group", "status": "OK"},
            {"name": "answer", "status": "OK"},
            {"name": "feedback_search_simulation", "status": "OK"},
            {"name": "feedback_ask_simulation", "status": "OK"},
        ],
        "summary": {
            "answer_page_records": 3,
            "answer_evidence_records": 8,
            "unsafe_answer_groups": 0,
            "feedback_ask_status": "OK",
            "feedback_ask_feedback_signals_used": 2,
            "feedback_ask_groups_adjusted": 2,
            "feedback_ask_rank_changed_records": 2,
            "feedback_ask_answer_changed": True,
            "feedback_ask_unsafe_groups": 0,
            "feedback_ask_context_warning_signals_used": 0,
        },
        "artifacts": {"answer_md": "answer.md", "feedback_ask_simulation_html": "sim.html"},
    }
    path = tmp_path / "trace_net_ask_summary.json"
    path.write_text(json.dumps(summary), encoding="utf-8")
    report = evaluate_trace_net_ask_quality(
        path,
        require_feedback_mode="simulate",
        require_feedback_simulation=True,
        min_feedback_signals_used=1,
        min_feedback_groups_adjusted=1,
        min_feedback_rank_changed_records=1,
        require_feedback_answer_changed=True,
    )
    assert report["status"] == "OK"


def test_trace_net_ask_quality_fails_on_unsafe(tmp_path):
    summary = {
        "status": "OK",
        "version": "trace_net_ask_v1_1_feedback_mode",
        "effective_query": "x",
        "options": {"feedback_mode": "off"},
        "stages": [{"name": n, "status": "OK"} for n in ["search", "citations", "group", "answer"]],
        "summary": {"answer_page_records": 1, "answer_evidence_records": 1, "unsafe_answer_groups": 1},
        "artifacts": {"answer_html": "answer.html"},
    }
    path = tmp_path / "trace_net_ask_summary.json"
    path.write_text(json.dumps(summary), encoding="utf-8")
    report = evaluate_trace_net_ask_quality(path, max_unsafe_answer_groups=0)
    assert report["status"] == "FAIL"


def test_trace_net_ask_quality_fails_if_simulation_required_but_missing(tmp_path):
    summary = {
        "status": "OK",
        "version": "trace_net_ask_v1_1_feedback_mode",
        "effective_query": "x",
        "options": {"feedback_mode": "simulate"},
        "stages": [{"name": n, "status": "OK"} for n in ["search", "citations", "group", "answer"]],
        "summary": {"answer_page_records": 1, "answer_evidence_records": 1, "unsafe_answer_groups": 0},
        "artifacts": {"answer_html": "answer.html"},
    }
    path = tmp_path / "trace_net_ask_summary.json"
    path.write_text(json.dumps(summary), encoding="utf-8")
    report = evaluate_trace_net_ask_quality(path, require_feedback_simulation=True)
    assert report["status"] == "FAIL"
